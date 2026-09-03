"""Fixed in-memory WAW Noise NX application profile.

This component owns cryptographic state only, not admission, a trust provider,
process authority, sockets, or key files. A caller supplies independently bound
metadata and the browser's independently trusted static-key fingerprint. It must
also enforce the separate ADMITTED/process/ring fences before releasing data.
Call ``check_deadline`` from the owner's bounded admission timer when idle and
``destroy`` on every disconnect, epoch change, cancellation, or reconnect.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import re
import secrets
import threading
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

import rfc8785
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from agentbox_protocol.awce import (
    AUTH_TAG_SIZE,
    HEADER_SIZE,
    INPUT_DIRECTION,
    MAX_OUTPUT_CURSOR,
    MAX_TERMINAL_SEQUENCE,
    OUTPUT_DIRECTION,
    decode_awce,
    encode_awce_header,
)
from agentbox_protocol.noise_nx import (
    PROTOCOL_NAME,
    NoiseTransport,
    NXInitiator,
    NXResponder,
)
from agentbox_protocol.waw_crypto_context import (
    ADMISSION_KEYS,
    CONTEXT_KEYS,
    canonical_context_bytes,
    derive_context,
    validate_admission,
    validate_context,
    validate_hex32,
)

NOISE_PROTOCOL = PROTOCOL_NAME.decode("ascii")
INPUT_LIMIT = 16_384
OUTPUT_LIMIT = 32_768
HANDSHAKE_SECONDS = 5.0
KEY_FRAME_LIMIT = 4096
KEY_DECODE_SECONDS = 0.005
CONFIRM_DOMAIN = b"agentbox-waw/noise-confirm/v1"
ACK_CANARY = hashlib.sha256(b"agentbox-waw/noise-confirm-ack/v1").digest()
INPUT_LABEL = b"browser-to-runtime"
OUTPUT_LABEL = b"runtime-to-browser"
_COMMON_KEYS = {"protocol_version", "noise_protocol"}
KEY_FRAME_KEYS = {
    "KEY_INIT": ADMISSION_KEYS
    | _COMMON_KEYS
    | {
        "crypto_envelope_version",
        "runtime_epoch",
        "browser_ephemeral_public_key",
        "noise_message_1",
    },
    "KEY_ATTEST": ADMISSION_KEYS
    | _COMMON_KEYS
    | {
        "crypto_envelope_version",
        "runtime_epoch",
        "runtime_attestation_x25519_fingerprint",
        "runtime_ephemeral_public_key",
        "noise_message_2",
    },
    "KEY_CONFIRM": CONTEXT_KEYS | _COMMON_KEYS | {"ciphertext"},
    "KEY_CONFIRM_ACK": CONTEXT_KEYS
    | _COMMON_KEYS
    | {
        "status",
        "transcript_context_hash",
        "ciphertext",
    },
}
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+\Z")
_R = TypeVar("_R")
Frame = dict[str, str | int]


class WAWCryptoError(RuntimeError):
    """Fixed profile failure. The owner must close the enclosing attachment."""


def encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def decode_base64url(value: object, length: int) -> bytes:
    if (
        type(value) is not str
        or len(value) != (length * 8 + 5) // 6
        or _BASE64URL.fullmatch(value) is None
    ):
        raise WAWCryptoError("invalid canonical base64url")
    decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if len(decoded) != length or encode_base64url(decoded) != value:
        raise WAWCryptoError("invalid canonical base64url")
    return decoded


def _json_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    if len(pairs) > 64:
        raise WAWCryptoError("key frame exceeds object-key limit")
    for key, value in pairs:
        if key in result:
            raise WAWCryptoError("duplicate key frame field")
        result[key] = value
    return result


def _invalid_number(value: str) -> None:
    raise WAWCryptoError("invalid key frame numeric encoding")


def validate_key_frame(frame_type: str, value: object) -> Frame:
    """Validate exact flat key metadata; no authentication is implied.

    Bytes are strict UTF-8 JSON with duplicate detection. Exact dictionaries are
    accepted for in-process composition after the owner's wire parser. Returned
    scalars are copied. This function never learns expected context from a frame.
    """
    started = time.thread_time()
    try:
        if type(frame_type) is not str or frame_type not in KEY_FRAME_KEYS:
            raise WAWCryptoError("unknown key frame type")
        if type(value) is bytes:
            if not value or len(value) > KEY_FRAME_LIMIT:
                raise WAWCryptoError("invalid key frame size")
            value = json.loads(
                value.decode("utf-8"),
                object_pairs_hook=_json_pairs,
                parse_float=_invalid_number,
                parse_constant=_invalid_number,
            )
        if type(value) is not dict or value.keys() != KEY_FRAME_KEYS[frame_type]:
            raise WAWCryptoError("invalid key frame fields")
        if any(type(item) not in (str, int) for item in value.values()):
            raise WAWCryptoError("key frame must contain exact flat scalars")
        frame: Frame = dict(value)
        if (
            type(frame["protocol_version"]) is not int
            or frame["protocol_version"] != 1
            or frame["noise_protocol"] != NOISE_PROTOCOL
            or type(frame["crypto_envelope_version"]) is not int
            or frame["crypto_envelope_version"] != 1
        ):
            raise WAWCryptoError("unsupported key frame profile")
        if frame_type in {"KEY_INIT", "KEY_ATTEST"}:
            derive_context({key: frame[key] for key in ADMISSION_KEYS}, frame["runtime_epoch"])
        else:
            validate_context({key: frame[key] for key in CONTEXT_KEYS})
            decode_base64url(frame["ciphertext"], 48)
        if frame_type == "KEY_INIT":
            decode_base64url(frame["browser_ephemeral_public_key"], 32)
            decode_base64url(frame["noise_message_1"], 32)
        elif frame_type == "KEY_ATTEST":
            validate_hex32(frame["runtime_attestation_x25519_fingerprint"])
            decode_base64url(frame["runtime_ephemeral_public_key"], 32)
            decode_base64url(frame["noise_message_2"], 128)
        elif frame_type == "KEY_CONFIRM_ACK":
            if frame["status"] != "verified":
                raise WAWCryptoError("invalid key confirmation status")
            validate_hex32(frame["transcript_context_hash"])
        if len(rfc8785.dumps(frame)) > KEY_FRAME_LIMIT:
            raise WAWCryptoError("key frame exceeds control payload limit")
        if time.thread_time() - started > KEY_DECODE_SECONDS:
            raise WAWCryptoError("key frame decode deadline exceeded")
        return frame
    except WAWCryptoError:
        raise
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise WAWCryptoError("invalid key frame") from None


def _operation(method: Callable[..., _R]) -> Callable[..., _R]:
    @wraps(method)
    def wrapped(self: _Profile, *args: Any, **kwargs: Any) -> _R:
        if self._closing.is_set():
            raise WAWCryptoError("application crypto profile is closed")
        with self._lock:
            try:
                pending = self._phase != "CRYPTO_READY"
                self._check_live(pending)
                result = method(self, *args, **kwargs)
                # Reject completion after a reentrant or cross-thread close request.
                self._check_live(pending)
                if pending and self._phase == "CRYPTO_READY":
                    # Private phase changes are provisional until this final
                    # guard succeeds. Publish only fully checked readiness.
                    self._published_ready.set()
                return result
            except BaseException as exc:
                self.destroy()
                if isinstance(exc, WAWCryptoError) or not isinstance(exc, Exception):
                    raise
                raise WAWCryptoError("application crypto operation failed") from None

    return wrapped


class _Profile:
    def __init__(
        self,
        admission: object,
        runtime_epoch: object,
        *,
        clock: Callable[[], float],
        admission_started_at: float | None,
    ) -> None:
        self._closing = threading.Event()
        self._published_ready = threading.Event()
        self._lock = threading.RLock()
        self._phase = "INIT"
        self._handshake: NXInitiator | NXResponder | None = None
        self._transport: NoiseTransport | None = None
        self._challenge = b""
        self._hash = b""
        self._output_cursor = 0
        self._clock = clock
        self._admission = validate_admission(admission)
        self._context = derive_context(self._admission, runtime_epoch)
        self._prologue = canonical_context_bytes(self._context)
        now = self._clock()
        started = now if admission_started_at is None else admission_started_at
        if (
            type(now) not in (int, float)
            or not math.isfinite(now)
            or type(started) not in (int, float)
            or not math.isfinite(started)
            or started > now
            or now - started >= HANDSHAKE_SECONDS
        ):
            raise WAWCryptoError("invalid or expired admission deadline")
        self._last_tick = now
        self._deadline = started + HANDSHAKE_SECONDS

    def _check_live(self, pending: bool) -> None:
        if self._closing.is_set() or self._phase == "CLOSED":
            raise WAWCryptoError("application crypto profile is closed")
        now = self._clock()
        if (
            type(now) not in (int, float)
            or not math.isfinite(now)
            or now < self._last_tick
            or (pending and now >= self._deadline)
        ):
            raise WAWCryptoError("application crypto deadline or clock failed")
        self._last_tick = now
        if self._closing.is_set() or self._phase == "CLOSED":
            raise WAWCryptoError("application crypto profile is closed")

    def _expect(self, phase: str) -> None:
        if self._phase != phase:
            raise WAWCryptoError("key frame is out of order")

    def _bound_frame(self, frame_type: str, value: object) -> Frame:
        frame = validate_key_frame(frame_type, value)
        if frame_type in {"KEY_INIT", "KEY_ATTEST"}:
            bound = derive_context(
                {key: frame[key] for key in ADMISSION_KEYS}, frame["runtime_epoch"]
            )
        else:
            bound = {key: frame[key] for key in CONTEXT_KEYS}
        if bound != self._context:
            raise WAWCryptoError("key frame differs from bound context")
        return frame

    def _admission_frame(self) -> Frame:
        return {
            **self._admission,
            "runtime_epoch": self._context["runtime_epoch"],
            "protocol_version": 1,
            "crypto_envelope_version": 1,
            "noise_protocol": NOISE_PROTOCOL,
        }

    def _context_frame(self) -> Frame:
        return {**self._context, "protocol_version": 1, "noise_protocol": NOISE_PROTOCOL}

    def _take_transport(self) -> NoiseTransport:
        if self._handshake is None:
            raise WAWCryptoError("handshake is unavailable")
        self._transport = self._handshake.take_transport()
        self._handshake = None
        self._hash = self._transport.handshake_hash
        return self._transport

    def _ready_transport(self) -> NoiseTransport:
        self._expect("CRYPTO_READY")
        if self._transport is None:
            raise WAWCryptoError("transport is unavailable")
        return self._transport

    def _confirmation(self) -> bytes:
        return hashlib.sha256(
            CONFIRM_DOMAIN + (32).to_bytes(4, "big") + self._challenge + self._hash
        ).digest()

    @property
    def closed(self) -> bool:
        """Immediate invalidation; destroy() returning proves key cleanup finished."""
        return self._closing.is_set()

    @property
    def crypto_ready(self) -> bool:
        """Local crypto readiness only; never proves ADMITTED or peer receipt."""
        # Never expose the private phase before the final operation guard.
        # Neither flag waits for crypto; closing permanently overrides a
        # successful publication, including a concurrent publication attempt.
        return self._published_ready.is_set() and not self._closing.is_set()

    @property
    def transcript_context_hash(self) -> bytes:
        with self._lock:
            return self._hash

    @property
    def context_id(self) -> bytes:
        with self._lock:
            return self._hash[:16]

    @_operation
    def check_deadline(self) -> None:
        """Owner timer callback; an idle expired handshake is destroyed."""

    def destroy(self) -> None:
        # Publish invalidation before waiting for exclusive ownership. An
        # in-flight operation still owns its CipherState until it completes,
        # but its completion check cannot release a successful result after
        # observing this request. Never clear/reuse this signal on reconnect.
        self._closing.set()
        self._published_ready.clear()
        with self._lock:
            self._phase = "CLOSED"
            # An in-flight publication racing the initial close signal is
            # invisible to readers and is cleared again under ownership.
            self._published_ready.clear()
            if self._handshake is not None:
                self._handshake.destroy()
            if self._transport is not None:
                self._transport.destroy()
            self._handshake = None
            self._transport = None
            self._challenge = b""
            self._hash = b""

    def _encrypt(self, plaintext: object, direction: int, cursor: int) -> bytes:
        transport = self._ready_transport()
        limit = INPUT_LIMIT if direction == INPUT_DIRECTION else OUTPUT_LIMIT
        if type(plaintext) is not bytes or not 1 <= len(plaintext) <= limit:
            raise WAWCryptoError("plaintext is outside the active directional limit")
        sequence = transport.send.nonce
        if not 1 <= sequence <= MAX_TERMINAL_SEQUENCE:
            raise WAWCryptoError("terminal crypto sequence exhausted or unconfirmed")
        self._validate_cursor(direction, cursor)
        header = encode_awce_header(
            crypto_envelope_version=1,
            direction_id=direction,
            flags=0,
            crypto_sequence=sequence,
            stream_cursor=cursor,
            context_id=self._hash[:16],
            ciphertext_length=len(plaintext) + AUTH_TAG_SIZE,
        )
        label = INPUT_LABEL if direction == INPUT_DIRECTION else OUTPUT_LABEL
        ciphertext = transport.send.encrypt(plaintext, header + self._hash + label)
        if direction == OUTPUT_DIRECTION:
            self._output_cursor = cursor
        return header + ciphertext

    def _decrypt(self, raw: object, direction: int, cursor: int) -> bytes:
        transport = self._ready_transport()
        limit = INPUT_LIMIT if direction == INPUT_DIRECTION else OUTPUT_LIMIT
        if type(raw) is not bytes or not HEADER_SIZE + 17 <= len(raw) <= HEADER_SIZE + 16 + limit:
            raise WAWCryptoError("envelope is outside the active directional limit")
        envelope = decode_awce(raw)
        if (
            envelope.direction_id != direction
            or envelope.context_id != self._hash[:16]
            or envelope.crypto_sequence != transport.receive.nonce
            or envelope.stream_cursor != cursor
        ):
            raise WAWCryptoError(
                "envelope differs from bound direction, context, sequence or cursor"
            )
        self._validate_cursor(direction, cursor)
        label = INPUT_LABEL if direction == INPUT_DIRECTION else OUTPUT_LABEL
        plaintext = transport.receive.decrypt(
            envelope.ciphertext, raw[:HEADER_SIZE] + self._hash + label
        )
        if not 1 <= len(plaintext) <= limit:
            raise WAWCryptoError("authenticated plaintext exceeds directional limit")
        if direction == OUTPUT_DIRECTION:
            self._output_cursor = cursor
        return plaintext

    def _validate_cursor(self, direction: int, cursor: int) -> None:
        if type(cursor) is not int:
            raise WAWCryptoError("invalid cursor type")
        if direction == INPUT_DIRECTION:
            if cursor != 0:
                raise WAWCryptoError("INPUT cursor must be zero")
        elif not self._output_cursor < cursor <= MAX_OUTPUT_CURSOR:
            raise WAWCryptoError("OUTPUT cursor is not increasing or is exhausted")

    def __repr__(self) -> str:
        return f"<{type(self).__name__} redacted>"


class BrowserCryptoProfile(_Profile):
    """NX initiator; expected fingerprint must come from independent trust."""

    def __init__(
        self,
        admission: object,
        runtime_epoch: object,
        expected_static_fingerprint: object,
        *,
        ephemeral_private_key: bytes | None = None,
        clock: Callable[[], float] = time.monotonic,
        admission_started_at: float | None = None,
    ) -> None:
        super().__init__(
            admission, runtime_epoch, clock=clock, admission_started_at=admission_started_at
        )
        try:
            self._expected_fingerprint = validate_hex32(expected_static_fingerprint)
            self._handshake = NXInitiator(self._prologue, ephemeral_private_key)
        except BaseException:
            self.destroy()
            raise

    @_operation
    def start(self) -> Frame:
        self._expect("INIT")
        message = cast(NXInitiator, self._handshake).write_message1()
        self._phase = "WAIT_ATTEST"
        return {
            **self._admission_frame(),
            "browser_ephemeral_public_key": encode_base64url(message),
            "noise_message_1": encode_base64url(message),
        }

    @_operation
    def receive_attest(self, value: object) -> Frame:
        self._expect("WAIT_ATTEST")
        frame = self._bound_frame("KEY_ATTEST", value)
        message = decode_base64url(frame["noise_message_2"], 128)
        if message[:32] != decode_base64url(frame["runtime_ephemeral_public_key"], 32):
            raise WAWCryptoError("Runtime ephemeral key metadata mismatch")
        claimed = frame["runtime_attestation_x25519_fingerprint"]
        if claimed != self._expected_fingerprint:
            raise WAWCryptoError("Runtime fingerprint differs from independent pin")
        self._challenge = cast(NXInitiator, self._handshake).read_message2(message)
        if len(self._challenge) != 32:
            raise WAWCryptoError("invalid Runtime challenge")
        transport = self._take_transport()
        fingerprint = hashlib.sha256(transport.remote_static_public_key).hexdigest()
        if not hmac.compare_digest(fingerprint, self._expected_fingerprint):
            raise WAWCryptoError("Runtime static key differs from independent pin")
        if transport.send.nonce != 0 or transport.receive.nonce != 0:
            raise WAWCryptoError("confirmation requires fresh CipherStates")
        ciphertext = transport.send.encrypt(self._confirmation(), b"")
        self._challenge = b""
        self._phase = "WAIT_ACK"
        return {**self._context_frame(), "ciphertext": encode_base64url(ciphertext)}

    @_operation
    def receive_ack(self, value: object) -> None:
        self._expect("WAIT_ACK")
        frame = self._bound_frame("KEY_CONFIRM_ACK", value)
        transport = self._transport
        if transport is None or transport.receive.nonce != 0:
            raise WAWCryptoError("ACK requires the fresh responder CipherState")
        if frame["transcript_context_hash"] != self._hash.hex():
            raise WAWCryptoError("ACK transcript hash differs from local Noise hash")
        canary = transport.receive.decrypt(decode_base64url(frame["ciphertext"], 48), b"")
        if not hmac.compare_digest(canary, ACK_CANARY):
            raise WAWCryptoError("ACK canary failed")
        self._phase = "CRYPTO_READY"

    @_operation
    def encrypt_input(self, plaintext: object) -> bytes:
        return self._encrypt(plaintext, INPUT_DIRECTION, 0)

    @_operation
    def decrypt_output(self, raw: object, *, expected_cursor: int) -> bytes:
        """Authenticate the independently selected ring/GAP cursor; return bytes."""
        return self._decrypt(raw, OUTPUT_DIRECTION, expected_cursor)


class RuntimeCryptoProfile(_Profile):
    """NX responder using an in-memory key; this component performs no key I/O."""

    def __init__(
        self,
        admission: object,
        runtime_epoch: object,
        static_private_key: bytes,
        *,
        ephemeral_private_key: bytes | None = None,
        random_bytes: Callable[[int], bytes] = secrets.token_bytes,
        clock: Callable[[], float] = time.monotonic,
        admission_started_at: float | None = None,
    ) -> None:
        super().__init__(
            admission, runtime_epoch, clock=clock, admission_started_at=admission_started_at
        )
        try:
            self._handshake = NXResponder(self._prologue, static_private_key, ephemeral_private_key)
            public = (
                X25519PrivateKey.from_private_bytes(static_private_key)
                .public_key()
                .public_bytes_raw()
            )
            self._fingerprint = hashlib.sha256(public).hexdigest()
            self._random_bytes = random_bytes
        except BaseException:
            self.destroy()
            raise

    @_operation
    def receive_init(self, value: object) -> Frame:
        self._expect("INIT")
        frame = self._bound_frame("KEY_INIT", value)
        message = decode_base64url(frame["noise_message_1"], 32)
        if message != decode_base64url(frame["browser_ephemeral_public_key"], 32):
            raise WAWCryptoError("browser ephemeral key metadata mismatch")
        handshake = cast(NXResponder, self._handshake)
        if handshake.read_message1(message) != b"":
            raise WAWCryptoError("NX message 1 payload must be empty")
        self._challenge = self._random_bytes(32)
        if type(self._challenge) is not bytes or len(self._challenge) != 32:
            raise WAWCryptoError("Runtime challenge source failed")
        self._check_live(True)
        message2 = handshake.write_message2(self._challenge)
        self._take_transport()
        self._phase = "WAIT_CONFIRM"
        return {
            **self._admission_frame(),
            "runtime_attestation_x25519_fingerprint": self._fingerprint,
            "runtime_ephemeral_public_key": encode_base64url(message2[:32]),
            "noise_message_2": encode_base64url(message2),
        }

    @_operation
    def receive_confirm(self, value: object) -> Frame:
        self._expect("WAIT_CONFIRM")
        frame = self._bound_frame("KEY_CONFIRM", value)
        transport = self._transport
        if transport is None or transport.send.nonce != 0 or transport.receive.nonce != 0:
            raise WAWCryptoError("confirmation requires fresh CipherStates")
        plaintext = transport.receive.decrypt(decode_base64url(frame["ciphertext"], 48), b"")
        if not hmac.compare_digest(plaintext, self._confirmation()):
            raise WAWCryptoError("browser confirmation failed")
        ciphertext = transport.send.encrypt(ACK_CANARY, b"")
        self._challenge = b""
        self._phase = "CRYPTO_READY"
        return {
            **self._context_frame(),
            "status": "verified",
            "transcript_context_hash": self._hash.hex(),
            "ciphertext": encode_base64url(ciphertext),
        }

    @_operation
    def decrypt_input(self, raw: object) -> bytes:
        return self._decrypt(raw, INPUT_DIRECTION, 0)

    @_operation
    def encrypt_output(self, plaintext: object, stream_cursor: int) -> bytes:
        """Encrypt an already selected ring record; cursor assignment precedes AEAD."""
        return self._encrypt(plaintext, OUTPUT_DIRECTION, stream_cursor)


__all__ = [
    "ACK_CANARY",
    "BrowserCryptoProfile",
    "CONFIRM_DOMAIN",
    "Frame",
    "HANDSHAKE_SECONDS",
    "INPUT_LABEL",
    "INPUT_LIMIT",
    "KEY_FRAME_KEYS",
    "KEY_FRAME_LIMIT",
    "NOISE_PROTOCOL",
    "OUTPUT_LABEL",
    "OUTPUT_LIMIT",
    "RuntimeCryptoProfile",
    "WAWCryptoError",
    "decode_base64url",
    "encode_base64url",
    "validate_key_frame",
]
