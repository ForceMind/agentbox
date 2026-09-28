from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
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
        (str(os.getpid()), "2", "agentbox-waw-control:agentbox-waw-control"),
        (str(os.getpid()), "2", "agentbox-waw-control:unexpected"),
        (str(os.getpid()), "2", "agentbox-waw-control:agentbox-waw-stream:extra"),
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


def test_activation_normalizes_named_roles_when_fd_order_is_reversed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    control_path = tmp_path / "control"
    stream_path = tmp_path / "stream"
    control_path.write_text("control")
    stream_path.write_text("stream")

    class _FD:
        def __init__(self, number: int) -> None:
            self.number = number
            self.closed = False

        def set_inheritable(self, _value: bool) -> None:
            pass

        def close(self) -> None:
            self.closed = True

    descriptors = {3: _FD(3), 4: _FD(4)}

    def check_role(sock: _FD, path: str, _uid: int, _gid: int) -> None:
        expected = str(stream_path if sock.number == 3 else control_path)
        if path != expected:
            raise WAWActivationError("descriptor name and path disagree")

    monkeypatch.setattr(
        "agentbox_runtime.waw_activation.socket.socket",
        lambda *, fileno: descriptors[fileno],
    )
    monkeypatch.setattr("agentbox_runtime.waw_activation._validate_socket", check_role)
    monkeypatch.setenv("LISTEN_PID", str(os.getpid()))
    monkeypatch.setenv("LISTEN_FDS", "2")
    monkeypatch.setenv("LISTEN_FDNAMES", "agentbox-waw-stream:agentbox-waw-control")

    sockets = load_waw_activated_sockets(
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
        control_path=str(control_path),
        stream_path=str(stream_path),
    )
    assert id(sockets.control) == id(descriptors[4])
    assert id(sockets.stream) == id(descriptors[3])

    monkeypatch.setenv("LISTEN_FDNAMES", "agentbox-waw-control:agentbox-waw-stream")
    with pytest.raises(WAWActivationError, match="provenance"):
        load_waw_activated_sockets(
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
            control_path=str(control_path),
            stream_path=str(stream_path),
        )
    assert descriptors[3].closed


@pytest.mark.skipif(sys.platform != "linux", reason="Linux AF_UNIX SO_ACCEPTCONN contract")
@pytest.mark.parametrize(
    ("fd_order", "names", "accepted"),
    [
        ("control-first", "agentbox-waw-control:agentbox-waw-stream", True),
        ("stream-first", "agentbox-waw-stream:agentbox-waw-control", True),
        ("control-first", "agentbox-waw-stream:agentbox-waw-control", False),
    ],
)
def test_activation_matches_fixed_names_to_paths_independent_of_fd_order(
    fd_order: str, names: str, accepted: bool
) -> None:
    # Run FD3/FD4 manipulation in a child so the test process never loses its
    # own descriptors. The short /tmp path fits AF_UNIX on macOS and Linux.
    child = r"""
import os, socket, sys
from pathlib import Path
from agentbox_runtime.waw_activation import WAWActivationError, load_waw_activated_sockets

root = Path(sys.argv[1])
listeners = {}
for name in ("control", "stream"):
    path = root / f"{name}.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen(4)
    path.chmod(0o660)
    listeners[name] = listener.detach()
order = ("control", "stream") if sys.argv[2] == "control-first" else ("stream", "control")
held = [os.dup(listeners[name]) for name in order]
for target, source in zip((3, 4), held):
    os.dup2(source, target)
for source in held:
    os.close(source)
os.environ["LISTEN_PID"] = str(os.getpid())
os.environ["LISTEN_FDS"] = "2"
os.environ["LISTEN_FDNAMES"] = sys.argv[3]
try:
    sockets = load_waw_activated_sockets(
        expected_uid=os.geteuid(), expected_gid=os.getegid(),
        control_path=str(root / "control.sock"), stream_path=str(root / "stream.sock"),
    )
except WAWActivationError as exc:
    print(str(exc), repr(exc.__cause__), file=sys.stderr)
    print("rejected")
else:
    print(sockets.control.getsockname(), sockets.stream.getsockname())
    sockets.close()
"""
    with tempfile.TemporaryDirectory(prefix="abw-", dir="/tmp") as directory:
        completed = subprocess.run(
            [sys.executable, "-c", child, directory, fd_order, names],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        if accepted:
            assert (
                completed.stdout.strip() == f"{directory}/control.sock {directory}/stream.sock"
            ), completed.stderr
        else:
            assert completed.stdout.strip() == "rejected"


@pytest.mark.skipif(sys.platform != "linux", reason="Linux AF_UNIX SO_ACCEPTCONN contract")
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


@pytest.mark.skipif(sys.platform != "linux", reason="Linux AF_UNIX SO_ACCEPTCONN contract")
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


@pytest.mark.skipif(sys.platform != "linux", reason="Linux AF_UNIX SO_ACCEPTCONN contract")
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


@pytest.mark.skipif(sys.platform != "linux", reason="Linux AF_UNIX SO_ACCEPTCONN contract")
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
