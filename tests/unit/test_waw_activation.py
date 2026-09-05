from __future__ import annotations

import os
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest
from agentbox_runtime.waw_activation import (
    WAWActivatedSockets,
    WAWActivationError,
    _validate_socket,
    load_waw_activated_sockets,
)


def test_activated_socket_take_moves_descriptors_once() -> None:
    control, control_peer = socket.socketpair()
    stream, stream_peer = socket.socketpair()
    source = WAWActivatedSockets(control, stream)
    try:
        owned = source.take()
        assert source.control.fileno() == source.stream.fileno() == -1
        assert owned.control.fileno() >= 0 and owned.stream.fileno() >= 0
        source.close()
        owned.control.send(b"c")
        owned.stream.send(b"s")
        assert control_peer.recv(1) == b"c" and stream_peer.recv(1) == b"s"
        with pytest.raises(WAWActivationError, match="already consumed"):
            source.take()
        owned.close()
    finally:
        control_peer.close()
        stream_peer.close()


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


def test_listener_descriptor_checks_descriptor_owner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "control.sock"
    listener = _listener(path)
    original_fstat = os.fstat

    def forged_fstat(fd: int) -> object:
        details = original_fstat(fd)
        return SimpleNamespace(
            st_mode=details.st_mode,
            st_dev=details.st_dev,
            st_ino=details.st_ino,
            st_uid=details.st_uid + 1,
            st_gid=details.st_gid,
        )

    monkeypatch.setattr(os, "fstat", forged_fstat)
    try:
        with pytest.raises(WAWActivationError):
            _validate_socket(listener, str(path), os.geteuid(), os.getegid())
    finally:
        listener.close()


def test_listener_descriptor_rejects_path_inode_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "control.sock"
    listener = _listener(path)
    original_fstat = os.fstat

    def forged_fstat(fd: int) -> object:
        details = original_fstat(fd)
        path_details = os.lstat(path)
        return SimpleNamespace(
            st_mode=details.st_mode,
            st_dev=path_details.st_dev,
            st_ino=path_details.st_ino + 1,
            st_uid=details.st_uid,
            st_gid=details.st_gid,
        )

    monkeypatch.setattr(os, "fstat", forged_fstat)
    try:
        with pytest.raises(WAWActivationError):
            _validate_socket(listener, str(path), os.geteuid(), os.getegid())
    finally:
        listener.close()
