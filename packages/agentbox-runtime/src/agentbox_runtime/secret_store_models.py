"""Closed, non-secret models for the Runtime Provider Secret Store foundation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

KEYSET_SCHEMA = "agentbox.provider-secret-keyset.v1"
STORE_SCHEMA = "agentbox.provider-secret-store.v1"
ENVELOPE_SCHEMA = "agentbox.provider-secret-envelope.v1"
ALGORITHM_ID = "A256GCM-HKDF-SHA256-v1"
KEYSET_MAX_BYTES = 16 * 1024
KEY_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


class SecretStoreHealthState(StrEnum):
    UNINITIALIZED = "UNINITIALIZED"
    HEALTHY = "HEALTHY"
    UNAVAILABLE = "UNAVAILABLE"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"


class SecretStoreFindingCode(StrEnum):
    SECRET_STORE_UNINITIALIZED = "SECRET_STORE_UNINITIALIZED"
    SECRET_STORE_PERMISSION_INVALID = "SECRET_STORE_PERMISSION_INVALID"
    SECRET_STORE_KEY_MISSING = "SECRET_STORE_KEY_MISSING"
    SECRET_STORE_KEYSET_INVALID = "SECRET_STORE_KEYSET_INVALID"
    SECRET_STORE_INTEGRITY_FAILED = "SECRET_STORE_INTEGRITY_FAILED"
    SECRET_STORE_FORMAT_UNSUPPORTED = "SECRET_STORE_FORMAT_UNSUPPORTED"
    SECRET_STORE_NEEDS_ATTENTION = "SECRET_STORE_NEEDS_ATTENTION"
    SECRET_STORE_UNAVAILABLE = "SECRET_STORE_UNAVAILABLE"
    SECRET_STORE_ROTATION_REQUIRED = "SECRET_STORE_ROTATION_REQUIRED"


class SecretStoreInitializeResult(StrEnum):
    INITIALIZED = "INITIALIZED"
    ALREADY_INITIALIZED = "ALREADY_INITIALIZED"
    SECRET_STORE_NEEDS_ATTENTION = "SECRET_STORE_NEEDS_ATTENTION"
    SECRET_STORE_UNAVAILABLE = "SECRET_STORE_UNAVAILABLE"


class SecretKeyState(StrEnum):
    CURRENT = "current"


@dataclass(frozen=True)
class SecretStoreHealth:
    state: SecretStoreHealthState
    finding_codes: tuple[SecretStoreFindingCode, ...]
    store_schema: str | None = None
    algorithm_schema: str | None = None


@dataclass(frozen=True)
class SecretKeyset:
    schema: str
    current_key_id: str
    current_key_version: int
    current_key_state: SecretKeyState

    @classmethod
    def initial(cls, key_id: str) -> SecretKeyset:
        if KEY_ID_PATTERN.fullmatch(key_id) is None:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_KEYSET_INVALID)
        return cls(
            schema=KEYSET_SCHEMA,
            current_key_id=key_id,
            current_key_version=1,
            current_key_state=SecretKeyState.CURRENT,
        )

    def to_bytes(self) -> bytes:
        value = {
            "current_key_id": self.current_key_id,
            "current_key_state": self.current_key_state.value,
            "current_key_version": self.current_key_version,
            "schema": self.schema,
        }
        payload = (
            json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
        ).encode("ascii")
        if len(payload) > KEYSET_MAX_BYTES:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_KEYSET_INVALID)
        return payload

    @classmethod
    def from_bytes(cls, payload: bytes) -> SecretKeyset:
        if not payload or len(payload) > KEYSET_MAX_BYTES:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_KEYSET_INVALID)

        def exact_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            value: dict[str, Any] = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("duplicate key")
                value[key] = item
            return value

        try:
            value = json.loads(payload.decode("ascii"), object_pairs_hook=exact_object)
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_KEYSET_INVALID) from exc
        expected = {
            "schema",
            "current_key_id",
            "current_key_version",
            "current_key_state",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_KEYSET_INVALID)
        schema = value["schema"]
        key_id = value["current_key_id"]
        key_version = value["current_key_version"]
        key_state = value["current_key_state"]
        if schema != KEYSET_SCHEMA:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_FORMAT_UNSUPPORTED)
        if (
            not isinstance(key_id, str)
            or KEY_ID_PATTERN.fullmatch(key_id) is None
            or type(key_version) is not int
            or key_version != 1
            or key_state != SecretKeyState.CURRENT.value
        ):
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_KEYSET_INVALID)
        keyset = cls(schema, key_id, key_version, SecretKeyState(key_state))
        if keyset.to_bytes() != payload:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_KEYSET_INVALID)
        return keyset


class SecretStoreError(RuntimeError):
    """Sanitized Secret Store error containing only a closed finding code."""

    def __init__(self, code: SecretStoreFindingCode) -> None:
        super().__init__(code.value)
        self.code = code
