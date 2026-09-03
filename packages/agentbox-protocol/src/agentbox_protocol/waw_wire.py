"""Closed WAW v1 wire profiles and a data-only four-leg transcript validator.

This layer is not an admission authority, Noise endpoint, PTY bridge or ACK mapper.
Successful validation proves syntax, observed ordering and bound metadata only.
Key JSON and terminal envelopes are retained byte-for-byte, never decrypted.
"""

from __future__ import annotations

import json
import re
import struct
import threading
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from agentbox_protocol.abws import ABWSError, FrameType, decode_frame
from agentbox_protocol.awce import AWCEError, decode_awce
from agentbox_protocol.waw_crypto_context import (
    ADMISSION_KEYS,
    CONTEXT_KEYS,
    MAX_U64,
    WAWContextError,
    derive_context,
    validate_admission,
    validate_context,
    validate_u64,
)

MAX_CONTROL_BYTES = 4096
MAX_FRAME_BYTES = 65536
VALIDATION_CPU_NS = 5_000_000
ADMISSION_TIMEOUT_NS = 5_000_000_000
INPUT_LIMIT = 16384
OUTPUT_LIMIT = 32768


class WireError(ValueError):
    """A bounded diagnostic which never echoes untrusted payloads or bearers."""

    def __init__(self) -> None:
        super().__init__("PROTOCOL_INVALID")


class Leg(StrEnum):
    BROWSER_TO_API = "browser-to-api"
    API_TO_BROWSER = "api-to-browser"
    API_TO_RUNTIME = "api-to-runtime"
    RUNTIME_TO_API = "runtime-to-api"


