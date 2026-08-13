"""Typed Linux platform detection based on ``/etc/os-release``."""

from __future__ import annotations

import platform as platform_module
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class PlatformSupport(StrEnum):
    SUPPORTED = "supported"
    PREVIEW = "preview"
    UNSUPPORTED = "unsupported"


class PackageFamily(StrEnum):
    DNF = "dnf"
    APT = "apt"
    UNKNOWN = "unknown"


class QualificationLevel(StrEnum):
    REAL_HOST_VALIDATED = "real_host_validated"
    CI_VALIDATED = "ci_validated"
    FIXTURE_VALIDATED = "fixture_validated"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class PlatformFacts:
    distribution_id: str
    version_id: str
    architecture: str
    package_family: PackageFamily
    support: PlatformSupport
    reason: str

    @property
    def supported(self) -> bool:
        return self.support != PlatformSupport.UNSUPPORTED


@dataclass(frozen=True)
class PlatformQualification:
    distribution: str
    release: str
    architecture: str
    qualification: QualificationLevel
    package_family: PackageFamily
    systemd_baseline: int
    python_strategy: str
    evidence: tuple[str, ...]
    limitations: tuple[str, ...]


def qualify_platform(facts: PlatformFacts) -> PlatformQualification:
    """Describe actual Phase 9 evidence without promoting fixture coverage."""
    identity = (facts.distribution_id, facts.version_id.split(".", 1)[0])
    if facts.architecture != "x86_64" or not facts.supported:
        systemd_baseline = 249 if facts.distribution_id == "ubuntu" else 0
        return PlatformQualification(
            facts.distribution_id,
            facts.version_id,
            facts.architecture,
            QualificationLevel.UNSUPPORTED,
            facts.package_family,
            systemd_baseline,
            (
                "stock Python 3.10 is below AgentBox >=3.11"
                if facts.distribution_id == "ubuntu" and facts.version_id == "22.04"
                else "no qualified Python/release artifact strategy"
            ),
            ("detection and rejection fixture",),
            (facts.reason,),
        )
    if identity == ("opencloudos", "9"):
        return PlatformQualification(
            facts.distribution_id,
            facts.version_id,
            facts.architecture,
            QualificationLevel.REAL_HOST_VALIDATED,
            facts.package_family,
            255,
            "distribution Python 3.11 and release-local venv",
            ("fixture", "systemd-analyze", "OpenCloudOS 9.4 real host"),
            ("validation is limited to the designated x86_64 host",),
        )
    if identity == ("ubuntu", "24"):
        return PlatformQualification(
            facts.distribution_id,
            facts.version_id,
            facts.architecture,
            QualificationLevel.CI_VALIDATED,
            facts.package_family,
            255,
            "stock Python 3.12 and release-local venv",
            ("GitHub Actions installer fixture", "systemd-analyze offline verification"),
            ("native PID 1 systemd and Runtime tools remain unverified",),
        )
    if identity == ("rocky", "9"):
        systemd_version, python = 252, "typed Python 3.11 package mapping; repository unverified"
    else:
        systemd_version, python = 252, "stock Python 3.11 and release-local venv"
    return PlatformQualification(
        facts.distribution_id,
        facts.version_id,
        facts.architecture,
        QualificationLevel.FIXTURE_VALIDATED,
        facts.package_family,
        systemd_version,
        python,
        ("os-release/package fixture", "filesystem plan", "offline unit verification"),
        ("native install, PID 1 systemd, upgrade, rollback, and Runtime remain unverified",),
    )


_VALUE = re.compile(r"^[A-Za-z0-9._+ -]{0,256}$")


def parse_os_release(content: str) -> dict[str, str]:
    """Parse the small public os-release grammar without evaluating shell."""
    values: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", key):
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
            value = value.replace("\\$", "$").replace('\\"', '"').replace("\\\\", "\\")
        if _VALUE.fullmatch(value):
            values[key] = value
    return values


