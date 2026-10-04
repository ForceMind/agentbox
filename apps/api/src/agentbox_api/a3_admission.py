"""Default-unwired, read-only A3 authentication adapter. No Runtime import.

The API retains only session/user IDs and auth epoch. The cross-boundary result
contains no session ID, username, cookie, CSRF value or authentication secret.
Calling current never authenticates again or refreshes idle/absolute expiry.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime

from agentbox_core.models import AdminUser, ControlPlaneSession, Project
from agentbox_core.services import AuthenticatedSession, ControlPlaneServices
from agentbox_core.waw_models import ProjectBindingRecord, RuntimeHostInstallation
from agentbox_core.waw_project_bindings import ProjectBindingStatus
from agentbox_protocol.a3_admission import A3CurrentAdmission
from sqlalchemy import select


class A3SessionCurrentness:
    def __init__(
        self,
        services: ControlPlaneServices,
        authenticated: AuthenticatedSession,
        *,
        runtime_epoch: Callable[[], str | None],
    ) -> None:
        if type(authenticated) is not AuthenticatedSession:
            raise TypeError("authenticated API session required")
        self._services = services
        self._session_id = authenticated.session_id
        self._user_id = authenticated.user_id
        self._auth_epoch = authenticated.auth_epoch
        self._epoch = runtime_epoch
        self._last: datetime | None = None
        self._closed = False
        # Noncredential domain-separated identity commitment, not bearer authority.
        self.session_scope = hashlib.sha256(
            b"agentbox-a3-content/session-scope/v1\0"
            + authenticated.session_id.encode("ascii")
            + b"\0"
            + authenticated.user_id.encode("ascii")
            + b"\0"
            + str(authenticated.auth_epoch).encode("ascii")
        ).digest()

    def close(self) -> None:
        self._closed = True

    def current(self, project_id: str, session_scope: bytes) -> A3CurrentAdmission | None:
        if self._closed or type(session_scope) is not bytes or session_scope != self.session_scope:
            return None
        try:
            with self._services.database.transaction() as session:
                row = session.get(ControlPlaneSession, self._session_id)
                user = session.get(AdminUser, self._user_id)
                project = session.get(Project, project_id)
                now = self._services.database.transaction_now(session)
                if (
                    row is None
                    or user is None
                    or not user.is_active
                    or row.user_id != self._user_id
                    or row.auth_epoch != self._auth_epoch
                    or row.revoked_at is not None
                    or now < row.last_seen_at
                    or now < row.recent_authenticated_at
                    or (self._last is not None and now < self._last)
                    or now >= min(row.expires_at, row.idle_expires_at)
                ):
                    self.close()
                    return None
                self._last = now
                if project is None or project.archived_at is not None or project.state != "ready":
                    return None
                bindings = list(
                    session.scalars(
                        select(ProjectBindingRecord).where(
                            ProjectBindingRecord.project_id == project_id,
                            ProjectBindingRecord.status == ProjectBindingStatus.CURRENT.value,
                        )
                    )
                )
                if len(bindings) != 1:
                    return None
                binding = bindings[0]
                host = session.get(RuntimeHostInstallation, binding.runtime_host_installation_id)
                epoch = self._epoch()
                if (
                    binding.binding_digest is None
                    or project.revision != binding.project_revision
                    or project.relative_path != binding.relative_key
                    or host is None
                    or host.revision != binding.runtime_host_installation_revision
                    or epoch is None
                    or host.last_runtime_epoch != epoch
                ):
                    return None
                return A3CurrentAdmission(
                    project_id,
                    binding.relative_key,
                    str(binding.project_revision),
                    str(binding.binding_revision),
                    binding.binding_digest,
                    host.id,
                    str(host.revision),
                    epoch,
                    self.session_scope,
                    self._auth_epoch,
                )
        except Exception:
            self.close()
            return None
