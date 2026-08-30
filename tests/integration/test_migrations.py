from __future__ import annotations

import os
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from agentbox_core.configuration import Environment, Settings
from agentbox_core.database import Database
from agentbox_core.errors import ProviderMetadataNotFound
from agentbox_core.models import Base
from agentbox_core.provider_models import RuntimeBindingState, RuntimeType
from agentbox_core.services import ControlPlaneServices, build_services
from conftest import downgrade_database, migrate_database
from pydantic import SecretStr
from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    UniqueConstraint,
    create_engine,
    event,
    inspect,
    text,
)
from sqlalchemy.engine import Engine

PHASE11_TABLES = {
    "waw_runtime_host_installations",
    "waw_agent_workspace_sessions",
    "waw_workspace_stop_operations",
    "runtime_installations",
    "provider_definitions",
    "provider_credentials",
    "runtime_provider_profiles",
    "runtime_provider_bindings",
    "runtime_session_provider_bindings",
    "provider_compatibility_evidence_sets",
    "provider_compatibility_observations",
    "confirmation_challenges",
    "provider_secret_provisioning_attempts",
}

PHASE11_TRIGGERS = {
    "trg_runtime_profiles_valid_snapshot",
    "trg_runtime_profiles_immutable_snapshot",
    "trg_runtime_bindings_valid_snapshot",
    "trg_runtime_bindings_immutable_selection",
    "trg_session_bindings_valid_snapshot",
    "trg_session_bindings_immutable_update",
    "trg_session_bindings_immutable_delete",
    "trg_compatibility_evidence_valid_scope",
    "trg_compatibility_evidence_sets_start_building",
    "trg_compatibility_expected_dimension",
    "trg_compatibility_runtime_scope",
    "trg_compatibility_auth_scope",
    "trg_compatibility_evidence_sets_immutable_scope",
    "trg_compatibility_evidence_sets_seal_transition",
    "trg_compatibility_evidence_sets_complete",
    "trg_provider_compatibility_evidence_sets_immutable_delete",
    "trg_provider_compatibility_observations_immutable_update",
    "trg_provider_compatibility_observations_immutable_delete",
}

