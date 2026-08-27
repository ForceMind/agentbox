"""Frozen Phase 11 Slice 3.2a approval schema used by Alembic revision 0005."""

# ruff: noqa: E501 -- exact database constraints remain readable as SQL literals.

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from agentbox_core.models import Base
from agentbox_core.provider_models import (
    CredentialKind,
    CredentialLifecycleState,
    ProviderLifecycleState,
    RuntimeType,
)
from agentbox_core.utc import UTC6DateTime


def _values(enum_type: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_type]


def _enum(enum_type: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_type,
        values_callable=_values,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        name=name,
    )


class ConfirmationPurpose(StrEnum):
    PROVIDER_SECRET_PROVISION = "provider_secret_provision"


class ConfirmationChallengeState(StrEnum):
    ISSUED = "issued"
    CONSUMED = "consumed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ChallengeTerminalResultCode(StrEnum):
    ATTEMPT_CREATED = "ATTEMPT_CREATED"
    CANCELLED_BY_ISSUER = "CANCELLED_BY_ISSUER"
    AUTH_EPOCH_ROTATED = "AUTH_EPOCH_ROTATED"
    SESSION_REVOKED = "SESSION_REVOKED"
    ADMIN_DEACTIVATED = "ADMIN_DEACTIVATED"
    CONFIRMATION_MISMATCH = "CONFIRMATION_MISMATCH"
    BOUND_ENTITY_STALE = "BOUND_ENTITY_STALE"
    CLOCK_ROLLBACK_DETECTED = "CLOCK_ROLLBACK_DETECTED"
    DEADLINE_EXPIRED = "DEADLINE_EXPIRED"


class ApprovalPublicErrorCode(StrEnum):
    APPROVAL_INVALID = "APPROVAL_INVALID"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_STALE = "APPROVAL_STALE"
    APPROVAL_ALREADY_FINAL = "APPROVAL_ALREADY_FINAL"
    APPROVAL_CONFLICT = "APPROVAL_CONFLICT"
    APPROVAL_UNAVAILABLE = "APPROVAL_UNAVAILABLE"


class ReauthenticationPublicErrorCode(StrEnum):
    INVALID_SESSION = "INVALID_SESSION"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    LOGIN_RATE_LIMITED = "LOGIN_RATE_LIMITED"
    REAUTH_UNAVAILABLE = "REAUTH_UNAVAILABLE"


class ProviderSecretProvisioningAttemptState(StrEnum):
    AUTHORIZED = "authorized"
    AUTHORIZE_PENDING = "authorize_pending"
    RUNTIME_STAGED = "runtime_staged"
    CANCEL_PENDING = "cancel_pending"
    RUNTIME_CONSUMING = "runtime_consuming"
    RUNTIME_COMMITTED_UNVERIFIED = "runtime_committed_unverified"
    RUNTIME_VERIFIED = "runtime_verified"
    RECONCILED = "reconciled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    NEEDS_ATTENTION = "needs_attention"


class AttemptTerminalResultCode(StrEnum):
    LOCAL_CANCELLED = "LOCAL_CANCELLED"
    RUNTIME_CANCELLED_CONFIRMED = "RUNTIME_CANCELLED_CONFIRMED"
    INTENT_EXPIRED_UNSENT = "INTENT_EXPIRED_UNSENT"
    INTENT_EXPIRED_NOT_FOUND_CONFIRMED = "INTENT_EXPIRED_NOT_FOUND_CONFIRMED"
    RUNTIME_INTENT_EXPIRED_CONFIRMED = "RUNTIME_INTENT_EXPIRED_CONFIRMED"
    RECONCILIATION_COMPLETE = "RECONCILIATION_COMPLETE"
    BOUND_ENTITY_STALE = "BOUND_ENTITY_STALE"
    RUNTIME_STATUS_CONTRADICTION = "RUNTIME_STATUS_CONTRADICTION"
    RUNTIME_OPERATION_UNCERTAIN = "RUNTIME_OPERATION_UNCERTAIN"
    ATTESTATION_REJECTED = "ATTESTATION_REJECTED"
    RUNTIME_REPORTED_UNEXPECTED_TERMINAL = "RUNTIME_REPORTED_UNEXPECTED_TERMINAL"
    AUTHORIZE_TRANSMISSION_LIMIT_EXCEEDED = "AUTHORIZE_TRANSMISSION_LIMIT_EXCEEDED"


