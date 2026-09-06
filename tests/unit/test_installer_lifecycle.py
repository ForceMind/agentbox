from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import tarfile
from pathlib import Path

import pytest
from agentbox_installer.artifact import (
    ArtifactError,
    ReleaseManifest,
    remove_verified_tree,
    sha256_file,
)
from agentbox_installer.host import HostMutationError, HostOperations
from agentbox_installer.layout import DIRECTORIES, InstallLayout
from agentbox_installer.lifecycle import (
    AgentBoxInstaller,
    InstallError,
    RollbackVerificationError,
    RollbackVerifiedError,
    _compare_versions,
)
from support.failure_injection import FailureInjector, InjectedCrash


def _artifact(
    tmp_path: Path, version: str, revision: str, *, real_migrations: bool = False
) -> tuple[Path, str]:
    files = {
        "alembic.ini": b"[alembic]\nscript_location = migrations\n",
        "migrations/README": b"fixture\n",
        "web/dist/index.html": b"<!doctype html><title>AgentBox</title>\n",
        "wheelhouse/agentbox-0.2.0-py3-none-any.whl": b"fixture-wheel\n",
    }
    if real_migrations:
        files["alembic.ini"] = Path("alembic.ini").read_bytes()
        files.update({str(path): path.read_bytes() for path in Path("migrations").rglob("*.py")})
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


def test_waw_binding_store_layout_is_runtime_private() -> None:
    binding_store = next(spec for spec in DIRECTORIES if spec.path.endswith("/bindings-v1"))

    assert binding_store.path == "/var/lib/agentbox-waw/bindings-v1"
    assert (binding_store.owner, binding_store.group, binding_store.mode) == (
        "agentbox-runtime",
        "agentbox-runtime",
        0o700,
    )


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
    assert stat_mode(layout.map("/var/lib/agentbox-waw")) == 0o750
    assert stat_mode(layout.map("/var/lib/agentbox-waw/runtime-epoch-v1")) == 0o700
    assert stat_mode(layout.map("/var/lib/agentbox-waw/bindings-v1")) == 0o700
    assert layout.map("/var/lib/agentbox-waw/runtime-epoch-v1/epoch.json").read_text() == (
        '{"epoch":"1","schema_version":"waw-runtime-epoch-v1"}'
    )
    secret_before = layout.map("/etc/agentbox/environment").read_bytes()
    config = layout.map("/etc/agentbox/agentbox.toml")
    config.write_text(config.read_text() + "session_ttl = 7200\n", encoding="utf-8")
    project = layout.map("/srv/agentbox/projects/preserved.txt")
    project.write_text("preserve me", encoding="utf-8")
    provider_store = layout.map(
        "/home/agentbox-runtime/.local/share/agentbox/provider-secrets/v1/store.sqlite3"
    )
    provider_store.parent.mkdir(parents=True)
    provider_store.write_bytes(b"synthetic-secret-store-preservation-canary")
    with sqlite3.connect(layout.database) as connection:
        connection.execute("CREATE TABLE admin_fixture(value TEXT)")
        connection.execute("INSERT INTO admin_fixture VALUES ('preserved')")

    epoch_path = layout.map("/var/lib/agentbox-waw/runtime-epoch-v1/epoch.json")
    epoch_path.write_text('{"epoch":"2","schema_version":"waw-runtime-epoch-v1"}')
    epoch_path.chmod(0o600)

    second = installer.apply(artifact, digest)
    third = installer.apply(artifact, digest)

    assert first.changed is True
    assert second.changed is False
    assert third.changed is False
    assert layout.map("/etc/agentbox/environment").read_bytes() == secret_before
    secret_value = next(
        line.split("=", 1)[1]
        for line in secret_before.decode("utf-8").splitlines()
        if line.startswith("AGENTBOX_SECRET_KEY=")
    )
    assert len(secret_value.encode("utf-8")) >= 32
    assert stat_mode(layout.map("/etc/agentbox/environment")) == 0o600
    assert secret_value not in layout.journal.read_text(encoding="utf-8")
    assert secret_value not in layout.receipt.read_text(encoding="utf-8")
    assert "session_ttl = 7200" in config.read_text()
    assert project.read_text() == "preserve me"
    assert provider_store.read_bytes() == b"synthetic-secret-store-preservation-canary"
    with sqlite3.connect(layout.database) as connection:
        assert connection.execute("SELECT value FROM admin_fixture").fetchone() == ("preserved",)
    assert stat_mode(layout.map("/var/lib/agentbox")) == 0o1770
    assert stat_mode(layout.map("/srv/agentbox/projects")) == 0o700
    assert stat_mode(layout.map("/run/agentbox")) == 0o3770
    assert stat_mode(layout.map("/var/lib/agentbox-waw")) == 0o750
    assert stat_mode(layout.map("/var/lib/agentbox-waw/runtime-epoch-v1")) == 0o700
    assert stat_mode(layout.map("/var/lib/agentbox-waw/bindings-v1")) == 0o700
    assert epoch_path.read_text() == ('{"epoch":"2","schema_version":"waw-runtime-epoch-v1"}')


