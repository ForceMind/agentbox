"""Canonical public HTTPS bootstrap codec; no private or Provider Secret inputs."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from agentbox_runtime.waw_manifest_codecs import CrossManifestPinV2


def encode_https_bootstrap(
    pin: CrossManifestPinV2,
    *,
    origin: str,
    build_identity: str,
    version: str,
    valid_from: datetime,
    valid_until: datetime,
) -> bytes:
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or not origin.isascii()
        or origin != origin.lower()
        or parsed.netloc.endswith(":443")
        or any(ord(char) < 33 for char in origin)
    ):
        raise ValueError("canonical HTTPS Origin is required")
    # Force invalid ports to fail without accepting an alternate parser view.
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError("HTTPS Origin port is invalid")
    if (
        re.fullmatch(r"[0-9a-f]{64}", build_identity) is None
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:(?:a|b|rc)[0-9]+)?", version) is None
    ):
        raise ValueError("public build identity is invalid")
    if (
        valid_from.tzinfo is None
        or valid_until.tzinfo is None
        or valid_from.utcoffset() != timedelta(0)
        or valid_until.utcoffset() != timedelta(0)
        or valid_from.microsecond
        or valid_until.microsecond
        or not timedelta(0) < valid_until - valid_from <= timedelta(days=31)
    ):
        raise ValueError("public bootstrap validity is invalid")
    values = {
        "schema_version": "agentbox-waw-https-bootstrap.v1",
        "trust_profile": "https-web-v1",
        "repository": "ForceMind/agentbox",
        "origin": origin,
        "build_identity": build_identity,
        "version": version,
        "runtime_host_installation_id": pin.runtime.runtime_host_installation_id,
        "runtime_host_installation_revision": pin.runtime.runtime_host_installation_revision,
        "runtime_attestation_x25519_fingerprint": (
            pin.runtime.runtime_attestation_x25519_fingerprint
        ),
        "host_manifest_digest": pin.runtime_manifest_digest,
        "valid_from": valid_from.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "valid_until": valid_until.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if (
        re.fullmatch(r"wri_[0-9a-f]{32}", values["runtime_host_installation_id"]) is None
        or re.fullmatch(r"[1-9][0-9]{0,19}", values["runtime_host_installation_revision"]) is None
        or int(values["runtime_host_installation_revision"]) > 2**64 - 1
        or any(
            re.fullmatch(r"[0-9a-f]{64}", values[field]) is None
            for field in ("runtime_attestation_x25519_fingerprint", "host_manifest_digest")
        )
    ):
        raise ValueError("public Runtime identity is invalid")
    return (
        json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode()
