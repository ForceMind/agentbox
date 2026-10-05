"""A3 API framing/auth control tests; no fixture plaintext in the relay."""

from __future__ import annotations

import asyncio
import base64
import json
from types import SimpleNamespace
from typing import Any

import pytest
from agentbox_api.a3_native_relay import _opening
from agentbox_api.waw_websocket_protocol import (
    A3_NATIVE_SCOPE_KEY,
    NATIVE_SCOPE_KEY,
    NativeWebSocketError,
    WAWWebSocketProtocol,
)
from agentbox_protocol.a3_content import ContentError

OPEN = {
    "schema_version": "a3-open/v1",
    "selection_id": "A" * 156,
    "request_nonce": "a" * 64,
    "csrf_token": "published-synthetic",
}
PATH = b"/api/v1/projects/prj_" + b"a" * 32 + b"/git/staged-stream"


def test_opening_exact_metadata_has_no_caller_path_or_command() -> None:
    assert _opening(json.dumps(OPEN).encode()) == OPEN
    for key in OPEN:
        with pytest.raises(ContentError):
            _opening(json.dumps({k: v for k, v in OPEN.items() if k != key}).encode())
        with pytest.raises(ContentError):
            _opening(json.dumps({**OPEN, key: True}).encode())
    for key in ("path", "command", "pin", "project_id", "relative_key", "epoch"):
        with pytest.raises(ContentError):
            _opening(json.dumps({**OPEN, key: "rejected"}).encode())
    with pytest.raises(ContentError):
        _opening(json.dumps(OPEN).replace("{", '{"schema_version":"a3-open/v1",', 1).encode())


@pytest.mark.parametrize("raw", [b"", b"{}", b"[]", b"null", b"\xff", b"x" * 8193, b"[" * 8192])
def test_opening_malformed_is_fixed_failure(raw: bytes) -> None:
    with pytest.raises(ContentError):
        _opening(raw)


class Transport(asyncio.Transport):
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closing = False
        self.buffered = 0

    def set_write_buffer_limits(self, high: int | None = None, low: int | None = None) -> None:
        pass

    def get_extra_info(self, name: str, default: Any = None) -> Any:
        return default

    def get_write_buffer_size(self) -> int:
        return self.buffered

    def write(self, data: Any) -> None:
        self.writes.append(bytes(data))

    def abort(self) -> None:
        self.closing = True

    def close(self) -> None:
        self.closing = True

    def is_closing(self) -> bool:
        return self.closing


def handshake(protocol: bytes = b"agentbox-a3-content-v2", path: bytes = PATH) -> bytes:
    return (
        b"GET " + path + b" HTTP/1.1\r\nHost: localhost\r\nOrigin: http://localhost\r\n"
        b"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\n"
        b"Sec-WebSocket-Protocol: "
        + protocol
        + b"\r\nSec-WebSocket-Key: "
        + base64.b64encode(b"0123456789abcdef")
        + b"\r\n\r\n"
    )


def test_native_a3_profile_has_own_route_subprotocol_and_scope_capability() -> None:
    async def run() -> None:
        state = SimpleNamespace(connections=set(), tasks=set())
        seen: list[dict[str, Any]] = []
        finished = asyncio.Event()

        async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
            seen.append(scope)
            assert (await receive())["type"] == "websocket.connect"
            await send({"type": "websocket.accept", "subprotocol": "agentbox-a3-content-v2"})
            await finished.wait()

        protocol = WAWWebSocketProtocol(SimpleNamespace(loaded=True, loaded_app=app), state, {})
        transport = Transport()
        protocol.connection_made(transport)
        protocol.data_received(handshake())
        await asyncio.sleep(0)
        assert protocol.is_open and protocol.message_limit == 8192
        assert seen[0]["extensions"] == {A3_NATIVE_SCOPE_KEY: protocol}
        assert NATIVE_SCOPE_KEY not in seen[0]["extensions"]
        assert b"Sec-WebSocket-Protocol: agentbox-a3-content-v2\r\n" in transport.writes[0]
        finished.set()
        await asyncio.gather(*state.tasks)
        protocol.connection_lost(None)

    asyncio.run(run())


@pytest.mark.parametrize(
    "protocol,path",
    [
        (b"agentbox-waw-v1", PATH),
        (b"agentbox-a3-content-v2", b"/api/v1/workspaces/aws_" + b"a" * 32 + b"/stream"),
        (b"agentbox-a3-content-v2", PATH + b"?path=bad"),
    ],
)
def test_native_a3_never_adopts_waw_profile_or_query(protocol: bytes, path: bytes) -> None:
    async def run() -> None:
        native = WAWWebSocketProtocol(
            SimpleNamespace(loaded=True, loaded_app=None),
            SimpleNamespace(connections=set(), tasks=set()),
            {},
        )
        transport = Transport()
        native.connection_made(transport)
        native.data_received(handshake(protocol, path))
        assert native._closed and not native._accepted and transport.closing
        native.connection_lost(None)

    asyncio.run(run())


