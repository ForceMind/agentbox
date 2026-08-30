"""Closed, bounded WAW control-socket v1 codec.

The control socket carries lifecycle metadata only.  It never carries a path,
command, process identifier, terminal bytes, ticket bearer, or ciphertext.
This module intentionally does not implement the separate ABWS stream or
Noise channel; it validates the exact JSON line boundary used before those
layers are admitted.
"""

from __future__ import annotations

import json
import re
from typing import Any

WAW_CONTROL_PROTOCOL_VERSION = 1
MAX_CONTROL_LINE = 16 * 1024
MAX_CONTROL_ENVELOPE = 4 * 1024
MAX_CONTROL_DEPTH = 16
MAX_CONTROL_KEYS = 64
MAX_U64 = 2**64 - 1

_REQUEST_ID = re.compile(r"\Awreq_[0-9a-f]{32}\Z")
_PROJECT_ID = re.compile(r"\Aprj_[0-9a-f]{32}\Z")
_WORKSPACE_ID = re.compile(r"\Aaws_[0-9a-f]{32}\Z")
_ATTACHMENT_ID = re.compile(r"\Aatt_[0-9a-f]{32}\Z")
_HOST_ID = re.compile(r"\Awri_[0-9a-f]{32}\Z")
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_NONCE = re.compile(r"\A[0-9a-f]{32}\Z")
_DECIMAL = re.compile(r"\A(?:0|[1-9][0-9]*)\Z")
_RELATIVE_KEY = re.compile(r"\A[^/\\.][^/\\]*\Z")


