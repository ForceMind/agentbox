from __future__ import annotations

import os
import platform
import stat
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from agentbox_runtime import waw_fixed_transport as transport
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_manifest_codecs import (
    RUNTIME_NAMESPACE_BINDING_V1,
    SCOPED_CGROUP_FILESYSTEM_V1,
    SCOPED_CGROUP_PROTECTION_V1,
    SCOPED_CGROUP_TEMPLATE_SHA256_V1,
    SCOPED_CGROUP_WORKSPACES_V1,
    WAWManifestCodecError,
    decode_cgroup_delegation_manifest,
    decode_project_root_manifest,
    decode_runtime_host_manifest_v2,
    encode_api_host_anchor_v2,
    encode_cgroup_delegation_manifest,
    encode_project_root_manifest,
    encode_runtime_host_manifest_v2,
    manifest_sha256,
    verify_api_host_anchor_v2_cross_manifest,
)
from test_waw_manifest_codecs import _cgroup, _project, _v2_cross_pin_inputs


def _project_data() -> dict[str, Any]:
    return {
        **_project(),
        "root_device": RUNTIME_NAMESPACE_BINDING_V1,
        "root_mount_id": RUNTIME_NAMESPACE_BINDING_V1,
        "root_filesystem_id": "fsid:101;inode:202",
    }


def _cgroup_data() -> dict[str, Any]:
    return {
        **_cgroup(),
        "protect_control_groups": SCOPED_CGROUP_PROTECTION_V1,
        "delegate_subgroup": SCOPED_CGROUP_WORKSPACES_V1,
        "policy_template_digest": SCOPED_CGROUP_TEMPLATE_SHA256_V1,
        "cgroup_mount_device": RUNTIME_NAMESPACE_BINDING_V1,
        "cgroup_mount_filesystem_id": SCOPED_CGROUP_FILESYSTEM_V1,
    }


@pytest.mark.parametrize(
    "identity",
    [
        "",
        "fsid:0;inode:2",
        "fsid:1;inode:0",
        "fsid:01;inode:2",
        "fsid:1;inode:2;other:3",
        "fsid:1;inode:18446744073709551616",
    ],
)
def test_namespace_project_requires_closed_positive_filesystem_and_inode(identity: str) -> None:
    with pytest.raises(WAWManifestCodecError):
        encode_project_root_manifest({**_project_data(), "root_filesystem_id": identity})


@pytest.mark.parametrize("field", ["root_device", "root_mount_id"])
def test_namespace_project_cannot_mix_legacy_device_or_mount(field: str) -> None:
    with pytest.raises(WAWManifestCodecError):
        encode_project_root_manifest({**_project_data(), field: "42"})


@pytest.mark.parametrize(
    "mutation", [{"protect_control_groups": "private"}, {"cgroup_mount_filesystem_id": "other"}]
)
def test_namespace_cgroup_requires_the_exact_scoped_profile(mutation: dict[str, str]) -> None:
    with pytest.raises(WAWManifestCodecError):
        encode_cgroup_delegation_manifest({**_cgroup_data(), **mutation})


@pytest.mark.parametrize("profile", ["both", "project", "cgroup"])
def test_v2_cross_pin_requires_one_consistent_namespace_profile(profile: str) -> None:
    values = list(_v2_cross_pin_inputs())
    if profile in {"both", "project"}:
        values[2] = encode_project_root_manifest(_project_data())
    if profile in {"both", "cgroup"}:
        values[3] = encode_cgroup_delegation_manifest(_cgroup_data())
    runtime = asdict(decode_runtime_host_manifest_v2(values[1]))
    runtime["project_root_manifest_digest"] = manifest_sha256(values[2])
    runtime["cgroup_delegation_manifest_digest"] = manifest_sha256(values[3])
    values[1] = encode_runtime_host_manifest_v2(runtime)
    from agentbox_runtime.waw_manifest_codecs import decode_api_host_anchor_v2

    anchor = asdict(decode_api_host_anchor_v2(values[0]))
    anchor["host_manifest_digest"] = manifest_sha256(values[1])
    anchor["project_root_manifest_digest"] = manifest_sha256(values[2])
    values[0] = encode_api_host_anchor_v2(anchor)
    if profile == "both":
        assert (
            verify_api_host_anchor_v2_cross_manifest(*values).project_root.root_mount_id
            == RUNTIME_NAMESPACE_BINDING_V1
        )
    else:
        with pytest.raises(WAWManifestCodecError, match="mixed v2"):
            verify_api_host_anchor_v2_cross_manifest(*values)


