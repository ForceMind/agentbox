from __future__ import annotations

import stat
from pathlib import Path

from agentbox_core.configuration import Environment, Settings
from agentbox_core.database import Database
from agentbox_core.services import ControlPlaneServices
from conftest import downgrade_database, migrate_database
from pydantic import SecretStr
from sqlalchemy import inspect


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
            "alembic_version",
        }
        assert database.migrations_current()
    finally:
        database.close()

    downgrade_database(database_url, "-1")
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
