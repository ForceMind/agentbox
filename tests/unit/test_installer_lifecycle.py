from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import tarfile
from pathlib import Path

import pytest
from agentbox_installer.artifact import ReleaseManifest, sha256_file
from agentbox_installer.host import HostOperations
from agentbox_installer.layout import InstallLayout
from agentbox_installer.lifecycle import (
    AgentBoxInstaller,
    InstallError,
    RollbackVerificationError,
    RollbackVerifiedError,
)


def _artifact(tmp_path: Path, version: str, revision: str) -> tuple[Path, str]:
    files = {
        "alembic.ini": b"[alembic]\nscript_location = migrations\n",
        "migrations/README": b"fixture\n",
        "web/dist/index.html": b"<!doctype html><title>AgentBox</title>\n",
        "wheelhouse/agentbox-0.2.0-py3-none-any.whl": b"fixture-wheel\n",
    }
    manifest = {
        "schema_version": 1,
        "version": version,
        "database_revision": revision,
        "database_backward_compatible": False,
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
    }
    artifact = tmp_path / f"agentbox-{version}.tar.gz"
    with tarfile.open(artifact, "w:gz") as archive:
        for name, content in {
            **files,
            "manifest.json": json.dumps(manifest, sort_keys=True).encode() + b"\n",
        }.items():
            member = tarfile.TarInfo(name)
            member.mode = 0o644
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return artifact, sha256_file(artifact)


def _installer(tmp_path: Path) -> tuple[AgentBoxInstaller, InstallLayout]:
    root = tmp_path / "root"
    (root / "etc").mkdir(parents=True)
    (root / "etc/os-release").write_text('ID="opencloudos"\nVERSION_ID="9.4"\n', encoding="utf-8")
    layout = InstallLayout(root)
    return AgentBoxInstaller(layout, HostOperations(real_host=False)), layout


def test_fresh_install_and_reinstall_are_idempotent_and_preserve_data(tmp_path: Path) -> None:
    installer, layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.2.0+dev.8", "0002_project_jobs")

    plan = installer.plan(artifact, digest)
    assert plan.state == "not_installed"
    assert plan.bind == "127.0.0.1:8787"
    assert "git" in plan.package_changes
    assert sorted(path.relative_to(layout.root).as_posix() for path in layout.root.rglob("*")) == [
        "etc",
        "etc/os-release",
    ]
    first = installer.apply(artifact, digest)
    secret_before = layout.map("/etc/agentbox/environment").read_bytes()
    config = layout.map("/etc/agentbox/agentbox.toml")
    config.write_text(config.read_text() + "session_ttl = 7200\n", encoding="utf-8")
    project = layout.map("/srv/agentbox/projects/preserved.txt")
    project.write_text("preserve me", encoding="utf-8")
    with sqlite3.connect(layout.database) as connection:
        connection.execute("CREATE TABLE admin_fixture(value TEXT)")
        connection.execute("INSERT INTO admin_fixture VALUES ('preserved')")

    second = installer.apply(artifact, digest)

    assert first.changed is True
    assert second.changed is False
    assert layout.map("/etc/agentbox/environment").read_bytes() == secret_before
    assert "session_ttl = 7200" in config.read_text()
    assert project.read_text() == "preserve me"
    with sqlite3.connect(layout.database) as connection:
        assert connection.execute("SELECT value FROM admin_fixture").fetchone() == ("preserved",)
    assert stat_mode(layout.map("/var/lib/agentbox")) == 0o700
    assert stat_mode(layout.map("/srv/agentbox/projects")) == 0o700
    assert stat_mode(layout.map("/run/agentbox")) == 0o2770


def test_upgrade_creates_verified_backup_and_rollback_restores_database(
    tmp_path: Path,
) -> None:
    installer, layout = _installer(tmp_path)
    first_artifact, first_digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    second_artifact, second_digest = _artifact(tmp_path, "0.2.1+dev.8", "revision_two")
    installer.apply(first_artifact, first_digest)
    with sqlite3.connect(layout.database) as connection:
        connection.execute("CREATE TABLE preserved(value TEXT)")
        connection.execute("INSERT INTO preserved VALUES ('before-upgrade')")

    upgrade = installer.apply(second_artifact, second_digest)
    rollback = installer.rollback()

    assert upgrade.backup_id is not None
    assert rollback.version == "0.2.0+dev.8"
    assert rollback.health_verified is True
    with sqlite3.connect(layout.database) as connection:
        assert connection.execute("SELECT value FROM preserved").fetchone() == ("before-upgrade",)


class FailingMigrationInstaller(AgentBoxInstaller):
    fail_revision: str | None = None

    def _run_migration(self, manifest: ReleaseManifest) -> None:
        if manifest.database_revision == self.fail_revision:
            raise RuntimeError("injected migration failure")
        super()._run_migration(manifest)


