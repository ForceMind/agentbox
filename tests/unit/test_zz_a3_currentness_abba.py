"""Only diagnostic orchestration is simulated; native tests and I/O stay real."""

from __future__ import annotations

import importlib.util
import json
import os
import struct
import sys
import zipfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from _pytest.compat import ascii_escaped

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/a3-currentness-abba.py"
REQUIREMENTS = ROOT / "scripts/a3-currentness-abba-requirements.txt"


@pytest.fixture
def runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("a3_abba_contract", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def collected(runner: ModuleType, pid: int = 1234) -> str:
    rows = [f"tests/unit/old.py::test_{index}" for index in range(5393)]
    rows[762] = runner.TARGET
    native = (
        "tests/native/test_waw_auth_native_linux.py::"
        "test_auth_probe_rejects_malformed_or_wrong_parent_record"
    )
    activation = "tests/unit/test_waw_activation.py::test_activation_metadata_must_be_exact"
    base: list[Any] = [
        b"AWP1",
        1,
        1,
        0,
        pid,
        os.geteuid(),
        os.getegid(),
        8,
        b"b" * 64,
        b"c" * 64,
        bytes(4),
    ]
    payloads = [struct.pack("!4sBBHIIIQ64s64s4s", *base) + b"oversize"]
    for field, value in (
        (0, b"AWP2"),
        (1, 2),
        (2, 3),
        (3, 1),
        (5, 0),
        (7, 0),
        (9, b"B" * 64),
        (10, b"\0\0\0\x01"),
    ):
        variant = base.copy()
        variant[field] = value
        payloads.append(struct.pack("!4sBBHIIIQ64s64s4s", *variant))
    for index, raw in enumerate(payloads):
        rows[292 + index] = native + "[" + ascii_escaped(raw) + "]"
    rows[291] = native + "[short]"
    base[4] = 1
    rows[301] = native + "[" + ascii_escaped(struct.pack("!4sBBHIIIQ64s64s4s", *base)) + "]"
    rows[2379] = activation + "[0-2-agentbox-waw-control:agentbox-waw-stream]"
    for index, suffix in enumerate(
        (
            "1-agentbox-waw-control",
            "2-agentbox-waw-control:agentbox-waw-control",
            "2-agentbox-waw-control:unexpected",
            "2-agentbox-waw-control:agentbox-waw-stream:extra",
        )
    ):
        rows[2380 + index] = f"{activation}[{pid}-{suffix}]"
    return "\n".join(rows) + "\n5393 tests collected\n"


def pytest_output(runner: ModuleType, failed: bool, *, target: bool = True) -> str:
    failure = (
        f"FAILED {runner.TARGET if target else 'tests/unit/other.py::test_other'} - PATCH_REVOKED\n"
        if failed
        else ""
    )
    return (
        "collected 5393 items\n"
        + failure
        + f"=== {5304 if failed else 5305} passed, {1 if failed else 0} failed, "
        "88 skipped in 310.00s ===\n"
    )


def test_fixed_cases_pins_and_workflow_boundaries(runner: ModuleType) -> None:
    assert [(case.name, case.sha) for case in runner.CASES] == [
        ("A1", "a586eaec27984e0632187048cc1b82e7e29552d1"),
        ("B1", "404daae0be4225b30a6e3e71ee239376bd5e6ca6"),
        ("B2", "404daae0be4225b30a6e3e71ee239376bd5e6ca6"),
        ("A2", "a586eaec27984e0632187048cc1b82e7e29552d1"),
    ]
    assert len(runner.pins(REQUIREMENTS)) == 74
    yaml = __import__("yaml")
    workflow = yaml.load(
        (ROOT / ".github/workflows/a3-currentness-abba.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert workflow["on"] == {"pull_request": {"types": ["labeled"]}}
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["compare"]
    assert job["runs-on"] == "ubuntu-24.04" and job["timeout-minutes"] == "35"
    comparison = next(
        step
        for step in job["steps"]
        if step.get("run") == "python harness/scripts/a3-currentness-abba.py"
    )
    assert comparison["timeout-minutes"] == "32"
    for guard in (
        "number == 149",
        "github.head_ref == 'diag/native-currentness-20261006'",
        "label.name == 'bug'",
        "github.run_attempt == '1'",
        "head.repo.full_name == 'ForceMind/agentbox'",
    ):
        assert guard in job["if"]
    checkouts = [
        step["with"]
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    ]
    assert len(checkouts) == 5
    assert [step["ref"] for step in checkouts[1:]] == [case.sha for case in runner.CASES]
    assert [step["path"] for step in checkouts[1:]] == [
        f"a3-abba-cases/{case.name.lower()}/source" for case in runner.CASES
    ]
    assert all(step["persist-credentials"] == "false" for step in checkouts)
    content = (ROOT / ".github/workflows/a3-currentness-abba.yml").read_text()
    for forbidden in (
        "pull_request_target",
        "workflow_dispatch",
        "sudo",
        "systemctl",
        "secrets.",
        "cache: pip",
        "continue-on-error",
    ):
        assert forbidden not in content
    assert [
        step["with"]["python-version"]
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/setup-python@")
    ] == ["3.13.15"]


@pytest.mark.parametrize(
    "bad", ["pytest>=9", "pytest==9.1.1\npytest==9.1.1", "agentbox==0.3.0rc31", "pip==26.2.1"]
)
def test_invalid_or_incomplete_pins_fail_closed(
    runner: ModuleType, tmp_path: Path, bad: str
) -> None:
    path = tmp_path / "pins.txt"
    path.write_text(bad)
    with pytest.raises(runner.DiagnosticError):
        runner.pins(path)


@pytest.mark.parametrize("change", ["python", "image", "plugin", "host_gate"])
def test_host_preflight_rejects_different_conditions(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    monkeypatch.setattr(runner.platform, "python_version", lambda: "3.13.15")
    monkeypatch.setattr(runner.platform, "system", lambda: "Linux")
    monkeypatch.setattr(runner.platform, "machine", lambda: "x86_64")
    monkeypatch.setenv(runner.IMAGE_VARIABLE, runner.IMAGE)
    for key in (
        "PYTEST_PLUGINS",
        "PYTEST_ADDOPTS",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        "AGENTBOX_WAW_NATIVE_HOST_GATE",
        "AGENTBOX_WAW_ACTUAL_CODEX_AUTH_PROBE",
        "AGENTBOX_WAW_NATIVE_BIN_DIR",
    ):
        monkeypatch.delenv(key, raising=False)
    runner.verify_host()
    if change == "python":
        monkeypatch.setattr(runner.platform, "python_version", lambda: "3.13.16")
    elif change == "image":
        monkeypatch.setenv(runner.IMAGE_VARIABLE, "different")
    elif change == "plugin":
        monkeypatch.setenv("PYTEST_PLUGINS", "unexpected")
    else:
        monkeypatch.setenv("AGENTBOX_WAW_ACTUAL_CODEX_AUTH_PROBE", "1")
    with pytest.raises(runner.DiagnosticError):
        runner.verify_host()


@pytest.mark.parametrize("change", ["commit", "tree", "dirty"])
def test_source_preflight_rejects_identity_or_tracked_changes(
    runner: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    case = runner.CASES[0]

    def checked(args: list[str], **_kwargs: Any) -> str:
        if args[1] == "status":
            return " M tracked.py" if change == "dirty" else ""
        return (
            ("0" * 40 if change == "commit" else case.sha)
            + "\n"
            + ("0" * 40 if change == "tree" else runner.TREES[case.sha])
        )

    monkeypatch.setattr(runner, "checked", checked)
    with pytest.raises(runner.DiagnosticError):
        runner.verify_source(case, tmp_path, tmp_path)


def test_collection_preserves_all_parameters_except_documented_pid_fields(
    runner: ModuleType,
) -> None:
    first = runner.collection(collected(runner, 1234))
    second = runner.collection(collected(runner, 9876))
    assert first == second and len(first) == 5393 and first[762] == runner.TARGET
    changed = collected(runner).replace("oversize]", "different]")
    with pytest.raises(runner.DiagnosticError, match="unexpected_auth_parameter"):
        runner.collection(changed)


@pytest.mark.parametrize("change", ["count", "target", "ignored", "pid"])
def test_collection_drift_is_invalid(runner: ModuleType, change: str) -> None:
    raw = collected(runner)
    if change == "count":
        raw = "\n".join(raw.splitlines()[1:])
    elif change == "target":
        raw = raw.replace(runner.TARGET, "tests/unit/old.py::wrong_target")
    elif change == "ignored":
        raw = raw.replace("tests/unit/old.py::test_1\n", runner.IGNORED + "::unexpected\n")
    else:
        raw = raw.replace(
            "test_activation_metadata_must_be_exact[1234-",
            "test_activation_metadata_must_be_exact[0-",
        )
    with pytest.raises(runner.DiagnosticError):
        runner.collection(raw)


def wheel(folder: Path, name: str, version: str, filename: str | None = None) -> Path:
    path = folder / (filename or f"{name}-{version}-py3-none-any.whl")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{name}-{version}.dist-info/METADATA",
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
        )
    return path


def test_wheelhouse_hash_version_and_readonly_contract(runner: ModuleType, tmp_path: Path) -> None:
    folder = tmp_path / "wheels"
    folder.mkdir()
    path = wheel(folder, "sample", "1.2.3")
    try:
        hashes, packages = runner.seal_wheels(folder, {"sample": "1.2.3"})
        assert packages == {"sample": hashes[path.name]}
        runner.verify_wheels(folder, hashes)
        path.chmod(0o644)
        with pytest.raises(runner.DiagnosticError, match="wheel_changed"):
            runner.verify_wheels(folder, hashes)
        path.write_bytes(b"changed")
        path.chmod(0o444)
        with pytest.raises(runner.DiagnosticError, match="wheel_changed"):
            runner.verify_wheels(folder, hashes)
    finally:
        folder.chmod(0o755)
        path.chmod(0o644)


@pytest.mark.parametrize("change", ["version", "duplicate", "extra", "symlink"])
def test_invalid_wheelhouse_is_rejected(runner: ModuleType, tmp_path: Path, change: str) -> None:
    folder = tmp_path / "wheels"
    folder.mkdir()
    path = wheel(folder, "sample", "1.2.3")
    if change == "duplicate":
        wheel(folder, "sample", "1.2.3", "duplicate.whl")
    elif change == "extra":
        (folder / "other.txt").write_text("not a wheel")
    elif change == "symlink":
        (folder / "alias.whl").symlink_to(path)
    with pytest.raises(runner.DiagnosticError):
        runner.seal_wheels(folder, {"sample": "9" if change == "version" else "1.2.3"})


@pytest.mark.parametrize(
    "change", ["extra_package", "wrong_version", "duplicate", "plugin", "source"]
)
def test_probe_rejects_wrong_package_plugin_or_module_source(
    runner: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    expected = {**runner.pins(REQUIREMENTS), "agentbox": "0.3.0rc31"}
    dists = [
        SimpleNamespace(metadata={"Name": name}, version=version)
        for name, version in expected.items()
    ]
    if change == "extra_package":
        dists.append(SimpleNamespace(metadata={"Name": "unplanned"}, version="1"))
    elif change == "wrong_version":
        dists[0].version = "0"
    elif change == "duplicate":
        dists.append(dists[0])
    plugins = [
        SimpleNamespace(name="anyio", value="anyio.pytest_plugin"),
        SimpleNamespace(name="platformdirs", value="platformdirs.pytest_plugin"),
    ]
    if change == "plugin":
        plugins.append(SimpleNamespace(name="unplanned", value="other"))
    fake_importlib = SimpleNamespace(
        metadata=SimpleNamespace(
            distributions=lambda: dists, entry_points=lambda **_kwargs: plugins
        ),
        import_module=lambda _name: SimpleNamespace(__file__=str(tmp_path / "wrong.py")),
    )
    monkeypatch.setattr(runner, "importlib", fake_importlib)
    monkeypatch.setattr(runner.platform, "python_version", lambda: "3.13.15")
    with pytest.raises(runner.DiagnosticError):
        runner.probe(tmp_path, REQUIREMENTS)


def test_probe_accepts_only_exact_source_and_packages(
    runner: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = {**runner.pins(REQUIREMENTS), "agentbox": "0.3.0rc31"}
    dists = [
        SimpleNamespace(metadata={"Name": name}, version=version)
        for name, version in expected.items()
    ]
    for relative in runner.MODULES.values():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# orchestration fixture\n")
    fake_importlib = SimpleNamespace(
        metadata=SimpleNamespace(
            distributions=lambda: dists,
            entry_points=lambda **_kwargs: [
                SimpleNamespace(name="anyio", value="anyio.pytest_plugin"),
                SimpleNamespace(name="platformdirs", value="platformdirs.pytest_plugin"),
            ],
        ),
        import_module=lambda name: SimpleNamespace(__file__=str(tmp_path / runner.MODULES[name])),
    )
    monkeypatch.setattr(runner, "importlib", fake_importlib)
    monkeypatch.setattr(runner.platform, "python_version", lambda: "3.13.15")
    evidence = runner.probe(tmp_path, REQUIREMENTS)
    assert evidence["packages"] == expected and len(evidence["modules"]) == 9


@pytest.mark.parametrize(
    "codes, expected, exit_code",
    [
        ([0, 0, 0, 0], "not_reproduced_not_a_fix", 0),
        ([1, 0, 0, 1], "observer_association_not_causation", 1),
        ([0, 1, 1, 0], "diagnostic_target_failure_observed", 1),
        ([1, 0, 0, 0], "inconclusive_failures_retained", 1),
    ],
)
def test_fixed_abba_runs_all_four_without_retry_and_retains_failures(
    runner: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    codes: list[int],
    expected: str,
    exit_code: int,
) -> None:
    work, artifacts = tmp_path / "work", tmp_path / "artifacts"
    work.mkdir()
    artifacts.mkdir()
    commands: list[list[str]] = []
    source_checks: list[str] = []
    monkeypatch.setattr(runner, "verify_host", lambda: None)
    monkeypatch.setattr(
        runner, "verify_source", lambda case, *_args: source_checks.append(case.name)
    )
    monkeypatch.setattr(runner, "verify_wheels", lambda *_args: None)
    pins = runner.pins(REQUIREMENTS)
    monkeypatch.setattr(
        runner,
        "seal_wheels",
        lambda *_args: ({"fixture.whl": "a" * 64}, {name: "a" * 64 for name in pins}),
    )

    def checked(args: list[str], **_kwargs: Any) -> str:
        commands.append(args)
        if "--probe" in args:
            return json.dumps({"prefix": str(Path(args[0]).parent.parent)})
        if "--collect-only" in args:
            return collected(runner)
        return ""

    native_commands: list[list[str]] = []

    def command(args: list[str], **kwargs: Any) -> int:
        # Simulate only the process orchestration, never monkeypatch native modules.
        index = len(native_commands)
        assert len([call for call in commands if "--collect-only" in call]) == 4
        native_commands.append(args)
        kwargs["log"].write_text(pytest_output(runner, bool(codes[index])))
        return codes[index]

    monkeypatch.setattr(runner, "checked", checked)
    monkeypatch.setattr(runner, "command", command)
    report: dict[str, Any] = {"results": []}
    assert runner.experiment(tmp_path, work, artifacts, report) == exit_code
    assert [result["case"] for result in report["results"]] == ["A1", "B1", "B2", "A2"]
    assert [result["exit_code"] for result in report["results"]] == codes
    assert report["interpretation"] == expected
    assert len(native_commands) == 4
    for case, args in zip(runner.CASES, native_commands, strict=True):
        assert args == [
            str(work / case.name / "venv/bin/python"),
            "-m",
            "pytest",
            "-o",
            "faulthandler_timeout=120",
            *case.pytest_args(),
        ]
    assert len({args[0] for args in native_commands}) == 4
    assert len([args for args in commands if "venv" in args]) == 4
    assert all(source_checks.count(case.name) == 3 for case in runner.CASES)
    assert len([args for args in commands if "--no-build-isolation" in args]) == 4
    assert len([args for args in commands if "--require-hashes" in args]) == 4
    assert json.loads((artifacts / "summary.json").read_text())["interpretation"] == expected


@pytest.mark.parametrize(
    "code,text",
    [
        (2, "collected 5393 items\n"),
        (0, "collected 5458 items\n5370 passed, 88 skipped"),
        (0, "collected 5393 items\n5304 passed, 89 skipped"),
        (0, "collected 5393 items\n5304 passed, 1 failed, 88 skipped"),
    ],
)
def test_incomplete_or_wrong_execution_is_not_a_green_result(
    runner: ModuleType, code: int, text: str
) -> None:
    with pytest.raises(runner.DiagnosticError):
        runner.outcome(code, text)


def test_failure_note_retention_is_bounded(runner: ModuleType) -> None:
    text = pytest_output(runner, True) + ("Native fixture timing " + "x" * 4000 + "\n") * 20
    result = runner.outcome(1, text)
    assert result["target_failed"] and len(result["currentness_notes"]) == 8
    assert all(len(note) <= 2048 for note in result["currentness_notes"])


def test_preparation_error_is_reported_as_incomplete(
    runner: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, temporary = tmp_path / "workspace", tmp_path / "temporary"
    workspace.mkdir()
    temporary.mkdir()
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("RUNNER_TEMP", str(temporary))
    monkeypatch.setattr(runner.sys, "argv", [str(SCRIPT)])

    def broken(*_args: object) -> int:
        raise runner.DiagnosticError("source_identity_mismatch")

    monkeypatch.setattr(runner, "experiment", broken)
    assert runner.main() == 2
    report = json.loads((workspace / "a3-abba-artifacts/summary.json").read_text())
    assert report["interpretation"] == "invalid_or_incomplete_comparison"
    assert report["results"] == []


@pytest.mark.parametrize("pid", [92, 4700, 23604, 23662, 23672])
def test_real_pytest_byte_ids_preserve_literal_backslash_pids(runner: ModuleType, pid: int) -> None:
    assert runner.collection(collected(runner, pid)) == runner.collection(collected(runner, 1234))


def test_forward_pid_field_encoding_matches_real_pytest_all_bytes(runner: ModuleType) -> None:
    raw = bytes(range(256))
    assert runner.pytest_byte_field(raw) == ascii_escaped(raw)
    assert runner.pytest_byte_field(b"\\") == "\\"


def test_collection_rejects_disagreeing_activation_pids(runner: ModuleType) -> None:
    raw = collected(runner).replace(
        "[1234-1-agentbox-waw-control]", "[1235-1-agentbox-waw-control]"
    )
    with pytest.raises(runner.DiagnosticError, match="inconsistent_collection_pid"):
        runner.collection(raw)


def test_collection_rejects_auth_pid_not_matching_activation_pid(runner: ModuleType) -> None:
    raw = collected(runner, 23672).replace("[23672-", "[23662-")
    with pytest.raises(runner.DiagnosticError, match="unexpected_auth_parameter"):
        runner.collection(raw)
