#!/usr/bin/env python3
"""Fixed, one-shot A3 A/B/B/A diagnostic; never a product or qualification runner."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import re
import struct
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from email.parser import BytesParser
from pathlib import Path
from typing import Any

A = "a586eaec27984e0632187048cc1b82e7e29552d1"
B = "404daae0be4225b30a6e3e71ee239376bd5e6ca6"
TREES = {
    A: "e5d9309dca123f17f9ff9ee48df0765c332ea451",
    B: "238a35a0629e3307560d3a57371e9f2410e3f047",
}
TARGET = (
    "tests/unit/test_a3_native_transport.py::"
    "test_native_records_hold_admission_through_publication_complete_and_revoke"
)
IGNORED = "tests/unit/test_zz_a3_currentness_diagnostics.py"
PYTHON = "3.13.15"
IMAGE = "20260927.320.1"
IMAGE_VARIABLE = "ImageVersion"  # Exact mixed-case GitHub runner field.
MAX_LOG_BYTES = 32 * 1024 * 1024
MODULES = {
    "agentbox_api.a3_native_transport": "apps/api/src/agentbox_api/a3_native_transport.py",
    "agentbox_core.a3_native_io": "packages/agentbox-core/src/agentbox_core/a3_native_io.py",
    "agentbox_protocol.a3_transport": (
        "packages/agentbox-protocol/src/agentbox_protocol/a3_transport.py"
    ),
    "agentbox_runtime.a3_native_transport": (
        "packages/agentbox-runtime/src/agentbox_runtime/a3_native_transport.py"
    ),
    "agentbox_browser_trust": (
        "packages/agentbox-browser-trust/src/agentbox_browser_trust/__init__.py"
    ),
    "agentbox_cli": "apps/cli/src/agentbox_cli/__init__.py",
    "agentbox_worker": "apps/worker/src/agentbox_worker/__init__.py",
    "agentbox_helper": "helper/src/agentbox_helper/__init__.py",
    "agentbox_installer": "installer/src/agentbox_installer/__init__.py",
}


class DiagnosticError(RuntimeError):
    """Only fixed diagnostic codes reach the summary."""


@dataclass(frozen=True)
class Case:
    name: str
    sha: str

    def source(self, workspace: Path) -> Path:
        return workspace / "a3-abba-cases" / self.name.lower() / "source"

    def pytest_args(self) -> list[str]:
        return [f"--ignore={IGNORED}"] if self.sha == B else []


CASES = (Case("A1", A), Case("B1", B), Case("B2", B), Case("A2", A))


def canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def pins(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)", line)
        if match is None:
            raise DiagnosticError("invalid_dependency_pin")
        name = canonical_name(match[1])
        if name in result or name == "agentbox":
            raise DiagnosticError("duplicate_or_editable_dependency_pin")
        result[name] = match[2]
    if len(result) != 74 or result.get("pip") != "26.2.1" or result.get("setuptools") != "84.0.0":
        raise DiagnosticError("incomplete_dependency_pins")
    return result


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_log(path: Path) -> str:
    if path.stat().st_size > MAX_LOG_BYTES:
        raise DiagnosticError("diagnostic_log_limit")
    return path.read_text(errors="replace")


def environment(venv: Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        env.pop(key, None)
    env.update(
        PYTHONNOUSERSITE="1",
        PIP_CONFIG_FILE=os.devnull,
        PIP_DISABLE_PIP_VERSION_CHECK="1",
        PIP_NO_INPUT="1",
        PIP_INDEX_URL="https://pypi.org/simple",
    )
    env.pop("PIP_EXTRA_INDEX_URL", None)
    if venv is not None:
        env["PATH"] = str(venv / "bin") + os.pathsep + env.get("PATH", "")
    return env


def command(args: list[str], *, cwd: Path, env: dict[str, str], log: Path) -> int:
    with log.open("w") as output:
        result = subprocess.run(
            args, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, check=False
        )
    read_log(log)
    return result.returncode


def checked(args: list[str], *, cwd: Path, env: dict[str, str], log: Path) -> str:
    print(f"ABBA preparation: {log.name}", flush=True)
    if command(args, cwd=cwd, env=env, log=log) != 0:
        raise DiagnosticError("preparation_command_failed")
    return read_log(log).strip()


def verify_host() -> None:
    if (
        platform.python_version() != PYTHON
        or platform.system() != "Linux"
        or platform.machine() != "x86_64"
    ):
        raise DiagnosticError("unexpected_python_or_platform")
    if os.environ.get(IMAGE_VARIABLE) != IMAGE:
        raise DiagnosticError("unexpected_runner_image")
    if any(
        os.environ.get(key)
        for key in (
            "AGENTBOX_WAW_NATIVE_HOST_GATE",
            "AGENTBOX_WAW_ACTUAL_CODEX_AUTH_PROBE",
            "AGENTBOX_WAW_NATIVE_BIN_DIR",
        )
    ):
        raise DiagnosticError("unexpected_host_gate")
    if any(
        os.environ.get(key)
        for key in ("PYTEST_PLUGINS", "PYTEST_ADDOPTS", "PYTEST_DISABLE_PLUGIN_AUTOLOAD")
    ):
        raise DiagnosticError("unexpected_pytest_plugin_configuration")


def verify_source(case: Case, workspace: Path, artifacts: Path) -> None:
    source = case.source(workspace)
    env = environment()
    identity = checked(
        ["git", "rev-parse", "HEAD", "HEAD^{tree}"],
        cwd=source,
        env=env,
        log=artifacts / f"{case.name}-source.log",
    ).splitlines()
    if identity != [case.sha, TREES[case.sha]]:
        raise DiagnosticError("source_identity_mismatch")
    dirty = checked(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=source,
        env=env,
        log=artifacts / f"{case.name}-tracked-status.log",
    )
    if dirty:
        raise DiagnosticError("tracked_source_changed")


def seal_wheels(folder: Path, expected: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    hashes: dict[str, str] = {}
    by_package: dict[str, str] = {}
    found: dict[str, str] = {}
    for path in sorted(folder.iterdir()):
        if path.is_symlink() or not path.is_file() or path.suffix != ".whl":
            raise DiagnosticError("unexpected_wheelhouse_entry")
        with zipfile.ZipFile(path) as wheel:
            names = [n for n in wheel.namelist() if n.endswith(".dist-info/METADATA")]
            if len(names) != 1 or wheel.getinfo(names[0]).file_size > 131072:
                raise DiagnosticError("invalid_wheel_metadata")
            metadata = BytesParser().parsebytes(wheel.read(names[0]))
        name, version = canonical_name(str(metadata.get("Name", ""))), str(
            metadata.get("Version", "")
        )
        if name in found:
            raise DiagnosticError("duplicate_wheel_distribution")
        found[name] = version
        hashes[path.name] = digest(path)
        by_package[name] = hashes[path.name]
    if found != expected:
        raise DiagnosticError("wheel_version_set_mismatch")
    for path in folder.iterdir():
        path.chmod(0o444)
    folder.chmod(0o555)
    return hashes, by_package


def verify_wheels(folder: Path, hashes: dict[str, str]) -> None:
    if folder.stat().st_mode & 0o222 or {p.name for p in folder.iterdir()} != set(hashes):
        raise DiagnosticError("wheelhouse_changed")
    for name, expected in hashes.items():
        path = folder / name
        if path.is_symlink() or path.stat().st_mode & 0o222 or digest(path) != expected:
            raise DiagnosticError("wheel_changed")


def probe(source: Path, requirement_file: Path) -> dict[str, Any]:
    expected = {**pins(requirement_file), "agentbox": "0.3.0rc31"}
    installed: dict[str, str] = {}
    for dist in importlib.metadata.distributions():
        name = canonical_name(str(dist.metadata["Name"]))
        if name in installed:
            raise DiagnosticError("duplicate_installed_distribution")
        installed[name] = dist.version
    if installed != expected or platform.python_version() != PYTHON:
        raise DiagnosticError("installed_version_set_mismatch")
    plugins = sorted(
        (entry.name, entry.value) for entry in importlib.metadata.entry_points(group="pytest11")
    )
    if plugins != [
        ("anyio", "anyio.pytest_plugin"),
        ("platformdirs", "platformdirs.pytest_plugin"),
    ]:
        raise DiagnosticError("pytest_plugin_set_mismatch")
    origins = {}
    for name, relative in MODULES.items():
        module = importlib.import_module(name)
        origin = Path(str(module.__file__)).resolve()
        if origin != (source / relative).resolve():
            raise DiagnosticError("module_origin_mismatch")
        origins[name] = {"source": relative, "sha256": digest(origin)}
    return {
        "python": platform.python_version(),
        "prefix": sys.prefix,
        "packages": installed,
        "plugins": plugins,
        "modules": origins,
    }


def pytest_byte_field(raw: bytes) -> str:
    """Forward-only pytest9.1.1 byte-field encoding; never decode a node ID."""
    controls = {9: r"\t", 10: r"\n", 13: r"\r"}
    return "".join(
        chr(value) if 32 <= value < 127 else controls.get(value, f"\\x{value:02x}") for value in raw
    )


def collection(text: str) -> list[str]:
    rows = [line for line in text.splitlines() if line.startswith("tests/") and "::" in line]
    if len(rows) != 5393 or rows[762] != TARGET or any(IGNORED in row for row in rows):
        raise DiagnosticError("collection_count_or_order_mismatch")
    native = (
        "tests/native/test_waw_auth_native_linux.py::"
        "test_auth_probe_rejects_malformed_or_wrong_parent_record"
    )
    activation = "tests/unit/test_waw_activation.py::test_activation_metadata_must_be_exact"
    suffixes = {
        "1-agentbox-waw-control",
        "2-agentbox-waw-control:agentbox-waw-control",
        "2-agentbox-waw-control:unexpected",
        "2-agentbox-waw-control:agentbox-waw-stream:extra",
    }
    # These four string parameters expose the same actual collection-process PID.
    # Their source is frozen and checked; bytes node IDs are not invertible.
    pids: set[int] = set()
    observed: set[str] = set()
    activation_ids: dict[str, str] = {}
    static_zero = 0
    for row in rows:
        if not row.startswith(activation + "["):
            continue
        if row == activation + "[0-2-agentbox-waw-control:agentbox-waw-stream]":
            static_zero += 1
            continue
        match = re.fullmatch(re.escape(activation) + r"\[([1-9][0-9]{0,9})-(.*)\]", row)
        if (
            match is None
            or not 1 < int(match[1]) < 2**32
            or match[2] not in suffixes
            or match[2] in observed
        ):
            raise DiagnosticError("unexpected_activation_parameter")
        pids.add(int(match[1]))
        observed.add(match[2])
        activation_ids[row] = activation + "[pid-normalized-" + match[2] + "]"
    if len(pids) != 1 or observed != suffixes or static_zero != 1:
        raise DiagnosticError("inconsistent_collection_pid")
    pid = next(iter(pids))
    # Exact frozen _auth_record schema; the collector and controller use this runner UID/GID.
    fields: list[Any] = [
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
    payloads = [struct.pack("!4sBBHIIIQ64s64s4s", *fields) + b"oversize"]
    for index, value in (
        (0, b"AWP2"),
        (1, 2),
        (2, 3),
        (3, 1),
        (5, 0),
        (7, 0),
        (9, b"B" * 64),
        (10, b"\0\0\0\x01"),
    ):
        variant = fields.copy()
        variant[index] = value
        payloads.append(struct.pack("!4sBBHIIIQ64s64s4s", *variant))
    auth_ids = {
        native
        + "["
        + pytest_byte_field(payload)
        + "]": (
            native
            + "["
            + pytest_byte_field(payload[:8])
            + "<runtime-pid>"
            + pytest_byte_field(payload[12:])
            + "]"
        )
        for payload in payloads
    }
    fields[4] = 1
    static_one = native + "[" + pytest_byte_field(struct.pack("!4sBBHIIIQ64s64s4s", *fields)) + "]"
    if len(auth_ids) != 9 or static_one in auth_ids:
        raise DiagnosticError("ambiguous_auth_parameter_encoding")
    normalized: list[str] = []
    observed_auth: set[str] = set()
    short, one = 0, 0
    for row in rows:
        if row in activation_ids:
            row = activation_ids[row]
        elif row.startswith(native + "["):
            if row == native + "[short]":
                short += 1
            elif row == static_one:
                one += 1
            elif row in auth_ids and row not in observed_auth:
                observed_auth.add(row)
                row = auth_ids[row]
            else:
                raise DiagnosticError("unexpected_auth_parameter")
        normalized.append(row)
    if (len(observed_auth), short, one) != (9, 1, 1):
        raise DiagnosticError("unexpected_dynamic_parameter_set")
    return normalized


def outcome(exit_code: int, text: str) -> dict[str, Any]:
    if exit_code not in (0, 1) or not re.search(r"collected 5393 items\b", text):
        raise DiagnosticError("incomplete_pytest_execution")
    summary = next(
        (line for line in reversed(text.splitlines()) if re.search(r"\d+ passed", line)), ""
    )
    counts = {
        word: int(match[1]) if (match := re.search(rf"(\d+) {word}\b", summary)) else 0
        for word in ("passed", "failed", "skipped")
    }
    if (
        sum(counts.values()) != 5393
        or counts["skipped"] != 88
        or (exit_code == 0) != (counts["failed"] == 0)
    ):
        raise DiagnosticError("unexpected_execution_counts")
    notes = [
        line.strip()[:2048]
        for line in text.splitlines()
        if "Native fixture currentness failures:" in line or "Native fixture timing " in line
    ][:8]
    return {
        "exit_code": exit_code,
        **counts,
        "target_failed": f"FAILED {TARGET}" in text,
        "currentness_notes": notes,
    }


def interpretation(results: list[dict[str, Any]]) -> str:
    if len(results) != 4:
        return "incomplete_comparison"
    target = [bool(item["target_failed"]) for item in results]
    if not any(item["failed"] for item in results):
        return "not_reproduced_not_a_fix"
    if (
        target == [True, False, False, True]
        and not results[1]["failed"]
        and not results[2]["failed"]
    ):
        return "observer_association_not_causation"
    if target[1] or target[2]:
        return "diagnostic_target_failure_observed"
    return "inconclusive_failures_retained"


def experiment(workspace: Path, work: Path, artifacts: Path, report: dict[str, Any]) -> int:
    verify_host()
    harness = Path(__file__).resolve()
    requirement_file = harness.with_name("a3-currentness-abba-requirements.txt")
    expected = pins(requirement_file)
    report["requirements_sha256"] = digest(requirement_file)
    wheels = work / "wheels"
    wheels.mkdir()
    checked(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--only-binary=:all:",
            "--no-deps",
            "--dest",
            str(wheels),
            "-r",
            str(requirement_file),
        ],
        cwd=workspace,
        env=environment(),
        log=artifacts / "wheel-download.log",
    )
    hashes, package_hashes = seal_wheels(wheels, expected)
    (artifacts / "wheel-sha256.json").write_text(
        json.dumps(hashes, sort_keys=True, indent=2) + "\n"
    )
    locked = work / "hashed-requirements.txt"
    locked.write_text(
        "".join(
            f"{name}=={version} --hash=sha256:{package_hashes[name]}\n"
            for name, version in sorted(expected.items())
        )
    )
    original_collection: list[str] | None = None
    prepared: list[tuple[Case, str, dict[str, str]]] = []
    for case in CASES:
        report["stage"] = case.name + "_preflight"
        save_report(artifacts, report)
        source = case.source(workspace)
        verify_source(case, workspace, artifacts)
        verify_wheels(wheels, hashes)
        venv = work / case.name / "venv"
        venv.parent.mkdir()
        checked(
            [sys.executable, "-m", "venv", str(venv)],
            cwd=source,
            env=environment(),
            log=artifacts / f"{case.name}-venv.log",
        )
        python = str(venv / "bin/python")
        env = environment(venv)
        checked(
            [
                python,
                "-m",
                "pip",
                "install",
                "--no-index",
                "--find-links",
                str(wheels),
                "--no-deps",
                "--require-hashes",
                "-r",
                str(locked),
            ],
            cwd=source,
            env=env,
            log=artifacts / f"{case.name}-dependencies.log",
        )
        checked(
            [
                python,
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--no-build-isolation",
                "-e",
                str(source) + "[dev]",
            ],
            cwd=source,
            env=env,
            log=artifacts / f"{case.name}-editable.log",
        )
        checked(
            [python, "-m", "pip", "check"],
            cwd=source,
            env=env,
            log=artifacts / f"{case.name}-pip-check.log",
        )
        raw = checked(
            [python, "-B", str(harness), "--probe", str(source)],
            cwd=source,
            env=env,
            log=artifacts / f"{case.name}-imports.json",
        )
        evidence = json.loads(raw)
        if Path(evidence["prefix"]).resolve() != venv.resolve():
            raise DiagnosticError("venv_prefix_mismatch")
        selected = collection(
            checked(
                [python, "-B", "-m", "pytest", "--collect-only", "-q", *case.pytest_args()],
                cwd=source,
                env=env,
                log=artifacts / f"{case.name}-collection.log",
            )
        )
        if original_collection is None:
            original_collection = selected
        elif selected != original_collection:
            raise DiagnosticError("original_collection_sequence_changed")
        prepared.append((case, python, env))
    # All four independent source/environment/collection checks precede measurements.
    for case, python, env in prepared:
        source = case.source(workspace)
        verify_source(case, workspace, artifacts)
        verify_wheels(wheels, hashes)
        report["stage"] = case.name + "_pytest"
        save_report(artifacts, report)
        print(f"ABBA {case.name}: starting original 5393 tests", flush=True)
        log = artifacts / f"{case.name}-pytest.log"
        result = outcome(
            command(
                [python, "-m", "pytest", "-o", "faulthandler_timeout=120", *case.pytest_args()],
                cwd=source,
                env=env,
                log=log,
            ),
            read_log(log),
        )
        report["results"].append({"case": case.name, "sha": case.sha, **result})
        save_report(artifacts, report)
        print(f"ABBA {case.name}: {json.dumps(result, sort_keys=True)}", flush=True)
        verify_source(case, workspace, artifacts)
        verify_wheels(wheels, hashes)
    report["stage"] = "complete"
    report["interpretation"] = interpretation(report["results"])
    save_report(artifacts, report)
    return 1 if any(item["exit_code"] for item in report["results"]) else 0


def save_report(artifacts: Path, report: dict[str, Any]) -> None:
    (artifacts / "summary.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--probe":
        print(
            json.dumps(
                probe(
                    Path(sys.argv[2]).resolve(),
                    Path(__file__).with_name("a3-currentness-abba-requirements.txt"),
                ),
                sort_keys=True,
            )
        )
        return 0
    if len(sys.argv) != 1:
        raise DiagnosticError("unexpected_runner_arguments")
    workspace = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    artifacts = workspace / "a3-abba-artifacts"
    artifacts.mkdir()
    work = Path(os.environ["RUNNER_TEMP"]) / "agentbox-a3-abba"
    work.mkdir()
    report: dict[str, Any] = {
        "schema": 1,
        "python": PYTHON,
        "runner_image": IMAGE,
        "scope": "diagnostic_old_suite_not_qualification",
        "sequence": [case.name for case in CASES],
        "results": [],
        "stage": "prepare",
        "interpretation": "incomplete_comparison",
    }
    save_report(artifacts, report)
    try:
        return experiment(workspace, work, artifacts, report)
    except Exception as error:
        report["interpretation"] = "invalid_or_incomplete_comparison"
        report["error"] = str(error) if type(error) is DiagnosticError else type(error).__name__
        save_report(artifacts, report)
        print(f"ABBA stopped: {report['error']}", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
