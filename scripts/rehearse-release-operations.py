#!/usr/bin/env python3
"""Rehearse an exact artifact upgrade and receipt-bound rollback in a fixture root.

The public entry point deliberately accepts every artifact, interpreter and
persistent path.  It never selects ``/`` and never invokes systemd.  Production
workflow code is expected to provide the two artifact-only Python environments
and a free explicit loopback endpoint.  The rehearsal starts and stops the
predecessor artifact API itself for the final process-bound health probes.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import inspect
import json
import os
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import NoReturn, Protocol, cast

from agentbox_installer.artifact import (
    ArtifactError,
    ReleaseManifest,
    extract_verified_tar,
    scan_wheel_bytes,
    sha256_file,
    verify_artifact_digest,
    verify_release,
)
from agentbox_installer.backup import BackupResult, verify_sqlite_backup

_SHA256 = re.compile(r"[0-9a-f]{64}")
_SOURCE_SHA = re.compile(r"[0-9a-f]{40}")
_BACKUP_ID = re.compile(r"[A-Za-z0-9_.-]{1,80}")
_TRANSACTION_ID = re.compile(r"[0-9a-f]{32}")
_MAX_JSON_BYTES = 1024 * 1024
_MAX_TREE_MEMBERS = 100_000
_MAX_TREE_BYTES = 2 * 1024 * 1024 * 1024
_MAX_DATABASE_ROWS = 2_000_000
_UNIT_NAMES = (
    "agentbox-api.service",
    "agentbox-worker.service",
    "agentbox-runtime.service",
    "agentbox-helper.socket",
    "agentbox-helper.service",
)
_APPLY_STEPS = (
    "identities",
    "directories",
    "configuration",
    "release_staged",
    "database_migrated",
    "units_installed",
    "release_activated",
    "health_verified",
    "retention_applied",
    "receipt_written",
)
_ROLLBACK_STEPS = (
    "rollback_preflight",
    "services_stopped",
    "database_restored",
    "release_activated",
    "services_restarted",
    "rollback_verified",
    "receipt_written",
)
_ENVIRONMENT_MODULES = (
    "agentbox_api",
    "agentbox_browser_trust",
    "agentbox_cli",
    "agentbox_core",
    "agentbox_helper",
    "agentbox_installer",
    "agentbox_protocol",
    "agentbox_runtime",
    "agentbox_worker",
)


class RehearsalError(RuntimeError):
    """A fail-closed operations-rehearsal check failed."""


def _fail(surface: str, reason: str) -> NoReturn:
    raise RehearsalError(f"{surface}: {reason}")


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _read_json(path: Path, surface: str) -> dict[str, object]:
    try:
        details = path.lstat()
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
            _fail(surface, "evidence file is unsafe")
        if details.st_size > _MAX_JSON_BYTES:
            _fail(surface, "evidence file exceeds its limit")
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
        )
    except RehearsalError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise RehearsalError(f"{surface}: evidence is unavailable or invalid") from exc
    if not isinstance(value, dict):
        _fail(surface, "evidence must be a JSON object")
    return cast(dict[str, object], value)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _hash_parts(parts: Sequence[bytes]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)
    return digest.hexdigest()


def _safe_root(path: Path, surface: str) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        _fail(surface, "root must be an absolute normalized path")
    absolute = Path(os.path.abspath(path))
    if absolute == Path("/") or len(absolute.parts) < 3:
        _fail(surface, "root is too broad")
    current = Path("/")
    for part in absolute.parts[1:]:
        current /= part
        try:
            details = current.lstat()
        except OSError as exc:
            raise RehearsalError(f"{surface}: root is unavailable") from exc
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
            _fail(surface, "root or its parent chain is unsafe")
    return absolute


def _path_in_root(root: Path, path: Path, surface: str) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        _fail(surface, "path must be absolute and normalized")
    absolute = Path(os.path.abspath(path))
    try:
        relative = absolute.relative_to(root)
    except ValueError as exc:
        raise RehearsalError(f"{surface}: path escapes the fixture root") from exc
    if not relative.parts:
        _fail(surface, "path must not equal the fixture root")
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        try:
            details = current.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            raise RehearsalError(f"{surface}: parent chain is unavailable") from exc
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
            _fail(surface, "parent chain is unsafe")
    return absolute


@dataclass(frozen=True)
class ArtifactInput:
    artifact: Path
    sha256: str
    version: str
    source_sha: str
    python: Path
    environment_root: Path
    environment_proof: Path


@dataclass(frozen=True)
class RehearsalPaths:
    fixture_root: Path
    work_root: Path
    database: Path
    releases_root: Path
    current_link: Path
    project_root: Path
    runtime_home: Path
    epoch_file: Path
    binding_store: Path
    receipt: Path
    journal: Path
    backups: Path
    project_canary: Path
    runtime_home_canary: Path
    binding_canary: Path


@dataclass(frozen=True)
class ArtifactEvidence:
    version: str
    source_sha: str
    database_revision: str
    artifact_sha256: str
    wheel_sha256: str
    environment_prefix: str
    installer_module: str


@dataclass(frozen=True)
class OperationOutcome:
    action: str
    version: str
    previous_version: str | None
    changed: bool
    health_verified: bool
    package_version: str
    environment_prefix: str
    installer_module: str
    alembic_upgrades: tuple[str, ...]
    database_revision: str | None


@dataclass(frozen=True)
class DatabaseFingerprint:
    schema_sha256: str
    logical_data_sha256: str
    row_count: int


@dataclass(frozen=True)
class PersistentFingerprint:
    database: DatabaseFingerprint
    project_tree_sha256: str
    runtime_home_tree_sha256: str
    epoch_sha256: str
    binding_store_tree_sha256: str


@dataclass(frozen=True)
class RehearsalResult:
    predecessor_version: str
    predecessor_source_sha: str
    candidate_version: str
    candidate_source_sha: str
    backup_id: str
    schema_sha256: str
    logical_data_sha256: str
    project_tree_sha256: str
    runtime_home_tree_sha256: str
    epoch_sha256: str
    binding_store_tree_sha256: str
    health_verified: bool


class OperationsRunner(Protocol):
    def prove(
        self,
        artifact: ArtifactInput,
        evidence: ArtifactEvidence,
        fixture_root: Path,
    ) -> OperationOutcome: ...

    def apply(
        self,
        artifact: ArtifactInput,
        evidence: ArtifactEvidence,
        fixture_root: Path,
    ) -> OperationOutcome: ...

    def rollback(
        self,
        artifact: ArtifactInput,
        evidence: ArtifactEvidence,
        fixture_root: Path,
        target_version: str,
    ) -> OperationOutcome: ...


class HealthProbe(Protocol):
    def read(self, expected: HealthExpectation) -> HealthObservation: ...


@dataclass(frozen=True)
class HealthExpectation:
    version: str
    source_sha: str
    artifact_sha256: str
    wheel_sha256: str
    environment_prefix: str
    python: str
    release_root: str
    database: str
    project_root: str
    current_link: str


@dataclass(frozen=True)
class HealthObservation:
    responses: Mapping[str, Mapping[str, object]]
    pid: int
    listener_owned: bool
    version: str
    source_sha: str
    artifact_sha256: str
    wheel_sha256: str
    environment_prefix: str
    python: str
    release_root: str
    database: str
    project_root: str
    current_link: str


class ArtifactPythonRunner:
    """Run only the typed internal driver under a supplied artifact-only Python."""

    def __init__(self, work_root: Path, script: Path | None = None) -> None:
        self._work_root = _safe_root(work_root, "work_root")
        self._script = (script or Path(__file__)).resolve()

    def prove(
        self,
        artifact: ArtifactInput,
        evidence: ArtifactEvidence,
        fixture_root: Path,
    ) -> OperationOutcome:
        return self._run(artifact, evidence, fixture_root, "prove", None)

    def apply(
        self,
        artifact: ArtifactInput,
        evidence: ArtifactEvidence,
        fixture_root: Path,
    ) -> OperationOutcome:
        return self._run(artifact, evidence, fixture_root, "apply", None)

    def rollback(
        self,
        artifact: ArtifactInput,
        evidence: ArtifactEvidence,
        fixture_root: Path,
        target_version: str,
    ) -> OperationOutcome:
        return self._run(artifact, evidence, fixture_root, "rollback", target_version)

    def _run(
        self,
        artifact: ArtifactInput,
        evidence: ArtifactEvidence,
        fixture_root: Path,
        action: str,
        target_version: str | None,
    ) -> OperationOutcome:
        argv = [
            str(artifact.python),
            "-B",
            "-I",
            str(self._script),
            "__artifact-driver",
            "--action",
            action,
            "--fixture-root",
            str(fixture_root),
            "--artifact",
            str(artifact.artifact),
            "--sha256",
            artifact.sha256,
            "--expected-version",
            evidence.version,
            "--expected-environment",
            str(artifact.environment_root),
        ]
        if target_version is not None:
            argv.extend(("--target-version", target_version))
        try:
            completed = subprocess.run(
                tuple(argv),
                cwd=artifact.environment_root,
                env={
                    "PATH": str(artifact.environment_root / "bin"),
                    "LANG": "C.UTF-8",
                    "PIP_CONFIG_FILE": os.devnull,
                    "PIP_NO_INDEX": "1",
                    "PIP_NO_INPUT": "1",
                    "PYTHONNOUSERSITE": "1",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "TMPDIR": str(self._work_root),
                },
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=600,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RehearsalError(f"{action}: artifact-local installer did not complete") from exc
        if completed.returncode != 0:
            _fail(action, "artifact-local installer returned failure")
        try:
            value = json.loads(
                completed.stdout.decode("utf-8", "strict"),
                object_pairs_hook=_strict_object,
            )
            if not isinstance(value, dict) or set(value) != {
                "action",
                "version",
                "previous_version",
                "changed",
                "health_verified",
                "package_version",
                "environment_prefix",
                "installer_module",
                "alembic_upgrades",
                "database_revision",
            }:
                _fail(action, "artifact-local result schema is invalid")
            previous = value.get("previous_version")
            upgrades = value.get("alembic_upgrades")
            database_revision = value.get("database_revision")
            string_fields = (
                value.get("action"),
                value.get("version"),
                value.get("package_version"),
                value.get("environment_prefix"),
                value.get("installer_module"),
            )
            if (
                any(not isinstance(item, str) for item in string_fields)
                or (previous is not None and not isinstance(previous, str))
                or type(value.get("changed")) is not bool
                or type(value.get("health_verified")) is not bool
                or not isinstance(upgrades, list)
                or any(not isinstance(item, str) for item in upgrades)
                or (database_revision is not None and not isinstance(database_revision, str))
            ):
                _fail(action, "artifact-local result values are invalid")
            outcome = OperationOutcome(
                action=cast(str, value["action"]),
                version=cast(str, value["version"]),
                previous_version=previous,
                changed=cast(bool, value["changed"]),
                health_verified=cast(bool, value["health_verified"]),
                package_version=cast(str, value["package_version"]),
                environment_prefix=cast(str, value["environment_prefix"]),
                installer_module=cast(str, value["installer_module"]),
                alembic_upgrades=tuple(cast(list[str], upgrades)),
                database_revision=database_revision,
            )
        except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise RehearsalError(f"{action}: artifact-local result is invalid") from exc
        if action == "rollback":
            if target_version is None:
                _fail(action, "rollback target is missing")
            result_version = target_version
        else:
            result_version = evidence.version
        _validate_operation_outcome(
            outcome,
            artifact,
            evidence,
            action,
            result_version=result_version,
            expected_database_revision=(
                evidence.database_revision
                if action == "apply"
                else outcome.database_revision
                if action == "rollback"
                else None
            ),
        )
        return outcome


class LoopbackHealthProbe:
    """Probe a loopback listener owned by one exact artifact API process on Linux."""

    _FIXED_CODE = (
        "import os,sys;"
        "keys=('AGENTBOX_DATA_DIR','AGENTBOX_DATABASE_URL','AGENTBOX_STATIC_DIR',"
        "'AGENTBOX_PROJECT_ROOT','AGENTBOX_BIND_HOST','AGENTBOX_BIND_PORT');"
        "os.environ.update(dict(zip(keys,sys.argv[1:7],strict=True)));"
        "os.environ['AGENTBOX_ENV']='test';"
        "from agentbox_api.main import run;run()"
    )

    def __init__(self, base_url: str) -> None:
        parsed = urllib.parse.urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or parsed.port is None
        ):
            _fail("health", "base URL must be an explicit IPv4 loopback HTTP endpoint")
        self._base_url = f"http://127.0.0.1:{parsed.port}"
        self._port = parsed.port

    def read(self, expected: HealthExpectation) -> HealthObservation:
        if sys.platform != "linux":
            _fail("health", "process-bound loopback proof requires Linux /proc")
        command = self._expected_command(expected)
        try:
            process = subprocess.Popen(  # noqa: S603 - exact artifact Python and fixed code
                command,
                cwd=expected.release_root,
                env={
                    "PATH": f"{expected.environment_prefix}/bin",
                    "LANG": "C.UTF-8",
                    "PYTHONNOUSERSITE": "1",
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise RehearsalError("health: exact artifact API process could not start") from exc
        listener_owned = False
        observed: dict[str, Mapping[str, object]] = {}
        release_root = ""
        try:
            process_root = Path(f"/proc/{process.pid}")
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    _fail("health", "exact artifact API process exited before readiness")
                try:
                    observed_command = tuple(
                        item.decode("utf-8", "strict")
                        for item in (process_root / "cmdline").read_bytes().split(b"\0")
                        if item
                    )
                    release_root = str((process_root / "cwd").resolve(strict=True))
                except (OSError, UnicodeError) as exc:
                    raise RehearsalError("health: API process provenance is unavailable") from exc
                if observed_command != command:
                    _fail("health", "API process command provenance mismatch")
                if release_root != expected.release_root:
                    _fail("health", "API process release-root provenance mismatch")
                listener_port = self._process_listener_port(process_root)
                listener_owned = listener_port is not None
                if listener_port is not None:
                    try:
                        observed = self._read_endpoints(listener_port)
                    except (OSError, UnicodeError, ValueError, urllib.error.URLError):
                        time.sleep(0.05)
                        continue
                    break
                time.sleep(0.05)
            if not listener_owned or set(observed) != {"health", "ready", "meta"}:
                _fail("health", "exact artifact API process did not become ready")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        return HealthObservation(
            responses=observed,
            pid=process.pid,
            listener_owned=listener_owned,
            version=command[11],
            source_sha=command[12],
            artifact_sha256=command[13],
            wheel_sha256=command[14],
            environment_prefix=expected.environment_prefix,
            python=command[0],
            release_root=release_root,
            database=expected.database,
            project_root=command[8],
            current_link=command[15],
        )

    def _expected_command(self, expected: HealthExpectation) -> tuple[str, ...]:
        return (
            expected.python,
            "-B",
            "-I",
            "-c",
            self._FIXED_CODE,
            str(Path(expected.database).parent),
            f"sqlite+pysqlite:///{expected.database}",
            f"{expected.release_root}/web/dist",
            expected.project_root,
            "127.0.0.1",
            str(self._port),
            expected.version,
            expected.source_sha,
            expected.artifact_sha256,
            expected.wheel_sha256,
            expected.current_link,
        )

    def _read_endpoints(self, port: int) -> dict[str, Mapping[str, object]]:
        observed: dict[str, Mapping[str, object]] = {}
        for name, endpoint in (
            ("health", "healthz"),
            ("ready", "readyz"),
            ("meta", "api/v1/meta"),
        ):
            with urllib.request.urlopen(  # noqa: S310 - validated fixed loopback base
                f"http://127.0.0.1:{port}/{endpoint}", timeout=2
            ) as response:
                payload = response.read(4097)
                if response.status != 200 or len(payload) > 4096:
                    _fail("health", f"{name} probe failed")
            value = json.loads(payload, object_pairs_hook=_strict_object)
            if not isinstance(value, dict):
                _fail("health", f"{name} response is invalid")
            observed[name] = cast(dict[str, object], value)
        return observed

    def _process_listener_port(self, process_root: Path) -> int | None:
        socket_inodes: set[str] = set()
        try:
            for descriptor in (process_root / "fd").iterdir():
                target = os.readlink(descriptor)
                match = re.fullmatch(r"socket:\[([0-9]+)\]", target)
                if match is not None:
                    socket_inodes.add(match.group(1))
            rows = Path("/proc/net/tcp").read_text(encoding="ascii").splitlines()[1:]
        except (OSError, UnicodeError) as exc:
            raise RehearsalError("health: API listener ownership is unavailable") from exc
        ports: set[int] = set()
        for row in rows:
            fields = row.split()
            local = fields[1] if len(fields) >= 2 else ""
            address, separator, port_value = local.partition(":")
            if (
                len(fields) >= 10
                and separator == ":"
                and address == "0100007F"
                and fields[3] == "0A"
                and fields[9] in socket_inodes
            ):
                try:
                    port = int(port_value, 16)
                except ValueError:
                    _fail("health", "API listener port provenance is invalid")
                if self._port in {0, port}:
                    ports.add(port)
        if len(ports) != 1:
            return None
        return ports.pop()


def _validate_operation_outcome(
    outcome: OperationOutcome,
    artifact: ArtifactInput,
    evidence: ArtifactEvidence,
    action: str,
    *,
    result_version: str,
    expected_database_revision: str | None,
) -> None:
    if outcome.action != action:
        _fail(action, "operation identity mismatch")
    if outcome.version != result_version or outcome.package_version != evidence.version:
        _fail(action, "artifact-local version mismatch")
    expected_prefix = Path(os.path.abspath(artifact.environment_root))
    observed_prefix = Path(os.path.abspath(outcome.environment_prefix))
    if (
        observed_prefix != expected_prefix
        or outcome.environment_prefix != evidence.environment_prefix
    ):
        _fail(action, "artifact environment prefix mismatch")
    module = Path(os.path.abspath(outcome.installer_module))
    try:
        module.relative_to(expected_prefix)
    except ValueError as exc:
        raise RehearsalError(
            f"{action}: installer module is outside the artifact environment"
        ) from exc
    if str(module) != evidence.installer_module:
        _fail(action, "installer module does not match the artifact environment proof")
    if action == "apply" and outcome.alembic_upgrades != (evidence.database_revision,):
        _fail(action, "exact Alembic upgrade evidence is missing")
    if action in {"rollback", "prove"} and outcome.alembic_upgrades:
        _fail(action, "operation unexpectedly ran an Alembic upgrade")
    if outcome.database_revision != expected_database_revision:
        _fail(action, "database revision read-back mismatch")
    if action == "prove" and (
        outcome.previous_version is not None or outcome.changed or outcome.health_verified
    ):
        _fail(action, "environment proof unexpectedly performed an operation")


def _canonical_distribution_name(value: object, surface: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 200:
        _fail(surface, "distribution name is invalid")
    normalized = re.sub(r"[-_.]+", "-", value).casefold()
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,199}", normalized) is None:
        _fail(surface, "distribution name is invalid")
    return normalized


def _read_pip_report_inventory(
    report: Path,
    unpacked_root: Path,
    manifest: ReleaseManifest,
    surface: str,
) -> tuple[dict[str, str], ...]:
    value = _read_json(report, f"{surface}_pip_report")
    installed = value.get("install")
    if not isinstance(installed, list) or not installed:
        _fail(surface, "pip report install inventory is invalid")
    wheelhouse = unpacked_root / "wheelhouse"
    if wheelhouse.is_symlink() or not wheelhouse.is_dir():
        _fail(surface, "unpacked wheelhouse is unavailable")
    values: list[dict[str, str]] = []
    names: set[str] = set()
    wheels: set[Path] = set()
    for item in installed:
        if not isinstance(item, dict):
            _fail(surface, "pip report install inventory is invalid")
        metadata = item.get("metadata")
        download = item.get("download_info")
        if not isinstance(metadata, dict) or not isinstance(download, dict):
            _fail(surface, "pip report install inventory is invalid")
        name = _canonical_distribution_name(metadata.get("name"), surface)
        version = metadata.get("version")
        url = download.get("url")
        archive = download.get("archive_info")
        if (
            not isinstance(version, str)
            or not version
            or not isinstance(url, str)
            or not isinstance(archive, dict)
        ):
            _fail(surface, "pip report install inventory is invalid")
        parsed = urllib.parse.urlsplit(url)
        if (
            parsed.scheme != "file"
            or parsed.netloc not in {"", "localhost"}
            or parsed.query
            or parsed.fragment
        ):
            _fail(surface, "pip report install inventory is invalid")
        wheel = Path(urllib.parse.unquote(parsed.path)).resolve()
        try:
            relative = wheel.relative_to(unpacked_root).as_posix()
        except ValueError as exc:
            raise RehearsalError(f"{surface}: pip report wheel escaped unpacked artifact") from exc
        hashes = archive.get("hashes")
        expected_digest = manifest.files.get(relative)
        if (
            name in names
            or wheel in wheels
            or not relative.startswith("wheelhouse/")
            or wheel.is_symlink()
            or not wheel.is_file()
            or not isinstance(hashes, dict)
            or hashes.get("sha256") != expected_digest
            or expected_digest is None
            or sha256_file(wheel) != expected_digest
        ):
            _fail(surface, "pip report wheel provenance is invalid")
        names.add(name)
        wheels.add(wheel)
        values.append(
            {
                "name": name,
                "version": version,
                "wheel_path": relative,
                "wheel_sha256": expected_digest,
            }
        )
    return tuple(sorted(values, key=lambda item: item["name"]))


def _site_distribution_inventory(site_packages: Path, surface: str) -> tuple[dict[str, str], ...]:
    try:
        entries = sorted(site_packages.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise RehearsalError(f"{surface}: site packages are unavailable") from exc
    values: list[dict[str, str]] = []
    names: set[str] = set()
    for entry in entries:
        if entry.name.endswith(".egg-info"):
            _fail(surface, "legacy distribution metadata is forbidden")
        if not entry.name.endswith(".dist-info"):
            continue
        try:
            details = entry.lstat()
        except OSError as exc:
            raise RehearsalError(f"{surface}: distribution metadata is unavailable") from exc
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
            _fail(surface, "distribution metadata is unsafe")
        metadata = entry / "METADATA"
        try:
            raw = metadata.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise RehearsalError(f"{surface}: distribution metadata is unavailable") from exc
        if len(raw) > _MAX_JSON_BYTES:
            _fail(surface, "distribution metadata exceeds its limit")
        name_matches = re.findall(r"(?m)^Name: ([^\r\n]+)$", raw)
        version_matches = re.findall(r"(?m)^Version: ([^\r\n]+)$", raw)
        if len(name_matches) != 1 or len(version_matches) != 1 or not version_matches[0]:
            _fail(surface, "distribution metadata is invalid")
        name = _canonical_distribution_name(name_matches[0], surface)
        if name in names:
            _fail(surface, "distribution metadata is duplicated")
        names.add(name)
        values.append({"name": name, "version": version_matches[0]})
    return tuple(sorted(values, key=lambda item: item["name"]))


def _verify_installed_wheel_payload(
    wheel: Path,
    site_packages: Path,
    surface: str,
) -> None:
    try:
        scan_wheel_bytes(wheel.read_bytes(), ())
        with zipfile.ZipFile(wheel) as archive:
            observed: set[str] = set()
            for member in archive.infolist():
                canonical_name = member.filename.rstrip("/")
                relative = PurePosixPath(canonical_name)
                if (
                    not canonical_name
                    or relative.is_absolute()
                    or any(part in {"", ".", ".."} for part in canonical_name.split("/"))
                    or "\\" in canonical_name
                    or canonical_name in observed
                ):
                    _fail(surface, "wheel contains an unsafe path")
                observed.add(canonical_name)
                unix_mode = member.external_attr >> 16
                file_type = stat.S_IFMT(unix_mode)
                if file_type and not (stat.S_ISREG(unix_mode) or stat.S_ISDIR(unix_mode)):
                    _fail(surface, "wheel contains a special filesystem object")
                if member.is_dir() or member.filename.endswith(".dist-info/RECORD"):
                    continue
                if ".data/" in member.filename:
                    _fail(surface, "wheel data scheme is unsupported")
                target = site_packages.joinpath(*relative.parts)
                try:
                    details = target.lstat()
                except OSError as exc:
                    raise RehearsalError(
                        f"{surface}: installed wheel payload is incomplete"
                    ) from exc
                if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
                    _fail(surface, "installed wheel payload is unsafe")
                if sha256_file(target) != hashlib.sha256(archive.read(member)).hexdigest():
                    _fail(surface, "installed wheel payload digest mismatch")
    except RehearsalError:
        raise
    except (ArtifactError, OSError, KeyError, RuntimeError, zipfile.BadZipFile) as exc:
        raise RehearsalError(f"{surface}: wheel verification failed") from exc


def _validate_environment_binding(
    spec: ArtifactInput,
    manifest: ReleaseManifest,
    release: Path,
    surface: str,
) -> tuple[str, str]:
    proof = _read_json(spec.environment_proof, f"{surface}_environment_proof")
    if set(proof) != {
        "schema_version",
        "artifact_sha256",
        "source_sha",
        "source_ref_kind",
        "version",
        "environment_prefix",
        "python_entry",
        "python_realpath",
        "site_packages",
        "agentbox_wheel",
        "pip_report",
        "installed_distributions",
        "module_origins",
        "include_system_site_packages",
        "pth_files",
        "installer_module",
    }:
        _fail(surface, "environment proof schema is invalid")
    wheel_paths = sorted(
        name
        for name in manifest.files
        if name.startswith("wheelhouse/agentbox-") and name.endswith(".whl")
    )
    if len(wheel_paths) != 1:
        _fail(surface, "artifact has no unique AgentBox wheel")
    wheel_path = wheel_paths[0]
    wheel_sha256 = manifest.files[wheel_path]
    environment_prefix = Path(os.path.abspath(spec.environment_root))
    python = Path(os.path.abspath(spec.python))
    python_realpath = python.resolve()
    site_packages_value = proof.get("site_packages")
    installer_module_value = proof.get("installer_module")
    agentbox_wheel = proof.get("agentbox_wheel")
    pip_report = proof.get("pip_report")
    installed_distributions = proof.get("installed_distributions")
    module_origins = proof.get("module_origins")
    if (
        not isinstance(site_packages_value, str)
        or not isinstance(installer_module_value, str)
        or not isinstance(agentbox_wheel, dict)
        or set(agentbox_wheel) != {"path", "sha256"}
        or not isinstance(pip_report, dict)
        or set(pip_report) != {"path", "sha256"}
        or not isinstance(installed_distributions, list)
        or not isinstance(module_origins, dict)
    ):
        _fail(surface, "environment proof paths are invalid")
    site_packages = Path(os.path.abspath(site_packages_value))
    installer_module = Path(os.path.abspath(installer_module_value))
    if (
        proof.get("schema_version") != 2
        or proof.get("artifact_sha256") != spec.sha256
        or proof.get("source_sha") != spec.source_sha
        or proof.get("source_ref_kind") != manifest.source_ref_kind
        or proof.get("version") != spec.version
        or proof.get("environment_prefix") != str(environment_prefix)
        or proof.get("python_entry") != str(python)
        or proof.get("python_realpath") != str(python_realpath)
        or agentbox_wheel.get("path") != wheel_path
        or agentbox_wheel.get("sha256") != wheel_sha256
        or proof.get("include_system_site_packages") is not False
        or proof.get("pth_files") != []
    ):
        _fail(surface, "environment proof is not bound to the exact artifact")
    try:
        site_packages.relative_to(environment_prefix)
        installer_module.relative_to(site_packages)
    except ValueError as exc:
        raise RehearsalError(f"{surface}: environment proof path escapes its prefix") from exc
    _safe_root(site_packages, f"{surface}_site_packages")
    expected_installer = site_packages / "agentbox_installer/lifecycle.py"
    if installer_module != expected_installer:
        _fail(surface, "environment proof installer module is not exact")
    wheel = release / wheel_path
    if sha256_file(wheel) != wheel_sha256:
        _fail(surface, "AgentBox wheel digest does not match the artifact manifest")
    try:
        scan_wheel_bytes(wheel.read_bytes(), ())
    except (ArtifactError, OSError) as exc:
        raise RehearsalError(f"{surface}: AgentBox wheel safety verification failed") from exc
    observed: set[str] = set()
    installer_member_found = False
    try:
        with zipfile.ZipFile(wheel) as archive:
            for member in archive.infolist():
                canonical_name = member.filename.rstrip("/")
                relative = PurePosixPath(canonical_name)
                if (
                    not canonical_name
                    or relative.is_absolute()
                    or any(part in {"", ".", ".."} for part in canonical_name.split("/"))
                    or "\\" in canonical_name
                    or canonical_name in observed
                ):
                    _fail(surface, "AgentBox wheel contains an unsafe path")
                observed.add(canonical_name)
                unix_mode = member.external_attr >> 16
                file_type = stat.S_IFMT(unix_mode)
                if file_type and not (stat.S_ISREG(unix_mode) or stat.S_ISDIR(unix_mode)):
                    _fail(surface, "AgentBox wheel contains a special filesystem object")
                if member.is_dir() or member.filename.endswith(".dist-info/RECORD"):
                    continue
                target = site_packages.joinpath(*relative.parts)
                try:
                    details = target.lstat()
                except OSError as exc:
                    raise RehearsalError(
                        f"{surface}: installed wheel payload is incomplete"
                    ) from exc
                if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
                    _fail(surface, "installed wheel payload is unsafe")
                expected_digest = hashlib.sha256(archive.read(member)).hexdigest()
                if sha256_file(target) != expected_digest:
                    _fail(surface, "installed wheel payload digest mismatch")
                if target == installer_module:
                    installer_member_found = True
    except RehearsalError:
        raise
    except (OSError, KeyError, RuntimeError, zipfile.BadZipFile) as exc:
        raise RehearsalError(f"{surface}: AgentBox wheel verification failed") from exc
    if not installer_member_found:
        _fail(surface, "AgentBox wheel does not contain the exact installer module")

    report_path_value = pip_report.get("path")
    report_sha256 = pip_report.get("sha256")
    workspace = environment_prefix.parent
    expected_report = workspace / "pip-report.json"
    unpacked_root = workspace / "unpacked"
    if (
        not isinstance(report_path_value, str)
        or not isinstance(report_sha256, str)
        or _SHA256.fullmatch(report_sha256) is None
        or Path(os.path.abspath(report_path_value)) != expected_report
        or Path(os.path.abspath(spec.environment_proof)) != workspace / "environment-proof.json"
        or unpacked_root.is_symlink()
        or not unpacked_root.is_dir()
        or expected_report.is_symlink()
        or not expected_report.is_file()
        or sha256_file(expected_report) != report_sha256
    ):
        _fail(surface, "environment proof workspace is invalid")
    report_distributions = _read_pip_report_inventory(
        expected_report,
        unpacked_root,
        manifest,
        surface,
    )
    if (
        any(
            not isinstance(item, dict)
            or set(item) != {"name", "version", "wheel_path", "wheel_sha256"}
            or not all(isinstance(item.get(name), str) for name in item)
            for item in installed_distributions
        )
        or tuple(installed_distributions) != report_distributions
    ):
        _fail(surface, "environment proof distribution inventory is invalid")
    expected_site_distributions = tuple(
        {"name": item["name"], "version": item["version"]} for item in report_distributions
    )
    if _site_distribution_inventory(site_packages, surface) != expected_site_distributions:
        _fail(surface, "installed distribution inventory differs from pip report")
    if any(site_packages.glob("*.pth")) or any(
        (site_packages / name).exists() for name in ("sitecustomize.py", "usercustomize.py")
    ):
        _fail(surface, "site customization is present")
    config = environment_prefix / "pyvenv.cfg"
    try:
        config_values = {
            line.partition("=")[0].strip(): line.partition("=")[2].strip()
            for line in config.read_text(encoding="utf-8").splitlines()
            if "=" in line
        }
    except (OSError, UnicodeError) as exc:
        raise RehearsalError(
            f"{surface}: virtual environment configuration is unavailable"
        ) from exc
    if config_values.get("include-system-site-packages", "").casefold() != "false":
        _fail(surface, "virtual environment includes system packages")
    if set(module_origins) != set(_ENVIRONMENT_MODULES):
        _fail(surface, "module origin inventory is invalid")
    for name in _ENVIRONMENT_MODULES:
        origin = module_origins.get(name)
        expected_origin = site_packages / name / "__init__.py"
        if not isinstance(origin, str) or Path(os.path.abspath(origin)) != expected_origin:
            _fail(surface, "module origin escaped the artifact environment")
    for item in report_distributions:
        wheel = unpacked_root / item["wheel_path"]
        if sha256_file(wheel) != item["wheel_sha256"]:
            _fail(surface, "unpacked wheel digest differs from pip report")
        _verify_installed_wheel_payload(wheel, site_packages, surface)
    return wheel_sha256, str(installer_module)


def _inspect_artifact(spec: ArtifactInput, work_root: Path, surface: str) -> ArtifactEvidence:
    if _SHA256.fullmatch(spec.sha256) is None or _SOURCE_SHA.fullmatch(spec.source_sha) is None:
        _fail(surface, "expected provenance is invalid")
    if not spec.artifact.is_absolute() or spec.artifact.is_symlink() or not spec.artifact.is_file():
        _fail(surface, "artifact path is unsafe or unavailable")
    if not spec.python.is_absolute() or not os.access(spec.python, os.X_OK):
        _fail(surface, "artifact Python is unavailable")
    environment_root = _safe_root(spec.environment_root, f"{surface}_environment")
    try:
        Path(os.path.abspath(spec.python)).relative_to(environment_root)
    except ValueError as exc:
        raise RehearsalError(f"{surface}: Python is outside the artifact environment") from exc
    try:
        verify_artifact_digest(spec.artifact, spec.sha256)
        with tempfile.TemporaryDirectory(prefix=f"{surface}-", dir=work_root) as temporary:
            release = Path(temporary) / "release"
            extract_verified_tar(spec.artifact, release)
            manifest = verify_release(release)
            if manifest.version != spec.version:
                _fail(surface, "artifact version mismatch")
            if manifest.source_commit != spec.source_sha:
                _fail(surface, "artifact source provenance mismatch")
            if manifest.schema_version < 2:
                _fail(surface, "artifact manifest lacks source provenance")
            wheel_sha256, installer_module = _validate_environment_binding(
                spec, manifest, release, surface
            )
    except (ArtifactError, OSError) as exc:
        raise RehearsalError(f"{surface}: artifact verification failed") from exc
    return ArtifactEvidence(
        manifest.version,
        spec.source_sha,
        manifest.database_revision,
        spec.sha256,
        wheel_sha256,
        str(Path(os.path.abspath(spec.environment_root))),
        installer_module,
    )


def _tree_fingerprint(root: Path, surface: str) -> str:
    try:
        details = root.lstat()
    except OSError as exc:
        raise RehearsalError(f"{surface}: tree is unavailable") from exc
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
        _fail(surface, "tree root is unsafe")
    digest = hashlib.sha256()
    byte_count = 0
    members = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
    for member_count, path in enumerate(members, start=1):
        if member_count > _MAX_TREE_MEMBERS:
            _fail(surface, "tree exceeds its member limit")
        relative = path.relative_to(root).as_posix().encode("utf-8")
        try:
            item = path.lstat()
        except OSError as exc:
            raise RehearsalError(f"{surface}: tree changed during inspection") from exc
        if stat.S_ISLNK(item.st_mode):
            _fail(surface, "tree contains a symlink")
        if stat.S_ISDIR(item.st_mode):
            parts: tuple[bytes, ...] = (
                b"directory",
                relative,
                f"{stat.S_IMODE(item.st_mode):04o}".encode("ascii"),
            )
        elif stat.S_ISREG(item.st_mode):
            byte_count += item.st_size
            if byte_count > _MAX_TREE_BYTES:
                _fail(surface, "tree exceeds its byte limit")
            parts = (
                b"file",
                relative,
                f"{stat.S_IMODE(item.st_mode):04o}".encode("ascii"),
                sha256_file(path).encode("ascii"),
            )
        else:
            _fail(surface, "tree contains a special filesystem object")
        for part in parts:
            digest.update(len(part).to_bytes(8, "big"))
            digest.update(part)
    return digest.hexdigest()


def _file_fingerprint(path: Path, surface: str) -> str:
    try:
        details = path.lstat()
    except OSError as exc:
        raise RehearsalError(f"{surface}: file is unavailable") from exc
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        _fail(surface, "file is unsafe")
    return _hash_parts(
        (
            f"{stat.S_IMODE(details.st_mode):04o}".encode("ascii"),
            sha256_file(path).encode("ascii"),
        )
    )


def _encode_sqlite_value(value: object) -> object:
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["integer", int(value)]
    if isinstance(value, int):
        return ["integer", value]
    if isinstance(value, float):
        return ["real", value.hex()]
    if isinstance(value, str):
        return ["text", value]
    if isinstance(value, bytes):
        return ["blob", value.hex()]
    _fail("database", "SQLite returned an unsupported value type")
    raise RehearsalError("database: unreachable value type")


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _database_revision(database: Path, surface: str) -> str:
    if database.is_symlink() or not database.is_file():
        _fail(surface, "SQLite database is unsafe or unavailable")
    try:
        database_uri_path = urllib.parse.quote(str(database), safe="/")
        with sqlite3.connect(f"file:{database_uri_path}?mode=ro", uri=True) as connection:
            connection.execute("PRAGMA query_only=ON")
            rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
    except sqlite3.Error as exc:
        raise RehearsalError(f"{surface}: Alembic revision read-back failed") from exc
    if (
        len(rows) != 1
        or len(rows[0]) != 1
        or not isinstance(rows[0][0], str)
        or re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", rows[0][0]) is None
    ):
        _fail(surface, "Alembic revision read-back is invalid")
    return rows[0][0]


def _database_fingerprint(database: Path, surface: str = "database") -> DatabaseFingerprint:
    if database.is_symlink() or not database.is_file():
        _fail(surface, "SQLite database is unsafe or unavailable")
    for suffix in ("-wal", "-shm"):
        if Path(f"{database}{suffix}").exists() or Path(f"{database}{suffix}").is_symlink():
            _fail(surface, "stale SQLite WAL/SHM exists")
    uri = f"file:{urllib.parse.quote(str(database), safe='/')}?mode=ro&immutable=1"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            connection.execute("PRAGMA query_only=ON")
            if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                _fail(surface, "SQLite quick_check failed")
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                _fail(surface, "SQLite foreign_key_check failed")
            schema_rows = connection.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name,tbl_name"
            ).fetchall()
            normalized_schema = [
                [
                    kind,
                    name,
                    table,
                    sql,
                    " ".join(sql.split()) if isinstance(sql, str) else None,
                ]
                for kind, name, table, sql in schema_rows
            ]
            tables = [
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' ORDER BY name"
                ).fetchall()
            ]
            data_parts: list[bytes] = []
            row_count = 0
            for table in tables:
                encoded_rows = [
                    _canonical_json([_encode_sqlite_value(value) for value in row])
                    for row in connection.execute(f"SELECT * FROM {_quote_identifier(table)}")
                ]
                row_count += len(encoded_rows)
                if row_count > _MAX_DATABASE_ROWS:
                    _fail(surface, "SQLite logical data exceeds its row limit")
                data_parts.append(_canonical_json(["table", table, len(encoded_rows)]))
                data_parts.extend(sorted(encoded_rows))
    except RehearsalError:
        raise
    except sqlite3.Error as exc:
        raise RehearsalError(f"{surface}: SQLite inspection failed") from exc
    return DatabaseFingerprint(
        schema_sha256=hashlib.sha256(_canonical_json(normalized_schema)).hexdigest(),
        logical_data_sha256=_hash_parts(data_parts),
        row_count=row_count,
    )


def _validate_epoch(path: Path) -> None:
    value = _read_json(path, "epoch")
    if set(value) != {"epoch", "schema_version"}:
        _fail("epoch", "epoch schema is invalid")
    epoch = value.get("epoch")
    if (
        value.get("schema_version") != "waw-runtime-epoch-v1"
        or not isinstance(epoch, str)
        or re.fullmatch(r"[1-9][0-9]*", epoch) is None
    ):
        _fail("epoch", "epoch value is invalid")


def _capture_persistent(paths: RehearsalPaths) -> PersistentFingerprint:
    _validate_epoch(paths.epoch_file)
    return PersistentFingerprint(
        database=_database_fingerprint(paths.database),
        project_tree_sha256=_tree_fingerprint(paths.project_root, "projects"),
        runtime_home_tree_sha256=_tree_fingerprint(paths.runtime_home, "runtime_home"),
        epoch_sha256=_file_fingerprint(paths.epoch_file, "epoch"),
        binding_store_tree_sha256=_tree_fingerprint(paths.binding_store, "binding_store"),
    )


def _write_nonsecret_canaries(paths: RehearsalPaths) -> None:
    token = os.urandom(24).hex()
    values = (
        (paths.project_canary, f"rc8-project-nonsecret:{token}\n"),
        (paths.runtime_home_canary, f"rc8-runtime-home-nonsecret:{token}\n"),
        (paths.binding_canary, f'{{"nonsecret_canary":"{token}","schema_version":1}}\n'),
    )
    for path, content in values:
        if path.exists() or path.is_symlink():
            _fail("canaries", "canary path already exists")
        try:
            parent = path.parent
            details = parent.lstat()
            if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
                _fail("canaries", "canary parent is unsafe")
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except RehearsalError:
            raise
        except OSError as exc:
            raise RehearsalError("canaries: could not create non-secret fixture canary") from exc
    try:
        with sqlite3.connect(paths.database) as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            if connection.execute("PRAGMA journal_mode=DELETE").fetchone() != ("delete",):
                _fail("canaries", "SQLite journal mode could not be made deterministic")
            connection.execute(
                "CREATE TABLE rc8_operations_canary "
                "(id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO rc8_operations_canary(id,value) VALUES (1,?)",
                (f"rc8-database-nonsecret:{token}",),
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise RehearsalError("canaries: SQLite canary creation failed") from exc


def _validate_paths(paths: RehearsalPaths) -> RehearsalPaths:
    fixture_root = _safe_root(paths.fixture_root, "fixture_root")
    work_root = _safe_root(paths.work_root, "work_root")
    values: dict[str, Path] = {}
    for field, path in asdict(paths).items():
        if field in {"fixture_root", "work_root"}:
            continue
        values[field] = _path_in_root(fixture_root, Path(path), field)
    expected = {
        "database": fixture_root / "var/lib/agentbox/agentbox.db",
        "releases_root": fixture_root / "opt/agentbox/releases",
        "current_link": fixture_root / "opt/agentbox/current",
        "project_root": fixture_root / "srv/agentbox/projects",
        "runtime_home": fixture_root / "home/agentbox-runtime",
        "epoch_file": fixture_root / "var/lib/agentbox-waw/runtime-epoch-v1/epoch.json",
        "binding_store": fixture_root / "var/lib/agentbox-waw/bindings-v1",
        "receipt": fixture_root / "var/lib/agentbox/install-receipt.json",
        "journal": fixture_root / "var/lib/agentbox/install-journal.json",
        "backups": fixture_root / "var/lib/agentbox/backups",
        "project_canary": fixture_root / "srv/agentbox/projects/.rc8-operations-canary",
        "runtime_home_canary": fixture_root / "home/agentbox-runtime/.rc8-operations-canary",
        "binding_canary": fixture_root / "var/lib/agentbox-waw/bindings-v1/.rc8-operations-canary",
    }
    for name, expected_path in expected.items():
        if values[name] != expected_path:
            _fail(name, "path does not match the exact fixture FHS layout")
    if _paths_overlap(fixture_root, work_root):
        _fail("work_root", "work root must not overlap the fixture root")
    return RehearsalPaths(fixture_root=fixture_root, work_root=work_root, **values)


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


def _validate_nonoverlap(spec: ArtifactInput, paths: RehearsalPaths, surface: str) -> None:
    environment = Path(os.path.abspath(spec.environment_root))
    artifact = Path(os.path.abspath(spec.artifact))
    proof = Path(os.path.abspath(spec.environment_proof))
    for name, path in (
        ("environment", environment),
        ("artifact", artifact),
        ("environment_proof", proof),
    ):
        if _paths_overlap(paths.fixture_root, path):
            _fail(surface, f"{name} must not overlap the fixture root")


def _validate_evidence_directories(paths: RehearsalPaths) -> None:
    for surface, directory in (
        ("releases", paths.releases_root),
        ("projects", paths.project_root),
        ("runtime_home", paths.runtime_home),
        ("epoch", paths.epoch_file.parent),
        ("binding_store", paths.binding_store),
        ("receipt", paths.receipt.parent),
        ("journal", paths.journal.parent),
        ("backup", paths.backups),
    ):
        _path_in_root(paths.fixture_root, directory / ".evidence-chain-check", surface)
        try:
            details = directory.lstat()
        except OSError as exc:
            raise RehearsalError(f"{surface}: evidence directory is unavailable") from exc
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
            _fail(surface, "evidence directory is unsafe")


def _validate_current_release(
    paths: RehearsalPaths,
    evidence: ArtifactEvidence,
    surface: str,
) -> None:
    link = paths.current_link
    if not link.is_symlink() or os.readlink(link) != f"releases/{evidence.version}":
        _fail(surface, "current symlink does not select the exact release")
    expected_release = paths.releases_root / evidence.version
    try:
        target = link.resolve(strict=True)
    except OSError as exc:
        raise RehearsalError(f"{surface}: current symlink target is unavailable") from exc
    if target != expected_release.resolve(strict=True):
        _fail(surface, "current symlink resolves outside the exact release")
    try:
        manifest = verify_release(expected_release, allow_generated_venv=True)
    except (ArtifactError, OSError) as exc:
        raise RehearsalError(f"{surface}: installed release verification failed") from exc
    if manifest.version != evidence.version or manifest.source_commit != evidence.source_sha:
        _fail(surface, "installed release provenance mismatch")


def _validate_receipt(
    path: Path,
    *,
    active: ArtifactEvidence,
    previous_version: str | None,
    require_backup: bool,
) -> dict[str, object]:
    value = _read_json(path, "receipt")
    expected_keys = {
        "schema_version",
        "active_version",
        "previous_version",
        "database_revision",
        "pre_change_backup_id",
        "pre_change_backup_manifest_sha256",
        "installed_at",
        "identities",
        "managed_units",
        "managed_unit_sha256",
        "managed_tmpfiles_sha256",
        "bind",
        "credentials_migrated",
        "projects_migrated",
    }
    identities = value.get("identities")
    unit_digests = value.get("managed_unit_sha256")
    if set(value) != expected_keys or value.get("schema_version") != 1:
        _fail("receipt", "receipt schema is invalid")
    if (
        value.get("active_version") != active.version
        or value.get("previous_version") != previous_version
        or value.get("database_revision") != active.database_revision
        or value.get("managed_units") != list(_UNIT_NAMES)
        or value.get("bind") != "127.0.0.1:8787"
        or value.get("credentials_migrated") is not False
        or value.get("projects_migrated") is not False
        or not isinstance(value.get("installed_at"), str)
    ):
        _fail("receipt", "receipt identity is invalid")
    if (
        not isinstance(identities, dict)
        or set(identities) != {"agentbox_uid", "agentbox_gid", "runtime_uid", "ipc_gid"}
        or any(
            not isinstance(item, int) or isinstance(item, bool) or item <= 0
            for item in identities.values()
        )
    ):
        _fail("receipt", "receipt identity facts are invalid")
    if (
        not isinstance(unit_digests, dict)
        or set(unit_digests) != set(_UNIT_NAMES)
        or any(
            not isinstance(item, str) or _SHA256.fullmatch(item) is None
            for item in unit_digests.values()
        )
        or not isinstance(value.get("managed_tmpfiles_sha256"), str)
        or _SHA256.fullmatch(cast(str, value["managed_tmpfiles_sha256"])) is None
    ):
        _fail("receipt", "receipt managed-file digests are invalid")
    backup_id = value.get("pre_change_backup_id")
    backup_digest = value.get("pre_change_backup_manifest_sha256")
    if require_backup:
        if (
            not isinstance(backup_id, str)
            or _BACKUP_ID.fullmatch(backup_id) is None
            or not isinstance(backup_digest, str)
            or _SHA256.fullmatch(backup_digest) is None
        ):
            _fail("receipt", "receipt backup binding is invalid")
    elif backup_id is not None or backup_digest is not None:
        _fail("receipt", "rollback receipt unexpectedly retains a backup binding")
    return value


def _validate_journal(path: Path, version: str, steps: tuple[str, ...]) -> None:
    value = _read_json(path, "journal")
    if set(value) != {
        "schema_version",
        "transaction_id",
        "version",
        "status",
        "completed_steps",
        "updated_at",
        "contains_secrets",
        "resources",
    }:
        _fail("journal", "journal schema is invalid")
    transaction_id = value.get("transaction_id")
    resources = value.get("resources")
    if (
        value.get("schema_version") != 2
        or not isinstance(transaction_id, str)
        or _TRANSACTION_ID.fullmatch(transaction_id) is None
        or value.get("version") != version
        or value.get("status") != "committed"
        or value.get("completed_steps") != list(steps)
        or value.get("contains_secrets") is not False
        or not isinstance(value.get("updated_at"), str)
    ):
        _fail("journal", "journal identity is invalid")
    if not isinstance(resources, list):
        _fail("journal", "journal resources are invalid")
    required_resource_keys = {
        "expected_path",
        "expected_type",
        "existed_before",
        "initial_identity",
        "created_identity",
    }
    if any(
        not isinstance(item, dict) or not required_resource_keys.issubset(item)
        for item in resources
    ):
        _fail("journal", "journal resource evidence is invalid")


def _validate_backup(
    paths: RehearsalPaths,
    receipt: Mapping[str, object],
    predecessor: ArtifactEvidence,
    expected_database: DatabaseFingerprint,
) -> str:
    backup_id = cast(str, receipt["pre_change_backup_id"])
    expected_manifest_digest = cast(str, receipt["pre_change_backup_manifest_sha256"])
    backup_root = paths.backups / backup_id
    manifest_path = backup_root / "manifest.json"
    try:
        backup_details = backup_root.lstat()
    except OSError as exc:
        raise RehearsalError("backup: backup directory is unavailable") from exc
    if stat.S_ISLNK(backup_details.st_mode) or not stat.S_ISDIR(backup_details.st_mode):
        _fail("backup", "backup directory is unsafe")
    if manifest_path.is_symlink() or not manifest_path.is_file():
        _fail("backup", "backup manifest is unavailable")
    if sha256_file(manifest_path) != expected_manifest_digest:
        _fail("backup", "backup manifest digest mismatch")
    manifest = _read_json(manifest_path, "backup")
    if set(manifest) != {
        "schema_version",
        "backup_id",
        "created_at",
        "application_version",
        "migration_revision",
        "database_sha256",
        "file_sha256",
        "contents",
        "units",
        "tmpfiles",
        "excluded",
    }:
        _fail("backup", "backup manifest schema is invalid")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("backup_id") != backup_id
        or manifest.get("application_version") != predecessor.version
        or manifest.get("migration_revision") != predecessor.database_revision
        or manifest.get("excluded") != ["runtime_credentials", "projects", "provider_secrets"]
        or not isinstance(manifest.get("created_at"), str)
        or not isinstance(manifest.get("file_sha256"), dict)
        or not isinstance(manifest.get("contents"), list)
        or not isinstance(manifest.get("units"), list)
        or not isinstance(manifest.get("tmpfiles"), list)
    ):
        _fail("backup", "backup target identity is invalid")
    database_digest = manifest.get("database_sha256")
    if not isinstance(database_digest, str) or _SHA256.fullmatch(database_digest) is None:
        _fail("backup", "backup database digest is invalid")
    result = BackupResult(backup_id, backup_root, database_digest)
    if not verify_sqlite_backup(result):
        _fail("backup", "backup integrity verification failed")
    for suffix in ("-wal", "-shm"):
        sidecar = backup_root / f"agentbox.db{suffix}"
        if sidecar.exists() or sidecar.is_symlink():
            _fail("backup", "backup contains stale SQLite WAL/SHM")
    observed = _database_fingerprint(backup_root / "agentbox.db", "backup_database")
    if observed != expected_database:
        _fail("backup", "backup database fingerprint mismatch")
    return backup_id


def _compare_persistent(before: PersistentFingerprint, after: PersistentFingerprint) -> None:
    comparisons = (
        ("database_schema", before.database.schema_sha256, after.database.schema_sha256),
        ("database_data", before.database.logical_data_sha256, after.database.logical_data_sha256),
        ("database_rows", before.database.row_count, after.database.row_count),
        ("projects", before.project_tree_sha256, after.project_tree_sha256),
        ("runtime_home", before.runtime_home_tree_sha256, after.runtime_home_tree_sha256),
        ("epoch", before.epoch_sha256, after.epoch_sha256),
        ("binding_store", before.binding_store_tree_sha256, after.binding_store_tree_sha256),
    )
    for surface, expected, observed in comparisons:
        if observed != expected:
            _fail(surface, "rollback fingerprint mismatch")


def _validate_health(
    probe: HealthProbe,
    predecessor: ArtifactInput,
    evidence: ArtifactEvidence,
    paths: RehearsalPaths,
) -> None:
    expected = HealthExpectation(
        version=evidence.version,
        source_sha=evidence.source_sha,
        artifact_sha256=evidence.artifact_sha256,
        wheel_sha256=evidence.wheel_sha256,
        environment_prefix=evidence.environment_prefix,
        python=str(Path(os.path.abspath(predecessor.python))),
        release_root=str(paths.releases_root / evidence.version),
        database=str(paths.database),
        project_root=str(paths.project_root),
        current_link=str(paths.current_link),
    )
    observation = probe.read(expected)
    if observation.pid <= 1 or not observation.listener_owned:
        _fail("health", "health listener is not owned by the proven artifact process")
    provenance = (
        ("version", observation.version, expected.version),
        ("source_sha", observation.source_sha, expected.source_sha),
        ("artifact_sha256", observation.artifact_sha256, expected.artifact_sha256),
        ("wheel_sha256", observation.wheel_sha256, expected.wheel_sha256),
        ("environment_prefix", observation.environment_prefix, expected.environment_prefix),
        ("python", observation.python, expected.python),
        ("release_root", observation.release_root, expected.release_root),
        ("database", observation.database, expected.database),
        ("project_root", observation.project_root, expected.project_root),
        ("current_link", observation.current_link, expected.current_link),
    )
    for _name, observed_value, expected_value in provenance:
        if observed_value != expected_value:
            _fail("health", "API process provenance does not match the predecessor artifact")
    observed = observation.responses
    if set(observed) != {"health", "ready", "meta"}:
        _fail("health", "health evidence set is incomplete")
    if observed["health"] != {"status": "ok"}:
        _fail("health", "healthz response is invalid")
    if observed["ready"].get("status") != "ready":
        _fail("health", "readyz response is invalid")
    if observed["meta"].get("version") != evidence.version:
        _fail("health", "meta version does not match the predecessor")


def run_rehearsal(
    predecessor: ArtifactInput,
    candidate: ArtifactInput,
    paths: RehearsalPaths,
    *,
    runner: OperationsRunner,
    health_probe: HealthProbe,
) -> RehearsalResult:
    """Execute and verify predecessor apply, candidate upgrade and exact rollback."""
    safe_paths = _validate_paths(paths)
    _validate_nonoverlap(predecessor, safe_paths, "predecessor")
    _validate_nonoverlap(candidate, safe_paths, "candidate")
    predecessor_evidence = _inspect_artifact(predecessor, safe_paths.work_root, "predecessor")
    candidate_evidence = _inspect_artifact(candidate, safe_paths.work_root, "candidate")
    if predecessor_evidence.version == candidate_evidence.version:
        _fail("provenance", "predecessor and candidate versions must differ")
    if predecessor_evidence.source_sha == candidate_evidence.source_sha:
        _fail("provenance", "predecessor and candidate source SHAs must differ")
    if predecessor.artifact.resolve() == candidate.artifact.resolve():
        _fail("provenance", "predecessor and candidate artifacts must be distinct")

    predecessor_runtime = runner.prove(predecessor, predecessor_evidence, safe_paths.fixture_root)
    _validate_operation_outcome(
        predecessor_runtime,
        predecessor,
        predecessor_evidence,
        "prove",
        result_version=predecessor_evidence.version,
        expected_database_revision=None,
    )
    candidate_runtime = runner.prove(candidate, candidate_evidence, safe_paths.fixture_root)
    _validate_operation_outcome(
        candidate_runtime,
        candidate,
        candidate_evidence,
        "prove",
        result_version=candidate_evidence.version,
        expected_database_revision=None,
    )

    initial = runner.apply(predecessor, predecessor_evidence, safe_paths.fixture_root)
    _validate_operation_outcome(
        initial,
        predecessor,
        predecessor_evidence,
        "apply",
        result_version=predecessor_evidence.version,
        expected_database_revision=predecessor_evidence.database_revision,
    )
    if initial.previous_version is not None or not initial.changed or not initial.health_verified:
        _fail("predecessor_apply", "initial fixture apply result is invalid")
    _validate_evidence_directories(safe_paths)
    _validate_current_release(safe_paths, predecessor_evidence, "predecessor_apply")
    if _database_revision(safe_paths.database, "predecessor_database") != (
        predecessor_evidence.database_revision
    ):
        _fail("predecessor_database", "installed Alembic revision mismatch")
    _validate_receipt(
        safe_paths.receipt,
        active=predecessor_evidence,
        previous_version=None,
        require_backup=False,
    )
    _validate_journal(safe_paths.journal, predecessor_evidence.version, _APPLY_STEPS)

    _write_nonsecret_canaries(safe_paths)
    before = _capture_persistent(safe_paths)

    upgrade = runner.apply(candidate, candidate_evidence, safe_paths.fixture_root)
    _validate_operation_outcome(
        upgrade,
        candidate,
        candidate_evidence,
        "apply",
        result_version=candidate_evidence.version,
        expected_database_revision=candidate_evidence.database_revision,
    )
    if (
        upgrade.previous_version != predecessor_evidence.version
        or not upgrade.changed
        or not upgrade.health_verified
    ):
        _fail("candidate_apply", "upgrade result is invalid")
    _validate_current_release(safe_paths, candidate_evidence, "candidate_apply")
    if _database_revision(safe_paths.database, "candidate_database") != (
        candidate_evidence.database_revision
    ):
        _fail("candidate_database", "installed Alembic revision mismatch")
    upgrade_receipt = _validate_receipt(
        safe_paths.receipt,
        active=candidate_evidence,
        previous_version=predecessor_evidence.version,
        require_backup=True,
    )
    _validate_journal(safe_paths.journal, candidate_evidence.version, _APPLY_STEPS)
    backup_id = _validate_backup(
        safe_paths,
        upgrade_receipt,
        predecessor_evidence,
        before.database,
    )
    candidate_database = _database_fingerprint(safe_paths.database)
    if candidate_database.row_count < before.database.row_count:
        _fail("candidate_database", "upgrade lost logical rows")

    rollback = runner.rollback(
        candidate,
        candidate_evidence,
        safe_paths.fixture_root,
        predecessor_evidence.version,
    )
    _validate_operation_outcome(
        rollback,
        candidate,
        candidate_evidence,
        "rollback",
        result_version=predecessor_evidence.version,
        expected_database_revision=predecessor_evidence.database_revision,
    )
    if (
        rollback.version != predecessor_evidence.version
        or rollback.previous_version != candidate_evidence.version
        or not rollback.changed
        or not rollback.health_verified
    ):
        _fail("rollback", "rollback result is invalid")
    _validate_evidence_directories(safe_paths)
    _validate_current_release(safe_paths, predecessor_evidence, "rollback")
    if _database_revision(safe_paths.database, "rollback_database") != (
        predecessor_evidence.database_revision
    ):
        _fail("rollback_database", "restored Alembic revision mismatch")
    _validate_receipt(
        safe_paths.receipt,
        active=predecessor_evidence,
        previous_version=candidate_evidence.version,
        require_backup=False,
    )
    _validate_journal(safe_paths.journal, predecessor_evidence.version, _ROLLBACK_STEPS)
    _validate_backup(
        safe_paths,
        upgrade_receipt,
        predecessor_evidence,
        before.database,
    )
    after = _capture_persistent(safe_paths)
    _compare_persistent(before, after)
    _validate_health(health_probe, predecessor, predecessor_evidence, safe_paths)

    return RehearsalResult(
        predecessor_version=predecessor_evidence.version,
        predecessor_source_sha=predecessor_evidence.source_sha,
        candidate_version=candidate_evidence.version,
        candidate_source_sha=candidate_evidence.source_sha,
        backup_id=backup_id,
        schema_sha256=after.database.schema_sha256,
        logical_data_sha256=after.database.logical_data_sha256,
        project_tree_sha256=after.project_tree_sha256,
        runtime_home_tree_sha256=after.runtime_home_tree_sha256,
        epoch_sha256=after.epoch_sha256,
        binding_store_tree_sha256=after.binding_store_tree_sha256,
        health_verified=True,
    )


def _driver_main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="rehearse-release-operations __artifact-driver")
    parser.add_argument("--action", choices=("prove", "apply", "rollback"), required=True)
    parser.add_argument("--fixture-root", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-environment", type=Path, required=True)
    parser.add_argument("--target-version")
    args = parser.parse_args(argv)

    from agentbox_installer.host import HostOperations
    from agentbox_installer.layout import InstallLayout
    from agentbox_installer.lifecycle import AgentBoxInstaller

    fixture_root = _safe_root(args.fixture_root, "fixture_root")
    expected_environment = _safe_root(args.expected_environment, "artifact_environment")
    prefix = Path(sys.prefix).resolve()
    if prefix != expected_environment.resolve():
        _fail("artifact_environment", "isolated Python prefix mismatch")
    installer_module = Path(inspect.getfile(AgentBoxInstaller)).resolve()
    try:
        installer_module.relative_to(prefix)
    except ValueError as exc:
        raise RehearsalError(
            "artifact_environment: installer import escaped the isolated environment"
        ) from exc
    package_version = importlib.metadata.version("agentbox")
    if package_version != args.expected_version:
        _fail("artifact_environment", "installed distribution version mismatch")

    if args.action == "prove":
        if args.target_version is not None:
            _fail("prove", "environment proof must not include a rollback target")
        print(
            json.dumps(
                {
                    "action": "prove",
                    "version": args.expected_version,
                    "previous_version": None,
                    "changed": False,
                    "health_verified": False,
                    "package_version": package_version,
                    "environment_prefix": str(prefix),
                    "installer_module": str(installer_module),
                    "alembic_upgrades": [],
                    "database_revision": None,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0

    class AlembicFixtureInstaller(AgentBoxInstaller):
        def __init__(self) -> None:
            super().__init__(InstallLayout(fixture_root), HostOperations(real_host=False))
            self.alembic_upgrades: list[str] = []

        def _run_migration(self, manifest: ReleaseManifest) -> None:
            from alembic import command
            from alembic.config import Config

            if self.host.real_host:
                _fail("migration", "real-host migration is forbidden in rehearsal")
            release = self.layout.release(manifest.version)
            config = Config(str(release / "alembic.ini"))
            config.set_main_option("script_location", str(release / "migrations"))
            config.set_main_option(
                "sqlalchemy.url",
                f"sqlite+pysqlite:///{self.layout.database}".replace("%", "%%"),
            )
            previous_environment = {
                key: os.environ.get(key)
                for key in ("AGENTBOX_ENV", "AGENTBOX_DATABASE_URL", "AGENTBOX_ALEMBIC_INI")
            }
            os.environ["AGENTBOX_ENV"] = "test"
            os.environ["AGENTBOX_DATABASE_URL"] = f"sqlite+pysqlite:///{self.layout.database}"
            os.environ["AGENTBOX_ALEMBIC_INI"] = str(release / "alembic.ini")
            try:
                command.upgrade(config, manifest.database_revision)
            finally:
                for key, previous in previous_environment.items():
                    if previous is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = previous
            self.alembic_upgrades.append(manifest.database_revision)
            os.chmod(self.layout.database, 0o600)

    installer = AlembicFixtureInstaller()
    if args.action == "apply":
        if args.target_version is not None:
            _fail("apply", "apply must not include a rollback target")
        result = installer.apply(args.artifact, args.sha256)
    else:
        if args.target_version is None:
            _fail("rollback", "rollback target is required")
        result = installer.rollback(args.target_version)
    database_revision = _database_revision(installer.layout.database, args.action)
    print(
        json.dumps(
            {
                "action": args.action,
                "version": result.version,
                "previous_version": result.previous_version,
                "changed": result.changed,
                "health_verified": result.health_verified,
                "package_version": package_version,
                "environment_prefix": str(prefix),
                "installer_module": str(installer_module),
                "alembic_upgrades": installer.alembic_upgrades,
                "database_revision": database_revision,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


def _artifact_from_args(args: argparse.Namespace, prefix: str) -> ArtifactInput:
    return ArtifactInput(
        artifact=Path(os.path.abspath(getattr(args, f"{prefix}_artifact"))),
        sha256=getattr(args, f"{prefix}_sha256"),
        version=getattr(args, f"{prefix}_version"),
        source_sha=getattr(args, f"{prefix}_source_sha"),
        python=Path(os.path.abspath(getattr(args, f"{prefix}_python"))),
        environment_root=Path(os.path.abspath(getattr(args, f"{prefix}_environment"))),
        environment_proof=Path(os.path.abspath(getattr(args, f"{prefix}_environment_proof"))),
    )


def _main_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    for prefix in ("predecessor", "candidate"):
        parser.add_argument(f"--{prefix}-artifact", type=Path, required=True)
        parser.add_argument(f"--{prefix}-sha256", required=True)
        parser.add_argument(f"--{prefix}-version", required=True)
        parser.add_argument(f"--{prefix}-source-sha", required=True)
        parser.add_argument(f"--{prefix}-python", type=Path, required=True)
        parser.add_argument(f"--{prefix}-environment", type=Path, required=True)
        parser.add_argument(f"--{prefix}-environment-proof", type=Path, required=True)
    parser.add_argument("--fixture-root", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--releases-root", type=Path, required=True)
    parser.add_argument("--current-link", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--runtime-home", type=Path, required=True)
    parser.add_argument("--epoch-file", type=Path, required=True)
    parser.add_argument("--binding-store", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--backups", type=Path, required=True)
    parser.add_argument("--project-canary", type=Path, required=True)
    parser.add_argument("--runtime-home-canary", type=Path, required=True)
    parser.add_argument("--binding-canary", type=Path, required=True)
    parser.add_argument("--health-base-url", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "__artifact-driver":
        return _driver_main(arguments[1:])
    args = _main_parser().parse_args(arguments)
    paths = RehearsalPaths(
        fixture_root=args.fixture_root,
        work_root=args.work_root,
        database=args.database,
        releases_root=args.releases_root,
        current_link=args.current_link,
        project_root=args.project_root,
        runtime_home=args.runtime_home,
        epoch_file=args.epoch_file,
        binding_store=args.binding_store,
        receipt=args.receipt,
        journal=args.journal,
        backups=args.backups,
        project_canary=args.project_canary,
        runtime_home_canary=args.runtime_home_canary,
        binding_canary=args.binding_canary,
    )
    try:
        result = run_rehearsal(
            _artifact_from_args(args, "predecessor"),
            _artifact_from_args(args, "candidate"),
            paths,
            runner=ArtifactPythonRunner(paths.work_root),
            health_probe=LoopbackHealthProbe(args.health_base_url),
        )
    except RehearsalError as exc:
        print(f"release operations rehearsal failed: {exc}", file=sys.stderr)
        return 17
    print(json.dumps(asdict(result), separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
