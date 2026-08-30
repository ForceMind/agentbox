"""Strict, bounded ABWS v1 binary frame codec.

This module deliberately implements only the outer ABWS framing contract.  It
does not implement Noise, WebSocket admission, or terminal payload decryption.
The latter payloads are opaque bytes to the API and Runtime stream adapters.
"""

from __future__ import annotations

import json
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

MAGIC = b"ABWS"
VERSION = 1
HEADER_SIZE = 24
MAX_PAYLOAD = 65_512
MAX_WAW_PAYLOAD = 49_212
MAX_JSON_PAYLOAD = 4_096
MAX_JSON_DEPTH = 16
MAX_JSON_KEYS = 64
MAX_FRAME = HEADER_SIZE + MAX_PAYLOAD
MAX_WAW_FRAME = HEADER_SIZE + MAX_WAW_PAYLOAD
_HEADER = struct.Struct("!4sBBHIQI")


class FrameType(IntEnum):
    WS_HELLO = 1
    RUNTIME_HELLO = 2
    KEY_INIT = 3
    KEY_ATTEST = 4
    KEY_CONFIRM = 5
    KEY_CONFIRM_ACK = 6
    HELLO_ACK = 7
    ADMITTED = 8
    INPUT = 9
    OUTPUT = 10
    RESIZE = 11
    HEARTBEAT = 12
    PING = 13
    PONG = 14
    DETACH = 15
    EXIT = 16
    GAP = 17
    ACK = 18
    ERROR = 19
    CLOSE = 20
    STATE = 21
    STREAM_READY = 22
    STREAM_READY_ACK = 23
    ADMISSION_COMMIT = 24
    ADMISSION_COMMIT_ACK = 25
    RESIZE_ACK = 26
    DETACH_ACK = 27


OPAQUE_TYPES = frozenset({FrameType.INPUT, FrameType.OUTPUT})
JSON_TYPES = frozenset(FrameType) - OPAQUE_TYPES


class ABWSError(ValueError):
    """Base error for malformed or out-of-contract ABWS frames."""


class IncompleteFrame(ABWSError):
    """The supplied byte string ends before a complete frame is available."""


class TrailingBytes(ABWSError):
    """A single-frame decode received bytes after the declared frame."""


def _reject_constant(value: str) -> None:
    raise ABWSError(f"JSON constant is not permitted: {value}")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ABWSError("duplicate JSON object key")
        result[key] = value
    return result


def _validate_json_value(value: Any, *, depth: int = 0, key_count: int = 0) -> int:
    if depth > MAX_JSON_DEPTH:
        raise ABWSError("JSON nesting exceeds ABWS control limit")
    if isinstance(value, str):
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ABWSError("unpaired UTF-16 surrogate is not permitted")
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ABWSError("JSON object keys must be strings")
            key_count += 1
            if key_count > MAX_JSON_KEYS:
                raise ABWSError("JSON object key count exceeds ABWS control limit")
            _validate_json_value(key, depth=depth + 1, key_count=key_count)
            key_count = _validate_json_value(item, depth=depth + 1, key_count=key_count)
    elif isinstance(value, list):
        for item in value:
            key_count = _validate_json_value(item, depth=depth + 1, key_count=key_count)
    return key_count


def _decode_json(payload: bytes) -> dict[str, Any]:
    if len(payload) > MAX_JSON_PAYLOAD:
        raise ABWSError("JSON payload exceeds ABWS control limit")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ABWSError("JSON payload is not valid UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, TypeError, RecursionError) as exc:
        raise ABWSError("JSON payload is malformed") from exc
    if not isinstance(value, dict):
        raise ABWSError("ABWS control payload must be a JSON object")
    _validate_json_value(value)
    if type(value.get("protocol_version")) is not int or value["protocol_version"] != 1:
        raise ABWSError("ABWS control payload requires protocol_version=1")
    return value


def _encode_json(payload: dict[str, Any]) -> bytes:
    if not isinstance(payload, dict):
        raise TypeError("ABWS control payload must be a dictionary")
    if type(payload.get("protocol_version")) is not int or payload["protocol_version"] != 1:
        raise ABWSError("ABWS control payload requires protocol_version=1")
    _validate_json_value(payload)
    try:
        data = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, UnicodeEncodeError, ValueError) as exc:
        raise ABWSError("ABWS control payload is not strict JSON") from exc
    if len(data) > MAX_JSON_PAYLOAD:
        raise ABWSError("JSON payload exceeds ABWS control limit")
    return data


