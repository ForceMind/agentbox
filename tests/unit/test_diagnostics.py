from __future__ import annotations

import json
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
        {"password": "DIAGNOSTIC-PASSWORD-CANARY"},
        {"safe": "Bearer " + "".join(("gh", "p_", "1234567890abcdefghijkl"))},
        {"safe": "https://user:credential@example.invalid/repo"},
        {"safe": "AGENTBOX_SECRET=DIAGNOSTIC-SECRET-CANARY"},
    ],
)
def test_diagnostics_export_fails_before_writing_secret_canaries(
    tmp_path: Path, payload: dict[str, str]
) -> None:
    output = tmp_path / "diagnostics.json"

    with pytest.raises(ValueError, match="diagnostic payload"):
        export_diagnostics(output, payload)

    assert not output.exists()
