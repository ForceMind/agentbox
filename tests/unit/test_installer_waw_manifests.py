from __future__ import annotations

import os
import struct
from pathlib import Path
from typing import Any

import pytest
from agentbox_installer.waw_manifest_install import WAWManifestInstallError, WAWManifestIssuer
from agentbox_runtime.waw_host_manifest import (
    WAW_PUBLIC_MANIFEST_FILENAMES_V2,
    load_verified_canonical_waw_manifest_bundle_v2,
)
from agentbox_runtime.waw_manifest_codecs import RUNTIME_NAMESPACE_BINDING_V1


def test_fixed_policy_plan_is_read_only_and_preparation_is_idempotent(tmp_path: Path) -> None:
    issuer, root = _fixture(tmp_path)
    (root / "etc").mkdir(mode=0o755)
    issuer.publish(issuer.observe(), "a" * 64)
    before = {str(path.relative_to(root)) for path in root.rglob("*")}
    targets = issuer.prepare_fixed_policies(plan=True)
    assert before == {str(path.relative_to(root)) for path in root.rglob("*")}
    assert issuer.prepare_fixed_policies() == targets
    inodes = [(root / target.lstrip("/")).stat().st_ino for target in targets]
    assert issuer.prepare_fixed_policies() == targets
    assert inodes == [(root / target.lstrip("/")).stat().st_ino for target in targets]
    for target, source in zip(
        targets,
        ("claude-managed-policy.v1.json", "codex-requirements.toml", "codex-managed-config.toml"),
        strict=True,
    ):
        path = root / target.lstrip("/")
        assert path.read_bytes() == (root / "usr/share/agentbox/waw" / source).read_bytes()
        assert path.stat().st_mode & 0o777 == 0o444


@pytest.mark.parametrize("kind", ["different", "prefix", "symlink"])
def test_fixed_policy_recovery_rejects_unrelated_or_linked_targets(
    tmp_path: Path, kind: str
) -> None:
    issuer, root = _fixture(tmp_path)
    directory = root / "etc/codex"
    directory.mkdir(parents=True, mode=0o755)
    issuer.publish(issuer.observe(), "a" * 64)
    target = directory / "requirements.toml"
    source = root / "usr/share/agentbox/waw/codex-requirements.toml"
    if kind == "symlink":
        target.symlink_to(source)
    else:
        target.write_bytes(source.read_bytes()[:8] if kind == "prefix" else b"different policy")
        target.chmod(0o444)
    with pytest.raises((WAWManifestInstallError, OSError)):
        issuer.prepare_fixed_policies()
    assert not (root / "etc/claude-code").exists()
    if kind == "prefix":
        issuer.prepare_fixed_policies(recover=True)
        assert target.read_bytes() == source.read_bytes()
        assert target.stat().st_mode & 0o777 == 0o444
    else:
        with pytest.raises((WAWManifestInstallError, OSError)):
            issuer.prepare_fixed_policies(recover=True)
        assert not (root / "etc/claude-code").exists()


@pytest.mark.parametrize("plan", [False, True])
def test_policy_lifecycle_keeps_profiles_disabled_and_never_initializes_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, plan: bool
) -> None:
    from agentbox_installer.cli import create_parser
    from agentbox_installer.host import HostOperations
    from agentbox_installer.layout import InstallLayout
    from agentbox_installer.lifecycle import AgentBoxInstaller

    issuer, root = _fixture(tmp_path)
    issuer.publish(issuer.observe(), "a" * 64)
    profiles = {
        "etc/agentbox/waw-api-profile.v1.json": (
            b'{"mode":"disabled","schema_version":"agentbox-waw-api-profile.v1"}\n'
        ),
        "var/lib/agentbox-waw/runtime-profile.v1.json": (
            b'{"mode":"disabled","schema_version":"agentbox-waw-runtime-profile.v1"}\n'
        ),
    }
    for name, raw in profiles.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o750)
        path.write_bytes(raw)
        path.chmod(0o440)
    (root / "etc").chmod(0o755)
    host = HostOperations(real_host=False)
    installer = AgentBoxInstaller(InstallLayout(root), host)
    monkeypatch.setattr(installer, "installation_state", lambda: "installed")
    monkeypatch.setattr(installer, "current_version", lambda: "0.3.0rc30")
    calls: list[str] = []
    monkeypatch.setattr(host, "require_waw_policy_quiescence", lambda: calls.append("quiescent"))

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("policy preparation must not initialize keys or start services")

    monkeypatch.setattr(host, "initialize_waw_runtime_key", forbidden)
    monkeypatch.setattr(host, "enable_and_start", forbidden)
    before = {str(path.relative_to(root)) for path in root.rglob("*")}
    result = installer.prepare_waw_policies(plan=plan)
    assert result["profiles"] == "disabled" and result["services_started"] is False
    assert calls == ([] if plan else ["quiescent"])
    assert all((root / name).read_bytes() == raw for name, raw in profiles.items())
    if plan:
        assert before == {str(path.relative_to(root)) for path in root.rglob("*")}
    args = create_parser().parse_args(["prepare-waw-policies", "--plan", "--recover", "--json"])
    assert args.plan and args.recover and args.json