def normalize_architecture(machine: str) -> str:
    return {"amd64": "x86_64", "arm64": "aarch64"}.get(machine.lower(), machine.lower())


def detect_platform(
    os_release_path: Path = Path("/etc/os-release"), *, architecture: str | None = None
) -> PlatformFacts:
    try:
        values = parse_os_release(os_release_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return PlatformFacts(
            distribution_id="unknown",
            version_id="unknown",
            architecture=normalize_architecture(architecture or platform_module.machine()),
            package_family=PackageFamily.UNKNOWN,
            support=PlatformSupport.UNSUPPORTED,
            reason="/etc/os-release is unavailable or invalid",
        )

    distro = values.get("ID", "unknown").lower()
    version = values.get("VERSION_ID", "unknown")
    arch = normalize_architecture(architecture or platform_module.machine())
    if arch != "x86_64":
        reason = (
            "aarch64 requires a qualified release artifact and Runtime compatibility evidence"
            if arch == "aarch64"
            else f"architecture {arch} is not supported"
        )
        return PlatformFacts(
            distro,
            version,
            arch,
            PackageFamily.UNKNOWN,
            PlatformSupport.UNSUPPORTED,
            reason,
        )

    major = version.split(".", 1)[0]
    if distro == "opencloudos" and major == "9":
        return PlatformFacts(
            distro, version, arch, PackageFamily.DNF, PlatformSupport.SUPPORTED, "validated target"
        )
    if distro == "rocky" and major == "9":
        return PlatformFacts(
            distro,
            version,
            arch,
            PackageFamily.DNF,
            PlatformSupport.PREVIEW,
            "fixture-tested preview",
        )
    if distro == "ubuntu" and version == "22.04":
        return PlatformFacts(
            distro,
            version,
            arch,
            PackageFamily.APT,
            PlatformSupport.UNSUPPORTED,
            "stock Python 3.10 does not satisfy AgentBox Python >=3.11",
        )
    if distro == "ubuntu" and version == "24.04":
        return PlatformFacts(
            distro, version, arch, PackageFamily.APT, PlatformSupport.PREVIEW, "CI target"
        )
    if distro == "debian" and major == "12":
        return PlatformFacts(
            distro,
            version,
            arch,
            PackageFamily.APT,
            PlatformSupport.PREVIEW,
            "fixture-tested preview",
        )
    return PlatformFacts(
        distro,
        version,
        arch,
        PackageFamily.UNKNOWN,
        PlatformSupport.UNSUPPORTED,
        "distribution release has no AgentBox adapter",
    )


LOGICAL_PACKAGES: dict[PackageFamily, dict[str, tuple[str, ...]]] = {
    PackageFamily.DNF: {
        "python": ("python3.11",),
        "python_venv": ("python3.11",),
        "git": ("git",),
        "tmux": ("tmux",),
        "curl": ("curl",),
        "bubblewrap": ("bubblewrap",),
        "sqlite": ("sqlite",),
        "systemd": ("systemd",),
    },
    PackageFamily.APT: {
        "python": ("python3", "python3-venv"),
        "python_venv": ("python3-venv",),
        "git": ("git",),
        "tmux": ("tmux",),
        "curl": ("curl",),
        "bubblewrap": ("bubblewrap",),
        "sqlite": ("sqlite3",),
        "systemd": ("systemd",),
    },
}


def resolve_packages(family: PackageFamily, logical_names: tuple[str, ...]) -> tuple[str, ...]:
    """Resolve fixed logical dependencies; callers cannot supply package names."""
    mapping = LOGICAL_PACKAGES.get(family)
    if mapping is None:
        raise ValueError("unsupported package family")
    packages: list[str] = []
    for logical_name in logical_names:
        if logical_name not in mapping:
            raise ValueError(f"unknown logical dependency: {logical_name}")
        packages.extend(mapping[logical_name])
    return tuple(dict.fromkeys(packages))
