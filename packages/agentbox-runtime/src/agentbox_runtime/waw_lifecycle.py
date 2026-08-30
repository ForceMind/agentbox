"""Bounded Runtime lifecycle registry for Web Agent Workspace control actions.

This module is the typed seam between the WAW control socket and a future
Runtime adapter.  It owns binding/generation fencing and lifecycle metadata;
it never accepts a path, command, argv, PID, signal, tmux target, or secret.
The side-effecting adapter is injected and receives only an immutable identity.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from agentbox_runtime.waw_control_server import WAWControlDispatchError
from agentbox_runtime.waw_workspace_attestation import (
    WAWWorkspaceAttestationError,
    WAWWorkspaceAttestationStore,
)

_BIND = "workspace.api_authority.bind"
_REGISTER = "workspace.project_binding.register"
_START = "workspace.workspace.start"
_STOP = "workspace.workspace.stop"
_STATUS = "workspace.workspace.status"
_RECONCILE = "workspace.workspace.reconcile"
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_DECIMAL = re.compile(r"\A(?:0|[1-9][0-9]{0,19})\Z")
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


@dataclass(frozen=True)
class _ProjectBinding:
    project_id: str
    relative_key: str
    project_revision: str
    binding_revision: str
    binding_digest: str
    runtime_host_installation_id: str
    runtime_host_installation_revision: str


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
        runtime_epoch: str = "1",
        attestation_store: WAWWorkspaceAttestationStore | None = None,
    ) -> None:
        self._host_id = runtime_host_installation_id
        self._host_revision = runtime_host_installation_revision
        self._host_manifest_digest = host_manifest_digest
        self._project_root_manifest_digest = project_root_manifest_digest
        self._enrollment_epoch = enrollment_epoch
        self._enrollment_state = enrollment_state
        self._runtime_epoch = runtime_epoch
        self._executor = executor
        self._binding_digest_factory = binding_digest_factory
        self._attestation_store = attestation_store
        self._authority: tuple[str, str] | None = None
        self._bindings: dict[str, _ProjectBinding] = {}
        self._workspaces: dict[str, tuple[WAWLifecycleIdentity, WAWLifecycleObservation]] = {}
        self._generation_floor: dict[str, int] = {}
        self._request_cache: OrderedDict[str, tuple[str, dict[str, Any]]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        """Dispatch one decoded control request; all mutations are serialized."""

        action = request.get("action")
        if not isinstance(action, str):
            raise WAWControlDispatchError("PROTOCOL_INVALID")
        async with self._lock:
            request_id = request.get("request_id")
            if not isinstance(request_id, str):
                raise WAWControlDispatchError("PROTOCOL_INVALID")
            fingerprint = json.dumps(
                request, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
            cached = self._request_cache.get(request_id)
            if cached is not None:
                if cached[0] != fingerprint:
                    raise WAWControlDispatchError("PROTOCOL_INVALID")
                return dict(cached[1])
            if action == _BIND:
                response = self._bind(request)
            elif action == _REGISTER:
                response = await self._register(request)
            elif action in {_START, _STOP, _STATUS, _RECONCILE}:
                response = await self._lifecycle(request, action)
            else:
                raise WAWControlDispatchError("PROTOCOL_INVALID")
            self._request_cache[request_id] = (fingerprint, dict(response))
            self._request_cache.move_to_end(request_id)
            while len(self._request_cache) > 1024:
                self._request_cache.popitem(last=False)
            return response

    def _bind(self, request: dict[str, Any]) -> dict[str, Any]:
        epoch = request["api_authority_epoch"]
        nonce = request["authority_nonce"]
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

    async def _register(self, request: dict[str, Any]) -> dict[str, Any]:
        self._require_authority()
        if (
            request["runtime_host_installation_id"] != self._host_id
            or request["runtime_host_installation_revision"] != self._host_revision
        ):
            raise WAWControlDispatchError("RUNTIME_INSTALLATION_MISMATCH")
        project_id = request["project_id"]
        previous = self._bindings.get(project_id)
        if previous is None and (
            request["binding_revision"] != "1"
            or request["previous_binding_revision"] is not None
            or request["previous_binding_digest"] is not None
        ):
            raise WAWControlDispatchError("PROJECT_IDENTITY_CHANGED")
        if (
            previous is not None
            and request["binding_revision"] != previous.binding_revision
            and (
                request["previous_binding_revision"] != previous.binding_revision
                or request["previous_binding_digest"] != previous.binding_digest
            )
        ):
            raise WAWControlDispatchError("PROJECT_IDENTITY_CHANGED")
        if self._binding_digest_factory is None:
            raise WAWControlDispatchError("RUNTIME_UNAVAILABLE", retryable=True)
        digest = self._binding_digest_factory(request)
        if isinstance(digest, Awaitable):
            digest = await digest
        if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
            raise WAWControlDispatchError("INTERNAL_BOUNDED")
        if previous is not None and request["binding_revision"] == previous.binding_revision:
            if (
                request["relative_key"] == previous.relative_key
                and request["project_revision"] == previous.project_revision
                and digest == previous.binding_digest
            ):
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
        binding = _ProjectBinding(
            project_id=project_id,
            relative_key=request["relative_key"],
            project_revision=request["project_revision"],
            binding_revision=request["binding_revision"],
            binding_digest=digest,
            runtime_host_installation_id=self._host_id,
            runtime_host_installation_revision=self._host_revision,
        )
        self._bindings[project_id] = binding
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

    async def _lifecycle(self, request: dict[str, Any], action: str) -> dict[str, Any]:
        self._require_authority()
        if request.get("agent_type") != "claude":
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
        self._check_identity(identity)
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
            raise WAWControlDispatchError("PROJECT_IDENTITY_CHANGED")
        if action == _STOP and current is None:
            raise WAWControlDispatchError("WORKSPACE_NOT_FOUND")
        if action == _STOP and current is not None and current[1].state == "STOPPED":
            return self._stop_response(request, current[1], "ALREADY_STOPPED")
        if action in {_STATUS, _RECONCILE} and current is None:
            raise WAWControlDispatchError("WORKSPACE_NOT_FOUND")
        if self._executor is None:
            raise WAWControlDispatchError("RUNTIME_UNAVAILABLE", retryable=True)
        method = {
            _START: self._executor.start,
            _STOP: self._executor.stop,
            _STATUS: self._executor.status,
            _RECONCILE: self._executor.reconcile,
        }[action]
        observation = await method(identity)
        self._validate_observation(observation)
        if action == _START and self._attestation_store is not None:
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
            except WAWWorkspaceAttestationError as exc:
                # A successful provider start without a committed generation
                # floor is unsafe to retain.  Attempt exact identity cleanup;
                # if cleanup cannot be proven, the workspace remains fenced
                # for explicit reconciliation.
                try:
                    cleanup = await self._executor.stop(identity)
                    self._validate_observation(cleanup)
                except Exception as cleanup_exc:
                    raise WAWControlDispatchError("RECONCILIATION_REQUIRED") from cleanup_exc
                raise WAWControlDispatchError("RECONCILIATION_REQUIRED") from exc
        self._workspaces[identity.workspace_id] = (identity, observation)
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

    def _require_authority(self) -> None:
        if self._authority is None:
            raise WAWControlDispatchError("BINDING_BOOTSTRAP_REQUIRED", retryable=True)

    def _check_identity(self, identity: WAWLifecycleIdentity) -> None:
        self._validate_generation(identity.generation)
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
    "BindingDigestFactory",
    "WAWLifecycleExecutor",
    "WAWLifecycleIdentity",
    "WAWLifecycleObservation",
    "WAWLifecycleRegistry",
]