@pytest.mark.parametrize(
    "content",
    (
        '{"epoch":"0","schema_version":"waw-runtime-epoch-v1"}',
        '{"epoch":"01","schema_version":"waw-runtime-epoch-v1"}',
        '{"epoch":"1","schema_version":"wrong"}',
        '{"epoch":"1","schema_version":"waw-runtime-epoch-v1","extra":true}',
        '{"epoch":"1","epoch":"2","schema_version":"waw-runtime-epoch-v1"}',
    ),
)
def test_waw_epoch_provisioning_rejects_malformed_existing_counter(
    tmp_path: Path, content: str
) -> None:
    installer, layout = _installer(tmp_path)
    installer._ensure_directories()
    path = layout.map("/var/lib/agentbox-waw/runtime-epoch-v1/epoch.json")
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(InstallError, match="epoch file is invalid"):
        installer._ensure_waw_epoch(allow_bootstrap=False)


def test_waw_epoch_provisioning_rejects_missing_counter_after_enrollment(tmp_path: Path) -> None:
    installer, _layout = _installer(tmp_path)
    installer._ensure_directories()
    with pytest.raises(InstallError, match="missing after enrollment"):
        installer._ensure_waw_epoch(allow_bootstrap=False)


def test_waw_epoch_provisioning_rejects_symlink_counter(tmp_path: Path) -> None:
    installer, layout = _installer(tmp_path)
    installer._ensure_directories()
    path = layout.map("/var/lib/agentbox-waw/runtime-epoch-v1/epoch.json")
    target = path.parent / "other.json"
    target.write_text('{"epoch":"1","schema_version":"waw-runtime-epoch-v1"}')
    path.symlink_to(target.name)
    with pytest.raises(InstallError, match="epoch file is unsafe"):
        installer._ensure_waw_epoch(allow_bootstrap=True)


@pytest.mark.parametrize(
    ("older", "newer"),
    (
        ("0.3.0-alpha.9", "0.3.0-alpha.10"),
        ("0.3.0-alpha", "0.3.0-alpha.1"),
        ("0.3.0-alpha.1", "0.3.0-alpha.beta"),
        ("0.3.0-beta.2", "0.3.0-beta.11"),
        ("0.3.0-beta", "0.3.0-rc.1"),
        ("0.3.0rc9", "0.3.0rc10"),
        ("0.3.0rc2", "0.3.0"),
    ),
)
def test_release_prerelease_identifiers_follow_numeric_semver_precedence(
    older: str, newer: str
) -> None:
    assert _compare_versions(older, newer) == -1
    assert _compare_versions(newer, older) == 1


def test_release_candidate_rc_and_build_metadata_normalization() -> None:
    assert _compare_versions("0.3.0rc1", "0.3.0-rc.1") == 0
    assert _compare_versions("0.3.0+build.1", "0.3.0+build.2") == 0
    assert _compare_versions("0.2.10+dev.9", "0.2.10+dev.8") == 0


@pytest.mark.parametrize(
    "version",
    ("0.3.0-alpha.01", "0.3", "0.3.0-alpha..1", "01.3.0", "not-a-version"),
)
def test_release_version_comparison_rejects_malformed_versions(version: str) -> None:
    with pytest.raises(InstallError, match="release version is invalid"):
        _compare_versions(version, "0.3.0")


def test_installer_plan_and_apply_accept_numeric_prerelease_upgrade_and_reject_downgrade(
    tmp_path: Path,
) -> None:
    installer, _layout = _installer(tmp_path)
    alpha_nine, alpha_nine_digest = _artifact(tmp_path, "0.3.0-alpha.9", "revision_one")
    alpha_ten, alpha_ten_digest = _artifact(tmp_path, "0.3.0-alpha.10", "revision_two")
    installer.apply(alpha_nine, alpha_nine_digest)

    assert installer.plan(alpha_ten, alpha_ten_digest).state == "installed_older_version"
    assert installer.apply(alpha_ten, alpha_ten_digest).version == "0.3.0-alpha.10"
    assert installer.plan(alpha_ten, alpha_ten_digest).state == "installed_same_version"
    assert installer.apply(alpha_ten, alpha_ten_digest).changed is False
    assert installer.plan(alpha_nine, alpha_nine_digest).state == "installed_newer_version"
    with pytest.raises(InstallError, match="downgrade is not supported"):
        installer.apply(alpha_nine, alpha_nine_digest)


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


