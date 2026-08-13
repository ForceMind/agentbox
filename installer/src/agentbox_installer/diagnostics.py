"""Read-only production deployment diagnostics with no secret output."""

from __future__ import annotations

import grp
import json
import os
import pwd
import re
import socket
import stat
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from agentbox_installer.layout import DIRECTORIES, InstallLayout
from agentbox_installer.lifecycle import UNIT_NAMES
from agentbox_installer.platform import QualificationLevel, detect_platform, qualify_platform


@dataclass(frozen=True)
class Check:
    state: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"state": self.state, "detail": self.detail}


class DiagnosticSeverity(StrEnum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class DiagnosticFinding:
    code: str
    category: str
    severity: DiagnosticSeverity
    summary: str
    details: str
    remediation_id: str | None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "code": self.code,
            "category": self.category,
            "severity": self.severity.value,
            "summary": self.summary,
            "details": self.details,
            "remediation_id": self.remediation_id,
        }


class DeploymentDoctor:
    def __init__(self, layout: InstallLayout | None = None) -> None:
        self.layout = layout or InstallLayout()

    def inspect(self) -> dict[str, object]:
        result: dict[str, object] = {
            "platform": self._platform().to_dict(),
            "identities": self._identities().to_dict(),
            "directories": self._directories().to_dict(),
            "units": self._units().to_dict(),
            "services": self._services(),
            "runtime_socket": self._socket("/run/agentbox/runtime.sock", 0o660).to_dict(),
            "helper_socket": self._socket("/run/agentbox/helper.sock", 0o660).to_dict(),
            "project_root": self._directory("/srv/agentbox/projects").to_dict(),
            "api_bind": self._api_listener().to_dict(),
            "disk": self._disk_usage(),
        }
        findings = self.findings(result)
        result["schema_version"] = 1
        result["overall"] = _overall(findings).value
        result["findings"] = [finding.to_dict() for finding in findings]
        return result

    def findings(self, observed: dict[str, object] | None = None) -> tuple[DiagnosticFinding, ...]:
        values = observed or {
            "platform": self._platform().to_dict(),
            "identities": self._identities().to_dict(),
            "directories": self._directories().to_dict(),
            "units": self._units().to_dict(),
            "runtime_socket": self._socket("/run/agentbox/runtime.sock", 0o660).to_dict(),
            "helper_socket": self._socket("/run/agentbox/helper.sock", 0o660).to_dict(),
            "project_root": self._directory("/srv/agentbox/projects").to_dict(),
            "api_bind": self._api_listener().to_dict(),
        }
        specifications = (
            (
                "PLATFORM_QUALIFICATION",
                "platform",
                "platform",
                "Platform qualification",
                "Review docs/PLATFORM_SUPPORT.md before installation",
                "platform-support",
            ),
            (
                "PROCESS_IDENTITIES",
                "identity",
                "identities",
                "System identities",
                "Verify the AgentBox installation receipt and service accounts",
                "identity-repair",
            ),
            (
                "MANAGED_DIRECTORY_PERMISSIONS",
                "filesystem",
                "directories",
                "Managed directory ownership and modes",
                "Compare ownership and modes with docs/DEPLOYMENT.md",
                "directory-permissions",
            ),
            (
                "SYSTEMD_UNITS",
                "systemd",
                "units",
                "AgentBox systemd units",
                "Reinstall only from a verified AgentBox artifact",
                "unit-repair",
            ),
            (
                "RUNTIME_SOCKET",
                "ipc",
                "runtime_socket",
                "Runtime socket boundary",
                "Check agentbox-runtime.service and /run/agentbox ownership",
                "runtime-socket",
            ),
            (
                "HELPER_SOCKET",
                "ipc",
                "helper_socket",
                "Helper socket boundary",
                "Check agentbox-helper.socket and peer identity policy",
                "helper-socket",
            ),
            (
                "PROJECT_ROOT",
                "filesystem",
                "project_root",
                "Project root",
                "Expected a private agentbox-runtime-owned directory",
                "project-root",
            ),
            (
                "API_LOOPBACK_BIND",
                "network",
                "api_bind",
                "API listener",
                "Restore the configured 127.0.0.1:8787 listener",
                "loopback-bind",
            ),
        )
        findings: list[DiagnosticFinding] = []
        for code, category, key, summary, remediation, remediation_id in specifications:
            raw = values.get(key)
            state = raw.get("state") if isinstance(raw, dict) else "unknown"
            detail = raw.get("detail") if isinstance(raw, dict) else "unavailable"
            safe_details = str(detail)[:384]
            if state != "ready":
                safe_details = f"{safe_details}. {remediation}"[:512]
            findings.append(
                DiagnosticFinding(
                    code,
                    category,
                    _severity(str(state)),
                    summary,
                    safe_details,
                    None if state == "ready" else remediation_id,
                )
            )
        return tuple(findings)

    def _platform(self) -> Check:
        facts = detect_platform(self.layout.map("/etc/os-release"))
        qualification = qualify_platform(facts)
        return Check(
            (
                "ready"
                if qualification.qualification is QualificationLevel.REAL_HOST_VALIDATED
                else (
                    "warning"
                    if qualification.qualification
                    in {QualificationLevel.CI_VALIDATED, QualificationLevel.FIXTURE_VALIDATED}
                    else "unsupported"
                )
            ),
            (
                f"{facts.distribution_id} {facts.version_id} "
                f"{facts.architecture} ({qualification.qualification.value})"
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

    def _disk_usage(self) -> dict[str, dict[str, int | str]]:
        result: dict[str, dict[str, int | str]] = {}
        for name, path in (
            ("state", "/var/lib/agentbox"),
            ("releases", "/opt/agentbox"),
            ("projects", "/srv/agentbox/projects"),
        ):
            target = self.layout.map(path)
            try:
                usage = os.statvfs(target)
            except OSError:
                result[name] = {"state": "unknown", "free_bytes": 0}
                continue
            result[name] = {
                "state": "ready",
                "free_bytes": int(usage.f_bavail * usage.f_frsize),
            }
        return result


def _severity(state: str) -> DiagnosticSeverity:
    return {
        "ready": DiagnosticSeverity.OK,
        "warning": DiagnosticSeverity.WARN,
        "not_ready": DiagnosticSeverity.FAIL,
        "unsupported": DiagnosticSeverity.FAIL,
    }.get(state, DiagnosticSeverity.UNKNOWN)


def _overall(findings: tuple[DiagnosticFinding, ...]) -> DiagnosticSeverity:
    severities = {finding.severity for finding in findings}
    for value in (
        DiagnosticSeverity.FAIL,
        DiagnosticSeverity.WARN,
        DiagnosticSeverity.UNKNOWN,
    ):
        if value in severities:
            return value
    return DiagnosticSeverity.OK


_SENSITIVE_KEY = re.compile(
    r"(?:password|secret|token|authorization|cookie|csrf|pair.?code|pane.?output)", re.I
)
_SENSITIVE_VALUE = re.compile(
    r"(?:Bearer\s+[A-Za-z0-9._~-]+|gh[pousr]_[A-Za-z0-9]{16,}|"
    r"https?://[^\s/:]+:[^\s/@]+@|(?:SECRET|TOKEN|PASSWORD|API_KEY)=\S+)",
    re.I,
)


def validate_diagnostic_payload(value: object) -> None:
    """Reject known secret-shaped keys/values before a report is written."""
    if isinstance(value, dict):
        for key, nested in value.items():
            if _SENSITIVE_KEY.search(str(key)):
                raise ValueError("diagnostic payload contains a forbidden field")
            validate_diagnostic_payload(nested)
        return
    if isinstance(value, list | tuple):
        for nested in value:
            validate_diagnostic_payload(nested)
        return
    if isinstance(value, str) and _SENSITIVE_VALUE.search(value):
        raise ValueError("diagnostic payload contains secret-shaped content")


def export_diagnostics(output: Path, payload: dict[str, Any]) -> None:
    """Create one restrictive, non-overwriting sanitized JSON report."""
    validate_diagnostic_payload(payload)
    encoded = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if len(encoded) > 1024 * 1024:
        raise ValueError("diagnostic payload exceeds its size limit")
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


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