APPROVAL_TRIGGERS = {
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


def _normalize_sql(value: str | None) -> str:
    return "" if value is None else "".join(value.lower().split())


def _orm_check_sql(engine: Engine, table_name: str, constraint: CheckConstraint) -> str:
    compiled = str(
        constraint.sqltext.compile(
            dialect=engine.dialect,
            compile_kwargs={"literal_binds": True},
        )
    )
    return _normalize_sql(compiled).replace(f"{table_name}.", "")


def _migration_table_signature(engine: Engine, table_name: str) -> dict[str, object]:
    inspector = inspect(engine)
    return {
        "columns": tuple(
            (column["name"], str(column["type"]).upper(), column["nullable"])
            for column in inspector.get_columns(table_name)
        ),
        "primary_key": tuple(inspector.get_pk_constraint(table_name)["constrained_columns"]),
        "foreign_keys": {
            (
                tuple(item["constrained_columns"]),
                item["referred_table"],
                tuple(item["referred_columns"]),
                item.get("options", {}).get("ondelete"),
            )
            for item in inspector.get_foreign_keys(table_name)
        },
        "unique": {
            tuple(item["column_names"]) for item in inspector.get_unique_constraints(table_name)
        },
        "checks": {
            (item["name"], _normalize_sql(item["sqltext"]))
            for item in inspector.get_check_constraints(table_name)
        },
        "indexes": {
            (item["name"], tuple(item["column_names"]), item["unique"])
            for item in inspector.get_indexes(table_name)
        },
    }


def _orm_table_signature(engine: Engine, table_name: str) -> dict[str, object]:
    table = Base.metadata.tables[table_name]
    return {
        "columns": tuple(
            (
                column.name,
                str(column.type.compile(dialect=engine.dialect)).upper(),
                column.nullable,
            )
            for column in table.columns
        ),
        "primary_key": tuple(column.name for column in table.primary_key.columns),
        "foreign_keys": {
            (
                tuple(element.parent.name for element in constraint.elements),
                constraint.elements[0].column.table.name,
                tuple(element.column.name for element in constraint.elements),
                constraint.ondelete,
            )
            for constraint in table.constraints
            if isinstance(constraint, ForeignKeyConstraint)
        },
        "unique": {
            tuple(column.name for column in constraint.columns)
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        },
        "checks": {
            (constraint.name, _orm_check_sql(engine, table_name, constraint))
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
        },
        "indexes": {
            (index.name, tuple(column.name for column in index.columns), index.unique)
            for index in table.indexes
        },
    }


def test_upgrade_downgrade_and_upgrade_again(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'migration.db'}"
    settings = Settings(
        env=Environment.TEST,
        database_url=database_url,
        data_dir=tmp_path,
        secret_key=SecretStr("migration-test-secret-that-is-long-enough"),
    )

    migrate_database(database_url)
    database = Database(settings)
    try:
        assert set(inspect(database.engine).get_table_names()) >= {
            "admin_users",
            "sessions",
            "audit_events",
            "login_rate_limit_buckets",
            "alembic_version",
            *PHASE11_TABLES,
        }
        assert database.migrations_current()
    finally:
        database.close()

    downgrade_database(database_url, "base")
    database = Database(settings)
    try:
        assert set(inspect(database.engine).get_table_names()) == {"alembic_version"}
        assert not database.migrations_current()
    finally:
        database.close()

    migrate_database(database_url)
    database = Database(settings)
    try:
        assert database.migrations_current()
    finally:
        database.close()


def test_phase11_upgrade_preserves_existing_data_without_automatic_adoption(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'pre-phase11.db'}"
    migrate_database(database_url, "0003_security_hardening")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO admin_users "
                    "(id, username, username_normalized, password_hash, is_active, "
                    "created_at, updated_at, last_login_at) VALUES "
                    "(:id, :username, :normalized, :hash, 1, :created, :updated, NULL)"
                ),
                {
                    "id": "adm_00000000000000000000000000000000",
                    "username": "maintainer",
                    "normalized": "maintainer",
                    "hash": "representative-existing-password-hash",
                    "created": "2026-08-15 00:00:00",
                    "updated": "2026-08-15 00:00:00",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO projects "
                    "(id, slug, display_name, relative_path, source_type, repository_url, "
                    "default_branch, state, archived_at, created_at, updated_at) VALUES "
                    "(:id, :slug, :name, :path, 'empty', NULL, NULL, 'ready', NULL, "
                    ":created, :updated)"
                ),
                {
                    "id": "prj_11111111111111111111111111111111",
                    "slug": "existing-project",
                    "name": "Existing Project",
                    "path": "existing-project",
                    "created": "2026-08-15 00:00:00",
                    "updated": "2026-08-15 00:00:00",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO sessions "
                    "(id, user_id, token_hash, csrf_hash, created_at, last_seen_at, "
                    "idle_expires_at, expires_at, revoked_at, client_label) VALUES "
                    "(:id, :user_id, :token_hash, :csrf_hash, :created, :seen, "
                    ":idle, :expires, NULL, :client_label)"
                ),
                {
                    "id": "ses_22222222222222222222222222222222",
                    "user_id": "adm_00000000000000000000000000000000",
                    "token_hash": "a" * 64,
                    "csrf_hash": "b" * 64,
                    "created": "2026-08-15 00:00:00",
                    "seen": "2026-08-15 00:00:00",
                    "idle": "2026-08-15 01:00:00",
                    "expires": "2026-08-16 00:00:00",
                    "client_label": "migration-fixture",
                },
            )
    finally:
        engine.dispose()

    migrate_database(database_url)
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT username FROM admin_users")).scalar_one() == (
                "maintainer"
            )
            assert connection.execute(text("SELECT slug FROM projects")).scalar_one() == (
                "existing-project"
            )
            assert connection.execute(text("SELECT client_label FROM sessions")).scalar_one() == (
                "migration-fixture"
            )
            for table_name in PHASE11_TABLES:
                assert (
                    connection.execute(text(f'SELECT count(*) FROM "{table_name}"')).scalar_one()
                    == 0
                )
        assert "provider_secret_provisioning_attempts" in inspect(engine).get_table_names()
    finally:
        engine.dispose()

    settings = Settings(
        env=Environment.TEST,
        database_url=database_url,
        data_dir=tmp_path,
        secret_key=SecretStr("migration-test-secret-that-is-long-enough"),
    )
    services = build_services(settings)
    try:
        with pytest.raises(ProviderMetadataNotFound):
            services.providers.runtime_management("rti_22222222222222222222222222222222")
        runtime = services.providers.register_runtime_installation(
            runtime_type=RuntimeType.CODEX,
            display_name="explicitly registered fixture",
            actor_id="adm_00000000000000000000000000000000",
        )
        unmanaged = services.providers.runtime_management(runtime.id)
        assert unmanaged.state is RuntimeBindingState.UNMANAGED
        assert unmanaged.runtime_binding_id is None
    finally:
        services.database.close()


