"""Inert A3 staged-content schemas/codecs; no admission, crypto or I/O authority.

Only canonical flat ASCII JSON is admitted. Patch bytes use canonical base64url.
This module must not be wired to a plaintext API or a WAW CipherState.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any, Final, Literal, TypedDict, cast

import rfc8785

from agentbox_protocol.waw_crypto_context import validate_hex32, validate_u64

PROTOCOL_ID: Final = "agentbox-a3-content/v1"
VERSION: Final = 1
MAX_PAGE_BYTES = 16_384  # Entire authenticated plaintext record, including metadata.
MAX_CONTROL_BYTES = 4096
MAX_PAGES = 16
MAX_PATCH_BYTES = 262_144
MAX_LINES = 4096
MAX_READ_MS = 30_000
MAX_TIME = 2**53 - 1
SELECTOR_DOMAIN = b"agentbox-a3-content/selector/v1\0"
AAD_DOMAIN = "agentbox-a3-content/aad/v1"
KINDS = ("PATCH_READ", "PATCH_PAGE", "PATCH_END", "PATCH_ERROR")
ERROR_CODES = frozenset(
    {
        "PATCH_STALE",
        "PATCH_TIMEOUT",
        "PATCH_TOO_LARGE",
        "PATCH_REVOKED",
        "PATCH_UNAVAILABLE_BINARY",
        "PATCH_UNAVAILABLE_BUSY",
        "PATCH_UNAVAILABLE_CONFIG",
        "PATCH_UNAVAILABLE_ENCODING",
        "PATCH_UNAVAILABLE_GIT",
        "PATCH_UNAVAILABLE_KIND",
        "PATCH_UNAVAILABLE_MODE",
        "PATCH_UNAVAILABLE_PATH",
        "PATCH_UNAVAILABLE_REPOSITORY",
        "PATCH_UNAVAILABLE_SENSITIVE_PATH",
        "PATCH_UNAVAILABLE_STATUS",
    }
)


class ContentError(ValueError):
    """Fixed, value-free failure; the read owner must close and discard plaintext."""

    def __init__(self, code: str = "PATCH_PROTOCOL_INVALID") -> None:
        super().__init__(code)


class ContentContext(TypedDict):
    protocol_id: Literal["agentbox-a3-content/v1"]
    protocol_version: Literal[1]
    project_id: str
    project_revision: str
    binding_revision: str
    binding_digest: str
    runtime_host_installation_id: str
    runtime_host_installation_revision: str
    session_scope: str
    runtime_epoch: str
    selector_commitment: str
    side: Literal["staged"]
    request_nonce: str


class Common(TypedDict):
    protocol_id: Literal["agentbox-a3-content/v1"]
    protocol_version: Literal[1]
    context_digest: str
    request_nonce: str


class PatchRead(Common):
    kind: Literal["PATCH_READ"]
    selection_id: str


class Description(Common):
    sequence: int
    total_bytes: int
    patch_digest: str
    observed_at_ms: str
    complete: bool


class PatchPage(Description):
    kind: Literal["PATCH_PAGE"]
    data: str


class PatchEnd(Description):
    kind: Literal["PATCH_END"]


class PatchError(Common):
    kind: Literal["PATCH_ERROR"]
    code: str


Message = PatchRead | PatchPage | PatchEnd | PatchError
_CONTEXT_KEYS = frozenset(ContentContext.__annotations__)
_COMMON_KEYS = frozenset(Common.__annotations__) | {"kind"}
_DESCRIPTION_KEYS = frozenset(Description.__annotations__) | {"kind"}
_MESSAGE_KEYS = {
    "PATCH_READ": _COMMON_KEYS | {"selection_id"},
    "PATCH_PAGE": _DESCRIPTION_KEYS | {"data"},
    "PATCH_END": _DESCRIPTION_KEYS,
    "PATCH_ERROR": _COMMON_KEYS | {"code"},
}
# The entire schema uses this ASCII alphabet; escapes, nested containers, floats,
# negative numbers, whitespace, null and alternate JSON spellings are not wire values.
_ATOM = rb'(?:"[A-Za-z0-9_/:.\-]*"|true|false|0|[1-9][0-9]*)'
_FLAT = re.compile(rb'\{"[a-z_]+":' + _ATOM + rb'(?:,"[a-z_]+":' + _ATOM + rb")*\}\Z")


def _canonical(value: object) -> bytes:
    return rfc8785.dumps(cast(Any, value))


def _record(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict or value.keys() != keys:
        raise ContentError()
    return dict(value)


def _integer(value: object, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ContentError()
    return value


def _hex(value: object) -> str:
    try:
        return validate_hex32(value)
    except ValueError:
        raise ContentError() from None


def _u64(value: object) -> str:
    try:
        return validate_u64(value)
    except ValueError:
        raise ContentError() from None


def _profile(value: dict[str, object]) -> None:
    if type(value["protocol_id"]) is not str or value["protocol_id"] != PROTOCOL_ID:
        raise ContentError()
    _integer(value["protocol_version"], VERSION, VERSION)


def _parse(raw: bytes, limit: int) -> dict[str, object]:
    if type(raw) is not bytes or not 1 <= len(raw) <= limit or _FLAT.fullmatch(raw) is None:
        raise ContentError()
    try:
        value = json.loads(raw)
        if len(value) > 16 or _canonical(value) != raw:
            raise ContentError()
    except (ValueError, OverflowError):
        raise ContentError() from None
    return cast(dict[str, object], value)


def validate_context(value: object) -> ContentContext:
    r = _record(value, _CONTEXT_KEYS)
    _profile(r)
    for key, prefix in (("project_id", "prj"), ("runtime_host_installation_id", "wri")):
        item = r[key]
        if type(item) is not str or re.fullmatch(prefix + r"_[a-f0-9]{32}", item) is None:
            raise ContentError()
    for key in (
        "project_revision",
        "binding_revision",
        "runtime_host_installation_revision",
        "runtime_epoch",
    ):
        _u64(r[key])
    for key in ("binding_digest", "session_scope", "selector_commitment", "request_nonce"):
        _hex(r[key])
    if type(r["side"]) is not str or r["side"] != "staged":
        raise ContentError()
    return cast(ContentContext, r)


def context_bytes(value: object) -> bytes:
    """RFC8785 context, to be the separate future Noise NX prologue unchanged."""
    return _canonical(validate_context(value))


def decode_context(raw: bytes) -> ContentContext:
    return validate_context(_parse(raw, MAX_CONTROL_BYTES))


def context_digest(value: object) -> str:
    return hashlib.sha256(context_bytes(value)).hexdigest()


def selector_commitment(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9_-]{156}", value) is None:
        raise ContentError()
    return hashlib.sha256(SELECTOR_DOMAIN + value.encode("ascii")).hexdigest()


def application_aad(context: object, transcript_hash: str, kind: str, sequence: int) -> bytes:
    """Define AAD bytes only; never create keys or consume/reset Noise nonces."""
    if type(kind) is not str or kind not in KINDS:
        raise ContentError()
    _integer(sequence, 0, MAX_PAGES)
    if kind in ("PATCH_READ", "PATCH_ERROR") and sequence != 0:
        raise ContentError()
    if kind == "PATCH_PAGE" and sequence >= MAX_PAGES:
        raise ContentError()
    if kind == "PATCH_END" and sequence == 0:
        raise ContentError()
    return _canonical(
        {
            "domain": AAD_DOMAIN,
            "context_digest": context_digest(context),
            "transcript_hash": _hex(transcript_hash),
            "kind": kind,
            "sequence": sequence,
            "direction": "browser-to-runtime" if kind == "PATCH_READ" else "runtime-to-browser",
        }
    )


def _payload(value: object) -> bytes:
    if (
        type(value) is not str
        or not 1 <= len(value) <= MAX_PAGE_BYTES
        or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None
    ):
        raise ContentError()
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except ValueError:
        raise ContentError() from None
    if _b64(raw) != value:
        raise ContentError()
    return raw


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def validate_message(value: object) -> Message:
    if type(value) is not dict or type(value.get("kind")) is not str or value["kind"] not in KINDS:
        raise ContentError()
    r = _record(value, _MESSAGE_KEYS[value["kind"]])
    _profile(r)
    _hex(r["context_digest"])
    _hex(r["request_nonce"])
    kind = r["kind"]
    if kind == "PATCH_READ":
        selector_commitment(r["selection_id"])
    elif kind == "PATCH_ERROR":
        if type(r["code"]) is not str or r["code"] not in ERROR_CODES:
            raise ContentError()
    else:
        _integer(
            r["sequence"], 0 if kind == "PATCH_PAGE" else 1, 15 if kind == "PATCH_PAGE" else 16
        )
        total = _integer(r["total_bytes"], 1, MAX_PATCH_BYTES)
        _hex(r["patch_digest"])
        _u64(r["observed_at_ms"])
        if type(r["complete"]) is not bool or r["complete"] != (kind == "PATCH_END"):
            raise ContentError()
        if kind == "PATCH_PAGE" and len(_payload(r["data"])) > total:
            raise ContentError()
    limit = MAX_PAGE_BYTES if kind == "PATCH_PAGE" else MAX_CONTROL_BYTES
    if len(_canonical(r)) > limit:
        raise ContentError()
    return cast(Message, r)


def encode_message(value: object) -> bytes:
    return _canonical(validate_message(value))


def decode_message(raw: bytes) -> Message:
    return validate_message(_parse(raw, MAX_PAGE_BYTES))


def _common(context: ContentContext) -> Common:
    return {
        "protocol_id": PROTOCOL_ID,
        "protocol_version": VERSION,
        "context_digest": context_digest(context),
        "request_nonce": context["request_nonce"],
    }


def _patch(raw: bytes) -> str:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_PATCH_BYTES:
        raise ContentError("PATCH_TOO_LARGE")
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise ContentError("PATCH_UNAVAILABLE_ENCODING") from None
    if len(text.splitlines()) > MAX_LINES:
        raise ContentError("PATCH_TOO_LARGE")
    return text


def prepare_pages(context: object, patch: bytes, observed_at_ms: str) -> tuple[bytes, ...]:
    """All-or-nothing planner: no page escapes before every budget passes."""
    c = validate_context(context)
    _patch(patch)
    description = {
        **_common(c),
        "kind": "PATCH_PAGE",
        "total_bytes": len(patch),
        "patch_digest": hashlib.sha256(patch).hexdigest(),
        "observed_at_ms": _u64(observed_at_ms),
        "complete": False,
    }
    # Reserve the largest two-digit sequence. Base64url length is ceil(n*8/6).
    overhead = len(_canonical({**description, "sequence": 15, "data": ""}))
    capacity = ((MAX_PAGE_BYTES - overhead) * 6) // 8
    count = (len(patch) + capacity - 1) // capacity
    if count > MAX_PAGES:
        raise ContentError("PATCH_TOO_LARGE")
    pages = tuple(
        encode_message(
            {
                **description,
                "sequence": index,
                "data": _b64(patch[index * capacity : (index + 1) * capacity]),
            }
        )
        for index in range(count)
    )
    end = encode_message({**description, "kind": "PATCH_END", "sequence": count, "complete": True})
    return (*pages, end)


class ContentRead:
    """Pure one-read transcript model, not a session/READY resolver or replay store.

    The external owner must supply trusted current context and monotonic time on
    EVERY call and call check while idle. Close on visibility/revocation/loss.
    Only END returns verified complete bytes; PAGE never exposes partial text.
    """

    def __init__(self, context: object, *, now_ms: int, deadline_ms: int) -> None:
        self._context = validate_context(context)
        self._last = _integer(now_ms, 0, MAX_TIME)
        self._deadline = _integer(deadline_ms, now_ms + 1, min(MAX_TIME, now_ms + MAX_READ_MS))
        self._closed = False
        self._started = False
        self._pages: list[bytes] = []
        self._size = 0
        self._description: tuple[int, str, str] | None = None

    def close(self) -> None:
        self._closed = True
        self._pages.clear()
        self._size = 0
        self._description = None

    def check(self, *, now_ms: int, current_context: object) -> None:
        try:
            if self._closed or validate_context(current_context) != self._context:
                raise ContentError()
            _integer(now_ms, self._last, MAX_TIME)
            if now_ms >= self._deadline:
                raise ContentError("PATCH_TIMEOUT")
            self._last = now_ms
        except ContentError:
            self.close()
            raise

    def accept(self, raw: bytes, *, now_ms: int, current_context: object) -> bytes | None:
        try:
            self.check(now_ms=now_ms, current_context=current_context)
            message = decode_message(raw)
            if (
                message["context_digest"] != context_digest(self._context)
                or message["request_nonce"] != self._context["request_nonce"]
            ):
                raise ContentError()
            if message["kind"] == "PATCH_READ":
                if (
                    self._started
                    or selector_commitment(message["selection_id"])
                    != self._context["selector_commitment"]
                ):
                    raise ContentError()
                self._started = True
                return None
            if not self._started:
                raise ContentError()
            if message["kind"] == "PATCH_ERROR":
                raise ContentError(message["code"])
            description = (
                message["total_bytes"],
                message["patch_digest"],
                message["observed_at_ms"],
            )
            if self._description is not None and description != self._description:
                raise ContentError()
            if message["sequence"] != len(self._pages):
                raise ContentError()
            if message["kind"] == "PATCH_PAGE":
                data = _payload(message["data"])
                if len(self._pages) >= MAX_PAGES or self._size + len(data) > message["total_bytes"]:
                    raise ContentError()
                self._description = description
                self._pages.append(data)
                self._size += len(data)
                return None
            patch = b"".join(self._pages)
            if (
                self._size != message["total_bytes"]
                or hashlib.sha256(patch).hexdigest() != message["patch_digest"]
            ):
                raise ContentError()
            _patch(patch)
            self.close()
            return patch
        except ContentError:
            self.close()
            raise
