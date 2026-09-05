"""Bounded Runtime lifecycle registry for Web Agent Workspace control actions.

This module is the typed seam between the WAW control socket and a future
Runtime adapter.  It owns binding/generation fencing and lifecycle metadata;
it never accepts a path, command, argv, PID, signal, tmux target, or secret.
The side-effecting adapter is injected and receives only an immutable identity.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import math
import re
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, replace
from typing import Any, Protocol, cast, runtime_checkable

from agentbox_core.waw import AgentType
from agentbox_core.waw_recovery import RecoveryError, ResumeHint
from agentbox_protocol.waw_control import WAWControlError, binding_inventory_digest

from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_cgroup_attestation import (
    WAWCgroupAttestation,
    verify_waw_cgroup_attestation_context,
)
from agentbox_runtime.waw_cgroup_attestation_store import (
    WAWCgroupAttestationStore,
    WAWCgroupAttestationStoreError,
)
from agentbox_runtime.waw_control_server import WAWControlDispatchError
from agentbox_runtime.waw_encrypted_stream import (
    EncryptedStreamError,
    RuntimePeer,
    WAWEncryptedAttachmentService,
)
from agentbox_runtime.waw_peer_authority import (
    WAWPeerAuthority,
    WAWPeerAuthorityError,
    WAWPeerBindStatus,
    WAWPeerCandidate,
    WAWPeerLease,
    WAWPeerTransferPlan,
)
from agentbox_runtime.waw_project_binding_store import (
    WAWDurableProjectBinding,
    WAWProjectBindingStore,
    WAWProjectBindingStoreError,
    WAWProjectBindingVerifier,
    WAWProjectBindingVerifierError,
)
from agentbox_runtime.waw_workspace_attestation import (
    WAWWorkspaceAttestationError,
    WAWWorkspaceAttestationStore,
)

_BIND = "workspace.api_authority.bind"
_REGISTER = "workspace.project_binding.register"
_FINALIZE_INVENTORY = "workspace.project_binding.inventory.finalize.v1"
_START = "workspace.workspace.start"
_STOP = "workspace.workspace.stop"
_STATUS = "workspace.workspace.status"
_RECONCILE = "workspace.workspace.reconcile"
_EVIDENCE = "workspace.workspace.executable_evidence.v1"
_ATTACH_PREPARE = "workspace.attach.prepare"
_ATTACH_DETACH = "workspace.attach.detach"
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_DECIMAL = re.compile(r"\A(?:0|[1-9][0-9]{0,19})\Z")
_POS_DECIMAL = re.compile(r"\A[1-9][0-9]{0,19}\Z")
_STATES = frozenset(
    {
        "STARTING",
        "RUNNING",
        "NEEDS_INTERACTION",
        "TRUST_REQUIRED",
        "LOGIN_REQUIRED",
        "STOPPING",
        "EXITED",
        "STOPPED",
        "MISSING",
        "COLLISION",
        "BROKEN",
        "UNKNOWN",
    }
)
_RECONCILIATION_STATES = frozenset(
    {
        "authoritative",
        "stopping",
        "missing",
        "collision",
        "exited",
        "reconciliation_required",
        "unknown",
    }
)
_PROCESS_STATES = _STATES | {"NOT_STARTED"}
_MAX_U64 = 2**64 - 1
_MAX_DETACHED_CLEANUPS = 32
_SUPPORTED_AGENT_TYPES = frozenset(agent.value for agent in AgentType)
_BOOTSTRAP_ACTIONS = frozenset({_BIND, _REGISTER, _FINALIZE_INVENTORY})

# Runtime observations are deliberately stricter than the underlying provider
# API.  An ambiguous process/lifecycle pair must never be exposed as healthy.
_OBSERVATION_PROCESS_STATES: dict[str, frozenset[str]] = {
    "STARTING": frozenset({"RUNNING", "NOT_STARTED"}),
    "RUNNING": frozenset({"RUNNING"}),
    "NEEDS_INTERACTION": frozenset({"RUNNING"}),
    "TRUST_REQUIRED": frozenset({"RUNNING"}),
    "LOGIN_REQUIRED": frozenset({"NOT_STARTED"}),
    "STOPPING": frozenset({"RUNNING", "STOPPED"}),
    "EXITED": frozenset({"STOPPED"}),
    "STOPPED": frozenset({"STOPPED"}),
    "MISSING": frozenset({"NOT_STARTED"}),
    "COLLISION": frozenset({"UNKNOWN"}),
    "BROKEN": frozenset({"UNKNOWN"}),
    "UNKNOWN": frozenset({"UNKNOWN"}),
}
_OBSERVATION_RECONCILIATION_STATES: dict[str, frozenset[str]] = {
    "STARTING": frozenset({"authoritative", "stopping"}),
    "RUNNING": frozenset({"authoritative"}),
    "NEEDS_INTERACTION": frozenset({"authoritative"}),
    "TRUST_REQUIRED": frozenset({"authoritative"}),
    "LOGIN_REQUIRED": frozenset({"authoritative"}),
    "STOPPING": frozenset({"stopping", "authoritative"}),
    "EXITED": frozenset({"exited", "authoritative"}),
    "STOPPED": frozenset({"authoritative"}),
    "MISSING": frozenset({"missing"}),
    "COLLISION": frozenset({"collision"}),
    "BROKEN": frozenset({"reconciliation_required", "unknown"}),
    "UNKNOWN": frozenset({"reconciliation_required", "unknown"}),
}


@dataclass(frozen=True)
class WAWLifecycleIdentity:
    workspace_id: str
    project_id: str
    agent_type: str
    generation: str
    binding_revision: str
    binding_digest: str
    runtime_host_installation_id: str
    runtime_host_installation_revision: str


@dataclass(frozen=True)
class WAWLifecycleObservation:
    """Runtime evidence returned by an injected, already-fenced adapter."""

    state: str
    reconciliation_state: str = "authoritative"
    process_state: str = "RUNNING"
    exit_code: int | None = None
    runtime_epoch: str = "1"


class WAWLifecycleExecutor(Protocol):
    async def start(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation: ...

    async def stop(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation: ...

    async def status(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation: ...

    async def reconcile(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation: ...


BindingDigestFactory = Callable[[dict[str, Any]], str | Awaitable[str]]
CgroupAttestationFactory = Callable[
    [WAWLifecycleIdentity, WAWLifecycleObservation],
    WAWCgroupAttestation | Awaitable[WAWCgroupAttestation],
]


@dataclass(frozen=True)
class WAWProjectBinding:
    """Internal canonical Project binding; relative_key is root-resolved only."""

    project_id: str
    relative_key: str
    project_revision: str
    binding_revision: str
    binding_digest: str
    runtime_host_installation_id: str
    runtime_host_installation_revision: str


@runtime_checkable
class WAWProjectBindingConsumer(Protocol):
    async def register_project_binding(self, binding: WAWProjectBinding) -> None: ...


@runtime_checkable
class WAWExecutableEvidenceProvider(Protocol):
    """Return an exact Runtime-observed executable fingerprint for one generation."""

    async def executable_evidence(self, identity: WAWLifecycleIdentity) -> str: ...


class WAWLifecycleRegistry:
    """Serialize and fence Runtime lifecycle dispatch for one host instance."""

    def __init__(
        self,
        *,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: str,
        host_manifest_digest: str,
        project_root_manifest_digest: str,
        enrollment_epoch: str = "1",
        enrollment_state: str = "steady",
        executor: WAWLifecycleExecutor | None = None,
        binding_digest_factory: BindingDigestFactory | None = None,
        binding_verifier: WAWProjectBindingVerifier | None = None,
        binding_store: WAWProjectBindingStore | None = None,
        runtime_epoch: str = "1",
        attestation_store: WAWWorkspaceAttestationStore | None = None,
        cgroup_attestation_store: WAWCgroupAttestationStore | None = None,
        cgroup_attestation_factory: CgroupAttestationFactory | None = None,
        cgroup_attestation_timeout_seconds: float = 2.0,
        cleanup_timeout_seconds: float = 2.0,
        peer_authority: WAWPeerAuthority | None = None,
    ) -> None:
        if not isinstance(runtime_epoch, str) or _POS_DECIMAL.fullmatch(runtime_epoch) is None:
            raise ValueError("runtime_epoch must be a canonical positive decimal")
        if int(runtime_epoch) > _MAX_U64:
            raise ValueError("runtime_epoch exceeds uint64")
        self._host_id = runtime_host_installation_id
        self._host_revision = runtime_host_installation_revision
        self._host_manifest_digest = host_manifest_digest
        self._project_root_manifest_digest = project_root_manifest_digest
        self._enrollment_epoch = enrollment_epoch
        self._enrollment_state = enrollment_state
        self._runtime_epoch = runtime_epoch
        self._executor = executor
        if (binding_verifier is None) != (binding_store is None):
            raise ValueError("binding verifier and durable store must be provided together")
        if binding_verifier is not None and binding_digest_factory is not None:
            raise ValueError("binding verifier replaces the digest factory")
        self._binding_digest_factory = binding_digest_factory
        self._binding_verifier = binding_verifier
        self._binding_store = binding_store
        self._binding_resources_closed = binding_verifier is None
        self._attestation_store = attestation_store
        if (cgroup_attestation_store is None) != (cgroup_attestation_factory is None):
            raise ValueError(
                "cgroup_attestation_store and cgroup_attestation_factory must be provided together"
            )
        self._cgroup_attestation_store = cgroup_attestation_store
        self._cgroup_attestation_factory = cgroup_attestation_factory
        if (
            isinstance(cgroup_attestation_timeout_seconds, bool)
            or not isinstance(cgroup_attestation_timeout_seconds, (int, float))
            or not math.isfinite(float(cgroup_attestation_timeout_seconds))
            or cgroup_attestation_timeout_seconds <= 0
        ):
            raise ValueError("cgroup_attestation_timeout_seconds must be positive")
        self._cgroup_attestation_timeout_seconds = float(cgroup_attestation_timeout_seconds)
        if (
            isinstance(cleanup_timeout_seconds, bool)
            or not isinstance(cleanup_timeout_seconds, (int, float))
            or not math.isfinite(float(cleanup_timeout_seconds))
            or cleanup_timeout_seconds <= 0
        ):
            raise ValueError("cleanup_timeout_seconds must be positive")
        self._cleanup_timeout_seconds = float(cleanup_timeout_seconds)
        if peer_authority is not None and type(peer_authority) is not WAWPeerAuthority:
            raise TypeError("peer_authority must be WAWPeerAuthority")
        self._peer_authority = peer_authority
        self._detached_cleanup_tasks: set[asyncio.Task[Any]] = set()
        self._detached_cleanup_identities: dict[asyncio.Task[Any], WAWLifecycleIdentity] = {}
        self._cleanup_quarantine: set[str] = set()
        self._authority: tuple[str, str] | None = None
        self._bindings: dict[str, WAWProjectBinding] = {}
        self._durable_bindings: dict[str, WAWDurableProjectBinding] = {}
        self._hydrated_bindings: set[str] = set()
        self._workspaces: dict[str, tuple[WAWLifecycleIdentity, WAWLifecycleObservation]] = {}
        self._attachments: dict[str, dict[str, Any]] = {}
        self._generation_floor: dict[str, int] = {}
        self._recovered_generation_floor: dict[str, int] = {}
        self._request_cache: OrderedDict[str, tuple[str, dict[str, Any]]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._encrypted_attachments: WAWEncryptedAttachmentService | None = None
        self._encrypted_operations: set[asyncio.Task[dict[str, Any]]] = set()
        self._peer_authority_identity: object | None = None
        self._authority_quarantined = False
        self._authority_quarantine_identities: list[object] = []
        self._shutting_down = False
        self._begin_shutdown_operation: asyncio.Task[None] | None = None
        self._wait_shutdown_operation: asyncio.Task[None] | None = None
        self._shutdown_failure: WAWControlDispatchError | None = None
        self._shutdown_cause: BaseException | None = None
        self._application_gate_required = False
        self._application_gate_open = True
        self._binding_replay_operation: asyncio.Task[None] | None = None
        self._binding_replay_complete = binding_store is None
        self._binding_inventory_finalized: tuple[tuple[str, str], str, str] | None = None

    def configure_encrypted_attachments(self, service: WAWEncryptedAttachmentService) -> None:
        """Install the real fixed service before serving; never replace live wiring."""
        if (
            type(service) is not WAWEncryptedAttachmentService
            or service.registry.runtime_epoch != self._runtime_epoch
            or self._encrypted_attachments is not None
            or self._attachments
        ):
            raise ValueError("encrypted attachment service cannot be installed")
        self._encrypted_attachments = service

    @property
    def peer_authority(self) -> WAWPeerAuthority | None:
        return self._peer_authority

    @property
    def shutdown_clean(self) -> bool:
        begin = self._begin_shutdown_operation
        wait = self._wait_shutdown_operation
        authority = self._peer_authority
        return (
            self._shutting_down
            and self._shutdown_failure is None
            and begin is not None
            and begin.done()
            and not begin.cancelled()
            and begin.exception() is None
            and wait is not None
            and wait.done()
            and not wait.cancelled()
            and wait.exception() is None
            and not self._encrypted_operations
            and not self._detached_cleanup_tasks
            and (self._binding_replay_operation is None or self._binding_replay_operation.done())
            and not self._authority_quarantine_identities
            and self._authority is None
            and self._peer_authority_identity is None
            and self._binding_resources_closed
            and (authority is None or authority.shutdown_clean)
        )

    def configure_peer_authority(self, authority: WAWPeerAuthority) -> None:
        """Install the sole API process authority before any control mutation."""

        if (
            type(authority) is not WAWPeerAuthority
            or self._peer_authority is not None
            or self._authority is not None
            or self._request_cache
            or self._attachments
        ):
            raise ValueError("peer authority cannot be installed")
        self._peer_authority = authority

    def configure_application_gate(self) -> None:
        """Require an application-level startup commit before control mutation."""

        if (
            self._application_gate_required
            or self._authority is not None
            or self._request_cache
            or self._attachments
            or self._shutting_down
        ):
            raise ValueError("application gate cannot be configured")
        self._application_gate_required = True
        self._application_gate_open = False

    def open_application_gate(self) -> None:
        if not self._application_gate_required or self._shutting_down:
            raise RuntimeError("application gate cannot be opened")
        if self._binding_store is not None and self._binding_inventory_finalized is None:
            raise RuntimeError("binding inventory is not finalized")
        self._application_gate_open = True

    def close_application_gate(self) -> None:
        if self._application_gate_required:
            self._application_gate_open = False

    def _fence_binding_inventory(self, *, replay_incomplete: bool = False) -> None:
        if not self.binding_inventory_finalize_required:
            return
        self._application_gate_open = False
        self._binding_inventory_finalized = None
        if replay_incomplete:
            self._binding_replay_complete = False

    @property
    def application_gate_open(self) -> bool:
        return not self._application_gate_required or self._application_gate_open

    @property
    def binding_inventory_finalize_required(self) -> bool:
        """Whether production startup awaits an exact API inventory commitment."""

        return self._application_gate_required and self._binding_store is not None

    async def restore_project_binding_inventory(self) -> None:
        """Validate and replay the complete durable inventory exactly once.

        This operation runs before the Runtime listeners start.  It deliberately
        performs descriptor and executor work outside the registry mutation lock,
        then publishes the validated set atomically.  Shutdown can therefore
        fence publication and boundedly observe a cancellation-resistant executor.
        """

        operation = self._binding_replay_operation
        if operation is None:
            operation = asyncio.create_task(self._perform_binding_inventory_replay())
            self._binding_replay_operation = operation
            operation.add_done_callback(self._consume_binding_replay)
        await asyncio.shield(operation)

    async def _perform_binding_inventory_replay(self) -> None:
        store = self._binding_store
        verifier = self._binding_verifier
        if store is None:
            self._binding_replay_complete = True
            return
        if verifier is None:
            raise WAWControlDispatchError("BINDING_REPLAY_INCOMPLETE")
        try:
            durable_values = tuple(sorted(store.list_current(), key=lambda item: item.project_id))
        except WAWProjectBindingStoreError as exc:
            raise WAWControlDispatchError("BINDING_REPLAY_INCOMPLETE") from exc

        bindings: dict[str, WAWProjectBinding] = {}
        durable_bindings: dict[str, WAWDurableProjectBinding] = {}
        for durable in durable_values:
            if durable.project_id in bindings:
                raise WAWControlDispatchError("BINDING_INVENTORY_MISMATCH")
            if (
                durable.runtime_host_installation_id != self._host_id
                or durable.runtime_host_installation_revision != self._host_revision
            ):
                raise WAWControlDispatchError("BINDING_INVENTORY_MISMATCH")
            try:
                digest = verifier.binding_digest(
                    {
                        "project_id": durable.project_id,
                        "relative_key": durable.relative_key,
                        "project_revision": durable.project_revision,
                    }
                )
            except WAWProjectBindingVerifierError as exc:
                raise WAWControlDispatchError("BINDING_INVENTORY_MISMATCH") from exc
            if not hmac.compare_digest(digest, durable.binding_digest):
                raise WAWControlDispatchError("BINDING_INVENTORY_MISMATCH")
            binding = self._binding_from_durable(durable)
            try:
                await self._register_executor_binding(binding)
            except asyncio.CancelledError:
                raise
            except BaseException as exc:
                raise WAWControlDispatchError("BINDING_REPLAY_INCOMPLETE") from exc
            bindings[durable.project_id] = binding
            durable_bindings[durable.project_id] = durable

        try:
            binding_inventory_digest(
                [self._binding_inventory_item(value) for value in durable_values]
            )
        except WAWControlError as exc:
            raise WAWControlDispatchError("BINDING_INVENTORY_MISMATCH") from exc
        async with self._lock:
            if self._shutting_down:
                raise WAWControlDispatchError("BINDING_REPLAY_INCOMPLETE")
            self._bindings = bindings
            self._durable_bindings = durable_bindings
            self._hydrated_bindings = set(bindings)
            self._binding_replay_complete = True

    @staticmethod
    def _consume_binding_replay(operation: asyncio.Task[None]) -> None:
        with suppress(BaseException):
            operation.result()

    async def begin_shutdown(self) -> None:
        """Fence dispatch and revoke authority state without closing its pidfd owner."""

        self._shutting_down = True
        operation = self._begin_shutdown_operation
        if operation is None:
            operation = asyncio.create_task(self._perform_begin_shutdown())
            self._begin_shutdown_operation = operation
            operation.add_done_callback(self._shutdown_done)
        await self._await_shutdown_operation(operation)

    async def wait_shutdown_workers(self) -> None:
        """Observe all lifecycle workers after the application closes peer authority."""

        self._shutting_down = True
        operation = self._wait_shutdown_operation
        if operation is None:
            operation = asyncio.create_task(self._perform_wait_shutdown_workers())
            self._wait_shutdown_operation = operation
            operation.add_done_callback(self._shutdown_done)
        await self._await_shutdown_operation(operation)

    async def _perform_begin_shutdown(self) -> None:
        first_error: BaseException | None = None
        async with self._lock:
            identities: list[object] = []
            if self._peer_authority_identity is not None:
                identities.append(self._peer_authority_identity)
            for identity in self._authority_quarantine_identities:
                if not any(current is identity for current in identities):
                    identities.append(identity)
            service = self._encrypted_attachments
            for identity in identities:
                confirmed = service is None
                if service is not None:
                    try:
                        confirmed = service.revoke_authority(identity)
                    except Exception as exc:
                        if first_error is None:
                            first_error = exc
                        confirmed = False
                if confirmed:
                    self._release_quarantined_authority_identity(identity)
                else:
                    self._quarantine_authority_identity(identity)
                    if first_error is None:
                        first_error = WAWControlDispatchError("RUNTIME_UNAVAILABLE", retryable=True)
            self._clear_peer_authority_caches()
        if first_error is not None:
            failure = self._record_shutdown_failure(first_error)
            raise failure from self._shutdown_cause

    async def _perform_wait_shutdown_workers(self) -> None:
        async with self._lock:
            workers = {
                task
                for task in self._encrypted_operations | self._detached_cleanup_tasks
                if not task.done()
            }
            replay = self._binding_replay_operation
            if replay is not None and not replay.done():
                workers.add(replay)
        if workers:
            _done, pending = await asyncio.wait(
                workers,
                timeout=self._cleanup_timeout_seconds,
            )
            if pending:
                self._authority_quarantined = True
                self._record_shutdown_failure(
                    WAWControlDispatchError("RUNTIME_UNAVAILABLE", retryable=True)
                )
        if self._shutdown_failure is None:
            try:
                self._close_binding_resources()
            except BaseException as exc:
                self._record_shutdown_failure(exc)
        if self._shutdown_failure is not None:
            raise self._shutdown_failure from self._shutdown_cause

    def _close_binding_resources(self) -> None:
        verifier, self._binding_verifier = self._binding_verifier, None
        store, self._binding_store = self._binding_store, None
        try:
            if verifier is not None:
                verifier.close()
            if store is not None:
                store.close()
        except (WAWProjectBindingStoreError, WAWProjectBindingVerifierError) as exc:
            raise WAWControlDispatchError("RUNTIME_UNAVAILABLE", retryable=True) from exc
        self._binding_resources_closed = True

    async def _await_shutdown_operation(self, operation: asyncio.Task[None]) -> None:
        try:
            await asyncio.shield(operation)
        except asyncio.CancelledError:
            if operation.cancelled():
                failure = self._record_shutdown_failure()
                raise failure from self._shutdown_cause
            raise
        except BaseException as exc:
            failure = self._record_shutdown_failure(exc)
            raise failure from self._shutdown_cause
        if self._shutdown_failure is not None:
            raise self._shutdown_failure from self._shutdown_cause

    def _shutdown_done(self, task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except BaseException as exc:
            self._record_shutdown_failure(exc)

    def _record_shutdown_failure(
        self, error: BaseException | None = None
    ) -> WAWControlDispatchError:
        self._authority_quarantined = True
        if self._shutdown_failure is None:
            self._shutdown_failure = WAWControlDispatchError("RUNTIME_UNAVAILABLE", retryable=True)
            self._shutdown_cause = error
        return self._shutdown_failure

    async def dispatch(
        self,
        request: dict[str, Any],
        peer: WAWPeerCandidate | WAWPeerLease | None = None,
    ) -> dict[str, Any]:
        """Dispatch one decoded control request; all mutations are serialized."""

        action = request.get("action")
        if not isinstance(action, str):
            raise WAWControlDispatchError("PROTOCOL_INVALID")
        self._require_dispatch_open(action)
        async with self._lock:
            self._require_dispatch_open(action)
            runtime_peer = self._validate_control_peer(action, peer)
            request_id = request.get("request_id")
            if not isinstance(request_id, str):
                raise WAWControlDispatchError("PROTOCOL_INVALID")
            fingerprint = json.dumps(
                request, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
            cached = self._request_cache.get(request_id)
            if (
                cached is not None
                and action != _BIND
                and not (
                    self._encrypted_attachments is not None
                    and action in {_ATTACH_PREPARE, _ATTACH_DETACH}
                )
            ):
                if cached[0] != fingerprint:
                    raise WAWControlDispatchError("PROTOCOL_INVALID")
                return dict(cached[1])
            if action == _BIND:
                response = self._bind(request, peer)
            elif action == _REGISTER:
                response = await self._register(request)
            elif action == _FINALIZE_INVENTORY:
                response = self._finalize_binding_inventory(request)
            elif action == _ATTACH_PREPARE:
                response = (
                    self._attach_prepare(request, runtime_peer)
                    if self._encrypted_attachments is None
                    else await self._encrypted_call(
                        lambda value: self._attach_prepare(value, runtime_peer), request
                    )
                )
            elif action == _ATTACH_DETACH:
                response = (
                    self._attach_detach(request, runtime_peer)
                    if self._encrypted_attachments is None
                    else await self._encrypted_call(
                        lambda value: self._attach_detach(value, runtime_peer), request
                    )
                )
            elif action == _EVIDENCE:
                response = await self._executable_evidence(request)
            elif action in {_START, _STOP, _STATUS, _RECONCILE}:
                response = await self._lifecycle(request, action)
            else:
                raise WAWControlDispatchError("PROTOCOL_INVALID")
            # A real PREPARED bearer is owned only by the capability authority;
            # never retain it in the generic request cache past burn/expiry.
            if action == _BIND or (
                self._encrypted_attachments is not None
                and action in {_ATTACH_PREPARE, _ATTACH_DETACH}
            ):
                return response
            self._request_cache[request_id] = (fingerprint, dict(response))
            self._request_cache.move_to_end(request_id)
            while len(self._request_cache) > 1024:
                self._request_cache.popitem(last=False)
            return response

    async def _encrypted_call(
        self, operation: Callable[[dict[str, Any]], dict[str, Any]], request: dict[str, Any]
    ) -> dict[str, Any]:
        """Keep bounded synchronous PTY/probe work off the control event loop.

        Cancellation never cancels a worker or frees its slot while effects may
        continue. Registry/supervisor ownership remains the exact reuse fence.
        """
        if len(self._encrypted_operations) >= 8:
            raise WAWControlDispatchError("RUNTIME_UNAVAILABLE")
        task = asyncio.create_task(asyncio.to_thread(operation, request))
        self._encrypted_operations.add(task)
        task.add_done_callback(self._encrypted_done)
        return await asyncio.shield(task)

    def _encrypted_done(self, task: asyncio.Task[dict[str, Any]]) -> None:
        self._encrypted_operations.discard(task)
        with suppress(BaseException):
            task.result()

    def _bind(
        self,
        request: dict[str, Any],
        peer: WAWPeerCandidate | WAWPeerLease | None,
    ) -> dict[str, Any]:
        if self._peer_authority is not None:
            if type(peer) not in {WAWPeerCandidate, WAWPeerLease}:
                raise WAWControlDispatchError("RUNTIME_PEER_FORBIDDEN")
            return self._bind_peer_authority(request, cast(WAWPeerCandidate | WAWPeerLease, peer))
        if self._encrypted_attachments is not None:
            try:
                self._encrypted_attachments.bind_authority(request)
            except EncryptedStreamError as exc:
                raise WAWControlDispatchError(exc.code) from None
        epoch = request["api_authority_epoch"]
        nonce = hashlib.sha256(request["authority_nonce"].encode("ascii")).hexdigest()
        current = self._authority
        if current is not None and current != (epoch, nonce):
            raise WAWControlDispatchError("RUNTIME_INSTALLATION_MISMATCH")
        self._authority = (epoch, nonce)
        return {
            "protocol_version": 1,
            "request_id": request["request_id"],
            "status": "ALREADY_BOUND" if current is not None else "BOUND",
            "api_authority_epoch": epoch,
            "runtime_epoch": self._runtime_epoch,
            "runtime_host_installation_id": self._host_id,
            "runtime_host_installation_revision": self._host_revision,
            "host_manifest_digest": self._host_manifest_digest,
            "project_root_manifest_digest": self._project_root_manifest_digest,
            "enrollment_epoch": self._enrollment_epoch,
            "enrollment_state": self._enrollment_state,
        }

    def _bind_peer_authority(
        self,
        request: dict[str, Any],
        peer: WAWPeerCandidate | WAWPeerLease,
    ) -> dict[str, Any]:
        authority = self._peer_authority
        assert authority is not None
        digest = hashlib.sha256(request["authority_nonce"].encode("ascii")).digest()
        plan: WAWPeerTransferPlan | None = None
        committed = False
        commit_attempted = False
        committed_identity = peer.runtime_peer.identity if type(peer) is WAWPeerLease else None
        possibly_published_identity: object | None = None
        try:
            plan = authority.prepare_bind(
                peer,
                api_authority_epoch=request["api_authority_epoch"],
                nonce_digest=digest,
            )
            if plan.revocation_required:
                if self._encrypted_operations:
                    raise WAWPeerAuthorityError("REVOCATION_INCOMPLETE")
                if (
                    self._encrypted_attachments is not None
                    and plan.replaces_identity is not None
                    and not self._encrypted_attachments.revoke_authority(plan.replaces_identity)
                ):
                    raise WAWPeerAuthorityError("REVOCATION_INCOMPLETE")
                self._clear_peer_authority_caches()
            if plan.status is WAWPeerBindStatus.ALREADY_BOUND:
                possibly_published_identity = committed_identity
            commit_attempted = True
            status = authority.commit_bind(plan)
            committed = True
            lease = authority.borrow()
            if lease is None:
                raise WAWPeerAuthorityError("PEER_NOT_CURRENT")
            committed_identity = lease.runtime_peer.identity
            bind_error: Exception | None = None
            try:
                if self._encrypted_attachments is not None:
                    self._encrypted_attachments.bind_authority(request, lease.runtime_peer)
            except Exception as exc:
                bind_error = exc
            try:
                lease.close()
            except Exception as exc:
                if bind_error is None:
                    bind_error = exc
            if bind_error is not None:
                raise bind_error
        except Exception as exc:
            if plan is not None and not committed:
                with suppress(WAWPeerAuthorityError):
                    authority.fail_bind(plan)
                if plan.revocation_required:
                    self._quarantine_authority_identity(plan.replaces_identity)
                    self._clear_peer_authority_caches()
            if committed or commit_attempted:
                self._authority_quarantined = True
                cleanup_identity = committed_identity if committed else possibly_published_identity
                revoked = self._encrypted_attachments is None or cleanup_identity is None
                if self._encrypted_attachments is not None and cleanup_identity is not None:
                    try:
                        revoked = self._encrypted_attachments.revoke_authority(cleanup_identity)
                    except Exception:
                        revoked = False
                if revoked:
                    self._release_quarantined_authority_identity(cleanup_identity)
                else:
                    self._quarantine_authority_identity(cleanup_identity)
                self._clear_peer_authority_caches()
                with suppress(WAWPeerAuthorityError):
                    authority.close()
                raise WAWControlDispatchError("RUNTIME_UNAVAILABLE", retryable=True) from None
            if not isinstance(exc, (WAWPeerAuthorityError, EncryptedStreamError)):
                raise
            code = exc.code
            if code in {
                "AUTHORITY_POISONED",
                "AUTHORITY_CLOSED",
                "RETIRED_EPOCHS_FULL",
                "REVOCATION_INCOMPLETE",
                "PEER_CLOSE_FAILED",
            }:
                raise WAWControlDispatchError("RUNTIME_UNAVAILABLE", retryable=True) from None
            if code in {"EPOCH_RETIRED", "AUTHORITY_CONFLICT"}:
                raise WAWControlDispatchError("RUNTIME_INSTALLATION_MISMATCH") from None
            raise WAWControlDispatchError("RUNTIME_PEER_FORBIDDEN") from None
        self._peer_authority_identity = committed_identity
        epoch = request["api_authority_epoch"]
        nonce = digest.hex()
        self._authority = (epoch, nonce)
        return {
            "protocol_version": 1,
            "request_id": request["request_id"],
            "status": status.value,
            "api_authority_epoch": epoch,
            "runtime_epoch": self._runtime_epoch,
            "runtime_host_installation_id": self._host_id,
            "runtime_host_installation_revision": self._host_revision,
            "host_manifest_digest": self._host_manifest_digest,
            "project_root_manifest_digest": self._project_root_manifest_digest,
            "enrollment_epoch": self._enrollment_epoch,
            "enrollment_state": self._enrollment_state,
        }

    def _clear_peer_authority_caches(self) -> None:
        self._authority = None
        self._peer_authority_identity = None
        self._attachments.clear()
        self._request_cache.clear()
        if self.binding_inventory_finalize_required:
            self._application_gate_open = False
            self._binding_inventory_finalized = None

    def _quarantine_authority_identity(self, identity: object | None) -> None:
        self._authority_quarantined = True
        if identity is not None and not any(
            current is identity for current in self._authority_quarantine_identities
        ):
            self._authority_quarantine_identities.append(identity)

    def _release_quarantined_authority_identity(self, identity: object | None) -> None:
        if identity is None:
            return
        self._authority_quarantine_identities = [
            current for current in self._authority_quarantine_identities if current is not identity
        ]

    async def _register(self, request: dict[str, Any]) -> dict[str, Any]:
        self._require_authority()
        if self.binding_inventory_finalize_required and not self._binding_replay_complete:
            raise WAWControlDispatchError("BINDING_REPLAY_INCOMPLETE")
        if (
            request["runtime_host_installation_id"] != self._host_id
            or request["runtime_host_installation_revision"] != self._host_revision
        ):
            raise WAWControlDispatchError("RUNTIME_INSTALLATION_MISMATCH")
        project_id = request["project_id"]
        previous = self._bindings.get(project_id)
        if previous is None:
            previous = self._hydrate_durable_binding(project_id)
        if previous is None and (
            request["binding_revision"] != "1"
            or request["previous_binding_revision"] is not None
            or request["previous_binding_digest"] is not None
        ):
            raise WAWControlDispatchError(
                "BINDING_BOOTSTRAP_REQUIRED"
                if self._binding_store is not None
                else "PROJECT_IDENTITY_CHANGED"
            )
        if (
            previous is not None
            and request["binding_revision"] != previous.binding_revision
            and (
                request["previous_binding_revision"] != previous.binding_revision
                or request["previous_binding_digest"] != previous.binding_digest
            )
        ):
            raise WAWControlDispatchError("PROJECT_IDENTITY_CHANGED")
        digest_value: object
        try:
            if self._binding_verifier is not None:
                digest_value = self._binding_verifier.binding_digest(request)
            elif self._binding_digest_factory is not None:
                digest_value = self._binding_digest_factory(request)
                if isinstance(digest_value, Awaitable):
                    digest_value = await digest_value
            else:
                raise WAWControlDispatchError("RUNTIME_UNAVAILABLE", retryable=True)
        except WAWProjectBindingVerifierError as exc:
            self._fence_binding_inventory(replay_incomplete=True)
            raise WAWControlDispatchError("RECONCILIATION_REQUIRED") from exc
        if not isinstance(digest_value, str) or not _DIGEST.fullmatch(digest_value):
            raise WAWControlDispatchError("INTERNAL_BOUNDED")
        digest = digest_value
        if previous is not None and request["binding_revision"] == previous.binding_revision:
            if (
                request["relative_key"] == previous.relative_key
                and request["project_revision"] == previous.project_revision
                and digest == previous.binding_digest
            ):
                try:
                    await self._register_executor_binding(previous)
                except asyncio.CancelledError:
                    self._fence_binding_inventory(replay_incomplete=True)
                    raise
                except BaseException as exc:
                    self._fence_binding_inventory(replay_incomplete=True)
                    raise WAWControlDispatchError("BINDING_REPLAY_INCOMPLETE") from exc
                self._hydrated_bindings.add(project_id)
                return {
                    "protocol_version": 1,
                    "request_id": request["request_id"],
                    "status": "ALREADY_CURRENT",
                    "project_id": project_id,
                    "binding_revision": previous.binding_revision,
                    "binding_digest": previous.binding_digest,
                    "runtime_host_installation_id": self._host_id,
                    "runtime_host_installation_revision": self._host_revision,
                }
            raise WAWControlDispatchError("PROJECT_IDENTITY_CHANGED")
        binding = WAWProjectBinding(
            project_id=project_id,
            relative_key=request["relative_key"],
            project_revision=request["project_revision"],
            binding_revision=request["binding_revision"],
            binding_digest=digest,
            runtime_host_installation_id=self._host_id,
            runtime_host_installation_revision=self._host_revision,
        )
        durable_binding = WAWDurableProjectBinding(
            project_id=binding.project_id,
            relative_key=binding.relative_key,
            project_revision=binding.project_revision,
            binding_revision=binding.binding_revision,
            binding_digest=binding.binding_digest,
            previous_binding_revision=request["previous_binding_revision"],
            previous_binding_digest=request["previous_binding_digest"],
            runtime_host_installation_id=binding.runtime_host_installation_id,
            runtime_host_installation_revision=binding.runtime_host_installation_revision,
        )
        try:
            await self._register_executor_binding(binding)
        except asyncio.CancelledError:
            self._fence_binding_inventory(replay_incomplete=True)
            raise
        except BaseException as exc:
            self._fence_binding_inventory(replay_incomplete=True)
            raise WAWControlDispatchError("BINDING_REPLAY_INCOMPLETE") from exc
        if self._binding_store is not None:
            try:
                durable_binding = self._binding_store.commit(durable_binding)
            except WAWProjectBindingStoreError as exc:
                self._fence_binding_inventory(replay_incomplete=True)
                raise WAWControlDispatchError("BINDING_REPLAY_INCOMPLETE") from exc
        self._bindings[project_id] = binding
        self._durable_bindings[project_id] = durable_binding
        self._hydrated_bindings.add(project_id)
        return {
            "protocol_version": 1,
            "request_id": request["request_id"],
            "status": "REGISTERED",
            "project_id": project_id,
            "binding_revision": binding.binding_revision,
            "binding_digest": digest,
            "runtime_host_installation_id": self._host_id,
            "runtime_host_installation_revision": self._host_revision,
        }

    def _hydrate_durable_binding(self, project_id: str) -> WAWProjectBinding | None:
        store = self._binding_store
        if store is None:
            return None
        try:
            durable = store.get(project_id)
        except WAWProjectBindingStoreError as exc:
            raise WAWControlDispatchError("RUNTIME_UNAVAILABLE", retryable=True) from exc
        if durable is None:
            return None
        if (
            durable.runtime_host_installation_id != self._host_id
            or durable.runtime_host_installation_revision != self._host_revision
        ):
            raise WAWControlDispatchError("RUNTIME_INSTALLATION_MISMATCH")
        binding = WAWProjectBinding(
            project_id=durable.project_id,
            relative_key=durable.relative_key,
            project_revision=durable.project_revision,
            binding_revision=durable.binding_revision,
            binding_digest=durable.binding_digest,
            runtime_host_installation_id=durable.runtime_host_installation_id,
            runtime_host_installation_revision=durable.runtime_host_installation_revision,
        )
        self._bindings[project_id] = binding
        self._durable_bindings[project_id] = durable
        return binding

    @staticmethod
    def _binding_from_durable(durable: WAWDurableProjectBinding) -> WAWProjectBinding:
        return WAWProjectBinding(
            project_id=durable.project_id,
            relative_key=durable.relative_key,
            project_revision=durable.project_revision,
            binding_revision=durable.binding_revision,
            binding_digest=durable.binding_digest,
            runtime_host_installation_id=durable.runtime_host_installation_id,
            runtime_host_installation_revision=durable.runtime_host_installation_revision,
        )

    @staticmethod
    def _binding_inventory_item(durable: WAWDurableProjectBinding) -> dict[str, str | None]:
        return {
            "project_id": durable.project_id,
            "relative_key": durable.relative_key,
            "project_revision": durable.project_revision,
            "binding_revision": durable.binding_revision,
            "previous_binding_revision": durable.previous_binding_revision,
            "previous_binding_digest": durable.previous_binding_digest,
            "binding_digest": durable.binding_digest,
            "runtime_host_installation_id": durable.runtime_host_installation_id,
            "runtime_host_installation_revision": durable.runtime_host_installation_revision,
        }

    def _finalize_binding_inventory(self, request: dict[str, Any]) -> dict[str, Any]:
        self._require_authority()
        if request["runtime_epoch"] != self._runtime_epoch:
            raise WAWControlDispatchError("RUNTIME_INSTALLATION_MISMATCH")
        if not self._binding_replay_complete:
            raise WAWControlDispatchError("BINDING_REPLAY_INCOMPLETE")
        if (
            set(self._bindings) != set(self._durable_bindings)
            or set(self._bindings) != self._hydrated_bindings
            or any(
                self._bindings[project_id] != self._binding_from_durable(durable)
                for project_id, durable in self._durable_bindings.items()
            )
        ):
            raise WAWControlDispatchError("BINDING_REPLAY_INCOMPLETE")
        try:
            count, digest = binding_inventory_digest(
                [
                    self._binding_inventory_item(self._durable_bindings[project_id])
                    for project_id in sorted(self._durable_bindings)
                ]
            )
        except WAWControlError as exc:
            raise WAWControlDispatchError("BINDING_REPLAY_INCOMPLETE") from exc
        if request["binding_count"] != count or not hmac.compare_digest(
            request["inventory_digest"], digest
        ):
            self._fence_binding_inventory()
            raise WAWControlDispatchError("BINDING_INVENTORY_MISMATCH")
        authority = self._authority
        assert authority is not None
        expected = (authority, count, digest)
        current = self._binding_inventory_finalized
        if current is not None:
            if current != expected:
                self._fence_binding_inventory()
                raise WAWControlDispatchError("BINDING_INVENTORY_MISMATCH")
            status = "ALREADY_FINALIZED"
        else:
            self._binding_inventory_finalized = expected
            try:
                if self._application_gate_required:
                    self.open_application_gate()
            except BaseException:
                self._binding_inventory_finalized = None
                raise
            status = "FINALIZED"
        return {
            "protocol_version": 1,
            "request_id": request["request_id"],
            "status": status,
            "runtime_epoch": self._runtime_epoch,
            "binding_count": count,
            "inventory_digest": digest,
        }

    async def _register_executor_binding(self, binding: WAWProjectBinding) -> None:
        consumer = cast(object, self._executor)
        if isinstance(consumer, WAWProjectBindingConsumer):
            await consumer.register_project_binding(binding)

    async def _executable_evidence(self, request: dict[str, Any]) -> dict[str, Any]:
        """Return a typed fingerprint only for an exact currently-started binding."""

        self._require_authority()
        if request.get("runtime_epoch") != self._runtime_epoch:
            raise WAWControlDispatchError("RUNTIME_INSTALLATION_MISMATCH")
        identity = WAWLifecycleIdentity(
            workspace_id=request["workspace_id"],
            project_id=request["project_id"],
            agent_type=request["agent_type"],
            generation=request["generation"],
            binding_revision=request["binding_revision"],
            binding_digest=request["binding_digest"],
            runtime_host_installation_id=request["runtime_host_installation_id"],
            runtime_host_installation_revision=request["runtime_host_installation_revision"],
        )
        self._hydrate_durable_generation_floor(identity.workspace_id)
        self._check_identity(identity)
        current = self._workspaces.get(identity.workspace_id)
        if (
            current is None
            or current[0] != identity
            or current[1].state
            not in {"RUNNING", "NEEDS_INTERACTION", "TRUST_REQUIRED", "LOGIN_REQUIRED"}
        ):
            raise WAWControlDispatchError("WORKSPACE_NOT_RUNNING")
        provider = cast(object, self._executor)
        if not isinstance(provider, WAWExecutableEvidenceProvider):
            raise WAWControlDispatchError("RUNTIME_UNAVAILABLE", retryable=True)
        try:
            fingerprint = await provider.executable_evidence(identity)
        except RuntimeOperationError as exc:
            raise WAWControlDispatchError("RUNTIME_UNAVAILABLE", retryable=True) from exc
        if not isinstance(fingerprint, str) or _DIGEST.fullmatch(fingerprint) is None:
            raise WAWControlDispatchError("INTERNAL_BOUNDED")
        return {
            "protocol_version": 1,
            "request_id": request["request_id"],
            "status": "EXECUTABLE_EVIDENCE",
            "workspace_id": identity.workspace_id,
            "project_id": identity.project_id,
            "agent_type": identity.agent_type,
            "generation": identity.generation,
            "binding_revision": identity.binding_revision,
            "binding_digest": identity.binding_digest,
            "runtime_host_installation_id": identity.runtime_host_installation_id,
            "runtime_host_installation_revision": identity.runtime_host_installation_revision,
            "runtime_epoch": self._runtime_epoch,
            "executable_fingerprint": fingerprint,
        }

    async def _lifecycle(self, request: dict[str, Any], action: str) -> dict[str, Any]:
        self._require_authority()
        # Keep the WAW agent boundary closed at the Runtime seam.  Both
        # providers use the same identity/fencing lifecycle contract; their
        # side-effecting executors remain separately injected and are never
        # selected from request-controlled values.
        if request.get("agent_type") not in _SUPPORTED_AGENT_TYPES:
            raise WAWControlDispatchError("WAW_AGENT_UNSUPPORTED")
        identity = WAWLifecycleIdentity(
            workspace_id=request["workspace_id"],
            project_id=request["project_id"],
            agent_type=request["agent_type"],
            generation=request["generation"],
            binding_revision=request["binding_revision"],
            binding_digest=request["binding_digest"],
            runtime_host_installation_id=request["runtime_host_installation_id"],
            runtime_host_installation_revision=request["runtime_host_installation_revision"],
        )
        self._hydrate_durable_generation_floor(identity.workspace_id)
        self._check_identity(identity)
        if self._cgroup_attestation_store is not None and identity.workspace_id not in (
            self._cleanup_quarantine
        ):
            try:
                snapshot = self._cgroup_attestation_store.snapshot(
                    workspace_id=identity.workspace_id
                )
                unresolved = snapshot.latest_unresolved
                unresolved_generations = snapshot.unresolved_generations
                latest_generation = snapshot.latest_generation
                if latest_generation is not None:
                    self._generation_floor[identity.workspace_id] = max(
                        self._generation_floor.get(identity.workspace_id, 0), latest_generation
                    )
                current = self._workspaces.get(identity.workspace_id)
                active_live = (
                    current is not None
                    and current[0].generation == identity.generation
                    and unresolved is not None
                    and unresolved_generations == (unresolved.generation,)
                    and unresolved.cleanup_state == "LIVE"
                    and unresolved.last_populated == "1"
                )
                if unresolved is not None and not active_live:
                    self._cleanup_quarantine.add(identity.workspace_id)
            except WAWCgroupAttestationStoreError as exc:
                raise WAWControlDispatchError("RECONCILIATION_REQUIRED") from exc
        if action == _RECONCILE and identity.workspace_id in self._cleanup_quarantine:
            return self._quarantine_reconcile_response(request)
        # In the in-memory development composition an exact Stop may retry
        # failed cleanup. Durable/host quarantines still require their existing
        # independent recovery evidence and cannot be cleared by this shortcut.
        cleanup_retry = (
            action == _STOP
            and self._attestation_store is None
            and self._cgroup_attestation_store is None
            and self._workspaces.get(identity.workspace_id, (None,))[0] == identity
            and identity not in self._detached_cleanup_identities.values()
        )
        if identity.workspace_id in self._cleanup_quarantine and not cleanup_retry:
            raise WAWControlDispatchError("RECONCILIATION_REQUIRED")
        current = self._workspaces.get(identity.workspace_id)
        if action == _START and current is not None:
            if (
                current[0].project_id != identity.project_id
                or current[0].agent_type != identity.agent_type
                or current[0].binding_revision != identity.binding_revision
                or current[0].binding_digest != identity.binding_digest
            ):
                raise WAWControlDispatchError("PROJECT_IDENTITY_CHANGED")
            if current[0] != identity and int(identity.generation) <= self._generation_floor.get(
                identity.workspace_id, 0
            ):
                raise WAWControlDispatchError("PROJECT_IDENTITY_CHANGED")
            if current[0] == identity and current[1].state == "STOPPED":
                raise WAWControlDispatchError("PROJECT_IDENTITY_CHANGED")
            if current[1].state in {
                "RUNNING",
                "NEEDS_INTERACTION",
                "TRUST_REQUIRED",
                "LOGIN_REQUIRED",
            }:
                return self._start_response(request, current[1], "ALREADY_RUNNING")
        elif current is not None and current[0] != identity:
            raise WAWControlDispatchError("PROJECT_IDENTITY_CHANGED")
        if action == _START and int(identity.generation) <= self._generation_floor.get(
            identity.workspace_id, 0
        ):
            raise WAWControlDispatchError(
                "RECONCILIATION_REQUIRED"
                if current is None and self._attestation_store is not None
                else "PROJECT_IDENTITY_CHANGED"
            )
        if action == _STOP and current is None:
            raise WAWControlDispatchError("WORKSPACE_NOT_FOUND")
        if action == _STOP and current is not None and current[1].state == "STOPPED":
            if self._cgroup_attestation_store is not None:
                try:
                    self._fence_cgroup_for_identity(identity)
                except Exception as exc:
                    raise WAWControlDispatchError("RECONCILIATION_REQUIRED") from exc
            return self._stop_response(request, current[1], "ALREADY_STOPPED")
        if action in {_STATUS, _RECONCILE} and current is None:
            raise WAWControlDispatchError("WORKSPACE_NOT_FOUND")
        if self._executor is None:
            raise WAWControlDispatchError("RUNTIME_UNAVAILABLE", retryable=True)
        if action == _START and self._attestation_store is not None:
            # Burn the generation durably before any executor side effect.
            # A restart must not reuse a generation whose start was interrupted.
            try:
                self._attestation_store.advance(
                    workspace_id=identity.workspace_id,
                    generation=int(identity.generation),
                    binding_revision=identity.binding_revision,
                    binding_digest=identity.binding_digest,
                    runtime_host_installation_id=identity.runtime_host_installation_id,
                    runtime_host_installation_revision=identity.runtime_host_installation_revision,
                    runtime_epoch=self._runtime_epoch,
                )
            except Exception as exc:
                self._cleanup_quarantine.add(identity.workspace_id)
                raise WAWControlDispatchError("RECONCILIATION_REQUIRED") from exc
        method = {
            _START: self._executor.start,
            _STOP: self._executor.stop,
            _STATUS: self._executor.status,
            _RECONCILE: self._executor.reconcile,
        }[action]
        try:
            observation = await method(identity)
            self._validate_observation(observation)
        except BaseException as exc:
            if action == _START:
                # A transport can create a process and then fail its readiness
                # check, or continue after caller cancellation. Retain the
                # attempted identity and fence retries before awaiting cleanup.
                await self._rollback_failed_executor_start(identity)
                raise
            if action == _STOP and self._cgroup_attestation_store is not None:
                self._cleanup_quarantine.add(identity.workspace_id)
                try:
                    self._fence_cgroup_for_identity(identity)
                except Exception as fence_exc:
                    raise WAWControlDispatchError("RECONCILIATION_REQUIRED") from fence_exc
                raise WAWControlDispatchError("RECONCILIATION_REQUIRED") from exc
            raise
        cgroup_record: WAWCgroupAttestation | None = None
        if action == _START and self._cgroup_attestation_store is not None:
            try:
                if self._cgroup_attestation_factory is None:  # pragma: no cover
                    raise WAWControlDispatchError("RECONCILIATION_REQUIRED")
                cgroup_record = await self._build_cgroup_attestation(identity, observation)
                verify_waw_cgroup_attestation_context(
                    cgroup_record,
                    expected_workspace_id=identity.workspace_id,
                    expected_project_id=identity.project_id,
                    expected_agent_type=identity.agent_type,
                    expected_generation=int(identity.generation),
                    expected_runtime_epoch=self._runtime_epoch,
                )
                if cgroup_record.cleanup_state != "LIVE" or cgroup_record.last_populated != "1":
                    raise WAWControlDispatchError("RECONCILIATION_REQUIRED")
                self._cgroup_attestation_store.write(cgroup_record)
            except Exception as exc:
                fence_error: Exception | None = None
                try:
                    await self._cleanup_failed_start(identity)
                except Exception as cleanup_exc:
                    fence_error = cleanup_exc
                if cgroup_record is not None:
                    try:
                        self._fence_cgroup_attestation(cgroup_record)
                    except Exception as cgroup_exc:
                        fence_error = cgroup_exc
                else:
                    try:
                        self._fence_cgroup_for_identity(identity)
                    except Exception as cgroup_exc:
                        fence_error = cgroup_exc
                if fence_error is not None:
                    raise WAWControlDispatchError("RECONCILIATION_REQUIRED") from fence_error
                raise WAWControlDispatchError("RECONCILIATION_REQUIRED") from exc
        if action == _STOP and self._cgroup_attestation_store is not None:
            try:
                if self._cgroup_attestation_factory is None:  # pragma: no cover
                    raise WAWControlDispatchError("RECONCILIATION_REQUIRED")
                cgroup_record = await self._build_cgroup_attestation(identity, observation)
                verify_waw_cgroup_attestation_context(
                    cgroup_record,
                    expected_workspace_id=identity.workspace_id,
                    expected_project_id=identity.project_id,
                    expected_agent_type=identity.agent_type,
                    expected_generation=int(identity.generation),
                    expected_runtime_epoch=self._runtime_epoch,
                )
                if cgroup_record.cleanup_state == "LIVE":
                    raise WAWControlDispatchError("RECONCILIATION_REQUIRED")
                self._cgroup_attestation_store.write(cgroup_record)
            except Exception as exc:
                self._cleanup_quarantine.add(identity.workspace_id)
                if cgroup_record is not None:
                    try:
                        self._fence_cgroup_attestation(cgroup_record)
                    except Exception as fence_exc:
                        raise WAWControlDispatchError("RECONCILIATION_REQUIRED") from fence_exc
                else:
                    try:
                        self._fence_cgroup_for_identity(identity)
                    except Exception as fence_exc:
                        raise WAWControlDispatchError("RECONCILIATION_REQUIRED") from fence_exc
                raise WAWControlDispatchError("RECONCILIATION_REQUIRED") from exc
        if action == _START and self._attestation_store is not None:
            try:
                record = self._attestation_store.read(identity.workspace_id)
                if record is None or (
                    record.min_generation != int(identity.generation)
                    or record.binding_revision != identity.binding_revision
                    or record.binding_digest != identity.binding_digest
                    or record.runtime_host_installation_id != identity.runtime_host_installation_id
                    or record.runtime_host_installation_revision
                    != identity.runtime_host_installation_revision
                    or record.runtime_epoch != self._runtime_epoch
                ):
                    raise WAWWorkspaceAttestationError("reserved generation read-back changed")
            except WAWWorkspaceAttestationError as exc:
                # A successful provider start without a committed generation
                # floor is unsafe to retain.  Attempt exact identity cleanup;
                # if cleanup cannot be proven, the workspace remains fenced
                # for explicit reconciliation.
                self._cleanup_quarantine.add(identity.workspace_id)
                cleanup_error: Exception | None = None
                try:
                    await self._cleanup_failed_start(identity)
                except Exception as cleanup_exc:
                    cleanup_error = cleanup_exc
                if cgroup_record is not None:
                    try:
                        self._fence_cgroup_attestation(cgroup_record)
                    except Exception as cgroup_exc:
                        cleanup_error = cgroup_exc
                else:
                    try:
                        self._fence_cgroup_for_identity(identity)
                    except Exception as cgroup_exc:
                        cleanup_error = cgroup_exc
                if cleanup_error is not None:
                    raise WAWControlDispatchError("RECONCILIATION_REQUIRED") from cleanup_error
                raise WAWControlDispatchError("RECONCILIATION_REQUIRED") from exc
        self._workspaces[identity.workspace_id] = (identity, observation)
        if cleanup_retry and observation.state == "STOPPED":
            self._cleanup_quarantine.discard(identity.workspace_id)
        if action == _START:
            self._generation_floor[identity.workspace_id] = max(
                self._generation_floor.get(identity.workspace_id, 0), int(identity.generation)
            )
        if action == _START:
            return self._start_response(request, observation, "STARTED")
        if action == _STOP:
            status = "STOPPED" if observation.state == "STOPPED" else "STOP_IN_PROGRESS"
            return self._stop_response(request, observation, status)
        if action == _STATUS:
            return self._status_response(request, observation)
        return self._reconcile_response(request, observation)

    def _attach_prepare(
        self, request: dict[str, Any], runtime_peer: RuntimePeer | None = None
    ) -> dict[str, Any]:
        """Reserve one tuple-bound attachment after Runtime liveness checks.

        This synthetic control-plane contract intentionally returns only a
        deterministic capability digest.  Actual Noise keys, PTY handles and
        terminal bytes remain in the future stream implementation.
        """

        self._require_authority()
        if request["runtime_epoch"] != self._runtime_epoch:
            raise WAWControlDispatchError("RUNTIME_INSTALLATION_MISMATCH")
        if self._authority is not None and request["api_authority_epoch"] != self._authority[0]:
            raise WAWControlDispatchError("RUNTIME_INSTALLATION_MISMATCH")
        workspace = self._workspaces.get(request["workspace_id"])
        if workspace is None:
            raise WAWControlDispatchError("WORKSPACE_NOT_FOUND")
        identity, observation = workspace
        if (
            identity.project_id != request["project_id"]
            or identity.agent_type != request["agent_type"]
            or identity.generation != request["generation"]
            or identity.binding_revision != request["binding_revision"]
            or identity.binding_digest != request["binding_digest"]
            or identity.runtime_host_installation_id != request["runtime_host_installation_id"]
            or identity.runtime_host_installation_revision
            != request["runtime_host_installation_revision"]
        ):
            raise WAWControlDispatchError("PROJECT_IDENTITY_CHANGED")
        if observation.state not in {
            "RUNNING",
            "NEEDS_INTERACTION",
            "TRUST_REQUIRED",
            "LOGIN_REQUIRED",
        }:
            raise WAWControlDispatchError("WORKSPACE_NOT_RUNNING")
        if self._encrypted_attachments is not None:
            try:
                return self._encrypted_attachments.prepare(request, runtime_peer)
            except EncryptedStreamError as exc:
                raise WAWControlDispatchError(exc.code) from None
        attachment_id = request["attachment_id"]
        try:
            if (
                not isinstance(request["auth_epoch"], str)
                or _POS_DECIMAL.fullmatch(request["auth_epoch"]) is None
                or int(request["auth_epoch"]) > _MAX_U64
            ):
                raise ValueError("auth_epoch must be canonical")
            ResumeHint(
                resume_cursor=(
                    None if request["resume_cursor"] is None else int(request["resume_cursor"])
                ),
                previous_runtime_epoch=(
                    None
                    if request["previous_runtime_epoch"] is None
                    else int(request["previous_runtime_epoch"])
                ),
            ).validate(current_runtime_epoch=int(self._runtime_epoch))
        except (RecoveryError, TypeError, ValueError) as exc:
            raise WAWControlDispatchError("RESUME_HINT_INVALID") from exc
        if attachment_id in self._attachments:
            raise WAWControlDispatchError("ATTACHMENT_PREPARE_REPLAY")
        if len(self._attachments) >= 32:
            raise WAWControlDispatchError("ATTACHMENT_TICKET_UNAVAILABLE")
        capability = hashlib.sha256(
            (
                "agentbox-waw-capability-v1\0"
                + attachment_id
                + "\0"
                + request["workspace_id"]
                + "\0"
                + request["lease_number"]
                + "\0"
                + request["runtime_epoch"]
            ).encode("ascii")
        ).hexdigest()
        self._attachments[attachment_id] = dict(request)
        return {
            "protocol_version": 1,
            "request_id": request["request_id"],
            "status": "PREPARED",
            "workspace_id": request["workspace_id"],
            "project_id": request["project_id"],
            "agent_type": request["agent_type"],
            "attachment_id": attachment_id,
            "mode": request["mode"],
            "lease_number": request["lease_number"],
            "generation": request["generation"],
            "binding_revision": request["binding_revision"],
            "binding_digest": request["binding_digest"],
            "auth_epoch": request["auth_epoch"],
            "api_authority_epoch": request["api_authority_epoch"],
            "runtime_host_installation_id": request["runtime_host_installation_id"],
            "runtime_host_installation_revision": request["runtime_host_installation_revision"],
            "runtime_epoch": self._runtime_epoch,
            "resume_cursor": request["resume_cursor"],
            "previous_runtime_epoch": request["previous_runtime_epoch"],
            "capability": capability,
        }

    def _attach_detach(
        self, request: dict[str, Any], runtime_peer: RuntimePeer | None = None
    ) -> dict[str, Any]:
        """Close one prepared attachment and return positive cleanup proof."""

        self._require_authority()
        if request["runtime_epoch"] != self._runtime_epoch:
            raise WAWControlDispatchError("RUNTIME_INSTALLATION_MISMATCH")
        if self._authority is not None and request["api_authority_epoch"] != self._authority[0]:
            raise WAWControlDispatchError("RUNTIME_INSTALLATION_MISMATCH")
        if self._encrypted_attachments is not None:
            try:
                return self._encrypted_attachments.detach(request, runtime_peer)
            except EncryptedStreamError as exc:
                raise WAWControlDispatchError(exc.code) from None
        current = self._attachments.get(request["attachment_id"])
        if current is None:
            raise WAWControlDispatchError("ATTACHMENT_STALE")
        fields = (
            "workspace_id",
            "project_id",
            "agent_type",
            "attachment_id",
            "mode",
            "lease_number",
            "generation",
            "binding_revision",
            "binding_digest",
            "auth_epoch",
            "api_authority_epoch",
            "runtime_host_installation_id",
            "runtime_host_installation_revision",
            "runtime_epoch",
        )
        if any(current.get(field) != request.get(field) for field in fields):
            raise WAWControlDispatchError("ATTACHMENT_STALE")
        del self._attachments[request["attachment_id"]]
        return {
            "protocol_version": 1,
            "request_id": request["request_id"],
            "status": "DETACHED",
            **{field: request[field] for field in fields},
            "cleanup_state": "ATTACH_PTY_CLOSED",
            "reason_code": None,
        }

    async def _rollback_failed_executor_start(self, identity: WAWLifecycleIdentity) -> None:
        self._generation_floor[identity.workspace_id] = max(
            self._generation_floor.get(identity.workspace_id, 0), int(identity.generation)
        )
        self._workspaces[identity.workspace_id] = (
            identity,
            WAWLifecycleObservation(
                state="UNKNOWN",
                process_state="UNKNOWN",
                reconciliation_state="reconciliation_required",
                runtime_epoch=self._runtime_epoch,
            ),
        )
        self._cleanup_quarantine.add(identity.workspace_id)
        try:
            await self._cleanup_failed_start(identity)
        except asyncio.CancelledError:
            # Late cleanup must not make this identity reusable. The existing
            # detached-cleanup tracker retains tasks until their actual end.
            raise
        except Exception as exc:
            raise WAWControlDispatchError("RECONCILIATION_REQUIRED") from exc
        finally:
            self._fence_cgroup_for_identity(identity)
        self._workspaces[identity.workspace_id] = (
            identity,
            WAWLifecycleObservation(
                state="STOPPED", process_state="STOPPED", runtime_epoch=self._runtime_epoch
            ),
        )
        if self._attestation_store is None and self._cgroup_attestation_store is None:
            self._cleanup_quarantine.discard(identity.workspace_id)

    async def _cleanup_failed_start(self, identity: WAWLifecycleIdentity) -> None:
        if self._executor is None:  # pragma: no cover - guarded by _lifecycle
            raise WAWControlDispatchError("RECONCILIATION_REQUIRED")
        if len(self._detached_cleanup_tasks) >= _MAX_DETACHED_CLEANUPS:
            raise WAWControlDispatchError("RECONCILIATION_REQUIRED")
        task = asyncio.create_task(self._executor.stop(identity))
        try:
            done, pending = await asyncio.wait({task}, timeout=self._cleanup_timeout_seconds)
        except BaseException:
            self._register_detached_cleanup(task, identity)
            raise
        if pending:
            self._register_detached_cleanup(task, identity)
            raise WAWControlDispatchError("RECONCILIATION_REQUIRED")
        cleanup = next(iter(done)).result()
        self._validate_observation(cleanup)
        if not (
            cleanup.state == "STOPPED"
            and cleanup.process_state == "STOPPED"
            and cleanup.reconciliation_state == "authoritative"
            and cleanup.runtime_epoch == self._runtime_epoch
        ):
            raise WAWControlDispatchError("RECONCILIATION_REQUIRED")

    def _register_detached_cleanup(
        self, task: asyncio.Task[Any], identity: WAWLifecycleIdentity
    ) -> None:
        self._detached_cleanup_tasks.add(task)
        self._detached_cleanup_identities[task] = identity
        self._cleanup_quarantine.add(identity.workspace_id)
        task.add_done_callback(self._consume_detached_cleanup)

    def _consume_detached_cleanup(self, task: asyncio.Task[Any]) -> None:
        self._detached_cleanup_tasks.discard(task)
        self._detached_cleanup_identities.pop(task, None)
        with suppress(BaseException):
            cleanup = task.result()
            self._validate_observation(cleanup)
            # A late STOPPED observation is necessary but not sufficient: the
            # quarantine remains until a host-gated EMPTY_DURABLE cgroup
            # read-back is explicitly acknowledged below.

    async def acknowledge_cgroup_cleanup(
        self,
        record: WAWCgroupAttestation,
        *,
        binding_revision: str | None = None,
        binding_digest: str | None = None,
    ) -> None:
        """Clear one workspace quarantine after host-gated empty read-back.

        Runtime host code may call this only after independently proving
        ``populated=0``, no attachment leaves, and durable cgroup cleanup.  A
        late executor STOPPED observation alone never clears quarantine.
        """

        async with self._lock:
            self._acknowledge_cgroup_cleanup_unlocked(
                record,
                binding_revision=binding_revision,
                binding_digest=binding_digest,
            )

    def _acknowledge_cgroup_cleanup_unlocked(
        self,
        record: WAWCgroupAttestation,
        *,
        binding_revision: str | None,
        binding_digest: str | None,
    ) -> None:
        if self._cgroup_attestation_store is None:
            raise WAWControlDispatchError("RECONCILIATION_REQUIRED")
        if binding_revision is None or binding_digest is None:
            raise WAWControlDispatchError("RECONCILIATION_REQUIRED")
        if record.workspace_id not in self._cleanup_quarantine:
            try:
                snapshot = self._cgroup_attestation_store.snapshot(workspace_id=record.workspace_id)
            except WAWCgroupAttestationStoreError as exc:
                raise WAWControlDispatchError("RECONCILIATION_REQUIRED") from exc
            if snapshot.latest_unresolved is None:
                raise WAWControlDispatchError("RECONCILIATION_REQUIRED")
            self._cleanup_quarantine.add(record.workspace_id)
        if record.cleanup_state != "EMPTY_DURABLE" or record.last_populated != "0":
            raise WAWControlDispatchError("RECONCILIATION_REQUIRED")
        if record.attachment_leaves:
            raise WAWControlDispatchError("RECONCILIATION_REQUIRED")
        if record.runtime_epoch != self._runtime_epoch:
            raise WAWControlDispatchError("RUNTIME_INSTALLATION_MISMATCH")
        active = self._workspaces.get(record.workspace_id)
        if active is not None:
            active_identity = active[0]
            if (
                active_identity.project_id != record.project_id
                or active_identity.agent_type != record.agent_type
                or int(active_identity.generation) != record.generation
                or active_identity.runtime_host_installation_id != self._host_id
                or active_identity.runtime_host_installation_revision != self._host_revision
                or binding_revision != active_identity.binding_revision
                or binding_digest != active_identity.binding_digest
            ):
                raise WAWControlDispatchError("RECONCILIATION_REQUIRED")
        else:
            binding = self._bindings.get(record.project_id)
            if binding is None or (
                binding_revision != binding.binding_revision
                or binding_digest != binding.binding_digest
            ):
                raise WAWControlDispatchError("RECONCILIATION_REQUIRED")
        unresolved = self._cgroup_attestation_store.latest_unresolved(
            workspace_id=record.workspace_id
        )
        if unresolved is None or record.generation != unresolved.generation:
            raise WAWControlDispatchError("RECONCILIATION_REQUIRED")
        verify_waw_cgroup_attestation_context(
            record,
            expected_workspace_id=unresolved.workspace_id,
            expected_project_id=unresolved.project_id,
            expected_agent_type=unresolved.agent_type,
            expected_generation=unresolved.generation,
            expected_runtime_epoch=self._runtime_epoch,
            expected_controller_configuration_digest=unresolved.controller_configuration_digest,
            expected_workspace_limits=unresolved.workspace_limits,
            expected_workload_limits=unresolved.workload_limits,
            expected_attachment_limits=unresolved.attachment_limits,
        )
        try:
            fully_empty = self._cgroup_attestation_store.acknowledge_empty(record)
        except WAWCgroupAttestationStoreError as exc:
            raise WAWControlDispatchError("RECONCILIATION_REQUIRED") from exc
        if fully_empty:
            self._cleanup_quarantine.discard(record.workspace_id)
            self._recovered_generation_floor[record.workspace_id] = record.generation

    async def _build_cgroup_attestation(
        self, identity: WAWLifecycleIdentity, observation: WAWLifecycleObservation
    ) -> WAWCgroupAttestation:
        if self._cgroup_attestation_factory is None:  # pragma: no cover
            raise WAWControlDispatchError("RECONCILIATION_REQUIRED")
        value = self._cgroup_attestation_factory(identity, observation)
        if isinstance(value, Awaitable):
            try:
                value = await asyncio.wait_for(
                    value, timeout=self._cgroup_attestation_timeout_seconds
                )
            except TimeoutError as exc:
                raise WAWControlDispatchError("RECONCILIATION_REQUIRED") from exc
        if not isinstance(value, WAWCgroupAttestation):
            raise WAWControlDispatchError("RECONCILIATION_REQUIRED")
        return value

    def _fence_cgroup_attestation(self, record: WAWCgroupAttestation) -> None:
        """Persist a conservative FENCED state without claiming empty cgroupfs."""

        if self._cgroup_attestation_store is None:  # pragma: no cover
            return
        fenced = (
            record if record.cleanup_state != "LIVE" else replace(record, cleanup_state="FENCED")
        )
        self._cgroup_attestation_store.write(fenced)

    def _fence_cgroup_for_identity(
        self, identity: WAWLifecycleIdentity, record: WAWCgroupAttestation | None = None
    ) -> None:
        if self._cgroup_attestation_store is None:
            return
        if record is None:
            record = self._cgroup_attestation_store.read(
                workspace_id=identity.workspace_id,
                generation=int(identity.generation),
            )
        if record is not None:
            self._fence_cgroup_attestation(record)

    def _quarantine_reconcile_response(self, request: dict[str, Any]) -> dict[str, Any]:
        """Return read-only evidence while cleanup quarantine remains active."""

        return {
            "protocol_version": 1,
            "request_id": request["request_id"],
            "status": "RECONCILIATION_REQUIRED",
            "workspace_id": request["workspace_id"],
            "project_id": request["project_id"],
            "agent_type": request["agent_type"],
            "generation": request["generation"],
            "binding_revision": request["binding_revision"],
            "binding_digest": request["binding_digest"],
            "runtime_epoch": self._runtime_epoch,
            "state": "UNKNOWN",
            "reconciliation_state": "reconciliation_required",
        }

    def _require_authority(self) -> None:
        if self._authority is None:
            raise WAWControlDispatchError("BINDING_BOOTSTRAP_REQUIRED", retryable=True)

    def _require_dispatch_open(self, action: str) -> None:
        if self._shutting_down or (
            self._application_gate_required
            and not self._application_gate_open
            and action not in _BOOTSTRAP_ACTIONS
        ):
            raise WAWControlDispatchError("RUNTIME_UNAVAILABLE", retryable=True)

    def _validate_control_peer(
        self,
        action: str,
        peer: WAWPeerCandidate | WAWPeerLease | None,
    ) -> RuntimePeer | None:
        authority = self._peer_authority
        if authority is None:
            return None
        if action == _BIND:
            if type(peer) not in {WAWPeerCandidate, WAWPeerLease}:
                raise WAWControlDispatchError("RUNTIME_PEER_FORBIDDEN")
            return peer.runtime_peer if type(peer) is WAWPeerLease else None
        if type(peer) is not WAWPeerLease or not peer.current():
            raise WAWControlDispatchError("BINDING_BOOTSTRAP_REQUIRED", retryable=True)
        if self._authority is None or peer.api_authority_epoch != self._authority[0]:
            raise WAWControlDispatchError("RUNTIME_PEER_FORBIDDEN")
        return peer.runtime_peer

    def _check_identity(self, identity: WAWLifecycleIdentity) -> None:
        self._validate_generation(identity.generation)
        if int(identity.generation) < self._generation_floor.get(identity.workspace_id, 0):
            raise WAWControlDispatchError(
                "RECONCILIATION_REQUIRED"
                if identity.workspace_id not in self._workspaces
                else "PROJECT_IDENTITY_CHANGED"
            )
        if (
            identity.runtime_host_installation_id != self._host_id
            or identity.runtime_host_installation_revision != self._host_revision
        ):
            raise WAWControlDispatchError("RUNTIME_INSTALLATION_MISMATCH")
        binding = self._bindings.get(identity.project_id)
        if binding is None:
            raise WAWControlDispatchError("BINDING_BOOTSTRAP_REQUIRED", retryable=True)
        if (
            identity.binding_revision != binding.binding_revision
            or identity.binding_digest != binding.binding_digest
        ):
            raise WAWControlDispatchError("PROJECT_IDENTITY_CHANGED")

    def _hydrate_durable_generation_floor(self, workspace_id: str) -> None:
        if self._attestation_store is None:
            return
        try:
            record = self._attestation_store.read(workspace_id)
        except Exception as exc:
            raise WAWControlDispatchError("RECONCILIATION_REQUIRED") from exc
        if record is not None:
            self._generation_floor[workspace_id] = max(
                self._generation_floor.get(workspace_id, 0), record.min_generation
            )
            if (
                workspace_id not in self._workspaces
                and record.min_generation > self._recovered_generation_floor.get(workspace_id, 0)
            ):
                # A durable generation is not proof its processes are gone.
                # Neither the same nor a newer generation may bypass recovery.
                self._cleanup_quarantine.add(workspace_id)

    def _validate_observation(self, observation: WAWLifecycleObservation) -> None:
        if observation.state not in _STATES:
            raise WAWControlDispatchError("INTERNAL_BOUNDED")
        if observation.reconciliation_state not in _RECONCILIATION_STATES:
            raise WAWControlDispatchError("INTERNAL_BOUNDED")
        if (
            observation.reconciliation_state
            not in _OBSERVATION_RECONCILIATION_STATES[observation.state]
        ):
            raise WAWControlDispatchError("INTERNAL_BOUNDED")
        if observation.process_state not in _PROCESS_STATES:
            raise WAWControlDispatchError("INTERNAL_BOUNDED")
        if observation.process_state not in _OBSERVATION_PROCESS_STATES[observation.state]:
            raise WAWControlDispatchError("INTERNAL_BOUNDED")
        if observation.state == "EXITED":
            if observation.exit_code is None:
                raise WAWControlDispatchError("INTERNAL_BOUNDED")
        elif observation.exit_code is not None:
            raise WAWControlDispatchError("INTERNAL_BOUNDED")
        if (
            not isinstance(observation.runtime_epoch, str)
            or not _DECIMAL.fullmatch(observation.runtime_epoch)
            or int(observation.runtime_epoch) == 0
        ):
            raise WAWControlDispatchError("INTERNAL_BOUNDED")
        if observation.runtime_epoch != self._runtime_epoch:
            raise WAWControlDispatchError("RUNTIME_INSTALLATION_MISMATCH")
        if observation.exit_code is not None and (
            type(observation.exit_code) is not int or not -128 <= observation.exit_code <= 255
        ):
            raise WAWControlDispatchError("INTERNAL_BOUNDED")

    @staticmethod
    def _validate_generation(generation: object) -> None:
        if (
            not isinstance(generation, str)
            or not _DECIMAL.fullmatch(generation)
            or int(generation) < 1
            or int(generation) > _MAX_U64
        ):
            raise WAWControlDispatchError("PROTOCOL_INVALID")

    @staticmethod
    def _start_response(
        request: dict[str, Any], observation: WAWLifecycleObservation, status: str
    ) -> dict[str, Any]:
        return {
            "protocol_version": 1,
            "request_id": request["request_id"],
            "status": status,
            "workspace_id": request["workspace_id"],
            "project_id": request["project_id"],
            "agent_type": request["agent_type"],
            "generation": request["generation"],
            "state": observation.state,
            "runtime_host_installation_id": request["runtime_host_installation_id"],
            "runtime_host_installation_revision": request["runtime_host_installation_revision"],
        }

    @staticmethod
    def _stop_response(
        request: dict[str, Any], observation: WAWLifecycleObservation, status: str
    ) -> dict[str, Any]:
        return {
            "protocol_version": 1,
            "request_id": request["request_id"],
            "status": status,
            "workspace_id": request["workspace_id"],
            "project_id": request["project_id"],
            "agent_type": request["agent_type"],
            "generation": request["generation"],
            "state": observation.state,
        }

    @staticmethod
    def _status_response(
        request: dict[str, Any], observation: WAWLifecycleObservation
    ) -> dict[str, Any]:
        return {
            "protocol_version": 1,
            "request_id": request["request_id"],
            "status": "STATUS",
            "workspace_id": request["workspace_id"],
            "project_id": request["project_id"],
            "agent_type": request["agent_type"],
            "generation": request["generation"],
            "binding_revision": request["binding_revision"],
            "binding_digest": request["binding_digest"],
            "state": observation.state,
            "reconciliation_state": observation.reconciliation_state,
            "runtime_epoch": observation.runtime_epoch,
            "process_state": observation.process_state,
            "exit_code": observation.exit_code,
            "attachment_capacity": {"admitted": "0", "pending": "0", "limit": "32"},
        }

    @staticmethod
    def _reconcile_response(
        request: dict[str, Any], observation: WAWLifecycleObservation
    ) -> dict[str, Any]:
        status = {
            "MISSING": "MISSING",
            "COLLISION": "COLLISION",
            "UNKNOWN": "UNKNOWN",
        }.get(observation.state, "RECONCILED")
        return {
            "protocol_version": 1,
            "request_id": request["request_id"],
            "status": status,
            "workspace_id": request["workspace_id"],
            "project_id": request["project_id"],
            "agent_type": request["agent_type"],
            "generation": request["generation"],
            "binding_revision": request["binding_revision"],
            "binding_digest": request["binding_digest"],
            "runtime_epoch": observation.runtime_epoch,
            "state": observation.state,
            "reconciliation_state": observation.reconciliation_state,
        }


__all__ = [
    "WAWProjectBinding",
    "WAWProjectBindingConsumer",
    "BindingDigestFactory",
    "WAWLifecycleExecutor",
    "WAWLifecycleIdentity",
    "WAWLifecycleObservation",
    "WAWLifecycleRegistry",
]
