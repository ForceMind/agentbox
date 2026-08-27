"""Add Runtime ownership and durable Control Plane approval authority.

Revision ID: 0005_phase11_control_plane_ownership_approval
Revises: 0004_phase11_provider_core
"""

# ruff: noqa: E501, SIM905 -- exact SQLite contracts are kept as auditable SQL literals.

from __future__ import annotations

from agentbox_core.approval_schema_v1 import (
    ConfirmationChallenge,
    ProviderSecretProvisioningAttempt,
    attempt_state_consistency_sql,
)
from alembic import context, op
from sqlalchemy import text
from sqlalchemy.schema import CreateIndex, CreateTable

revision = "0005_phase11_control_plane_ownership_approval"
down_revision = "0004_phase11_provider_core"
branch_labels = None
depends_on = None


def _scalar(sql: str) -> int:
    return int(op.get_bind().exec_driver_sql(sql).scalar_one())


def _preflight_sessions() -> int:
    count = _scalar("SELECT COUNT(*) FROM sessions")
    invalid_required_timestamps = " OR ".join(
        _invalid_source_datetime(f"s.{column}")
        for column in ("created_at", "last_seen_at", "idle_expires_at", "expires_at")
    )
    invalid_revoked_at = _invalid_source_datetime("s.revoked_at")
    invalid = _scalar(
        "SELECT COUNT(*) FROM sessions s WHERE "
        "length(s.id)<>36 OR substr(s.id,1,4)<>'ses_' OR substr(s.id,5) GLOB '*[^0-9a-f]*' "
        "OR length(s.user_id)<>36 OR substr(s.user_id,1,4)<>'adm_' OR substr(s.user_id,5) GLOB '*[^0-9a-f]*' "
        "OR length(s.token_hash)<>64 OR s.token_hash GLOB '*[^0-9a-f]*' "
        "OR length(s.csrf_hash)<>64 OR s.csrf_hash GLOB '*[^0-9a-f]*' "
        f"OR ({invalid_required_timestamps}) "
        f"OR (s.revoked_at IS NOT NULL AND ({invalid_revoked_at})) "
        "OR s.created_at>s.last_seen_at OR s.created_at>s.idle_expires_at OR s.created_at>s.expires_at "
        "OR NOT EXISTS (SELECT 1 FROM admin_users a WHERE a.id=s.user_id)"
    )
    if invalid:
        raise RuntimeError("PHASE11_0005_SESSION_PREFLIGHT_FAILED")
    return count


def _trigger(name: str) -> str:
    value = (
        op.get_bind()
        .execute(
            text("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=:name"),
            {"name": name},
        )
        .scalar_one_or_none()
    )
    if not value:
        raise RuntimeError(f"PHASE11_0005_SOURCE_TRIGGER_MISSING:{name}")
    return str(value)


def _create_model_table(table: object) -> None:
    bind = op.get_bind()
    bind.execute(CreateTable(table))
    for index in table.indexes:
        bind.execute(CreateIndex(index))


def _profile_triggers_for_owner() -> tuple[str, str]:
    valid = _trigger("trg_runtime_profiles_valid_snapshot")
    immutable = _trigger("trg_runtime_profiles_immutable_snapshot")
    needle = "AND credential.provider_id = NEW.provider_id "
    if valid.count(needle) != 1:
        raise RuntimeError("PHASE11_0005_SOURCE_PROFILE_TRIGGER_INVALID")
    valid = valid.replace(
        needle,
        needle + "AND credential.runtime_installation_id = NEW.runtime_installation_id ",
    )
    return valid, immutable


