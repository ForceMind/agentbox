"""Chrome Native Messaging bridge with no trust-store or mutation authority."""

from __future__ import annotations

import hashlib
import os
import re
import socket
import stat
import struct
import sys
from typing import NoReturn

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from agentbox_browser_trust.codec import (
    TRUSTD_MESSAGE_MAX,
    BinaryStream,
    b64url_decode,
    canonical_json,
    exact_object,
    read_frame,
    read_native_message,
    strict_json,
    write_frame,
    write_native_message,
)
from agentbox_browser_trust.daemon import DEFAULT_SOCKET

BROKER_RESPONSE_KEYS = frozenset(
    {
        "protocol_version",
        "type",
        "origin",
        "document_id",
        "native_nonce",
        "provider_installation_id",
        "provider_epoch",
        "provider_public_key",
        "signature",
    }
)


def _fail() -> NoReturn:
    raise RuntimeError("browser trust native bridge is unavailable")


def _verify_broker_opened(value: object, expected_open: dict[str, object]) -> None:
    item = exact_object(value, BROKER_RESPONSE_KEYS)
    if item["protocol_version"] != 1 or item["type"] != "BROKER_OPENED":
        _fail()
    public_key = b64url_decode(item["provider_public_key"], size=32, limit=32)
    expected_fingerprint = expected_open.get("provider_installation_key_fingerprint")
    if (
        type(expected_fingerprint) is not str
        or hashlib.sha256(public_key).hexdigest() != expected_fingerprint
        or item["origin"] != expected_open.get("origin")
        or item["document_id"] != expected_open.get("document_id")
        or item["native_nonce"] != expected_open.get("native_nonce")
        or type(item["provider_installation_id"]) is not str
        or not re.fullmatch(r"bti_[a-f0-9]{32}", item["provider_installation_id"])
        or type(item["provider_epoch"]) is not str
        or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", item["provider_epoch"])
    ):
        _fail()
    signature = b64url_decode(item["signature"], size=64, limit=64)
    unsigned = {key: entry for key, entry in item.items() if key != "signature"}
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature,
            b"agentbox-waw/trustd-session/v1\0" + canonical_json(unsigned, limit=4096),
        )
    except (InvalidSignature, ValueError):
        _fail()


def bridge(
    chrome_input: BinaryStream,
    chrome_output: BinaryStream,
    trustd: BinaryStream,
) -> None:
    opened = read_native_message(chrome_input)
    if type(opened) is not dict:
        _fail()
    fingerprint = opened.get("provider_installation_key_fingerprint")
    if type(fingerprint) is not str:
        _fail()
    write_frame(
        trustd,
        canonical_json(opened, limit=4096),
        limit=4096,
        little_endian=False,
    )
    broker_response = strict_json(read_frame(trustd, limit=4096, little_endian=False), limit=4096)
    _verify_broker_opened(broker_response, opened)
    while True:
        request = read_native_message(chrome_input)
        write_frame(
            trustd,
            canonical_json(request, limit=4096),
            limit=4096,
            little_endian=False,
        )
        response = strict_json(read_frame(trustd, limit=TRUSTD_MESSAGE_MAX, little_endian=False))
        write_native_message(chrome_output, response)
        if type(response) is dict and response.get("type") in ("CLOSE", "INVALIDATE"):
            return


def verify_trustd_peer(connection: socket.socket) -> None:
    option = getattr(socket, "SO_PEERCRED", None)
    if option is None:
        _fail()
    raw = connection.getsockopt(socket.SOL_SOCKET, option, struct.calcsize("3i"))
    pid, uid, gid = struct.unpack("3i", raw)
    info = os.stat(DEFAULT_SOCKET, follow_symlinks=False)
    if (
        pid < 1
        or not stat.S_ISSOCK(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o660
        or info.st_uid != uid
        or info.st_gid != gid
    ):
        _fail()


def run() -> None:
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        connection.connect(str(DEFAULT_SOCKET))
        verify_trustd_peer(connection)
        stream = connection.makefile("rwb", buffering=0)
        try:
            bridge(sys.stdin.buffer, sys.stdout.buffer, stream)
        finally:
            stream.close()
    finally:
        connection.close()


def main() -> None:
    run()
