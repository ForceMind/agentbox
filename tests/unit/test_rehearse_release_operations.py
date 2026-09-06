from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import venv
import zipfile
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from agentbox_installer.artifact import extract_verified_tar, sha256_file
from agentbox_installer.backup import create_sqlite_backup

SCRIPT = Path(__file__).parents[2] / "scripts/rehearse-release-operations.py"


def _load_script() -> ModuleType:
    specification = importlib.util.spec_from_file_location(
        "agentbox_rehearse_release_operations", SCRIPT
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("operations rehearsal script could not be loaded")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


operations: Any = _load_script()


def _wheel(version: str) -> bytes:
    payload = io.BytesIO()
    modules = {
        "agentbox_api/__init__.py": "",
        "agentbox_browser_trust/__init__.py": "",
        "agentbox_cli/__init__.py": "",
        "agentbox_core/__init__.py": "",
        "agentbox_helper/__init__.py": "",
        "agentbox_installer/__init__.py": "",
        "agentbox_installer/artifact.py": (
            "from dataclasses import dataclass\n"
            "class ArtifactError(RuntimeError): pass\n"
            "@dataclass\nclass ReleaseManifest:\n    version: str = ''\n"
            "def _unavailable(*args, **kwargs): raise RuntimeError('stub')\n"
            "extract_verified_tar = _unavailable\nsha256_file = _unavailable\n"
            "scan_wheel_bytes = _unavailable\nverify_artifact_digest = _unavailable\n"
            "verify_release = _unavailable\n"
        ),
        "agentbox_installer/backup.py": (
            "from dataclasses import dataclass\nfrom pathlib import Path\n"
            "@dataclass\nclass BackupResult:\n    backup_id: str\n    path: Path\n"
            "    database_sha256: str\n"
            "def verify_sqlite_backup(*args, **kwargs): return False\n"
        ),
        "agentbox_installer/host.py": (
            "class HostOperations:\n    def __init__(self, *, real_host): "
            "self.real_host = real_host\n"
        ),
        "agentbox_installer/layout.py": (
            "class InstallLayout:\n    def __init__(self, root): self.root = root\n"
        ),
        "agentbox_installer/lifecycle.py": "class AgentBoxInstaller: pass\n",
        "agentbox_protocol/__init__.py": "",
        "agentbox_runtime/__init__.py": "",
        "agentbox_worker/__init__.py": "",
    }
    with zipfile.ZipFile(payload, "w") as archive:
        for name, content in modules.items():
            archive.writestr(name, content)
        archive.writestr(
            f"agentbox-{version}.dist-info/METADATA",
            f"Metadata-Version: 2.4\nName: agentbox\nVersion: {version}\n",
        )
        archive.writestr(
            f"agentbox-{version}.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: rc8-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
    return payload.getvalue()


def _artifact(
    tmp_path: Path,
    *,
    version: str,
    source_sha: str,
    revision: str,
    source_ref_kind: str | None = None,
) -> tuple[Path, str, str]:
    wheel = _wheel(version)
    files = {
        "VERSION": f"{version}\n".encode("ascii"),
        "LICENSE": b"fixture license\n",
        "THIRD_PARTY_NOTICES.md": b"fixture notices\n",
        "SBOM.spdx.json": json.dumps(
            {
                "spdxVersion": "SPDX-2.3",
                "dataLicense": "CC0-1.0",
                "name": f"AgentBox {version} SBOM",
            },
            sort_keys=True,
        ).encode()
        + b"\n",
        "install.sh": b"#!/usr/bin/env bash\nexit 99\n",
        "alembic.ini": b"[alembic]\nscript_location = migrations\n",
        "web/dist/index.html": b"<!doctype html><title>fixture</title>\n",
        f"wheelhouse/agentbox-{version}-py3-none-any.whl": wheel,
        f"migrations/versions/{revision}.py": (
            f"revision = {revision!r}\ndown_revision = None\n"
        ).encode("ascii"),
    }
    for abi in ("cp311", "cp312", "cp313"):
        files[f"wheelhouse/fixture-1.0-{abi}-{abi}-manylinux_2_28_x86_64.whl"] = b"fixture\n"
    manifest = {
        "schema_version": 3,
        "version": version,
        "database_revision": revision,
        "database_backward_compatible": False,
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
        "source_commit": source_sha,
        "source_ref_kind": source_ref_kind
        or ("main" if version == "0.3.0rc7" else "pull_request_head"),
        "target_platform": "linux",
        "target_architecture": "x86_64",
        "build_mode": "release-candidate",
        "file_allowlist": sorted(files),
        "required_python": ">=3.11,<3.14",
        "supported_python_abis": ["cp311", "cp312", "cp313"],
        "build_toolchain": {
            "node": "22.23.2",
            "pip": "26.2.1",
            "pnpm": "11.20.0",
            "setuptools": "83.0.0",
            "wheel": "0.46.2",
        },
        "platform_support": [
            {
                "distribution": "fixture",
                "release": "1",
                "architecture": "x86_64",
                "qualification": "synthetic-only",
            }
        ],
        "artifact_authenticity": "unsigned; sha256 integrity only",
        "sbom_filename": "SBOM.spdx.json",
        "license_filename": "LICENSE",
        "third_party_notices_filename": "THIRD_PARTY_NOTICES.md",
        "executable_files": ["install.sh"],
    }
    artifact = tmp_path / f"agentbox-{version}-linux-x86_64.tar.gz"
    with tarfile.open(artifact, "w:gz") as archive:
        for name, content in {
            **files,
            "RELEASE_MANIFEST.json": json.dumps(manifest, sort_keys=True).encode() + b"\n",
        }.items():
            member = tarfile.TarInfo(name)
            member.mode = 0o755 if name == "install.sh" else 0o644
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return artifact, sha256_file(artifact), hashlib.sha256(wheel).hexdigest()


def _environment(
    tmp_path: Path,
    name: str,
    *,
    artifact: Path,
    artifact_sha256: str,
    version: str,
    source_sha: str,
    wheel_sha256: str,
    real_venv: bool = False,
) -> tuple[Path, Path, Path]:
    workspace = tmp_path / name
    root = workspace / "environment"
    if real_venv:
        venv.EnvBuilder(with_pip=False).create(root)
    else:
        python = root / "bin/python"
        python.parent.mkdir(parents=True)
        python.write_text("#!/bin/sh\nexit 99\n", encoding="ascii")
        python.chmod(0o755)
        (root / "pyvenv.cfg").write_text("include-system-site-packages = false\n", encoding="ascii")
    python = root / "bin/python"
    if real_venv:
        completed = subprocess.run(
            (
                str(python),
                "-I",
                "-c",
                "import sysconfig; print(sysconfig.get_paths()['purelib'])",
            ),
            capture_output=True,
            text=True,
            check=True,
        )
        site_packages = Path(completed.stdout.strip())
    else:
        site_packages = root / "lib/site-packages"
        site_packages.mkdir(parents=True)
    wheel_path = f"wheelhouse/agentbox-{version}-py3-none-any.whl"
    with tarfile.open(artifact, "r:gz") as archive:
        stream = archive.extractfile(wheel_path)
        if stream is None:
            raise RuntimeError("fixture wheel is unavailable")
        wheel_payload = stream.read()
    unpacked_wheel = workspace / "unpacked" / wheel_path
    unpacked_wheel.parent.mkdir(parents=True, exist_ok=True)
    unpacked_wheel.write_bytes(wheel_payload)
    with zipfile.ZipFile(io.BytesIO(wheel_payload)) as wheel_archive:
        for member in wheel_archive.infolist():
            if member.is_dir():
                continue
            target = site_packages.joinpath(*Path(member.filename).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(wheel_archive.read(member))
    installer_module = site_packages / "agentbox_installer/lifecycle.py"
    source_ref_kind = "main" if version == "0.3.0rc7" else "pull_request_head"
    report = workspace / "pip-report.json"
    _write_json(
        report,
        {
            "version": "1",
            "pip_version": "26.2.1",
            "install": [
                {
                    "metadata": {"name": "agentbox", "version": version},
                    "download_info": {
                        "url": unpacked_wheel.as_uri(),
                        "archive_info": {"hashes": {"sha256": wheel_sha256}},
                    },
                }
            ],
        },
    )
    proof = workspace / "environment-proof.json"
    _write_json(
        proof,
        {
            "schema_version": 2,
            "artifact_sha256": artifact_sha256,
            "source_sha": source_sha,
            "source_ref_kind": source_ref_kind,
            "version": version,
            "environment_prefix": str(root),
            "python_entry": str(python),
            "python_realpath": str(python.resolve()),
            "site_packages": str(site_packages),
            "agentbox_wheel": {"path": wheel_path, "sha256": wheel_sha256},
            "pip_report": {"path": str(report), "sha256": sha256_file(report)},
            "installed_distributions": [
                {
                    "name": "agentbox",
                    "version": version,
                    "wheel_path": wheel_path,
                    "wheel_sha256": wheel_sha256,
                }
            ],
            "module_origins": {
                name: str(site_packages / name / "__init__.py")
                for name in (
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
            },
            "include_system_site_packages": False,
            "pth_files": [],
            "installer_module": str(installer_module),
        },
    )
    return root, python, proof


def _receipt(
    active: Any,
    previous: str | None,
    *,
    backup_id: str | None = None,
    backup_digest: str | None = None,
) -> dict[str, object]:
    digest = "a" * 64
    return {
        "schema_version": 1,
        "active_version": active.version,
        "previous_version": previous,
        "database_revision": active.database_revision,
        "pre_change_backup_id": backup_id,
        "pre_change_backup_manifest_sha256": backup_digest,
        "installed_at": "2026-09-06T00:00:00+00:00",
        "identities": {
            "agentbox_uid": 19001,
            "agentbox_gid": 19001,
            "runtime_uid": 19002,
            "ipc_gid": 19003,
        },
        "managed_units": list(operations._UNIT_NAMES),
        "managed_unit_sha256": {name: digest for name in operations._UNIT_NAMES},
        "managed_tmpfiles_sha256": digest,
        "bind": "127.0.0.1:8787",
        "credentials_migrated": False,
        "projects_migrated": False,
    }


def _journal(version: str, steps: tuple[str, ...]) -> dict[str, object]:
    return {
        "schema_version": 2,
        "transaction_id": "b" * 32,
        "version": version,
        "status": "committed",
        "completed_steps": list(steps),
        "updated_at": "2026-09-06T00:00:00+00:00",
        "contains_secrets": False,
        "resources": [],
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


class SyntheticRunner:
    def __init__(
        self,
        paths: Any,
        *,
        missing_alembic: bool = False,
        tamper_backup: bool = False,
        rollback_tamper: str | None = None,
        wrong_candidate_revision: bool = False,
    ) -> None:
        self.paths = paths
        self.missing_alembic = missing_alembic
        self.tamper_backup = tamper_backup
        self.rollback_tamper = rollback_tamper
        self.wrong_candidate_revision = wrong_candidate_revision
        self.calls: list[str] = []

    @staticmethod
    def _outcome(
        artifact: Any,
        evidence: Any,
        *,
        action: str,
        result_version: str,
        previous: str | None,
        alembic: tuple[str, ...],
        database_revision: str | None,
    ) -> Any:
        return operations.OperationOutcome(
            action=action,
            version=result_version,
            previous_version=previous,
            changed=action != "prove",
            health_verified=action != "prove",
            package_version=evidence.version,
            environment_prefix=str(artifact.environment_root),
            installer_module=evidence.installer_module,
            alembic_upgrades=alembic,
            database_revision=database_revision,
        )

    def prove(self, artifact: Any, evidence: Any, fixture_root: Path) -> Any:
        if fixture_root != self.paths.fixture_root:
            raise RuntimeError("unexpected fixture root")
        self.calls.append(f"prove:{evidence.version}")
        return self._outcome(
            artifact,
            evidence,
            action="prove",
            result_version=evidence.version,
            previous=None,
            alembic=(),
            database_revision=None,
        )

    def _install_release(self, artifact: Any, version: str) -> None:
        target = self.paths.releases_root / version
        extract_verified_tar(artifact.artifact, target)

    def _activate(self, version: str) -> None:
        self.paths.current_link.parent.mkdir(parents=True, exist_ok=True)
        if self.paths.current_link.exists() or self.paths.current_link.is_symlink():
            self.paths.current_link.unlink()
        self.paths.current_link.symlink_to(f"releases/{version}")

    def apply(
        self,
        artifact: Any,
        evidence: Any,
        fixture_root: Path,
    ) -> Any:
        if fixture_root != self.paths.fixture_root:
            raise RuntimeError("unexpected fixture root")
        self.calls.append(f"apply:{evidence.version}")
        self.paths.releases_root.mkdir(parents=True, exist_ok=True)
        self._install_release(artifact, evidence.version)
        if not self.paths.database.exists():
            self.paths.database.parent.mkdir(parents=True)
            self.paths.backups.mkdir(parents=True)
            self.paths.project_root.mkdir(parents=True)
            self.paths.runtime_home.mkdir(parents=True)
            self.paths.binding_store.mkdir(parents=True)
            self.paths.epoch_file.parent.mkdir(parents=True, exist_ok=True)
            self.paths.epoch_file.write_text(
                '{"epoch":"7","schema_version":"waw-runtime-epoch-v1"}\n',
                encoding="utf-8",
            )
            self.paths.epoch_file.chmod(0o600)
            with sqlite3.connect(self.paths.database) as connection:
                connection.execute(
                    "CREATE TABLE alembic_version (version_num VARCHAR(80) NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO alembic_version(version_num) VALUES (?)",
                    (evidence.database_revision,),
                )
                connection.execute(
                    "CREATE TABLE durable_data (id INTEGER PRIMARY KEY, value TEXT NOT NULL UNIQUE)"
                )
                connection.execute("INSERT INTO durable_data VALUES (1,'preserved')")
            previous = None
            backup_id = None
            backup_digest = None
        else:
            previous = "0.3.0rc7"
            backup = create_sqlite_backup(
                self.paths.database,
                self.paths.backups,
                application_version=previous,
                migration_revision="revision_rc7",
                backup_id="rc8-upgrade-backup",
            )
            backup_id = backup.backup_id
            backup_manifest = backup.path / "manifest.json"
            backup_digest = sha256_file(backup_manifest)
            with sqlite3.connect(self.paths.database) as connection:
                connection.execute("CREATE TABLE candidate_schema(value TEXT)")
                connection.execute("DELETE FROM alembic_version")
                connection.execute(
                    "INSERT INTO alembic_version(version_num) VALUES (?)",
                    (
                        (
                            "wrong_candidate_revision"
                            if self.wrong_candidate_revision
                            else evidence.database_revision
                        ),
                    ),
                )
            if self.tamper_backup:
                backup_manifest.write_text("{}\n", encoding="utf-8")
        self._activate(evidence.version)
        _write_json(
            self.paths.receipt,
            _receipt(
                evidence,
                previous,
                backup_id=backup_id,
                backup_digest=backup_digest,
            ),
        )
        _write_json(self.paths.journal, _journal(evidence.version, operations._APPLY_STEPS))
        alembic = (
            ()
            if self.missing_alembic and evidence.version == "0.3.0rc8"
            else (evidence.database_revision,)
        )
        return self._outcome(
            artifact,
            evidence,
            action="apply",
            result_version=evidence.version,
            previous=previous,
            alembic=alembic,
            database_revision=evidence.database_revision,
        )

    def rollback(
        self,
        artifact: Any,
        evidence: Any,
        fixture_root: Path,
        target_version: str,
    ) -> Any:
        if fixture_root != self.paths.fixture_root:
            raise RuntimeError("unexpected fixture root")
        self.calls.append(f"rollback:{target_version}")
        backup_database = self.paths.backups / "rc8-upgrade-backup/agentbox.db"
        shutil.copyfile(backup_database, self.paths.database)
        self._activate(target_version)
        predecessor = operations.ArtifactEvidence(
            target_version,
            "1" * 40,
            "revision_rc7",
            "a" * 64,
            "b" * 64,
            str(artifact.environment_root),
            evidence.installer_module,
        )
        _write_json(
            self.paths.receipt,
            _receipt(predecessor, evidence.version),
        )
        _write_json(self.paths.journal, _journal(target_version, operations._ROLLBACK_STEPS))
        if self.rollback_tamper == "projects":
            self.paths.project_canary.write_text("changed\n", encoding="utf-8")
        elif self.rollback_tamper == "runtime_home":
            self.paths.runtime_home_canary.write_text("changed\n", encoding="utf-8")
        elif self.rollback_tamper == "epoch":
            self.paths.epoch_file.write_text(
                '{"epoch":"8","schema_version":"waw-runtime-epoch-v1"}\n',
                encoding="utf-8",
            )
        elif self.rollback_tamper == "binding_store":
            self.paths.binding_canary.write_text("changed\n", encoding="utf-8")
        elif self.rollback_tamper == "binding_root_symlink":
            moved = self.paths.binding_store.with_name("bindings-v1-moved")
            self.paths.binding_store.rename(moved)
            self.paths.binding_store.symlink_to(moved.name, target_is_directory=True)
        elif self.rollback_tamper == "database_data":
            with sqlite3.connect(self.paths.database) as connection:
                connection.execute("UPDATE durable_data SET value='changed' WHERE id=1")
        elif self.rollback_tamper == "database_schema":
            with sqlite3.connect(self.paths.database) as connection:
                connection.execute("CREATE TABLE rollback_drift(value TEXT)")
        elif self.rollback_tamper == "wal":
            Path(f"{self.paths.database}-wal").write_bytes(b"stale")
        elif self.rollback_tamper == "shm":
            Path(f"{self.paths.database}-shm").write_bytes(b"stale")
        elif self.rollback_tamper == "receipt":
            value = json.loads(self.paths.receipt.read_text(encoding="utf-8"))
            value["active_version"] = "0.3.0rc8"
            _write_json(self.paths.receipt, value)
        elif self.rollback_tamper == "journal":
            value = json.loads(self.paths.journal.read_text(encoding="utf-8"))
            value["status"] = "running"
            _write_json(self.paths.journal, value)
        return self._outcome(
            artifact,
            evidence,
            action="rollback",
            result_version=target_version,
            previous=evidence.version,
            alembic=(),
            database_revision="revision_rc7",
        )


class SyntheticHealth:
    def __init__(self, *, listener_owned: bool = True, source_sha: str | None = None) -> None:
        self.listener_owned = listener_owned
        self.source_sha = source_sha

    def read(self, expected: Any) -> Any:
        return operations.HealthObservation(
            responses={
                "health": {"status": "ok"},
                "ready": {"status": "ready"},
                "meta": {"version": expected.version},
            },
            pid=42001,
            listener_owned=self.listener_owned,
            version=expected.version,
            source_sha=self.source_sha or expected.source_sha,
            artifact_sha256=expected.artifact_sha256,
            wheel_sha256=expected.wheel_sha256,
            environment_prefix=expected.environment_prefix,
            python=expected.python,
            release_root=expected.release_root,
            database=expected.database,
            project_root=expected.project_root,
            current_link=expected.current_link,
        )


@pytest.fixture
def rehearsal(tmp_path: Path) -> tuple[Any, Any, Any]:
    fixture_root = tmp_path / "fixture-root"
    work_root = tmp_path / "work-root"
    fixture_root.mkdir()
    work_root.mkdir()
    predecessor_artifact, predecessor_digest, predecessor_wheel_digest = _artifact(
        tmp_path,
        version="0.3.0rc7",
        source_sha="1" * 40,
        revision="revision_rc7",
    )
    candidate_artifact, candidate_digest, candidate_wheel_digest = _artifact(
        tmp_path,
        version="0.3.0rc8",
        source_sha="2" * 40,
        revision="revision_rc8",
    )
    predecessor_environment, predecessor_python, predecessor_proof = _environment(
        tmp_path,
        "predecessor-env",
        artifact=predecessor_artifact,
        artifact_sha256=predecessor_digest,
        version="0.3.0rc7",
        source_sha="1" * 40,
        wheel_sha256=predecessor_wheel_digest,
    )
    candidate_environment, candidate_python, candidate_proof = _environment(
        tmp_path,
        "candidate-env",
        artifact=candidate_artifact,
        artifact_sha256=candidate_digest,
        version="0.3.0rc8",
        source_sha="2" * 40,
        wheel_sha256=candidate_wheel_digest,
    )
    predecessor = operations.ArtifactInput(
        artifact=predecessor_artifact,
        sha256=predecessor_digest,
        version="0.3.0rc7",
        source_sha="1" * 40,
        python=predecessor_python,
        environment_root=predecessor_environment,
        environment_proof=predecessor_proof,
    )
    candidate = operations.ArtifactInput(
        artifact=candidate_artifact,
        sha256=candidate_digest,
        version="0.3.0rc8",
        source_sha="2" * 40,
        python=candidate_python,
        environment_root=candidate_environment,
        environment_proof=candidate_proof,
    )
    paths = operations.RehearsalPaths(
        fixture_root=fixture_root,
        work_root=work_root,
        database=fixture_root / "var/lib/agentbox/agentbox.db",
        releases_root=fixture_root / "opt/agentbox/releases",
        current_link=fixture_root / "opt/agentbox/current",
        project_root=fixture_root / "srv/agentbox/projects",
        runtime_home=fixture_root / "home/agentbox-runtime",
        epoch_file=fixture_root / "var/lib/agentbox-waw/runtime-epoch-v1/epoch.json",
        binding_store=fixture_root / "var/lib/agentbox-waw/bindings-v1",
        receipt=fixture_root / "var/lib/agentbox/install-receipt.json",
        journal=fixture_root / "var/lib/agentbox/install-journal.json",
        backups=fixture_root / "var/lib/agentbox/backups",
        project_canary=fixture_root / "srv/agentbox/projects/.rc8-operations-canary",
        runtime_home_canary=fixture_root / "home/agentbox-runtime/.rc8-operations-canary",
        binding_canary=(fixture_root / "var/lib/agentbox-waw/bindings-v1/.rc8-operations-canary"),
    )
    return predecessor, candidate, paths


def test_exact_upgrade_and_rollback_preserve_all_fingerprints(
    rehearsal: tuple[Any, Any, Any],
) -> None:
    predecessor, candidate, paths = rehearsal
    runner = SyntheticRunner(paths)

    result = operations.run_rehearsal(
        predecessor,
        candidate,
        paths,
        runner=runner,
        health_probe=SyntheticHealth(),
    )

    assert result.predecessor_version == "0.3.0rc7"
    assert result.candidate_version == "0.3.0rc8"
    assert result.backup_id == "rc8-upgrade-backup"
    assert result.health_verified is True
    assert runner.calls == [
        "prove:0.3.0rc7",
        "prove:0.3.0rc8",
        "apply:0.3.0rc7",
        "apply:0.3.0rc8",
        "rollback:0.3.0rc7",
    ]
    assert not Path(f"{paths.database}-wal").exists()
    assert not Path(f"{paths.database}-shm").exists()


def test_candidate_source_mismatch_fails_before_any_operation(
    rehearsal: tuple[Any, Any, Any],
) -> None:
    predecessor, candidate, paths = rehearsal
    runner = SyntheticRunner(paths)
    candidate = replace(candidate, source_sha="3" * 40)

    with pytest.raises(operations.RehearsalError, match="candidate: artifact source provenance"):
        operations.run_rehearsal(
            predecessor,
            candidate,
            paths,
            runner=runner,
            health_probe=SyntheticHealth(),
        )

    assert runner.calls == []


def test_candidate_requires_exact_alembic_upgrade_evidence(
    rehearsal: tuple[Any, Any, Any],
) -> None:
    predecessor, candidate, paths = rehearsal
    runner = SyntheticRunner(paths, missing_alembic=True)

    with pytest.raises(operations.RehearsalError, match="apply: exact Alembic upgrade"):
        operations.run_rehearsal(
            predecessor,
            candidate,
            paths,
            runner=runner,
            health_probe=SyntheticHealth(),
        )


def test_candidate_revision_is_read_back_from_the_actual_database(
    rehearsal: tuple[Any, Any, Any],
) -> None:
    predecessor, candidate, paths = rehearsal
    runner = SyntheticRunner(paths, wrong_candidate_revision=True)

    with pytest.raises(operations.RehearsalError, match="candidate_database: installed Alembic"):
        operations.run_rehearsal(
            predecessor,
            candidate,
            paths,
            runner=runner,
            health_probe=SyntheticHealth(),
        )


def test_upgrade_rejects_tampered_receipt_bound_backup(
    rehearsal: tuple[Any, Any, Any],
) -> None:
    predecessor, candidate, paths = rehearsal
    runner = SyntheticRunner(paths, tamper_backup=True)

    with pytest.raises(operations.RehearsalError, match="backup: backup manifest digest"):
        operations.run_rehearsal(
            predecessor,
            candidate,
            paths,
            runner=runner,
            health_probe=SyntheticHealth(),
        )


@pytest.mark.parametrize(
    ("tamper", "surface"),
    (
        ("projects", "projects"),
        ("runtime_home", "runtime_home"),
        ("epoch", "epoch"),
        ("binding_store", "binding_store"),
        ("binding_root_symlink", "binding_store"),
        ("database_data", "database_data"),
        ("database_schema", "database_schema"),
        ("wal", "database"),
        ("shm", "database"),
    ),
)
def test_rollback_fails_closed_on_persistent_state_drift(
    rehearsal: tuple[Any, Any, Any],
    tamper: str,
    surface: str,
) -> None:
    predecessor, candidate, paths = rehearsal
    runner = SyntheticRunner(paths, rollback_tamper=tamper)

    with pytest.raises(operations.RehearsalError, match=rf"{surface}:"):
        operations.run_rehearsal(
            predecessor,
            candidate,
            paths,
            runner=runner,
            health_probe=SyntheticHealth(),
        )


@pytest.mark.parametrize(("tamper", "surface"), (("receipt", "receipt"), ("journal", "journal")))
def test_rollback_rejects_corrupt_receipt_or_journal(
    rehearsal: tuple[Any, Any, Any], tamper: str, surface: str
) -> None:
    predecessor, candidate, paths = rehearsal
    runner = SyntheticRunner(paths, rollback_tamper=tamper)

    with pytest.raises(operations.RehearsalError, match=rf"{surface}:"):
        operations.run_rehearsal(
            predecessor,
            candidate,
            paths,
            runner=runner,
            health_probe=SyntheticHealth(),
        )


def test_fixture_paths_cannot_escape_the_explicit_root(
    rehearsal: tuple[Any, Any, Any], tmp_path: Path
) -> None:
    predecessor, candidate, paths = rehearsal
    outside = tmp_path / "outside-projects"
    outside.mkdir()
    paths = replace(paths, project_root=outside)
    runner = SyntheticRunner(paths)

    with pytest.raises(operations.RehearsalError, match="project_root: path escapes"):
        operations.run_rehearsal(
            predecessor,
            candidate,
            paths,
            runner=runner,
            health_probe=SyntheticHealth(),
        )

    assert runner.calls == []


def test_exact_fhs_mapping_rejects_an_in_root_alias(
    rehearsal: tuple[Any, Any, Any],
) -> None:
    predecessor, candidate, paths = rehearsal
    paths = replace(paths, runtime_home=paths.fixture_root / "home/runtime-alias")
    runner = SyntheticRunner(paths)

    with pytest.raises(operations.RehearsalError, match="runtime_home: path does not match"):
        operations.run_rehearsal(
            predecessor,
            candidate,
            paths,
            runner=runner,
            health_probe=SyntheticHealth(),
        )


def test_work_root_cannot_overlap_fixture_root(
    rehearsal: tuple[Any, Any, Any],
) -> None:
    predecessor, candidate, paths = rehearsal
    overlapping_work = paths.fixture_root / "work"
    overlapping_work.mkdir()
    paths = replace(paths, work_root=overlapping_work)

    with pytest.raises(operations.RehearsalError, match="work_root: work root must not overlap"):
        operations.run_rehearsal(
            predecessor,
            candidate,
            paths,
            runner=SyntheticRunner(paths),
            health_probe=SyntheticHealth(),
        )


def test_artifact_environment_cannot_overlap_fixture_root(
    rehearsal: tuple[Any, Any, Any],
) -> None:
    predecessor, candidate, paths = rehearsal
    overlapping_environment = paths.fixture_root / "artifact-env"
    overlapping_environment.mkdir()
    predecessor = replace(predecessor, environment_root=overlapping_environment)

    with pytest.raises(
        operations.RehearsalError, match="predecessor: environment must not overlap"
    ):
        operations.run_rehearsal(
            predecessor,
            candidate,
            paths,
            runner=SyntheticRunner(paths),
            health_probe=SyntheticHealth(),
        )


def test_artifact_file_cannot_be_inside_fixture_root(
    rehearsal: tuple[Any, Any, Any],
) -> None:
    predecessor, candidate, paths = rehearsal
    overlapping_artifact = paths.fixture_root / predecessor.artifact.name
    shutil.copyfile(predecessor.artifact, overlapping_artifact)
    predecessor = replace(predecessor, artifact=overlapping_artifact)

    with pytest.raises(operations.RehearsalError, match="predecessor: artifact must not overlap"):
        operations.run_rehearsal(
            predecessor,
            candidate,
            paths,
            runner=SyntheticRunner(paths),
            health_probe=SyntheticHealth(),
        )


def test_environment_payload_is_bound_to_the_artifact_wheel(
    rehearsal: tuple[Any, Any, Any],
) -> None:
    predecessor, candidate, paths = rehearsal
    installed_installer = (
        predecessor.environment_root / "lib/site-packages/agentbox_installer/lifecycle.py"
    )
    installed_installer.write_text("class AgentBoxInstaller: altered = True\n", encoding="utf-8")
    runner = SyntheticRunner(paths)

    with pytest.raises(operations.RehearsalError, match="installed wheel payload digest mismatch"):
        operations.run_rehearsal(
            predecessor,
            candidate,
            paths,
            runner=runner,
            health_probe=SyntheticHealth(),
        )

    assert runner.calls == []


@pytest.mark.parametrize(
    "mutation",
    (
        lambda proof: proof.update(source_ref_kind="other"),
        lambda proof: proof.update(pth_files=["unapproved.pth"]),
        lambda proof: proof["module_origins"].update(agentbox_core="/tmp/escaped.py"),
        lambda proof: proof.update(
            installed_distributions=[
                *proof["installed_distributions"],
                {
                    "name": "ambient",
                    "version": "1",
                    "wheel_path": "wheelhouse/ambient-1-py3-none-any.whl",
                    "wheel_sha256": "0" * 64,
                },
            ]
        ),
    ),
)
def test_environment_proof_rejects_ref_site_module_and_distribution_drift(
    rehearsal: tuple[Any, Any, Any], mutation: Any
) -> None:
    predecessor, candidate, paths = rehearsal
    proof = json.loads(candidate.environment_proof.read_text(encoding="utf-8"))
    mutation(proof)
    _write_json(candidate.environment_proof, proof)

    with pytest.raises(operations.RehearsalError, match="candidate:"):
        operations.run_rehearsal(
            predecessor,
            candidate,
            paths,
            runner=SyntheticRunner(paths),
            health_probe=SyntheticHealth(),
        )


def test_environment_proof_rejects_actual_site_customization(
    rehearsal: tuple[Any, Any, Any],
) -> None:
    predecessor, candidate, paths = rehearsal
    proof = json.loads(candidate.environment_proof.read_text(encoding="utf-8"))
    site_packages = Path(proof["site_packages"])
    (site_packages / "unapproved.pth").write_text("/tmp/ambient\n", encoding="utf-8")

    with pytest.raises(operations.RehearsalError, match="site customization is present"):
        operations.run_rehearsal(
            predecessor,
            candidate,
            paths,
            runner=SyntheticRunner(paths),
            health_probe=SyntheticHealth(),
        )


@pytest.mark.parametrize(
    "health",
    (
        SyntheticHealth(listener_owned=False),
        SyntheticHealth(source_sha="f" * 40),
    ),
)
def test_health_requires_the_exact_listener_owner_and_artifact_provenance(
    rehearsal: tuple[Any, Any, Any], health: SyntheticHealth
) -> None:
    predecessor, candidate, paths = rehearsal

    with pytest.raises(operations.RehearsalError, match="health:"):
        operations.run_rehearsal(
            predecessor,
            candidate,
            paths,
            runner=SyntheticRunner(paths),
            health_probe=health,
        )


def test_rehearsal_critical_checks_never_use_python_assert() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=SCRIPT.name)
    assert not any(isinstance(node, ast.Assert) for node in ast.walk(tree))


def test_fixture_root_rejects_a_symlinked_parent(tmp_path: Path) -> None:
    real_parent = tmp_path / "real-parent"
    fixture_root = real_parent / "fixture-root"
    fixture_root.mkdir(parents=True)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(operations.RehearsalError, match="parent chain is unsafe"):
        operations._safe_root(linked_parent / "fixture-root", "fixture_root")


def test_real_artifact_python_runner_proves_a_temp_isolated_environment(tmp_path: Path) -> None:
    artifact, artifact_digest, wheel_digest = _artifact(
        tmp_path,
        version="0.3.0rc8",
        source_sha="2" * 40,
        revision="revision_rc8",
    )
    environment, python, proof = _environment(
        tmp_path,
        "real-artifact-env",
        artifact=artifact,
        artifact_sha256=artifact_digest,
        version="0.3.0rc8",
        source_sha="2" * 40,
        wheel_sha256=wheel_digest,
        real_venv=True,
    )
    work_root = tmp_path / "work-root"
    fixture_root = tmp_path / "fixture-root"
    work_root.mkdir()
    fixture_root.mkdir()
    artifact_input = operations.ArtifactInput(
        artifact=artifact,
        sha256=artifact_digest,
        version="0.3.0rc8",
        source_sha="2" * 40,
        python=python,
        environment_root=environment,
        environment_proof=proof,
    )
    evidence = operations._inspect_artifact(artifact_input, work_root, "candidate")
    runner = operations.ArtifactPythonRunner(work_root, script=SCRIPT)

    outcome = runner.prove(artifact_input, evidence, fixture_root)

    assert outcome.action == "prove"
    assert outcome.version == "0.3.0rc8"
    assert outcome.environment_prefix == str(environment)
    assert outcome.installer_module == evidence.installer_module
    assert outcome.alembic_upgrades == ()
    assert outcome.database_revision is None
