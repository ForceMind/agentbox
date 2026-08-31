"""Contract-only WAW handshake state machine.

This module models the metadata ordering required before an external Noise
implementation may run. It deliberately performs no cryptography, key or
nonce handling, socket/WebSocket I/O, PTY access, process operation, or peer
authentication. ``READY_FOR_EXTERNAL_HANDSHAKE`` means only that the frozen
metadata sequence was accepted; it does not mean authenticated, secure, or
established transport.
"""

from __future__ import annotations

import hashlib
import re
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, fields
from enum import StrEnum
from threading import Lock
from typing import Any, TypeVar, cast

import rfc8785

_MAX_U64 = 2**64 - 1
_DECIMAL = re.compile(r"\A(?:0|[1-9][0-9]{0,19})\Z")
_POSITIVE_DECIMAL = re.compile(r"\A[1-9][0-9]{0,19}\Z")
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_WORKSPACE_ID = re.compile(r"\Aaws_[0-9a-f]{32}\Z")
_PROJECT_ID = re.compile(r"\Aprj_[0-9a-f]{32}\Z")
_HOST_ID = re.compile(r"\Awri_[0-9a-f]{32}\Z")
_ATTACHMENT_ID = re.compile(r"\Aatt_[0-9a-f]{32}\Z")
_HANDSHAKE_ID = re.compile(r"\Awsh_[0-9a-f]{32}\Z")


