from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

import pytest
from agentbox_runtime.waw_fixed_transport import (
    NATIVE_READY,
    NATIVE_READY_DEADLINE_SECONDS,
)

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check-waw-native.py"


def test_native_sources_header_and_portable_c17_gate() -> None:
    completed = subprocess.run(
        [sys.executable, str(CHECK), "--portable-only"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "WAW native portable gate passed" in completed.stdout


def test_native_source_inventory_has_no_shell_or_path_lookup_execution() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "native" / "waw" / "src").glob("*.[ch]"))
    )
    forbidden = ("system" + "(", "popen" + "(", "execvp" + "(", "execlp" + "(")
    assert all(token not in source for token in forbidden)
    assert "/bin/" + "sh" not in source
    assert "execveat" in source
    assert "AT_EMPTY_PATH" in source
    assert "AGENTBOX_WAW_READY_STATUS_RUNNING" in source


def test_native_ready_header_matches_python_adapter() -> None:
    header = (ROOT / "native" / "waw" / "include" / "agentbox_waw_protocol.h").read_text(
        encoding="utf-8"
    )
    assert NATIVE_READY == b"AWR1\x01\x01\x00\x00"
    assert NATIVE_READY_DEADLINE_SECONDS == 1.0
    assert '#define AGENTBOX_WAW_READY_MAGIC "AWR1"' in header
    assert "AGENTBOX_WAW_READY_FRAME_BYTES UINT32_C(8)" in header
    assert "AGENTBOX_WAW_READY_DEADLINE_MS UINT32_C(1000)" in header


def test_linux_ci_uses_the_full_workspace_hash_for_cgroup_identity() -> None:
    workflow = (ROOT / ".github/workflows/backend.yml").read_text(encoding="utf-8")
    assert f"WORKSPACE_HASH: {'a' * 64}" in workflow
    assert "ws-${WORKSPACE_HASH}-g7/workload" in workflow
    assert "WORKSPACE_PREFIX" not in workflow
    assert "sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0" in workflow


@pytest.mark.skipif(platform.system() != "Linux", reason="Linux-only PTY/pidfd/execveat gate")
def test_linux_native_runtime_gate_is_collected_separately() -> None:
    assert platform.system() == "Linux"
