"""Fail-closed loader for the two systemd-precreated WAW sockets.

The loader consumes only the exact descriptor set owned by
``agentbox-waw.target``.  It never binds, listens, unlinks, or replaces a
socket pathname, and it treats LISTEN_* environment values as consistency
hints that must agree with descriptor inspection.
"""

from __future__ import annotations

import os
import socket
import stat
from dataclasses import dataclass
from pathlib import Path

_CONTROL_NAME = "agentbox-waw-control"
_STREAM_NAME = "agentbox-waw-stream"
_CONTROL_PATH = "/run/agentbox-waw/workspace-control.sock"
_STREAM_PATH = "/run/agentbox-waw/workspace-stream.sock"


class WAWActivationError(RuntimeError):
    """The inherited WAW descriptor set is incomplete or untrusted."""


@dataclass(frozen=True)
class WAWActivatedSockets:
    control: socket.socket
    stream: socket.socket

    def close(self) -> None:
        self.control.close()
        self.stream.close()


def load_waw_activated_sockets(
    *,
    expected_uid: int,
    expected_gid: int,
    control_path: str = _CONTROL_PATH,
    stream_path: str = _STREAM_PATH,
) -> WAWActivatedSockets:
    """Adopt exactly two validated systemd descriptors (FD 3 and FD 4)."""

    if type(expected_uid) is not int or expected_uid < 0:
        raise ValueError("expected_uid must be a non-negative integer")
    if type(expected_gid) is not int or expected_gid < 0:
        raise ValueError("expected_gid must be a non-negative integer")
    if not control_path.startswith("/") or not stream_path.startswith("/"):
        raise ValueError("WAW socket paths must be absolute")
    if control_path == stream_path:
        raise ValueError("WAW socket paths must be distinct")
    if os.environ.get("LISTEN_PID") != str(os.getpid()):
        raise WAWActivationError("systemd LISTEN_PID is missing or mismatched")
    if os.environ.get("LISTEN_FDS") != "2":
        raise WAWActivationError("WAW socket descriptor count is incomplete")
    names = os.environ.get("LISTEN_FDNAMES", "").split(":")
    if names != [_CONTROL_NAME, _STREAM_NAME]:
        raise WAWActivationError("WAW socket descriptor names are incomplete or reordered")

    sockets: list[socket.socket] = []
    try:
        for fd, expected_path in ((3, control_path), (4, stream_path)):
            sock: socket.socket | None = None
            try:
                sock = socket.socket(fileno=fd)
                sock.set_inheritable(False)
                _validate_socket(sock, expected_path, expected_uid, expected_gid)
            except (OSError, ValueError, WAWActivationError) as exc:
                if sock is not None:
                    sock.close()
                raise WAWActivationError("WAW socket descriptor provenance is invalid") from exc
            sockets.append(sock)
        first = os.stat(control_path, follow_symlinks=False)
        second = os.stat(stream_path, follow_symlinks=False)
        if (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino):
            raise WAWActivationError("WAW control and stream descriptors are duplicated")
        return WAWActivatedSockets(control=sockets[0], stream=sockets[1])
    except Exception:
        for sock in sockets:
            sock.close()
        raise


def _validate_socket(
    sock: socket.socket, expected_path: str, expected_uid: int, expected_gid: int
) -> None:
    if sock.family != socket.AF_UNIX or sock.type != socket.SOCK_STREAM:
        raise WAWActivationError("WAW descriptor is not AF_UNIX SOCK_STREAM")
    if sock.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) != 1:
        raise WAWActivationError("WAW descriptor is not listening")
    actual = sock.getsockname()
    if isinstance(actual, bytes):
        actual = actual.decode("utf-8")
    if actual != expected_path:
        raise WAWActivationError("WAW descriptor pathname does not match activation map")
    details = os.lstat(Path(expected_path))
    descriptor = os.fstat(sock.fileno())
    if (
        not stat.S_ISSOCK(details.st_mode)
        or not stat.S_ISSOCK(descriptor.st_mode)
        or (details.st_dev, details.st_ino) != (descriptor.st_dev, descriptor.st_ino)
        or details.st_uid != expected_uid
        or details.st_gid != expected_gid
        or descriptor.st_uid != expected_uid
        or descriptor.st_gid != expected_gid
        or stat.S_IMODE(details.st_mode) != 0o660
    ):
        raise WAWActivationError("WAW socket pathname provenance is invalid")


__all__ = ["WAWActivatedSockets", "WAWActivationError", "load_waw_activated_sockets"]