def test_a3_guard_after_backpressure_fences_before_transport_acceptance() -> None:
    async def run() -> None:
        native = WAWWebSocketProtocol(
            SimpleNamespace(loaded=True, loaded_app=None),
            SimpleNamespace(connections=set(), tasks=set()),
            {},
        )
        transport = Transport()
        native.connection_made(transport)
        native._a3 = native._accepted = native._requested = True
        current = True
        checks: list[bytes] = []

        def guard(raw: bytes) -> None:
            assert raw == b"opaque A3 record"
            checks.append(raw)
            if not current:
                native.abort(4403)
                raise NativeWebSocketError(4403)

        native.install_publication_guard(guard)
        native.pause_writing()
        task = asyncio.create_task(
            native.send({"type": "websocket.send", "bytes": b"opaque A3 record"})
        )
        await asyncio.sleep(0)
        assert not checks and not transport.writes
        current = False
        native.resume_writing()
        with pytest.raises(NativeWebSocketError):
            await task
        assert len(checks) == 1 and not transport.writes and transport.closing
        native.connection_lost(None)

    asyncio.run(run())


def test_a3_close_aborts_owned_residual_buffer_without_claiming_kernel_retraction() -> None:
    async def run() -> None:
        native = WAWWebSocketProtocol(
            SimpleNamespace(loaded=True, loaded_app=None),
            SimpleNamespace(connections=set(), tasks=set()),
            {},
        )
        transport = Transport()
        native.connection_made(transport)
        native._a3 = native._accepted = native._requested = True
        transport.buffered = 200
        native.close(4403)
        assert transport.closing and native._closed and not transport.writes
        native.connection_lost(None)

    asyncio.run(run())


def test_consumption_ack_does_not_release_runtime_before_native_drain() -> None:
    asyncio.run(_relay_backpressure_case(revoke=False))


def test_runtime_eof_while_api_write_paused_aborts_owned_buffer_and_no_ack() -> None:
    asyncio.run(_relay_backpressure_case(revoke=True))


async def _relay_backpressure_case(*, revoke: bool) -> None:
    import hashlib
    import time

    from agentbox_api.a3_native_relay import A3NativeRelay
    from agentbox_protocol.a3_transport import NativeFrame
    from agentbox_protocol.a3_transport import NativeKind as K

    raw = b"opaque synthetic record"
    runtime_frames: asyncio.Queue[NativeFrame | None] = asyncio.Queue(1)
    browser_frames: asyncio.Queue[bytes] = asyncio.Queue(2)
    sent_record = asyncio.Event()
    callbacks: list[Any] = []
    published: list[tuple[int, str]] = []
    current = True
    closed = False

    class Opaque:
        async def await_readable(self, deadline_ns: int) -> None:
            del deadline_ns

        async def areceive(self, *args: Any, **kwargs: Any) -> NativeFrame:
            value = await runtime_frames.get()
            if value is None:
                raise ContentError("PATCH_REVOKED")
            return value

    class Bundle:
        _ready = False
        deadline_ns = time.monotonic_ns() + 30_000_000_000
        opaque = Opaque()

        def check_peer(self) -> None:
            if closed:
                raise ContentError("PATCH_REVOKED")

        def check_current(self) -> None:
            self.check_peer()
            if not current:
                raise ContentError("PATCH_REVOKED")

        def subscribe_close(self, callback: Any) -> None:
            callbacks.append(callback)

        def close(self) -> None:
            nonlocal closed
            if not closed:
                closed = True
                for callback in callbacks:
                    callback()

        def record(self, value: bytes) -> tuple[int, str]:
            assert value == raw
            return 1, hashlib.sha256(value).hexdigest()

        def publish(self, value: bytes) -> None:
            assert value == raw
            self.check_current()

        async def published(self, sequence: int, digest: str) -> None:
            self.check_current()
            published.append((sequence, digest))

        def live(self, sequence: int, challenge: bytes) -> None:
            del sequence, challenge
            self.check_current()

    native = WAWWebSocketProtocol(
        SimpleNamespace(loaded=True, loaded_app=None),
        SimpleNamespace(connections=set(), tasks=set()),
        {},
    )

    class Buffered(Transport):
        def write(self, data: Any) -> None:
            super().write(data)
            if bytes(data).endswith(raw):
                self.buffered = len(data)
                native.pause_writing()
                sent_record.set()

    transport = Buffered()
    native.connection_made(transport)
    native._a3 = native._accepted = native._requested = True

    class Browser:
        async def send_bytes(self, value: bytes) -> None:
            await native.send({"type": "websocket.send", "bytes": value})

        async def receive_bytes(self) -> bytes:
            return await browser_frames.get()

    bundle = Bundle()
    tasks: list[asyncio.Task[Any]] = []
    relay = object.__new__(A3NativeRelay)
    serving = asyncio.create_task(relay._relay(Browser(), native, bundle, tasks))  # type: ignore[arg-type]
    try:
        await runtime_frames.put(NativeFrame(K.READY, 2, {}))
        await runtime_frames.put(NativeFrame(K.RECORD, 3, raw))
        await asyncio.wait_for(sent_record.wait(), 1)
        await browser_frames.put(b"A3CA\x01" + bytes(4) + hashlib.sha256(raw).digest())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not published and transport.buffered
        if revoke:
            current = False
            await runtime_frames.put(None)
            with pytest.raises((ContentError, NativeWebSocketError)):
                await asyncio.wait_for(serving, 1)
            assert native._closed and transport.closing and not published
        else:
            transport.buffered = 0
            native.resume_writing()
            for _ in range(50):
                if published:
                    break
                await asyncio.sleep(0.001)
            assert published == [(1, hashlib.sha256(raw).hexdigest())]
    finally:
        bundle.close()
        serving.cancel()
        for task in tasks:
            task.cancel()
        await asyncio.gather(serving, *tasks, return_exceptions=True)
        native.connection_lost(None)