_BA, _AB, _AR, _RA = tuple(Leg)
_ALLOWED = {
    _BA: frozenset((1, 3, 5, 9, 11, 12, 13, 15)),
    _AB: frozenset((4, 6, 8, 10, 14, 16, 17, 18, 19, 20, 21, 26, 27)),
    _AR: frozenset((2, 3, 5, 9, 11, 12, 13, 14, 15, 20, 22, 24)),
    _RA: frozenset((4, 6, 7, 10, 12, 13, 14, 16, 17, 18, 19, 20, 21, 23, 25, 26, 27)),
}
_HANDSHAKE = {_BA: (1, 3, 5), _AB: (4, 6, 8), _AR: (2, 3, 5, 22, 24), _RA: (7, 4, 6, 23, 25)}
KEY_TYPES = frozenset(
    (FrameType.KEY_INIT, FrameType.KEY_ATTEST, FrameType.KEY_CONFIRM, FrameType.KEY_CONFIRM_ACK)
)
WORKSPACE_STATES = frozenset(
    [
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
    ]
)
ERROR_CODES = frozenset(
    [
        "PROTOCOL_INVALID",
        "SEQUENCE_EXHAUSTED",
        "RANDOMNESS_UNAVAILABLE",
        "RUNTIME_INSTALLATION_UNTRUSTED",
        "RUNTIME_INSTALLATION_MISMATCH",
        "RUNTIME_PEER_FORBIDDEN",
        "RUNTIME_UNAVAILABLE",
        "WAW_SOCKET_SET_INCOMPLETE",
        "WAW_SOCKET_PROVENANCE_INVALID",
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
    ]
)
_RUNTIME_CLOSE = frozenset(
    [
        "ADMISSION_TIMEOUT",
        "ATTACHMENT_STALE",
        "PROTOCOL_INVALID",
        "SEQUENCE_EXHAUSTED",
        "RUNTIME_RESTART",
        "RUNTIME_UNAVAILABLE",
        "WORKSPACE_EXITED",
        "WORKSPACE_STOPPED",
        "OUTPUT_BACKPRESSURE",
        "TERMINAL_PARSE_LIMIT",
        "CONTROL_RATE_LIMITED",
    ]
)
_API_CLOSE = frozenset(
    [
        "DETACHED",
        "LEASE_STALE",
        "SESSION_REVOKED",
        "AUTH_EPOCH_CHANGED",
        "ADMISSION_TIMEOUT",
        "ATTACHMENT_STALE",
        "PROTOCOL_INVALID",
        "SERVICE_SHUTDOWN",
        "RUNTIME_UNAVAILABLE",
        "OUTPUT_BACKPRESSURE",
        "TERMINAL_PARSE_LIMIT",
    ]
)
_INTERNAL_CLOSE = _API_CLOSE | {"CONTROL_RATE_LIMITED", "INTERNAL_BOUNDED"}
_REJECT = frozenset(
    [
        "ATTACHMENT_STALE",
        "WORKSPACE_NOT_RUNNING",
        "WORKSPACE_EXITED",
        "WORKSPACE_STOPPED",
        "RECONCILIATION_REQUIRED",
    ]
)
_RESIZE_REJECT = frozenset(
    [
        "CONTROL_RATE_LIMITED",
        "ATTACHMENT_STALE",
        "WORKSPACE_NOT_RUNNING",
        "WORKSPACE_EXITED",
        "WORKSPACE_STOPPED",
        "RESIZE_FAILED",
    ]
)
_DETACH_REJECT = _REJECT | {"DETACH_FAILED"}
_A = {key: "admission" for key in ADMISSION_KEYS}
_C = {key: "context" for key in CONTEXT_KEYS}
_BASE = {"protocol_version": "one"}
_LEASE = {"attachment_id": "att", "lease_number": "u64"}
_EPOCH = {"runtime_epoch": "u64"}
_B64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def _schema(kind: FrameType, leg: Leg) -> dict[str, str]:
    body: dict[str, str]
    if kind in (FrameType.WS_HELLO, FrameType.RUNTIME_HELLO):
        body = (
            _A
            | _EPOCH
            | {"resume_cursor": "nullable_cursor", "previous_runtime_epoch": "nullable_u64"}
        )
        body |= {"ticket": "wat"} if kind == FrameType.WS_HELLO else {"capability": "hex32"}
    elif kind in (FrameType.KEY_INIT, FrameType.KEY_ATTEST):
        body = _A | _EPOCH | {"noise_protocol": "noise", "crypto_envelope_version": "one"}
        body |= (
            {"browser_ephemeral_public_key": "b64_32", "noise_message_1": "b64_32"}
            if kind == FrameType.KEY_INIT
            else {
                "runtime_attestation_x25519_fingerprint": "hex32",
                "runtime_ephemeral_public_key": "b64_32",
                "noise_message_2": "b64_128",
            }
        )
    elif kind in (FrameType.KEY_CONFIRM, FrameType.KEY_CONFIRM_ACK):
        body = _C | {"noise_protocol": "noise", "ciphertext": "b64_48"}
        if kind == FrameType.KEY_CONFIRM_ACK:
            body |= {"status": "verified", "transcript_context_hash": "hex32"}
    elif kind in (FrameType.HELLO_ACK, FrameType.ADMITTED, FrameType.STREAM_READY_ACK):
        body = _A | _EPOCH | {"state": "RUNNING", "output_cursor": "cursor"}
        if kind == FrameType.HELLO_ACK:
            body |= {"input_limit": "input_limit", "output_limit": "output_limit"}
        elif kind == FrameType.ADMITTED:
            body |= {"lease_expires_at": "timestamp"}
        else:
            body |= {"admission_fence": "hex32"}
    elif kind in (
        FrameType.STREAM_READY,
        FrameType.ADMISSION_COMMIT,
        FrameType.ADMISSION_COMMIT_ACK,
    ):
        body = _A | _EPOCH
        if kind == FrameType.ADMISSION_COMMIT:
            body |= {"admission_fence": "hex32"}
        elif kind == FrameType.ADMISSION_COMMIT_ACK:
            body |= {"result": "commit_result", "reason_code": "nullable_reject"}
    elif kind == FrameType.RESIZE:
        body = _LEASE | {"columns": "columns", "rows": "rows"}
    elif kind == FrameType.RESIZE_ACK:
        body = _LEASE | {
            "acknowledged_hop_sequence": "u64",
            "requested_columns": "columns",
            "requested_rows": "rows",
            "effective_columns": "nullable_columns",
            "effective_rows": "nullable_rows",
            "result": "resize_result",
            "reason_code": "nullable_resize_reject",
        }
    elif kind == FrameType.HEARTBEAT:
        body = _LEASE | {"sent_at_monotonic_tick": "u64"}
    elif kind in (FrameType.PING, FrameType.PONG):
        body = {
            "nonce": "hex8",
            (
                "sent_at_monotonic_tick"
                if kind == FrameType.PING
                else "echoed_sent_at_monotonic_tick"
            ): "u64",
        }
    elif kind == FrameType.DETACH:
        body = dict(_LEASE)
    elif kind == FrameType.DETACH_ACK:
        body = (_A | _EPOCH if leg == _RA else dict(_LEASE)) | {
            "acknowledged_hop_sequence": "u64",
            "result": "detach_result",
            "cleanup_state": "cleanup",
            "reason_code": "nullable_detach_reject",
        }
    elif kind == FrameType.EXIT:
        body = {"state": "exit_state", "exit_code": "nullable_exit_code"}
    elif kind == FrameType.GAP:
        body = {"from_cursor": "cursor", "to_cursor": "u64_zero", "reason": "gap_reason"}
    elif kind == FrameType.ACK:
        body = {
            "runtime_input_hop_sequence": "u64",
            "crypto_sequence": "crypto",
            "result": "input_result",
            "reason_code": "nullable_input_reject",
        }
        if leg == _AB:
            body |= {"browser_input_hop_sequence": "u64"}
    elif kind == FrameType.ERROR:
        body = {"code": "error", "retryable": "bool", "request_id": "nullable_wreq"}
    elif kind == FrameType.CLOSE:
        body = {"code": "close", "workspace_state_at_close": "state"}
    elif kind == FrameType.STATE:
        body = {
            "workspace_id": "aws",
            "project_id": "prj",
            "agent_type": "agent",
            "generation": "u64",
            "state": "state",
            "reason_code": "nullable_error",
        }
        if leg == _RA:
            body |= _EPOCH
    else:
        raise WireError()
    return _BASE | body


