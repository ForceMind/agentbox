"""Inert, independent A3 Noise session; no production key or transport I/O.

Trust/currentness ports are supplied by composition, not learned from wire data.
The owner must drive idle expiry and close on visibility, revocation and loss.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

import rfc8785

from agentbox_protocol.a3_content import (
    ContentContext,
    ContentError,
    ContentRead,
    application_aad,
    context_bytes,
    context_digest,
    decode_message,
    validate_context,
)
from agentbox_protocol.noise_nx import NoiseTransport, NXInitiator, NXResponder

MAX_OUTER_BYTES = 24 * 1024
MAX_KEY_BYTES = 4096
MAX_CIPHERTEXT_BYTES = 16384 + 16
HANDSHAKE_MS = 5000
RECORD_DOMAIN = "agentbox-a3-content/record/v1"
CONFIRM_DOMAIN = b"agentbox-a3-content/noise-confirm/v1"
ACK_CANARY = hashlib.sha256(b"agentbox-a3-content/noise-confirm-ack/v1").digest()
_KEY_LENGTHS = {
    "A3_KEY_INIT": 32,
    "A3_KEY_ATTEST": 128,
    "A3_KEY_CONFIRM": 48,
    "A3_KEY_CONFIRM_ACK": 48,
}
_ATOM = rb'(?:"[A-Za-z0-9_/:.\-]*"|0|[1-9][0-9]*)'
_FLAT = re.compile(rb'\{"[a-z_]+":' + _ATOM + rb'(?:,"[a-z_]+":' + _ATOM + rb")*\}\Z")
_R = TypeVar("_R")


def _canonical(value: object) -> bytes:
    return rfc8785.dumps(cast(Any, value))


def _hex(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ContentError()
    return value


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: object, low: int, high: int) -> bytes:
    if (
        type(value) is not str
        or not 1 <= len(value) <= (high * 8 + 5) // 6
        or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None
    ):
        raise ContentError()
    try:
        result = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except ValueError:
        raise ContentError() from None
    if not low <= len(result) <= high or _b64(result) != value:
        raise ContentError()
    return result


def _parse(raw: bytes, limit: int) -> dict[str, Any]:
    if type(raw) is not bytes or not 1 <= len(raw) <= limit or _FLAT.fullmatch(raw) is None:
        raise ContentError()
    try:
        value = json.loads(raw)
        if len(value) > 7 or _canonical(value) != raw:
            raise ContentError()
    except (ValueError, OverflowError):
        raise ContentError() from None
    return cast(dict[str, Any], value)


def decode_key(raw: bytes) -> dict[str, Any]:
    """Strict opaque key schema, not a pin or authentication source."""
    value = _parse(raw, MAX_KEY_BYTES)
    kind = value.get("kind")
    if type(kind) is not str or kind not in _KEY_LENGTHS:
        raise ContentError()
    keys = {"protocol_id", "protocol_version", "context_digest", "kind", "data"}
    if kind == "A3_KEY_CONFIRM_ACK":
        keys.add("transcript_hash")
        _hex(value.get("transcript_hash"))
    if (
        value.keys() != keys
        or value["protocol_id"] != "agentbox-a3-content/v1"
        or type(value["protocol_version"]) is not int
        or value["protocol_version"] != 1
    ):
        raise ContentError()
    _hex(value["context_digest"])
    _unb64(value["data"], _KEY_LENGTHS[kind], _KEY_LENGTHS[kind])
    return value


def decode_record(raw: bytes) -> dict[str, Any]:
    """Bound allocation before parsing/decoding any untrusted ciphertext."""
    value = _parse(raw, MAX_OUTER_BYTES)
    if value.keys() != {"domain", "context_digest", "kind", "sequence", "ciphertext"}:
        raise ContentError()
    if value["domain"] != RECORD_DOMAIN:
        raise ContentError()
    _hex(value["context_digest"])
    kind, seq = value["kind"], value["sequence"]
    if type(kind) is not str or type(seq) is not int:
        raise ContentError()
    if not (
        (kind in ("PATCH_READ", "PATCH_ERROR") and seq == 0)
        or (kind == "PATCH_PAGE" and 0 <= seq < 16)
        or (kind == "PATCH_END" and 1 <= seq <= 16)
    ):
        raise ContentError()
    _unb64(value["ciphertext"], 17, MAX_CIPHERTEXT_BYTES)
    return value


def _operation(method: Callable[..., _R]) -> Callable[..., _R]:
    @wraps(method)
    def wrapped(self: _Profile, *args: Any, **kwargs: Any) -> _R:
        with self._lock:
            try:
                pending = self._phase != "READY"
                self._check(pending)
                result = method(self, *args, **kwargs)
                self._check(pending)
                if self._phase == "READY":
                    self._ready.set()
                if self._complete:
                    self.close()
                return result
            except BaseException as exc:
                self.close()
                if isinstance(exc, ContentError) or not isinstance(exc, Exception):
                    raise
                raise ContentError() from None

    return wrapped


class _Profile:
    def __init__(
        self,
        context: object,
        *,
        clock_ms: Callable[[], int],
        current: Callable[[], ContentContext],
        deadline_ms: int,
    ) -> None:
        self._lock = threading.RLock()
        self._closing = threading.Event()
        self._ready = threading.Event()
        self._phase = "INIT"
        self._complete = False
        self._context = validate_context(context)
        self._digest = context_digest(self._context)
        self._clock = clock_ms
        self._current = current
        now = clock_ms()
        if (
            type(now) is not int
            or not 0 <= now < 2**53
            or type(deadline_ms) is not int
            or not now < deadline_ms <= min(now + 30000, 2**53 - 1)
        ):
            raise ContentError()
        self._last = now
        self._deadline = deadline_ms
        self._handshake_deadline = min(deadline_ms, now + HANDSHAKE_MS)
        self._handshake: NXInitiator | NXResponder | None = None
        self._transport: NoiseTransport | None = None
        self._challenge = b""
        self._hash = b""
        self._read = ContentRead(self._context, now_ms=now, deadline_ms=deadline_ms)

    def _check(self, pending: bool) -> None:
        now = self._clock()
        if (
            self._closing.is_set()
            or type(now) is not int
            or now < self._last
            or now >= (self._handshake_deadline if pending else self._deadline)
            or validate_context(self._current()) != self._context
        ):
            raise ContentError("PATCH_REVOKED")
        self._last = now
        if self._closing.is_set():
            raise ContentError()

    @_operation
    def check(self) -> None:
        """Called by the owning timer and immediately before each actual send."""

    @property
    def crypto_ready(self) -> bool:
        return self._ready.is_set() and not self._closing.is_set()

    def close(self) -> None:
        self._closing.set()
        self._ready.clear()
        with self._lock:
            self._phase = "CLOSED"
            self._read.close()
            if self._handshake is not None:
                self._handshake.destroy()
            if self._transport is not None:
                self._transport.destroy()
            self._handshake = None
            self._transport = None
            self._hash = self._challenge = b""

    def _expect(self, phase: str) -> None:
        if self._phase != phase:
            raise ContentError()

    def _key(self, kind: str, data: bytes, **extra: str) -> bytes:
        raw = _canonical(
            {
                "protocol_id": "agentbox-a3-content/v1",
                "protocol_version": 1,
                "context_digest": self._digest,
                "kind": kind,
                "data": _b64(data),
                **extra,
            }
        )
        decode_key(raw)
        return raw

    def _bound_key(self, raw: bytes, kind: str) -> dict[str, Any]:
        value = decode_key(raw)
        if value["kind"] != kind or value["context_digest"] != self._digest:
            raise ContentError()
        return value

    def _take(self) -> NoiseTransport:
        assert self._handshake is not None
        self._transport = self._handshake.take_transport()
        self._handshake = None
        self._hash = self._transport.handshake_hash
        if self._transport.send.nonce != 0 or self._transport.receive.nonce != 0:
            raise ContentError()
        return self._transport

    def _confirmation(self) -> bytes:
        return hashlib.sha256(
            CONFIRM_DOMAIN + (32).to_bytes(4, "big") + self._challenge + self._hash
        ).digest()

    def _encode(self, raw: bytes, browser: bool) -> bytes:
        self._expect("READY")
        message = decode_message(raw)
        kind, seq = message["kind"], message.get("sequence", 0)
        if (kind == "PATCH_READ") != browser:
            raise ContentError()
        try:
            self._read.accept(raw, now_ms=self._clock(), current_context=self._current())
        except ContentError as exc:
            # ERROR is terminal by definition; only the exact validated error
            # after a begun, correctly bound READ may be sent to the peer.
            if message["kind"] != "PATCH_ERROR" or str(exc) != message["code"]:
                raise
        transport = self._transport
        if transport is None or not 1 <= transport.send.nonce <= 17:
            raise ContentError()
        cipher = transport.send.encrypt(
            raw, application_aad(self._context, self._hash.hex(), kind, cast(int, seq))
        )
        result = _canonical(
            {
                "domain": RECORD_DOMAIN,
                "context_digest": self._digest,
                "kind": kind,
                "sequence": seq,
                "ciphertext": _b64(cipher),
            }
        )
        decode_record(result)
        return result

    def _decode(self, raw: bytes, browser: bool) -> tuple[bytes, bytes | None]:
        self._expect("READY")
        value = decode_record(raw)
        if value["context_digest"] != self._digest or (value["kind"] == "PATCH_READ") == browser:
            raise ContentError()
        transport = self._transport
        if transport is None or not 1 <= transport.receive.nonce <= 17:
            raise ContentError()
        plain = transport.receive.decrypt(
            _unb64(value["ciphertext"], 17, MAX_CIPHERTEXT_BYTES),
            application_aad(self._context, self._hash.hex(), value["kind"], value["sequence"]),
        )
        message = decode_message(plain)
        if (
            message["context_digest"] != value["context_digest"]
            or message["kind"] != value["kind"]
            or message.get("sequence", 0) != value["sequence"]
            or message["request_nonce"] != self._context["request_nonce"]
        ):
            raise ContentError()
        complete = self._read.accept(plain, now_ms=self._clock(), current_context=self._current())
        return plain, complete

    def __repr__(self) -> str:
        return f"<{type(self).__name__} redacted>"


class A3Browser(_Profile):
    """Fixture-capable initiator; independent pin/currentness provider is required."""

    def __init__(
        self,
        context: object,
        *,
        expected_pin: Callable[[], str],
        clock_ms: Callable[[], int],
        current: Callable[[], ContentContext],
        deadline_ms: int,
        ephemeral_private_key: bytes | None = None,
    ) -> None:
        super().__init__(context, clock_ms=clock_ms, current=current, deadline_ms=deadline_ms)
        self._pin_port = expected_pin
        self._pin = _hex(expected_pin())
        self._handshake = NXInitiator(context_bytes(self._context), ephemeral_private_key)

    def _check(self, pending: bool) -> None:
        super()._check(pending)
        if _hex(self._pin_port()) != self._pin:
            raise ContentError("PATCH_REVOKED")

    @_operation
    def start(self) -> bytes:
        self._expect("INIT")
        raw = cast(NXInitiator, self._handshake).write_message1()
        self._phase = "ATTEST"
        return self._key("A3_KEY_INIT", raw)

    @_operation
    def receive_attest(self, raw: bytes) -> bytes:
        self._expect("ATTEST")
        value = self._bound_key(raw, "A3_KEY_ATTEST")
        self._challenge = cast(NXInitiator, self._handshake).read_message2(
            _unb64(value["data"], 128, 128)
        )
        if len(self._challenge) != 32:
            raise ContentError()
        transport = self._take()
        if not hmac.compare_digest(
            hashlib.sha256(transport.remote_static_public_key).hexdigest(), self._pin
        ):
            raise ContentError()
        confirm = transport.send.encrypt(self._confirmation(), b"")
        self._challenge = b""
        self._phase = "ACK"
        return self._key("A3_KEY_CONFIRM", confirm)

    @_operation
    def receive_ack(self, raw: bytes) -> None:
        self._expect("ACK")
        value = self._bound_key(raw, "A3_KEY_CONFIRM_ACK")
        transport = self._transport
        if (
            transport is None
            or transport.receive.nonce != 0
            or value["transcript_hash"] != self._hash.hex()
        ):
            raise ContentError()
        if not hmac.compare_digest(
            transport.receive.decrypt(_unb64(value["data"], 48, 48), b""), ACK_CANARY
        ):
            raise ContentError()
        self._phase = "READY"

    @_operation
    def encrypt_read(self, raw: bytes) -> bytes:
        return self._encode(raw, True)

    @_operation
    def receive_record(self, raw: bytes) -> bytes | None:
        result = self._decode(raw, True)[1]
        self._complete = result is not None
        return result


class A3Runtime(_Profile):
    """Responder receives an in-memory key from trusted composition; no key loading."""

    def __init__(
        self,
        context: object,
        static_private_key: bytes,
        *,
        clock_ms: Callable[[], int],
        current: Callable[[], ContentContext],
        deadline_ms: int,
        ephemeral_private_key: bytes | None = None,
        random_bytes: Callable[[int], bytes] = secrets.token_bytes,
    ) -> None:
        super().__init__(context, clock_ms=clock_ms, current=current, deadline_ms=deadline_ms)
        self._random = random_bytes
        self._handshake = NXResponder(
            context_bytes(self._context), static_private_key, ephemeral_private_key
        )

    @_operation
    def receive_init(self, raw: bytes) -> bytes:
        self._expect("INIT")
        value = self._bound_key(raw, "A3_KEY_INIT")
        handshake = cast(NXResponder, self._handshake)
        if handshake.read_message1(_unb64(value["data"], 32, 32)) != b"":
            raise ContentError()
        self._challenge = self._random(32)
        if type(self._challenge) is not bytes or len(self._challenge) != 32:
            raise ContentError()
        self._check(True)
        message = handshake.write_message2(self._challenge)
        self._take()
        self._phase = "CONFIRM"
        return self._key("A3_KEY_ATTEST", message)

    @_operation
    def receive_confirm(self, raw: bytes) -> bytes:
        self._expect("CONFIRM")
        value = self._bound_key(raw, "A3_KEY_CONFIRM")
        transport = self._transport
        if transport is None or transport.receive.nonce != 0 or transport.send.nonce != 0:
            raise ContentError()
        if not hmac.compare_digest(
            transport.receive.decrypt(_unb64(value["data"], 48, 48), b""), self._confirmation()
        ):
            raise ContentError()
        ack = transport.send.encrypt(ACK_CANARY, b"")
        self._challenge = b""
        self._phase = "READY"
        return self._key("A3_KEY_CONFIRM_ACK", ack, transcript_hash=self._hash.hex())

    @_operation
    def receive_read(self, raw: bytes) -> bytes:
        return self._decode(raw, False)[0]

    @_operation
    def encrypt_record(self, raw: bytes) -> bytes:
        return self._encode(raw, False)
