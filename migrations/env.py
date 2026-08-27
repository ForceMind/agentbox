"""Alembic environment for the AgentBox control-plane database."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from logging.config import fileConfig
from pathlib import Path

import agentbox_core.approval_models  # noqa: F401 -- registers Slice 3.2a metadata
import agentbox_core.provider_models  # noqa: F401 -- registers Phase 11 metadata
from agentbox_core.models import Base
from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection, make_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_PHASE11_HEAD = "0005_phase11_control_plane_ownership_approval"
_PHASE11_TABLES = {"confirmation_challenges", "provider_secret_provisioning_attempts"}
_PHASE11_TRIGGERS = {
    "trg_confirmation_challenges_binding_immutable",
    "trg_confirmation_challenges_legal_transition",
    "trg_confirmation_challenges_consumed_attempt",
    "trg_confirmation_challenges_unresolved_attempt_guard",
    "trg_confirmation_challenges_delete_guard",
    "trg_provider_secret_attempts_insert_matches_challenge",
    "trg_provider_secret_attempts_consume_challenge",
    "trg_provider_secret_attempts_authority_immutable",
    "trg_provider_secret_attempts_legal_transition",
    "trg_provider_secret_attempts_transition_consistency",
    "trg_provider_secret_attempts_delete_guard",
}
_PHASE11_SOURCE_TRIGGERS = {
    "trg_runtime_profiles_valid_snapshot",
    "trg_runtime_profiles_immutable_snapshot",
    "trg_compatibility_evidence_valid_scope",
    "trg_runtime_bindings_valid_snapshot",
}
_PHASE11_COLUMNS = {
    "provider_credentials": {
        "id",
        "provider_id",
        "runtime_installation_id",
        "kind",
        "runtime_secret_ref",
        "secret_version",
        "state",
        "revision",
        "created_at",
        "updated_at",
    },
    "runtime_provider_profiles": {
        "id",
        "runtime_installation_id",
        "provider_id",
        "provider_revision",
        "credential_id",
        "credential_revision",
        "credential_secret_version",
        "adapter_type",
        "adapter_schema_version",
        "state",
        "revision",
        "created_at",
        "updated_at",
    },
    "sessions": {
        "id",
        "user_id",
        "token_hash",
        "csrf_hash",
        "created_at",
        "recent_authenticated_at",
        "auth_epoch",
        "last_seen_at",
        "idle_expires_at",
        "expires_at",
        "revoked_at",
        "client_label",
    },
    "confirmation_challenges": {
        "id",
        "schema_version",
        "intent_contract_version",
        "purpose",
        "state",
        "admin_user_id",
        "control_plane_session_id",
        "auth_epoch",
        "recent_authenticated_at",
        "issue_request_id",
        "runtime_installation_id",
        "runtime_installation_revision",
        "runtime_type",
        "provider_id",
        "provider_revision",
        "provider_state",
        "credential_id",
        "credential_revision",
        "credential_kind",
        "credential_state",
        "expected_runtime_secret_ref",
        "expected_secret_version",
        "credential_runtime_installation_id",
        "intended_state",
        "intended_secret_version",
        "confirmation_verifier",
        "approval_digest",
        "provisioning_intent_id",
        "issued_at",
        "created_at",
        "expires_at",
        "intent_issued_at",
        "intent_expires_at",
        "initial_cancellation_epoch",
        "last_observed_at",
        "cancellation_epoch",
        "terminal_at",
        "consumed_at",
        "consumed_request_id",
        "terminal_result_code",
        "retention_eligible_at",
    },
    "provider_secret_provisioning_attempts": {
        "id",
        "schema_version",
        "intent_contract_version",
        "purpose",
        "state",
        "challenge_id",
        "provisioning_intent_id",
        "authorization_request_id",
        "admin_user_id",
        "control_plane_session_id",
        "auth_epoch",
        "runtime_installation_id",
        "runtime_installation_revision",
        "runtime_type",
        "provider_id",
        "provider_revision",
        "provider_state",
        "credential_id",
        "credential_revision",
        "credential_kind",
        "credential_state",
        "credential_runtime_installation_id",
        "expected_runtime_secret_ref",
        "expected_secret_version",
        "intended_state",
        "intended_secret_version",
        "approval_digest",
        "intent_issued_at",
        "authorized_at",
        "expires_at",
        "created_at",
        "updated_at",
        "authorize_requested_at",
        "authorize_request_id",
        "authorize_attempt_count",
        "authorize_last_result_code",
        "runtime_staged_at",
        "runtime_consuming_at",
        "runtime_committed_at",
        "runtime_commit_observed_at",
        "runtime_verified_at",
        "reconciled_at",
        "terminal_at",
        "initial_cancellation_epoch",
        "cancellation_epoch",
        "cancel_requested_at",
        "cancel_request_id",
        "cancellation_result_code",
        "runtime_attestation_code",
        "terminal_result_code",
        "retention_eligible_at",
    },
}


def _columns(connection: Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")}


def _invalid_source_datetime(column: str) -> str:
    raw_seconds = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]"
    raw_microseconds = raw_seconds + ".[0-9][0-9][0-9][0-9][0-9][0-9]"
    year = f"CAST(substr({column},1,4) AS INTEGER)"
    month = f"CAST(substr({column},6,2) AS INTEGER)"
    day = f"CAST(substr({column},9,2) AS INTEGER)"
    max_day = (
        f"CASE WHEN {month} IN (1,3,5,7,8,10,12) THEN 31 "
        f"WHEN {month} IN (4,6,9,11) THEN 30 WHEN {month}=2 THEN "
        f"CASE WHEN ({year}%4=0 AND ({year}%100<>0 OR {year}%400=0)) THEN 29 ELSE 28 END "
        "ELSE 0 END"
    )
    valid_calendar = (
        f"{year} BETWEEN 1 AND 9999 AND {month} BETWEEN 1 AND 12 "
        f"AND {day} BETWEEN 1 AND ({max_day}) "
        f"AND CAST(substr({column},12,2) AS INTEGER) BETWEEN 0 AND 23 "
        f"AND CAST(substr({column},15,2) AS INTEGER) BETWEEN 0 AND 59 "
        f"AND CAST(substr({column},18,2) AS INTEGER) BETWEEN 0 AND 59"
    )
    return (
        f"typeof({column})<>'text' OR NOT ((length({column})=19 AND {column} GLOB "
        f"'{raw_seconds}') OR (length({column})=26 AND {column} GLOB '{raw_microseconds}')) "
        f"OR NOT ({valid_calendar})"
    )


def _phase_a_phase11_preflight(connection: Connection) -> None:
    """Fail before FK disable when an existing 0004 database cannot enter 0005."""
    destination = context.get_revision_argument()
    destinations = {destination} if isinstance(destination, str) else set(destination or ())
    if not destinations.intersection({"head", _PHASE11_HEAD}):
        return
    has_version_table = connection.exec_driver_sql(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='alembic_version'"
    ).scalar_one()
    if not has_version_table:
        return
    versions = tuple(
        row[0] for row in connection.exec_driver_sql("SELECT version_num FROM alembic_version")
    )
    if versions != ("0004_phase11_provider_core",):
        return
    required_tables = {
        "provider_credentials",
        "runtime_provider_profiles",
        "sessions",
        "runtime_installations",
        "provider_definitions",
        "provider_compatibility_evidence_sets",
        "provider_compatibility_observations",
        "runtime_provider_bindings",
    }
    tables = {
        row[0]
        for row in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if not required_tables.issubset(tables):
        raise RuntimeError("PHASE11_0005_SOURCE_SCHEMA_INVALID")
    source_columns = {
        "provider_credentials": _PHASE11_COLUMNS["provider_credentials"]
        - {"runtime_installation_id"},
        "runtime_provider_profiles": _PHASE11_COLUMNS["runtime_provider_profiles"],
        "sessions": _PHASE11_COLUMNS["sessions"] - {"recent_authenticated_at", "auth_epoch"},
    }
    if any(_columns(connection, table) != columns for table, columns in source_columns.items()):
        raise RuntimeError("PHASE11_0005_SOURCE_SCHEMA_INVALID")
    triggers = {
        row[0]
        for row in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger'")
    }
    if not _PHASE11_SOURCE_TRIGGERS.issubset(triggers):
        raise RuntimeError("PHASE11_0005_SOURCE_SCHEMA_INVALID")
    credential_count = connection.exec_driver_sql(
        "SELECT COUNT(*) FROM provider_credentials"
    ).scalar_one()
    if credential_count:
        raise RuntimeError("PHASE11_0005_LEGACY_CREDENTIALS_PRESENT")
    invalid_required_timestamps = " OR ".join(
        _invalid_source_datetime(f"s.{column}")
        for column in ("created_at", "last_seen_at", "idle_expires_at", "expires_at")
    )
    invalid_revoked_at = _invalid_source_datetime("s.revoked_at")
    invalid_sessions = connection.exec_driver_sql(
        "SELECT COUNT(*) FROM sessions s WHERE "
        "length(s.id)<>36 OR substr(s.id,1,4)<>'ses_' OR substr(s.id,5) GLOB '*[^0-9a-f]*' "
        "OR length(s.user_id)<>36 OR substr(s.user_id,1,4)<>'adm_' "
        "OR substr(s.user_id,5) GLOB '*[^0-9a-f]*' "
        "OR length(s.token_hash)<>64 OR s.token_hash GLOB '*[^0-9a-f]*' "
        "OR length(s.csrf_hash)<>64 OR s.csrf_hash GLOB '*[^0-9a-f]*' "
        f"OR ({invalid_required_timestamps}) "
        f"OR (s.revoked_at IS NOT NULL AND ({invalid_revoked_at})) "
        "OR s.created_at>s.last_seen_at OR s.created_at>s.idle_expires_at "
        "OR s.created_at>s.expires_at OR NOT EXISTS "
        "(SELECT 1 FROM admin_users a WHERE a.id=s.user_id)"
    ).scalar_one()
    if invalid_sessions:
        raise RuntimeError("PHASE11_0005_SESSION_PREFLIGHT_FAILED")


def _verify_version_and_phase11_inventory(connection: Connection) -> None:
    version_table = connection.exec_driver_sql(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='alembic_version'"
    ).scalar_one()
    if not version_table:
        raise RuntimeError("PHASE11_0005_VERSION_TABLE_MISSING")
    versions = tuple(
        row[0] for row in connection.exec_driver_sql("SELECT version_num FROM alembic_version")
    )
    if not versions:
        return
    if len(versions) != 1:
        raise RuntimeError("PHASE11_0005_VERSION_ROW_INVALID")
    tables = {
        row[0]
        for row in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")
    }
    triggers = {
        row[0]
        for row in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger'")
    }
    if versions[0] == "0004_phase11_provider_core":
        if _PHASE11_TABLES.intersection(tables) or _PHASE11_TRIGGERS.intersection(triggers):
            raise RuntimeError("PHASE11_0005_DOWNGRADE_INVENTORY_FAILED")
        expected = {
            "provider_credentials": _PHASE11_COLUMNS["provider_credentials"]
            - {"runtime_installation_id"},
            "runtime_provider_profiles": _PHASE11_COLUMNS["runtime_provider_profiles"],
            "sessions": _PHASE11_COLUMNS["sessions"] - {"recent_authenticated_at", "auth_epoch"},
        }
        if any(_columns(connection, table) != columns for table, columns in expected.items()):
            raise RuntimeError("PHASE11_0005_DOWNGRADE_INVENTORY_FAILED")
        return
    if versions[0] != _PHASE11_HEAD:
        return
    if not _PHASE11_TABLES.issubset(tables) or not _PHASE11_TRIGGERS.issubset(triggers):
        raise RuntimeError("PHASE11_0005_SCHEMA_INVENTORY_FAILED")
    if any(_columns(connection, table) != columns for table, columns in _PHASE11_COLUMNS.items()):
        raise RuntimeError("PHASE11_0005_SCHEMA_INVENTORY_FAILED")


def configured_database_url() -> str:
    url = os.environ.get("AGENTBOX_DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    if not url:
        raise RuntimeError("database URL is required")
    parsed = make_url(url)
    database = parsed.database
    if parsed.get_backend_name() == "sqlite" and database is not None and database != ":memory:":
        parent = Path(database).expanduser().parent
        if not parent.exists():
            if os.environ.get("AGENTBOX_ENV", "development") == "production":
                raise RuntimeError("production database directory must be created by the installer")
            parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    return url


def run_migrations_offline() -> None:
    url = configured_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    config.set_main_option("sqlalchemy.url", configured_database_url().replace("%", "%%"))
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        isolation_level="AUTOCOMMIT",
    )
    with connectable.connect() as connection:
        clock_holder: dict[str, str | None] = {"value": None}

        def migration_now_utc6() -> str:
            value = clock_holder["value"]
            if value is None:
                raise RuntimeError("migration authority clock is not transaction-pinned")
            return value

        connection.connection.driver_connection.create_function(
            "agentbox_now_utc6", 0, migration_now_utc6
        )
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()
        if connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 1:
            raise RuntimeError("PHASE11_0005_FOREIGN_KEYS_REQUIRED")
        if connection.exec_driver_sql("PRAGMA foreign_key_check").all():
            raise RuntimeError("PHASE11_0005_FOREIGN_KEY_CHECK_FAILED")
        if connection.exec_driver_sql("PRAGMA quick_check").all() != [("ok",)]:
            raise RuntimeError("PHASE11_0005_QUICK_CHECK_FAILED")
        _phase_a_phase11_preflight(connection)
        connection.commit()
        if connection.in_transaction():
            raise RuntimeError("PHASE11_0005_ACTIVE_TRANSACTION_BEFORE_FK_OFF")
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        if connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 0:
            raise RuntimeError("PHASE11_0005_FOREIGN_KEYS_DISABLE_FAILED")
        connection.commit()
        if connection.in_transaction():
            raise RuntimeError("PHASE11_0005_ACTIVE_TRANSACTION_BEFORE_LOCK")
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            transactional_ddl=True,
        )
        clock_holder["value"] = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            context.run_migrations()
            _verify_version_and_phase11_inventory(connection)
            if connection.exec_driver_sql("PRAGMA foreign_key_check").all():
                raise RuntimeError("PHASE11_0005_FOREIGN_KEY_CHECK_FAILED")
            if connection.exec_driver_sql("PRAGMA quick_check").all() != [("ok",)]:
                raise RuntimeError("PHASE11_0005_QUICK_CHECK_FAILED")
            connection.exec_driver_sql("COMMIT")
            connection.commit()
        except Exception:
            if connection.in_transaction():
                connection.exec_driver_sql("ROLLBACK")
                connection.rollback()
            raise
        finally:
            clock_holder["value"] = None
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        if connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 1:
            raise RuntimeError("PHASE11_0005_FOREIGN_KEYS_REENABLE_FAILED")
        if connection.exec_driver_sql("PRAGMA foreign_key_check").all():
            raise RuntimeError("PHASE11_0005_FOREIGN_KEY_CHECK_FAILED")
        if connection.exec_driver_sql("PRAGMA quick_check").all() != [("ok",)]:
            raise RuntimeError("PHASE11_0005_QUICK_CHECK_FAILED")
        _verify_version_and_phase11_inventory(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
