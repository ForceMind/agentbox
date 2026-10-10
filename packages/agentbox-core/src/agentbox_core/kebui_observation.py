"""Isolated K2 candidate validators for already-decoded, noncontent metadata.

These functions only check shape and copy metadata into immutable values. They
do not authenticate a source, authorize an action, or provide a JSON decoder.
No production adapter, transport, persistence, or content processing is wired.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, cast

from agentbox_core.waw import (
    AgentType,
    WAWDomainError,
    validate_binding_digest,
    validate_positive_u64,
    validate_project_id,
    validate_runtime_host_installation_id,
)

_COUNTER_FIELDS = frozenset(
    {
        "auth_epoch",
        "project_revision",
        "binding_revision",
        "host_revision",
        "runtime_epoch",
        "api_authority_epoch",
        "conversation_revision",
        "generation",
    }
)
_SCOPE_FIELDS = _COUNTER_FIELDS | {
    "owner_scope",
    "project_id",
    "binding_digest",
    "host_id",
    "agent_type",
    "execution_kind",
    "conversation_id",
    "turn_id",
}
_OBSERVATION_FIELDS = frozenset({"scope", "revision", "status"})
_POSITIVE_DECIMAL = re.compile(r"\A[1-9][0-9]{0,19}\Z")
_CONVERSATION_ID = re.compile(r"\Akcv_[0-9a-f]{32}\Z")
_TURN_ID = re.compile(r"\Aktr_[0-9a-f]{32}\Z")
_INVALID_SCOPE = "invalid observation scope"
_INVALID_OBSERVATION = "invalid observation"


class KebuiObservationError(ValueError):
    """A metadata candidate failed closed without including its input in errors."""


class ObservationStatus(StrEnum):
    """Proposed metadata labels; none establish a real adapter capability."""

    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_INPUT = "awaiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    UNKNOWN = "unknown"


_STATUSES = frozenset(status.value for status in ObservationStatus)


@dataclass(frozen=True, slots=True)
class ConversationScope:
    """Copied metadata identity, obtained through :func:`parse_scope`."""

    owner_scope: str
    auth_epoch: str
    project_id: str
    project_revision: str
    binding_revision: str
    binding_digest: str
    host_id: str
    host_revision: str
    runtime_epoch: str
    api_authority_epoch: str
    agent_type: AgentType
    execution_kind: Literal["structured-candidate"]
    conversation_id: str
    conversation_revision: str
    generation: str
    turn_id: str


@dataclass(frozen=True, slots=True)
class ConversationObservation:
    """Copied observation, obtained through :func:`parse_observation`."""

    scope: ConversationScope
    revision: str
    status: ObservationStatus


def _plain_record(value: object, fields: frozenset[str], error: str) -> dict[str, object]:
    # Reject subclasses and wrong counts before iteration, conversion or copying.
    if type(value) is not dict or len(value) != len(fields):
        raise KebuiObservationError(error)
    if any(type(key) is not str for key in value) or value.keys() != fields:
        raise KebuiObservationError(error)
    return cast(dict[str, object], value.copy())


def _positive_u64(value: object, error: str) -> str:
    # Bound work before int conversion, and reject booleans, Unicode digits,
    # exponents, whitespace, signs and leading zeros instead of coercing them.
    if type(value) is not str or not 1 <= len(value) <= 20:
        raise KebuiObservationError(error)
    if not _POSITIVE_DECIMAL.fullmatch(value):
        raise KebuiObservationError(error)
    try:
        validate_positive_u64(int(value))
    except WAWDomainError:
        raise KebuiObservationError(error) from None
    return value


def parse_scope(value: object) -> ConversationScope:
    """Validate exactly the frozen 16-field scope, with no caller-owned aliases."""

    record = _plain_record(value, _SCOPE_FIELDS, _INVALID_SCOPE)
    if any(type(item) is not str for item in record.values()):
        raise KebuiObservationError(_INVALID_SCOPE)
    strings = cast(dict[str, str], record)
    for field in _COUNTER_FIELDS:
        _positive_u64(strings[field], _INVALID_SCOPE)
    try:
        validate_binding_digest(strings["owner_scope"])
        validate_project_id(strings["project_id"])
        validate_binding_digest(strings["binding_digest"])
        validate_runtime_host_installation_id(strings["host_id"])
    except WAWDomainError:
        raise KebuiObservationError(_INVALID_SCOPE) from None
    if (
        strings["agent_type"] not in ("claude", "codex")
        or strings["execution_kind"] != "structured-candidate"
        or not _CONVERSATION_ID.fullmatch(strings["conversation_id"])
        or not _TURN_ID.fullmatch(strings["turn_id"])
    ):
        raise KebuiObservationError(_INVALID_SCOPE)
    return ConversationScope(
        owner_scope=strings["owner_scope"],
        auth_epoch=strings["auth_epoch"],
        project_id=strings["project_id"],
        project_revision=strings["project_revision"],
        binding_revision=strings["binding_revision"],
        binding_digest=strings["binding_digest"],
        host_id=strings["host_id"],
        host_revision=strings["host_revision"],
        runtime_epoch=strings["runtime_epoch"],
        api_authority_epoch=strings["api_authority_epoch"],
        agent_type=AgentType(strings["agent_type"]),
        execution_kind="structured-candidate",
        conversation_id=strings["conversation_id"],
        conversation_revision=strings["conversation_revision"],
        generation=strings["generation"],
        turn_id=strings["turn_id"],
    )


def parse_observation(value: object) -> ConversationObservation:
    """Validate one metadata observation; never interpret content or execute it."""

    record = _plain_record(value, _OBSERVATION_FIELDS, _INVALID_OBSERVATION)
    scope = parse_scope(record["scope"])
    revision = _positive_u64(record["revision"], _INVALID_OBSERVATION)
    status = record["status"]
    if type(status) is not str or not 1 <= len(status) <= 17 or status not in _STATUSES:
        raise KebuiObservationError(_INVALID_OBSERVATION)
    return ConversationObservation(scope=scope, revision=revision, status=ObservationStatus(status))


__all__ = [
    "ConversationObservation",
    "ConversationScope",
    "KebuiObservationError",
    "ObservationStatus",
    "parse_observation",
    "parse_scope",
]
