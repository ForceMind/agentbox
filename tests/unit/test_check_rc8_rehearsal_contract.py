from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/check-rc8-rehearsal-contract.py"
SHA = "a" * 40


def _module() -> ModuleType:
    specification = importlib.util.spec_from_file_location("rc8_contract", SCRIPT)
    if specification is None or specification.loader is None:
        raise RuntimeError("rc8 contract checker could not load")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _contract() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "stage": "r11-rc8-artifact-operations",
        "predecessor": {
            "version": "0.3.0rc7",
            "merge_sha": "87f5bce964eba231a6a7ade73eaedac7e54646ae",
        },
        "candidate": {"version": "0.3.0rc8", "source_sha": "WORKFLOW_EXACT_HEAD"},
        "required_rehearsals": [
            "unpacked_native_source",
            "wheelhouse_import_provenance",
            "synthetic_waw_end_to_end",
            "exact_upgrade_rollback",
            "canary_surface_scan",
        ],
        "forbidden_capabilities": [
            "systemd_activation",
            "real_provider_secret",
            "real_vendor_login",
            "real_host_qualification",
            "production_fault_switch",
        ],
    }


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def test_contract_returns_only_fixed_inputs(tmp_path: Path) -> None:
    module = _module()
    contract = tmp_path / "contract.json"
    _write(contract, _contract())

    assert module.validate_contract(contract, SHA) == {
        "candidate_sha": SHA,
        "candidate_version": "0.3.0rc8",
        "predecessor_sha": "87f5bce964eba231a6a7ade73eaedac7e54646ae",
        "predecessor_version": "0.3.0rc7",
    }


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(extra=True),
        lambda value: value["candidate"].update(source_sha="a" * 40),
        lambda value: value["predecessor"].update(version="0.3.0rc6"),
        lambda value: value.update(forbidden_capabilities=[]),
        lambda value: value.update(required_rehearsals="synthetic_waw_end_to_end"),
    ],
)
def test_contract_rejects_unapproved_values(tmp_path: Path, mutation: Any) -> None:
    module = _module()
    value = _contract()
    mutation(value)
    contract = tmp_path / "contract.json"
    _write(contract, value)

    with pytest.raises(module.ContractError):
        module.validate_contract(contract, SHA)


def test_contract_rejects_duplicate_json_keys_without_echoing_input(tmp_path: Path) -> None:
    module = _module()
    contract = tmp_path / "contract.json"
    contract.write_text('{"schema_version":1,"schema_version":1}\n', encoding="utf-8")

    with pytest.raises(module.ContractError):
        module.validate_contract(contract, SHA)


def test_cli_writes_validated_github_outputs(tmp_path: Path) -> None:
    contract = tmp_path / "contract.json"
    output = tmp_path / "github-output"
    _write(contract, _contract())
    output.touch()
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--contract",
            str(contract),
            "--candidate-sha",
            SHA,
            "--github-output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert output.read_text(encoding="ascii") == (
        f"candidate_sha={SHA}\n"
        "candidate_version=0.3.0rc8\n"
        "predecessor_sha=87f5bce964eba231a6a7ade73eaedac7e54646ae\n"
        "predecessor_version=0.3.0rc7\n"
    )
