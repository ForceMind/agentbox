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
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Any, Protocol, cast, runtime_checkable

from agentbox_protocol.waw_control import (
    MAX_CONTROL_ENVELOPE,
    MAX_CONTROL_LINE,
    WAWControlError,
    decode_control_request,
    encode_control_response,
)

_REQUEST_ID = re.compile(rb"wreq_[0-9a-f]{32}")
FIXED_BACKLOG = 64


class WAWControlDispatchError(RuntimeError):
    """A bounded, normalized error returned by an injected dispatcher."""

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@runtime_checkable
class WAWControlPeerContext(Protocol):
    """One authorizer-issued process context owned by a dispatch child."""

    def close(self) -> None: ...


Dispatch = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
PeerAwareDispatch = Callable[[dict[str, Any], WAWControlPeerContext], Awaitable[dict[str, Any]]]
PeerAuthorizer = Callable[[int, int, int, int], WAWControlPeerContext | None]


@dataclass(frozen=True)
class _ControlPeerCredentials:
    pid: int
    uid: int
    gid: int
    pidfd: int


class _PeerContextOwner:
    """Close one dispatch peer context exactly once across all task exits."""

    def __init__(self, peer: WAWControlPeerContext | None) -> None:
        self._peer = peer
        self._lock = Lock()

    def close(self) -> bool:
        with self._lock:
            peer, self._peer = self._peer, None
        if peer is None:
            return True
        try:
            peer.close()
        except Exception:
            return False
        return True


class _WAWControlDispatchPoisoned(TimeoutError):
    """The dispatcher did not stop within the bounded cancellation grace."""


class _SocketOwnership(Enum):
    RAW = "RAW"
    IN_FLIGHT = "IN_FLIGHT"
    TRANSFERRED = "TRANSFERRED"