@dataclass(frozen=True)
class ABWSFrame:
    """One decoded ABWS frame and its validated outer payload."""

    frame_type: FrameType
    hop_sequence: int
    payload: bytes
    json_payload: dict[str, Any] | None = None

    @property
    def type(self) -> FrameType:
        """Compatibility alias for callers that use ``type`` terminology."""

        return self.frame_type


def _coerce_type(frame_type: FrameType | int) -> FrameType:
    if isinstance(frame_type, bool):
        raise ABWSError("unknown ABWS frame type")
    try:
        return frame_type if isinstance(frame_type, FrameType) else FrameType(frame_type)
    except (TypeError, ValueError) as exc:
        raise ABWSError("unknown ABWS frame type") from exc


def _validate_header(*, version: int, flags: int, reserved: int, payload_length: int) -> None:
    if version != VERSION:
        raise ABWSError("unsupported ABWS version")
    if flags != 0:
        raise ABWSError("ABWS flags are reserved and must be zero")
    if reserved != 0:
        raise ABWSError("ABWS reserved field must be zero")
    if payload_length > MAX_PAYLOAD:
        raise ABWSError("ABWS payload exceeds parser limit")


def encode_frame(
    frame_type: FrameType | int,
    payload: bytes | bytearray | memoryview | dict[str, Any],
    hop_sequence: int,
) -> bytes:
    """Encode one strict ABWS frame.

    ``INPUT`` and ``OUTPUT`` payloads remain opaque bytes.  All other frame
    types require a strict JSON object carrying ``protocol_version=1``.
    """

    kind = _coerce_type(frame_type)
    if not isinstance(hop_sequence, int) or isinstance(hop_sequence, bool):
        raise ABWSError("hop_sequence must be an integer")
    if hop_sequence < 1 or hop_sequence > 0xFFFFFFFFFFFFFFFF:
        raise ABWSError("hop_sequence must be a non-zero uint64")
    if kind in JSON_TYPES:
        if not isinstance(payload, dict):
            raise ABWSError("ABWS control payload must be a dictionary")
        encoded_payload = _encode_json(payload)
    else:
        if isinstance(payload, (str, dict)):
            raise TypeError("opaque ABWS payload must be bytes")
        try:
            encoded_payload = bytes(payload)
        except (TypeError, ValueError) as exc:
            raise TypeError("opaque ABWS payload must be bytes") from exc
        if len(encoded_payload) > MAX_WAW_PAYLOAD:
            raise ABWSError("WAW opaque payload exceeds 49,212-byte limit")
    if len(encoded_payload) > MAX_PAYLOAD:
        raise ABWSError("ABWS payload exceeds parser limit")
    return (
        _HEADER.pack(MAGIC, VERSION, int(kind), 0, len(encoded_payload), hop_sequence, 0)
        + encoded_payload
    )


def decode_frame(
    data: bytes | bytearray | memoryview, *, expected_sequence: int | None = None
) -> ABWSFrame:
    """Decode exactly one complete ABWS frame, rejecting all trailing bytes."""

    try:
        raw = bytes(data)
    except (TypeError, ValueError) as exc:
        raise TypeError("ABWS frame must be bytes") from exc
    if len(raw) < HEADER_SIZE:
        raise IncompleteFrame("ABWS header is incomplete")
    magic, version, raw_type, flags, payload_length, hop_sequence, reserved = _HEADER.unpack(
        raw[:HEADER_SIZE]
    )
    if magic != MAGIC:
        raise ABWSError("invalid ABWS magic")
    _validate_header(
        version=version,
        flags=flags,
        reserved=reserved,
        payload_length=payload_length,
    )
    kind = _coerce_type(raw_type)
    expected_length = HEADER_SIZE + payload_length
    if len(raw) < expected_length:
        raise IncompleteFrame("ABWS payload is incomplete")
    if len(raw) > expected_length:
        raise TrailingBytes("ABWS single-frame decode has trailing bytes")
    if hop_sequence < 1:
        raise ABWSError("hop_sequence must be a non-zero uint64")
    if expected_sequence is not None:
        if expected_sequence < 1 or expected_sequence > 0xFFFFFFFFFFFFFFFF:
            raise ABWSError("expected_sequence must be a non-zero uint64")
        if hop_sequence != expected_sequence:
            raise ABWSError("ABWS hop sequence is not contiguous")
    payload = raw[HEADER_SIZE:]
    json_payload = _decode_json(payload) if kind in JSON_TYPES else None
    return ABWSFrame(kind, hop_sequence, payload, json_payload)


