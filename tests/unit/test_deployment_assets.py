from __future__ import annotations

import re
import shutil
import subprocess
from importlib import resources
from pathlib import Path

import pytest
from agentbox_installer.hardening import (
    HardeningDecision,
    review_unit_hardening,
    systemd_capabilities,
)
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
    for unit in (api, worker, runtime, helper):
        assert "CapabilityBoundingSet=\n" in unit
        assert "AmbientCapabilities=\n" in unit
        assert "PrivateDevices=true" in unit
        assert "ProtectClock=true" in unit
        assert "ProtectHostname=true" in unit
        assert "ProtectKernelLogs=true" in unit
        assert "RestrictRealtime=true" in unit
        assert "SystemCallArchitectures=native" in unit
    for unit in (api, worker, helper):
        assert "RestrictNamespaces=true" in unit
        assert "MemoryDenyWriteExecute=true" in unit
        assert "SystemCallFilter=@system-service" in unit
        assert "SystemCallErrorNumber=EPERM" in unit
    assert "RestrictNamespaces=true" not in runtime
    assert "MemoryDenyWriteExecute=true" not in runtime
    assert "PrivateNetwork=true" in helper
    assert "ReadWritePaths=" not in helper


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


def test_systemd_units_contain_only_static_typed_execution_fields() -> None:
    expected = {
        "agentbox-api.service": "/opt/agentbox/current/venv/bin/agentbox-api",
        "agentbox-worker.service": "/opt/agentbox/current/venv/bin/agentbox-worker",
        "agentbox-runtime.service": "/opt/agentbox/current/venv/bin/agentbox-runtime",
        "agentbox-helper.service": "/opt/agentbox/current/venv/bin/agentbox-helper",
    }
    for name, executable in expected.items():
        unit = _unit(name)
        exec_lines = [line for line in unit.splitlines() if line.startswith("ExecStart=")]
        assert exec_lines == [f"ExecStart={executable}"]
        assert "/bin/sh" not in unit
        assert "$" not in unit
        assert "{" not in unit
        assert "Environment=" not in unit
    assert "User=agentbox\n" in _unit("agentbox-api.service")
    assert "User=agentbox\n" in _unit("agentbox-worker.service")
    assert "User=agentbox-runtime\n" in _unit("agentbox-runtime.service")
    assert "User=root\n" in _unit("agentbox-helper.service")


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

    if "Option --root is only supported for cat-config" in result.stderr:
        pytest.skip("installed systemd-analyze cannot verify a fixture root")
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


@pytest.mark.parametrize("systemd_version", [249, 252, 255])
def test_units_are_compatible_with_every_qualified_systemd_baseline(
    systemd_version: int,
) -> None:
    for name in UNIT_NAMES:
        matrix = systemd_capabilities(_unit(name), systemd_version)
        assert matrix.compatible, (name, matrix.unsupported_directives)


def test_hardening_review_preserves_runtime_compatibility_exceptions() -> None:
    for name in (
        "agentbox-api.service",
        "agentbox-worker.service",
        "agentbox-helper.service",
    ):
        findings = review_unit_hardening(name, _unit(name))
        assert all(item.decision is HardeningDecision.APPLIED for item in findings)

    runtime = review_unit_hardening("agentbox-runtime.service", _unit("agentbox-runtime.service"))
    assert {item.directive for item in runtime} == {
        "SystemCallFilter",
        "RestrictNamespaces",
        "MemoryDenyWriteExecute",
    }
    assert all(item.decision is HardeningDecision.ACCEPTED_LIMITATION for item in runtime)