def _create_credentials() -> None:
    op.execute(
        "CREATE TABLE provider_credentials_new ("
        "id VARCHAR(40) NOT NULL PRIMARY KEY, provider_id VARCHAR(40) NOT NULL, "
        "runtime_installation_id VARCHAR(40) NOT NULL, kind VARCHAR(7) NOT NULL, "
        "runtime_secret_ref VARCHAR(40), secret_version INTEGER, state VARCHAR(15) NOT NULL, "
        "revision INTEGER NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, "
        "CONSTRAINT ck_provider_credentials_revision CHECK (revision >= 1), "
        "CONSTRAINT ck_provider_credentials_state_reference CHECK ((state = 'missing' AND runtime_secret_ref IS NULL AND secret_version IS NULL) OR (state IN ('configured','rotating','revoked','needs_attention') AND runtime_secret_ref IS NOT NULL AND secret_version IS NOT NULL AND secret_version >= 1)), "
        "CONSTRAINT ck_provider_credentials_secret_reference_format CHECK (runtime_secret_ref IS NULL OR (length(runtime_secret_ref)=36 AND substr(runtime_secret_ref,1,4)='sec_' AND substr(runtime_secret_ref,5) NOT GLOB '*[^0-9a-f]*')), "
        "CONSTRAINT fk_provider_credentials_runtime_installation FOREIGN KEY(runtime_installation_id) REFERENCES runtime_installations(id) ON DELETE RESTRICT, "
        "FOREIGN KEY(provider_id) REFERENCES provider_definitions(id) ON DELETE RESTRICT, "
        "CONSTRAINT uq_provider_credentials_id_provider UNIQUE(id,provider_id), "
        "CONSTRAINT uq_provider_credentials_runtime_identity UNIQUE(id,provider_id,runtime_installation_id), "
        "CONSTRAINT uq_provider_credentials_provider_runtime_kind UNIQUE(provider_id,runtime_installation_id,kind), "
        "CONSTRAINT provider_credential_kind CHECK (kind IN ('api_key')), "
        "CONSTRAINT provider_credential_state CHECK (state IN ('missing','configured','rotating','revoked','needs_attention')))"
    )
    op.execute(
        "INSERT INTO provider_credentials_new SELECT id,provider_id,NULL,kind,runtime_secret_ref,secret_version,state,revision,created_at,updated_at FROM provider_credentials WHERE 0"
    )
    op.execute("DROP TABLE provider_credentials")
    op.execute("ALTER TABLE provider_credentials_new RENAME TO provider_credentials")
    op.execute(
        "CREATE INDEX ix_provider_credentials_runtime_installation_id ON provider_credentials(runtime_installation_id)"
    )
    op.execute(
        "CREATE TRIGGER trg_provider_credentials_identity_immutable BEFORE UPDATE ON provider_credentials "
        "WHEN NEW.id IS NOT OLD.id OR NEW.provider_id IS NOT OLD.provider_id OR NEW.runtime_installation_id IS NOT OLD.runtime_installation_id OR NEW.kind IS NOT OLD.kind OR NEW.created_at IS NOT OLD.created_at "
        "BEGIN SELECT RAISE(ABORT,'credential identity is immutable'); END"
    )


def _create_profiles(valid_trigger: str, immutable_trigger: str) -> None:
    op.execute(
        "CREATE TABLE runtime_provider_profiles_new ("
        "id VARCHAR(40) NOT NULL PRIMARY KEY, runtime_installation_id VARCHAR(40) NOT NULL, provider_id VARCHAR(40) NOT NULL, provider_revision INTEGER NOT NULL, "
        "credential_id VARCHAR(40), credential_revision INTEGER, credential_secret_version INTEGER, adapter_type VARCHAR(5) NOT NULL, adapter_schema_version INTEGER NOT NULL, "
        "state VARCHAR(15) NOT NULL, revision INTEGER NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, "
        "CONSTRAINT ck_runtime_profiles_provider_revision CHECK(provider_revision>=1), CONSTRAINT ck_runtime_profiles_adapter_schema CHECK(adapter_schema_version>=1), "
        "CONSTRAINT ck_runtime_profiles_revision CHECK(revision>=1), CONSTRAINT ck_runtime_profiles_credential_reference CHECK ((credential_id IS NULL AND credential_revision IS NULL AND credential_secret_version IS NULL) OR (credential_id IS NOT NULL AND credential_revision IS NOT NULL AND credential_revision>=1 AND credential_secret_version IS NOT NULL AND credential_secret_version>=1)), "
        "FOREIGN KEY(provider_id) REFERENCES provider_definitions(id) ON DELETE RESTRICT, "
        "CONSTRAINT fk_runtime_profiles_installation_adapter FOREIGN KEY(runtime_installation_id,adapter_type) REFERENCES runtime_installations(id,runtime_type) ON DELETE RESTRICT, "
        "CONSTRAINT fk_runtime_profiles_credential_runtime_identity FOREIGN KEY(credential_id,provider_id,runtime_installation_id) REFERENCES provider_credentials(id,provider_id,runtime_installation_id) ON DELETE RESTRICT, "
        "CONSTRAINT uq_runtime_provider_profiles_identity UNIQUE(id,runtime_installation_id,provider_id), "
        "CONSTRAINT runtime_profile_adapter_type CHECK(adapter_type IN ('codex')), "
        "CONSTRAINT runtime_profile_state CHECK(state IN ('draft','valid','superseded','incompatible','needs_attention')))"
    )
    op.execute("INSERT INTO runtime_provider_profiles_new SELECT * FROM runtime_provider_profiles")
    op.execute("DROP TABLE runtime_provider_profiles")
    op.execute("ALTER TABLE runtime_provider_profiles_new RENAME TO runtime_provider_profiles")
    op.execute(valid_trigger)
    op.execute(immutable_trigger)


