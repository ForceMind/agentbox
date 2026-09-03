"""Concrete Runtime executor for the shared WAW supervisor seam.

This adapter owns no browser authority.  It binds trusted Runtime command and
transport factories to one exact workspace generation and keeps the resulting
supervisor alive until positive stop evidence is observed.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any, TypeVar

from agentbox_core.waw import (
    AgentType,
    WAWDomainError,
    WorkspaceStopOperation,
    validate_binding_digest,
    validate_positive_u64,
    validate_project_id,
    validate_runtime_host_installation_id,
    validate_workspace_id,
)
from agentbox_core.waw_tickets import ActiveAttachment, AttachmentTuple

from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.project import ConfiguredProject, ProjectRegistry
from agentbox_runtime.waw_lifecycle import (
    WAWLifecycleIdentity,
    WAWLifecycleObservation,
    WAWProjectBinding,
)
from agentbox_runtime.waw_managed_command import (
    WAWManagedCommand,
    managed_command_agent_type,
    validate_managed_command,
)
from agentbox_runtime.waw_pty import PtyGeometry
from agentbox_runtime.waw_stream_bridge import WAWStreamBridge
from agentbox_runtime.waw_supervisor import (
    RuntimeProbeEvidence,
    SupervisorState,
    WAWSupervisor,
    WAWTransport,
)


@dataclass(frozen=True)
class _SupervisorKey:
    workspace_id: str
    project_id: str
    agent_type: str
    generation: str
    binding_revision: str
    binding_digest: str
    runtime_host_installation_id: str
    runtime_host_installation_revision: str
    runtime_epoch: str


@dataclass(frozen=True)
class _StartSnapshot:
    binding: tuple[WAWProjectBinding, ConfiguredProject]
    prior: tuple[tuple[_SupervisorKey, WAWSupervisor], ...]


CommandFactory = Callable[[WAWLifecycleIdentity, ConfiguredProject], WAWManagedCommand]
TransportFactory = Callable[[WAWLifecycleIdentity, WAWManagedCommand], WAWTransport]
_T = TypeVar("_T")


class WAWSupervisorExecutor:
    """Run exact identity-bound supervisors behind the lifecycle executor port."""

    def __init__(
        self,
        *,
        runtime_epoch: str,
        project_registry: ProjectRegistry,
        command_factory: CommandFactory,
        transport_factory: TransportFactory,
        geometry: PtyGeometry,
        clock: Callable[[], float],
        attachment_validator: Callable[[ActiveAttachment], bool],
    ) -> None:
        if (
            not isinstance(runtime_epoch, str)
            or not runtime_epoch.isascii()
            or not runtime_epoch.isdecimal()
            or runtime_epoch.startswith("0")
        ):
            raise RuntimeOperationError(
                "WAW_RUNTIME_EPOCH_INVALID", "Runtime epoch is invalid", category="validation"
            )
        validate_positive_u64(int(runtime_epoch), field="runtime_epoch")
        self._runtime_epoch = runtime_epoch
        self._projects = project_registry
        self._command_factory = command_factory
        self._transport_factory = transport_factory
        self._geometry = geometry
        self._clock = clock
        self._attachment_validator = attachment_validator
        self._supervisors: dict[_SupervisorKey, WAWSupervisor] = {}
        self._bindings: dict[str, tuple[WAWProjectBinding, ConfiguredProject]] = {}
        self._map_lock = threading.RLock()
        self._inflight: dict[str, asyncio.Task[Any]] = {}
        self._inflight_project_ids: dict[str, str] = {}
        self._inflight_tokens: dict[str, object] = {}
        self._binding_inflight: dict[str, asyncio.Task[Any]] = {}
        self._binding_reserved: set[str] = set()

    async def register_project_binding(self, binding: WAWProjectBinding) -> None:
        """Resolve and commit one Runtime Project binding without wire changes."""

        if type(binding) is not WAWProjectBinding:
            raise RuntimeOperationError(
                "WAW_BINDING_INVALID", "Project binding type is invalid", category="validation"
            )
        project_id = self._binding_field(binding, "project_id")
        with self._map_lock:
            current = self._bindings.get(project_id)
            if current is not None and current[0] == binding:
                return
            if project_id in self._binding_inflight or project_id in self._binding_reserved:
                raise RuntimeOperationError(
                    "WAW_OPERATION_BUSY",
                    "Project binding update is already in progress",
                    category="conflict",
                )
            if current is not None and int(current[0].binding_revision) == int(
                binding.binding_revision
            ):
                raise RuntimeOperationError(
                    "PROJECT_IDENTITY_CHANGED",
                    "Binding revision was reused with different identity",
                    category="conflict",
                )
            if project_id in self._inflight_project_ids.values():
                raise RuntimeOperationError(
                    "WAW_OPERATION_BUSY",
                    "Project operation is already in progress",
                    category="conflict",
                )
            self._binding_reserved.add(project_id)
            task = asyncio.create_task(asyncio.to_thread(self._resolve_binding, binding))
            self._binding_inflight[project_id] = task
        try:
            project = await asyncio.shield(task)
        except asyncio.CancelledError:
            task.add_done_callback(
                lambda finished: self._clear_binding_cancelled(project_id, finished)
            )
            raise
        except BaseException:
            if task.done():
                self._consume_binding_task(project_id, task)
                with self._map_lock:
                    self._binding_reserved.discard(project_id)
            else:
                task.add_done_callback(
                    lambda finished: self._clear_binding_cancelled(project_id, finished)
                )
            raise
        with self._map_lock:
            current = self._bindings.get(project_id)
            if current is not None and int(current[0].binding_revision) >= int(
                binding.binding_revision
            ):
                if current[0] != binding:
                    self._consume_binding_task(project_id, task)
                    self._binding_reserved.discard(project_id)
                    raise RuntimeOperationError(
                        "PROJECT_IDENTITY_CHANGED", "Project binding is stale", category="conflict"
                    )
                self._consume_binding_task(project_id, task)
                self._binding_reserved.discard(project_id)
                return
        # Resolution checked every existing supervisor off the event loop.
        # The reservation prevents new starts until this synchronous commit;
        # another await here would create a cancellation/commit gap.
        with self._map_lock:
            self._bindings[project_id] = (binding, project)
            self._binding_reserved.discard(project_id)
        self._consume_binding_task(project_id, task)

    async def start(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        key = self._key(identity)
        operation_token = object()

        def operation() -> WAWLifecycleObservation:
            start_snapshot = self._start_snapshot(key, operation_token)
            command = self._command(identity, start_snapshot.binding)
            transport = self._transport_factory(identity, command)
            supervisor = WAWSupervisor(
                workspace_id=key.workspace_id,
                generation=int(key.generation),
                command=command,
                transport=transport,
                geometry=self._geometry,
                clock=self._clock,
                attachment_validator=self._attachment_validator,
                stop_binding=self._stop_binding(identity),
                runtime_epoch=self._runtime_epoch,
            )
            self._commit_start(key, supervisor, start_snapshot, operation_token)
            snapshot = supervisor.start()
            return self._start_observation(snapshot.state)

        return await self._submit(key, operation, operation_token=operation_token)

    async def status(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        return await self._probe(identity)

    async def reconcile(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        return await self._probe(identity)

    async def stop(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        key = self._key(identity)

        def operation() -> WAWLifecycleObservation:
            with self._map_lock:
                supervisor = self._supervisors.get(key)
            if supervisor is None:
                raise RuntimeOperationError(
                    "WAW_WORKSPACE_NOT_FOUND",
                    "Exact workspace supervisor is unavailable",
                    category="conflict",
                )
            snapshot = supervisor.exact_stop(self._stop_binding(identity))
            if snapshot.state is not SupervisorState.STOPPED:
                raise RuntimeOperationError(
                    "WAW_STOP_UNCONFIRMED",
                    "Exact stop did not reach STOPPED",
                    category="conflict",
                )
            return self._observation(SupervisorState.STOPPED, process_state="STOPPED")

        return await self._submit(key, operation)

    def bridge(
        self, identity: WAWLifecycleIdentity, attachment: ActiveAttachment
    ) -> WAWStreamBridge:
        """Construct a bridge over the exact supervisor without admitting it."""

        key = self._key(identity)
        with self._map_lock:
            pending = self._inflight.get(key.workspace_id)
            if pending is not None and not pending.done():
                raise RuntimeOperationError(
                    "WAW_OPERATION_BUSY",
                    "Workspace operation is already in progress",
                    category="conflict",
                )
            supervisor = self._supervisors.get(key)
            if supervisor is None:
                raise RuntimeOperationError(
                    "WAW_WORKSPACE_NOT_FOUND",
                    "Exact workspace supervisor is unavailable",
                    category="conflict",
                )
        return WAWStreamBridge(supervisor, attachment)

    def encrypted_supervisor(self, claims: AttachmentTuple) -> WAWSupervisor:
        """Resolve the exact running generation for the fixed encrypted service."""
        identity = WAWLifecycleIdentity(
            workspace_id=claims.workspace_id,
            project_id=claims.project_id,
            agent_type=str(claims.agent_type),
            generation=str(claims.generation),
            binding_revision=str(claims.binding_revision),
            binding_digest=claims.binding_digest,
            runtime_host_installation_id=claims.runtime_host_installation_id,
            runtime_host_installation_revision=str(claims.runtime_host_installation_revision),
        )
        key = self._key(identity)
        with self._map_lock:
            pending = self._inflight.get(key.workspace_id)
            if pending is not None and not pending.done():
                raise RuntimeOperationError(
                    "WAW_OPERATION_BUSY", "Workspace operation is pending", category="conflict"
                )
            supervisor = self._supervisors.get(key)
            if supervisor is None or not self._encrypted_binding_current_locked(claims):
                raise RuntimeOperationError(
                    "WAW_ATTACHMENT_STALE",
                    "Exact Runtime binding is unavailable",
                    category="conflict",
                )
            return supervisor

    def encrypted_binding_current(self, claims: AttachmentTuple) -> bool:
        """Current registered binding predicate, called inside the attachment fence."""
        with self._map_lock:
            return self._encrypted_binding_current_locked(claims)

    def _encrypted_binding_current_locked(self, claims: AttachmentTuple) -> bool:
        bound = self._bindings.get(claims.project_id)
        if bound is None or claims.project_id in self._binding_reserved:
            return False
        binding = bound[0]
        return (
            binding.project_id == claims.project_id
            and binding.binding_revision == str(claims.binding_revision)
            and binding.binding_digest == claims.binding_digest
            and binding.runtime_host_installation_id == claims.runtime_host_installation_id
            and binding.runtime_host_installation_revision
            == str(claims.runtime_host_installation_revision)
        )

    async def _probe(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        key = self._key(identity)

        def operation() -> WAWLifecycleObservation:
            with self._map_lock:
                supervisor = self._supervisors.get(key)
            if supervisor is None:
                raise RuntimeOperationError(
                    "WAW_WORKSPACE_NOT_FOUND",
                    "Exact workspace supervisor is unavailable",
                    category="conflict",
                )
            evidence = supervisor.probe()
            if evidence.workspace_id != key.workspace_id or evidence.generation != int(
                key.generation
            ):
                raise RuntimeOperationError(
                    "WAW_PROBE_IDENTITY_MISMATCH",
                    "Runtime probe identity is stale",
                    category="conflict",
                )
            return self._probe_observation(evidence)

        return await self._submit(key, operation)

    def _resolve_binding(self, binding: WAWProjectBinding) -> ConfiguredProject:
        validate_project_id(self._binding_field(binding, "project_id"))
        self._binding_decimal(binding, "project_revision")
        self._binding_decimal(binding, "binding_revision")
        validate_binding_digest(self._binding_field(binding, "binding_digest"))
        validate_runtime_host_installation_id(
            self._binding_field(binding, "runtime_host_installation_id")
        )
        self._binding_decimal(binding, "runtime_host_installation_revision")
        relative_key = self._binding_field(binding, "relative_key")
        project = self._projects.resolve(relative_key)
        if self._project_has_live_supervisor(self._binding_field(binding, "project_id")):
            raise RuntimeOperationError(
                "RECONCILIATION_REQUIRED",
                "Project binding cannot change while a workspace is live",
                category="conflict",
            )
        return project

    def _project_has_live_supervisor(self, project_id: str) -> bool:
        with self._map_lock:
            supervisors = [
                supervisor
                for key, supervisor in self._supervisors.items()
                if key.project_id == project_id
            ]
        return any(supervisor.state is not SupervisorState.STOPPED for supervisor in supervisors)

    @staticmethod
    def _binding_field(binding: WAWProjectBinding, name: str) -> str:
        value = getattr(binding, name, None)
        if not isinstance(value, str) or not value:
            raise RuntimeOperationError(
                "WAW_BINDING_INVALID", "Project binding is invalid", category="validation"
            )
        return value

    @classmethod
    def _binding_decimal(cls, binding: WAWProjectBinding, name: str) -> str:
        value = cls._binding_field(binding, name)
        if not value.isascii() or not value.isdecimal() or value.startswith("0"):
            raise RuntimeOperationError(
                "WAW_BINDING_INVALID", "Project binding number is invalid", category="validation"
            )
        try:
            validate_positive_u64(int(value), field=name)
        except WAWDomainError as exc:
            raise RuntimeOperationError(
                "WAW_BINDING_INVALID", "Project binding number is invalid", category="validation"
            ) from exc
        return value

    def _command(
        self,
        identity: WAWLifecycleIdentity,
        bound: tuple[WAWProjectBinding, ConfiguredProject],
    ) -> WAWManagedCommand:
        binding, registered_project = bound
        if (
            int(binding.binding_revision) != int(self._field(identity, "binding_revision"))
            or binding.binding_digest != self._field(identity, "binding_digest")
            or binding.runtime_host_installation_id
            != self._field(identity, "runtime_host_installation_id")
            or int(binding.runtime_host_installation_revision)
            != int(self._field(identity, "runtime_host_installation_revision"))
        ):
            raise RuntimeOperationError(
                "WAW_COMMAND_IDENTITY_MISMATCH",
                "Runtime binding does not match identity",
                category="conflict",
            )
        resolved = self._projects.resolve(binding.relative_key)
        if resolved != registered_project:
            raise RuntimeOperationError(
                "WAW_PROJECT_CHANGED", "Registered Project path changed", category="conflict"
            )
        command = validate_managed_command(self._command_factory(identity, resolved))
        if (
            command.workspace_id != self._field(identity, "workspace_id")
            or command.project_id != self._field(identity, "project_id")
            or command.cwd != resolved.path
            or managed_command_agent_type(command).value != self._field(identity, "agent_type")
        ):
            raise RuntimeOperationError(
                "WAW_COMMAND_IDENTITY_MISMATCH",
                "Runtime command does not match Project identity",
                category="validation",
            )
        return command

    def _stop_binding(self, identity: WAWLifecycleIdentity) -> WorkspaceStopOperation:
        return WorkspaceStopOperation(
            workspace_id=self._field(identity, "workspace_id"),
            project_id=self._field(identity, "project_id"),
            agent_type=AgentType(self._field(identity, "agent_type")),
            generation=int(self._field(identity, "generation")),
            binding_revision=int(self._field(identity, "binding_revision")),
            binding_digest=self._field(identity, "binding_digest"),
            runtime_host_installation_id=self._field(identity, "runtime_host_installation_id"),
            runtime_host_installation_revision=int(
                self._field(identity, "runtime_host_installation_revision")
            ),
        )

    def _key(self, identity: WAWLifecycleIdentity) -> _SupervisorKey:
        if type(identity) is not WAWLifecycleIdentity:
            raise RuntimeOperationError(
                "WAW_IDENTITY_INVALID", "Runtime identity type is invalid", category="validation"
            )
        fields = {
            name: self._field(identity, name)
            for name in (
                "workspace_id",
                "project_id",
                "agent_type",
                "generation",
                "binding_revision",
                "binding_digest",
                "runtime_host_installation_id",
                "runtime_host_installation_revision",
            )
        }
        try:
            validate_workspace_id(fields["workspace_id"])
            validate_project_id(fields["project_id"])
            validate_binding_digest(fields["binding_digest"])
            validate_runtime_host_installation_id(fields["runtime_host_installation_id"])
            AgentType(fields["agent_type"])
            for name in ("generation", "binding_revision", "runtime_host_installation_revision"):
                value = fields[name]
                if not value.isascii() or not value.isdecimal() or value.startswith("0"):
                    raise ValueError(name)
                validate_positive_u64(int(value), field=name)
        except (TypeError, ValueError, WAWDomainError) as exc:
            raise RuntimeOperationError(
                "WAW_IDENTITY_INVALID", "Runtime identity is invalid", category="validation"
            ) from exc
        self._stop_binding(identity)
        return _SupervisorKey(**fields, runtime_epoch=self._runtime_epoch)

    @staticmethod
    def _field(identity: WAWLifecycleIdentity, name: str) -> str:
        value = getattr(identity, name, None)
        if not isinstance(value, str) or not value:
            raise RuntimeOperationError(
                "WAW_IDENTITY_INVALID", "Runtime identity is invalid", category="validation"
            )
        return value

    async def _submit(
        self,
        key: _SupervisorKey,
        operation: Callable[[], _T],
        *,
        operation_token: object | None = None,
    ) -> _T:
        workspace_id = key.workspace_id
        token = object() if operation_token is None else operation_token
        with self._map_lock:
            existing = self._inflight.get(workspace_id)
            if existing is not None and not existing.done():
                raise RuntimeOperationError(
                    "WAW_OPERATION_BUSY",
                    "Workspace operation is already in progress",
                    category="conflict",
                )
            task: asyncio.Task[_T] = asyncio.create_task(asyncio.to_thread(operation))
            self._inflight[workspace_id] = task
            self._inflight_project_ids[workspace_id] = key.project_id
            self._inflight_tokens[workspace_id] = token
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # Keep the worker alive until its bounded operation finishes; a
            # cancellation must never permit overlapping transport effects.
            task.add_done_callback(lambda finished: self._clear_inflight(workspace_id, finished))
            raise
        finally:
            if task.done():
                self._clear_inflight(workspace_id, task)

    def _clear_inflight(self, workspace_id: str, task: asyncio.Task[Any]) -> None:
        if not task.cancelled():
            task.exception()
        with self._map_lock:
            if self._inflight.get(workspace_id) is task:
                self._inflight.pop(workspace_id, None)
                self._inflight_project_ids.pop(workspace_id, None)
                self._inflight_tokens.pop(workspace_id, None)

    def _consume_binding_task(self, project_id: str, task: asyncio.Task[Any]) -> None:
        if not task.cancelled():
            task.exception()
        with self._map_lock:
            if self._binding_inflight.get(project_id) is task:
                self._binding_inflight.pop(project_id, None)

    def _clear_binding_cancelled(self, project_id: str, task: asyncio.Task[Any]) -> None:
        self._consume_binding_task(project_id, task)
        with self._map_lock:
            self._binding_reserved.discard(project_id)

    def _start_snapshot(self, key: _SupervisorKey, operation_token: object) -> _StartSnapshot:
        with self._map_lock:
            self._assert_start_map_locked(key)
            self._assert_start_inflight_locked(key, operation_token)
            binding = self._bindings.get(key.project_id)
            if binding is None:
                raise RuntimeOperationError(
                    "WAW_BINDING_REQUIRED",
                    "Project binding is not registered",
                    category="conflict",
                )
            if not self._binding_matches_key(binding[0], key):
                raise RuntimeOperationError(
                    "WAW_COMMAND_IDENTITY_MISMATCH",
                    "Runtime binding does not match identity",
                    category="conflict",
                )
            prior = tuple(
                (prior_key, supervisor)
                for prior_key, supervisor in self._supervisors.items()
                if prior_key.workspace_id == key.workspace_id
            )
        for prior_key, supervisor in prior:
            with supervisor.stopped_generation_guard(self._operation_for_key(prior_key)):
                pass
        return _StartSnapshot(binding, prior)

    def _commit_start(
        self,
        key: _SupervisorKey,
        supervisor: WAWSupervisor,
        start_snapshot: _StartSnapshot,
        operation_token: object,
    ) -> None:
        # Runtime attachment guards acquire supervisor then map. Hold every old
        # state lock in the same order through the map replacement so a late
        # cleanup cannot invalidate STOPPED after the final check.
        with ExitStack() as guards:
            for prior_key, prior in start_snapshot.prior:
                guards.enter_context(
                    prior.stopped_generation_guard(self._operation_for_key(prior_key))
                )
            with self._map_lock:
                self._assert_start_map_locked(key)
                self._assert_start_inflight_locked(key, operation_token)
                current_binding = self._bindings.get(key.project_id)
                if current_binding is not start_snapshot.binding or not self._binding_matches_key(
                    current_binding[0], key
                ):
                    raise RuntimeOperationError(
                        "WAW_COMMAND_IDENTITY_MISMATCH",
                        "Runtime binding changed during start",
                        category="conflict",
                    )
                current_prior = {
                    prior_key: prior
                    for prior_key, prior in self._supervisors.items()
                    if prior_key.workspace_id == key.workspace_id
                }
                expected_prior = dict(start_snapshot.prior)
                if current_prior.keys() != expected_prior.keys() or any(
                    current_prior[prior_key] is not prior
                    for prior_key, prior in start_snapshot.prior
                ):
                    raise RuntimeOperationError(
                        "RECONCILIATION_REQUIRED",
                        "Workspace generation changed during start",
                        category="conflict",
                    )
                self._supervisors = {
                    prior_key: prior
                    for prior_key, prior in self._supervisors.items()
                    if prior_key.workspace_id != key.workspace_id
                }
                self._supervisors[key] = supervisor

    def _assert_start_map_locked(self, key: _SupervisorKey) -> None:
        if key.project_id in self._binding_reserved or key.project_id in self._binding_inflight:
            raise RuntimeOperationError(
                "WAW_OPERATION_BUSY",
                "Project binding update is in progress",
                category="conflict",
            )
        if key in self._supervisors:
            raise RuntimeOperationError(
                "WAW_START_INVALID",
                "Workspace generation is already registered",
                category="conflict",
            )
        if any(
            prior_key.workspace_id == key.workspace_id
            and int(prior_key.generation) >= int(key.generation)
            for prior_key in self._supervisors
        ):
            raise RuntimeOperationError(
                "WAW_GENERATION_STALE",
                "Workspace generation is not strictly newer",
                category="conflict",
            )

    def _assert_start_inflight_locked(self, key: _SupervisorKey, operation_token: object) -> None:
        if (
            key.workspace_id not in self._inflight
            or self._inflight_project_ids.get(key.workspace_id) != key.project_id
            or self._inflight_tokens.get(key.workspace_id) is not operation_token
        ):
            raise RuntimeOperationError(
                "WAW_OPERATION_BUSY",
                "Workspace start reservation changed",
                category="conflict",
            )

    @staticmethod
    def _binding_matches_key(binding: WAWProjectBinding, key: _SupervisorKey) -> bool:
        return (
            binding.project_id == key.project_id
            and binding.binding_revision == key.binding_revision
            and binding.binding_digest == key.binding_digest
            and binding.runtime_host_installation_id == key.runtime_host_installation_id
            and binding.runtime_host_installation_revision == key.runtime_host_installation_revision
        )

    @staticmethod
    def _operation_for_key(key: _SupervisorKey) -> WorkspaceStopOperation:
        return WorkspaceStopOperation(
            workspace_id=key.workspace_id,
            project_id=key.project_id,
            agent_type=AgentType(key.agent_type),
            generation=int(key.generation),
            binding_revision=int(key.binding_revision),
            binding_digest=key.binding_digest,
            runtime_host_installation_id=key.runtime_host_installation_id,
            runtime_host_installation_revision=int(key.runtime_host_installation_revision),
        )

    def _start_observation(self, state: SupervisorState) -> WAWLifecycleObservation:
        process_state = "NOT_STARTED" if state is SupervisorState.LOGIN_REQUIRED else "RUNNING"
        return self._observation(state, process_state=process_state)

    def _observation(
        self, state: SupervisorState, *, process_state: str
    ) -> WAWLifecycleObservation:
        return WAWLifecycleObservation(
            state=state.value,
            reconciliation_state="authoritative",
            process_state=process_state,
            runtime_epoch=self._runtime_epoch,
        )

    def _probe_observation(self, evidence: RuntimeProbeEvidence) -> WAWLifecycleObservation:
        state = evidence.state.value
        process_state = (
            "STOPPED"
            if state in {"STOPPED", "EXITED"}
            else (
                "NOT_STARTED"
                if state == "MISSING"
                else (
                    "UNKNOWN"
                    if state in {"COLLISION", "UNKNOWN"}
                    else "NOT_STARTED" if state == "LOGIN_REQUIRED" else "RUNNING"
                )
            )
        )
        reconciliation = {
            "MISSING": "missing",
            "COLLISION": "collision",
            "UNKNOWN": "unknown",
            "EXITED": "exited",
        }.get(state, "authoritative")
        return WAWLifecycleObservation(
            state=state,
            reconciliation_state=reconciliation,
            process_state=process_state,
            exit_code=evidence.exit_code if state == "EXITED" else None,
            runtime_epoch=self._runtime_epoch,
        )


__all__ = ["WAWSupervisorExecutor"]
