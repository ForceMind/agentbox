from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from agentbox_runtime import RuntimeOperationError, TmuxAdapter
from agentbox_runtime.process import ExecutableIdentity, ProcessResult, inspect_executable

FIXTURES = Path(__file__).parents[1] / "fixtures" / "tmux"


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.stdin: list[bytes | None] = []
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
        stdin_data: bytes | None = None,
        error_prefix: str = "CODEX",
    ) -> ProcessResult:
        del executable, environment, cwd, timeout_seconds, stdout_limit, stderr_limit
        del sensitive_output, error_prefix
        argv = tuple(arguments)
        self.calls.append(argv)
        self.stdin.append(stdin_data)
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
            1,
            b"",
            b"error connecting to /tmp/tmux-992/default (No such file or directory)\n",
        ),
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
async def test_tmux_pane_command_requires_claude_identity(tmp_path: Path) -> None:
    identity = make_executable(tmp_path / "bin" / "tmux")
    runner = RecordingRunner()
    runner.responses = [ProcessResult(("tmux",), 0, b"claude\n", b"")]
    adapter = TmuxAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(identity.path.parent)},
        runner=runner,  # type: ignore[arg-type]
    )
    assert await adapter.pane_command("agentbox-claude-project-123") == "claude"
    assert runner.calls == [
        (
            "display-message",
            "-p",
            "-t",
            "=agentbox-claude-project-123:0.0",
            "#{pane_current_command}",
        )
    ]


@pytest.mark.anyio
async def test_tmux_rejects_raw_session_name_injection(tmp_path: Path) -> None:
    identity = make_executable(tmp_path / "bin" / "tmux")
    adapter = TmuxAdapter(environment={"HOME": str(tmp_path), "PATH": str(identity.path.parent)})
    for name in ("../escape", "name; kill-server", "similar:1", "name with spaces"):
        with pytest.raises(RuntimeOperationError):
            await adapter.has_session(name)


@pytest.mark.anyio
async def test_tmux_write_input_uses_stdin_buffer_and_exact_pane(tmp_path: Path) -> None:
    identity = make_executable(tmp_path / "bin" / "tmux")
    runner = RecordingRunner()
    runner.responses = [
        ProcessResult(("tmux",), 0, b"", b""),
        ProcessResult(("tmux",), 0, b"", b""),
        ProcessResult(("tmux",), 0, b"", b""),
        ProcessResult(("tmux",), 0, b"", b""),
    ]
    adapter = TmuxAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(identity.path.parent)},
        runner=runner,  # type: ignore[arg-type]
    )
    name = "agentbox-waw-claude-123"
    payload = b"opaque\x00input\r"

    await adapter.write_input(name, payload)

    buffer_name = f"agentbox-waw-input-{name}"
    assert runner.calls == [
        ("has-session", "-t", f"={name}"),
        ("load-buffer", "-b", buffer_name, "-"),
        ("paste-buffer", "-d", "-b", buffer_name, "-t", f"={name}:0.0"),
        ("delete-buffer", "-b", buffer_name),
    ]
    assert runner.stdin == [None, payload, None, None]


@pytest.mark.anyio
async def test_tmux_write_input_deletes_buffer_when_paste_fails(tmp_path: Path) -> None:
    identity = make_executable(tmp_path / "bin" / "tmux")
    runner = RecordingRunner()
    runner.responses = [
        ProcessResult(("tmux",), 0, b"", b""),
        ProcessResult(("tmux",), 0, b"", b""),
        ProcessResult(("tmux",), 1, b"", b"paste failed"),
        ProcessResult(("tmux",), 0, b"", b""),
    ]
    adapter = TmuxAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(identity.path.parent)},
        runner=runner,  # type: ignore[arg-type]
    )
    name = "agentbox-waw-claude-paste-failure"

    with pytest.raises(RuntimeOperationError, match="could not be pasted"):
        await adapter.write_input(name, b"opaque input")

    buffer_name = f"agentbox-waw-input-{name}"
    assert runner.calls[-1] == ("delete-buffer", "-b", buffer_name)


@pytest.mark.anyio
async def test_tmux_write_input_cleans_buffer_when_load_fails(tmp_path: Path) -> None:
    identity = make_executable(tmp_path / "bin" / "tmux")
    runner = RecordingRunner()
    runner.responses = [
        ProcessResult(("tmux",), 0, b"", b""),
        ProcessResult(("tmux",), 1, b"", b"load failed"),
        ProcessResult(("tmux",), 0, b"", b""),
    ]
    adapter = TmuxAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(identity.path.parent)},
        runner=runner,  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeOperationError, match="could not be loaded"):
        await adapter.write_input("agentbox-waw-claude-load-failure", b"opaque input")

    assert runner.calls[-1] == (
        "delete-buffer",
        "-b",
        "agentbox-waw-input-agentbox-waw-claude-load-failure",
    )


@pytest.mark.anyio
async def test_tmux_write_input_treats_paste_delete_race_as_success(tmp_path: Path) -> None:
    """The -d paste can remove the buffer before explicit cleanup runs."""

    identity = make_executable(tmp_path / "bin" / "tmux")
    runner = RecordingRunner()
    runner.responses = [
        ProcessResult(("tmux",), 0, b"", b""),
        ProcessResult(("tmux",), 0, b"", b""),
        ProcessResult(("tmux",), 0, b"", b""),
        ProcessResult(("tmux",), 1, b"", b"buffer not found"),
    ]
    adapter = TmuxAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(identity.path.parent)},
        runner=runner,  # type: ignore[arg-type]
    )

    await adapter.write_input("agentbox-waw-claude-paste-canary", b"opaque input")
    assert runner.calls[-1][0] == "delete-buffer"


