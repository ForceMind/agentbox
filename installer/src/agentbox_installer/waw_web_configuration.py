"""Fixed TLS and browser-origin checks for the independent Web entry."""

from __future__ import annotations

import json
import re
import tomllib
from datetime import datetime
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from agentbox_installer.waw_web_ingress import render_web_ingress


def configure_browser_origin(raw: bytes, origin: str) -> bytes:
    render_web_ingress(origin)
    text = raw.decode("utf-8")
    before = tomllib.loads(text)
    targets = {"allowed_origins": [origin], "trusted_proxies": ["127.0.0.1/32"]}
    for name, value in targets.items():
        if before.get(name) not in ([], value):
            raise ValueError("existing browser configuration differs; explicit migration required")
        pattern = rf"^{name}\s*=\s*\[[^\r\n]*\]\s*$"
        text, count = re.subn(pattern, f"{name} = {json.dumps(value)}", text, flags=re.MULTILINE)
        if count != 1:
            raise ValueError("browser configuration requires one fixed top-level declaration")
    if tomllib.loads(text) != before | targets:
        raise ValueError("browser configuration would change unrelated settings")
    return text.encode("utf-8")


def validate_web_tls(certificates: bytes, private_key: bytes, origin: str, now: datetime) -> str:
    """Check the fixed TLS leaf/key; public CA trust is checked by HTTPS clients."""
    render_web_ingress(origin)
    chain = x509.load_pem_x509_certificates(certificates)
    if not chain:
        raise ValueError("Web TLS certificate chain is empty")
    leaf = chain[0]
    key = serialization.load_pem_private_key(private_key, password=None)
    encoding = serialization.Encoding.DER
    format = serialization.PublicFormat.SubjectPublicKeyInfo
    if leaf.public_key().public_bytes(encoding, format) != key.public_key().public_bytes(
        encoding, format
    ):
        raise ValueError("Web TLS certificate/key mismatch")
    if not leaf.not_valid_before_utc <= now < leaf.not_valid_after_utc:
        raise ValueError("Web TLS certificate is not currently valid")
    try:
        names = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound as exc:
        raise ValueError("Web TLS certificate requires a DNS subject alternative name") from exc
    hostname = urlsplit(origin).hostname
    assert hostname is not None
    matched = False
    for name in names.get_values_for_type(x509.DNSName):
        name = name.lower()
        if name == hostname or (
            name.startswith("*.")
            and "*" not in name[2:]
            and hostname.count(".") == name.count(".")
            and hostname.endswith(name[1:])
        ):
            matched = True
    if not matched:
        raise ValueError("Web TLS certificate does not match the Origin")
    return leaf.not_valid_after_utc.isoformat()
