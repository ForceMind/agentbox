from __future__ import annotations

import re
import shutil
import subprocess
from importlib import resources
from pathlib import Path

import pytest
from agentbox_installer.lifecycle import UNIT_NAMES


def _unit(name: str) -> str:
    return (resources.files("agentbox_installer") / "assets/systemd" / name).read_text()


def test_service_identities_and_loopback_configuration_are_separated() -> None:
    api = _unit("agentbox-api.service")
    worker = _unit("agentbox-worker.service")
    runtime = _unit("agentbox-runtime.service")
    helper = _unit("agentbox-helper.service")

    assert "User=agentbox\n" in api
    assert "User=agentbox\n" in worker
    assert "User=agentbox-runtime\n" in runtime
    assert "User=root\n" in helper
    assert "NoNewPrivileges=true" in api
    assert "NoNewPrivileges=true" in worker
    assert "NoNewPrivileges=true" in runtime
    assert "ProtectSystem=strict" in api
    assert "ReadWritePaths=/srv/agentbox/projects" not in api
    assert "ReadWritePaths=/srv/agentbox/projects" not in worker
    assert "ReadWritePaths=/var/lib/agentbox" not in runtime


def test_helper_socket_is_not_world_writable_and_units_are_namespaced() -> None:
    helper_socket = _unit("agentbox-helper.socket")
    assert "ListenStream=/run/agentbox/helper.sock" in helper_socket
    assert "SocketUser=root" in helper_socket
    assert "SocketGroup=agentbox" in helper_socket
    assert "SocketMode=0660" in helper_socket
    assert all(re.fullmatch(r"agentbox-[a-z-]+\.(?:service|socket)", name) for name in UNIT_NAMES)


def test_runtime_environment_has_no_application_secret_or_root_credentials() -> None:
    runtime = _unit("agentbox-runtime.service")
    forbidden = ("/root/.codex", "/root/.claude", "/root/.config/gh", "SECRET_KEY")
    assert all(value not in runtime for value in forbidden)


def test_systemd_analyze_verifies_units_against_fixture_root(tmp_path: Path) -> None:
    analyzer = shutil.which("systemd-analyze")
    if analyzer is None:
        pytest.skip("systemd-analyze is unavailable")
    root = tmp_path / "root"
    unit_root = root / "etc/systemd/system"
    executable_root = root / "opt/agentbox/current/venv/bin"
    unit_root.mkdir(parents=True)
    executable_root.mkdir(parents=True)
    (root / "etc/os-release").write_text('ID="agentbox-fixture"\n')
    for executable in ("agentbox-api", "agentbox-worker", "agentbox-runtime", "agentbox-helper"):
        path = executable_root / executable
        path.write_text("#!/bin/sh\nexit 0\n")
        path.chmod(0o755)
    asset_root = resources.files("agentbox_installer") / "assets/systemd"
    for name in UNIT_NAMES:
        (unit_root / name).write_text((asset_root / name).read_text())
    for target in (
        "sysinit.target",
        "basic.target",
        "network.target",
        "local-fs.target",
        "multi-user.target",
        "sockets.target",
        "shutdown.target",
    ):
        (unit_root / target).write_text(f"[Unit]\nDescription=Fixture {target}\n")

    result = subprocess.run(  # noqa: S603 - fixed diagnostic executable and fixture input
        (
            analyzer,
            f"--root={root}",
            "verify",
            *(str(unit_root / name) for name in UNIT_NAMES),
        ),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    for name in (
        "agentbox-api.service",
        "agentbox-worker.service",
        "agentbox-runtime.service",
        "agentbox-helper.service",
    ):
        security = subprocess.run(  # noqa: S603 - fixed offline unit assessment
            (
                analyzer,
                f"--root={root}",
                "security",
                "--offline=yes",
                name,
            ),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert security.returncode == 0, security.stderr
        assert "Overall exposure level" in security.stdout
