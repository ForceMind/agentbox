from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from agentbox_runtime.codex import (
    CodexAdapter,
    CodexManager,
    CurrentUserProcessInspector,
    parse_pair_code,
)
from agentbox_runtime.models import (
    AuthenticationState,
    CapabilityState,
    InstallationType,
    RemoteState,
    RuntimeOperationError,
)
from agentbox_runtime.process import ExecutableIdentity, ProcessResult
from agentbox_runtime.waw_conflicts import (
    WAWConflictCoordinator,
    WAWLegacyClaudeState,
    WAWLegacyCodexState,
    WAWManagedConflictState,
)

FIXTURES = Path("tests/fixtures/codex")
CANARY = "PAIR-SECRET-CANARY-UNIT-7K3M"
FORMAL_PROJECT = "prj_" + "1" * 32


class FakeRunner:
    def __init__(self, responses: Mapping[tuple[str, ...], ProcessResult | Exception]) -> None:
        self.responses = dict(responses)
        self.calls: list[dict[str, Any]] = []

    async def run(
        self,
        executable: ExecutableIdentity,
        arguments: tuple[str, ...],
        **kwargs: Any,
    ) -> ProcessResult:
        self.calls.append({"executable": executable.path, "arguments": arguments, **kwargs})
        response = self.responses.get(arguments)
        if isinstance(response, Exception):
            raise response
        if response is None:
            return result(arguments, exit_code=1, stderr=b"not supported")
        return response


class FakeInspector:
    def __init__(self, running: bool = False) -> None:
        self.running = running

    def is_remote_running(self, executable: Path) -> bool:
        del executable
        return self.running


class ConflictProbe:
    def __init__(self, states: tuple[WAWManagedConflictState, ...] = ()) -> None:
        self.states = states
        self.calls: list[str] = []

    def legacy_claude(self, project_id: str) -> WAWLegacyClaudeState:
        del project_id
        return WAWLegacyClaudeState.ABSENT

    def legacy_codex_remote(self) -> WAWLegacyCodexState:
        return WAWLegacyCodexState.ABSENT

    def waw_for_project(self, project_id: str) -> tuple[WAWManagedConflictState, ...]:
        self.calls.append(project_id)
        return self.states

    def waw_for_host(self) -> tuple[WAWManagedConflictState, ...]:
        self.calls.append("host")
        return self.states


def result(
    arguments: tuple[str, ...],
    *,
    stdout: bytes = b"",
    stderr: bytes = b"",
    exit_code: int = 0,
) -> ProcessResult:
    return ProcessResult(
        argv=("/fixture/codex", *arguments),
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
    )


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def make_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/false\n", encoding="utf-8")
    path.chmod(0o755)


def base_responses(
    *, remote_help: bytes | None = None
) -> dict[tuple[str, ...], ProcessResult | Exception]:
    remote = remote_help or fixture("0.146.1-remote-help-no-status.txt")
    return {
        ("--version",): result(("--version",), stdout=b"codex-cli 0.146.1\n"),
        ("--help",): result(("--help",), stdout=fixture("0.146.1-main-help.txt")),
        ("remote-control", "--help"): result(("remote-control", "--help"), stdout=remote),
        ("login", "--help"): result(
            ("login", "--help"), stdout=b"Commands:\n  status  Show login status\n"
        ),
        ("login", "status"): result(("login", "status"), stdout=b"Authenticated with ChatGPT\n"),
    }


@pytest.mark.anyio
async def test_current_standalone_capabilities_without_status(tmp_path: Path) -> None:
    home = tmp_path / "home"
    codex = home / ".local/bin/codex"
    make_executable(codex)
    runner = FakeRunner(base_responses())
    adapter = CodexAdapter(
        environment={"HOME": str(home), "PATH": str(codex.parent)},
        runner=runner,  # type: ignore[arg-type]
        process_inspector=FakeInspector(),  # type: ignore[arg-type]
    )

    status = await adapter.status()

    assert status.installed is True
    assert status.version == "0.146.1"
    assert status.installation_type is InstallationType.STANDALONE
    assert status.authentication is AuthenticationState.AUTHENTICATED
    assert status.capabilities.remote_control is CapabilityState.SUPPORTED
    assert status.capabilities.start is CapabilityState.SUPPORTED
    assert status.capabilities.stop is CapabilityState.SUPPORTED
    assert status.capabilities.pair is CapabilityState.SUPPORTED
    assert status.capabilities.status is CapabilityState.UNSUPPORTED
    assert status.remote_state is RemoteState.UNKNOWN


