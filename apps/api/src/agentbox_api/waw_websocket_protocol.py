"""Native, bounded RFC6455 boundary for the fixed WAW ASGI endpoint.

Uvicorn supplies the HTTP upgrade handoff. This adapter owns frame parsing,
fragment deadlines and *all* automatic controls before ASGI reassembly. It uses
the existing RFC6455 policy, never compression or terminal-content decoding.
No raw request, cookie, key, control payload or application bytes are logged.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import re
import secrets
import sys
import threading
from collections import deque
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, cast

import h11
from agentbox_protocol.waw_websocket_contract import (
    WAWWebSocketContractError,
    WAWWebSocketDirection,
    WAWWebSocketSession,
    accept_frame,
)
from agentbox_protocol.waw_websocket_parser import parse_websocket_frame
from uvicorn.protocols.utils import get_local_addr, get_remote_addr, is_ssl

from agentbox_api.waw_input_budget import (
    BrowserDelivery,
    InputBudget,
    InputBudgetError,
    InputBudgetOverflow,
    InputBudgetOwner,
    InputBudgetToken,
    is_encoded_input,
)

NATIVE_SCOPE_KEY = "agentbox.waw.native.v1"
_PATH = re.compile(rb"/api/v1/workspaces/aws_[a-f0-9]{32}/stream")
_MAX_BUFFER = 65550
_MAX_MESSAGE = 65536
_BYTEARRAY_BASE = sys.getsizeof(bytearray())
_BYTES_BASE = sys.getsizeof(b"")


class NativeWebSocketError(RuntimeError):
    def __init__(self, close_code: int = 4400) -> None:
        self.close_code = close_code
        super().__init__("WAW native transport closed")


@dataclass(frozen=True, eq=False, repr=False)
class _PartialSlot:
    owner: object


class PartialFrameBudget:
    """One server's shared, exact-owner parser allocation budget.

    Charges include both retained arrays, conservative array growth, and bulk
    parsing copies before allocation. Native controls have their independent
    <=125-byte parser and never acquire an application partial slot.
    """

    def __init__(self, *, slots: int = 128, bytes_limit: int = 8 * 1024 * 1024) -> None:
        if (
            type(slots) is not int
            or not 1 <= slots <= 128
            or type(bytes_limit) is not int
            or not 1 <= bytes_limit <= 8 * 1024 * 1024
        ):
            raise ValueError("invalid partial-frame budget")
        self._maximum, self._byte_limit = slots, bytes_limit
        self._slots: dict[_PartialSlot, int] = {}
        self._bytes = 0
        self.peak_bytes = self.peak_slot_bytes = 0
        self._lock = threading.Lock()

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._slots)

    @property
    def reserved_bytes(self) -> int:
        with self._lock:
            return self._bytes

    def acquire(self, owner: object) -> _PartialSlot:
        with self._lock:
            if len(self._slots) >= self._maximum:
                raise NativeWebSocketError(4429)
            slot = _PartialSlot(owner)
            self._slots[slot] = 0
            return slot

    def charge(self, slot: _PartialSlot, owner: object, size: int) -> None:
        with self._lock:
            if slot.owner is not owner or slot not in self._slots:
                raise NativeWebSocketError()
            if type(size) is not int or not 0 <= size <= 65536:
                raise NativeWebSocketError(4429)
            total = self._bytes - self._slots[slot] + size
            if total > self._byte_limit:
                raise NativeWebSocketError(4429)
            self._slots[slot], self._bytes = size, total
            self.peak_bytes = max(self.peak_bytes, total)
            self.peak_slot_bytes = max(self.peak_slot_bytes, size)

    def release(self, slot: _PartialSlot, owner: object) -> bool:
        with self._lock:
            if slot.owner is not owner or slot not in self._slots:
                return False
            self._bytes -= self._slots.pop(slot)
            return True


_POOL_CREATION_LOCK = threading.Lock()


def _server_budget(server_state: Any) -> PartialFrameBudget:
    with _POOL_CREATION_LOCK:
        pool = getattr(server_state, "_agentbox_partial_budget", None)
        if pool is None:
            pool = PartialFrameBudget()
            server_state._agentbox_partial_budget = pool
        if type(pool) is not PartialFrameBudget:
            raise NativeWebSocketError()
        return pool


def server_frame(opcode: int, payload: bytes) -> bytes:
    """One unmasked, final, uncompressed server frame."""
    size = len(payload)
    if size > _MAX_MESSAGE:
        raise NativeWebSocketError(1009)
    length = (
        bytes((size,))
        if size < 126
        else (
            b"\x7e" + size.to_bytes(2, "big") if size < 65536 else b"\x7f" + size.to_bytes(8, "big")
        )
    )
    return bytes((0x80 | opcode,)) + length + payload


class WAWWebSocketProtocol(asyncio.Protocol):
    """Uvicorn protocol class; install explicitly with ``ws=...``.

    The scope capability is an instance, not a caller-provided header. Real WAW
    handlers require this exact adapter so an ordinary ASGI receive callback
    cannot accidentally claim native-frame qualification.
    """

    def __init__(
        self,
        config: Any,
        server_state: Any,
        app_state: dict[str, Any],
        _loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        if not config.loaded:
            config.load()
        self.loop = _loop or asyncio.get_event_loop()
        self.app = config.loaded_app
        self._state = app_state
        self._connections, self._tasks = server_state.connections, server_state.tasks
        self.partial_budget = _server_budget(server_state)
        self._partial_slot: _PartialSlot | None = None
        self._input_budget: InputBudget | None = None
        self.transport: asyncio.Transport | None = None
        self.scope: dict[str, Any] = {}
        self.peer_address: tuple[str, int] | None = None
        self.tls = False
        self._publication_guard: Callable[[bytes], None] | None = None
        self._http = h11.Connection(h11.SERVER, max_incomplete_event_size=8192)
        self._headers_size = 0
        self._key = b""
        self._requested = self._accepted = self._closed = self._lost = False
        self._close_code = 1006
        self._buffer = bytearray()
        self._message = bytearray()
        self._policy = WAWWebSocketSession()
        self._queue: deque[dict[str, Any]] = deque()
        self._delivery_tokens: dict[int, tuple[bytes, InputBudgetToken]] = {}
        self._queued_bytes = 0
        self._readable = asyncio.Event()
        self._writable = asyncio.Event()
        self._writable.set()
        self._fragment_timer: asyncio.TimerHandle | None = None
        self._close_timer: asyncio.TimerHandle | None = None
        self._ping_timer: asyncio.TimerHandle | None = None
        self._pong_timer: asyncio.TimerHandle | None = None
        self._pending_ping: bytes | None = None
        self._started = self.loop.time()
        self._window = self._slots = 0
        self._peer_ping_window = -1
        self._parsing = False
        self.message_limit = 4120

    @property
    def is_open(self) -> bool:
        return self._accepted and not self._closed

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = cast(asyncio.Transport, transport)
        self.transport.set_write_buffer_limits(high=0, low=0)
        self.peer_address = get_remote_addr(self.transport)
        self.tls = is_ssl(self.transport)
        self._connections.add(self)

    def connection_lost(self, exc: Exception | None) -> None:
        del exc
        self._lost = self._closed = True
        self._cancel_timers()
        self._connections.discard(self)
        self._buffer.clear()
        self._message.clear()
        self._release_partial()
        self._queue.clear()
        self._delivery_tokens.clear()
        self._queued_bytes = 0
        if self._input_budget is not None:
            self._input_budget.close()
        self._readable.set()
        self._writable.set()

    def pause_writing(self) -> None:
        self._writable.clear()

    def resume_writing(self) -> None:
        self._writable.set()

    def eof_received(self) -> None:
        self.close(1006)

    def shutdown(self) -> None:
        self.close(1012)

    def data_received(self, data: bytes) -> None:
        if self._closed:
            return
        try:
            if not self._requested:
                self._headers_size += len(data)
                if self._headers_size > 4096:
                    raise NativeWebSocketError()
                self._http.receive_data(data)
                event = self._http.next_event()
                if event is h11.NEED_DATA:
                    return
                if not isinstance(event, h11.Request):
                    raise NativeWebSocketError()
                self._upgrade(event)
                # Unaccepted early data is forbidden, not silently consumed.
                if self._http.trailing_data[0]:
                    raise NativeWebSocketError()
                return
            if not self._accepted:
                raise NativeWebSocketError()
            if len(data) > _MAX_BUFFER:
                raise NativeWebSocketError(1009)
            self._feed(data)
        except InputBudgetOverflow:
            self.abort(4429)
        except InputBudgetError:
            self.abort(4400)
        except NativeWebSocketError as error:
            self.close(error.close_code)
        except (h11.RemoteProtocolError, ValueError, WAWWebSocketContractError):
            self.close(4400)

    def _charge_partial(
        self, extra: int = 0, *, buffer_size: int | None = None, message_size: int | None = None
    ) -> None:
        if self._partial_slot is not None:
            # Charge actual owned array allocations (including spare capacity).
            # Before resize, reserve a conservative replacement alongside the
            # old allocation; before a bytes copy, reserve its full size too.
            size = sys.getsizeof(self._buffer) + sys.getsizeof(self._message) + extra
            for projected in (buffer_size, message_size):
                if projected is not None:
                    size += 2 * (projected + _BYTEARRAY_BASE)
            self.partial_budget.charge(self._partial_slot, self, size)

    def _release_partial(self) -> None:
        if self._partial_slot is not None:
            self.partial_budget.release(self._partial_slot, self)
            self._partial_slot = None

    def _feed(self, data: bytes) -> None:
        """Feed one header/body at a time, charging before any owned bulk copy."""
        view = memoryview(data)
        offset, completed = 0, 0
        try:
            while offset < len(view) and not self._closed:
                if completed >= 64:
                    raise NativeWebSocketError(4429)
                first = self._buffer[0] if self._buffer else view[offset]
                if first & 15 in (0, 2) and self._partial_slot is None:
                    self._partial_slot = self.partial_budget.acquire(self)
                length = len(self._buffer)
                target = 2
                if length >= 2:
                    short = self._buffer[1] & 127
                    extra = 2 if short == 126 else 8 if short == 127 else 0
                    target = 2 + extra
                    if length >= target:
                        size = int.from_bytes(self._buffer[2:target], "big") if extra else short
                        target += 4 + size
                count = min(target - length, len(view) - offset)
                if count <= 0:
                    raise NativeWebSocketError()
                self._charge_partial(buffer_size=length + count)
                piece = view[offset : offset + count]
                try:
                    self._buffer.extend(piece)
                finally:
                    piece.release()
                self._charge_partial()
                offset += count
                if self._fragment_timer is None:
                    self._fragment_timer = self.loop.call_later(0.1, self.close, 4408)
                self._parse()
                if not self._buffer:
                    completed += 1
        finally:
            view.release()

    def _upgrade(self, event: h11.Request) -> None:
        if (
            event.method != b"GET"
            or event.http_version != b"1.1"
            or _PATH.fullmatch(event.target) is None
        ):
            raise NativeWebSocketError()
        headers = list(event.headers)
        names: dict[bytes, bytes] = {}
        for name, value in headers:
            if name in names:
                # No duplicate Host/Origin/Cookie/upgrade/extension ambiguity.
                raise NativeWebSocketError()
            limit = 512 if name in (b"host", b"origin") else 4096 if name == b"cookie" else 256
            if len(value) > limit or any(v < 32 or v > 126 for v in value):
                raise NativeWebSocketError()
            names[name] = value
        key = names.get(b"sec-websocket-key", b"")
        if (
            names.get(b"upgrade", b"").lower() != b"websocket"
            or names.get(b"connection", b"").lower() != b"upgrade"
            or names.get(b"sec-websocket-version") != b"13"
            or b"origin" not in names
            or b"host" not in names
            or b"content-length" in names
            or b"transfer-encoding" in names
            or names.get(b"sec-websocket-protocol") != b"agentbox-waw-v1"
            or len(key) != 24
        ):
            raise NativeWebSocketError()
        try:
            decoded = base64.b64decode(key, validate=True)
        except ValueError:
            raise NativeWebSocketError() from None
        if len(decoded) != 16 or base64.b64encode(decoded) != key:
            raise NativeWebSocketError()
        self._key = key
        self._requested = True
        assert self.transport is not None
        self.scope = {
            "type": "websocket",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "scheme": "wss" if self.tls else "ws",
            "server": get_local_addr(self.transport),
            "client": self.peer_address,
            "root_path": "",
            "path": event.target.decode("ascii"),
            "raw_path": event.target,
            "query_string": b"",
            "headers": headers,
            "subprotocols": ["agentbox-waw-v1"],
            "state": self._state.copy(),
            "extensions": {NATIVE_SCOPE_KEY: self},
        }
        self._queue.append({"type": "websocket.connect"})
        self._readable.set()
        task = self.loop.create_task(self._run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self) -> None:
        try:
            await self.app(self.scope, self.receive, self.send)
        except BaseException:
            # Uvicorn's default exception formatter would disclose payloads.
            self.close(1011)
        finally:
            if not self._closed:
                self.close(1000 if self._accepted else 1008)

    def _parse(self) -> None:
        if self._parsing or self._closed:
            return
        self._parsing = True
        try:
            for _ in range(64):
                if len(self._buffer) < 2:
                    break
                first, second = self._buffer[:2]
                opcode, short = first & 15, second & 127
                if first & 0x70 or not second & 0x80 or opcode not in (0, 2, 8, 9, 10):
                    raise NativeWebSocketError()
                extra = 2 if short == 126 else 8 if short == 127 else 0
                if len(self._buffer) < 2 + extra:
                    break
                size = int.from_bytes(self._buffer[2 : 2 + extra], "big") if extra else short
                if extra and (size < (126 if extra == 2 else 65536) or size >= 2**63):
                    raise NativeWebSocketError()
                if opcode >= 8:
                    if not first & 0x80:
                        raise NativeWebSocketError()
                    if size > (125 if opcode == 8 else 32):
                        raise NativeWebSocketError(4400 if opcode == 8 else 4429)
                elif size > self.message_limit or len(self._message) + size > self.message_limit:
                    raise NativeWebSocketError(1009)
                total = 6 + extra + size
                if len(self._buffer) < total:
                    break
                raw_cost = _BYTES_BASE + total
                self._charge_partial(raw_cost)
                raw_view = memoryview(self._buffer)[:total]
                try:
                    raw = bytes(raw_view)
                finally:
                    raw_view.release()
                del self._buffer[:total]
                self._charge_partial(raw_cost)
                metadata = parse_websocket_frame(raw, WAWWebSocketDirection.CLIENT_TO_RUNTIME)
                self._policy = accept_frame(self._policy, metadata)
                key = raw[2 + extra : 6 + extra]
                payload_cost = _BYTES_BASE + size
                self._charge_partial(raw_cost + payload_cost)
                payload_view = memoryview(raw)[6 + extra :]
                try:
                    payload = bytes(
                        value ^ key[index % 4] for index, value in enumerate(payload_view)
                    )
                finally:
                    payload_view.release()
                del raw
                self._charge_partial(payload_cost)
                if opcode >= 8:
                    self._control(opcode, payload)
                else:
                    self._charge_partial(
                        payload_cost, message_size=len(self._message) + len(payload)
                    )
                    self._message.extend(payload)
                del payload
                self._charge_partial()
                if opcode < 8 and metadata.fin:
                    token: InputBudgetToken | None = None
                    try:
                        # Reserve the complete encoded INPUT before its immutable
                        # ready-queue bytes copy is allocated.  The parser pool
                        # continues to account for the short-lived copy itself.
                        if self._input_budget is not None and is_encoded_input(self._message):
                            try:
                                token = self._input_budget.reserve_native(len(self._message))
                            except InputBudgetError:
                                raise
                            except BaseException:
                                # An overflow-fence failure remains observable,
                                # but no browser bytes may continue afterward.
                                self.abort(4429)
                                raise
                        if (
                            self._queued_bytes + len(self._message) > 65536
                            or len(self._queue) >= 64
                        ):
                            raise NativeWebSocketError(4429)
                        self._charge_partial(_BYTES_BASE + len(self._message))
                        body = bytes(self._message)
                        self._message.clear()
                        self._charge_partial(_BYTES_BASE + len(body))
                        message: dict[str, Any] = {
                            "type": "websocket.receive",
                            "bytes": body,
                        }
                        if token is not None:
                            message["agentbox.waw.input-token.v1"] = token
                        self._queue.append(message)
                        self._queued_bytes += len(body)
                        token = None  # Ownership is now retained by the ready queue.
                        self._charge_partial()
                        self._readable.set()
                    except BaseException:
                        if token is not None and self._input_budget is not None:
                            self._input_budget.release(token, owner=InputBudgetOwner.NATIVE_READY)
                        raise
                if self.transport is None or self.transport.is_closing():
                    return
            else:
                # Bound callback work even for thousands of empty data frames.
                self.loop.call_soon(self._continue_parse)
            if not self._buffer and self._policy.fragment_count == 0:
                self._release_partial()
                if self._fragment_timer is not None:
                    self._fragment_timer.cancel()
                    self._fragment_timer = None
        finally:
            self._parsing = False

    def _continue_parse(self) -> None:
        try:
            self._parse()
        except InputBudgetOverflow:
            self.abort(4429)
        except InputBudgetError:
            self.abort(4400)
        except NativeWebSocketError as error:
            self.close(error.close_code)
        except WAWWebSocketContractError:
            self.close(4400)

    def _reserve_slots(self, count: int) -> None:
        window = int((self.loop.time() - self._started) // 5)
        if window != self._window:
            self._window, self._slots = window, (1 if self._pending_ping is not None else 0)
        if self._slots + count > 4:
            raise NativeWebSocketError(4429)
        self._slots += count

    def _control(self, opcode: int, payload: bytes) -> None:
        if opcode == 8:
            self._reserve_slots(1)
            # Validate the direction-specific WAW code allowlist at transport.
            code = int.from_bytes(payload[:2], "big") if payload else 1000
            if code not in (1000, 1001, 1008, 1009, 1011, 1012, 1013):
                raise NativeWebSocketError()
            self.close(code)
        elif opcode == 9:
            self._reserve_slots(2)
            if self._peer_ping_window == self._window:
                raise NativeWebSocketError(4429)
            self._peer_ping_window = self._window
            self._write(server_frame(10, payload))
        elif opcode == 10:
            self._reserve_slots(0)
            if self._pending_ping is None or not secrets.compare_digest(
                payload, self._pending_ping
            ):
                raise NativeWebSocketError()
            self._pending_ping = None
            if self._pong_timer is not None:
                self._pong_timer.cancel()
                self._pong_timer = None

    def _ping(self) -> None:
        if self._closed:
            return
        try:
            self._reserve_slots(2)
            if self._pending_ping is not None:
                raise NativeWebSocketError(4408)
            self._pending_ping = secrets.token_bytes(16)
            self._write(server_frame(9, self._pending_ping))
            self._pong_timer = self.loop.call_later(5, self.close, 4408)
            self._ping_timer = self.loop.call_later(20, self._ping)
        except NativeWebSocketError as error:
            self.close(error.close_code)

    def _write(self, raw: bytes) -> None:
        if self.transport is None or self._lost:
            raise NativeWebSocketError()
        if self.transport.get_write_buffer_size() + len(raw) > 65550:
            raise NativeWebSocketError(1013)
        self.transport.write(raw)

    async def receive(self) -> dict[str, Any]:
        while not self._queue and not self._closed:
            self._readable.clear()
            await self._readable.wait()
        if self._closed:
            return {"type": "websocket.disconnect", "code": self._close_code}
        message = self._queue.popleft()
        raw = message.get("bytes")
        self._queued_bytes -= len(raw) if type(raw) is bytes else 0
        token = message.pop("agentbox.waw.input-token.v1", None)
        if type(raw) is bytes and type(token) is InputBudgetToken:
            # The process-local capability is retained by native code and is
            # never placed in the ASGI message returned to application code.
            self._delivery_tokens[id(raw)] = (raw, token)
        return message

    def install_input_budget(self, budget: InputBudget) -> None:
        """Bind an exact attachment ledger without dropping pre-bound messages."""

        if self._input_budget is not None or type(budget) is not InputBudget:
            raise NativeWebSocketError()
        self._input_budget = budget
        try:
            for message in self._queue:
                raw = message.get("bytes")
                if type(raw) is bytes and is_encoded_input(raw):
                    message["agentbox.waw.input-token.v1"] = budget.reserve_native(len(raw))
        except InputBudgetOverflow:
            self.abort(4429)
            raise
        except BaseException:
            self.abort(4400)
            raise

    def claim_received(self, message: Mapping[str, Any]) -> BrowserDelivery:
        """Transfer one popped INPUT from native-ready to browser delivery."""

        raw = message.get("bytes")
        if type(raw) is not bytes:
            raise NativeWebSocketError()
        retained = self._delivery_tokens.pop(id(raw), None)
        token = retained[1] if retained is not None and retained[0] is raw else None
        if is_encoded_input(raw):
            if self._input_budget is None or type(token) is not InputBudgetToken:
                self.abort(4400)
                raise NativeWebSocketError()
            try:
                self._input_budget.transfer(
                    token,
                    source=InputBudgetOwner.NATIVE_READY,
                    target=InputBudgetOwner.BROWSER_DELIVERY,
                )
            except InputBudgetError:
                self.abort(4400)
                raise NativeWebSocketError() from None
            return BrowserDelivery(raw, token)
        if token is not None:
            self.abort(4400)
            raise NativeWebSocketError()
        return BrowserDelivery(raw)

    async def send(self, message: dict[str, Any]) -> None:
        if self._closed:
            raise NativeWebSocketError(self._close_code)
        kind = message.get("type")
        if kind == "websocket.close":
            self.close(message.get("code", 1000))
            return
        if not self._accepted:
            if (
                kind != "websocket.accept"
                or message.get("subprotocol") != "agentbox-waw-v1"
                or message.get("headers")
            ):
                raise NativeWebSocketError()
            accept = base64.b64encode(
                hashlib.sha1(self._key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest()
            )
            self._write(
                b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                b"Connection: Upgrade\r\nSec-WebSocket-Accept: "
                + accept
                + b"\r\nSec-WebSocket-Protocol: agentbox-waw-v1\r\nCache-Control: no-store\r\n\r\n"
            )
            self._accepted = True
            self._key = b""
            self._ping_timer = self.loop.call_later(20, self._ping)
            return
        payload = message.get("bytes")
        if (
            kind != "websocket.send"
            or type(payload) is not bytes
            or message.get("text") is not None
        ):
            raise NativeWebSocketError()
        await self._writable.wait()
        if self._closed:
            raise NativeWebSocketError(self._close_code)
        if self._publication_guard is not None:
            self._publication_guard(payload)
        if self._closed:
            raise NativeWebSocketError(self._close_code)
        self._write(server_frame(2, payload))
        # Retain the relay queue charge until asyncio has drained every byte.
        await self._writable.wait()
        if self._closed:
            raise NativeWebSocketError(self._close_code)

    def _cancel_timers(self) -> None:
        for timer in (self._fragment_timer, self._ping_timer, self._pong_timer, self._close_timer):
            if timer is not None:
                timer.cancel()
        self._pending_ping = None

    def close(self, code: int) -> None:
        if self._closed:
            return
        if self.transport is not None and self.transport.get_write_buffer_size():
            # A data frame is only partly published. A close reply cannot
            # justify draining the remaining ciphertext after the fence.
            self.abort(code)
            return
        self._cancel_timers()
        self._close_code = code
        self._closed = True
        self._buffer.clear()
        self._message.clear()
        self._release_partial()
        self._queue.clear()
        self._delivery_tokens.clear()
        self._queued_bytes = 0
        if self._input_budget is not None:
            self._input_budget.close()
        self._readable.set()
        self._writable.set()
        if self.transport is not None:
            with suppress(Exception):
                self.transport.write(
                    server_frame(8, (code if code != 1006 else 1001).to_bytes(2, "big"))
                    if self._accepted
                    else b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n"
                    b"Connection: close\r\nCache-Control: no-store\r\n\r\n"
                )
                self.transport.close()
            self._close_timer = self.loop.call_later(1, self.transport.abort)

    def abort(self, code: int) -> None:
        """Discard a partially published frame; never append CLOSE behind it."""
        self._cancel_timers()
        self._close_code = code
        self._closed = True
        self._buffer.clear()
        self._message.clear()
        self._release_partial()
        self._queue.clear()
        self._delivery_tokens.clear()
        self._queued_bytes = 0
        if self._input_budget is not None:
            self._input_budget.close()
        self._readable.set()
        self._writable.set()
        if self.transport is not None:
            self.transport.abort()

    def install_publication_guard(self, guard: Callable[[bytes], None]) -> None:
        if self._publication_guard is not None:
            raise NativeWebSocketError()
        self._publication_guard = guard
