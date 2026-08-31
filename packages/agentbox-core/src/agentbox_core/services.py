"""Minimal Phase 3 application services for admin, auth, sessions, and audit."""

from __future__ import annotations

import hmac
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from agentbox_core.approval_models import (
    AttemptTerminalResultCode,
    AuthorizeResultCode,
    CancellationResultCode,
    ChallengeTerminalResultCode,
    ConfirmationChallenge,
    ConfirmationChallengeState,
    ProviderSecretProvisioningAttempt,
    ProviderSecretProvisioningAttemptState,
    RuntimeAttestationResultCode,
    RuntimeProviderSecretProvisionStatus,
)
from agentbox_core.approvals import ApprovalService
from agentbox_core.clock import Clock, SystemClock
from agentbox_core.configuration import Settings
from agentbox_core.database import Database
from agentbox_core.errors import (
    AdminAlreadyInitialized,
    AdminNotInitialized,
    DatabaseNotReady,
    InvalidCredentials,
    InvalidCsrfToken,
    InvalidSession,
    LoginRateLimited,
    ReauthenticationInvalidCredentials,
    ReauthenticationInvalidSession,
    ReauthenticationRateLimited,
    ReauthenticationUnavailable,
)
from agentbox_core.jobs import JobService
from agentbox_core.models import AdminUser, AuditEvent, ControlPlaneSession, Job
from agentbox_core.projects import ProjectService
from agentbox_core.providers import ProviderRepository
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
from agentbox_core.utc import aware_utc
from agentbox_core.waw_sessions import WorkspaceSessionService


@dataclass(frozen=True)
class IssuedSession:
    token: str
    csrf_token: str
    session_id: str
    user_id: str
    username: str
    expires_at: datetime
    authenticated_at: datetime
    auth_epoch: int


@dataclass(frozen=True)
class AuthenticatedSession:
    session_id: str
    user_id: str
    username: str
    expires_at: datetime
    authenticated_at: datetime
    auth_epoch: int
    csrf_token: str


@dataclass(frozen=True)
class SessionMetadata:
    session_id: str
    created_at: datetime
    last_seen_at: datetime
    idle_expires_at: datetime
    expires_at: datetime
    client_label: str | None
    recent_authenticated_at: datetime
    auth_epoch: int