def test_failed_migration_rolls_back_and_verifies_previous_release(tmp_path: Path) -> None:
    base, layout = _installer(tmp_path)
    installer = FailingMigrationInstaller(layout, base.host)
    first_artifact, first_digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    second_artifact, second_digest = _artifact(tmp_path, "0.2.1+dev.8", "revision_two")
    installer.apply(first_artifact, first_digest)
    installer.fail_revision = "revision_two"

    with pytest.raises(RollbackVerifiedError, match="rollback verified"):
        installer.apply(second_artifact, second_digest)

    assert installer.current_version() == "0.2.0+dev.8"
    assert installer.health_check()


class HealthFailureInstaller(AgentBoxInstaller):
    fail_health = False

    def health_check(self, expected_version: str | None = None) -> bool:
        return (
            False if self.fail_health else super().health_check(expected_version=expected_version)
        )


def test_rollback_verification_failure_is_reported_truthfully(tmp_path: Path) -> None:
    base, layout = _installer(tmp_path)
    installer = HealthFailureInstaller(layout, base.host)
    first_artifact, first_digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    second_artifact, second_digest = _artifact(tmp_path, "0.2.1+dev.8", "revision_two")
    installer.apply(first_artifact, first_digest)
    installer.fail_health = True

    with pytest.raises(RollbackVerificationError, match="verification failed"):
        installer.apply(second_artifact, second_digest)


def test_directory_collision_fails_without_overwriting_unknown_file(tmp_path: Path) -> None:
    installer, layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    collision = layout.map("/etc/agentbox")
    collision.write_text("unknown", encoding="utf-8")

    with pytest.raises((InstallError, FileExistsError, NotADirectoryError)):
        installer.apply(artifact, digest)

    assert collision.read_text() == "unknown"


def test_uninstall_removes_only_program_files_and_preserves_all_data(tmp_path: Path) -> None:
    installer, layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    installer.apply(artifact, digest)
    project = layout.map("/srv/agentbox/projects/project-data")
    project.write_text("preserved")
    runtime_auth = layout.map("/home/agentbox-runtime/.codex")
    runtime_auth.mkdir()
    (runtime_auth / "fixture").write_text("preserved")
    config_before = layout.map("/etc/agentbox/agentbox.toml").read_bytes()
    database_before = layout.database.read_bytes()

    result = installer.uninstall()

    assert result["purge"] == "not_available"
    assert installer.installation_state() == "uninstalled_data_preserved"
    assert not layout.current_link.exists()
    assert list(layout.map("/opt/agentbox/releases").iterdir()) == []
    assert project.read_text() == "preserved"
    assert (runtime_auth / "fixture").read_text() == "preserved"
    assert layout.map("/etc/agentbox/agentbox.toml").read_bytes() == config_before
    assert layout.database.read_bytes() == database_before
    assert not any(
        layout.map(f"/etc/systemd/system/{name}").exists()
        for name in (
            "agentbox-api.service",
            "agentbox-worker.service",
            "agentbox-runtime.service",
            "agentbox-helper.socket",
            "agentbox-helper.service",
        )
    )


def test_fresh_install_refuses_unknown_unit_and_records_verified_cleanup(
    tmp_path: Path,
) -> None:
    installer, layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    unit_root = layout.map("/etc/systemd/system")
    unit_root.mkdir(parents=True)
    unknown = unit_root / "agentbox-api.service"
    unknown.write_text("[Service]\nExecStart=/bin/false\n")

    with pytest.raises(InstallError, match="unowned"):
        installer.apply(artifact, digest)

    assert unknown.read_text() == "[Service]\nExecStart=/bin/false\n"
    assert not layout.current_link.exists()
    assert not layout.database.exists()
    journal = json.loads(layout.journal.read_text())
    assert journal["status"] == "rollback_verified"
    assert journal["contains_secrets"] is False


def test_concurrent_lifecycle_transaction_is_rejected(tmp_path: Path) -> None:
    installer, _layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")

    with (
        installer._lifecycle_lock(),
        pytest.raises(InstallError, match="transaction is active"),
    ):
        installer.apply(artifact, digest)


def test_upgrade_rejects_externally_modified_managed_unit(tmp_path: Path) -> None:
    installer, layout = _installer(tmp_path)
    first_artifact, first_digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    second_artifact, second_digest = _artifact(tmp_path, "0.2.1+dev.8", "revision_two")
    installer.apply(first_artifact, first_digest)
    unit = layout.map("/etc/systemd/system/agentbox-api.service")
    unit.write_text("[Service]\nExecStart=/unknown\n", encoding="utf-8")

    with pytest.raises(RollbackVerifiedError, match="rollback verified"):
        installer.apply(second_artifact, second_digest)

    assert unit.read_text(encoding="utf-8") == "[Service]\nExecStart=/unknown\n"
    assert installer.current_version() == "0.2.0+dev.8"


@pytest.mark.parametrize("target", ["../../tmp/escape", "/tmp/escape", "not-semver"])
def test_rollback_rejects_untrusted_receipt_target(tmp_path: Path, target: str) -> None:
    installer, layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    installer.apply(artifact, digest)
    receipt = json.loads(layout.receipt.read_text(encoding="utf-8"))
    receipt["previous_version"] = target
    layout.receipt.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(InstallError, match="previous release"):
        installer.rollback()


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o7777
