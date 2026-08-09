"""Password, opaque-token, CSRF, and security-redaction primitives."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import unicodedata
from collections.abc import Mapping
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type

from agentbox_core.errors import PasswordPolicyViolation

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "token",
    "secret",
    "cookie",
    "authorization",
    "csrf",
    "session",
    "private_key",
)
SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(password|passwd|token|secret|cookie|authorization|csrf|session)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)


class PasswordManager:
    """Argon2id hashing with one process-level dummy verifier."""

    def __init__(
        self,
        *,
        time_cost: int = 3,
        memory_cost: int = 65_536,
        parallelism: int = 2,
    ) -> None:
        self._hasher = PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            hash_len=32,
            salt_len=16,
            type=Type.ID,
        )
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(32))

    @property
    def dummy_hash(self) -> str:
        return self._dummy_hash

    def validate_new_password(self, password: str) -> None:
        if len(password) < 12 or len(password) > 1024:
            raise PasswordPolicyViolation()
        if password.casefold() in {
            "passwordpassword",
            "agentboxagentbox",
            "123456789012",
            "qwertyuiopas",
        }:
            raise PasswordPolicyViolation()

    def hash(self, password: str) -> str:
        self.validate_new_password(password)
        return self._hasher.hash(password)

    def verify(self, encoded_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(encoded_hash, password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False

    def needs_rehash(self, encoded_hash: str) -> bool:
        return self._hasher.check_needs_rehash(encoded_hash)


def normalize_username(username: str) -> str:
    normalized_display = unicodedata.normalize("NFKC", username).strip()
    if not USERNAME_PATTERN.fullmatch(normalized_display):
        raise ValueError("username must use 1-64 ASCII letters, digits, dot, underscore, or hyphen")
    return normalized_display.casefold()


def new_identifier(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(16)}"


def generate_session_token() -> str:
    """Return at least 256 bits of opaque entropy in URL-safe form."""
    return secrets.token_urlsafe(32)


def keyed_digest(application_secret: str, purpose: str, value: str) -> str:
    return hmac.new(
        application_secret.encode("utf-8"),
        f"{purpose}\0{value}".encode(),
        hashlib.sha256,
    ).hexdigest()


def derive_csrf_token(application_secret: str, session_id: str, token_hash: str) -> str:
    digest = hmac.new(
        application_secret.encode("utf-8"),
        f"csrf-token\0{session_id}\0{token_hash}".encode(),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def source_fingerprint(application_secret: str, source: str) -> str:
    return keyed_digest(application_secret, "login-source", source)[:24]


def is_sensitive_key(key: str) -> bool:
    lowered = key.casefold()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def redact_text(value: str, *, limit: int = 1024) -> str:
    bounded = value.replace("\r", " ").replace("\n", " ")[:limit]
    return SENSITIVE_ASSIGNMENT_PATTERN.sub(r"\1\2[REDACTED]", bounded)


def sanitize_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Allow only a small, non-secret, flat audit metadata object."""
    if metadata is None:
        return {}
    if len(metadata) > 16:
        raise ValueError("audit metadata has too many fields")
    sanitized: dict[str, Any] = {}
    for key, value in metadata.items():
        if len(key) > 64 or is_sensitive_key(key):
            raise ValueError("audit metadata contains a forbidden key")
        if value is None or isinstance(value, (bool, int)):
            sanitized[key] = value
        elif isinstance(value, str) and len(value) <= 256:
            sanitized[key] = value.replace("\r", " ").replace("\n", " ")
        else:
            raise ValueError("audit metadata values must be bounded scalars")
    return sanitized