def _utc6(column: str) -> str:
    return f"CASE WHEN length({column})=26 THEN {column} ELSE strftime('%Y-%m-%d %H:%M:%f',{column}) || '000' END"


def _utc6_constraint(column: str) -> str:
    pattern = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]"
    return f"length({column})=26 AND {column} GLOB '{pattern}' AND {_utc6_calendar(column)}"


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


def _invalid_source_datetime(column: str) -> str:
    raw_seconds = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]"
    raw_microseconds = raw_seconds + ".[0-9][0-9][0-9][0-9][0-9][0-9]"
    return (
        f"typeof({column})<>'text' OR NOT ((length({column})=19 AND {column} GLOB "
        f"'{raw_seconds}') OR (length({column})=26 AND {column} GLOB '{raw_microseconds}')) "
        f"OR NOT ({_utc6_calendar(column)})"
    )


def _clock_invalid() -> str:
    pattern = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]"
    return (
        "NOT (typeof(agentbox_now_utc6())='text' "
        "AND length(agentbox_now_utc6())=26 "
        f"AND agentbox_now_utc6() GLOB '{pattern}' "
        f"AND {_utc6_calendar('agentbox_now_utc6()')})"
    )


def _create_sessions() -> None:
    timestamp_check = (
        " AND ".join(
            _utc6_constraint(column)
            for column in (
                "created_at",
                "recent_authenticated_at",
                "last_seen_at",
                "idle_expires_at",
                "expires_at",
            )
        )
        + " AND (revoked_at IS NULL OR ("
        + _utc6_constraint("revoked_at")
        + "))"
    )
    op.execute(
        "CREATE TABLE sessions_new (id VARCHAR(40) NOT NULL PRIMARY KEY, user_id VARCHAR(40) NOT NULL, token_hash VARCHAR(64) NOT NULL UNIQUE, csrf_hash VARCHAR(64) NOT NULL, "
        "created_at DATETIME NOT NULL, recent_authenticated_at DATETIME NOT NULL, auth_epoch INTEGER NOT NULL DEFAULT 1, last_seen_at DATETIME NOT NULL, idle_expires_at DATETIME NOT NULL, expires_at DATETIME NOT NULL, revoked_at DATETIME, client_label VARCHAR(80), "
        "FOREIGN KEY(user_id) REFERENCES admin_users(id) ON DELETE CASCADE, CONSTRAINT uq_sessions_id_user UNIQUE(id,user_id), "
        "CONSTRAINT ck_sessions_auth_epoch CHECK(auth_epoch>=1), CONSTRAINT ck_sessions_recent_auth_bounds CHECK(recent_authenticated_at>=created_at AND recent_authenticated_at<=last_seen_at), "
        "CONSTRAINT ck_sessions_utc6 CHECK(" + timestamp_check + "))"
    )
    op.execute(
        "INSERT INTO sessions_new SELECT id,user_id,token_hash,csrf_hash,"
        + _utc6("created_at")
        + ","
        + _utc6("created_at")
        + ",1,"
        + _utc6("last_seen_at")
        + ","
        + _utc6("idle_expires_at")
        + ","
        + _utc6("expires_at")
        + ",CASE WHEN revoked_at IS NULL THEN NULL ELSE "
        + _utc6("revoked_at")
        + " END,client_label FROM sessions"
    )
    op.execute("DROP TABLE sessions")
    op.execute("ALTER TABLE sessions_new RENAME TO sessions")
    op.execute("CREATE INDEX ix_sessions_expires_at ON sessions(expires_at)")
    op.execute("CREATE INDEX ix_sessions_revoked_at ON sessions(revoked_at)")
    op.execute("CREATE INDEX ix_sessions_user_id ON sessions(user_id)")