@pytest.mark.parametrize("operation", ["handshake", "request"])
def test_final_synchronous_db_check_cannot_expose_late_success(
    monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    import time

    from agentbox_api import a3_native_transport as module
    from agentbox_api.a3_native_transport import A3NativeBundle
    from agentbox_protocol.a3_transport import NativeFrame
    from agentbox_protocol.a3_transport import NativeKind as K

    async def run() -> None:
        clock = [0]
        monkeypatch.setattr(time, "monotonic_ns", lambda: clock[0])
        monkeypatch.setattr(module, "_deadline", lambda _seconds: 100)

        class Channel:
            payload: Any = None

            async def asend(self, kind: Any, payload: Any, **kwargs: Any) -> None:
                self.payload = payload

            async def areceive(self, expected: Any, **kwargs: Any) -> NativeFrame:
                return NativeFrame(
                    K.HELLO_ACK if operation == "handshake" else K.OWNED, 1, self.payload
                )

        bundle = object.__new__(A3NativeBundle)
        bundle.bundle_id = "a" * 32
        bundle.digest = "b" * 64
        bundle.deadline_ns = 1000
        bundle._checker = None
        bundle.command = Channel()  # type: ignore[assignment]
        bundle.opaque = Channel()  # type: ignore[assignment]
        bundle.checker = Channel()  # type: ignore[assignment]
        checks = [0]

        def slow_final_check() -> None:
            checks[0] += 1
            if operation == "handshake" or checks[0] == 2:
                clock[0] = 101

        bundle.check_current = slow_final_check  # type: ignore[method-assign]
        with pytest.raises(ContentError, match="PATCH_TIMEOUT"):
            if operation == "handshake":
                await bundle.handshake(100)
            else:
                await bundle.request(K.OPEN, {}, K.OWNED, 1)
        assert bundle._checker is None

    asyncio.run(run())


def test_api_bundle_slot_includes_deferred_async_descriptor_cleanup() -> None:
    import socket
    import time

    from agentbox_api.a3_native_transport import A3NativeBundle, A3NativeSource
    from agentbox_core.a3_native_io import NativeChannel
    from agentbox_protocol.a3_transport import NativeKind as K

    async def run() -> None:
        left, right = socket.socketpair()
        channel = NativeChannel(left, lambda: None)
        source = object.__new__(A3NativeSource)
        bundle = object.__new__(A3NativeBundle)
        bundle._checker = None
        bundle._channels = [channel]
        source._bundles = {bundle}
        receiving = asyncio.create_task(
            channel.areceive(frozenset({K.RECORD}), deadline_ns=time.monotonic_ns() + 1_000_000_000)
        )
        try:
            await asyncio.sleep(0)
            channel.close()
            assert channel.closed and not bool(channel.shutdown_complete)
            source._retire(bundle)
            assert bundle in source._bundles
            await asyncio.gather(receiving, return_exceptions=True)
            assert channel.shutdown_complete
            source._retire(bundle)
            assert bundle not in source._bundles
        finally:
            right.close()
            channel.close()
            receiving.cancel()
            await asyncio.gather(receiving, return_exceptions=True)

    asyncio.run(run())