class WAWNoiseContractError(ValueError):
    """A contract-only handshake record or transition is invalid."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class WAWNoiseMessageType(StrEnum):
    WS_HELLO = "WS_HELLO"
    RUNTIME_HELLO = "RUNTIME_HELLO"
    KEY_INIT = "KEY_INIT"
    HELLO_ACK = "HELLO_ACK"
    KEY_ATTEST = "KEY_ATTEST"
    KEY_CONFIRM = "KEY_CONFIRM"
    KEY_CONFIRM_ACK = "KEY_CONFIRM_ACK"
    STREAM_READY = "STREAM_READY"
    STREAM_READY_ACK = "STREAM_READY_ACK"
    ADMISSION_COMMIT = "ADMISSION_COMMIT"
    ADMISSION_COMMIT_ACK = "ADMISSION_COMMIT_ACK"
    ADMITTED = "ADMITTED"


class WAWNoiseRole(StrEnum):
    CLIENT = "CLIENT"
    RUNTIME = "RUNTIME"


class WAWNoiseState(StrEnum):
    INIT = "INIT"
    CLIENT_HELLO_ACCEPTED = "CLIENT_HELLO_ACCEPTED"
    SERVER_HELLO_ACCEPTED = "SERVER_HELLO_ACCEPTED"
    KEY_INIT_ACCEPTED = "KEY_INIT_ACCEPTED"
    HELLO_ACK_ACCEPTED = "HELLO_ACK_ACCEPTED"
    KEY_ATTEST_ACCEPTED = "KEY_ATTEST_ACCEPTED"
    KEY_CONFIRM_ACCEPTED = "KEY_CONFIRM_ACCEPTED"
    KEY_CONFIRM_ACK_ACCEPTED = "KEY_CONFIRM_ACK_ACCEPTED"
    STREAM_READY_ACCEPTED = "STREAM_READY_ACCEPTED"
    STREAM_READY_ACK_ACCEPTED = "STREAM_READY_ACK_ACCEPTED"
    ADMISSION_COMMIT_ACCEPTED = "ADMISSION_COMMIT_ACCEPTED"
    ADMISSION_COMMIT_ACK_ACCEPTED = "ADMISSION_COMMIT_ACK_ACCEPTED"
    READY_FOR_EXTERNAL_HANDSHAKE = "READY_FOR_EXTERNAL_HANDSHAKE"
    REJECTED = "REJECTED"


class WAWNoiseReplayFence:
    """Bounded in-memory reservation set; it performs no I/O or authentication."""

    def __init__(self, *, capacity: int = 64) -> None:
        if type(capacity) is not int or not 1 <= capacity <= 1024:
            raise ValueError("capacity must be an integer in 1..1024")
        self._capacity = capacity
        self._lock = Lock()
        self._reserved: set[tuple[str, str]] = set()
        self._order: deque[tuple[str, str]] = deque()

    def reserve(self, handshake_id: str, tuple_value: WAWNoiseTuple) -> None:
        _text(handshake_id, "handshake_id", _HANDSHAKE_ID)
        _validate_tuple(tuple_value)
        key = (handshake_id, tuple_digest(tuple_value))
        with self._lock:
            if key in self._reserved or any(item[0] == handshake_id for item in self._reserved):
                raise WAWNoiseContractError(
                    "HANDSHAKE_REPLAY", "handshake identity was already reserved"
                )
            if len(self._order) >= self._capacity:
                raise WAWNoiseContractError(
                    "HANDSHAKE_REPLAY_WINDOW_EXHAUSTED",
                    "bounded handshake replay window is exhausted",
                )
            self._order.append(key)
            self._reserved.add(key)


@dataclass(frozen=True)
class WAWNoiseTuple:
    """Outer lifecycle tuple injected by an already-authorized caller."""

    workspace_id: str
    project_id: str
    agent_type: str
    generation: int
    runtime_epoch: str
    runtime_host_installation_id: str
    runtime_host_installation_revision: str
    binding_revision: str
    binding_digest: str
    api_authority_epoch: str
    auth_epoch: str
    attachment_id: str


@dataclass(frozen=True)
class WAWNoiseMessage:
    """Metadata-only message; it has no key, nonce, ciphertext or payload."""

    protocol_version: int
    message_type: WAWNoiseMessageType
    role: WAWNoiseRole
    handshake_id: str
    sequence: int
    tuple: WAWNoiseTuple
    transcript_digest: str


@dataclass(frozen=True)
class WAWNoiseSession:
    """Immutable contract state for one synthetic handshake attempt."""

    handshake_id: str
    tuple: WAWNoiseTuple
    state: WAWNoiseState
    next_sequence: int
    transcript_digest: str


_T = TypeVar("_T")


def _text(value: object, field: str, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value or len(value) > 512 or "\x00" in value:
        raise WAWNoiseContractError("PROTOCOL_INVALID", f"invalid {field}")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise WAWNoiseContractError("PROTOCOL_INVALID", f"invalid {field}")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise WAWNoiseContractError("PROTOCOL_INVALID", f"invalid {field}")
    return value


def _decimal(value: object, field: str, *, positive: bool = False) -> str:
    pattern = _POSITIVE_DECIMAL if positive else _DECIMAL
    value = _text(value, field, pattern)
    if int(value) > _MAX_U64:
        raise WAWNoiseContractError("PROTOCOL_INVALID", f"invalid {field}")
    return value


def _digest(value: object, field: str) -> str:
    value = _text(value, field, _DIGEST)
    if value == "0" * 64:
        raise WAWNoiseContractError("PROTOCOL_INVALID", f"invalid {field}")
    return value


def _validate_tuple(value: WAWNoiseTuple) -> None:
    if type(value) is not WAWNoiseTuple:
        raise WAWNoiseContractError("PROTOCOL_INVALID", "tuple must be an exact typed record")
    _text(value.workspace_id, "workspace_id", _WORKSPACE_ID)
    _text(value.project_id, "project_id", _PROJECT_ID)
    if value.agent_type != "claude":
        raise WAWNoiseContractError("WAW_AGENT_UNSUPPORTED", "contract-only WAW-1 accepts Claude")
    if type(value.generation) is not int or not 1 <= value.generation <= _MAX_U64:
        raise WAWNoiseContractError("PROTOCOL_INVALID", "invalid generation")
    _decimal(value.runtime_epoch, "runtime_epoch", positive=True)
    _text(value.runtime_host_installation_id, "runtime_host_installation_id", _HOST_ID)
    _decimal(
        value.runtime_host_installation_revision,
        "runtime_host_installation_revision",
        positive=True,
    )
    _decimal(value.binding_revision, "binding_revision", positive=True)
    _digest(value.binding_digest, "binding_digest")
    _decimal(value.api_authority_epoch, "api_authority_epoch", positive=True)
    _decimal(value.auth_epoch, "auth_epoch", positive=True)
    _text(value.attachment_id, "attachment_id", _ATTACHMENT_ID)


def _closed(value: object, cls: type[_T]) -> _T:
    if type(value) is cls:
        return value
    if not isinstance(value, Mapping):
        raise WAWNoiseContractError("PROTOCOL_INVALID", f"{cls.__name__} must be a closed mapping")
    expected = {item.name for item in fields(cast(Any, cls))}
    if set(value) != expected:
        raise WAWNoiseContractError("PROTOCOL_INVALID", f"{cls.__name__} fields are not closed")
    data = dict(value)
    try:
        if cls is WAWNoiseTuple:
            return cls(**data)
        data["message_type"] = WAWNoiseMessageType(data["message_type"])
        data["role"] = WAWNoiseRole(data["role"])
        data["tuple"] = _closed(data["tuple"], WAWNoiseTuple)
        return cls(**data)
    except (TypeError, ValueError, KeyError) as exc:
        raise WAWNoiseContractError(
            "PROTOCOL_INVALID", f"{cls.__name__} fields are malformed"
        ) from exc


def _tuple_payload(value: WAWNoiseTuple) -> dict[str, Any]:
    return {
        "workspace_id": value.workspace_id,
        "project_id": value.project_id,
        "agent_type": value.agent_type,
        "generation": value.generation,
        "runtime_epoch": value.runtime_epoch,
        "runtime_host_installation_id": value.runtime_host_installation_id,
        "runtime_host_installation_revision": value.runtime_host_installation_revision,
        "binding_revision": value.binding_revision,
        "binding_digest": value.binding_digest,
        "api_authority_epoch": value.api_authority_epoch,
        "auth_epoch": value.auth_epoch,
        "attachment_id": value.attachment_id,
    }


def _message_payload(value: WAWNoiseMessage) -> dict[str, Any]:
    return {
        "protocol_version": value.protocol_version,
        "message_type": value.message_type.value,
        "role": value.role.value,
        "handshake_id": value.handshake_id,
        "sequence": value.sequence,
        "tuple": _tuple_payload(value.tuple),
    }


def _digest_bytes(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(rfc8785.dumps(dict(value))).hexdigest()


def tuple_digest(value: WAWNoiseTuple | Mapping[str, Any]) -> str:
    """Return a structural SHA-256 digest, not a MAC or authentication proof."""

    bound = _closed(value, WAWNoiseTuple)
    _validate_tuple(bound)
    return _digest_bytes(_tuple_payload(bound))


def encode_message(value: WAWNoiseMessage | Mapping[str, Any]) -> bytes:
    """Encode one canonical metadata message; no terminal payload is accepted."""

    message = _closed(value, WAWNoiseMessage)
    _validate_message(message)
    return rfc8785.dumps(
        {**_message_payload(message), "transcript_digest": message.transcript_digest}
    )


def decode_message(value: Mapping[str, Any]) -> WAWNoiseMessage:
    """Decode one already-parsed closed mapping without accepting extensions."""

    message = _closed(value, WAWNoiseMessage)
    _validate_message(message)
    return message


def _validate_message(message: WAWNoiseMessage) -> None:
    if type(message.protocol_version) is not int or message.protocol_version != 1:
        raise WAWNoiseContractError("PROTOCOL_INVALID", "unsupported protocol_version")
    _text(message.handshake_id, "handshake_id", _HANDSHAKE_ID)
    if type(message.sequence) is not int or not 0 <= message.sequence <= _MAX_U64:
        raise WAWNoiseContractError("PROTOCOL_INVALID", "invalid sequence")
    _validate_tuple(message.tuple)
    _digest(message.transcript_digest, "transcript_digest")


_TRANSITIONS: dict[WAWNoiseState, tuple[WAWNoiseMessageType, WAWNoiseRole, WAWNoiseState]] = {
    WAWNoiseState.INIT: (
        WAWNoiseMessageType.WS_HELLO,
        WAWNoiseRole.CLIENT,
        WAWNoiseState.CLIENT_HELLO_ACCEPTED,
    ),
    WAWNoiseState.CLIENT_HELLO_ACCEPTED: (
        WAWNoiseMessageType.RUNTIME_HELLO,
        WAWNoiseRole.RUNTIME,
        WAWNoiseState.SERVER_HELLO_ACCEPTED,
    ),
    WAWNoiseState.SERVER_HELLO_ACCEPTED: (
        WAWNoiseMessageType.KEY_INIT,
        WAWNoiseRole.CLIENT,
        WAWNoiseState.KEY_INIT_ACCEPTED,
    ),
    WAWNoiseState.KEY_INIT_ACCEPTED: (
        WAWNoiseMessageType.HELLO_ACK,
        WAWNoiseRole.RUNTIME,
        WAWNoiseState.HELLO_ACK_ACCEPTED,
    ),
    WAWNoiseState.HELLO_ACK_ACCEPTED: (
        WAWNoiseMessageType.KEY_ATTEST,
        WAWNoiseRole.RUNTIME,
        WAWNoiseState.KEY_ATTEST_ACCEPTED,
    ),
    WAWNoiseState.KEY_ATTEST_ACCEPTED: (
        WAWNoiseMessageType.KEY_CONFIRM,
        WAWNoiseRole.CLIENT,
        WAWNoiseState.KEY_CONFIRM_ACCEPTED,
    ),
    WAWNoiseState.KEY_CONFIRM_ACCEPTED: (
        WAWNoiseMessageType.KEY_CONFIRM_ACK,
        WAWNoiseRole.RUNTIME,
        WAWNoiseState.KEY_CONFIRM_ACK_ACCEPTED,
    ),
    WAWNoiseState.KEY_CONFIRM_ACK_ACCEPTED: (
        WAWNoiseMessageType.STREAM_READY,
        WAWNoiseRole.CLIENT,
        WAWNoiseState.STREAM_READY_ACCEPTED,
    ),
    WAWNoiseState.STREAM_READY_ACCEPTED: (
        WAWNoiseMessageType.STREAM_READY_ACK,
        WAWNoiseRole.RUNTIME,
        WAWNoiseState.STREAM_READY_ACK_ACCEPTED,
    ),
    WAWNoiseState.STREAM_READY_ACK_ACCEPTED: (
        WAWNoiseMessageType.ADMISSION_COMMIT,
        WAWNoiseRole.CLIENT,
        WAWNoiseState.ADMISSION_COMMIT_ACCEPTED,
    ),
    WAWNoiseState.ADMISSION_COMMIT_ACCEPTED: (
        WAWNoiseMessageType.ADMISSION_COMMIT_ACK,
        WAWNoiseRole.RUNTIME,
        WAWNoiseState.ADMISSION_COMMIT_ACK_ACCEPTED,
    ),
    WAWNoiseState.ADMISSION_COMMIT_ACK_ACCEPTED: (
        WAWNoiseMessageType.ADMITTED,
        WAWNoiseRole.RUNTIME,
        WAWNoiseState.READY_FOR_EXTERNAL_HANDSHAKE,
    ),
}


def start_session(
    tuple_value: WAWNoiseTuple | Mapping[str, Any],
    handshake_id: str,
    *,
    replay_fence: WAWNoiseReplayFence,
) -> WAWNoiseSession:
    """Create immutable INIT state for one bounded synthetic handshake."""

    bound_tuple = _closed(tuple_value, WAWNoiseTuple)
    _validate_tuple(bound_tuple)
    _text(handshake_id, "handshake_id", _HANDSHAKE_ID)
    if type(replay_fence) is not WAWNoiseReplayFence:
        raise WAWNoiseContractError("PROTOCOL_INVALID", "replay_fence is required")
    replay_fence.reserve(handshake_id, bound_tuple)
    return WAWNoiseSession(
        handshake_id=handshake_id,
        tuple=bound_tuple,
        state=WAWNoiseState.INIT,
        next_sequence=0,
        transcript_digest=tuple_digest(bound_tuple),
    )


def accept_message(
    session: WAWNoiseSession, message: WAWNoiseMessage | Mapping[str, Any]
) -> WAWNoiseSession:
    """Purely accept one exact next metadata message or raise fail-closed."""

    _validate_session(session)
    if session.state in {WAWNoiseState.REJECTED, WAWNoiseState.READY_FOR_EXTERNAL_HANDSHAKE}:
        raise WAWNoiseContractError("HANDSHAKE_TERMINAL", "handshake state is terminal")
    if isinstance(message, Mapping):
        bound = decode_message(message)
    elif type(message) is WAWNoiseMessage:
        bound = message
        _validate_message(bound)
    else:
        raise WAWNoiseContractError("PROTOCOL_INVALID", "message must be an exact typed record")
    expected_type, expected_role, next_state = _TRANSITIONS[session.state]
    if bound.handshake_id != session.handshake_id:
        raise WAWNoiseContractError("HANDSHAKE_ID_MISMATCH", "handshake identity changed")
    if bound.tuple != session.tuple:
        raise WAWNoiseContractError("WAW_TUPLE_MISMATCH", "lifecycle tuple changed")
    if bound.message_type is not expected_type or bound.role is not expected_role:
        raise WAWNoiseContractError(
            "HANDSHAKE_ORDER_INVALID", "message is not the exact next role/type"
        )
    if bound.sequence != session.next_sequence:
        raise WAWNoiseContractError(
            "HANDSHAKE_SEQUENCE_INVALID", "message sequence is not contiguous"
        )
    if bound.transcript_digest != session.transcript_digest:
        raise WAWNoiseContractError("TRANSCRIPT_MISMATCH", "transcript digest is stale or replayed")
    if session.next_sequence == _MAX_U64:
        raise WAWNoiseContractError(
            "HANDSHAKE_SEQUENCE_EXHAUSTED", "handshake sequence is exhausted"
        )
    next_digest = _digest_bytes(
        {"previous": session.transcript_digest, "message": _message_payload(bound)}
    )
    return WAWNoiseSession(
        handshake_id=session.handshake_id,
        tuple=session.tuple,
        state=next_state,
        next_sequence=session.next_sequence + 1,
        transcript_digest=next_digest,
    )


def _validate_session(session: object) -> None:
    if type(session) is not WAWNoiseSession:
        raise WAWNoiseContractError("PROTOCOL_INVALID", "session must be an exact typed record")
    value = session
    if not isinstance(value.state, WAWNoiseState):
        raise WAWNoiseContractError("PROTOCOL_INVALID", "session state is invalid")
    if type(value.next_sequence) is not int or not 0 <= value.next_sequence <= _MAX_U64:
        raise WAWNoiseContractError("PROTOCOL_INVALID", "session sequence is invalid")
    _validate_tuple(value.tuple)
    _text(value.handshake_id, "handshake_id", _HANDSHAKE_ID)
    _digest(value.transcript_digest, "transcript_digest")


__all__ = [
    "WAWNoiseContractError",
    "WAWNoiseReplayFence",
    "WAWNoiseMessageType",
    "WAWNoiseRole",
    "WAWNoiseState",
    "WAWNoiseTuple",
    "WAWNoiseMessage",
    "WAWNoiseSession",
    "accept_message",
    "decode_message",
    "encode_message",
    "start_session",
    "tuple_digest",
]
