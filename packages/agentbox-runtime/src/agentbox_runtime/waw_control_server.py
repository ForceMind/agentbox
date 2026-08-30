"""Strict dispatcher for the dedicated WAW control Unix socket.

The socket is supplied by the caller (normally a pre-created systemd
descriptor).  This module never binds, unlinks, replaces, or otherwise
manages a socket pathname, and it performs no workspace side effects itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import socket
import struct
import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

from agentbox_protocol.waw_control import (
    MAX_CONTROL_ENVELOPE,
    MAX_CONTROL_LINE,
    WAWControlError,
    decode_control_request,
    encode_control_response,
)

_REQUEST_ID = re.compile(rb"wreq_[0-9a-f]{32}")


class WAWControlDispatchError(RuntimeError):
    """A bounded, normalized error returned by an injected dispatcher."""

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


Dispatch = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class WAWControlServer:
    """One-request/one-response WAW control listener over an existing socket."""

    def __init__(
        self,
        sock: socket.socket,
        dispatch: Dispatch,
        *,
        expected_peer_uid: int,
        expected_peer_gid: int,
        timeout_seconds: float = 2.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if sock.family != socket.AF_UNIX or sock.type != socket.SOCK_STREAM:
            raise ValueError("WAW control socket must be AF_UNIX SOCK_STREAM")
        if sock.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) != 1:
            raise ValueError("WAW control socket must already be listening")
        if sock.get_inheritable():
            raise ValueError("WAW control socket must be close-on-exec")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if type(expected_peer_uid) is not int or expected_peer_uid < 0:
            raise ValueError("expected_peer_uid must be a non-negative integer")
        if type(expected_peer_gid) is not int or expected_peer_gid < 0:
            raise ValueError("expected_peer_gid must be a non-negative integer")
        self._sock = sock
        self._dispatch = dispatch
        self._timeout_seconds = timeout_seconds
        self._expected_peer_uid = expected_peer_uid
        self._expected_peer_gid = expected_peer_gid
        self._monotonic = monotonic
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("WAW control server is already started")
        self._sock.setblocking(False)
        self._server = await asyncio.start_unix_server(
            self._handle,
            sock=self._sock,
            start_serving=True,
            limit=MAX_CONTROL_LINE + 1,
        )

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        deadline = self._monotonic() + self._timeout_seconds
        peer_pidfd: int | None = None
        try:
            peer_pidfd = self._peer_pidfd(writer)
            if peer_pidfd is None:
                return
            try:
                raw = await self._with_deadline(reader.readline(), deadline)
            except asyncio.LimitOverrunError:
                return
            request_id = self._request_id(raw)
            if not raw or len(raw) > MAX_CONTROL_LINE or not raw.endswith(b"\n"):
                await self._send_error(writer, request_id, "PROTOCOL_INVALID", deadline=deadline)
                return
            try:
                request = decode_control_request(raw)
            except WAWControlError:
                await self._send_error(writer, request_id, "PROTOCOL_INVALID", deadline=deadline)
                return
            # A control connection carries exactly one request.  A short
            # bounded probe catches concatenated/trailing bytes without
            # keeping an otherwise idle client open for the full deadline.
            try:
                trailing = await self._with_deadline(
                    reader.read(1), min(deadline, self._monotonic() + 0.01)
                )
            except TimeoutError:
                trailing = b""
            if trailing:
                await self._send_error(
                    writer, request["request_id"], "PROTOCOL_INVALID", deadline=deadline
                )
                return
            try:
                response = await self._with_deadline(self._dispatch(request), deadline)
            except WAWControlDispatchError as exc:
                response = self._error(request["request_id"], exc.code, exc.retryable)
            except TimeoutError:
                response = self._error(request["request_id"], "INTERNAL_BOUNDED", True)
            except Exception:
                response = self._error(request["request_id"], "INTERNAL_BOUNDED", False)
            if (
                not isinstance(response, dict)
                or response.get("request_id") != request["request_id"]
            ):
                response = self._error(request["request_id"], "INTERNAL_BOUNDED", False)
            try:
                encoded = encode_control_response(response, request["action"])
            except WAWControlError:
                encoded = self._error_bytes(request["request_id"], "INTERNAL_BOUNDED", False)
            if len(encoded) > MAX_CONTROL_ENVELOPE:
                encoded = self._error_bytes(request["request_id"], "INTERNAL_BOUNDED", False)
            writer.write(encoded)
            await self._with_deadline(writer.drain(), deadline)
        except (OSError, TimeoutError):
            # The peer may have disappeared or the bounded deadline expired;
            # no retry or side effect is attempted by this transport layer.
            return
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
            if peer_pidfd is not None:
                with contextlib.suppress(OSError):
                    os.close(peer_pidfd)

    def _peer_pidfd(self, writer: asyncio.StreamWriter) -> int | None:
        peer_socket = writer.get_extra_info("socket")
        if peer_socket is None or not hasattr(peer_socket, "getsockopt"):
            return None
        try:
            raw = cast(
                bytes,
                peer_socket.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
                ),
            )
            pid, uid, gid = cast(tuple[int, int, int], struct.unpack("3i", raw))
        except (AttributeError, OSError, struct.error):
            return None
        if uid != self._expected_peer_uid or gid != self._expected_peer_gid:
            return None
        try:
            return os.pidfd_open(pid, 0)
        except (OSError, OverflowError, ValueError):
            return None

    async def _send_error(
        self, writer: asyncio.StreamWriter, request_id: str | None, code: str, *, deadline: float
    ) -> None:
        if request_id is None:
            return
        writer.write(self._error_bytes(request_id, code, False))
        with contextlib.suppress(OSError, TimeoutError, asyncio.TimeoutError):
            await self._with_deadline(writer.drain(), deadline)

    @staticmethod
    def _error(request_id: str, code: str, retryable: bool) -> dict[str, Any]:
        return {
            "protocol_version": 1,
            "request_id": request_id,
            "status": "ERROR",
            "error_code": code,
            "retryable": retryable,
        }

    @classmethod
    def _error_bytes(cls, request_id: str, code: str, retryable: bool) -> bytes:
        return (
            json.dumps(
                cls._error(request_id, code, retryable), separators=(",", ":"), allow_nan=False
            ).encode()
            + b"\n"
        )

    @staticmethod
    def _request_id(raw: bytes) -> str | None:
        match = _REQUEST_ID.search(raw)
        return match.group().decode("ascii") if match else None

    async def _with_deadline(self, awaitable: Any, deadline: float) -> Any:
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            if hasattr(awaitable, "close"):
                awaitable.close()
            raise TimeoutError("WAW control deadline exceeded")
        return await asyncio.wait_for(awaitable, timeout=remaining)


__all__ = ["Dispatch", "WAWControlDispatchError", "WAWControlServer"]
