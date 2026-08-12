"""Root host operations restricted to the Installer boundary."""

from __future__ import annotations

import grp
import os
import pwd
import re
import shutil
import socket
import stat
import subprocess
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from agentbox_installer.platform import PackageFamily


class HostMutationError(RuntimeError):
    pass


@dataclass(frozen=True)
class IdentityFacts:
    agentbox_uid: int
    agentbox_gid: int
    runtime_uid: int
    ipc_gid: int


class HostOperations:
    """Fixed user, ownership, systemd and migration operations."""

    def __init__(self, *, real_host: bool) -> None:
        self.real_host = real_host

    @staticmethod
    def _run(argv: tuple[str, ...], *, timeout: int = 120) -> None:
        try:
            result = subprocess.run(  # noqa: S603 - fixed argv in the Installer boundary
                argv,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise HostMutationError("fixed host operation failed to execute") from exc
        if result.returncode != 0:
            raise HostMutationError("fixed host operation returned failure")

    def require_root(self) -> None:
        if self.real_host and os.geteuid() != 0:
            raise HostMutationError("real-host installation requires root")

    def systemd_available(self) -> bool:
        if not self.real_host:
            return True
        try:
            comm = Path("/proc/1/comm").read_text(encoding="ascii").strip()
        except (OSError, UnicodeError):
            return False
        return comm == "systemd" and Path("/run/systemd/system").is_dir()

    def ensure_identities(self, expected: IdentityFacts | None = None) -> IdentityFacts:
        if not self.real_host:
            return IdentityFacts(19001, 19001, 19002, 19003)
        self.require_root()
        group_names = ("agentbox", "agentbox-runtime", "agentbox-runtime-ipc")
        users = (
            ("agentbox", "/var/lib/agentbox", "agentbox"),
            ("agentbox-runtime", "/home/agentbox-runtime", "agentbox-runtime"),
        )
        existing_groups = {}
        existing_users = {}
        for group_name in group_names:
            with suppress(KeyError):
                existing_groups[group_name] = grp.getgrnam(group_name)
        for user_name, _home, _primary_group in users:
            with suppress(KeyError):
                existing_users[user_name] = pwd.getpwnam(user_name)
        if existing_groups or existing_users:
            if expected is None:
                raise HostMutationError(
                    "pre-existing AgentBox identity names lack an installation receipt"
                )
            self._validate_existing_identities(existing_users, existing_groups, expected)
        else:
            for group_name in group_names:
                self._run(("/usr/sbin/groupadd", "--system", group_name))
            for user_name, home, primary_group in users:
                self._run(
                    (
                        "/usr/sbin/useradd",
                        "--system",
                        "--gid",
                        primary_group,
                        "--home-dir",
                        home,
                        "--shell",
                        "/usr/sbin/nologin",
                        user_name,
                    )
                )
        self._run(("/usr/sbin/usermod", "--append", "--groups", "agentbox-runtime-ipc", "agentbox"))
        self._run(
            (
                "/usr/sbin/usermod",
                "--append",
                "--groups",
                "agentbox-runtime-ipc",
                "agentbox-runtime",
            )
        )
        agentbox = pwd.getpwnam("agentbox")
        runtime = pwd.getpwnam("agentbox-runtime")
        agentbox_group = grp.getgrnam("agentbox")
        runtime_group = grp.getgrnam("agentbox-runtime")
        ipc = grp.getgrnam("agentbox-runtime-ipc")
        if agentbox.pw_uid == runtime.pw_uid or ipc.gr_gid in {agentbox.pw_gid, runtime.pw_gid}:
            raise HostMutationError("AgentBox identity collision detected")
        observed = IdentityFacts(agentbox.pw_uid, agentbox.pw_gid, runtime.pw_uid, ipc.gr_gid)
        self._validate_existing_identities(
            {"agentbox": agentbox, "agentbox-runtime": runtime},
            {
                "agentbox": agentbox_group,
                "agentbox-runtime": runtime_group,
                "agentbox-runtime-ipc": ipc,
            },
            observed,
        )
        if expected is not None and observed != expected:
            raise HostMutationError("AgentBox identity no longer matches its installation receipt")
        return observed

    @staticmethod
    def _validate_existing_identities(
        users: Mapping[str, object],
        groups: Mapping[str, object],
        expected: IdentityFacts,
    ) -> None:
        if set(users) != {"agentbox", "agentbox-runtime"} or set(groups) != {
            "agentbox",
            "agentbox-runtime",
            "agentbox-runtime-ipc",
        }:
            raise HostMutationError("AgentBox identity set is incomplete or colliding")
        agentbox = users["agentbox"]
        runtime = users["agentbox-runtime"]
        agentbox_group = groups["agentbox"]
        runtime_group = groups["agentbox-runtime"]
        ipc_group = groups["agentbox-runtime-ipc"]
        if (
            getattr(agentbox, "pw_uid", None) != expected.agentbox_uid
            or getattr(agentbox, "pw_gid", None) != expected.agentbox_gid
            or getattr(agentbox, "pw_dir", None) != "/var/lib/agentbox"
            or getattr(agentbox, "pw_shell", None) != "/usr/sbin/nologin"
            or getattr(runtime, "pw_uid", None) != expected.runtime_uid
            or getattr(runtime, "pw_gid", None) != getattr(runtime_group, "gr_gid", None)
            or getattr(runtime, "pw_dir", None) != "/home/agentbox-runtime"
            or getattr(runtime, "pw_shell", None) != "/usr/sbin/nologin"
            or getattr(agentbox_group, "gr_gid", None) != expected.agentbox_gid
            or getattr(ipc_group, "gr_gid", None) != expected.ipc_gid
        ):
            raise HostMutationError("pre-existing AgentBox identity does not match its receipt")

    def owner_ids(self, owner: str, group: str) -> tuple[int, int]:
        if not self.real_host:
            owners = {"root": 0, "agentbox": 19001, "agentbox-runtime": 19002}
            groups = {
                "root": 0,
                "agentbox": 19001,
                "agentbox-runtime": 19002,
                "agentbox-runtime-ipc": 19003,
            }
            return owners[owner], groups[group]
        return pwd.getpwnam(owner).pw_uid, grp.getgrnam(group).gr_gid

    def set_owner_mode(self, path: Path, owner: str, group: str, mode: int) -> None:
        path.lstat()
        if path.is_symlink():
            raise HostMutationError("refusing ownership change through a symlink")
        os.chmod(path, mode)
        if self.real_host:
            uid, gid = self.owner_ids(owner, group)
            os.chown(path, uid, gid)

    def port_available(self, host: str, port: int) -> bool:
        if not self.real_host:
            return True
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, port))
            except OSError:
                return False
        return True

    def install_unit_file(self, source: Path, destination: Path) -> None:
        self._atomic_copy(source, destination, 0o644)

    def daemon_reload(self) -> None:
        if self.real_host:
            self._run(("/usr/bin/systemctl", "daemon-reload"))

    def enable_and_start(self) -> None:
        if not self.real_host:
            return
        self._run(("/usr/bin/systemctl", "enable", "--now", "agentbox-helper.socket"))
        self._run(
            (
                "/usr/bin/systemctl",
                "enable",
                "--now",
                "agentbox-runtime.service",
                "agentbox-worker.service",
                "agentbox-api.service",
            )
        )

    def stop_agentbox(self) -> None:
        if self.real_host:
            self._run(
                (
                    "/usr/bin/systemctl",
                    "stop",
                    "agentbox-api.service",
                    "agentbox-worker.service",
                    "agentbox-runtime.service",
                )
            )

    def disable_and_stop(self) -> None:
        if not self.real_host:
            return
        self._run(
            (
                "/usr/bin/systemctl",
                "disable",
                "--now",
                "agentbox-api.service",
                "agentbox-worker.service",
                "agentbox-runtime.service",
                "agentbox-helper.socket",
            )
        )

    def restart_agentbox(self) -> None:
        if self.real_host:
            self._run(
                (
                    "/usr/bin/systemctl",
                    "restart",
                    "agentbox-runtime.service",
                    "agentbox-worker.service",
                    "agentbox-api.service",
                )
            )

    def deployment_ready(self) -> bool:
        if not self.real_host:
            return True
        for unit in (
            "agentbox-api.service",
            "agentbox-worker.service",
            "agentbox-runtime.service",
            "agentbox-helper.socket",
        ):
            try:
                result = subprocess.run(  # noqa: S603 - fixed read-only service check
                    ("/usr/bin/systemctl", "is-active", "--quiet", unit),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                    env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
                )
            except (OSError, subprocess.TimeoutExpired):
                return False
            if result.returncode != 0:
                return False
        for path in (Path("/run/agentbox/runtime.sock"), Path("/run/agentbox/helper.sock")):
            try:
                if not stat.S_ISSOCK(path.lstat().st_mode):
                    return False
            except OSError:
                return False
        return True

    def migrate(self, release: Path, environment_file: Path) -> None:
        if not self.real_host:
            return
        executable = release / "venv/bin/alembic"
        if (
            executable.is_symlink()
            or not executable.is_file()
            or not os.access(executable, os.X_OK)
        ):
            raise HostMutationError("release Alembic executable is unavailable")
        environment: dict[str, str] = {
            "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG": "C.UTF-8",
            "AGENTBOX_DATABASE_URL": "sqlite+pysqlite:////var/lib/agentbox/agentbox.db",
        }
        allowed_environment_keys = {
            "AGENTBOX_ENV",
            "AGENTBOX_TOML_FILE",
            "AGENTBOX_SECRET_KEY",
            "AGENTBOX_STATIC_DIR",
        }
        observed_keys: set[str] = set()
        for line in environment_file.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if (
                separator != "="
                or key not in allowed_environment_keys
                or key in observed_keys
                or re.fullmatch(r"[A-Za-z0-9_./:+,-]+", value) is None
            ):
                raise HostMutationError("AgentBox environment file is invalid")
            environment[key] = value
            observed_keys.add(key)
        if observed_keys != allowed_environment_keys:
            raise HostMutationError("AgentBox environment file is incomplete")
        try:
            result = subprocess.run(  # noqa: S603 - fixed release executable and argv
                (
                    "/usr/sbin/runuser",
                    "--user",
                    "agentbox",
                    "--",
                    str(executable),
                    "-c",
                    str(release / "alembic.ini"),
                    "upgrade",
                    "head",
                ),
                cwd=release,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise HostMutationError("database migration failed") from exc
        if result.returncode != 0:
            raise HostMutationError("database migration failed")

    def prepare_release_environment(self, release: Path) -> None:
        if not self.real_host:
            return
        wheelhouse = release / "wheelhouse"
        wheels = sorted(wheelhouse.glob("agentbox-*.whl"))
        if len(wheels) != 1 or any(path.is_symlink() for path in wheels):
            raise HostMutationError("release must contain exactly one AgentBox wheel")
        venv = release / "venv"
        if venv.exists() or venv.is_symlink():
            executable = venv / "bin/agentbox"
            if executable.is_file() and not executable.is_symlink():
                return
            raise HostMutationError("release Python environment is incomplete")
        self._run(("/usr/bin/python3", "-m", "venv", str(venv)), timeout=180)
        pip = venv / "bin/pip"
        try:
            result = subprocess.run(  # noqa: S603 - verified release wheel and fixed argv
                (
                    str(pip),
                    "install",
                    "--no-index",
                    "--disable-pip-version-check",
                    "--find-links",
                    str(wheelhouse),
                    str(wheels[0]),
                ),
                cwd=release,
                env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=300,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise HostMutationError("release Python environment installation failed") from exc
        if result.returncode != 0:
            raise HostMutationError("release Python environment installation failed")
        self._run((str(venv / "bin/agentbox"), "--version"), timeout=30)

    def install_packages(self, family: PackageFamily, packages: tuple[str, ...]) -> None:
        if not self.real_host or not packages:
            return
        if family is PackageFamily.DNF:
            self._run(
                (
                    "/usr/bin/dnf",
                    "--assumeyes",
                    "--setopt=install_weak_deps=False",
                    "install",
                    *packages,
                ),
                timeout=600,
            )
            return
        if family is PackageFamily.APT:
            self._run(("/usr/bin/apt-get", "update"), timeout=600)
            try:
                result = subprocess.run(  # noqa: S603 - fixed platform package plan
                    (
                        "/usr/bin/apt-get",
                        "--yes",
                        "--no-install-recommends",
                        "install",
                        *packages,
                    ),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=600,
                    check=False,
                    env={
                        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                        "LANG": "C.UTF-8",
                        "DEBIAN_FRONTEND": "noninteractive",
                    },
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise HostMutationError("fixed APT package plan failed") from exc
            if result.returncode != 0:
                raise HostMutationError("fixed APT package plan failed")
            return
        raise HostMutationError("unsupported package family")

    @staticmethod
    def copy_file(source: Path, destination: Path, mode: int) -> None:
        HostOperations._atomic_copy(source, destination, mode)

    @staticmethod
    def _atomic_copy(source: Path, destination: Path, mode: int) -> None:
        if source.is_symlink() or not source.is_file():
            raise HostMutationError("unsafe file copy source")
        parent_descriptor = os.open(
            destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        temporary_name = f".{destination.name}.agentbox-new"
        try:
            try:
                details = os.stat(destination.name, dir_fd=parent_descriptor, follow_symlinks=False)
            except FileNotFoundError:
                details = None
            if details is not None and stat.S_ISLNK(details.st_mode):
                raise HostMutationError("unsafe file copy target")
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                mode,
                dir_fd=parent_descriptor,
            )
            with source.open("rb") as input_stream, os.fdopen(descriptor, "wb") as output:
                shutil.copyfileobj(input_stream, output)
                output.flush()
                os.fsync(output.fileno())
            os.replace(
                temporary_name,
                destination.name,
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
