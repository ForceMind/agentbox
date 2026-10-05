"""A3-only bounded I/O over supplied connected UDS; never a connector/authority.

The trusted caller authenticates the socket with its existing pidfd authority.
This module owns only framing, exact directional sequences and absolute I/O bounds.
"""

from __future__ import annotations

import asyncio
import contextvars
import select
import socket
import threading
import time
from collections.abc import Callable
from contextlib import suppress

from agentbox_protocol.a3_content import ContentError
from agentbox_protocol.a3_transport import (
    HEADER_BYTES,
    NativeFrame,
    NativeKind,
    decode_frame,
    decode_header,
    encode_frame,
)

Guard = Callable[[], None]
# Nested guards/RPCs inherit the current absolute I/O budget, never renew it.
NATIVE_IO_DEADLINE: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "a3_native_io_deadline", default=None
)


def deadline_after(seconds: float, *, cap_ns: int | None = None) -> int:
    deadline = time.monotonic_ns() + int(seconds * 1_000_000_000)
    return deadline if cap_ns is None else min(deadline, cap_ns)


class NativeChannel:
    """One nonblocking connected stream, one reader and one writer, no worker pool."""

    def __init__(self, sock: socket.socket, check_current: Guard) -> None:
        if (
            type(sock) is not socket.socket
            or sock.family != socket.AF_UNIX
            or sock.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM
            or not callable(check_current)
        ):
            raise ContentError("PATCH_REVOKED")
        sock.getpeername()
        sock.set_inheritable(False)
        sock.setblocking(False)
        # Linux reports twice the requested budget for bookkeeping overhead.
        # Both directions remain bounded independently of userspace frame limits.
        for option in (socket.SO_SNDBUF, socket.SO_RCVBUF):
            sock.setsockopt(socket.SOL_SOCKET, option, 32768)
            if not 0 < sock.getsockopt(socket.SOL_SOCKET, option) <= 65536:
                raise ContentError("PATCH_UNAVAILABLE_CONFIG")
        self._socket = sock
        self._current = check_current
        self._send_lock = threading.Lock()
        self._receive_lock = threading.Lock()
        self._send_sequence = 1
        self._receive_sequence = 1
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def shutdown_complete(self) -> bool:
        """Fencing alone is not descriptor cleanup; owners retain capacity until true."""
        return (
            self._closed
            and self._socket.fileno() < 0
            and not self._send_lock.locked()
            and not self._receive_lock.locked()
        )

    def check(self) -> None:
        if self._closed:
            raise ContentError("PATCH_REVOKED")
        self._current()
        if self._closed:
            raise ContentError("PATCH_REVOKED")

    def close(self) -> None:
        self._closed = True
        with suppress(OSError):
            self._socket.shutdown(socket.SHUT_RDWR)
        self._final_close()

    def _final_close(self) -> None:
        # Keep the descriptor allocated until exact-owner loop registrations are
        # removed. A closed/reused numeric fd must never lose its new watcher.
        if self._closed and not self._send_lock.locked() and not self._receive_lock.locked():
            with suppress(OSError):
                self._socket.close()

    def _check(self, deadline_ns: int, guard: Guard | None) -> float:
        self.check()
        if guard is not None:
            inherited = NATIVE_IO_DEADLINE.get()
            token = NATIVE_IO_DEADLINE.set(
                deadline_ns if inherited is None else min(deadline_ns, inherited)
            )
            try:
                guard()
            finally:
                NATIVE_IO_DEADLINE.reset(token)
        self.check()
        remaining = (deadline_ns - time.monotonic_ns()) / 1_000_000_000
        if remaining <= 0:
            raise ContentError("PATCH_TIMEOUT")
        return remaining

    def _wait(self, write: bool, deadline_ns: int, guard: Guard | None) -> None:
        while True:
            remaining = self._check(deadline_ns, guard)
            readable, writable, exceptional = select.select(
                [] if write else [self._socket],
                [self._socket] if write else [],
                [self._socket],
                min(remaining, 0.05),
            )
            # The owning send/receive checks immediately before its syscall.
            # An idle iteration rechecks at the top before its next bounded wait.
            if exceptional:
                raise ContentError("PATCH_REVOKED")
            if readable or writable:
                return

    def wait_readable(self, deadline_ns: int, guard: Guard | None = None) -> None:
        self._enter(self._receive_lock)
        try:
            self._wait(False, deadline_ns, guard)
            self._check(deadline_ns, guard)
        except BaseException:
            self.close()
            raise
        finally:
            self._receive_lock.release()
            self._final_close()

    async def _await(self, write: bool, deadline_ns: int, guard: Guard | None) -> None:
        loop = asyncio.get_running_loop()
        while True:
            remaining = self._check(deadline_ns, guard)
            future: asyncio.Future[None] = loop.create_future()
            fd = self._socket.fileno()

            def ready(pending: asyncio.Future[None] = future) -> None:
                if not pending.done():
                    pending.set_result(None)

            if write:
                loop.add_writer(fd, ready)
            else:
                loop.add_reader(fd, ready)
            try:
                done, _ = await asyncio.wait({future}, timeout=min(remaining, 0.05))
            finally:
                if write:
                    loop.remove_writer(fd)
                else:
                    loop.remove_reader(fd)
                if not future.done():
                    future.cancel()
            # The syscall owner performs the final full guard without an await
            # before I/O; a timeout iteration rechecks at the top of this loop.
            if done:
                return

    async def await_readable(self, deadline_ns: int, guard: Guard | None = None) -> None:
        self._enter(self._receive_lock)
        try:
            await self._await(False, deadline_ns, guard)
            self._check(deadline_ns, guard)
        except BaseException:
            self.close()
            raise
        finally:
            self._receive_lock.release()
            self._final_close()

    def _enter(self, lock: threading.Lock) -> None:
        if not lock.acquire(blocking=False):
            self.close()
            raise ContentError()

    def send(
        self,
        kind: NativeKind,
        payload: dict[str, object] | bytes,
        *,
        deadline_ns: int,
        guard: Guard | None = None,
    ) -> None:
        self._enter(self._send_lock)
        try:
            raw = encode_frame(kind, self._send_sequence, payload)
            view = memoryview(raw)
            while view:
                self._wait(True, deadline_ns, guard)
                self._check(deadline_ns, guard)
                try:
                    count = self._socket.send(view)
                except BlockingIOError:
                    continue
                if count <= 0:
                    raise ContentError("PATCH_REVOKED")
                view = view[count:]
            self._send_sequence += 1
        except BaseException:
            self.close()
            raise
        finally:
            self._send_lock.release()
            self._final_close()

    async def asend(
        self,
        kind: NativeKind,
        payload: dict[str, object] | bytes,
        *,
        deadline_ns: int,
        guard: Guard | None = None,
    ) -> None:
        self._enter(self._send_lock)
        try:
            raw = encode_frame(kind, self._send_sequence, payload)
            view = memoryview(raw)
            while view:
                await self._await(True, deadline_ns, guard)
                self._check(deadline_ns, guard)
                try:
                    count = self._socket.send(view)
                except BlockingIOError:
                    continue
                if count <= 0:
                    raise ContentError("PATCH_REVOKED")
                view = view[count:]
            self._send_sequence += 1
        except BaseException:
            self.close()
            raise
        finally:
            self._send_lock.release()
            self._final_close()

    def _header(self, raw: bytes, expected: frozenset[NativeKind]) -> int:
        kind, sequence, length = decode_header(raw)
        if kind not in expected or sequence != self._receive_sequence:
            raise ContentError()
        return length

    def receive(
        self, expected: frozenset[NativeKind], *, deadline_ns: int, guard: Guard | None = None
    ) -> NativeFrame:
        self._enter(self._receive_lock)
        try:
            raw = bytearray()
            target = HEADER_BYTES
            while len(raw) < target:
                self._wait(False, deadline_ns, guard)
                self._check(deadline_ns, guard)
                try:
                    part = self._socket.recv(target - len(raw))
                except BlockingIOError:
                    continue
                if not part:
                    raise ContentError("PATCH_REVOKED")
                raw.extend(part)
                if len(raw) == HEADER_BYTES and target == HEADER_BYTES:
                    target += self._header(bytes(raw), expected)
            result = decode_frame(bytes(raw))
            self._check(deadline_ns, guard)
            self._receive_sequence += 1
            return result
        except BaseException:
            self.close()
            raise
        finally:
            self._receive_lock.release()
            self._final_close()

    async def areceive(
        self, expected: frozenset[NativeKind], *, deadline_ns: int, guard: Guard | None = None
    ) -> NativeFrame:
        self._enter(self._receive_lock)
        try:
            raw = bytearray()
            target = HEADER_BYTES
            while len(raw) < target:
                await self._await(False, deadline_ns, guard)
                self._check(deadline_ns, guard)
                try:
                    part = self._socket.recv(target - len(raw))
                except BlockingIOError:
                    continue
                if not part:
                    raise ContentError("PATCH_REVOKED")
                raw.extend(part)
                if len(raw) == HEADER_BYTES and target == HEADER_BYTES:
                    target += self._header(bytes(raw), expected)
            result = decode_frame(bytes(raw))
            self._check(deadline_ns, guard)
            self._receive_sequence += 1
            return result
        except BaseException:
            self.close()
            raise
        finally:
            self._receive_lock.release()
            self._final_close()
