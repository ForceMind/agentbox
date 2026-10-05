"""A3 fixed WebSocket relay: bounded metadata controls and opaque records only."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import time
from typing import Any
from urllib.parse import urlsplit

from agentbox_core.configuration import Settings
from agentbox_protocol.a3_content import ERROR_CODES, ContentError
from agentbox_protocol.a3_transport import NativeKind as K
from agentbox_protocol.a3_transport import facts_to_wire
from fastapi import WebSocket

from agentbox_api.a3_admission import A3SessionCurrentness
from agentbox_api.a3_native_transport import A3NativeBundle, A3NativeSource
from agentbox_api.waw_websocket_protocol import A3_NATIVE_SCOPE_KEY, WAWWebSocketProtocol

_PROJECT = re.compile(r"prj_[0-9a-f]{32}\Z")
_SELECTOR = re.compile(r"[A-Za-z0-9_-]{156}\Z")
_NONCE = re.compile(r"[0-9a-f]{64}\Z")
_READY = b"A3RD\x01"


def _invalid() -> ContentError:
    return ContentError()


def _opening(raw: bytes) -> dict[str, str]:
    def exact_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise _invalid()
            result[key] = value
        return result

    if not 1 <= len(raw) <= 8192:
        raise _invalid()
    try:
        value = json.loads(raw, object_pairs_hook=exact_pairs)
    except (ValueError, UnicodeError, RecursionError):
        raise _invalid() from None
    fields = {"schema_version", "selection_id", "request_nonce", "csrf_token"}
    if (
        type(value) is not dict
        or set(value) != fields
        or any(type(v) is not str for v in value.values())
    ):
        raise _invalid()
    if (
        value["schema_version"] != "a3-open/v1"
        or _SELECTOR.fullmatch(value["selection_id"]) is None
        or _NONCE.fullmatch(value["request_nonce"]) is None
        or not 1 <= len(value["csrf_token"]) <= 256
    ):
        raise _invalid()
    return value


class A3NativeRelay:
    """One browser owner; one record and one challenge mailbox, no relay backlog."""

    def __init__(self, source: A3NativeSource, settings: Settings) -> None:
        self.source, self.settings = source, settings
        self._active = 0

    async def __call__(self, websocket: WebSocket) -> None:
        native = websocket.scope.get("extensions", {}).get(A3_NATIVE_SCOPE_KEY)
        if type(native) is not WAWWebSocketProtocol or self._active >= 4:
            await websocket.close(code=1013)
            return
        self._active += 1
        bundle: A3NativeBundle | None = None
        current: A3SessionCurrentness | None = None
        tasks: list[asyncio.Task[Any]] = []
        try:
            project_id = websocket.path_params["project_id"]
            if _PROJECT.fullmatch(project_id) is None or websocket.query_params:
                raise _invalid()
            headers = dict(websocket.scope["headers"])
            origin = headers.get(b"origin", b"").decode("ascii")
            host = headers.get(b"host", b"").decode("ascii")
            if origin not in self.settings.allowed_origins or urlsplit(origin).netloc != host:
                raise _invalid()
            peer = ipaddress.ip_address(
                native.peer_address[0] if native.peer_address else "invalid"
            )
            proxy = any(peer in ipaddress.ip_network(n) for n in self.settings.trusted_proxies)
            if (
                not native.tls
                and not peer.is_loopback
                and not (
                    proxy
                    and headers.get(b"x-forwarded-proto") == b"https"
                    and origin.startswith("https:")
                )
            ):
                raise _invalid()
            cookies = [
                part.strip().partition("=")[2]
                for part in headers.get(b"cookie", b"").decode("ascii").split(";")
                if part.strip().partition("=")[0] == "agentbox_session"
            ]
            if len(cookies) != 1 or not 1 <= len(cookies[0]) <= 128:
                raise _invalid()
            authenticated = self.source.services.sessions.authenticate(cookies[0])
            await websocket.accept(subprotocol="agentbox-a3-content-v2")
            async with asyncio.timeout(5):
                opening = _opening(await websocket.receive_bytes())
            self.source.services.sessions.validate_csrf(authenticated, opening["csrf_token"])
            current = A3SessionCurrentness(
                self.source.services, authenticated, runtime_epoch=self.source.runtime_epoch
            )
            facts = current.current(project_id, current.session_scope)
            if facts is None:
                raise ContentError("PATCH_REVOKED")
            bundle = await self.source.connect(facts, current)
            native.message_limit = 24576
            await bundle.request(
                K.OPEN,
                {
                    "facts": facts_to_wire(facts),
                    "selection_id": opening["selection_id"],
                    "request_nonce": opening["request_nonce"],
                },
                K.OWNED,
                1,
            )
            await self._relay(websocket, native, bundle, tasks)
        except BaseException:
            # Never reflect cookie, selector, credentials, wire bytes or exception text.
            if not native._closed:
                native.abort(4400)
        finally:
            if bundle is not None:
                bundle.close()
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            try:
                if bundle is not None:
                    await bundle.wait_closed()
            finally:
                if current is not None:
                    current.close()
                self._active -= 1

    async def _relay(
        self,
        websocket: WebSocket,
        native: WAWWebSocketProtocol,
        bundle: A3NativeBundle,
        tasks: list[asyncio.Task[Any]],
    ) -> None:
        wake = asyncio.Event()
        ack = asyncio.Event()
        records: asyncio.Queue[bytes] = asyncio.Queue(1)
        challenge: tuple[int, bytes] | None = None
        expected_ack: bytes | None = None
        last_challenge = -1
        last_challenge_bytes: bytes | None = None
        ready_pending = False
        complete = False
        error: str | None = None
        ready_sent = False
        client_records = 0
        last_control = 0.0

        def closed() -> None:
            if not native._closed:
                native.abort(4403)
            wake.set()
            ack.set()

        bundle.subscribe_close(closed)

        def publish(raw: bytes) -> None:
            if raw == _READY:
                bundle.check_current()
            elif len(raw) == 25 and raw[:5] == b"A3CR\x01":
                bundle.live(int.from_bytes(raw[5:9], "big"), raw[9:])
            elif raw[:5] == b"A3ER\x01":
                bundle.check_current()
            else:
                bundle.publish(raw)

        native.install_publication_guard(publish)

        async def runtime_reader() -> None:
            nonlocal ready_pending, complete, error
            try:
                while True:
                    await bundle.opaque.await_readable(bundle.deadline_ns)
                    frame = await bundle.opaque.areceive(
                        frozenset({K.READY, K.RECORD, K.COMPLETE, K.ERROR}),
                        deadline_ns=min(bundle.deadline_ns, time.monotonic_ns() + 1_000_000_000),
                    )
                    if frame.kind is K.READY:
                        if ready_pending or bundle._ready or complete:
                            raise _invalid()
                        bundle._ready = True
                        ready_pending = True
                    elif frame.kind is K.RECORD:
                        if not bundle._ready or complete or type(frame.payload) is not bytes:
                            raise _invalid()
                        records.put_nowait(frame.payload)
                    elif frame.kind is K.COMPLETE:
                        if not bundle._ready or complete:
                            raise _invalid()
                        complete = True
                    else:
                        if (
                            type(frame.payload) is not dict
                            or frame.payload.get("code") not in ERROR_CODES
                        ):
                            raise _invalid()
                        error = str(frame.payload["code"])
                    wake.set()
            finally:
                bundle.close()

        async def browser_reader() -> None:
            nonlocal challenge, last_challenge, last_challenge_bytes, client_records, last_control
            try:
                while True:
                    raw = await websocket.receive_bytes()
                    if len(raw) == 41 and raw[:5] == b"A3CA\x01":
                        if expected_ack != raw or ack.is_set():
                            raise _invalid()
                        ack.set()
                    elif len(raw) == 25 and raw[:5] == b"A3CQ\x01":
                        sequence = int.from_bytes(raw[5:9], "big")
                        now = time.monotonic()
                        if (
                            not ready_sent
                            or challenge is not None
                            or sequence != last_challenge + 1
                            or raw[9:] == last_challenge_bytes
                            or (last_control and now - last_control < 0.1)
                        ):
                            raise _invalid()
                        challenge = sequence, raw[9:]
                        last_challenge, last_challenge_bytes, last_control = sequence, raw[9:], now
                        wake.set()
                    else:
                        if not ready_sent or raw.startswith(b"A3") or not 1 <= len(raw) <= 24576:
                            raise _invalid()
                        client_records += 1
                        if client_records > 3:
                            raise _invalid()
                        await bundle.opaque.asend(
                            K.RECORD,
                            raw,
                            deadline_ns=min(
                                bundle.deadline_ns, time.monotonic_ns() + 1_000_000_000
                            ),
                            guard=bundle.check_current,
                        )
            finally:
                bundle.close()

        async def idle_currentness() -> None:
            try:
                while True:
                    await asyncio.sleep(0.05)
                    bundle.check_current()
                    if time.monotonic_ns() >= bundle.deadline_ns or not native.is_open:
                        raise _invalid()
            finally:
                bundle.close()

        async def writer() -> None:
            nonlocal ready_pending, ready_sent, challenge, expected_ack
            try:
                while True:
                    bundle.check_peer()
                    wake.clear()
                    if error is not None:
                        await websocket.send_bytes(b"A3ER\x01" + error.encode("ascii"))
                        # The fixed error is wholly accepted/drained, then close.
                        native.close(1000)
                        return
                    if ready_pending:
                        ready_pending = False
                        await websocket.send_bytes(_READY)
                        ready_sent = True
                        continue
                    if challenge is not None:
                        sequence, value = challenge
                        # Keep the mailbox occupied through guarded publication.
                        await websocket.send_bytes(
                            b"A3CR\x01" + sequence.to_bytes(4, "big") + value
                        )
                        challenge = None
                        continue
                    if not records.empty():
                        raw = records.get_nowait()
                        sequence, digest = bundle.record(raw)
                        expected_ack = (
                            b"A3CA\x01" + (sequence - 1).to_bytes(4, "big") + bytes.fromhex(digest)
                        )
                        ack.clear()
                        # Awaiting send covers the native transport drain. An ACK
                        # arriving earlier is only one of the two required facts.
                        async with asyncio.timeout(1):
                            await websocket.send_bytes(raw)
                            await ack.wait()
                        bundle.check_peer()
                        if not ack.is_set():
                            raise _invalid()
                        expected_ack = None
                        await bundle.published(sequence, digest)
                        continue
                    await wake.wait()
            finally:
                bundle.close()

        tasks.extend(
            asyncio.create_task(coro())
            for coro in (runtime_reader, browser_reader, idle_currentness, writer)
        )
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
