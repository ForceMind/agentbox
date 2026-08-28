"""Slice 3.2a approval authority; no Runtime or Secret operation is representable."""

# ruff: noqa: E501 -- exact deterministic maintenance SQL remains a single contract.

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast

import rfc8785
from sqlalchemy import delete, func, select, text
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
    ConfirmationPurpose,
    ProviderSecretProvisioningAttempt,
    ProviderSecretProvisioningAttemptState,
)
from agentbox_core.clock import Clock
from agentbox_core.database import Database
from agentbox_core.errors import (
    ApprovalAlreadyFinal,
    ApprovalConflict,
    ApprovalExpired,
    ApprovalInvalid,
    ApprovalStale,
    ApprovalUnavailable,
    DatabaseNotReady,
)
from agentbox_core.models import AdminUser, ControlPlaneSession
from agentbox_core.provider_models import (
    CredentialKind,
    CredentialLifecycleState,
    Provider,
    ProviderCredential,
    ProviderLifecycleState,
    RuntimeInstallation,
    RuntimeType,
)
from agentbox_core.security import keyed_digest, new_identifier
from agentbox_core.utc import raw_utc6

APPROVAL_TTL = timedelta(seconds=300)
RETENTION = timedelta(days=30)
_OPAQUE = re.compile(r"[0-9a-f]{32}")
_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")
_APPROVAL_DOMAIN = b"AgentBox\0provider-secret-provision-approval\0v1\0"
_CONFIRMATION_DOMAIN = "AgentBox\0provider-secret-confirmation\0v1\0"


class AuditRecorder(Protocol):
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
    ) -> object: ...


class AuthenticatedSession(Protocol):
    @property
    def session_id(self) -> str: ...

    @property
    def user_id(self) -> str: ...

    @property
    def username(self) -> str: ...

    @property
    def expires_at(self) -> datetime: ...

    @property
    def authenticated_at(self) -> datetime: ...

    @property
    def auth_epoch(self) -> int: ...

    @property
    def csrf_token(self) -> str: ...


@dataclass(frozen=True)
class ChallengeIssue:
    runtime_installation_id: str
    runtime_installation_revision: int
    runtime_type: RuntimeType
    provider_id: str
    provider_revision: int
    provider_state: ProviderLifecycleState
    credential_id: str
    credential_revision: int
    credential_kind: CredentialKind
    credential_state: CredentialLifecycleState


@dataclass(frozen=True)
class ApprovalMaintenanceResult:
    approval_expired_count: int
    attempt_pruned_count: int
    challenge_pruned_count: int
    auth_context_pruned_count: int


def _id(value: str, prefix: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith(f"{prefix}_")
        or not _OPAQUE.fullmatch(value[4:])
    ):
        raise ApprovalInvalid()
    return value


def _request(value: str) -> str:
    if not isinstance(value, str) or not _REQUEST_ID.fullmatch(value):
        raise ApprovalInvalid()
    return value


