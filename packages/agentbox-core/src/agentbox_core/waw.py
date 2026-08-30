"""Pure domain primitives for the Web Agent Workspace (WAW) lifecycle.

This module deliberately has no database, Runtime, filesystem, process, or
secret dependencies.  It provides the small immutable value objects shared by
the future Control Plane and Runtime implementations.  Persistence and
transport adapters must enforce the same invariants at their own boundaries.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

_HEX32 = r"[a-f0-9]{32}"
_ID_PATTERNS = {
    "workspace": re.compile(rf"\Aaws_{_HEX32}\Z"),
    "project": re.compile(rf"\Aprj_{_HEX32}\Z"),
    "attachment": re.compile(rf"\Aatt_{_HEX32}\Z"),
    "stop_operation": re.compile(rf"\Awso_{_HEX32}\Z"),
    "runtime_host": re.compile(rf"\Awri_{_HEX32}\Z"),
}
_BINDING_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_MAX_U64 = 2**64 - 1


class AgentType(StrEnum):
    """Closed WAW V1 agent set."""

    CLAUDE = "claude"
    CODEX = "codex"


class WorkspaceState(StrEnum):
    """Durable workspace lifecycle states from the WAW proposal."""

    STARTING = "STARTING"
    RUNNING = "RUNNING"
    NEEDS_INTERACTION = "NEEDS_INTERACTION"
    TRUST_REQUIRED = "TRUST_REQUIRED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    STOPPING = "STOPPING"
    EXITED = "EXITED"
    STOPPED = "STOPPED"
    MISSING = "MISSING"
    COLLISION = "COLLISION"
    BROKEN = "BROKEN"
    UNKNOWN = "UNKNOWN"


class ReconciliationState(StrEnum):
    """Bounded durable reconciliation classification."""

    AUTHORITATIVE = "authoritative"
    STOPPING = "stopping"
    MISSING = "missing"
    COLLISION = "collision"
    EXITED = "exited"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    UNKNOWN = "unknown"


class StopResult(StrEnum):
    """Terminal and in-flight exact-stop outcomes."""

    PENDING = "PENDING"
    STOPPED = "STOPPED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    TIMEOUT = "TIMEOUT"


class WAWDomainError(ValueError):
    """A caller supplied an invalid WAW value or attempted an invalid transition."""


def _validate_id(value: str, kind: str) -> str:
    pattern = _ID_PATTERNS[kind]
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise WAWDomainError(f"invalid {kind} identifier")
    return value


def validate_workspace_id(value: str) -> str:
    return _validate_id(value, "workspace")


def validate_project_id(value: str) -> str:
    return _validate_id(value, "project")


def validate_attachment_id(value: str) -> str:
    return _validate_id(value, "attachment")


def validate_stop_operation_id(value: str) -> str:
    return _validate_id(value, "stop_operation")


def validate_runtime_host_installation_id(value: str) -> str:
    return _validate_id(value, "runtime_host")


def validate_binding_digest(value: str) -> str:
    if not isinstance(value, str) or not _BINDING_DIGEST.fullmatch(value):
        raise WAWDomainError("binding_digest must be 64 lowercase hexadecimal characters")
    return value


def validate_positive_u64(value: int, *, field: str = "value") -> int:
    if type(value) is not int or not 1 <= value <= _MAX_U64:
        raise WAWDomainError(f"{field} must be an unsigned integer in 1..2^64-1")
    return value


def workspace_id(project_id: str, agent_type: AgentType | str) -> str:
    """Return the deterministic WAW identity for one Project/AgentType pair."""

    validate_project_id(project_id)
    agent = _agent_type(agent_type)
    digest = hashlib.sha256(
        b"agentbox-waw-v1\0" + project_id.encode("utf-8") + b"\0" + agent.value.encode("ascii")
    ).hexdigest()[:32]
    return f"aws_{digest}"


def managed_session_name(project_id: str, agent_type: AgentType | str) -> str:
    """Return the bounded, non-caller-controlled tmux session name."""

    validate_project_id(project_id)
    agent = _agent_type(agent_type)
    value = (
        f"agentbox-waw-{agent.value}-{hashlib.sha256(project_id.encode('utf-8')).hexdigest()[:16]}"
    )
    if len(value) > 80:  # Defensive guard if the fixed prefix ever changes.
        raise WAWDomainError("managed session name exceeds 80 characters")
    return value


def managed_marker(
    *,
    runtime_host_installation_id: str,
    runtime_host_installation_revision: int,
    project_id: str,
    agent_type: AgentType | str,
    workspace_id_value: str,
    generation: int,
    binding_revision: int,
    binding_digest: str,
) -> str:
    """Return the generation-and-binding-fenced Runtime marker."""

    host_id = validate_runtime_host_installation_id(runtime_host_installation_id)
    validate_positive_u64(
        runtime_host_installation_revision, field="runtime_host_installation_revision"
    )
    validate_project_id(project_id)
    agent = _agent_type(agent_type)
    validate_workspace_id(workspace_id_value)
    validate_positive_u64(generation, field="generation")
    validate_positive_u64(binding_revision, field="binding_revision")
    digest = validate_binding_digest(binding_digest)
    components = (
        "agentbox-waw-v1",
        host_id,
        str(runtime_host_installation_revision),
        project_id,
        agent.value,
        workspace_id_value,
        str(generation),
        str(binding_revision),
        digest,
    )
    payload = "\0".join(components).encode("utf-8")
    return f"waw-v1:{host_id}:{hashlib.sha256(payload).hexdigest()[:32]}"


@dataclass(frozen=True)
class GenerationCounter:
    """Monotonic non-wrapping process-generation allocator."""

    current: int = 0

    def __post_init__(self) -> None:
        if type(self.current) is not int or not 0 <= self.current <= _MAX_U64:
            raise WAWDomainError("generation counter is outside the uint64 domain")

    def allocate(self) -> tuple[int, GenerationCounter]:
        if self.current == _MAX_U64:
            raise WAWDomainError("generation counter exhausted")
        generation = self.current + 1
        return generation, replace(self, current=generation)


_TRANSITIONS: dict[WorkspaceState, frozenset[WorkspaceState]] = {
    WorkspaceState.STARTING: frozenset(
        {
            WorkspaceState.RUNNING,
            WorkspaceState.NEEDS_INTERACTION,
            WorkspaceState.TRUST_REQUIRED,
            WorkspaceState.LOGIN_REQUIRED,
            WorkspaceState.STOPPING,
            WorkspaceState.EXITED,
            WorkspaceState.BROKEN,
            WorkspaceState.UNKNOWN,
        }
    ),
    WorkspaceState.RUNNING: frozenset(
        {
            WorkspaceState.NEEDS_INTERACTION,
            WorkspaceState.TRUST_REQUIRED,
            WorkspaceState.LOGIN_REQUIRED,
            WorkspaceState.STOPPING,
            WorkspaceState.EXITED,
            WorkspaceState.BROKEN,
            WorkspaceState.UNKNOWN,
        }
    ),
    WorkspaceState.NEEDS_INTERACTION: frozenset(
        {
            WorkspaceState.RUNNING,
            WorkspaceState.STOPPING,
            WorkspaceState.BROKEN,
            WorkspaceState.UNKNOWN,
        }
    ),
    WorkspaceState.TRUST_REQUIRED: frozenset(
        {
            WorkspaceState.RUNNING,
            WorkspaceState.STOPPING,
            WorkspaceState.BROKEN,
            WorkspaceState.UNKNOWN,
        }
    ),
    WorkspaceState.LOGIN_REQUIRED: frozenset(
        {
            WorkspaceState.RUNNING,
            WorkspaceState.STOPPING,
            WorkspaceState.BROKEN,
            WorkspaceState.UNKNOWN,
        }
    ),
    WorkspaceState.STOPPING: frozenset(
        {WorkspaceState.STOPPED, WorkspaceState.UNKNOWN, WorkspaceState.BROKEN}
    ),
    WorkspaceState.EXITED: frozenset({WorkspaceState.STARTING, WorkspaceState.STOPPING}),
    WorkspaceState.STOPPED: frozenset({WorkspaceState.STARTING}),
    WorkspaceState.MISSING: frozenset({WorkspaceState.STARTING, WorkspaceState.STOPPING}),
    WorkspaceState.COLLISION: frozenset({WorkspaceState.STOPPING, WorkspaceState.UNKNOWN}),
    WorkspaceState.BROKEN: frozenset(
        {WorkspaceState.STARTING, WorkspaceState.STOPPING, WorkspaceState.UNKNOWN}
    ),
    WorkspaceState.UNKNOWN: frozenset({WorkspaceState.STARTING, WorkspaceState.STOPPING}),
}


def _agent_type(value: AgentType | str) -> AgentType:
    try:
        return value if isinstance(value, AgentType) else AgentType(value)
    except (TypeError, ValueError) as exc:
        raise WAWDomainError("agent_type must be claude or codex") from exc


def _workspace_state(value: WorkspaceState | str) -> WorkspaceState:
    try:
        return value if isinstance(value, WorkspaceState) else WorkspaceState(value)
    except (TypeError, ValueError) as exc:
        raise WAWDomainError("workspace state is invalid") from exc


def _reconciliation_state(value: ReconciliationState | str) -> ReconciliationState:
    try:
        return value if isinstance(value, ReconciliationState) else ReconciliationState(value)
    except (TypeError, ValueError) as exc:
        raise WAWDomainError("reconciliation state is invalid") from exc


def _stop_result(value: StopResult | str) -> StopResult:
    try:
        return value if isinstance(value, StopResult) else StopResult(value)
    except (TypeError, ValueError) as exc:
        raise WAWDomainError("stop result is invalid") from exc


@dataclass(frozen=True)
class AgentWorkspaceSession:
    """Non-secret durable identity and lifecycle metadata for one WAW workspace."""

    project_id: str
    agent_type: AgentType | str
    runtime_host_installation_id: str
    runtime_host_installation_revision: int
    binding_revision: int
    binding_digest: str
    generation: int = 1
    state: WorkspaceState | str = WorkspaceState.STARTING
    reconciliation_state: ReconciliationState | str = ReconciliationState.AUTHORITATIVE
    id: str | None = None

    def __post_init__(self) -> None:
        validate_project_id(self.project_id)
        object.__setattr__(self, "agent_type", _agent_type(self.agent_type))
        validate_runtime_host_installation_id(self.runtime_host_installation_id)
        validate_positive_u64(
            self.runtime_host_installation_revision,
            field="runtime_host_installation_revision",
        )
        validate_positive_u64(self.binding_revision, field="binding_revision")
        validate_binding_digest(self.binding_digest)
        validate_positive_u64(self.generation, field="generation")
        object.__setattr__(self, "state", _workspace_state(self.state))
        object.__setattr__(
            self, "reconciliation_state", _reconciliation_state(self.reconciliation_state)
        )
        expected_id = workspace_id(self.project_id, self.agent_type)
        if self.id is None:
            object.__setattr__(self, "id", expected_id)
        elif validate_workspace_id(self.id) != expected_id:
            raise WAWDomainError("workspace id does not match project and agent_type")

    @property
    def workspace_id(self) -> str:
        assert self.id is not None
        return self.id

    @property
    def runtime_session_name(self) -> str:
        return managed_session_name(self.project_id, self.agent_type)

    @property
    def runtime_marker(self) -> str:
        return managed_marker(
            runtime_host_installation_id=self.runtime_host_installation_id,
            runtime_host_installation_revision=self.runtime_host_installation_revision,
            project_id=self.project_id,
            agent_type=self.agent_type,
            workspace_id_value=self.workspace_id,
            generation=self.generation,
            binding_revision=self.binding_revision,
            binding_digest=self.binding_digest,
        )

    def transition(
        self,
        state: WorkspaceState | str,
        *,
        reconciliation_state: ReconciliationState | str | None = None,
    ) -> AgentWorkspaceSession:
        target = _workspace_state(state)
        current = _workspace_state(self.state)
        if target is current:
            return self
        if target not in _TRANSITIONS[current]:
            raise WAWDomainError(f"invalid workspace transition {current}->{target}")
        next_reconciliation = self.reconciliation_state
        if reconciliation_state is not None:
            next_reconciliation = (
                reconciliation_state
                if isinstance(reconciliation_state, ReconciliationState)
                else _reconciliation_state(reconciliation_state)
            )
        return replace(self, state=target, reconciliation_state=next_reconciliation)


@dataclass(frozen=True)
class WriterLease:
    """One server-issued writer lease; terminal bytes are intentionally absent."""

    workspace_id: str
    attachment_id: str
    generation: int
    lease_number: int
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        validate_workspace_id(self.workspace_id)
        validate_attachment_id(self.attachment_id)
        validate_positive_u64(self.generation, field="generation")
        validate_positive_u64(self.lease_number, field="lease_number")
        if self.expires_at < self.issued_at:
            raise WAWDomainError("lease expiry precedes issuance")

    def matches(
        self, *, workspace_id: str, attachment_id: str, generation: int, lease_number: int
    ) -> bool:
        return (
            self.workspace_id == workspace_id
            and self.attachment_id == attachment_id
            and self.generation == generation
            and self.lease_number == lease_number
        )

    def active_at(self, now: datetime) -> bool:
        return self.issued_at <= now < self.expires_at


@dataclass(frozen=True)
class WriterLeaseSlot:
    """Immutable one-writer slot state used by an adapter under its own lock."""

    lease: WriterLease | None = None

    def acquire(self, lease: WriterLease, *, now: datetime) -> WriterLeaseSlot:
        if self.lease is not None and self.lease.active_at(now):
            raise WAWDomainError("workspace already has an active writer lease")
        return replace(self, lease=lease)

    def release(self, lease: WriterLease, *, now: datetime) -> WriterLeaseSlot:
        if self.lease is None:
            return self
        if not self.lease.matches(
            workspace_id=lease.workspace_id,
            attachment_id=lease.attachment_id,
            generation=lease.generation,
            lease_number=lease.lease_number,
        ):
            raise WAWDomainError("writer lease does not match current slot")
        return replace(self, lease=None)


def new_attachment_id() -> str:
    return f"att_{secrets.token_hex(16)}"


@dataclass(frozen=True)
class WorkspaceStopOperation:
    """Generation-keyed durable Stop intent; no process/path fields are allowed."""

    workspace_id: str
    project_id: str
    agent_type: AgentType | str
    generation: int
    binding_revision: int
    binding_digest: str
    runtime_host_installation_id: str
    runtime_host_installation_revision: int
    stop_operation_id: str | None = None
    result: StopResult | str = StopResult.PENDING

    def __post_init__(self) -> None:
        validate_workspace_id(self.workspace_id)
        validate_project_id(self.project_id)
        if workspace_id(self.project_id, self.agent_type) != self.workspace_id:
            raise WAWDomainError("stop operation workspace does not match Project/AgentType")
        object.__setattr__(self, "agent_type", _agent_type(self.agent_type))
        validate_positive_u64(self.generation, field="generation")
        validate_positive_u64(self.binding_revision, field="binding_revision")
        validate_binding_digest(self.binding_digest)
        validate_runtime_host_installation_id(self.runtime_host_installation_id)
        validate_positive_u64(
            self.runtime_host_installation_revision,
            field="runtime_host_installation_revision",
        )
        object.__setattr__(self, "result", _stop_result(self.result))
        if self.stop_operation_id is None:
            object.__setattr__(self, "stop_operation_id", f"wso_{secrets.token_hex(16)}")
        else:
            validate_stop_operation_id(self.stop_operation_id)

    def complete(self, result: StopResult | str) -> WorkspaceStopOperation:
        outcome = _stop_result(result)
        if self.result is not StopResult.PENDING:
            if outcome is self.result:
                return self
            raise WAWDomainError("stop operation is already terminal")
        return replace(self, result=outcome)


__all__ = [
    "AgentType",
    "AgentWorkspaceSession",
    "GenerationCounter",
    "ReconciliationState",
    "StopResult",
    "WAWDomainError",
    "WorkspaceState",
    "WorkspaceStopOperation",
    "WriterLease",
    "WriterLeaseSlot",
    "managed_marker",
    "managed_session_name",
    "new_attachment_id",
    "validate_attachment_id",
    "validate_binding_digest",
    "validate_positive_u64",
    "validate_project_id",
    "validate_runtime_host_installation_id",
    "validate_stop_operation_id",
    "validate_workspace_id",
    "workspace_id",
]
