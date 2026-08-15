from __future__ import annotations

import stat
from pathlib import Path

from agentbox_core.configuration import Environment, Settings
from agentbox_core.database import Database
from agentbox_core.provider_models import RuntimeBindingState
from agentbox_core.services import ControlPlaneServices, build_services
from conftest import downgrade_database, migrate_database
from pydantic import SecretStr
from sqlalchemy import create_engine, inspect, text

PHASE11_TABLES = {
    "runtime_installations",
    "provider_definitions",
    "provider_credentials",
    "runtime_provider_profiles",
    "runtime_provider_bindings",
    "runtime_session_provider_bindings",
    "provider_compatibility_observations",
    "provider_config_transactions",
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
            for table_name in PHASE11_TABLES:
                assert (
                    connection.execute(text(f'SELECT count(*) FROM "{table_name}"')).scalar_one()
                    == 0
                )
        assert not any("secret" in name for name in inspect(engine).get_table_names())
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
        unmanaged = services.providers.runtime_management("rti_22222222222222222222222222222222")
        assert unmanaged.state is RuntimeBindingState.UNMANAGED
        assert unmanaged.runtime_binding_id is None
    finally:
        services.database.close()


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