def _scalar(value: object, rule: str, leg: Leg) -> None:
    if rule in ("admission", "context"):
        return
    if rule.startswith("nullable_"):
        if value is None:
            return
        rule = rule.removeprefix("nullable_")
    if rule in ("u64", "crypto", "cursor", "u64_zero"):
        minimum = 0 if rule in ("cursor", "u64_zero") else 1
        maximum = MAX_U64 - 1 if rule in ("cursor", "crypto") else MAX_U64
        if (
            type(value) is not str
            or re.fullmatch(r"0|[1-9][0-9]{0,19}", value) is None
            or not minimum <= int(value) <= maximum
        ):
            raise WireError()
        return
    if rule in ("one", "input_limit", "output_limit", "columns", "rows", "exit_code"):
        bounds = {
            "one": (1, 1),
            "input_limit": (INPUT_LIMIT, INPUT_LIMIT),
            "output_limit": (OUTPUT_LIMIT, OUTPUT_LIMIT),
            "columns": (8, 240),
            "rows": (1, 200),
            "exit_code": (-128, 255),
        }
        low, high = bounds[rule]
        if type(value) is not int or not low <= value <= high:
            raise WireError()
        return
    if rule == "bool":
        if type(value) is not bool:
            raise WireError()
        return
    if type(value) is not str:
        raise WireError()
    if rule in ("att", "aws", "prj", "wat", "wreq"):
        if re.fullmatch(rule + r"_[a-f0-9]{32}", value) is None:
            raise WireError()
    elif rule in ("hex8", "hex32"):
        if re.fullmatch(r"[a-f0-9]{" + ("16" if rule == "hex8" else "64") + r"}", value) is None:
            raise WireError()
    elif rule.startswith("b64_"):
        size = int(rule[4:])
        chars = (size * 8 + 5) // 6
        remainder = size % 3
        if (
            len(value) != chars
            or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None
            or (remainder and _B64_ALPHABET.index(value[-1]) % (16 if remainder == 1 else 4))
        ):
            raise WireError()
    elif rule == "timestamp":
        if (
            re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z", value)
            is None
        ):
            raise WireError()
        try:
            # Strict ASCII grammar was checked above. Constructing the calendar
            # value directly avoids strptime's first-use import inside the 5 ms
            # budget while preserving year/day/leap/clock/microsecond validation.
            datetime(
                int(value[0:4]),
                int(value[5:7]),
                int(value[8:10]),
                int(value[11:13]),
                int(value[14:16]),
                int(value[17:19]),
                int(value[20:26]),
            )
        except ValueError:
            raise WireError() from None
    else:
        enums = {
            "noise": {"Noise_NX_25519_AESGCM_SHA256"},
            "verified": {"verified"},
            "RUNNING": {"RUNNING"},
            "agent": {"claude", "codex"},
            "commit_result": {"committed", "rejected"},
            "resize_result": {"applied", "rejected"},
            "detach_result": {"detached", "already_detached", "rejected"},
            "cleanup": {"ATTACH_PTY_CLOSED", "ATTACH_PTY_CLOSE_UNCERTAIN"},
            "exit_state": {"EXITED", "STOPPED", "MISSING", "COLLISION", "BROKEN", "UNKNOWN"},
            "gap_reason": {"baseline_redraw", "ring_overflow", "cursor_expired", "slow_client"},
            "input_result": {"accepted", "written_to_pty", "write_uncertain", "rejected"},
            "error": ERROR_CODES,
            "state": WORKSPACE_STATES,
            "reject": _REJECT,
            "resize_reject": _RESIZE_REJECT,
            "detach_reject": _DETACH_REJECT,
            "input_reject": _REJECT | {"INPUT_RATE_LIMITED", "INPUT_WRITE_UNCERTAIN"},
            "close": (
                _INTERNAL_CLOSE
                if leg == _AR
                else _RUNTIME_CLOSE if leg == _RA else _RUNTIME_CLOSE | _API_CLOSE
            ),
        }
        if value not in enums[rule]:
            raise WireError()


def _profile(kind: object, leg: object) -> tuple[FrameType, Leg]:
    if not isinstance(kind, int) or isinstance(kind, bool) or type(leg) is not Leg:
        raise WireError()
    try:
        frame_type = FrameType(kind)
    except ValueError:
        raise WireError() from None
    if frame_type not in _ALLOWED[leg]:
        raise WireError()
    return frame_type, leg


