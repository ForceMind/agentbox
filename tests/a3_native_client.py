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
from agentbox_protocol.a3_content import context_digest, encode_message, validate_context
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
                "selector_commitment": hashlib.sha256(self.selection.encode("ascii")).hexdigest(),
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

    def exact(self, size: int) -> bytes:
        result = bytearray()
        while len(result) < size:
            raw = self.socket.recv(size - len(result))
            if not raw:
                raise EOFError("native WebSocket closed")
            result.extend(raw)
        return bytes(result)

    def send(self, payload: bytes) -> None:
        mask = secrets.token_bytes(4)
        size = len(payload)
        header = bytes((0x82, 0x80 | size)) if size < 126 else b"\x82\xfe" + size.to_bytes(2, "big")
        self.socket.sendall(
            header + mask + bytes(value ^ mask[i % 4] for i, value in enumerate(payload))
        )

    def receive(self) -> bytes:
        header = self.exact(2)
        if header[0] == 0x88:
            raise EOFError("native WebSocket close frame")
        assert header[0] == 0x82 and header[1] < 128
        size = header[1]
        if size == 126:
            size = int.from_bytes(self.exact(2), "big")
        elif size == 127:
            size = int.from_bytes(self.exact(8), "big")
        assert size <= 24576
        return self.exact(size)

    def current(self) -> None:
        challenge = secrets.token_bytes(16)
        suffix = self.challenge_sequence.to_bytes(4, "big") + challenge
        self.send(b"A3CQ\x01" + suffix)
        assert self.receive() == b"A3CR\x01" + suffix
        self.challenge_sequence += 1

    def record(self, *, ack: bool = True) -> bytes:
        raw = self.receive()
        assert not raw.startswith((b"A3CR", b"A3RD", b"A3ER"))
        if ack:
            self.ack(raw)
        return raw

    def ack(self, raw: bytes) -> None:
        self.send(b"A3CA\x01" + self.ack_sequence.to_bytes(4, "big") + hashlib.sha256(raw).digest())
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
