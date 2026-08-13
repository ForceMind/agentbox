from __future__ import annotations

from pathlib import Path

import pytest
from agentbox_installer.dependencies import detect_dependencies
from agentbox_installer.layout import InstallLayout
from agentbox_installer.platform import (
    PackageFamily,
    PlatformSupport,
    QualificationLevel,
    detect_platform,
    parse_os_release,
    qualify_platform,
    resolve_packages,
)


@pytest.mark.parametrize(
    ("identifier", "version", "family", "support"),
    [
        ("opencloudos", "9.4", PackageFamily.DNF, PlatformSupport.SUPPORTED),
        ("rocky", "9.5", PackageFamily.DNF, PlatformSupport.PREVIEW),
        ("ubuntu", "22.04", PackageFamily.APT, PlatformSupport.UNSUPPORTED),
        ("ubuntu", "24.04", PackageFamily.APT, PlatformSupport.PREVIEW),
        ("debian", "12", PackageFamily.APT, PlatformSupport.PREVIEW),
    ],
)
def test_platform_matrix(
    tmp_path: Path,
    identifier: str,
    version: str,
    family: PackageFamily,
    support: PlatformSupport,
) -> None:
    os_release = tmp_path / "os-release"
    os_release.write_text(f'ID="{identifier}"\nVERSION_ID="{version}"\n', encoding="utf-8")

    facts = detect_platform(os_release, architecture="x86_64")

    assert facts.package_family is family
    assert facts.support is support


@pytest.mark.parametrize(
    ("identifier", "version", "architecture"),
    [
        ("ubuntu", "20.04", "x86_64"),
        ("fedora", "42", "x86_64"),
        ("opencloudos", "9.4", "aarch64"),
        ("opencloudos", "9.4", "riscv64"),
    ],
)
def test_unsupported_platforms_fail_closed(
    tmp_path: Path, identifier: str, version: str, architecture: str
) -> None:
    os_release = tmp_path / "os-release"
    os_release.write_text(f"ID={identifier}\nVERSION_ID={version}\n", encoding="utf-8")

    assert detect_platform(os_release, architecture=architecture).supported is False


def test_ubuntu_2204_is_fixture_only_until_python_runtime_is_qualified(
    tmp_path: Path,
) -> None:
    os_release = tmp_path / "os-release"
    os_release.write_text('ID="ubuntu"\nVERSION_ID="22.04"\n', encoding="utf-8")

    facts = detect_platform(os_release, architecture="x86_64")

    assert facts.support is PlatformSupport.UNSUPPORTED
    assert facts.package_family is PackageFamily.APT
    assert "Python 3.10" in facts.reason


def test_os_release_parser_never_evaluates_shell() -> None:
    values = parse_os_release('ID="ubuntu"\nEVIL="$(touch /tmp/nope)"\nVERSION_ID="24.04"')

    assert values == {"ID": "ubuntu", "VERSION_ID": "24.04"}


def test_package_mapping_is_typed_and_fixed() -> None:
    assert resolve_packages(PackageFamily.APT, ("python", "git")) == (
        "python3",
        "python3-venv",
        "git",
    )
    with pytest.raises(ValueError, match="unknown logical"):
        resolve_packages(PackageFamily.DNF, ("openssh-server",))


def test_dependency_detection_accepts_only_executables_in_fixed_roots(tmp_path: Path) -> None:
    root = tmp_path / "root"
    binaries = root / "usr/bin"
    binaries.mkdir(parents=True)
    git = binaries / "git"
    git.write_text("#!/bin/sh\n")
    git.chmod(0o755)
    outside = root / "opt/untrusted"
    outside.mkdir(parents=True)
    fake_python = outside / "python3"
    fake_python.write_text("#!/bin/sh\n")
    fake_python.chmod(0o755)
    (binaries / "python3").symlink_to(fake_python)

    status = {item.name: item for item in detect_dependencies(InstallLayout(root))}

    assert status["git"].installed is True
    assert status["python"].installed is False
    assert status["node"].required_for_core is False
    assert status["node"].required_for_runtime is True
    assert "official" in status["codex"].installation_policy


@pytest.mark.parametrize(
    ("identifier", "version", "qualification", "systemd_version"),
    [
        ("opencloudos", "9.4", QualificationLevel.REAL_HOST_VALIDATED, 255),
        ("ubuntu", "22.04", QualificationLevel.UNSUPPORTED, 249),
        ("ubuntu", "24.04", QualificationLevel.CI_VALIDATED, 255),
        ("rocky", "9.5", QualificationLevel.FIXTURE_VALIDATED, 252),
        ("debian", "12", QualificationLevel.FIXTURE_VALIDATED, 252),
    ],
)
def test_platform_qualification_never_promotes_fixture_evidence(
    tmp_path: Path,
    identifier: str,
    version: str,
    qualification: QualificationLevel,
    systemd_version: int,
) -> None:
    os_release = tmp_path / f"{identifier}-os-release"
    os_release.write_text(f"ID={identifier}\nVERSION_ID={version}\n", encoding="utf-8")

    observed = qualify_platform(detect_platform(os_release, architecture="x86_64"))

    assert observed.qualification is qualification
    assert observed.systemd_baseline == systemd_version


def test_runtime_tools_are_optional_without_weakening_core_dependency_evidence(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    (root / "usr/bin").mkdir(parents=True)

    status = {item.name: item for item in detect_dependencies(InstallLayout(root))}

    assert status["tmux"].required_for_core is False
    assert status["tmux"].required_for_runtime is True
    assert status["codex"].required_for_core is False
    assert status["claude"].required_for_core is False
    assert status["node"].required_for_core is False
