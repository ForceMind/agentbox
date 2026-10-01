from __future__ import annotations

import os
import subprocess
import sys
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

import pytest
from agentbox_installer.host import HostMutationError, HostOperations


@pytest.mark.parametrize("state", ["inactive", "active", "runtime", "incomplete", "denied"])
def test_fixed_policy_guard_requires_inactive_units_and_complete_uid_visibility(
    monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    host = HostOperations(real_host=True)
    monkeypatch.setattr(host, "require_root", lambda: None)
    monkeypatch.setattr(host, "owner_ids", lambda *_args: (19002, 19002))
    monkeypatch.setattr(sys, "platform", "linux")
    queried: list[tuple[str, ...]] = []

    def query(argv: tuple[str, ...], **_kwargs: Any) -> Any:
        queried.append(argv)
        return SimpleNamespace(
            returncode=0, stdout="active\n" if state == "active" else "inactive\n"
        )

    monkeypatch.setattr(subprocess, "run", query)
    monkeypatch.setattr(
        os, "scandir", lambda path: nullcontext(iter([SimpleNamespace(name="100")]))
    )
    opened: list[str] = []

    def open_status(path: str, _flags: int) -> int:
        opened.append(path)
        if state == "denied":
            raise PermissionError("synthetic metadata visibility denial")
        return 9

    raw = b"Name:\tfake\nUid:\t0\t0\t0\t0\n"
    if state == "runtime":
        raw = b"Uid:\t19002\t19002\t19002\t19002\n"
    elif state == "incomplete":
        raw = b"Uid:\t19002\n"
    monkeypatch.setattr(os, "open", open_status)
    monkeypatch.setattr(os, "read", lambda _fd, _size: raw)
    monkeypatch.setattr(os, "close", lambda _fd: None)
    if state == "inactive":
        host.require_waw_policy_quiescence()
    else:
        with pytest.raises((HostMutationError, PermissionError)):
            host.require_waw_policy_quiescence()
    assert queried and all(argv[:2] == ("/usr/bin/systemctl", "show") for argv in queried)
    assert opened == ([] if state == "active" else ["/proc/100/status"])
