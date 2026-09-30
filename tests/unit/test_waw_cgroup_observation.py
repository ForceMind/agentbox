from __future__ import annotations

import os
import stat
from types import SimpleNamespace
from typing import Any, cast

import pytest
from agentbox_runtime import waw_cgroup_observation as subject
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_cgroup_observation import WAWCgroupObservationFactory
from test_waw_scoped_cgroup import _manifest


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


def test_observation_requires_real_systemd_invocation_identity() -> None:
    with pytest.raises(RuntimeOperationError, match="invocation"):
        WAWCgroupObservationFactory(
            cast(Any, None), cast(Any, None), invocation_id="", runtime_epoch=lambda: "1"
        )
