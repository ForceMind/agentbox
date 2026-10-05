"""A3-only bounded native consumers. No Runtime authority, key or process import.

The explicit composition owns endpoint selection and existing published Runtime
peer authority. This module only consumes fresh connected three-socket bundles.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import socket
import threading
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from agentbox_core.a3_native_io import NATIVE_IO_DEADLINE, NativeChannel
from agentbox_core.services import ControlPlaneServices
from agentbox_protocol.a3_admission import A3CurrentAdmission
from agentbox_protocol.a3_content import ContentError
from agentbox_protocol.a3_transport import NativeKind as K
from agentbox_protocol.a3_transport import facts_digest, facts_to_wire

from agentbox_api.a3_admission import A3SessionCurrentness
from agentbox_api.a3_observation import A3StagedMetadata
from agentbox_api.waw_control_client import BoundRuntimePeer, RuntimePeerBorrow

Sockets = tuple[socket.socket, socket.socket, socket.socket]
Connector = Callable[[A3CurrentAdmission], Awaitable[Sockets]]


def _deadline(seconds: float) -> int:
    return time.monotonic_ns() + int(seconds * 1_000_000_000)


def _failed() -> ContentError:
    return ContentError("PATCH_REVOKED")


class A3NativeBundle:
    """One operation, three channels, one checker thread, no reconnect or reuse."""

    def __init__(
        self,
        sockets: Sockets,
        peer: BoundRuntimePeer,
        facts: A3CurrentAdmission,
        current: A3SessionCurrentness,
        retired: Callable[[A3NativeBundle], None],
    ) -> None:
        self.facts, self.current = facts, current
        self.bundle_id, self.digest = secrets.token_hex(16), facts_digest(facts)
        self._sockets = sockets
        self._borrows: list[RuntimePeerBorrow] = []
        self._channels: list[NativeChannel] = []
        self._closed = threading.Event()
        self._checker: threading.Thread | None = None
        self._loop = asyncio.get_running_loop()
        self._retired = retired
        self._close_callbacks: list[Callable[[], None]] = []
        self._guard_lock = threading.RLock()
        self._ready = False
        self._pending: tuple[int, bytes] | None = None
        self._record_sequence = 0
        self.deadline_ns = _deadline(30)
        try:
            if type(peer) is not BoundRuntimePeer or not peer.current():
                raise _failed()
            for sock in sockets:
                self._borrows.append(peer.borrow(sock))
            if any(
                borrow.parent is not peer or borrow.generation != peer.generation
                for borrow in self._borrows
            ):
                raise _failed()
            for sock in sockets:
                self._channels.append(NativeChannel(sock, self.check_peer))
            self.command, self.opaque, self.checker = self._channels
        except BaseException:
            self.close()
            raise

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def check_peer(self) -> None:
        if self.closed or not self._borrows or any(not peer.current() for peer in self._borrows):
            raise _failed()

    def check_current(self) -> None:
        # A single checker thread and the native publication frontier may both
        # consult the same adapter; serialize its monotonic observation state.
        with self._guard_lock:
            self.check_peer()
            if self.current.current(self.facts.project_id, self.facts.session_scope) != self.facts:
                raise _failed()
            self.check_peer()

    async def handshake(self, deadline_ns: int) -> None:
        channels = (self.command, self.opaque, self.checker)
        for channel, role in zip(channels, ("command", "opaque", "currentness"), strict=True):
            await channel.asend(
                K.HELLO,
                {"bundle_id": self.bundle_id, "role": role, "facts_digest": self.digest},
                deadline_ns=deadline_ns,
                guard=self.check_current,
            )
        for channel, role in zip(channels, ("command", "opaque", "currentness"), strict=True):
            frame = await channel.areceive(frozenset({K.HELLO_ACK}), deadline_ns=deadline_ns)
            if frame.payload != {
                "bundle_id": self.bundle_id,
                "role": role,
                "facts_digest": self.digest,
            }:
                raise _failed()
        self.check_current()
        if time.monotonic_ns() >= deadline_ns:
            raise ContentError("PATCH_TIMEOUT")
        self._checker = threading.Thread(
            target=self._check_loop, name="a3-currentness", daemon=True
        )
        self._checker.start()

    def _check_loop(self) -> None:
        try:
            while not self.closed:
                self.checker.wait_readable(deadline_ns=self.deadline_ns)
                end = min(self.deadline_ns, _deadline(0.25))
                frame = self.checker.receive(frozenset({K.CURRENT}), deadline_ns=end)
                payload = frame.payload
                if not isinstance(payload, dict) or payload.get("facts_digest") != self.digest:
                    raise _failed()
                self.check_current()
                self.checker.send(
                    K.CURRENT_REPLY,
                    {**payload, "current": True},
                    deadline_ns=end,
                    guard=self.check_current,
                )
        except BaseException:
            self.close()
        finally:
            with suppress(RuntimeError):
                self._loop.call_soon_threadsafe(self._retired, self)

    async def request(
        self, kind: K, payload: dict[str, object], expected: K, seconds: float
    ) -> Any:
        end = min(self.deadline_ns, _deadline(seconds))
        self.check_current()
        await self.command.asend(kind, payload, deadline_ns=end, guard=self.check_current)
        frame = await self.command.areceive(frozenset({expected, K.ERROR}), deadline_ns=end)
        self.check_current()
        if time.monotonic_ns() >= end:
            raise ContentError("PATCH_TIMEOUT")
        if frame.kind is K.ERROR:
            assert isinstance(frame.payload, dict)
            raise ContentError(str(frame.payload["code"]))
        return frame.payload

    def _rpc(self, kind: K, payload: dict[str, object], expected: K) -> None:
        inherited = NATIVE_IO_DEADLINE.get()
        end = min(self.deadline_ns, _deadline(0.25), inherited or self.deadline_ns)
        self.check_current()
        self.command.send(kind, payload, deadline_ns=end, guard=self.check_current)
        frame = self.command.receive(frozenset({expected}), deadline_ns=end)
        if frame.payload != payload:
            raise _failed()
        # Last local authority read follows the remote observation; no await
        # separates this complete guard from transport acceptance in the caller.
        self.check_current()
        if time.monotonic_ns() >= end:
            raise _failed()

    def record(self, raw: bytes) -> tuple[int, str]:
        if self._pending is not None or type(raw) is not bytes or not 1 <= len(raw) <= 24576:
            raise _failed()
        self._record_sequence += 1
        if self._record_sequence > 2**32 - 1:
            raise _failed()
        self._pending = self._record_sequence, raw
        return self._record_sequence, hashlib.sha256(raw).hexdigest()

    def publish(self, raw: bytes) -> None:
        pending = self._pending
        if pending is None or pending[1] != raw:
            raise _failed()
        self._rpc(
            K.PUBLISH_CHECK,
            {"record_sequence": pending[0], "record_sha256": hashlib.sha256(raw).hexdigest()},
            K.CHECKED,
        )

    def live(self, sequence: int, challenge: bytes) -> None:
        if not self._ready or len(challenge) != 16:
            raise _failed()
        self._rpc(
            K.LIVE,
            {"observation_sequence": sequence, "challenge": challenge.hex()},
            K.LIVE_REPLY,
        )

    async def published(self, sequence: int, digest: str) -> None:
        if self._pending is None or self._pending[0] != sequence:
            raise _failed()
        payload = {"record_sequence": sequence, "record_sha256": digest}
        reply = await self.request(K.PUBLISHED, payload, K.ACK, 1)
        if reply != payload:
            raise _failed()
        self._pending = None

    def subscribe_close(self, callback: Callable[[], None]) -> None:
        if self.closed:
            callback()
        else:
            self._close_callbacks.append(callback)

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        for channel in self._channels:
            channel.close()
        for sock in self._sockets[len(self._channels) :]:
            with suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)
            with suppress(OSError):
                sock.close()
        for borrow in self._borrows:
            with suppress(Exception):
                borrow.close()
        callbacks, self._close_callbacks = self._close_callbacks, []
        for callback in callbacks:
            with suppress(RuntimeError):
                self._loop.call_soon_threadsafe(callback)
        if self._checker is None:
            self._retired(self)

    async def wait_closed(self) -> None:
        self.close()
        end = _deadline(1)
        while (self._checker is not None and self._checker.is_alive()) or not all(
            channel.shutdown_complete for channel in self._channels
        ):
            if time.monotonic_ns() >= end:
                # Keep the source capacity charged until the late thread exits.
                raise RuntimeError("A3 checker cleanup incomplete")
            await asyncio.sleep(0.005)
        self._retired(self)


class A3NativeSource:
    """Explicit default-off native composition, with four total bundle slots."""

    def __init__(
        self,
        services: ControlPlaneServices,
        *,
        runtime_epoch: Callable[[], str | None],
        connector: Connector,
        runtime_peer: Callable[[], BoundRuntimePeer | None],
    ) -> None:
        self.services = services
        self._epoch, self._connector, self._peer = runtime_epoch, connector, runtime_peer
        self._bundles: set[A3NativeBundle] = set()
        self._connecting = 0
        self._closed = False

    def _retire(self, bundle: A3NativeBundle) -> None:
        if (bundle._checker is None or not bundle._checker.is_alive()) and all(
            channel.shutdown_complete for channel in bundle._channels
        ):
            self._bundles.discard(bundle)
        else:
            # Capacity includes the actual thread lifetime, even late cleanup.
            asyncio.get_running_loop().call_later(0.005, self._retire, bundle)

    def runtime_epoch(self) -> str | None:
        return None if self._closed else self._epoch()

    async def connect(
        self, facts: A3CurrentAdmission, current: A3SessionCurrentness
    ) -> A3NativeBundle:
        if self._closed or self._connecting + len(self._bundles) >= 4:
            raise ContentError("PATCH_UNAVAILABLE_BUSY")
        self._connecting += 1
        sockets: Sockets | None = None
        bundle: A3NativeBundle | None = None
        end = _deadline(1)
        try:
            async with asyncio.timeout(1):
                sockets = await self._connector(facts)
                if (
                    type(sockets) is not tuple
                    or len(sockets) != 3
                    or any(type(sock) is not socket.socket for sock in sockets)
                    or len({sock.fileno() for sock in sockets}) != 3
                    or len(
                        {
                            (os.fstat(sock.fileno()).st_dev, os.fstat(sock.fileno()).st_ino)
                            for sock in sockets
                        }
                    )
                    != 3
                ):
                    raise _failed()
                peer = self._peer()
                if type(peer) is not BoundRuntimePeer or self._closed:
                    raise _failed()
                bundle = A3NativeBundle(sockets, peer, facts, current, self._retire)
                self._bundles.add(bundle)
                await bundle.handshake(end)
                return bundle
        except BaseException:
            if bundle is not None:
                await bundle.wait_closed()
            elif sockets is not None:
                for sock in sockets:
                    if type(sock) is socket.socket:
                        with suppress(OSError):
                            sock.close()
            raise
        finally:
            self._connecting -= 1

    async def observe_current(
        self, facts: A3CurrentAdmission, current: A3SessionCurrentness
    ) -> A3StagedMetadata:
        bundle = await self.connect(facts, current)
        try:
            reply = await bundle.request(K.OBSERVE, {"facts": facts_to_wire(facts)}, K.METADATA, 5)
            return A3StagedMetadata.model_validate_json(json.dumps(reply))
        finally:
            await bundle.wait_closed()

    async def close(self) -> None:
        self._closed = True
        bundles = tuple(self._bundles)
        for bundle in bundles:
            bundle.close()
        await asyncio.gather(*(bundle.wait_closed() for bundle in bundles))
