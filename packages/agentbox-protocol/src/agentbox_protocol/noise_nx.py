"""Small, fixed Noise NX implementation for the WAW transport seam.

This module implements only ``Noise_NX_25519_AESGCM_SHA256`` (Noise revision
34).  It deliberately has no socket, WebSocket, ABWS, or application-payload
knowledge.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PROTOCOL_NAME = b"Noise_NX_25519_AESGCM_SHA256"
MAX_MESSAGE_SIZE = 65535
MAX_NONCE = 2**64 - 1
MAX_ASSOCIATED_DATA = 65535
_EMPTY = b""


class NoiseNXError(RuntimeError):
    """A Noise state, key, message, or authentication operation is invalid."""


_P = ParamSpec("_P")
_R = TypeVar("_R")


def _locked(method: Callable[..., _R]) -> Callable[..., _R]:
    @wraps(method)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> _R:
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


def _key(value: bytes, name: str) -> X25519PrivateKey:
    if not isinstance(value, bytes) or len(value) != 32:
        raise NoiseNXError(f"{name} must be exactly 32 bytes")
    try:
        return X25519PrivateKey.from_private_bytes(value)
    except (TypeError, ValueError) as exc:
        raise NoiseNXError(f"{name} is invalid") from exc


def _public(value: X25519PrivateKey) -> bytes:
    return value.public_key().public_bytes_raw()


def _dh(private: X25519PrivateKey, peer: bytes) -> bytes:
    if not isinstance(peer, bytes) or len(peer) != 32:
        raise NoiseNXError("X25519 public key is invalid")
    try:
        return private.exchange(X25519PublicKey.from_public_bytes(peer))
    except (TypeError, ValueError) as exc:
        raise NoiseNXError("X25519 DH failed") from exc


def _hkdf(chaining_key: bytes, material: bytes) -> tuple[bytes, bytes]:
    temp = hmac.new(chaining_key, material, hashlib.sha256).digest()
    first = hmac.new(temp, b"\x01", hashlib.sha256).digest()
    second = hmac.new(temp, first + b"\x02", hashlib.sha256).digest()
    return first, second


class CipherState:
    """One direction of a Noise transport split; key and nonce are private."""

    __slots__ = ("__key", "__nonce", "__closed", "__lock")

    def __init__(self, key: bytes) -> None:
        if not isinstance(key, bytes) or len(key) != 32:
            raise NoiseNXError("CipherState key is invalid")
        self.__key = key
        self.__nonce = 0
        self.__closed = False
        self.__lock = threading.RLock()

    @property
    def nonce(self) -> int:
        with self.__lock:
            return self.__nonce

    def encrypt(self, plaintext: object, associated_data: object = b"") -> bytes:
        with self.__lock:
            plaintext, associated_data = self._ready(plaintext, associated_data)
            nonce = b"\0\0\0\0" + self.__nonce.to_bytes(8, "big")
            try:
                result = AESGCM(self.__key).encrypt(nonce, plaintext, associated_data)
            except Exception as exc:
                self.destroy()
                raise NoiseNXError("Noise encryption failed") from exc
            self.__advance()
            return result

    def decrypt(self, ciphertext: object, associated_data: object = b"") -> bytes:
        with self.__lock:
            ciphertext, associated_data = self._ready(ciphertext, associated_data, decrypt=True)
            nonce = b"\0\0\0\0" + self.__nonce.to_bytes(8, "big")
            try:
                result = AESGCM(self.__key).decrypt(nonce, ciphertext, associated_data)
            except (InvalidTag, ValueError, TypeError) as exc:
                self.destroy()
                raise NoiseNXError("Noise authentication failed") from exc
            self.__advance()
            return result

    def destroy(self) -> None:
        with self.__lock:
            self.__closed = True
            self.__key = b""

    def _ready(
        self, value: object, associated_data: object, *, decrypt: bool = False
    ) -> tuple[bytes, bytes]:
        if self.__closed:
            raise NoiseNXError("CipherState is closed")
        if not isinstance(value, bytes) or not isinstance(associated_data, bytes):
            self.destroy()
            raise NoiseNXError("CipherState inputs must be bytes")
        if len(associated_data) > MAX_ASSOCIATED_DATA:
            self.destroy()
            raise NoiseNXError("Noise associated data exceeds 65535 bytes")
        if len(value) > MAX_MESSAGE_SIZE or (not decrypt and len(value) > MAX_MESSAGE_SIZE - 16):
            self.destroy()
            raise NoiseNXError("Noise message exceeds 65535 bytes")
        if decrypt and len(value) < 16:
            self.destroy()
            raise NoiseNXError("Noise ciphertext is shorter than its authentication tag")
        if self.__nonce >= MAX_NONCE:
            self.destroy()
            raise NoiseNXError("Noise nonce exhausted")
        return value, associated_data

    def __advance(self) -> None:
        self.__nonce += 1

    def __repr__(self) -> str:
        return "<CipherState redacted>"


@dataclass(frozen=True)
class NoiseTransport:
    send: CipherState
    receive: CipherState
    handshake_hash: bytes
    remote_static_public_key: bytes

    def destroy(self) -> None:
        self.send.destroy()
        self.receive.destroy()


class _Handshake:
    def __init__(self, prologue: bytes) -> None:
        if not isinstance(prologue, bytes) or len(prologue) > MAX_MESSAGE_SIZE:
            raise NoiseNXError("prologue is invalid")
        self._h = PROTOCOL_NAME + b"\0" * (32 - len(PROTOCOL_NAME))
        self._ck = self._h
        self._mix_hash(prologue)
        self._closed = False
        self._transport: NoiseTransport | None = None
        self._cipher: CipherState | None = None
        self._lock = threading.RLock()

    def _invalid(self, message: str) -> NoiseNXError:
        self.destroy()
        return NoiseNXError(message)

    def _mix_hash(self, data: bytes) -> None:
        self._h = hashlib.sha256(self._h + data).digest()

    def _mix_key(self, material: bytes) -> None:
        self._ck, key = _hkdf(self._ck, material)
        if self._cipher is not None:
            self._cipher.destroy()
        self._cipher = CipherState(key)

    def _encrypt_and_hash(self, payload: bytes) -> bytes:
        result = payload if self._cipher is None else self._cipher.encrypt(payload, self._h)
        self._mix_hash(result)
        return result

    def _decrypt_and_hash(self, payload: bytes) -> bytes:
        cipher = self._cipher
        result = payload if cipher is None else cipher.decrypt(payload, self._h)
        self._mix_hash(payload)
        return result

    @_locked
    def take_transport(self) -> NoiseTransport:
        if self._closed or self._transport is None:
            raise NoiseNXError("Noise transport is unavailable")
        result = self._transport
        self._transport = None
        cipher = getattr(self, "_cipher", None)
        if cipher is not None:
            cipher.destroy()
            self._cipher = None
        self._clear_handshake_material()
        self._closed = True
        return result

    @_locked
    def destroy(self) -> None:
        self._closed = True
        cipher = getattr(self, "_cipher", None)
        if cipher is not None:
            cipher.destroy()
        if self._transport is not None:
            self._transport.destroy()
        self._transport = None
        self._clear_handshake_material()

    def _clear_handshake_material(self) -> None:
        self._ck = b""
        self._h = b""
        for name in ("_e", "_s", "_re"):
            if hasattr(self, name):
                setattr(self, name, None)

    def _finish(self, remote_static: bytes, initiator: bool) -> None:
        k1, k2 = _hkdf(self._ck, _EMPTY)
        send, receive = (
            (CipherState(k1), CipherState(k2)) if initiator else (CipherState(k2), CipherState(k1))
        )
        self._transport = NoiseTransport(send, receive, self._h, remote_static)

    def _check_message(self, raw: bytes) -> None:
        if self._closed or not isinstance(raw, bytes) or len(raw) > MAX_MESSAGE_SIZE:
            raise self._invalid("Noise handshake message is invalid")


class NXInitiator(_Handshake):
    def __init__(self, prologue: bytes, ephemeral_private_key: bytes | None = None) -> None:
        super().__init__(prologue)
        self._e = (
            _key(ephemeral_private_key, "ephemeral_private_key")
            if ephemeral_private_key is not None
            else X25519PrivateKey.generate()
        )
        self._re: bytes | None = None
        self._message1_written = False

    @_locked
    def write_message1(self, payload: bytes = b"") -> bytes:
        if (
            self._closed
            or self._message1_written
            or not isinstance(payload, bytes)
            or len(payload) > MAX_MESSAGE_SIZE - 32
        ):
            raise self._invalid("message1 is not writable")
        self._message1_written = True
        result = _public(self._e) + payload
        self._mix_hash(_public(self._e))
        self._mix_hash(payload)
        return result

    @_locked
    def read_message2(self, raw: bytes) -> bytes:
        self._check_message(raw)
        if not self._message1_written or self._re is not None or len(raw) < 32 + 48:
            raise self._invalid("message2 is invalid or out of order")
        self._re = raw[:32]
        self._mix_hash(self._re)
        try:
            self._mix_key(_dh(self._e, self._re))
            remote_static = self._decrypt_and_hash(raw[32:80])
            if len(remote_static) != 32:
                raise NoiseNXError("responder static key is invalid")
            self._mix_key(_dh(self._e, remote_static))
            payload = self._decrypt_and_hash(raw[80:])
        except NoiseNXError:
            self.destroy()
            raise
        self._finish(remote_static, True)
        return payload


class NXResponder(_Handshake):
    def __init__(
        self, prologue: bytes, static_private_key: bytes, ephemeral_private_key: bytes | None = None
    ) -> None:
        super().__init__(prologue)
        self._s = _key(static_private_key, "static_private_key")
        self._e = (
            _key(ephemeral_private_key, "ephemeral_private_key")
            if ephemeral_private_key is not None
            else None
        )
        self._re: bytes | None = None
        self._message2_written = False

    @_locked
    def read_message1(self, raw: bytes) -> bytes:
        self._check_message(raw)
        if self._re is not None or len(raw) < 32:
            raise self._invalid("message1 is invalid or out of order")
        self._re = raw[:32]
        self._mix_hash(self._re)
        payload = raw[32:]
        self._mix_hash(payload)
        return payload

    @_locked
    def write_message2(self, payload: bytes = b"") -> bytes:
        if (
            self._closed
            or self._message2_written
            or self._re is None
            or not isinstance(payload, bytes)
            or len(payload) > MAX_MESSAGE_SIZE - 96
        ):
            raise self._invalid("message2 is not writable")
        self._message2_written = True
        self._e = self._e or X25519PrivateKey.generate()
        e_public = _public(self._e)
        self._mix_hash(e_public)
        try:
            self._mix_key(_dh(self._e, self._re))
            encrypted_static = self._encrypt_and_hash(_public(self._s))
            self._mix_key(_dh(self._s, self._re))
            encrypted_payload = self._encrypt_and_hash(payload)
        except NoiseNXError:
            self.destroy()
            raise
        self._finish(b"", False)
        return e_public + encrypted_static + encrypted_payload


__all__ = [
    "CipherState",
    "MAX_MESSAGE_SIZE",
    "NoiseNXError",
    "NoiseTransport",
    "NXInitiator",
    "NXResponder",
    "PROTOCOL_NAME",
]