class OverlapDetectingRunner(RecordingRunner):
    def __init__(self) -> None:
        super().__init__()
        self._active_buffer_ops = 0
        self.max_active_buffer_ops = 0

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
        stdin_data: bytes | None = None,
        error_prefix: str = "CODEX",
    ) -> ProcessResult:
        if arguments[0] not in {"load-buffer", "paste-buffer", "delete-buffer"}:
            return await super().run(
                executable,
                arguments,
                environment=environment,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
                stdout_limit=stdout_limit,
                stderr_limit=stderr_limit,
                sensitive_output=sensitive_output,
                stdin_data=stdin_data,
                error_prefix=error_prefix,
            )
        self._active_buffer_ops += 1
        self.max_active_buffer_ops = max(self.max_active_buffer_ops, self._active_buffer_ops)
        try:
            await asyncio.sleep(0)
            return await super().run(
                executable,
                arguments,
                environment=environment,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
                stdout_limit=stdout_limit,
                stderr_limit=stderr_limit,
                sensitive_output=sensitive_output,
                stdin_data=stdin_data,
                error_prefix=error_prefix,
            )
        finally:
            self._active_buffer_ops -= 1


@pytest.mark.anyio
async def test_tmux_write_input_serializes_fixed_buffer_per_session(tmp_path: Path) -> None:
    identity = make_executable(tmp_path / "bin" / "tmux")
    runner = OverlapDetectingRunner()
    adapter = TmuxAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(identity.path.parent)},
        runner=runner,  # type: ignore[arg-type]
    )

    await asyncio.gather(
        adapter.write_input("agentbox-waw-claude-concurrent", b"first"),
        adapter.write_input("agentbox-waw-claude-concurrent", b"second"),
    )

    assert runner.max_active_buffer_ops == 1
    buffer_calls = [
        (call[0], stdin)
        for call, stdin in zip(runner.calls, runner.stdin, strict=True)
        if call[0] in {"load-buffer", "paste-buffer", "delete-buffer"}
    ]
    assert [call[0] for call in buffer_calls] == [
        "load-buffer",
        "paste-buffer",
        "delete-buffer",
        "load-buffer",
        "paste-buffer",
        "delete-buffer",
    ]
    assert [stdin for call, stdin in buffer_calls if call == "load-buffer"] == [
        b"first",
        b"second",
    ]


@pytest.mark.anyio
async def test_tmux_write_input_serializes_across_adapter_instances(tmp_path: Path) -> None:
    identity = make_executable(tmp_path / "bin" / "tmux")
    runner = OverlapDetectingRunner()
    environment = {"HOME": str(tmp_path), "PATH": str(identity.path.parent)}
    first = TmuxAdapter(environment=environment, runner=runner)  # type: ignore[arg-type]
    second = TmuxAdapter(environment=environment, runner=runner)  # type: ignore[arg-type]

    await asyncio.gather(
        first.write_input("agentbox-waw-claude-cross-instance", b"first"),
        second.write_input("agentbox-waw-claude-cross-instance", b"second"),
    )

    assert runner.max_active_buffer_ops == 1


@pytest.mark.anyio
async def test_tmux_write_input_serializes_across_event_loops(tmp_path: Path) -> None:
    identity = make_executable(tmp_path / "bin" / "tmux")
    runner = OverlapDetectingRunner()
    environment = {"HOME": str(tmp_path), "PATH": str(identity.path.parent)}
    first = TmuxAdapter(environment=environment, runner=runner)  # type: ignore[arg-type]
    second = TmuxAdapter(environment=environment, runner=runner)  # type: ignore[arg-type]

    def invoke(adapter: TmuxAdapter, payload: bytes) -> None:
        asyncio.run(adapter.write_input("agentbox-waw-claude-cross-loop", payload))

    await asyncio.gather(
        asyncio.to_thread(invoke, first, b"first"),
        asyncio.to_thread(invoke, second, b"second"),
    )

    assert runner.max_active_buffer_ops == 1


class RaisingRunner(RecordingRunner):
    def __init__(self, error: BaseException) -> None:
        super().__init__()
        self.error = error

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
        stdin_data: bytes | None = None,
        error_prefix: str = "CODEX",
    ) -> ProcessResult:
        del executable, environment, cwd, timeout_seconds, stdout_limit, stderr_limit
        del sensitive_output, error_prefix
        argv = tuple(arguments)
        self.calls.append(argv)
        self.stdin.append(stdin_data)
        if argv[0] == "paste-buffer":
            raise self.error
        return ProcessResult(argv, 0, b"", b"")


@pytest.mark.anyio
async def test_tmux_write_input_deletes_buffer_when_paste_raises(tmp_path: Path) -> None:
    identity = make_executable(tmp_path / "bin" / "tmux")
    runner = RaisingRunner(RuntimeOperationError("TMUX_COMMAND_TIMEOUT", "timed out"))
    adapter = TmuxAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(identity.path.parent)},
        runner=runner,  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeOperationError, match="timed out"):
        await adapter.write_input("agentbox-waw-claude-exception", b"opaque input")

    assert runner.calls[-1] == (
        "delete-buffer",
        "-b",
        "agentbox-waw-input-agentbox-waw-claude-exception",
    )
