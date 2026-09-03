"""Strict opaque AgentBox WAW Crypto Envelope (AWCE) v1 framing.

This codec owns the immutable application envelope only.  It deliberately does
not encrypt, decrypt, construct associated data, or advance a Noise state.
Ciphertext and context identifiers stay opaque at this layer.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

MAGIC = b"AWCE"
VERSION = 1
HEADER_SIZE = 44
AUTH_TAG_SIZE = 16
MIN_PLAINTEXT_SIZE = 1
MAX_PLAINTEXT_SIZE = 49_152
MIN_CIPHERTEXT_SIZE = MIN_PLAINTEXT_SIZE + AUTH_TAG_SIZE
MAX_CIPHERTEXT_SIZE = MAX_PLAINTEXT_SIZE + AUTH_TAG_SIZE
MIN_ENVELOPE_SIZE = HEADER_SIZE + MIN_CIPHERTEXT_SIZE
MAX_ENVELOPE_SIZE = HEADER_SIZE + MAX_CIPHERTEXT_SIZE
CONTEXT_ID_SIZE = 16
INPUT_DIRECTION = 1
OUTPUT_DIRECTION = 2
MIN_TERMINAL_SEQUENCE = 1
MAX_TERMINAL_SEQUENCE = 0xFFFFFFFFFFFFFFFE
MIN_OUTPUT_CURSOR = 1
MAX_OUTPUT_CURSOR = 0xFFFFFFFFFFFFFFFE

_HEADER = struct.Struct("!4sBBHQQI16s")


class AWCEError(ValueError):
    """An AWCE envelope is malformed or outside the fixed v1 contract."""


class IncompleteAWCE(AWCEError):
    """The supplied byte string ends before a complete AWCE envelope."""


class TrailingAWCEBytes(AWCEError):
    """A single-envelope decode received bytes after the declared envelope."""


def _require_exact_uint(value: object, *, name: str, maximum: int, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum or value > maximum:
        raise AWCEError(f"{name} is invalid")
    return value


def _require_bytes(value: object, *, name: str, length: int | None = None) -> bytes:
    if type(value) is not bytes or (length is not None and len(value) != length):
        raise AWCEError(f"{name} is invalid")
    return value


def _validate_fields(
    *,
    crypto_envelope_version: object,
    direction_id: object,
    flags: object,
    crypto_sequence: object,
    stream_cursor: object,
    context_id: object,
    ciphertext: object,
) -> None:
    _validate_header_fields(
        crypto_envelope_version=crypto_envelope_version,
        direction_id=direction_id,
        flags=flags,
        crypto_sequence=crypto_sequence,
        stream_cursor=stream_cursor,
        context_id=context_id,
        ciphertext_length=len(_require_bytes(ciphertext, name="AWCE ciphertext")),
    )


def _validate_header_fields(
    *,
    crypto_envelope_version: object,
    direction_id: object,
    flags: object,
    crypto_sequence: object,
    stream_cursor: object,
    context_id: object,
    ciphertext_length: object,
) -> tuple[int, int, int, int, int, int, bytes]:
    if crypto_envelope_version != VERSION or type(crypto_envelope_version) is not int:
        raise AWCEError("unsupported AWCE version")
    direction = _require_exact_uint(direction_id, name="AWCE direction", maximum=0xFF)
    if direction not in (INPUT_DIRECTION, OUTPUT_DIRECTION):
        raise AWCEError("unknown AWCE direction")
    if _require_exact_uint(flags, name="AWCE flags", maximum=0xFFFF) != 0:
        raise AWCEError("AWCE flags are reserved and must be zero")
    _require_exact_uint(
        crypto_sequence,
        name="AWCE crypto_sequence",
        minimum=MIN_TERMINAL_SEQUENCE,
        maximum=MAX_TERMINAL_SEQUENCE,
    )
    cursor = _require_exact_uint(
        stream_cursor,
        name="AWCE stream_cursor",
        maximum=MAX_OUTPUT_CURSOR,
    )
    if (direction == INPUT_DIRECTION and cursor != 0) or (
        direction == OUTPUT_DIRECTION and cursor < MIN_OUTPUT_CURSOR
    ):
        raise AWCEError("AWCE stream_cursor is invalid for its direction")
    _require_bytes(context_id, name="AWCE context_id", length=CONTEXT_ID_SIZE)
    length = _require_exact_uint(
        ciphertext_length,
        name="AWCE ciphertext length",
        maximum=MAX_CIPHERTEXT_SIZE,
    )
    if length < MIN_CIPHERTEXT_SIZE:
        raise AWCEError("AWCE ciphertext length is outside the v1 limit")
    return (
        crypto_envelope_version,
        direction,
        _require_exact_uint(flags, name="AWCE flags", maximum=0xFFFF),
        _require_exact_uint(
            crypto_sequence,
            name="AWCE crypto_sequence",
            minimum=MIN_TERMINAL_SEQUENCE,
            maximum=MAX_TERMINAL_SEQUENCE,
        ),
        cursor,
        length,
        _require_bytes(context_id, name="AWCE context_id", length=CONTEXT_ID_SIZE),
    )


@dataclass(frozen=True, slots=True, repr=False)
class AWCEEnvelope:
    """A validated immutable AWCE v1 envelope with opaque payload fields."""

    crypto_envelope_version: int
    direction_id: int
    flags: int
    crypto_sequence: int
    stream_cursor: int
    context_id: bytes = field(repr=False)
    ciphertext: bytes = field(repr=False)

    def __post_init__(self) -> None:
        _validate_fields(
            crypto_envelope_version=self.crypto_envelope_version,
            direction_id=self.direction_id,
            flags=self.flags,
            crypto_sequence=self.crypto_sequence,
            stream_cursor=self.stream_cursor,
            context_id=self.context_id,
            ciphertext=self.ciphertext,
        )

    @property
    def ciphertext_length(self) -> int:
        """The encoded ciphertext length, including the GCM tag."""

        return len(self.ciphertext)

    def __repr__(self) -> str:
        return (
            "AWCEEnvelope("
            f"crypto_envelope_version={self.crypto_envelope_version}, "
            f"direction_id={self.direction_id}, flags={self.flags}, "
            f"crypto_sequence={self.crypto_sequence}, stream_cursor={self.stream_cursor}, "
            f"ciphertext_length={self.ciphertext_length}, "
            "context_id=<redacted>)"
        )


def encode_awce(envelope: object) -> bytes:
    """Encode one exact AWCE v1 envelope without touching its opaque bytes."""

    if type(envelope) is not AWCEEnvelope:
        raise AWCEError("AWCE envelope must be an exact typed record")
    return (
        encode_awce_header(
            crypto_envelope_version=envelope.crypto_envelope_version,
            direction_id=envelope.direction_id,
            flags=envelope.flags,
            crypto_sequence=envelope.crypto_sequence,
            stream_cursor=envelope.stream_cursor,
            context_id=envelope.context_id,
            ciphertext_length=envelope.ciphertext_length,
        )
        + envelope.ciphertext
    )


def encode_awce_header(
    *,
    crypto_envelope_version: object,
    direction_id: object,
    flags: object,
    crypto_sequence: object,
    stream_cursor: object,
    context_id: object,
    ciphertext_length: object,
) -> bytes:
    """Encode the exact 44-byte AWCE header before opaque ciphertext exists.

    ``ciphertext_length`` includes the 16-byte authentication tag.  This
    function only constructs framing bytes; it does not create an authenticated
    envelope or establish any cryptographic context.
    """

    validated = _validate_header_fields(
        crypto_envelope_version=crypto_envelope_version,
        direction_id=direction_id,
        flags=flags,
        crypto_sequence=crypto_sequence,
        stream_cursor=stream_cursor,
        context_id=context_id,
        ciphertext_length=ciphertext_length,
    )
    return _HEADER.pack(
        MAGIC,
        *validated,
    )


def decode_awce(data: object) -> AWCEEnvelope:
    """Decode exactly one AWCE v1 envelope and reject truncation or trailing bytes."""

    if type(data) is not bytes:
        raise TypeError("AWCE envelope must be bytes")
    if len(data) < HEADER_SIZE:
        raise IncompleteAWCE("AWCE header is incomplete")
    if len(data) > MAX_ENVELOPE_SIZE:
        raise AWCEError("AWCE envelope exceeds the v1 limit")
    (
        magic,
        crypto_envelope_version,
        direction_id,
        flags,
        crypto_sequence,
        stream_cursor,
        ciphertext_length,
        context_id,
    ) = _HEADER.unpack(data[:HEADER_SIZE])
    if magic != MAGIC:
        raise AWCEError("invalid AWCE magic")
    if ciphertext_length < MIN_CIPHERTEXT_SIZE or ciphertext_length > MAX_CIPHERTEXT_SIZE:
        raise AWCEError("AWCE ciphertext length is outside the v1 limit")
    expected_length = HEADER_SIZE + ciphertext_length
    if len(data) < expected_length:
        raise IncompleteAWCE("AWCE ciphertext is incomplete")
    if len(data) > expected_length:
        raise TrailingAWCEBytes("AWCE single-envelope decode has trailing bytes")
    return AWCEEnvelope(
        crypto_envelope_version=crypto_envelope_version,
        direction_id=direction_id,
        flags=flags,
        crypto_sequence=crypto_sequence,
        stream_cursor=stream_cursor,
        context_id=context_id,
        ciphertext=data[HEADER_SIZE:],
    )


__all__ = [
    "AUTH_TAG_SIZE",
    "AWCEEnvelope",
    "AWCEError",
    "CONTEXT_ID_SIZE",
    "HEADER_SIZE",
    "INPUT_DIRECTION",
    "IncompleteAWCE",
    "MAGIC",
    "MAX_CIPHERTEXT_SIZE",
    "MAX_ENVELOPE_SIZE",
    "MAX_OUTPUT_CURSOR",
    "MAX_PLAINTEXT_SIZE",
    "MAX_TERMINAL_SEQUENCE",
    "MIN_CIPHERTEXT_SIZE",
    "MIN_ENVELOPE_SIZE",
    "MIN_OUTPUT_CURSOR",
    "MIN_PLAINTEXT_SIZE",
    "MIN_TERMINAL_SEQUENCE",
    "OUTPUT_DIRECTION",
    "TrailingAWCEBytes",
    "VERSION",
    "decode_awce",
    "encode_awce",
    "encode_awce_header",
]