def validate_payload(
    frame_type: FrameType | int,
    leg: Leg,
    payload: object,
    *,
    admission: object | None = None,
    runtime_epoch: object | None = None,
    trusted_context: bool = True,
) -> dict[str, Any] | bytes:
    """Validate a closed profile; optional bound tuple is compared, never learned.

    Standalone schemas cannot prove server origin, an ACK mapping, a live lease,
    a ping nonce match or a process transition. Those need the owning authority.
    """
    try:
        kind, leg = _profile(frame_type, leg)
        if type(trusted_context) is not bool:
            raise WireError()
        if kind in (FrameType.INPUT, FrameType.OUTPUT):
            if type(payload) is not bytes:
                raise WireError()
            envelope = decode_awce(payload)
            direction, ceiling = (1, INPUT_LIMIT) if kind == FrameType.INPUT else (2, OUTPUT_LIMIT)
            if envelope.direction_id != direction or envelope.ciphertext_length > ceiling + 16:
                raise WireError()
            return payload
        schema = _schema(kind, leg)
        if type(payload) is not dict or payload.keys() != schema.keys():
            raise WireError()
        result = dict(payload)
        for key, rule in schema.items():
            _scalar(result[key], rule, leg)
        if result.keys() >= ADMISSION_KEYS:
            validate_admission({key: result[key] for key in ADMISSION_KEYS})
        elif result.keys() >= CONTEXT_KEYS:
            validate_context({key: result[key] for key in CONTEXT_KEYS})
        if admission is not None:
            bound = validate_admission(admission)
            for key in ADMISSION_KEYS & result.keys():
                if result[key] != bound[key]:
                    raise WireError()
        if runtime_epoch is not None:
            epoch = validate_u64(runtime_epoch)
            if "runtime_epoch" in result and result["runtime_epoch"] != epoch:
                raise WireError()
        if kind == FrameType.ERROR and trusted_context and result["request_id"] is None:
            raise WireError()
        if kind == FrameType.RESIZE_ACK:
            if result["result"] == "applied":
                if result["reason_code"] is not None or any(
                    result["effective_" + dimension] != result["requested_" + dimension]
                    for dimension in ("columns", "rows")
                ):
                    raise WireError()
            elif (
                result["reason_code"] is None
                or result["effective_columns"] is not None
                or result["effective_rows"] is not None
            ):
                raise WireError()
        elif kind == FrameType.DETACH_ACK:
            positive = result["result"] != "rejected"
            if (result["reason_code"] is None) != positive or result["cleanup_state"] != (
                "ATTACH_PTY_CLOSED" if positive else "ATTACH_PTY_CLOSE_UNCERTAIN"
            ):
                raise WireError()
        elif kind == FrameType.ADMISSION_COMMIT_ACK:
            if (result["result"] == "committed") != (result["reason_code"] is None):
                raise WireError()
        elif kind == FrameType.ACK:
            outcome, reason = result["result"], result["reason_code"]
            if outcome in ("accepted", "written_to_pty"):
                if reason is not None:
                    raise WireError()
            elif outcome == "write_uncertain":
                if reason != "INPUT_WRITE_UNCERTAIN":
                    raise WireError()
            elif reason not in _REJECT | {"INPUT_RATE_LIMITED"}:
                raise WireError()
        elif kind == FrameType.GAP:
            start, end = int(result["from_cursor"]), int(result["to_cursor"])
            if result["reason"] == "baseline_redraw":
                if start != 0 or end != 0:
                    raise WireError()
            elif not 1 <= start < end:
                raise WireError()
        return result
    except (WAWContextError, AWCEError, TypeError, KeyError):
        raise WireError() from None


def _exact_integer(token: str) -> int:
    """Exact decimal arithmetic without floating point or decimal context limits."""
    match = re.fullmatch(r"(-?)([0-9]+)(?:\.([0-9]+))?(?:[eE]([+-]?[0-9]+))?", token)
    if match is None:
        raise WireError()
    sign, whole, fraction, exponent = match.groups()
    fraction = fraction or ""
    digits = (whole + fraction).lstrip("0")
    if not digits:
        return 0
    shift = int(exponent or "0") - len(fraction)
    if shift >= 0:
        if len(digits) + shift > 5:
            raise WireError()
        integral = digits + "0" * shift
    else:
        trim = -shift
        if trim >= len(digits) or any(char != "0" for char in digits[-trim:]):
            raise WireError()
        integral = digits[:-trim]
    if len(integral) > 5:
        raise WireError()
    result = int(sign + integral)
    if abs(result) > 32768:
        raise WireError()
    return result


@dataclass(frozen=True, slots=True, repr=False)
class _NumberToken:
    """Preserve a Number spelling without constructing a new type per frame."""

    text: str


def _json_bytes(payload: bytes) -> dict[str, Any]:
    if not 1 <= len(payload) <= MAX_CONTROL_BYTES:
        raise WireError()
    # Bound recursion before the JSON implementation constructs any containers.
    depth = 0
    quoted = escaped = False
    for byte in payload:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > 16:
                raise WireError()
        elif byte in (93, 125):
            depth -= 1
    count = 0

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        nonlocal count
        count += len(items)
        if count > 64:
            raise WireError()
        record: dict[str, Any] = {}
        for key, item in items:
            if key in record:
                raise WireError()
            if type(item) is _NumberToken:
                if key in ("protocol_version", "crypto_envelope_version") and item.text != "1":
                    raise WireError()
                item = _exact_integer(item.text)
            record[key] = item
        return record

    def constant(_: str) -> None:
        raise WireError()

    try:
        value = json.loads(
            payload.decode("utf-8", "strict"),
            object_pairs_hook=pairs,
            parse_float=_NumberToken,
            parse_int=_NumberToken,
            parse_constant=constant,
        )
        if type(value) is not dict:
            raise WireError()
        # No wire profile contains nested data. Reject every non-scalar before
        # copying, including escaped unpaired surrogates in keys or values.
        for key, item in value.items():
            if any(0xD800 <= ord(char) <= 0xDFFF for char in key):
                raise WireError()
            if type(item) not in (str, int, bool, type(None)):
                raise WireError()
            if type(item) is str and any(0xD800 <= ord(char) <= 0xDFFF for char in item):
                raise WireError()
        return value
    except (UnicodeError, ValueError, RecursionError, OverflowError):
        raise WireError() from None