def test_0005_rejects_every_legacy_credential_before_schema_change(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'legacy-credential.db'}"
    migrate_database(database_url, "0004_phase11_provider_core")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO provider_definitions "
                    "(id,identity_schema_version,display_name,provider_type,endpoint,"
                    "wire_protocol,model,state,revision,created_at,updated_at) VALUES "
                    "('prv_11111111111111111111111111111111',1,'Legacy','official_openai',"
                    "'https://api.openai.com/v1','responses','gpt-5','configured',1,"
                    "'2026-08-25 00:00:00.000000','2026-08-25 00:00:00.000000')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO provider_credentials "
                    "(id,provider_id,kind,runtime_secret_ref,secret_version,state,revision,"
                    "created_at,updated_at) VALUES "
                    "('crd_22222222222222222222222222222222',"
                    "'prv_11111111111111111111111111111111','api_key',NULL,NULL,'missing',1,"
                    "'2026-08-25 00:00:00.000000','2026-08-25 00:00:00.000000')"
                )
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="PHASE11_0005_LEGACY_CREDENTIALS_PRESENT"):
        migrate_database(database_url)

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "0004_phase11_provider_core"
            )
            assert (
                connection.execute(text("SELECT COUNT(*) FROM provider_credentials")).scalar_one()
                == 1
            )
            assert "runtime_installation_id" not in {
                row[1]
                for row in connection.execute(text("PRAGMA table_info(provider_credentials)"))
            }
    finally:
        engine.dispose()


def test_0005_source_schema_preflight_fails_before_any_mutation(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'invalid-source-schema.db'}"
    migrate_database(database_url, "0004_phase11_provider_core")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP TRIGGER trg_runtime_profiles_valid_snapshot"))
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="PHASE11_0005_SOURCE_SCHEMA_INVALID"):
        migrate_database(database_url)

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "0004_phase11_provider_core"
            )
            assert "runtime_installation_id" not in {
                row[1]
                for row in connection.execute(text("PRAGMA table_info(provider_credentials)"))
            }
            assert (
                connection.execute(
                    text(
                        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
                        "AND name IN ('confirmation_challenges',"
                        "'provider_secret_provisioning_attempts')"
                    )
                ).scalar_one()
                == 0
            )
    finally:
        engine.dispose()


