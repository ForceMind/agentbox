"""Exact non-secret WAW application-crypto context and canonical prologue.

Validation does not authenticate admission metadata or supply a trust provider.
Callers must supply their already-bound admission and Runtime epoch separately.
"""

from __future__ import annotations

import re

import rfc8785

PROTOCOL_ID = "agentbox-waw/v1"
CRYPTO_ENVELOPE_VERSION = 1
MAX_U64 = 2**64 - 1
ADMISSION_KEYS = frozenset(
    {
        "attachment_id",
        "workspace_id",
        "project_id",
        "agent_type",
        "runtime_host_installation_id",
        "runtime_host_installation_revision",
        "auth_epoch",
        "api_authority_epoch",
        "lease_number",
        "generation",
        "binding_revision",
        "mode",
        "binding_digest",
    }
)
CONTEXT_KEYS = (ADMISSION_KEYS - {"mode"}) | {
    "protocol_id",
    "crypto_envelope_version",
    "runtime_epoch",
}
U64_KEYS = frozenset(
    {
        "runtime_host_installation_revision",
        "auth_epoch",
        "api_authority_epoch",
        "lease_number",
        "generation",
        "binding_revision",
    }
)
_IDS = {
    "attachment_id": "att",
    "workspace_id": "aws",
    "project_id": "prj",
    "runtime_host_installation_id": "wri",
}
_DECIMAL = re.compile(r"[1-9][0-9]{0,19}\Z")
_HEX32 = re.compile(r"[a-f0-9]{64}\Z")


class WAWContextError(ValueError):
    """A closed application context is invalid; values are never echoed."""


def validate_u64(value: object) -> str:
    """Validate one positive canonical uint64 JSON string without coercion."""
    if type(value) is not str or _DECIMAL.fullmatch(value) is None or int(value) > MAX_U64:
        raise WAWContextError("invalid positive uint64 string")
    return value


def validate_hex32(value: object) -> str:
    if type(value) is not str or _HEX32.fullmatch(value) is None:
        raise WAWContextError("invalid lowercase 32-byte hexadecimal string")
    return value


def validate_admission(value: object) -> dict[str, str]:
    """Validate all 13 members and return a detached exact scalar dictionary."""
    if type(value) is not dict or value.keys() != ADMISSION_KEYS:
        raise WAWContextError("invalid AdmissionTuple fields")
    result: dict[str, str] = {}
    for key in ADMISSION_KEYS:
        item = value[key]
        if type(item) is not str:
            raise WAWContextError("invalid AdmissionTuple scalar type")
        if key in U64_KEYS:
            validate_u64(item)
        elif key in _IDS:
            if re.fullmatch(_IDS[key] + r"_[a-f0-9]{32}", item) is None:
                raise WAWContextError("invalid AdmissionTuple identifier")
        elif key == "binding_digest":
            validate_hex32(item)
        elif key == "mode" and item != "writer":
            raise WAWContextError("invalid AdmissionTuple mode")
        elif key == "agent_type" and item not in {"claude", "codex"}:
            raise WAWContextError("invalid AdmissionTuple agent type")
        result[key] = item
    return result


def derive_context(admission: object, runtime_epoch: object) -> dict[str, str | int]:
    """Omit validated writer mode and bind the already-known Runtime epoch."""
    bound = validate_admission(admission)
    result: dict[str, str | int] = {key: item for key, item in bound.items() if key != "mode"}
    result.update(
        protocol_id=PROTOCOL_ID,
        crypto_envelope_version=CRYPTO_ENVELOPE_VERSION,
        runtime_epoch=validate_u64(runtime_epoch),
    )
    return result


def validate_context(value: object) -> dict[str, str | int]:
    """Validate exactly 15 context members; no missing wire field is defaulted."""
    if type(value) is not dict or value.keys() != CONTEXT_KEYS:
        raise WAWContextError("invalid HandshakeContext fields")
    if (
        type(value["protocol_id"]) is not str
        or value["protocol_id"] != PROTOCOL_ID
        or type(value["crypto_envelope_version"]) is not int
        or value["crypto_envelope_version"] != CRYPTO_ENVELOPE_VERSION
    ):
        raise WAWContextError("unsupported application crypto profile")
    admission = {key: value[key] for key in ADMISSION_KEYS if key != "mode"}
    # Mode is not a member of C; this reconstructs its fixed derivation domain.
    admission["mode"] = "writer"
    return derive_context(admission, value["runtime_epoch"])


def canonical_context_bytes(value: object) -> bytes:
    """Complete RFC 8785 UTF-8 C bytes used unchanged as the Noise prologue."""
    return rfc8785.dumps(validate_context(value))


__all__ = [
    "ADMISSION_KEYS",
    "CONTEXT_KEYS",
    "CRYPTO_ENVELOPE_VERSION",
    "MAX_U64",
    "PROTOCOL_ID",
    "U64_KEYS",
    "WAWContextError",
    "canonical_context_bytes",
    "derive_context",
    "validate_admission",
    "validate_context",
    "validate_hex32",
    "validate_u64",
]