class CancellationResultCode(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"
    LOCAL_CANCELLED = "LOCAL_CANCELLED"
    RUNTIME_CANCEL_REQUESTED = "RUNTIME_CANCEL_REQUESTED"
    RUNTIME_CANCELLED_CONFIRMED = "RUNTIME_CANCELLED_CONFIRMED"
    RUNTIME_CANCEL_LOST_TO_CONSUMING = "RUNTIME_CANCEL_LOST_TO_CONSUMING"
    RUNTIME_CANCEL_LOST_TO_COMMITTED_UNVERIFIED = "RUNTIME_CANCEL_LOST_TO_COMMITTED_UNVERIFIED"
    RUNTIME_CANCEL_LOST_TO_VERIFIED = "RUNTIME_CANCEL_LOST_TO_VERIFIED"
    RUNTIME_CANCEL_LOST_TO_EXPIRY = "RUNTIME_CANCEL_LOST_TO_EXPIRY"
    RUNTIME_CANCEL_CONTRADICTION = "RUNTIME_CANCEL_CONTRADICTION"


class RuntimeAttestationResultCode(StrEnum):
    VERIFIED_LIVE_PLAINTEXT_MATCH = "VERIFIED_LIVE_PLAINTEXT_MATCH"
    VERIFIED_RECOVERED_AEAD_REOPEN = "VERIFIED_RECOVERED_AEAD_REOPEN"


class AuthorizeResultCode(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"
    REQUEST_PERSISTED = "REQUEST_PERSISTED"
    STATUS_NOT_FOUND = "STATUS_NOT_FOUND"
    RESEND_PERSISTED = "RESEND_PERSISTED"
    STATUS_STAGED = "STATUS_STAGED"
    STATUS_CONSUMING = "STATUS_CONSUMING"
    STATUS_COMMITTED_UNVERIFIED = "STATUS_COMMITTED_UNVERIFIED"
    STATUS_VERIFIED = "STATUS_VERIFIED"
    STATUS_EXPIRED = "STATUS_EXPIRED"
    STATUS_CANCELLED_UNEXPECTED = "STATUS_CANCELLED_UNEXPECTED"
    STATUS_FAILED_UNEXPECTED = "STATUS_FAILED_UNEXPECTED"
    STATUS_NEEDS_ATTENTION_UNEXPECTED = "STATUS_NEEDS_ATTENTION_UNEXPECTED"
    STATUS_EXPIRED_UNRECONCILED_UNEXPECTED = "STATUS_EXPIRED_UNRECONCILED_UNEXPECTED"
    STATUS_UNAVAILABLE = "STATUS_UNAVAILABLE"
    STATUS_MALFORMED = "STATUS_MALFORMED"
    STATUS_CONTRADICTORY = "STATUS_CONTRADICTORY"
    TRANSMISSION_LIMIT_EXCEEDED = "TRANSMISSION_LIMIT_EXCEEDED"


class RuntimeProviderSecretProvisionStatus(StrEnum):
    NOT_FOUND = "NOT_FOUND"
    STAGED = "STAGED"
    CONSUMING = "CONSUMING"
    COMMITTED_UNVERIFIED = "COMMITTED_UNVERIFIED"
    VERIFIED = "VERIFIED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    EXPIRED_UNRECONCILED = "EXPIRED_UNRECONCILED"


_ID_CHECK = "length({column}) = 36 AND substr({column}, 1, 4) = '{prefix}_' AND substr({column}, 5) NOT GLOB '*[^0-9a-f]*'"
_HEX64 = "length({column}) = 64 AND {column} NOT GLOB '*[^0-9a-f]*'"
_REQUEST_ID = "length({column}) BETWEEN 1 AND 64 AND substr({column},1,1) GLOB '[A-Za-z0-9]' AND {column} NOT GLOB '*[^A-Za-z0-9._:-]*'"
_UTC6_GLOB = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]"


def _utc6_calendar(column: str) -> str:
    year = f"CAST(substr({column},1,4) AS INTEGER)"
    month = f"CAST(substr({column},6,2) AS INTEGER)"
    day = f"CAST(substr({column},9,2) AS INTEGER)"
    max_day = (
        f"CASE WHEN {month} IN (1,3,5,7,8,10,12) THEN 31 "
        f"WHEN {month} IN (4,6,9,11) THEN 30 WHEN {month}=2 THEN "
        f"CASE WHEN ({year}%4=0 AND ({year}%100<>0 OR {year}%400=0)) THEN 29 ELSE 28 END "
        "ELSE 0 END"
    )
    return (
        f"{year} BETWEEN 1 AND 9999 AND {month} BETWEEN 1 AND 12 "
        f"AND {day} BETWEEN 1 AND ({max_day}) "
        f"AND CAST(substr({column},12,2) AS INTEGER) BETWEEN 0 AND 23 "
        f"AND CAST(substr({column},15,2) AS INTEGER) BETWEEN 0 AND 59 "
        f"AND CAST(substr({column},18,2) AS INTEGER) BETWEEN 0 AND 59"
    )


_UTC6 = (
    "length({column}) = 26 AND {column} GLOB '" + _UTC6_GLOB + "' AND " + _utc6_calendar("{column}")
)


def attempt_state_consistency_sql(prefix: str = "") -> str:
    """Return the closed Attempt state/field cross-product for checks and triggers."""

    def c(name: str) -> str:
        return f"{prefix}{name}"

    def null(*names: str) -> str:
        return " AND ".join(f"{c(name)} IS NULL" for name in names)

    def present(*names: str) -> str:
        return " AND ".join(f"{c(name)} IS NOT NULL" for name in names)

    runtime_after_authorize = (
        "runtime_staged_at",
        "runtime_consuming_at",
        "runtime_committed_at",
        "runtime_commit_observed_at",
        "runtime_verified_at",
        "reconciled_at",
    )
    terminal = ("terminal_at", "terminal_result_code", "retention_eligible_at")
    cancel = ("cancel_requested_at", "cancel_request_id")
    safe_retention = (
        f"{c('retention_eligible_at')} = datetime({c('terminal_at')}, '+30 days') || "
        f"substr({c('terminal_at')},20,7)"
    )
    authorized = (
        f"{c('state')}='authorized' AND {null('authorize_requested_at','authorize_request_id',*runtime_after_authorize,*cancel,'runtime_attestation_code',*terminal)} "
        f"AND {c('authorize_attempt_count')}=0 AND {c('authorize_last_result_code')}='NOT_REQUESTED' "
        f"AND {c('cancellation_epoch')}=0 AND {c('cancellation_result_code')}='NOT_REQUESTED'"
    )
    authorize_pending = (
        f"{c('state')}='authorize_pending' AND {present('authorize_requested_at','authorize_request_id')} "
        f"AND {c('authorize_attempt_count')} BETWEEN 1 AND 3 "
        f"AND {c('authorize_last_result_code')} IN ('REQUEST_PERSISTED','RESEND_PERSISTED','STATUS_UNAVAILABLE') "
        f"AND {c('cancellation_epoch')}=0 AND {c('cancellation_result_code')}='NOT_REQUESTED' "
        f"AND {null(*runtime_after_authorize,*cancel,'runtime_attestation_code',*terminal)}"
    )
    runtime_staged = (
        f"{c('state')}='runtime_staged' AND {present('authorize_requested_at','authorize_request_id','runtime_staged_at')} "
        f"AND {c('authorize_attempt_count')} BETWEEN 1 AND 3 AND {c('authorize_last_result_code')}='STATUS_STAGED' "
        f"AND {c('cancellation_epoch')}=0 AND {c('cancellation_result_code')}='NOT_REQUESTED' "
        f"AND {null('runtime_consuming_at','runtime_committed_at','runtime_commit_observed_at','runtime_verified_at','reconciled_at',*cancel,'runtime_attestation_code',*terminal)}"
    )
    cancel_pending = (
        f"{c('state')}='cancel_pending' AND {present('authorize_requested_at','authorize_request_id',*cancel)} "
        f"AND {c('authorize_attempt_count')} BETWEEN 1 AND 3 "
        f"AND {c('authorize_last_result_code')} IN ('REQUEST_PERSISTED','RESEND_PERSISTED','STATUS_UNAVAILABLE','STATUS_STAGED') "
        f"AND (({c('authorize_last_result_code')}='STATUS_STAGED' AND {c('runtime_staged_at')} IS NOT NULL) OR "
        f"({c('authorize_last_result_code')}<>'STATUS_STAGED' AND {c('runtime_staged_at')} IS NULL)) "
        f"AND {c('cancellation_epoch')}=1 AND {c('cancellation_result_code')}='RUNTIME_CANCEL_REQUESTED' "
        f"AND {null('runtime_consuming_at','runtime_committed_at','runtime_commit_observed_at','runtime_verified_at','reconciled_at','runtime_attestation_code',*terminal)}"
    )
    consuming = (
        f"{c('state')}='runtime_consuming' AND {present('authorize_requested_at','authorize_request_id','runtime_consuming_at')} "
        f"AND {c('authorize_attempt_count')} BETWEEN 1 AND 3 AND {c('authorize_last_result_code')}='STATUS_CONSUMING' "
        f"AND (({c('cancellation_result_code')}='NOT_REQUESTED' AND {c('cancellation_epoch')}=0 AND {null(*cancel)}) OR "
        f"({c('cancellation_result_code')}='RUNTIME_CANCEL_LOST_TO_CONSUMING' AND {c('cancellation_epoch')}=1 AND {present(*cancel)})) "
        f"AND {null('runtime_committed_at','runtime_commit_observed_at','runtime_verified_at','reconciled_at','runtime_attestation_code',*terminal)}"
    )
    committed = (
        f"{c('state')}='runtime_committed_unverified' AND {present('authorize_requested_at','authorize_request_id','runtime_commit_observed_at')} "
        f"AND {c('authorize_attempt_count')} BETWEEN 1 AND 3 AND {c('authorize_last_result_code')}='STATUS_COMMITTED_UNVERIFIED' "
        f"AND (({c('cancellation_result_code')}='NOT_REQUESTED' AND {c('cancellation_epoch')}=0 AND {null(*cancel)}) OR "
        f"({c('cancellation_result_code')}='RUNTIME_CANCEL_LOST_TO_COMMITTED_UNVERIFIED' AND {c('cancellation_epoch')}=1 AND {present(*cancel)})) "
        f"AND {null('runtime_verified_at','reconciled_at','runtime_attestation_code',*terminal)}"
    )
    verified_base = (
        f"{present('authorize_requested_at','authorize_request_id','runtime_verified_at','runtime_attestation_code')} "
        f"AND {c('authorize_attempt_count')} BETWEEN 1 AND 3 AND {c('authorize_last_result_code')}='STATUS_VERIFIED' "
        f"AND (({c('cancellation_result_code')}='NOT_REQUESTED' AND {c('cancellation_epoch')}=0 AND {null(*cancel)}) OR "
        f"({c('cancellation_result_code')}='RUNTIME_CANCEL_LOST_TO_VERIFIED' AND {c('cancellation_epoch')}=1 AND {present(*cancel)}))"
    )
    verified = (
        f"{c('state')}='runtime_verified' AND {verified_base} AND {null('reconciled_at',*terminal)}"
    )
    reconciled = (
        f"{c('state')}='reconciled' AND {verified_base} AND {present('reconciled_at','terminal_at','retention_eligible_at')} "
        f"AND {c('reconciled_at')}={c('terminal_at')} AND {c('updated_at')}={c('terminal_at')} "
        f"AND {c('terminal_result_code')}='RECONCILIATION_COMPLETE' AND {safe_retention}"
    )
    cancelled = (
        f"{c('state')}='cancelled' AND {present(*cancel,'terminal_at','retention_eligible_at')} "
        f"AND {c('cancellation_epoch')}=1 AND {null('runtime_consuming_at','runtime_committed_at','runtime_commit_observed_at','runtime_verified_at','reconciled_at','runtime_attestation_code')} "
        f"AND {c('updated_at')}={c('terminal_at')} AND (({null('authorize_requested_at','authorize_request_id','runtime_staged_at')} AND {c('authorize_attempt_count')}=0 "
        f"AND {c('authorize_last_result_code')}='NOT_REQUESTED' AND {c('cancellation_result_code')}='LOCAL_CANCELLED' AND {c('terminal_result_code')}='LOCAL_CANCELLED') OR "
        f"({present('authorize_requested_at','authorize_request_id')} AND {c('authorize_attempt_count')} BETWEEN 1 AND 3 "
        f"AND {c('authorize_last_result_code')} IN ('REQUEST_PERSISTED','RESEND_PERSISTED','STATUS_UNAVAILABLE','STATUS_STAGED') "
        f"AND (({c('authorize_last_result_code')}='STATUS_STAGED' AND {c('runtime_staged_at')} IS NOT NULL) OR "
        f"({c('authorize_last_result_code')}<>'STATUS_STAGED' AND {c('runtime_staged_at')} IS NULL)) "
        f"AND {c('cancellation_result_code')}='RUNTIME_CANCELLED_CONFIRMED' AND {c('terminal_result_code')}='RUNTIME_CANCELLED_CONFIRMED')) "
        f"AND ({c('cancellation_result_code')}<>'LOCAL_CANCELLED' OR ({c('cancel_requested_at')}={c('terminal_at')})) "
        f"AND {safe_retention}"
    )
    expired = (
        f"{c('state')}='expired' AND {present('terminal_at','retention_eligible_at')} "
        f"AND {c('updated_at')}={c('terminal_at')} "
        f"AND {null('runtime_consuming_at','runtime_committed_at','runtime_commit_observed_at','runtime_verified_at','reconciled_at','runtime_attestation_code')} "
        f"AND (({null('authorize_requested_at','authorize_request_id','runtime_staged_at',*cancel)} AND {c('authorize_attempt_count')}=0 "
        f"AND {c('authorize_last_result_code')}='NOT_REQUESTED' AND {c('cancellation_epoch')}=0 AND {c('cancellation_result_code')}='NOT_REQUESTED' "
        f"AND {c('terminal_result_code')}='INTENT_EXPIRED_UNSENT') OR "
        f"({present('authorize_requested_at','authorize_request_id')} AND {c('authorize_attempt_count')} BETWEEN 1 AND 3 "
        f"AND {c('authorize_last_result_code')}='STATUS_NOT_FOUND' AND {null('runtime_staged_at',*cancel)} "
        f"AND {c('cancellation_epoch')}=0 AND {c('cancellation_result_code')}='NOT_REQUESTED' AND {c('terminal_result_code')}='INTENT_EXPIRED_NOT_FOUND_CONFIRMED') OR "
        f"({present('authorize_requested_at','authorize_request_id')} AND {c('authorize_attempt_count')} BETWEEN 1 AND 3 "
        f"AND {c('authorize_last_result_code')}='STATUS_EXPIRED' AND {c('terminal_result_code')}='RUNTIME_INTENT_EXPIRED_CONFIRMED' "
        f"AND (({c('cancellation_result_code')}='NOT_REQUESTED' AND {c('cancellation_epoch')}=0 AND {null(*cancel)}) OR "
        f"({c('cancellation_result_code')}='RUNTIME_CANCEL_LOST_TO_EXPIRY' AND {c('cancellation_epoch')}=1 AND {present(*cancel)})))) "
        f"AND {safe_retention}"
    )
    needs_attention = (
        f"{c('state')}='needs_attention' AND {c('terminal_at')} IS NOT NULL AND {c('updated_at')}={c('terminal_at')} AND {c('retention_eligible_at')} IS NULL "
        f"AND {c('reconciled_at')} IS NULL AND {c('terminal_result_code')} IN "
        "('BOUND_ENTITY_STALE','RUNTIME_STATUS_CONTRADICTION','RUNTIME_OPERATION_UNCERTAIN','ATTESTATION_REJECTED','RUNTIME_REPORTED_UNEXPECTED_TERMINAL','AUTHORIZE_TRANSMISSION_LIMIT_EXCEEDED')"
    )
    return (
        "("
        + ") OR (".join(
            (
                authorized,
                authorize_pending,
                runtime_staged,
                cancel_pending,
                consuming,
                committed,
                verified,
                reconciled,
                cancelled,
                expired,
                needs_attention,
            )
        )
        + ")"
    )


class ConfirmationChallenge(Base):
    __tablename__ = "confirmation_challenges"
    __table_args__ = (
        UniqueConstraint(
            "id", "provisioning_intent_id", name="uq_confirmation_challenges_id_intent"
        ),
        UniqueConstraint("provisioning_intent_id", name="uq_confirmation_challenges_intent"),
        ForeignKeyConstraint(
            ["control_plane_session_id", "admin_user_id"],
            ["sessions.id", "sessions.user_id"],
            ondelete="RESTRICT",
            name="fk_confirmation_challenges_session_admin",
        ),
        ForeignKeyConstraint(
            ["runtime_installation_id"],
            ["runtime_installations.id"],
            ondelete="RESTRICT",
            name="fk_confirmation_challenges_runtime_installation",
        ),
        ForeignKeyConstraint(
            ["provider_id"],
            ["provider_definitions.id"],
            ondelete="RESTRICT",
            name="fk_confirmation_challenges_provider",
        ),
        ForeignKeyConstraint(
            ["credential_id", "provider_id", "credential_runtime_installation_id"],
            [
                "provider_credentials.id",
                "provider_credentials.provider_id",
                "provider_credentials.runtime_installation_id",
            ],
            ondelete="RESTRICT",
            name="fk_confirmation_challenges_credential_runtime_identity",
        ),
        CheckConstraint(
            _ID_CHECK.format(column="id", prefix="cch"), name="ck_confirmation_challenges_id"
        ),
        CheckConstraint(
            "schema_version = 1 AND intent_contract_version = 1 AND auth_epoch >= 1 "
            "AND runtime_installation_revision >= 1 AND provider_revision >= 1 "
            "AND credential_revision >= 1 AND intended_secret_version = 1 "
            "AND initial_cancellation_epoch = 0 AND cancellation_epoch >= 0",
            name="ck_confirmation_challenges_schema",
        ),
        CheckConstraint(
            "runtime_type = 'codex' AND credential_kind = 'api_key' "
            "AND credential_state = 'missing' AND intended_state = 'configured' "
            "AND provider_state IN ('configured','validated')",
            name="ck_confirmation_challenges_expected_missing",
        ),
        CheckConstraint(
            "expected_runtime_secret_ref IS NULL AND expected_secret_version IS NULL",
            name="ck_confirmation_challenges_expected_reference",
        ),
        CheckConstraint(
            "credential_runtime_installation_id = runtime_installation_id",
            name="ck_confirmation_challenges_runtime_owner",
        ),
        CheckConstraint(
            _HEX64.format(column="confirmation_verifier")
            + " AND "
            + _HEX64.format(column="approval_digest"),
            name="ck_confirmation_challenges_digest",
        ),
        CheckConstraint(
            _REQUEST_ID.format(column="issue_request_id")
            + " AND (consumed_request_id IS NULL OR ("
            + _REQUEST_ID.format(column="consumed_request_id")
            + "))",
            name="ck_confirmation_challenges_request_ids",
        ),
        CheckConstraint(
            "created_at = issued_at AND intent_issued_at = issued_at AND "
            "intent_expires_at = expires_at AND expires_at = datetime(issued_at, '+300 seconds') || substr(issued_at,20,7) "
            "AND last_observed_at >= issued_at AND "
            + " AND ".join(
                _UTC6.format(column=column)
                for column in (
                    "recent_authenticated_at",
                    "issued_at",
                    "created_at",
                    "expires_at",
                    "intent_issued_at",
                    "intent_expires_at",
                    "last_observed_at",
                )
            )
            + " AND (terminal_at IS NULL OR ("
            + _UTC6.format(column="terminal_at")
            + ")) AND (consumed_at IS NULL OR ("
            + _UTC6.format(column="consumed_at")
            + ")) AND (retention_eligible_at IS NULL OR ("
            + _UTC6.format(column="retention_eligible_at")
            + "))",
            name="ck_confirmation_challenges_timestamps",
        ),
        CheckConstraint(
            "(state = 'issued' AND terminal_at IS NULL AND consumed_at IS NULL "
            "AND consumed_request_id IS NULL AND terminal_result_code IS NULL "
            "AND retention_eligible_at IS NULL AND cancellation_epoch = 0) OR "
            "(state = 'consumed' AND terminal_at IS NOT NULL AND consumed_at = terminal_at "
            "AND consumed_request_id IS NOT NULL AND terminal_result_code = 'ATTEMPT_CREATED' "
            "AND cancellation_epoch = 0 AND retention_eligible_at = datetime(terminal_at, '+30 days') || substr(terminal_at,20,7)) OR "
            "(state = 'cancelled' AND terminal_at IS NOT NULL AND consumed_at IS NULL "
            "AND consumed_request_id IS NULL AND terminal_result_code IN ('CANCELLED_BY_ISSUER','AUTH_EPOCH_ROTATED','SESSION_REVOKED','ADMIN_DEACTIVATED','CONFIRMATION_MISMATCH','BOUND_ENTITY_STALE','CLOCK_ROLLBACK_DETECTED') "
            "AND cancellation_epoch = 1 AND retention_eligible_at = datetime(terminal_at, '+30 days') || substr(terminal_at,20,7)) OR "
            "(state = 'expired' AND terminal_at IS NOT NULL AND consumed_at IS NULL "
            "AND consumed_request_id IS NULL AND terminal_result_code = 'DEADLINE_EXPIRED' "
            "AND cancellation_epoch = 0 AND retention_eligible_at = datetime(terminal_at, '+30 days') || substr(terminal_at,20,7))",
            name="ck_confirmation_challenges_terminal",
        ),
        Index("ix_confirmation_challenges_session_state", "control_plane_session_id", "state"),
        Index("ix_confirmation_challenges_credential_state", "credential_id", "state"),
        Index("ix_confirmation_challenges_terminal_at", "terminal_at"),
        Index(
            "uq_confirmation_challenges_issued_credential",
            "credential_id",
            unique=True,
            sqlite_where=text("state = 'issued'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    intent_contract_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    purpose: Mapped[ConfirmationPurpose] = mapped_column(
        _enum(ConfirmationPurpose, "confirmation_purpose"), nullable=False
    )
    state: Mapped[ConfirmationChallengeState] = mapped_column(
        _enum(ConfirmationChallengeState, "confirmation_challenge_state"), nullable=False
    )
    admin_user_id: Mapped[str] = mapped_column(String(40), nullable=False)
    control_plane_session_id: Mapped[str] = mapped_column(String(40), nullable=False)
    auth_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    recent_authenticated_at: Mapped[datetime] = mapped_column(UTC6DateTime(), nullable=False)
    issue_request_id: Mapped[str] = mapped_column(String(72), nullable=False)
    runtime_installation_id: Mapped[str] = mapped_column(String(40), nullable=False)
    runtime_installation_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    runtime_type: Mapped[RuntimeType] = mapped_column(
        _enum(RuntimeType, "confirmation_runtime_type"), nullable=False
    )
    provider_id: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_state: Mapped[ProviderLifecycleState] = mapped_column(
        _enum(ProviderLifecycleState, "confirmation_provider_state"), nullable=False
    )
    credential_id: Mapped[str] = mapped_column(String(40), nullable=False)
    credential_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    credential_kind: Mapped[CredentialKind] = mapped_column(
        _enum(CredentialKind, "confirmation_credential_kind"), nullable=False
    )
    credential_state: Mapped[CredentialLifecycleState] = mapped_column(
        _enum(CredentialLifecycleState, "confirmation_credential_state"), nullable=False
    )
    expected_runtime_secret_ref: Mapped[str | None] = mapped_column(String(40))
    expected_secret_version: Mapped[int | None] = mapped_column(Integer)
    credential_runtime_installation_id: Mapped[str] = mapped_column(String(40), nullable=False)
    intended_state: Mapped[CredentialLifecycleState] = mapped_column(
        _enum(CredentialLifecycleState, "confirmation_intended_state"), nullable=False
    )
    intended_secret_version: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmation_verifier: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    provisioning_intent_id: Mapped[str] = mapped_column(String(40), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(UTC6DateTime(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC6DateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTC6DateTime(), nullable=False)
    intent_issued_at: Mapped[datetime] = mapped_column(UTC6DateTime(), nullable=False)
    intent_expires_at: Mapped[datetime] = mapped_column(UTC6DateTime(), nullable=False)
    initial_cancellation_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_observed_at: Mapped[datetime] = mapped_column(UTC6DateTime(), nullable=False)
    cancellation_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    terminal_at: Mapped[datetime | None] = mapped_column(UTC6DateTime())
    consumed_at: Mapped[datetime | None] = mapped_column(UTC6DateTime())
    consumed_request_id: Mapped[str | None] = mapped_column(String(72))
    terminal_result_code: Mapped[ChallengeTerminalResultCode | None] = mapped_column(
        _enum(ChallengeTerminalResultCode, "challenge_terminal_result_code")
    )
    retention_eligible_at: Mapped[datetime | None] = mapped_column(UTC6DateTime())


class ProviderSecretProvisioningAttempt(Base):
    __tablename__ = "provider_secret_provisioning_attempts"
    __table_args__ = (
        UniqueConstraint("challenge_id", name="uq_provider_secret_attempts_challenge"),
        UniqueConstraint("provisioning_intent_id", name="uq_provider_secret_attempts_intent"),
        ForeignKeyConstraint(
            ["challenge_id", "provisioning_intent_id"],
            ["confirmation_challenges.id", "confirmation_challenges.provisioning_intent_id"],
            ondelete="RESTRICT",
            name="fk_provider_secret_attempts_challenge_intent",
        ),
        ForeignKeyConstraint(
            ["control_plane_session_id", "admin_user_id"],
            ["sessions.id", "sessions.user_id"],
            ondelete="RESTRICT",
            name="fk_provider_secret_attempts_session_admin",
        ),
        ForeignKeyConstraint(
            ["runtime_installation_id"],
            ["runtime_installations.id"],
            ondelete="RESTRICT",
            name="fk_provider_secret_attempts_runtime_installation",
        ),
        ForeignKeyConstraint(
            ["provider_id"],
            ["provider_definitions.id"],
            ondelete="RESTRICT",
            name="fk_provider_secret_attempts_provider",
        ),
        ForeignKeyConstraint(
            ["credential_id", "provider_id", "credential_runtime_installation_id"],
            [
                "provider_credentials.id",
                "provider_credentials.provider_id",
                "provider_credentials.runtime_installation_id",
            ],
            ondelete="RESTRICT",
            name="fk_provider_secret_attempts_credential_runtime_identity",
        ),
        CheckConstraint(
            _ID_CHECK.format(column="id", prefix="psa"), name="ck_provider_secret_attempts_id"
        ),
        CheckConstraint(
            _ID_CHECK.format(column="provisioning_intent_id", prefix="psi"),
            name="ck_provider_secret_attempts_intent_id",
        ),
        CheckConstraint(
            "schema_version = 1 AND intent_contract_version = 1 AND auth_epoch >= 1 "
            "AND runtime_installation_revision >= 1 AND provider_revision >= 1 "
            "AND credential_revision >= 1 AND intended_secret_version = 1 "
            "AND initial_cancellation_epoch = 0 AND cancellation_epoch >= 0 "
            "AND authorize_attempt_count BETWEEN 0 AND 3",
            name="ck_provider_secret_attempts_schema",
        ),
        CheckConstraint(
            "expected_runtime_secret_ref IS NULL AND expected_secret_version IS NULL "
            "AND runtime_type = 'codex' AND credential_kind = 'api_key' "
            "AND credential_state = 'missing' AND intended_state = 'configured' "
            "AND provider_state IN ('configured','validated') "
            "AND credential_runtime_installation_id = runtime_installation_id",
            name="ck_provider_secret_attempts_expected_missing",
        ),
        CheckConstraint(
            _HEX64.format(column="approval_digest"), name="ck_provider_secret_attempts_digest"
        ),
        CheckConstraint(
            _REQUEST_ID.format(column="authorization_request_id")
            + " AND (authorize_request_id IS NULL OR ("
            + _REQUEST_ID.format(column="authorize_request_id")
            + ")) AND (cancel_request_id IS NULL OR ("
            + _REQUEST_ID.format(column="cancel_request_id")
            + "))",
            name="ck_provider_secret_attempts_request_ids",
        ),
        CheckConstraint(
            "intent_issued_at < expires_at AND authorized_at >= intent_issued_at "
            "AND authorized_at < expires_at AND created_at = authorized_at "
            "AND updated_at >= created_at AND "
            + " AND ".join(
                _UTC6.format(column=column)
                for column in (
                    "intent_issued_at",
                    "authorized_at",
                    "expires_at",
                    "created_at",
                    "updated_at",
                )
            )
            + " AND "
            + " AND ".join(
                f"({column} IS NULL OR ({_UTC6.format(column=column)}))"
                for column in (
                    "authorize_requested_at",
                    "runtime_staged_at",
                    "runtime_consuming_at",
                    "runtime_committed_at",
                    "runtime_commit_observed_at",
                    "runtime_verified_at",
                    "reconciled_at",
                    "terminal_at",
                    "cancel_requested_at",
                    "retention_eligible_at",
                )
            )
            + " AND "
            + " AND ".join(
                f"({column} IS NULL OR ({column} >= authorized_at AND {column} <= updated_at))"
                for column in (
                    "authorize_requested_at",
                    "runtime_staged_at",
                    "runtime_consuming_at",
                    "runtime_committed_at",
                    "runtime_commit_observed_at",
                    "runtime_verified_at",
                    "reconciled_at",
                    "terminal_at",
                    "cancel_requested_at",
                )
            ),
            name="ck_provider_secret_attempts_timestamps",
        ),
        CheckConstraint(
            attempt_state_consistency_sql(),
            name="ck_provider_secret_attempts_state_timestamps",
        ),
        Index(
            "uq_provider_secret_attempts_unresolved_credential",
            "credential_id",
            unique=True,
            sqlite_where=text(
                "state IN ('authorized','authorize_pending','runtime_staged','cancel_pending','runtime_consuming','runtime_committed_unverified','runtime_verified','needs_attention')"
            ),
        ),
        Index("ix_provider_secret_attempts_state_updated", "state", "updated_at"),
        Index("ix_provider_secret_attempts_terminal_at", "terminal_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    intent_contract_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    purpose: Mapped[ConfirmationPurpose] = mapped_column(
        _enum(ConfirmationPurpose, "attempt_purpose"), nullable=False
    )
    state: Mapped[ProviderSecretProvisioningAttemptState] = mapped_column(
        _enum(ProviderSecretProvisioningAttemptState, "provider_secret_attempt_state"),
        nullable=False,
    )
    challenge_id: Mapped[str] = mapped_column(String(40), nullable=False)
    provisioning_intent_id: Mapped[str] = mapped_column(String(40), nullable=False)
    authorization_request_id: Mapped[str] = mapped_column(String(72), nullable=False)
    admin_user_id: Mapped[str] = mapped_column(String(40), nullable=False)
    control_plane_session_id: Mapped[str] = mapped_column(String(40), nullable=False)
    auth_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    runtime_installation_id: Mapped[str] = mapped_column(String(40), nullable=False)
    runtime_installation_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    runtime_type: Mapped[RuntimeType] = mapped_column(
        _enum(RuntimeType, "attempt_runtime_type"), nullable=False
    )
    provider_id: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_state: Mapped[ProviderLifecycleState] = mapped_column(
        _enum(ProviderLifecycleState, "attempt_provider_state"), nullable=False
    )
    credential_id: Mapped[str] = mapped_column(String(40), nullable=False)
    credential_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    credential_kind: Mapped[CredentialKind] = mapped_column(
        _enum(CredentialKind, "attempt_credential_kind"), nullable=False
    )
    credential_state: Mapped[CredentialLifecycleState] = mapped_column(
        _enum(CredentialLifecycleState, "attempt_credential_state"), nullable=False
    )
    credential_runtime_installation_id: Mapped[str] = mapped_column(String(40), nullable=False)
    expected_runtime_secret_ref: Mapped[str | None] = mapped_column(String(40))
    expected_secret_version: Mapped[int | None] = mapped_column(Integer)
    intended_state: Mapped[CredentialLifecycleState] = mapped_column(
        _enum(CredentialLifecycleState, "attempt_intended_state"), nullable=False
    )
    intended_secret_version: Mapped[int] = mapped_column(Integer, nullable=False)
    approval_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    intent_issued_at: Mapped[datetime] = mapped_column(UTC6DateTime(), nullable=False)
    authorized_at: Mapped[datetime] = mapped_column(UTC6DateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTC6DateTime(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC6DateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTC6DateTime(), nullable=False)
    authorize_requested_at: Mapped[datetime | None] = mapped_column(UTC6DateTime())
    authorize_request_id: Mapped[str | None] = mapped_column(String(72))
    authorize_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    authorize_last_result_code: Mapped[AuthorizeResultCode] = mapped_column(
        _enum(AuthorizeResultCode, "authorize_result_code"), nullable=False
    )
    runtime_staged_at: Mapped[datetime | None] = mapped_column(UTC6DateTime())
    runtime_consuming_at: Mapped[datetime | None] = mapped_column(UTC6DateTime())
    runtime_committed_at: Mapped[datetime | None] = mapped_column(UTC6DateTime())
    runtime_commit_observed_at: Mapped[datetime | None] = mapped_column(UTC6DateTime())
    runtime_verified_at: Mapped[datetime | None] = mapped_column(UTC6DateTime())
    reconciled_at: Mapped[datetime | None] = mapped_column(UTC6DateTime())
    terminal_at: Mapped[datetime | None] = mapped_column(UTC6DateTime())
    initial_cancellation_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancellation_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(UTC6DateTime())
    cancel_request_id: Mapped[str | None] = mapped_column(String(72))
    cancellation_result_code: Mapped[CancellationResultCode] = mapped_column(
        _enum(CancellationResultCode, "cancellation_result_code"), nullable=False
    )
    runtime_attestation_code: Mapped[RuntimeAttestationResultCode | None] = mapped_column(
        _enum(RuntimeAttestationResultCode, "runtime_attestation_result_code")
    )
    terminal_result_code: Mapped[AttemptTerminalResultCode | None] = mapped_column(
        _enum(AttemptTerminalResultCode, "attempt_terminal_result_code")
    )
    retention_eligible_at: Mapped[datetime | None] = mapped_column(UTC6DateTime())