@pytest.mark.anyio
async def test_missing_remote_control_is_unsupported(tmp_path: Path) -> None:
    codex = tmp_path / "bin/codex"
    make_executable(codex)
    responses: dict[tuple[str, ...], ProcessResult | Exception] = base_responses()
    responses[("--help",)] = result(("--help",), stdout=fixture("no-remote-control-main-help.txt"))
    adapter = CodexAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(codex.parent)},
        runner=FakeRunner(responses),  # type: ignore[arg-type]
        process_inspector=FakeInspector(),  # type: ignore[arg-type]
    )
    status = await adapter.status()
    assert status.capabilities.remote_control is CapabilityState.UNSUPPORTED
    assert status.capabilities.pair is CapabilityState.UNSUPPORTED


@pytest.mark.anyio
async def test_malformed_and_nonzero_help_are_unknown(tmp_path: Path) -> None:
    codex = tmp_path / "bin/codex"
    make_executable(codex)
    for help_result in (
        result(("--help",), stdout=fixture("malformed-help.txt")),
        result(("--help",), exit_code=2, stderr=b"failed"),
    ):
        responses: dict[tuple[str, ...], ProcessResult | Exception] = base_responses()
        responses[("--help",)] = help_result
        adapter = CodexAdapter(
            environment={"HOME": str(tmp_path), "PATH": str(codex.parent)},
            runner=FakeRunner(responses),  # type: ignore[arg-type]
            process_inspector=FakeInspector(),  # type: ignore[arg-type]
        )
        assert (await adapter.status()).capabilities.remote_control is CapabilityState.UNKNOWN


@pytest.mark.anyio
async def test_help_timeout_degrades_capabilities_to_unknown(tmp_path: Path) -> None:
    codex = tmp_path / "bin/codex"
    make_executable(codex)
    responses: dict[tuple[str, ...], ProcessResult | Exception] = base_responses()
    responses[("--help",)] = RuntimeOperationError(
        "CODEX_COMMAND_TIMEOUT", "Codex command timed out", category="timeout"
    )
    adapter = CodexAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(codex.parent)},
        runner=FakeRunner(responses),  # type: ignore[arg-type]
        process_inspector=FakeInspector(),  # type: ignore[arg-type]
    )

    status = await adapter.status()

    assert status.installed is True
    assert status.capabilities.remote_control is CapabilityState.UNKNOWN
    assert "CODEX_CAPABILITY_PROBE_FAILED" in {finding.code for finding in status.diagnostics}


@pytest.mark.anyio
async def test_unknown_future_remote_command_does_not_enable_actions(tmp_path: Path) -> None:
    codex = tmp_path / "bin/codex"
    make_executable(codex)
    responses = base_responses(remote_help=b"Commands:\n  teleport  Future action\n")
    adapter = CodexAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(codex.parent)},
        runner=FakeRunner(responses),  # type: ignore[arg-type]
        process_inspector=FakeInspector(),  # type: ignore[arg-type]
    )

    capabilities = (await adapter.status()).capabilities

    assert capabilities.remote_control is CapabilityState.SUPPORTED
    assert capabilities.start is CapabilityState.UNSUPPORTED
    assert capabilities.stop is CapabilityState.UNSUPPORTED
    assert capabilities.pair is CapabilityState.UNSUPPORTED


@pytest.mark.anyio
async def test_installation_detection_covers_missing_npm_and_conflict(tmp_path: Path) -> None:
    missing = CodexAdapter(environment={"HOME": str(tmp_path), "PATH": str(tmp_path / "empty")})
    assert (await missing.status()).installed is False

    home = tmp_path / "home"
    codex = home / ".local/bin/codex"
    npm = home / ".local/bin/npm"
    make_executable(codex)
    make_executable(npm)
    responses = base_responses()
    responses[("list", "-g", "--depth=0", "--json")] = result(
        ("list", "-g", "--depth=0", "--json"),
        stdout=json.dumps({"dependencies": {"@openai/codex": {"version": "0.1"}}}).encode(),
    )
    adapter = CodexAdapter(
        environment={"HOME": str(home), "PATH": str(codex.parent)},
        runner=FakeRunner(responses),  # type: ignore[arg-type]
        process_inspector=FakeInspector(),  # type: ignore[arg-type]
    )
    status = await adapter.status()
    assert status.installation_type is InstallationType.CONFLICT
    assert status.conflict_detected is True


