"""Pure, fail-closed preflight for a future WAW attachment admission.

The helper intentionally stops before WebSocket/Noise handshake or Runtime
side effects.  It is safe to inject into tests/dev harnesses while production
attachment routing remains unavailable by default.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast
from urllib.parse import urlsplit

from agentbox_core.services import AuthenticatedSession
from agentbox_core.waw import validate_positive_u64, validate_runtime_host_installation_id
from agentbox_core.waw_models import AgentWorkspaceSessionRecord
from agentbox_core.waw_tickets import (
    AttachmentAuthority,
    AuthenticatedAttachmentContext,
    IssuedAttachmentTicket,
    TicketAuthorityError,
)

from agentbox_api.waw_authorization import WorkspaceAuthorizationPolicy

_POSITIVE_DECIMAL = re.compile(r"\A[1-9][0-9]{0,19}\Z")
_DEFAULT_ALLOWED_ORIGINS = frozenset({"https://agentbox.invalid"})


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
        try:
            validate_runtime_host_installation_id(self.runtime_host_installation_id)
            validate_positive_u64(
                self.runtime_host_installation_revision,
                field="runtime_host_installation_revision",
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Runtime host identity is invalid") from exc
        if not isinstance(self.ready, bool):
            raise ValueError("ready must be a boolean")
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
    allowed_origins: Collection[str] | None = None,
    expires_at: datetime | None = None,
) -> IssuedAttachmentTicket:
    """Run ordered admission checks and issue one transient attachment ticket.

    The returned bearer exists only in the caller's transient response.  This
    helper performs no database, Runtime, WebSocket, or Audit writes.
    """

    _validate_origin(origin, allowed_origins)
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
        raise WAWAdmissionError("RUNTIME_INSTALLATION_MISMATCH", "Runtime host identity is stale")
    try:
        context = AuthenticatedAttachmentContext(
            session_id=authenticated.session_id,
            user_id=authenticated.user_id,
            authorization_scope=row.authorization_scope,
            origin=origin,
            runtime_epoch=runtime.runtime_epoch,
            auth_epoch=authenticated.auth_epoch,
        )
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
            context=context,
        )
    except TicketAuthorityError as exc:
        raise WAWAdmissionError(exc.code.value, str(exc)) from exc


class ProtocolRecentAuth(Protocol):
    def is_recently_authenticated(self, authenticated: AuthenticatedSession) -> bool: ...


def _validate_origin(origin: str, allowed_origins: Collection[str] | None) -> None:
    allowed = _DEFAULT_ALLOWED_ORIGINS if allowed_origins is None else frozenset(allowed_origins)
    if not isinstance(origin, str) or len(origin) > 256 or origin not in allowed:
        raise WAWAdmissionError("ORIGIN_INVALID", "Origin is not allowlisted")
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise WAWAdmissionError("ORIGIN_INVALID", "Origin is not canonical")


__all__ = [
    "ProtocolRecentAuth",
    "WAWAdmissionError",
    "WAWRuntimeReadiness",
    "WorkspaceAdmissionRow",
    "prepare_attachment",
]
