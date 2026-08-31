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


class _WAWControlDispatchPoisoned(TimeoutError):
    """The dispatcher did not stop within the bounded cancellation grace."""


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
        cancellation_grace_seconds: float = 0.05,
        max_active_connections: int = 64,
        max_active_dispatches: int = 16,
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
        if cancellation_grace_seconds <= 0:
            raise ValueError("cancellation_grace_seconds must be positive")
        if type(max_active_connections) is not int or max_active_connections <= 0:
            raise ValueError("max_active_connections must be a positive integer")
        if type(max_active_dispatches) is not int or max_active_dispatches <= 0:
            raise ValueError("max_active_dispatches must be a positive integer")
        if type(expected_peer_uid) is not int or expected_peer_uid < 0:
            raise ValueError("expected_peer_uid must be a non-negative integer")
        if type(expected_peer_gid) is not int or expected_peer_gid < 0:
            raise ValueError("expected_peer_gid must be a non-negative integer")
        self._sock = sock
        self._dispatch = dispatch
        self._timeout_seconds = timeout_seconds
        self._cancellation_grace_seconds = cancellation_grace_seconds
        self._max_active_connections = max_active_connections
        self._max_active_dispatches = max_active_dispatches
        self._expected_peer_uid = expected_peer_uid
        self._expected_peer_gid = expected_peer_gid
        self._monotonic = monotonic
        self._server: asyncio.AbstractServer | None = None
        self._poisoned = False
        self._closing = False
        self._connection_tasks: set[asyncio.Task[Any]] = set()
        self._writers: set[asyncio.StreamWriter] = set()
        self._dispatch_tasks: set[asyncio.Task[Any]] = set()
        self._io_tasks: set[asyncio.Task[Any]] = set()
        # Detached cleanup observers cannot be interrupted by a second
        # cancellation of the connection/close task.
        self._cleanup_tasks: set[asyncio.Task[Any]] = set()
        # ``close`` is itself a bounded, independently owned operation.  A
        # caller cancelling its await must not cancel the cleanup operation
        # half way through (or make a later close report a false clean
        # state).
        self._close_operation: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("WAW control server is already started")
        if self._poisoned:
            raise RuntimeError("WAW control server is poisoned")
        self._closing = False
        self._sock.setblocking(False)
        self._server = await asyncio.start_unix_server(
            self._handle,
            sock=self._sock,
            start_serving=True,
            limit=MAX_CONTROL_LINE + 1,
        )

    async def close(self) -> None:
        operation = self._close_operation
        if operation is None or operation.done():
            operation = asyncio.create_task(self._perform_close())
            self._close_operation = operation
            self._cleanup_tasks.add(operation)
            operation.add_done_callback(self._consume_cleanup_task)
        try:
            # Shield the operation from cancellation of this caller.  The
            # operation owns all cleanup and remains observable through the
            # registries until every child reaches a terminal state.
            await asyncio.shield(operation)
        except asyncio.CancelledError:
            # Cancellation is a fail-closed event.  Do not claim that close
            # completed: the independent operation continues and will mark
            # the listener poisoned if any bounded cleanup remains pending.
            # Keep the close operation and any I/O child it currently owns
            # out of the poison cancellation set.  Cancelling those tasks
            # here would defeat the shield and turn caller cancellation into
            # cancellation of the cleanup operation itself.
            self._poison_listener(exclude={operation, *self._io_tasks})
            raise

    async def _perform_close(self) -> None:
        """Run close in an independently owned cancellation quarantine.

        ``shield`` protects the worker from the normal caller cancellation,
        but a direct task cancellation (loop teardown or an accidental owner
        reference) can still reach the worker.  Consume that cancellation,
        clear the worker's cancellation state, and make one more bounded
        cleanup pass.  The worker then returns a poisoned/incomplete state
        rather than exposing a cancelled cleanup task to ``close`` callers.
        """
        for attempt in range(2):
            try:
                await self._perform_close_body()
                return
            except asyncio.CancelledError:
                current = asyncio.current_task()
                self._poison_listener(exclude={current} if current is not None else set())
                if current is not None:
                    while current.cancelling():
                        current.uncancel()
                if attempt == 1:
                    self._closing = True
                    return

    async def _perform_close_body(self) -> None:
        self._closing = True
        if self._server is not None:
            self._server.close()
            try:
                await self._bounded_io(self._server.wait_closed(), self._cancellation_grace_seconds)
            except (TimeoutError, _WAWControlDispatchPoisoned):
                # ``wait_closed`` is transport-owned and may resist
                # cancellation.  Keep cleanup bounded and quarantine the
                # listener; the tracked I/O task will consume any late
                # exception when it eventually terminates.
                self._poison_listener()
            except asyncio.CancelledError:
                # The close operation should only be cancelled during loop
                # teardown.  Preserve fail-closed state and let the caller's
                # cancellation path report the incomplete cleanup.
                self._poison_listener()
                raise
            self._server = None
        # Close and cancellation are deliberately bounded.  A dispatcher
        # which refuses cancellation is poisoned and is never admitted again.
        current = asyncio.current_task()
        dispatch_tasks = set(self._dispatch_tasks)
        io_tasks = set(self._io_tasks)
        cleanup_tasks = {task for task in self._cleanup_tasks if task is not current}
        for task in dispatch_tasks | io_tasks:
            if task is not current:
                task.cancel()
        connection_tasks = {task for task in self._connection_tasks if task is not current}
        for task in connection_tasks:
            task.cancel()
        # Cleanup observers are intentionally not cancelled here: they are
        # the independent quarantine path for child tasks whose owners may
        # have received repeated cancellation.  Include them in the bounded
        # wait so close does not return while an observer is still running.
        pending = dispatch_tasks | io_tasks | connection_tasks | cleanup_tasks
        if pending:
            done, _ = await asyncio.wait(pending, timeout=self._cancellation_grace_seconds)
            for task in done:
                with contextlib.suppress(BaseException):
                    task.result()
            if any(not task.done() for task in pending):
                self._poison_listener()
        for writer in tuple(self._writers):
            await self._close_writer(writer)
            self._writers.discard(writer)
        # A task's done callback runs on the next loop turn.  Retire tasks
        # that became terminal while the bounded wait was yielding so the
        # final state check reflects the actual registries, not callback
        # scheduling order.
        current = asyncio.current_task()
        for task in tuple(self._connection_tasks):
            if task.done():
                self._connection_tasks.discard(task)
        for task in tuple(self._dispatch_tasks):
            if task.done():
                self._consume_dispatch_task(task)
        for task in tuple(self._io_tasks):
            if task.done():
                self._consume_io_task(task)
        for task in tuple(self._cleanup_tasks):
            if task is not current and task.done():
                self._consume_cleanup_task(task)
        # A poisoned or incomplete close remains visibly closed.  In
        # particular, never clear ``_closing`` merely because this bounded
        # observer returned while a detached child is still alive.
        if (
            self._poisoned
            or self._connection_tasks
            or self._dispatch_tasks
            or self._io_tasks
            or any(task is not current for task in self._cleanup_tasks)
            or self._writers
        ):
            self._poison_listener()
        else:
            self._closing = False

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        current = asyncio.current_task()
        if current is None:
            await self._close_writer(writer)
            return
        if (
            self._poisoned
            or self._closing
            or len(self._connection_tasks) >= self._max_active_connections
        ):
            await self._close_writer(writer)
            return
        self._connection_tasks.add(current)
        self._writers.add(writer)
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
                response = await self._dispatch_with_deadline(request, deadline)
            except _WAWControlDispatchPoisoned:
                # The dispatcher may still be executing after cancellation.  A
                # late mutation is unsafe to expose through this server, so
                # close this connection and refuse all subsequent requests.
                return
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
        except (OSError, TimeoutError, _WAWControlDispatchPoisoned):
            # The peer may have disappeared or the bounded deadline expired;
            # no retry or side effect is attempted by this transport layer.
            return
        finally:
            self._connection_tasks.discard(current)
            self._writers.discard(writer)
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

    async def _send_error(
        self, writer: asyncio.StreamWriter, request_id: str | None, code: str, *, deadline: float
    ) -> None:
        if request_id is None:
            return
        writer.write(self._error_bytes(request_id, code, False))
        with contextlib.suppress(
            OSError, TimeoutError, asyncio.TimeoutError, _WAWControlDispatchPoisoned
        ):
            await self._with_deadline(writer.drain(), deadline)

    async def _close_writer(self, writer: asyncio.StreamWriter) -> None:
        writer.close()
        with contextlib.suppress(
            OSError, TimeoutError, asyncio.TimeoutError, _WAWControlDispatchPoisoned
        ):
            await self._bounded_io(writer.wait_closed(), self._cancellation_grace_seconds)

    def _poison_listener(self, *, exclude: set[asyncio.Task[Any]] | None = None) -> None:
        self._poisoned = True
        self._closing = True
        if self._server is not None:
            self._server.close()
        current = asyncio.current_task()
        excluded = {current} if current is not None else set()
        if exclude:
            excluded.update(exclude)
        for task in (
            tuple(self._dispatch_tasks) + tuple(self._io_tasks) + tuple(self._connection_tasks)
        ):
            if task not in excluded:
                task.cancel()
        for writer in tuple(self._writers):
            writer.close()

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
        return await self._bounded_io(awaitable, remaining)

    async def _bounded_io(self, awaitable: Any, timeout: float) -> Any:
        """Observe an I/O awaitable with a hard timeout and bounded cancel grace.

        ``wait_for`` waits for cancellation-resistant transports to finish
        their cancellation handler.  Keep the listener fail-closed when an
        I/O task does not terminate within the configured grace, while the
        done callback consumes any late exception from the detached task.
        """

        if timeout <= 0:
            if hasattr(awaitable, "close"):
                awaitable.close()
            raise TimeoutError("WAW control I/O deadline exceeded")
        task = asyncio.ensure_future(awaitable)
        self._io_tasks.add(task)
        task.add_done_callback(self._consume_io_task)
        try:
            done, _ = await asyncio.wait({task}, timeout=timeout)
        except asyncio.CancelledError:
            # Cancellation of the handler (or ``close``) must not abandon the
            # transport operation.  Explicitly cancel the child and give it
            # the same bounded grace as a deadline timeout.  If it ignores
            # cancellation, poison the listener before propagating the
            # caller's cancellation; the done callback remains responsible
            # for consuming any eventual late exception.
            task.cancel()
            self._poison_listener(exclude={task})
            self._schedule_cancel_cleanup(task)
            raise
        if task in done:
            try:
                return task.result()
            finally:
                self._consume_io_task(task)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=min(self._cancellation_grace_seconds, timeout))
        if task in done:
            self._consume_io_task(task)
            raise TimeoutError("WAW control I/O deadline exceeded")
        self._poison_listener(exclude={task})
        raise _WAWControlDispatchPoisoned("WAW control I/O did not cancel")

    def _schedule_cancel_cleanup(self, task: asyncio.Task[Any]) -> None:
        cleanup = asyncio.create_task(self._observe_cancelled_task(task))
        self._cleanup_tasks.add(cleanup)
        cleanup.add_done_callback(self._consume_cleanup_task)

    async def _observe_cancelled_task(self, task: asyncio.Task[Any]) -> None:
        """Observe child cancellation independently of its cancelled caller."""
        try:
            done, _ = await asyncio.wait({task}, timeout=self._cancellation_grace_seconds)
        except asyncio.CancelledError:
            # Even cancellation of the observer (for example during loop
            # teardown) must leave the listener fail-closed.  The child's done
            # callback still consumes any eventual late result.
            self._poison_listener(exclude={task})
            raise
        if task not in done:
            self._poison_listener(exclude={task})

    def _consume_cleanup_task(self, task: asyncio.Task[Any]) -> None:
        self._cleanup_tasks.discard(task)
        if task is self._close_operation:
            self._close_operation = None
        with contextlib.suppress(BaseException):
            task.result()

    def _consume_io_task(self, task: asyncio.Task[Any]) -> None:
        self._io_tasks.discard(task)
        with contextlib.suppress(BaseException):
            task.result()

    async def _dispatch_with_deadline(
        self, request: dict[str, Any], deadline: float
    ) -> dict[str, Any]:
        """Run dispatch with a hard observation deadline.

        ``asyncio.wait_for`` waits for a cancellation-resistant coroutine to
        finish its cancellation handler.  That makes the control connection's
        deadline unbounded and can allow a late workspace mutation to race a
        newer request.  Observe an independent task instead, cancel it at the
        deadline, and wait only a small bounded grace.  If it is still live,
        poison the listener so no later request can reuse the potentially
        unsafe dispatcher.
        """

        if self._poisoned or self._closing:
            raise WAWControlDispatchError("CONTROL_UNAVAILABLE", retryable=True)
        if len(self._dispatch_tasks) >= self._max_active_dispatches:
            raise WAWControlDispatchError("CONTROL_BUSY", retryable=True)

        async def invoke() -> dict[str, Any]:
            return await self._dispatch(request)

        task: asyncio.Task[dict[str, Any]] = asyncio.create_task(invoke())
        self._dispatch_tasks.add(task)
        task.add_done_callback(self._consume_dispatch_task)
        remaining = deadline - self._monotonic()
        try:
            if remaining > 0:
                done, _ = await asyncio.wait({task}, timeout=remaining)
            else:
                done = set()
        except asyncio.CancelledError:
            # The outer connection task may receive repeated cancellation.
            # Quarantine immediately and let an independent bounded observer
            # consume the child result, rather than awaiting in this path.
            task.cancel()
            self._poison_listener(exclude={task})
            self._schedule_cancel_cleanup(task)
            raise
        if task in done:
            return task.result()

        task.cancel()
        done, _ = await asyncio.wait(
            {task}, timeout=min(self._cancellation_grace_seconds, self._timeout_seconds)
        )
        if task in done:
            # Consume cancellation/errors before translating the timeout.  A
            # normal coroutine finishes promptly after cancellation and is
            # safe to report as a bounded request failure.
            with contextlib.suppress(BaseException):
                task.result()
            raise TimeoutError("WAW control dispatch deadline exceeded")

        self._poison_listener()
        raise _WAWControlDispatchPoisoned("WAW control dispatcher did not cancel")

    def _consume_dispatch_task(self, task: asyncio.Task[Any]) -> None:
        self._dispatch_tasks.discard(task)
        with contextlib.suppress(BaseException):
            task.result()


__all__ = ["Dispatch", "WAWControlDispatchError", "WAWControlServer"]
