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
from agentbox_installer.waw_package_guard import _RAW, WAWPackageStartGuard, _guard_raw
from test_installer_waw_manifests import _fixture


def test_package_guard_failure_keeps_armed_recovery_intent(tmp_path: Path) -> None:
    issuer, root = _fixture(tmp_path)
    (root / "usr/sbin").mkdir()
    guard = WAWPackageStartGuard(issuer)
    path = root / "usr/sbin/policy-rc.d"
    dependencies = ("certbot",)
    preparing = _guard_raw(dependencies, "preparing")
    armed = _guard_raw(dependencies, "armed")
    prepared: list[tuple[str, ...]] = []
    restored: list[tuple[str, ...]] = []

    def prepare(names: tuple[str, ...]) -> None:
        assert path.read_bytes() == preparing
        prepared.append(names)

    def install() -> None:
        assert path.read_bytes() == armed
        assert path.stat().st_mode & 0o777 == 0o755
        raise RuntimeError("synthetic APT failure")

    with pytest.raises(RuntimeError, match="APT"):
        guard.run(
            install,
            dependencies=dependencies,
            prepare=prepare,
            restore=restored.append,
        )
    assert prepared == [dependencies]
    assert path.read_bytes() == armed

    with pytest.raises(WAWManifestInstallError, match="recover"):
        guard.recover_interrupted()
    guard.recover_interrupted(recover=True, restore=restored.append)
    assert restored == [dependencies]
    assert not path.exists()


def test_package_guard_prepare_failure_removes_preparing_guard(tmp_path: Path) -> None:
    issuer, root = _fixture(tmp_path)
    (root / "usr/sbin").mkdir()
    path = root / "usr/sbin/policy-rc.d"

    def prepare(_dependencies: tuple[str, ...]) -> None:
        assert path.read_bytes() == _guard_raw(("certbot",), "preparing")
        raise RuntimeError("preflight failed")

    with pytest.raises(RuntimeError, match="preflight"):
        WAWPackageStartGuard(issuer).run(
            lambda: pytest.fail("APT must not start"),
            dependencies=("certbot",),
            prepare=prepare,
            restore=lambda _dependencies: pytest.fail("recovery must not run"),
        )
    assert not path.exists()


def test_package_guard_preserves_foreign_policy_even_with_recovery(
    tmp_path: Path,
) -> None:
    issuer, root = _fixture(tmp_path)
    (root / "usr/sbin").mkdir()
    path = root / "usr/sbin/policy-rc.d"
    path.write_bytes(b"#!/bin/sh\n# operator policy\nexit 0\n")
    path.chmod(0o755)
    before = path.read_bytes()

    with pytest.raises(WAWManifestInstallError, match="foreign or unsafe"):
        WAWPackageStartGuard(issuer).run(
            lambda: pytest.fail("foreign policy must reject before APT"),
            dependencies=("certbot",),
            prepare=lambda _dependencies: pytest.fail("preflight must not run"),
            restore=lambda _dependencies: pytest.fail("recovery must not run"),
            recover=True,
        )
    assert path.read_bytes() == before


def test_legacy_matching_guard_requires_explicit_recovery(tmp_path: Path) -> None:
    issuer, root = _fixture(tmp_path)
    (root / "usr/sbin").mkdir()
    path = root / "usr/sbin/policy-rc.d"
    path.write_bytes(_RAW)
    path.chmod(0o755)
    guard = WAWPackageStartGuard(issuer)

    with pytest.raises(WAWManifestInstallError, match="recover"):
        guard.recover_interrupted()
    assert guard.recover_interrupted(recover=True) == ()
    assert not path.exists()


def _dependency_installer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[AgentBoxInstaller, Path]:
    _issuer, root = _fixture(tmp_path)
    (root / "usr/sbin").mkdir()
    (root / "etc").mkdir()
    (root / "etc/os-release").write_text('ID="ubuntu"\nVERSION_ID="24.04"\n')
    monkeypatch.setattr(
        lifecycle,
        "detect_platform",
        lambda source: detect_platform(source, architecture="x86_64"),
    )
    installer = AgentBoxInstaller(InstallLayout(root), HostOperations(real_host=False))
    monkeypatch.setattr(installer, "installation_state", lambda: "installed")
    monkeypatch.setattr(installer, "current_version", lambda: "0.3.0rc30")
    monkeypatch.setattr(installer.host, "systemd_version", lambda: 255)
    return installer, root


