"""Actual TCP/RFC6455 frames reach the native adapter before ASGI messages."""

from __future__ import annotations

import asyncio
import base64
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from agentbox_api.waw_input_budget import (
    InputBudget,
    InputBudgetError,
    InputBudgetOwner,
)
from agentbox_api.waw_websocket_protocol import (
    NATIVE_SCOPE_KEY,
    NativeWebSocketError,
    WAWWebSocketProtocol,
)
from agentbox_protocol.abws import FrameType as F
from agentbox_protocol.abws import encode_frame

PATH = b"/api/v1/workspaces/aws_" + b"a" * 32 + b"/stream"
KEY = base64.b64encode(b"0123456789abcdef")


def handshake(*, extra: bytes = b"", path: bytes = PATH) -> bytes:
    return (
        b"GET " + path + b" HTTP/1.1\r\nHost: localhost\r\nOrigin: http://localhost\r\n"
        b"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\n"
        b"Sec-WebSocket-Protocol: agentbox-waw-v1\r\nSec-WebSocket-Key: "
        + KEY
        + b"\r\n"
        + extra
        + b"\r\n"
    )


def client_frame(
    payload: bytes, *, opcode: int = 2, fin: bool = True, masked: bool = True, rsv: int = 0
) -> bytes:
    length = len(payload)
    mask = b"abcd" if masked else b""
    first = bytes(((128 if fin else 0) | rsv | opcode,))
    flag = 128 if masked else 0
    prefix = (
        bytes((flag | length,))
        if length < 126
        else (
            bytes((flag | 126,)) + length.to_bytes(2, "big")
            if length < 65536
            else bytes((flag | 127,)) + length.to_bytes(8, "big")
        )
    )
    return (
        first
        + prefix
        + mask
        + (
            bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
            if masked
            else payload
        )
    )


