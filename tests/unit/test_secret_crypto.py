from __future__ import annotations

import inspect
from dataclasses import replace

import pytest
import rfc8785
from agentbox_runtime.secret_crypto import (
    _b64url_decode,
    _b64url_encode,
    _SealedSecretEnvelope,
    _SecretEnvelopeCodec,
    derive_key_id,
    run_secret_crypto_self_test,
)
from agentbox_runtime.secret_store_models import SecretStoreError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

RUNTIME_ID = "rti_11111111111111111111111111111111"
CREDENTIAL_ID = "crd_22222222222222222222222222222222"


class SequenceEntropy:
    def __init__(self) -> None:
        self.calls: list[int] = []
        self._counter = 1

    def __call__(self, size: int) -> bytes:
        self.calls.append(size)
        value = bytes([self._counter]) * size
        self._counter += 1
        return value


def _codec(
    root: bytes = b"R" * 32, *, entropy: SequenceEntropy | None = None
) -> _SecretEnvelopeCodec:
    return _SecretEnvelopeCodec(
        root,
        runtime_installation_id=RUNTIME_ID,
        kek_key_id=derive_key_id(root),
        entropy=entropy or SequenceEntropy(),
    )


def _envelope() -> tuple[_SecretEnvelopeCodec, _SealedSecretEnvelope]:
    codec = _codec()
    envelope = codec.seal_for_internal_verification(
        credential_id=CREDENTIAL_ID,
        credential_kind="api_key",
        secret_version=1,
        plaintext=b"synthetic-provider-value",
    )
    return codec, envelope


def test_aes256gcm_matches_published_nist_empty_plaintext_vector() -> None:
    key = bytes.fromhex("00" * 32)
    nonce = bytes.fromhex("000000000000000000000000")
    assert AESGCM(key).encrypt(nonce, b"", None).hex() == "530f8afbc74536b9a963b4f1c4cb738b"


def test_rfc8785_matches_canonical_public_example() -> None:
    assert rfc8785.dumps({"key": "value", "another-key": 2}) == (b'{"another-key":2,"key":"value"}')


def test_envelope_round_trip_uses_independent_material_and_redacts_repr() -> None:
    entropy = SequenceEntropy()
    codec = _codec(entropy=entropy)
    envelope = codec.seal_for_internal_verification(
        credential_id=CREDENTIAL_ID,
        credential_kind="api_key",
        secret_version=7,
        plaintext=b"synthetic-provider-value",
    )

    assert codec.open_for_internal_verification(envelope) == b"synthetic-provider-value"
    assert entropy.calls == [16, 16, 32, 12, 12]
    assert envelope.payload_nonce != envelope.wrap_nonce
    assert envelope.secret_record_id.startswith("sec_")
    assert envelope.dek_envelope_id.startswith("dek_")
    assert repr(envelope) == "<_SealedSecretEnvelope redacted>"
    assert "synthetic-provider-value" not in repr(envelope)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("envelope_schema", "agentbox.provider-secret-envelope.v2"),
        ("algorithm_id", "unknown"),
        ("runtime_installation_id", "rti_33333333333333333333333333333333"),
        ("credential_id", "crd_33333333333333333333333333333333"),
        ("secret_record_id", "sec_33333333333333333333333333333333"),
        ("secret_version", 2),
        ("dek_envelope_id", "dek_33333333333333333333333333333333"),
        ("kek_key_id", "3" * 32),
        ("kek_key_version", 2),
    ),
)
def test_identity_algorithm_schema_and_version_transplants_fail(field: str, value: object) -> None:
    codec, envelope = _envelope()
    with pytest.raises(SecretStoreError, match="SECRET_STORE_INTEGRITY_FAILED"):
        codec.open_for_internal_verification(
            replace(envelope, **{field: value})  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "field",
    ("payload_nonce", "payload_ciphertext", "payload_aad", "wrap_nonce", "wrapped_dek", "wrap_aad"),
)
def test_modified_envelope_binary_fields_fail_closed(field: str) -> None:
    codec, envelope = _envelope()
    original = getattr(envelope, field)
    replacement = ("A" if original[0] != "A" else "B") + original[1:]
    with pytest.raises(SecretStoreError, match="SECRET_STORE_INTEGRITY_FAILED"):
        codec.open_for_internal_verification(replace(envelope, **{field: replacement}))


def test_wrong_root_key_fails_closed() -> None:
    _codec_one, envelope = _envelope()
    wrong_root = b"W" * 32
    wrong_codec = _SecretEnvelopeCodec(
        wrong_root,
        runtime_installation_id=RUNTIME_ID,
        kek_key_id=envelope.kek_key_id,
    )
    with pytest.raises(SecretStoreError, match="SECRET_STORE_INTEGRITY_FAILED"):
        wrong_codec.open_for_internal_verification(envelope)


@pytest.mark.parametrize(
    "plaintext",
    (
        b"",
        b"x" * 16_385,
        b"line\nfeed",
        b"carriage\rreturn",
        b"nul\x00byte",
        b"control\x1f",
        "unicode-雪".encode(),
    ),
)
def test_plaintext_contract_rejects_invalid_values(plaintext: bytes) -> None:
    with pytest.raises(SecretStoreError, match="SECRET_STORE_INTEGRITY_FAILED"):
        _codec().seal_for_internal_verification(
            credential_id=CREDENTIAL_ID,
            credential_kind="api_key",
            secret_version=1,
            plaintext=plaintext,
        )


def test_plaintext_contract_accepts_exact_visible_ascii_bounds() -> None:
    for plaintext in (b"!", b"~" * 16_384):
        codec = _codec()
        envelope = codec.seal_for_internal_verification(
            credential_id=CREDENTIAL_ID,
            credential_kind="api_key",
            secret_version=1,
            plaintext=plaintext,
        )
        assert codec.open_for_internal_verification(envelope) == plaintext


@pytest.mark.parametrize("root", (b"", b"x" * 31, b"x" * 33))
def test_invalid_root_key_length_is_rejected(root: bytes) -> None:
    with pytest.raises(SecretStoreError, match="SECRET_STORE_INTEGRITY_FAILED"):
        derive_key_id(root)


@pytest.mark.parametrize("encoded", ("YQ==", " YQ", "YQ\n", "YQ+", "YQ/", "Y"))
def test_base64url_decoder_rejects_noncanonical_input(encoded: str) -> None:
    with pytest.raises(SecretStoreError, match="SECRET_STORE_INTEGRITY_FAILED"):
        _b64url_decode(encoded, maximum=32)


def test_base64url_has_one_unpadded_canonical_round_trip() -> None:
    encoded = _b64url_encode(b"\x00\xffcanonical")
    assert "=" not in encoded
    assert _b64url_decode(encoded, maximum=32) == b"\x00\xffcanonical"


def test_internal_seal_api_exposes_no_nonce_or_secret_identity_input() -> None:
    parameters = inspect.signature(_SecretEnvelopeCodec.seal_for_internal_verification).parameters
    assert "nonce" not in parameters
    assert "secret_record_id" not in parameters
    assert "dek_envelope_id" not in parameters


def test_internal_crypto_self_test_returns_only_boolean() -> None:
    result = run_secret_crypto_self_test()
    assert result is True
    assert type(result) is bool
