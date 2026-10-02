"""Disposable native PID-1 proof for the fixed Web maintenance sandbox."""

from __future__ import annotations

import importlib.resources
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

import pytest


@pytest.mark.skipif(
    os.geteuid() != 0 or os.environ.get("GITHUB_ACTIONS") != "true",
    reason="isolated Linux CI Root/native-PID-1 gate required",
)
def test_actual_web_maintenance_sandbox_write_and_read_boundaries() -> None:
    assert Path("/proc/1/comm").read_text().strip() == "systemd"
    suffix = uuid.uuid4().hex
    name = "agentbox-maintenance-probe-" + suffix
    unit = name + ".service"
    unit_path = Path("/run/systemd/system") / unit

    def systemctl(*args: str) -> str:
        return subprocess.run(  # noqa: S603 - exact test-owned disposable unit
            ["/usr/bin/systemctl", *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        ).stdout.strip()

    with tempfile.TemporaryDirectory(prefix=name + "-", dir="/var/lib") as directory:
        root = Path(directory)
        root.chmod(0o755)
        allowed = root / "allowed"
        allowed.mkdir(mode=0o700)
        secret = root / "secret"
        secret.mkdir(mode=0o700)
        (secret / "canary").write_text("must-not-be-readable", encoding="utf-8")
        outside = root / "outside"
        outside.mkdir(mode=0o755)
        output = allowed / "result.json"
        script = root / "probe.py"
        script.write_text(
            """from __future__ import annotations
import errno
import json
import os
import sys
from pathlib import Path

allowed, secret, outside, output = map(Path, sys.argv[1:])
assert os.geteuid() == 0
status = Path("/proc/self/status").read_text()
no_new_privileges = next(
    line.split()[1] for line in status.splitlines() if line.startswith("NoNewPrivs:")
)
assert no_new_privileges == "1"
(allowed / "write-ok").write_text("ok")
try:
    (secret / "canary").read_text()
except OSError as exc:
    assert exc.errno in {errno.EACCES, errno.EPERM, errno.ENOENT}, exc.errno
else:
    raise AssertionError("inaccessible maintenance path was readable")
try:
    (outside / "write-denied").write_text("bad")
except OSError as exc:
    assert exc.errno in {errno.EROFS, errno.EACCES, errno.EPERM}, exc.errno
else:
    raise AssertionError("ProtectSystem=strict allowed an unrelated write")
output.write_text(json.dumps({
    "schema_version": "agentbox-web-maintenance-sandbox-probe.v1",
    "root_identity": True,
    "no_new_privileges": True,
    "allowed_write": True,
    "sensitive_read_denied": True,
    "unrelated_write_denied": True,
}, sort_keys=True))
""",
            encoding="utf-8",
        )
        script.chmod(0o555)

        source = (
            importlib.resources.files("agentbox_installer")
            .joinpath("assets/systemd/agentbox-web-maintenance.service")
            .read_text()
        )
        source = source.replace("agentbox-web.service", "")
        source = source.replace(
            "ExecStart=/opt/agentbox/current/venv/bin/agentbox-install maintain-waw-web --recover",
            f"ExecStart=/usr/bin/python3 {script} {allowed} {secret} {outside} {output}",
        )
        read_write_paths = (
            "ReadWritePaths=/etc/agentbox-web /var/lib/agentbox-web "
            "/var/lib/agentbox/.install.lock"
        )
        source = source.replace(read_write_paths, f"ReadWritePaths={allowed}")
        inaccessible = next(
            line for line in source.splitlines() if line.startswith("InaccessiblePaths=")
        )
        source = source.replace(inaccessible, f"InaccessiblePaths={secret}")
        with unit_path.open("x", encoding="utf-8") as stream:
            stream.write(source)
        try:
            systemctl("daemon-reload")
            systemctl("start", unit)
            result = json.loads(output.read_text(encoding="utf-8"))
            assert result == {
                "schema_version": "agentbox-web-maintenance-sandbox-probe.v1",
                "root_identity": True,
                "no_new_privileges": True,
                "allowed_write": True,
                "sensitive_read_denied": True,
                "unrelated_write_denied": True,
            }
            print(json.dumps(result, sort_keys=True))
        finally:
            subprocess.run(  # noqa: S603 - stop only this test-owned unit
                ["/usr/bin/systemctl", "stop", unit],
                check=False,
                capture_output=True,
                timeout=20,
            )
            unit_path.unlink()
            systemctl("daemon-reload")