class WAWControlServer:
    """One-request/one-response WAW control listener over an existing socket."""

    def __init__(
        self,
        sock: socket.socket,
        dispatch: Dispatch | PeerAwareDispatch,
        *,
        expected_peer_uid: int,
        expected_peer_gid: int,
        timeout_seconds: float = 2.0,
        cancellation_grace_seconds: float = 0.05,
        max_active_connections: int = 64,
        max_active_dispatches: int = 16,
        monotonic: Callable[[], float] = time.monotonic,
        peer_authorizer: PeerAuthorizer | None = None,
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
        self._peer_authorizer = peer_authorizer
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
        self._closed = False
        self._socket_ownership = _SocketOwnership.RAW
        self._raw_socket_closed = False
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
        self._start_operation: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._poisoned:
            raise RuntimeError("WAW control server is poisoned")
        if self._closing or self._closed or self._close_operation is not None:
            raise RuntimeError("WAW control server is unavailable")
        if self._server is not None:
            return
        operation = self._start_operation
        if operation is None:
            operation = asyncio.create_task(self._perform_start())
            self._start_operation = operation
            operation.add_done_callback(self._consume_start_operation)
        await asyncio.shield(operation)

    async def _perform_start(self) -> None:
        if self._poisoned or self._closing or self._closed:
            raise RuntimeError("WAW control server is unavailable")
        if self._server is not None:
            return
        self._closing = False
        try:
            self._sock.listen(FIXED_BACKLOG)
            self._sock.setblocking(False)
            self._socket_ownership = _SocketOwnership.IN_FLIGHT
            server = await asyncio.start_unix_server(
                self._handle,
                sock=self._sock,
                backlog=FIXED_BACKLOG,
                start_serving=True,
                limit=MAX_CONTROL_LINE + 1,
            )
            self._socket_ownership = _SocketOwnership.TRANSFERRED
            if self._closing or self._closed:
                server.close()
                with contextlib.suppress(OSError):
                    await server.wait_closed()
                raise RuntimeError("WAW control server closed during activation")
            self._server = server
        except asyncio.CancelledError:
            self._fail_start()
            raise
        except (OSError, RuntimeError, ValueError):
            self._fail_start()
            raise RuntimeError("WAW control listener activation failed") from None
        except BaseException:
            self._fail_start()
            raise

    def _consume_start_operation(self, task: asyncio.Task[None]) -> None:
        if self._start_operation is task:
            self._start_operation = None
        with contextlib.suppress(BaseException):
            task.result()

    def _fail_start(self) -> None:
        self._poisoned = True
        self._closing = True
        self._closed = True
        if self._server is not None:
            with contextlib.suppress(OSError):
                self._server.close()
            self._server = None
        if self._socket_ownership is _SocketOwnership.RAW:
            self._close_raw_socket()

    def _close_raw_socket(self) -> None:
        if self._raw_socket_closed or self._socket_ownership is not _SocketOwnership.RAW:
            return
        self._raw_socket_closed = True
        with contextlib.suppress(OSError, AttributeError):
            self._sock.close()

    def close(self) -> Coroutine[Any, Any, None]:
        self._closing = True
        self._closed = True
        operation = self._close_operation
        if operation is None or operation.done():
            operation = asyncio.create_task(self._perform_close())
            self._close_operation = operation
            self._cleanup_tasks.add(operation)
            operation.add_done_callback(self._consume_cleanup_task)
        return self._await_close(operation)

    async def _await_close(self, operation: asyncio.Task[None]) -> None:
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
        self._closed = True
        start_operation = self._start_operation
        start_pending = False
        if start_operation is not None and not start_operation.done():
            done, _ = await asyncio.wait(
                {start_operation}, timeout=self._cancellation_grace_seconds
            )
            start_pending = start_operation not in done
            if start_pending:
                self._poison_listener(exclude={start_operation})
            else:
                with contextlib.suppress(BaseException):
                    start_operation.result()
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
        elif not start_pending and self._socket_ownership is _SocketOwnership.RAW:
            self._close_raw_socket()
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
            or start_pending
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
        peer_credentials: _ControlPeerCredentials | None = None
        try:
            peer_credentials = self._peer_credentials(writer)
            if peer_credentials is None:
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
            peer_context: WAWControlPeerContext | None = None
            if self._peer_authorizer is not None:
                peer_context = self._authorize_peer(peer_credentials)
                if peer_context is None:
                    return
            try:
                response = await self._dispatch_with_deadline(
                    request,
                    deadline,
                    peer_context=peer_context,
                )
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
            detached_credentials, peer_credentials = peer_credentials, None
            try:
                await self._close_writer(writer)
            finally:
                if detached_credentials is not None:
                    try:
                        os.close(detached_credentials.pidfd)
                    except OSError:
                        self._poison_listener()

    def _peer_credentials(self, writer: asyncio.StreamWriter) -> _ControlPeerCredentials | None:
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
            pidfd = os.pidfd_open(pid, 0)
            return _ControlPeerCredentials(pid, uid, gid, pidfd)
        except (OSError, OverflowError, ValueError):
            return None

    def _authorize_peer(self, credentials: _ControlPeerCredentials) -> WAWControlPeerContext | None:
        authorizer = self._peer_authorizer
        if authorizer is None:
            return None
        try:
            peer = authorizer(
                credentials.pid,
                credentials.uid,
                credentials.gid,
                credentials.pidfd,
            )
        except Exception:
            return None
        return peer if isinstance(peer, WAWControlPeerContext) else None

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
        self,
        request: dict[str, Any],
        deadline: float,
        *,
        peer_context: WAWControlPeerContext | None = None,
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

        peer_owner = _PeerContextOwner(peer_context)
        if self._poisoned or self._closing:
            self._close_peer_owner(peer_owner)
            raise WAWControlDispatchError("CONTROL_UNAVAILABLE", retryable=True)
        if len(self._dispatch_tasks) >= self._max_active_dispatches:
            self._close_peer_owner(peer_owner)
            raise WAWControlDispatchError("CONTROL_BUSY", retryable=True)

        async def invoke() -> dict[str, Any]:
            try:
                if peer_context is None:
                    response = await cast(Dispatch, self._dispatch)(request)
                else:
                    response = await cast(PeerAwareDispatch, self._dispatch)(request, peer_context)
            except BaseException:
                self._close_peer_owner(peer_owner)
                raise
            if not self._close_peer_owner(peer_owner):
                raise WAWControlDispatchError("CONTROL_UNAVAILABLE", retryable=True)
            return response

        try:
            task: asyncio.Task[dict[str, Any]] = asyncio.create_task(invoke())
        except BaseException:
            self._close_peer_owner(peer_owner)
            raise
        self._dispatch_tasks.add(task)
        task.add_done_callback(
            lambda finished: self._consume_dispatch_task(finished, peer_owner=peer_owner)
        )
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

    def _consume_dispatch_task(
        self, task: asyncio.Task[Any], *, peer_owner: _PeerContextOwner | None = None
    ) -> None:
        self._dispatch_tasks.discard(task)
        if peer_owner is not None:
            self._close_peer_owner(peer_owner)
        with contextlib.suppress(BaseException):
            task.result()

    def _close_peer_owner(self, owner: _PeerContextOwner) -> bool:
        if not owner.close():
            self._poison_listener()
            return False
        return True


__all__ = [
    "Dispatch",
    "FIXED_BACKLOG",
    "PeerAuthorizer",
    "PeerAwareDispatch",
    "WAWControlDispatchError",
    "WAWControlPeerContext",
    "WAWControlServer",
]