def _utc6(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def approval_document(challenge: ConfirmationChallenge) -> dict[str, object]:
    """Return the exact typed canonical document; callers must never persist it."""
    return {
        "schema": "agentbox.provider-secret-provision-approval.v1",
        "challenge_id": challenge.id,
        "purpose": challenge.purpose.value,
        "admin_user_id": challenge.admin_user_id,
        "control_plane_session_id": challenge.control_plane_session_id,
        "auth_epoch": challenge.auth_epoch,
        "recent_authenticated_at": _utc6(challenge.recent_authenticated_at),
        "issue_request_id": challenge.issue_request_id,
        "provisioning_intent_id": challenge.provisioning_intent_id,
        "intent_contract_version": challenge.intent_contract_version,
        "intent_issued_at": _utc6(challenge.intent_issued_at),
        "intent_expires_at": _utc6(challenge.intent_expires_at),
        "initial_cancellation_epoch": challenge.initial_cancellation_epoch,
        "runtime_installation_id": challenge.runtime_installation_id,
        "runtime_installation_revision": challenge.runtime_installation_revision,
        "runtime_type": challenge.runtime_type.value,
        "provider_id": challenge.provider_id,
        "provider_revision": challenge.provider_revision,
        "provider_state": challenge.provider_state.value,
        "credential_id": challenge.credential_id,
        "credential_revision": challenge.credential_revision,
        "credential_kind": challenge.credential_kind.value,
        "credential_state": challenge.credential_state.value,
        "expected_runtime_secret_ref": challenge.expected_runtime_secret_ref,
        "expected_secret_version": challenge.expected_secret_version,
        "credential_runtime_installation_id": challenge.credential_runtime_installation_id,
        "intended_state": challenge.intended_state.value,
        "intended_secret_version": challenge.intended_secret_version,
        "issued_at": _utc6(challenge.issued_at),
        "expires_at": _utc6(challenge.expires_at),
        "cancellation_epoch": challenge.cancellation_epoch,
        "confirmation_verifier": challenge.confirmation_verifier,
    }


def approval_digest(challenge: ConfirmationChallenge) -> str:
    return hashlib.sha256(
        _APPROVAL_DOMAIN + rfc8785.dumps(cast(Any, approval_document(challenge)))
    ).hexdigest()


class ApprovalService:
    def __init__(
        self,
        database: Database,
        clock: Clock,
        audit: AuditRecorder,
        application_secret: str,
        session_retention_seconds: int,
    ) -> None:
        self._database = database
        self._clock = clock
        self._audit = audit
        self._secret = application_secret
        self._session_retention = timedelta(seconds=session_retention_seconds)

    def issue(
        self,
        authenticated: AuthenticatedSession,
        values: ChallengeIssue,
        *,
        request_id: str,
    ) -> ConfirmationChallenge:
        _request(request_id)
        try:
            with self._database.transaction() as session:
                session.execute(text("BEGIN IMMEDIATE"))
                now = self._database.transaction_now(session)
                if (
                    now < authenticated.authenticated_at
                    or now - authenticated.authenticated_at > APPROVAL_TTL
                ):
                    raise ApprovalStale()
                stored, runtime, provider, credential = self._bound_entities(
                    session, authenticated, values, now
                )
                conflict = session.scalar(
                    select(func.count())
                    .select_from(ConfirmationChallenge)
                    .where(
                        ConfirmationChallenge.credential_id == credential.id,
                        ConfirmationChallenge.state == ConfirmationChallengeState.ISSUED,
                    )
                ) or session.scalar(
                    select(func.count())
                    .select_from(ProviderSecretProvisioningAttempt)
                    .where(
                        ProviderSecretProvisioningAttempt.credential_id == credential.id,
                        ProviderSecretProvisioningAttempt.state.in_(
                            tuple(
                                state
                                for state in ProviderSecretProvisioningAttemptState
                                if state
                                not in {
                                    ProviderSecretProvisioningAttemptState.RECONCILED,
                                    ProviderSecretProvisioningAttemptState.CANCELLED,
                                    ProviderSecretProvisioningAttemptState.EXPIRED,
                                }
                            )
                        ),
                    )
                )
                if conflict:
                    raise ApprovalConflict()
                challenge_id = self._unique_id(session, ConfirmationChallenge, "cch")
                intent_id = self._unique_id(
                    session, ConfirmationChallenge, "psi", column="provisioning_intent_id"
                )
                expected_confirmation = f"PROVISION {credential.id}"
                verifier = hmac.new(
                    self._secret.encode(),
                    f"{_CONFIRMATION_DOMAIN}{challenge_id}\0{expected_confirmation}".encode(),
                    hashlib.sha256,
                ).hexdigest()
                challenge = ConfirmationChallenge(
                    id=challenge_id,
                    schema_version=1,
                    intent_contract_version=1,
                    purpose=ConfirmationPurpose.PROVIDER_SECRET_PROVISION,
                    state=ConfirmationChallengeState.ISSUED,
                    admin_user_id=authenticated.user_id,
                    control_plane_session_id=authenticated.session_id,
                    auth_epoch=stored.auth_epoch,
                    recent_authenticated_at=stored.recent_authenticated_at,
                    issue_request_id=request_id,
                    runtime_installation_id=runtime.id,
                    runtime_installation_revision=runtime.revision,
                    runtime_type=runtime.runtime_type,
                    provider_id=provider.id,
                    provider_revision=provider.revision,
                    provider_state=provider.state,
                    credential_id=credential.id,
                    credential_revision=credential.revision,
                    credential_kind=credential.kind,
                    credential_state=credential.state,
                    expected_runtime_secret_ref=None,
                    expected_secret_version=None,
                    credential_runtime_installation_id=credential.runtime_installation_id,
                    intended_state=CredentialLifecycleState.CONFIGURED,
                    intended_secret_version=1,
                    confirmation_verifier=verifier,
                    approval_digest="0" * 64,
                    provisioning_intent_id=intent_id,
                    issued_at=now,
                    created_at=now,
                    expires_at=now + APPROVAL_TTL,
                    intent_issued_at=now,
                    intent_expires_at=now + APPROVAL_TTL,
                    initial_cancellation_epoch=0,
                    last_observed_at=now,
                    cancellation_epoch=0,
                )
                challenge.approval_digest = approval_digest(challenge)
                session.add(challenge)
                self._audit.record(
                    session,
                    actor_type="admin_user",
                    actor_id=authenticated.user_id,
                    action="provider_secret.challenge_issued",
                    result="succeeded",
                    request_id=request_id,
                    target_type="confirmation_challenge",
                    target_id=challenge.id,
                    metadata=self._challenge_audit(challenge),
                )
                session.flush()
                return challenge
        except (DatabaseNotReady, IntegrityError, OperationalError, ValueError) as exc:
            raise ApprovalUnavailable() from exc

    def _consume_checkpoint(self, stage: str) -> None:
        """No-op failure seam; tests raise here without replacing DB triggers."""

    def consume(
        self,
        authenticated: AuthenticatedSession,
        challenge_id: str,
        *,
        confirmation: str,
        authorization_request_id: str,
    ) -> ProviderSecretProvisioningAttempt:
        try:
            _id(challenge_id, "cch")
        except ApprovalInvalid as exc:
            self._record_rejection(
                authenticated,
                challenge_id=None,
                request_id=None,
                error=exc,
                id_well_formed=False,
            )
            raise
        try:
            _request(authorization_request_id)
        except ApprovalInvalid as exc:
            self._record_rejection(
                authenticated,
                challenge_id=challenge_id,
                request_id=None,
                error=exc,
                id_well_formed=True,
            )
            raise
        deferred_error: Exception | None = None
        attempt: ProviderSecretProvisioningAttempt | None = None
        try:
            with self._database.transaction() as session:
                session.execute(text("BEGIN IMMEDIATE"))
                now = self._database.transaction_now(session)
                challenge = session.get(ConfirmationChallenge, challenge_id)
                if challenge is None or not self._same_actor(challenge, authenticated):
                    raise ApprovalInvalid()
                if (
                    challenge.schema_version != 1
                    or challenge.intent_contract_version != 1
                    or challenge.purpose is not ConfirmationPurpose.PROVIDER_SECRET_PROVISION
                ):
                    raise ApprovalInvalid()
                if challenge.state is not ConfirmationChallengeState.ISSUED:
                    raise ApprovalAlreadyFinal()
                if now < challenge.issued_at or now < challenge.last_observed_at:
                    self._terminalize_challenge(
                        challenge, now, ChallengeTerminalResultCode.CLOCK_ROLLBACK_DETECTED
                    )
                    deferred_error = ApprovalUnavailable()
                elif now >= challenge.expires_at:
                    self._expire_challenge(challenge, now)
                    deferred_error = ApprovalExpired()
                stored = (
                    session.get(ControlPlaneSession, authenticated.session_id)
                    if deferred_error is None
                    else None
                )
                admin = (
                    session.get(AdminUser, authenticated.user_id)
                    if deferred_error is None
                    else None
                )
                if deferred_error is None and (admin is None or not admin.is_active):
                    self._terminalize_challenge(
                        challenge, now, ChallengeTerminalResultCode.ADMIN_DEACTIVATED
                    )
                    deferred_error = ApprovalInvalid()
                if deferred_error is None and (
                    stored is None
                    or admin is None
                    or stored.user_id != admin.id
                    or stored.revoked_at is not None
                    or stored.expires_at <= now
                    or stored.idle_expires_at <= now
                ):
                    self._terminalize_challenge(
                        challenge, now, ChallengeTerminalResultCode.SESSION_REVOKED
                    )
                    deferred_error = ApprovalInvalid()
                if deferred_error is None:
                    assert stored is not None
                    if now < stored.recent_authenticated_at:
                        self._terminalize_challenge(
                            challenge, now, ChallengeTerminalResultCode.CLOCK_ROLLBACK_DETECTED
                        )
                        deferred_error = ApprovalUnavailable()
                    elif (
                        stored.auth_epoch != challenge.auth_epoch
                        or stored.auth_epoch != authenticated.auth_epoch
                        or stored.recent_authenticated_at != challenge.recent_authenticated_at
                        or stored.recent_authenticated_at != authenticated.authenticated_at
                        or now - stored.recent_authenticated_at > APPROVAL_TTL
                    ):
                        self._terminalize_challenge(
                            challenge, now, ChallengeTerminalResultCode.AUTH_EPOCH_ROTATED
                        )
                        deferred_error = ApprovalStale()
                if deferred_error is None and not self._challenge_entities_current(
                    session, challenge
                ):
                    self._terminalize_challenge(
                        challenge, now, ChallengeTerminalResultCode.BOUND_ENTITY_STALE
                    )
                    deferred_error = ApprovalStale()
                expected_digest = approval_digest(challenge)
                if deferred_error is None and not hmac.compare_digest(
                    expected_digest, challenge.approval_digest
                ):
                    raise ApprovalInvalid()
                supplied_verifier = hmac.new(
                    self._secret.encode(),
                    f"{_CONFIRMATION_DOMAIN}{challenge.id}\0{confirmation}".encode(),
                    hashlib.sha256,
                ).hexdigest()
                if deferred_error is None and not hmac.compare_digest(
                    supplied_verifier, challenge.confirmation_verifier
                ):
                    self._terminalize_challenge(
                        challenge, now, ChallengeTerminalResultCode.CONFIRMATION_MISMATCH
                    )
                    deferred_error = ApprovalInvalid()

                if deferred_error is None:
                    self._consume_checkpoint("after_validation")
                    challenge.last_observed_at = now
                    self._consume_checkpoint("before_attempt_construct")
                    attempt = self._attempt_from_challenge(
                        session, challenge, authorization_request_id, now
                    )
                    self._consume_checkpoint("before_attempt_insert")
                    session.add(attempt)
                    session.flush()
                    self._consume_checkpoint("after_attempt_insert")
                    self._consume_checkpoint("before_challenge_audit")
                    self._audit.record(
                        session,
                        actor_type="admin_user",
                        actor_id=authenticated.user_id,
                        action="provider_secret.challenge_consumed",
                        result="succeeded",
                        request_id=authorization_request_id,
                        target_type="confirmation_challenge",
                        target_id=challenge.id,
                        metadata={
                            "provisioning_attempt_id": attempt.id,
                            "provisioning_intent_id": attempt.provisioning_intent_id,
                            "runtime_installation_id": attempt.runtime_installation_id,
                            "runtime_revision": attempt.runtime_installation_revision,
                            "provider_id": attempt.provider_id,
                            "provider_revision": attempt.provider_revision,
                            "credential_id": attempt.credential_id,
                            "credential_revision": attempt.credential_revision,
                            "approval_digest": attempt.approval_digest,
                            "auth_context_fingerprint": self._auth_fingerprint(
                                authenticated.session_id
                            ),
                        },
                    )
                    session.flush()
                    self._consume_checkpoint("after_challenge_audit")
                    self._consume_checkpoint("before_attempt_audit")
                    self._audit.record(
                        session,
                        actor_type="admin_user",
                        actor_id=authenticated.user_id,
                        action="provider_secret.attempt_created",
                        result="succeeded",
                        request_id=authorization_request_id,
                        target_type="provider_secret_provisioning_attempt",
                        target_id=attempt.id,
                        metadata={
                            "challenge_id": attempt.challenge_id,
                            "provisioning_intent_id": attempt.provisioning_intent_id,
                            "runtime_installation_id": attempt.runtime_installation_id,
                            "runtime_revision": attempt.runtime_installation_revision,
                            "provider_id": attempt.provider_id,
                            "provider_revision": attempt.provider_revision,
                            "credential_id": attempt.credential_id,
                            "credential_revision": attempt.credential_revision,
                            "state": attempt.state.value,
                            "approval_digest": attempt.approval_digest,
                            "auth_context_fingerprint": self._auth_fingerprint(
                                authenticated.session_id
                            ),
                        },
                    )
                    session.flush()
                    self._consume_checkpoint("after_attempt_audit")
                    self._consume_checkpoint("before_final_flush")
                    session.flush()
                    self._consume_checkpoint("after_final_flush")
                    self._consume_checkpoint("before_commit")
            self._consume_checkpoint("after_commit")
        except (DatabaseNotReady, IntegrityError, OperationalError, ValueError) as exc:
            raise ApprovalUnavailable() from exc
        except (
            ApprovalAlreadyFinal,
            ApprovalConflict,
            ApprovalExpired,
            ApprovalInvalid,
            ApprovalStale,
            ApprovalUnavailable,
        ) as exc:
            self._record_rejection(
                authenticated,
                challenge_id=challenge_id,
                request_id=authorization_request_id,
                error=exc,
                id_well_formed=True,
            )
            raise
        if deferred_error is not None:
            self._record_rejection(
                authenticated,
                challenge_id=challenge_id,
                request_id=authorization_request_id,
                error=deferred_error,
                id_well_formed=True,
            )
            raise deferred_error
        assert attempt is not None
        return attempt

    def cancel_challenge(
        self,
        authenticated: AuthenticatedSession,
        challenge_id: str,
        *,
        request_id: str,
    ) -> ConfirmationChallenge:
        _id(challenge_id, "cch")
        _request(request_id)
        expired = False
        deferred_error: Exception | None = None
        try:
            with self._database.transaction() as session:
                session.execute(text("BEGIN IMMEDIATE"))
                now = self._database.transaction_now(session)
                challenge = session.get(ConfirmationChallenge, challenge_id)
                if challenge is None or not self._same_actor(challenge, authenticated):
                    raise ApprovalInvalid()
                if challenge.state is ConfirmationChallengeState.CANCELLED:
                    return challenge
                if challenge.state is not ConfirmationChallengeState.ISSUED:
                    raise ApprovalAlreadyFinal()
                stored = session.get(ControlPlaneSession, authenticated.session_id)
                admin = session.get(AdminUser, authenticated.user_id)
                if now < challenge.issued_at or now < challenge.last_observed_at:
                    self._terminalize_challenge(
                        challenge, now, ChallengeTerminalResultCode.CLOCK_ROLLBACK_DETECTED
                    )
                    deferred_error = ApprovalUnavailable()
                elif admin is None or not admin.is_active:
                    self._terminalize_challenge(
                        challenge, now, ChallengeTerminalResultCode.ADMIN_DEACTIVATED
                    )
                    deferred_error = ApprovalInvalid()
                elif (
                    stored is None
                    or stored.user_id != admin.id
                    or stored.revoked_at is not None
                    or stored.expires_at <= now
                    or stored.idle_expires_at <= now
                ):
                    self._terminalize_challenge(
                        challenge, now, ChallengeTerminalResultCode.SESSION_REVOKED
                    )
                    deferred_error = ApprovalInvalid()
                elif now >= challenge.expires_at:
                    self._expire_challenge(challenge, now)
                    expired = True
                elif deferred_error is None:
                    self._terminalize_challenge(
                        challenge, now, ChallengeTerminalResultCode.CANCELLED_BY_ISSUER
                    )
                    assert challenge.terminal_result_code is not None
                    self._audit.record(
                        session,
                        actor_type="admin_user",
                        actor_id=authenticated.user_id,
                        action="provider_secret.challenge_cancelled",
                        result="succeeded",
                        request_id=request_id,
                        target_type="confirmation_challenge",
                        target_id=challenge.id,
                        metadata={
                            "purpose": challenge.purpose.value,
                            "terminal_result_code": challenge.terminal_result_code.value,
                            "runtime_installation_id": challenge.runtime_installation_id,
                            "provider_id": challenge.provider_id,
                            "credential_id": challenge.credential_id,
                            "provisioning_intent_id": challenge.provisioning_intent_id,
                            "auth_context_fingerprint": self._auth_fingerprint(
                                authenticated.session_id
                            ),
                        },
                    )
                    session.flush()
        except (DatabaseNotReady, IntegrityError, OperationalError, ValueError) as exc:
            raise ApprovalUnavailable() from exc
        except (ApprovalAlreadyFinal, ApprovalInvalid) as exc:
            self._record_rejection(
                authenticated,
                challenge_id=challenge_id,
                request_id=request_id,
                error=exc,
                id_well_formed=True,
            )
            raise
        if deferred_error is not None:
            self._record_rejection(
                authenticated,
                challenge_id=challenge_id,
                request_id=request_id,
                error=deferred_error,
                id_well_formed=True,
            )
            raise deferred_error
        if expired:
            error = ApprovalAlreadyFinal()
            self._record_rejection(
                authenticated,
                challenge_id=challenge_id,
                request_id=request_id,
                error=error,
                id_well_formed=True,
            )
            raise error
        return challenge

    def cancel_authorized_attempt(
        self,
        authenticated: AuthenticatedSession,
        attempt_id: str,
        *,
        request_id: str,
    ) -> ProviderSecretProvisioningAttempt:
        _id(attempt_id, "psa")
        _request(request_id)
        expired = False
        try:
            with self._database.transaction() as session:
                session.execute(text("BEGIN IMMEDIATE"))
                now = self._database.transaction_now(session)
                attempt = session.get(ProviderSecretProvisioningAttempt, attempt_id)
                if (
                    attempt is None
                    or attempt.admin_user_id != authenticated.user_id
                    or attempt.control_plane_session_id != authenticated.session_id
                ):
                    raise ApprovalInvalid()
                if attempt.state is ProviderSecretProvisioningAttemptState.CANCELLED:
                    return attempt
                if attempt.state is not ProviderSecretProvisioningAttemptState.AUTHORIZED:
                    raise ApprovalAlreadyFinal()
                stored = session.get(ControlPlaneSession, authenticated.session_id)
                admin = session.get(AdminUser, authenticated.user_id)
                if (
                    stored is None
                    or admin is None
                    or not admin.is_active
                    or stored.user_id != admin.id
                    or stored.revoked_at is not None
                    or stored.expires_at <= now
                    or stored.idle_expires_at <= now
                ):
                    raise ApprovalInvalid()
                if (
                    attempt.authorize_requested_at is not None
                    or attempt.authorize_request_id is not None
                    or attempt.authorize_attempt_count != 0
                    or attempt.authorize_last_result_code is not AuthorizeResultCode.NOT_REQUESTED
                ):
                    raise ApprovalConflict()
                if now >= attempt.expires_at:
                    attempt.state = ProviderSecretProvisioningAttemptState.EXPIRED
                    attempt.updated_at = now
                    attempt.terminal_at = now
                    attempt.terminal_result_code = AttemptTerminalResultCode.INTENT_EXPIRED_UNSENT
                    attempt.retention_eligible_at = now + RETENTION
                    expired = True
                else:
                    attempt.state = ProviderSecretProvisioningAttemptState.CANCELLED
                    attempt.updated_at = now
                    attempt.cancellation_epoch = 1
                    attempt.cancel_requested_at = now
                    attempt.cancel_request_id = request_id
                    attempt.cancellation_result_code = CancellationResultCode.LOCAL_CANCELLED
                    attempt.terminal_at = now
                    attempt.terminal_result_code = AttemptTerminalResultCode.LOCAL_CANCELLED
                    attempt.retention_eligible_at = now + RETENTION
                self._audit.record(
                    session,
                    actor_type="admin_user",
                    actor_id=authenticated.user_id,
                    action="provider_secret.attempt_transitioned",
                    result="succeeded",
                    request_id=request_id,
                    target_type="provider_secret_provisioning_attempt",
                    target_id=attempt.id,
                    metadata={
                        "from_state": "authorized",
                        "to_state": attempt.state.value,
                        "authorize_result_code": AuthorizeResultCode.NOT_REQUESTED.value,
                        "terminal_result_code": attempt.terminal_result_code.value,
                        "cancellation_result_code": attempt.cancellation_result_code.value,
                        "runtime_installation_id": attempt.runtime_installation_id,
                        "provider_id": attempt.provider_id,
                        "credential_id": attempt.credential_id,
                        "provisioning_intent_id": attempt.provisioning_intent_id,
                    },
                )
                session.flush()
        except (DatabaseNotReady, IntegrityError, OperationalError, ValueError) as exc:
            raise ApprovalUnavailable() from exc
        if expired:
            raise ApprovalAlreadyFinal()
        return attempt

    def maintenance(self) -> ApprovalMaintenanceResult:
        """Apply one deterministic, globally bounded approval maintenance batch."""
        counts = [0, 0, 0, 0]
        try:
            with self._database.transaction() as session:
                session.execute(text("BEGIN IMMEDIATE"))
                now = self._database.transaction_now(session)
                candidates = session.execute(
                    text(
                        "SELECT priority, id FROM ("
                        "SELECT 1 priority, expires_at eligible_at, id FROM confirmation_challenges WHERE state='issued' AND expires_at <= :now "
                        "UNION ALL SELECT 1, expires_at, id FROM provider_secret_provisioning_attempts WHERE state='authorized' AND expires_at <= :now "
                        "UNION ALL SELECT 2, terminal_at, id FROM provider_secret_provisioning_attempts WHERE state IN ('reconciled','cancelled','expired') AND retention_eligible_at <= :now "
                        "UNION ALL SELECT 3, terminal_at, id FROM confirmation_challenges c WHERE state IN ('consumed','cancelled','expired') AND retention_eligible_at <= :now AND NOT EXISTS (SELECT 1 FROM provider_secret_provisioning_attempts a WHERE a.challenge_id=c.id) "
                        "UNION ALL SELECT 4, min(idle_expires_at,expires_at,COALESCE(revoked_at,expires_at)), id FROM sessions s WHERE (revoked_at <= :session_cutoff OR idle_expires_at <= :session_cutoff OR expires_at <= :session_cutoff) AND NOT EXISTS (SELECT 1 FROM confirmation_challenges c WHERE c.control_plane_session_id=s.id) AND NOT EXISTS (SELECT 1 FROM provider_secret_provisioning_attempts a WHERE a.control_plane_session_id=s.id)"
                        ") ORDER BY priority, eligible_at, id LIMIT 100"
                    ),
                    {
                        "now": raw_utc6(now),
                        "session_cutoff": raw_utc6(now - self._session_retention),
                    },
                ).all()
                for priority, row_id in candidates:
                    if priority == 1 and str(row_id).startswith("cch_"):
                        challenge = session.get(ConfirmationChallenge, row_id)
                        if (
                            challenge is not None
                            and challenge.state is ConfirmationChallengeState.ISSUED
                        ):
                            self._expire_challenge(challenge, now)
                            if (
                                cast(ConfirmationChallengeState, challenge.state)
                                is ConfirmationChallengeState.EXPIRED
                            ):
                                counts[0] += 1
                    elif priority == 1:
                        attempt = session.get(ProviderSecretProvisioningAttempt, row_id)
                        if (
                            attempt is not None
                            and attempt.state is ProviderSecretProvisioningAttemptState.AUTHORIZED
                        ):
                            attempt.state = ProviderSecretProvisioningAttemptState.EXPIRED
                            attempt.updated_at = now
                            attempt.terminal_at = now
                            attempt.terminal_result_code = (
                                AttemptTerminalResultCode.INTENT_EXPIRED_UNSENT
                            )
                            attempt.retention_eligible_at = now + RETENTION
                            self._audit.record(
                                session,
                                actor_type="system",
                                actor_id=None,
                                action="provider_secret.attempt_transitioned",
                                result="succeeded",
                                request_id=None,
                                target_type="provider_secret_provisioning_attempt",
                                target_id=attempt.id,
                                metadata={
                                    "from_state": "authorized",
                                    "to_state": "expired",
                                    "authorize_result_code": AuthorizeResultCode.NOT_REQUESTED.value,
                                    "terminal_result_code": AttemptTerminalResultCode.INTENT_EXPIRED_UNSENT.value,
                                    "cancellation_result_code": CancellationResultCode.NOT_REQUESTED.value,
                                    "runtime_installation_id": attempt.runtime_installation_id,
                                    "provider_id": attempt.provider_id,
                                    "credential_id": attempt.credential_id,
                                    "provisioning_intent_id": attempt.provisioning_intent_id,
                                },
                            )
                            counts[0] += 1
                    elif priority == 2:
                        result = cast(
                            CursorResult[object],
                            session.execute(
                                delete(ProviderSecretProvisioningAttempt).where(
                                    ProviderSecretProvisioningAttempt.id == row_id
                                )
                            ),
                        )
                        counts[1] += int(result.rowcount or 0)
                    elif priority == 3:
                        result = cast(
                            CursorResult[object],
                            session.execute(
                                delete(ConfirmationChallenge).where(
                                    ConfirmationChallenge.id == row_id
                                )
                            ),
                        )
                        counts[2] += int(result.rowcount or 0)
                    else:
                        result = cast(
                            CursorResult[object],
                            session.execute(
                                delete(ControlPlaneSession).where(ControlPlaneSession.id == row_id)
                            ),
                        )
                        counts[3] += int(result.rowcount or 0)
                self._audit.record(
                    session,
                    actor_type="system",
                    actor_id=None,
                    action="provider_secret.maintenance_completed",
                    result="succeeded",
                    request_id=None,
                    target_type="provider_secret_maintenance",
                    target_id=None,
                    metadata={
                        "approval_expired_count": counts[0],
                        "attempt_pruned_count": counts[1],
                        "challenge_pruned_count": counts[2],
                        "auth_context_pruned_count": counts[3],
                    },
                )
        except (DatabaseNotReady, IntegrityError, OperationalError, ValueError) as exc:
            raise ApprovalUnavailable() from exc
        return ApprovalMaintenanceResult(*counts)

    def _bound_entities(
        self,
        session: Session,
        authenticated: AuthenticatedSession,
        values: ChallengeIssue,
        now: datetime,
    ) -> tuple[ControlPlaneSession, RuntimeInstallation, Provider, ProviderCredential]:
        stored = session.get(ControlPlaneSession, _id(authenticated.session_id, "ses"))
        admin = session.get(AdminUser, _id(authenticated.user_id, "adm"))
        runtime = session.get(RuntimeInstallation, _id(values.runtime_installation_id, "rti"))
        provider = session.get(Provider, _id(values.provider_id, "prv"))
        credential = session.get(ProviderCredential, _id(values.credential_id, "crd"))
        if (
            stored is None
            or admin is None
            or runtime is None
            or provider is None
            or credential is None
        ):
            raise ApprovalInvalid()
        if (
            stored.user_id != admin.id
            or stored.id != authenticated.session_id
            or not admin.is_active
            or stored.revoked_at is not None
            or stored.expires_at <= now
            or stored.idle_expires_at <= now
            or stored.auth_epoch != authenticated.auth_epoch
            or stored.recent_authenticated_at != authenticated.authenticated_at
            or now < stored.recent_authenticated_at
            or now - stored.recent_authenticated_at > APPROVAL_TTL
            or runtime.revision != values.runtime_installation_revision
            or runtime.runtime_type is not values.runtime_type
            or runtime.runtime_type is not RuntimeType.CODEX
            or provider.revision != values.provider_revision
            or provider.state is not values.provider_state
            or provider.state
            not in (ProviderLifecycleState.CONFIGURED, ProviderLifecycleState.VALIDATED)
            or credential.revision != values.credential_revision
            or credential.kind is not values.credential_kind
            or credential.kind is not CredentialKind.API_KEY
            or credential.state is not values.credential_state
            or credential.state is not CredentialLifecycleState.MISSING
            or credential.provider_id != provider.id
            or credential.runtime_installation_id != runtime.id
            or credential.runtime_secret_ref is not None
            or credential.secret_version is not None
        ):
            raise ApprovalStale()
        return stored, runtime, provider, credential

    def _challenge_entities_current(
        self, session: Session, challenge: ConfirmationChallenge
    ) -> bool:
        runtime = session.get(RuntimeInstallation, challenge.runtime_installation_id)
        provider = session.get(Provider, challenge.provider_id)
        credential = session.get(ProviderCredential, challenge.credential_id)
        return bool(
            challenge.schema_version == 1
            and challenge.intent_contract_version == 1
            and challenge.purpose is ConfirmationPurpose.PROVIDER_SECRET_PROVISION
            and runtime is not None
            and provider is not None
            and credential is not None
            and runtime.revision == challenge.runtime_installation_revision
            and runtime.runtime_type is challenge.runtime_type
            and provider.revision == challenge.provider_revision
            and provider.state is challenge.provider_state
            and credential.revision == challenge.credential_revision
            and credential.kind is challenge.credential_kind
            and credential.state is challenge.credential_state
            and credential.provider_id == challenge.provider_id
            and credential.runtime_installation_id == challenge.runtime_installation_id
            and credential.runtime_secret_ref is None
            and credential.secret_version is None
        )

    def _attempt_from_challenge(
        self, session: Session, challenge: ConfirmationChallenge, request_id: str, now: datetime
    ) -> ProviderSecretProvisioningAttempt:
        return ProviderSecretProvisioningAttempt(
            id=self._unique_id(session, ProviderSecretProvisioningAttempt, "psa"),
            schema_version=1,
            intent_contract_version=challenge.intent_contract_version,
            purpose=challenge.purpose,
            state=ProviderSecretProvisioningAttemptState.AUTHORIZED,
            challenge_id=challenge.id,
            provisioning_intent_id=challenge.provisioning_intent_id,
            authorization_request_id=request_id,
            admin_user_id=challenge.admin_user_id,
            control_plane_session_id=challenge.control_plane_session_id,
            auth_epoch=challenge.auth_epoch,
            runtime_installation_id=challenge.runtime_installation_id,
            runtime_installation_revision=challenge.runtime_installation_revision,
            runtime_type=challenge.runtime_type,
            provider_id=challenge.provider_id,
            provider_revision=challenge.provider_revision,
            provider_state=challenge.provider_state,
            credential_id=challenge.credential_id,
            credential_revision=challenge.credential_revision,
            credential_kind=challenge.credential_kind,
            credential_state=challenge.credential_state,
            credential_runtime_installation_id=challenge.credential_runtime_installation_id,
            expected_runtime_secret_ref=None,
            expected_secret_version=None,
            intended_state=challenge.intended_state,
            intended_secret_version=challenge.intended_secret_version,
            approval_digest=challenge.approval_digest,
            intent_issued_at=challenge.intent_issued_at,
            authorized_at=now,
            expires_at=challenge.expires_at,
            created_at=now,
            updated_at=now,
            authorize_attempt_count=0,
            authorize_last_result_code=AuthorizeResultCode.NOT_REQUESTED,
            initial_cancellation_epoch=challenge.initial_cancellation_epoch,
            cancellation_epoch=challenge.cancellation_epoch,
            cancellation_result_code=CancellationResultCode.NOT_REQUESTED,
        )

    @staticmethod
    def _unique_id(
        session: Session, model: type[object], prefix: str, *, column: str = "id"
    ) -> str:
        attribute = getattr(model, column)
        for _attempt in range(4):
            candidate = new_identifier(prefix)
            if session.scalar(select(attribute).where(attribute == candidate)) is None:
                return candidate
        raise ApprovalUnavailable()

    @staticmethod
    def _same_actor(challenge: ConfirmationChallenge, authenticated: AuthenticatedSession) -> bool:
        return (
            challenge.admin_user_id == authenticated.user_id
            and challenge.control_plane_session_id == authenticated.session_id
        )

    @staticmethod
    def _terminalize_challenge(
        challenge: ConfirmationChallenge, now: datetime, result: ChallengeTerminalResultCode
    ) -> None:
        terminal_time = max(now, challenge.issued_at, challenge.last_observed_at)
        challenge.state = ConfirmationChallengeState.CANCELLED
        challenge.cancellation_epoch = 1
        challenge.last_observed_at = terminal_time
        challenge.terminal_at = terminal_time
        challenge.terminal_result_code = result
        challenge.retention_eligible_at = terminal_time + RETENTION

    @staticmethod
    def _expire_challenge(challenge: ConfirmationChallenge, now: datetime) -> None:
        if now < challenge.issued_at or now < challenge.last_observed_at:
            ApprovalService._terminalize_challenge(
                challenge, now, ChallengeTerminalResultCode.CLOCK_ROLLBACK_DETECTED
            )
            return
        challenge.state = ConfirmationChallengeState.EXPIRED
        challenge.last_observed_at = now
        challenge.terminal_at = now
        challenge.terminal_result_code = ChallengeTerminalResultCode.DEADLINE_EXPIRED
        challenge.retention_eligible_at = now + RETENTION

    def _auth_fingerprint(self, session_id: str) -> str:
        return keyed_digest(self._secret, "audit-auth-context", session_id)[:24]

    def _record_rejection(
        self,
        authenticated: AuthenticatedSession,
        *,
        challenge_id: str | None,
        request_id: str | None,
        error: Exception,
        id_well_formed: bool,
    ) -> None:
        """Record only normalized rejection data; never expose an arbitrary target tuple."""
        reason_code = (
            error.code
            if isinstance(
                error,
                (
                    ApprovalAlreadyFinal,
                    ApprovalConflict,
                    ApprovalExpired,
                    ApprovalInvalid,
                    ApprovalStale,
                    ApprovalUnavailable,
                ),
            )
            else ApprovalUnavailable.code
        )
        try:
            with self._database.transaction() as session:
                target_id: str | None = None
                if challenge_id is not None and id_well_formed:
                    challenge = session.get(ConfirmationChallenge, challenge_id)
                    if challenge is not None and self._same_actor(challenge, authenticated):
                        target_id = challenge.id
                self._audit.record(
                    session,
                    actor_type="admin_user",
                    actor_id=authenticated.user_id,
                    action="provider_secret.challenge_rejected",
                    result="rejected",
                    request_id=request_id,
                    target_type="confirmation_challenge" if target_id is not None else None,
                    target_id=target_id,
                    metadata={"reason_code": reason_code, "id_well_formed": id_well_formed},
                )
        except (DatabaseNotReady, IntegrityError, OperationalError, ValueError) as exc:
            raise ApprovalUnavailable() from exc

    def _challenge_audit(self, challenge: ConfirmationChallenge) -> dict[str, object]:
        return {
            "runtime_installation_id": challenge.runtime_installation_id,
            "runtime_revision": challenge.runtime_installation_revision,
            "provider_id": challenge.provider_id,
            "provider_revision": challenge.provider_revision,
            "credential_id": challenge.credential_id,
            "credential_revision": challenge.credential_revision,
            "auth_context_fingerprint": self._auth_fingerprint(challenge.control_plane_session_id),
            "auth_epoch": challenge.auth_epoch,
            "purpose": challenge.purpose.value,
            "expires_at": _utc6(challenge.expires_at),
            "approval_digest": challenge.approval_digest,
            "provisioning_intent_id": challenge.provisioning_intent_id,
        }
