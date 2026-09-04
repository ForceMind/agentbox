from __future__ import annotations

import asyncio
import dataclasses
import os
import signal
import sys
from pathlib import Path
from typing import Any

import pytest
from agentbox_core.waw import AgentType
from agentbox_runtime import waw_vendor_probe as subject
from agentbox_runtime.waw_process_profile import INTERACTIVE_PROFILE_CONSTANTS_V1
from agentbox_runtime.waw_vendor_probe import (
    WAW_VENDOR_PROBE_OUTPUT_LIMIT,
    WAWIsolatedProbeCompletion,
    WAWProcessIsolationKind,
    WAWProcessIsolationPort,
    WAWVendorProbeError,
    WAWVendorProbeFailure,
    WAWVendorProbeId,
    WAWVendorProbeParserId,
    WAWVendorProbeProfile,
    WAWVendorProbeResult,
    WAWVendorProbeRunner,
    waw_vendor_probe_output_digest,
)

CODEX_UNAUTH = b"Not logged in\n"


class _QualifiedPort(WAWProcessIsolationPort):
    def __init__(
        self,
        *,
        exit_code: int,
        stdout: bytes = b"",
        stderr: bytes = b"",
        descendants_remaining: int = 0,
    ) -> None:
        super().__init__(
            isolation_kind=WAWProcessIsolationKind.PREBIRTH_CGROUP,
            production_qualified=True,
        )
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.descendants_remaining = descendants_remaining

    async def execute(
        self,
        profile: WAWVendorProbeProfile,
        arguments: tuple[str, ...],
        *,
        timeout_seconds: float,
        output_limit: int,
        terminate_grace_seconds: float,
    ) -> WAWIsolatedProbeCompletion:
        del profile, arguments, timeout_seconds, output_limit, terminate_grace_seconds
        return WAWIsolatedProbeCompletion(
            self.exit_code,
            self.stdout,
            self.stderr,
            WAWVendorProbeFailure.NONE,
            self.cleanup_proof(
                leader_reaped=True,
                descendants_remaining=self.descendants_remaining,
            ),
        )


