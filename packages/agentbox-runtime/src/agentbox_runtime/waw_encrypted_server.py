"""Bounded WAW ABWS byte-stream listener over a trusted inherited Unix socket.

Never binds/unlinks a pathname or launches a process. The required peer verifier
must authenticate the connected API pidfd/unit and sole authority binding. An
injected test listener/verifier is explicitly not systemd or real-host evidence.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import math
import socket
import struct
import threading
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from agentbox_protocol.abws import HEADER_SIZE, FrameType
from agentbox_protocol.waw_wire import Leg, decode_wire_frame

from agentbox_runtime.waw_activation import WAWActivatedSockets
from agentbox_runtime.waw_encrypted_stream import (
    EncryptedStreamError,
    RuntimePeer,
    WAWEncryptedRegistry,
    WAWEncryptedSession,
    failure_profile,
)

PeerVerifier = Callable[[Any], RuntimePeer | None]
_HEADER = struct.Struct("!4sBBHIQI")
FIXED_BACKLOG = 64


class _SocketPublication:
    """One already-connected nonblocking socket, never a reconnectable gateway."""

    def __init__(self, peer: socket.socket) -> None:
        self._peer = peer
        self._fenced = False
        self._lock = threading.Lock()

    def send(self, data: memoryview) -> int:
        with self._lock:
            if self._fenced:
                raise EncryptedStreamError("ATTACHMENT_STALE")
            return self._peer.send(data)

    def fence(self) -> bool:
        with self._lock:
            if self._fenced:
                return True
            try:
                self._peer.shutdown(socket.SHUT_RDWR)
            except OSError as exc:
                if self._peer.fileno() >= 0 and exc.errno not in {errno.ENOTCONN, errno.EBADF}:
                    return False
            self._fenced = True
            return True


@dataclass(repr=False)
class _Publication:
    """Transport-owned complete-frame publication frontier, never a crypto counter."""

    next_hop: int = 1
    uncertain: bool = False
    terminal: bool = False
    hello_published: bool = False
    _retry_frame: bytes | None = field(default=None, repr=False)
    _retried: bool = False

    def begin(self, raw: bytes) -> None:
        if self.uncertain or self.terminal:
            raise EncryptedStreamError()
        frame = decode_wire_frame(raw, Leg.RUNTIME_TO_API)
        if frame.hop_sequence != self.next_hop and (
            self._retried or self._retry_frame is None or raw != self._retry_frame
        ):
            raise EncryptedStreamError()
        # From here until complete(), any exception means the peer may have
        # seen part/all of the frame. It is never safe to append another frame.
        self.uncertain = True

    def complete(self, raw: bytes) -> None:
        frame = decode_wire_frame(raw, Leg.RUNTIME_TO_API)
        if frame.hop_sequence == self.next_hop:
            self.next_hop += 1
            self._retry_frame = (
                raw
                if frame.frame_type
                in {
                    FrameType.ADMISSION_COMMIT_ACK,
                    FrameType.DETACH_ACK,
                }
                else None
            )
            self._retried = False
        else:
            self._retried = True
        self.hello_published |= frame.frame_type is FrameType.HELLO_ACK
        self.terminal |= frame.frame_type is FrameType.CLOSE
        self.uncertain = False


class WAWEncryptedServer:
    """At most 64 streams; one <=64KiB accumulator and bounded writes per stream.

    All synchronous Runtime operations execute in worker threads, serializing
    state inside the registry/supervisor locks. Timeout invalidates a session
    immediately, quarantines its ownership and observes late cleanup; it never
    treats cancelled thread work as proof that a PTY has closed.
    """

    def __init__(
        self,
        sock: socket.socket,
        registry: WAWEncryptedRegistry,
        *,
        peer_verifier: PeerVerifier,
        maximum_connections: int = 64,
        frame_timeout: float = 1.0,
        write_timeout: float = 1.0,
    ) -> None:
        try:
            listening = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) == 1
        except OSError:
            listening = False
        if (
            sock.family != socket.AF_UNIX
            or sock.type != socket.SOCK_STREAM
            or not listening
            or sock.get_inheritable()
        ):
            raise ValueError("a trusted close-on-exec listening Unix stream socket is required")
        if type(maximum_connections) is not int or not 1 <= maximum_connections <= 64:
            raise ValueError("invalid Runtime stream capacity")
        if any(
            type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 1
            for value in (frame_timeout, write_timeout)
        ):
            raise ValueError("invalid bounded stream timeout")
        self._socket, self._registry, self._verify = sock, registry, peer_verifier
        self._maximum = maximum_connections
        self._frame_timeout, self._write_timeout = frame_timeout, write_timeout
        self._accept_task: asyncio.Task[None] | None = None
        self._connections: set[asyncio.Task[Any]] = set()
        self._workers: set[asyncio.Task[Any]] = set()
        self._sessions: set[WAWEncryptedSession] = set()
        self._peers: set[socket.socket] = set()
        self._closing = False
        self._poisoned = False
        self._closed = False
        self._close_operation: asyncio.Task[None] | None = None
        self._close_complete = False
        self._close_failure: RuntimeError | None = None

    @classmethod
    def from_activated(
        cls,
        sockets: WAWActivatedSockets,
        registry: WAWEncryptedRegistry,
        *,
        peer_verifier: PeerVerifier,
    ) -> WAWEncryptedServer:
        """Compose only the loader-verified named workspace-stream descriptor."""
        if type(sockets) is not WAWActivatedSockets:
            raise ValueError("verified WAW activated socket set is required")
        if sockets.stream.getsockname() != "/run/agentbox-waw/workspace-stream.sock":
            raise ValueError("activated WAW stream socket has the wrong fixed identity")
        return cls(sockets.stream, registry, peer_verifier=peer_verifier)

    @property
    def poisoned(self) -> bool:
        return self._poisoned

    async def start(self) -> None:
        if self._closing or self._poisoned or self._closed or self._close_operation is not None:
            raise RuntimeError("WAW stream listener is unavailable")
        if self._accept_task is not None:
            if not self._accept_task.done():
                return
            with contextlib.suppress(BaseException):
                self._accept_task.result()
            self._fail_start()
            raise RuntimeError("WAW stream listener is unavailable")
        try:
            self._socket.listen(FIXED_BACKLOG)
            self._socket.setblocking(False)
            self._accept_task = asyncio.create_task(self._accept())
            self._accept_task.add_done_callback(self._accept_done)
        except (OSError, RuntimeError, ValueError):
            self._fail_start()
            raise RuntimeError("WAW stream listener activation failed") from None
        except BaseException:
            self._fail_start()
            raise

    def _fail_start(self) -> None:
        self._poisoned = True
        self._closing = True
        self._closed = True
        with contextlib.suppress(Exception):
            self._registry.invalidate()
        with contextlib.suppress(OSError):
            self._socket.close()

    def _accept_done(self, task: asyncio.Task[None]) -> None:
        with contextlib.suppress(BaseException):
            task.result()
        if self._accept_task is task and not self._closing and not self._closed:
            self._poison()

    async def _accept(self) -> None:
        loop = asyncio.get_running_loop()
        while not self._closing:
            peer, _ = await loop.sock_accept(self._socket)
            if self._closing or len(self._connections) >= self._maximum:
                peer.close()
                continue
            peer.setblocking(False)
            peer.set_inheritable(False)
            task = asyncio.create_task(self._handle(peer))
            self._connections.add(task)
            self._peers.add(peer)

    async def _operation(self, function: Callable[[], Any], timeout: float) -> Any:
        task = asyncio.create_task(asyncio.to_thread(function))
        self._workers.add(task)
        task.add_done_callback(self._finish_worker)
        try:
            done, _ = await asyncio.wait({task}, timeout=max(0, timeout))
        except asyncio.CancelledError:
            self._poison()
            raise
        if task not in done:
            self._poison()
            raise TimeoutError("Runtime operation deadline")
        return task.result()

    def _finish_worker(self, task: asyncio.Task[Any]) -> None:
        self._workers.discard(task)
        with contextlib.suppress(BaseException):
            task.result()

    def _poison(self) -> None:
        self._poisoned = self._closing = True
        with contextlib.suppress(Exception):
            self._registry.invalidate()
        with contextlib.suppress(OSError):
            self._socket.close()
        if self._accept_task is not None:
            self._accept_task.cancel()
        for session in tuple(self._sessions):
            # This signal never waits on an in-flight crypto/PTY lock.
            session.invalidate()
        for peer in tuple(self._peers):
            peer.close()

    async def _exact(self, peer: socket.socket, size: int) -> bytes:
        # sock_recv reads exactly the remaining declared bounded amount; there
        # is no StreamReader read-ahead, hidden 2*limit buffer or language queue.
        buffer = bytearray()
        loop = asyncio.get_running_loop()
        while len(buffer) < size:
            chunk = await loop.sock_recv(peer, size - len(buffer))
            if not chunk:
                raise EOFError("WAW stream ended")
            buffer.extend(chunk)
        return bytes(buffer)

    async def _read_frame(self, peer: socket.socket, timeout: float) -> bytes:
        async with asyncio.timeout(timeout):
            first = await self._exact(peer, 1)
        async with asyncio.timeout(min(timeout, self._frame_timeout)):
            header = first + await self._exact(peer, HEADER_SIZE - 1)
            magic, version, kind, flags, length, sequence, reserved = _HEADER.unpack(header)
            limit = 16444 if kind == 9 else 4096
            if (
                magic != b"ABWS"
                or version != 1
                or flags
                or reserved
                or sequence == 0
                or kind not in {2, 3, 5, 9, 11, 12, 13, 14, 15, 20, 22, 24}
                or not 1 <= length <= limit
            ):
                raise EncryptedStreamError()
            return header + await self._exact(peer, length)

    async def _writable(self, peer: socket.socket) -> None:
        loop = asyncio.get_running_loop()
        ready: asyncio.Future[None] = loop.create_future()
        fd = peer.fileno()

        def wake() -> None:
            if not ready.done():
                ready.set_result(None)

        loop.add_writer(fd, wake)
        try:
            await ready
        finally:
            loop.remove_writer(fd)

    async def _send(
        self,
        peer: socket.socket,
        frames: tuple[bytes, ...],
        publication: _Publication,
        socket_publication: _SocketPublication,
        session: WAWEncryptedSession | None,
    ) -> None:
        for frame in frames:
            publication.begin(frame)
            offset = 0
            timeout = (
                self._write_timeout
                if session is None
                else session.publication_timeout(self._write_timeout)
            )
            async with asyncio.timeout(timeout):
                while offset < len(frame):
                    try:
                        written = (
                            session.publish_chunk(frame, offset)
                            if session is not None
                            else socket_publication.send(memoryview(frame)[offset:])
                        )
                    except (BlockingIOError, InterruptedError):
                        await self._writable(peer)
                        continue
                    if written <= 0:
                        raise OSError("WAW socket write did not progress")
                    offset += written
                    if offset < len(frame):
                        await asyncio.sleep(0)
            publication.complete(frame)

    async def _handle(self, peer_socket: socket.socket) -> None:
        task = asyncio.current_task()
        assert task is not None
        session: WAWEncryptedSession | None = None
        publication = _Publication()
        socket_publication = _SocketPublication(peer_socket)
        verified_peer = False
        pending_read: asyncio.Task[bytes] | None = None
        started = time.monotonic()
        try:
            for option in (socket.SO_RCVBUF, socket.SO_SNDBUF):
                peer_socket.setsockopt(socket.SOL_SOCKET, option, 32768)
                if peer_socket.getsockopt(socket.SOL_SOCKET, option) > 65536:
                    return
            peer = self._verify(peer_socket)
            if peer is None or peer.current() is not True:
                return
            verified_peer = True
            hello = await self._read_frame(peer_socket, 5.0)
            session, ack = await self._operation(
                lambda: self._registry.open(peer, hello, publication=socket_publication),
                min(1.0, 5 - (time.monotonic() - started)),
            )
            self._sessions.add(session)
            await self._send(peer_socket, (ack,), publication, socket_publication, session)
            while not self._closing and not session.closed:
                if pending_read is None:
                    pending_read = asyncio.create_task(
                        self._read_frame(
                            peer_socket,
                            (
                                max(0.001, 5 - (time.monotonic() - started))
                                if not session.committed
                                else 10.0
                            ),
                        )
                    )
                done, _ = await asyncio.wait({pending_read}, timeout=0.05)
                if pending_read in done:
                    raw = pending_read.result()
                    pending_read = None
                    frames = await self._operation(partial(session.receive, raw), 1.0)
                    await self._send(peer_socket, frames, publication, socket_publication, session)
                    if session.committed:
                        await self._send(
                            peer_socket,
                            await self._operation(session.flush_input, 1.0),
                            publication,
                            socket_publication,
                            session,
                        )
                if session.closed:
                    break
                await self._send(
                    peer_socket,
                    await self._operation(session.tick, 1.0),
                    publication,
                    socket_publication,
                    session,
                )
                if session.committed:
                    await self._send(
                        peer_socket,
                        await self._operation(session.output, 1.0),
                        publication,
                        socket_publication,
                        session,
                    )
        except (Exception, asyncio.CancelledError) as error:
            # A failed/partial socket write makes the publication frontier
            # unknowable. Never reuse its hop or append bytes after it.
            if (
                verified_peer
                and not self._closing
                and not publication.uncertain
                and not publication.terminal
                and not isinstance(error, (EOFError, asyncio.CancelledError))
                and not (isinstance(error, OSError) and not isinstance(error, TimeoutError))
            ):
                with contextlib.suppress(Exception):
                    if session is not None:
                        await self._operation(partial(session.close, drain_control=True), 1.0)
                    frames = failure_profile(
                        error,
                        next_hop=publication.next_hop,
                        trusted_context=publication.hello_published,
                    )
                    await self._send(peer_socket, frames, publication, socket_publication, session)
        finally:
            if pending_read is not None:
                pending_read.cancel()
                with contextlib.suppress(BaseException):
                    await pending_read
            if session is not None:
                session.invalidate()
                with contextlib.suppress(BaseException):
                    await self._operation(session.close, 1.0)
                self._sessions.discard(session)
            socket_publication.fence()
            peer_socket.close()
            self._peers.discard(peer_socket)
            self._connections.discard(task)

    def close(self) -> Coroutine[Any, Any, None]:
        self._closing = True
        self._closed = True
        if self._close_failure is not None:
            return self._raise_close_failure()
        operation = self._close_operation
        if operation is None:
            if self._close_complete:
                return self._completed_close()
            operation = asyncio.create_task(self._perform_close())
            self._close_operation = operation
            operation.add_done_callback(self._close_done)
        return self._await_close(operation)

    async def _completed_close(self) -> None:
        return None

    async def _raise_close_failure(self) -> None:
        raise RuntimeError("WAW stream listener close failed") from None

    async def _await_close(self, operation: asyncio.Task[None]) -> None:
        try:
            await asyncio.shield(operation)
        except asyncio.CancelledError:
            if operation.cancelled():
                self._record_close_failure()
                raise RuntimeError("WAW stream listener close failed") from None
            raise
        except BaseException:
            self._record_close_failure()
            raise RuntimeError("WAW stream listener close failed") from None
        if self._close_failure is not None:
            raise RuntimeError("WAW stream listener close failed") from None

    def _close_done(self, task: asyncio.Task[None]) -> None:
        if self._close_operation is task:
            self._close_operation = None
        try:
            task.result()
        except BaseException:
            self._record_close_failure()
        else:
            self._close_complete = True

    def _record_close_failure(self) -> None:
        if self._close_failure is not None:
            return
        self._close_failure = RuntimeError("WAW stream listener close failed")
        self._closed = True
        self._poison()

    async def _perform_close(self) -> None:
        self._closing = True
        self._closed = True
        with contextlib.suppress(OSError):
            self._socket.close()
        if self._accept_task is not None:
            self._accept_task.cancel()
            done, _ = await asyncio.wait({self._accept_task}, timeout=1.0)
            if self._accept_task in done:
                with contextlib.suppress(BaseException):
                    self._accept_task.result()
            else:
                self._poison()
        for session in tuple(self._sessions):
            session.invalidate()
        for peer in tuple(self._peers):
            peer.close()
        if self._connections:
            _, pending = await asyncio.wait(self._connections, timeout=1.0)
            if pending:
                self._poison()
                for task in pending:
                    task.cancel()
        if self._workers:
            _, pending = await asyncio.wait(self._workers, timeout=1.0)
            if pending:
                self._poison()
