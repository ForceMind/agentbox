"""Idempotent install, staged upgrade, and verified rollback lifecycle."""

from __future__ import annotations

import fcntl
import hashlib
import importlib.resources
import json
import os
import re
import secrets
import shutil
import sqlite3
import stat
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from agentbox_installer.artifact import (
    ArtifactError,
    ReleaseManifest,
    extract_verified_tar,
    load_manifest,
    remove_verified_tree,
    verify_artifact_digest,
    verify_release,
)
from agentbox_installer.backup import BackupResult, create_sqlite_backup, verify_sqlite_backup
from agentbox_installer.dependencies import REQUIRED_BASE, detect_dependencies
from agentbox_installer.hardening import validate_unit_compatibility
from agentbox_installer.host import HostOperations, IdentityFacts
from agentbox_installer.layout import DIRECTORIES, InstallLayout
from agentbox_installer.platform import PlatformFacts, detect_platform, resolve_packages
from agentbox_installer.retention import enforce_retention
from agentbox_installer.versioning import valid_version, version_precedence

UNIT_NAMES = (
    "agentbox-api.service",
    "agentbox-worker.service",
    "agentbox-runtime.service",
    "agentbox-helper.socket",
    "agentbox-helper.service",
)
HARDENED_DATA_LAYOUT_MIN_VERSION = "0.2.5"


def _compare_versions(candidate: str, current: str) -> int:
    """Compare release precedence; build metadata never authorizes downgrade."""
    try:
        candidate_key = version_precedence(candidate)
        current_key = version_precedence(current)
    except ValueError as exc:
        raise InstallError("installed or candidate release version is invalid") from exc

    return (candidate_key > current_key) - (candidate_key < current_key)


class InstallError(RuntimeError):
    pass


class RollbackVerifiedError(InstallError):
    pass


class RollbackVerificationError(InstallError):
    pass


@dataclass(frozen=True)
class InstallPlan:
    platform: PlatformFacts
    version: str
    state: str
    users: tuple[str, ...]
    groups: tuple[str, ...]
    directories: tuple[dict[str, object], ...]
    files: tuple[str, ...]
    units: tuple[str, ...]
    bind: str
    port_state: str
    systemd_state: str
    package_changes: tuple[str, ...]
    dependencies: tuple[dict[str, object], ...]
    existing_root_runtime: str
    network_changes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["platform"] = asdict(self.platform)
        return value


@dataclass(frozen=True)
class LifecycleResult:
    version: str
    previous_version: str | None
    changed: bool
    backup_id: str | None
    health_verified: bool


