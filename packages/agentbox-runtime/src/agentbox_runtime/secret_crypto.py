"""Private envelope primitives for the Runtime-owned Provider Secret Store."""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field

import rfc8785
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from agentbox_runtime.secret_store_models import (
    ALGORITHM_ID,
    ENVELOPE_SCHEMA,
    SecretStoreError,
    SecretStoreFindingCode,
)

ROOT_KEY_BYTES = 32
DEK_BYTES = 32
NONCE_BYTES = 12
GCM_TAG_BYTES = 16
MAX_SECRET_PLAINTEXT_BYTES = 16_384
MAX_CANONICAL_AAD_BYTES = 4_096
HKDF_INFO = b"agentbox/provider-secret/kek/v1"
HKDF_SALT_DOMAIN = b"agentbox/provider-secret/hkdf-salt/v1"
KEY_ID_DOMAIN = b"agentbox/provider-secret/key-id/v1"
_IDENTITY = {
    "runtime_installation_id": re.compile(r"rti_[0-9a-f]{32}"),
    "credential_id": re.compile(r"crd_[0-9a-f]{32}"),
    "secret_record_id": re.compile(r"sec_[0-9a-f]{32}"),
    "dek_envelope_id": re.compile(r"dek_[0-9a-f]{32}"),
}
_CREDENTIAL_KINDS = frozenset({"api_key"})
_B64URL = re.compile(r"[A-Za-z0-9_-]+")


_Entropy = Callable[[int], bytes]


def derive_key_id(root_key: bytes) -> str:
    _require_exact_bytes(root_key, ROOT_KEY_BYTES)
    return hashlib.sha256(KEY_ID_DOMAIN + root_key).hexdigest()[:32]


def _require_identity(name: str, value: str) -> None:
    pattern = _IDENTITY[name]
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)


def _require_exact_bytes(value: bytes, expected: int) -> None:
    if not isinstance(value, bytes) or len(value) != expected:
        raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)


def _validate_plaintext(value: bytes) -> None:
    if (
        not isinstance(value, bytes)
        or not 1 <= len(value) <= MAX_SECRET_PLAINTEXT_BYTES
        or any(byte < 0x20 or byte > 0x7E for byte in value)
    ):
        raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str, *, expected: int | None = None, maximum: int) -> bytes:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > ((maximum + 2) // 3) * 4
        or _B64URL.fullmatch(value) is None
        or "=" in value
    ):
        raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
    padding = "=" * ((4 - len(value) % 4) % 4)
    try:
        decoded = base64.b64decode(value + padding, altchars=b"-_", validate=True)
    except (ValueError, binascii.Error) as exc:
        raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED) from exc
    if len(decoded) > maximum or (expected is not None and len(decoded) != expected):
        raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
    if _b64url_encode(decoded) != value:
        raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
    return decoded


def _canonicalize(value: dict[str, str | int]) -> bytes:
    try:
        encoded = rfc8785.dumps(value)
    except (rfc8785.CanonicalizationError, TypeError, ValueError) as exc:
        raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED) from exc
    if not encoded or len(encoded) > MAX_CANONICAL_AAD_BYTES:
        raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
    return encoded


def _payload_aad(
    *,
    runtime_installation_id: str,
    credential_id: str,
    secret_record_id: str,
    credential_kind: str,
    secret_version: int,
    dek_envelope_id: str,
) -> bytes:
    return _canonicalize(
        {
            "algorithm_id": ALGORITHM_ID,
            "credential_id": credential_id,
            "credential_kind": credential_kind,
            "dek_envelope_id": dek_envelope_id,
            "envelope_schema": ENVELOPE_SCHEMA,
            "runtime_installation_id": runtime_installation_id,
            "secret_record_id": secret_record_id,
            "secret_version": secret_version,
        }
    )


def _wrap_aad(
    *,
    runtime_installation_id: str,
    secret_record_id: str,
    secret_version: int,
    dek_envelope_id: str,
    kek_key_id: str,
    kek_key_version: int,
) -> bytes:
    return _canonicalize(
        {
            "algorithm_id": ALGORITHM_ID,
            "dek_envelope_id": dek_envelope_id,
            "envelope_schema": ENVELOPE_SCHEMA,
            "kek_key_id": kek_key_id,
            "kek_key_version": kek_key_version,
            "runtime_installation_id": runtime_installation_id,
            "secret_record_id": secret_record_id,
            "secret_version": secret_version,
        }
    )


