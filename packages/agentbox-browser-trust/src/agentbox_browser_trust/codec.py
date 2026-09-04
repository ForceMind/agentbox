"""Closed canonical JSON and bounded length-prefix codecs for browser trust."""

from __future__ import annotations

import base64
import json
import struct
from collections.abc import Iterable
from typing import Any, NoReturn, Protocol, cast

import rfc8785

NATIVE_MESSAGE_MAX = 1024 * 1024
TRUSTD_MESSAGE_MAX = 512 * 1024
TRUST_RECORD_MAX = 4096


class TrustCodecError(ValueError):
    """A public provider message is malformed or outside its fixed bound."""


class BinaryStream(Protocol):
    def read(self, size: int = -1, /) -> bytes: ...

    def write(self, value: bytes, /) -> int | None: ...

    def flush(self) -> None: ...


def _fail() -> NoReturn:
    raise TrustCodecError("browser trust message is invalid")


def canonical_json(value: object, *, limit: int = TRUSTD_MESSAGE_MAX) -> bytes:
    try:
        encoded = rfc8785.dumps(cast(Any, value))
    except (rfc8785.CanonicalizationError, TypeError, ValueError):
        _fail()
    if not encoded or len(encoded) > limit:
        _fail()
    return encoded


def strict_json(raw: bytes, *, limit: int = TRUSTD_MESSAGE_MAX) -> object:
    if type(raw) is not bytes or not raw or len(raw) > limit:
        _fail()

    def pairs(values: Iterable[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if type(key) is not str or key in result:
                _fail()
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, TrustCodecError):
        _fail()
    if canonical_json(value, limit=limit) != raw:
        _fail()
    return value


def exact_object(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict or frozenset(value) != keys:
        _fail()
    return value


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(value: object, *, size: int | None = None, limit: int) -> bytes:
    if type(value) is not str or not value or "=" in value:
        _fail()
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, UnicodeEncodeError):
        _fail()
    if len(raw) > limit or (size is not None and len(raw) != size) or b64url_encode(raw) != value:
        _fail()
    return raw


def read_frame(stream: BinaryStream, *, limit: int, little_endian: bool) -> bytes:
    prefix = _read_exact(stream, 4)
    length = struct.unpack("<I" if little_endian else ">I", prefix)[0]
    if length < 1 or length > limit:
        _fail()
    return _read_exact(stream, length)


def write_frame(stream: BinaryStream, payload: bytes, *, limit: int, little_endian: bool) -> None:
    if type(payload) is not bytes or not payload or len(payload) > limit:
        _fail()
    _write_all(stream, struct.pack("<I" if little_endian else ">I", len(payload)))
    _write_all(stream, payload)
    stream.flush()


def _read_exact(stream: BinaryStream, length: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < length:
        value = stream.read(length - len(chunks))
        if type(value) is not bytes or not value:
            _fail()
        chunks.extend(value)
    return bytes(chunks)


def _write_all(stream: BinaryStream, value: bytes) -> None:
    offset = 0
    while offset < len(value):
        written = stream.write(value[offset:])
        if type(written) is not int or written < 1:
            _fail()
        offset += written


def read_native_message(stream: BinaryStream) -> object:
    return strict_json(read_frame(stream, limit=NATIVE_MESSAGE_MAX, little_endian=True))


def write_native_message(stream: BinaryStream, value: object) -> None:
    write_frame(
        stream,
        canonical_json(value, limit=NATIVE_MESSAGE_MAX),
        limit=NATIVE_MESSAGE_MAX,
        little_endian=True,
    )
