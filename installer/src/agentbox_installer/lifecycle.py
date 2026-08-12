"""Idempotent install, staged upgrade, and verified rollback lifecycle."""

from __future__ import annotations

import fcntl
import hashlib
import importlib.resources
import json
import os
import re
import secrets
import sqlite3
import stat
import time
import tomllib
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentbox_installer.artifact import (
    VERSION_PATTERN,
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
from agentbox_installer.host import HostOperations, IdentityFacts
from agentbox_installer.layout import DIRECTORIES, InstallLayout
from agentbox_installer.platform import PlatformFacts, detect_platform, resolve_packages

UNIT_NAMES = (
    "agentbox-api.service",
    "agentbox-worker.service",
    "agentbox-runtime.service",
    "agentbox-helper.socket",
    "agentbox-helper.service",
)


def _compare_versions(candidate: str, current: str) -> int:
    """Compare the ordered SemVer core; build metadata never authorizes downgrade."""
    pattern = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")
    candidate_match = pattern.fullmatch(candidate)
    current_match = pattern.fullmatch(current)
    if candidate_match is None or current_match is None:
        raise InstallError("installed or candidate release version is invalid")
    candidate_key = tuple(int(part) for part in candidate_match.groups())
    current_key = tuple(int(part) for part in current_match.groups())
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
            return LifecycleResult(plan.version, current, False, None, self.health_check())
        if state == "installed_newer_version":
            raise InstallError("downgrade is not supported; use a verified rollback target")
        if state == "partial_or_broken":
            raise InstallError(
                "existing AgentBox installation is partial or broken; inspect before repair"
            )
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

        identities = self.host.ensure_identities()
        self._ensure_directories()
        self._write_journal(
            status="running",
            version=plan.version,
            completed=("identities", "directories"),
        )
        self._write_initial_configuration(identities)
        self._write_journal(
            status="running",
            version=plan.version,
            completed=("identities", "directories", "configuration"),
        )
        manifest = self._stage_release(artifact, expected_sha256)
        self.host.prepare_release_environment(self.layout.release(manifest.version))
        self._write_journal(
            status="running",
            version=plan.version,
            completed=("identities", "directories", "configuration", "release_staged"),
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
        database_created = not self.layout.database.exists()
        activated = False
        try:
            self._run_migration(manifest)
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
            )
            self._install_units()
            self._activate(manifest.version)
            activated = True
            self.host.daemon_reload()
            self.host.enable_and_start()
            if not self.health_check():
                raise InstallError("post-install health verification failed")
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
                    "receipt_written",
                ),
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
                database_created=database_created,
                activated=activated,
            )
            self._write_journal(
                status="rollback_verified" if rollback_ok else "rollback_verification_failed",
                version=plan.version,
                completed=("rollback_attempted",),
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
        target = target_version or receipt.get("previous_version")
        if not isinstance(target, str) or not VERSION_PATTERN.fullmatch(target):
            raise InstallError("no previous release is recorded")
        target_manifest = verify_release(self.layout.release(target), allow_generated_venv=True)
        if target_manifest.version != target:
            raise InstallError("rollback target identity does not match its release")
        backup_id = receipt.get("pre_change_backup_id")
        backup = self._load_backup(str(backup_id)) if backup_id else None
        if not target_manifest.database_backward_compatible and backup is None:
            raise InstallError("application rollback requires a verified database backup")
        self.host.stop_agentbox()
        if backup is not None:
            self._restore_backup(backup)
        self._activate(target)
        self.host.restart_agentbox()
        verified = self.current_version() == target and self.health_check()
        if not verified:
            raise RollbackVerificationError("rollback attempted but verification failed")
        identities = self.host.ensure_identities()
        self._write_receipt(target_manifest, current, None, identities)
        return LifecycleResult(target, current, True, backup.backup_id if backup else None, True)

    def uninstall(self) -> dict[str, object]:
        self.host.require_root()
        with self._lifecycle_lock():
            return self._uninstall_locked()

    def _uninstall_locked(self) -> dict[str, object]:
        """Remove only verified program files/units; persistent data is always retained."""
        receipt = self._read_receipt()
        if receipt is None:
            raise InstallError("AgentBox installation receipt is unavailable")
        self.host.disable_and_stop()
        link = self.layout.current_link
        if link.is_symlink() and self.current_version() is not None:
            link.unlink()
        releases_root = self.layout.map("/opt/agentbox/releases")
        if releases_root.is_dir() and not releases_root.is_symlink():
            for release in releases_root.iterdir():
                if release.is_symlink() or not release.is_dir():
                    raise InstallError("uninstall found an unknown release object")
                verify_release(release, allow_generated_venv=True)
                remove_verified_tree(release)
        package_root = importlib.resources.files("agentbox_installer") / "assets/systemd"
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
            target.unlink()
        tmpfiles = self.layout.map("/etc/tmpfiles.d/agentbox.conf")
        expected_tmpfiles = Path(
            str(importlib.resources.files("agentbox_installer") / "assets/tmpfiles.d/agentbox.conf")
        )
        if tmpfiles.is_file() and not tmpfiles.is_symlink():
            if tmpfiles.read_bytes() != expected_tmpfiles.read_bytes():
                raise InstallError("refusing to remove a modified tmpfiles policy")
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
        if parent.is_symlink():
            raise InstallError("installer lifecycle lock parent is unsafe")
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
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
        verify_artifact_digest(artifact, expected_sha256)
        import tempfile

        releases = self.layout.map("/opt/agentbox/releases")
        with tempfile.TemporaryDirectory(prefix=".agentbox-stage-", dir=releases) as temporary:
            extracted = Path(temporary) / "release"
            extract_verified_tar(artifact, extracted)
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

    def _ensure_directories(self) -> None:
        for item in DIRECTORIES:
            target = self.layout.map(item.path)
            if target.is_symlink():
                raise InstallError(f"refusing symlink at managed directory {item.path}")
            target.mkdir(mode=item.mode, parents=True, exist_ok=True)
            if not target.is_dir():
                raise InstallError(f"managed directory collision at {item.path}")
            self.host.set_owner_mode(target, item.owner, item.group, item.mode)

    def _write_initial_configuration(self, identities: IdentityFacts) -> None:
        config = self.layout.map("/etc/agentbox/agentbox.toml")
        environment = self.layout.map("/etc/agentbox/environment")
        runtime_environment = self.layout.map("/etc/agentbox/runtime-environment")
        helper_environment = self.layout.map("/etc/agentbox/helper-environment")
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
            self._atomic_write(
                runtime_environment,
                "\n".join(
                    (
                        "AGENTBOX_ENV=production",
                        "AGENTBOX_RUNTIME_SOCKET=/run/agentbox/runtime.sock",
                        f"AGENTBOX_RUNTIME_SOCKET_GID={identities.ipc_gid}",
                        f"AGENTBOX_RUNTIME_ALLOWED_UIDS={identities.agentbox_uid}",
                        "AGENTBOX_PROJECT_ROOT=/srv/agentbox/projects",
                        "HOME=/home/agentbox-runtime",
                        "PATH=/home/agentbox-runtime/.local/bin:/usr/local/bin:/usr/bin:/bin",
                        "LANG=C.UTF-8",
                        "TERM=xterm-256color",
                        "XDG_CACHE_HOME=/home/agentbox-runtime/.cache",
                        "XDG_CONFIG_HOME=/home/agentbox-runtime/.config",
                        "XDG_DATA_HOME=/home/agentbox-runtime/.local/share",
                        "XDG_STATE_HOME=/home/agentbox-runtime/.local/state",
                        "",
                    )
                ),
                0o640,
            )
        if not helper_environment.exists():
            self._atomic_write(
                helper_environment,
                f"AGENTBOX_HELPER_ALLOWED_UIDS={identities.agentbox_uid}\n",
                0o600,
            )
        for path, owner, group, mode in (
            (config, "root", "agentbox", 0o640),
            (environment, "root", "agentbox", 0o640),
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
        if runtime_values["AGENTBOX_RUNTIME_ALLOWED_UIDS"] != str(
            identities.agentbox_uid
        ) or runtime_values["AGENTBOX_RUNTIME_SOCKET_GID"] != str(identities.ipc_gid):
            raise InstallError("AgentBox Runtime environment identity is stale")
        helper_values = self._parse_environment_file(
            helper_environment, {"AGENTBOX_HELPER_ALLOWED_UIDS"}
        )
        if helper_values["AGENTBOX_HELPER_ALLOWED_UIDS"] != str(identities.agentbox_uid):
            raise InstallError("AgentBox Helper environment identity is stale")

    def _install_units(self) -> None:
        unit_root = self.layout.map("/etc/systemd/system")
        tmpfiles_root = self.layout.map("/etc/tmpfiles.d")
        unit_root.mkdir(mode=0o755, parents=True, exist_ok=True)
        tmpfiles_root.mkdir(mode=0o755, parents=True, exist_ok=True)
        package_root = importlib.resources.files("agentbox_installer") / "assets"
        receipt = self._read_receipt()
        managed_hashes = receipt.get("managed_unit_sha256", {}) if receipt else {}
        for name in UNIT_NAMES:
            source = Path(str(package_root / "systemd" / name))
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
                or "\x00" in value
                or "\n" in value
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
        database_created: bool,
        activated: bool,
    ) -> bool:
        try:
            self.host.stop_agentbox()
            if previous is None:
                self.host.disable_and_stop()
                if activated and self.layout.current_link.is_symlink():
                    self.layout.current_link.unlink()
                if database_created and self.layout.database.is_file():
                    self.layout.database.unlink()
                return True
            if backup is not None:
                self._restore_backup(backup)
            self._activate(previous)
            self.host.restart_agentbox()
            return self.current_version() == previous and self.health_check()
        except Exception:
            return False

    def _restore_backup(self, backup: BackupResult) -> None:
        if self.host.real_host:
            for path in (backup.path, *backup.path.rglob("*")):
                details = path.lstat()
                if details.st_uid != 0 or details.st_gid != 0 or path.is_symlink():
                    raise InstallError("database backup ownership is unsafe")
        if not verify_sqlite_backup(backup):
            raise InstallError("database backup verification failed")
        self.host.copy_file(backup.path / "agentbox.db", self.layout.database, 0o600)
        self.host.set_owner_mode(self.layout.database, "agentbox", "agentbox", 0o600)
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
            self.host.daemon_reload()

    def _load_backup(self, backup_id: str) -> BackupResult:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", backup_id):
            raise InstallError("recorded database backup identifier is invalid")
        manifest_path = self.layout.backups / backup_id / "manifest.json"
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
            digest = str(value["database_sha256"])
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            raise InstallError("recorded database backup is unavailable") from exc
        return BackupResult(backup_id, manifest_path.parent, digest)

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
        self.host.set_owner_mode(self.layout.receipt, "agentbox", "agentbox", 0o600)

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _write_journal(self, *, status: str, version: str, completed: tuple[str, ...]) -> None:
        allowed_statuses = {
            "running",
            "committed",
            "rollback_verified",
            "rollback_verification_failed",
        }
        if status not in allowed_statuses:
            raise ValueError("installer journal status is invalid")
        value = {
            "schema_version": 1,
            "version": version,
            "status": status,
            "completed_steps": list(completed),
            "updated_at": datetime.now(UTC).isoformat(),
            "contains_secrets": False,
        }
        self._atomic_write(
            self.layout.journal,
            json.dumps(value, sort_keys=True) + "\n",
            0o600,
        )
        self.host.set_owner_mode(self.layout.journal, "agentbox", "agentbox", 0o600)

    def _read_receipt(self) -> dict[str, Any] | None:
        path = self.layout.receipt
        if path.is_symlink() or not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) and value.get("schema_version") == 1 else None

    @staticmethod
    def _atomic_write(path: Path, content: str, mode: int) -> None:
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