def test_namespace_binding_cannot_downgrade_to_v1_bundle() -> None:
    from agentbox_runtime.waw_manifest_codecs import (
        decode_api_host_anchor,
        decode_runtime_host_manifest,
        encode_api_host_anchor,
        encode_runtime_host_manifest,
        verify_api_host_anchor_cross_manifest,
    )
    from test_waw_manifest_codecs import _cross_pin_inputs

    anchor, runtime, _project_raw, _cgroup_raw = _cross_pin_inputs()
    project = encode_project_root_manifest(_project_data())
    cgroup = encode_cgroup_delegation_manifest(_cgroup_data())
    runtime_data = asdict(decode_runtime_host_manifest(runtime))
    runtime_data["project_root_manifest_digest"] = manifest_sha256(project)
    runtime_data["cgroup_delegation_policy_digest"] = manifest_sha256(cgroup)
    runtime = encode_runtime_host_manifest(runtime_data)
    anchor_data = asdict(decode_api_host_anchor(anchor))
    anchor_data["host_manifest_digest"] = manifest_sha256(runtime)
    anchor_data["project_root_manifest_digest"] = manifest_sha256(project)
    with pytest.raises(WAWManifestCodecError, match="v2 runtime bundle"):
        verify_api_host_anchor_cross_manifest(
            encode_api_host_anchor(anchor_data), runtime, project, cgroup
        )


@pytest.mark.parametrize("mount_id,device", [("31", "0:31"), ("131", "0:41")])
def test_namespace_cgroup_binds_current_kernel_device_and_mount(
    monkeypatch: pytest.MonkeyPatch, mount_id: str, device: str
) -> None:
    manifest = decode_cgroup_delegation_manifest(encode_cgroup_delegation_manifest(_cgroup_data()))
    raw = (
        f"30 1 {device} / /sys/fs/cgroup ro - cgroup2 cgroup rw\n"
        f"{mount_id} 30 {device} /system.slice/agentbox-runtime.service "
        "/sys/fs/cgroup/system.slice/agentbox-runtime.service rw - cgroup2 cgroup rw\n"
    )
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: raw)
    assert transport._mountinfo_matches_cgroup(mount_id, manifest, device)
    assert not transport._mountinfo_matches_cgroup(mount_id, manifest)
    assert not transport._mountinfo_matches_cgroup(mount_id, manifest, "0:99")
    assert not transport._mountinfo_matches_cgroup("999", manifest, device)


@pytest.mark.parametrize("change", ["none", "filesystem", "inode", "mount"])
def test_namespace_project_keeps_physical_identity_and_live_mount_checks(
    monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    manifest = decode_project_root_manifest(encode_project_root_manifest(_project_data()))
    facts = SimpleNamespace(st_dev=2049, st_ino=202, st_gid=0, st_mode=stat.S_IFDIR | 0o755)
    monkeypatch.setattr(transport, "_verify_installed_directory", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(os, "fstat", lambda _fd: facts)
    monkeypatch.setattr(
        os, "fstatvfs", lambda _fd: SimpleNamespace(f_fsid=999 if change == "filesystem" else 101)
    )
    if change == "inode":
        facts.st_ino = 999
    monkeypatch.setattr(transport, "_fd_mount_id", lambda _fd: "131")
    monkeypatch.setattr(transport, "_mountinfo_has_device", lambda *_args: change != "mount")
    if change == "none":
        transport._verify_project_root_descriptor(9, manifest)
    else:
        with pytest.raises(RuntimeOperationError):
            transport._verify_project_root_descriptor(9, manifest)


@pytest.mark.skipif(platform.system() != "Linux", reason="real Linux /proc FD mount identity")
def test_namespace_project_verifies_real_linux_fd_and_filesystem(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        facts = os.fstat(descriptor)
        manifest = decode_project_root_manifest(
            encode_project_root_manifest(
                {
                    **_project_data(),
                    "configured_root": str(tmp_path),
                    "root_uid": str(facts.st_uid),
                    "root_gid": str(facts.st_gid),
                    "root_mode": "700",
                    "root_filesystem_id": transport._project_filesystem_identity(descriptor),
                }
            )
        )
        transport._verify_project_root_descriptor(descriptor, manifest)
    finally:
        os.close(descriptor)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("pos:\t0\nflags:\t02100000\nmnt_id:\t402\nino:\t1\n", "402"),
        ("mnt_id:\t42\nmnt_id:\t43\n", None),
        ("mnt_id:\t\n", None),
        ("mnt_id:\t 42\n", None),
        ("mnt_id:\tabc\n", None),
    ],
)
def test_fd_mount_id_parses_kernel_separator_without_including_tab(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: str | None
) -> None:
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: raw)
    if expected is None:
        with pytest.raises(RuntimeOperationError):
            transport._fd_mount_id(9)
    else:
        assert transport._fd_mount_id(9) == expected