def _create_approval_triggers() -> None:
    immutable_challenge = (
        "id schema_version intent_contract_version purpose admin_user_id control_plane_session_id auth_epoch recent_authenticated_at issue_request_id runtime_installation_id runtime_installation_revision runtime_type provider_id provider_revision provider_state credential_id credential_revision credential_kind credential_state expected_runtime_secret_ref expected_secret_version credential_runtime_installation_id intended_state intended_secret_version confirmation_verifier approval_digest provisioning_intent_id issued_at created_at expires_at intent_issued_at intent_expires_at initial_cancellation_epoch"
    ).split()
    op.execute(
        "CREATE TRIGGER trg_confirmation_challenges_binding_immutable BEFORE UPDATE ON confirmation_challenges WHEN "
        + " OR ".join(f"NEW.{column} IS NOT OLD.{column}" for column in immutable_challenge)
        + " OR (OLD.state<>'issued' AND NEW.retention_eligible_at IS NOT OLD.retention_eligible_at) BEGIN SELECT RAISE(ABORT,'confirmation challenge binding is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_confirmation_challenges_legal_transition BEFORE UPDATE ON confirmation_challenges WHEN "
        + _clock_invalid()
        + " OR NOT (OLD.state='issued' AND NEW.state IN ('issued','consumed','cancelled','expired')) "
        "OR NEW.last_observed_at<OLD.last_observed_at "
        "OR (NEW.last_observed_at>agentbox_now_utc6() AND NOT (NEW.state='cancelled' AND NEW.terminal_result_code='CLOCK_ROLLBACK_DETECTED' AND NEW.last_observed_at=OLD.last_observed_at AND NEW.terminal_at=OLD.last_observed_at)) "
        "OR (agentbox_now_utc6()<OLD.last_observed_at AND NOT (NEW.state='cancelled' AND NEW.terminal_result_code='CLOCK_ROLLBACK_DETECTED' AND NEW.last_observed_at=OLD.last_observed_at AND NEW.terminal_at=OLD.last_observed_at)) "
        "OR (NEW.state='issued' AND (agentbox_now_utc6()>=OLD.expires_at OR NEW.last_observed_at IS NOT agentbox_now_utc6())) "
        "OR (NEW.state='consumed' AND (agentbox_now_utc6()>=OLD.expires_at OR NEW.last_observed_at IS NOT agentbox_now_utc6())) "
        "OR (NEW.state='cancelled' AND NEW.terminal_result_code<>'CLOCK_ROLLBACK_DETECTED' AND NEW.last_observed_at IS NOT agentbox_now_utc6()) "
        "OR (NEW.state='expired' AND (agentbox_now_utc6()<OLD.expires_at OR NEW.last_observed_at IS NOT agentbox_now_utc6())) "
        "BEGIN SELECT RAISE(ABORT,'illegal confirmation challenge transition'); END"
    )
    copied = (
        "schema_version intent_contract_version purpose provisioning_intent_id admin_user_id control_plane_session_id auth_epoch runtime_installation_id runtime_installation_revision runtime_type provider_id provider_revision provider_state credential_id credential_revision credential_kind credential_state credential_runtime_installation_id expected_runtime_secret_ref expected_secret_version intended_state intended_secret_version approval_digest intent_issued_at expires_at initial_cancellation_epoch"
    ).split()
    reverse_comparisons = " AND ".join(f"a.{column} IS OLD.{column}" for column in copied)
    op.execute(
        "CREATE TRIGGER trg_confirmation_challenges_consumed_attempt BEFORE UPDATE OF state ON confirmation_challenges WHEN OLD.state='issued' AND NEW.state='consumed' AND NOT EXISTS (SELECT 1 FROM provider_secret_provisioning_attempts a WHERE a.challenge_id=OLD.id AND a.state='authorized' AND "
        + reverse_comparisons
        + " AND a.authorization_request_id IS NEW.consumed_request_id AND a.authorized_at IS NEW.consumed_at AND a.authorized_at IS NEW.terminal_at AND a.authorized_at IS NEW.last_observed_at) BEGIN SELECT RAISE(ABORT,'consumed challenge requires exact attempt'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_confirmation_challenges_unresolved_attempt_guard BEFORE INSERT ON confirmation_challenges WHEN EXISTS (SELECT 1 FROM provider_secret_provisioning_attempts a WHERE a.credential_id=NEW.credential_id AND a.state IN ('authorized','authorize_pending','runtime_staged','cancel_pending','runtime_consuming','runtime_committed_unverified','runtime_verified','needs_attention')) BEGIN SELECT RAISE(ABORT,'credential has unresolved provisioning attempt'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_confirmation_challenges_delete_guard BEFORE DELETE ON confirmation_challenges WHEN "
        + _clock_invalid()
        + " OR OLD.state='issued' OR EXISTS (SELECT 1 FROM provider_secret_provisioning_attempts a WHERE a.challenge_id=OLD.id) "
        "OR OLD.retention_eligible_at IS NULL OR OLD.terminal_at IS NULL "
        "OR OLD.retention_eligible_at IS NOT datetime(OLD.terminal_at,'+30 days')||substr(OLD.terminal_at,20,7) "
        "OR NOT ((OLD.state='consumed' AND OLD.consumed_at IS OLD.terminal_at AND OLD.consumed_request_id IS NOT NULL AND OLD.terminal_result_code='ATTEMPT_CREATED' AND OLD.cancellation_epoch=0) "
        "OR (OLD.state='cancelled' AND OLD.consumed_at IS NULL AND OLD.consumed_request_id IS NULL AND OLD.terminal_result_code IN ('CANCELLED_BY_ISSUER','AUTH_EPOCH_ROTATED','SESSION_REVOKED','ADMIN_DEACTIVATED','CONFIRMATION_MISMATCH','BOUND_ENTITY_STALE','CLOCK_ROLLBACK_DETECTED') AND OLD.cancellation_epoch=1) "
        "OR (OLD.state='expired' AND OLD.consumed_at IS NULL AND OLD.consumed_request_id IS NULL AND OLD.terminal_result_code='DEADLINE_EXPIRED' AND OLD.cancellation_epoch=0)) "
        "OR agentbox_now_utc6()<OLD.last_observed_at OR agentbox_now_utc6()<OLD.retention_eligible_at "
        "BEGIN SELECT RAISE(ABORT,'confirmation challenge is not retention eligible'); END"
    )

    comparisons = " AND ".join(f"c.{column} IS NEW.{column}" for column in copied)
    op.execute(
        "CREATE TRIGGER trg_provider_secret_attempts_insert_matches_challenge BEFORE INSERT ON provider_secret_provisioning_attempts WHEN "
        + _clock_invalid()
        + " OR NEW.authorized_at IS NOT agentbox_now_utc6() OR NEW.updated_at IS NOT agentbox_now_utc6() OR NEW.created_at IS NOT agentbox_now_utc6() OR NEW.state<>'authorized' OR NOT EXISTS (SELECT 1 FROM confirmation_challenges c WHERE c.id=NEW.challenge_id AND c.state='issued' AND "
        + comparisons
        + ") BEGIN SELECT RAISE(ABORT,'provider secret attempt does not match challenge'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_provider_secret_attempts_consume_challenge AFTER INSERT ON provider_secret_provisioning_attempts BEGIN UPDATE confirmation_challenges SET state='consumed',last_observed_at=NEW.authorized_at,terminal_at=NEW.authorized_at,consumed_at=NEW.authorized_at,consumed_request_id=NEW.authorization_request_id,terminal_result_code='ATTEMPT_CREATED',retention_eligible_at=datetime(NEW.authorized_at,'+30 days')||substr(NEW.authorized_at,20,7) WHERE id=NEW.challenge_id AND provisioning_intent_id=NEW.provisioning_intent_id AND approval_digest=NEW.approval_digest AND schema_version=NEW.schema_version AND intent_contract_version=NEW.intent_contract_version AND purpose=NEW.purpose AND admin_user_id=NEW.admin_user_id AND control_plane_session_id=NEW.control_plane_session_id AND auth_epoch=NEW.auth_epoch AND runtime_installation_id=NEW.runtime_installation_id AND runtime_installation_revision=NEW.runtime_installation_revision AND runtime_type=NEW.runtime_type AND provider_id=NEW.provider_id AND provider_revision=NEW.provider_revision AND provider_state=NEW.provider_state AND credential_id=NEW.credential_id AND credential_revision=NEW.credential_revision AND credential_kind=NEW.credential_kind AND credential_state=NEW.credential_state AND credential_runtime_installation_id=NEW.credential_runtime_installation_id AND expected_runtime_secret_ref IS NEW.expected_runtime_secret_ref AND expected_secret_version IS NEW.expected_secret_version AND intended_state=NEW.intended_state AND intended_secret_version=NEW.intended_secret_version AND intent_issued_at=NEW.intent_issued_at AND expires_at=NEW.expires_at AND initial_cancellation_epoch=NEW.initial_cancellation_epoch AND cancellation_epoch=NEW.initial_cancellation_epoch AND state='issued'; SELECT CASE WHEN changes()<>1 THEN RAISE(ABORT,'provider secret challenge consume mismatch') END; END"
    )
    immutable_attempt = (
        "id schema_version intent_contract_version purpose challenge_id provisioning_intent_id authorization_request_id admin_user_id control_plane_session_id auth_epoch runtime_installation_id runtime_installation_revision runtime_type provider_id provider_revision provider_state credential_id credential_revision credential_kind credential_state credential_runtime_installation_id expected_runtime_secret_ref expected_secret_version intended_state intended_secret_version approval_digest intent_issued_at authorized_at expires_at created_at initial_cancellation_epoch"
    ).split()
    op.execute(
        "CREATE TRIGGER trg_provider_secret_attempts_authority_immutable BEFORE UPDATE ON provider_secret_provisioning_attempts WHEN "
        + " OR ".join(f"NEW.{column} IS NOT OLD.{column}" for column in immutable_attempt)
        + " OR (OLD.terminal_at IS NOT NULL AND NEW.retention_eligible_at IS NOT OLD.retention_eligible_at) BEGIN SELECT RAISE(ABORT,'provider secret attempt authority is immutable'); END"
    )
    arrows = "(OLD.state='authorized' AND NEW.state IN ('authorize_pending','cancelled','expired','needs_attention')) OR (OLD.state='authorize_pending' AND NEW.state IN ('runtime_staged','runtime_consuming','runtime_committed_unverified','runtime_verified','cancel_pending','expired','needs_attention')) OR (OLD.state='runtime_staged' AND NEW.state IN ('cancel_pending','runtime_consuming','runtime_committed_unverified','runtime_verified','expired','needs_attention')) OR (OLD.state='cancel_pending' AND NEW.state IN ('cancelled','runtime_consuming','runtime_committed_unverified','runtime_verified','expired','needs_attention')) OR (OLD.state='runtime_consuming' AND NEW.state IN ('runtime_committed_unverified','runtime_verified','needs_attention')) OR (OLD.state='runtime_committed_unverified' AND NEW.state IN ('runtime_verified','needs_attention')) OR (OLD.state='runtime_verified' AND NEW.state IN ('reconciled','needs_attention'))"
    op.execute(
        "CREATE TRIGGER trg_provider_secret_attempts_legal_transition BEFORE UPDATE OF state ON provider_secret_provisioning_attempts WHEN "
        + _clock_invalid()
        + " OR NOT ("
        + arrows
        + ") OR agentbox_now_utc6()<OLD.updated_at OR NEW.updated_at<OLD.updated_at OR NEW.updated_at>agentbox_now_utc6() "
        "OR (OLD.state='authorized' AND NEW.state='cancelled' AND agentbox_now_utc6()>=OLD.expires_at) "
        "OR (OLD.state='authorized' AND NEW.state='expired' AND agentbox_now_utc6()<OLD.expires_at) "
        "BEGIN SELECT RAISE(ABORT,'illegal provider secret attempt transition'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_provider_secret_attempts_transition_consistency BEFORE UPDATE ON provider_secret_provisioning_attempts WHEN "
        + _clock_invalid()
        + " OR agentbox_now_utc6()<OLD.updated_at OR NEW.updated_at IS NOT agentbox_now_utc6() OR NOT ("
        + attempt_state_consistency_sql("NEW.")
        + ") OR (NEW.state=OLD.state AND NOT (OLD.state='authorize_pending' AND ((NEW.authorize_last_result_code='RESEND_PERSISTED' AND OLD.authorize_attempt_count<3 AND NEW.authorize_attempt_count=OLD.authorize_attempt_count+1 AND NEW.authorize_requested_at IS agentbox_now_utc6() AND NEW.authorize_request_id IS NOT OLD.authorize_request_id) OR (NEW.authorize_last_result_code='STATUS_UNAVAILABLE' AND NEW.authorize_attempt_count=OLD.authorize_attempt_count AND NEW.authorize_requested_at IS OLD.authorize_requested_at AND NEW.authorize_request_id IS OLD.authorize_request_id)))) OR (NEW.state='reconciled' AND (OLD.state<>'runtime_verified' OR OLD.runtime_verified_at IS NULL OR OLD.runtime_attestation_code IS NULL)) BEGIN SELECT RAISE(ABORT,'provider secret attempt transition is inconsistent'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_provider_secret_attempts_delete_guard BEFORE DELETE ON provider_secret_provisioning_attempts WHEN "
        + _clock_invalid()
        + " OR OLD.state NOT IN ('reconciled','cancelled','expired') OR NOT ("
        + attempt_state_consistency_sql("OLD.")
        + ") OR OLD.retention_eligible_at IS NULL OR OLD.terminal_at IS NULL OR OLD.retention_eligible_at IS NOT datetime(OLD.terminal_at,'+30 days')||substr(OLD.terminal_at,20,7) OR agentbox_now_utc6()<OLD.updated_at OR agentbox_now_utc6()<OLD.retention_eligible_at BEGIN SELECT RAISE(ABORT,'provider secret attempt is not retention eligible'); END"
    )


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("PHASE11_0005_ONLINE_SQLITE_REQUIRED")
    bind = op.get_bind()
    if bind.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 0 or not bind.in_transaction():
        raise RuntimeError("PHASE11_0005_RUNNER_CONTRACT_REQUIRED")
    legacy_count = _scalar("SELECT COUNT(*) FROM provider_credentials")
    if legacy_count:
        raise RuntimeError("PHASE11_0005_LEGACY_CREDENTIALS_PRESENT")
    session_count = _preflight_sessions()
    profile_count = _scalar("SELECT COUNT(*) FROM runtime_provider_profiles")
    valid_trigger, immutable_trigger = _profile_triggers_for_owner()
    compatibility_trigger = _trigger("trg_compatibility_evidence_valid_scope")
    binding_trigger = _trigger("trg_runtime_bindings_valid_snapshot")
    op.execute("DROP TRIGGER trg_runtime_profiles_valid_snapshot")
    op.execute("DROP TRIGGER trg_runtime_profiles_immutable_snapshot")
    op.execute("DROP TRIGGER trg_compatibility_evidence_valid_scope")
    op.execute("DROP TRIGGER trg_runtime_bindings_valid_snapshot")
    _create_credentials()
    _create_profiles(valid_trigger, immutable_trigger)
    op.execute(compatibility_trigger)
    op.execute(binding_trigger)
    _create_sessions()
    _create_model_table(ConfirmationChallenge.__table__)
    _create_model_table(ProviderSecretProvisioningAttempt.__table__)
    _create_approval_triggers()
    if (
        _scalar("SELECT COUNT(*) FROM provider_credentials") != 0
        or _scalar("SELECT COUNT(*) FROM sessions") != session_count
        or _scalar("SELECT COUNT(*) FROM runtime_provider_profiles") != profile_count
        or _scalar(
            "SELECT COUNT(*) FROM sessions WHERE auth_epoch<>1 OR recent_authenticated_at<>created_at"
        )
    ):
        raise RuntimeError("PHASE11_0005_COPY_VERIFY_FAILED")