class PartiallyFailingMigrationInstaller(AgentBoxInstaller):
    fail_revision: str | None = None

    def _run_migration(self, manifest: ReleaseManifest) -> None:
        if manifest.database_revision == self.fail_revision:
            with sqlite3.connect(self.layout.database) as connection:
                connection.execute("CREATE TABLE partial_mutation(value TEXT)")
                connection.execute("DELETE FROM alembic_version")
                connection.execute(
                    "INSERT INTO alembic_version(version_num) VALUES (?)",
                    (manifest.database_revision,),
                )
            raise RuntimeError("injected partial migration failure")
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


def test_partially_applied_migration_restores_snapshot_before_binary_rollback(
    tmp_path: Path,
) -> None:
    base, layout = _installer(tmp_path)
    installer = PartiallyFailingMigrationInstaller(layout, base.host)
    first_artifact, first_digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    second_artifact, second_digest = _artifact(tmp_path, "0.2.1+dev.8", "revision_two")
    installer.apply(first_artifact, first_digest)
    installer.fail_revision = "revision_two"

    with pytest.raises(RollbackVerifiedError, match="rollback verified"):
        installer.apply(second_artifact, second_digest)

    assert installer.current_version() == "0.2.0+dev.8"
    with sqlite3.connect(layout.database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "revision_one",
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name='partial_mutation'"
        ).fetchone() == (0,)


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
    provider_store = layout.map(
        "/home/agentbox-runtime/.local/share/agentbox/provider-secrets/v1/store.sqlite3"
    )
    provider_store.parent.mkdir(parents=True)
    provider_store.write_bytes(b"synthetic-secret-store-preservation-canary")
    config_before = layout.map("/etc/agentbox/agentbox.toml").read_bytes()
    database_before = layout.database.read_bytes()

    result = installer.uninstall()

    assert result["purge"] == "not_available"
    assert installer.installation_state() == "uninstalled_data_preserved"
    assert not layout.current_link.exists()
    assert list(layout.map("/opt/agentbox/releases").iterdir()) == []
    assert project.read_text() == "preserved"
    assert (runtime_auth / "fixture").read_text() == "preserved"
    assert provider_store.read_bytes() == b"synthetic-secret-store-preservation-canary"
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


