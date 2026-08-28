"""Alembic environment for the AgentBox control-plane database."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from logging.config import fileConfig
from pathlib import Path

import agentbox_core.approval_models  # noqa: F401 -- registers Slice 3.2a metadata
import agentbox_core.provider_models  # noqa: F401 -- registers Phase 11 metadata
from agentbox_core.migration_inventory import verify_phase11_inventory
from agentbox_core.models import Base
from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection, make_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_PHASE11_HEAD = "0005_phase11_control_plane_ownership_approval"


def _plan_enters_phase11() -> bool:
    """Resolve the same Alembic revision steps that run_migrations will execute.

    The configured command's fn handles aliases, relative targets and offline
    ranges. Inspecting its steps is read-only and cannot create a version table.
    """
    migration_context = context.get_context()
    heads = migration_context.get_current_heads()
    steps = migration_context.opts["fn"](heads, migration_context)
    return any(step.is_upgrade and step.revision.revision == _PHASE11_HEAD for step in steps)


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
    if not _plan_enters_phase11():
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
    verify_phase11_inventory(
        connection, "0004_phase11_provider_core", "PHASE11_0005_SOURCE_SCHEMA_INVALID"
    )
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


def _verify_version_and_phase11_inventory(
    connection: Connection, expected_versions: tuple[str, ...]
) -> None:
    version_table = connection.exec_driver_sql(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='alembic_version'"
    ).scalar_one()
    if not version_table:
        raise RuntimeError("PHASE11_0005_VERSION_TABLE_MISSING")
    versions = tuple(
        row[0] for row in connection.exec_driver_sql("SELECT version_num FROM alembic_version")
    )
    if versions != expected_versions:
        raise RuntimeError("PHASE11_0005_VERSION_ROW_INVALID")
    if not versions:
        return
    if len(versions) != 1:
        raise RuntimeError("PHASE11_0005_VERSION_ROW_INVALID")
    if versions[0] == "0004_phase11_provider_core":
        verify_phase11_inventory(connection, versions[0], "PHASE11_0005_DOWNGRADE_INVENTORY_FAILED")
    elif versions[0] == _PHASE11_HEAD:
        verify_phase11_inventory(connection, versions[0], "PHASE11_0005_SCHEMA_INVENTORY_FAILED")


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
    if _plan_enters_phase11():
        raise RuntimeError("PHASE11_0005_OFFLINE_UNSUPPORTED")
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
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            transactional_ddl=True,
        )
        _phase_a_phase11_preflight(connection)
        if connection.exec_driver_sql("PRAGMA foreign_key_check").all():
            raise RuntimeError("PHASE11_0005_FOREIGN_KEY_CHECK_FAILED")
        if connection.exec_driver_sql("PRAGMA quick_check").all() != [("ok",)]:
            raise RuntimeError("PHASE11_0005_QUICK_CHECK_FAILED")
        connection.commit()
        if connection.in_transaction():
            raise RuntimeError("PHASE11_0005_ACTIVE_TRANSACTION_BEFORE_FK_OFF")
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        if connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 0:
            raise RuntimeError("PHASE11_0005_FOREIGN_KEYS_DISABLE_FAILED")
        connection.commit()
        if connection.in_transaction():
            raise RuntimeError("PHASE11_0005_ACTIVE_TRANSACTION_BEFORE_LOCK")
        clock_holder["value"] = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            _phase_a_phase11_preflight(connection)
            if connection.exec_driver_sql("PRAGMA foreign_key_check").all():
                raise RuntimeError("PHASE11_0005_FOREIGN_KEY_CHECK_FAILED")
            if connection.exec_driver_sql("PRAGMA quick_check").all() != [("ok",)]:
                raise RuntimeError("PHASE11_0005_QUICK_CHECK_FAILED")
            migration_context = context.get_context()
            current_heads = migration_context.get_current_heads()
            steps = list(migration_context.opts["fn"](current_heads, migration_context))
            expected_versions = tuple(steps[-1].to_revisions) if steps else current_heads
            context.run_migrations()
            _verify_version_and_phase11_inventory(connection, expected_versions)
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
        _verify_version_and_phase11_inventory(connection, expected_versions)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
