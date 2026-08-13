"""Version-aware systemd hardening compatibility and review evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class HardeningDecision(StrEnum):
    APPLIED = "applied"
    REQUIRED = "business_required"
    ACCEPTED_LIMITATION = "accepted_compatibility_limitation"


@dataclass(frozen=True)
class HardeningFinding:
    directive: str
    service: str
    current_exposure: str
    fixable: bool
    compatibility_impact: str
    decision: HardeningDecision
    test_evidence: str


@dataclass(frozen=True)
class SystemdCapabilityMatrix:
    version: int
    supported_directives: tuple[str, ...]
    unsupported_directives: tuple[str, ...]

    @property
    def compatible(self) -> bool:
        return not self.unsupported_directives


# Minimum systemd releases are taken from the public systemd.exec and
# systemd.resource-control directive histories.  Unknown security directives
# fail closed instead of being assumed portable.
DIRECTIVE_MINIMUM_VERSION: dict[str, int] = {
    "AmbientCapabilities": 229,
    "CapabilityBoundingSet": 209,
    "IPAddressAllow": 235,
    "IPAddressDeny": 235,
    "LockPersonality": 231,
    "MemoryDenyWriteExecute": 231,
    "NoNewPrivileges": 211,
    "PrivateDevices": 209,
    "PrivateNetwork": 209,
    "PrivateTmp": 186,
    "ProcSubset": 247,
    "ProtectClock": 245,
    "ProtectControlGroups": 232,
    "ProtectHome": 214,
    "ProtectHostname": 242,
    "ProtectKernelLogs": 244,
    "ProtectKernelModules": 232,
    "ProtectKernelTunables": 232,
    "ProtectProc": 247,
    "ProtectSystem": 214,
    "ReadWritePaths": 214,
    "RemoveIPC": 232,
    "RestrictAddressFamilies": 211,
    "RestrictNamespaces": 232,
    "RestrictRealtime": 231,
    "RestrictSUIDSGID": 228,
    "RuntimeMaxSec": 229,
    "SystemCallArchitectures": 209,
    "SystemCallErrorNumber": 209,
    "SystemCallFilter": 187,
}


def unit_security_directives(content: str) -> tuple[str, ...]:
    directives: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "[")) or "=" not in line:
            continue
        directive = line.split("=", 1)[0]
        if directive in DIRECTIVE_MINIMUM_VERSION:
            directives.append(directive)
    return tuple(dict.fromkeys(directives))


def systemd_capabilities(content: str, version: int) -> SystemdCapabilityMatrix:
    if version < 1:
        raise ValueError("systemd version must be positive")
    directives = unit_security_directives(content)
    supported = tuple(
        directive for directive in directives if DIRECTIVE_MINIMUM_VERSION[directive] <= version
    )
    unsupported = tuple(
        directive for directive in directives if DIRECTIVE_MINIMUM_VERSION[directive] > version
    )
    return SystemdCapabilityMatrix(version, supported, unsupported)


def validate_unit_compatibility(content: str, version: int) -> None:
    matrix = systemd_capabilities(content, version)
    if matrix.unsupported_directives:
        joined = ", ".join(matrix.unsupported_directives)
        raise ValueError(f"systemd {version} does not support unit directives: {joined}")


def review_unit_hardening(name: str, content: str) -> tuple[HardeningFinding, ...]:
    """Return the Phase 9 decisions whose compatibility needs explicit review."""
    runtime = name == "agentbox-runtime.service"
    return (
        HardeningFinding(
            directive="SystemCallFilter",
            service=name,
            current_exposure=(
                "broad Runtime syscall surface"
                if runtime
                else (
                    "system-service syscall set"
                    if "SystemCallFilter=@system-service" in content
                    else "unfiltered syscall surface"
                )
            ),
            fixable=not runtime,
            compatibility_impact=(
                "Filtering Runtime can break bubblewrap, tmux, Git, Node/V8, Codex, or Claude"
                if runtime
                else "Validated with unit startup and service-specific tests"
            ),
            decision=(
                HardeningDecision.ACCEPTED_LIMITATION if runtime else HardeningDecision.APPLIED
            ),
            test_evidence=(
                "Runtime adapter/process/namespace fixtures plus OpenCloudOS service probe"
                if runtime
                else "systemd-analyze verify/security and service regression"
            ),
        ),
        HardeningFinding(
            directive="RestrictNamespaces",
            service=name,
            current_exposure="Runtime retains namespace creation" if runtime else "disabled",
            fixable=not runtime,
            compatibility_impact=(
                "Runtime user namespaces are required by bubblewrap-compatible workflows"
                if runtime
                else "No service namespace creation is required"
            ),
            decision=(
                HardeningDecision.ACCEPTED_LIMITATION if runtime else HardeningDecision.APPLIED
            ),
            test_evidence="unit semantic assertions and deployment matrix",
        ),
        HardeningFinding(
            directive="MemoryDenyWriteExecute",
            service=name,
            current_exposure="JIT-compatible executable memory" if runtime else "denied",
            fixable=not runtime,
            compatibility_impact=(
                "Node/V8-backed Runtime tools may require executable memory"
                if runtime
                else "Python service and Helper paths do not require JIT memory"
            ),
            decision=(
                HardeningDecision.ACCEPTED_LIMITATION if runtime else HardeningDecision.APPLIED
            ),
            test_evidence="unit semantic assertions and service regression",
        ),
    )
