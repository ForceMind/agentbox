"""Bounded API-side client for the dedicated WAW control socket.

This client is intentionally a one-request/one-response transport.  It never
opens the legacy Runtime socket, unlinks socket paths, or exposes a generic
action gateway to callers.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import stat
import struct
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from agentbox_protocol.waw_control import (
    MAX_CONTROL_ENVELOPE,
    MAX_CONTROL_LINE,
    WAWControlError,
    decode_control_response,
    encode_control_request,
)


class WAWControlClientError(RuntimeError):
    """Transport or protocol failure talking to the WAW Runtime endpoint."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class WAWSocketPathIdentity:
    """Stable identity observed for a root-owned Unix socket path."""

    device: int
    inode: int


def _check_socket_path(
    path: Path, *, expected_uid: int, expected_gid: int, expected_mode: int
) -> WAWSocketPathIdentity:
    """Reject symlink/socket replacement and unexpected DAC ownership before I/O."""

    try:
        parent = path.parent
        parent_stat = os.lstat(parent)
        details = os.lstat(path)
    except OSError as exc:
        raise WAWControlClientError(
            "RUNTIME_UNAVAILABLE",
            "WAW Runtime control socket provenance is unavailable",
            retryable=True,
        ) from exc
    if (
        not stat.S_ISDIR(parent_stat.st_mode)
        or stat.S_ISLNK(parent_stat.st_mode)
        or not stat.S_ISSOCK(details.st_mode)
        or details.st_uid != expected_uid
        or details.st_gid != expected_gid
        or stat.S_IMODE(details.st_mode) != expected_mode
    ):
        raise WAWControlClientError(
            "WAW_SOCKET_PROVENANCE_INVALID", "WAW Runtime control socket provenance is invalid"
        )
    return WAWSocketPathIdentity(details.st_dev, details.st_ino)


class WAWControlClient:
    """Issue one strict control request on a dedicated Unix socket."""

    def __init__(
        self,
        socket_path: Path,
        *,
        expected_peer_uid: int,
        expected_peer_gid: int,
        expected_socket_uid: int,
        expected_socket_gid: int,
        expected_socket_mode: int = 0o660,
        timeout_seconds: float = 2.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(socket_path, Path):
            raise TypeError("socket_path must be a Path")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if type(expected_peer_uid) is not int or expected_peer_uid < 0:
            raise ValueError("expected_peer_uid must be a non-negative integer")
        if type(expected_peer_gid) is not int or expected_peer_gid < 0:
            raise ValueError("expected_peer_gid must be a non-negative integer")
        if type(expected_socket_uid) is not int or expected_socket_uid < 0:
            raise ValueError("expected_socket_uid must be a non-negative integer")
        if type(expected_socket_gid) is not int or expected_socket_gid < 0:
            raise ValueError("expected_socket_gid must be a non-negative integer")
        if type(expected_socket_mode) is not int or not 0 <= expected_socket_mode <= 0o7777:
            raise ValueError("expected_socket_mode must be an octal file mode")
        self._socket_path = socket_path
        self._expected_peer_uid = expected_peer_uid
        self._expected_peer_gid = expected_peer_gid
        self._expected_socket_uid = expected_socket_uid
        self._expected_socket_gid = expected_socket_gid
        self._expected_socket_mode = expected_socket_mode
        self._timeout_seconds = timeout_seconds
        self._monotonic = monotonic

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    async def request(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
        """Send one validated request and decode its matching response."""

        try:
            encoded = encode_control_request(request)
            request_id = request["request_id"]
        except (KeyError, WAWControlError, TypeError, ValueError) as exc:
            raise WAWControlClientError(
                "PROTOCOL_INVALID", "WAW control request is invalid"
            ) from exc
        if request.get("action") != action:
            raise WAWControlClientError(
                "PROTOCOL_INVALID", "WAW control action does not match request"
            )
        if len(encoded) > MAX_CONTROL_LINE or len(encoded) > MAX_CONTROL_ENVELOPE:
            raise WAWControlClientError("PROTOCOL_INVALID", "WAW control request is oversized")

        deadline = self._monotonic() + self._timeout_seconds
        before_path = _check_socket_path(
            self._socket_path,
            expected_uid=self._expected_socket_uid,
            expected_gid=self._expected_socket_gid,
            expected_mode=self._expected_socket_mode,
        )
        reader: asyncio.StreamReader
        writer: asyncio.StreamWriter
        try:
            reader, writer = await self._with_deadline(
                asyncio.open_unix_connection(self._socket_path, limit=MAX_CONTROL_LINE + 1),
                deadline,
            )
        except (OSError, TimeoutError) as exc:
            raise WAWControlClientError(
                "RUNTIME_UNAVAILABLE", "WAW Runtime control endpoint is unavailable", retryable=True
            ) from exc
        try:
            after_path = _check_socket_path(
                self._socket_path,
                expected_uid=self._expected_socket_uid,
                expected_gid=self._expected_socket_gid,
                expected_mode=self._expected_socket_mode,
            )
            if after_path != before_path:
                raise WAWControlClientError(
                    "WAW_SOCKET_PROVENANCE_INVALID", "WAW Runtime socket changed during connect"
                )
            if not self._peer_is_expected(writer):
                raise WAWControlClientError(
                    "RUNTIME_PEER_FORBIDDEN", "WAW Runtime peer credentials are not trusted"
                )
            writer.write(encoded)
            await self._with_deadline(writer.drain(), deadline)
            raw = await self._with_deadline(reader.readline(), deadline)
            if not raw or len(raw) > MAX_CONTROL_LINE or not raw.endswith(b"\n"):
                raise WAWControlClientError(
                    "PROTOCOL_INVALID", "WAW control response framing is invalid"
                )
            try:
                response = decode_control_response(raw, action, expected_request_id=request_id)
            except WAWControlError as exc:
                raise WAWControlClientError(
                    "PROTOCOL_INVALID", "WAW control response is invalid"
                ) from exc
            # The listener closes after the single response.  Any byte after
            # that response would represent a concatenated/trailed record.
            try:
                trailing = await self._with_deadline(reader.read(1), deadline)
            except TimeoutError as exc:
                raise WAWControlClientError(
                    "PROTOCOL_INVALID", "WAW control response did not terminate"
                ) from exc
            if trailing:
                raise WAWControlClientError(
                    "PROTOCOL_INVALID", "WAW control response has trailing bytes"
                )
            return response
        except (OSError, TimeoutError) as exc:
            raise WAWControlClientError(
                "RUNTIME_UNAVAILABLE", "WAW Runtime control request timed out", retryable=True
            ) from exc
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()

    def _peer_is_expected(self, writer: asyncio.StreamWriter) -> bool:
        peer_socket = writer.get_extra_info("socket")
        if peer_socket is None or not hasattr(peer_socket, "getsockopt"):
            return False
        try:
            raw = cast(
                bytes,
                peer_socket.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
                ),
            )
            _pid, uid, gid = cast(tuple[int, int, int], struct.unpack("3i", raw))
        except (AttributeError, OSError, struct.error):
            return False
        return bool(uid == self._expected_peer_uid and gid == self._expected_peer_gid)

    async def _with_deadline(self, awaitable: Any, deadline: float) -> Any:
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            if hasattr(awaitable, "close"):
                awaitable.close()
            raise TimeoutError("WAW control deadline exceeded")
        return await asyncio.wait_for(awaitable, timeout=remaining)


__all__ = ["WAWControlClient", "WAWControlClientError", "WAWSocketPathIdentity"]
