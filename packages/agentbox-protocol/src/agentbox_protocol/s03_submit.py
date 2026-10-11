"""Bounded, isolated synthetic S03 submit codec. Not an authenticated source.

Only the existing NX primitive is reused. Deterministic vectors have no admission
capability; the private responder seam always generates fresh session ephemerals.
"""

from __future__ import annotations

import base64
import hashlib
import re
from contextlib import suppress
from dataclasses import dataclass, fields
from typing import cast

from agentbox_core.kebui_observation import ConversationScope, parse_scope

from .noise_nx import NoiseTransport, NXResponder

CONTEXT_DOMAIN = b"agentbox-s03-submit/context/v1\x00"
PROLOGUE_DOMAIN = b"agentbox-s03-submit/noise-prologue/v1\x00"
AAD_DOMAIN = b"agentbox-s03-submit/aad/v1\x00"
CONFIRM_DOMAIN = b"agentbox-s03-submit/confirm/v1\x00"
READY_DOMAIN = b"agentbox-s03-submit/ready/v1\x00"
FRAME_DOMAIN = "agentbox-s03-submit/frame/v1"
ADAPTER_PROFILE = "kebui-synthetic-adapter-v1"
MAX_BODY_BYTES = 16384
MAX_FRAME_BYTES = 22031
MAX_CONTEXT_BYTES = 739
MAX_U64 = 2**64 - 1
RUNTIME_STATIC_PRIVATE = b"\xd0" * 32  # Published synthetic fixture, never a deployment key.
RUNTIME_PIN = bytes.fromhex("b25dc5485163369e179437bb72fe4bd4a142482682c302d66a3a2d4865c3fd0b")
SCOPE_FIELDS = tuple(field.name for field in fields(ConversationScope))
CONTEXT_FIELDS = SCOPE_FIELDS + (
    "execution_id",
    "request_id",
    "channel_id",
    "source_lease_id",
    "adapter_profile",
)
_KIND_LIMITS = {
    "KEY_INIT": (0, 32, 32),
    "KEY_ATTEST": (0, 96, 96),
    "KEY_CONFIRM": (0, 111, 111),
    "KEY_READY": (0, 109, 109),
    "SUBMIT": (1, 17, 16400),
}
_SAFE_CODES = frozenset({"s03_unavailable", "s03_invalid", "s03_busy", "s03_revoked"})
_FRAME = re.compile(
    rb'\{"context":"([0-9a-f]{64})","data":"([A-Za-z0-9_-]{1,21867})",'
    rb'"domain":"agentbox-s03-submit/frame/v1","kind":"'
    rb'(KEY_INIT|KEY_ATTEST|KEY_CONFIRM|KEY_READY|SUBMIT)","seq":([01]),"version":1\}'
)


class S03Error(RuntimeError):
    """Only closed, fixed codes. No private exception or payload attributes."""

    def __init__(self, code: str = "s03_invalid") -> None:
        super().__init__(code if type(code) is str and code in _SAFE_CODES else "s03_invalid")


def _safe_code(error: BaseException) -> str:
    if (
        type(error) is S03Error
        and len(error.args) == 1
        and type(error.args[0]) is str
        and error.args[0] in _SAFE_CODES
    ):
        return error.args[0]
    return "s03_invalid"


@dataclass(frozen=True, slots=True, repr=False)
class SubmitContext:
    scope: ConversationScope
    execution_id: str
    request_id: str
    channel_id: str
    source_lease_id: str
    runtime_pin: bytes
    encoded: bytes
    digest: bytes

    @property
    def cd(self) -> str:
        return self.digest.hex()

    @property
    def prologue(self) -> bytes:
        return PROLOGUE_DOMAIN + self.encoded

    def _retire(self) -> None:
        # Mutable retirement only removes owned crypto buffers; frozen metadata
        # remains usable by the independent current-owner/receipt path.
        for name in ("runtime_pin", "encoded", "digest"):
            object.__setattr__(self, name, b"")

    def __repr__(self) -> str:
        return "<SubmitContext synthetic>"