def _unsafe_downgrade() -> bool:
    return any(
        (
            _scalar("SELECT COUNT(*) FROM provider_credentials"),
            _scalar("SELECT COUNT(*) FROM confirmation_challenges"),
            _scalar("SELECT COUNT(*) FROM provider_secret_provisioning_attempts"),
            _scalar(
                "SELECT COUNT(*) FROM sessions WHERE auth_epoch<>1 OR recent_authenticated_at<>created_at"
            ),
        )
    )


def downgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("PHASE11_0005_ONLINE_SQLITE_REQUIRED")
    bind = op.get_bind()
    if bind.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 0 or not bind.in_transaction():
        raise RuntimeError("PHASE11_0005_RUNNER_CONTRACT_REQUIRED")
    if _unsafe_downgrade():
        raise RuntimeError("PHASE11_0005_DOWNGRADE_UNSAFE")
    session_count = _scalar("SELECT COUNT(*) FROM sessions")
    profile_count = _scalar("SELECT COUNT(*) FROM runtime_provider_profiles")
    op.execute("DROP TABLE provider_secret_provisioning_attempts")
    op.execute("DROP TABLE confirmation_challenges")
    op.execute(
        "CREATE TABLE sessions_old (id VARCHAR(40) NOT NULL PRIMARY KEY,user_id VARCHAR(40) NOT NULL,token_hash VARCHAR(64) NOT NULL UNIQUE,csrf_hash VARCHAR(64) NOT NULL,created_at DATETIME NOT NULL,last_seen_at DATETIME NOT NULL,idle_expires_at DATETIME NOT NULL,expires_at DATETIME NOT NULL,revoked_at DATETIME,client_label VARCHAR(80),FOREIGN KEY(user_id) REFERENCES admin_users(id) ON DELETE CASCADE)"
    )
    op.execute(
        "INSERT INTO sessions_old SELECT id,user_id,token_hash,csrf_hash,created_at,last_seen_at,idle_expires_at,expires_at,revoked_at,client_label FROM sessions"
    )
    op.execute("DROP TABLE sessions")
    op.execute("ALTER TABLE sessions_old RENAME TO sessions")
    op.execute("CREATE INDEX ix_sessions_expires_at ON sessions(expires_at)")
    op.execute("CREATE INDEX ix_sessions_revoked_at ON sessions(revoked_at)")
    op.execute("CREATE INDEX ix_sessions_user_id ON sessions(user_id)")
    current_valid = _trigger("trg_runtime_profiles_valid_snapshot")
    current_immutable = _trigger("trg_runtime_profiles_immutable_snapshot")
    compatibility_trigger = _trigger("trg_compatibility_evidence_valid_scope")
    binding_trigger = _trigger("trg_runtime_bindings_valid_snapshot")
    op.execute("DROP TRIGGER trg_runtime_profiles_valid_snapshot")
    op.execute("DROP TRIGGER trg_runtime_profiles_immutable_snapshot")
    op.execute("DROP TRIGGER trg_compatibility_evidence_valid_scope")
    op.execute("DROP TRIGGER trg_runtime_bindings_valid_snapshot")
    old_valid = current_valid.replace(
        "AND credential.runtime_installation_id = NEW.runtime_installation_id ", ""
    )
    op.execute(
        "CREATE TABLE runtime_provider_profiles_old (id VARCHAR(40) NOT NULL PRIMARY KEY,runtime_installation_id VARCHAR(40) NOT NULL,provider_id VARCHAR(40) NOT NULL,provider_revision INTEGER NOT NULL,credential_id VARCHAR(40),credential_revision INTEGER,credential_secret_version INTEGER,adapter_type VARCHAR(5) NOT NULL,adapter_schema_version INTEGER NOT NULL,state VARCHAR(15) NOT NULL,revision INTEGER NOT NULL,created_at DATETIME NOT NULL,updated_at DATETIME NOT NULL,CONSTRAINT ck_runtime_profiles_provider_revision CHECK(provider_revision>=1),CONSTRAINT ck_runtime_profiles_adapter_schema CHECK(adapter_schema_version>=1),CONSTRAINT ck_runtime_profiles_revision CHECK(revision>=1),CONSTRAINT ck_runtime_profiles_credential_reference CHECK((credential_id IS NULL AND credential_revision IS NULL AND credential_secret_version IS NULL) OR (credential_id IS NOT NULL AND credential_revision IS NOT NULL AND credential_revision>=1 AND credential_secret_version IS NOT NULL AND credential_secret_version>=1)),FOREIGN KEY(provider_id) REFERENCES provider_definitions(id) ON DELETE RESTRICT,CONSTRAINT fk_runtime_profiles_installation_adapter FOREIGN KEY(runtime_installation_id,adapter_type) REFERENCES runtime_installations(id,runtime_type) ON DELETE RESTRICT,CONSTRAINT fk_runtime_profiles_credential_provider FOREIGN KEY(credential_id,provider_id) REFERENCES provider_credentials(id,provider_id) ON DELETE RESTRICT,CONSTRAINT uq_runtime_provider_profiles_identity UNIQUE(id,runtime_installation_id,provider_id),CONSTRAINT runtime_profile_adapter_type CHECK(adapter_type IN ('codex')),CONSTRAINT runtime_profile_state CHECK(state IN ('draft','valid','superseded','incompatible','needs_attention')))"
    )
    op.execute("INSERT INTO runtime_provider_profiles_old SELECT * FROM runtime_provider_profiles")
    op.execute("DROP TABLE runtime_provider_profiles")
    op.execute("ALTER TABLE runtime_provider_profiles_old RENAME TO runtime_provider_profiles")
    op.execute(
        "CREATE TABLE provider_credentials_old (id VARCHAR(40) NOT NULL PRIMARY KEY,provider_id VARCHAR(40) NOT NULL,kind VARCHAR(7) NOT NULL,runtime_secret_ref VARCHAR(40),secret_version INTEGER,state VARCHAR(15) NOT NULL,revision INTEGER NOT NULL,created_at DATETIME NOT NULL,updated_at DATETIME NOT NULL,CONSTRAINT ck_provider_credentials_revision CHECK(revision>=1),CONSTRAINT ck_provider_credentials_state_reference CHECK((state='missing' AND runtime_secret_ref IS NULL AND secret_version IS NULL) OR (state IN ('configured','rotating','revoked','needs_attention') AND runtime_secret_ref IS NOT NULL AND secret_version IS NOT NULL AND secret_version>=1)),CONSTRAINT ck_provider_credentials_secret_reference_format CHECK(runtime_secret_ref IS NULL OR (length(runtime_secret_ref)=36 AND substr(runtime_secret_ref,1,4)='sec_' AND substr(runtime_secret_ref,5) NOT GLOB '*[^0-9a-f]*')),FOREIGN KEY(provider_id) REFERENCES provider_definitions(id) ON DELETE RESTRICT,CONSTRAINT uq_provider_credentials_id_provider UNIQUE(id,provider_id),CONSTRAINT uq_provider_credentials_provider UNIQUE(provider_id),CONSTRAINT provider_credential_kind CHECK(kind IN ('api_key')),CONSTRAINT provider_credential_state CHECK(state IN ('missing','configured','rotating','revoked','needs_attention')))"
    )
    op.execute("DROP TABLE provider_credentials")
    op.execute("ALTER TABLE provider_credentials_old RENAME TO provider_credentials")
    op.execute(old_valid)
    op.execute(current_immutable)
    op.execute(compatibility_trigger)
    op.execute(binding_trigger)
    if (
        _scalar("SELECT COUNT(*) FROM provider_credentials") != 0
        or _scalar("SELECT COUNT(*) FROM sessions") != session_count
        or _scalar("SELECT COUNT(*) FROM runtime_provider_profiles") != profile_count
    ):
        raise RuntimeError("PHASE11_0005_COPY_VERIFY_FAILED")
