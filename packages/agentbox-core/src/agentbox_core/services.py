"""Minimal Phase 3 application services for admin, auth, sessions, and audit."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agentbox_core.clock import Clock, SystemClock
from agentbox_core.configuration import Settings
from agentbox_core.database import Database
from agentbox_core.errors import (
    AdminAlreadyInitialized,
    AdminNotInitialized,
    InvalidCredentials,
    InvalidCsrfToken,
    InvalidSession,
    LoginRateLimited,
)
from agentbox_core.jobs import JobService
from agentbox_core.models import AdminUser, AuditEvent, ControlPlaneSession, Job
from agentbox_core.projects import ProjectService
from agentbox_core.rate_limit import LoginRateLimiter
from agentbox_core.security import (
    PasswordManager,
    derive_csrf_token,
    generate_session_token,
    keyed_digest,
    new_identifier,
    normalize_username,
    sanitize_metadata,
    source_fingerprint,
)


@dataclass(frozen=True)
class IssuedSession:
    token: str
    csrf_token: str
    session_id: str
    user_id: str
    username: str
    expires_at: datetime
    authenticated_at: datetime


@dataclass(frozen=True)
class AuthenticatedSession:
    session_id: str
    user_id: str
    username: str
    expires_at: datetime
    authenticated_at: datetime
    csrf_token: str


@dataclass(frozen=True)
class SessionMetadata:
    session_id: str
    created_at: datetime
    last_seen_at: datetime
    idle_expires_at: datetime
    expires_at: datetime
    client_label: str | None


class AuditService:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def record(
        self,
        session: Session,
        *,
        actor_type: str,
        actor_id: str | None,
        action: str,
        result: str,
        request_id: str | None,
        target_type: str | None = None,
        target_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            id=new_identifier("aud"),
            actor_type=actor_type[:32],
            actor_id=actor_id[:80] if actor_id else None,
            action=action[:80],
            target_type=target_type[:40] if target_type else None,
            target_id=target_id[:80] if target_id else None,
            result=result[:32],
            request_id=request_id[:72] if request_id else None,
            created_at=self._clock.now(),
            metadata_json=sanitize_metadata(metadata),
        )
        session.add(event)
        return event


class AdminService:
    def __init__(
        self,
        database: Database,
        password_manager: PasswordManager,
        audit: AuditService,
        clock: Clock | None = None,
    ) -> None:
        self._database = database
        self._password_manager = password_manager
        self._audit = audit
        self._clock = clock or SystemClock()

    def initialize(self, username: str, password: str, request_id: str | None = None) -> AdminUser:
        normalized = normalize_username(username)
        password_hash = self._password_manager.hash(password)
        now = self._clock.now()
        try:
            with self._database.transaction() as session:
                session.execute(text("BEGIN IMMEDIATE"))
                if session.scalar(
                    select(func.count()).select_from(AdminUser).where(AdminUser.is_active.is_(True))
                ):
                    raise AdminAlreadyInitialized()
                admin = AdminUser(
                    id=new_identifier("adm"),
                    username=username.strip(),
                    username_normalized=normalized,
                    password_hash=password_hash,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
                session.add(admin)
                self._audit.record(
                    session,
                    actor_type="local_admin",
                    actor_id=admin.id,
                    action="admin_initialized",
                    result="succeeded",
                    request_id=request_id,
                    target_type="admin_user",
                    target_id=admin.id,
                )
                session.flush()
                return admin
        except IntegrityError as exc:
            raise AdminAlreadyInitialized() from exc

    def status(self) -> tuple[bool, str | None]:
        with self._database.transaction() as session:
            admin = session.scalar(select(AdminUser).where(AdminUser.is_active.is_(True)))
            return admin is not None, admin.username if admin else None

    def change_password(
        self,
        current_password: str,
        new_password: str,
        *,
        request_id: str | None = None,
    ) -> int:
        """Change the sole administrator password and revoke every Session."""
        admin_id, observed_hash = self._verify_local_password(current_password)
        replacement_hash = self._password_manager.hash(new_password)
        now = self._clock.now()
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            admin = session.get(AdminUser, admin_id)
            if (
                admin is None
                or not admin.is_active
                or not hmac.compare_digest(admin.password_hash, observed_hash)
            ):
                raise InvalidCredentials()
            admin.password_hash = replacement_hash
            admin.updated_at = now
            active_sessions = tuple(
                session.scalars(
                    select(ControlPlaneSession).where(
                        ControlPlaneSession.user_id == admin.id,
                        ControlPlaneSession.revoked_at.is_(None),
                    )
                )
            )
            for stored in active_sessions:
                stored.revoked_at = now
            self._audit.record(
                session,
                actor_type="local_admin",
                actor_id=admin.id,
                action="admin_password_changed",
                result="succeeded",
                request_id=request_id,
                target_type="admin_user",
                target_id=admin.id,
                metadata={"revoked_count": len(active_sessions)},
            )
            return len(active_sessions)

    def sessions(self, current_password: str) -> tuple[SessionMetadata, ...]:
        admin_id, _observed_hash = self._verify_local_password(current_password)
        now = self._clock.now()
        with self._database.transaction() as session:
            return tuple(
                SessionMetadata(
                    session_id=stored.id,
                    created_at=stored.created_at,
                    last_seen_at=stored.last_seen_at,
                    idle_expires_at=stored.idle_expires_at,
                    expires_at=stored.expires_at,
                    client_label=stored.client_label,
                )
                for stored in session.scalars(
                    select(ControlPlaneSession)
                    .where(
                        ControlPlaneSession.user_id == admin_id,
                        ControlPlaneSession.revoked_at.is_(None),
                        ControlPlaneSession.expires_at > now,
                        ControlPlaneSession.idle_expires_at > now,
                    )
                    .order_by(ControlPlaneSession.created_at.desc())
                )
            )

    def revoke_sessions(self, current_password: str, *, request_id: str | None = None) -> int:
        admin_id, _observed_hash = self._verify_local_password(current_password)
        now = self._clock.now()
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            active_sessions = tuple(
                session.scalars(
                    select(ControlPlaneSession).where(
                        ControlPlaneSession.user_id == admin_id,
                        ControlPlaneSession.revoked_at.is_(None),
                    )
                )
            )
            for stored in active_sessions:
                stored.revoked_at = now
            self._audit.record(
                session,
                actor_type="local_admin",
                actor_id=admin_id,
                action="admin_sessions_revoked",
                result="succeeded",
                request_id=request_id,
                target_type="admin_user",
                target_id=admin_id,
                metadata={"revoked_count": len(active_sessions)},
            )
            return len(active_sessions)

    def _verify_local_password(self, password: str) -> tuple[str, str]:
        with self._database.transaction() as session:
            admin = session.scalar(select(AdminUser).where(AdminUser.is_active.is_(True)))
            if admin is None:
                raise AdminNotInitialized()
            admin_id = admin.id
            encoded_hash = admin.password_hash
        if not self._password_manager.verify(encoded_hash, password):
            raise InvalidCredentials()
        return admin_id, encoded_hash


class SessionService:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        audit: AuditService,
        clock: Clock,
    ) -> None:
        self._database = database
        self._settings = settings
        self._audit = audit
        self._clock = clock
        self._secret = settings.secret_key.get_secret_value()

    def issue(self, session: Session, user: AdminUser, client_label: str | None) -> IssuedSession:
        now = self._clock.now()
        active_sessions = list(
            session.scalars(
                select(ControlPlaneSession)
                .where(
                    ControlPlaneSession.user_id == user.id,
                    ControlPlaneSession.revoked_at.is_(None),
                    ControlPlaneSession.expires_at > now,
                    ControlPlaneSession.idle_expires_at > now,
                )
                .order_by(ControlPlaneSession.created_at.asc())
            )
        )
        excess = len(active_sessions) - self._settings.max_active_sessions + 1
        for stale in active_sessions[: max(0, excess)]:
            stale.revoked_at = now
            self._audit.record(
                session,
                actor_type="system",
                actor_id=None,
                action="session_revoked",
                result="succeeded",
                request_id=None,
                target_type="session",
                target_id=stale.id,
                metadata={"reason": "active_session_limit"},
            )

        raw_token = generate_session_token()
        session_id = new_identifier("ses")
        token_hash = keyed_digest(self._secret, "session-token", raw_token)
        csrf_token = derive_csrf_token(self._secret, session_id, token_hash)
        csrf_hash = keyed_digest(self._secret, "csrf-verifier", csrf_token)
        expires_at = now + timedelta(seconds=self._settings.session_ttl)
        idle_expires_at = min(
            expires_at,
            now + timedelta(seconds=self._settings.session_idle_ttl),
        )
        session.add(
            ControlPlaneSession(
                id=session_id,
                user_id=user.id,
                token_hash=token_hash,
                csrf_hash=csrf_hash,
                created_at=now,
                last_seen_at=now,
                idle_expires_at=idle_expires_at,
                expires_at=expires_at,
                client_label=client_label[:80] if client_label else None,
            )
        )
        return IssuedSession(
            token=raw_token,
            csrf_token=csrf_token,
            session_id=session_id,
            user_id=user.id,
            username=user.username,
            expires_at=expires_at,
            authenticated_at=now,
        )

    def authenticate(self, raw_token: str | None) -> AuthenticatedSession:
        if not raw_token or len(raw_token) > 128:
            raise InvalidSession()
        token_hash = keyed_digest(self._secret, "session-token", raw_token)
        now = self._clock.now()
        with self._database.transaction() as session:
            stored = session.scalar(
                select(ControlPlaneSession)
                .join(ControlPlaneSession.user)
                .where(ControlPlaneSession.token_hash == token_hash)
            )
            if (
                stored is None
                or stored.revoked_at is not None
                or stored.expires_at <= now
                or stored.idle_expires_at <= now
                or not stored.user.is_active
            ):
                raise InvalidSession()
            stored.last_seen_at = now
            stored.idle_expires_at = min(
                stored.expires_at,
                now + timedelta(seconds=self._settings.session_idle_ttl),
            )
            csrf_token = derive_csrf_token(self._secret, stored.id, stored.token_hash)
            return AuthenticatedSession(
                session_id=stored.id,
                user_id=stored.user.id,
                username=stored.user.username,
                expires_at=stored.expires_at,
                authenticated_at=stored.created_at,
                csrf_token=csrf_token,
            )

    def validate_csrf(self, authenticated: AuthenticatedSession, supplied: str | None) -> None:
        if not supplied or len(supplied) > 128:
            raise InvalidCsrfToken()
        supplied_hash = keyed_digest(self._secret, "csrf-verifier", supplied)
        with self._database.transaction() as session:
            stored_hash = session.scalar(
                select(ControlPlaneSession.csrf_hash).where(
                    ControlPlaneSession.id == authenticated.session_id
                )
            )
        if stored_hash is None or not hmac.compare_digest(stored_hash, supplied_hash):
            raise InvalidCsrfToken()

    def is_recently_authenticated(
        self, authenticated: AuthenticatedSession, *, max_age_seconds: int
    ) -> bool:
        return self._clock.now() - authenticated.authenticated_at <= timedelta(
            seconds=max_age_seconds
        )

    def revoke(
        self,
        authenticated: AuthenticatedSession,
        *,
        request_id: str | None,
        reason: str = "logout",
    ) -> None:
        now = self._clock.now()
        with self._database.transaction() as session:
            stored = session.get(ControlPlaneSession, authenticated.session_id)
            if stored is None or stored.revoked_at is not None:
                raise InvalidSession()
            stored.revoked_at = now
            self._audit.record(
                session,
                actor_type="admin",
                actor_id=authenticated.user_id,
                action="logout" if reason == "logout" else "session_revoked",
                result="succeeded",
                request_id=request_id,
                target_type="session",
                target_id=authenticated.session_id,
                metadata={"reason": reason},
            )

    def cleanup(self) -> int:
        now = self._clock.now()
        cutoff = now - timedelta(seconds=self._settings.session_retention)
        with self._database.transaction() as session:
            result = cast(
                CursorResult[object],
                session.connection().execute(
                    delete(ControlPlaneSession).where(
                        or_(
                            ControlPlaneSession.expires_at <= cutoff,
                            ControlPlaneSession.idle_expires_at <= cutoff,
                            ControlPlaneSession.revoked_at <= cutoff,
                        )
                    )
                ),
            )
            return int(result.rowcount or 0)


class AuthService:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        password_manager: PasswordManager,
        session_service: SessionService,
        audit: AuditService,
        rate_limiter: LoginRateLimiter,
        clock: Clock,
    ) -> None:
        self._database = database
        self._password_manager = password_manager
        self._sessions = session_service
        self._audit = audit
        self._rate_limiter = rate_limiter
        self._clock = clock
        self._secret = settings.secret_key.get_secret_value()

    def login(
        self,
        *,
        username: str,
        password: str,
        source_identifier: str,
        request_id: str | None,
        client_label: str | None = None,
    ) -> IssuedSession:
        try:
            normalized = normalize_username(username)
        except ValueError:
            # This sentinel cannot be produced by normalize_username, so
            # malformed input cannot collide with a legitimate `invalid` user
            # and lock that account through the persistent limiter.
            normalized = "\0invalid"

        decision = self._rate_limiter.check(normalized, source_identifier)
        if not decision.allowed:
            self._record_failed_login(
                normalized, source_identifier, request_id, reason="rate_limited"
            )
            raise LoginRateLimited(retry_after=decision.retry_after)

        with self._database.transaction() as session:
            user = session.scalar(
                select(AdminUser).where(AdminUser.username_normalized == normalized)
            )
            user_id = user.id if user is not None else None
            encoded_hash = (
                user.password_hash if user is not None else self._password_manager.dummy_hash
            )
            active = bool(user is not None and user.is_active)

        # Password work deliberately runs outside a database transaction. The
        # API schedules this complete login method on its bounded thread gate,
        # so verification (including the dummy path) never blocks its event loop.
        password_ok = self._password_manager.verify(encoded_hash, password)

        if not password_ok or not active or user_id is None:
            self._rate_limiter.register_failure(normalized, source_identifier)
            self._record_failed_login(
                normalized, source_identifier, request_id, reason="invalid_credentials"
            )
            raise InvalidCredentials()

        replacement_hash = None
        if self._password_manager.needs_rehash(encoded_hash):
            replacement_hash = self._password_manager.hash(password)

        now = self._clock.now()
        try:
            with self._database.transaction() as session:
                # Reserve SQLite's single writer before revalidating the hash.
                # Password rotation then either commits first and invalidates
                # this Login, or waits until this Session is committed and
                # revokes it in the subsequent password-change transaction.
                session.execute(text("BEGIN IMMEDIATE"))
                current_user = session.get(AdminUser, user_id)
                if (
                    current_user is None
                    or not current_user.is_active
                    or not hmac.compare_digest(current_user.password_hash, encoded_hash)
                ):
                    raise InvalidCredentials()
                current_user.last_login_at = now
                current_user.updated_at = now
                if replacement_hash is not None:
                    current_user.password_hash = replacement_hash
                issued = self._sessions.issue(session, current_user, client_label)
                self._audit.record(
                    session,
                    actor_type="admin",
                    actor_id=current_user.id,
                    action="login_succeeded",
                    result="succeeded",
                    request_id=request_id,
                    target_type="session",
                    target_id=issued.session_id,
                    metadata={
                        "source_fingerprint": source_fingerprint(
                            self._secret, source_identifier
                        )
                    },
                )
        except InvalidCredentials:
            self._rate_limiter.register_failure(normalized, source_identifier)
            self._record_failed_login(
                normalized,
                source_identifier,
                request_id,
                reason="invalid_credentials",
            )
            raise

        # Clear only the account-specific failure buckets after the complete
        # authorization, Session, and success-audit transaction has committed.
        self._rate_limiter.register_success(normalized, source_identifier)
        return issued

    def _record_failed_login(
        self,
        normalized_username: str,
        source_identifier: str,
        request_id: str | None,
        *,
        reason: str,
    ) -> None:
        with self._database.transaction() as session:
            self._audit.record(
                session,
                actor_type="anonymous",
                actor_id=None,
                action="login_failed",
                result="failed",
                request_id=request_id,
                target_type="admin_user",
                target_id=None,
                metadata={
                    "reason": reason,
                    "source_fingerprint": source_fingerprint(self._secret, source_identifier),
                    "username_fingerprint": keyed_digest(
                        self._secret, "audit-username", normalized_username
                    )[:24],
                },
            )


@dataclass(frozen=True)
class RetentionResult:
    jobs_deleted: int
    audit_events_deleted: int
    rate_limit_buckets_deleted: int


class RetentionService:
    """Bound durable control-plane metadata without touching active work."""

    def __init__(
        self,
        database: Database,
        settings: Settings,
        clock: Clock,
        rate_limits: LoginRateLimiter,
    ) -> None:
        self._database = database
        self._clock = clock
        self._job_retention = timedelta(seconds=settings.job_retention)
        self._audit_retention = timedelta(seconds=settings.audit_retention)
        self._rate_limits = rate_limits

    def cleanup(self) -> RetentionResult:
        now = self._clock.now()
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            job_result = cast(
                CursorResult[object],
                session.execute(
                    delete(Job).where(
                        Job.status.in_(("succeeded", "failed", "cancelled")),
                        Job.finished_at.is_not(None),
                        Job.finished_at <= now - self._job_retention,
                    )
                ),
            )
            audit_result = cast(
                CursorResult[object],
                session.execute(
                    delete(AuditEvent).where(AuditEvent.created_at <= now - self._audit_retention)
                ),
            )
        return RetentionResult(
            jobs_deleted=int(job_result.rowcount or 0),
            audit_events_deleted=int(audit_result.rowcount or 0),
            rate_limit_buckets_deleted=self._rate_limits.cleanup(),
        )


@dataclass(frozen=True)
class ControlPlaneServices:
    database: Database
    admin: AdminService
    auth: AuthService
    sessions: SessionService
    rate_limits: LoginRateLimiter
    audit: AuditService
    projects: ProjectService
    jobs: JobService
    retention: RetentionService


def build_services(
    settings: Settings,
    *,
    clock: Clock | None = None,
    password_manager: PasswordManager | None = None,
) -> ControlPlaneServices:
    actual_clock = clock or SystemClock()
    actual_password_manager = password_manager or PasswordManager()
    database = Database(settings)
    audit = AuditService(actual_clock)
    sessions = SessionService(database, settings, audit, actual_clock)
    rate_limiter = LoginRateLimiter(
        database=database,
        secret=settings.secret_key.get_secret_value(),
        clock=actual_clock,
        limit=settings.login_rate_limit,
        window_seconds=settings.login_rate_window,
        lock_seconds=settings.login_lock_duration,
        max_rows=settings.login_rate_max_buckets,
    )
    auth = AuthService(
        database,
        settings,
        actual_password_manager,
        sessions,
        audit,
        rate_limiter,
        actual_clock,
    )
    admin = AdminService(database, actual_password_manager, audit, actual_clock)
    projects = ProjectService(database, actual_clock)
    jobs = JobService(database, settings, actual_clock)
    retention = RetentionService(database, settings, actual_clock, rate_limiter)
    return ControlPlaneServices(
        database=database,
        admin=admin,
        auth=auth,
        sessions=sessions,
        rate_limits=rate_limiter,
        audit=audit,
        projects=projects,
        jobs=jobs,
        retention=retention,
    )


def require_admin_initialized(services: ControlPlaneServices) -> None:
    initialized, _username = services.admin.status()
    if not initialized:
        raise AdminNotInitialized()
