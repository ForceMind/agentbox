from __future__ import annotations

import os
import stat
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from agentbox_runtime import waw_fixed_transport as subject
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_fixed_transport import WAWVerifiedExecutionAuthority
from test_waw_scoped_cgroup import _manifest


@pytest.mark.parametrize(
    "variation", ["valid", "populated", "threaded", "missing_controller", "no_readback"]
)
def test_controller_setup_requires_empty_domain_and_positive_readback(
    monkeypatch: pytest.MonkeyPatch, variation: str
) -> None:
    values = {
        "cgroup.type": "domain",
        "cgroup.procs": "",
        "cgroup.controllers": "cpu memory pids",
        "cgroup.subtree_control": "cpu memory pids",
    }
    if variation == "populated":
        values["cgroup.procs"] = "123"
    if variation == "threaded":
        values["cgroup.type"] = "threaded"
    if variation == "missing_controller":
        values["cgroup.controllers"] = "cpu pids"
    if variation == "no_readback":
        values["cgroup.subtree_control"] = ""
    writes: list[tuple[int, str, bytes]] = []
    monkeypatch.setattr(subject, "_read_cgroup_file", lambda _fd, name: values[name])
    monkeypatch.setattr(
        subject, "_write_cgroup_setup", lambda fd, name, data: writes.append((fd, name, data))
    )
    if variation == "valid":
        subject._enable_cgroup_controllers(9)
        assert writes == [(9, "cgroup.subtree_control", b"+cpu +memory +pids\n")]
    else:
        with pytest.raises(RuntimeOperationError):
            subject._enable_cgroup_controllers(9)
        assert bool(writes) == (variation == "no_readback")


@pytest.mark.parametrize("variation", ["valid", "existing", "limit_failure"])
def test_workload_creation_is_create_only_and_preserves_existing_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variation: str
) -> None:
    root = tmp_path / "delegate"
    root.mkdir()
    name = "ws-" + "a" * 64 + "-g1"
    if variation == "existing":
        (root / name).mkdir()
        (root / name / "user-canary").write_text("preserved")
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    authority = cast(
        WAWVerifiedExecutionAuthority,
        SimpleNamespace(_manifest=SimpleNamespace(cgroup=_manifest())),
    )
    monkeypatch.setattr(subject, "_enable_cgroup_controllers", lambda _fd: None)
    monkeypatch.setattr(subject, "_verify_delegate_root", lambda *_args: ("31", "fixture"))
    writes: dict[str, bytes] = {}

    def write(_fd: int, key: str, data: bytes) -> None:
        writes[key] = data
        if variation == "limit_failure":
            raise OSError("write failure")

    monkeypatch.setattr(subject, "_write_cgroup_setup", write)
    monkeypatch.setattr(subject, "_validate_delegated_workload", lambda *_args: None)
    try:
        if variation == "valid":
            subject._create_bound_workload_cgroup(descriptor, name, authority)
            assert (root / name / "workload").is_dir()
            assert writes == {
                "pids.max": b"256\n",
                "memory.max": b"536870912\n",
                "memory.swap.max": b"0\n",
                "cpu.max": b"400000 100000\n",
            }
        elif variation == "existing":
            with pytest.raises(RuntimeOperationError, match="already exists"):
                subject._create_bound_workload_cgroup(descriptor, name, authority)
            assert (root / name / "user-canary").read_text() == "preserved" and writes == {}
        else:
            with pytest.raises(OSError, match="write failure"):
                subject._create_bound_workload_cgroup(descriptor, name, authority)
            assert not (root / name).exists()
    finally:
        os.close(descriptor)


@pytest.mark.parametrize("name", ["../outside", "caller", "ws-" + "a" * 64 + "-g0"])
def test_cgroup_creation_has_no_arbitrary_directory_selector(name: str) -> None:
    with pytest.raises(RuntimeOperationError, match="identity is invalid"):
        subject._create_bound_workload_cgroup(-1, name, cast(Any, object()))


def test_setup_write_names_remain_closed() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        subject._write_cgroup_setup(-1, "caller-file", b"caller")


@pytest.mark.parametrize(
    "variation", ["valid", "wrong_owner", "wrong_group", "writable", "bad_mount", "root_caller"]
)
def test_workspace_root_creation_requires_verified_scoped_service(
    monkeypatch: pytest.MonkeyPatch, variation: str
) -> None:
    manifest = _manifest()
    authority = cast(
        WAWVerifiedExecutionAuthority, SimpleNamespace(_manifest=SimpleNamespace(cgroup=manifest))
    )
    facts = SimpleNamespace(st_dev=31, st_uid=19002, st_gid=19002, st_mode=stat.S_IFDIR | 0o755)
    if variation == "wrong_owner":
        facts.st_uid = 19001
    if variation == "wrong_group":
        facts.st_gid = 19001
    if variation == "writable":
        facts.st_mode |= 0o020
    monkeypatch.setattr(os, "geteuid", lambda: 0 if variation == "root_caller" else 19002)
    monkeypatch.setattr(os, "getegid", lambda: 19002)
    monkeypatch.setattr(os, "open", lambda *_args, **_kwargs: 9)
    monkeypatch.setattr(os, "fstat", lambda _fd: facts)
    monkeypatch.setattr(subject, "_fd_mount_id", lambda _fd: "31")
    monkeypatch.setattr(
        subject, "_mountinfo_matches_cgroup", lambda *_args: variation != "bad_mount"
    )
    writes: list[tuple[str, str | int]] = []
    closed: list[int] = []
    monkeypatch.setattr(subject, "_close_fd", closed.append)
    monkeypatch.setattr(
        subject, "_enable_cgroup_controllers", lambda fd: writes.append(("controllers", fd))
    )
    monkeypatch.setattr(os, "mkdir", lambda name, *_args, **_kwargs: writes.append(("mkdir", name)))
    monkeypatch.setattr(subject, "_open_relative_directory", lambda *_args, **_kwargs: 10)
    monkeypatch.setattr(subject, "_verify_delegate_root", lambda *_args: None)
    if variation == "valid":
        assert subject._open_scoped_workspace_root(authority) == 10
        assert writes == [
            ("controllers", 9),
            ("mkdir", manifest.delegate_subgroup),
            ("controllers", 10),
        ]
        assert closed == [9]
    else:
        with pytest.raises(RuntimeOperationError):
            subject._open_scoped_workspace_root(authority)
        assert writes == []
        assert closed == ([] if variation == "root_caller" else [9])
