from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from agentbox_installer import lifecycle
from agentbox_installer.cli import main
from agentbox_installer.host import HostMutationError
from agentbox_installer.layout import InstallLayout
from agentbox_installer.lifecycle import AgentBoxInstaller, InstallError
from agentbox_installer.platform import PlatformFacts, detect_platform
from pytest import MonkeyPatch
from test_installer_lifecycle import _artifact, _installer


@pytest.fixture(autouse=True)
def _server_fixture(monkeypatch: MonkeyPatch) -> None:
    def detect(path: Path) -> PlatformFacts:
        return detect_platform(path, architecture="x86_64")

    monkeypatch.setattr(lifecycle, "detect_platform", detect)


def _stage(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> tuple[AgentBoxInstaller, InstallLayout, Path, str]:
    installer, layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.3.0rc30", "revision_one")
    with monkeypatch.context() as scoped:

        def fail(_release: Path) -> None:
            raise HostMutationError("injected native build failure")

        scoped.setattr(installer.host, "prepare_waw_helpers", fail)
        with pytest.raises(HostMutationError, match="injected"):
            installer.apply(artifact, digest)
    assert installer.installation_state() == "staged"
    assert not layout.database.exists()
    return installer, layout, artifact, digest


def test_deferred_fresh_install_never_starts_legacy_services_and_pins_resume_mode(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    installer, layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.3.0rc30", "revision_one")

    def forbidden() -> None:
        raise AssertionError("deferred install must not start legacy services or probe live health")

    monkeypatch.setattr(installer.host, "enable_and_start", forbidden)
    monkeypatch.setattr(installer, "health_check", forbidden)
    with monkeypatch.context() as scoped:

        def fail(_release: Path) -> None:
            raise HostMutationError("injected native build failure")

        scoped.setattr(installer.host, "prepare_waw_helpers", fail)
        with pytest.raises(HostMutationError):
            installer.apply(artifact, digest, defer_activation=True)
    evidence = json.loads(layout.journal.read_text())["staging_recovery"]
    assert evidence["activation_policy"] == "deferred-v1"
    with pytest.raises(InstallError, match="activation policy"):
        installer.resume_install(artifact, digest)
    result = installer.resume_install(artifact, digest, defer_activation=True)
    assert result.health_verified is False
    assert installer.installation_state() == "installed"
    journal = json.loads(layout.journal.read_text())
    assert "activation_deferred" in journal["completed_steps"]
    assert "health_verified" not in journal["completed_steps"]
    with pytest.raises(InstallError, match="fresh"):
        installer.apply(artifact, digest, defer_activation=True)


def test_staged_resume_cli_requires_explicit_fixture_mode_and_returns_real_result(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _instance, layout, artifact, digest = _stage(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENTBOX_INSTALLER_TEST_MODE", "1")
    code = main(
        [
            "--fixture-root",
            str(layout.root),
            "resume-install",
            "--artifact",
            str(artifact),
            "--sha256",
            digest,
            "--json",
        ]
    )
    assert code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["version"] == "0.3.0rc30"
    assert result["health_verified"] is True
    assert json.loads(layout.journal.read_text())["status"] == "committed"


def test_explicit_staged_resume_keeps_identity_config_and_transaction(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    installer, layout, artifact, digest = _stage(tmp_path, monkeypatch)
    journal = json.loads(layout.journal.read_text())
    assert journal["schema_version"] == 3
    identity = journal["transaction_id"]
    environment = layout.map("/etc/agentbox/environment")
    before = hashlib.sha256(environment.read_bytes()).hexdigest()
    epoch = layout.map("/var/lib/agentbox-waw/runtime-epoch-v1/epoch.json")
    epoch_inode = epoch.stat().st_ino
    with pytest.raises(InstallError, match="recovery state"):
        installer.apply(artifact, digest)
    monkeypatch.setattr(
        installer.host, "ensure_identities", lambda *_args: pytest.fail("identities replayed")
    )
    monkeypatch.setattr(
        installer,
        "_write_initial_configuration",
        lambda *_args: pytest.fail("configuration replayed"),
    )
    assert installer.resume_install(artifact, digest).health_verified
    assert json.loads(layout.journal.read_text())["transaction_id"] == identity
    assert hashlib.sha256(environment.read_bytes()).hexdigest() == before
    assert epoch.stat().st_ino == epoch_inode
    assert installer.installation_state() == "installed"
    with pytest.raises(InstallError, match="no recovery evidence"):
        installer.resume_install(artifact, digest)


def test_repeated_staging_failure_retains_same_resume_proof(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    installer, layout, artifact, digest = _stage(tmp_path, monkeypatch)
    before = json.loads(layout.journal.read_text())
    with monkeypatch.context() as scoped:

        def fail(_release: Path) -> None:
            raise HostMutationError("another interrupted build")

        scoped.setattr(installer.host, "prepare_waw_helpers", fail)
        with pytest.raises(HostMutationError):
            installer.resume_install(artifact, digest)
    after = json.loads(layout.journal.read_text())
    assert after["transaction_id"] == before["transaction_id"]
    assert after["staging_recovery"] == before["staging_recovery"]
    assert installer.resume_install(artifact, digest).health_verified


def test_resume_after_release_staged_checkpoint_before_any_migration(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    installer, layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.3.0rc30", "revision_one")
    with monkeypatch.context() as scoped:

        def crash(_previous: str | None) -> None:
            raise RuntimeError("power loss before database work")

        scoped.setattr(installer, "_backup_before_change", crash)
        with pytest.raises(RuntimeError, match="power loss"):
            installer.apply(artifact, digest)
    assert json.loads(layout.journal.read_text())["completed_steps"][-1] == "release_staged"
    assert not layout.database.exists()
    assert installer.resume_install(artifact, digest).health_verified


@pytest.mark.parametrize(
    "change",
    [
        "artifact",
        "old_journal",
        "migration",
        "database",
        "receipt",
        "current",
        "config",
        "mode",
        "symlink",
        "hardlink",
        "directory",
        "identity",
        "resources",
        "extra_field",
        "unit",
        "lock",
    ],
)
def test_staged_resume_refuses_uncertain_or_changed_evidence_before_mutation(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    change: str,
) -> None:
    installer, layout, artifact, digest = _stage(tmp_path, monkeypatch)
    journal = json.loads(layout.journal.read_text())
    environment = layout.map("/etc/agentbox/environment")
    if change == "artifact":
        with artifact.open("ab") as stream:
            stream.write(b"different pinned archive")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    elif change == "old_journal":
        journal["schema_version"] = 2
    elif change == "migration":
        journal["completed_steps"].append("database_migration_started")
    elif change == "database":
        layout.database.write_bytes(b"preserve")
    elif change == "receipt":
        layout.receipt.write_bytes(b"preserve")
    elif change == "current":
        layout.current_link.symlink_to(layout.release("0.3.0rc30"), target_is_directory=True)
    elif change == "config":
        with environment.open("ab") as stream:
            stream.write(b"changed\n")
    elif change == "mode":
        environment.chmod(0o644)
    elif change == "symlink":
        environment.unlink()
        outside = tmp_path / "outside"
        outside.write_bytes(b"preserve")
        environment.symlink_to(outside)
    elif change == "hardlink":
        os.link(environment, tmp_path / "alias")
    elif change == "directory":
        layout.map("/run/agentbox-waw/tmp").chmod(0o777)
    elif change == "identity":
        journal["staging_recovery"]["identities"]["runtime_uid"] += 1
    elif change == "resources":
        journal["resources"].pop()
    elif change == "extra_field":
        journal["staging_recovery"]["unknown"] = "field"
    elif change == "unit":
        unit = layout.map("/etc/systemd/system/agentbox-api.service")
        unit.parent.mkdir(parents=True, exist_ok=True)
        unit.write_bytes(b"preserve")
    else:
        layout.map("/run/agentbox-waw-api/waw-api.v1.lock").unlink()
    layout.journal.write_text(json.dumps(journal))
    protected = layout.journal.read_bytes()
    monkeypatch.setattr(
        installer, "_apply_locked", lambda *_args, **_kwargs: pytest.fail("mutation reached")
    )
    with pytest.raises((InstallError, HostMutationError)):
        installer.resume_install(artifact, digest)
    assert layout.journal.read_bytes() == protected
    if change in {"database", "receipt"}:
        assert getattr(layout, change).read_bytes() == b"preserve"
