"""Strict codecs for installer-owned, non-secret WAW trust records.

These codecs deliberately only handle data.  They do not read or write host
files and do not interpret any value as a command, environment, credential, or
terminal payload.  Every decoder rejects duplicate keys, unknown fields, and
non-canonical RFC 8785 JSON.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

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
_PROJECT_ROOT_MODE = re.compile(r"\A[0-7]{3}\Z")
_CGROUP_SUBGROUP = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_STATES = frozenset({"bootstrap", "steady", "rotation"})
_CGROUP_SERVICE_LIMITS = {
    "tasks_max": 256,
    "memory_max": 536_870_912,
    "memory_swap_max": 0,
    "cpu_quota_percent": 400,
    "cpu_quota_period_usec": 100_000,
}


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
    cgroup_delegation_policy_digest: str
    project_root_manifest_path: str
    project_root_manifest_digest: str
    socket_digest: str
    config_digest: str
    enrollment_epoch: str
    enrollment_state: str


@dataclass(frozen=True)
class CrossManifestPin:
    """The strictly decoded records validated by a cross-manifest pin.

    The records are returned so callers cannot accidentally continue with a
    different, independently decoded view of the bytes that were checked.
    This is still a data-only value; it performs no host discovery or I/O.
    """

    anchor: APIHostAnchor
    runtime: RuntimeHostManifest
    project_root: ProjectRootManifest
    cgroup: CgroupDelegationManifest
    runtime_manifest_digest: str
    project_root_manifest_digest: str
    cgroup_manifest_digest: str


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
        "cgroup_delegation_policy_digest",
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
    # A zero digest is a sentinel used by incomplete/unknown evidence and
    # must never be accepted as an identity or trust anchor.
    if _DIGEST.fullmatch(value) is None or value == "0" * 64:
        raise WAWManifestCodecError(f"invalid {field}")
    return value


def _project_root_mode(value: object) -> str:
    """Validate the canonical three-digit octal project-root mode.

    The wire representation intentionally omits a leading ``0`` (as in the
    existing manifest vectors), while each digit is still octal.  The root
    must be searchable/readable/writable by its owner, and group/other write
    or special bits are not permitted.  The latter prevents a manifest from
    authorizing a world/group-writable or set-id project root.
    """

    if not isinstance(value, str) or _PROJECT_ROOT_MODE.fullmatch(value) is None:
        raise WAWManifestCodecError("invalid root_mode")
    mode = int(value, 8)
    if mode & 0o700 != 0o700 or mode & 0o022:
        raise WAWManifestCodecError("unsafe root_mode")
    return value


def _cgroup_subgroup(value: object) -> str:
    """Validate a single safe systemd cgroup subgroup component."""

    if not isinstance(value, str) or _CGROUP_SUBGROUP.fullmatch(value) is None:
        raise WAWManifestCodecError("invalid delegate_subgroup")
    if value in {".", ".."}:
        raise WAWManifestCodecError("invalid delegate_subgroup")
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
    if not isinstance(encoded, bytes) or not encoded or len(encoded) > _MAX_BYTES:
        raise WAWManifestCodecError("manifest is oversized")
    return encoded


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
    ):
        _u64(value[field])
    _project_root_mode(value["root_mode"])
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
        "protect_control_groups",
        "kill_mode",
    ):
        _string(value[field])
    _cgroup_subgroup(value["delegate_subgroup"])
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
    for field, expected in _CGROUP_SERVICE_LIMITS.items():
        actual = _positive_int(value[field], field)
        if actual != expected:
            raise WAWManifestCodecError(f"{field} must equal the approved service limit")
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
        "cgroup_delegation_policy_digest",
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


def _strict_record_bytes(
    value: object,
    record_type: type[_T],
    encoder: Any,
    decoder: Any,
) -> tuple[_T, bytes]:
    """Normalize a typed record or bytes through the strict decoder.

    Typed records are re-encoded and decoded as well, so this verifier has a
    single canonical representation and never validates a looser mapping or
    an independently constructed object.  Raw bytes are always decoded first
    and therefore inherit duplicate-key, schema, canonicalization, and
    identity validation from the record decoder.
    """

    if isinstance(value, bytes):
        record = decoder(value)
        return record, value
    if isinstance(value, record_type):
        raw = encoder(value)
        return decoder(raw), raw
    raise WAWManifestCodecError("cross-manifest pin requires typed records or bytes")


def verify_api_host_anchor_cross_manifest(
    anchor: APIHostAnchor | bytes,
    runtime: RuntimeHostManifest | bytes,
    project_root: ProjectRootManifest | bytes,
    cgroup_delegation: CgroupDelegationManifest | bytes,
) -> CrossManifestPin:
    """Verify the complete non-secret manifest bundle cross-pin.

    Every input is routed through its strict canonical decoder.  The API
    anchor must pin the exact SHA-256 bytes of both the Runtime and Project
    Root records; the Runtime record must independently pin the exact Project
    Root bytes and the cgroup delegation record.  Runtime identity and
    enrollment context must match the API anchor exactly.  Any mismatch,
    replayed enrollment context, legacy
    schema, non-canonical bytes, or sentinel digest raises
    :class:`WAWManifestCodecError` before a result is returned.
    """

    anchor_record, _anchor_raw = _strict_record_bytes(
        anchor, APIHostAnchor, encode_api_host_anchor, decode_api_host_anchor
    )
    runtime_record, runtime_raw = _strict_record_bytes(
        runtime, RuntimeHostManifest, encode_runtime_host_manifest, decode_runtime_host_manifest
    )
    project_record, project_raw = _strict_record_bytes(
        project_root,
        ProjectRootManifest,
        encode_project_root_manifest,
        decode_project_root_manifest,
    )
    cgroup_record, cgroup_raw = _strict_record_bytes(
        cgroup_delegation,
        CgroupDelegationManifest,
        encode_cgroup_delegation_manifest,
        decode_cgroup_delegation_manifest,
    )

    runtime_digest = manifest_sha256(runtime_raw)
    project_digest = manifest_sha256(project_raw)
    cgroup_digest = manifest_sha256(cgroup_raw)
    if not hmac.compare_digest(anchor_record.host_manifest_digest, runtime_digest):
        raise WAWManifestCodecError("API anchor does not pin Runtime manifest bytes")
    if not hmac.compare_digest(anchor_record.project_root_manifest_digest, project_digest):
        raise WAWManifestCodecError("API anchor does not pin ProjectRoot manifest bytes")
    if not hmac.compare_digest(runtime_record.project_root_manifest_digest, project_digest):
        raise WAWManifestCodecError("Runtime does not pin ProjectRoot manifest bytes")
    if not hmac.compare_digest(runtime_record.cgroup_delegation_policy_digest, cgroup_digest):
        raise WAWManifestCodecError("Runtime does not pin cgroup delegation manifest bytes")

    for field in (
        "runtime_host_installation_id",
        "runtime_host_installation_revision",
        "runtime_attestation_x25519_fingerprint",
        "enrollment_epoch",
        "enrollment_state",
    ):
        if getattr(anchor_record, field) != getattr(runtime_record, field):
            raise WAWManifestCodecError(f"cross-manifest identity mismatch: {field}")

    return CrossManifestPin(
        anchor=anchor_record,
        runtime=runtime_record,
        project_root=project_record,
        cgroup=cgroup_record,
        runtime_manifest_digest=runtime_digest,
        project_root_manifest_digest=project_digest,
        cgroup_manifest_digest=cgroup_digest,
    )


def manifest_sha256(raw: bytes) -> str:
    """Return the digest of already-canonical manifest bytes."""

    if not isinstance(raw, bytes) or len(raw) == 0 or len(raw) > _MAX_BYTES:
        raise WAWManifestCodecError("manifest bytes are invalid")
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "APIHostAnchor",
    "CgroupDelegationManifest",
    "CrossManifestPin",
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
    "verify_api_host_anchor_cross_manifest",
]
