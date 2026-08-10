"""Typed, non-secret Codex Runtime observations and action results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class CapabilityState(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class InstallationType(StrEnum):
    STANDALONE = "standalone"
    NPM = "npm"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


class AuthenticationState(StrEnum):
    AUTHENTICATED = "authenticated"
    UNAUTHENTICATED = "unauthenticated"
    UNKNOWN = "unknown"


class RemoteState(StrEnum):
    RUNNING = "running"
    STOPPED = "stopped"
    BROKEN = "broken"
    UNKNOWN = "unknown"


class ClaudeSessionState(StrEnum):
    RUNNING = "running"
    STOPPED = "stopped"
    STARTING = "starting"
    NEEDS_INTERACTION = "needs_interaction"
    BROKEN = "broken"
    UNKNOWN = "unknown"


class WorkspaceState(StrEnum):
    UNKNOWN = "unknown"
    REQUIRES_USER_CONFIRMATION = "requires_user_confirmation"
    INITIALIZED_BY_AGENTBOX = "initialized_by_agentbox"


@dataclass(frozen=True)
class CodexCapabilities:
    remote_control: CapabilityState = CapabilityState.UNKNOWN
    start: CapabilityState = CapabilityState.UNKNOWN
    stop: CapabilityState = CapabilityState.UNKNOWN
    pair: CapabilityState = CapabilityState.UNKNOWN
    status: CapabilityState = CapabilityState.UNKNOWN


@dataclass(frozen=True)
class DiagnosticFinding:
    code: str
    severity: str
    summary: str
    remediation: str | None = None


@dataclass(frozen=True)
class CodexStatus:
    installed: bool
    version: str | None
    selected_executable: str | None
    alternatives: tuple[str, ...] = ()
    installation_type: InstallationType = InstallationType.UNKNOWN
    conflict_detected: bool = False
    authentication: AuthenticationState = AuthenticationState.UNKNOWN
    capabilities: CodexCapabilities = field(default_factory=CodexCapabilities)
    remote_state: RemoteState = RemoteState.UNKNOWN
    remote_confidence: str = "unknown"
    diagnostics: tuple[DiagnosticFinding, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RemoteActionResult:
    outcome: str
    remote_state: RemoteState

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PairCodeResult:
    code: str
    expires_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClaudeCapabilities:
    remote_control: CapabilityState = CapabilityState.UNKNOWN
    remote_start: CapabilityState = CapabilityState.UNKNOWN
    version: CapabilityState = CapabilityState.UNKNOWN


@dataclass(frozen=True)
class ClaudeSession:
    project_id: str
    display_name: str
    state: ClaudeSessionState
    managed: bool
    session_name: str
    attach_command: str
    workspace_state: WorkspaceState = WorkspaceState.UNKNOWN
    tmux_running: bool = False
    remote_readiness: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClaudeStatus:
    installed: bool
    version: str | None
    authentication: AuthenticationState
    capabilities: ClaudeCapabilities
    tmux_installed: bool
    tmux_version: str | None
    managed_sessions: int
    unmanaged_sessions: int
    workspace_interaction_warnings: int
    diagnostics: tuple[DiagnosticFinding, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClaudeSessionActionResult:
    outcome: str
    session: ClaudeSession

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClaudeSessionOutput:
    project_id: str
    session_name: str
    output: str
    truncated: bool
    sensitive: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProjectWorkspace:
    project_key: str
    display_name: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GitStatus:
    is_repository: bool
    branch: str | None = None
    detached_head: bool = False
    unborn_branch: bool = False
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0
    staged_count: int = 0
    unstaged_count: int = 0
    untracked_count: int = 0
    conflicted_count: int = 0
    clean: bool = True
    remote_url: str | None = None
    submodules_detected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GitInstallationStatus:
    installed: bool
    version: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GitBranch:
    name: str
    current: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GitActionResult:
    outcome: str
    branch: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GitHubStatus:
    installed: bool
    version: str | None
    authentication: AuthenticationState

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GitHubProjectStatus:
    available: bool
    repository: str | None = None
    pull_request_number: int | None = None
    pull_request_title: str | None = None
    pull_request_state: str | None = None
    pull_request_draft: bool | None = None
    pull_request_url: str | None = None
    checks: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GitHubPullRequestResult:
    number: int | None
    url: str
    draft: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RuntimeOperationError(Exception):
    """Normalized Runtime failure that never embeds captured process output."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        category: str = "broken",
        retryable: bool = False,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.category = category
        self.retryable = retryable
        self.retry_after = retry_after
