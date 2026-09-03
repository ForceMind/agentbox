from __future__ import annotations

import hashlib

import pytest
from agentbox_protocol.waw_crypto_context import (
    ADMISSION_KEYS,
    CONTEXT_KEYS,
    U64_KEYS,
    WAWContextError,
    canonical_context_bytes,
    derive_context,
    validate_admission,
    validate_context,
)

ADMISSION = {
    "attachment_id": "att_" + "1" * 32,
    "workspace_id": "aws_" + "2" * 32,
    "project_id": "prj_" + "3" * 32,
    "agent_type": "codex",
    "runtime_host_installation_id": "wri_" + "4" * 32,
    "runtime_host_installation_revision": "7",
    "auth_epoch": "8",
    "api_authority_epoch": "9",
    "lease_number": "10",
    "mode": "writer",
    "generation": "11",
    "binding_revision": "12",
    "binding_digest": "a" * 64,
}

# Independently written expected ASCII/JCS bytes, not another call to the serializer.
CANONICAL = (
    '{"agent_type":"codex","api_authority_epoch":"9",'
    '"attachment_id":"att_11111111111111111111111111111111","auth_epoch":"8",'
    '"binding_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
    '"binding_revision":"12","crypto_envelope_version":1,"generation":"11",'
    '"lease_number":"10","project_id":"prj_33333333333333333333333333333333",'
    '"protocol_id":"agentbox-waw/v1","runtime_epoch":"13",'
    '"runtime_host_installation_id":"wri_44444444444444444444444444444444",'
    '"runtime_host_installation_revision":"7",'
    '"workspace_id":"aws_22222222222222222222222222222222"}'
).encode("ascii")


def test_exact_context_derivation_and_canonical_bytes() -> None:
    source = dict(ADMISSION)
    admission = validate_admission(source)
    context = derive_context(admission, "13")
    assert len(admission) == 13 and admission.keys() == ADMISSION_KEYS
    assert len(context) == 15 and context.keys() == CONTEXT_KEYS
    assert canonical_context_bytes(context) == CANONICAL
    assert (
        hashlib.sha256(canonical_context_bytes(context)).digest()
        == hashlib.sha256(CANONICAL).digest()
    )
    assert canonical_context_bytes(dict(reversed(list(context.items())))) == CANONICAL
    source["mode"] = "viewer"
    assert admission["mode"] == "writer"
    copy = validate_context(context)
    context["generation"] = "14"
    assert copy["generation"] == "11"


@pytest.mark.parametrize("key", sorted(ADMISSION_KEYS))
@pytest.mark.parametrize("change", ["missing", "wrong_type", "invalid"])
def test_every_admission_field_is_required_and_validated(key: str, change: str) -> None:
    value: dict[str, object] = dict(ADMISSION)
    if change == "missing":
        del value[key]
    else:
        value[key] = None if change == "wrong_type" else "invalid"
    with pytest.raises(WAWContextError):
        validate_admission(value)
    with pytest.raises(WAWContextError):
        derive_context(value, "13")


@pytest.mark.parametrize("key", sorted(CONTEXT_KEYS))
@pytest.mark.parametrize("change", ["missing", "wrong_type", "invalid"])
def test_every_context_field_is_required_and_validated(key: str, change: str) -> None:
    value: dict[str, object] = dict(derive_context(ADMISSION, "13"))
    if change == "missing":
        del value[key]
    else:
        value[key] = None if change == "wrong_type" else "invalid"
    with pytest.raises(WAWContextError):
        canonical_context_bytes(value)


@pytest.mark.parametrize(
    "extra", ["context", "origin", "ticket", "mode", "protocol_version", "cursor"]
)
def test_context_rejects_extensions(extra: str) -> None:
    value = derive_context(ADMISSION, "13")
    value[extra] = "x"
    with pytest.raises(WAWContextError):
        validate_context(value)


@pytest.mark.parametrize("key", sorted(U64_KEYS | {"runtime_epoch"}))
@pytest.mark.parametrize(
    "invalid", [True, 1, 1.0, "0", "01", "-1", "+1", "1e1", " 1", "1\n", "18446744073709551616"]
)
def test_uint64s_never_coerce_or_round(key: str, invalid: object) -> None:
    value: dict[str, object] = dict(derive_context(ADMISSION, "13"))
    value[key] = invalid
    with pytest.raises(WAWContextError):
        validate_context(value)


@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_zero_hex_digest_and_maximum_u64_are_valid_grammar(agent: str) -> None:
    value = dict(ADMISSION, agent_type=agent, binding_digest="0" * 64)
    for key in U64_KEYS:
        value[key] = "18446744073709551615"
    context = derive_context(value, "18446744073709551615")
    assert validate_context(context) == context


@pytest.mark.parametrize("value", [None, [], {}, {**ADMISSION, "extra": "x"}])
def test_admission_does_not_accept_missing_or_extra_objects(value: object) -> None:
    with pytest.raises(WAWContextError):
        validate_admission(value)


@pytest.mark.parametrize("version", [True, "1", 1.0, 0, 2])
def test_context_version_is_exact_integer(version: object) -> None:
    context: dict[str, object] = dict(derive_context(ADMISSION, "13"))
    context["crypto_envelope_version"] = version
    with pytest.raises(WAWContextError):
        validate_context(context)