class AuditService:
    _SLICE_32A_KEYS: dict[str, frozenset[str]] = {
        "provider_credential.created": frozenset(
            {
                "runtime_installation_id",
                "runtime_revision",
                "provider_id",
                "provider_revision",
                "kind",
                "state",
                "revision",
            }
        ),
        "reauth_succeeded": frozenset({"auth_context_fingerprint", "source_fingerprint", "reason"}),
        "reauth_failed": frozenset({"auth_context_fingerprint", "source_fingerprint", "reason"}),
        "provider_secret.challenge_issued": frozenset(
            {
                "runtime_installation_id",
                "runtime_revision",
                "provider_id",
                "provider_revision",
                "credential_id",
                "credential_revision",
                "auth_context_fingerprint",
                "auth_epoch",
                "purpose",
                "expires_at",
                "approval_digest",
                "provisioning_intent_id",
            }
        ),
        "provider_secret.challenge_cancelled": frozenset(
            {
                "purpose",
                "terminal_result_code",
                "runtime_installation_id",
                "provider_id",
                "credential_id",
                "provisioning_intent_id",
                "auth_context_fingerprint",
            }
        ),
        "provider_secret.challenge_consumed": frozenset(
            {
                "provisioning_attempt_id",
                "provisioning_intent_id",
                "runtime_installation_id",
                "runtime_revision",
                "provider_id",
                "provider_revision",
                "credential_id",
                "credential_revision",
                "approval_digest",
                "auth_context_fingerprint",
            }
        ),
        "provider_secret.challenge_rejected": frozenset({"reason_code", "id_well_formed"}),
        "provider_secret.attempt_created": frozenset(
            {
                "challenge_id",
                "provisioning_intent_id",
                "runtime_installation_id",
                "runtime_revision",
                "provider_id",
                "provider_revision",
                "credential_id",
                "credential_revision",
                "state",
                "approval_digest",
                "auth_context_fingerprint",
            }
        ),
        "provider_secret.authorize_pending": frozenset(
            {
                "from_state",
                "to_state",
                "attempt_count",
                "authorize_result_code",
                "runtime_installation_id",
                "provider_id",
                "credential_id",
                "provisioning_intent_id",
            }
        ),
        "provider_secret.authorize_status_checked": frozenset(
            {
                "from_state",
                "to_state",
                "attempt_count",
                "authorize_result_code",
                "runtime_status",
                "runtime_installation_id",
                "provider_id",
                "credential_id",
                "provisioning_intent_id",
            }
        ),
        "provider_secret.authorize_retry_admitted": frozenset(
            {
                "state",
                "attempt_count",
                "authorize_result_code",
                "runtime_installation_id",
                "provider_id",
                "credential_id",
                "provisioning_intent_id",
            }
        ),
        "provider_secret.cancel_pending": frozenset(
            {
                "from_state",
                "to_state",
                "cancellation_result_code",
                "runtime_installation_id",
                "provider_id",
                "credential_id",
                "provisioning_intent_id",
            }
        ),
        "provider_secret.attempt_transitioned": frozenset(
            {
                "from_state",
                "to_state",
                "authorize_result_code",
                "terminal_result_code",
                "cancellation_result_code",
                "runtime_attestation_code",
                "runtime_installation_id",
                "provider_id",
                "credential_id",
                "provisioning_intent_id",
            }
        ),
        "provider_secret.maintenance_completed": frozenset(
            {
                "approval_expired_count",
                "attempt_pruned_count",
                "challenge_pruned_count",
                "auth_context_pruned_count",
            }
        ),
    }
    _SLICE_32A_RESULTS: dict[str, frozenset[str]] = {
        "provider_credential.created": frozenset({"succeeded"}),
        "reauth_succeeded": frozenset({"succeeded"}),
        "reauth_failed": frozenset({"failed"}),
        "provider_secret.challenge_issued": frozenset({"succeeded"}),
        "provider_secret.challenge_cancelled": frozenset({"succeeded"}),
        "provider_secret.challenge_consumed": frozenset({"succeeded"}),
        "provider_secret.challenge_rejected": frozenset({"rejected"}),
        "provider_secret.attempt_created": frozenset({"succeeded"}),
        "provider_secret.authorize_pending": frozenset({"succeeded"}),
        "provider_secret.authorize_status_checked": frozenset(
            {"succeeded", "failed", "needs_attention"}
        ),
        "provider_secret.authorize_retry_admitted": frozenset({"succeeded"}),
        "provider_secret.cancel_pending": frozenset({"succeeded"}),
        "provider_secret.attempt_transitioned": frozenset(
            {"succeeded", "failed", "needs_attention"}
        ),
        "provider_secret.maintenance_completed": frozenset({"succeeded"}),
    }
    _SLICE_32A_OPTIONAL_KEYS: dict[str, frozenset[str]] = {
        "reauth_failed": frozenset({"auth_context_fingerprint"}),
        "provider_secret.attempt_transitioned": frozenset(
            {"authorize_result_code", "terminal_result_code", "runtime_attestation_code"}
        ),
        "provider_secret.authorize_status_checked": frozenset({"runtime_status"}),
    }

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
        allowed = self._SLICE_32A_KEYS.get(action)
        if allowed is not None:
            supplied = set(metadata or {})
            optional = self._SLICE_32A_OPTIONAL_KEYS.get(action, frozenset())
            required = allowed - optional
            if not required.issubset(supplied) or not supplied.issubset(allowed):
                raise ValueError("audit metadata is outside the Slice 3.2a action allowlist")
            if result not in self._SLICE_32A_RESULTS[action]:
                raise ValueError("audit result is outside the Slice 3.2a action allowlist")
            self._validate_slice32a_envelope(
                action,
                actor_type=actor_type,
                actor_id=actor_id,
                target_type=target_type,
                target_id=target_id,
            )
            self._validate_slice32a_values(action, metadata or {})
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

    @staticmethod
    def _validate_slice32a_envelope(
        action: str,
        *,
        actor_type: str,
        actor_id: str | None,
        target_type: str | None,
        target_id: str | None,
    ) -> None:
        admin_actions = {
            "provider_credential.created",
            "reauth_succeeded",
            "reauth_failed",
            "provider_secret.challenge_issued",
            "provider_secret.challenge_cancelled",
            "provider_secret.challenge_consumed",
            "provider_secret.challenge_rejected",
            "provider_secret.attempt_created",
        }
        if action in admin_actions and (
            actor_type != "admin_user"
            or actor_id is None
            or len(actor_id) != 36
            or not actor_id.startswith("adm_")
            or any(character not in "0123456789abcdef" for character in actor_id[4:])
        ):
            raise ValueError("Slice 3.2a audit actor is invalid")
        if action == "provider_secret.maintenance_completed" and (
            actor_type != "system" or actor_id is not None
        ):
            raise ValueError("Slice 3.2a maintenance actor is invalid")
        target_contract = {
            "provider_credential.created": ("provider_credential", "crd_"),
            "provider_secret.challenge_issued": ("confirmation_challenge", "cch_"),
            "provider_secret.challenge_cancelled": ("confirmation_challenge", "cch_"),
            "provider_secret.challenge_consumed": ("confirmation_challenge", "cch_"),
            "provider_secret.attempt_created": (
                "provider_secret_provisioning_attempt",
                "psa_",
            ),
            "provider_secret.authorize_pending": (
                "provider_secret_provisioning_attempt",
                "psa_",
            ),
            "provider_secret.authorize_status_checked": (
                "provider_secret_provisioning_attempt",
                "psa_",
            ),
            "provider_secret.authorize_retry_admitted": (
                "provider_secret_provisioning_attempt",
                "psa_",
            ),
            "provider_secret.cancel_pending": (
                "provider_secret_provisioning_attempt",
                "psa_",
            ),
            "provider_secret.attempt_transitioned": (
                "provider_secret_provisioning_attempt",
                "psa_",
            ),
        }
        expected_target = target_contract.get(action)
        if expected_target is not None:
            expected_type, prefix = expected_target
            if (
                target_type != expected_type
                or target_id is None
                or len(target_id) != 36
                or not target_id.startswith(prefix)
                or any(character not in "0123456789abcdef" for character in target_id[4:])
            ):
                raise ValueError("Slice 3.2a audit target is invalid")
        if action in {"reauth_succeeded", "reauth_failed"} and (
            target_type != "auth_context" or target_id is not None
        ):
            raise ValueError("reauth audit target is invalid")
        if action == "provider_secret.maintenance_completed" and (
            target_type != "provider_secret_maintenance" or target_id is not None
        ):
            raise ValueError("approval maintenance audit target is invalid")
        if action == "provider_secret.challenge_rejected":
            if target_id is None and target_type is not None:
                raise ValueError("approval rejection audit target is invalid")
            if target_id is not None and (
                target_type != "confirmation_challenge"
                or len(target_id) != 36
                or not target_id.startswith("cch_")
                or any(character not in "0123456789abcdef" for character in target_id[4:])
            ):
                raise ValueError("approval rejection audit target is invalid")

    @staticmethod
    def _validate_slice32a_values(action: str, metadata: dict[str, object]) -> None:
        fingerprint_keys = {"auth_context_fingerprint", "source_fingerprint"}
        for key in fingerprint_keys & metadata.keys():
            value = metadata[key]
            if (
                not isinstance(value, str)
                or len(value) != 24
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise ValueError("audit fingerprint is not 24 lowercase hexadecimal characters")
        id_prefixes = {
            "runtime_installation_id": "rti_",
            "provider_id": "prv_",
            "credential_id": "crd_",
            "provisioning_intent_id": "psi_",
            "challenge_id": "cch_",
            "provisioning_attempt_id": "psa_",
        }
        for key, prefix in id_prefixes.items():
            if key not in metadata:
                continue
            value = metadata[key]
            if (
                not isinstance(value, str)
                or len(value) != 36
                or not value.startswith(prefix)
                or any(character not in "0123456789abcdef" for character in value[4:])
            ):
                raise ValueError("audit authority identifier is invalid")
        for key in {"approval_digest"} & metadata.keys():
            value = metadata[key]
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise ValueError("audit approval digest is invalid")
        for key in {
            "runtime_revision",
            "provider_revision",
            "credential_revision",
            "revision",
            "auth_epoch",
            "attempt_count",
        } & metadata.keys():
            value = metadata[key]
            if type(value) is not int or value < 1:
                raise ValueError("audit authority revision/count is invalid")
        if action == "provider_credential.created" and (
            metadata.get("kind") != "api_key"
            or metadata.get("state") != "missing"
            or metadata.get("revision") != 1
        ):
            raise ValueError("provider credential creation metadata is invalid")
        if action == "provider_secret.challenge_issued" and metadata.get("purpose") != (
            "provider_secret_provision"
        ):
            raise ValueError("approval purpose is invalid")
        if "expires_at" in metadata:
            expires_at = metadata["expires_at"]
            try:
                parsed_expiry = datetime.strptime(cast(str, expires_at), "%Y-%m-%dT%H:%M:%S.%fZ")
            except (TypeError, ValueError) as exc:
                raise ValueError("approval expiry audit timestamp is invalid") from exc
            if not isinstance(expires_at, str) or (
                parsed_expiry.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != expires_at
            ):
                raise ValueError("approval expiry audit timestamp is invalid")
        if action == "provider_secret.attempt_created" and metadata.get("state") != "authorized":
            raise ValueError("initial provisioning attempt state is invalid")
        if action == "reauth_succeeded" and metadata.get("reason") != "credentials_rotated":
            raise ValueError("reauth success reason is invalid")
        if action == "reauth_failed" and metadata.get("reason") not in {
            "invalid_credentials",
            "rate_limited",
            "session_invalid",
            "password_changed",
        }:
            raise ValueError("reauth failure reason is invalid")
        if action == "provider_secret.challenge_rejected" and (
            metadata.get("reason_code")
            not in {
                "APPROVAL_INVALID",
                "APPROVAL_EXPIRED",
                "APPROVAL_STALE",
                "APPROVAL_ALREADY_FINAL",
                "APPROVAL_CONFLICT",
                "APPROVAL_UNAVAILABLE",
            }
            or type(metadata.get("id_well_formed")) is not bool
        ):
            raise ValueError("approval rejection metadata is invalid")
        if action == "provider_secret.maintenance_completed":
            counts = tuple(metadata.values())
            if any(type(value) is not int or not 0 <= value <= 100 for value in counts):
                raise ValueError("approval maintenance counts are invalid")
            if sum(cast(int, value) for value in counts) > 100:
                raise ValueError("approval maintenance counts are invalid")
        closed_values: dict[str, frozenset[str]] = {
            "from_state": frozenset(
                state.value for state in ProviderSecretProvisioningAttemptState
            ),
            "to_state": frozenset(state.value for state in ProviderSecretProvisioningAttemptState),
            "authorize_result_code": frozenset(code.value for code in AuthorizeResultCode),
            "cancellation_result_code": frozenset(code.value for code in CancellationResultCode),
            "runtime_attestation_code": frozenset(
                code.value for code in RuntimeAttestationResultCode
            ),
            "runtime_status": frozenset(
                status.value for status in RuntimeProviderSecretProvisionStatus
            ),
        }
        for key, allowed in closed_values.items():
            if key in metadata and metadata[key] not in allowed:
                raise ValueError("approval audit state/result value is invalid")
        if (
            action != "provider_credential.created"
            and "state" in metadata
            and metadata["state"]
            not in frozenset(state.value for state in ProviderSecretProvisioningAttemptState)
        ):
            raise ValueError("approval audit attempt state is invalid")
        if "terminal_result_code" in metadata:
            allowed_terminal = (
                frozenset(code.value for code in ChallengeTerminalResultCode)
                if action == "provider_secret.challenge_cancelled"
                else frozenset(code.value for code in AttemptTerminalResultCode)
            )
            if metadata["terminal_result_code"] not in allowed_terminal:
                raise ValueError("approval audit terminal result is invalid")
        if action == "provider_secret.authorize_pending" and (
            metadata.get("from_state") != "authorized"
            or metadata.get("to_state") != "authorize_pending"
            or metadata.get("attempt_count") != 1
            or metadata.get("authorize_result_code") != "REQUEST_PERSISTED"
        ):
            raise ValueError("authorize-pending audit transition is invalid")
        if action == "provider_secret.authorize_retry_admitted" and (
            metadata.get("state") != "authorize_pending"
            or metadata.get("attempt_count") not in {2, 3}
            or metadata.get("authorize_result_code") != "RESEND_PERSISTED"
        ):
            raise ValueError("authorize retry audit transition is invalid")
        if action == "provider_secret.cancel_pending" and (
            metadata.get("to_state") != "cancel_pending"
            or metadata.get("cancellation_result_code") != "RUNTIME_CANCEL_REQUESTED"
        ):
            raise ValueError("cancel-pending audit transition is invalid")


def _cancel_session_challenges(
    session: Session,
    *,
    session_ids: tuple[str, ...],
    now: datetime,
    result_code: ChallengeTerminalResultCode,
    auth_epoch: int | None = None,
) -> None:
    """Cancel approval authority before invalidating its exact Session."""
    if not session_ids:
        return
    statement = select(ConfirmationChallenge).where(
        ConfirmationChallenge.control_plane_session_id.in_(session_ids),
        ConfirmationChallenge.state == ConfirmationChallengeState.ISSUED,
    )
    if auth_epoch is not None:
        statement = statement.where(ConfirmationChallenge.auth_epoch == auth_epoch)
    challenges = tuple(session.scalars(statement))
    for challenge in challenges:
        clock_rollback = now < challenge.issued_at or now < challenge.last_observed_at
        terminal_time = max(now, challenge.issued_at, challenge.last_observed_at)
        challenge.state = ConfirmationChallengeState.CANCELLED
        challenge.cancellation_epoch = 1
        challenge.last_observed_at = terminal_time
        challenge.terminal_at = terminal_time
        challenge.terminal_result_code = (
            ChallengeTerminalResultCode.CLOCK_ROLLBACK_DETECTED if clock_rollback else result_code
        )
        challenge.retention_eligible_at = terminal_time + timedelta(days=30)


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
        now = aware_utc(self._clock.now())
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
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            now = self._database.transaction_now(session)
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
            _cancel_session_challenges(
                session,
                session_ids=tuple(stored.id for stored in active_sessions),
                now=now,
                result_code=ChallengeTerminalResultCode.SESSION_REVOKED,
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
        now = aware_utc(self._clock.now())
        with self._database.transaction() as session:
            return tuple(
                SessionMetadata(
                    session_id=stored.id,
                    created_at=stored.created_at,
                    last_seen_at=stored.last_seen_at,
                    idle_expires_at=stored.idle_expires_at,
                    expires_at=stored.expires_at,
                    client_label=stored.client_label,
                    recent_authenticated_at=stored.recent_authenticated_at,
                    auth_epoch=stored.auth_epoch,
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
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            now = self._database.transaction_now(session)
            active_sessions = tuple(
                session.scalars(
                    select(ControlPlaneSession).where(
                        ControlPlaneSession.user_id == admin_id,
                        ControlPlaneSession.revoked_at.is_(None),
                    )
                )
            )
            _cancel_session_challenges(
                session,
                session_ids=tuple(stored.id for stored in active_sessions),
                now=now,
                result_code=ChallengeTerminalResultCode.SESSION_REVOKED,
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
        self._session_idle_ttl = settings.session_idle_ttl

    def issue(self, session: Session, user: AdminUser, client_label: str | None) -> IssuedSession:
        now = self._database.transaction_now(session)
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
        evicted = tuple(stale.id for stale in active_sessions[: max(0, excess)])
        _cancel_session_challenges(
            session,
            session_ids=evicted,
            now=now,
            result_code=ChallengeTerminalResultCode.SESSION_REVOKED,
        )
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
                recent_authenticated_at=now,
                auth_epoch=1,
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
            auth_epoch=1,
        )

    def authenticate(self, raw_token: str | None) -> AuthenticatedSession:
        if not raw_token or len(raw_token) > 128:
            raise InvalidSession()
        token_hash = keyed_digest(self._secret, "session-token", raw_token)
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            now = self._database.transaction_now(session)
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
                or now < stored.recent_authenticated_at
                or now < stored.last_seen_at
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
                authenticated_at=stored.recent_authenticated_at,
                auth_epoch=stored.auth_epoch,
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
        age = aware_utc(self._clock.now()) - authenticated.authenticated_at
        return timedelta(0) <= age <= timedelta(seconds=max_age_seconds)

    def revoke(
        self,
        authenticated: AuthenticatedSession,
        *,
        request_id: str | None,
        reason: str = "logout",
    ) -> None:
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            now = self._database.transaction_now(session)
            stored = session.get(ControlPlaneSession, authenticated.session_id)
            if stored is None or stored.revoked_at is not None:
                raise InvalidSession()
            _cancel_session_challenges(
                session,
                session_ids=(stored.id,),
                now=now,
                result_code=ChallengeTerminalResultCode.SESSION_REVOKED,
            )
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
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            now = self._database.transaction_now(session)
            cutoff = now - timedelta(seconds=self._settings.session_retention)
            result = cast(
                CursorResult[object],
                session.connection().execute(
                    delete(ControlPlaneSession).where(
                        or_(
                            ControlPlaneSession.expires_at <= cutoff,
                            ControlPlaneSession.idle_expires_at <= cutoff,
                            ControlPlaneSession.revoked_at <= cutoff,
                        ),
                        ~select(ConfirmationChallenge.id)
                        .where(
                            ConfirmationChallenge.control_plane_session_id == ControlPlaneSession.id
                        )
                        .exists(),
                        ~select(ProviderSecretProvisioningAttempt.id)
                        .where(
                            ProviderSecretProvisioningAttempt.control_plane_session_id
                            == ControlPlaneSession.id
                        )
                        .exists(),
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
        reauth_rate_limiter: LoginRateLimiter,
        clock: Clock,
    ) -> None:
        self._database = database
        self._password_manager = password_manager
        self._sessions = session_service
        self._audit = audit
        self._rate_limiter = rate_limiter
        self._reauth_rate_limiter = reauth_rate_limiter
        self._clock = clock
        self._secret = settings.secret_key.get_secret_value()
        self._session_idle_ttl = settings.session_idle_ttl

    def reauthenticate(
        self,
        authenticated: AuthenticatedSession,
        *,
        password: str,
        source_identifier: str,
        request_id: str | None,
    ) -> IssuedSession:
        """Rotate one exact Session's bearer and CSRF credentials after password proof."""
        try:
            decision = self._reauth_rate_limiter.check(authenticated.user_id, source_identifier)
        except DatabaseNotReady as exc:
            raise ReauthenticationUnavailable() from exc
        if not decision.allowed:
            self._record_reauth_failure(
                authenticated, source_identifier, request_id, reason="rate_limited"
            )
            raise ReauthenticationRateLimited(retry_after=decision.retry_after)

        try:
            with self._database.transaction() as session:
                now = self._database.transaction_now(session)
                stored = session.get(ControlPlaneSession, authenticated.session_id)
                user = session.get(AdminUser, authenticated.user_id)
                if stored is not None and (
                    now < stored.recent_authenticated_at or now < stored.last_seen_at
                ):
                    raise ReauthenticationUnavailable()
                invalid_context = (
                    stored is None
                    or user is None
                    or stored.user_id != user.id
                    or stored.revoked_at is not None
                    or stored.expires_at <= now
                    or stored.idle_expires_at <= now
                    or stored.auth_epoch != authenticated.auth_epoch
                )
                observed_hash = user.password_hash if user is not None else ""
                active = bool(user is not None and user.is_active)
        except (IntegrityError, OperationalError, ValueError) as exc:
            raise ReauthenticationUnavailable() from exc
        if invalid_context:
            self._record_reauth_failure(
                authenticated,
                source_identifier,
                request_id,
                reason="session_invalid",
            )
            raise ReauthenticationInvalidSession()

        if not active:
            self._record_reauth_failure(
                authenticated,
                source_identifier,
                request_id,
                reason="invalid_credentials",
            )
            raise ReauthenticationInvalidCredentials()

        if not self._password_manager.verify(observed_hash, password):
            try:
                self._reauth_rate_limiter.register_failure(authenticated.user_id, source_identifier)
            except DatabaseNotReady as exc:
                raise ReauthenticationUnavailable() from exc
            self._record_reauth_failure(
                authenticated,
                source_identifier,
                request_id,
                reason="invalid_credentials",
            )
            raise ReauthenticationInvalidCredentials()

        try:
            with self._database.transaction() as session:
                session.execute(text("BEGIN IMMEDIATE"))
                now = self._database.transaction_now(session)
                stored = session.get(ControlPlaneSession, authenticated.session_id)
                user = session.get(AdminUser, authenticated.user_id)
                if stored is not None and (
                    now < stored.recent_authenticated_at or now < stored.last_seen_at
                ):
                    raise ReauthenticationUnavailable()
                if (
                    stored is None
                    or user is None
                    or stored.user_id != user.id
                    or not user.is_active
                    or stored.revoked_at is not None
                    or stored.expires_at <= now
                    or stored.idle_expires_at <= now
                    or stored.auth_epoch != authenticated.auth_epoch
                    or not hmac.compare_digest(user.password_hash, observed_hash)
                ):
                    raise ReauthenticationInvalidCredentials()

                raw_token = ""
                token_hash = ""
                for _attempt in range(4):
                    candidate = generate_session_token()
                    candidate_hash = keyed_digest(self._secret, "session-token", candidate)
                    if hmac.compare_digest(candidate_hash, stored.token_hash):
                        continue
                    collision = session.scalar(
                        select(ControlPlaneSession.id).where(
                            ControlPlaneSession.token_hash == candidate_hash,
                            ControlPlaneSession.id != stored.id,
                        )
                    )
                    if collision is None:
                        raw_token = candidate
                        token_hash = candidate_hash
                        break
                if not raw_token:
                    raise ReauthenticationUnavailable()

                csrf_token = derive_csrf_token(self._secret, stored.id, token_hash)
                stored.token_hash = token_hash
                stored.csrf_hash = keyed_digest(self._secret, "csrf-verifier", csrf_token)
                prior_epoch = stored.auth_epoch
                stored.auth_epoch += 1
                stored.recent_authenticated_at = now
                stored.last_seen_at = now
                stored.idle_expires_at = min(
                    stored.expires_at,
                    now + timedelta(seconds=self._session_idle_ttl),
                )
                _cancel_session_challenges(
                    session,
                    session_ids=(stored.id,),
                    now=now,
                    result_code=ChallengeTerminalResultCode.AUTH_EPOCH_ROTATED,
                    auth_epoch=prior_epoch,
                )
                self._audit.record(
                    session,
                    actor_type="admin_user",
                    actor_id=user.id,
                    action="reauth_succeeded",
                    result="succeeded",
                    request_id=request_id,
                    target_type="auth_context",
                    target_id=None,
                    metadata={
                        "auth_context_fingerprint": keyed_digest(
                            self._secret, "audit-auth-context", stored.id
                        )[:24],
                        "source_fingerprint": source_fingerprint(self._secret, source_identifier),
                        "reason": "credentials_rotated",
                    },
                )
                issued = IssuedSession(
                    token=raw_token,
                    csrf_token=csrf_token,
                    session_id=stored.id,
                    user_id=user.id,
                    username=user.username,
                    expires_at=stored.expires_at,
                    authenticated_at=now,
                    auth_epoch=stored.auth_epoch,
                )
        except ReauthenticationInvalidCredentials:
            try:
                self._reauth_rate_limiter.register_failure(authenticated.user_id, source_identifier)
            except DatabaseNotReady as exc:
                raise ReauthenticationUnavailable() from exc
            self._record_reauth_failure(
                authenticated,
                source_identifier,
                request_id,
                reason="password_changed",
            )
            raise
        except (DatabaseNotReady, IntegrityError, OperationalError, ValueError) as exc:
            raise ReauthenticationUnavailable() from exc

        with suppress(DatabaseNotReady):
            self._reauth_rate_limiter.register_success(authenticated.user_id, source_identifier)
            # The credential rotation and its success Audit are already committed.
            # A best-effort throttle cleanup failure must not strand the new token.
        return issued

    def _record_reauth_failure(
        self,
        authenticated: AuthenticatedSession,
        source_identifier: str,
        request_id: str | None,
        *,
        reason: str,
    ) -> None:
        metadata: dict[str, object] = {
            "source_fingerprint": source_fingerprint(self._secret, source_identifier),
            "reason": reason,
        }
        metadata["auth_context_fingerprint"] = keyed_digest(
            self._secret, "audit-auth-context", authenticated.session_id
        )[:24]
        try:
            with self._database.transaction() as session:
                self._audit.record(
                    session,
                    actor_type="admin_user",
                    actor_id=authenticated.user_id,
                    action="reauth_failed",
                    result="failed",
                    request_id=request_id,
                    target_type="auth_context",
                    target_id=None,
                    metadata=metadata,
                )
        except (IntegrityError, OperationalError, ValueError) as exc:
            raise ReauthenticationUnavailable() from exc

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

        try:
            with self._database.transaction() as session:
                # Reserve SQLite's single writer before revalidating the hash.
                # Password rotation then either commits first and invalidates
                # this Login, or waits until this Session is committed and
                # revokes it in the subsequent password-change transaction.
                session.execute(text("BEGIN IMMEDIATE"))
                now = self._database.transaction_now(session)
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
                        "source_fingerprint": source_fingerprint(self._secret, source_identifier)
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
    reauth_rate_limits: LoginRateLimiter
    audit: AuditService
    projects: ProjectService
    providers: ProviderRepository
    approvals: ApprovalService
    jobs: JobService
    retention: RetentionService
    workspaces: WorkspaceSessionService


def build_services(
    settings: Settings,
    *,
    clock: Clock | None = None,
    password_manager: PasswordManager | None = None,
) -> ControlPlaneServices:
    actual_clock = clock or SystemClock()
    actual_password_manager = password_manager or PasswordManager()
    database = Database(settings, actual_clock)
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
    reauth_rate_limiter = LoginRateLimiter(
        database=database,
        secret=settings.secret_key.get_secret_value(),
        clock=actual_clock,
        limit=settings.login_rate_limit,
        window_seconds=settings.login_rate_window,
        lock_seconds=settings.login_lock_duration,
        max_rows=settings.login_rate_max_buckets,
        purpose="reauth",
    )
    auth = AuthService(
        database,
        settings,
        actual_password_manager,
        sessions,
        audit,
        rate_limiter,
        reauth_rate_limiter,
        actual_clock,
    )
    admin = AdminService(database, actual_password_manager, audit, actual_clock)
    projects = ProjectService(database, actual_clock)
    providers = ProviderRepository(database, actual_clock, audit)
    approvals = ApprovalService(
        database,
        actual_clock,
        audit,
        settings.secret_key.get_secret_value(),
        settings.session_retention,
    )
    jobs = JobService(database, settings, actual_clock)
    retention = RetentionService(database, settings, actual_clock, rate_limiter)
    workspaces = WorkspaceSessionService(database, actual_clock)
    return ControlPlaneServices(
        database=database,
        admin=admin,
        auth=auth,
        sessions=sessions,
        rate_limits=rate_limiter,
        reauth_rate_limits=reauth_rate_limiter,
        audit=audit,
        projects=projects,
        providers=providers,
        approvals=approvals,
        jobs=jobs,
        retention=retention,
        workspaces=workspaces,
    )


def require_admin_initialized(services: ControlPlaneServices) -> None:
    initialized, _username = services.admin.status()
    if not initialized:
        raise AdminNotInitialized()