def _fixture(tmp_path: Path) -> tuple[WAWManifestIssuer, Path]:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    for name in (
        "srv/agentbox/projects",
        "var/lib/agentbox-waw",
        "usr/bin",
        "usr/local/bin",
        "usr/share",
        "opt/agentbox/releases/0.3.0rc30/libexec",
    ):
        path = root / name
        path.mkdir(parents=True, exist_ok=True)
        for parent in (path, *path.parents):
            if parent == root:
                break
            parent.chmod(0o755)
    (root / "var/lib/agentbox-waw").chmod(0o750)
    header = bytearray(128)
    header[:7] = b"\x7fELF\x02\x01\x01"
    header[18:20] = b"\x3e\x00"
    struct.pack_into("<HHI", header, 16, 3, 62, 1)
    struct.pack_into("<H", header, 52, 64)
    for name in (
        "usr/bin/false",
        "usr/bin/tmux",
        "usr/local/bin/claude",
        "usr/local/bin/codex",
        "opt/agentbox/releases/0.3.0rc30/libexec/agentbox-waw-pane-bootstrap",
        "opt/agentbox/releases/0.3.0rc30/libexec/agentbox-waw-bridge",
        "opt/agentbox/releases/0.3.0rc30/libexec/agentbox-waw-attach-supervisor",
    ):
        path = root / name
        path.write_bytes(header)
        path.chmod(0o755)
    source = (
        Path(__file__).resolve().parents[2]
        / "packages/agentbox-runtime/src/agentbox_runtime/assets/waw-inert"
    )
    for name in (
        "tmux.conf",
        "sandbox-policies.v1.json",
        "claude/managed-settings.json",
        "codex/requirements.toml",
        "codex/managed_config.toml",
    ):
        path = root / "opt/agentbox/releases/0.3.0rc30/waw/templates" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((source / name).read_bytes())
        path.chmod(0o644)
    issuer = WAWManifestIssuer(
        root,
        "0.3.0rc30",
        owner_uid=os.geteuid(),
        root_gid=os.getegid(),
        runtime_uid=os.geteuid(),
        runtime_gid=os.getegid(),
    )
    return issuer, root


def _load(root: Path) -> Any:
    return load_verified_canonical_waw_manifest_bundle_v2(
        root / "var/lib/agentbox-waw/runtime-host-installation.v2.json",
        root / "usr/share/agentbox/waw",
        expected_runtime_uid=os.geteuid(),
        expected_runtime_gid=os.getegid(),
        expected_public_uid=os.geteuid(),
        expected_public_gid=os.getegid(),
        runtime_trusted_root=root,
    )


def test_installed_resource_observations_publish_complete_cross_verified_bundle(
    tmp_path: Path,
) -> None:
    issuer, root = _fixture(tmp_path)
    observed = issuer.observe()
    result = issuer.publish(observed, "a" * 64)
    pin = _load(root)
    assert pin.runtime.runtime_host_installation_id == result.runtime_host_installation_id
    assert pin.runtime_manifest_digest == result.host_manifest_digest
    assert pin.project_root.root_mount_id == RUNTIME_NAMESPACE_BINDING_V1
    assert pin.cgroup.cgroup_mount_device == RUNTIME_NAMESPACE_BINDING_V1
    assert set(path.name for path in (root / "usr/share/agentbox/waw").iterdir()) == set(
        WAW_PUBLIC_MANIFEST_FILENAMES_V2
    )
    assert all(
        "/releases/0.3.0rc30/libexec/" in entry.path
        for entry in pin.executable_inventory.executables[1:4]
    )
    private = root / "var/lib/agentbox-waw/runtime-host-installation.v2.json"
    inode = private.stat().st_ino
    repeated = issuer.publish(issuer.observe(), "a" * 64)
    assert repeated == result and private.stat().st_ino == inode


def test_publication_source_drift_fails_before_writing_authority(tmp_path: Path) -> None:
    issuer, root = _fixture(tmp_path)
    observed = issuer.observe()
    vendor = root / "usr/local/bin/codex"
    vendor.write_bytes(vendor.read_bytes() + b"changed")
    with pytest.raises(WAWManifestInstallError, match="source changed"):
        issuer.publish(observed, "a" * 64)
    assert not (root / "var/lib/agentbox-waw/runtime-host-installation.v2.json").exists()


