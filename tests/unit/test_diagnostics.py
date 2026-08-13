from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from agentbox_installer.diagnostics import (
    DeploymentDoctor,
    DiagnosticSeverity,
    export_diagnostics,
)
from agentbox_installer.layout import DIRECTORIES, InstallLayout


def _fixture_layout(tmp_path: Path) -> InstallLayout:
    root = tmp_path / "root"
    root.mkdir()
    os_release = root / "etc/os-release"
    os_release.parent.mkdir(parents=True)
    os_release.write_text('ID="rocky"\nVERSION_ID="9.5"\n', encoding="utf-8")
    for item in DIRECTORIES:
        target = root / item.path.lstrip("/")
        target.mkdir(parents=True, exist_ok=True)
        target.chmod(item.mode)
    (root / "etc/systemd/system").mkdir(parents=True, exist_ok=True)
    return InstallLayout(root)


def test_doctor_json_contract_has_actionable_stable_findings(tmp_path: Path) -> None:
    report = DeploymentDoctor(_fixture_layout(tmp_path)).inspect()

    assert report["schema_version"] == 1
    assert report["overall"] in {severity.value for severity in DiagnosticSeverity}
    findings = report["findings"]
    assert isinstance(findings, list)
    assert findings
    for finding in findings:
        assert isinstance(finding, dict)
        assert set(finding) == {
            "code",
            "category",
            "severity",
            "summary",
            "details",
            "remediation_id",
        }
        assert finding["severity"] in {severity.value for severity in DiagnosticSeverity}
    platform = next(item for item in findings if item["code"] == "PLATFORM_QUALIFICATION")
    assert platform["severity"] == "WARN"
    assert "fixture_validated" in platform["details"]


def test_doctor_detects_permission_drift_without_repairing_it(tmp_path: Path) -> None:
    layout = _fixture_layout(tmp_path)
    project_root = layout.map("/srv/agentbox/projects")
    project_root.chmod(0o755)

    before = stat.S_IMODE(project_root.stat().st_mode)
    report = DeploymentDoctor(layout).inspect()
    findings = report["findings"]
    assert isinstance(findings, list)
    finding = next(
        item
        for item in findings
        if isinstance(item, dict) and item["code"] == "MANAGED_DIRECTORY_PERMISSIONS"
    )

    assert finding["severity"] == "FAIL"
    assert "/srv/agentbox/projects" in finding["details"]
    assert stat.S_IMODE(project_root.stat().st_mode) == before


def test_diagnostics_export_is_restrictive_non_overwriting_and_sanitized(
    tmp_path: Path,
) -> None:
    output = tmp_path / "diagnostics.json"
    safe = {
        "schema_version": 1,
        "agentbox_version": "fixture",
        "findings": [{"code": "READY", "details": "no sensitive values"}],
    }

    export_diagnostics(output, safe)

    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text(encoding="utf-8")) == safe
    with pytest.raises(FileExistsError):
        export_diagnostics(output, safe)


@pytest.mark.parametrize(
    "payload",
    [
        {"password": "PASSWORD-CANARY"},
        {"session_token": "SESSION-TOKEN-CANARY"},
        {"csrf_verifier": "CSRF-CANARY"},
        {"application_secret": "APP-SECRET-CANARY"},
        {"pair_code": "CODEX-PAIR-CANARY"},
        {"pane_output": "CLAUDE-OUTPUT-CANARY"},
        {"github_token": "GITHUB-TOKEN-CANARY"},
        {"remote_url": "https://user:GIT-CREDENTIAL-CANARY@example.invalid/repo"},
        {"ssh_private_key": "SSH-KEY-CANARY"},
        {"provider_api_key": "PROVIDER-KEY-CANARY"},
    ],
)
def test_diagnostics_export_fails_before_writing_secret_canaries(
    tmp_path: Path, payload: dict[str, str]
) -> None:
    output = tmp_path / "diagnostics.json"

    with pytest.raises(ValueError, match="diagnostic payload"):
        export_diagnostics(output, payload)

    assert not output.exists()


def test_diagnostics_export_rejects_symlinked_output_and_parent(tmp_path: Path) -> None:
    safe = {"schema_version": 1, "state": "ready"}
    existing = tmp_path / "existing.json"
    existing.write_text("preserve", encoding="utf-8")
    output_link = tmp_path / "diagnostics.json"
    output_link.symlink_to(existing)

    with pytest.raises(FileExistsError):
        export_diagnostics(output_link, safe)
    assert existing.read_text(encoding="utf-8") == "preserve"

    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(ValueError, match="parent must not contain symlinks"):
        export_diagnostics(linked_parent / "diagnostics.json", safe)
    assert not (real_parent / "diagnostics.json").exists()


def test_diagnostics_export_enforces_structural_and_filename_bounds(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="findings limit"):
        export_diagnostics(
            tmp_path / "diagnostics.json",
            {"findings": [{"code": "SAFE"}] * 65},
        )
    with pytest.raises(ValueError, match="message limit"):
        export_diagnostics(tmp_path / "diagnostics.json", {"detail": "x" * 1025})
    with pytest.raises(ValueError, match="filename"):
        export_diagnostics(tmp_path / ("x" * 129), {"state": "ready"})


def test_diagnostics_export_removes_incomplete_file_on_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "diagnostics.json"
    real_fsync = os.fsync
    calls = 0

    def fail_first_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_first_fsync)
    with pytest.raises(OSError, match="injected fsync failure"):
        export_diagnostics(output, {"schema_version": 1, "state": "ready"})

    assert not output.exists()
