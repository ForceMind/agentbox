"""Closed, bounded WAW control-socket v1 codec.

The control socket carries lifecycle metadata only.  It never carries a path,
command, process identifier, terminal bytes, ticket bearer, or ciphertext.
This module intentionally does not implement the separate ABWS stream or
Noise channel; it validates the exact JSON line boundary used before those
layers are admitted.
"""

from __future__ import annotations

import hmac
import json
import re
import unicodedata
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
_DECIMAL = re.compile(r"\A(?:0|[1-9][0-9]{0,19})\Z")
_CAPABILITY = re.compile(r"\A[0-9a-f]{64}\Z")
_RELATIVE_KEY = re.compile(r"\A[^/\\.][^/\\]*\Z")

_ERROR_CODES = frozenset(
    {
        "PROTOCOL_INVALID",
        "SEQUENCE_EXHAUSTED",
        "RANDOMNESS_UNAVAILABLE",
        "RUNTIME_INSTALLATION_UNTRUSTED",
        "RUNTIME_INSTALLATION_MISMATCH",
        "RUNTIME_PEER_FORBIDDEN",
        "RUNTIME_UNAVAILABLE",
        "WAW_SOCKET_SET_INCOMPLETE",
        "WAW_SOCKET_PROVENANCE_INVALID",
        "WAW_AGENT_UNSUPPORTED",
        "CONTROL_BUSY",
        "CONTROL_UNAVAILABLE",
        "WAW_TMP_UNTRUSTED",
        "WAW_CGROUP_UNTRUSTED",
        "SERVICE_SHUTDOWN",
        "WORKSPACE_NOT_FOUND",
        "WORKSPACE_NOT_READY",
        "WORKSPACE_NOT_RUNNING",
        "WORKSPACE_START_IN_PROGRESS",
        "WORKSPACE_WRITER_BUSY",
        "WORKSPACE_RESOURCE_LIMITED",
        "WORKSPACE_COLLISION",
        "WORKSPACE_MISSING",
        "WORKSPACE_EXITED",
        "WORKSPACE_STOPPED",
        "RECONCILIATION_REQUIRED",
        "BINDING_BOOTSTRAP_REQUIRED",
        "PROJECT_PATH_UNSUPPORTED",
        "PROJECT_RUNTIME_ACTIVE",
        "PROJECT_IDENTITY_CHANGED",
        "CODEX_REMOTE_CONFLICT",
        "WORKSPACE_AUTH_REQUIRED",
        "WORKSPACE_AUTH_STATUS_UNKNOWN",
        "WORKSPACE_AUTH_CHECK_REQUIRED",
        "WORKSPACE_TRUST_REQUIRED",
        "WORKSPACE_EXECUTABLE_UNSUPPORTED",
        "ATTACHMENT_TICKET_EXPIRED",
        "ATTACHMENT_TICKET_REPLAYED",
        "ATTACHMENT_TICKET_UNAVAILABLE",
        "ATTACHMENT_TICKET_RATE_LIMITED",
        "KEY_CONFIRM_FAILED",
        "STREAM_CRYPTO_FAILURE",
        "ATTACHMENT_PREPARE_REPLAY",
        "ATTACHMENT_STALE",
        "DETACH_FAILED",
        "DETACH_IN_PROGRESS",
        "ATTACHMENT_NOT_READY",
        "ADMITTED_DELIVERY_FAILED",
        "INPUT_RATE_LIMITED",
        "CONTROL_RATE_LIMITED",
        "OUTPUT_BACKPRESSURE",
        "RESIZE_FAILED",
        "TERMINAL_PARSE_LIMIT",
        "INPUT_WRITE_UNCERTAIN",
        "STOP_TIMEOUT",
        "INTERNAL_BOUNDED",
    }
)


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
    if not value.endswith(b"\n") or value[:-1].find(b"\n") >= 0 or value[:-1].endswith(b"\r"):
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


