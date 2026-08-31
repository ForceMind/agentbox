"""Canonical, non-secret dynamic cgroup attestation records.

This module validates only an immutable metadata record.  It never reads
cgroupfs, resolves a pathname, launches a process, or changes Runtime state.
The real host read-back and durable Runtime-only persistence remain separate
host-gated operations.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

import rfc8785

_MAX_BYTES = 64 * 1024
_MAX_STRING = 512
_MAX_U64 = 2**64 - 1
_DECIMAL = re.compile(r"\A(?:0|[1-9][0-9]{0,19})\Z")
_POSITIVE_DECIMAL = re.compile(r"\A[1-9][0-9]{0,19}\Z")
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_WORKSPACE_ID = re.compile(r"\Aaws_[0-9a-f]{32}\Z")
_PROJECT_ID = re.compile(r"\Aprj_[0-9a-f]{32}\Z")
_ATTACHMENT_ID = re.compile(r"\Aatt_[0-9a-f]{32}\Z")
_DEVICE = re.compile(r"\A[0-9]{1,10}:[0-9]{1,10}\Z")
_COMPONENT = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_CLEANUP_STATES = frozenset({"LIVE", "FENCED", "EMPTY_DURABLE"})
_AGENT_TYPES = frozenset({"claude", "codex"})
_SCHEMA = "waw-cgroup-attestation-v1"


class WAWCgroupAttestationError(ValueError):
    """A dynamic cgroup attestation is malformed or unsafe."""


@dataclass(frozen=True)
class WAWCgroupLimits:
    """Exact controller limits echoed in an attestation record."""

    memory_max: int
    memory_swap_max: int
    cpu_quota_usec: int
    cpu_period_usec: int
    pids_max: int


@dataclass(frozen=True)
class WAWCgroupAttachmentLeaf:
    """One bounded attachment leaf identity (at most one in V1)."""

    attachment_id: str
    relative_path: str
    device: str
    inode: str
    lease_number: int
    cleanup_state: str


@dataclass(frozen=True)
class WAWCgroupAttestation:
    """Canonical dynamic cgroup identity and cleanup evidence."""

    workspace_id: str
    project_id: str
    agent_type: str
    generation: int
    runtime_epoch: str
    service_unit: str
    service_invocation_id: str
    service_cgroup_device: str
    service_cgroup_inode: str
    service_cgroup_mount_id: str
    delegated_subgroup: str
    delegate_subgroup_device: str
    delegate_subgroup_inode: str
    delegate_subgroup_mount_id: str
    cgroup_mount_id: str
    cgroup_filesystem_id: str
    workspace_relative_path: str
    workspace_device: str
    workspace_inode: str
    workload_relative_path: str
    workload_device: str
    workload_inode: str
    attachment_leaves: tuple[WAWCgroupAttachmentLeaf, ...]
    controller_configuration_digest: str
    workspace_limits: WAWCgroupLimits
    workload_limits: WAWCgroupLimits
    attachment_limits: WAWCgroupLimits
    last_frozen: str
    last_populated: str
    cleanup_state: str


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WAWCgroupAttestationError("duplicate JSON key")
        result[key] = value
    return result


def _string(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > _MAX_STRING
        or "\x00" in value
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
    ):
        raise WAWCgroupAttestationError(f"invalid {field}")
    return value


def _component(value: object, field: str) -> str:
    value = _string(value, field)
    if _COMPONENT.fullmatch(value) is None or value in {".", ".."}:
        raise WAWCgroupAttestationError(f"invalid {field}")
    return value


def _relative_path(value: object, field: str) -> str:
    value = _string(value, field)
    parts = value.split("/")
    if value.startswith("/") or any(
        _COMPONENT.fullmatch(part) is None or part in {".", ".."} for part in parts
    ):
        raise WAWCgroupAttestationError(f"invalid {field}")
    return value


def _decimal(value: object, field: str, *, positive: bool = False) -> str:
    if not isinstance(value, str) or not (
        (_POSITIVE_DECIMAL if positive else _DECIMAL).fullmatch(value)
    ):
        raise WAWCgroupAttestationError(f"invalid {field}")
    if int(value) > _MAX_U64:
        raise WAWCgroupAttestationError(f"invalid {field}")
    return value


def _uint(value: object, field: str, *, positive: bool = False) -> int:
    if type(value) is not int or value < (1 if positive else 0) or value > _MAX_U64:
        raise WAWCgroupAttestationError(f"invalid {field}")
    return value


def _device(value: object, field: str) -> str:
    value = _string(value, field)
    if _DEVICE.fullmatch(value) is None:
        raise WAWCgroupAttestationError(f"invalid {field}")
    major, minor = value.split(":")
    if (len(major) > 1 and major.startswith("0")) or (len(minor) > 1 and minor.startswith("0")):
        raise WAWCgroupAttestationError(f"invalid {field}")
    return value


def _digest(value: object, field: str) -> str:
    value = _string(value, field)
    if _DIGEST.fullmatch(value) is None or value == "0" * 64:
        raise WAWCgroupAttestationError(f"invalid {field}")
    return value


def _limits(value: object, field: str) -> WAWCgroupLimits:
    if isinstance(value, WAWCgroupLimits):
        values = {
            "memory_max": value.memory_max,
            "memory_swap_max": value.memory_swap_max,
            "cpu_quota_usec": value.cpu_quota_usec,
            "cpu_period_usec": value.cpu_period_usec,
            "pids_max": value.pids_max,
        }
    elif isinstance(value, dict):
        values = value
    else:
        raise WAWCgroupAttestationError(f"invalid {field}")
    expected = {
        "memory_max",
        "memory_swap_max",
        "cpu_quota_usec",
        "cpu_period_usec",
        "pids_max",
    }
    if set(values) != expected:
        raise WAWCgroupAttestationError(f"invalid {field}")
    return WAWCgroupLimits(
        memory_max=_uint(values["memory_max"], f"{field}.memory_max", positive=True),
        memory_swap_max=_uint(values["memory_swap_max"], f"{field}.memory_swap_max"),
        cpu_quota_usec=_uint(values["cpu_quota_usec"], f"{field}.cpu_quota_usec", positive=True),
        cpu_period_usec=_uint(values["cpu_period_usec"], f"{field}.cpu_period_usec", positive=True),
        pids_max=_uint(values["pids_max"], f"{field}.pids_max", positive=True),
    )


def _leaf(value: object) -> WAWCgroupAttachmentLeaf:
    if isinstance(value, WAWCgroupAttachmentLeaf):
        values = {
            "attachment_id": value.attachment_id,
            "relative_path": value.relative_path,
            "device": value.device,
            "inode": value.inode,
            "lease_number": value.lease_number,
            "cleanup_state": value.cleanup_state,
        }
    elif isinstance(value, dict):
        values = value
    else:
        raise WAWCgroupAttestationError("invalid attachment_leaves")
    if set(values) != {
        "attachment_id",
        "relative_path",
        "device",
        "inode",
        "lease_number",
        "cleanup_state",
    }:
        raise WAWCgroupAttestationError("invalid attachment_leaves")
    attachment_id = _string(values["attachment_id"], "attachment_id")
    if _ATTACHMENT_ID.fullmatch(attachment_id) is None:
        raise WAWCgroupAttestationError("invalid attachment_id")
    cleanup_state = _string(values["cleanup_state"], "cleanup_state")
    if cleanup_state not in _CLEANUP_STATES:
        raise WAWCgroupAttestationError("invalid attachment cleanup_state")
    return WAWCgroupAttachmentLeaf(
        attachment_id=attachment_id,
        relative_path=_relative_path(values["relative_path"], "attachment relative_path"),
        device=_device(values["device"], "attachment device"),
        inode=_decimal(values["inode"], "attachment inode", positive=True),
        lease_number=_uint(values["lease_number"], "attachment lease_number", positive=True),
        cleanup_state=cleanup_state,
    )


def _mapping(value: object) -> dict[str, Any]:
    if isinstance(value, WAWCgroupAttestation):
        result = {key: getattr(value, key) for key in _FIELDS}
    elif isinstance(value, dict):
        result = dict(value)
    else:
        raise WAWCgroupAttestationError("attestation must be a mapping or typed record")
    if "schema_version" in result and result.pop("schema_version") != _SCHEMA:
        raise WAWCgroupAttestationError("invalid schema_version")
    if set(result) != set(_FIELDS):
        raise WAWCgroupAttestationError("attestation fields are not closed")
    return result


_FIELDS = (
    "workspace_id",
    "project_id",
    "agent_type",
    "generation",
    "runtime_epoch",
    "service_unit",
    "service_invocation_id",
    "service_cgroup_device",
    "service_cgroup_inode",
    "service_cgroup_mount_id",
    "delegated_subgroup",
    "delegate_subgroup_device",
    "delegate_subgroup_inode",
    "delegate_subgroup_mount_id",
    "cgroup_mount_id",
    "cgroup_filesystem_id",
    "workspace_relative_path",
    "workspace_device",
    "workspace_inode",
    "workload_relative_path",
    "workload_device",
    "workload_inode",
    "attachment_leaves",
    "controller_configuration_digest",
    "workspace_limits",
    "workload_limits",
    "attachment_limits",
    "last_frozen",
    "last_populated",
    "cleanup_state",
)


def _validated(value: object) -> WAWCgroupAttestation:
    values = _mapping(value)
    workspace_id = _string(values["workspace_id"], "workspace_id")
    if _WORKSPACE_ID.fullmatch(workspace_id) is None:
        raise WAWCgroupAttestationError("invalid workspace_id")
    project_id = _string(values["project_id"], "project_id")
    if _PROJECT_ID.fullmatch(project_id) is None:
        raise WAWCgroupAttestationError("invalid project_id")
    agent_type = _string(values["agent_type"], "agent_type")
    if agent_type not in _AGENT_TYPES:
        raise WAWCgroupAttestationError("invalid agent_type")
    generation = _uint(values["generation"], "generation", positive=True)
    runtime_epoch = _decimal(values["runtime_epoch"], "runtime_epoch", positive=True)
    service_unit = _string(values["service_unit"], "service_unit")
    if service_unit != "agentbox-runtime.service":
        raise WAWCgroupAttestationError("invalid service_unit")
    service_invocation_id = _component(values["service_invocation_id"], "service_invocation_id")
    for field in (
        "service_cgroup_device",
        "delegate_subgroup_device",
        "workspace_device",
        "workload_device",
    ):
        _device(values[field], field)
    for field in (
        "service_cgroup_inode",
        "service_cgroup_mount_id",
        "delegate_subgroup_inode",
        "delegate_subgroup_mount_id",
        "cgroup_mount_id",
        "workspace_inode",
        "workload_inode",
    ):
        _decimal(values[field], field, positive=True)
    delegated_subgroup = _component(values["delegated_subgroup"], "delegated_subgroup")
    cgroup_filesystem_id = _component(values["cgroup_filesystem_id"], "cgroup_filesystem_id")
    workspace_relative_path = _relative_path(
        values["workspace_relative_path"], "workspace_relative_path"
    )
    workload_relative_path = _relative_path(
        values["workload_relative_path"], "workload_relative_path"
    )
    leaves = values["attachment_leaves"]
    if type(leaves) not in (list, tuple) or len(leaves) > 1:
        raise WAWCgroupAttestationError("attachment_leaves must contain at most one leaf")
    attachment_leaves = tuple(_leaf(item) for item in leaves)
    controller_digest = _digest(
        values["controller_configuration_digest"], "controller_configuration_digest"
    )
    last_frozen = _string(values["last_frozen"], "last_frozen")
    last_populated = _string(values["last_populated"], "last_populated")
    if last_frozen not in {"0", "1"} or last_populated not in {"0", "1"}:
        raise WAWCgroupAttestationError("invalid cgroup state flag")
    cleanup_state = _string(values["cleanup_state"], "cleanup_state")
    if cleanup_state not in _CLEANUP_STATES:
        raise WAWCgroupAttestationError("invalid cleanup_state")
    workspace_limits = _limits(values["workspace_limits"], "workspace_limits")
    workload_limits = _limits(values["workload_limits"], "workload_limits")
    attachment_limits = _limits(values["attachment_limits"], "attachment_limits")
    for field in ("memory_max", "cpu_quota_usec", "cpu_period_usec", "pids_max"):
        if getattr(attachment_limits, field) > getattr(workload_limits, field) or getattr(
            workload_limits, field
        ) > getattr(workspace_limits, field):
            raise WAWCgroupAttestationError("cgroup limits violate hierarchy")
    if cleanup_state == "EMPTY_DURABLE" and (attachment_leaves or last_populated != "0"):
        raise WAWCgroupAttestationError(
            "EMPTY_DURABLE requires no attachment leaves and populated=0"
        )
    return WAWCgroupAttestation(
        workspace_id=workspace_id,
        project_id=project_id,
        agent_type=agent_type,
        generation=generation,
        runtime_epoch=runtime_epoch,
        service_unit=service_unit,
        service_invocation_id=service_invocation_id,
        service_cgroup_device=values["service_cgroup_device"],
        service_cgroup_inode=values["service_cgroup_inode"],
        service_cgroup_mount_id=values["service_cgroup_mount_id"],
        delegated_subgroup=delegated_subgroup,
        delegate_subgroup_device=values["delegate_subgroup_device"],
        delegate_subgroup_inode=values["delegate_subgroup_inode"],
        delegate_subgroup_mount_id=values["delegate_subgroup_mount_id"],
        cgroup_mount_id=values["cgroup_mount_id"],
        cgroup_filesystem_id=cgroup_filesystem_id,
        workspace_relative_path=workspace_relative_path,
        workspace_device=values["workspace_device"],
        workspace_inode=values["workspace_inode"],
        workload_relative_path=workload_relative_path,
        workload_device=values["workload_device"],
        workload_inode=values["workload_inode"],
        attachment_leaves=attachment_leaves,
        controller_configuration_digest=controller_digest,
        workspace_limits=workspace_limits,
        workload_limits=workload_limits,
        attachment_limits=attachment_limits,
        last_frozen=last_frozen,
        last_populated=last_populated,
        cleanup_state=cleanup_state,
    )


def encode_waw_cgroup_attestation(value: object) -> bytes:
    """Encode one validated attestation as canonical JSON bytes."""

    record = _validated(value)
    payload: dict[str, Any] = {
        "agent_type": record.agent_type,
        "attachment_leaves": [
            {
                "attachment_id": leaf.attachment_id,
                "cleanup_state": leaf.cleanup_state,
                "device": leaf.device,
                "inode": leaf.inode,
                "lease_number": leaf.lease_number,
                "relative_path": leaf.relative_path,
            }
            for leaf in record.attachment_leaves
        ],
        "attachment_limits": _limits_payload(record.attachment_limits),
        "cgroup_filesystem_id": record.cgroup_filesystem_id,
        "cgroup_mount_id": record.cgroup_mount_id,
        "cleanup_state": record.cleanup_state,
        "controller_configuration_digest": record.controller_configuration_digest,
        "delegate_subgroup_device": record.delegate_subgroup_device,
        "delegate_subgroup_inode": record.delegate_subgroup_inode,
        "delegate_subgroup_mount_id": record.delegate_subgroup_mount_id,
        "delegated_subgroup": record.delegated_subgroup,
        "generation": record.generation,
        "last_frozen": record.last_frozen,
        "last_populated": record.last_populated,
        "project_id": record.project_id,
        "runtime_epoch": record.runtime_epoch,
        "schema_version": _SCHEMA,
        "service_cgroup_device": record.service_cgroup_device,
        "service_cgroup_inode": record.service_cgroup_inode,
        "service_cgroup_mount_id": record.service_cgroup_mount_id,
        "service_invocation_id": record.service_invocation_id,
        "service_unit": record.service_unit,
        "workload_device": record.workload_device,
        "workload_inode": record.workload_inode,
        "workload_limits": _limits_payload(record.workload_limits),
        "workload_relative_path": record.workload_relative_path,
        "workspace_device": record.workspace_device,
        "workspace_id": record.workspace_id,
        "workspace_inode": record.workspace_inode,
        "workspace_limits": _limits_payload(record.workspace_limits),
        "workspace_relative_path": record.workspace_relative_path,
    }
    try:
        raw = rfc8785.dumps(payload)
    except (TypeError, ValueError, rfc8785.CanonicalizationError) as exc:
        raise WAWCgroupAttestationError("attestation canonicalization failed") from exc
    if not isinstance(raw, bytes) or not raw or len(raw) > _MAX_BYTES:
        raise WAWCgroupAttestationError("attestation is oversized")
    return raw


def _limits_payload(value: WAWCgroupLimits) -> dict[str, int]:
    return {
        "cpu_period_usec": value.cpu_period_usec,
        "cpu_quota_usec": value.cpu_quota_usec,
        "memory_max": value.memory_max,
        "memory_swap_max": value.memory_swap_max,
        "pids_max": value.pids_max,
    }


def decode_waw_cgroup_attestation(raw: bytes) -> WAWCgroupAttestation:
    """Decode canonical JSON bytes and reject duplicates/unknown fields."""

    if not isinstance(raw, bytes) or not raw or len(raw) > _MAX_BYTES:
        raise WAWCgroupAttestationError("attestation bytes are invalid")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_pairs)
    except WAWCgroupAttestationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise WAWCgroupAttestationError("attestation JSON is invalid") from exc
    record = _validated(value)
    if encode_waw_cgroup_attestation(record) != raw:
        raise WAWCgroupAttestationError("attestation is not canonical")
    return record


def waw_cgroup_attestation_sha256(raw: bytes) -> str:
    """Return the SHA-256 digest of canonical attestation bytes."""

    decode_waw_cgroup_attestation(raw)
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "WAWCgroupAttachmentLeaf",
    "WAWCgroupAttestation",
    "WAWCgroupAttestationError",
    "WAWCgroupLimits",
    "decode_waw_cgroup_attestation",
    "encode_waw_cgroup_attestation",
    "waw_cgroup_attestation_sha256",
]