def test_uninstall_preflights_every_managed_object_before_stopping_services(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installer, layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    installer.apply(artifact, digest)
    unit = layout.map("/etc/systemd/system/agentbox-worker.service")
    unit.write_text("[Service]\nExecStart=/modified\n", encoding="utf-8")
    stopped = False

    def disable_and_stop() -> None:
        nonlocal stopped
        stopped = True

    monkeypatch.setattr(installer.host, "disable_and_stop", disable_and_stop)

    with pytest.raises(InstallError, match="modified or unsafe systemd unit"):
        installer.uninstall()

    assert stopped is False
    assert installer.current_version() == "0.2.0+dev.8"
    assert layout.current_link.is_symlink()
    assert layout.release("0.2.0+dev.8").is_dir()


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
    assert journal["schema_version"] == 2
    assert len(journal["transaction_id"]) == 32
    assert all(
        {"expected_path", "expected_type", "existed_before", "initial_identity", "created_identity"}
        <= set(resource)
        for resource in journal["resources"]
    )


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


def test_rollback_rejects_retained_release_other_than_receipt_previous(
    tmp_path: Path,
) -> None:
    installer, layout = _installer(tmp_path)
    releases = [
        _artifact(tmp_path, "0.2.0+dev.8", "revision_one"),
        _artifact(tmp_path, "0.2.1+dev.8", "revision_two"),
        _artifact(tmp_path, "0.2.2+dev.8", "revision_three"),
    ]
    for artifact, digest in releases:
        installer.apply(artifact, digest)

    with pytest.raises(InstallError, match="must match the receipt's previous release"):
        installer.rollback("0.2.0+dev.8")

    assert installer.current_version() == "0.2.2+dev.8"
    assert layout.database.is_file()


def test_rollback_backup_metadata_must_match_direct_previous_release(
    tmp_path: Path,
) -> None:
    installer, layout = _installer(tmp_path)
    first_artifact, first_digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    second_artifact, second_digest = _artifact(tmp_path, "0.2.1+dev.8", "revision_two")
    installer.apply(first_artifact, first_digest)
    installer.apply(second_artifact, second_digest)
    receipt = json.loads(layout.receipt.read_text(encoding="utf-8"))
    backup_manifest = layout.backups / str(receipt["pre_change_backup_id"]) / "manifest.json"
    manifest = json.loads(backup_manifest.read_text(encoding="utf-8"))
    manifest["application_version"] = "0.1.9"
    backup_manifest.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    receipt["pre_change_backup_manifest_sha256"] = installer._digest(backup_manifest)
    layout.receipt.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(InstallError, match="not bound to the rollback target"):
        installer.rollback()

    assert installer.current_version() == "0.2.1+dev.8"


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o7777


@pytest.mark.parametrize(
    "managed_parent",
    [
        "/var/lib/agentbox",
        "/opt/agentbox",
        "/srv/agentbox",
    ],
)
def test_installer_rejects_symlink_in_any_privileged_parent_chain(
    tmp_path: Path, managed_parent: str
) -> None:
    installer, layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    outside = tmp_path / "outside"
    outside.mkdir()
    parent = layout.map(managed_parent)
    parent.parent.mkdir(parents=True, exist_ok=True)
    parent.symlink_to(outside, target_is_directory=True)

    with pytest.raises(InstallError, match="unsafe|refusing symlink"):
        installer.apply(artifact, digest)

    assert list(outside.iterdir()) == []


def test_current_release_requires_exact_relative_root_owned_layout(tmp_path: Path) -> None:
    installer, layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    installer.apply(artifact, digest)
    layout.current_link.unlink()
    layout.current_link.symlink_to(layout.release("0.2.0+dev.8"))

    assert installer.current_version() is None
    assert installer.installation_state() == "partial_or_broken"


@pytest.mark.parametrize(
    ("completed", "expected"),
    [
        (["release_staged"], "staged"),
        (["release_staged", "database_migrated"], "partially_migrated"),
        ([], "preflight_interrupted"),
        (["unexpected_step"], "unknown"),
    ],
)
def test_unfinished_transaction_states_fail_closed(
    tmp_path: Path, completed: list[str], expected: str
) -> None:
    installer, layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    installer.apply(artifact, digest)
    journal = json.loads(layout.journal.read_text(encoding="utf-8"))
    journal["status"] = "running"
    journal["completed_steps"] = completed
    layout.journal.write_text(json.dumps(journal), encoding="utf-8")

    assert installer.installation_state() == expected
    with pytest.raises(InstallError, match=f"recovery state is {expected}"):
        installer.apply(artifact, digest)


@pytest.mark.parametrize(
    ("journal_content", "message"),
    [
        ("{not-json", "journal is corrupt"),
        ('{"schema_version": 999}', "journal schema is unsupported"),
    ],
)
def test_corrupt_or_unknown_installer_journal_fails_closed(
    tmp_path: Path, journal_content: str, message: str
) -> None:
    installer, layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    installer.apply(artifact, digest)
    layout.journal.write_text(journal_content, encoding="utf-8")

    with pytest.raises(InstallError, match=message):
        installer.installation_state()


def test_real_host_journal_reader_requires_root_owned_mode_0600(tmp_path: Path) -> None:
    installer, layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    installer.apply(artifact, digest)
    layout.journal.chmod(0o640)
    real_host_reader = AgentBoxInstaller(layout, HostOperations(real_host=True))

    with pytest.raises(InstallError, match="journal permissions are unsafe"):
        real_host_reader.installation_state()


def test_power_loss_after_activation_is_detected_without_reapplying_mutation(
    tmp_path: Path,
) -> None:
    installer, layout = _installer(tmp_path)
    first_artifact, first_digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    second_artifact, second_digest = _artifact(tmp_path, "0.2.1+dev.8", "revision_two")
    installer.apply(first_artifact, first_digest)
    manifest = installer._stage_release(second_artifact, second_digest)
    installer._activate(manifest.version)
    journal = json.loads(layout.journal.read_text(encoding="utf-8"))
    journal["status"] = "running"
    journal["version"] = manifest.version
    journal["completed_steps"] = ["database_migrated", "release_activated"]
    layout.journal.write_text(json.dumps(journal), encoding="utf-8")

    assert installer.installation_state() == "activated"
    with pytest.raises(InstallError, match="recovery state is activated"):
        installer.apply(second_artifact, second_digest)


def test_conflicting_staged_release_is_rejected_before_transaction_journal_changes(
    tmp_path: Path,
) -> None:
    installer, layout = _installer(tmp_path)
    first_artifact, first_digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    installer.apply(first_artifact, first_digest)
    journal_before = layout.journal.read_bytes()
    staged_artifact, staged_digest = _artifact(tmp_path, "0.2.1+dev.8", "revision_two")
    installer._stage_release(staged_artifact, staged_digest)
    conflicting_artifact, conflicting_digest = _artifact(tmp_path, "0.2.1+dev.8", "revision_three")

    with pytest.raises(InstallError, match="existing release does not match"):
        installer.apply(conflicting_artifact, conflicting_digest)

    assert installer.current_version() == "0.2.0+dev.8"
    assert layout.journal.read_bytes() == journal_before


def test_failed_rollback_state_is_reported_as_pending(tmp_path: Path) -> None:
    installer, layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    installer.apply(artifact, digest)
    journal = json.loads(layout.journal.read_text(encoding="utf-8"))
    journal["status"] = "rollback_verification_failed"
    layout.journal.write_text(json.dumps(journal), encoding="utf-8")

    assert installer.installation_state() == "rollback_pending"


def test_preflight_recovery_requires_known_current_database_and_health(
    tmp_path: Path,
) -> None:
    installer, layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    installer.apply(artifact, digest)
    journal = json.loads(layout.journal.read_text(encoding="utf-8"))
    journal["status"] = "running"
    journal["completed_steps"] = ["identities", "directories", "configuration"]
    layout.journal.write_text(json.dumps(journal), encoding="utf-8")

    assert installer.installation_state() == "preflight_interrupted"
    result = installer.recover()

    assert result.health_verified is True
    assert installer.installation_state() == "installed"
    recovered = json.loads(layout.journal.read_text(encoding="utf-8"))
    assert recovered["status"] == "rollback_verified"
    assert "preflight_recovery_verified" in recovered["completed_steps"]


def test_legacy_database_layout_boundary_is_versioned() -> None:
    assert AgentBoxInstaller._uses_legacy_database_layout("0.2.4+dev.8") is True
    assert AgentBoxInstaller._uses_legacy_database_layout("0.2.5+dev.8") is False


def test_operator_recovery_verifies_known_current_release_without_replay(
    tmp_path: Path,
) -> None:
    installer, layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    installer.apply(artifact, digest)
    journal = json.loads(layout.journal.read_text(encoding="utf-8"))
    journal["status"] = "rollback_verification_failed"
    layout.journal.write_text(json.dumps(journal), encoding="utf-8")

    result = installer.recover()

    assert result.changed is False
    assert result.version == "0.2.0+dev.8"
    assert result.health_verified is True
    assert installer.installation_state() == "installed"
    assert stat_mode(layout.map("/var/lib/agentbox")) == 0o1770
    recovered = json.loads(layout.journal.read_text(encoding="utf-8"))
    assert recovered["transaction_id"] == journal["transaction_id"]
    assert recovered["status"] == "rollback_verified"
    assert "operator_recovery_verified" in recovered["completed_steps"]


def test_operator_recovery_rejects_untrusted_journal_identity(tmp_path: Path) -> None:
    installer, layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    installer.apply(artifact, digest)
    journal = json.loads(layout.journal.read_text(encoding="utf-8"))
    journal["status"] = "rollback_verification_failed"
    journal["transaction_id"] = "../../untrusted"
    layout.journal.write_text(json.dumps(journal), encoding="utf-8")

    with pytest.raises(InstallError, match="recovery identity is invalid"):
        installer.recover()


class RollbackProbeHost(HostOperations):
    def __init__(self) -> None:
        super().__init__(real_host=False)
        self.fail_restart = False
        self.ready = True

    def restart_agentbox(self) -> None:
        if self.fail_restart:
            raise HostMutationError("injected service restart failure")

    def deployment_ready(self) -> bool:
        return self.ready


class RollbackProbeInstaller(AgentBoxInstaller):
    failed_verification: str | None = None

    def health_check(self, expected_version: str | None = None) -> bool:
        if self.failed_verification in {"healthz", "readyz", "reported_version"}:
            return False
        return super().health_check(expected_version=expected_version)

    def _database_integrity_and_revision(self, expected_revision: str | None) -> bool:
        if self.failed_verification == "database_integrity":
            return False
        return super()._database_integrity_and_revision(expected_revision)


def test_operator_recovery_restart_failure_remains_pending(tmp_path: Path) -> None:
    _base, layout = _installer(tmp_path)
    host = RollbackProbeHost()
    installer = RollbackProbeInstaller(layout, host)
    artifact, digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    installer.apply(artifact, digest)
    journal = json.loads(layout.journal.read_text(encoding="utf-8"))
    journal["status"] = "rollback_verification_failed"
    layout.journal.write_text(json.dumps(journal), encoding="utf-8")
    host.fail_restart = True

    with pytest.raises(RollbackVerificationError, match="verification failed"):
        installer.recover()

    assert installer.installation_state() == "rollback_pending"
    assert json.loads(layout.journal.read_text())["status"] == "rollback_verification_failed"


def _upgraded_installer(
    tmp_path: Path,
) -> tuple[RollbackProbeInstaller, InstallLayout, RollbackProbeHost]:
    base, layout = _installer(tmp_path)
    host = RollbackProbeHost()
    installer = RollbackProbeInstaller(layout, host)
    first_artifact, first_digest = _artifact(tmp_path, "0.2.0+dev.8", "revision_one")
    second_artifact, second_digest = _artifact(tmp_path, "0.2.1+dev.8", "revision_two")
    installer.apply(first_artifact, first_digest)
    installer.apply(second_artifact, second_digest)
    return installer, layout, host


@pytest.mark.parametrize(
    "failed_verification",
    ["healthz", "readyz", "reported_version", "database_integrity"],
)
def test_rollback_never_reports_verified_when_a_required_probe_fails(
    tmp_path: Path, failed_verification: str
) -> None:
    installer, layout, _host = _upgraded_installer(tmp_path)
    installer.failed_verification = failed_verification

    with pytest.raises(RollbackVerificationError, match="verification failed"):
        installer.rollback()

    journal = json.loads(layout.journal.read_text(encoding="utf-8"))
    assert journal["status"] == "rollback_verification_failed"


def test_rollback_restart_failure_is_attempted_but_never_reported_verified(
    tmp_path: Path,
) -> None:
    installer, layout, host = _upgraded_installer(tmp_path)
    host.fail_restart = True

    with pytest.raises(RollbackVerificationError, match="verification failed"):
        installer.rollback()

    assert json.loads(layout.journal.read_text())["status"] == "rollback_verification_failed"


@pytest.mark.parametrize("failed_component", ["runtime_socket", "helper_socket"])
def test_rollback_socket_or_helper_readiness_failure_is_not_a_false_positive(
    tmp_path: Path, failed_component: str
) -> None:
    installer, layout, host = _upgraded_installer(tmp_path)
    host.ready = False

    with pytest.raises(RollbackVerificationError, match="verification failed"):
        installer.rollback()

    assert failed_component in {"runtime_socket", "helper_socket"}
    assert json.loads(layout.journal.read_text())["status"] == "rollback_verification_failed"


def test_rollback_rejects_missing_release_before_stopping_services(tmp_path: Path) -> None:
    installer, layout, _host = _upgraded_installer(tmp_path)
    remove_verified_tree(layout.release("0.2.0+dev.8"))

    with pytest.raises(ArtifactError, match="release root is unavailable"):
        installer.rollback()

    assert installer.current_version() == "0.2.1+dev.8"


def test_rollback_rejects_corrupt_backup_before_stopping_services(tmp_path: Path) -> None:
    installer, layout, _host = _upgraded_installer(tmp_path)
    receipt = json.loads(layout.receipt.read_text(encoding="utf-8"))
    backup_database = layout.backups / str(receipt["pre_change_backup_id"]) / "agentbox.db"
    backup_database.write_bytes(b"corrupt")

    with pytest.raises(InstallError, match="backup verification failed"):
        installer.rollback()

    assert installer.current_version() == "0.2.1+dev.8"


@pytest.mark.parametrize(
    ("point", "target", "attribute", "expected_state"),
    [
        ("after_users", "host", "ensure_identities", "preflight_interrupted"),
        ("after_dirs", "installer", "_ensure_directories", "preflight_interrupted"),
        ("after_config", "installer", "_write_initial_configuration", "preflight_interrupted"),
        ("after_release_extraction", "installer", "_stage_release", "staged"),
        ("after_migration", "installer", "_run_migration", "partially_migrated"),
        ("after_current_symlink", "installer", "_activate", "activated"),
        ("after_daemon_reload", "host", "daemon_reload", "activated"),
        ("after_service_start", "host", "enable_and_start", "activated"),
        ("before_health_verification", "installer", "health_check", "activated"),
    ],
)
def test_test_only_installer_crash_matrix_is_classified_without_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    point: str,
    target: str,
    attribute: str,
    expected_state: str,
) -> None:
    installer, _layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.2.0+dev.9", "0003_security_hardening")
    injector = FailureInjector(point)
    owner = installer if target == "installer" else installer.host
    monkeypatch.setattr(owner, attribute, injector.after(point, getattr(owner, attribute)))

    with pytest.raises(InjectedCrash, match=point):
        installer.apply(artifact, digest)

    assert installer.installation_state() == expected_state
    with pytest.raises(InstallError, match=f"recovery state is {expected_state}"):
        installer.apply(artifact, digest)