def iter_frames(data: bytes | bytearray | memoryview) -> Iterator[ABWSFrame]:
    """Decode a byte-stream containing zero or more complete ABWS frames."""

    try:
        raw = bytes(data)
    except (TypeError, ValueError) as exc:
        raise TypeError("ABWS stream must be bytes") from exc
    offset = 0
    while offset < len(raw):
        remaining = raw[offset:]
        if len(remaining) < HEADER_SIZE:
            raise IncompleteFrame("ABWS stream ends with a partial header")
        payload_length = _HEADER.unpack(remaining[:HEADER_SIZE])[4]
        frame_length = HEADER_SIZE + payload_length
        if len(remaining) < frame_length:
            raise IncompleteFrame("ABWS stream ends with a partial frame")
        yield decode_frame(remaining[:frame_length])
        offset += frame_length


class ABWSParser:
    """Incremental bounded parser for one ordered ABWS leg."""

    def __init__(self, *, first_sequence: int = 1) -> None:
        if first_sequence < 1 or first_sequence > 0xFFFFFFFFFFFFFFFF:
            raise ABWSError("first_sequence must be a non-zero uint64")
        self._buffer = bytearray()
        self._expected_sequence = first_sequence
        self._exhausted = False

    @property
    def expected_sequence(self) -> int:
        return self._expected_sequence

    def feed(self, data: bytes | bytearray | memoryview) -> tuple[ABWSFrame, ...]:
        if self._exhausted and data:
            raise ABWSError("ABWS hop sequence exhausted")
        try:
            chunk = bytes(data)
        except (TypeError, ValueError) as exc:
            raise TypeError("ABWS stream chunk must be bytes") from exc
        frames: list[ABWSFrame] = []
        offset = 0
        while offset < len(chunk) or self._buffer:
            # A partial frame is bounded to the maximum full-frame size.  Feed
            # large byte-stream chunks in bounded pieces so an attacker cannot
            # force an unbounded parser buffer before framing is validated.
            if offset < len(chunk):
                capacity = MAX_FRAME - len(self._buffer)
                if capacity <= 0:
                    raise ABWSError("ABWS partial-frame buffer exceeds limit")
                take = min(capacity, len(chunk) - offset)
                self._buffer.extend(chunk[offset : offset + take])
                offset += take
            progressed = False
            while len(self._buffer) >= HEADER_SIZE:
                payload_length = _HEADER.unpack(self._buffer[:HEADER_SIZE])[4]
                if payload_length > MAX_PAYLOAD:
                    raise ABWSError("ABWS payload exceeds parser limit")
                frame_length = HEADER_SIZE + payload_length
                if len(self._buffer) < frame_length:
                    break
                frame = decode_frame(
                    self._buffer[:frame_length], expected_sequence=self._expected_sequence
                )
                del self._buffer[:frame_length]
                frames.append(frame)
                progressed = True
                if self._expected_sequence == 0xFFFFFFFFFFFFFFFF:
                    self._exhausted = True
                    if self._buffer or offset < len(chunk):
                        raise ABWSError("ABWS hop sequence exhausted")
                else:
                    self._expected_sequence += 1
            if offset >= len(chunk):
                break
            if len(self._buffer) == MAX_FRAME and not progressed:
                raise ABWSError("ABWS partial-frame buffer exceeds limit")
        return tuple(frames)

    def finish(self) -> None:
        if self._buffer:
            raise IncompleteFrame("ABWS stream ended before a complete frame")


# Names used by callers that prefer explicit codec terminology.
ABWSFrameType = FrameType
ABWSProtocolError = ABWSError
decode = decode_frame
encode = encode_frame


__all__ = [
    "ABWSFrame",
    "ABWSFrameType",
    "ABWSParser",
    "ABWSError",
    "ABWSProtocolError",
    "FrameType",
    "HEADER_SIZE",
    "MAGIC",
    "MAX_FRAME",
    "MAX_JSON_PAYLOAD",
    "MAX_JSON_DEPTH",
    "MAX_JSON_KEYS",
    "MAX_PAYLOAD",
    "MAX_WAW_FRAME",
    "MAX_WAW_PAYLOAD",
    "OPAQUE_TYPES",
    "JSON_TYPES",
    "IncompleteFrame",
    "TrailingBytes",
    "decode",
    "decode_frame",
    "encode",
    "encode_frame",
    "iter_frames",
]
