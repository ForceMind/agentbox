from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from agentbox_runtime import waw_cgroup_observation as subject
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_cgroup_observation import WAWCgroupObservationFactory
from test_waw_cgroup_attestation import _record
from test_waw_scoped_cgroup import _manifest


@pytest.mark.parametrize(
    "state", ["empty", "partial", "populated", "unknown-leaf", "inode-drift", "store-drift"]
)
def test_fixed_cleanup_removes_only_the_observed_empty_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    delegate = tmp_path / "delegate"
    workspace_id = "aws_" + "1" * 32
    name = "ws-" + hashlib.sha256(workspace_id.encode()).hexdigest() + "-g1"
    workspace = delegate / name
    workload = workspace / "workload"
    workload.mkdir(parents=True)
    limits = _record().workload_limits

    def device(path: Path) -> str:
        return f"{os.major(path.stat().st_dev)}:{os.minor(path.stat().st_dev)}"

    record = replace(
        _record(),
        runtime_epoch="2",
        service_invocation_id="2" * 32,
        delegate_subgroup_device=device(delegate),
        delegate_subgroup_inode=str(delegate.stat().st_ino),
        workspace_relative_path=name,
        workload_relative_path=name + "/workload",
        workspace_device=device(workspace),
        workspace_inode=str(workspace.stat().st_ino),
        workload_device=device(workload),
        workload_inode=str(workload.stat().st_ino),
        workspace_limits=limits,
        workload_limits=limits,
        attachment_leaves=(),
        last_populated="0",
        cleanup_state="EMPTY_DURABLE",
    )
    if state == "partial":
        workload.rmdir()
    elif state == "unknown-leaf":
        (workspace / "unrecorded").mkdir()
    elif state == "inode-drift":
        record = replace(record, workspace_inode=str(int(record.workspace_inode) + 1))
    monkeypatch.setattr(subject, "cgroup_delegate_root_path", lambda _manifest: str(delegate))
    monkeypatch.setattr(
        subject,
        "_verify_delegate_root",
        lambda *_args: (record.cgroup_mount_id, record.cgroup_filesystem_id),
    )
    monkeypatch.setattr(subject, "_fd_mount_id", lambda _fd: record.cgroup_mount_id)
    monkeypatch.setattr(subject, "_cgroup_event", lambda *_args: 1 if state == "populated" else 0)
    monkeypatch.setattr(WAWCgroupObservationFactory, "_limits", staticmethod(lambda _fd: limits))
    authority = SimpleNamespace(_manifest=SimpleNamespace(cgroup=None))
    store = SimpleNamespace(read=lambda **_kwargs: None if state == "store-drift" else record)
    factory = WAWCgroupObservationFactory(
        lambda: cast(Any, authority),
        cast(Any, store),
        invocation_id="2" * 32,
        runtime_epoch=lambda: "2",
    )
    if state in {"empty", "partial"}:
        factory.finalize_recovery(record)
        assert not workspace.exists() and delegate.exists()
    else:
        with pytest.raises(RuntimeOperationError):
            factory.finalize_recovery(record)
        assert workspace.exists() and workload.exists()


@pytest.mark.parametrize("state", ["absent", "reappeared", "denied"])
def test_recovery_absence_uses_actual_directory_enoent_and_rejects_other_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    service = tmp_path / "service"
    delegate = service / "agentbox-runtime-workspaces"
    delegate.mkdir(parents=True)
    workspace_id = "aws_" + "1" * 32
    name = "ws-" + hashlib.sha256(workspace_id.encode()).hexdigest() + "-g1"
    old = replace(
        _record(),
        runtime_epoch="1",
        workspace_relative_path=name,
        workload_relative_path=name + "/workload",
    )
    identity = SimpleNamespace(
        workspace_id=workspace_id,
        project_id=old.project_id,
        agent_type=old.agent_type,
        generation="1",
    )
    monkeypatch.setattr(subject, "SCOPED_CGROUP_SERVICE_ROOT_V1", str(service))
    monkeypatch.setattr(
        subject,
        "_open_scoped_workspace_root",
        lambda _authority: os.open(delegate, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW),
    )
    monkeypatch.setattr(
        subject, "_verify_delegate_root", lambda *_args: ("31", "scoped-runtime-cgroup2-v1")
    )
    monkeypatch.setattr(subject, "_fd_mount_id", lambda _fd: "31")
    if state == "denied":

        def denied(*_args: Any, **_kwargs: Any) -> int:
            raise PermissionError("synthetic denied lookup")

        monkeypatch.setattr(subject, "_open_relative_directory", denied)
    if state == "reappeared":
        original_stat = os.stat
        calls = 0

        def changing_stat(path: Any, *args: Any, **kwargs: Any) -> Any:
            nonlocal calls
            if path == name and "dir_fd" in kwargs:
                calls += 1
                if calls == 2:
                    (delegate / name).mkdir()
            return original_stat(path, *args, **kwargs)

        monkeypatch.setattr(os, "stat", changing_stat)
    authority = SimpleNamespace(_manifest=SimpleNamespace(cgroup=_manifest()))
    factory = WAWCgroupObservationFactory(
        lambda: cast(Any, authority),
        cast(Any, SimpleNamespace(read=lambda **_kwargs: old)),
        invocation_id="2" * 32,
        runtime_epoch=lambda: "2",
    )
    if state != "absent":
        with pytest.raises((RuntimeOperationError, PermissionError)):
            factory.observe_recovery(cast(Any, identity))
    else:
        result = factory.observe_recovery(cast(Any, identity))
        assert result.workspace_presence == "absent"
        assert result.workspace_inode == result.workload_inode == "absent"
        assert result.service_cgroup_inode == str(service.stat().st_ino)
        assert result.delegate_subgroup_inode == str(delegate.stat().st_ino)
        assert result.runtime_epoch == "2" and result.cleanup_state == "EMPTY_DURABLE"