def _u64(value: Any, *, name: str) -> str:
    return _decimal_u64(value, name=name)


def _decimal_u64(value: Any, *, name: str, allow_zero: bool = False) -> str:
    if not isinstance(value, str) or not _DECIMAL.fullmatch(value):
        raise WAWControlError(f"{name} is not a canonical decimal uint64")
    parsed = int(value)
    if parsed > MAX_U64 or (not allow_zero and parsed == 0):
        raise WAWControlError(f"{name} is not a uint64")
    return value


def _common(value: dict[str, Any], action: str) -> None:
    if type(value.get("protocol_version")) is not int or value["protocol_version"] != 1:
        raise WAWControlError("protocol_version must be 1")
    _string(value.get("request_id"), name="request_id", pattern=_REQUEST_ID)
    if value.get("action") != action:
        raise WAWControlError("action is invalid")


def validate_relative_key(value: Any) -> str:
    """Validate the one-component WAW Project key shared by wire and ledger."""

    key = _string(value, name="relative_key")
    if (
        len(key) > 80
        or key != key.strip()
        or key in {".", ".."}
        or not _RELATIVE_KEY.fullmatch(key)
        or unicodedata.normalize("NFC", key) != key
    ):
        raise WAWControlError("relative_key is invalid")
    if any(unicodedata.category(char).startswith("C") for char in key):
        raise WAWControlError("relative_key contains a Unicode category C character")
    if any(ord(char) < 32 or 0x7F <= ord(char) <= 0x9F for char in key):
        raise WAWControlError("relative_key contains a control character")
    if any(not (char.isalnum() or char in {"-", "_", ".", " "}) for char in key):
        raise WAWControlError("relative_key contains unsupported characters")
    return key


def _relative_key(value: Any) -> str:
    """Compatibility wrapper for callers predating the public validator."""

    return validate_relative_key(value)


