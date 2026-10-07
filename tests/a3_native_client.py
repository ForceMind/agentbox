"""Small test-only RFC6455 client; actual API native framing is exercised."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import socket
import time
from typing import Any
from urllib.parse import urlsplit

import httpx
from a3_native_fixture import PASSWORD, PIN, PROJECT_ID, USERNAME, A3NativeFixture
from agentbox_protocol.a3_content import (
    context_digest,
    encode_message,
    selector_commitment,
    validate_context,
)
from agentbox_protocol.a3_crypto import A3Browser


def login(fixture: A3NativeFixture) -> tuple[httpx.Client, str]:
    client = httpx.Client(
        base_url=fixture.api_origin, headers={"Origin": fixture.api_origin}, timeout=10
    )
    response = client.post("/api/v1/auth/login", json={"username": USERNAME, "password": PASSWORD})
    assert response.status_code == 200
    return client, response.json()["data"]["csrf_token"]


def observe(client: httpx.Client, csrf: str) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/projects/{PROJECT_ID}/git/staged-observation", headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()["data"]
    return result


class NativeBrowser:
    def __init__(
        self,
        fixture: A3NativeFixture,
        client: httpx.Client,
        csrf: str,
        metadata: dict[str, Any],
        *,
        filename: str = "success.txt",
        nonce: str | None = None,
    ) -> None:
        self.ack_sequence = 0
        self.challenge_sequence = 0
        entry = next(item for item in metadata["entries"] if item["path"] == filename)
        self.selection = entry["selection_id"]
        self.nonce = nonce or secrets.token_hex(32)
        facts = {key: value for key, value in metadata["binding"].items() if key != "auth_epoch"}
        self.context = validate_context(
            {
                **facts,
                "protocol_id": "agentbox-a3-content/v1",
                "protocol_version": 1,
                "selector_commitment": selector_commitment(self.selection),
                "side": "staged",
                "request_nonce": self.nonce,
            }
        )
        self.crypto = A3Browser(
            self.context,
            expected_pin=lambda: hashlib.sha256(bytes.fromhex(PIN)).hexdigest(),
            clock_ms=lambda: time.monotonic_ns() // 1_000_000,
            current=lambda: self.context,
            deadline_ms=time.monotonic_ns() // 1_000_000 + 30000,
        )
        address = urlsplit(fixture.api_origin)
        self.socket = socket.create_connection(
            (address.hostname or "127.0.0.1", address.port or 80), 5
        )
        self.socket.settimeout(3)
        key = base64.b64encode(secrets.token_bytes(16)).decode()
        self.socket.sendall(
            (
                f"GET /api/v1/projects/{PROJECT_ID}/git/staged-stream HTTP/1.1\r\n"
                f"Host: {address.netloc}\r\nOrigin: {fixture.api_origin}\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\n"
                f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Protocol: agentbox-a3-content-v2\r\n"
                f"Cookie: agentbox_session={client.cookies['agentbox_session']}\r\n\r\n"
            ).encode("ascii")
        )
        response = bytearray()
        while not response.endswith(b"\r\n\r\n"):
            response.extend(self.exact(1))
            if len(response) > 8192:
                raise AssertionError("unbounded HTTP upgrade")
        assert response.startswith(b"HTTP/1.1 101 ")
        self.send(
            json.dumps(
                {
                    "schema_version": "a3-open/v1",
                    "selection_id": self.selection,
                    "request_nonce": self.nonce,
                    "csrf_token": csrf,
                }
            ).encode()
        )

    def exact(self, size: int, *, deadline: float | None = None) -> bytes:
        result = bytearray()
        while len(result) < size:
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("test WebSocket receive expired")
                self.socket.settimeout(remaining)
            raw = self.socket.recv(size - len(result))
            if not raw:
                raise EOFError("native WebSocket closed")
            result.extend(raw)
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("test WebSocket receive expired")
        return bytes(result)

    def send(self, payload: bytes, *, deadline: float | None = None) -> None:
        self._send_frame(2, payload, deadline=deadline)

    def _send_frame(self, opcode: int, payload: bytes, *, deadline: float | None = None) -> None:
        assert opcode in {2, 8, 10}
        size = len(payload)
        assert size <= (24576 if opcode == 2 else 125)
        mask = secrets.token_bytes(4)
        header = (
            bytes((0x80 | opcode, 0x80 | size))
            if size < 126
            else bytes((0x80 | opcode, 0xFE)) + size.to_bytes(2, "big")
        )
        frame = header + mask + bytes(value ^ mask[i % 4] for i, value in enumerate(payload))
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("test WebSocket control expired")
            self.socket.settimeout(remaining)
        self.socket.sendall(frame)
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("test WebSocket control expired")

    def receive(self, *, deadline: float | None = None) -> bytes:
        # RFC6455 automatic controls are outside the A3 application transcript.
        # Answer the server's normal 20-second PING without extending any A3 TTL.
        if deadline is None:
            deadline = time.monotonic() + 3
        for _ in range(9):
            header = self.exact(2, deadline=deadline)
            assert header[0] in {0x82, 0x88, 0x89, 0x8A} and header[1] < 128
            opcode, size = header[0] & 15, header[1]
            if opcode != 2:
                assert size <= 125
            elif size == 126:
                size = int.from_bytes(self.exact(2, deadline=deadline), "big")
                assert size >= 126
            elif size == 127:
                size = int.from_bytes(self.exact(8, deadline=deadline), "big")
                assert size >= 65536
            assert size <= 24576
            payload = self.exact(size, deadline=deadline)
            if opcode == 2:
                return payload
            if opcode == 9:
                self._send_frame(10, payload, deadline=deadline)
            elif opcode == 8:
                assert len(payload) != 1
                if len(payload) >= 2:
                    code = int.from_bytes(payload[:2], "big")
                    assert (
                        code
                        in {1000, 1001, 1002, 1003, 1007, 1008, 1009, 1010, 1011, 1012, 1013, 1014}
                        or 3000 <= code <= 4999
                    )
                    payload[2:].decode("utf-8", errors="strict")
                self._send_frame(8, payload, deadline=deadline)
                raise EOFError("native WebSocket close frame")
            # Bounded unsolicited PONG handling is permitted by RFC6455.
        raise AssertionError("test WebSocket control flood")

    def current(self, *, deadline: float | None = None, challenge: bytes | None = None) -> None:
        challenge = secrets.token_bytes(16) if challenge is None else challenge
        assert len(challenge) == 16
        suffix = self.challenge_sequence.to_bytes(4, "big") + challenge
        self.send(b"A3CQ\x01" + suffix, deadline=deadline)
        assert self.receive(deadline=deadline) == b"A3CR\x01" + suffix
        self.challenge_sequence += 1

    def record(self, *, ack: bool = True, deadline: float | None = None) -> bytes:
        raw = self.receive(deadline=deadline)
        assert not raw.startswith((b"A3CR", b"A3RD", b"A3ER"))
        if ack:
            self.ack(raw, deadline=deadline)
        return raw

    def ack(self, raw: bytes, *, deadline: float | None = None) -> None:
        self.send(
            b"A3CA\x01" + self.ack_sequence.to_bytes(4, "big") + hashlib.sha256(raw).digest(),
            deadline=deadline,
        )
        self.ack_sequence += 1

    def handshake(self) -> None:
        assert self.receive() == b"A3RD\x01"
        self.current()
        self.send(self.crypto.start())
        self.send(self.crypto.receive_attest(self.record()))
        self.crypto.receive_ack(self.record())
        self.send(
            self.crypto.encrypt_read(
                encode_message(
                    {
                        "protocol_id": "agentbox-a3-content/v1",
                        "protocol_version": 1,
                        "context_digest": context_digest(self.context),
                        "request_nonce": self.nonce,
                        "kind": "PATCH_READ",
                        "selection_id": self.selection,
                    }
                )
            )
        )

    def complete(self) -> bytes:
        self.handshake()
        result = None
        while result is None:
            result = self.crypto.receive_record(self.record())
        return result

    def close(self) -> None:
        self.crypto.close()
        self.socket.close()
