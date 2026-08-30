"""Pure, fail-closed preflight for a future WAW attachment admission.

The helper intentionally stops before WebSocket/Noise handshake or Runtime
side effects.  It is safe to inject into tests/dev harnesses while production
attachment routing remains unavailable by default.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast

from agentbox_core.services import AuthenticatedSession
from agentbox_core.waw_models import AgentWorkspaceSessionRecord
from agentbox_core.waw_tickets import AttachmentAuthority, IssuedAttachmentTicket, TicketAuthorityError
from agentbox_api.waw_authorization import WorkspaceAuthorizationPolicy

_POSITIVE_DECIMAL = re.compile(r"\A[1-9][0-9]{0,19}\Z")


class WAWAdmissionError(RuntimeError):
    """A bounded preflight rejection with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class WorkspaceAdmissionRow(Protocol):
    id: str
    project_id: str
    authorization_scope: str
    agent_type: str
    generation: int
    binding_revision: int
    binding_digest: str
    runtime_host_installation_id: str
    runtime_host_installation_revision: int
    state: str


@dataclass(frozen=True)
class WAWRuntimeReadiness:
    """Explicit, already-attested Runtime identity for preflight only."""

    runtime_host_installation_id: str
    runtime_host_installation_revision: int
    runtime_epoch: str
    ready: bool = True

    def __post_init__(self) -> None:
        if not self.runtime_host_installation_id or self.runtime_host_installation_revision < 1:
            raise ValueError("Runtime host identity is invalid")
        if _POSITIVE_DECIMAL.fullmatch(self.runtime_epoch) is None:
            raise ValueError("runtime_epoch is invalid")


def prepare_attachment(
    *,
    authenticated: AuthenticatedSession,
    row: WorkspaceAdmissionRow,
    policy: WorkspaceAuthorizationPolicy,
    recent_authenticator: ProtocolRecentAuth,
    runtime: WAWRuntimeReadiness | None,
    bound_runtime_epoch: str | None,
    authority: AttachmentAuthority,
    origin: str = "https://agentbox.invalid",
    expires_at: datetime | None = None,
) -> IssuedAttachmentTicket:
    """Run ordered admission checks and issue one transient attachment ticket.

    The returned bearer exists only in the caller's transient response.  This
    helper performs no database, Runtime, WebSocket, or Audit writes.
    """

    if not policy.allows(authenticated, cast(AgentWorkspaceSessionRecord, row)):
        raise WAWAdmissionError("WORKSPACE_NOT_FOUND", "Workspace is not available")
    if not recent_authenticator.is_recently_authenticated(authenticated):
        raise WAWAdmissionError("RECENT_AUTH_REQUIRED", "Recent authentication is required")
    if row.state != "RUNNING":
        raise WAWAdmissionError("WORKSPACE_NOT_RUNNING", "Workspace is not running")
    if runtime is None or not runtime.ready:
        raise WAWAdmissionError("RUNTIME_UNAVAILABLE", "WAW Runtime is not ready")
    if bound_runtime_epoch is None or runtime.runtime_epoch != bound_runtime_epoch:
        raise WAWAdmissionError("RUNTIME_INSTALLATION_MISMATCH", "Runtime epoch is stale")
    if (
        runtime.runtime_host_installation_id != row.runtime_host_installation_id
        or runtime.runtime_host_installation_revision != row.runtime_host_installation_revision
    ):
        raise WAWAdmissionError(
            "RUNTIME_INSTALLATION_MISMATCH", "Runtime host identity is stale"
        )
    try:
        return authority.issue(
            workspace_id=row.id,
            project_id=row.project_id,
            agent_type=row.agent_type,
            attachment_id=f"att_{secrets.token_hex(16)}",
            generation=row.generation,
            auth_epoch=authenticated.auth_epoch,
            runtime_host_installation_id=row.runtime_host_installation_id,
            runtime_host_installation_revision=row.runtime_host_installation_revision,
            binding_revision=row.binding_revision,
            binding_digest=row.binding_digest,
            origin=origin,
            expires_at=expires_at,
        )
    except TicketAuthorityError as exc:
        raise WAWAdmissionError(exc.code.value, str(exc)) from exc


class ProtocolRecentAuth(Protocol):
    def is_recently_authenticated(self, authenticated: AuthenticatedSession) -> bool: ...


__all__ = [
    "ProtocolRecentAuth",
    "WAWAdmissionError",
    "WAWRuntimeReadiness",
    "WorkspaceAdmissionRow",
    "prepare_attachment",
]
