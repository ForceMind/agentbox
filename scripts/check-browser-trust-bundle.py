#!/usr/bin/env python3
"""Exercise the production extension dist through the public-only bundle builder."""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path

from agentbox_browser_trust.packaging import build_client_bundle, chrome_extension_id
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "clients/browser-trust/extension/dist"
EXPECTED_DIST = {
    "managed_schema.json",
    "manifest.json",
    "protocol.d.ts",
    "protocol.js",
    "serviceWorker.d.ts",
    "serviceWorker.js",
}


def main() -> None:
    if {path.name for path in DIST.iterdir()} != EXPECTED_DIST:
        raise ValueError("browser trust extension dist inventory is invalid")
    public_key = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        .public_key()
        .public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    with tempfile.TemporaryDirectory(prefix="agentbox-browser-trust-bundle-") as temporary:
        output = Path(temporary) / "bundle"
        build_client_bundle(
            output,
            extension_dist=DIST,
            extension_id=chrome_extension_id(public_key),
            extension_public_key=base64.b64encode(public_key).decode("ascii"),
            origin="https://example.agentbox.test",
            update_url="https://updates.agentbox.test/chrome/update.xml",
            provider_fingerprint="a" * 64,
            client_uids=(1000,),
        )
        required = {
            output / "extension/manifest.json",
            output / "native-messaging/com.forcemind.agentbox.waw_trust.json",
            output / "chrome-policy/agentbox-waw-trust.json",
            output / "trustd/clients.v1.json",
        }
        if not all(path.is_file() for path in required):
            raise ValueError("browser trust client bundle output is incomplete")
    print("browser trust extension dist bundle gate passed")


if __name__ == "__main__":
    main()
