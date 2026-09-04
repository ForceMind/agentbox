"""Closed codecs for the installer-owned WAW executable and CLI profiles.

The records in this module are installation data, never request data.  They do
not accept commands, environment mappings, secrets, credentials, caller IDs or
filesystem destinations.  Runtime still has to establish file provenance and
whole-bundle cross-pins before using a decoded record.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import rfc8785

EXECUTABLE_INVENTORY_SCHEMA_V1 = "waw-executable-inventory-v1"
INTERACTIVE_PROFILE_BUNDLE_SCHEMA_V1 = "waw-interactive-profile-bundle-v1"
CODEX_MANAGED_POLICY_BUNDLE_SCHEMA_V1 = "waw-codex-managed-policy-bundle-v1"
_MAX_BYTES = 64 * 1024
_MAX_PATH_BYTES = 4096
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")


class WAWProcessProfileError(ValueError):
    """An executable inventory or interactive profile is not the fixed v1 record."""


@dataclass(frozen=True)
class ExecutablePolicyV1:
    kind: str
    max_bytes: int
    version_identity: str
    version_probe_id: str
    fixed_path: str | None


@dataclass(frozen=True)
class ExecutableInventoryEntryV1:
    kind: str
    path: str
    sha256: str
    max_bytes: int
    version_identity: str
    version_probe_id: str


@dataclass(frozen=True)
class ExecutableInventoryV1:
    executables: tuple[ExecutableInventoryEntryV1, ...]


@dataclass(frozen=True)
class InteractiveProfileV1:
    agent_type: str
    profile_id: str
    executable_kind: str
    workspace_argv: tuple[str, ...]
    version_argv: tuple[str, ...]
    auth_probe_argv: tuple[str, ...]
    local_login_argv: tuple[str, ...]
    auth_parser_id: str
    home: str
    state_env_name: str
    state_root: str
    environment_profile_id: str
    managed_policy_path: str
    # Claude hashes its one policy file. Codex hashes the canonical exact-two
    # policy-bundle record, whose entries independently pin both Unix files.
    managed_policy_digest: str
    retention_profile_id: str
    rlimit_profile_id: str
    sandbox_profile_id: str
    trust_mode: str


@dataclass(frozen=True)
class InteractiveProfileBundleV1:
    profiles: tuple[InteractiveProfileV1, ...]


@dataclass(frozen=True)
class CodexManagedPolicyFileV1:
    name: str
    sha256: str


@dataclass(frozen=True)
class CodexManagedPolicyBundleV1:
    files: tuple[CodexManagedPolicyFileV1, ...]


# Vendor executable locations and digests are R12 enrollment observations.  The
# four AgentBox/system executables have invariant package locations here; every
# entry has invariant order, size ceiling, version identity and parser/probe ID.
EXECUTABLE_POLICIES_V1 = (
    ExecutablePolicyV1(
        "tmux", 64 * 1024 * 1024, "tmux-version-v1", "tmux-probe-v1", "/usr/bin/tmux"
    ),
    ExecutablePolicyV1(
        "pane_bootstrap",
        16 * 1024 * 1024,
        "pane-bootstrap-version-v1",
        "pane-bootstrap-probe-v1",
        "/opt/agentbox/current/libexec/agentbox-waw-pane-bootstrap",
    ),
    ExecutablePolicyV1(
        "bridge",
        16 * 1024 * 1024,
        "bridge-version-v1",
        "bridge-probe-v1",
        "/opt/agentbox/current/libexec/agentbox-waw-bridge",
    ),
    ExecutablePolicyV1(
        "attach_supervisor",
        16 * 1024 * 1024,
        "attach-supervisor-version-v1",
        "attach-supervisor-probe-v1",
        "/opt/agentbox/current/libexec/agentbox-waw-attach-supervisor",
    ),
    ExecutablePolicyV1("claude", 256 * 1024 * 1024, "claude-version-v1", "claude-probe-v1", None),
    ExecutablePolicyV1("codex", 256 * 1024 * 1024, "codex-version-v1", "codex-probe-v1", None),
)
EXECUTABLE_POLICY_BY_KIND_V1 = MappingProxyType(
    {policy.kind: policy for policy in EXECUTABLE_POLICIES_V1}
)


def _profile_constants(agent_type: str) -> dict[str, object]:
    home = f"/var/lib/agentbox-waw/vendor-homes/{agent_type}"
    if agent_type == "claude":
        return {
            "agent_type": "claude",
            "profile_id": "claude-interactive-v1",
            "executable_kind": "claude",
            "workspace_argv": (),
            "version_argv": ("--version",),
            "auth_probe_argv": ("auth", "status"),
            "local_login_argv": ("auth", "login"),
            "auth_parser_id": "claude-auth-status-v1",
            "home": home,
            "state_env_name": "CLAUDE_CONFIG_DIR",
            "state_root": f"{home}/.config/claude",
            "environment_profile_id": "claude-environment-v1",
            "managed_policy_path": "/etc/claude-code/managed-settings.json",
            "retention_profile_id": "claude-retention-v1",
            "rlimit_profile_id": "interactive-rlimit-v1",
            "sandbox_profile_id": "interactive-sandbox-v1",
            "trust_mode": "local-login-project-trust-v1",
        }
    return {
        "agent_type": "codex",
        "profile_id": "codex-interactive-v1",
        "executable_kind": "codex",
        "workspace_argv": (),
        "version_argv": ("--version",),
        "auth_probe_argv": ("login", "status"),
        "local_login_argv": ("login", "--device-auth"),
        "auth_parser_id": "codex-login-status-v1",
        "home": home,
        "state_env_name": "CODEX_HOME",
        "state_root": f"{home}/.config/codex",
        "environment_profile_id": "codex-environment-v1",
        "managed_policy_path": "/etc/codex",
        "retention_profile_id": "codex-retention-v1",
        "rlimit_profile_id": "interactive-rlimit-v1",
        "sandbox_profile_id": "interactive-sandbox-v1",
        "trust_mode": "local-login-project-trust-v1",
    }


INTERACTIVE_PROFILE_CONSTANTS_V1 = MappingProxyType(
    {
        agent_type: MappingProxyType(_profile_constants(agent_type))
        for agent_type in ("claude", "codex")
    }
)

_EXECUTABLE_FIELDS = (
    "kind",
    "path",
    "sha256",
    "max_bytes",
    "version_identity",
    "version_probe_id",
)
_PROFILE_FIELDS = (
    "agent_type",
    "profile_id",
    "executable_kind",
    "workspace_argv",
    "version_argv",
    "auth_probe_argv",
    "local_login_argv",
    "auth_parser_id",
    "home",
    "state_env_name",
    "state_root",
    "environment_profile_id",
    "managed_policy_path",
    "managed_policy_digest",
    "retention_profile_id",
    "rlimit_profile_id",
    "sandbox_profile_id",
    "trust_mode",
)
_CODEX_POLICY_FILE_FIELDS = ("name", "sha256")
_CODEX_POLICY_NAMES = ("requirements.toml", "managed_config.toml")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WAWProcessProfileError("duplicate JSON key")
        result[key] = value
    return result


def _string(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 512
        or "\x00" in value
        or unicodedata.normalize("NFC", value) != value
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
    ):
        raise WAWProcessProfileError("invalid bounded string")
    return value


def _absolute_path(value: object) -> str:
    path = _string(value)
    if (
        len(path.encode("utf-8")) > _MAX_PATH_BYTES
        or not path.startswith("/")
        or path.startswith("//")
        or "\\" in path
        or any(component in {"", ".", ".."} for component in path.split("/")[1:])
    ):
        raise WAWProcessProfileError("invalid absolute path")
    return path


def _digest(value: object) -> str:
    digest = _string(value)
    if _DIGEST.fullmatch(digest) is None or digest == "0" * 64:
        raise WAWProcessProfileError("invalid SHA-256 digest")
    return digest


def _argv(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or len(value) > 8:
        raise WAWProcessProfileError("invalid fixed argv")
    result = tuple(_string(item) for item in value)
    if any("/" in item or "=" in item for item in result):
        raise WAWProcessProfileError("argv contains a path or environment assignment")
    return result


def _object(value: object, fields: tuple[str, ...], name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise WAWProcessProfileError(f"{name} must be an object")
    data = dict(value)
    if set(data) != set(fields):
        raise WAWProcessProfileError(f"{name} fields are not closed")
    return data


def _canonical(value: Mapping[str, Any]) -> bytes:
    try:
        raw = rfc8785.dumps(dict(value))
    except (TypeError, ValueError, rfc8785.CanonicalizationError) as exc:
        raise WAWProcessProfileError("profile record cannot be canonicalized") from exc
    if not isinstance(raw, bytes) or not raw or len(raw) > _MAX_BYTES:
        raise WAWProcessProfileError("profile record is oversized")
    return raw


def encode_codex_managed_policy_bundle_v1(*, requirements: bytes, managed_config: bytes) -> bytes:
    """Bind the two exact Unix Codex managed-policy files as one authority."""

    if not isinstance(requirements, bytes) or not requirements:
        raise WAWProcessProfileError("Codex requirements policy bytes are invalid")
    if not isinstance(managed_config, bytes) or not managed_config:
        raise WAWProcessProfileError("Codex managed defaults bytes are invalid")
    files = [
        {"name": _CODEX_POLICY_NAMES[0], "sha256": hashlib.sha256(requirements).hexdigest()},
        {"name": _CODEX_POLICY_NAMES[1], "sha256": hashlib.sha256(managed_config).hexdigest()},
    ]
    return _canonical({"schema_version": CODEX_MANAGED_POLICY_BUNDLE_SCHEMA_V1, "files": files})


def decode_codex_managed_policy_bundle_v1(raw: bytes) -> CodexManagedPolicyBundleV1:
    _value, files = _decode_object(raw, CODEX_MANAGED_POLICY_BUNDLE_SCHEMA_V1, "files")
    if len(files) != 2:
        raise WAWProcessProfileError("Codex policy bundle must contain exact-two files")
    decoded: list[CodexManagedPolicyFileV1] = []
    for value, expected_name in zip(files, _CODEX_POLICY_NAMES, strict=True):
        data = _object(value, _CODEX_POLICY_FILE_FIELDS, "Codex policy file")
        if data["name"] != expected_name:
            raise WAWProcessProfileError("Codex policy file order or name is invalid")
        decoded.append(CodexManagedPolicyFileV1(expected_name, _digest(data["sha256"])))
    return CodexManagedPolicyBundleV1(tuple(decoded))


def verify_codex_managed_policy_bundle_v1(
    raw: bytes, *, requirements: bytes, managed_config: bytes
) -> CodexManagedPolicyBundleV1:
    bundle = decode_codex_managed_policy_bundle_v1(raw)
    actual = (
        hashlib.sha256(requirements).hexdigest(),
        hashlib.sha256(managed_config).hexdigest(),
    )
    if any(
        not hmac.compare_digest(record.sha256, digest)
        for record, digest in zip(bundle.files, actual, strict=True)
    ):
        raise WAWProcessProfileError("Codex managed policy bundle digest mismatch")
    return bundle


def _decode_object(raw: bytes, schema: str, field: str) -> tuple[dict[str, Any], list[Any]]:
    if not isinstance(raw, bytes) or not raw or len(raw) > _MAX_BYTES:
        raise WAWProcessProfileError("profile bytes are invalid")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise WAWProcessProfileError("profile JSON is invalid") from exc
    if not isinstance(value, dict) or set(value) != {"schema_version", field}:
        raise WAWProcessProfileError("profile top-level fields are not closed")
    if value["schema_version"] != schema or not isinstance(value[field], list):
        raise WAWProcessProfileError("profile schema or collection is invalid")
    if _canonical(value) != raw:
        raise WAWProcessProfileError("profile record is not canonical RFC 8785 JSON")
    return value, value[field]


def _entry_data(entry: ExecutableInventoryEntryV1 | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(entry, ExecutableInventoryEntryV1):
        return {field: getattr(entry, field) for field in _EXECUTABLE_FIELDS}
    return _object(entry, _EXECUTABLE_FIELDS, "executable entry")


def _validate_entry(data: Mapping[str, Any], expected: ExecutablePolicyV1) -> None:
    path = _absolute_path(data["path"])
    _digest(data["sha256"])
    if (
        data["kind"] != expected.kind
        or type(data["max_bytes"]) is not int
        or data["max_bytes"] != expected.max_bytes
        or data["version_identity"] != expected.version_identity
        or data["version_probe_id"] != expected.version_probe_id
        or (expected.fixed_path is not None and path != expected.fixed_path)
    ):
        raise WAWProcessProfileError("executable entry does not match the fixed policy")


def encode_executable_inventory_v1(
    value: ExecutableInventoryV1 | Mapping[str, Any],
) -> bytes:
    entries = (
        value.executables
        if isinstance(value, ExecutableInventoryV1)
        else _object(value, ("executables",), "executable inventory")["executables"]
    )
    if type(entries) not in (list, tuple) or len(entries) != len(EXECUTABLE_POLICIES_V1):
        raise WAWProcessProfileError("executable inventory must contain exact-six entries")
    encoded: list[dict[str, Any]] = []
    for entry, expected in zip(entries, EXECUTABLE_POLICIES_V1, strict=True):
        data = _entry_data(entry)
        _validate_entry(data, expected)
        encoded.append(data)
    if len({entry["path"] for entry in encoded}) != len(encoded):
        raise WAWProcessProfileError("executable inventory paths must be distinct")
    return _canonical({"schema_version": EXECUTABLE_INVENTORY_SCHEMA_V1, "executables": encoded})


def decode_executable_inventory_v1(raw: bytes) -> ExecutableInventoryV1:
    _value, entries = _decode_object(raw, EXECUTABLE_INVENTORY_SCHEMA_V1, "executables")
    if len(entries) != len(EXECUTABLE_POLICIES_V1):
        raise WAWProcessProfileError("executable inventory must contain exact-six entries")
    decoded: list[ExecutableInventoryEntryV1] = []
    for entry, expected in zip(entries, EXECUTABLE_POLICIES_V1, strict=True):
        data = _object(entry, _EXECUTABLE_FIELDS, "executable entry")
        _validate_entry(data, expected)
        decoded.append(ExecutableInventoryEntryV1(**data))
    if len({entry.path for entry in decoded}) != len(decoded):
        raise WAWProcessProfileError("executable inventory paths must be distinct")
    return ExecutableInventoryV1(tuple(decoded))


def _profile_data(profile: InteractiveProfileV1 | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(profile, InteractiveProfileV1):
        return {field: getattr(profile, field) for field in _PROFILE_FIELDS}
    return _object(profile, _PROFILE_FIELDS, "interactive profile")


def _validate_profile(data: dict[str, Any], expected: Mapping[str, object]) -> None:
    for field in ("workspace_argv", "version_argv", "auth_probe_argv", "local_login_argv"):
        data[field] = _argv(data[field])
    for field in ("home", "state_root", "managed_policy_path"):
        _absolute_path(data[field])
    _digest(data["managed_policy_digest"])
    for field, fixed in expected.items():
        actual = data[field]
        if isinstance(fixed, tuple):
            actual = tuple(actual)
        if actual != fixed:
            raise WAWProcessProfileError(f"interactive profile field is not fixed: {field}")


def encode_interactive_profile_bundle_v1(
    value: InteractiveProfileBundleV1 | Mapping[str, Any],
) -> bytes:
    profiles = (
        value.profiles
        if isinstance(value, InteractiveProfileBundleV1)
        else _object(value, ("profiles",), "interactive profile bundle")["profiles"]
    )
    if type(profiles) not in (list, tuple) or len(profiles) != 2:
        raise WAWProcessProfileError("interactive profile bundle must contain exact profiles")
    encoded: list[dict[str, Any]] = []
    for profile, agent_type in zip(profiles, ("claude", "codex"), strict=True):
        data = _profile_data(profile)
        _validate_profile(data, INTERACTIVE_PROFILE_CONSTANTS_V1[agent_type])
        for field in ("workspace_argv", "version_argv", "auth_probe_argv", "local_login_argv"):
            data[field] = list(data[field])
        encoded.append(data)
    return _canonical({"schema_version": INTERACTIVE_PROFILE_BUNDLE_SCHEMA_V1, "profiles": encoded})


def decode_interactive_profile_bundle_v1(raw: bytes) -> InteractiveProfileBundleV1:
    _value, profiles = _decode_object(raw, INTERACTIVE_PROFILE_BUNDLE_SCHEMA_V1, "profiles")
    if len(profiles) != 2:
        raise WAWProcessProfileError("interactive profile bundle must contain exact profiles")
    decoded: list[InteractiveProfileV1] = []
    for profile, agent_type in zip(profiles, ("claude", "codex"), strict=True):
        data = _object(profile, _PROFILE_FIELDS, "interactive profile")
        _validate_profile(data, INTERACTIVE_PROFILE_CONSTANTS_V1[agent_type])
        decoded.append(InteractiveProfileV1(**data))
    return InteractiveProfileBundleV1(tuple(decoded))


__all__ = [
    "CODEX_MANAGED_POLICY_BUNDLE_SCHEMA_V1",
    "EXECUTABLE_INVENTORY_SCHEMA_V1",
    "EXECUTABLE_POLICIES_V1",
    "EXECUTABLE_POLICY_BY_KIND_V1",
    "INTERACTIVE_PROFILE_BUNDLE_SCHEMA_V1",
    "INTERACTIVE_PROFILE_CONSTANTS_V1",
    "ExecutableInventoryEntryV1",
    "ExecutableInventoryV1",
    "ExecutablePolicyV1",
    "CodexManagedPolicyBundleV1",
    "CodexManagedPolicyFileV1",
    "InteractiveProfileBundleV1",
    "InteractiveProfileV1",
    "WAWProcessProfileError",
    "decode_executable_inventory_v1",
    "decode_codex_managed_policy_bundle_v1",
    "decode_interactive_profile_bundle_v1",
    "encode_executable_inventory_v1",
    "encode_codex_managed_policy_bundle_v1",
    "encode_interactive_profile_bundle_v1",
    "verify_codex_managed_policy_bundle_v1",
]
