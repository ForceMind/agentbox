"""Pure reducer for WAW cgroup cleanup recovery decisions.

The reducer consumes only typed, already-observed metadata. It never opens a
cgroup path, writes an attestation store, invokes an executor, or exposes a
control-plane/API operation. A caller must perform host read-back and durable
compare-and-ack separately after receiving :attr:`ACK_EMPTY`.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from enum import StrEnum
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
_AGENT_TYPES = frozenset({"claude", "codex"})
_CLEANUP_STATES = frozenset({"LIVE", "FENCED", "EMPTY_DURABLE"})


class WAWCleanupRecoveryError(ValueError):
    """The reducer input is malformed or not a closed typed record."""


class CleanupRecoveryDecision(StrEnum):
    """Safe outcome of one pure cleanup recovery reduction."""

    KEEP_QUARANTINED = "KEEP_QUARANTINED"
    ACK_EMPTY = "ACK_EMPTY"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class CleanupEvidenceSource(StrEnum):
    """Non-production provenance labels accepted by this pure contract."""

    SYNTHETIC = "SYNTHETIC"
    FAKE_RUNTIME = "FAKE_RUNTIME"


@dataclass(frozen=True)
class WAWCleanupActiveIdentity:
    workspace_id: str
    project_id: str
    agent_type: str
    generation: int
    runtime_epoch: str
    binding_revision: str
    binding_digest: str
    runtime_host_installation_id: str
    runtime_host_installation_revision: str


@dataclass(frozen=True)
class WAWCleanupDurableSnapshot:
    workspace_id: str
    project_id: str
    agent_type: str
    generation: int
    runtime_epoch: str
    binding_revision: str
    binding_digest: str
    runtime_host_installation_id: str
    runtime_host_installation_revision: str
    cgroup_identity_digest: str
    attestation_digest: str
    cleanup_state: str
    last_populated: str
    attachment_leaves: tuple[str, ...]
    latest_generation: int
    unresolved_generations: tuple[int, ...]


@dataclass(frozen=True)
class WAWCleanupEvidence:
    workspace_id: str
    project_id: str
    agent_type: str
    generation: int
    runtime_epoch: str
    binding_revision: str
    binding_digest: str
    runtime_host_installation_id: str
    runtime_host_installation_revision: str
    cgroup_identity_digest: str
    attestation_digest: str
    cleanup_state: str
    last_populated: str
    attachment_leaves: tuple[str, ...]
    evidence_source: CleanupEvidenceSource


_T = TypeVar("_T")


def _closed(value: object, cls: type[_T]) -> _T:
    if type(value) is cls:
        return value
    if not isinstance(value, Mapping):
        raise WAWCleanupRecoveryError(f"{cls.__name__} must be a typed record")
    expected = {field.name for field in fields(cast(Any, cls))}
    if set(value) != expected:
        raise WAWCleanupRecoveryError(f"{cls.__name__} fields are not closed")
    data = dict(value)
    if cls in (WAWCleanupDurableSnapshot, WAWCleanupEvidence):
        leaves = data["attachment_leaves"]
        if isinstance(leaves, list):
            data["attachment_leaves"] = tuple(leaves)
        if cls is WAWCleanupDurableSnapshot:
            unresolved = data["unresolved_generations"]
            if isinstance(unresolved, list):
                data["unresolved_generations"] = tuple(unresolved)
        elif isinstance(data["evidence_source"], str):
            try:
                data["evidence_source"] = CleanupEvidenceSource(data["evidence_source"])
            except ValueError as exc:
                raise WAWCleanupRecoveryError("invalid evidence_source") from exc
    try:
        return cls(**data)
    except (TypeError, ValueError) as exc:
        raise WAWCleanupRecoveryError(f"{cls.__name__} fields are malformed") from exc


def _text(value: object, field: str, *, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value or len(value) > 512 or "\x00" in value:
        raise WAWCleanupRecoveryError(f"invalid {field}")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise WAWCleanupRecoveryError(f"invalid {field}")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise WAWCleanupRecoveryError(f"invalid {field}")
    return value


def _decimal(value: object, field: str, *, positive: bool = False) -> str:
    value = _text(value, field, pattern=_POSITIVE_DECIMAL if positive else _DECIMAL)
    if int(value) > _MAX_U64:
        raise WAWCleanupRecoveryError(f"invalid {field}")
    return value


def _generation(value: object) -> int:
    if type(value) is not int or not 1 <= value <= _MAX_U64:
        raise WAWCleanupRecoveryError("invalid generation")
    return value


def _digest(value: object, field: str) -> str:
    value = _text(value, field, pattern=_DIGEST)
    if value == "0" * 64:
        raise WAWCleanupRecoveryError(f"invalid {field}")
    return value


def _identity_fields(
    value: WAWCleanupActiveIdentity | WAWCleanupDurableSnapshot | WAWCleanupEvidence,
) -> None:
    _text(value.workspace_id, "workspace_id", pattern=_WORKSPACE_ID)
    _text(value.project_id, "project_id", pattern=_PROJECT_ID)
    if value.agent_type not in _AGENT_TYPES:
        raise WAWCleanupRecoveryError("invalid agent_type")
    _generation(value.generation)
    _decimal(value.runtime_epoch, "runtime_epoch", positive=True)
    _decimal(value.binding_revision, "binding_revision", positive=True)
    _digest(value.binding_digest, "binding_digest")
    _text(value.runtime_host_installation_id, "runtime_host_installation_id", pattern=_HOST_ID)
    _decimal(
        value.runtime_host_installation_revision,
        "runtime_host_installation_revision",
        positive=True,
    )


def _record_fields(value: WAWCleanupDurableSnapshot | WAWCleanupEvidence) -> None:
    _identity_fields(value)
    _digest(value.attestation_digest, "attestation_digest")
    if value.cleanup_state not in _CLEANUP_STATES:
        raise WAWCleanupRecoveryError("invalid cleanup_state")
    if value.last_populated not in {"0", "1"}:
        raise WAWCleanupRecoveryError("invalid last_populated")
    _digest(value.cgroup_identity_digest, "cgroup_identity_digest")
    if value.cleanup_state == "EMPTY_DURABLE" and (
        value.last_populated != "0" or value.attachment_leaves
    ):
        raise WAWCleanupRecoveryError("EMPTY_DURABLE requires populated=0 and no attachment leaves")
    if value.cleanup_state == "LIVE" and value.last_populated != "1":
        raise WAWCleanupRecoveryError("LIVE requires populated=1")
    if not isinstance(value.attachment_leaves, tuple):
        raise WAWCleanupRecoveryError("attachment_leaves must be a tuple")
    if len(value.attachment_leaves) > 1:
        raise WAWCleanupRecoveryError("too many attachment leaves")
    seen: set[str] = set()
    for leaf in value.attachment_leaves:
        _text(leaf, "attachment leaf", pattern=_ATTACHMENT_ID)
        if leaf in seen:
            raise WAWCleanupRecoveryError("duplicate attachment leaf")
        seen.add(leaf)
    if isinstance(value, WAWCleanupEvidence) and value.evidence_source not in {
        CleanupEvidenceSource.SYNTHETIC,
        CleanupEvidenceSource.FAKE_RUNTIME,
    }:
        raise WAWCleanupRecoveryError("invalid evidence_source")


def _snapshot(value: WAWCleanupDurableSnapshot) -> None:
    _record_fields(value)
    _generation(value.latest_generation)
    if not isinstance(value.unresolved_generations, tuple) or not value.unresolved_generations:
        raise WAWCleanupRecoveryError("unresolved_generations must be non-empty")
    previous = 0
    for generation in value.unresolved_generations:
        _generation(generation)
        if generation <= previous:
            raise WAWCleanupRecoveryError("unresolved_generations must be sorted and unique")
        previous = generation
    if value.generation not in value.unresolved_generations:
        raise WAWCleanupRecoveryError("snapshot generation is not unresolved")
    if value.latest_generation < value.unresolved_generations[-1]:
        raise WAWCleanupRecoveryError("latest_generation is below unresolved generation")
    if value.latest_generation != value.unresolved_generations[-1]:
        raise WAWCleanupRecoveryError("latest_generation is not latest unresolved generation")


def _canonical_record_payload(
    value: WAWCleanupDurableSnapshot | WAWCleanupEvidence,
) -> dict[str, Any]:
    return {
        "workspace_id": value.workspace_id,
        "project_id": value.project_id,
        "agent_type": value.agent_type,
        "generation": value.generation,
        "runtime_epoch": value.runtime_epoch,
        "binding_revision": value.binding_revision,
        "binding_digest": value.binding_digest,
        "runtime_host_installation_id": value.runtime_host_installation_id,
        "runtime_host_installation_revision": value.runtime_host_installation_revision,
        "cgroup_identity_digest": value.cgroup_identity_digest,
        "cleanup_state": value.cleanup_state,
        "last_populated": value.last_populated,
        "attachment_leaves": list(value.attachment_leaves),
        "evidence_source": (
            value.evidence_source.value if isinstance(value, WAWCleanupEvidence) else None
        ),
        "latest_generation": (
            value.latest_generation if isinstance(value, WAWCleanupDurableSnapshot) else None
        ),
        "unresolved_generations": (
            list(value.unresolved_generations)
            if isinstance(value, WAWCleanupDurableSnapshot)
            else None
        ),
    }


def cleanup_attestation_digest(value: WAWCleanupDurableSnapshot | WAWCleanupEvidence) -> str:
    """Return SHA-256 of canonical record fields, excluding the digest itself."""

    try:
        raw = rfc8785.dumps(_canonical_record_payload(value))
    except (TypeError, ValueError) as exc:
        raise WAWCleanupRecoveryError("cannot canonicalize attestation record") from exc
    return hashlib.sha256(raw).hexdigest()


def _same_identity(
    active: WAWCleanupActiveIdentity,
    value: WAWCleanupDurableSnapshot | WAWCleanupEvidence,
) -> bool:
    return (
        active.workspace_id == value.workspace_id
        and active.project_id == value.project_id
        and active.agent_type == value.agent_type
        and active.generation == value.generation
        and active.runtime_epoch == value.runtime_epoch
        and active.binding_revision == value.binding_revision
        and active.binding_digest == value.binding_digest
        and active.runtime_host_installation_id == value.runtime_host_installation_id
        and active.runtime_host_installation_revision == value.runtime_host_installation_revision
    )


def reduce_cleanup_recovery(
    active_identity: WAWCleanupActiveIdentity | Mapping[str, Any],
    durable_snapshot: WAWCleanupDurableSnapshot | Mapping[str, Any] | None,
    evidence: WAWCleanupEvidence | Mapping[str, Any],
) -> CleanupRecoveryDecision:
    """Reduce observed cleanup metadata to one fail-closed decision.

    ``ACK_EMPTY`` is returned only for an exact identity tuple, a valid digest
    for each canonical record, and evidence for the latest unresolved
    generation. The caller must still perform host-authenticated read-back and
    locked durable acknowledgment; this reducer cannot clear quarantine.
    """

    active = _closed(active_identity, WAWCleanupActiveIdentity)
    observed = _closed(evidence, WAWCleanupEvidence)
    _identity_fields(active)
    _record_fields(observed)
    if cleanup_attestation_digest(observed) != observed.attestation_digest:
        return CleanupRecoveryDecision.RECONCILIATION_REQUIRED
    if durable_snapshot is None:
        return CleanupRecoveryDecision.RECONCILIATION_REQUIRED
    snapshot = _closed(durable_snapshot, WAWCleanupDurableSnapshot)
    _snapshot(snapshot)
    if cleanup_attestation_digest(snapshot) != snapshot.attestation_digest:
        return CleanupRecoveryDecision.RECONCILIATION_REQUIRED
    if snapshot.cleanup_state == "EMPTY_DURABLE":
        return CleanupRecoveryDecision.RECONCILIATION_REQUIRED
    if not _same_identity(active, snapshot) or not _same_identity(active, observed):
        return CleanupRecoveryDecision.RECONCILIATION_REQUIRED
    if snapshot.cgroup_identity_digest != observed.cgroup_identity_digest:
        return CleanupRecoveryDecision.RECONCILIATION_REQUIRED
    if snapshot.generation != snapshot.unresolved_generations[-1]:
        return CleanupRecoveryDecision.RECONCILIATION_REQUIRED
    if (
        observed.cleanup_state != snapshot.cleanup_state
        and observed.cleanup_state != "EMPTY_DURABLE"
    ):
        return CleanupRecoveryDecision.RECONCILIATION_REQUIRED
    if observed.cleanup_state == "EMPTY_DURABLE":
        if observed.last_populated != "0" or observed.attachment_leaves:
            return CleanupRecoveryDecision.RECONCILIATION_REQUIRED
        return CleanupRecoveryDecision.ACK_EMPTY
    return CleanupRecoveryDecision.KEEP_QUARANTINED


__all__ = [
    "CleanupRecoveryDecision",
    "CleanupEvidenceSource",
    "WAWCleanupActiveIdentity",
    "WAWCleanupDurableSnapshot",
    "WAWCleanupEvidence",
    "WAWCleanupRecoveryError",
    "cleanup_attestation_digest",
    "reduce_cleanup_recovery",
]