def test_upgrade_crash_after_backup_preserves_old_release_and_stops_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer, _layout = _installer(tmp_path)
    first, first_digest = _artifact(tmp_path, "0.2.0+dev.9", "revision_one")
    second, second_digest = _artifact(tmp_path, "0.2.1+dev.9", "revision_two")
    installer.apply(first, first_digest)
    injector = FailureInjector("after_backup")
    monkeypatch.setattr(
        installer,
        "_backup_before_change",
        injector.after("after_backup", installer._backup_before_change),
    )

    with pytest.raises(InjectedCrash, match="after_backup"):
        installer.apply(second, second_digest)

    assert installer.current_version() == "0.2.0+dev.9"
    assert installer.installation_state() == "staged"
    with pytest.raises(InstallError, match="recovery state is staged"):
        installer.apply(second, second_digest)


@pytest.mark.parametrize(
    ("point", "target", "attribute", "expected_version", "expected_state"),
    [
        ("upgrade_stage", "installer", "_stage_release", "0.2.0+dev.9", "staged"),
        ("upgrade_backup", "installer", "_backup_before_change", "0.2.0+dev.9", "staged"),
        (
            "upgrade_migration",
            "installer",
            "_run_migration",
            "0.2.0+dev.9",
            "partially_migrated",
        ),
        ("upgrade_activate", "installer", "_activate", "0.2.1+dev.9", "activated"),
        ("upgrade_restart", "host", "enable_and_start", "0.2.1+dev.9", "activated"),
        ("upgrade_health", "installer", "health_check", "0.2.1+dev.9", "activated"),
        ("upgrade_receipt", "installer", "_write_receipt", "0.2.1+dev.9", "activated"),
    ],
)
def test_upgrade_crash_matrix_is_classified_without_mutation_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    point: str,
    target: str,
    attribute: str,
    expected_version: str,
    expected_state: str,
) -> None:
    installer, _layout = _installer(tmp_path)
    first, first_digest = _artifact(tmp_path, "0.2.0+dev.9", "revision_one")
    second, second_digest = _artifact(tmp_path, "0.2.1+dev.9", "revision_two")
    installer.apply(first, first_digest)
    injector = FailureInjector(point)
    owner = installer if target == "installer" else installer.host
    monkeypatch.setattr(owner, attribute, injector.after(point, getattr(owner, attribute)))

    with pytest.raises(InjectedCrash, match=point):
        installer.apply(second, second_digest)

    assert installer.current_version() == expected_version
    assert installer.installation_state() == expected_state
    with pytest.raises(InstallError, match=f"recovery state is {expected_state}"):
        installer.apply(second, second_digest)


