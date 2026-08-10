from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from agentbox_runtime import RuntimeOperationError, TmuxAdapter
from agentbox_runtime.process import ExecutableIdentity, ProcessResult, inspect_executable

FIXTURES = Path(__file__).parents[1] / "fixtures" / "tmux"


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.responses: list[ProcessResult] = []

    async def run(
        self,
        executable: ExecutableIdentity,
        arguments: Sequence[str],
        *,
        environment: Mapping[str, str],
        cwd: Path,
        timeout_seconds: float,
        stdout_limit: int,
        stderr_limit: int,
        sensitive_output: bool = False,
        error_prefix: str = "CODEX",
    ) -> ProcessResult:
        del executable, environment, cwd, timeout_seconds, stdout_limit, stderr_limit
        del sensitive_output, error_prefix
        argv = tuple(arguments)
        self.calls.append(argv)
        return self.responses.pop(0) if self.responses else ProcessResult(argv, 0, b"", b"")


def make_executable(path: Path) -> ExecutableIdentity:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(0o755)
    return inspect_executable(path)


@pytest.mark.anyio
async def test_tmux_create_uses_fixed_argv_cwd_and_management_marker(tmp_path: Path) -> None:
    tmux_identity = make_executable(tmp_path / "bin" / "tmux")
    claude_identity = make_executable(tmp_path / "bin" / "claude")
    sleep_identity = make_executable(tmp_path / "bin" / "sleep")
    project = tmp_path / "project with spaces"
    project.mkdir()
    runner = RecordingRunner()
    adapter = TmuxAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(tmux_identity.path.parent)},
        runner=runner,  # type: ignore[arg-type]
    )
    await adapter.create_session(
        "agentbox-claude-safe-a1b2c3",
        cwd=project,
        command=claude_identity,
        managed_marker="v1:0123456789abcdef",
    )

    assert runner.calls == [
        (
            "new-session",
            "-d",
            "-s",
            "agentbox-claude-safe-a1b2c3",
            "-c",
            str(project),
            "-e",
            "AGENTBOX_MANAGED_SESSION=v1:0123456789abcdef",
            str(sleep_identity.path),
            "30",
            ";",
            "set-window-option",
            "-t",
            "=agentbox-claude-safe-a1b2c3:0",
            "remain-on-exit",
            "on",
            ";",
            "respawn-pane",
            "-k",
            "-t",
            "=agentbox-claude-safe-a1b2c3:0.0",
            "-c",
            str(project),
            str(claude_identity.path),
            "remote-control",
        ),
    ]
    assert all("kill-server" not in call and "pkill" not in call for call in runner.calls)


@pytest.mark.anyio
async def test_tmux_exact_targets_and_bounded_capture(tmp_path: Path) -> None:
    identity = make_executable(tmp_path / "bin" / "tmux")
    runner = RecordingRunner()
    runner.responses = [
        ProcessResult(("tmux",), 0, b"", b""),
        ProcessResult(("tmux",), 0, (FIXTURES / "capture-pane.txt").read_bytes(), b""),
        ProcessResult(("tmux",), 0, b"", b""),
        ProcessResult(("tmux",), 0, b"", b""),
    ]
    adapter = TmuxAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(identity.path.parent)},
        runner=runner,  # type: ignore[arg-type]
    )
    name = "agentbox-claude-project-123"
    assert await adapter.has_session(name) is True
    assert (
        await adapter.capture_pane(name, lines=100) == (FIXTURES / "capture-pane.txt").read_bytes()
    )
    assert await adapter.kill_session(name) is True
    assert runner.calls == [
        ("has-session", "-t", f"={name}"),
        ("capture-pane", "-p", "-t", f"={name}:0.0", "-S", "-100"),
        ("has-session", "-t", f"={name}"),
        ("kill-session", "-t", f"={name}"),
    ]


@pytest.mark.anyio
async def test_tmux_list_fixtures_distinguish_safe_and_malformed_names(tmp_path: Path) -> None:
    identity = make_executable(tmp_path / "bin" / "tmux")
    runner = RecordingRunner()
    runner.responses = [
        ProcessResult(("tmux",), 0, (FIXTURES / "empty-list.txt").read_bytes(), b""),
        ProcessResult(
            ("tmux",),
            0,
            b"".join(
                [
                    (FIXTURES / "managed-list.txt").read_bytes(),
                    (FIXTURES / "unmanaged-list.txt").read_bytes(),
                    (FIXTURES / "malformed-list.txt").read_bytes(),
                ]
            ),
            b"",
        ),
        ProcessResult(("tmux",), 1, b"", (FIXTURES / "missing-session.txt").read_bytes()),
    ]
    adapter = TmuxAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(identity.path.parent)},
        runner=runner,  # type: ignore[arg-type]
    )

    assert await adapter.list_sessions() == ()
    assert await adapter.list_sessions() == (
        "agentbox-claude-project-a-123456789abc",
        "personal-session",
        "claude-legacy",
    )
    assert await adapter.has_session("agentbox-claude-project-a-123456789abc") is False


@pytest.mark.anyio
async def test_tmux_prepares_fixed_direct_workspace_interaction(tmp_path: Path) -> None:
    tmux_identity = make_executable(tmp_path / "bin" / "tmux")
    claude_identity = make_executable(tmp_path / "bin" / "claude")
    project = (tmp_path / "project").resolve()
    project.mkdir()
    runner = RecordingRunner()
    runner.responses = [
        ProcessResult(("tmux",), 0, b"1\n", b""),
        ProcessResult(("tmux",), 0, b"", b""),
    ]
    adapter = TmuxAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(tmux_identity.path.parent)},
        runner=runner,  # type: ignore[arg-type]
    )
    name = "agentbox-claude-project-123"

    assert await adapter.pane_dead(name) is True
    await adapter.prepare_workspace_interaction(name, cwd=project, command=claude_identity)

    assert runner.calls == [
        ("display-message", "-p", "-t", f"={name}:0.0", "#{pane_dead}"),
        (
            "respawn-pane",
            "-k",
            "-t",
            f"={name}:0.0",
            "-c",
            str(project),
            str(claude_identity.path),
            "--",
        ),
    ]
    assert all(len(call) > 1 and "sh" not in call for call in runner.calls)


@pytest.mark.anyio
async def test_tmux_rejects_raw_session_name_injection(tmp_path: Path) -> None:
    identity = make_executable(tmp_path / "bin" / "tmux")
    adapter = TmuxAdapter(environment={"HOME": str(tmp_path), "PATH": str(identity.path.parent)})
    for name in ("../escape", "name; kill-server", "similar:1", "name with spaces"):
        with pytest.raises(RuntimeOperationError):
            await adapter.has_session(name)