@dataclass(frozen=True, slots=True, repr=False)
class WireFrame:
    frame_type: FrameType
    leg: Leg
    hop_sequence: int
    _payload: bytes = field(repr=False)
    _json: Mapping[str, Any] | None = field(repr=False)
    _wire: bytes = field(repr=False)
    replay: bool = False

    def __post_init__(self) -> None:
        if self._json is not None:
            object.__setattr__(self, "_json", MappingProxyType(dict(self._json)))

    @property
    def payload(self) -> bytes:
        return self._payload

    @property
    def json_payload(self) -> dict[str, Any] | None:
        return None if self._json is None else dict(self._json)

    @property
    def wire_bytes(self) -> bytes:
        return self._wire

    def __repr__(self) -> str:
        return (
            f"WireFrame(frame_type={self.frame_type.name}, leg={self.leg.value}, "
            f"hop_sequence={self.hop_sequence}, payload=<redacted>)"
        )


def decode_wire_frame(
    raw: object,
    leg: Leg,
    *,
    admission: object | None = None,
    runtime_epoch: object | None = None,
    trusted_context: bool = True,
) -> WireFrame:
    """Decode exactly one complete frame, with a 5 ms control validation budget."""
    started = time.thread_time_ns()
    try:
        if (
            not isinstance(raw, (bytes, bytearray, memoryview))
            or not 24 <= len(raw) <= MAX_FRAME_BYTES
        ):
            raise WireError()
        if isinstance(raw, memoryview) and raw.nbytes > MAX_FRAME_BYTES:
            raise WireError()
        wire = bytes(raw)
        kind, leg = _profile(wire[5], leg)
        original = wire[24:]
        record = None if kind in (FrameType.INPUT, FrameType.OUTPUT) else _json_bytes(original)
        frame = decode_frame(wire)
        validated = validate_payload(
            kind,
            leg,
            original if record is None else record,
            admission=admission,
            runtime_epoch=runtime_epoch,
            trusted_context=trusted_context,
        )
        if record is not None and time.thread_time_ns() - started > VALIDATION_CPU_NS:
            raise WireError()
        return WireFrame(
            kind,
            leg,
            frame.hop_sequence,
            original,
            validated if isinstance(validated, dict) else None,
            wire,
        )
    except (ABWSError, UnicodeError, ValueError, TypeError, OverflowError, struct.error):
        raise WireError() from None


def _pack(kind: FrameType, payload: bytes, hop_sequence: int) -> bytes:
    if type(hop_sequence) is not int or not 1 <= hop_sequence <= MAX_U64:
        raise WireError()
    return struct.pack("!4sBBHIQI", b"ABWS", 1, kind, 0, len(payload), hop_sequence, 0) + payload


def encode_wire_frame(
    frame_type: FrameType | int,
    leg: Leg,
    payload: object,
    hop_sequence: int,
    *,
    admission: object | None = None,
    runtime_epoch: object | None = None,
    trusted_context: bool = True,
) -> bytes:
    """Create an origin frame. A relay must use forward_wire_frame instead."""
    validated = validate_payload(
        frame_type,
        leg,
        payload,
        admission=admission,
        runtime_epoch=runtime_epoch,
        trusted_context=trusted_context,
    )
    try:
        encoded = (
            validated
            if type(validated) is bytes
            else json.dumps(
                validated, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ).encode("utf-8")
        )
        raw = _pack(FrameType(frame_type), encoded, hop_sequence)
        return decode_wire_frame(
            raw,
            leg,
            admission=admission,
            runtime_epoch=runtime_epoch,
            trusted_context=trusted_context,
        ).wire_bytes
    except (UnicodeError, ValueError, TypeError):
        raise WireError() from None


def forward_wire_frame(frame: WireFrame, leg: Leg, hop_sequence: int) -> bytes:
    """Relay only key/opaque profiles, changing only the hop header.

    Metadata ACK/STATE/etc. translations need explicit validation and an authority
    mapping, so this function deliberately cannot translate those profiles.
    """
    if (
        type(frame) is not WireFrame
        or (frame.leg, leg) not in ((_BA, _AR), (_RA, _AB))
        or frame.frame_type not in KEY_TYPES | {FrameType.INPUT, FrameType.OUTPUT}
    ):
        raise WireError()
    raw = _pack(frame.frame_type, frame.payload, hop_sequence)
    return decode_wire_frame(raw, leg).wire_bytes