def test_crash_after_committed_journal_is_a_completed_idempotent_upgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer, _layout = _installer(tmp_path)
    first, first_digest = _artifact(tmp_path, "0.2.0+dev.9", "revision_one")
    second, second_digest = _artifact(tmp_path, "0.2.1+dev.9", "revision_two")
    installer.apply(first, first_digest)
    original = installer._write_journal

    def crash_after_commit(**values: object) -> None:
        original(**values)  # type: ignore[arg-type]
        if values.get("status") == "committed":
            raise InjectedCrash("injected crash at upgrade_commit")

    monkeypatch.setattr(installer, "_write_journal", crash_after_commit)
    with pytest.raises(InjectedCrash, match="upgrade_commit"):
        installer.apply(second, second_digest)

    assert installer.current_version() == "0.2.1+dev.9"
    assert installer.installation_state() == "installed"
    monkeypatch.setattr(installer, "_write_journal", original)
    result = installer.apply(second, second_digest)
    assert result.changed is False


def test_release_staging_disk_full_never_replaces_current_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer, _layout = _installer(tmp_path)
    first, first_digest = _artifact(tmp_path, "0.2.0+dev.9", "revision_one")
    second, second_digest = _artifact(tmp_path, "0.2.1+dev.9", "revision_two")
    installer.apply(first, first_digest)

    def disk_full(_artifact: Path, _digest: str) -> ReleaseManifest:
        raise OSError(28, "fixture disk full")

    monkeypatch.setattr(installer, "_stage_release", disk_full)
    with pytest.raises(OSError, match="disk full"):
        installer.apply(second, second_digest)

    assert installer.current_version() == "0.2.0+dev.9"
    assert installer.installation_state() == "unknown"


