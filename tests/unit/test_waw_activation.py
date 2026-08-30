from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest
from agentbox_runtime.waw_activation import (
    WAWActivationError,
    _validate_socket,
    load_waw_activated_sockets,
)


def _listener(path: Path, *, mode: int = 0o660) -> socket.socket:
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen(4)
    path.chmod(mode)
    return listener


@pytest.mark.parametrize(
    ("listen_pid", "listen_fds", "listen_names"),
    (
        ("0", "2", "agentbox-waw-control:agentbox-waw-stream"),
        (str(os.getpid()), "1", "agentbox-waw-control"),
        (str(os.getpid()), "2", "agentbox-waw-stream:agentbox-waw-control"),
    ),
)
def test_activation_metadata_must_be_exact(
    monkeypatch: pytest.MonkeyPatch,
    listen_pid: str,
    listen_fds: str,
    listen_names: str,
) -> None:
    monkeypatch.setenv("LISTEN_PID", listen_pid)
    monkeypatch.setenv("LISTEN_FDS", listen_fds)
    monkeypatch.setenv("LISTEN_FDNAMES", listen_names)
    with pytest.raises(WAWActivationError):
        load_waw_activated_sockets(expected_uid=os.geteuid(), expected_gid=os.getegid())


def test_listener_descriptor_requires_exact_path_owner_group_and_mode(tmp_path: Path) -> None:
    path = tmp_path / "control.sock"
    listener = _listener(path)
    try:
        _validate_socket(listener, str(path), os.geteuid(), os.getegid())
        path.chmod(0o600)
        with pytest.raises(WAWActivationError):
            _validate_socket(listener, str(path), os.geteuid(), os.getegid())
    finally:
        listener.close()


def test_listener_descriptor_rejects_non_listening_socket(tmp_path: Path) -> None:
    path = tmp_path / "control.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    path.chmod(0o660)
    try:
        with pytest.raises(WAWActivationError):
            _validate_socket(listener, str(path), os.geteuid(), os.getegid())
    finally:
        listener.close()