@pytest.mark.anyio
async def test_npm_only_and_broken_path_candidate_are_classified_safely(
    tmp_path: Path,
) -> None:
    npm_bin = tmp_path / "npm-bin"
    (tmp_path / "home").mkdir()
    codex = npm_bin / "codex"
    npm = npm_bin / "npm"
    make_executable(codex)
    make_executable(npm)
    responses = base_responses()
    responses[("list", "-g", "--depth=0", "--json")] = result(
        ("list", "-g", "--depth=0", "--json"),
        stdout=b'{"dependencies":{"@openai/codex":{"version":"0.1"}}}',
    )
    adapter = CodexAdapter(
        environment={"HOME": str(tmp_path / "home"), "PATH": str(npm_bin)},
        runner=FakeRunner(responses),  # type: ignore[arg-type]
        process_inspector=FakeInspector(),  # type: ignore[arg-type]
    )
    assert (await adapter.status()).installation_type is InstallationType.NPM

    broken_bin = tmp_path / "broken-bin"
    broken_bin.mkdir()
    (broken_bin / "codex").symlink_to(tmp_path / "missing")
    broken = CodexAdapter(environment={"HOME": str(tmp_path), "PATH": str(broken_bin)})
    broken_status = await broken.status()
    assert broken_status.installed is False
    assert "CODEX_ALTERNATIVE_INVALID" in {finding.code for finding in broken_status.diagnostics}


@pytest.mark.anyio
async def test_remote_action_result_is_not_reused_as_live_state(tmp_path: Path) -> None:
    codex = tmp_path / "bin/codex"
    make_executable(codex)
    responses = base_responses()
    responses[("remote-control", "start")] = result(("remote-control", "start"))
    responses[("remote-control", "stop")] = result(("remote-control", "stop"))
    runner = FakeRunner(responses)
    adapter = CodexAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(codex.parent)},
        runner=runner,  # type: ignore[arg-type]
        process_inspector=FakeInspector(),  # type: ignore[arg-type]
    )
    assert (await adapter.start_remote()).outcome == "started"
    assert (await adapter.status()).remote_state is RemoteState.UNKNOWN
    assert (await adapter.start_remote()).outcome == "started"
    assert (await adapter.stop_remote()).outcome == "stopped"
    assert (await adapter.status()).remote_state is RemoteState.UNKNOWN
    assert (await adapter.stop_remote()).outcome == "stopped"
    assert sum(call["arguments"] == ("remote-control", "start") for call in runner.calls) == 2
    assert sum(call["arguments"] == ("remote-control", "stop") for call in runner.calls) == 2


@pytest.mark.anyio
async def test_live_process_evidence_keeps_start_idempotent(tmp_path: Path) -> None:
    codex = tmp_path / "bin/codex"
    make_executable(codex)
    runner = FakeRunner(base_responses())
    adapter = CodexAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(codex.parent)},
        runner=runner,  # type: ignore[arg-type]
        process_inspector=FakeInspector(running=True),  # type: ignore[arg-type]
    )

    assert (await adapter.start_remote()).outcome == "already_running"
    assert not any(call["arguments"] == ("remote-control", "start") for call in runner.calls)


@pytest.mark.anyio
async def test_native_remote_status_distinguishes_not_running_and_broken(
    tmp_path: Path,
) -> None:
    codex = tmp_path / "bin/codex"
    make_executable(codex)
    remote_help = b"Commands:\n  start  Start\n  stop  Stop\n  pair  Pair\n  status  Status\n"
    for status_result, expected in (
        (
            result(("remote-control", "status"), stdout=b"Remote is not running\n"),
            RemoteState.STOPPED,
        ),
        (
            result(("remote-control", "status"), stdout=b"Remote is active\n"),
            RemoteState.RUNNING,
        ),
        (
            result(("remote-control", "status"), exit_code=2, stderr=b"failed"),
            RemoteState.BROKEN,
        ),
    ):
        responses = base_responses(remote_help=remote_help)
        responses[("remote-control", "status")] = status_result
        adapter = CodexAdapter(
            environment={"HOME": str(tmp_path), "PATH": str(codex.parent)},
            runner=FakeRunner(responses),  # type: ignore[arg-type]
            process_inspector=FakeInspector(),  # type: ignore[arg-type]
        )
        assert (await adapter.status()).remote_state is expected