class WAWControlError(ValueError):
    """Malformed or out-of-contract WAW control data."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WAWControlError("duplicate JSON object key")
        result[key] = value
    return result


def _walk(value: Any, *, depth: int = 0, keys: int = 0) -> int:
    if depth > MAX_CONTROL_DEPTH:
        raise WAWControlError("JSON nesting exceeds WAW control limit")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise WAWControlError("JSON object keys must be strings")
            keys += 1
            if keys > MAX_CONTROL_KEYS:
                raise WAWControlError("JSON object key count exceeds WAW control limit")
            keys = _walk(item, depth=depth + 1, keys=keys)
    elif isinstance(value, list):
        for item in value:
            keys = _walk(item, depth=depth + 1, keys=keys)
    elif isinstance(value, str) and any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise WAWControlError("unpaired UTF-16 surrogate is not permitted")
    return keys


def _load_line(raw: bytes | bytearray | memoryview) -> dict[str, Any]:
    try:
        value = bytes(raw)
    except (TypeError, ValueError) as exc:
        raise WAWControlError("control record must be bytes") from exc
    if len(value) > MAX_CONTROL_LINE:
        raise WAWControlError("control record exceeds 16 KiB")
    if not value.endswith(b"\n") or value[:-1].find(b"\n") >= 0:
        raise WAWControlError("control record must end with exactly one LF")
    body = value[:-1]
    if len(body) + 1 > MAX_CONTROL_ENVELOPE:
        # A bounded oversized record is still rejected before any action.  The
        # caller may normalize this to PROTOCOL_INVALID at the socket layer.
        raise WAWControlError("control envelope exceeds 4 KiB")
    try:
        decoded = json.loads(body, object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except (json.JSONDecodeError, RecursionError, UnicodeDecodeError, TypeError) as exc:
        raise WAWControlError("control JSON is malformed") from exc
    if not isinstance(decoded, dict):
        raise WAWControlError("control JSON must be an object")
    _walk(decoded)
    return decoded


def _reject_constant(value: str) -> None:
    raise WAWControlError(f"JSON constant is not permitted: {value}")


def _require_keys(value: dict[str, Any], expected: set[str]) -> None:
    if set(value) != expected:
        raise WAWControlError("control action fields are not exact")


def _string(value: Any, *, name: str, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value:
        raise WAWControlError(f"{name} is invalid")
    if pattern is not None and not pattern.fullmatch(value):
        raise WAWControlError(f"{name} is invalid")
    return value


def _u64(value: Any, *, name: str) -> int:
    if type(value) is not int or not 1 <= value <= MAX_U64:
        raise WAWControlError(f"{name} is not a uint64")
    return value


def _decimal_u64(value: Any, *, name: str, allow_zero: bool = False) -> str:
    if not isinstance(value, str) or not _DECIMAL.fullmatch(value):
        raise WAWControlError(f"{name} is not a canonical decimal uint64")
    parsed = int(value)
    if parsed > MAX_U64 or (not allow_zero and parsed == 0):
        raise WAWControlError(f"{name} is not a uint64")
    return value


def _common(value: dict[str, Any], action: str) -> None:
    if value.get("protocol_version") != WAW_CONTROL_PROTOCOL_VERSION:
        raise WAWControlError("protocol_version must be 1")
    _string(value.get("request_id"), name="request_id", pattern=_REQUEST_ID)
    if value.get("action") != action:
        raise WAWControlError("action is invalid")


def _relative_key(value: Any) -> str:
    key = _string(value, name="relative_key")
    if (
        len(key) > 80
        or key != key.strip()
        or key in {".", ".."}
        or not _RELATIVE_KEY.fullmatch(key)
    ):
        raise WAWControlError("relative_key is invalid")
    if any(ord(char) < 32 or 0x7F <= ord(char) <= 0x9F for char in key):
        raise WAWControlError("relative_key contains a control character")
    if any(not (char.isalnum() or char in {"-", "_", ".", " "}) for char in key):
        raise WAWControlError("relative_key contains unsupported characters")
    return key


def _validate_request(value: dict[str, Any]) -> dict[str, Any]:
    action = value.get("action")
    if not isinstance(action, str):
        raise WAWControlError("action is invalid")
    common = {"protocol_version", "request_id", "action"}
    schemas: dict[str, set[str]] = {
        "workspace.api_authority.bind": common | {"api_authority_epoch", "authority_nonce"},
        "workspace.project_binding.register": common
        | {
            "project_id", "relative_key", "project_revision", "binding_revision",
            "previous_binding_revision", "previous_binding_digest", "schema_version",
            "runtime_host_installation_id", "runtime_host_installation_revision",
        },
        "workspace.workspace.start": common
        | {
            "workspace_id", "project_id", "agent_type", "generation", "binding_revision",
            "binding_digest", "runtime_host_installation_id", "runtime_host_installation_revision",
        },
        "workspace.workspace.stop": common
        | {
            "workspace_id", "project_id", "agent_type", "generation", "binding_revision",
            "binding_digest", "runtime_host_installation_id", "runtime_host_installation_revision",
        },
        "workspace.workspace.status": common
        | {
            "workspace_id", "project_id", "agent_type", "generation", "binding_revision",
            "binding_digest", "runtime_host_installation_id", "runtime_host_installation_revision",
        },
        "workspace.workspace.reconcile": common
        | {
            "workspace_id", "project_id", "agent_type", "generation", "binding_revision",
            "binding_digest", "runtime_host_installation_id", "runtime_host_installation_revision",
        },
        "workspace.attach.prepare": common
        | {
            "workspace_id", "project_id", "agent_type", "attachment_id", "mode", "lease_number",
            "generation", "binding_revision", "binding_digest", "auth_epoch", "api_authority_epoch",
            "runtime_host_installation_id", "runtime_host_installation_revision", "runtime_epoch",
            "resume_cursor", "previous_runtime_epoch",
        },
        "workspace.attach.detach": common
        | {
            "workspace_id", "project_id", "agent_type", "attachment_id", "mode", "lease_number",
            "generation", "binding_revision", "binding_digest", "auth_epoch", "api_authority_epoch",
            "runtime_host_installation_id", "runtime_host_installation_revision", "runtime_epoch",
        },
    }
    expected = schemas.get(action)
    if expected is None:
        raise WAWControlError("unsupported WAW control action")
    _require_keys(value, expected)
    _common(value, action)
    if action == "workspace.api_authority.bind":
        _u64(value["api_authority_epoch"], name="api_authority_epoch")
        _string(value["authority_nonce"], name="authority_nonce", pattern=_NONCE)
        return value
    if action == "workspace.project_binding.register":
        _string(value["project_id"], name="project_id", pattern=_PROJECT_ID)
        _relative_key(value["relative_key"])
        for name in ("project_revision", "binding_revision", "runtime_host_installation_revision"):
            _u64(value[name], name=name)
        previous = value["previous_binding_revision"]
        previous_digest = value["previous_binding_digest"]
        if value["binding_revision"] == 1:
            if previous is not None or previous_digest is not None:
                raise WAWControlError("first binding cannot have a predecessor")
        else:
            _u64(previous, name="previous_binding_revision")
            _string(previous_digest, name="previous_binding_digest", pattern=_DIGEST)
        if value["schema_version"] != "waw-project-binding-v1":
            raise WAWControlError("schema_version is invalid")
        _string(
            value["runtime_host_installation_id"],
            name="runtime_host_installation_id",
            pattern=_HOST_ID,
        )
        return value
    _string(value["workspace_id"], name="workspace_id", pattern=_WORKSPACE_ID)
    _string(value["project_id"], name="project_id", pattern=_PROJECT_ID)
    if value["agent_type"] not in {"claude", "codex"}:
        raise WAWControlError("agent_type is invalid")
    for name in ("generation", "binding_revision", "runtime_host_installation_revision"):
        _u64(value[name], name=name)
    _string(value["binding_digest"], name="binding_digest", pattern=_DIGEST)
    _string(
        value["runtime_host_installation_id"],
        name="runtime_host_installation_id",
        pattern=_HOST_ID,
    )
    if action.startswith("workspace.attach"):
        _string(value["attachment_id"], name="attachment_id", pattern=_ATTACHMENT_ID)
        if value["mode"] != "writer":
            raise WAWControlError("mode is invalid")
        _u64(value["lease_number"], name="lease_number")
        _u64(value["auth_epoch"], name="auth_epoch")
        _u64(value["api_authority_epoch"], name="api_authority_epoch")
        _decimal_u64(value["runtime_epoch"], name="runtime_epoch")
        if action.endswith("prepare"):
            if value["resume_cursor"] is not None:
                _decimal_u64(value["resume_cursor"], name="resume_cursor", allow_zero=True)
            if value["previous_runtime_epoch"] is not None:
                _decimal_u64(value["previous_runtime_epoch"], name="previous_runtime_epoch")
    return value


def decode_control_request(raw: bytes | bytearray | memoryview) -> dict[str, Any]:
    """Decode and validate one WAW control request line."""

    return _validate_request(_load_line(raw))


def encode_control_request(request: dict[str, Any]) -> bytes:
    """Validate and encode one WAW control request line."""

    _validate_request(request)
    try:
        encoded = json.dumps(
            request, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8") + b"\n"
    except (TypeError, UnicodeEncodeError, ValueError) as exc:
        raise WAWControlError("control request is not strict JSON") from exc
    if len(encoded) > MAX_CONTROL_ENVELOPE:
        raise WAWControlError("control envelope exceeds 4 KiB")
    return encoded


__all__ = [
    "MAX_CONTROL_ENVELOPE",
    "MAX_CONTROL_KEYS",
    "MAX_CONTROL_LINE",
    "MAX_CONTROL_DEPTH",
    "MAX_U64",
    "WAW_CONTROL_PROTOCOL_VERSION",
    "WAWControlError",
    "decode_control_request",
    "encode_control_request",
]
