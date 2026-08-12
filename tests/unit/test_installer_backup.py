from __future__ import annotations

import sqlite3
import threading
import time
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
    tmpfiles = tmp_path / "agentbox.conf"
    tmpfiles.write_text("d /run/agentbox 3770 root agentbox -\n", encoding="utf-8")
    backups = tmp_path / "backups"
    backups.mkdir()

    result = create_sqlite_backup(
        database,
        backups,
        application_version="0.2.0",
        migration_revision="0002_project_jobs",
        config_path=config,
        unit_paths=(unit,),
        tmpfiles_path=tmpfiles,
        backup_id="tamper-fixture",
    )
    assert verify_sqlite_backup(result)

    (result.path / "units/agentbox-api.service").write_text(
        "[Service]\nExecStart=/attacker\n", encoding="utf-8"
    )
    assert not verify_sqlite_backup(result)

    (result.path / "units/agentbox-api.service").write_text(
        "[Service]\nExecStart=/safe\n", encoding="utf-8"
    )
    (result.path / "tmpfiles/agentbox.conf").write_text(
        "d /run/agentbox 0777 root root -\n", encoding="utf-8"
    )
    assert not verify_sqlite_backup(result)


def test_online_backup_is_consistent_during_concurrent_wal_writes(tmp_path: Path) -> None:
    database = tmp_path / "agentbox.db"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE events(sequence INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO events VALUES (0, 'seed')")
    backups = tmp_path / "backups"
    backups.mkdir(mode=0o700)
    started = threading.Event()
    stopped = threading.Event()

    def write_committed_rows() -> None:
        sequence = 1
        with sqlite3.connect(database, timeout=5) as writer:
            while not stopped.is_set():
                writer.execute("INSERT INTO events VALUES (?, 'committed')", (sequence,))
                writer.commit()
                started.set()
                sequence += 1
                time.sleep(0.001)

    thread = threading.Thread(target=write_committed_rows)
    thread.start()
    assert started.wait(timeout=5)
    try:
        result = create_sqlite_backup(
            database,
            backups,
            application_version="0.2.4+dev.8",
            migration_revision="0002_project_jobs",
            backup_id="concurrent-wal-fixture",
        )
    finally:
        stopped.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert verify_sqlite_backup(result)
    with sqlite3.connect(result.path / "agentbox.db") as restored:
        assert restored.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        snapshot_rows = restored.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    with sqlite3.connect(database) as live:
        live_rows = live.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert 2 <= snapshot_rows <= live_rows
    assert not (result.path / "agentbox.db-wal").exists()
    assert not (result.path / "agentbox.db-shm").exists()


def test_backup_manifest_and_config_never_include_application_secret(tmp_path: Path) -> None:
    database = tmp_path / "agentbox.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE sample(value TEXT)")
    config = tmp_path / "agentbox.toml"
    canary = "phase8-secret-canary-never-copy"
    config.write_text(f'env = "production"\nsecret_key = "{canary}"\n', encoding="utf-8")
    backups = tmp_path / "backups"
    backups.mkdir()

    try:
        create_sqlite_backup(
            database,
            backups,
            application_version="0.2.4+dev.8",
            migration_revision="0002_project_jobs",
            config_path=config,
            backup_id="secret-rejection-fixture",
        )
    except RuntimeError as exc:
        assert "secret field" in str(exc)
    else:
        raise AssertionError("secret-bearing config backup was accepted")
    assert canary not in repr(list(backups.rglob("*")))
