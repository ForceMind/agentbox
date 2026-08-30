"""Strict codecs for installer-owned, non-secret WAW trust records.

These codecs deliberately only handle data.  They do not read or write host
files and do not interpret any value as a command, environment, credential, or
terminal payload.  Every decoder rejects duplicate keys, unknown fields, and
non-canonical RFC 8785 JSON.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeVar, cast

import rfc8785

_MAX_BYTES = 64 * 1024
_MAX_STRING = 512
_MAX_PATH = 4096
_MAX_U64 = 2**64 - 1
_DECIMAL = re.compile(r"\A(?:0|[1-9][0-9]{0,19})\Z")
_POSITIVE_DECIMAL = re.compile(r"\A[1-9][0-9]{0,19}\Z")
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_ID = re.compile(r"\A(?:wri|prj)_[0-9a-f]{32}\Z")
_RUNTIME_ID = re.compile(r"\Awri_[0-9a-f]{32}\Z")
_HEX_FINGERPRINT = _DIGEST
_STATES = frozenset({"bootstrap", "steady", "rotation"})


class WAWManifestCodecError(ValueError):
    """A WAW manifest is malformed, unsafe, or not canonical."""


@dataclass(frozen=True)
class ProjectRootManifest:
    manifest_revision: str
    configured_root: str
    root_device: str
    root_mount_id: str
    root_filesystem_id: str
    root_uid: str
    root_gid: str
    root_mode: str
    relative_key_grammar_version: str
    binding_digest_algorithm: str
    no_shell_executable_path: str
    no_shell_executable_digest: str


@dataclass(frozen=True)
class CgroupDelegationManifest:
    service_unit: str
    cgroup_mount_type: str
    cgroup_mount_device: str
    cgroup_mount_filesystem_id: str
    cgroup_schema_identity: str
    delegate: bool
    delegate_subgroup: str
    protect_control_groups: str
    kill_mode: str
    controllers: tuple[str, ...]
    tasks_max: int
    memory_max: int
    memory_swap_max: int
    cpu_quota_percent: int
    cpu_quota_period_usec: int
    policy_template_digest: str


@dataclass(frozen=True)
class APIHostAnchor:
    runtime_host_installation_id: str
    runtime_host_installation_revision: str
    runtime_attestation_x25519_fingerprint: str
    host_manifest_digest: str
    project_root_manifest_digest: str
    enrollment_epoch: str
    enrollment_state: str


@dataclass(frozen=True)
class RuntimeHostManifest:
    runtime_host_installation_id: str
    runtime_host_installation_revision: str
    runtime_attestation_x25519_fingerprint: str
    tmux_fingerprint: str
    bridge_fingerprint: str
    claude_fingerprint: str
    codex_fingerprint: str
    attach_supervisor_fingerprint: str
    project_root_manifest_path: str
    project_root_manifest_digest: str
    socket_digest: str
    config_digest: str
    enrollment_epoch: str
    enrollment_state: str


_T = TypeVar("_T")
_SCHEMAS: dict[type[Any], str] = {
    ProjectRootManifest: "waw-project-root-v1",
    CgroupDelegationManifest: "waw-cgroup-delegation-v1",
    APIHostAnchor: "waw-api-host-anchor-v1",
    RuntimeHostManifest: "waw-runtime-host-installation-v1",
}

_FIELD_NAMES: dict[type[Any], tuple[str, ...]] = {
    ProjectRootManifest: (
        "manifest_revision",
        "configured_root",
        "root_device",
        "root_mount_id",
        "root_filesystem_id",
        "root_uid",
        "root_gid",
        "root_mode",
        "relative_key_grammar_version",
        "binding_digest_algorithm",
        "no_shell_executable_path",
        "no_shell_executable_digest",
    ),
    CgroupDelegationManifest: (
        "service_unit",
        "cgroup_mount_type",
        "cgroup_mount_device",
        "cgroup_mount_filesystem_id",
        "cgroup_schema_identity",
        "delegate",
        "delegate_subgroup",
        "protect_control_groups",
        "kill_mode",
        "controllers",
        "tasks_max",
        "memory_max",
        "memory_swap_max",
        "cpu_quota_percent",
        "cpu_quota_period_usec",
        "policy_template_digest",
    ),
    APIHostAnchor: (
        "runtime_host_installation_id",
        "runtime_host_installation_revision",
        "runtime_attestation_x25519_fingerprint",
        "host_manifest_digest",
        "project_root_manifest_digest",
        "enrollment_epoch",
        "enrollment_state",
    ),
    RuntimeHostManifest: (
        "runtime_host_installation_id",
        "runtime_host_installation_revision",
        "runtime_attestation_x25519_fingerprint",
        "tmux_fingerprint",
        "bridge_fingerprint",
        "claude_fingerprint",
        "codex_fingerprint",
        "attach_supervisor_fingerprint",
        "project_root_manifest_path",
        "project_root_manifest_digest",
        "socket_digest",
        "config_digest",
        "enrollment_epoch",
        "enrollment_state",
    ),
}


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WAWManifestCodecError("duplicate JSON key")
        result[key] = value
    return result


def _u64(value: object, *, positive: bool = False) -> str:
    if not isinstance(value, str) or not (  # bool is never a string, kept explicit for clarity
        (_POSITIVE_DECIMAL if positive else _DECIMAL).fullmatch(value)
    ):
        raise WAWManifestCodecError("invalid unsigned decimal")
    if int(value) > _MAX_U64:
        raise WAWManifestCodecError("unsigned decimal exceeds uint64")
    return value


def _string(value: object, *, path: bool = False) -> str:
    if not isinstance(value, str) or len(value) > (_MAX_PATH if path else _MAX_STRING):
        raise WAWManifestCodecError("invalid bounded string")
    if not value or "\x00" in value or unicodedata.normalize("NFC", value) != value:
        raise WAWManifestCodecError("invalid string grammar")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise WAWManifestCodecError("control character in string")
    return value


def _absolute_path(value: object) -> str:
    value = _string(value, path=True)
    if not value.startswith("/") or value.startswith("//") or "\\" in value:
        raise WAWManifestCodecError("invalid absolute path")
    components = value.split("/")
    if any(component in {"", ".", ".."} for component in components[1:]):
        raise WAWManifestCodecError("invalid path components")
    return value


def _digest(value: object, field: str) -> str:
    value = _string(value)
    if _DIGEST.fullmatch(value) is None:
        raise WAWManifestCodecError(f"invalid {field}")
    return value


def _id(value: object, field: str) -> str:
    value = _string(value)
    if _ID.fullmatch(value) is None or value.endswith("0" * 32):
        raise WAWManifestCodecError(f"invalid {field}")
    return value


def _runtime_id(value: object) -> str:
    value = _string(value)
    if _RUNTIME_ID.fullmatch(value) is None or value.endswith("0" * 32):
        raise WAWManifestCodecError("invalid runtime_host_installation_id")
    return value


def _positive_int(value: object, field: str) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_U64:
        raise WAWManifestCodecError(f"invalid {field}")
    return value


def _mapping(value: object, cls: type[_T]) -> dict[str, Any]:
    if isinstance(value, cls):
        data = {name: getattr(value, name) for name in _FIELD_NAMES[cls]}
    elif isinstance(value, Mapping):
        data = dict(value)
    else:
        raise WAWManifestCodecError("manifest must be a mapping or typed record")
    expected = set(_FIELD_NAMES[cls])
    if "schema_version" in data and data.pop("schema_version") != _SCHEMAS[cls]:
        raise WAWManifestCodecError("manifest schema is invalid")
    if set(data) != expected:
        raise WAWManifestCodecError("manifest fields are not closed")
    data["schema_version"] = _SCHEMAS[cls]
    return data


def _canonical(value: Mapping[str, Any]) -> bytes:
    try:
        encoded = rfc8785.dumps(dict(value))
    except (TypeError, ValueError, rfc8785.CanonicalizationError) as exc:
        raise WAWManifestCodecError("manifest cannot be canonicalized") from exc
    if not encoded or len(encoded) > _MAX_BYTES:
        raise WAWManifestCodecError("manifest is oversized")
    return cast(bytes, encoded)


def _encode(value: object, cls: type[_T], validate: Any) -> bytes:
    data = _mapping(value, cls)
    validate(data)
    return _canonical(data)


def _decode(raw: bytes, cls: type[_T], validate: Any) -> _T:
    if not isinstance(raw, bytes) or not raw or len(raw) > _MAX_BYTES:
        raise WAWManifestCodecError("manifest bytes are invalid")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise WAWManifestCodecError("manifest JSON is invalid") from exc
    if not isinstance(value, dict):
        raise WAWManifestCodecError("manifest must be an object")
    expected = {"schema_version", *_FIELD_NAMES[cls]}
    if set(value) != expected or value.get("schema_version") != _SCHEMAS[cls]:
        raise WAWManifestCodecError("manifest fields or schema are invalid")
    validate(value)
    if _canonical(value) != raw:
        raise WAWManifestCodecError("manifest is not canonical RFC 8785 JSON")
    kwargs = {name: value[name] for name in _FIELD_NAMES[cls]}
    if cls is CgroupDelegationManifest:
        kwargs["controllers"] = tuple(kwargs["controllers"])
    return cls(**kwargs)


def _validate_project(value: Mapping[str, Any]) -> None:
    _u64(value["manifest_revision"], positive=True)
    root = _absolute_path(value["configured_root"])
    if root == "/" or root.startswith("/home/"):
        raise WAWManifestCodecError("configured root is outside the approved project root")
    for field in (
        "root_device",
        "root_mount_id",
        "root_uid",
        "root_gid",
        "root_mode",
    ):
        _u64(value[field])
    _string(value["root_filesystem_id"])
    if value["relative_key_grammar_version"] != "one-component-v1":
        raise WAWManifestCodecError("unsupported relative key grammar")
    if value["binding_digest_algorithm"] != "sha256-rfc8785":
        raise WAWManifestCodecError("unsupported binding digest algorithm")
    if _absolute_path(value["no_shell_executable_path"]) != "/bin/false":
        raise WAWManifestCodecError("unexpected no-shell executable")
    _digest(value["no_shell_executable_digest"], "no_shell_executable_digest")


def _validate_cgroup(value: Mapping[str, Any]) -> None:
    for field in (
        "service_unit",
        "cgroup_mount_type",
        "cgroup_mount_device",
        "cgroup_mount_filesystem_id",
        "cgroup_schema_identity",
        "delegate_subgroup",
        "protect_control_groups",
        "kill_mode",
    ):
        _string(value[field])
    if (
        value["service_unit"] != "agentbox-runtime.service"
        or value["cgroup_mount_type"] != "cgroup2"
    ):
        raise WAWManifestCodecError("unsupported cgroup policy identity")
    _string(value["cgroup_mount_device"])
    _string(value["cgroup_mount_filesystem_id"])
    if not isinstance(value["delegate"], bool) or value["delegate"] is not True:
        raise WAWManifestCodecError("cgroup delegation must be enabled")
    if value["protect_control_groups"] != "private" or value["kill_mode"] != "process":
        raise WAWManifestCodecError("unsupported cgroup service policy")
    controllers = value["controllers"]
    if type(controllers) not in (list, tuple) or tuple(controllers) != ("cpu", "memory", "pids"):
        raise WAWManifestCodecError("controller set must be canonical")
    for controller in controllers:
        _string(controller)
    for field in (
        "tasks_max",
        "memory_max",
        "memory_swap_max",
        "cpu_quota_percent",
        "cpu_quota_period_usec",
    ):
        _positive_int(value[field], field)
    _digest(value["policy_template_digest"], "policy_template_digest")


def _validate_anchor(value: Mapping[str, Any]) -> None:
    _runtime_id(value["runtime_host_installation_id"])
    _u64(value["runtime_host_installation_revision"], positive=True)
    _digest(
        value["runtime_attestation_x25519_fingerprint"], "runtime_attestation_x25519_fingerprint"
    )
    _digest(value["host_manifest_digest"], "host_manifest_digest")
    _digest(value["project_root_manifest_digest"], "project_root_manifest_digest")
    _u64(value["enrollment_epoch"], positive=True)
    if value["enrollment_state"] not in _STATES:
        raise WAWManifestCodecError("invalid enrollment state")


def _validate_runtime(value: Mapping[str, Any]) -> None:
    _runtime_id(value["runtime_host_installation_id"])
    _u64(value["runtime_host_installation_revision"], positive=True)
    _digest(
        value["runtime_attestation_x25519_fingerprint"], "runtime_attestation_x25519_fingerprint"
    )
    for field in (
        "tmux_fingerprint",
        "bridge_fingerprint",
        "claude_fingerprint",
        "codex_fingerprint",
        "attach_supervisor_fingerprint",
        "project_root_manifest_digest",
        "socket_digest",
        "config_digest",
    ):
        _digest(value[field], field)
    _absolute_path(value["project_root_manifest_path"])
    _u64(value["enrollment_epoch"], positive=True)
    if value["enrollment_state"] not in _STATES:
        raise WAWManifestCodecError("invalid enrollment state")


def encode_project_root_manifest(value: ProjectRootManifest | Mapping[str, Any]) -> bytes:
    return _encode(value, ProjectRootManifest, _validate_project)


def decode_project_root_manifest(raw: bytes) -> ProjectRootManifest:
    return _decode(raw, ProjectRootManifest, _validate_project)


def encode_cgroup_delegation_manifest(value: CgroupDelegationManifest | Mapping[str, Any]) -> bytes:
    return _encode(value, CgroupDelegationManifest, _validate_cgroup)


def decode_cgroup_delegation_manifest(raw: bytes) -> CgroupDelegationManifest:
    return _decode(raw, CgroupDelegationManifest, _validate_cgroup)


def encode_api_host_anchor(value: APIHostAnchor | Mapping[str, Any]) -> bytes:
    return _encode(value, APIHostAnchor, _validate_anchor)


def decode_api_host_anchor(raw: bytes) -> APIHostAnchor:
    return _decode(raw, APIHostAnchor, _validate_anchor)


def encode_runtime_host_manifest(value: RuntimeHostManifest | Mapping[str, Any]) -> bytes:
    return _encode(value, RuntimeHostManifest, _validate_runtime)


def decode_runtime_host_manifest(raw: bytes) -> RuntimeHostManifest:
    return _decode(raw, RuntimeHostManifest, _validate_runtime)


def manifest_sha256(raw: bytes) -> str:
    """Return the digest of already-canonical manifest bytes."""

    if not isinstance(raw, bytes) or len(raw) == 0 or len(raw) > _MAX_BYTES:
        raise WAWManifestCodecError("manifest bytes are invalid")
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "APIHostAnchor",
    "CgroupDelegationManifest",
    "ProjectRootManifest",
    "RuntimeHostManifest",
    "WAWManifestCodecError",
    "decode_api_host_anchor",
    "decode_cgroup_delegation_manifest",
    "decode_project_root_manifest",
    "decode_runtime_host_manifest",
    "encode_api_host_anchor",
    "encode_cgroup_delegation_manifest",
    "encode_project_root_manifest",
    "encode_runtime_host_manifest",
    "manifest_sha256",
]
