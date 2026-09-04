"""Host-wide bidirectional conflict coordinator for WAW and legacy starts.

The coordinator owns the shared start lock.  A successful acquire returns a
lease that the caller holds through its exact start/reservation boundary.  It
only decides and serializes; it never adopts, migrates, stops, or launches a
legacy or WAW process.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from agentbox_core.waw import AgentType, validate_project_id


class WAWConflictError(RuntimeError):
    """A start is denied or the shared conflict lease is misused."""

    def __init__(self, code: str) -> None:
        if code not in {"PROJECT_RUNTIME_ACTIVE", "CODEX_REMOTE_CONFLICT"}:
            raise ValueError("conflict code is invalid")
        super().__init__(code)
        self.code = code


class WAWLegacyClaudeState(StrEnum):
    ABSENT = "ABSENT"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    NEEDS_INTERACTION = "NEEDS_INTERACTION"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    TRUST_REQUIRED = "TRUST_REQUIRED"
    BROKEN = "BROKEN"
    UNKNOWN = "UNKNOWN"
    STOPPED = "STOPPED"
    EXITED = "EXITED"


class WAWLegacyCodexState(StrEnum):
    ABSENT = "ABSENT"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    NEEDS_INTERACTION = "NEEDS_INTERACTION"
    BROKEN = "BROKEN"
    UNKNOWN = "UNKNOWN"
    STOPPED = "STOPPED"
    EXITED = "EXITED"


class WAWManagedConflictState(StrEnum):
    ABSENT = "ABSENT"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    NEEDS_INTERACTION = "NEEDS_INTERACTION"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    TRUST_REQUIRED = "TRUST_REQUIRED"
    STOPPING = "STOPPING"
    BROKEN = "BROKEN"
    UNKNOWN = "UNKNOWN"
    COLLISION = "COLLISION"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    INPUT_UNCERTAIN = "INPUT_UNCERTAIN"
    STOPPED = "STOPPED"
    EXITED = "EXITED"


_CLAUDE_CONFLICT = frozenset(
    {
        WAWLegacyClaudeState.STARTING,
        WAWLegacyClaudeState.RUNNING,
        WAWLegacyClaudeState.NEEDS_INTERACTION,
        WAWLegacyClaudeState.LOGIN_REQUIRED,
        WAWLegacyClaudeState.TRUST_REQUIRED,
        WAWLegacyClaudeState.BROKEN,
        WAWLegacyClaudeState.UNKNOWN,
    }
)
_CODEX_CONFLICT = frozenset(
    {
        WAWLegacyCodexState.STARTING,
        WAWLegacyCodexState.RUNNING,
        WAWLegacyCodexState.NEEDS_INTERACTION,
        WAWLegacyCodexState.BROKEN,
        WAWLegacyCodexState.UNKNOWN,
    }
)
_WAW_TERMINAL = frozenset(
    {
        WAWManagedConflictState.ABSENT,
        WAWManagedConflictState.STOPPED,
        WAWManagedConflictState.EXITED,
    }
)

# The Runtime service represents one host. Sharing this lock prevents separate
# legacy/WAW coordinator instances from splitting the host start critical section.
_HOST_START_LOCK = threading.Lock()


@runtime_checkable
class WAWConflictProbe(Protocol):
    """Read-only exact state probes called only while the host lock is held."""

    def legacy_claude(self, project_id: str) -> WAWLegacyClaudeState:
        """Return the same-Project legacy Claude state or positive ABSENT."""

    def legacy_codex_remote(self) -> WAWLegacyCodexState:
        """Return the host-global Codex Remote state or positive ABSENT."""

    def waw_for_project(self, project_id: str) -> tuple[WAWManagedConflictState, ...]:
        """Return every WAW row for one Project and both AgentTypes."""

    def waw_for_host(self) -> tuple[WAWManagedConflictState, ...]:
        """Return every WAW row on the Runtime host."""


@dataclass(frozen=True)
class _LeaseIdentity:
    operation: str
    project_id: str | None
    agent_type: AgentType | None


class WAWConflictLease:
    """Exclusive host start lease; release is idempotent."""

    def __init__(
        self,
        coordinator: WAWConflictCoordinator,
        identity: _LeaseIdentity,
    ) -> None:
        self._coordinator = coordinator
        self._identity = identity
        self._released = False

    @property
    def operation(self) -> str:
        return self._identity.operation

    @property
    def project_id(self) -> str | None:
        return self._identity.project_id

    @property
    def agent_type(self) -> AgentType | None:
        return self._identity.agent_type

    @property
    def released(self) -> bool:
        return self._released

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._coordinator._release(self)

    def __enter__(self) -> WAWConflictLease:
        if self._released:
            raise WAWConflictError("PROJECT_RUNTIME_ACTIVE")
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


class WAWConflictCoordinator:
    """One Runtime-host conflict authority shared by WAW and legacy actions."""

    def __init__(self, probe: WAWConflictProbe) -> None:
        if not isinstance(probe, WAWConflictProbe):
            raise TypeError("probe must implement WAWConflictProbe")
        self._probe = probe
        self._lock = _HOST_START_LOCK
        self._active: WAWConflictLease | None = None

    def acquire_waw_start(self, *, project_id: str, agent_type: AgentType) -> WAWConflictLease:
        validate_project_id(project_id)
        if type(agent_type) is not AgentType:
            raise ValueError("agent_type is invalid")
        self._lock.acquire()
        try:
            # Required deterministic precedence: same-Project Claude is checked
            # before the host-global Codex Remote predicate.
            try:
                claude_state = self._probe.legacy_claude(project_id)
            except Exception as exc:
                raise WAWConflictError("PROJECT_RUNTIME_ACTIVE") from exc
            if type(claude_state) is not WAWLegacyClaudeState or claude_state in _CLAUDE_CONFLICT:
                raise WAWConflictError("PROJECT_RUNTIME_ACTIVE")
            try:
                codex_state = self._probe.legacy_codex_remote()
            except Exception as exc:
                raise WAWConflictError("CODEX_REMOTE_CONFLICT") from exc
            if type(codex_state) is not WAWLegacyCodexState or codex_state in _CODEX_CONFLICT:
                raise WAWConflictError("CODEX_REMOTE_CONFLICT")
            return self._lease(_LeaseIdentity("WAW_START", project_id, agent_type))
        except BaseException:
            self._lock.release()
            raise

    def acquire_legacy_claude_start(self, *, project_id: str) -> WAWConflictLease:
        validate_project_id(project_id)
        self._lock.acquire()
        try:
            try:
                states = self._probe.waw_for_project(project_id)
                self._validate_waw_states(states)
            except Exception as exc:
                raise WAWConflictError("PROJECT_RUNTIME_ACTIVE") from exc
            if any(state not in _WAW_TERMINAL for state in states):
                raise WAWConflictError("PROJECT_RUNTIME_ACTIVE")
            return self._lease(_LeaseIdentity("LEGACY_CLAUDE_START", project_id, None))
        except BaseException:
            self._lock.release()
            raise

    def acquire_legacy_codex_start(self) -> WAWConflictLease:
        self._lock.acquire()
        try:
            try:
                states = self._probe.waw_for_host()
                self._validate_waw_states(states)
            except Exception as exc:
                raise WAWConflictError("CODEX_REMOTE_CONFLICT") from exc
            if any(state not in _WAW_TERMINAL for state in states):
                raise WAWConflictError("CODEX_REMOTE_CONFLICT")
            return self._lease(_LeaseIdentity("LEGACY_CODEX_START", None, None))
        except BaseException:
            self._lock.release()
            raise

    def _lease(self, identity: _LeaseIdentity) -> WAWConflictLease:
        if self._active is not None:
            raise AssertionError("host conflict lock has an existing lease")
        lease = WAWConflictLease(self, identity)
        self._active = lease
        return lease

    def _release(self, lease: WAWConflictLease) -> None:
        if self._active is not lease:
            raise WAWConflictError("PROJECT_RUNTIME_ACTIVE")
        self._active = None
        self._lock.release()

    @staticmethod
    def _validate_waw_states(states: object) -> None:
        if type(states) is not tuple or any(
            type(state) is not WAWManagedConflictState for state in states
        ):
            raise ValueError("WAW conflict probe result is invalid")


__all__ = [
    "WAWConflictCoordinator",
    "WAWConflictError",
    "WAWConflictLease",
    "WAWConflictProbe",
    "WAWLegacyClaudeState",
    "WAWLegacyCodexState",
    "WAWManagedConflictState",
]
