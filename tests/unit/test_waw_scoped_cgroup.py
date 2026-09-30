from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from agentbox_runtime import waw_fixed_transport as transport
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_fixed_transport import (
    WAWVerifiedExecutionAuthority,
    _mountinfo_matches_cgroup,
)
from agentbox_runtime.waw_manifest_codecs import (
    SCOPED_CGROUP_PROTECTION_V1,
    SCOPED_CGROUP_TEMPLATE_SHA256_V1,
    SCOPED_CGROUP_WORKSPACES_V1,
    CgroupDelegationManifest,
    WAWManifestCodecError,
    cgroup_delegate_root_path,
    decode_cgroup_delegation_manifest,
    encode_cgroup_delegation_manifest,
)
from pytest import MonkeyPatch
from test_waw_manifest_codecs import _cgroup


def _manifest() -> CgroupDelegationManifest:
    value = {
        **_cgroup(),
        "protect_control_groups": SCOPED_CGROUP_PROTECTION_V1,
        "delegate_subgroup": SCOPED_CGROUP_WORKSPACES_V1,
        "policy_template_digest": SCOPED_CGROUP_TEMPLATE_SHA256_V1,
    }
    return decode_cgroup_delegation_manifest(encode_cgroup_delegation_manifest(value))


def test_scoped_policy_uses_one_fixed_service_workspace_root() -> None:
    assert cgroup_delegate_root_path(_manifest()) == (
        "/sys/fs/cgroup/system.slice/agentbox-runtime.service/agentbox-runtime-workspaces"
    )
    legacy = decode_cgroup_delegation_manifest(encode_cgroup_delegation_manifest(_cgroup()))
    assert cgroup_delegate_root_path(legacy) == "/sys/fs/cgroup/agentbox-runtime-supervisor"


def test_scoped_profile_pins_the_actual_installer_dropin() -> None:
    root = Path(__file__).resolve().parents[2]
    policy = root / "installer/src/agentbox_installer/assets/systemd/agentbox-runtime-waw.v1.conf"
    assert hashlib.sha256(policy.read_bytes()).hexdigest() == SCOPED_CGROUP_TEMPLATE_SHA256_V1
    with pytest.raises(WAWManifestCodecError, match="policy template"):
        encode_cgroup_delegation_manifest(
            {
                **_cgroup(),
                "protect_control_groups": SCOPED_CGROUP_PROTECTION_V1,
                "delegate_subgroup": SCOPED_CGROUP_WORKSPACES_V1,
            }
        )


@pytest.mark.parametrize("subgroup", ["../outside", "system.slice/other.service", "other", ""])
def test_scoped_policy_cannot_choose_an_arbitrary_subtree(subgroup: str) -> None:
    with pytest.raises(WAWManifestCodecError):
        encode_cgroup_delegation_manifest(
            {
                **_cgroup(),
                "protect_control_groups": SCOPED_CGROUP_PROTECTION_V1,
                "delegate_subgroup": subgroup,
            }
        )


@pytest.mark.parametrize(
    "change", ["none", "global_rw", "scope_ro", "wrong_scope", "wrong_root", "outside_rw"]
)
def test_scoped_mount_requires_exact_rw_service_and_ro_global(
    monkeypatch: MonkeyPatch,
    change: str,
) -> None:
    global_mount = "30 1 0:31 / /sys/fs/cgroup ro - cgroup2 cgroup rw\n"
    scoped_mount = (
        "31 30 0:31 /system.slice/agentbox-runtime.service "
        "/sys/fs/cgroup/system.slice/agentbox-runtime.service rw - cgroup2 cgroup rw\n"
    )
    if change == "global_rw":
        global_mount = global_mount.replace(" ro ", " rw ")
    elif change == "scope_ro":
        scoped_mount = scoped_mount.replace(" rw -", " ro -")
    elif change == "wrong_scope":
        scoped_mount = scoped_mount.replace("agentbox-runtime.service", "other.service")
    elif change == "wrong_root":
        scoped_mount = scoped_mount.replace("0:31 /system.slice/agentbox-runtime.service", "0:31 /")
    elif change == "outside_rw":
        scoped_mount += "32 30 0:31 /other /sys/fs/cgroup/other rw - cgroup2 cgroup rw\n"
    original = Path.read_text

    def read(path: Path, *args: object, **kwargs: object) -> str:
        if path == Path("/proc/self/mountinfo"):
            return global_mount + scoped_mount
        return original(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", read)
    assert _mountinfo_matches_cgroup("31", _manifest()) is (change == "none")


@pytest.mark.parametrize(
    "change", ["none", "root_caller", "wrong_owner", "wrong_group", "writable"]
)
def test_scoped_descriptor_requires_exact_nonroot_runtime_ownership(
    monkeypatch: MonkeyPatch,
    change: str,
) -> None:
    manifest = _manifest()
    authority = cast(
        WAWVerifiedExecutionAuthority, SimpleNamespace(_manifest=SimpleNamespace(cgroup=manifest))
    )
    facts = SimpleNamespace(st_dev=31, st_uid=19002, st_gid=19002, st_mode=stat.S_IFDIR | 0o755)
    if change == "wrong_owner":
        facts.st_uid = 19001
    elif change == "wrong_group":
        facts.st_gid = 19001
    elif change == "writable":
        facts.st_mode |= 0o020
    monkeypatch.setattr(os, "fstat", lambda _fd: facts)
    monkeypatch.setattr(os, "geteuid", lambda: 0 if change == "root_caller" else 19002)
    monkeypatch.setattr(os, "getegid", lambda: 19002)
    monkeypatch.setattr(os, "major", lambda _dev: 0)
    monkeypatch.setattr(os, "minor", lambda _dev: 31)
    monkeypatch.setattr(os, "readlink", lambda _path: cgroup_delegate_root_path(manifest))
    monkeypatch.setattr(transport, "_fd_mount_id", lambda _fd: "31")
    monkeypatch.setattr(transport, "_mountinfo_matches_cgroup", lambda *_args: True)
    if change == "none":
        assert transport._verify_delegate_root(9, authority) == (
            "31",
            manifest.cgroup_mount_filesystem_id,
        )
    else:
        with pytest.raises(RuntimeOperationError):
            transport._verify_delegate_root(9, authority)
