from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from agentbox_installer.waw_https_bootstrap import encode_https_bootstrap
from test_installer_waw_manifests import _fixture, _load


@pytest.mark.parametrize(
    "origin",
    [
        "https://example.agentbox.test",
        "http://example.agentbox.test",
        "https://user@example.agentbox.test",
        "https://example.agentbox.test/",
        "https://example.agentbox.test:443",
        "https://example.agentbox.test?x=1",
    ],
)
def test_public_bootstrap_requires_canonical_origin_and_contains_only_public_fields(
    tmp_path: Path, origin: str
) -> None:
    issuer, root = _fixture(tmp_path)
    issuer.publish(issuer.observe(), "a" * 64)
    pin = _load(root)
    now = datetime(2026, 10, 1, tzinfo=UTC)
    args: dict[str, Any] = dict(
        origin=origin,
        build_identity="b" * 64,
        version="0.3.0rc30",
        valid_from=now,
        valid_until=now + timedelta(days=1),
    )
    if origin != "https://example.agentbox.test":
        with pytest.raises(ValueError):
            encode_https_bootstrap(pin, **args)
    else:
        raw = encode_https_bootstrap(pin, **args)
        value = json.loads(raw)
        assert value["trust_profile"] == "https-web-v1"
        assert value["runtime_attestation_x25519_fingerprint"] == "a" * 64
        assert len(value) == 12
        assert raw == (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
