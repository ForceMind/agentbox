"""Real nginx/TLS routing probe in a disposable non-production directory."""

from __future__ import annotations

import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from agentbox_installer.waw_web_ingress import render_web_ingress


@pytest.mark.skipif(shutil.which("nginx") is None, reason="real nginx is required")
def test_actual_https_static_api_and_upstream_redirect_boundary(tmp_path: Path) -> None:
    class MaliciousAPI(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("X-Accel-Redirect", "/index.html")
            self.send_header("Content-Security-Policy", "script-src * 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(b"alert('api fixture')")

        def log_message(self, format: str, *args: object) -> None:
            pass

    backend = ThreadingHTTPServer(("127.0.0.1", 0), MaliciousAPI)
    thread = threading.Thread(target=backend.serve_forever, daemon=True)
    thread.start()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    origin = f"https://localhost:{port}"
    web = tmp_path / "web"
    (web / ".well-known/agentbox").mkdir(parents=True)
    (web / "assets").mkdir()
    (web / "index.html").write_text("<html>Root static fixture</html>")
    (web / "assets/app.js").write_text("console.log('static fixture')")
    (web / ".publication.v1.json").write_text("private publication ledger")
    (web / ".well-known/agentbox/waw-bootstrap.v1.json").write_text('{"fixture":true}')
    tls = tmp_path / "tls"
    tls.mkdir()
    subprocess.run(  # noqa: S603 - fixed fixture certificate command
        [
            "/usr/bin/openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(tls / "privkey.pem"),
            "-out",
            str(tls / "fullchain.pem"),
            "-subj",
            "/CN=localhost",
            "-days",
            "1",
        ],
        check=True,
        capture_output=True,
        timeout=10,
    )
    run = tmp_path / "run"
    run.mkdir()
    # Substitute only fixture locations/loopback ports and avoid requiring a
    # production Unix account. Production renderer remains fixed and unchanged.
    config = render_web_ingress(origin).decode()
    config = config.replace("worker_processes auto;", "worker_processes 1;")
    config = config.replace("/run/agentbox-web", str(run))
    config = config.replace("/run/credentials/agentbox-web.service", str(tls))
    config = config.replace("/var/lib/agentbox-web/current", str(web))
    config = config.replace("127.0.0.1:8787", f"127.0.0.1:{backend.server_port}")
    path = tmp_path / "nginx.conf"
    path.write_text(config)
    executable = shutil.which("nginx")
    assert executable is not None
    process: subprocess.Popen[bytes] | None = None
    try:
        subprocess.run(  # noqa: S603 - selected installed nginx, fixed fixture config
            [executable, "-t", "-c", str(path)], check=True, capture_output=True, timeout=10
        )
        with (tmp_path / "nginx.log").open("wb") as log:
            process = subprocess.Popen(  # noqa: S603 - fixed foreground fixture command
                [executable, "-c", str(path), "-g", "daemon off;"], stdout=log, stderr=log
            )
            # Verification is intentionally disabled only for this self-signed
            # local test certificate; installation does not use this client.
            with httpx.Client(verify=False, trust_env=False, timeout=2) as client:
                deadline = time.monotonic() + 5
                while True:
                    try:
                        response = client.get(origin + "/projects")
                        break
                    except httpx.ConnectError:
                        assert process.poll() is None, (tmp_path / "nginx.log").read_text()
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.05)
                assert response.status_code == 200 and "Root static fixture" in response.text
                assert response.headers["cache-control"] == "no-store"
                assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
                assert client.get(origin + "/.publication.v1.json").status_code == 404
                assert client.get(origin + "/api/unregistered").status_code == 404
                assert client.post(origin + "/projects").status_code == 403
                assert client.get(origin + "/assets/missing.js").status_code == 404
                asset = client.get(origin + "/assets/app.js")
                assert asset.headers["content-type"] == "application/javascript"
                assert "immutable" in asset.headers["cache-control"]
                bootstrap = client.get(origin + "/.well-known/agentbox/waw-bootstrap.v1.json")
                assert bootstrap.json() == {"fixture": True}
                api = client.get(origin + "/api/v1/probe")
                assert api.text == "alert('api fixture')"
                assert api.headers["content-type"] == "application/json"
                assert "sandbox" in api.headers["content-security-policy"]
                assert api.headers["x-content-type-options"] == "nosniff"
                assert client.get(origin, headers={"Host": "foreign.test"}).status_code == 421
    finally:
        if process is not None:
            process.terminate()
            process.wait(timeout=5)
        backend.shutdown()
        backend.server_close()
        thread.join(timeout=5)