def test_0005_invalid_session_preflight_fails_before_any_mutation(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'invalid-source-session.db'}"
    migrate_database(database_url, "0004_phase11_provider_core")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO admin_users "
                    "(id,username,username_normalized,password_hash,is_active,created_at,"
                    "updated_at,last_login_at) VALUES "
                    "('adm_00000000000000000000000000000000','maintainer','maintainer',"
                    "'representative-existing-password-hash',1,'2026-02-28 00:00:00',"
                    "'2026-02-28 00:00:00',NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO sessions "
                    "(id,user_id,token_hash,csrf_hash,created_at,last_seen_at,idle_expires_at,"
                    "expires_at,revoked_at,client_label) VALUES "
                    "('ses_22222222222222222222222222222222',"
                    "'adm_00000000000000000000000000000000',:token_hash,:csrf_hash,"
                    "'2026-02-28 00:00:00','2026-02-30 00:00:00',"
                    "'2026-03-01 00:00:00','2026-03-02 00:00:00',NULL,'invalid-calendar')"
                ),
                {"token_hash": "a" * 64, "csrf_hash": "b" * 64},
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="PHASE11_0005_SESSION_PREFLIGHT_FAILED"):
        migrate_database(database_url)

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "0004_phase11_provider_core"
            )
            assert "runtime_installation_id" not in {
                row[1]
                for row in connection.execute(text("PRAGMA table_info(provider_credentials)"))
            }
            assert (
                connection.execute(
                    text(
                        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
                        "AND name IN ('confirmation_challenges',"
                        "'provider_secret_provisioning_attempts')"
                    )
                ).scalar_one()
                == 0
            )
    finally:
        engine.dispose()


def test_0005_unsafe_downgrade_rolls_back_schema_and_version(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'unsafe-downgrade.db'}"
    migrate_database(database_url)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO admin_users "
                    "(id,username,username_normalized,password_hash,is_active,created_at,"
                    "updated_at,last_login_at) VALUES "
                    "('adm_11111111111111111111111111111111','owner','owner','hash',1,"
                    "'2026-08-25 00:00:00.000000','2026-08-25 00:00:00.000000',NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO sessions "
                    "(id,user_id,token_hash,csrf_hash,created_at,recent_authenticated_at,"
                    "auth_epoch,last_seen_at,idle_expires_at,expires_at,revoked_at,client_label) "
                    "VALUES ('ses_22222222222222222222222222222222',"
                    "'adm_11111111111111111111111111111111',:token,:csrf,"
                    "'2026-08-25 00:00:00.000000','2026-08-25 00:00:00.000000',2,"
                    "'2026-08-25 00:00:00.000000','2026-08-25 01:00:00.000000',"
                    "'2026-08-26 00:00:00.000000',NULL,'fixture')"
                ),
                {"token": "a" * 64, "csrf": "b" * 64},
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="PHASE11_0005_DOWNGRADE_UNSAFE"):
        downgrade_database(database_url, "0004_phase11_provider_core")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "0006_waw_workspace_metadata"
            )
            assert "confirmation_challenges" in inspect(engine).get_table_names()
            assert "auth_epoch" in {
                row[1] for row in connection.execute(text("PRAGMA table_info(sessions)"))
            }
    finally:
        engine.dispose()


def test_phase11_migration_matches_orm_metadata_and_installs_exact_triggers(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'phase11-schema-parity.db'}"
    migrate_database(database_url)
    engine = create_engine(database_url)
    try:
        for table_name in PHASE11_TABLES:
            assert _migration_table_signature(engine, table_name) == _orm_table_signature(
                engine, table_name
            )
        with engine.connect() as connection:
            triggers = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT name FROM sqlite_master "
                        "WHERE type = 'trigger' AND (name LIKE 'trg_session_bindings_%' "
                        "OR name LIKE 'trg_runtime_profiles_%' "
                        "OR name LIKE 'trg_runtime_bindings_%' "
                        "OR name LIKE 'trg_compatibility_%' "
                        "OR name LIKE 'trg_provider_compatibility_%')"
                    )
                )
            }
        assert triggers == PHASE11_TRIGGERS
        with engine.connect() as connection:
            approval_triggers = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='trigger' "
                        "AND (name LIKE 'trg_confirmation_challenges_%' "
                        "OR name LIKE 'trg_provider_secret_attempts_%')"
                    )
                )
            }
        assert approval_triggers == APPROVAL_TRIGGERS
    finally:
        engine.dispose()


