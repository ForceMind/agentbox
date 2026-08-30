"""Bounded API-side client for the dedicated WAW control socket.

This client is intentionally a one-request/one-response transport.  It never
opens the legacy Runtime socket, unlinks socket paths, or exposes a generic
action gateway to callers.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
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


def validate_runtime_bind_attestation(
    response: dict[str, Any],
    *,
    expected_runtime_host_installation_id: str,
    expected_runtime_host_installation_revision: str,
    expected_host_manifest_digest: str,
    expected_project_root_manifest_digest: str,
    expected_runtime_epoch: str | None = None,
) -> dict[str, Any]:
    """Require a bind response to match the locally trusted host anchor."""

    if response.get("status") not in {"BOUND", "ALREADY_BOUND"}:
        raise WAWControlClientError(
            "RUNTIME_INSTALLATION_MISMATCH", "Runtime did not provide a bound attestation"
        )
    checks = (
        ("runtime_host_installation_id", expected_runtime_host_installation_id),
        ("runtime_host_installation_revision", expected_runtime_host_installation_revision),
        ("host_manifest_digest", expected_host_manifest_digest),
        ("project_root_manifest_digest", expected_project_root_manifest_digest),
    )
    for field, expected in checks:
        actual = response.get(field)
        if not isinstance(actual, str) or not hmac.compare_digest(actual, expected):
            raise WAWControlClientError(
                "RUNTIME_INSTALLATION_MISMATCH", "Runtime bind attestation does not match anchor"
            )
    if expected_runtime_epoch is not None:
        actual_epoch = response.get("runtime_epoch")
        if not isinstance(actual_epoch, str) or not hmac.compare_digest(
            actual_epoch, expected_runtime_epoch
        ):
            raise WAWControlClientError(
                "RUNTIME_INSTALLATION_MISMATCH", "Runtime epoch does not match anchor"
            )
    return response


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
        cancellation_grace_seconds: float = 0.05,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(socket_path, Path):
            raise TypeError("socket_path must be a Path")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if cancellation_grace_seconds <= 0:
            raise ValueError("cancellation_grace_seconds must be positive")
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
        self._cancellation_grace_seconds = cancellation_grace_seconds
        self._monotonic = monotonic
        # A cancellation-resistant operation can outlive its request.  Such
        # a client must not be used again until its owner has explicitly
        # re-established the Runtime connection/epoch.
        self._poisoned = False

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    @property
    def poisoned(self) -> bool:
        """Whether a timed-out operation may still be mutating transport state."""

        return self._poisoned

    async def reconnect(self) -> None:
        """Clear the fail-closed transport fence after external reconnect."""

        self._poisoned = False

    async def request(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
        """Send one validated request and decode its matching response."""

        if self._poisoned:
            raise WAWControlClientError(
                "RUNTIME_UNAVAILABLE",
                "WAW Runtime control transport is poisoned; reconnect is required",
                retryable=True,
            )

        peer_pidfd: int | None = None
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
            peer_pidfd = self._peer_pidfd(writer)
            if peer_pidfd is None:
                raise WAWControlClientError(
                    "RUNTIME_PEER_FORBIDDEN", "WAW Runtime peer credentials are not trusted"
                )
            writer.write(encoded)
            await self._with_deadline(writer.drain(), deadline)
            try:
                raw = await self._with_deadline(reader.readline(), deadline)
            except (asyncio.LimitOverrunError, ValueError) as exc:
                raise WAWControlClientError(
                    "PROTOCOL_INVALID", "WAW control response exceeds its bounded line limit"
                ) from exc
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
            await self._close_writer(writer)
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

    def _poison(self) -> None:
        self._poisoned = True

    async def _close_writer(self, writer: asyncio.StreamWriter) -> None:
        """Close without allowing a broken wait_closed() to hold the request."""

        with contextlib.suppress(OSError, RuntimeError):
            writer.close()
        try:
            close_wait = writer.wait_closed()
        except (OSError, RuntimeError):
            return
        task = asyncio.ensure_future(close_wait)
        try:
            _done, pending = await asyncio.wait({task}, timeout=self._cancellation_grace_seconds)
        except asyncio.CancelledError:
            self._poison()
            task.cancel()
            with contextlib.suppress(BaseException):
                await asyncio.shield(self._finish_cancel(task))
            raise
        if pending:
            self._poison()
            task.cancel()
            task.add_done_callback(self._consume_late_task)
        else:
            with contextlib.suppress(BaseException):
                task.result()

    @staticmethod
    def _consume_late_task(task: asyncio.Future[Any]) -> None:
        with contextlib.suppress(BaseException):
            task.result()

    async def _with_deadline(self, awaitable: Any, deadline: float) -> Any:
        """Await with a hard deadline and bounded cancellation cleanup.

        ``asyncio.wait_for`` may itself exceed its timeout while waiting for a
        cancellation-resistant coroutine to acknowledge cancellation.  Keep
        the request bounded by detaching that operation after a short grace
        period and poison this client so no later request can reuse it.
        """

        remaining = deadline - self._monotonic()
        if remaining <= 0:
            self._poison()
            if hasattr(awaitable, "close"):
                awaitable.close()
            raise TimeoutError("WAW control deadline exceeded")
        task = asyncio.ensure_future(awaitable)
        try:
            done, _pending = await asyncio.wait({task}, timeout=remaining)
        except asyncio.CancelledError:
            self._poison()
            task.cancel()
            with contextlib.suppress(BaseException):
                await asyncio.shield(self._finish_cancel(task))
            raise
        if done:
            return task.result()

        self._poison()
        task.cancel()
        _cancelled_done, cancelled_pending = await asyncio.wait(
            {task}, timeout=self._cancellation_grace_seconds
        )
        if cancelled_pending:
            self._poison()
            # The task owns the operation and may finish later.  Consume its
            # eventual exception without keeping the request alive.
            task.add_done_callback(self._consume_late_task)
        else:
            with contextlib.suppress(BaseException):
                task.result()
        raise TimeoutError("WAW control deadline exceeded")

    async def _finish_cancel(self, task: asyncio.Future[Any]) -> None:
        """Give cancellation a small grace window, never joining indefinitely."""

        _done, pending = await asyncio.wait({task}, timeout=self._cancellation_grace_seconds)
        if pending:
            task.add_done_callback(self._consume_late_task)


__all__ = [
    "WAWControlClient",
    "WAWControlClientError",
    "WAWSocketPathIdentity",
    "validate_runtime_bind_attestation",
]
