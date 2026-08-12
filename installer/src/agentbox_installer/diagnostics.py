"""Read-only production deployment diagnostics with no secret output."""

from __future__ import annotations

import grp
import pwd
import socket
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agentbox_installer.layout import DIRECTORIES, InstallLayout
from agentbox_installer.lifecycle import UNIT_NAMES
from agentbox_installer.platform import detect_platform


@dataclass(frozen=True)
class Check:
    state: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"state": self.state, "detail": self.detail}


class DeploymentDoctor:
    def __init__(self, layout: InstallLayout | None = None) -> None:
        self.layout = layout or InstallLayout()

    def inspect(self) -> dict[str, object]:
        return {
            "platform": self._platform().to_dict(),
            "identities": self._identities().to_dict(),
            "directories": self._directories().to_dict(),
            "units": self._units().to_dict(),
            "services": self._services(),
            "runtime_socket": self._socket("/run/agentbox/runtime.sock", 0o660).to_dict(),
            "helper_socket": self._socket("/run/agentbox/helper.sock", 0o660).to_dict(),
            "project_root": self._directory("/srv/agentbox/projects").to_dict(),
            "api_bind": self._api_listener().to_dict(),
        }

    def _platform(self) -> Check:
        facts = detect_platform(self.layout.map("/etc/os-release"))
        return Check(
            "ready" if facts.supported else "unsupported",
            (
                f"{facts.distribution_id} {facts.version_id} "
                f"{facts.architecture} ({facts.support.value})"
            ),
        )

    def _identities(self) -> Check:
        if not self.layout.is_real_host:
            return Check("unknown", "identity lookup is unavailable in fixture root")
        missing: list[str] = []
        for name in ("agentbox", "agentbox-runtime"):
            try:
                pwd.getpwnam(name)
            except KeyError:
                missing.append(name)
        for name in ("agentbox", "agentbox-runtime", "agentbox-runtime-ipc"):
            try:
                grp.getgrnam(name)
            except KeyError:
                missing.append(name)
        return Check(
            "ready" if not missing else "not_ready",
            ", ".join(missing) or "present",
        )

    def _directories(self) -> Check:
        failures: list[str] = []
        for item in DIRECTORIES:
            target = self.layout.map(item.path)
            if target.is_symlink() or not target.is_dir():
                failures.append(item.path)
                continue
            if target.stat().st_mode & 0o7777 != item.mode:
                failures.append(item.path)
                continue
            if self.layout.is_real_host:
                details = target.stat()
                try:
                    expected_uid = pwd.getpwnam(item.owner).pw_uid
                    expected_gid = grp.getgrnam(item.group).gr_gid
                except KeyError:
                    failures.append(item.path)
                    continue
                if (details.st_uid, details.st_gid) != (expected_uid, expected_gid):
                    failures.append(item.path)
        return Check(
            "ready" if not failures else "not_ready",
            "all managed modes/owners match" if not failures else ", ".join(failures),
        )

    def _directory(self, path: str) -> Check:
        target = self.layout.map(path)
        if target.is_symlink() or not target.is_dir():
            return Check("not_ready", "missing or unsafe")
        return Check("ready", "present")

    def _units(self) -> Check:
        missing = [
            name
            for name in UNIT_NAMES
            if not self.layout.map(f"/etc/systemd/system/{name}").is_file()
            or self.layout.map(f"/etc/systemd/system/{name}").is_symlink()
        ]
        return Check("ready" if not missing else "not_ready", ", ".join(missing) or "installed")

    def _services(self) -> dict[str, str]:
        if not self.layout.is_real_host:
            return {name: "unknown" for name in UNIT_NAMES}
        return {name: self._service_state(name) for name in UNIT_NAMES}

    @staticmethod
    def _service_state(name: str) -> str:
        try:
            result = subprocess.run(  # noqa: S603 - fixed read-only systemd query
                ("/usr/bin/systemctl", "is-active", name),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
            )
        except (OSError, subprocess.TimeoutExpired):
            return "unknown"
        value = result.stdout.strip()
        return (
            value
            if value in {"active", "inactive", "failed", "activating", "deactivating"}
            else "unknown"
        )

    def _socket(self, path: str, expected_mode: int) -> Check:
        target = self.layout.map(path)
        try:
            details = target.lstat()
        except OSError:
            return Check("not_ready", "unavailable")
        if not stat.S_ISSOCK(details.st_mode) or details.st_mode & 0o777 != expected_mode:
            return Check("not_ready", "type or mode mismatch")
        return Check("ready", f"mode {expected_mode:04o}")

    def _api_listener(self) -> Check:
        if not self.layout.is_real_host:
            return Check("unknown", "listener inspection unavailable in fixture root")
        listeners = _proc_listeners(8787)
        if not listeners:
            return Check("not_ready", "port 8787 is not listening")
        if listeners != {"127.0.0.1", "::1"} and listeners != {"127.0.0.1"}:
            return Check("not_ready", "port 8787 has a non-loopback listener")
        return Check("ready", ",".join(sorted(listeners)))


def _proc_listeners(port: int) -> set[str]:
    values: set[str] = set()
    for path, family in (
        (Path("/proc/net/tcp"), socket.AF_INET),
        (Path("/proc/net/tcp6"), socket.AF_INET6),
    ):
        try:
            lines = path.read_text(encoding="ascii").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 4 or fields[3] != "0A":
                continue
            raw_address, raw_port = fields[1].split(":")
            if int(raw_port, 16) != port:
                continue
            packed = bytes.fromhex(raw_address)
            if family == socket.AF_INET:
                values.add(socket.inet_ntop(family, packed[::-1]))
            else:
                words = b"".join(packed[index : index + 4][::-1] for index in range(0, 16, 4))
                values.add(socket.inet_ntop(family, words))
    return values