def _derive_kek(root_key: bytes, runtime_installation_id: str) -> bytes:
    _require_exact_bytes(root_key, ROOT_KEY_BYTES)
    _require_identity("runtime_installation_id", runtime_installation_id)
    salt = hashlib.sha256(HKDF_SALT_DOMAIN + runtime_installation_id.encode("ascii")).digest()
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=HKDF_INFO,
    ).derive(root_key)


@dataclass(frozen=True, repr=False)
class _SealedSecretEnvelope:
    envelope_schema: str
    algorithm_id: str
    runtime_installation_id: str
    credential_id: str
    credential_kind: str
    secret_record_id: str
    secret_version: int
    dek_envelope_id: str
    kek_key_id: str
    kek_key_version: int
    payload_nonce: str = field(repr=False)
    payload_ciphertext: str = field(repr=False)
    payload_aad: str = field(repr=False)
    wrap_nonce: str = field(repr=False)
    wrapped_dek: str = field(repr=False)
    wrap_aad: str = field(repr=False)

    def __repr__(self) -> str:
        return "<_SealedSecretEnvelope redacted>"


def _validate_envelope_structure(envelope: _SealedSecretEnvelope) -> None:
    if (
        envelope.envelope_schema != ENVELOPE_SCHEMA
        or envelope.algorithm_id != ALGORITHM_ID
        or envelope.credential_kind not in _CREDENTIAL_KINDS
        or type(envelope.secret_version) is not int
        or envelope.secret_version < 1
        or re.fullmatch(r"[0-9a-f]{32}", envelope.kek_key_id) is None
        or type(envelope.kek_key_version) is not int
        or envelope.kek_key_version < 1
    ):
        raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
    for name, value in (
        ("runtime_installation_id", envelope.runtime_installation_id),
        ("credential_id", envelope.credential_id),
        ("secret_record_id", envelope.secret_record_id),
        ("dek_envelope_id", envelope.dek_envelope_id),
    ):
        _require_identity(name, value)
    expected_payload_aad = _payload_aad(
        runtime_installation_id=envelope.runtime_installation_id,
        credential_id=envelope.credential_id,
        secret_record_id=envelope.secret_record_id,
        credential_kind=envelope.credential_kind,
        secret_version=envelope.secret_version,
        dek_envelope_id=envelope.dek_envelope_id,
    )
    expected_wrap_aad = _wrap_aad(
        runtime_installation_id=envelope.runtime_installation_id,
        secret_record_id=envelope.secret_record_id,
        secret_version=envelope.secret_version,
        dek_envelope_id=envelope.dek_envelope_id,
        kek_key_id=envelope.kek_key_id,
        kek_key_version=envelope.kek_key_version,
    )
    if (
        _b64url_decode(envelope.payload_aad, maximum=MAX_CANONICAL_AAD_BYTES)
        != expected_payload_aad
        or _b64url_decode(envelope.wrap_aad, maximum=MAX_CANONICAL_AAD_BYTES) != expected_wrap_aad
    ):
        raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
    _b64url_decode(envelope.payload_nonce, expected=NONCE_BYTES, maximum=NONCE_BYTES)
    _b64url_decode(envelope.wrap_nonce, expected=NONCE_BYTES, maximum=NONCE_BYTES)
    payload_ciphertext = _b64url_decode(
        envelope.payload_ciphertext,
        maximum=MAX_SECRET_PLAINTEXT_BYTES + GCM_TAG_BYTES,
    )
    _b64url_decode(
        envelope.wrapped_dek,
        expected=DEK_BYTES + GCM_TAG_BYTES,
        maximum=DEK_BYTES + GCM_TAG_BYTES,
    )
    if (
        not GCM_TAG_BYTES + 1
        <= len(payload_ciphertext)
        <= (MAX_SECRET_PLAINTEXT_BYTES + GCM_TAG_BYTES)
    ):
        raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)