def _build_context(value: object) -> SubmitContext:
    if type(value) is not dict or value.keys() != set(CONTEXT_FIELDS) | {"runtime_pin"}:
        raise S03Error()
    if any(type(key) is not str or type(item) is not str for key, item in value.items()):
        raise S03Error()
    record = cast(dict[str, str], value)
    # The original parser bounds each string before conversion; no coercion.
    scope = parse_scope({name: record[name] for name in SCOPE_FIELDS})
    for name, prefix in (
        ("execution_id", "kexe_"),
        ("request_id", "kreq_"),
        ("channel_id", "ks03c_"),
        ("source_lease_id", "ks03l_"),
    ):
        item = record[name]
        if len(item) != len(prefix) + 32 or not re.fullmatch(prefix + "[0-9a-f]{32}", item):
            raise S03Error()
    if record["adapter_profile"] != ADAPTER_PROFILE:
        raise S03Error()
    if len(record["runtime_pin"]) != 64 or not re.fullmatch("[0-9a-f]{64}", record["runtime_pin"]):
        raise S03Error()
    pin = bytes.fromhex(record["runtime_pin"])
    # At most 21 bounded fragments and one 739-byte assembly, not body fragments.
    parts = [CONTEXT_DOMAIN]
    for name in CONTEXT_FIELDS:
        raw = record[name].encode("ascii")
        parts.append(len(raw).to_bytes(2, "big") + raw)
    parts.append(pin)
    encoded = b"".join(parts)
    if len(encoded) > MAX_CONTEXT_BYTES:
        raise S03Error()
    return SubmitContext(
        scope,
        record["execution_id"],
        record["request_id"],
        record["channel_id"],
        record["source_lease_id"],
        pin,
        encoded,
        hashlib.sha256(encoded).digest(),
    )


def build_context(value: object) -> SubmitContext:
    """Pure bounded metadata snapshot, never a source/permit constructor."""
    result = None
    with suppress(Exception):
        result = _build_context(value)
    value = None
    if result is None:
        raise S03Error()
    return result


def aad(digest: bytes, handshake_hash: bytes, direction: int, kind: int, seq: int) -> bytes:
    if (
        type(digest) is not bytes
        or len(digest) != 32
        or type(handshake_hash) is not bytes
        or len(handshake_hash) != 32
        or type(direction) is not int
        or type(kind) is not int
        or type(seq) is not int
        or (direction, kind, seq) not in {(0, 3, 0), (1, 4, 0), (0, 5, 1)}
    ):
        digest = handshake_hash = b""
        raise S03Error()
    return AAD_DOMAIN + digest + handshake_hash + bytes((direction, kind)) + seq.to_bytes(8, "big")


def encode_frame(cd: str, kind: str, seq: int, data: bytes) -> bytes:
    result: bytes | None = None
    try:
        if (
            type(cd) is not str
            or len(cd) != 64
            or not re.fullmatch("[0-9a-f]{64}", cd)
            or type(kind) is not str
            or kind not in _KIND_LIMITS
            or type(seq) is not int
            or type(data) is not bytes
        ):
            raise S03Error()
        expected, minimum, maximum = _KIND_LIMITS[kind]
        if seq != expected or not minimum <= len(data) <= maximum:
            raise S03Error()
        encoded = base64.urlsafe_b64encode(data).rstrip(b"=")
        result = (
            b'{"context":"'
            + cd.encode("ascii")
            + b'","data":"'
            + encoded
            + b'","domain":"agentbox-s03-submit/frame/v1","kind":"'
            + kind.encode("ascii")
            + b'","seq":'
            + str(seq).encode("ascii")
            + b',"version":1}'
        )
        encoded = b""
    except Exception:
        pass
    data = b""
    if result is None:
        raise S03Error()
    return result


