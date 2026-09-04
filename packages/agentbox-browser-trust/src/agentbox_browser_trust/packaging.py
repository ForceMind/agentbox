"""Build a deployment-bound, public-only managed Chrome trust client bundle."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import NoReturn
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization

from agentbox_browser_trust.codec import canonical_json
from agentbox_browser_trust.records import canonical_origin

EXTENSION_ID = re.compile(r"^[a-p]{32}$")
HEX64 = re.compile(r"^[a-f0-9]{64}$")
NATIVE_HOST_NAME = "com.forcemind.agentbox.waw_trust"
EXPECTED_EXTENSION_FILES = frozenset(
    {
        "managed_schema.json",
        "manifest.json",
        "protocol.d.ts",
        "protocol.js",
        "serviceWorker.d.ts",
        "serviceWorker.js",
    }
)


class BrowserTrustPackageError(RuntimeError):
    """A production client bundle input is missing, ambiguous or inconsistent."""


def _fail() -> NoReturn:
    raise BrowserTrustPackageError("browser trust client package inputs are invalid")


def chrome_extension_id(public_key_der: bytes) -> str:
    if type(public_key_der) is not bytes or len(public_key_der) < 32 or len(public_key_der) > 4096:
        _fail()
    digest = hashlib.sha256(public_key_der).digest()[:16]
    return "".join(chr(ord("a") + nibble) for byte in digest for nibble in (byte >> 4, byte & 15))


def _public_key(value: str) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, UnicodeEncodeError):
        _fail()
    if base64.b64encode(raw).decode("ascii") != value:
        _fail()
    try:
        public_key = serialization.load_der_public_key(raw)
        canonical = public_key.public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    except (TypeError, ValueError):
        _fail()
    if canonical != raw:
        _fail()
    return canonical


def _match_pattern(origin: str) -> str:
    parsed = urlsplit(origin)
    host = parsed.hostname
    if not host:
        _fail()
    return f"https://{'[' + host + ']' if ':' in host else host}/*"


def _read_extension_dist(directory: Path) -> dict[str, bytes]:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        directory_fd = os.open(directory, flags)
    except OSError:
        _fail()
    try:
        info = os.fstat(directory_fd)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_gid != os.getegid()
            or stat.S_IMODE(info.st_mode) & 0o022
        ):
            _fail()
        names = frozenset(os.listdir(directory_fd))
        if names != EXPECTED_EXTENSION_FILES:
            _fail()
        captured: dict[str, bytes] = {}
        for name in sorted(names):
            file_flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                file_flags |= os.O_NOFOLLOW
            descriptor = os.open(name, file_flags, dir_fd=directory_fd)
            try:
                item = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(item.st_mode)
                    or item.st_nlink != 1
                    or item.st_uid != os.geteuid()
                    or item.st_gid != os.getegid()
                    or item.st_size < 1
                    or item.st_size > 512 * 1024
                ):
                    _fail()
                chunks = bytearray()
                while len(chunks) < item.st_size:
                    chunk = os.read(descriptor, item.st_size - len(chunks))
                    if not chunk:
                        _fail()
                    chunks.extend(chunk)
                captured[name] = bytes(chunks)
            finally:
                os.close(descriptor)
        return captured
    finally:
        os.close(directory_fd)


def build_client_bundle(
    output: Path,
    *,
    extension_dist: Path,
    extension_id: str,
    extension_public_key: str,
    origin: str,
    update_url: str,
    provider_fingerprint: str,
    client_uids: tuple[int, ...],
) -> None:
    origin = canonical_origin(origin)
    update = urlsplit(update_url)
    if (
        not EXTENSION_ID.fullmatch(extension_id)
        or chrome_extension_id(_public_key(extension_public_key)) != extension_id
        or update.scheme != "https"
        or not update.hostname
        or update.username
        or update.password
        or update.fragment
        or not HEX64.fullmatch(provider_fingerprint)
        or not 1 <= len(client_uids) <= 32
        or len(set(client_uids)) != len(client_uids)
        or any(type(uid) is not int or uid < 1 or uid > 0x7FFFFFFF for uid in client_uids)
        or output.exists()
    ):
        _fail()
    captured = _read_extension_dist(extension_dist)
    manifest = json.loads(captured["manifest.json"].decode("utf-8"))
    if (
        type(manifest) is not dict
        or frozenset(manifest)
        != {
            "manifest_version",
            "name",
            "version",
            "description",
            "background",
            "permissions",
            "incognito",
            "storage",
        }
        or manifest["manifest_version"] != 3
        or manifest["background"] != {"service_worker": "serviceWorker.js", "type": "module"}
        or manifest["permissions"] != ["nativeMessaging", "storage"]
        or manifest["incognito"] != "not_allowed"
        or manifest["storage"] != {"managed_schema": "managed_schema.json"}
    ):
        _fail()
    output.mkdir(mode=0o755, parents=True)
    extension_output = output / "extension"
    extension_output.mkdir(mode=0o755)
    for name in ("managed_schema.json", "protocol.js", "serviceWorker.js"):
        (extension_output / name).write_bytes(captured[name])
    production_manifest = {
        **manifest,
        "name": "AgentBox WAW Trust Bridge",
        "key": extension_public_key,
        "update_url": update_url,
        "externally_connectable": {"matches": [_match_pattern(origin)]},
    }
    (extension_output / "manifest.json").write_bytes(canonical_json(production_manifest))

    native = output / "native-messaging"
    native.mkdir(mode=0o755)
    native_manifest = {
        "name": NATIVE_HOST_NAME,
        "description": "AgentBox WAW managed trust provider bridge",
        "path": "/opt/agentbox-browser-trust/current/bin/agentbox-browser-trust-native",
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }
    (native / f"{NATIVE_HOST_NAME}.json").write_bytes(canonical_json(native_manifest))

    policy = output / "chrome-policy"
    policy.mkdir(mode=0o755)
    chrome_policy = {
        "ExtensionSettings": {
            extension_id: {
                "installation_mode": "force_installed",
                "update_url": update_url,
            }
        },
        "3rdparty": {
            "extensions": {
                extension_id: {
                    "provider_installation_key_fingerprint": provider_fingerprint,
                    "allowed_origins": [origin],
                }
            }
        },
    }
    (policy / "agentbox-waw-trust.json").write_bytes(canonical_json(chrome_policy))

    trustd = output / "trustd"
    trustd.mkdir(mode=0o755)
    clients = {
        "schema_version": "waw-browser-trust-clients-v1",
        "uids": list(client_uids),
    }
    (trustd / "clients.v1.json").write_bytes(canonical_json(clients, limit=4096))
    for path in output.rglob("*"):
        os.chmod(path, 0o755 if path.is_dir() else 0o644)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="agentbox-browser-trust-package")
    value.add_argument("--output", type=Path, required=True)
    value.add_argument("--extension-dist", type=Path, required=True)
    value.add_argument("--extension-id", required=True)
    value.add_argument("--extension-public-key", required=True)
    value.add_argument("--origin", required=True)
    value.add_argument("--update-url", required=True)
    value.add_argument("--provider-fingerprint", required=True)
    value.add_argument("--client-uid", action="append", required=True, type=int)
    return value


def main() -> None:
    arguments = parser().parse_args()
    build_client_bundle(
        arguments.output,
        extension_dist=arguments.extension_dist,
        extension_id=arguments.extension_id,
        extension_public_key=arguments.extension_public_key,
        origin=arguments.origin,
        update_url=arguments.update_url,
        provider_fingerprint=arguments.provider_fingerprint,
        client_uids=tuple(arguments.client_uid),
    )
