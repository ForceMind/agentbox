"""Disposable native PID-1 proof for the actual DynamicUser/credential unit."""

from __future__ import annotations

import importlib.resources
import os
import socket
import ssl
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.request import urlopen

import pytest
from agentbox_installer.waw_web_ingress import render_web_ingress
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


@pytest.mark.skipif(
    os.geteuid() != 0 or os.environ.get("GITHUB_ACTIONS") != "true",
    reason="isolated Linux CI Root/native-PID-1 gate required",
)
def test_actual_dynamic_user_tls_credentials_and_write_denial() -> None:
    assert Path("/proc/1/comm").read_text().strip() == "systemd"
    suffix = uuid.uuid4().hex
    name = "agentbox-web-probe-" + suffix
    unit = name + ".service"
    unit_path = Path("/run/systemd/system") / unit

    def systemctl(*args: str) -> str:
        return subprocess.run(  # noqa: S603 - exact own disposable service, no shell
            ["/usr/bin/systemctl", *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        ).stdout.strip()

    with tempfile.TemporaryDirectory(prefix=name + "-", dir="/var/lib") as directory:
        root = Path(directory)
        root.chmod(0o755)
        web = root / "web"
        web.mkdir()
        (web / "index.html").write_text("Root-owned DynamicUser TLS fixture")
        (web / "index.html").chmod(0o444)
        tls = root / "tls"
        tls.mkdir(mode=0o700)
        private = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
        now = datetime.now(UTC)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(private.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
            .sign(private, hashes.SHA256())
        )
        cert = certificate.public_bytes(serialization.Encoding.PEM)
        key = private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        for filename, raw, mode in (("fullchain.pem", cert, 0o644), ("privkey.pem", key, 0o600)):
            path = tls / filename
            path.write_bytes(raw)
            path.chmod(mode)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        origin = f"https://localhost:{port}"
        configuration = render_web_ingress(origin).decode()
        configuration = configuration.replace("worker_processes auto;", "worker_processes 1;")
        configuration = configuration.replace("/run/agentbox-web", "/run/" + name)
        configuration = configuration.replace("/var/lib/agentbox-web/current", str(web))
        configuration = configuration.replace(
            "/run/credentials/agentbox-web.service", "/run/credentials/" + unit
        )
        config = root / "nginx.conf"
        config.write_text(configuration)
        config.chmod(0o444)
        source = (
            importlib.resources.files("agentbox_installer")
            .joinpath("assets/systemd/agentbox-web.service")
            .read_text()
        )
        source = source.replace("agentbox-api.service", "")
        source = source.replace("User=agentbox-web", "User=abw-" + suffix[:12])
        source = source.replace("/etc/agentbox-web/tls", str(tls))
        source = source.replace("/etc/agentbox-web/nginx.conf", str(config))
        source = source.replace("RuntimeDirectory=agentbox-web", "RuntimeDirectory=" + name)
        source = source.replace("/run/agentbox-web", "/run/" + name)
        source = source.replace(
            "[Install]",
            f"ExecStartPost=/usr/bin/test ! -w {web / 'index.html'}\n"
            f"ExecStartPost=/usr/bin/test -r /run/credentials/{unit}/privkey.pem\n\n[Install]",
        )
        with unit_path.open("x") as stream:
            stream.write(source)
        try:
            systemctl("daemon-reload")
            systemctl("start", unit)
            systemctl("is-active", "--quiet", unit)
            pid = int(systemctl("show", unit, "--property=MainPID", "--value"))
            status = Path(f"/proc/{pid}/status").read_text()
            uid = next(line for line in status.splitlines() if line.startswith("Uid:"))
            assert all(int(value) > 0 for value in uid.split()[1:])
            context = ssl.create_default_context(cafile=str(tls / "fullchain.pem"))
            with urlopen(origin + "/projects", context=context, timeout=5) as response:
                assert response.read() == b"Root-owned DynamicUser TLS fixture"
            assert (tls / "privkey.pem").stat().st_mode & 0o777 == 0o600
            print("DynamicUser, LoadCredential, HTTPS and kernel write-denial: PASS")
        finally:
            subprocess.run(  # noqa: S603 - stop only this test-owned unit
                ["/usr/bin/systemctl", "stop", unit], check=False, capture_output=True, timeout=20
            )
            unit_path.unlink()
            systemctl("daemon-reload")
