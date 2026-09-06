from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/rehearse-rc8-workflow.py"


def _module() -> ModuleType:
    specification = importlib.util.spec_from_file_location("rc8_workflow", SCRIPT)
    if specification is None or specification.loader is None:
        raise RuntimeError("rc8 workflow rehearsal could not load")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def test_dynamic_registry_binds_payload_private_key_and_actual_ticket(tmp_path: Path) -> None:
    module = _module()
    registry = tmp_path / "canaries.json"
    initial = module._write_initial_canaries(registry)
    ticket = b"wat_0123456789abcdef0123456789abcdef"
    registry.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "canaries": [
                    {
                        "kind": name,
                        "value_base64": base64.b64encode(value).decode("ascii"),
                    }
                    for name, value in (
                        ("payload", initial["payload"]),
                        ("private_key", initial["private_key"]),
                        ("ticket", ticket),
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    registry.chmod(0o600)

    assert module._read_completed_canaries(registry, initial) == (
        initial["payload"],
        initial["private_key"],
        ticket,
    )


def test_workflow_arguments_use_only_fixed_fhs_paths_and_ephemeral_port(tmp_path: Path) -> None:
    module = _module()
    artifact = {name: tmp_path / name for name in ("artifact", "checksums", "manifest", "sbom")}
    artifact["artifact"].write_bytes(b"fixture artifact")
    arguments = module._operations_arguments(
        predecessor=artifact,
        candidate=artifact,
        predecessor_workspace=tmp_path / "predecessor",
        candidate_workspace=tmp_path / "candidate",
        fixture=tmp_path / "fixture",
        work_root=tmp_path / "work",
        health_port=19_999,
    )

    assert "http://127.0.0.1:19999" in arguments
    assert str(tmp_path / "fixture/var/lib/agentbox/agentbox.db") in arguments
    assert str(tmp_path / "fixture/opt/agentbox/current") in arguments
    assert "systemctl" not in " ".join(arguments)


def test_bounded_capture_terminates_oversized_child_output(tmp_path: Path) -> None:
    module = _module()
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    with pytest.raises(module.WorkflowError, match="overflow"):
        module._capture_command(
            "overflow",
            (sys.executable, "-c", f"print('x' * {module._MAX_LOG_BYTES + 1})"),
            cwd=tmp_path,
            env={"PATH": str(Path(sys.executable).parent)},
            evidence=evidence,
            timeout=30,
        )
    assert (evidence / "overflow.stdout").stat().st_size <= module._MAX_LOG_BYTES
    assert (evidence / "overflow.stderr").stat().st_size <= module._MAX_LOG_BYTES


def test_failure_scan_only_receives_declared_existing_surfaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    root = tmp_path / "work"
    root.mkdir()
    evidence = root / "evidence"
    evidence.mkdir()
    canary_root = tmp_path / "canaries"
    canary_root.mkdir()
    candidate_bundle = tmp_path / "candidate-bundle"
    predecessor_bundle = tmp_path / "predecessor-bundle"
    fixture = root / "fixture"
    candidate_bundle.mkdir()
    predecessor_bundle.mkdir()
    database = fixture / "var/lib/agentbox/agentbox.db"
    database.parent.mkdir(parents=True)
    database.write_bytes(b"fixture-canary-surface")
    observed: dict[str, Any] = {}

    def fake_scan(**kwargs: Any) -> None:
        observed.update(kwargs)

    monkeypatch.setattr(module, "_scan", fake_scan)
    module._scan_failure_evidence(
        root=root,
        evidence=evidence,
        canary_root=canary_root,
        initial_canaries={"payload": b"p" * 16, "private_key": b"k" * 32},
        candidate_source=ROOT,
        candidate_bundle=candidate_bundle,
        predecessor_bundle=predecessor_bundle,
        fixture=fixture,
    )

    assert observed["surfaces"] == {
        "captured_logs": evidence,
        "candidate_bundle": candidate_bundle,
        "predecessor_bundle": predecessor_bundle,
        "fixture_database": database,
    }
    assert observed["registry"] == canary_root / "partial-canaries.json"


def test_environment_surfaces_exclude_venv_bin_symlinks(tmp_path: Path) -> None:
    module = _module()
    workspace = tmp_path / "candidate"
    site_packages = workspace / "environment/lib/python3.11/site-packages"
    site_packages.mkdir(parents=True)
    (workspace / "environment/pyvenv.cfg").write_text(
        "include-system-site-packages = false\n", encoding="ascii"
    )
    (workspace / "pip-report.json").write_text("{}\n", encoding="utf-8")
    (workspace / "unpacked").mkdir()
    (workspace / "home").mkdir()
    proof = workspace / "environment-proof.json"
    proof.write_text(json.dumps({"site_packages": str(site_packages)}), encoding="utf-8")

    surfaces = module._environment_surfaces("candidate", workspace)

    assert "candidate_environment" not in surfaces
    assert surfaces["candidate_site_packages"] == site_packages
    assert all("/bin" not in str(path) for path in surfaces.values())


def test_operations_failure_summary_is_strict_and_never_echoes_stderr(tmp_path: Path) -> None:
    module = _module()
    stdout = tmp_path / "stdout"
    stderr = tmp_path / "stderr"
    stdout.write_bytes(b"")
    stderr.write_text(
        "release operations rehearsal failed: candidate: installed wheel payload digest mismatch\n",
        encoding="utf-8",
    )
    assert module._operations_failure_surface(stdout, stderr) == "upgrade-rollback.candidate"

    stderr.write_text(
        "release operations rehearsal failed: payload: rc8-secret-canary\n",
        encoding="utf-8",
    )
    assert module._operations_failure_surface(stdout, stderr) == "upgrade-rollback"