class _SecretEnvelopeCodec:
    """Private action-bound codec; this module exposes no generic Secret service."""

    def __init__(
        self,
        root_key: bytes,
        *,
        runtime_installation_id: str,
        kek_key_id: str,
        kek_key_version: int = 1,
        entropy: _Entropy = os.urandom,
    ) -> None:
        _require_exact_bytes(root_key, ROOT_KEY_BYTES)
        _require_identity("runtime_installation_id", runtime_installation_id)
        if (
            re.fullmatch(r"[0-9a-f]{32}", kek_key_id) is None
            or type(kek_key_version) is not int
            or kek_key_version < 1
        ):
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
        self._root_key = bytearray(root_key)
        self._runtime_installation_id = runtime_installation_id
        self._kek_key_id = kek_key_id
        self._kek_key_version = kek_key_version
        self._entropy = entropy

    def _clear_root_key(self) -> None:
        """Best-effort cleanup for the codec's private mutable key copy."""
        for index in range(len(self._root_key)):
            self._root_key[index] = 0

    def _random(self, size: int) -> bytes:
        try:
            value = self._entropy(size)
        except Exception as exc:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_UNAVAILABLE) from exc
        if not isinstance(value, bytes) or len(value) != size:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_UNAVAILABLE)
        return value

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}_{self._random(16).hex()}"

    def seal_for_internal_verification(
        self,
        *,
        credential_id: str,
        credential_kind: str,
        secret_version: int,
        plaintext: bytes,
    ) -> _SealedSecretEnvelope:
        _require_identity("credential_id", credential_id)
        if credential_kind not in _CREDENTIAL_KINDS:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
        if type(secret_version) is not int or secret_version < 1:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
        _validate_plaintext(plaintext)
        secret_record_id = self._new_id("sec")
        dek_envelope_id = self._new_id("dek")
        dek = bytearray(self._random(DEK_BYTES))
        payload_nonce = self._random(NONCE_BYTES)
        wrap_nonce = self._random(NONCE_BYTES)
        kek = bytearray()
        plain_copy = bytearray(plaintext)
        try:
            payload_aad = _payload_aad(
                runtime_installation_id=self._runtime_installation_id,
                credential_id=credential_id,
                secret_record_id=secret_record_id,
                credential_kind=credential_kind,
                secret_version=secret_version,
                dek_envelope_id=dek_envelope_id,
            )
            wrap_aad = _wrap_aad(
                runtime_installation_id=self._runtime_installation_id,
                secret_record_id=secret_record_id,
                secret_version=secret_version,
                dek_envelope_id=dek_envelope_id,
                kek_key_id=self._kek_key_id,
                kek_key_version=self._kek_key_version,
            )
            kek.extend(_derive_kek(bytes(self._root_key), self._runtime_installation_id))
            payload_ciphertext = AESGCM(bytes(dek)).encrypt(
                payload_nonce, bytes(plain_copy), payload_aad
            )
            wrapped_dek = AESGCM(bytes(kek)).encrypt(wrap_nonce, bytes(dek), wrap_aad)
            if (
                len(payload_ciphertext) != len(plaintext) + GCM_TAG_BYTES
                or len(wrapped_dek) != DEK_BYTES + GCM_TAG_BYTES
            ):
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
            return _SealedSecretEnvelope(
                envelope_schema=ENVELOPE_SCHEMA,
                algorithm_id=ALGORITHM_ID,
                runtime_installation_id=self._runtime_installation_id,
                credential_id=credential_id,
                credential_kind=credential_kind,
                secret_record_id=secret_record_id,
                secret_version=secret_version,
                dek_envelope_id=dek_envelope_id,
                kek_key_id=self._kek_key_id,
                kek_key_version=self._kek_key_version,
                payload_nonce=_b64url_encode(payload_nonce),
                payload_ciphertext=_b64url_encode(payload_ciphertext),
                payload_aad=_b64url_encode(payload_aad),
                wrap_nonce=_b64url_encode(wrap_nonce),
                wrapped_dek=_b64url_encode(wrapped_dek),
                wrap_aad=_b64url_encode(wrap_aad),
            )
        except SecretStoreError:
            raise
        except Exception as exc:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED) from exc
        finally:
            for index in range(len(dek)):
                dek[index] = 0
            for index in range(len(kek)):
                kek[index] = 0
            for index in range(len(plain_copy)):
                plain_copy[index] = 0

    def open_for_internal_verification(self, envelope: _SealedSecretEnvelope) -> bytes:
        _validate_envelope_structure(envelope)
        if (
            envelope.envelope_schema != ENVELOPE_SCHEMA
            or envelope.algorithm_id != ALGORITHM_ID
            or envelope.runtime_installation_id != self._runtime_installation_id
            or envelope.kek_key_id != self._kek_key_id
            or envelope.kek_key_version != self._kek_key_version
            or envelope.credential_kind not in _CREDENTIAL_KINDS
            or type(envelope.secret_version) is not int
            or envelope.secret_version < 1
        ):
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
        for name, value in (
            ("runtime_installation_id", envelope.runtime_installation_id),
            ("credential_id", envelope.credential_id),
            ("secret_record_id", envelope.secret_record_id),
            ("dek_envelope_id", envelope.dek_envelope_id),
        ):
            _require_identity(name, value)
        expected_payload_aad = _payload_aad(
            runtime_installation_id=envelope.runtime_installation_id,
            credential_id=envelope.credential_id,
            secret_record_id=envelope.secret_record_id,
            credential_kind=envelope.credential_kind,
            secret_version=envelope.secret_version,
            dek_envelope_id=envelope.dek_envelope_id,
        )
        expected_wrap_aad = _wrap_aad(
            runtime_installation_id=envelope.runtime_installation_id,
            secret_record_id=envelope.secret_record_id,
            secret_version=envelope.secret_version,
            dek_envelope_id=envelope.dek_envelope_id,
            kek_key_id=envelope.kek_key_id,
            kek_key_version=envelope.kek_key_version,
        )
        stored_payload_aad = _b64url_decode(envelope.payload_aad, maximum=MAX_CANONICAL_AAD_BYTES)
        stored_wrap_aad = _b64url_decode(envelope.wrap_aad, maximum=MAX_CANONICAL_AAD_BYTES)
        if stored_payload_aad != expected_payload_aad or stored_wrap_aad != expected_wrap_aad:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
        payload_nonce = _b64url_decode(
            envelope.payload_nonce, expected=NONCE_BYTES, maximum=NONCE_BYTES
        )
        wrap_nonce = _b64url_decode(envelope.wrap_nonce, expected=NONCE_BYTES, maximum=NONCE_BYTES)
        payload_ciphertext = _b64url_decode(
            envelope.payload_ciphertext,
            maximum=MAX_SECRET_PLAINTEXT_BYTES + GCM_TAG_BYTES,
        )
        wrapped_dek = _b64url_decode(
            envelope.wrapped_dek,
            expected=DEK_BYTES + GCM_TAG_BYTES,
            maximum=DEK_BYTES + GCM_TAG_BYTES,
        )
        if (
            not GCM_TAG_BYTES + 1
            <= len(payload_ciphertext)
            <= MAX_SECRET_PLAINTEXT_BYTES + GCM_TAG_BYTES
        ):
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
        kek = bytearray()
        dek = bytearray()
        try:
            kek.extend(_derive_kek(bytes(self._root_key), self._runtime_installation_id))
            dek.extend(AESGCM(bytes(kek)).decrypt(wrap_nonce, wrapped_dek, expected_wrap_aad))
            _require_exact_bytes(bytes(dek), DEK_BYTES)
            plaintext = AESGCM(bytes(dek)).decrypt(
                payload_nonce, payload_ciphertext, expected_payload_aad
            )
            _validate_plaintext(plaintext)
            return plaintext
        except (InvalidTag, ValueError, SecretStoreError) as exc:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED) from exc
        finally:
            for index in range(len(kek)):
                kek[index] = 0
            for index in range(len(dek)):
                dek[index] = 0


def run_secret_crypto_self_test() -> bool:
    """Exercise the frozen primitives in memory and return no sensitive material."""
    root = bytearray(os.urandom(ROOT_KEY_BYTES))
    plain = bytearray(base64.urlsafe_b64encode(os.urandom(24)).rstrip(b"="))
    opened = bytearray()
    codec: _SecretEnvelopeCodec | None = None
    try:
        key_id = derive_key_id(bytes(root))
        codec = _SecretEnvelopeCodec(
            bytes(root),
            runtime_installation_id="rti_00000000000000000000000000000000",
            kek_key_id=key_id,
        )
        envelope = codec.seal_for_internal_verification(
            credential_id="crd_00000000000000000000000000000000",
            credential_kind="api_key",
            secret_version=1,
            plaintext=bytes(plain),
        )
        opened.extend(codec.open_for_internal_verification(envelope))
        return opened == plain
    except SecretStoreError:
        return False
    finally:
        if codec is not None:
            codec._clear_root_key()
        for buffer in (root, plain, opened):
            for index in range(len(buffer)):
                buffer[index] = 0