class WireSession:
    """API-side observed four-leg transcript, with no I/O or admission effects.

    The caller supplies authenticated context and a private connection token. A
    browser or Runtime cannot observe this complete trace and uses the directional
    codec plus its endpoint controller instead. Monotonic times are integer ns.
    ACK-reference mapping, crypto verification, lease/health/rate policy and Audit
    remain the coordinator's responsibility. ``admitted`` means ADMITTED was
    observed, not that browser verification or server queue release is proven.
    Public operations are serialized with a reentrant lock. Pending immutable
    relay bytes are a bounded transcript witness, not a network send queue; ACK
    lifecycle and aggregate metadata/transport queue budgets remain external.
    """

    def __init__(
        self, admission: object, runtime_epoch: object, *, stream_id: object, started_at: int
    ) -> None:
        try:
            self._admission = validate_admission(admission)
            self._context = derive_context(admission, runtime_epoch)
        except WAWContextError:
            raise WireError() from None
        if stream_id is None or type(started_at) is not int or started_at < 0:
            raise WireError()
        self._lock = threading.RLock()
        self._stream_id = stream_id
        self._started = self._last_now = started_at
        self._next = {leg: 1 for leg in Leg}
        self._seen: dict[tuple[Leg, FrameType], WireFrame] = {}
        self._terminal: set[Leg] = set()
        self._must_close: set[Leg] = set()
        self._crypto = {leg: 1 for leg in Leg}
        self._cursor = {_RA: 0, _AB: 0}
        self._retries: set[tuple[Leg, FrameType]] = set()
        self._detach_at: int | None = None
        self._detach: dict[Leg, WireFrame] = {}
        self._failed = self._closed = False
        self._exits: dict[Leg, WireFrame] = {}
        self._pending: dict[FrameType, deque[bytes]] = {
            FrameType.INPUT: deque(),
            FrameType.OUTPUT: deque(),
        }
        self._pending_bytes = {FrameType.INPUT: 0, FrameType.OUTPUT: 0}

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    @property
    def failed(self) -> bool:
        with self._lock:
            return self._failed

    @property
    def admitted(self) -> bool:
        with self._lock:
            return (_AB, FrameType.ADMITTED) in self._seen and not self._failed and not self._closed

    @property
    def committed(self) -> bool:
        with self._lock:
            ack = self._seen.get((_RA, FrameType.ADMISSION_COMMIT_ACK))
            return ack is not None and ack._json is not None and ack._json["result"] == "committed"

    def expected_sequence(self, leg: Leg) -> int:
        with self._lock:
            if type(leg) is not Leg:
                raise WireError()
            return self._next[leg]

    def close(self) -> None:
        """Record external transport destruction; it can never be reopened."""
        with self._lock:
            self._closed = True
            self._seen.clear()
            self._detach.clear()
            for queue in self._pending.values():
                queue.clear()
            self._pending_bytes = {FrameType.INPUT: 0, FrameType.OUTPUT: 0}

    def _has(self, leg: Leg, kind: FrameType) -> bool:
        return (leg, kind) in self._seen

    def _require(self, leg: Leg, kind: FrameType) -> WireFrame:
        frame = self._seen.get((leg, kind))
        if frame is None:
            raise WireError()
        return frame

    def _retry(self, frame: WireFrame, now: int) -> bool:
        key = (frame.leg, frame.frame_type)
        original = self._seen.get(key)
        if frame.frame_type == FrameType.DETACH and frame.leg == _AR:
            original = self._detach.get(_AR)
            if (
                self._detach_at is None
                or now - self._detach_at >= ADMISSION_TIMEOUT_NS
                or _RA in self._detach
            ):
                raise WireError()
        elif frame.frame_type == FrameType.ADMISSION_COMMIT and frame.leg == _AR:
            if self._has(_AB, FrameType.ADMITTED) or self._next[_RA] > 6 or self._next[_AR] > 6:
                raise WireError()
        elif frame.frame_type == FrameType.ADMISSION_COMMIT_ACK and frame.leg == _RA:
            if (_AR, FrameType.ADMISSION_COMMIT) not in self._retries or self._has(
                _AB, FrameType.ADMITTED
            ):
                raise WireError()
        else:
            raise WireError()
        if (
            self._failed
            or key in self._retries
            or original is None
            or original.wire_bytes != frame.wire_bytes
        ):
            raise WireError()
        if frame.frame_type != FrameType.DETACH and now - self._started >= ADMISSION_TIMEOUT_NS:
            raise WireError()
        self._retries.add(key)
        return True

    def _order(self, frame: WireFrame) -> None:
        leg, kind = frame.leg, frame.frame_type
        prerequisites = {
            (_BA, FrameType.KEY_INIT): (_BA, FrameType.WS_HELLO),
            (_AR, FrameType.RUNTIME_HELLO): (_BA, FrameType.KEY_INIT),
            (_AR, FrameType.KEY_INIT): (_AR, FrameType.RUNTIME_HELLO),
            (_RA, FrameType.HELLO_ACK): (_AR, FrameType.KEY_INIT),
            (_RA, FrameType.KEY_ATTEST): (_RA, FrameType.HELLO_ACK),
            (_AB, FrameType.KEY_ATTEST): (_RA, FrameType.KEY_ATTEST),
            (_BA, FrameType.KEY_CONFIRM): (_AB, FrameType.KEY_ATTEST),
            (_AR, FrameType.KEY_CONFIRM): (_BA, FrameType.KEY_CONFIRM),
            (_RA, FrameType.KEY_CONFIRM_ACK): (_AR, FrameType.KEY_CONFIRM),
            (_AB, FrameType.KEY_CONFIRM_ACK): (_RA, FrameType.KEY_CONFIRM_ACK),
            (_AR, FrameType.STREAM_READY): (_AB, FrameType.KEY_CONFIRM_ACK),
            (_RA, FrameType.STREAM_READY_ACK): (_AR, FrameType.STREAM_READY),
            (_AR, FrameType.ADMISSION_COMMIT): (_RA, FrameType.STREAM_READY_ACK),
            (_RA, FrameType.ADMISSION_COMMIT_ACK): (_AR, FrameType.ADMISSION_COMMIT),
            (_AB, FrameType.ADMITTED): (_RA, FrameType.ADMISSION_COMMIT_ACK),
        }
        previous = prerequisites.get((leg, kind))
        if previous is not None:
            self._require(*previous)
        if kind in KEY_TYPES and leg in (_AR, _AB):
            source = _BA if leg == _AR else _RA
            if frame.payload != self._require(source, kind).payload:
                raise WireError()
        record = frame._json
        if record is None:
            return
        if kind == FrameType.RUNTIME_HELLO:
            hello = self._require(_BA, FrameType.WS_HELLO)._json
            if hello is None or any(
                record[key] != hello[key] for key in ("resume_cursor", "previous_runtime_epoch")
            ):
                raise WireError()
        if kind in (FrameType.STREAM_READY_ACK, FrameType.ADMITTED):
            hello = self._require(_RA, FrameType.HELLO_ACK)._json
            if hello is None or record["output_cursor"] != hello["output_cursor"]:
                raise WireError()
        if kind == FrameType.ADMISSION_COMMIT:
            ready = self._require(_RA, FrameType.STREAM_READY_ACK)._json
            if ready is None or record["admission_fence"] != ready["admission_fence"]:
                raise WireError()
        if kind == FrameType.ADMITTED and not self.committed:
            raise WireError()

    def _relay_check(self, frame: WireFrame) -> bool:
        """Validate one bounded FIFO relation before committing trace changes."""
        kind = frame.frame_type
        source = frame.leg == (_BA if kind == FrameType.INPUT else _RA)
        queue = self._pending[kind]
        if source:
            limit = (
                65536
                if kind == FrameType.INPUT or not self._has(_AB, FrameType.ADMITTED)
                else 262144
            )
            if self._pending_bytes[kind] + len(frame.wire_bytes) > limit or (len(queue) >= 256):
                raise WireError()
        elif not queue or queue[0] != frame.payload:
            raise WireError()
        return source

    def _phase(self, frame: WireFrame) -> None:
        leg, kind, seq = frame.leg, frame.frame_type, frame.hop_sequence
        if leg in self._terminal or (leg in self._must_close and kind != FrameType.CLOSE):
            raise WireError()
        if self._failed and kind not in (
            FrameType.STATE,
            FrameType.ERROR,
            FrameType.CLOSE,
            FrameType.EXIT,
        ):
            raise WireError()
        if (
            kind == FrameType.STATE
            and frame._json is not None
            and frame._json["state"] == "RUNNING"
            and (self._failed or not self._has(_AB, FrameType.ADMITTED))
        ):
            raise WireError()
        handshake = _HANDSHAKE[leg]
        if seq <= len(handshake):
            if kind == handshake[seq - 1]:
                if self._failed:
                    raise WireError()
                self._order(frame)
                return
            if kind == FrameType.CLOSE and leg == _AR and self._has(_AR, FrameType.RUNTIME_HELLO):
                return
            if leg == _RA:
                if seq <= 2 and kind == FrameType.ERROR:
                    self._require(_AR, FrameType.KEY_INIT)
                    return
                if seq >= 3 and kind in (FrameType.STATE, FrameType.ERROR, FrameType.CLOSE):
                    if kind == FrameType.CLOSE and leg not in self._must_close:
                        raise WireError()
                    return
            if leg == _AB and kind in (FrameType.ERROR, FrameType.STATE, FrameType.CLOSE):
                if kind == FrameType.ERROR:
                    return
                if not self._has(_AB, FrameType.KEY_ATTEST) or (
                    kind == FrameType.CLOSE and leg not in self._must_close
                ):
                    raise WireError()
                return
            raise WireError()
        if kind == FrameType.EXIT and self._failed:
            original = self._exits.get(_RA)
            if (
                leg != _AB
                or original is None
                or leg in self._exits
                or frame._json != original._json
            ):
                raise WireError()
            return
        if kind in (FrameType.CLOSE, FrameType.ERROR, FrameType.STATE) and self._failed:
            return
        if leg in (_BA, _AB):
            if not self.admitted:
                raise WireError()
        elif not self.committed:
            raise WireError()
        if leg == _AR and kind != FrameType.CLOSE and not self.admitted:
            raise WireError()
        if kind in {FrameType(value) for values in _HANDSHAKE.values() for value in values}:
            raise WireError()
        if self._detach and kind not in (
            FrameType.DETACH,
            FrameType.DETACH_ACK,
            FrameType.CLOSE,
            FrameType.ERROR,
            FrameType.STATE,
            FrameType.ACK,
            FrameType.EXIT,
        ):
            raise WireError()
        self._order(frame)
        if kind == FrameType.DETACH:
            if leg in self._detach or (leg == _AR and _BA not in self._detach):
                raise WireError()
        elif kind == FrameType.DETACH_ACK:
            request_leg = _AR if leg == _RA else _BA
            request = self._detach.get(request_leg)
            if (
                request is None
                or leg in self._detach
                or frame._json is None
                or frame._json["acknowledged_hop_sequence"] != str(request.hop_sequence)
            ):
                raise WireError()
            if leg == _AB:
                response = self._detach.get(_RA)
                if (
                    response is None
                    or response._json is None
                    or any(
                        frame._json[key] != response._json[key]
                        for key in ("result", "cleanup_state", "reason_code")
                    )
                ):
                    raise WireError()

    def accept(self, leg: Leg, raw: object, *, stream_id: object, now: int) -> WireFrame:
        """Observe a complete frame atomically; every invalid event closes this trace.

        Original sequence counters are unchanged on failure. No I/O, writer state,
        decryption state, Audit or process state is changed by this operation.
        """
        with self._lock:
            try:
                if (
                    self._closed
                    or stream_id is not self._stream_id
                    or type(now) is not int
                    or now < self._last_now
                    or type(leg) is not Leg
                ):
                    raise WireError()
                if (
                    not self._has(_AB, FrameType.ADMITTED)
                    and now - self._started >= ADMISSION_TIMEOUT_NS
                ):
                    raise WireError()
                trusted = self._has(_AR, FrameType.RUNTIME_HELLO)
                frame = decode_wire_frame(
                    raw,
                    leg,
                    admission=self._admission,
                    runtime_epoch=self._context["runtime_epoch"],
                    trusted_context=trusted,
                )
                if frame.hop_sequence != self._next[leg] and self._retry(frame, now):
                    self._last_now = now
                    return WireFrame(
                        frame.frame_type,
                        leg,
                        frame.hop_sequence,
                        frame.payload,
                        frame._json,
                        frame.wire_bytes,
                        True,
                    )
                self._phase(frame)
                kind, record = frame.frame_type, frame._json
                if kind in (FrameType.INPUT, FrameType.OUTPUT):
                    source = self._relay_check(frame)
                    envelope = decode_awce(frame.payload)
                    confirmation = self._require(_RA, FrameType.KEY_CONFIRM_ACK)._json
                    if (
                        confirmation is None
                        or envelope.context_id
                        != bytes.fromhex(confirmation["transcript_context_hash"])[:16]
                        or envelope.crypto_sequence != self._crypto[leg]
                    ):
                        raise WireError()
                    if kind == FrameType.OUTPUT and envelope.stream_cursor <= self._cursor[leg]:
                        raise WireError()
                    if source:
                        self._pending[kind].append(frame.payload)
                        self._pending_bytes[kind] += len(frame.wire_bytes)
                    else:
                        released = self._pending[kind].popleft()
                        self._pending_bytes[kind] -= 24 + len(released)
                    self._crypto[leg] += 1
                    if kind == FrameType.OUTPUT:
                        self._cursor[leg] = envelope.stream_cursor
                if kind == FrameType.DETACH:
                    self._detach[leg] = frame
                    if leg == _AR:
                        self._detach_at = now
                elif kind == FrameType.DETACH_ACK:
                    self._detach[leg] = frame
                    self._must_close.add(leg)
                if kind == FrameType.CLOSE:
                    self._terminal.add(leg)
                    self._failed = True
                elif kind == FrameType.EXIT:
                    self._exits[leg] = frame
                    self._must_close.add(leg)
                    self._failed = True
                elif kind in (FrameType.ERROR, FrameType.STATE):
                    if kind == FrameType.ERROR or (
                        record is not None
                        and record["state"] != "RUNNING"
                        and (
                            not self._has(_AB, FrameType.ADMITTED)
                            or record["state"] != "NEEDS_INTERACTION"
                        )
                    ):
                        self._failed = True
                        if (leg == _RA and frame.hop_sequence <= 2) or (
                            leg == _AB and not self._has(_AB, FrameType.KEY_ATTEST)
                        ):
                            self._terminal.add(leg)
                        else:
                            self._must_close.add(leg)
                elif (
                    kind == FrameType.ADMISSION_COMMIT_ACK
                    and record is not None
                    and record["result"] == "rejected"
                ):
                    self._failed = True
                    self._must_close.add(leg)
                if self._failed:
                    for queue in self._pending.values():
                        queue.clear()
                    self._pending_bytes = {FrameType.INPUT: 0, FrameType.OUTPUT: 0}
                if kind in KEY_TYPES or int(kind) in _HANDSHAKE[leg]:
                    self._seen[(leg, kind)] = frame
                self._next[leg] += 1
                self._last_now = now
                if frame.hop_sequence == MAX_U64:
                    self._terminal.add(leg)
                return frame
            except (WireError, KeyError, ValueError, TypeError):
                self.close()
                raise WireError() from None
