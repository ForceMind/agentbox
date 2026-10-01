from __future__ import annotations

import json
import os
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from agentbox_installer.host import HostOperations
from agentbox_installer.layout import InstallLayout
from agentbox_installer.lifecycle import AgentBoxInstaller, InstallError
from agentbox_installer.waw_activation import WAWActivationTransaction
from agentbox_installer.waw_web_configuration import configure_browser_origin, validate_web_tls
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from test_installer_waw_web_publication import _publisher


def _tls(hostname: str = "example.agentbox.test") -> tuple[bytes, bytes]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=3))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM), key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _configured_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[AgentBoxInstaller, Path, str]:
    publisher, root, args = _publisher(tmp_path)
    now = datetime.now(UTC).replace(microsecond=0)
    args.update(valid_from=now - timedelta(minutes=1), valid_until=now + timedelta(days=1))
    publisher.publish(**args)
    tls = root / "etc/agentbox-web/tls"
    tls.mkdir(mode=0o700)
    cert, key = _tls()
    for name, raw, mode in (("fullchain.pem", cert, 0o644), ("privkey.pem", key, 0o600)):
        path = tls / name
        path.write_bytes(raw)
        path.chmod(mode)
    config = root / "etc/agentbox/agentbox.toml"
    config.parent.mkdir(exist_ok=True)
    config.write_bytes(b'env = "production"\nallowed_origins = []\ntrusted_proxies = []\n')
    config.chmod(0o640)
    host = HostOperations(real_host=False)
    installer = AgentBoxInstaller(InstallLayout(root), host)
    monkeypatch.setattr(installer, "installation_state", lambda: "installed")
    monkeypatch.setattr(installer, "current_version", lambda: "0.3.0rc30")
    return installer, root, args["origin"]


def test_web_configuration_plan_apply_and_idempotence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer, root, origin = _configured_fixture(tmp_path, monkeypatch)
    config = root / "etc/agentbox/agentbox.toml"
    before = config.read_bytes()
    plan = installer.configure_waw_web(origin=origin, plan=True)
    assert config.read_bytes() == before and plan["services_started"] is False
    applied = installer.configure_waw_web(origin=origin)
    assert applied["status"] == "configured" and applied["qualified"] is False
    assert tomllib.loads(config.read_text()) == {
        "env": "production",
        "allowed_origins": [origin],
        "trusted_proxies": ["127.0.0.1/32"],
    }
    assert config.stat().st_mode & 0o777 == 0o640 and config.stat().st_gid == os.getegid()
    inode = config.stat().st_ino
    installer.configure_waw_web(origin=origin)
    assert config.stat().st_ino == inode
    with pytest.raises(InstallError, match="resource failed"):
        installer.configure_waw_web(origin=origin, activate=True)


def test_web_configuration_never_overwrites_other_origin() -> None:
    with pytest.raises(ValueError, match="migration"):
        configure_browser_origin(
            b'allowed_origins = ["https://other.test"]\ntrusted_proxies = []\n',
            "https://example.agentbox.test",
        )


def test_web_tls_mismatch_wrong_hostname_expiry_and_wildcard() -> None:
    cert, key = _tls()
    now = datetime.now(UTC)
    validate_web_tls(cert, key, "https://example.agentbox.test", now)
    with pytest.raises(ValueError, match="Origin"):
        validate_web_tls(cert, key, "https://other.test", now)
    with pytest.raises(ValueError, match="valid"):
        validate_web_tls(cert, key, "https://example.agentbox.test", now + timedelta(days=4))
    _cert, other_key = _tls()
    with pytest.raises(ValueError, match="mismatch"):
        validate_web_tls(cert, other_key, "https://example.agentbox.test", now)
    cert, key = _tls("*.agentbox.test")
    validate_web_tls(cert, key, "https://example.agentbox.test", now)
    with pytest.raises(ValueError, match="Origin"):
        validate_web_tls(cert, key, "https://nested.example.agentbox.test", now)


def test_web_configuration_rejects_tls_permissions_before_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer, root, origin = _configured_fixture(tmp_path, monkeypatch)
    config = root / "etc/agentbox/agentbox.toml"
    before = config.read_bytes()
    (root / "etc/agentbox-web/tls/privkey.pem").chmod(0o644)
    with pytest.raises(RuntimeError, match="provenance"):
        installer.configure_waw_web(origin=origin)
    assert config.read_bytes() == before


def test_web_configuration_refuses_drifted_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer, root, origin = _configured_fixture(tmp_path, monkeypatch)
    current = root / "var/lib/agentbox-web/current"
    bootstrap = current / ".well-known/agentbox/waw-bootstrap.v1.json"
    value = json.loads(bootstrap.read_bytes())
    value["origin"] = "https://foreign.test"
    bootstrap.chmod(0o644)
    bootstrap.write_text(json.dumps(value))
    bootstrap.chmod(0o444)
    with pytest.raises(RuntimeError):
        installer.configure_waw_web(origin=origin)


def test_web_activation_only_starts_after_configuration_and_stops_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer, _root, origin = _configured_fixture(tmp_path, monkeypatch)
    calls: list[str] = []
    monkeypatch.setattr(WAWActivationTransaction, "inspect", lambda self, *, recover: "started")
    monkeypatch.setattr(installer.host, "start_web_service", lambda: calls.append("start"))
    monkeypatch.setattr(installer.host, "stop_web_service", lambda: calls.append("stop"))
    with pytest.raises(InstallError, match="configure-waw-web"):
        installer.configure_waw_web(origin=origin, activate=True)
    assert calls == []
    installer.configure_waw_web(origin=origin)
    installer.configure_waw_web(origin=origin, plan=True, activate=True)
    assert calls == []
    result = installer.configure_waw_web(origin=origin, activate=True)
    assert calls == ["start"] and result["services_started"] is True
    assert result["qualified"] is False

    def failure() -> None:
        calls.append("failed")
        raise RuntimeError("synthetic HTTPS startup failure")

    monkeypatch.setattr(installer.host, "start_web_service", failure)
    with pytest.raises(RuntimeError, match="synthetic HTTPS"):
        installer.configure_waw_web(origin=origin, activate=True)
    assert calls == ["start", "failed", "stop"]
