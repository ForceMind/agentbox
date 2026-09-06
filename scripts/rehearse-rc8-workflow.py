#!/usr/bin/env python3
"""Run the software-only rc8 dual-artifact rehearsal without disclosing canaries.

This script is the only workflow entry point that handles dynamic rc8 canaries.
It writes subprocess output to a private evidence directory, scans every
declared surface before emitting a non-secret result, and never enables an R12
host capability.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import json
import os
import re
import runpy
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_MAX_LOG_BYTES = 4 * 1024 * 1024
_MAX_SURFACES = 64
_PREDECESSOR_VERSION = "0.3.0rc7"
_CANDIDATE_VERSION = "0.3.0rc8"
_PREDECESSOR_SHA = "87f5bce964eba231a6a7ade73eaedac7e54646ae"
_CANARY_ORDER = ("payload", "private_key", "ticket")
_OPERATIONS_FAILURE_SURFACES = frozenset(
    {
        "predecessor",
        "candidate",
        "provenance",
        "health",
        "apply",
        "rollback",
        "predecessor_apply",
        "candidate_apply",
        "database",
        "backup",
        "receipt",
        "journal",
        "projects",
        "runtime_home",
        "epoch",
        "binding_store",
    }
)


class WorkflowError(RuntimeError):
    def __init__(self, surface: str) -> None:
        self.surface = surface
        super().__init__(surface)


def _fail(surface: str) -> NoReturn:
    raise WorkflowError(surface)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise WorkflowError("artifact input") from exc
    return digest.hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for name, item in pairs:
        if name in value:
            _fail("workflow input")
        value[name] = item
    return value


def _safe_existing_directory(path: Path, surface: str) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        _fail(surface)
    try:
        details = path.lstat()
    except OSError as exc:
        raise WorkflowError(surface) from exc
    if path.is_symlink() or not stat.S_ISDIR(details.st_mode):
        _fail(surface)
    return path.resolve()


def _fresh_directory(path: Path, surface: str) -> Path:
    if not path.is_absolute() or path.exists() or path.is_symlink():
        _fail(surface)
    parent = path.parent
    try:
        details = parent.lstat()
        if parent.is_symlink() or not stat.S_ISDIR(details.st_mode):
            _fail(surface)
        path.mkdir(mode=0o700)
    except WorkflowError:
        raise
    except OSError as exc:
        raise WorkflowError(surface) from exc
    return path.resolve()


def _paths_overlap(first: Path, second: Path) -> bool:
    try:
        first.relative_to(second)
        return True
    except ValueError:
        pass
    try:
        second.relative_to(first)
        return True
    except ValueError:
        return False


def _destroy_canary_root(root: Path) -> None:
    try:
        for path in root.iterdir():
            details = path.lstat()
            if path.is_symlink() or not stat.S_ISREG(details.st_mode):
                _fail("canary cleanup")
            path.unlink()
        parent = root.parent
        root.rmdir()
        descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except WorkflowError:
        raise
    except OSError as exc:
        raise WorkflowError("canary cleanup") from exc


def _safe_file(path: Path, surface: str) -> Path:
    try:
        details = path.lstat()
    except OSError as exc:
        raise WorkflowError(surface) from exc
    if path.is_symlink() or not stat.S_ISREG(details.st_mode):
        _fail(surface)
    return path.resolve()


def _available_loopback_port() -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
    except OSError as exc:
        raise WorkflowError("health port") from exc
    if not isinstance(port, int) or not 1 <= port <= 65_535:
        _fail("health port")
    return port


def _git_head(source: Path, surface: str) -> str:
    try:
        completed = subprocess.run(
            ("git", "-C", str(source), "rev-parse", "HEAD"),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env={"LANG": "C.UTF-8", "PATH": os.defpath},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkflowError(surface) from exc
    value = completed.stdout.strip()
    if completed.returncode != 0 or completed.stderr or _SHA.fullmatch(value) is None:
        _fail(surface)
    return value


def _validate_contract(checker: Path, contract: Path, candidate_sha: str) -> None:
    if _safe_file(checker, "workflow input") != checker.resolve():
        _fail("workflow input")
    try:
        namespace = runpy.run_path(str(checker))
        validator = namespace.get("validate_contract")
        if not callable(validator):
            _fail("workflow input")
        value = validator(contract, candidate_sha)
    except WorkflowError:
        raise
    except Exception as exc:
        raise WorkflowError("workflow input") from exc
    if value != {
        "candidate_sha": candidate_sha,
        "candidate_version": _CANDIDATE_VERSION,
        "predecessor_sha": _PREDECESSOR_SHA,
        "predecessor_version": _PREDECESSOR_VERSION,
    }:
        _fail("workflow input")


def _write_private(path: Path, payload: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise WorkflowError("workflow evidence") from exc


def _artifact_inputs(directory: Path, version: str, surface: str) -> dict[str, Path]:
    root = _safe_existing_directory(directory, surface)
    try:
        artifacts = sorted(root.glob(f"agentbox-{version}-linux-x86_64.tar.gz"))
    except OSError as exc:
        raise WorkflowError(surface) from exc
    if len(artifacts) != 1:
        _fail(surface)
    values = {
        "artifact": artifacts[0],
        "checksums": root / "SHA256SUMS",
        "manifest": root / "RELEASE_MANIFEST.json",
        "sbom": root / "SBOM.spdx.json",
    }
    return {name: _safe_file(path, surface) for name, path in values.items()}


def _environment(work_root: Path, *, installer_source: Path) -> dict[str, str]:
    return {
        "HOME": str(work_root / "home"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.defpath,
        "PIP_CONFIG_FILE": os.devnull,
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_INDEX": "1",
        "PIP_NO_INPUT": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": str(installer_source),
        "TMPDIR": str(work_root / "tmp"),
    }


def _capture_command(
    label: str,
    argv: tuple[str, ...],
    *,
    cwd: Path,
    env: dict[str, str],
    evidence: Path,
    timeout: int,
    failure_surface: Callable[[Path, Path], str] | None = None,
) -> None:
    """Capture bounded child output; no child log reaches workflow stdout/stderr."""

    stdout_path = evidence / f"{label}.stdout"
    stderr_path = evidence / f"{label}.stderr"
    try:
        stdout_stream = os.fdopen(
            os.open(stdout_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600),
            "wb",
        )
        stderr_stream = os.fdopen(
            os.open(stderr_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600),
            "wb",
        )
    except OSError as exc:
        raise WorkflowError("workflow evidence") from exc
    try:
        process = subprocess.Popen(  # noqa: S603 - all callers pass reviewed fixed argv
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        stdout_stream.close()
        stderr_stream.close()
        raise WorkflowError(label) from exc
    total = 0
    lock = threading.Lock()
    exceeded = threading.Event()

    def stop_group(signal_value: signal.Signals) -> None:
        try:
            os.killpg(process.pid, signal_value)
            return
        except (ProcessLookupError, PermissionError):
            pass
        with contextlib.suppress(ProcessLookupError):
            if signal_value == signal.SIGKILL:
                process.kill()
            else:
                process.terminate()

    def drain(source: Any, destination: Any) -> None:
        nonlocal total
        try:
            while True:
                chunk = source.read(64 * 1024)
                if not chunk:
                    return
                with lock:
                    remaining = _MAX_LOG_BYTES - total
                    total += len(chunk)
                    if remaining > 0:
                        destination.write(chunk[:remaining])
                    if total > _MAX_LOG_BYTES and not exceeded.is_set():
                        exceeded.set()
                        stop_group(signal.SIGTERM)
        except (OSError, ValueError):
            return
        finally:
            destination.flush()

    threads = [
        threading.Thread(target=drain, args=(process.stdout, stdout_stream), daemon=True),
        threading.Thread(target=drain, args=(process.stderr, stderr_stream), daemon=True),
    ]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        stop_group(signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            stop_group(signal.SIGKILL)
            process.wait(timeout=10)
    for thread in threads:
        thread.join(timeout=10)
    drain_incomplete = any(thread.is_alive() for thread in threads)
    if drain_incomplete:
        stop_group(signal.SIGKILL)
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=5)
        for source in (process.stdout, process.stderr):
            if source is not None:
                with contextlib.suppress(OSError):
                    source.close()
        for thread in threads:
            thread.join(timeout=5)
        drain_incomplete = any(thread.is_alive() for thread in threads)
    stdout_stream.close()
    stderr_stream.close()
    try:
        before = tuple(path.stat() for path in (stdout_path, stderr_path))
        time.sleep(0.01)
        after = tuple(path.stat() for path in (stdout_path, stderr_path))
    except OSError as exc:
        raise WorkflowError("workflow evidence") from exc
    if any(
        first.st_dev != second.st_dev
        or first.st_ino != second.st_ino
        or first.st_size != second.st_size
        for first, second in zip(before, after, strict=True)
    ):
        _fail(label)
    if drain_incomplete or timed_out or exceeded.is_set() or process.returncode != 0:
        if failure_surface is not None:
            _fail(failure_surface(stdout_path, stderr_path))
        _fail(label)


def _prepare_artifact_environment(
    *,
    label: str,
    artifact: dict[str, Path],
    expected_sha: str,
    expected_ref_kind: str,
    workspace: Path,
    candidate_source: Path,
    work_root: Path,
    evidence: Path,
    native: bool,
) -> None:
    argv = [
        sys.executable,
        str(candidate_source / "scripts/rehearse-waw-artifact.py"),
        "--artifact",
        str(artifact["artifact"]),
        "--checksums",
        str(artifact["checksums"]),
        "--manifest",
        str(artifact["manifest"]),
        "--sbom",
        str(artifact["sbom"]),
        "--expected-source-commit",
        expected_sha,
        "--expected-source-ref-kind",
        expected_ref_kind,
        "--workspace-root",
        str(workspace),
    ]
    if not native:
        argv.append("--skip-native")
    _capture_command(
        label,
        tuple(argv),
        cwd=candidate_source,
        env=_environment(work_root, installer_source=candidate_source / "installer/src"),
        evidence=evidence,
        timeout=900,
    )


def _write_initial_canaries(path: Path) -> dict[str, bytes]:
    values = {
        "payload": b"rc8-payload-" + os.urandom(24).hex().encode("ascii"),
        "private_key": os.urandom(32),
    }
    payload = (
        json.dumps(
            {
                "schema_version": 1,
                "canaries": [
                    {"kind": name, "value_base64": base64.b64encode(values[name]).decode("ascii")}
                    for name in ("payload", "private_key")
                ],
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    _write_private(path, payload)
    return values


def _read_completed_canaries(path: Path, initial: dict[str, bytes]) -> tuple[bytes, ...]:
    try:
        details = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(details.st_mode) or details.st_mode & 0o077:
            _fail("canary registry")
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    except WorkflowError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise WorkflowError("canary registry") from exc
    if not isinstance(value, dict) or set(value) != {"schema_version", "canaries"}:
        _fail("canary registry")
    entries = value.get("canaries")
    if value.get("schema_version") != 1 or not isinstance(entries, list) or len(entries) != 3:
        _fail("canary registry")
    decoded: dict[str, bytes] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"kind", "value_base64"}:
            _fail("canary registry")
        kind = entry.get("kind")
        encoded = entry.get("value_base64")
        if kind not in {"payload", "private_key", "ticket"} or not isinstance(encoded, str):
            _fail("canary registry")
        try:
            raw = base64.b64decode(encoded.encode("ascii"), validate=True)
        except Exception as exc:
            raise WorkflowError("canary registry") from exc
        if base64.b64encode(raw).decode("ascii") != encoded or kind in decoded:
            _fail("canary registry")
        decoded[kind] = raw
    if (
        set(decoded) != {"payload", "private_key", "ticket"}
        or decoded["payload"] != initial["payload"]
        or decoded["private_key"] != initial["private_key"]
        or len(decoded["ticket"]) < 16
        or not decoded["ticket"].startswith(b"wat_")
    ):
        _fail("canary registry")
    return (decoded["payload"], decoded["private_key"], decoded["ticket"])


def _synthetic_runner(
    candidate_workspace: Path,
    candidate_version: str,
    registry: Path,
    *,
    work_root: Path,
    evidence: Path,
) -> None:
    environment_root = candidate_workspace / "environment"
    work = work_root / "synthetic-work"
    synthetic_evidence = evidence / "synthetic"
    for directory in (
        work,
        work_root / "synthetic-home",
        work_root / "synthetic-tmp",
        synthetic_evidence,
    ):
        directory.mkdir(mode=0o700)
    env = {
        "AGENTBOX_RC8_EXPECTED_ARTIFACT_VERSION": candidate_version,
        "AGENTBOX_RC8_EXPECTED_VENV_ROOT": str(environment_root),
        "AGENTBOX_RC8_EVIDENCE_DIR": str(synthetic_evidence),
        "HOME": str(work_root / "synthetic-home"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": f"{environment_root / 'bin'}{os.pathsep}{os.defpath}",
        "PIP_CONFIG_FILE": os.devnull,
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_INDEX": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "TMPDIR": str(work_root / "synthetic-tmp"),
    }
    _capture_command(
        "artifact-synthetic",
        (
            str(environment_root / "bin/python"),
            "-I",
            str(candidate_workspace / "unpacked/rehearsal/waw_rc8_synthetic.py"),
            "--require-loopback",
            "--canary-file",
            str(registry),
        ),
        cwd=work,
        env=env,
        evidence=evidence,
        timeout=90,
    )


def _operations_arguments(
    *,
    predecessor: dict[str, Path],
    candidate: dict[str, Path],
    predecessor_workspace: Path,
    candidate_workspace: Path,
    fixture: Path,
    work_root: Path,
    health_port: int,
) -> tuple[str, ...]:
    fields = [
        ("predecessor", predecessor, _PREDECESSOR_VERSION, _PREDECESSOR_SHA, predecessor_workspace),
        ("candidate", candidate, _CANDIDATE_VERSION, "WORKFLOW_CANDIDATE", candidate_workspace),
    ]
    args: list[str] = []
    for prefix, artifact, version, source_sha, workspace in fields:
        args.extend(
            (
                f"--{prefix}-artifact",
                str(artifact["artifact"]),
                f"--{prefix}-sha256",
                _sha256(artifact["artifact"]),
                f"--{prefix}-version",
                version,
                f"--{prefix}-source-sha",
                source_sha,
                f"--{prefix}-python",
                str(workspace / "environment/bin/python"),
                f"--{prefix}-environment",
                str(workspace / "environment"),
                f"--{prefix}-environment-proof",
                str(workspace / "environment-proof.json"),
            )
        )
    args.extend(
        (
            "--fixture-root",
            str(fixture),
            "--work-root",
            str(work_root),
            "--database",
            str(fixture / "var/lib/agentbox/agentbox.db"),
            "--releases-root",
            str(fixture / "opt/agentbox/releases"),
            "--current-link",
            str(fixture / "opt/agentbox/current"),
            "--project-root",
            str(fixture / "srv/agentbox/projects"),
            "--runtime-home",
            str(fixture / "home/agentbox-runtime"),
            "--epoch-file",
            str(fixture / "var/lib/agentbox-waw/runtime-epoch-v1/epoch.json"),
            "--binding-store",
            str(fixture / "var/lib/agentbox-waw/bindings-v1"),
            "--receipt",
            str(fixture / "var/lib/agentbox/install-receipt.json"),
            "--journal",
            str(fixture / "var/lib/agentbox/install-journal.json"),
            "--backups",
            str(fixture / "var/lib/agentbox/backups"),
            "--project-canary",
            str(fixture / "srv/agentbox/projects/.rc8-operations-canary"),
            "--runtime-home-canary",
            str(fixture / "home/agentbox-runtime/.rc8-operations-canary"),
            "--binding-canary",
            str(fixture / "var/lib/agentbox-waw/bindings-v1/.rc8-operations-canary"),
            "--health-base-url",
            f"http://127.0.0.1:{health_port}",
        )
    )
    return tuple(args)


def _environment_summary(workspace: Path) -> dict[str, object]:
    proof = _safe_file(workspace / "environment-proof.json", "environment proof")
    try:
        value = json.loads(proof.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise WorkflowError("environment proof") from exc
    if not isinstance(value, dict):
        _fail("environment proof")
    wheel = value.get("agentbox_wheel")
    distributions = value.get("installed_distributions")
    modules = value.get("module_origins")
    if (
        not isinstance(wheel, dict)
        or not isinstance(wheel.get("sha256"), str)
        or not isinstance(distributions, list)
        or not isinstance(modules, dict)
    ):
        _fail("environment proof")
    public_distributions: list[dict[str, str]] = []
    for item in distributions:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("name"), str)
            or not isinstance(item.get("version"), str)
        ):
            _fail("environment proof")
        public_distributions.append({"name": item["name"], "version": item["version"]})
    if any(not isinstance(name, str) for name in modules):
        _fail("environment proof")
    return {
        "agentbox_wheel_sha256": wheel["sha256"],
        "installed_distributions": sorted(public_distributions, key=lambda item: item["name"]),
        "module_names": sorted(modules),
    }


def _operations_summary(path: Path) -> dict[str, object]:
    report = _safe_file(path, "operations report")
    try:
        value = json.loads(report.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise WorkflowError("operations report") from exc
    required = {
        "predecessor_version",
        "predecessor_source_sha",
        "candidate_version",
        "candidate_source_sha",
        "backup_id",
        "schema_sha256",
        "logical_data_sha256",
        "project_tree_sha256",
        "runtime_home_tree_sha256",
        "epoch_sha256",
        "binding_store_tree_sha256",
        "health_verified",
    }
    if (
        not isinstance(value, dict)
        or set(value) != required
        or value.get("health_verified") is not True
    ):
        _fail("operations report")
    if any(not isinstance(value[name], str) for name in required - {"health_verified"}):
        _fail("operations report")
    return value


def _operations_failure_surface(_stdout: Path, stderr: Path) -> str:
    """Expose only a fixed operations surface after private stderr is scanned."""

    try:
        raw = stderr.read_bytes()
        text = raw.decode("utf-8", "strict")
    except (OSError, UnicodeError):
        return "upgrade-rollback"
    match = re.fullmatch(
        r"release operations rehearsal failed: ([a-z][a-z0-9_]{0,63}): [A-Za-z0-9 _.:-]{1,300}\n",
        text,
    )
    if match is None or match.group(1) not in _OPERATIONS_FAILURE_SURFACES:
        return "upgrade-rollback"
    return f"upgrade-rollback.{match.group(1)}"


def _write_result(
    path: Path,
    *,
    candidate: dict[str, Path],
    predecessor: dict[str, Path],
    candidate_sha: str,
    canary_scan: str,
    environments: dict[str, dict[str, object]],
    operations: dict[str, object],
) -> None:
    value = {
        "schema_version": 1,
        "candidate": {
            "version": _CANDIDATE_VERSION,
            "source_sha": candidate_sha,
            "artifact_sha256": _sha256(candidate["artifact"]),
        },
        "predecessor": {
            "version": _PREDECESSOR_VERSION,
            "source_sha": _PREDECESSOR_SHA,
            "artifact_sha256": _sha256(predecessor["artifact"]),
        },
        "environment_provenance": "passed",
        "environment_summary": environments,
        "synthetic_waw": "passed",
        "upgrade_rollback": "passed",
        "operations_summary": operations,
        "canary_scan": canary_scan,
        "canary_kinds": ["payload", "private_key", "ticket"],
        "surface_names": [
            "candidate_bundle",
            "predecessor_bundle",
            "candidate_site_packages",
            "candidate_pyvenv",
            "candidate_pip_report",
            "candidate_environment_proof",
            "candidate_unpacked",
            "candidate_workspace_home",
            "predecessor_site_packages",
            "predecessor_pyvenv",
            "predecessor_pip_report",
            "predecessor_environment_proof",
            "predecessor_unpacked",
            "predecessor_workspace_home",
            "fixture_releases",
            "fixture_database",
            "fixture_projects",
            "fixture_runtime_home",
            "fixture_epoch",
            "fixture_bindings",
            "fixture_receipt",
            "fixture_journal",
            "fixture_backups",
            "fixture_current_link",
            "operations_work",
            "workflow_home",
            "workflow_tmp",
            "synthetic_work",
            "synthetic_home",
            "synthetic_tmp",
            "operations_home",
            "operations_tmp",
            "scan_home",
            "scan_tmp",
            "captured_logs",
            "rehearsal_report",
        ],
        "contains_secrets": False,
        "host_qualification": False,
    }
    _write_private(
        path,
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n",
    )


def _environment_surfaces(prefix: str, workspace: Path) -> dict[str, Path]:
    proof_path = _safe_file(workspace / "environment-proof.json", "environment proof")
    try:
        proof = json.loads(proof_path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise WorkflowError("environment proof") from exc
    if not isinstance(proof, dict):
        _fail("environment proof")
    site_packages = proof.get("site_packages")
    if not isinstance(site_packages, str):
        _fail("environment proof")
    site = Path(site_packages)
    environment = workspace / "environment"
    try:
        site.relative_to(environment)
    except ValueError as exc:
        raise WorkflowError("environment proof") from exc
    return {
        f"{prefix}_site_packages": site,
        f"{prefix}_pyvenv": environment / "pyvenv.cfg",
        f"{prefix}_pip_report": workspace / "pip-report.json",
        f"{prefix}_environment_proof": proof_path,
        f"{prefix}_unpacked": workspace / "unpacked",
        f"{prefix}_workspace_home": workspace / "home",
    }


def _existing_fixture_surfaces(fixture: Path, evidence: Path, *, label: str) -> dict[str, Path]:
    values = {
        "fixture_releases": fixture / "opt/agentbox/releases",
        "fixture_database": fixture / "var/lib/agentbox/agentbox.db",
        "fixture_projects": fixture / "srv/agentbox/projects",
        "fixture_runtime_home": fixture / "home/agentbox-runtime",
        "fixture_epoch": fixture / "var/lib/agentbox-waw/runtime-epoch-v1/epoch.json",
        "fixture_bindings": fixture / "var/lib/agentbox-waw/bindings-v1",
        "fixture_receipt": fixture / "var/lib/agentbox/install-receipt.json",
        "fixture_journal": fixture / "var/lib/agentbox/install-journal.json",
        "fixture_backups": fixture / "var/lib/agentbox/backups",
    }
    observed = {
        name: path for name, path in values.items() if path.exists() and not path.is_symlink()
    }
    current = fixture / "opt/agentbox/current"
    if current.is_symlink():
        try:
            target = os.readlink(current)
        except OSError as exc:
            raise WorkflowError("current link") from exc
        link_evidence = evidence / f"current-link-{label}.json"
        _write_private(
            link_evidence,
            (
                json.dumps(
                    {"current_target": target},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n"
            ),
        )
        observed["fixture_current_link"] = link_evidence
    return observed


def _fixture_surfaces(fixture: Path, evidence: Path) -> dict[str, Path]:
    observed = _existing_fixture_surfaces(fixture, evidence, label="success")
    required = {
        "fixture_releases",
        "fixture_database",
        "fixture_projects",
        "fixture_runtime_home",
        "fixture_epoch",
        "fixture_bindings",
        "fixture_receipt",
        "fixture_journal",
        "fixture_backups",
        "fixture_current_link",
    }
    if set(observed) != required:
        _fail("fixture evidence")
    return observed


def _prepare_fixture(root: Path) -> Path:
    fixture = root / "fixture"
    (fixture / "etc").mkdir(parents=True, mode=0o700)
    _write_private(fixture / "etc/os-release", b"ID=ubuntu\nVERSION_ID=24.04\n")
    return fixture


def _prepare_operations_workspace(
    root: Path,
    candidate_workspace: Path,
) -> tuple[Path, dict[str, str]]:
    work = root / "operations-work"
    work.mkdir(mode=0o700)
    home = root / "operations-home"
    temporary = root / "operations-tmp"
    for directory in (home, temporary):
        directory.mkdir(mode=0o700)
    return work, {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": f"{candidate_workspace / 'environment/bin'}{os.pathsep}{os.defpath}",
        "PIP_CONFIG_FILE": os.devnull,
        "PIP_NO_INDEX": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "TMPDIR": str(temporary),
    }


def _prepare_scan_workspace(root: Path, candidate_workspace: Path) -> dict[str, str]:
    home = root / "scan-home"
    temporary = root / "scan-tmp"
    for directory in (home, temporary):
        directory.mkdir(mode=0o700)
    return {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": f"{candidate_workspace / 'environment/bin'}{os.pathsep}{os.defpath}",
        "PIP_CONFIG_FILE": os.devnull,
        "PIP_NO_INDEX": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "TMPDIR": str(temporary),
    }


def _scan(
    *,
    python: Path,
    scanner: Path,
    registry: Path,
    surfaces: dict[str, Path],
    cwd: Path,
    env: dict[str, str],
    evidence: Path,
    label: str,
) -> None:
    if not 1 <= len(surfaces) <= _MAX_SURFACES:
        _fail("canary scan")
    args: list[str] = [str(python), "-I", str(scanner), "--canary-file", str(registry)]
    for name, path in surfaces.items():
        args.extend(("--surface", f"{name}={path}"))
    _capture_command(label, tuple(args), cwd=cwd, env=env, evidence=evidence, timeout=300)


def _scan_failure_evidence(
    *,
    root: Path,
    evidence: Path,
    canary_root: Path,
    initial_canaries: dict[str, bytes],
    candidate_source: Path,
    candidate_bundle: Path,
    predecessor_bundle: Path,
    fixture: Path,
) -> None:
    """Scan every existing surface before reporting a failing rehearsal step."""

    registry = canary_root / "canaries.json"
    try:
        completed = _read_completed_canaries(registry, initial_canaries)
        initial_canaries["ticket"] = completed[2]
    except WorkflowError:
        pass
    partial = canary_root / "partial-canaries.json"
    _write_private(
        partial,
        json.dumps(
            [
                base64.b64encode(initial_canaries[name]).decode("ascii")
                for name in _CANARY_ORDER
                if name in initial_canaries
            ],
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n",
    )
    surfaces = {
        "captured_logs": evidence,
        "candidate_bundle": candidate_bundle,
        "predecessor_bundle": predecessor_bundle,
    }
    for prefix in ("candidate", "predecessor"):
        workspace = root / prefix
        if not workspace.exists() or workspace.is_symlink():
            continue
        unpacked = workspace / "unpacked"
        if unpacked.exists() and not unpacked.is_symlink():
            surfaces[f"{prefix}_unpacked"] = unpacked
        with contextlib.suppress(WorkflowError):
            surfaces.update(_environment_surfaces(prefix, workspace))
    for name in (
        "operations-work",
        "synthetic-work",
        "synthetic-home",
        "synthetic-tmp",
        "operations-home",
        "operations-tmp",
        "rc8-rehearsal-result.json",
    ):
        path = root / name
        if path.exists() and not path.is_symlink():
            surfaces[name.replace("-", "_").removesuffix(".json")] = path
    if fixture.exists() and not fixture.is_symlink():
        surfaces.update(_existing_fixture_surfaces(fixture, evidence, label="failure"))
    for directory in (root / "failure-scan-home", root / "failure-scan-tmp"):
        directory.mkdir(mode=0o700)
    scanner_evidence = root / "failure-scan-private"
    scanner_evidence.mkdir(mode=0o700)
    _scan(
        python=Path(sys.executable),
        scanner=candidate_source / "scripts/scan-rc8-rehearsal-canaries.py",
        registry=partial,
        surfaces=surfaces,
        cwd=root,
        env={
            "HOME": str(root / "failure-scan-home"),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": os.defpath,
            "PIP_CONFIG_FILE": os.devnull,
            "PIP_NO_INDEX": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "TMPDIR": str(root / "failure-scan-tmp"),
        },
        evidence=scanner_evidence,
        label="canary-scan-failure",
    )


def rehearse(arguments: argparse.Namespace) -> dict[str, object]:
    candidate_sha = arguments.candidate_sha
    if _SHA.fullmatch(candidate_sha) is None:
        _fail("workflow input")
    candidate_source = _safe_existing_directory(arguments.candidate_source, "candidate source")
    predecessor_source = _safe_existing_directory(
        arguments.predecessor_source,
        "predecessor source",
    )
    if candidate_source == predecessor_source:
        _fail("workflow input")
    _validate_contract(
        candidate_source / "scripts/check-rc8-rehearsal-contract.py",
        _safe_file(arguments.contract, "workflow input"),
        candidate_sha,
    )
    if _git_head(candidate_source, "candidate source") != candidate_sha:
        _fail("candidate source")
    if _git_head(predecessor_source, "predecessor source") != _PREDECESSOR_SHA:
        _fail("predecessor source")
    candidate_artifact = _artifact_inputs(
        arguments.candidate_artifact_directory,
        _CANDIDATE_VERSION,
        "candidate artifact",
    )
    predecessor_artifact = _artifact_inputs(
        arguments.predecessor_artifact_directory,
        _PREDECESSOR_VERSION,
        "predecessor artifact",
    )
    root = _fresh_directory(arguments.work_root, "workflow workspace")
    evidence = root / "evidence"
    evidence.mkdir(mode=0o700)
    for directory in (root / "home", root / "tmp"):
        directory.mkdir(mode=0o700)
    canary_root = _fresh_directory(arguments.canary_root, "canary registry")
    if any(
        _paths_overlap(canary_root, path)
        for path in (
            root,
            candidate_source,
            predecessor_source,
            candidate_artifact["artifact"].parent,
            predecessor_artifact["artifact"].parent,
        )
    ):
        _fail("canary registry")
    registry = canary_root / "canaries.json"
    initial_canaries = _write_initial_canaries(registry)
    candidate_workspace = root / "candidate"
    predecessor_workspace = root / "predecessor"
    fixture = root / "fixture"

    def guarded(callback: Any) -> Any:
        try:
            return callback()
        except Exception as exc:
            _scan_failure_evidence(
                root=root,
                evidence=evidence,
                canary_root=canary_root,
                initial_canaries=initial_canaries,
                candidate_source=candidate_source,
                candidate_bundle=candidate_artifact["artifact"].parent,
                predecessor_bundle=predecessor_artifact["artifact"].parent,
                fixture=fixture,
            )
            if isinstance(exc, WorkflowError):
                raise
            raise WorkflowError("internal") from exc

    guarded(
        lambda: _prepare_artifact_environment(
            label="candidate-provenance",
            artifact=candidate_artifact,
            expected_sha=candidate_sha,
            expected_ref_kind=arguments.candidate_source_ref_kind,
            workspace=candidate_workspace,
            candidate_source=candidate_source,
            work_root=root,
            evidence=evidence,
            native=True,
        )
    )
    guarded(
        lambda: _prepare_artifact_environment(
            label="predecessor-provenance",
            artifact=predecessor_artifact,
            expected_sha=_PREDECESSOR_SHA,
            expected_ref_kind="main",
            workspace=predecessor_workspace,
            candidate_source=candidate_source,
            work_root=root,
            evidence=evidence,
            native=False,
        )
    )
    guarded(
        lambda: _synthetic_runner(
            candidate_workspace,
            _CANDIDATE_VERSION,
            registry,
            work_root=root,
            evidence=evidence,
        )
    )
    completed_canaries = guarded(lambda: _read_completed_canaries(registry, initial_canaries))
    initial_canaries["ticket"] = completed_canaries[2]
    fixture = guarded(lambda: _prepare_fixture(root))
    operations_work, operations_environment = guarded(
        lambda: _prepare_operations_workspace(root, candidate_workspace)
    )

    def operation_arguments() -> list[str]:
        values = list(
            _operations_arguments(
                predecessor=predecessor_artifact,
                candidate=candidate_artifact,
                predecessor_workspace=predecessor_workspace,
                candidate_workspace=candidate_workspace,
                fixture=fixture,
                work_root=operations_work,
                health_port=_available_loopback_port(),
            )
        )
        values[values.index("WORKFLOW_CANDIDATE")] = candidate_sha
        return values

    operation_args = guarded(operation_arguments)
    guarded(
        lambda: _capture_command(
            "upgrade-rollback",
            (
                str(candidate_workspace / "environment/bin/python"),
                "-I",
                str(candidate_source / "scripts/rehearse-release-operations.py"),
                *operation_args,
            ),
            cwd=operations_work,
            env=operations_environment,
            evidence=evidence,
            timeout=900,
            failure_surface=_operations_failure_surface,
        )
    )
    environments = guarded(
        lambda: {
            "candidate": _environment_summary(candidate_workspace),
            "predecessor": _environment_summary(predecessor_workspace),
        }
    )
    operations = guarded(lambda: _operations_summary(evidence / "upgrade-rollback.stdout"))
    result = root / "rc8-rehearsal-result.json"
    guarded(
        lambda: _write_result(
            result,
            candidate=candidate_artifact,
            predecessor=predecessor_artifact,
            candidate_sha=candidate_sha,
            canary_scan="pending",
            environments=environments,
            operations=operations,
        )
    )
    scan_environment = guarded(lambda: _prepare_scan_workspace(root, candidate_workspace))
    scanner_evidence = guarded(
        lambda: _fresh_directory(root / "scanner-private", "scanner evidence")
    )

    def rehearsal_surfaces() -> dict[str, Path]:
        return {
            "candidate_bundle": candidate_artifact["artifact"].parent,
            "predecessor_bundle": predecessor_artifact["artifact"].parent,
            **_environment_surfaces("candidate", candidate_workspace),
            **_environment_surfaces("predecessor", predecessor_workspace),
            **_fixture_surfaces(fixture, evidence),
            "operations_work": operations_work,
            "workflow_home": root / "home",
            "workflow_tmp": root / "tmp",
            "synthetic_work": root / "synthetic-work",
            "synthetic_home": root / "synthetic-home",
            "synthetic_tmp": root / "synthetic-tmp",
            "operations_home": root / "operations-home",
            "operations_tmp": root / "operations-tmp",
            "scan_home": root / "scan-home",
            "scan_tmp": root / "scan-tmp",
            "captured_logs": evidence,
            "rehearsal_report": result,
        }

    surfaces = guarded(rehearsal_surfaces)
    guarded(
        lambda: _scan(
            python=candidate_workspace / "environment/bin/python",
            scanner=candidate_source / "scripts/scan-rc8-rehearsal-canaries.py",
            registry=registry,
            surfaces=surfaces,
            cwd=root,
            env=scan_environment,
            evidence=scanner_evidence,
            label="canary-scan",
        )
    )

    def replace_result() -> None:
        result.unlink()
        _write_result(
            result,
            candidate=candidate_artifact,
            predecessor=predecessor_artifact,
            candidate_sha=candidate_sha,
            canary_scan="passed",
            environments=environments,
            operations=operations,
        )

    guarded(replace_result)
    guarded(
        lambda: _scan(
            python=candidate_workspace / "environment/bin/python",
            scanner=candidate_source / "scripts/scan-rc8-rehearsal-canaries.py",
            registry=registry,
            surfaces=surfaces,
            cwd=root,
            env=scan_environment,
            evidence=scanner_evidence,
            label="canary-scan-final",
        )
    )
    value = json.loads(result.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    if not isinstance(value, dict):
        _fail("workflow result")
    _destroy_canary_root(canary_root)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument(
        "--candidate-source-ref-kind",
        choices=("pull_request_head", "main"),
        required=True,
    )
    parser.add_argument("--candidate-source", type=Path, required=True)
    parser.add_argument("--predecessor-source", type=Path, required=True)
    parser.add_argument("--candidate-artifact-directory", type=Path, required=True)
    parser.add_argument("--predecessor-artifact-directory", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--canary-root", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        value = rehearse(arguments)
    except WorkflowError as exc:
        parser.exit(1, f"rc8 workflow rehearsal failed: {exc.surface}\n")
    except Exception:
        parser.exit(1, "rc8 workflow rehearsal failed: internal\n")
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