def test_phase11_downgrade_removes_only_additive_provider_schema(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'phase11-downgrade.db'}"
    migrate_database(database_url)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO projects "
                    "(id, slug, display_name, relative_path, source_type, repository_url, "
                    "default_branch, state, archived_at, created_at, updated_at) VALUES "
                    "('prj_33333333333333333333333333333333', 'preserved', 'Preserved', "
                    "'preserved', 'empty', NULL, NULL, 'ready', NULL, "
                    "'2026-08-15 00:00:00', '2026-08-15 00:00:00')"
                )
            )
    finally:
        engine.dispose()

    downgrade_database(database_url, "0003_security_hardening")
    engine = create_engine(database_url)
    try:
        table_names = set(inspect(engine).get_table_names())
        assert not (PHASE11_TABLES & table_names)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT slug FROM projects")).scalar_one() == (
                "preserved"
            )
            remaining_triggers = {
                row[0]
                for row in connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type = 'trigger'")
                )
            }
            assert not (remaining_triggers & PHASE11_TRIGGERS)
    finally:
        engine.dispose()


def test_sqlite_security_pragmas(
    settings: Settings,
    services: ControlPlaneServices,
) -> None:
    database = services.database
    state = database.pragma_state()

    assert state["journal_mode"] == "wal"
    assert state["foreign_keys"] == 1
    assert state["busy_timeout"] == settings.database_busy_timeout_ms
    database_path = Path(database.engine.url.database or "")
    assert stat.S_IMODE(database_path.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "target",
    [
        "head",
        "0005_phase11_control_plane_ownership_approval",
        "+1",
        "heads",
        "0004_phase11_provider_core+1",
    ],
)
def test_0005_target_plan_preflight_before_fk_off(tmp_path: Path, target: str) -> None:
    path = tmp_path / "target.db"
    url = f"sqlite+pysqlite:///{path}"
    migrate_database(url, "0004_phase11_provider_core")
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER trg_runtime_profiles_valid_snapshot")
        before = tuple(connection.iterdump())
    statements: list[str] = []

    def trace(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", trace)
    try:
        with pytest.raises(RuntimeError, match="^PHASE11_0005_SOURCE_SCHEMA_INVALID$"):
            migrate_database(url, target)
    finally:
        event.remove(Engine, "before_cursor_execute", trace)
    assert "PRAGMA foreign_keys=OFF" not in statements
    assert "BEGIN IMMEDIATE" not in statements
    with sqlite3.connect(path) as connection:
        assert tuple(connection.iterdump()) == before
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0004_phase11_provider_core",
        )
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name IN "
                "('confirmation_challenges','provider_secret_provisioning_attempts')"
            ).fetchall()
            == []
        )