@pytest.mark.anyio
async def test_unsupported_start_fails_without_invocation(tmp_path: Path) -> None:
    codex = tmp_path / "bin/codex"
    make_executable(codex)
    responses = base_responses(remote_help=b"Commands:\n  pair  Pair\n")
    runner = FakeRunner(responses)
    adapter = CodexAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(codex.parent)},
        runner=runner,  # type: ignore[arg-type]
        process_inspector=FakeInspector(),  # type: ignore[arg-type]
    )
    with pytest.raises(RuntimeOperationError) as raised:
        await adapter.start_remote()
    assert raised.value.code == "CODEX_REMOTE_UNSUPPORTED"
    assert not any(call["arguments"] == ("remote-control", "start") for call in runner.calls)


@pytest.mark.anyio
async def test_remote_action_failure_and_timeout_are_safe(tmp_path: Path) -> None:
    codex = tmp_path / "bin/codex"
    make_executable(codex)
    for failure, expected in (
        (result(("remote-control", "start"), exit_code=2), "CODEX_REMOTE_START_FAILED"),
        (
            RuntimeOperationError(
                "CODEX_COMMAND_TIMEOUT", "Codex command timed out", category="timeout"
            ),
            "CODEX_COMMAND_TIMEOUT",
        ),
    ):
        responses: dict[tuple[str, ...], ProcessResult | Exception] = base_responses()
        responses[("remote-control", "start")] = failure
        adapter = CodexAdapter(
            environment={"HOME": str(tmp_path), "PATH": str(codex.parent)},
            runner=FakeRunner(responses),  # type: ignore[arg-type]
            process_inspector=FakeInspector(),  # type: ignore[arg-type]
        )
        with pytest.raises(RuntimeOperationError) as raised:
            await adapter.start_remote()
        assert raised.value.code == expected


@pytest.mark.anyio
async def test_bound_waw_rows_block_codex_remote_before_start(tmp_path: Path) -> None:
    codex = tmp_path / "bin/codex"
    make_executable(codex)
    runner = FakeRunner(base_responses())
    adapter = CodexAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(codex.parent)},
        runner=runner,  # type: ignore[arg-type]
        process_inspector=FakeInspector(),  # type: ignore[arg-type]
    )
    probe = ConflictProbe((WAWManagedConflictState.RUNNING,))
    manager = CodexManager(adapter, conflict_coordinator=WAWConflictCoordinator(probe))

    with pytest.raises(RuntimeOperationError) as raised:
        await manager.start_remote()

    assert raised.value.code == "CODEX_REMOTE_CONFLICT"
    assert probe.calls == ["host"]
    assert runner.calls == []


@pytest.mark.anyio
async def test_codex_remote_holds_host_lease_through_command_completion(tmp_path: Path) -> None:
    codex = tmp_path / "bin/codex"
    make_executable(codex)
    responses = base_responses()
    responses[("remote-control", "start")] = result(("remote-control", "start"))
    runner = FakeRunner(responses)
    original_run = runner.run
    entered_start = asyncio.Event()
    release_start = asyncio.Event()

    async def paused_run(
        executable: ExecutableIdentity, arguments: tuple[str, ...], **kwargs: Any
    ) -> ProcessResult:
        if arguments == ("remote-control", "start"):
            entered_start.set()
            await release_start.wait()
        return await original_run(executable, arguments, **kwargs)

    runner.run = paused_run  # type: ignore[method-assign]
    adapter = CodexAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(codex.parent)},
        runner=runner,  # type: ignore[arg-type]
        process_inspector=FakeInspector(),  # type: ignore[arg-type]
    )
    coordinator = WAWConflictCoordinator(ConflictProbe())
    manager = CodexManager(adapter, conflict_coordinator=coordinator)
    start = asyncio.create_task(manager.start_remote())
    await asyncio.wait_for(entered_start.wait(), timeout=1)
    competing = asyncio.create_task(
        asyncio.to_thread(coordinator.acquire_legacy_claude_start, project_id=FORMAL_PROJECT)
    )
    await asyncio.sleep(0.02)
    assert not competing.done()
    release_start.set()
    assert (await start).outcome == "started"
    (await competing).release()


