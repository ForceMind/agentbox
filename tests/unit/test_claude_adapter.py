from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from agentbox_runtime import (
    AuthenticationState,
    CapabilityState,
    ClaudeAdapter,
    RuntimeOperationError,
    sanitize_pane_output,
)
from agentbox_runtime.claude import classify_startup_output
from agentbox_runtime.models import ClaudeSessionState
from agentbox_runtime.process import ExecutableIdentity, ProcessResult

FIXTURES = Path(__file__).parents[1] / "fixtures" / "claude"


class FixtureRunner:
    def __init__(self, responses: Mapping[tuple[str, ...], ProcessResult | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[tuple[str, ...], Path]] = []

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
        del executable, environment, timeout_seconds, stdout_limit, stderr_limit
        del sensitive_output, error_prefix
        key = tuple(arguments)
        self.calls.append((key, cwd))
        response = self.responses[key]
        if isinstance(response, Exception):
            raise response
        return response


def result(stdout: bytes = b"", stderr: bytes = b"", exit_code: int = 0) -> ProcessResult:
    return ProcessResult(("/fixture/claude",), exit_code, stdout, stderr)


def executable(tmp_path: Path) -> Path:
    binary = tmp_path / "bin" / "claude"
    binary.parent.mkdir()
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    return binary


@pytest.mark.anyio
async def test_claude_capabilities_use_public_help_not_version_guess(tmp_path: Path) -> None:
    binary = executable(tmp_path)
    runner = FixtureRunner(
        {
            ("--version",): result(b"claude 1.2.3\n"),
            ("--help",): result((FIXTURES / "remote-supported.txt").read_bytes()),
            ("remote-control", "--help"): result((FIXTURES / "remote-help.txt").read_bytes()),
            ("auth", "status"): result(
                (FIXTURES / "unauthenticated.txt").read_bytes(), exit_code=1
            ),
        }
    )
    adapter = ClaudeAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(binary.parent)},
        runner=runner,  # type: ignore[arg-type]
    )

    installed, version, authentication, capabilities, _findings = await adapter.inspect()
    assert installed is True
    assert version == "1.2.3"
    assert authentication is AuthenticationState.UNAUTHENTICATED
    assert capabilities.remote_control is CapabilityState.SUPPORTED
    assert capabilities.remote_start is CapabilityState.SUPPORTED
    assert all(cwd == tmp_path for _arguments, cwd in runner.calls)


@pytest.mark.anyio
async def test_claude_remote_unsupported_and_probe_timeout_fail_closed(tmp_path: Path) -> None:
    binary = executable(tmp_path)
    runner = FixtureRunner(
        {
            ("--version",): result(b"claude 9.9.9"),
            ("--help",): result((FIXTURES / "remote-unsupported.txt").read_bytes()),
            ("auth", "status"): RuntimeOperationError(
                "CLAUDE_COMMAND_TIMEOUT", "Runtime command timed out", category="timeout"
            ),
        }
    )
    adapter = ClaudeAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(binary.parent)},
        runner=runner,  # type: ignore[arg-type]
    )
    _installed, _version, auth, capabilities, _findings = await adapter.inspect()
    assert auth is AuthenticationState.UNKNOWN
    assert capabilities.remote_control is CapabilityState.UNSUPPORTED


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("trust-prompt.txt", ClaudeSessionState.NEEDS_INTERACTION),
        ("unauthenticated.txt", ClaudeSessionState.NEEDS_INTERACTION),
        ("ready.txt", ClaudeSessionState.RUNNING),
        ("unexpected.txt", ClaudeSessionState.UNKNOWN),
    ],
)
def test_startup_output_parser_is_conservative(fixture: str, expected: ClaudeSessionState) -> None:
    assert classify_startup_output((FIXTURES / fixture).read_text()) is expected


def test_pane_output_is_line_byte_and_control_bounded() -> None:
    raw = b"first\n\x1b[31msecret-like text\x1b[0m\n\x00bad\x07\nlast"
    output, truncated = sanitize_pane_output(raw, line_limit=3, byte_limit=32)
    assert "\x1b" not in output and "\x00" not in output and "\x07" not in output
    assert output.endswith("last")
    assert len(output.encode()) <= 32
    assert truncated is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"2.1.226 (Claude Code)\n", "2.1.226"),
        (b"claude 1.2.3\n", "1.2.3"),
        (b"Claude Code version 3.4.5-beta.1\n", "3.4.5-beta.1"),
    ],
)
def test_claude_version_parser_supports_public_output_orders(raw: bytes, expected: str) -> None:
    assert ClaudeAdapter._parse_version(result(raw)) == expected