@pytest.mark.parametrize(
    "target",
    [
        "head",
        "0005_phase11_control_plane_ownership_approval",
        "0004_phase11_provider_core:0005_phase11_control_plane_ownership_approval",
    ],
)
def test_0005_offline_command_rejected_without_sql_or_mutation(tmp_path: Path, target: str) -> None:
    path = tmp_path / "offline.db"
    url = f"sqlite+pysqlite:///{path}"
    migrate_database(url, "0004_phase11_provider_core")
    before = path.read_bytes()
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", target, "--sql"],
        env={**os.environ, "AGENTBOX_DATABASE_URL": url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "RuntimeError: PHASE11_0005_OFFLINE_UNSUPPORTED" in result.stderr
    assert result.stdout == ""
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "drift",
    [
        "trigger_body",
        "missing_trigger",
        "fk_target",
        "fk_columns",
        "fk_ondelete",
        "unique",
        "check",
        "index_missing",
        "index_altered",
        "index_desc",
        "index_collation",
        "column",
        "default",
        "nullable",
        "evidence_fk",
    ],
)
def test_0005_canonical_source_drift_is_zero_mutation(tmp_path: Path, drift: str) -> None:
    path = tmp_path / "drift.db"
    url = f"sqlite+pysqlite:///{path}"
    migrate_database(url, "0004_phase11_provider_core")
    with sqlite3.connect(path) as connection:
        if drift in {"trigger_body", "missing_trigger"}:
            name = "trg_runtime_profiles_valid_snapshot"
            original = connection.execute(
                "SELECT sql FROM sqlite_master WHERE name=?", (name,)
            ).fetchone()[0]
            connection.execute(f"DROP TRIGGER {name}")
            if drift == "trigger_body":
                connection.execute(original.replace("RAISE(ABORT,", "RAISE(FAIL,"))
        elif drift == "unique":
            original = connection.execute(
                "SELECT sql FROM sqlite_master WHERE name='provider_credentials'"
            ).fetchone()[0]
            triggers = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='trigger' AND "
                "tbl_name='provider_credentials'"
            ).fetchall()
            # Rebuild in this fixture so the removed UNIQUE has no orphan autoindex.
            connection.execute("PRAGMA legacy_alter_table=ON")
            connection.execute("DROP TABLE provider_credentials")
            connection.execute(
                original.replace(
                    "CONSTRAINT uq_provider_credentials_provider UNIQUE (provider_id),", ""
                )
            )
            for (trigger,) in triggers:
                connection.execute(trigger)
        elif drift.startswith("index_"):
            connection.execute("DROP INDEX ix_sessions_expires_at")
            if drift == "index_altered":
                connection.execute("CREATE INDEX ix_sessions_expires_at ON sessions(last_seen_at)")
            elif drift == "index_desc":
                connection.execute(
                    "CREATE INDEX ix_sessions_expires_at ON sessions(expires_at DESC)"
                )
            elif drift == "index_collation":
                connection.execute(
                    "CREATE INDEX ix_sessions_expires_at ON sessions(expires_at COLLATE NOCASE)"
                )
        elif drift == "column":
            connection.execute("ALTER TABLE sessions ADD COLUMN unexpected INTEGER")
        else:
            table = "provider_credentials"
            if drift in {"default", "nullable"}:
                table = "sessions"
            elif drift == "evidence_fk":
                table = "provider_compatibility_evidence_sets"
            original = connection.execute(
                "SELECT sql FROM sqlite_master WHERE name=?", (table,)
            ).fetchone()[0]
            replacements = {
                "fk_target": (
                    "REFERENCES provider_definitions (id)",
                    "REFERENCES runtime_installations (id)",
                ),
                "fk_columns": ("FOREIGN KEY(provider_id)", "FOREIGN KEY(id)"),
                "fk_ondelete": ("ON DELETE RESTRICT", "ON DELETE CASCADE"),
                "unique": ("CONSTRAINT uq_provider_credentials_provider UNIQUE (provider_id),", ""),
                "check": ("revision >= 1", "revision >= 0"),
                "default": ("client_label VARCHAR(80)", "client_label VARCHAR(80) DEFAULT 'drift'"),
                "nullable": ("csrf_hash VARCHAR(64) NOT NULL", "csrf_hash VARCHAR(64)"),
                "evidence_fk": (
                    "REFERENCES provider_credentials (id, provider_id)",
                    "REFERENCES provider_credentials (provider_id, id)",
                ),
            }
            old, new = replacements[drift]
            assert old in original
            changed = original.replace(old, new, 1)
            connection.execute("PRAGMA writable_schema=ON")
            connection.execute(
                "UPDATE sqlite_master SET sql=? WHERE name=? AND type='table'", (changed, table)
            )
            connection.execute("PRAGMA writable_schema=OFF")
    before_bytes = path.read_bytes()
    with sqlite3.connect(path) as connection:
        before = tuple(connection.iterdump())
    statements: list[str] = []

    def trace(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", trace)
    try:
        with pytest.raises(RuntimeError, match="^PHASE11_0005_SOURCE_SCHEMA_INVALID$"):
            migrate_database(url)
    finally:
        event.remove(Engine, "before_cursor_execute", trace)
    assert "PRAGMA foreign_keys=OFF" not in statements
    assert "BEGIN IMMEDIATE" not in statements
    assert path.read_bytes() == before_bytes
    with sqlite3.connect(path) as connection:
        assert tuple(connection.iterdump()) == before
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0004_phase11_provider_core",
        )
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name LIKE "
                "'%confirmation_challenges%' OR name LIKE '%provider_secret%'"
            ).fetchall()
            == []
        )


