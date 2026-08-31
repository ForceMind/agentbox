"""Bounded, metadata-only RFC6455 frame parser for future WAW transport.

The parser consumes exactly one complete frame and returns only header/control
metadata. It never returns or persists terminal payload bytes and never exposes
masking keys. It does not implement Origin/CSRF/authentication, Noise, ABWS, terminal
content, sockets, WebSockets, PTYs, or cryptography. It is not a production
transport implementation.
"""

from __future__ import annotations

from typing import Final, NoReturn

from agentbox_protocol.waw_websocket_contract import (
    WAWWebSocketContractError,
    WAWWebSocketDirection,
    WAWWebSocketFrame,
    WAWWebSocketOpcode,
    WAWWebSocketPolicy,
)

MAX_FRAME_INPUT: Final = 65536 + 14
_ALLOWED_CLOSE_CODES = frozenset(range(1000, 1004)) | frozenset(range(1007, 1015))


class WAWWebSocketParseError(WAWWebSocketContractError):
    """A frame is truncated, non-canonical, unsafe, or has trailing bytes."""


def _reject(code: str, message: str) -> NoReturn:
    raise WAWWebSocketParseError(code, message)


def _need(raw: bytes, end: int) -> None:
    if len(raw) < end:
        _reject("FRAME_TRUNCATED", "frame header, mask, or payload is truncated")


def _validate_policy(policy: WAWWebSocketPolicy) -> None:
    if type(policy) is not WAWWebSocketPolicy:
        _reject("PROTOCOL_INVALID", "policy must be an exact typed record")
    try:
        WAWWebSocketPolicy.__post_init__(policy)
    except (TypeError, ValueError) as exc:
        raise WAWWebSocketParseError("PROTOCOL_INVALID", "policy budget is invalid") from exc


def _unmask(payload: bytes, key: bytes) -> bytes:
    return bytes(value ^ key[index % 4] for index, value in enumerate(payload))


def parse_websocket_frame(
    raw: bytes | bytearray | memoryview,
    direction: WAWWebSocketDirection,
    *,
    policy: WAWWebSocketPolicy | None = None,
) -> WAWWebSocketFrame:
    """Parse one bounded frame without exposing or persisting payload bytes."""

    if not isinstance(raw, (bytes, bytearray, memoryview)):
        _reject("PROTOCOL_INVALID", "frame input must be bytes")
    if type(direction) is not WAWWebSocketDirection:
        _reject("PROTOCOL_INVALID", "direction is invalid")
    policy = WAWWebSocketPolicy() if policy is None else policy
    _validate_policy(policy)
    raw = bytes(raw)
    if not raw or len(raw) > MAX_FRAME_INPUT:
        _reject("FRAME_TOO_LARGE", "frame input exceeds bounded parser input")
    _need(raw, 2)
    first, second = raw[0], raw[1]
    fin = bool(first & 0x80)
    rsv1 = bool(first & 0x40)
    rsv2 = bool(first & 0x20)
    rsv3 = bool(first & 0x10)
    try:
        opcode = {
            0: WAWWebSocketOpcode.CONTINUATION,
            1: WAWWebSocketOpcode.TEXT,
            2: WAWWebSocketOpcode.BINARY,
            8: WAWWebSocketOpcode.CLOSE,
            9: WAWWebSocketOpcode.PING,
            10: WAWWebSocketOpcode.PONG,
        }[first & 0x0F]
    except KeyError:
        _reject("OPCODE_FORBIDDEN", "opcode is reserved or unknown")
    if opcode is WAWWebSocketOpcode.TEXT:
        _reject("TEXT_FORBIDDEN", "WAW accepts binary data only")
    if rsv1 or rsv2 or rsv3:
        _reject("EXTENSION_FORBIDDEN", "reserved bits are not enabled")

    masked = bool(second & 0x80)
    length_code = second & 0x7F
    offset = 2
    if length_code <= 125:
        payload_length = length_code
    elif length_code == 126:
        _need(raw, offset + 2)
        payload_length = int.from_bytes(raw[offset : offset + 2], "big")
        if payload_length < 126:
            _reject("LENGTH_NON_CANONICAL", "16-bit length uses a non-minimal encoding")
        offset += 2
    else:
        _need(raw, offset + 8)
        extended = raw[offset : offset + 8]
        if extended[0] & 0x80:
            _reject("LENGTH_OVERFLOW", "64-bit length has its reserved high bit set")
        payload_length = int.from_bytes(extended, "big")
        if payload_length < 65536:
            _reject("LENGTH_NON_CANONICAL", "64-bit length uses a non-minimal encoding")
        offset += 8
    if payload_length > policy.max_frame_payload:
        _reject("FRAME_TOO_LARGE", "frame payload exceeds the fixed policy")
    expected_mask = direction is WAWWebSocketDirection.CLIENT_TO_RUNTIME
    if masked is not expected_mask:
        _reject("MASKING_INVALID", "frame masking does not match its fixed direction")
    if opcode in {
        WAWWebSocketOpcode.CLOSE,
        WAWWebSocketOpcode.PING,
        WAWWebSocketOpcode.PONG,
    } and (not fin or payload_length > 125):
        _reject("CONTROL_FRAME_INVALID", "control frames must be final and at most 125 bytes")

    mask_key = raw[offset : offset + 4] if masked else b""
    payload_offset = offset + (4 if masked else 0)
    _need(raw, payload_offset + payload_length)
    if len(raw) != payload_offset + payload_length:
        _reject("TRAILING_BYTES", "concatenated or trailing frame bytes are forbidden")

    close_code: int | None = None
    close_reason_bytes = 0
    close_reason_utf8_valid = True
    if opcode is WAWWebSocketOpcode.CLOSE and payload_length:
        payload = raw[payload_offset : payload_offset + payload_length]
        if masked:
            payload = _unmask(payload, mask_key)
        if payload_length == 1:
            _reject("CLOSE_PAYLOAD_INVALID", "close payload cannot contain one byte")
        close_code = int.from_bytes(payload[:2], "big")
        if close_code not in _ALLOWED_CLOSE_CODES and not 3000 <= close_code <= 4999:
            _reject("CLOSE_CODE_INVALID", "close code is reserved or outside the allowed range")
        close_reason_bytes = payload_length - 2
        if close_reason_bytes > policy.max_close_reason_bytes:
            _reject("CLOSE_REASON_INVALID", "close reason exceeds the fixed limit")
        try:
            payload[2:].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WAWWebSocketParseError(
                "CLOSE_REASON_INVALID", "close reason UTF-8 is invalid"
            ) from exc

    return WAWWebSocketFrame(
        direction=direction,
        opcode=opcode,
        fin=fin,
        masked=masked,
        rsv1=rsv1,
        rsv2=rsv2,
        rsv3=rsv3,
        payload_length=payload_length,
        close_code=close_code,
        close_reason_bytes=close_reason_bytes,
        close_reason_utf8_valid=close_reason_utf8_valid,
    )


__all__ = ["MAX_FRAME_INPUT", "WAWWebSocketParseError", "parse_websocket_frame"]