def test_interrupted_public_bundle_requires_explicit_matching_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issuer, root = _fixture(tmp_path)
    observed = issuer.observe()
    original = issuer._create_file
    calls = 0

    def interrupt(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 5:
            raise RuntimeError("publication interrupted")
        original(*args, **kwargs)

    monkeypatch.setattr(issuer, "_create_file", interrupt)
    with pytest.raises(RuntimeError, match="interrupted"):
        issuer.publish(observed, "a" * 64)
    assert not (root / "var/lib/agentbox-waw/runtime-host-installation.v2.json").exists()
    monkeypatch.setattr(issuer, "_create_file", original)
    with pytest.raises(WAWManifestInstallError, match="requires --recover"):
        issuer.publish(issuer.observe(), "a" * 64)
    issuer.publish(issuer.observe(), "a" * 64, recover=True)
    assert _load(root).runtime.runtime_attestation_x25519_fingerprint == "a" * 64


@pytest.mark.parametrize("mutation", ["symlink", "script", "writable", "missing"])
def test_preparation_rejects_untrusted_or_missing_vendor_binary(
    tmp_path: Path, mutation: str
) -> None:
    issuer, root = _fixture(tmp_path)
    vendor = root / "usr/local/bin/claude"
    if mutation == "symlink":
        vendor.unlink()
        vendor.symlink_to(root / "usr/bin/tmux")
    elif mutation == "script":
        vendor.write_bytes(b"#!/bin/sh\nexit 0\n")
    elif mutation == "writable":
        vendor.chmod(0o775)
    else:
        vendor.unlink()
    with pytest.raises((WAWManifestInstallError, OSError)):
        issuer.observe()


def test_existing_enrollment_cannot_rotate_key_or_resources_implicitly(tmp_path: Path) -> None:
    issuer, root = _fixture(tmp_path)
    issuer.publish(issuer.observe(), "a" * 64)
    private = root / "var/lib/agentbox-waw/runtime-host-installation.v2.json"
    original = private.read_bytes()
    with pytest.raises(WAWManifestInstallError, match="explicit rotation"):
        issuer.publish(issuer.observe(), "b" * 64, recover=True)
    assert private.read_bytes() == original


@pytest.mark.parametrize("plan", [True, False])
def test_installer_preparation_connects_public_key_pin_and_preserves_disabled_profiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, plan: bool
) -> None:
    from agentbox_installer.cli import create_parser
    from agentbox_installer.host import HostOperations
    from agentbox_installer.layout import InstallLayout
    from agentbox_installer.lifecycle import AgentBoxInstaller

    _issuer, root = _fixture(tmp_path)
    profiles = {
        "etc/agentbox/waw-api-profile.v1.json": (
            b'{"mode":"disabled","schema_version":"agentbox-waw-api-profile.v1"}\n'
        ),
        "var/lib/agentbox-waw/runtime-profile.v1.json": (
            b'{"mode":"disabled","schema_version":"agentbox-waw-runtime-profile.v1"}\n'
        ),
    }
    for name, raw in profiles.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o750)
        path.write_bytes(raw)
        path.chmod(0o440)
    installer = AgentBoxInstaller(InstallLayout(root), HostOperations(real_host=False))
    monkeypatch.setattr(installer, "installation_state", lambda: "installed")
    monkeypatch.setattr(installer, "current_version", lambda: "0.3.0rc30")
    calls: list[tuple[Path, bool]] = []

    def initialize(release: Path, *, recover: bool = False) -> str:
        calls.append((release, recover))
        return "a" * 64

    monkeypatch.setattr(installer.host, "initialize_waw_runtime_key", initialize)
    result = installer.prepare_waw_manifests(plan=plan)
    assert all((root / name).read_bytes() == raw for name, raw in profiles.items())
    if plan:
        assert calls == []
        assert result.status == "resources_validated_key_not_initialized"
        assert not (root / "usr/share/agentbox/waw").exists()
    else:
        assert calls == [(root / "opt/agentbox/releases/0.3.0rc30", False)]
        assert _load(root).runtime_manifest_digest == result.host_manifest_digest
    args = create_parser().parse_args(["prepare-waw-manifests", "--plan", "--json"])
    assert args.plan and args.json and not args.recover


@pytest.mark.parametrize("kind", ["private", "public", "unrelated"])
def test_exact_unpublished_manifest_prefix_recovery_preserves_existing_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    issuer, root = _fixture(tmp_path)
    observed = issuer.observe()
    original = issuer._create_file

    def interrupt(parent: int, name: str, raw: bytes, mode: int, gid: int, **kwargs: Any) -> None:
        target = (kind == "private" and name == "runtime-host-installation.initial-v2.pending") or (
            kind != "private" and name == "api-host-anchor.v2.json"
        )
        if target:
            prefix = raw[:17] if kind != "unrelated" else b"unrelated user file"
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode, dir_fd=parent)
            try:
                os.write(fd, prefix)
                os.fchmod(fd, mode)
            finally:
                os.close(fd)
            raise RuntimeError("prefix interrupted")
        original(parent, name, raw, mode, gid, **kwargs)

    monkeypatch.setattr(issuer, "_create_file", interrupt)
    with pytest.raises(RuntimeError, match="interrupted"):
        issuer.publish(observed, "a" * 64)
    monkeypatch.setattr(issuer, "_create_file", original)
    if kind == "unrelated":
        path = root / "usr/share/agentbox/waw/api-host-anchor.v2.json"
        before = path.stat().st_mode
        with pytest.raises(WAWManifestInstallError, match="unsafe or different"):
            issuer.publish(issuer.observe(), "a" * 64, recover=True)
        assert path.read_bytes() == b"unrelated user file" and path.stat().st_mode == before
    else:
        issuer.publish(issuer.observe(), "a" * 64, recover=True)
        assert _load(root).runtime.runtime_attestation_x25519_fingerprint == "a" * 64