def _validate_request(value: dict[str, Any]) -> dict[str, Any]:
    action = value.get("action")
    if not isinstance(action, str):
        raise WAWControlError("action is invalid")
    common = {"protocol_version", "request_id", "action"}
    schemas: dict[str, set[str]] = {
        "workspace.api_authority.bind": common | {"api_authority_epoch", "authority_nonce"},
        "workspace.project_binding.register": common
        | {
            "project_id",
            "relative_key",
            "project_revision",
            "binding_revision",
            "previous_binding_revision",
            "previous_binding_digest",
            "schema_version",
            "runtime_host_installation_id",
            "runtime_host_installation_revision",
        },
        "workspace.workspace.start": common
        | {
            "workspace_id",
            "project_id",
            "agent_type",
            "generation",
            "binding_revision",
            "binding_digest",
            "runtime_host_installation_id",
            "runtime_host_installation_revision",
        },
        "workspace.workspace.stop": common
        | {
            "workspace_id",
            "project_id",
            "agent_type",
            "generation",
            "binding_revision",
            "binding_digest",
            "runtime_host_installation_id",
            "runtime_host_installation_revision",
        },
        "workspace.workspace.status": common
        | {
            "workspace_id",
            "project_id",
            "agent_type",
            "generation",
            "binding_revision",
            "binding_digest",
            "runtime_host_installation_id",
            "runtime_host_installation_revision",
        },
        "workspace.workspace.reconcile": common
        | {
            "workspace_id",
            "project_id",
            "agent_type",
            "generation",
            "binding_revision",
            "binding_digest",
            "runtime_host_installation_id",
            "runtime_host_installation_revision",
        },
        "workspace.attach.prepare": common
        | {
            "workspace_id",
            "project_id",
            "agent_type",
            "attachment_id",
            "mode",
            "lease_number",
            "generation",
            "binding_revision",
            "binding_digest",
            "auth_epoch",
            "api_authority_epoch",
            "runtime_host_installation_id",
            "runtime_host_installation_revision",
            "runtime_epoch",
            "resume_cursor",
            "previous_runtime_epoch",
        },
        "workspace.attach.detach": common
        | {
            "workspace_id",
            "project_id",
            "agent_type",
            "attachment_id",
            "mode",
            "lease_number",
            "generation",
            "binding_revision",
            "binding_digest",
            "auth_epoch",
            "api_authority_epoch",
            "runtime_host_installation_id",
            "runtime_host_installation_revision",
            "runtime_epoch",
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
        validate_relative_key(value["relative_key"])
        for name in ("project_revision", "binding_revision", "runtime_host_installation_revision"):
            _u64(value[name], name=name)
        previous = value["previous_binding_revision"]
        previous_digest = value["previous_binding_digest"]
        if value["binding_revision"] == "1":
            if previous is not None or previous_digest is not None:
                raise WAWControlError("first binding cannot have a predecessor")
        else:
            _u64(previous, name="previous_binding_revision")
            _string(previous_digest, name="previous_binding_digest", pattern=_DIGEST)
            if int(previous) + 1 != int(value["binding_revision"]):
                raise WAWControlError("binding predecessor must be the exact prior revision")
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
        encoded = (
            json.dumps(request, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode(
                "utf-8"
            )
            + b"\n"
        )
    except (TypeError, UnicodeEncodeError, ValueError) as exc:
        raise WAWControlError("control request is not strict JSON") from exc
    if len(encoded) > MAX_CONTROL_ENVELOPE:
        raise WAWControlError("control envelope exceeds 4 KiB")
    return encoded


_COMMON_RESPONSE = {"protocol_version", "request_id", "status"}
_WORKSPACE_STATES = frozenset(
    {
        "STARTING",
        "RUNNING",
        "NEEDS_INTERACTION",
        "TRUST_REQUIRED",
        "LOGIN_REQUIRED",
        "STOPPING",
        "EXITED",
        "STOPPED",
        "MISSING",
        "COLLISION",
        "BROKEN",
        "UNKNOWN",
    }
)
_RECONCILIATION_STATES = frozenset(
    {
        "authoritative",
        "stopping",
        "missing",
        "collision",
        "exited",
        "reconciliation_required",
        "unknown",
    }
)
_PROCESS_STATES = frozenset(
    {
        "NOT_STARTED",
        "STARTING",
        "RUNNING",
        "LOGIN_REQUIRED",
        "TRUST_REQUIRED",
        "NEEDS_INTERACTION",
        "EXITED",
        "STOPPING",
        "STOPPED",
        "MISSING",
        "COLLISION",
        "BROKEN",
        "UNKNOWN",
    }
)
_TUPLE_RESPONSE = {
    "workspace_id",
    "project_id",
    "agent_type",
    "attachment_id",
    "mode",
    "lease_number",
    "generation",
    "binding_revision",
    "binding_digest",
    "auth_epoch",
    "api_authority_epoch",
    "runtime_host_installation_id",
    "runtime_host_installation_revision",
    "runtime_epoch",
}


def _response_error(value: dict[str, Any]) -> dict[str, Any]:
    _require_keys(value, _COMMON_RESPONSE | {"error_code", "retryable"})
    if value["status"] != "ERROR":
        raise WAWControlError("response status is invalid")
    _string(value["request_id"], name="request_id", pattern=_REQUEST_ID)
    if type(value["protocol_version"]) is not int or value["protocol_version"] != 1:
        raise WAWControlError("protocol_version must be 1")
    _string(value["error_code"], name="error_code")
    if value["error_code"] not in _ERROR_CODES:
        raise WAWControlError("error_code is invalid")
    if type(value["retryable"]) is not bool:
        raise WAWControlError("retryable is invalid")
    return value


def _response_common(value: dict[str, Any], expected: set[str]) -> None:
    _require_keys(value, expected)
    if type(value["protocol_version"]) is not int or value["protocol_version"] != 1:
        raise WAWControlError("protocol_version must be 1")
    _string(value["request_id"], name="request_id", pattern=_REQUEST_ID)
    if value["status"] == "ERROR":
        _response_error(value)
        raise WAWControlError("error response has wrong schema")


def _response_identity(value: dict[str, Any], *, attachment: bool = False) -> None:
    _string(value["workspace_id"], name="workspace_id", pattern=_WORKSPACE_ID)
    _string(value["project_id"], name="project_id", pattern=_PROJECT_ID)
    if value["agent_type"] not in {"claude", "codex"}:
        raise WAWControlError("agent_type is invalid")
    if attachment:
        _string(value["attachment_id"], name="attachment_id", pattern=_ATTACHMENT_ID)
        if value["mode"] != "writer":
            raise WAWControlError("mode is invalid")
        _string(value["binding_digest"], name="binding_digest", pattern=_DIGEST)
        for name in (
            "lease_number",
            "generation",
            "binding_revision",
            "auth_epoch",
            "api_authority_epoch",
            "runtime_host_installation_revision",
        ):
            _decimal_u64(value[name], name=name)
        _string(
            value["runtime_host_installation_id"],
            name="runtime_host_installation_id",
            pattern=_HOST_ID,
        )
        _decimal_u64(value["runtime_epoch"], name="runtime_epoch")


def _validate_response(
    value: dict[str, Any], action: str, expected_request_id: str | None = None
) -> dict[str, Any]:
    if not isinstance(action, str):
        raise WAWControlError("response action is invalid")
    if not isinstance(value, dict):
        raise WAWControlError("control response must be an object")
    if expected_request_id is not None:
        _string(expected_request_id, name="expected_request_id", pattern=_REQUEST_ID)
        request_id = value.get("request_id")
        if not isinstance(request_id, str) or not hmac.compare_digest(
            request_id, expected_request_id
        ):
            raise WAWControlError("response request_id does not match request")
    supported_actions = {
        "workspace.api_authority.bind",
        "workspace.project_binding.register",
        "workspace.workspace.start",
        "workspace.workspace.stop",
        "workspace.workspace.status",
        "workspace.workspace.reconcile",
        "workspace.attach.prepare",
        "workspace.attach.detach",
    }
    if action not in supported_actions:
        raise WAWControlError("unsupported WAW control action")
    if value.get("status") == "ERROR":
        return _response_error(value)

    success: dict[str, set[str]] = {
        "workspace.api_authority.bind": _COMMON_RESPONSE
        | {
            "api_authority_epoch",
            "runtime_epoch",
            "runtime_host_installation_id",
            "runtime_host_installation_revision",
            "host_manifest_digest",
            "project_root_manifest_digest",
            "enrollment_epoch",
            "enrollment_state",
        },
        "workspace.project_binding.register": _COMMON_RESPONSE
        | {
            "project_id",
            "binding_revision",
            "binding_digest",
            "runtime_host_installation_id",
            "runtime_host_installation_revision",
        },
        "workspace.workspace.start": _COMMON_RESPONSE
        | {
            "workspace_id",
            "project_id",
            "agent_type",
            "generation",
            "state",
            "runtime_host_installation_id",
            "runtime_host_installation_revision",
        },
        "workspace.workspace.stop": _COMMON_RESPONSE
        | {"workspace_id", "project_id", "agent_type", "generation", "state"},
        "workspace.workspace.status": _COMMON_RESPONSE
        | {
            "workspace_id",
            "project_id",
            "agent_type",
            "generation",
            "binding_revision",
            "binding_digest",
            "state",
            "reconciliation_state",
            "runtime_epoch",
            "process_state",
            "exit_code",
            "attachment_capacity",
        },
        "workspace.workspace.reconcile": _COMMON_RESPONSE
        | {
            "workspace_id",
            "project_id",
            "agent_type",
            "generation",
            "binding_revision",
            "binding_digest",
            "runtime_epoch",
            "state",
            "reconciliation_state",
        },
        "workspace.attach.prepare": _COMMON_RESPONSE
        | _TUPLE_RESPONSE
        | {"resume_cursor", "previous_runtime_epoch", "capability"},
        "workspace.attach.detach": _COMMON_RESPONSE
        | _TUPLE_RESPONSE
        | {"cleanup_state", "reason_code"},
    }
    expected = success.get(action)
    if expected is None:
        raise WAWControlError("unsupported WAW control action")
    if action == "workspace.attach.prepare" and value.get("status") != "PREPARED":
        expected = expected - {"capability"}
    _response_common(value, expected)
    status = value["status"]
    if action == "workspace.api_authority.bind":
        if status not in {"BOUND", "ALREADY_BOUND"}:
            raise WAWControlError("response status is invalid")
        _decimal_u64(value["api_authority_epoch"], name="api_authority_epoch")
        _decimal_u64(value["runtime_epoch"], name="runtime_epoch")
        _string(
            value["runtime_host_installation_id"],
            name="runtime_host_installation_id",
            pattern=_HOST_ID,
        )
        _decimal_u64(
            value["runtime_host_installation_revision"], name="runtime_host_installation_revision"
        )
        _string(value["host_manifest_digest"], name="host_manifest_digest", pattern=_DIGEST)
        _string(
            value["project_root_manifest_digest"],
            name="project_root_manifest_digest",
            pattern=_DIGEST,
        )
        _decimal_u64(value["enrollment_epoch"], name="enrollment_epoch")
        if value["enrollment_state"] not in {"bootstrap", "steady", "rotation"}:
            raise WAWControlError("enrollment_state is invalid")
    elif action == "workspace.project_binding.register":
        if status not in {"REGISTERED", "ALREADY_CURRENT"}:
            raise WAWControlError("response status is invalid")
        _string(value["project_id"], name="project_id", pattern=_PROJECT_ID)
        _decimal_u64(value["binding_revision"], name="binding_revision")
        _string(value["binding_digest"], name="binding_digest", pattern=_DIGEST)
        _string(
            value["runtime_host_installation_id"],
            name="runtime_host_installation_id",
            pattern=_HOST_ID,
        )
        _decimal_u64(
            value["runtime_host_installation_revision"], name="runtime_host_installation_revision"
        )
    elif action in {"workspace.workspace.start", "workspace.workspace.stop"}:
        allowed = (
            {"STARTED", "ALREADY_RUNNING", "START_IN_PROGRESS"}
            if action.endswith("start")
            else {"STOPPED", "ALREADY_STOPPED", "STOP_IN_PROGRESS"}
        )
        if status not in allowed:
            raise WAWControlError("response status is invalid")
        _response_identity(value)
        _decimal_u64(value["generation"], name="generation")
        if action.endswith("start"):
            _string(
                value["runtime_host_installation_id"],
                name="runtime_host_installation_id",
                pattern=_HOST_ID,
            )
            _decimal_u64(
                value["runtime_host_installation_revision"],
                name="runtime_host_installation_revision",
            )
        if value["state"] not in _WORKSPACE_STATES:
            raise WAWControlError("state is invalid")
    elif action == "workspace.workspace.status":
        if status != "STATUS":
            raise WAWControlError("response status is invalid")
        _response_identity(value)
        _decimal_u64(value["generation"], name="generation")
        _decimal_u64(value["binding_revision"], name="binding_revision")
        _string(value["binding_digest"], name="binding_digest", pattern=_DIGEST)
        _decimal_u64(value["runtime_epoch"], name="runtime_epoch")
        if (
            value["state"] not in _WORKSPACE_STATES
            or value["reconciliation_state"] not in _RECONCILIATION_STATES
            or value["process_state"] not in _PROCESS_STATES
        ):
            raise WAWControlError("status state is invalid")
        if value["exit_code"] is not None and (
            type(value["exit_code"]) is not int or not -128 <= value["exit_code"] <= 255
        ):
            raise WAWControlError("exit_code is invalid")
        cap = value["attachment_capacity"]
        if not isinstance(cap, dict) or set(cap) != {"admitted", "pending", "limit"}:
            raise WAWControlError("attachment_capacity is invalid")
        for name in ("admitted", "pending", "limit"):
            _decimal_u64(cap[name], name=f"attachment_capacity.{name}", allow_zero=True)
        if cap["limit"] != "32" or int(cap["admitted"]) + int(cap["pending"]) > 64:
            raise WAWControlError("attachment_capacity is invalid")
    elif action == "workspace.workspace.reconcile":
        if status not in {
            "RECONCILED",
            "MISSING",
            "COLLISION",
            "UNKNOWN",
            "RECONCILIATION_REQUIRED",
        }:
            raise WAWControlError("response status is invalid")
        _response_identity(value)
        for name in ("generation", "binding_revision", "runtime_epoch"):
            _decimal_u64(value[name], name=name)
        _string(value["binding_digest"], name="binding_digest", pattern=_DIGEST)
        if (
            value["state"] not in _WORKSPACE_STATES
            or value["reconciliation_state"] not in _RECONCILIATION_STATES
        ):
            raise WAWControlError("reconciliation state is invalid")
    elif action == "workspace.attach.prepare":
        if status not in {
            "PREPARED",
            "RECONCILIATION_REQUIRED",
            "WORKSPACE_WRITER_BUSY",
            "WORKSPACE_NOT_RUNNING",
        }:
            raise WAWControlError("response status is invalid")
        _response_identity(value, attachment=True)
        if value["resume_cursor"] is not None:
            _decimal_u64(value["resume_cursor"], name="resume_cursor", allow_zero=True)
        if value["previous_runtime_epoch"] is not None:
            _decimal_u64(value["previous_runtime_epoch"], name="previous_runtime_epoch")
        if status == "PREPARED":
            _string(value["capability"], name="capability", pattern=_CAPABILITY)
        elif "capability" in value:
            raise WAWControlError("capability is forbidden for non-prepared response")
    elif action == "workspace.attach.detach":
        if status not in {"DETACHED", "ALREADY_DETACHED", "DETACH_IN_PROGRESS", "REJECTED"}:
            raise WAWControlError("response status is invalid")
        _response_identity(value, attachment=True)
        if status in {"DETACHED", "ALREADY_DETACHED"}:
            if value["cleanup_state"] != "ATTACH_PTY_CLOSED" or value["reason_code"] is not None:
                raise WAWControlError("detach cleanup result is invalid")
        elif status == "DETACH_IN_PROGRESS":
            if value["cleanup_state"] != "ATTACH_PTY_CLOSE_UNCERTAIN" or value[
                "reason_code"
            ] not in {"DETACH_IN_PROGRESS", "RECONCILIATION_REQUIRED"}:
                raise WAWControlError("detach cleanup result is invalid")
        elif value["cleanup_state"] != "ATTACH_PTY_CLOSE_UNCERTAIN" or value["reason_code"] not in {
            "DETACH_FAILED",
            "RECONCILIATION_REQUIRED",
        }:
            raise WAWControlError("detach cleanup result is invalid")
    return value


def decode_control_response(
    raw: bytes | bytearray | memoryview,
    action: str,
    *,
    expected_request_id: str | None = None,
) -> dict[str, Any]:
    """Decode and validate one action-bound WAW control response line."""

    return _validate_response(_load_line(raw), action, expected_request_id)


def encode_control_response(response: dict[str, Any], action: str) -> bytes:
    """Validate and encode one action-bound WAW control response line."""

    _validate_response(response, action)
    try:
        encoded = (
            json.dumps(response, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode(
                "utf-8"
            )
            + b"\n"
        )
    except (TypeError, UnicodeEncodeError, ValueError) as exc:
        raise WAWControlError("control response is not strict JSON") from exc
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
    "decode_control_response",
    "encode_control_request",
    "encode_control_response",
    "validate_relative_key",
]
