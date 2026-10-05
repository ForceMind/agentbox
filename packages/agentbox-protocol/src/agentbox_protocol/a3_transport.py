"""Exact A3-only native frames and copied admission facts; no I/O or authority."""

from __future__ import annotations

import hashlib
import json
import re
import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, cast

from agentbox_protocol.a3_admission import A3CurrentAdmission
from agentbox_protocol.a3_content import ERROR_CODES, ContentError
from agentbox_protocol.waw_control import WAWControlError, validate_relative_key

MAX_CONTROL_BYTES = 8192
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_RECORD_BYTES = 24 * 1024
HEADER_BYTES = 13
_HEADER = struct.Struct(">4sBII")
_HEX32 = re.compile(r"[0-9a-f]{32}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_U64 = re.compile(r"[1-9][0-9]{0,19}\Z")
_SELECTOR = re.compile(r"[A-Za-z0-9_-]{156}\Z")
_FACT_KEYS = frozenset(A3CurrentAdmission.__dataclass_fields__)
_ENTRY_KEYS = frozenset({"path", "kind", "side", "selection_id", "unavailable_code"})
_METADATA_CODES = frozenset(
    {
        "PATCH_STALE",
        "PATCH_UNAVAILABLE_KIND",
        "PATCH_UNAVAILABLE_MODE",
        "PATCH_UNAVAILABLE_PATH",
        "PATCH_UNAVAILABLE_SENSITIVE_PATH",
        "PATCH_UNAVAILABLE_STATUS",
    }
)
_ENTRY_KINDS = frozenset(
    {
        "added",
        "modified",
        "deleted",
        "renamed",
        "copied",
        "typechanged",
        "conflicted",
    }
)


class NativeKind(IntEnum):
    HELLO = 1
    HELLO_ACK = 2
    OBSERVE = 3
    METADATA = 4
    OPEN = 5
    OWNED = 6
    PUBLISH_CHECK = 7
    CHECKED = 8
    PUBLISHED = 9
    ACK = 10
    CURRENT = 11
    CURRENT_REPLY = 12
    RECORD = 13
    ERROR = 14
    COMPLETE = 15
    CLOSE = 16
    LIVE = 17
    LIVE_REPLY = 18
    READY = 19


@dataclass(frozen=True, slots=True)
class NativeFrame:
    kind: NativeKind
    sequence: int
    payload: dict[str, object] | bytes = field(repr=False)


def _invalid() -> ContentError:
    return ContentError()


def _object(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict or value.keys() != keys:
        raise _invalid()
    return cast(dict[str, object], value)


def _string(value: object, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise _invalid()
    return value


def _u64(value: object) -> str:
    text = _string(value, _U64)
    if int(text) > 2**64 - 1:
        raise _invalid()
    return text


def _u32(value: object, *, zero: bool = False) -> int:
    if type(value) is not int or not (0 if zero else 1) <= value <= 2**32 - 1:
        raise _invalid()
    return value


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False
        ).encode("ascii")
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise _invalid() from None


def facts_from_wire(value: object) -> A3CurrentAdmission:
    facts = _object(value, _FACT_KEYS)
    project = _string(facts["project_id"], re.compile(r"prj_[0-9a-f]{32}\Z"))
    host = _string(facts["runtime_host_installation_id"], re.compile(r"wri_[0-9a-f]{32}\Z"))
    try:
        relative_key = validate_relative_key(facts["relative_key"])
    except (WAWControlError, ValueError, TypeError):
        raise _invalid() from None
    return A3CurrentAdmission(
        project_id=project,
        relative_key=relative_key,
        project_revision=_u64(facts["project_revision"]),
        binding_revision=_u64(facts["binding_revision"]),
        binding_digest=_string(facts["binding_digest"], _HEX64),
        runtime_host_installation_id=host,
        runtime_host_installation_revision=_u64(facts["runtime_host_installation_revision"]),
        runtime_epoch=_u64(facts["runtime_epoch"]),
        session_scope=bytes.fromhex(_string(facts["session_scope"], _HEX64)),
        auth_epoch=int(_u64(facts["auth_epoch"])),
    )


def facts_to_wire(facts: A3CurrentAdmission) -> dict[str, object]:
    if (
        type(facts) is not A3CurrentAdmission
        or type(facts.session_scope) is not bytes
        or type(facts.auth_epoch) is not int
    ):
        raise _invalid()
    result = {name: getattr(facts, name) for name in _FACT_KEYS}
    result["session_scope"] = facts.session_scope.hex()
    result["auth_epoch"] = str(facts.auth_epoch)
    facts_from_wire(result)
    return result


def facts_digest(facts: A3CurrentAdmission) -> str:
    return hashlib.sha256(_canonical(facts_to_wire(facts))).hexdigest()


def _metadata(value: object) -> dict[str, object]:
    data = _object(value, frozenset({"snapshot_sha256", "entries"}))
    _string(data["snapshot_sha256"], _HEX64)
    entries = data["entries"]
    if type(entries) is not list or len(entries) > 10000:
        raise _invalid()
    paths: set[str] = set()
    encoded_size = len(_canonical({"snapshot_sha256": data["snapshot_sha256"], "entries": []}))
    for value in entries:
        entry = _object(value, _ENTRY_KEYS)
        path, kind = entry["path"], entry["kind"]
        if (
            type(path) is not str
            or not 1 <= len(path) <= 4096
            or path in paths
            or any(0xD800 <= ord(char) <= 0xDFFF for char in path)
            or type(kind) is not str
            or kind not in _ENTRY_KINDS
            or entry["side"] != "staged"
        ):
            raise _invalid()
        paths.add(path)
        selector, code = entry["selection_id"], entry["unavailable_code"]
        if selector is not None:
            _string(selector, _SELECTOR)
            if kind not in {"added", "modified", "deleted"} or code is not None:
                raise _invalid()
        elif type(code) is not str or code not in _METADATA_CODES:
            raise _invalid()
        encoded_size += len(_canonical(entry)) + (1 if len(paths) > 1 else 0)
        if encoded_size > MAX_METADATA_BYTES:
            raise _invalid()
    return data


def validate_payload(kind: NativeKind, payload: object) -> dict[str, object] | bytes:
    if type(kind) is not NativeKind:
        raise _invalid()
    if kind is NativeKind.RECORD:
        if type(payload) is not bytes or not 1 <= len(payload) <= MAX_RECORD_BYTES:
            raise _invalid()
        return payload
    if kind in {NativeKind.HELLO, NativeKind.HELLO_ACK}:
        data = _object(payload, frozenset({"bundle_id", "role", "facts_digest"}))
        _string(data["bundle_id"], _HEX32)
        _string(data["facts_digest"], _HEX64)
        if type(data["role"]) is not str or data["role"] not in {
            "command",
            "opaque",
            "currentness",
        }:
            raise _invalid()
    elif kind is NativeKind.OBSERVE:
        data = _object(payload, frozenset({"facts"}))
        facts_from_wire(data["facts"])
    elif kind is NativeKind.OPEN:
        data = _object(payload, frozenset({"facts", "selection_id", "request_nonce"}))
        facts_from_wire(data["facts"])
        _string(data["selection_id"], _SELECTOR)
        _string(data["request_nonce"], _HEX64)
    elif kind is NativeKind.METADATA:
        data = _metadata(payload)
    elif kind in {
        NativeKind.PUBLISH_CHECK,
        NativeKind.CHECKED,
        NativeKind.PUBLISHED,
        NativeKind.ACK,
    }:
        data = _object(payload, frozenset({"record_sequence", "record_sha256"}))
        _u32(data["record_sequence"])
        _string(data["record_sha256"], _HEX64)
    elif kind in {NativeKind.CURRENT, NativeKind.CURRENT_REPLY}:
        keys = {"facts_digest", "challenge"}
        if kind is NativeKind.CURRENT_REPLY:
            keys.add("current")
        data = _object(payload, frozenset(keys))
        _string(data["facts_digest"], _HEX64)
        _string(data["challenge"], _HEX32)
        if kind is NativeKind.CURRENT_REPLY and type(data["current"]) is not bool:
            raise _invalid()
    elif kind in {NativeKind.LIVE, NativeKind.LIVE_REPLY}:
        data = _object(payload, frozenset({"observation_sequence", "challenge"}))
        _u32(data["observation_sequence"], zero=True)
        _string(data["challenge"], _HEX32)
    elif kind is NativeKind.ERROR:
        data = _object(payload, frozenset({"code"}))
        if type(data["code"]) is not str or data["code"] not in ERROR_CODES:
            raise _invalid()
    else:
        data = _object(payload, frozenset())
    return data


def payload_limit(kind: NativeKind) -> int:
    if kind is NativeKind.METADATA:
        return MAX_METADATA_BYTES
    if kind is NativeKind.RECORD:
        return MAX_RECORD_BYTES
    return MAX_CONTROL_BYTES


def decode_header(raw: bytes) -> tuple[NativeKind, int, int]:
    if type(raw) is not bytes or len(raw) != HEADER_BYTES:
        raise _invalid()
    magic, number, sequence, length = _HEADER.unpack(raw)
    try:
        kind = NativeKind(number)
    except ValueError:
        raise _invalid() from None
    if magic != b"A3N1" or sequence == 0 or not 1 <= length <= payload_limit(kind):
        raise _invalid()
    return kind, sequence, length


def encode_frame(kind: NativeKind, sequence: int, payload: dict[str, object] | bytes) -> bytes:
    _u32(sequence)
    valid = validate_payload(kind, payload)
    body = valid if type(valid) is bytes else _canonical(valid)
    if not 1 <= len(body) <= payload_limit(kind):
        raise _invalid()
    return _HEADER.pack(b"A3N1", kind.value, sequence, len(body)) + body


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _invalid()
        result[key] = value
    return result


def decode_frame(raw: bytes) -> NativeFrame:
    if type(raw) is not bytes or len(raw) < HEADER_BYTES:
        raise _invalid()
    kind, sequence, length = decode_header(raw[:HEADER_BYTES])
    if len(raw) != HEADER_BYTES + length:
        raise _invalid()
    body = raw[HEADER_BYTES:]
    if kind is NativeKind.RECORD:
        payload: dict[str, object] | bytes = body
    else:
        try:
            loaded = json.loads(body.decode("ascii"), object_pairs_hook=_pairs)
        except (ValueError, UnicodeError, RecursionError):
            raise _invalid() from None
        if _canonical(loaded) != body:
            raise _invalid()
        payload = validate_payload(kind, loaded)
    return NativeFrame(kind, sequence, payload)