class _EscapingTestPort(WAWProcessIsolationPort):
    """Test-only port tracking a leader and its setsid child outside the PGID."""

    def __init__(self) -> None:
        super().__init__(
            isolation_kind=WAWProcessIsolationKind.SYNTHETIC_SUBPROCESS,
            production_qualified=False,
        )
        self.started = asyncio.Event()
        self.cleanup_started = asyncio.Event()
        self.release_cleanup = asyncio.Event()
        self.leader: asyncio.subprocess.Process | None = None
        self.escaped_pid: int | None = None
        self.signals: list[str] = []

    async def execute(
        self,
        profile: WAWVendorProbeProfile,
        arguments: tuple[str, ...],
        *,
        timeout_seconds: float,
        output_limit: int,
        terminate_grace_seconds: float,
    ) -> WAWIsolatedProbeCompletion:
        del profile, arguments, timeout_seconds, output_limit, terminate_grace_seconds
        child_code = (
            "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "print('ready', flush=True); time.sleep(30)"
        )
        leader_code = (
            "import signal,subprocess,sys; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            f"child=subprocess.Popen([sys.executable,'-c',{child_code!r}],"
            "stdout=subprocess.PIPE,start_new_session=True); "
            "assert child.stdout.readline() == b'ready\\n'; "
            "print(child.pid,flush=True); child.wait()"
        )
        self.leader = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            leader_code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        assert self.leader.stdout is not None
        self.escaped_pid = int(await self.leader.stdout.readline())
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cleanup = asyncio.create_task(self._cleanup())
            await subject._await_cleanup_uninterruptibly(cleanup)
            raise AssertionError("unreachable after cancellation") from None
        raise AssertionError("unreachable")

    async def _cleanup(self) -> subject.WAWProcessCleanupProof:
        assert self.leader is not None
        assert self.escaped_pid is not None
        self.cleanup_started.set()
        os.killpg(self.leader.pid, signal.SIGTERM)
        os.killpg(self.escaped_pid, signal.SIGTERM)
        self.signals.append("TERM")
        await self.release_cleanup.wait()
        try:
            await asyncio.wait_for(self.leader.wait(), timeout=0.02)
        except TimeoutError:
            os.killpg(self.escaped_pid, signal.SIGKILL)
            self.signals.append("KILL")
            try:
                await asyncio.wait_for(self.leader.wait(), timeout=1)
            except TimeoutError:
                self.leader.kill()
                await self.leader.wait()
        return self.cleanup_proof(leader_reaped=True, descendants_remaining=0)


def _script(tmp_path: Path) -> Path:
    path = tmp_path / "synthetic-public-probe"
    path.write_text(
        """#!/bin/sh
case "$MODE" in
  auth) printf 'Authenticated\\n'; exit 0 ;;
  unauth) printf 'Not logged in\\n'; exit 1 ;;
  unknown) printf 'unexpected failure\\n' >&2; exit 1 ;;
  nonzero) exit 17 ;;
  nonutf8) printf '\\377'; exit 0 ;;
  exact-limit) dd if=/dev/zero bs=4096 count=1 2>/dev/null; exit 0 ;;
  over-limit) dd if=/dev/zero bs=4097 count=1 2>/dev/null; exit 0 ;;
  signal) kill -TERM $$ ;;
  timeout) trap '' TERM; sleep 30 ;;
  descendant) (sleep 30) >/dev/null 2>&1 & exit 0 ;;
esac
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _profiles(
    tmp_path: Path, *, mode: str, synthetic_test_only: bool = False
) -> dict[AgentType, WAWVendorProbeProfile]:
    executable = _script(tmp_path)
    environment = (("HOME", str(tmp_path)), ("MODE", mode), ("PATH", "/usr/bin:/bin"))
    return {
        AgentType.CLAUDE: WAWVendorProbeProfile(
            str(INTERACTIVE_PROFILE_CONSTANTS_V1["claude"]["profile_id"]),
            AgentType.CLAUDE,
            "1.2.3",
            WAWVendorProbeId.CLAUDE_AUTH_STATUS_V1,
            WAWVendorProbeParserId.CLAUDE_EXIT_STATUS_V1,
            executable,
            tmp_path,
            environment,
            synthetic_test_only=synthetic_test_only,
        ),
        AgentType.CODEX: WAWVendorProbeProfile(
            str(INTERACTIVE_PROFILE_CONSTANTS_V1["codex"]["profile_id"]),
            AgentType.CODEX,
            "0.146.1",
            WAWVendorProbeId.CODEX_LOGIN_STATUS_V1,
            WAWVendorProbeParserId.CODEX_EXACT_STATUS_V1,
            executable,
            tmp_path,
            environment,
            waw_vendor_probe_output_digest(CODEX_UNAUTH, b""),
            synthetic_test_only,
        ),
    }


def _synthetic_runner(tmp_path: Path, *, mode: str, **kwargs: Any) -> WAWVendorProbeRunner:
    return WAWVendorProbeRunner(
        _profiles(tmp_path, mode=mode, synthetic_test_only=True),
        subject._synthetic_subprocess_port_for_tests(),
        **kwargs,
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("agent_type", "version", "mode", "expected"),
    [
        (AgentType.CLAUDE, "1.2.3", "auth", WAWVendorProbeResult.AUTHENTICATED),
        (AgentType.CLAUDE, "1.2.3", "unauth", WAWVendorProbeResult.UNAUTHENTICATED),
        (AgentType.CLAUDE, "1.2.3", "nonzero", WAWVendorProbeResult.UNKNOWN),
        (AgentType.CODEX, "0.146.1", "auth", WAWVendorProbeResult.AUTHENTICATED),
        (AgentType.CODEX, "0.146.1", "unauth", WAWVendorProbeResult.UNAUTHENTICATED),
        (AgentType.CODEX, "0.146.1", "unknown", WAWVendorProbeResult.UNKNOWN),
        (AgentType.CODEX, "0.146.1", "nonzero", WAWVendorProbeResult.UNKNOWN),
    ],
)
async def test_exact_version_bound_parser_matrix(
    tmp_path: Path,
    agent_type: AgentType,
    version: str,
    mode: str,
    expected: WAWVendorProbeResult,
) -> None:
    values = {
        "auth": (0, b"Authenticated\n", b""),
        "unauth": (1, CODEX_UNAUTH, b""),
        "unknown": (1, b"", b"unexpected failure\n"),
        "nonzero": (17, b"", b""),
    }
    exit_code, stdout, stderr = values[mode]
    evidence = await WAWVendorProbeRunner(
        _profiles(tmp_path, mode=mode),
        _QualifiedPort(exit_code=exit_code, stdout=stdout, stderr=stderr),
    ).probe(agent_type=agent_type, observed_vendor_version=version)
    assert evidence.result is expected
    assert evidence.failure is WAWVendorProbeFailure.NONE
    assert not ({"stdout", "stderr", "output", "text"} & dataclasses.asdict(evidence).keys())


@pytest.mark.anyio
async def test_only_version_mismatch_is_unsupported_and_does_not_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def forbidden_spawn(*_args: object, **_kwargs: object) -> Any:
        nonlocal calls
        calls += 1
        raise AssertionError("version mismatch must not spawn")

    monkeypatch.setattr(subject, "_create_subprocess_exec", forbidden_spawn)
    evidence = await _synthetic_runner(tmp_path, mode="auth").probe(
        agent_type=AgentType.CODEX, observed_vendor_version="0.146.2"
    )
    assert evidence.result is WAWVendorProbeResult.UNSUPPORTED
    assert evidence.failure is WAWVendorProbeFailure.VERSION_MISMATCH
    assert evidence.exit_code is None
    assert calls == 0


@pytest.mark.anyio
async def test_spawn_error_is_unknown_not_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unavailable(*_args: object, **_kwargs: object) -> Any:
        raise OSError("synthetic private detail")

    monkeypatch.setattr(subject, "_create_subprocess_exec", unavailable)
    evidence = await _synthetic_runner(tmp_path, mode="auth").probe(
        agent_type=AgentType.CLAUDE, observed_vendor_version="1.2.3"
    )
    assert evidence.result is WAWVendorProbeResult.UNKNOWN
    assert evidence.failure is WAWVendorProbeFailure.SPAWN_ERROR
    assert "synthetic private detail" not in repr(evidence)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("mode", "failure"),
    [
        ("over-limit", WAWVendorProbeFailure.OUTPUT_LIMIT),
        ("nonutf8", WAWVendorProbeFailure.NON_UTF8),
        ("signal", WAWVendorProbeFailure.SIGNALLED),
    ],
)
async def test_output_signal_and_encoding_fail_closed(
    tmp_path: Path, mode: str, failure: WAWVendorProbeFailure
) -> None:
    evidence = await _synthetic_runner(tmp_path, mode=mode).probe(
        agent_type=AgentType.CLAUDE, observed_vendor_version="1.2.3"
    )
    assert evidence.result is WAWVendorProbeResult.UNKNOWN
    assert evidence.failure is failure


@pytest.mark.anyio
async def test_exact_combined_output_limit_is_accepted(tmp_path: Path) -> None:
    evidence = await _synthetic_runner(tmp_path, mode="exact-limit").probe(
        agent_type=AgentType.CLAUDE, observed_vendor_version="1.2.3"
    )
    assert WAW_VENDOR_PROBE_OUTPUT_LIMIT == 4096
    assert evidence.result is WAWVendorProbeResult.UNKNOWN
    assert evidence.failure is WAWVendorProbeFailure.UNQUALIFIED_ISOLATION


@pytest.mark.anyio
async def test_synthetic_profile_stays_unknown_even_with_qualified_port(tmp_path: Path) -> None:
    evidence = await WAWVendorProbeRunner(
        _profiles(tmp_path, mode="auth", synthetic_test_only=True),
        _QualifiedPort(exit_code=0, stdout=b"Authenticated\n"),
    ).probe(agent_type=AgentType.CLAUDE, observed_vendor_version="1.2.3")
    assert evidence.result is WAWVendorProbeResult.UNKNOWN
    assert evidence.failure is WAWVendorProbeFailure.UNQUALIFIED_ISOLATION


@pytest.mark.anyio
async def test_qualified_port_requires_complete_port_issued_cleanup_proof(tmp_path: Path) -> None:
    evidence = await WAWVendorProbeRunner(
        _profiles(tmp_path, mode="auth"),
        _QualifiedPort(exit_code=0, stdout=b"Authenticated\n", descendants_remaining=1),
    ).probe(agent_type=AgentType.CLAUDE, observed_vendor_version="1.2.3")
    assert evidence.result is WAWVendorProbeResult.UNKNOWN
    assert evidence.failure is WAWVendorProbeFailure.CLEANUP_UNPROVEN


@pytest.mark.anyio
async def test_setsid_escape_term_ignore_and_double_cancel_finish_one_cleanup(
    tmp_path: Path,
) -> None:
    port = _EscapingTestPort()
    runner = WAWVendorProbeRunner(_profiles(tmp_path, mode="auth"), port)
    task = asyncio.create_task(
        runner.probe(agent_type=AgentType.CLAUDE, observed_vendor_version="1.2.3")
    )
    await asyncio.wait_for(port.started.wait(), timeout=2)
    task.cancel()
    await asyncio.wait_for(port.cleanup_started.wait(), timeout=2)
    task.cancel()
    port.release_cleanup.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert port.signals == ["TERM", "KILL"]
    assert port.leader is not None and port.leader.returncode is not None
    assert port.escaped_pid is not None
    with pytest.raises(ProcessLookupError):
        os.kill(port.escaped_pid, 0)


@pytest.mark.anyio
async def test_timeout_terminates_process_group_and_reaps_leader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    signals: list[int] = []
    real_killpg = os.killpg

    def recorded_killpg(process_group: int, sent_signal: int) -> None:
        signals.append(sent_signal)
        real_killpg(process_group, sent_signal)

    monkeypatch.setattr(subject, "_killpg", recorded_killpg)
    runner = _synthetic_runner(
        tmp_path,
        mode="timeout",
        timeout_seconds=0.05,
        terminate_grace_seconds=0.02,
    )
    evidence = await runner.probe(agent_type=AgentType.CLAUDE, observed_vendor_version="1.2.3")
    assert evidence.result is WAWVendorProbeResult.UNKNOWN
    assert evidence.failure is WAWVendorProbeFailure.TIMEOUT
    assert signal.SIGTERM in signals
    assert 0 in signals  # The process-group existence check ran after TERM.


@pytest.mark.anyio
async def test_successful_leader_with_live_descendant_is_failed_and_group_is_killed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    signals: list[int] = []
    real_killpg = os.killpg

    def recorded_killpg(process_group: int, sent_signal: int) -> None:
        signals.append(sent_signal)
        real_killpg(process_group, sent_signal)

    monkeypatch.setattr(subject, "_killpg", recorded_killpg)
    evidence = await _synthetic_runner(
        tmp_path, mode="descendant", terminate_grace_seconds=0.02
    ).probe(agent_type=AgentType.CLAUDE, observed_vendor_version="1.2.3")
    assert evidence.result is WAWVendorProbeResult.UNKNOWN
    assert evidence.failure is WAWVendorProbeFailure.PROCESS_GROUP
    assert signal.SIGTERM in signals


@pytest.mark.anyio
async def test_live_group_classification_is_stable_under_parallel_repetition(
    tmp_path: Path,
) -> None:
    for _ in range(3):
        evidence = await asyncio.gather(
            *(
                _synthetic_runner(tmp_path, mode="descendant", terminate_grace_seconds=0.02).probe(
                    agent_type=AgentType.CLAUDE,
                    observed_vendor_version="1.2.3",
                )
                for _ in range(6)
            )
        )
        assert {item.result for item in evidence} == {WAWVendorProbeResult.UNKNOWN}
        assert {item.failure for item in evidence} == {WAWVendorProbeFailure.PROCESS_GROUP}


@pytest.mark.anyio
async def test_private_subprocess_harness_rejects_production_profile_and_arbitrary_argv(
    tmp_path: Path,
) -> None:
    port = subject._synthetic_subprocess_port_for_tests()
    production = _profiles(tmp_path, mode="auth")[AgentType.CLAUDE]
    synthetic = _profiles(tmp_path, mode="auth", synthetic_test_only=True)[AgentType.CLAUDE]
    with pytest.raises(WAWVendorProbeError, match="test-only"):
        await port.execute(
            production,
            ("auth", "status"),
            timeout_seconds=0.1,
            output_limit=WAW_VENDOR_PROBE_OUTPUT_LIMIT,
            terminate_grace_seconds=0.02,
        )
    with pytest.raises(WAWVendorProbeError, match="test-only"):
        await port.execute(
            synthetic,
            ("arbitrary",),
            timeout_seconds=0.1,
            output_limit=WAW_VENDOR_PROBE_OUTPUT_LIMIT,
            terminate_grace_seconds=0.02,
        )


def test_profiles_reject_cross_agent_parser_and_unbounded_configuration(tmp_path: Path) -> None:
    executable = _script(tmp_path)
    with pytest.raises(WAWVendorProbeError):
        WAWVendorProbeProfile(
            str(INTERACTIVE_PROFILE_CONSTANTS_V1["claude"]["profile_id"]),
            AgentType.CLAUDE,
            "1.2.3",
            WAWVendorProbeId.CODEX_LOGIN_STATUS_V1,
            WAWVendorProbeParserId.CODEX_EXACT_STATUS_V1,
            executable,
            tmp_path,
            (),
        )
    with pytest.raises(WAWVendorProbeError):
        _synthetic_runner(tmp_path, mode="auth", timeout_seconds=31)
