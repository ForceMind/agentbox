from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import tarfile
from pathlib import Path

import pytest
from agentbox_installer.artifact import extract_verified_tar
from agentbox_installer.backup import create_sqlite_backup
from agentbox_installer.retention import _version_key, enforce_retention


def _release(root: Path, version: str) -> None:
    payload = f"release-{version}".encode()
    manifest = {
        "schema_version": 1,
        "version": version,
        "database_revision": "0003_security_hardening",
        "database_backward_compatible": True,
        "files": {"payload.txt": hashlib.sha256(payload).hexdigest()},
    }
    archive = root.parent / f"{version}.tar"
    with tarfile.open(archive, "w") as bundle:
        for name, content in (
            ("payload.txt", payload),
            ("manifest.json", json.dumps(manifest).encode()),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            bundle.addfile(info, io.BytesIO(content))
    extract_verified_tar(archive, root / version)


def test_retention_deletes_only_verified_unprotected_agentbox_objects(
    tmp_path: Path,
) -> None:
    backups = tmp_path / "backups"
    releases = tmp_path / "releases"
    backups.mkdir()
    releases.mkdir()
    database = tmp_path / "agentbox.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE sample(value TEXT)")

    for index in range(1, 8):
        create_sqlite_backup(
            database,
            backups,
            application_version=f"0.2.{index}",
            migration_revision="0003_security_hardening",
            backup_id=f"backup-{index}",
        )
        _release(releases, f"0.2.{index}")

    corrupt_backup = backups / "operator-file"
    corrupt_backup.mkdir()
    (corrupt_backup / "manifest.json").write_text("{}", encoding="utf-8")
    corrupt_release = releases / "0.2.99"
    corrupt_release.mkdir()
    (corrupt_release / "manifest.json").write_text("{}", encoding="utf-8")

    result = enforce_retention(
        backups_root=backups,
        releases_root=releases,
        protected_backup_ids=frozenset({"backup-1"}),
        protected_release_versions=frozenset({"0.2.1", "0.2.7"}),
    )

    assert set(result.removed_backups) == {"backup-2", "backup-3"}
    assert set(result.removed_releases) == {"0.2.2", "0.2.3", "0.2.4"}
    assert (backups / "backup-1").is_dir()
    assert (releases / "0.2.1").is_dir()
    assert corrupt_backup.is_dir()
    assert corrupt_release.is_dir()


def test_retention_rejects_symlinked_roots_without_touching_target(tmp_path: Path) -> None:
    real_backups = tmp_path / "real-backups"
    real_backups.mkdir()
    backups = tmp_path / "backups"
    backups.symlink_to(real_backups, target_is_directory=True)
    releases = tmp_path / "releases"
    releases.mkdir()

    try:
        enforce_retention(
            backups_root=backups,
            releases_root=releases,
            protected_backup_ids=frozenset(),
            protected_release_versions=frozenset(),
        )
    except RuntimeError as exc:
        assert "unsafe" in str(exc)
    else:
        raise AssertionError("symlinked retention root was accepted")
    assert real_backups.is_dir()


def test_retention_derives_and_preserves_current_release_target(tmp_path: Path) -> None:
    backups = tmp_path / "backups"
    releases = tmp_path / "releases"
    backups.mkdir()
    releases.mkdir()
    for index in range(1, 7):
        _release(releases, f"0.3.{index}")
    (tmp_path / "current").symlink_to("releases/0.3.1")

    result = enforce_retention(
        backups_root=backups,
        releases_root=releases,
        protected_backup_ids=frozenset(),
        protected_release_versions=frozenset(),
    )

    assert "0.3.1" not in result.removed_releases
    assert (releases / "0.3.1").is_dir()
    assert (tmp_path / "current").resolve() == releases / "0.3.1"


def test_retention_fails_closed_for_escaping_current_release_link(tmp_path: Path) -> None:
    backups = tmp_path / "backups"
    releases = tmp_path / "releases"
    outside = tmp_path / "outside"
    backups.mkdir()
    releases.mkdir()
    outside.mkdir()
    _release(releases, "0.4.1")
    (tmp_path / "current").symlink_to(outside, target_is_directory=True)

    try:
        enforce_retention(
            backups_root=backups,
            releases_root=releases,
            protected_backup_ids=frozenset(),
            protected_release_versions=frozenset(),
        )
    except RuntimeError as exc:
        assert "current release target is unsafe" in str(exc)
    else:
        raise AssertionError("escaping current release target was accepted")
    assert (releases / "0.4.1").is_dir()


def test_retention_orders_release_candidates_before_the_stable_release() -> None:
    versions = [
        "0.2.10+dev.9",
        "0.3.0-alpha.9",
        "0.3.0-alpha.10",
        "0.3.0-beta.2",
        "0.3.0-beta.11",
        "0.3.0rc1",
        "0.3.0rc2",
        "0.3.0",
    ]

    assert sorted(versions, key=_version_key) == versions


def test_retention_normalizes_rc_and_ignores_build_metadata() -> None:
    assert _version_key("0.3.0rc1") == _version_key("0.3.0-rc.1")
    assert _version_key("0.3.0+build.1") == _version_key("0.3.0+build.2")


def test_retention_rejects_numeric_prerelease_leading_zero() -> None:
    with pytest.raises(ValueError, match="leading zero"):
        _version_key("0.3.0-alpha.01")