@pytest.mark.parametrize(
    "target",
    [
        "+1",
        "0005_phase11_control_plane_ownership_approval",
        "0004_phase11_provider_core+1",
        "heads",
    ],
)
def test_0005_real_command_supported_targets(tmp_path: Path, target: str) -> None:
    path = tmp_path / "success.db"
    url = f"sqlite+pysqlite:///{path}"
    migrate_database(url, "0004_phase11_provider_core")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", target],
        env={**os.environ, "AGENTBOX_DATABASE_URL": url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as connection:
        expected_revision = (
            "0006_waw_workspace_metadata"
            if target == "heads"
            else "0005_phase11_control_plane_ownership_approval"
        )
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            expected_revision,
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA quick_check").fetchall() == [("ok",)]


def test_online_range_is_rejected_by_alembic_without_mutation(tmp_path: Path) -> None:
    path = tmp_path / "range.db"
    url = f"sqlite+pysqlite:///{path}"
    migrate_database(url, "0004_phase11_provider_core")
    before = path.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "0004_phase11_provider_core:0005_phase11_control_plane_ownership_approval",
        ],
        env={**os.environ, "AGENTBOX_DATABASE_URL": url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Range revision not allowed" in result.stdout + result.stderr
    assert path.read_bytes() == before


def test_historical_offline_sql_still_supported(tmp_path: Path) -> None:
    path = tmp_path / "historical.db"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0004_phase11_provider_core", "--sql"],
        env={**os.environ, "AGENTBOX_DATABASE_URL": f"sqlite:///{path}"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE provider_credentials" in result.stdout
    assert not path.exists()


def test_phase_b_rechecks_source_after_outer_preflight(tmp_path: Path) -> None:
    path = tmp_path / "phase_b.db"
    url = f"sqlite+pysqlite:///{path}"
    migrate_database(url, "0004_phase11_provider_core")
    changed = False

    def mutate(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        nonlocal changed
        if statement == "PRAGMA foreign_keys=OFF":
            with sqlite3.connect(path) as writer:
                writer.execute("DROP INDEX ix_sessions_expires_at")
            changed = True

    event.listen(Engine, "after_cursor_execute", mutate)
    try:
        with pytest.raises(RuntimeError, match="^PHASE11_0005_SOURCE_SCHEMA_INVALID$"):
            migrate_database(url)
    finally:
        event.remove(Engine, "after_cursor_execute", mutate)
    assert changed
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0004_phase11_provider_core",
        )
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='confirmation_challenges'"
            ).fetchall()
            == []
        )


def test_source_inventory_accepts_sqlite_internal_statistics(tmp_path: Path) -> None:
    path = tmp_path / "statistics.db"
    url = f"sqlite+pysqlite:///{path}"
    migrate_database(url, "0004_phase11_provider_core")
    with sqlite3.connect(path) as connection:
        connection.execute("ANALYZE")
        connection.execute("CREATE TABLE unrelated_extension(value TEXT)")
    migrate_database(url)


def test_phase_b_rejects_wrong_exact_version_before_commit(tmp_path: Path) -> None:
    from sqlalchemy.engine import Connection

    path = tmp_path / "wrong-version.db"
    url = f"sqlite+pysqlite:///{path}"
    migrate_database(url, "0004_phase11_provider_core")
    before = path.read_bytes()
    changed = False

    def corrupt(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        nonlocal changed
        if not changed and statement.startswith("UPDATE alembic_version"):
            changed = True
            connection.exec_driver_sql(
                "UPDATE alembic_version SET version_num='unexpected_revision'"
            )

    event.listen(Engine, "after_cursor_execute", corrupt)
    try:
        with pytest.raises(RuntimeError, match="^PHASE11_0005_VERSION_ROW_INVALID$"):
            migrate_database(url, "0005_phase11_control_plane_ownership_approval")
    finally:
        event.remove(Engine, "after_cursor_execute", corrupt)
    assert changed
    assert path.read_bytes() == before