def decode_frame(raw: object, cd: str, kind: str, seq: int) -> bytes:
    """One bounded bytes scan and exactly one Base64 decode, no JSON parser."""
    result = None
    match = encoded = decoded = None
    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_FRAME_BYTES:
            raise S03Error()
        if type(kind) is not str or kind not in _KIND_LIMITS or type(seq) is not int:
            raise S03Error()
        expected, minimum, maximum = _KIND_LIMITS[kind]
        if seq != expected or type(cd) is not str or len(cd) != 64:
            raise S03Error()
        match = _FRAME.fullmatch(raw)
        if match is None:
            raise S03Error()
        if match[1] != cd.encode("ascii") or match[3] != kind.encode("ascii"):
            raise S03Error()
        if match[4] != str(seq).encode("ascii"):
            raise S03Error()
        encoded = match[2]
        if len(encoded) % 4 == 1:
            raise S03Error()
        decoded = base64.b64decode(
            encoded + b"=" * (-len(encoded) % 4), altchars=b"-_", validate=True
        )
        if not minimum <= len(decoded) <= maximum:
            raise S03Error()
        if base64.urlsafe_b64encode(decoded).rstrip(b"=") != encoded:
            raise S03Error()
        result = decoded
    except Exception:
        pass
    finally:
        raw = match = encoded = decoded = None
    if result is None:
        raise S03Error()
    return result


class _RuntimeSession:
    """Private synchronous responder. Only runtime composition decrypts bodies."""

    def __init__(self, context: SubmitContext) -> None:
        self.context: SubmitContext | None = context
        self.state = "NEW"
        self._handshake: NXResponder | None = NXResponder(context.prologue, RUNTIME_STATIC_PRIVATE)
        self._transport: NoiseTransport | None = None

    def close(self) -> None:
        self.state = "CLOSED"
        if self._handshake is not None:
            self._handshake.destroy()
            self._handshake = None
        if self._transport is not None:
            self._transport.destroy()
            self._transport = None
        self.context = None

    def receive_handshake(self, raw: object) -> bytes:
        result = None
        data = None
        try:
            context = self.context
            if context is None:
                raise S03Error("s03_revoked")
            if self.state == "NEW":
                self.state = "ATTEST_SENT"  # Spend before decode/crypto.
                data = decode_frame(raw, context.cd, "KEY_INIT", 0)
                if self._handshake is None or self._handshake.read_message1(data) != b"":
                    raise S03Error()
                response = self._handshake.write_message2()
                self._transport = self._handshake.take_transport()
                self._handshake.destroy()
                self._handshake = None
                result = encode_frame(context.cd, "KEY_ATTEST", 0, response)
                response = b""
            elif self.state == "ATTEST_SENT":
                self.state = "READY_SENT"
                data = decode_frame(raw, context.cd, "KEY_CONFIRM", 0)
                transport = self._transport
                if transport is None or transport.receive.nonce != 0 or transport.send.nonce != 0:
                    raise S03Error()
                hh = transport.handshake_hash
                confirmation = transport.receive.decrypt(data, aad(context.digest, hh, 0, 3, 0))
                if confirmation != CONFIRM_DOMAIN + context.digest + hh:
                    raise S03Error()
                confirmation = b""
                response = transport.send.encrypt(
                    READY_DOMAIN + context.digest + hh, aad(context.digest, hh, 1, 4, 0)
                )
                result = encode_frame(context.cd, "KEY_READY", 0, response)
                response = b""
            else:
                raise S03Error()
        except Exception:
            self.close()
        finally:
            raw = data = None
        if result is None:
            raise S03Error()
        return result

    def _decrypt_submit(self, raw: object) -> bytes:
        result = None
        data = None
        try:
            context = self.context
            transport = self._transport
            if self.state != "READY_SENT" or context is None or transport is None:
                raise S03Error()
            self.state = "SUBMIT_ATTEMPTED"
            data = decode_frame(raw, context.cd, "SUBMIT", 1)
            if transport.receive.nonce != 1:
                raise S03Error()
            result = transport.receive.decrypt(
                data, aad(context.digest, transport.handshake_hash, 0, 5, 1)
            )
            if type(result) is not bytes or not 1 <= len(result) <= MAX_BODY_BYTES:
                result = None
        except Exception:
            pass
        finally:
            self.close()
            raw = data = None
        if result is None:
            raise S03Error()
        return result
