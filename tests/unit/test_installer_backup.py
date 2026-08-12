from __future__ import annotations

import sqlite3
from pathlib import Path

from agentbox_installer.backup import create_sqlite_backup, verify_sqlite_backup


def test_sqlite_online_backup_includes_wal_data_and_excludes_projects(tmp_path: Path) -> None:
    database = tmp_path / "agentbox.db"
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE sample(value TEXT)")
    connection.execute("INSERT INTO sample VALUES ('committed-in-wal')")
    connection.commit()
    backups = tmp_path / "backups"
    backups.mkdir()

    result = create_sqlite_backup(
        database,
        backups,
        application_version="0.1.0",
        migration_revision="0002_project_jobs",
        backup_id="fixture-backup",
    )

    assert verify_sqlite_backup(result)
    with sqlite3.connect(result.path / "agentbox.db") as restored:
        assert restored.execute("SELECT value FROM sample").fetchone() == ("committed-in-wal",)
    assert not (result.path / "projects").exists()
    assert not (result.path / "agentbox.db-wal").exists()
    assert not (result.path / "agentbox.db-shm").exists()
    connection.close()


def test_backup_bundle_rejects_tampered_config_or_unit(tmp_path: Path) -> None:
    database = tmp_path / "agentbox.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE sample(value TEXT)")
    config = tmp_path / "agentbox.toml"
    config.write_text('env = "production"\n', encoding="utf-8")
    unit = tmp_path / "agentbox-api.service"
    unit.write_text("[Service]\nExecStart=/safe\n", encoding="utf-8")
    backups = tmp_path / "backups"
    backups.mkdir()

    result = create_sqlite_backup(
        database,
        backups,
        application_version="0.2.0",
        migration_revision="0002_project_jobs",
        config_path=config,
        unit_paths=(unit,),
        backup_id="tamper-fixture",
    )
    assert verify_sqlite_backup(result)

    (result.path / "units/agentbox-api.service").write_text(
        "[Service]\nExecStart=/attacker\n", encoding="utf-8"
    )
    assert not verify_sqlite_backup(result)