@pytest.mark.parametrize(
    "state,populated,extra,expected",
    [
        ("RUNNING", 1, False, "LIVE"),
        ("STOPPED", 0, False, "EMPTY_DURABLE"),
        ("STOPPED", 1, False, "FENCED"),
        ("RUNNING", 0, False, None),
        ("STOPPED", 0, True, None),
    ],
)
def test_fd_observation_never_claims_empty_from_status_alone(
    monkeypatch: pytest.MonkeyPatch, state: str, populated: int, extra: bool, expected: str | None
) -> None:
    opened = iter([9, 10])
    monkeypatch.setattr(os, "geteuid", lambda: 19002)
    monkeypatch.setattr(os, "getegid", lambda: 19002)
    monkeypatch.setattr(os, "open", lambda *_args, **_kwargs: next(opened))
    monkeypatch.setattr(os, "close", lambda _fd: None)
    monkeypatch.setattr(subject, "_open_scoped_workspace_root", lambda _authority: 10)
    monkeypatch.setattr(
        subject,
        "_open_relative_directory",
        lambda _fd, name, **_kwargs: 11 if name.startswith("ws-") else 12,
    )
    monkeypatch.setattr(
        os, "listdir", lambda fd: ["workload"] if fd == 11 else (["unrecorded"] if extra else [])
    )
    monkeypatch.setattr(
        os, "stat", lambda *_args, **_kwargs: SimpleNamespace(st_mode=stat.S_IFDIR | 0o755)
    )
    monkeypatch.setattr(
        os,
        "fstat",
        lambda fd: SimpleNamespace(
            st_dev=31, st_ino=fd, st_uid=19002, st_gid=19002, st_mode=stat.S_IFDIR | 0o755
        ),
    )
    monkeypatch.setattr(
        subject,
        "_verify_delegate_root",
        lambda *_args: ("31", _manifest().cgroup_mount_filesystem_id),
    )
    monkeypatch.setattr(subject, "_fd_mount_id", lambda _fd: "31")
    monkeypatch.setattr(
        subject, "_cgroup_event", lambda _fd, field: populated if field == "populated" else 0
    )
    limits = {
        "cpu.max": "400000 100000",
        "memory.max": "536870912",
        "memory.swap.max": "0",
        "pids.max": "256",
    }
    monkeypatch.setattr(subject, "_read_cgroup_file", lambda _fd, name: limits[name])
    records: list[Any] = []
    authority = SimpleNamespace(_manifest=SimpleNamespace(cgroup=_manifest()))
    factory = WAWCgroupObservationFactory(
        lambda: cast(Any, authority),
        cast(Any, SimpleNamespace(write=records.append)),
        invocation_id="1" * 32,
        runtime_epoch=lambda: "2",
    )
    identity = SimpleNamespace(
        workspace_id="aws_" + "2" * 32,
        project_id="prj_" + "3" * 32,
        agent_type="claude",
        generation="1",
    )
    if expected is None:
        with pytest.raises(RuntimeOperationError):
            factory(cast(Any, identity), cast(Any, SimpleNamespace(state=state)))
        assert records == []
    else:
        result = factory(cast(Any, identity), cast(Any, SimpleNamespace(state=state)))
        assert result.cleanup_state == expected and result.runtime_epoch == "2"
        assert bool(records) == (expected == "EMPTY_DURABLE")
        assert result.workspace_relative_path.startswith("ws-")
        assert len(result.workspace_relative_path) > 64
        if state == "STOPPED":
            records.clear()
            opened = iter([9, 10])
            recovery = factory.observe_recovery(cast(Any, identity))
            assert recovery == result
            assert records == []


def test_observation_requires_real_systemd_invocation_identity() -> None:
    with pytest.raises(RuntimeOperationError, match="invocation"):
        WAWCgroupObservationFactory(
            cast(Any, None), cast(Any, None), invocation_id="", runtime_epoch=lambda: "1"
        )