class Phase11MigrationInstaller(AgentBoxInstaller):
    def _run_migration(self, manifest: ReleaseManifest) -> None:
        from conftest import migrate_database

        migrate_database(f"sqlite+pysqlite:///{self.layout.database}", manifest.database_revision)


@pytest.mark.parametrize("phase", ["before_commit", "after_commit"])
def test_phase11_exact_inventory_failure_restores_verified_predecessor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    import agentbox_core.migration_inventory as inventory
    from sqlalchemy.engine import Connection

    base, layout = _installer(tmp_path)
    installer = Phase11MigrationInstaller(layout, base.host)
    predecessor = "0004_phase11_provider_core"
    destination = "0005_phase11_control_plane_ownership_approval"
    first, first_digest = _artifact(tmp_path, "0.2.0+dev.8", predecessor)
    second, second_digest = _artifact(tmp_path, "0.2.1+dev.8", destination)
    installer.apply(first, first_digest)
    with sqlite3.connect(layout.database) as connection:
        before = tuple(connection.iterdump())
    verify = inventory.verify_phase11_inventory
    calls = 0
    failed_revision: str | None = None

    def corrupt(connection: Connection, revision: str, error: str) -> None:
        nonlocal calls, failed_revision
        if revision == destination:
            calls += 1
            if calls == (1 if phase == "before_commit" else 2):
                connection.exec_driver_sql("DROP INDEX ix_confirmation_challenges_terminal_at")
                # An independent connection distinguishes uncommitted from committed DDL/version.
                with sqlite3.connect(layout.database) as reader:
                    failed_revision = reader.execute(
                        "SELECT version_num FROM alembic_version"
                    ).fetchone()[0]
        verify(connection, revision, error)

    monkeypatch.setattr(inventory, "verify_phase11_inventory", corrupt)
    with pytest.raises(RollbackVerifiedError, match="rollback verified"):
        installer.apply(second, second_digest)
    assert calls == (1 if phase == "before_commit" else 2)
    assert failed_revision == (predecessor if phase == "before_commit" else destination)
    assert installer.current_version() == "0.2.0+dev.8"
    assert installer._database_integrity_and_revision(predecessor)
    with sqlite3.connect(layout.database) as connection:
        assert tuple(connection.iterdump()) == before
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA quick_check").fetchall() == [("ok",)]
    assert not Path(f"{layout.database}-wal").exists()
    assert not Path(f"{layout.database}-shm").exists()


def test_phase11_restore_gate_rejects_same_version_schema_drift(tmp_path: Path) -> None:
    from conftest import migrate_database

    installer, layout = _installer(tmp_path)
    layout.database.parent.mkdir(parents=True)
    predecessor = "0004_phase11_provider_core"
    migrate_database(f"sqlite+pysqlite:///{layout.database}", predecessor)
    assert installer._database_integrity_and_revision(predecessor)
    with sqlite3.connect(layout.database) as connection:
        connection.execute("DROP INDEX ix_sessions_expires_at")
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert not installer._database_integrity_and_revision(predecessor)
    assert not installer._database_integrity_and_revision(None)


def test_phase11_fixture_install_uses_real_migrations_and_exact_gate(tmp_path: Path) -> None:
    installer, layout = _installer(tmp_path)
    artifact, digest = _artifact(
        tmp_path,
        "0.2.1+dev.8",
        "0005_phase11_control_plane_ownership_approval",
        real_migrations=True,
    )
    installer.apply(artifact, digest)
    assert installer._database_integrity_and_revision(
        "0005_phase11_control_plane_ownership_approval"
    )
    with sqlite3.connect(layout.database) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name='confirmation_challenges'"
        ).fetchone() == ("confirmation_challenges",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