def test_pair_parser_is_conservative_and_discards_raw_output() -> None:
    assert parse_pair_code(f"Pairing code: {CANARY}\n".encode(), b"").code == CANARY
    for output in (b"unlabelled ABCD-1234\n", b"Pairing code: ONE1\nPair code: TWO2\n"):
        with pytest.raises(RuntimeOperationError) as raised:
            parse_pair_code(output, b"")
        assert raised.value.code == "CODEX_PAIR_OUTPUT_UNRECOGNIZED"
        assert not any(value in str(raised.value) for value in ("ABCD-1234", "ONE1", "TWO2"))


@pytest.mark.anyio
async def test_pair_cooldown_is_deterministic(tmp_path: Path) -> None:
    codex = tmp_path / "bin/codex"
    make_executable(codex)
    responses = base_responses()
    responses[("remote-control", "pair")] = result(
        ("remote-control", "pair"), stdout=f"Pairing code: {CANARY}\n".encode()
    )
    runner = FakeRunner(responses)
    adapter = CodexAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(codex.parent)},
        runner=runner,  # type: ignore[arg-type]
        process_inspector=FakeInspector(),  # type: ignore[arg-type]
    )
    now = [100.0]
    manager = CodexManager(adapter, pair_cooldown_seconds=10, monotonic=lambda: now[0])
    assert (await manager.generate_pair_code()).code == CANARY
    with pytest.raises(RuntimeOperationError) as raised:
        await manager.generate_pair_code()
    assert raised.value.code == "CODEX_PAIR_RATE_LIMITED"
    assert raised.value.retry_after == 10
    now[0] += 10
    assert (await manager.generate_pair_code()).code == CANARY


@pytest.mark.anyio
async def test_unauthenticated_pair_fails_before_pair_command(tmp_path: Path) -> None:
    codex = tmp_path / "bin/codex"
    make_executable(codex)
    responses = base_responses()
    responses[("login", "status")] = result(
        ("login", "status"), exit_code=1, stderr=b"Not logged in\n"
    )
    runner = FakeRunner(responses)
    adapter = CodexAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(codex.parent)},
        runner=runner,  # type: ignore[arg-type]
        process_inspector=FakeInspector(),  # type: ignore[arg-type]
    )
    with pytest.raises(RuntimeOperationError) as raised:
        await adapter.generate_pair_code()
    assert raised.value.code == "CODEX_UNAUTHENTICATED"
    assert not any(call["arguments"] == ("remote-control", "pair") for call in runner.calls)


@pytest.mark.anyio
async def test_pair_timeout_is_normalized_without_output(tmp_path: Path) -> None:
    codex = tmp_path / "bin/codex"
    make_executable(codex)
    responses: dict[tuple[str, ...], ProcessResult | Exception] = base_responses()
    responses[("remote-control", "pair")] = RuntimeOperationError(
        "CODEX_COMMAND_TIMEOUT", "Codex command timed out", category="timeout"
    )
    adapter = CodexAdapter(
        environment={"HOME": str(tmp_path), "PATH": str(codex.parent)},
        runner=FakeRunner(responses),  # type: ignore[arg-type]
        process_inspector=FakeInspector(),  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeOperationError) as raised:
        await adapter.generate_pair_code()

    assert raised.value.code == "CODEX_PAIR_TIMEOUT"
    assert raised.value.retryable is True


def test_process_inspector_rejects_unrelated_argv_and_executable(tmp_path: Path) -> None:
    expected = tmp_path / "codex"
    unrelated = tmp_path / "other"
    make_executable(expected)
    make_executable(unrelated)
    expected_resolved = expected.resolve()
    proc = tmp_path / "proc"
    for pid, executable, argv in (
        ("101", unrelated, b"other\0remote-control\0start\0"),
        ("102", expected, b"codex\0exec\0start\0"),
    ):
        process = proc / pid
        process.mkdir(parents=True)
        (process / "exe").symlink_to(executable)
        (process / "cmdline").write_bytes(argv)
    inspector = CurrentUserProcessInspector(proc_root=proc)

    assert inspector.is_remote_running(expected_resolved) is False

    matching = proc / "103"
    matching.mkdir()
    (matching / "exe").symlink_to(expected)
    (matching / "cmdline").write_bytes(b"codex\0remote-control\0start\0")
    assert inspector.is_remote_running(expected_resolved) is True