async def server_frame(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    first, second = await asyncio.wait_for(reader.readexactly(2), 2)
    assert not second & 128
    length = second & 127
    if length in (126, 127):
        length = int.from_bytes(await reader.readexactly(2 if length == 126 else 8), "big")
    return first & 15, await reader.readexactly(length)


@asynccontextmanager
async def connected(
    *, request: bytes | None = None, uvicorn: bool = False
) -> AsyncIterator[tuple[asyncio.StreamReader, asyncio.StreamWriter, list[bytes], dict[str, Any]]]:
    seen: list[bytes] = []
    state: dict[str, Any] = {}

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        state.update(scope)
        assert (await receive())["type"] == "websocket.connect"
        await send({"type": "websocket.accept", "subprotocol": "agentbox-waw-v1"})
        while True:
            message = await receive()
            if message["type"] == "websocket.disconnect":
                break
            seen.append(message["bytes"])
            await send({"type": "websocket.send", "bytes": message["bytes"]})

    loop = asyncio.get_running_loop()
    task = None
    if uvicorn:
        import socket

        from uvicorn import Config, Server

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        address = sock.getsockname()
        config = Config(
            app,
            lifespan="off",
            ws=WAWWebSocketProtocol,
            access_log=False,
            proxy_headers=False,
            log_level="critical",
        )
        server = Server(config)
        task = asyncio.create_task(server.serve(sockets=[sock]))
        while not server.started:
            await asyncio.sleep(0.001)
    else:
        state_holder = SimpleNamespace(connections=set(), tasks=set())
        native_config = SimpleNamespace(loaded=True, loaded_app=app)
        tcp = await loop.create_server(
            lambda: WAWWebSocketProtocol(native_config, state_holder, {}), "127.0.0.1", 0
        )
        address = tcp.sockets[0].getsockname()
    reader, writer = await asyncio.open_connection(*address[:2])
    writer.write(handshake() if request is None else request)
    await writer.drain()
    try:
        yield reader, writer, seen, state
    finally:
        writer.close()
        await writer.wait_closed()
        if task is not None:
            server.should_exit = True
            await task
        else:
            tcp.close()
            await tcp.wait_closed()
            for connection in tuple(state_holder.connections):
                connection.shutdown()
            if state_holder.tasks:
                await asyncio.gather(*state_holder.tasks, return_exceptions=True)


@pytest.mark.parametrize("uvicorn", [False, True])
def test_actual_upgrade_and_fragment_reassembly(uvicorn: bool) -> None:
    async def run() -> None:
        async with connected(uvicorn=uvicorn) as (reader, writer, seen, state):
            response = await reader.readuntil(b"\r\n\r\n")
            assert response.startswith(b"HTTP/1.1 101")
            expected = base64.b64encode(
                hashlib.sha1(KEY + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest()
            )
            assert b"Sec-WebSocket-Accept: " + expected in response
            assert type(state["extensions"][NATIVE_SCOPE_KEY]) is WAWWebSocketProtocol
            writer.write(client_frame(b"abc", fin=False) + client_frame(b"d", opcode=0))
            await writer.drain()
            assert await server_frame(reader) == (2, b"abcd")
            assert seen == [b"abcd"]

    asyncio.run(run())


@pytest.mark.parametrize(
    "request_raw",
    [
        handshake(extra=b"Origin: http://localhost\r\n"),
        handshake(extra=b"Sec-WebSocket-Key: " + KEY + b"\r\n"),
        handshake(path=PATH + b"?ticket=CANARY"),
        handshake(path=PATH.replace(b"/stream", b"/%73tream")),
        handshake().replace(b"agentbox-waw-v1", b"wrong"),
        handshake().replace(b"Version: 13", b"Version: 12"),
    ],
)
def test_invalid_upgrade_never_reaches_asgi(request_raw: bytes) -> None:
    async def run() -> None:
        async with connected(request=request_raw) as (reader, _writer, seen, state):
            assert (await reader.readuntil(b"\r\n\r\n")).startswith(b"HTTP/1.1 403")
            assert not seen and not state

    asyncio.run(run())


def test_browser_deflate_offer_declined_and_rsv_rejected() -> None:
    async def run() -> None:
        async with connected(
            request=handshake(
                extra=b"Sec-WebSocket-Extensions: permessage-deflate; client_max_window_bits\r\n"
            )
        ) as (reader, writer, seen, _):
            response = await reader.readuntil(b"\r\n\r\n")
            assert b"101" in response and b"Sec-WebSocket-Extensions" not in response
            writer.write(client_frame(b"bad", rsv=64))
            assert await server_frame(reader) == (8, (4400).to_bytes(2, "big"))
            assert not seen

    asyncio.run(run())


@pytest.mark.parametrize(
    ("frame", "code"),
    [
        (client_frame(b"text", opcode=1), 4400),
        (client_frame(b"bad", masked=False), 4400),
        (client_frame(b"x", opcode=9, fin=False), 4400),
        (client_frame(b"x" * 33, opcode=9), 4429),
        (client_frame(b"x" * 126, opcode=8), 4400),
        (client_frame(b"nonce", opcode=10), 4400),
        (client_frame(b"x" * 4121), 1009),
    ],
)
def test_native_rejections_precede_message_allocation(frame: bytes, code: int) -> None:
    async def run() -> None:
        async with connected() as (reader, writer, seen, _):
            await reader.readuntil(b"\r\n\r\n")
            writer.write(frame)
            assert await server_frame(reader) == (8, code.to_bytes(2, "big"))
            assert not seen

    asyncio.run(run())


def test_fragment_deadline_and_aggregate_limit_are_native() -> None:
    async def run() -> None:
        async with connected() as (reader, writer, seen, _):
            await reader.readuntil(b"\r\n\r\n")
            writer.write(client_frame(b"x", fin=False))
            assert await server_frame(reader) == (8, (4408).to_bytes(2, "big"))
            assert not seen
        async with connected() as (reader, writer, seen, state):
            await reader.readuntil(b"\r\n\r\n")
            state["extensions"][NATIVE_SCOPE_KEY].message_limit = 65536
            writer.write(client_frame(b"x" * 16384, fin=False))
            await writer.drain()
            await asyncio.sleep(0)
            writer.write(b"\x80\xfe" + (49153).to_bytes(2, "big") + b"abcd")
            assert await server_frame(reader) == (8, (1009).to_bytes(2, "big"))
            assert not seen

    asyncio.run(run())


def test_native_ping_budget_matching_pong_and_no_application_state() -> None:
    async def run() -> None:
        async with connected() as (reader, writer, seen, state):
            await reader.readuntil(b"\r\n\r\n")
            writer.write(client_frame(b"ping", opcode=9))
            assert await server_frame(reader) == (10, b"ping")
            protocol = state["extensions"][NATIVE_SCOPE_KEY]
            protocol._ping()
            opcode, nonce = await server_frame(reader)
            assert opcode == 9 and len(nonce) == 16
            writer.write(client_frame(nonce, opcode=10))
            await writer.drain()
            await asyncio.sleep(0.005)
            assert protocol._pending_ping is None
            assert not seen
            writer.write(client_frame(b"again", opcode=9))
            assert await server_frame(reader) == (8, (4429).to_bytes(2, "big"))

    asyncio.run(run())


@pytest.mark.parametrize("code", [1000, 1001, 1008, 1009, 1011, 1012, 1013, 4400, 1002, 1005])
def test_native_close_direction_and_reason_privacy(code: int) -> None:
    async def run() -> None:
        async with connected() as (reader, writer, seen, _state):
            await reader.readuntil(b"\r\n\r\n")
            writer.write(client_frame(code.to_bytes(2, "big") + b"PRIVATE-CLOSE-REASON", opcode=8))
            expected = 4400 if code in (4400, 1002, 1005) else code
            assert await server_frame(reader) == (8, expected.to_bytes(2, "big"))
            assert not seen

    asyncio.run(run())


@pytest.mark.parametrize("native_close", [False, True])
def test_abort_discards_buffered_frame_without_appending_close(native_close: bool) -> None:
    async def run() -> None:
        from agentbox_api.waw_websocket_protocol import NativeWebSocketError

        protocol = WAWWebSocketProtocol(
            SimpleNamespace(loaded=True, loaded_app=None),
            SimpleNamespace(connections=set(), tasks=set()),
            {},
        )

        class BufferedTransport(asyncio.Transport):
            def __init__(self) -> None:
                self.pending = bytearray()
                self.written: list[bytes] = []
                self.aborted = False
                self.closed = False

            def set_write_buffer_limits(
                self, high: int | None = None, low: int | None = None
            ) -> None:
                pass

            def get_extra_info(self, name: str, default: Any = None) -> Any:
                return default

            def get_write_buffer_size(self) -> int:
                return len(self.pending)

            def write(self, data: Any) -> None:
                self.pending.extend(data)
                self.written.append(bytes(data))
                protocol.pause_writing()

            def abort(self) -> None:
                self.aborted = True
                self.pending.clear()

            def close(self) -> None:
                self.closed = True

            def is_closing(self) -> bool:
                return self.aborted or self.closed

        transport = BufferedTransport()
        protocol.connection_made(transport)
        protocol._accepted = True
        sending = asyncio.create_task(
            protocol.send({"type": "websocket.send", "bytes": b"synthetic ciphertext"})
        )
        await asyncio.sleep(0)
        assert transport.pending and not sending.done()
        if native_close:
            protocol.close(4403)
        else:
            protocol.abort(4403)
        with pytest.raises(NativeWebSocketError):
            await sending
        assert transport.aborted and not transport.closed and not transport.pending
        assert len(transport.written) == 1 and transport.written[0][0] == 0x82

    asyncio.run(run())


def test_native_guard_rechecks_after_backpressure_before_writing() -> None:
    async def run() -> None:
        from agentbox_api.waw_websocket_protocol import NativeWebSocketError

        protocol = WAWWebSocketProtocol(
            SimpleNamespace(loaded=True, loaded_app=None),
            SimpleNamespace(connections=set(), tasks=set()),
            {},
        )
        allowed = True
        checked = 0

        def guard(_raw: bytes) -> None:
            nonlocal checked
            checked += 1
            if not allowed:
                protocol.abort(4403)
                raise NativeWebSocketError(4403)

        class Transport(asyncio.Transport):
            def __init__(self) -> None:
                self.writes: list[bytes] = []
                self.aborted = False

            def set_write_buffer_limits(
                self, high: int | None = None, low: int | None = None
            ) -> None:
                pass

            def get_extra_info(self, name: str, default: Any = None) -> Any:
                return default

            def get_write_buffer_size(self) -> int:
                return 0

            def write(self, data: Any) -> None:
                self.writes.append(bytes(data))

            def abort(self) -> None:
                self.aborted = True

        transport = Transport()
        protocol.connection_made(transport)
        protocol._accepted = True
        protocol.install_publication_guard(guard)
        protocol.pause_writing()
        sending = asyncio.create_task(
            protocol.send({"type": "websocket.send", "bytes": b"synthetic ciphertext"})
        )
        await asyncio.sleep(0)
        assert checked == 0 and not sending.done()
        allowed = False
        protocol.resume_writing()
        with pytest.raises(NativeWebSocketError):
            await sending
        assert checked == 1 and not transport.writes and transport.aborted

    asyncio.run(run())


class BudgetTransport(asyncio.Transport):
    """Synthetic transport for actual native parser/pool state-machine tests."""

    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closing = False

    def set_write_buffer_limits(self, high: int | None = None, low: int | None = None) -> None:
        pass

    def get_extra_info(self, name: str, default: Any = None) -> Any:
        return default

    def get_write_buffer_size(self) -> int:
        return 0

    def write(self, data: Any) -> None:
        self.writes.append(bytes(data))

    def close(self) -> None:
        self.closing = True

    def abort(self) -> None:
        self.closing = True

    def is_closing(self) -> bool:
        return self.closing


def budget_protocol(
    loop: asyncio.AbstractEventLoop, state: Any, *, active: bool
) -> tuple[WAWWebSocketProtocol, BudgetTransport]:
    protocol = WAWWebSocketProtocol(
        SimpleNamespace(loaded=True, loaded_app=None), state, {}, _loop=loop
    )
    transport = BudgetTransport()
    protocol.connection_made(transport)
    protocol._requested = protocol._accepted = True
    protocol.message_limit = 65536 if active else 4120
    return protocol, transport


def encoded_input(size: int, hop: int = 1) -> bytes:
    assert size >= 24
    result = encode_frame(F.INPUT, b"x" * (size - 24), hop)
    assert len(result) == size
    return result


def test_input_budget_identity_owner_liveness_and_exact_release() -> None:
    connection = object()
    budget = InputBudget(
        connection_id=connection, attachment_id="att_" + "a" * 32, runtime_epoch="7"
    )
    tokens = [budget.reserve_native(size) for size in (101, 202, 303, 404)]
    assert "att_" not in repr(budget) + repr(tokens[0])
    budget.transfer(
        tokens[1],
        source=InputBudgetOwner.NATIVE_READY,
        target=InputBudgetOwner.BROWSER_DELIVERY,
    )
    budget.transfer(
        tokens[2],
        source=InputBudgetOwner.NATIVE_READY,
        target=InputBudgetOwner.BROWSER_DELIVERY,
    )
    budget.transfer(
        tokens[2],
        source=InputBudgetOwner.BROWSER_DELIVERY,
        target=InputBudgetOwner.RELAY_RUNTIME_PENDING,
    )
    budget.transfer(
        tokens[3],
        source=InputBudgetOwner.NATIVE_READY,
        target=InputBudgetOwner.BROWSER_DELIVERY,
    )
    budget.transfer(
        tokens[3],
        source=InputBudgetOwner.BROWSER_DELIVERY,
        target=InputBudgetOwner.RELAY_RUNTIME_PENDING,
    )
    budget.transfer(
        tokens[3],
        source=InputBudgetOwner.RELAY_RUNTIME_PENDING,
        target=InputBudgetOwner.RUNTIME_SEND_INFLIGHT,
    )
    assert budget.owner_bytes == {
        InputBudgetOwner.NATIVE_READY: 101,
        InputBudgetOwner.BROWSER_DELIVERY: 202,
        InputBudgetOwner.RELAY_RUNTIME_PENDING: 303,
        InputBudgetOwner.RUNTIME_SEND_INFLIGHT: 404,
    }
    assert budget.reserved_bytes == 1010 and budget.live_count == 4
    other = InputBudget(connection_id=object(), attachment_id="att_" + "a" * 32, runtime_epoch="7")
    assert not other.release(tokens[0], owner=InputBudgetOwner.NATIVE_READY)
    with pytest.raises(InputBudgetError):
        budget.assert_identity(
            connection_id=object(), attachment_id="att_" + "a" * 32, runtime_epoch="7"
        )
    assert budget.release(tokens[0], owner=InputBudgetOwner.NATIVE_READY)
    assert not budget.release(tokens[0], owner=InputBudgetOwner.NATIVE_READY)
    budget.close()
    assert budget.closed and budget.reserved_bytes == budget.live_count == 0
    assert all(not token.live for token in tokens)
    assert not budget.release(tokens[3], owner=InputBudgetOwner.RUNTIME_SEND_INFLIGHT)


def test_native_shared_input_budget_allows_65536_and_fences_65872_before_copy() -> None:
    loop = asyncio.new_event_loop()
    state = SimpleNamespace(connections=set(), tasks=set())
    exact, _ = budget_protocol(loop, state, active=True)
    exact_budget = InputBudget(
        connection_id=object(), attachment_id="att_" + "b" * 32, runtime_epoch="8"
    )
    exact.install_input_budget(exact_budget)
    overflow, transport = budget_protocol(loop, state, active=True)
    overflow_budget = InputBudget(
        connection_id=object(), attachment_id="att_" + "c" * 32, runtime_epoch="9"
    )
    overflow.install_input_budget(overflow_budget)
    plus_one, plus_one_transport = budget_protocol(loop, state, active=True)
    plus_one_budget = InputBudget(
        connection_id=object(), attachment_id="att_" + "d" * 32, runtime_epoch="10"
    )
    plus_one.install_input_budget(plus_one_budget)
    fenced: list[int] = []

    def fence() -> None:
        assert not transport.closing
        fenced.append(overflow_budget.reserved_bytes)

    overflow_budget.install_overflow_fence(fence)
    plus_one_budget.install_overflow_fence(lambda: fenced.append(plus_one_budget.reserved_bytes))
    try:
        for size in (16468, 16468, 16468, 16132):
            exact.data_received(client_frame(encoded_input(size)))
        assert not exact._closed
        assert exact_budget.reserved_bytes == exact_budget.peak_bytes == 65536
        # Complete INPUT credits outlive the independent partial-parser pool.
        assert exact.partial_budget.count == exact.partial_budget.reserved_bytes == 0

        overflow.data_received(client_frame(encoded_input(16468, 1)))
        first = loop.run_until_complete(overflow.receive())
        assert set(first) == {"type", "bytes"}
        delivery = overflow.claim_received(first)
        assert delivery.input_token is not None
        overflow_budget.transfer(
            delivery.input_token,
            source=InputBudgetOwner.BROWSER_DELIVERY,
            target=InputBudgetOwner.RELAY_RUNTIME_PENDING,
        )
        for number in range(2, 5):
            overflow.data_received(client_frame(encoded_input(16468, number)))
        assert overflow._closed and overflow._close_code == 4429 and transport.closing
        assert fenced == [3 * 16468]
        assert overflow_budget.peak_bytes == 3 * 16468
        assert overflow_budget.reserved_bytes == overflow_budget.live_count == 0
        assert overflow.partial_budget.count == overflow.partial_budget.reserved_bytes == 0

        for number, size in enumerate((16468, 16468, 16468, 16133), 1):
            plus_one.data_received(client_frame(encoded_input(size, number)))
        assert plus_one._closed and plus_one._close_code == 4429
        assert plus_one_transport.closing and fenced[-1] == 3 * 16468
        assert plus_one_budget.peak_bytes == 3 * 16468
    finally:
        exact.connection_lost(None)
        overflow.connection_lost(None)
        plus_one.connection_lost(None)
        loop.close()


def test_native_overflow_fence_exception_propagates_after_abort() -> None:
    loop = asyncio.new_event_loop()
    protocol, transport = budget_protocol(
        loop, SimpleNamespace(connections=set(), tasks=set()), active=True
    )
    budget = InputBudget(
        connection_id=object(), attachment_id="att_" + "e" * 32, runtime_epoch="11"
    )
    protocol.install_input_budget(budget)

    def failed_fence() -> None:
        raise RuntimeError("synthetic fence failure")

    budget.install_overflow_fence(failed_fence)
    try:
        for number in range(1, 4):
            protocol.data_received(client_frame(encoded_input(16468, number)))
        with pytest.raises(RuntimeError, match="synthetic fence failure"):
            protocol.data_received(client_frame(encoded_input(16468, 4)))
        assert protocol._closed and protocol._close_code == 4429 and transport.closing
        assert budget.reserved_bytes == budget.live_count == 0
    finally:
        protocol.connection_lost(None)
        loop.close()


def test_install_input_budget_charges_existing_ready_frame_without_reset() -> None:
    loop = asyncio.new_event_loop()
    protocol, _ = budget_protocol(
        loop, SimpleNamespace(connections=set(), tasks=set()), active=False
    )
    raw = encoded_input(4000)
    protocol.data_received(client_frame(raw))
    budget = InputBudget(
        connection_id=object(), attachment_id="att_" + "f" * 32, runtime_epoch="12"
    )
    try:
        protocol.install_input_budget(budget)
        assert budget.reserved_bytes == len(raw)
        assert protocol._queue[0]["bytes"] == raw
        with pytest.raises(NativeWebSocketError):
            protocol.install_input_budget(
                InputBudget(
                    connection_id=object(),
                    attachment_id="att_" + "0" * 32,
                    runtime_epoch="13",
                )
            )
        assert budget.reserved_bytes == len(raw)
    finally:
        protocol.connection_lost(None)
        loop.close()


def test_shared_pool_counts_reachable_active_plus_pending_mix_and_rejects_129th() -> None:
    # Four active + 124 pending is inside the upstream logical ceilings; this
    # does not claim 129 admitted writers or real authentication/host evidence.
    loop = asyncio.new_event_loop()
    state = SimpleNamespace(connections=set(), tasks=set())
    protocols: list[WAWWebSocketProtocol] = []
    try:
        for number in range(128):
            protocol, _ = budget_protocol(loop, state, active=number < 4)
            protocols.append(protocol)
            protocol.data_received(client_frame(b"x", fin=False))
        pool = protocols[0].partial_budget
        assert all(protocol.partial_budget is pool for protocol in protocols)
        assert pool.count == 128 and pool.reserved_bytes > 0
        denied, transport = budget_protocol(loop, state, active=False)
        protocols.append(denied)
        denied.data_received(client_frame(b"x", fin=False))
        assert denied._closed and denied._close_code == 4429 and not denied._buffer
        assert pool.count == 128
        assert transport.writes[-1][-2:] == (4429).to_bytes(2, "big")
        protocols[0].connection_lost(None)
        replacement, _ = budget_protocol(loop, state, active=False)
        protocols.append(replacement)
        replacement.data_received(client_frame(b"x", fin=False))
        assert pool.count == 128
        protocols[0].abort(4403)  # Old connection cannot release replacement.
        assert pool.count == 128
    finally:
        for protocol in protocols:
            protocol.connection_lost(None)
        assert protocols[0].partial_budget.count == 0
        assert protocols[0].partial_budget.reserved_bytes == 0
        loop.close()


def test_pool_slot_and_total_byte_limits_are_atomic_and_owner_exact() -> None:
    from agentbox_api.waw_websocket_protocol import NativeWebSocketError, PartialFrameBudget

    pool = PartialFrameBudget()
    owners = [object() for _ in range(128)]
    slots = [pool.acquire(owner) for owner in owners]
    for slot, owner in zip(slots, owners, strict=True):
        pool.charge(slot, owner, 65536)
    assert pool.reserved_bytes == pool.peak_bytes == 8 * 1024 * 1024
    with pytest.raises(NativeWebSocketError):
        pool.acquire(object())
    with pytest.raises(NativeWebSocketError):
        pool.charge(slots[0], owners[0], 65537)
    assert not pool.release(slots[0], owners[1])
    assert pool.reserved_bytes == 8 * 1024 * 1024
    assert pool.release(slots[0], owners[0])
    assert not pool.release(slots[0], owners[0])
    smaller = PartialFrameBudget(slots=2, bytes_limit=100)
    first, second = object(), object()
    a, b = smaller.acquire(first), smaller.acquire(second)
    smaller.charge(a, first, 60)
    smaller.charge(b, second, 40)
    with pytest.raises(NativeWebSocketError):
        smaller.charge(b, second, 41)
    assert smaller.reserved_bytes == 100


@pytest.mark.parametrize("ending", ["complete", "protocol", "close", "abort", "disconnect"])
def test_partial_slot_releases_on_every_synchronous_end(ending: str) -> None:
    loop = asyncio.new_event_loop()
    protocol, _ = budget_protocol(
        loop, SimpleNamespace(connections=set(), tasks=set()), active=True
    )
    try:
        protocol.data_received(client_frame(b"a", fin=False))
        assert protocol.partial_budget.count == 1
        if ending == "complete":
            protocol.data_received(client_frame(b"b", opcode=0))
        elif ending == "protocol":
            protocol.data_received(client_frame(b"bad", masked=False))
        elif ending == "close":
            protocol.data_received(client_frame((1000).to_bytes(2, "big"), opcode=8))
        elif ending == "abort":
            protocol.abort(4403)
        else:
            protocol.connection_lost(None)
        assert protocol.partial_budget.count == protocol.partial_budget.reserved_bytes == 0
        protocol.connection_lost(None)
        assert protocol.partial_budget.count == 0
    finally:
        protocol.connection_lost(None)
        loop.close()


@pytest.mark.parametrize("cancel", [False, True])
def test_partial_slot_released_by_real_timer_or_asgi_cancellation(cancel: bool) -> None:
    async def run() -> None:
        async with connected() as (reader, writer, _seen, state):
            await reader.readuntil(b"\r\n\r\n")
            native = state["extensions"][NATIVE_SCOPE_KEY]
            writer.write(client_frame(b"a", fin=False))
            await writer.drain()
            async with asyncio.timeout(1):
                while native.partial_budget.count != 1:
                    await asyncio.sleep(0)
            if cancel:
                for task in tuple(native._tasks):
                    task.cancel()
            assert (await server_frame(reader))[0] == 8
            assert native.partial_budget.count == native.partial_budget.reserved_bytes == 0

    asyncio.run(run())


def test_parser_reserves_bulk_copies_and_growth_before_allocation() -> None:
    loop = asyncio.new_event_loop()
    protocol, _ = budget_protocol(
        loop, SimpleNamespace(connections=set(), tasks=set()), active=True
    )
    try:
        # Max V1 encoded INPUT is 16,468 bytes. Header/TCP fragmentation must
        # not change the legal message or omit scratch/growth allocation cost.
        payload = b"x" * 16468
        frame = client_frame(payload)
        for offset in range(0, len(frame), 251):
            protocol.data_received(frame[offset : offset + 251])
        assert not bool(protocol._closed)
        assert protocol._queue[0]["bytes"] == payload
        assert protocol.partial_budget.count == protocol.partial_budget.reserved_bytes == 0
        assert 2 * len(payload) < protocol.partial_budget.peak_slot_bytes <= 65536
        # A larger non-V1 payload may hit the stricter allocation ceiling even
        # though the RFC6455 payload ceiling itself remains 64 KiB.
        protocol.data_received(client_frame(b"x" * 24000))
        assert protocol._closed and protocol._close_code == 4429
        assert protocol.partial_budget.count == protocol.partial_budget.reserved_bytes == 0
        assert protocol.partial_budget.peak_slot_bytes <= 65536
    finally:
        protocol.connection_lost(None)
        loop.close()


def test_pool_full_still_allows_independently_bounded_native_control() -> None:
    from agentbox_api.waw_websocket_protocol import PartialFrameBudget

    loop = asyncio.new_event_loop()
    pool = PartialFrameBudget(slots=1)
    owner = object()
    slot = pool.acquire(owner)
    state = SimpleNamespace(connections=set(), tasks=set(), _agentbox_partial_budget=pool)
    protocol, transport = budget_protocol(loop, state, active=False)
    try:
        protocol.data_received(client_frame(b"nonce", opcode=9))
        assert not protocol._closed and pool.count == 1
        assert transport.writes == [b"\x8a\x05nonce"]
        assert pool.release(slot, owner)
    finally:
        protocol.connection_lost(None)
        loop.close()