class AgentBoxInstaller:
    def __init__(self, layout: InstallLayout, host: HostOperations) -> None:
        self.layout = layout
        self.host = host

    def installation_state(self) -> str:
        receipt = self._read_receipt()
        current = self.current_version()
        recovery = self._recovery_state(receipt, current)
        if recovery is not None:
            return recovery
        if receipt is None and current is None:
            return "not_installed"
        if receipt is not None and current is None and receipt.get("program_files_removed") is True:
            return "uninstalled_data_preserved"
        if receipt is None or current is None:
            return "partial_or_broken"
        if receipt.get("active_version") != current:
            return "partial_or_broken"
        try:
            verify_release(self.layout.release(current), allow_generated_venv=True)
        except (ArtifactError, OSError):
            return "partial_or_broken"
        return "installed"

    def plan(self, artifact: Path, expected_sha256: str) -> InstallPlan:
        verify_artifact_digest(artifact, expected_sha256)
        version = self._peek_artifact_manifest(artifact).version
        os_release = self.layout.map("/etc/os-release")
        platform = detect_platform(os_release)
        dependencies = detect_dependencies(self.layout)
        missing_logical = tuple(
            item.name for item in dependencies if item.name in REQUIRED_BASE and not item.installed
        )
        package_changes = (
            resolve_packages(platform.package_family, missing_logical)
            if platform.supported and missing_logical
            else ()
        )
        installation_state = self.installation_state()
        current = self.current_version()
        if installation_state == "installed" and current is not None:
            comparison = _compare_versions(version, current)
            installation_state = (
                "installed_same_version"
                if comparison == 0
                else "installed_older_version" if comparison > 0 else "installed_newer_version"
            )
        return InstallPlan(
            platform=platform,
            version=version,
            state=installation_state,
            users=("agentbox", "agentbox-runtime"),
            groups=("agentbox", "agentbox-runtime", "agentbox-runtime-ipc"),
            directories=tuple(
                {
                    "path": item.path,
                    "owner": item.owner,
                    "group": item.group,
                    "mode": f"{item.mode:04o}",
                }
                for item in DIRECTORIES
            ),
            files=(
                "/etc/agentbox/agentbox.toml",
                "/etc/agentbox/environment",
                "/etc/agentbox/runtime-environment",
                "/etc/agentbox/helper-environment",
                "/var/lib/agentbox/agentbox.db",
                "/var/lib/agentbox/install-receipt.json",
                f"/opt/agentbox/releases/{version}",
                "/opt/agentbox/current",
            ),
            units=UNIT_NAMES,
            bind="127.0.0.1:8787",
            port_state=(
                "managed"
                if current is not None
                else "available" if self.host.port_available("127.0.0.1", 8787) else "in_use"
            ),
            systemd_state="available" if self.host.systemd_available() else "unavailable",
            package_changes=package_changes,
            dependencies=tuple(asdict(item) for item in dependencies),
            existing_root_runtime="detected but unmanaged; credentials and sessions are unchanged",
            network_changes=(),
        )

    def apply(self, artifact: Path, expected_sha256: str) -> LifecycleResult:
        self.host.require_root()
        with self._lifecycle_lock():
            return self._apply_locked(artifact, expected_sha256)

    def _apply_locked(self, artifact: Path, expected_sha256: str) -> LifecycleResult:
        plan = self.plan(artifact, expected_sha256)
        if not plan.platform.supported:
            raise InstallError(plan.platform.reason)
        if plan.systemd_state != "available":
            raise InstallError("native systemd is required")
        state = plan.state
        current = self.current_version()
        if state == "installed_same_version" and current == plan.version:
            existing = verify_release(self.layout.release(plan.version), allow_generated_venv=True)
            candidate = self._peek_artifact_manifest(artifact)
            if existing != candidate:
                raise InstallError("same-version artifact does not match installed release")
            self.host.ensure_identities(self._receipt_identities(self._read_receipt()))
            return LifecycleResult(plan.version, current, False, None, self.health_check())
        if state == "installed_newer_version":
            raise InstallError("downgrade is not supported; use a verified rollback target")
        if state in {
            "partial_or_broken",
            "preflight_interrupted",
            "staged",
            "activated",
            "partially_migrated",
            "rollback_pending",
            "unknown",
        }:
            raise InstallError(
                f"AgentBox lifecycle recovery state is {state}; inspect before repair"
            )
        candidate = self._peek_artifact_manifest(artifact)
        candidate_target = self.layout.release(candidate.version)
        if candidate_target.exists() or candidate_target.is_symlink():
            existing_candidate = verify_release(
                candidate_target,
                allow_generated_venv=True,
            )
            if existing_candidate != candidate:
                raise InstallError("existing release does not match the verified artifact")
        if current is None and not self.host.port_available("127.0.0.1", 8787):
            raise InstallError("configured AgentBox port 8787 is already in use")

        self.host.install_packages(plan.platform.package_family, plan.package_changes)
        if self.host.real_host:
            missing_after_install = [
                item.name
                for item in detect_dependencies(self.layout)
                if item.name in REQUIRED_BASE and not item.installed
            ]
            if missing_after_install:
                raise InstallError("required dependencies remain unavailable after package install")

        transaction_id = secrets.token_hex(16)
        resources = self._snapshot_transaction_resources(plan.version)
        self._write_journal(
            status="running",
            version=plan.version,
            completed=(),
            transaction_id=transaction_id,
            resources=resources,
        )
        identities = self.host.ensure_identities(self._receipt_identities(self._read_receipt()))
        self._write_journal(
            status="running",
            version=plan.version,
            completed=("identities",),
            transaction_id=transaction_id,
            resources=resources,
        )
        self._ensure_directories()
        self._write_journal(
            status="running",
            version=plan.version,
            completed=("identities", "directories"),
            transaction_id=transaction_id,
            resources=resources,
        )
        self._write_initial_configuration(identities)
        self._write_journal(
            status="running",
            version=plan.version,
            completed=("identities", "directories", "configuration"),
            transaction_id=transaction_id,
            resources=resources,
        )
        self._write_journal(
            status="running",
            version=plan.version,
            completed=(
                "identities",
                "directories",
                "configuration",
                "release_staging_started",
            ),
            transaction_id=transaction_id,
            resources=resources,
        )
        manifest = self._stage_release(artifact, expected_sha256)
        self.host.prepare_release_environment(self.layout.release(manifest.version))
        self._write_journal(
            status="running",
            version=plan.version,
            completed=("identities", "directories", "configuration", "release_staged"),
            transaction_id=transaction_id,
            resources=resources,
        )
        previous = current
        if previous is not None:
            self.host.stop_agentbox()
        try:
            backup = self._backup_before_change(previous)
        except Exception:
            if previous is not None:
                self.host.restart_agentbox()
            raise
        activated = False
        try:
            self._write_journal(
                status="running",
                version=plan.version,
                completed=(
                    "identities",
                    "directories",
                    "configuration",
                    "release_staged",
                    "database_migration_started",
                ),
                transaction_id=transaction_id,
                resources=resources,
            )
            try:
                self._run_migration(manifest)
            finally:
                self._record_created_database_objects(resources)
            self._write_journal(
                status="running",
                version=plan.version,
                completed=(
                    "identities",
                    "directories",
                    "configuration",
                    "release_staged",
                    "database_migrated",
                ),
                transaction_id=transaction_id,
                resources=resources,
            )
            if not self._database_integrity_and_revision(manifest.database_revision):
                raise InstallError("post-migration database verification failed")
            self._install_units()
            self._write_journal(
                status="running",
                version=plan.version,
                completed=(
                    "identities",
                    "directories",
                    "configuration",
                    "release_staged",
                    "database_migrated",
                    "units_installed",
                ),
                transaction_id=transaction_id,
                resources=resources,
            )
            self._activate(manifest.version)
            activated = True
            self._write_journal(
                status="running",
                version=plan.version,
                completed=(
                    "identities",
                    "directories",
                    "configuration",
                    "release_staged",
                    "database_migrated",
                    "units_installed",
                    "release_activated",
                ),
                transaction_id=transaction_id,
                resources=resources,
            )
            self.host.daemon_reload()
            self.host.enable_and_start()
            if not self.health_check():
                raise InstallError("post-install health verification failed")
            enforce_retention(
                backups_root=self.layout.backups,
                releases_root=self.layout.map("/opt/agentbox/releases"),
                protected_backup_ids=(
                    frozenset({backup.backup_id}) if backup is not None else frozenset()
                ),
                protected_release_versions=frozenset(
                    value for value in (manifest.version, previous) if value is not None
                ),
            )
            self._write_journal(
                status="running",
                version=plan.version,
                completed=(
                    "identities",
                    "directories",
                    "configuration",
                    "release_staged",
                    "database_migrated",
                    "units_installed",
                    "release_activated",
                    "health_verified",
                    "retention_applied",
                    "receipt_write_started",
                ),
                transaction_id=transaction_id,
                resources=resources,
            )
            self._write_receipt(manifest, previous, backup, identities)
            self._write_journal(
                status="committed",
                version=plan.version,
                completed=(
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
                ),
                transaction_id=transaction_id,
                resources=resources,
            )
            return LifecycleResult(
                manifest.version,
                previous,
                True,
                backup.backup_id if backup else None,
                True,
            )
        except Exception as exc:
            rollback_ok = self._rollback_failed_change(
                previous=previous,
                backup=backup,
                activated=activated,
                attempted_version=plan.version,
                transaction_id=transaction_id,
                resources=resources,
            )
            self._write_journal(
                status="rollback_verified" if rollback_ok else "rollback_verification_failed",
                version=plan.version,
                completed=("rollback_attempted",),
                transaction_id=transaction_id,
                resources=resources,
            )
            if previous is not None and rollback_ok:
                raise RollbackVerifiedError("upgrade failed; rollback verified") from exc
            if previous is not None:
                raise RollbackVerificationError(
                    "upgrade failed; rollback attempted but verification failed"
                ) from exc
            raise InstallError(
                f"installation failed; AgentBox services were stopped: {exc}"
            ) from exc

    def rollback(self, target_version: str | None = None) -> LifecycleResult:
        self.host.require_root()
        with self._lifecycle_lock():
            return self._rollback_locked(target_version)

    def _rollback_locked(self, target_version: str | None = None) -> LifecycleResult:
        receipt = self._read_receipt()
        current = self.current_version()
        if receipt is None or current is None:
            raise InstallError("AgentBox installation receipt is unavailable")
        recorded_previous = receipt.get("previous_version")
        if not valid_version(recorded_previous):
            raise InstallError("no previous release is recorded")
        if target_version is not None and target_version != recorded_previous:
            raise InstallError("rollback target must match the receipt's previous release")
        target = recorded_previous
        if self.host.real_host and self._uses_legacy_database_layout(target):
            raise InstallError(
                "rollback target predates the hardened database layout; "
                "automatic legacy rollback is unavailable"
            )
        target_manifest = verify_release(self.layout.release(target), allow_generated_venv=True)
        if target_manifest.version != target:
            raise InstallError("rollback target identity does not match its release")
        backup_id = receipt.get("pre_change_backup_id")
        manifest_digest = receipt.get("pre_change_backup_manifest_sha256")
        if manifest_digest is not None and not isinstance(manifest_digest, str):
            raise InstallError("recorded database backup identity is invalid")
        backup = (
            self._load_backup(str(backup_id), expected_manifest_sha256=manifest_digest)
            if backup_id
            else None
        )
        if not target_manifest.database_backward_compatible and backup is None:
            raise InstallError("application rollback requires a verified database backup")
        if backup is not None:
            self._verify_backup_for_target(
                backup,
                application_version=target,
                migration_revision=target_manifest.database_revision,
            )
        transaction_id = secrets.token_hex(16)
        resources = self._snapshot_transaction_resources(target)
        self._write_journal(
            status="running",
            version=target,
            completed=("rollback_preflight",),
            transaction_id=transaction_id,
            resources=resources,
        )
        try:
            self.host.stop_agentbox()
            if backup is not None:
                self._restore_backup(backup)
            self._write_journal(
                status="running",
                version=target,
                completed=("rollback_preflight", "services_stopped", "database_restored"),
                transaction_id=transaction_id,
                resources=resources,
            )
            self._activate(target)
            self._prepare_database_directory_for_release(target)
            self._write_journal(
                status="running",
                version=target,
                completed=(
                    "rollback_preflight",
                    "services_stopped",
                    "database_restored",
                    "release_activated",
                ),
                transaction_id=transaction_id,
                resources=resources,
            )
            self.host.restart_agentbox()
            expected_revision = target_manifest.database_revision if backup is not None else None
            verified = (
                self.current_version() == target
                and self._database_integrity_and_revision(expected_revision)
                and self.health_check(expected_version=target)
            )
            if not verified:
                raise RollbackVerificationError("rollback attempted but verification failed")
            identities = self.host.ensure_identities(self._receipt_identities(receipt))
            self._write_receipt(target_manifest, current, None, identities)
            self._write_journal(
                status="committed",
                version=target,
                completed=(
                    "rollback_preflight",
                    "services_stopped",
                    "database_restored",
                    "release_activated",
                    "services_restarted",
                    "rollback_verified",
                    "receipt_written",
                ),
                transaction_id=transaction_id,
                resources=resources,
            )
            return LifecycleResult(
                target, current, True, backup.backup_id if backup else None, True
            )
        except Exception as exc:
            self._write_journal(
                status="rollback_verification_failed",
                version=target,
                completed=("rollback_attempted",),
                transaction_id=transaction_id,
                resources=resources,
            )
            if isinstance(exc, RollbackVerificationError):
                raise
            raise RollbackVerificationError("rollback attempted but verification failed") from exc

    def recover(self) -> LifecycleResult:
        """Verify and close a failed-rollback journal without replaying mutations."""
        self.host.require_root()
        with self._lifecycle_lock():
            return self._recover_locked()

    def _recover_locked(self) -> LifecycleResult:
        receipt = self._read_receipt()
        journal = self._read_journal()
        current = self.current_version()
        recovery_state = self._recovery_state(receipt, current)
        if recovery_state not in {"rollback_pending", "preflight_interrupted"}:
            raise InstallError("no recoverable lifecycle transaction is available")
        if receipt is None or journal is None or current is None:
            raise InstallError("rollback recovery identity is incomplete")
        transaction_id = journal.get("transaction_id")
        resources = journal.get("resources")
        attempted_version = journal.get("version")
        if (
            not isinstance(transaction_id, str)
            or re.fullmatch(r"[0-9a-f]{32}", transaction_id) is None
            or not isinstance(resources, list)
            or not all(isinstance(item, dict) for item in resources)
            or not isinstance(attempted_version, str)
            or not valid_version(attempted_version)
            or receipt.get("active_version") != current
        ):
            raise InstallError("rollback recovery identity is invalid")
        manifest = verify_release(self.layout.release(current), allow_generated_venv=True)
        if manifest.version != current:
            raise InstallError("rollback recovery release identity does not match")
        if recovery_state == "rollback_pending":
            self._prepare_database_directory_for_release(current)
            try:
                self.host.restart_agentbox()
            except Exception as exc:
                raise RollbackVerificationError(
                    "rollback attempted but verification failed"
                ) from exc
        if not (
            self.current_version() == current
            and self._database_integrity_and_revision(manifest.database_revision)
            and self.health_check(expected_version=current)
        ):
            raise RollbackVerificationError("rollback attempted but verification failed")
        # A pre-hardening release validates its data parent only at process
        # initialization. Restore the root-owned sticky boundary before
        # recording recovery; the operator must immediately update to a
        # hardened release, and any intervening restart fails closed.
        if recovery_state == "rollback_pending" and self._uses_legacy_database_layout(current):
            self._harden_database_directory()
        completed_raw = journal.get("completed_steps")
        completed = (
            tuple(value for value in completed_raw if isinstance(value, str))
            if isinstance(completed_raw, list)
            else ()
        )
        self._write_journal(
            status="rollback_verified",
            version=attempted_version,
            completed=(
                *completed,
                (
                    "operator_recovery_verified"
                    if recovery_state == "rollback_pending"
                    else "preflight_recovery_verified"
                ),
            ),
            transaction_id=transaction_id,
            resources=resources,
        )
        self.host.set_owner_mode(self.layout.receipt, "root", "root", 0o600)
        return LifecycleResult(current, current, False, None, True)

    def uninstall(self) -> dict[str, object]:
        self.host.require_root()
        with self._lifecycle_lock():
            return self._uninstall_locked()

    def _uninstall_locked(self) -> dict[str, object]:
        """Remove only verified program files/units; persistent data is always retained."""
        receipt = self._read_receipt()
        if receipt is None:
            raise InstallError("AgentBox installation receipt is unavailable")
        link = self.layout.current_link
        current = self.current_version()
        if not link.is_symlink() or current is None or receipt.get("active_version") != current:
            raise InstallError("uninstall current release identity is invalid")
        releases_root = self.layout.map("/opt/agentbox/releases")
        if releases_root.is_symlink() or not releases_root.is_dir():
            raise InstallError("uninstall release root is unsafe")
        releases = tuple(sorted(releases_root.iterdir()))
        for release in releases:
            if release.is_symlink() or not release.is_dir():
                raise InstallError("uninstall found an unknown release object")
            verify_release(release, allow_generated_venv=True)
        package_root = importlib.resources.files("agentbox_installer") / "assets/systemd"
        units: list[Path] = []
        for name in UNIT_NAMES:
            target = self.layout.map(f"/etc/systemd/system/{name}")
            if not target.exists() and not target.is_symlink():
                continue
            source = Path(str(package_root / name))
            if (
                target.is_symlink()
                or not target.is_file()
                or target.read_bytes() != source.read_bytes()
            ):
                raise InstallError("refusing to remove a modified or unsafe systemd unit")
            units.append(target)
        tmpfiles = self.layout.map("/etc/tmpfiles.d/agentbox.conf")
        expected_tmpfiles = Path(
            str(importlib.resources.files("agentbox_installer") / "assets/tmpfiles.d/agentbox.conf")
        )
        remove_tmpfiles = tmpfiles.exists() or tmpfiles.is_symlink()
        if remove_tmpfiles and (
            tmpfiles.is_symlink()
            or not tmpfiles.is_file()
            or tmpfiles.read_bytes() != expected_tmpfiles.read_bytes()
        ):
            raise InstallError("refusing to remove a modified tmpfiles policy")

        # Every removable object is validated before the first host mutation.
        self.host.disable_and_stop()
        link.unlink()
        for release in releases:
            remove_verified_tree(release)
        for target in units:
            target.unlink()
        if remove_tmpfiles:
            tmpfiles.unlink()
        self.host.daemon_reload()
        receipt["uninstalled_at"] = datetime.now(UTC).isoformat()
        receipt["active_version"] = None
        receipt["program_files_removed"] = True
        self._atomic_write(
            self.layout.receipt,
            json.dumps(receipt, sort_keys=True) + "\n",
            0o600,
        )
        return {
            "program_files": "removed",
            "configuration": "preserved",
            "database": "preserved",
            "projects": "preserved",
            "runtime_home": "preserved",
            "purge": "not_available",
        }

    def current_version(self) -> str | None:
        link = self.layout.current_link
        if not link.is_symlink():
            return None
        target = os.readlink(link)
        relative_target = PurePosixPath(target)
        if (
            relative_target.is_absolute()
            or len(relative_target.parts) != 2
            or relative_target.parts[0] != "releases"
            or not valid_version(relative_target.parts[1])
        ):
            return None
        path = (link.parent / target).resolve(strict=False)
        releases = self.layout.map("/opt/agentbox/releases").resolve(strict=False)
        try:
            relative = path.relative_to(releases)
        except ValueError:
            return None
        if len(relative.parts) != 1:
            return None
        try:
            manifest = verify_release(path, allow_generated_venv=True)
        except (ArtifactError, OSError):
            return None
        return manifest.version if manifest.version == relative.name else None

    @contextmanager
    def _lifecycle_lock(self) -> Iterator[None]:
        parent = self.layout.map("/var/lib/agentbox")
        self._ensure_trusted_parent_chain(parent)
        if not parent.exists():
            parent.mkdir(mode=0o700, parents=False)
        details = parent.lstat()
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
            raise InstallError("installer lifecycle lock parent is unsafe")
        if self.host.real_host and details.st_uid != 0:
            raise InstallError("installer lifecycle lock parent is not root-owned")
        descriptor = os.open(
            parent / ".install.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
        )
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise InstallError("installer lifecycle lock is unsafe")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise InstallError("another AgentBox lifecycle transaction is active") from exc
            yield
        finally:
            os.close(descriptor)

    def health_check(self, expected_version: str | None = None) -> bool:
        if not self.host.real_host:
            current = self.current_version()
            return (
                current is not None
                and self.layout.database.is_file()
                and self._database_integrity_and_revision(None)
                and self.host.deployment_ready()
                and (expected_version is None or current == expected_version)
            )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self._health_check_once(expected_version):
                return True
            time.sleep(0.25)
        return False

    def _health_check_once(self, expected_version: str | None = None) -> bool:
        for endpoint in ("healthz", "readyz"):
            try:
                with urllib.request.urlopen(  # noqa: S310 - fixed loopback URL
                    f"http://127.0.0.1:8787/{endpoint}", timeout=5
                ) as response:
                    if response.status != 200 or len(response.read(4097)) > 4096:
                        return False
            except (OSError, urllib.error.URLError):
                return False
        try:
            with urllib.request.urlopen(  # noqa: S310 - fixed loopback URL
                "http://127.0.0.1:8787/api/v1/meta", timeout=5
            ) as response:
                raw = response.read(4097)
                if response.status != 200 or len(raw) > 4096:
                    return False
                value = json.loads(raw)
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            return False
        required_version = expected_version or self.current_version()
        return (
            isinstance(value, dict)
            and value.get("version") == required_version
            and self.host.deployment_ready()
        )

    def _peek_artifact_manifest(self, artifact: Path) -> ReleaseManifest:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="agentbox-plan-") as temporary:
            destination = Path(temporary) / "release"
            extract_verified_tar(artifact, destination)
            return verify_release(destination)

    def _stage_release(self, artifact: Path, expected_sha256: str) -> ReleaseManifest:
        releases = self.layout.map("/opt/agentbox/releases")
        self._assert_trusted_parent(releases)
        artifact_copy = releases / f".artifact-{secrets.token_hex(16)}.tar"
        source_descriptor = -1
        output_descriptor = -1
        try:
            source_descriptor = os.open(artifact, os.O_RDONLY | os.O_NOFOLLOW)
            source_details = os.fstat(source_descriptor)
            if not stat.S_ISREG(source_details.st_mode):
                raise InstallError("release artifact is not a regular file")
            output_descriptor = os.open(
                artifact_copy,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            with (
                os.fdopen(source_descriptor, "rb", closefd=True) as source,
                os.fdopen(output_descriptor, "wb", closefd=True) as output,
            ):
                source_descriptor = -1
                output_descriptor = -1
                shutil.copyfileobj(source, output, length=1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
            verify_artifact_digest(artifact_copy, expected_sha256)
            with tempfile.TemporaryDirectory(prefix=".agentbox-stage-", dir=releases) as temporary:
                extracted = Path(temporary) / "release"
                extract_verified_tar(artifact_copy, extracted)
                manifest = verify_release(extracted)
                target = self.layout.release(manifest.version)
                if target.exists() or target.is_symlink():
                    existing = verify_release(target, allow_generated_venv=True)
                    if existing != manifest:
                        raise InstallError("existing release does not match the verified artifact")
                    return manifest
                os.replace(extracted, target)
                self._restrict_release(target)
                verify_release(target, manifest)
                return manifest
        except OSError as exc:
            raise InstallError("release artifact could not be staged safely") from exc
        finally:
            if source_descriptor >= 0:
                os.close(source_descriptor)
            if output_descriptor >= 0:
                os.close(output_descriptor)
            with suppress(FileNotFoundError):
                artifact_copy.unlink()

    def _ensure_directories(self) -> None:
        for item in DIRECTORIES:
            target = self.layout.map(item.path)
            self._ensure_trusted_parent_chain(target)
            if not target.exists() and not target.is_symlink():
                target.mkdir(mode=item.mode, parents=False)
            details = target.lstat()
            if stat.S_ISLNK(details.st_mode):
                raise InstallError(f"refusing symlink at managed directory {item.path}")
            if not stat.S_ISDIR(details.st_mode):
                raise InstallError(f"managed directory collision at {item.path}")
            self.host.set_owner_mode(target, item.owner, item.group, item.mode)

    def _write_initial_configuration(self, identities: IdentityFacts) -> None:
        config = self.layout.map("/etc/agentbox/agentbox.toml")
        environment = self.layout.map("/etc/agentbox/environment")
        runtime_environment = self.layout.map("/etc/agentbox/runtime-environment")
        helper_environment = self.layout.map("/etc/agentbox/helper-environment")
        runtime_lines = (
            "AGENTBOX_ENV=production",
            "AGENTBOX_RUNTIME_SOCKET=/run/agentbox/runtime.sock",
            f"AGENTBOX_RUNTIME_SOCKET_GID={identities.ipc_gid}",
            f"AGENTBOX_RUNTIME_ALLOWED_UIDS={identities.agentbox_uid}",
            f"AGENTBOX_RUNTIME_ALLOWED_GIDS={identities.agentbox_gid}",
            "AGENTBOX_PROJECT_ROOT=/srv/agentbox/projects",
            "HOME=/home/agentbox-runtime",
            "PATH=/home/agentbox-runtime/.local/bin:/usr/local/bin:/usr/bin:/bin",
            "LANG=C.UTF-8",
            "TERM=xterm-256color",
            "XDG_CACHE_HOME=/home/agentbox-runtime/.cache",
            "XDG_CONFIG_HOME=/home/agentbox-runtime/.config",
            "XDG_DATA_HOME=/home/agentbox-runtime/.local/share",
            "XDG_STATE_HOME=/home/agentbox-runtime/.local/state",
        )
        runtime_content = "\n".join((*runtime_lines, ""))
        if not config.exists():
            self._atomic_write(
                config,
                (
                    'env = "production"\n'
                    'bind_host = "127.0.0.1"\n'
                    "bind_port = 8787\n"
                    'database_url = "sqlite+pysqlite:////var/lib/agentbox/agentbox.db"\n'
                    'alembic_ini = "/opt/agentbox/current/alembic.ini"\n'
                    'data_dir = "/var/lib/agentbox"\n'
                    'runtime_socket = "/run/agentbox/runtime.sock"\n'
                    'project_root = "/srv/agentbox/projects"\n'
                    "allowed_origins = []\n"
                    "trusted_proxies = []\n"
                ),
                0o640,
            )
        if not environment.exists():
            secret = secrets.token_urlsafe(48)
            self._atomic_write(
                environment,
                "\n".join(
                    (
                        "AGENTBOX_ENV=production",
                        "AGENTBOX_TOML_FILE=/etc/agentbox/agentbox.toml",
                        f"AGENTBOX_SECRET_KEY={secret}",
                        "AGENTBOX_STATIC_DIR=/opt/agentbox/current/web/dist",
                        "",
                    )
                ),
                0o640,
            )
        if not runtime_environment.exists():
            self._atomic_write(runtime_environment, runtime_content, 0o640)
        else:
            legacy_runtime_content = "\n".join(
                (
                    *(
                        line
                        for line in runtime_lines
                        if not line.startswith("AGENTBOX_RUNTIME_ALLOWED_GIDS=")
                    ),
                    "",
                )
            )
            try:
                observed_runtime_content = runtime_environment.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise InstallError("AgentBox Runtime environment is unavailable") from exc
            if observed_runtime_content == legacy_runtime_content:
                self._atomic_write(runtime_environment, runtime_content, 0o640)
        helper_content = (
            f"AGENTBOX_HELPER_ALLOWED_UIDS={identities.agentbox_uid}\n"
            f"AGENTBOX_HELPER_ALLOWED_GIDS={identities.agentbox_gid}\n"
        )
        if not helper_environment.exists():
            self._atomic_write(
                helper_environment,
                helper_content,
                0o600,
            )
        else:
            # Schema 1 installations recorded only the allowed UID. Upgrade
            # that exact root-owned shape without accepting arbitrary keys.
            try:
                legacy_helper = self._parse_environment_file(
                    helper_environment, {"AGENTBOX_HELPER_ALLOWED_UIDS"}
                )
            except InstallError:
                legacy_helper = None
            if legacy_helper == {"AGENTBOX_HELPER_ALLOWED_UIDS": str(identities.agentbox_uid)}:
                self._atomic_write(helper_environment, helper_content, 0o600)
        for path, owner, group, mode in (
            (config, "root", "agentbox", 0o640),
            # systemd PID 1 reads this file and passes the environment to the
            # non-root services; the service identity cannot read or rewrite it.
            (environment, "root", "root", 0o600),
            (runtime_environment, "root", "agentbox-runtime", 0o640),
            (helper_environment, "root", "root", 0o600),
        ):
            self.host.set_owner_mode(path, owner, group, mode)
        try:
            config_values = tomllib.loads(config.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise InstallError("AgentBox production config is invalid") from exc
        required_config = {
            "env": "production",
            "bind_host": "127.0.0.1",
            "bind_port": 8787,
            "database_url": "sqlite+pysqlite:////var/lib/agentbox/agentbox.db",
            "alembic_ini": "/opt/agentbox/current/alembic.ini",
            "data_dir": "/var/lib/agentbox",
            "runtime_socket": "/run/agentbox/runtime.sock",
            "project_root": "/srv/agentbox/projects",
        }
        if any(config_values.get(key) != value for key, value in required_config.items()):
            raise InstallError("AgentBox production config changes a required safety boundary")
        origins = config_values.get("allowed_origins", [])
        if not isinstance(origins, list) or any(
            not isinstance(origin, str) or not origin.startswith("https://") for origin in origins
        ):
            raise InstallError("AgentBox production origins must use HTTPS")
        if any(
            str(key).lower() in {"secret", "secret_key", "token", "password", "api_key"}
            for key in config_values
        ):
            raise InstallError("AgentBox secret material must not be stored in TOML")
        application_values = self._parse_environment_file(
            environment,
            {
                "AGENTBOX_ENV",
                "AGENTBOX_TOML_FILE",
                "AGENTBOX_SECRET_KEY",
                "AGENTBOX_STATIC_DIR",
            },
        )
        if (
            application_values["AGENTBOX_ENV"] != "production"
            or len(application_values["AGENTBOX_SECRET_KEY"].encode()) < 32
        ):
            raise InstallError("AgentBox application environment is invalid")
        runtime_values = self._parse_environment_file(
            runtime_environment,
            {
                "AGENTBOX_ENV",
                "AGENTBOX_RUNTIME_SOCKET",
                "AGENTBOX_RUNTIME_SOCKET_GID",
                "AGENTBOX_RUNTIME_ALLOWED_UIDS",
                "AGENTBOX_RUNTIME_ALLOWED_GIDS",
                "AGENTBOX_PROJECT_ROOT",
                "HOME",
                "PATH",
                "LANG",
                "TERM",
                "XDG_CACHE_HOME",
                "XDG_CONFIG_HOME",
                "XDG_DATA_HOME",
                "XDG_STATE_HOME",
            },
        )
        if (
            runtime_values["AGENTBOX_RUNTIME_ALLOWED_UIDS"] != str(identities.agentbox_uid)
            or runtime_values["AGENTBOX_RUNTIME_ALLOWED_GIDS"] != str(identities.agentbox_gid)
            or runtime_values["AGENTBOX_RUNTIME_SOCKET_GID"] != str(identities.ipc_gid)
        ):
            raise InstallError("AgentBox Runtime environment identity is stale")
        helper_values = self._parse_environment_file(
            helper_environment,
            {"AGENTBOX_HELPER_ALLOWED_UIDS", "AGENTBOX_HELPER_ALLOWED_GIDS"},
        )
        if helper_values["AGENTBOX_HELPER_ALLOWED_UIDS"] != str(
            identities.agentbox_uid
        ) or helper_values["AGENTBOX_HELPER_ALLOWED_GIDS"] != str(identities.agentbox_gid):
            raise InstallError("AgentBox Helper environment identity is stale")

    def _install_units(self) -> None:
        unit_root = self.layout.map("/etc/systemd/system")
        tmpfiles_root = self.layout.map("/etc/tmpfiles.d")
        for root in (unit_root, tmpfiles_root):
            self._ensure_trusted_parent_chain(root)
            if not root.exists() and not root.is_symlink():
                root.mkdir(mode=0o755, parents=False)
            details = root.lstat()
            if (
                stat.S_ISLNK(details.st_mode)
                or not stat.S_ISDIR(details.st_mode)
                or (self.host.real_host and details.st_uid != 0)
            ):
                raise InstallError("systemd installation directory is unsafe")
        package_root = importlib.resources.files("agentbox_installer") / "assets"
        receipt = self._read_receipt()
        managed_hashes = receipt.get("managed_unit_sha256", {}) if receipt else {}
        systemd_version = self.host.systemd_version()
        for name in UNIT_NAMES:
            source = Path(str(package_root / "systemd" / name))
            try:
                validate_unit_compatibility(source.read_text(encoding="utf-8"), systemd_version)
            except (OSError, UnicodeError, ValueError) as exc:
                raise InstallError("AgentBox unit is incompatible with host systemd") from exc
            target = unit_root / name
            if target.exists() or target.is_symlink():
                if target.is_symlink() or not target.is_file():
                    raise InstallError("refusing to replace an unsafe AgentBox unit name")
                if receipt is None:
                    if target.read_bytes() != source.read_bytes():
                        raise InstallError("refusing to replace an unowned AgentBox unit name")
                elif not isinstance(managed_hashes, dict) or managed_hashes.get(
                    name
                ) != self._digest(target):
                    raise InstallError("managed AgentBox unit changed concurrently or externally")
            self.host.install_unit_file(source, target)
        tmpfiles_source = Path(str(package_root / "tmpfiles.d" / "agentbox.conf"))
        tmpfiles_target = tmpfiles_root / "agentbox.conf"
        if tmpfiles_target.exists() or tmpfiles_target.is_symlink():
            expected = receipt.get("managed_tmpfiles_sha256") if receipt else None
            if tmpfiles_target.is_symlink() or not tmpfiles_target.is_file():
                raise InstallError("refusing to replace an unsafe tmpfiles policy")
            if receipt is None and tmpfiles_target.read_bytes() != tmpfiles_source.read_bytes():
                raise InstallError("refusing to replace an unowned tmpfiles policy")
            if receipt is not None and expected != self._digest(tmpfiles_target):
                raise InstallError("managed tmpfiles policy changed concurrently or externally")
        self.host.install_unit_file(tmpfiles_source, tmpfiles_target)

    @staticmethod
    def _parse_environment_file(path: Path, expected_keys: set[str]) -> dict[str, str]:
        values: dict[str, str] = {}
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise InstallError("AgentBox environment file is unavailable") from exc
        for line in lines:
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if (
                separator != "="
                or key not in expected_keys
                or key in values
                or not value
                or re.fullmatch(r"[A-Za-z0-9_./:+,-]+", value) is None
            ):
                raise InstallError("AgentBox environment file is invalid")
            values[key] = value
        if set(values) != expected_keys:
            raise InstallError("AgentBox environment file is incomplete")
        return values

    def _run_migration(self, manifest: ReleaseManifest) -> None:
        if not self.host.real_host:
            with sqlite3.connect(self.layout.database) as connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(80) NOT NULL)"
                )
                connection.execute("DELETE FROM alembic_version")
                connection.execute(
                    "INSERT INTO alembic_version(version_num) VALUES (?)",
                    (manifest.database_revision,),
                )
            os.chmod(self.layout.database, 0o600)
            return
        self.host.migrate(
            self.layout.release(manifest.version), self.layout.map("/etc/agentbox/environment")
        )
        for suffix in ("", "-wal", "-shm"):
            database_file = Path(f"{self.layout.database}{suffix}")
            if database_file.exists():
                self.host.set_owner_mode(database_file, "agentbox", "agentbox", 0o600)

    def _backup_before_change(self, current: str | None) -> BackupResult | None:
        if current is None or not self.layout.database.exists():
            return None
        manifest = load_manifest(self.layout.release(current))
        self._assert_trusted_parent(self.layout.backups)
        result = create_sqlite_backup(
            self.layout.database,
            self.layout.backups,
            application_version=current,
            migration_revision=manifest.database_revision,
            config_path=self.layout.map("/etc/agentbox/agentbox.toml"),
            unit_paths=tuple(
                path
                for name in UNIT_NAMES
                if (path := self.layout.map(f"/etc/systemd/system/{name}")).is_file()
                and not path.is_symlink()
            ),
            tmpfiles_path=(
                tmpfiles
                if (
                    (tmpfiles := self.layout.map("/etc/tmpfiles.d/agentbox.conf")).is_file()
                    and not tmpfiles.is_symlink()
                )
                else None
            ),
        )
        if self.host.real_host:
            for path in (result.path, *result.path.rglob("*")):
                if path.is_symlink():
                    raise InstallError("backup contains an unsafe filesystem object")
                self.host.set_owner_mode(path, "root", "root", 0o700 if path.is_dir() else 0o600)
        return result

    def _activate(self, version: str) -> None:
        release = self.layout.release(version)
        verify_release(release, allow_generated_venv=True)
        link = self.layout.current_link
        self._assert_trusted_parent(link)
        if link.exists() and not link.is_symlink():
            raise InstallError("current release path is not a symlink")
        temporary = link.with_name(".current.agentbox-new")
        if temporary.exists() or temporary.is_symlink():
            raise InstallError("release activation staging collision")
        os.symlink(f"releases/{version}", temporary)
        os.replace(temporary, link)

    def _rollback_failed_change(
        self,
        *,
        previous: str | None,
        backup: BackupResult | None,
        activated: bool,
        attempted_version: str,
        transaction_id: str,
        resources: list[dict[str, Any]],
    ) -> bool:
        del transaction_id
        try:
            self.host.stop_agentbox()
            if previous is None:
                self.host.disable_and_stop()
                if activated and not self._remove_transaction_current_link(
                    resources, attempted_version
                ):
                    return False
                if not self._remove_transaction_database_objects(resources):
                    return False
                return self.current_version() is None and not self.layout.database.exists()
            if backup is not None:
                self._restore_backup(backup)
            self._activate(previous)
            self._prepare_database_directory_for_release(previous)
            legacy = self.host.real_host and self._uses_legacy_database_layout(previous)
            try:
                self.host.restart_agentbox()
                previous_manifest = load_manifest(self.layout.release(previous))
                verified = (
                    self.current_version() == previous
                    and self._database_integrity_and_revision(previous_manifest.database_revision)
                    and self.health_check(expected_version=previous)
                )
            finally:
                if legacy:
                    self.host.stop_agentbox()
                    self._harden_database_directory()
            # A legacy process that cannot restart under the hardened layout is
            # not a stable verified rollback, even if its point-in-time probes
            # passed before it was stopped.
            return verified and not legacy
        except Exception:
            return False

    def _prepare_database_directory_for_release(self, version: str) -> None:
        """Use the exact data layout understood by the release being activated."""
        parent = self.layout.database.parent
        self._assert_trusted_parent(self.layout.database)
        if self._uses_legacy_database_layout(version):
            self.host.set_owner_mode(parent, "agentbox", "agentbox", 0o700)
        else:
            self._harden_database_directory()

    @staticmethod
    def _uses_legacy_database_layout(version: str) -> bool:
        return _compare_versions(version, HARDENED_DATA_LAYOUT_MIN_VERSION) < 0

    def _harden_database_directory(self) -> None:
        self.host.set_owner_mode(
            self.layout.database.parent,
            "root",
            "agentbox",
            0o1770,
        )

    def _restore_backup(self, backup: BackupResult) -> None:
        self._verify_backup_for_restore(backup)
        self._remove_database_sidecars()
        self._assert_trusted_parent(self.layout.database)
        self.host.copy_file(backup.path / "agentbox.db", self.layout.database, 0o600)
        self.host.set_owner_mode(self.layout.database, "agentbox", "agentbox", 0o600)
        if not self._database_integrity_and_revision(None):
            raise InstallError("restored database integrity verification failed")
        config_backup = backup.path / "agentbox.toml"
        if config_backup.is_file() and not config_backup.is_symlink():
            self.host.copy_file(
                config_backup,
                self.layout.map("/etc/agentbox/agentbox.toml"),
                0o640,
            )
            self.host.set_owner_mode(
                self.layout.map("/etc/agentbox/agentbox.toml"), "root", "agentbox", 0o640
            )
        units_backup = backup.path / "units"
        if units_backup.is_dir() and not units_backup.is_symlink():
            for name in UNIT_NAMES:
                source = units_backup / name
                if source.is_file() and not source.is_symlink():
                    self.host.copy_file(
                        source,
                        self.layout.map(f"/etc/systemd/system/{name}"),
                        0o644,
                    )
        tmpfiles_backup = backup.path / "tmpfiles/agentbox.conf"
        if tmpfiles_backup.is_file() and not tmpfiles_backup.is_symlink():
            self.host.copy_file(
                tmpfiles_backup,
                self.layout.map("/etc/tmpfiles.d/agentbox.conf"),
                0o644,
            )
        self.host.daemon_reload()

    def _verify_backup_for_restore(self, backup: BackupResult) -> None:
        if self.host.real_host:
            for path in (backup.path, *backup.path.rglob("*")):
                details = path.lstat()
                if details.st_uid != 0 or details.st_gid != 0 or stat.S_ISLNK(details.st_mode):
                    raise InstallError("database backup ownership is unsafe")
        if not verify_sqlite_backup(backup):
            raise InstallError("database backup verification failed")

    def _verify_backup_for_target(
        self,
        backup: BackupResult,
        *,
        application_version: str,
        migration_revision: str,
    ) -> None:
        self._verify_backup_for_restore(backup)
        manifest_path = backup.path / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise InstallError("database backup target evidence is unavailable") from exc
        if (
            not isinstance(manifest, dict)
            or manifest.get("application_version") != application_version
            or manifest.get("migration_revision") != migration_revision
        ):
            raise InstallError("database backup is not bound to the rollback target")

    def _load_backup(
        self, backup_id: str, *, expected_manifest_sha256: str | None = None
    ) -> BackupResult:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", backup_id):
            raise InstallError("recorded database backup identifier is invalid")
        manifest_path = self.layout.backups / backup_id / "manifest.json"
        if expected_manifest_sha256 is not None and (
            not re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256)
            or manifest_path.is_symlink()
            or not manifest_path.is_file()
            or self._digest(manifest_path) != expected_manifest_sha256
        ):
            raise InstallError("recorded database backup identity does not match")
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
            digest = str(value["database_sha256"])
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            raise InstallError("recorded database backup is unavailable") from exc
        return BackupResult(backup_id, manifest_path.parent, digest)

    def _database_integrity_and_revision(self, expected_revision: str | None) -> bool:
        database = self.layout.database
        if database.is_symlink() or not database.is_file():
            return False
        try:
            with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
                connection.execute("PRAGMA query_only=ON")
                if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    return False
                rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
                if expected_revision is not None and rows != [(expected_revision,)]:
                    return False
                if len(rows) != 1:
                    return False
                if rows[0][0] in {
                    "0004_phase11_provider_core",
                    "0005_phase11_control_plane_ownership_approval",
                }:
                    from agentbox_core.migration_inventory import verify_phase11_database

                    return verify_phase11_database(database, rows[0][0])
                return True
        except sqlite3.Error:
            return False

    def _remove_database_sidecars(self) -> None:
        self._assert_trusted_parent(self.layout.database)
        removed = False
        for suffix in ("-wal", "-shm"):
            path = Path(f"{self.layout.database}{suffix}")
            try:
                details = path.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
                raise InstallError("SQLite sidecar is unsafe")
            if self.host.real_host:
                expected_uid, expected_gid = self.host.owner_ids("agentbox", "agentbox")
                if details.st_uid != expected_uid or details.st_gid != expected_gid:
                    raise InstallError("SQLite sidecar ownership is unsafe")
            path.unlink()
            removed = True
        if removed:
            descriptor = os.open(
                self.layout.database.parent,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    @staticmethod
    def _filesystem_identity(path: Path) -> dict[str, object] | None:
        try:
            details = path.lstat()
        except FileNotFoundError:
            return None
        if stat.S_ISREG(details.st_mode):
            object_type = "regular_file"
        elif stat.S_ISDIR(details.st_mode):
            object_type = "directory"
        elif stat.S_ISLNK(details.st_mode):
            object_type = "symlink"
        elif stat.S_ISSOCK(details.st_mode):
            object_type = "socket"
        else:
            object_type = "other"
        return {
            "type": object_type,
            "owner_uid": details.st_uid,
            "group_gid": details.st_gid,
            "mode": f"{stat.S_IMODE(details.st_mode):04o}",
            "device": details.st_dev,
            "inode": details.st_ino,
        }

    def _snapshot_transaction_resources(self, version: str) -> list[dict[str, Any]]:
        expected: dict[str, str] = {item.path: "directory" for item in DIRECTORIES}
        expected.update(
            {
                "/etc/agentbox/agentbox.toml": "regular_file",
                "/etc/agentbox/environment": "regular_file",
                "/etc/agentbox/runtime-environment": "regular_file",
                "/etc/agentbox/helper-environment": "regular_file",
                "/var/lib/agentbox/agentbox.db": "regular_file",
                "/var/lib/agentbox/agentbox.db-wal": "regular_file",
                "/var/lib/agentbox/agentbox.db-shm": "regular_file",
                "/var/lib/agentbox/install-receipt.json": "regular_file",
                "/var/lib/agentbox/install-journal.json": "regular_file",
                f"/opt/agentbox/releases/{version}": "directory",
                "/opt/agentbox/current": "symlink",
                "/etc/tmpfiles.d/agentbox.conf": "regular_file",
                **{f"/etc/systemd/system/{name}": "regular_file" for name in UNIT_NAMES},
            }
        )
        resources: list[dict[str, Any]] = []
        for path, expected_type in sorted(expected.items()):
            mapped = self.layout.map(path)
            identity = self._filesystem_identity(mapped)
            resources.append(
                {
                    "expected_path": path,
                    "expected_type": expected_type,
                    "existed_before": identity is not None,
                    "initial_identity": identity,
                    "created_identity": None,
                }
            )
        return resources

    def _record_created_database_objects(self, resources: list[dict[str, Any]]) -> None:
        for resource in resources:
            path = resource.get("expected_path")
            if (
                path
                not in {
                    "/var/lib/agentbox/agentbox.db",
                    "/var/lib/agentbox/agentbox.db-wal",
                    "/var/lib/agentbox/agentbox.db-shm",
                }
                or resource.get("existed_before") is not False
            ):
                continue
            identity = self._filesystem_identity(self.layout.map(str(path)))
            if identity is not None and identity.get("type") != "regular_file":
                raise InstallError("migration created an unsafe database object")
            resource["created_identity"] = identity

    @staticmethod
    def _resource(resources: list[dict[str, Any]], expected_path: str) -> dict[str, Any] | None:
        return next(
            (item for item in resources if item.get("expected_path") == expected_path),
            None,
        )

    def _remove_transaction_database_objects(self, resources: list[dict[str, Any]]) -> bool:
        for path_value in (
            "/var/lib/agentbox/agentbox.db-wal",
            "/var/lib/agentbox/agentbox.db-shm",
            "/var/lib/agentbox/agentbox.db",
        ):
            resource = self._resource(resources, path_value)
            if resource is None or resource.get("existed_before") is not False:
                return False
            path = self.layout.map(path_value)
            observed = self._filesystem_identity(path)
            if observed is None:
                continue
            if observed != resource.get("created_identity"):
                return False
            path.unlink()
        return True

    def _remove_transaction_current_link(
        self, resources: list[dict[str, Any]], attempted_version: str
    ) -> bool:
        resource = self._resource(resources, "/opt/agentbox/current")
        link = self.layout.current_link
        if resource is None or resource.get("existed_before") is not False or not link.is_symlink():
            return False
        if os.readlink(link) != f"releases/{attempted_version}":
            return False
        self._assert_trusted_parent(link)
        link.unlink()
        return True

    def _recovery_state(self, receipt: dict[str, Any] | None, current: str | None) -> str | None:
        journal = self._read_journal()
        if journal is None:
            return None
        status = journal.get("status")
        if status == "rollback_verification_failed":
            return "rollback_pending"
        if status != "running":
            return None
        version = journal.get("version")
        completed_raw = journal.get("completed_steps")
        if not isinstance(version, str) or not isinstance(completed_raw, list):
            return "unknown"
        completed = {value for value in completed_raw if isinstance(value, str)}
        preflight_steps = {"identities", "directories", "configuration"}
        if completed.issubset(preflight_steps):
            return "preflight_interrupted"
        receipt_version = receipt.get("active_version") if receipt is not None else None
        if current == version and receipt_version != version:
            return "activated"
        if (
            current == version
            and receipt_version == version
            and "receipt_write_started" in completed
        ):
            # The release receipt was durably replaced, but the final committed
            # journal write was interrupted. Treat it as activated/verify-only,
            # never as a partially migrated state that could invite DB replay.
            return "activated"
        if "database_migrated" in completed or "database_migration_started" in completed:
            return "partially_migrated"
        if "release_staged" in completed:
            return "staged"
        if "release_staging_started" in completed:
            try:
                staged = verify_release(self.layout.release(version), allow_generated_venv=True)
            except (ArtifactError, OSError):
                return "unknown"
            return "staged" if staged.version == version else "unknown"
        return "unknown"

    def _write_receipt(
        self,
        manifest: ReleaseManifest,
        previous: str | None,
        backup: BackupResult | None,
        identities: IdentityFacts,
    ) -> None:
        receipt = {
            "schema_version": 1,
            "active_version": manifest.version,
            "previous_version": previous,
            "database_revision": manifest.database_revision,
            "pre_change_backup_id": backup.backup_id if backup else None,
            "pre_change_backup_manifest_sha256": (
                self._digest(backup.path / "manifest.json") if backup else None
            ),
            "installed_at": datetime.now(UTC).isoformat(),
            "identities": asdict(identities),
            "managed_units": list(UNIT_NAMES),
            "managed_unit_sha256": {
                name: self._digest(self.layout.map(f"/etc/systemd/system/{name}"))
                for name in UNIT_NAMES
            },
            "managed_tmpfiles_sha256": self._digest(
                self.layout.map("/etc/tmpfiles.d/agentbox.conf")
            ),
            "bind": "127.0.0.1:8787",
            "credentials_migrated": False,
            "projects_migrated": False,
        }
        self._atomic_write(self.layout.receipt, json.dumps(receipt, sort_keys=True) + "\n", 0o600)
        self.host.set_owner_mode(self.layout.receipt, "root", "root", 0o600)

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _write_journal(
        self,
        *,
        status: str,
        version: str,
        completed: tuple[str, ...],
        transaction_id: str,
        resources: list[dict[str, Any]],
    ) -> None:
        allowed_statuses = {
            "running",
            "committed",
            "rollback_verified",
            "rollback_verification_failed",
        }
        if status not in allowed_statuses:
            raise ValueError("installer journal status is invalid")
        value = {
            "schema_version": 2,
            "transaction_id": transaction_id,
            "version": version,
            "status": status,
            "completed_steps": list(completed),
            "updated_at": datetime.now(UTC).isoformat(),
            "contains_secrets": False,
            "resources": resources,
        }
        self._atomic_write(
            self.layout.journal,
            json.dumps(value, sort_keys=True) + "\n",
            0o600,
        )
        self.host.set_owner_mode(self.layout.journal, "root", "root", 0o600)

    def _read_receipt(self) -> dict[str, Any] | None:
        path = self.layout.receipt
        if path.is_symlink() or not path.is_file():
            return None
        details = path.lstat()
        if self.host.real_host and (
            details.st_uid != 0 or details.st_gid != 0 or stat.S_IMODE(details.st_mode) != 0o600
        ):
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) and value.get("schema_version") == 1 else None

    @staticmethod
    def _receipt_identities(receipt: dict[str, Any] | None) -> IdentityFacts | None:
        if receipt is None:
            return None
        raw = receipt.get("identities")
        required = {"agentbox_uid", "agentbox_gid", "runtime_uid", "ipc_gid"}
        if not isinstance(raw, dict) or set(raw) != required:
            raise InstallError("installation receipt identity evidence is invalid")
        values = tuple(raw[key] for key in sorted(required))
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in values
        ):
            raise InstallError("installation receipt identity evidence is invalid")
        return IdentityFacts(
            agentbox_uid=raw["agentbox_uid"],
            agentbox_gid=raw["agentbox_gid"],
            runtime_uid=raw["runtime_uid"],
            ipc_gid=raw["ipc_gid"],
        )

    def _read_journal(self) -> dict[str, Any] | None:
        path = self.layout.journal
        if not path.exists() and not path.is_symlink():
            return None
        if path.is_symlink() or not path.is_file():
            raise InstallError("installer journal is unsafe")
        details = path.lstat()
        if self.host.real_host and (
            details.st_uid != 0 or details.st_gid != 0 or stat.S_IMODE(details.st_mode) != 0o600
        ):
            raise InstallError("installer journal permissions are unsafe")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise InstallError("installer journal is corrupt") from exc
        if not isinstance(value, dict) or value.get("schema_version") not in {1, 2}:
            raise InstallError("installer journal schema is unsupported")
        return value

    def _atomic_write(self, path: Path, content: str, mode: int) -> None:
        self._assert_trusted_parent(path)
        parent_descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        temporary_name = f".{path.name}.agentbox-new"
        try:
            try:
                existing = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
            except FileNotFoundError:
                existing = None
            if existing is not None and stat.S_ISLNK(existing.st_mode):
                raise InstallError("refusing to replace a symlinked managed file")
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                mode,
                dir_fd=parent_descriptor,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(
                temporary_name,
                path.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            os.fsync(parent_descriptor)
        except Exception:
            with suppress(FileNotFoundError):
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            raise
        finally:
            os.close(parent_descriptor)

    def _assert_trusted_parent(self, path: Path) -> None:
        """Reject symlinked or non-root parent chains for privileged writes."""
        parent = path.parent
        root = self.layout.root
        if root.is_symlink() or not root.is_dir():
            raise InstallError("installer fixture/root boundary is unsafe")
        try:
            relative = parent.relative_to(root)
        except ValueError as exc:
            raise InstallError("installer path escapes its root") from exc
        cursor = root
        for part in relative.parts:
            cursor = cursor / part
            try:
                details = cursor.lstat()
            except FileNotFoundError as exc:
                raise InstallError("installer parent directory is missing") from exc
            if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
                raise InstallError("installer parent chain is unsafe")
            if self.host.real_host and details.st_uid != 0:
                raise InstallError("installer parent chain is not root-owned")

    def _ensure_trusted_parent_chain(self, path: Path) -> None:
        """Create missing parents one component at a time without following links."""
        root = self.layout.root
        if root.is_symlink() or not root.is_dir():
            raise InstallError("installer fixture/root boundary is unsafe")
        try:
            relative = path.parent.relative_to(root)
        except ValueError as exc:
            raise InstallError("installer path escapes its root") from exc
        cursor = root
        for part in relative.parts:
            cursor = cursor / part
            try:
                details = cursor.lstat()
            except FileNotFoundError:
                cursor.mkdir(mode=0o755, parents=False)
                details = cursor.lstat()
            if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
                raise InstallError("installer parent chain is unsafe")
            if self.host.real_host and details.st_uid != 0:
                raise InstallError("installer parent chain is not root-owned")

    @staticmethod
    def _restrict_release(release: Path) -> None:
        os.chmod(release, 0o755)
        for path in release.rglob("*"):
            details = path.lstat()
            if stat.S_ISDIR(details.st_mode):
                os.chmod(path, 0o755)
            elif stat.S_ISREG(details.st_mode):
                executable = bool(details.st_mode & 0o111)
                os.chmod(path, 0o755 if executable else 0o644)