def test_dependency_recovery_restores_recorded_units_after_packages_are_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer, root = _dependency_installer(tmp_path, monkeypatch)
    path = root / "usr/sbin/policy-rc.d"
    dependencies = ("certbot", "nginx")
    path.write_bytes(_guard_raw(dependencies, "armed"))
    path.chmod(0o755)
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
    restored: list[tuple[str, ...]] = []
    monkeypatch.setattr(installer.host, "quiesce_waw_dependency_units", restored.append)

    with pytest.raises(WAWManifestInstallError, match="recover"):
        installer.install_waw_dependencies()
    assert path.read_bytes() == _guard_raw(dependencies, "armed")
    assert restored == []

    result = installer.install_waw_dependencies(recover=True)
    assert result["packages"] == ()
    assert result["status"] == "installed"
    assert restored == [dependencies]
    assert not path.exists()


def test_preparing_dependency_guard_recovery_does_not_restore_units(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer, root = _dependency_installer(tmp_path, monkeypatch)
    path = root / "usr/sbin/policy-rc.d"
    dependencies = ("certbot",)
    path.write_bytes(_guard_raw(dependencies, "preparing"))
    path.chmod(0o755)
    monkeypatch.setattr(
        lifecycle,
        "detect_dependencies",
        lambda _layout: (DependencyStatus("certbot", False, False, True, None, "fixture"),),
    )
    monkeypatch.setattr(
        installer.host,
        "quiesce_waw_dependency_units",
        lambda _dependencies: pytest.fail("preparing recovery must not mutate units"),
    )

    installer.install_waw_dependencies(recover=True)
    assert not path.exists()


def test_dependency_noop_preserves_foreign_policy_but_recovery_rejects_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer, root = _dependency_installer(tmp_path, monkeypatch)
    path = root / "usr/sbin/policy-rc.d"
    foreign = b"#!/bin/sh\n# operator policy\nexit 0\n"
    path.write_bytes(foreign)
    path.chmod(0o755)
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


def test_dependency_plan_apply_quiesces_only_recorded_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer, root = _dependency_installer(tmp_path, monkeypatch)
    installed = False

    def detect(_layout: InstallLayout) -> tuple[DependencyStatus, ...]:
        return tuple(
            DependencyStatus(name, False, False, installed, None, "fixture")
            for name in ("nginx", "certbot")
        )

    calls: list[tuple[str, ...]] = []
    prepared: list[tuple[str, ...]] = []
    quiesced: list[tuple[str, ...]] = []

    def install(_family: object, packages: tuple[str, ...]) -> None:
        nonlocal installed
        assert (root / "usr/sbin/policy-rc.d").read_bytes() == _guard_raw(
            ("certbot", "nginx"), "armed"
        )
        calls.append(packages)
        installed = True

    monkeypatch.setattr(lifecycle, "detect_dependencies", detect)
    monkeypatch.setattr(installer.host, "install_packages", install)
    monkeypatch.setattr(installer.host, "require_waw_dependency_units_absent", prepared.append)
    monkeypatch.setattr(installer.host, "quiesce_waw_dependency_units", quiesced.append)

    result = installer.install_waw_dependencies(plan=True)
    assert result["packages"] == ("nginx", "certbot") and calls == []

    installer.install_waw_dependencies()
    assert calls == [("nginx", "certbot")]
    assert prepared == [("certbot", "nginx")]
    assert quiesced == [("certbot", "nginx")]
    assert not (root / "usr/sbin/policy-rc.d").exists()

    installer.install_waw_dependencies()
    assert len(calls) == 1
    monkeypatch.setattr(installer.host, "systemd_version", lambda: 249)
    with pytest.raises(InstallError, match="255"):
        installer.install_waw_dependencies(plan=True)
