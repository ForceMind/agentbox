from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest
from agentbox_runtime.codex_remote_observation import LinuxCodexRemoteObserver
from agentbox_runtime.models import RemoteState


def _fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[LinuxCodexRemoteObserver, Path, Path]:
    proc = tmp_path / "proc"
    proc.mkdir()
    executable = tmp_path / "codex"
    executable.write_bytes(b"fixture")
    process = proc / "101"
    process.mkdir()
    uid = os.geteuid()
    (process / "status").write_bytes(f"Uid:\t{uid}\t{uid}\t{uid}\t{uid}\n".encode())
    fields = ["S"] + ["0"] * 19
    fields[19] = "100"
    (process / "stat").write_bytes(("101 (fixture) " + " ".join(fields)).encode())
    (process / "exe").symlink_to(executable)
    (process / "cmdline").write_bytes(b"codex\0")
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(os, "getresuid", lambda: (uid, uid, uid), raising=False)
    observer = LinuxCodexRemoteObserver(proc)
    monkeypatch.setattr(observer, "_namespace_complete", lambda _fd: True)
    return observer, executable, process


@pytest.mark.parametrize(
    "kind",
    [
        "stopped",
        "running",
        "global-options",
        "empty-argv",
        "bad-uid",
        "missing-exe",
        "pid-reuse",
        "hidden",
        "alternate-executable",
    ],
)
def test_complete_remote_observation_never_promotes_incomplete_or_changed_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    observer, executable, process = _fixture(tmp_path, monkeypatch)
    expected = RemoteState.UNKNOWN
    if kind == "stopped":
        expected = RemoteState.STOPPED
    elif kind in {"running", "global-options"}:
        (process / "cmdline").write_bytes(
            b"codex\0--config\0fixture\0remote-control\0start\0"
            if kind == "global-options"
            else b"codex\0remote-control\0start\0"
        )
        expected = RemoteState.RUNNING
    elif kind == "empty-argv":
        (process / "cmdline").write_bytes(b"")
    elif kind == "bad-uid":
        (process / "status").write_bytes(b"Uid:\t1001\n")
    elif kind == "missing-exe":
        (process / "exe").unlink()
    elif kind == "hidden":
        monkeypatch.setattr(observer, "_namespace_complete", lambda _fd: False)
    elif kind == "alternate-executable":
        alternate = executable.parent / "codex-old"
        alternate.write_bytes(b"other fixture")
        (process / "exe").unlink()
        (process / "exe").symlink_to(alternate)
        (process / "cmdline").write_bytes(b"codex\0remote-control\0start\0")
    else:
        original = observer._snapshot
        calls = 0

        def snapshot(*args: Any) -> Any:
            nonlocal calls
            calls += 1
            if calls == 2:
                raw = (process / "stat").read_bytes().replace(b" 100", b" 200")
                (process / "stat").write_bytes(raw)
            return original(*args)

        monkeypatch.setattr(observer, "_snapshot", snapshot)
    assert observer.observe(executable) is expected


def test_current_uid_permission_failure_keeps_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observer, executable, _process = _fixture(tmp_path, monkeypatch)

    def denied(*_args: object) -> bytes:
        raise PermissionError("fixture denied process metadata")

    monkeypatch.setattr(observer, "_read", denied)
    assert observer.observe(executable) is RemoteState.UNKNOWN
