from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from agentbox_installer.waw_web_certificates import web_acme_argv


@pytest.mark.skipif(shutil.which("certbot") is None, reason="actual distro certbot is required")
def test_distro_certbot_accepts_fixed_standalone_flags_without_network(tmp_path: Path) -> None:
    argv = list(web_acme_argv("https://example.agentbox.test", "owner@example.test"))
    executable = shutil.which("certbot")
    assert executable is not None
    argv[0] = executable
    for flag in ("--config-dir", "--work-dir", "--logs-dir"):
        path = tmp_path / flag[2:]
        path.mkdir()
        argv[argv.index(flag) + 1] = str(path)
    config = tmp_path / "cli.ini"
    config.write_text("# fixture: no hooks\n")
    argv[argv.index("--config") + 1] = str(config)
    result = subprocess.run(  # noqa: S603 - actual CLI parser only, --help exits before CA actions
        [*argv, "--help"], capture_output=True, text=True, timeout=10, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "certbot" in result.stdout.lower()
