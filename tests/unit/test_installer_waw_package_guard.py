from __future__ import annotations

from pathlib import Path

import pytest
from agentbox_installer import lifecycle
from agentbox_installer.dependencies import DependencyStatus
from agentbox_installer.host import HostOperations
from agentbox_installer.layout import InstallLayout
from agentbox_installer.lifecycle import AgentBoxInstaller, InstallError
from agentbox_installer.platform import detect_platform
from agentbox_installer.waw_manifest_install import WAWManifestInstallError
from agentbox_installer.waw_package_guard import _RAW, WAWPackageStartGuard
from test_installer_waw_manifests import _fixture


def test_package_guard_blocks_starts_and_is_removed_after_failure(tmp_path: Path) -> None:
    issuer, root = _fixture(tmp_path)
    (root / "usr/sbin").mkdir()
    guard = WAWPackageStartGuard(issuer)
    path = root / "usr/sbin/policy-rc.d"

    def install() -> None:
        assert path.read_bytes() == _RAW
        assert path.stat().st_mode & 0o777 == 0o755
        raise RuntimeError("synthetic APT failure")

    with pytest.raises(RuntimeError, match="APT"):
        guard.run(install)
    assert not path.exists()


def test_package_guard_preserves_foreign_policy_even_with_recovery(tmp_path: Path) -> None:
    issuer, root = _fixture(tmp_path)
    (root / "usr/sbin").mkdir()
    path = root / "usr/sbin/policy-rc.d"
    path.write_bytes(b"#!/bin/sh\n# operator policy\nexit 0\n")
    path.chmod(0o755)
    before = path.read_bytes()

    def forbidden() -> None:
        raise AssertionError("foreign policy must reject before APT")

    with pytest.raises(WAWManifestInstallError):
        WAWPackageStartGuard(issuer).run(forbidden, recover=True)
    assert path.read_bytes() == before


def test_matching_guard_requires_explicit_recovery(tmp_path: Path) -> None:
    issuer, root = _fixture(tmp_path)
    (root / "usr/sbin").mkdir()
    path = root / "usr/sbin/policy-rc.d"
    path.write_bytes(_RAW)
    path.chmod(0o755)
    guard = WAWPackageStartGuard(issuer)
    with pytest.raises(WAWManifestInstallError, match="recover"):
        guard.run(lambda: None)
    guard.run(lambda: None, recover=True)
    assert not path.exists()


def test_dependency_recovery_cleans_guard_after_packages_are_already_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _issuer, root = _fixture(tmp_path)
    (root / "usr/sbin").mkdir()
    (root / "etc").mkdir()
    (root / "etc/os-release").write_text('ID="ubuntu"\nVERSION_ID="24.04"\n')
    path = root / "usr/sbin/policy-rc.d"
    path.write_bytes(_RAW)
    path.chmod(0o755)
    monkeypatch.setattr(
        lifecycle, "detect_platform", lambda source: detect_platform(source, architecture="x86_64")
    )
    installer = AgentBoxInstaller(InstallLayout(root), HostOperations(real_host=False))
    monkeypatch.setattr(installer, "installation_state", lambda: "installed")
    monkeypatch.setattr(installer, "current_version", lambda: "0.3.0rc30")
    monkeypatch.setattr(installer.host, "systemd_version", lambda: 255)
    monkeypatch.setattr(
        lifecycle,
        "detect_dependencies",
        lambda _layout: tuple(
            DependencyStatus(name, False, False, True, None, "fixture")
            for name in ("nginx", "certbot")
        ),
    )
    monkeypatch.setattr(
        installer.host,
        "install_packages",
        lambda *_args: pytest.fail("APT must not rerun after dependencies completed"),
    )

    with pytest.raises(WAWManifestInstallError, match="recover"):
        installer.install_waw_dependencies()
    assert path.read_bytes() == _RAW

    result = installer.install_waw_dependencies(recover=True)
    assert result["packages"] == ()
    assert result["status"] == "installed"
    assert not path.exists()


def test_dependency_noop_preserves_foreign_policy_but_recovery_rejects_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _issuer, root = _fixture(tmp_path)
    (root / "usr/sbin").mkdir()
    (root / "etc").mkdir()
    (root / "etc/os-release").write_text('ID="ubuntu"\nVERSION_ID="24.04"\n')
    path = root / "usr/sbin/policy-rc.d"
    foreign = b"#!/bin/sh\n# operator policy\nexit 0\n"
    path.write_bytes(foreign)
    path.chmod(0o755)
    monkeypatch.setattr(
        lifecycle, "detect_platform", lambda source: detect_platform(source, architecture="x86_64")
    )
    installer = AgentBoxInstaller(InstallLayout(root), HostOperations(real_host=False))
    monkeypatch.setattr(installer, "installation_state", lambda: "installed")
    monkeypatch.setattr(installer, "current_version", lambda: "0.3.0rc30")
    monkeypatch.setattr(installer.host, "systemd_version", lambda: 255)
    monkeypatch.setattr(
        lifecycle,
        "detect_dependencies",
        lambda _layout: tuple(
            DependencyStatus(name, False, False, True, None, "fixture")
            for name in ("nginx", "certbot")
        ),
    )

    result = installer.install_waw_dependencies()
    assert result["packages"] == ()
    assert path.read_bytes() == foreign

    with pytest.raises(WAWManifestInstallError, match="foreign or unsafe"):
        installer.install_waw_dependencies(recover=True)
    assert path.read_bytes() == foreign


def test_dependency_plan_apply_and_installed_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _issuer, root = _fixture(tmp_path)
    (root / "usr/sbin").mkdir()
    (root / "etc").mkdir()
    (root / "etc/os-release").write_text('ID="ubuntu"\nVERSION_ID="24.04"\n')
    monkeypatch.setattr(
        lifecycle, "detect_platform", lambda path: detect_platform(path, architecture="x86_64")
    )
    installer = AgentBoxInstaller(InstallLayout(root), HostOperations(real_host=False))
    monkeypatch.setattr(installer, "installation_state", lambda: "installed")
    monkeypatch.setattr(installer, "current_version", lambda: "0.3.0rc30")
    monkeypatch.setattr(installer.host, "systemd_version", lambda: 255)
    installed = False

    def detect(_layout: InstallLayout) -> tuple[DependencyStatus, ...]:
        return tuple(
            DependencyStatus(name, False, False, installed, None, "fixture")
            for name in ("nginx", "certbot")
        )

    calls: list[tuple[str, ...]] = []

    def install(_family: object, packages: tuple[str, ...]) -> None:
        nonlocal installed
        assert (root / "usr/sbin/policy-rc.d").read_bytes() == _RAW
        calls.append(packages)
        installed = True

    monkeypatch.setattr(lifecycle, "detect_dependencies", detect)
    monkeypatch.setattr(installer.host, "install_packages", install)
    result = installer.install_waw_dependencies(plan=True)
    assert result["packages"] == ("nginx", "certbot") and calls == []
    installer.install_waw_dependencies()
    assert calls == [("nginx", "certbot")]
    assert not (root / "usr/sbin/policy-rc.d").exists()
    installer.install_waw_dependencies()
    assert len(calls) == 1
    monkeypatch.setattr(installer.host, "systemd_version", lambda: 249)
    with pytest.raises(InstallError, match="255"):
        installer.install_waw_dependencies(plan=True)
