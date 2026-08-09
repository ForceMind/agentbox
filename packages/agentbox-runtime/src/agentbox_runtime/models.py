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
