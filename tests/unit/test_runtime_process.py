from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import sys
from pathlib import Path

import pytest
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.process import (
    ControlledProcessRunner,
    ExecutableIdentity,
    inspect_executable,
    minimal_runtime_environment,
)


def _trusted_test_python(tmp_path: Path) -> ExecutableIdentity:
    """Give runner tests an executable with production-safe ownership modes."""
    tmp_path.chmod(0o700)
    executable = tmp_path / "python"
    shutil.copy2(Path(sys.executable).resolve(strict=True), executable)
    executable.chmod(0o755)
    return inspect_executable(executable)


@pytest.mark.anyio
async def test_runner_uses_argv_fixed_cwd_and_environment_allowlist(tmp_path: Path) -> None:
    runner = ControlledProcessRunner()
    identity = _trusted_test_python(tmp_path)
    environment = {
        "HOME": str(tmp_path),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "AGENTBOX_SECRET_KEY": "must-not-pass",
        "GITHUB_TOKEN": "must-not-pass",
        "OPENAI_API_KEY": "must-not-pass",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_ASKPASS": "/bin/false",
        "SSH_ASKPASS": "/bin/false",
    }
    script = (
        "import json,os,sys;"
        "print(json.dumps({'cwd':os.getcwd(),'argv':sys.argv[1:],"
        "'secret':os.getenv('AGENTBOX_SECRET_KEY'),'github':os.getenv('GITHUB_TOKEN'),"
        "'openai':os.getenv('OPENAI_API_KEY'),"
        "'git_config':os.getenv('GIT_CONFIG_GLOBAL'),"
        "'git_askpass':os.getenv('GIT_ASKPASS'),"
        "'ssh_askpass':os.getenv('SSH_ASKPASS')}))"
    )
    result = await runner.run(
        identity,
        ("-c", script, "literal;$(not-a-shell)"),
        environment=environment,
        cwd=tmp_path,
        timeout_seconds=5,
        stdout_limit=4096,
        stderr_limit=4096,
    )

    assert result.exit_code == 0
    assert b'"argv": ["literal;$(not-a-shell)"]' in result.stdout
    assert f'"cwd": "{tmp_path}"'.encode() in result.stdout
    assert b'"secret": null' in result.stdout
    assert b'"github": null' in result.stdout
    assert b'"openai": null' in result.stdout
    assert b'"git_config": "/dev/null"' in result.stdout
    assert b'"git_askpass": "/bin/false"' in result.stdout
    assert b'"ssh_askpass": "/bin/false"' in result.stdout
    assert result.argv[0] == str(identity.path)


@pytest.mark.anyio
async def test_runner_enforces_output_caps(tmp_path: Path) -> None:
    runner = ControlledProcessRunner()
    identity = _trusted_test_python(tmp_path)
    with pytest.raises(RuntimeOperationError, match="output limit") as raised:
        await runner.run(
            identity,
            ("-c", "print('x' * 5000)"),
            environment={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
            cwd=tmp_path,
            timeout_seconds=5,
            stdout_limit=128,
            stderr_limit=128,
        )
    assert raised.value.code == "CODEX_OUTPUT_LIMIT_EXCEEDED"


@pytest.mark.anyio
async def test_runner_times_out_and_cleans_up_spawned_process(tmp_path: Path) -> None:
    runner = ControlledProcessRunner(terminate_grace_seconds=0.1)
    identity = _trusted_test_python(tmp_path)
    pid_file = tmp_path / "spawned.pid"
    with pytest.raises(RuntimeOperationError) as raised:
        await runner.run(
            identity,
            (
                "-c",
                "import os,pathlib,time;"
                f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()));"
                "time.sleep(30)",
            ),
            environment={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
            cwd=tmp_path,
            timeout_seconds=0.05,
            stdout_limit=128,
            stderr_limit=128,
        )
    assert raised.value.code == "CODEX_COMMAND_TIMEOUT"
    spawned_pid = int(pid_file.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(spawned_pid, 0)


@pytest.mark.anyio
async def test_runner_external_cancellation_cleans_only_its_spawned_process_group(
    tmp_path: Path,
) -> None:
    runner = ControlledProcessRunner(terminate_grace_seconds=0.1)
    identity = _trusted_test_python(tmp_path)
    pid_file = tmp_path / "cancelled.pid"
    sentinel = await asyncio.create_subprocess_exec(
        str(identity.path),
        "-c",
        "import time; time.sleep(30)",
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    task = asyncio.create_task(
        runner.run(
            identity,
            (
                "-c",
                "import os,pathlib,time;"
                f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()));"
                "time.sleep(30)",
            ),
            environment={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
            cwd=tmp_path,
            timeout_seconds=25,
            stdout_limit=128,
            stderr_limit=128,
        )
    )
    try:
        for _ in range(200):
            if pid_file.exists():
                break
            await asyncio.sleep(0.01)
        assert pid_file.exists(), "spawned process did not publish its PID"
        spawned_pid = int(pid_file.read_text(encoding="utf-8"))
        assert spawned_pid not in {os.getpid(), sentinel.pid}

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        with pytest.raises(ProcessLookupError):
            os.kill(spawned_pid, 0)
        assert sentinel.returncode is None
        os.kill(sentinel.pid, 0)
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if sentinel.returncode is None:
            sentinel.terminate()
        await sentinel.wait()


def test_executable_resolution_rejects_broken_and_writable_files(tmp_path: Path) -> None:
    broken = tmp_path / "broken"
    broken.symlink_to(tmp_path / "missing")
    with pytest.raises(RuntimeOperationError):
        inspect_executable(broken.absolute())

    unsafe = tmp_path / "unsafe"
    unsafe.write_text("not executed", encoding="utf-8")
    unsafe.chmod(0o777)
    with pytest.raises(RuntimeOperationError, match="permissions"):
        inspect_executable(unsafe.absolute())

    unsafe_directory = tmp_path / "unsafe-directory"
    unsafe_directory.mkdir(mode=0o777)
    unsafe_directory.chmod(0o777)
    executable = unsafe_directory / "codex"
    executable.write_text("#!/bin/false\n", encoding="utf-8")
    executable.chmod(0o755)
    with pytest.raises(RuntimeOperationError, match="directory permissions"):
        inspect_executable(executable.absolute())


@pytest.mark.anyio
async def test_runner_rejects_executable_replacement_before_spawn(tmp_path: Path) -> None:
    executable = tmp_path / "codex"
    executable.write_text("#!/bin/false\n", encoding="utf-8")
    executable.chmod(0o755)
    identity = inspect_executable(executable.absolute())
    executable.write_text("#!/bin/true\n", encoding="utf-8")
    executable.chmod(0o755)

    with pytest.raises(RuntimeOperationError) as raised:
        await ControlledProcessRunner().run(
            identity,
            ("--version",),
            environment={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
            cwd=tmp_path,
            timeout_seconds=1,
            stdout_limit=128,
            stderr_limit=128,
        )
    assert raised.value.code == "CODEX_EXECUTABLE_CHANGED"


def test_minimal_environment_is_an_explicit_allowlist() -> None:
    result = minimal_runtime_environment(
        {
            "HOME": "/runtime-home",
            "PATH": "/usr/bin:/bin",
            "TERM": "xterm",
            "AWS_SECRET_ACCESS_KEY": "no",
            "ANTHROPIC_API_KEY": "no",
            "GIT_CONFIG_GLOBAL": "/hostile/global",
            "GIT_ASKPASS": "/safe/askpass",
            "SSH_ASKPASS": "/safe/ssh-askpass",
        }
    )
    assert result == {
        "HOME": "/runtime-home",
        "PATH": "/usr/bin:/bin",
        "TERM": "xterm",
        "GIT_CONFIG_GLOBAL": "/hostile/global",
        "GIT_ASKPASS": "/safe/askpass",
        "SSH_ASKPASS": "/safe/ssh-askpass",
        "LANG": "C.UTF-8",
    }

    sanitized_path = minimal_runtime_environment(
        {"HOME": "/runtime-home", "PATH": ".:/safe/bin::relative:/usr/bin"}
    )
    assert sanitized_path["PATH"] == "/safe/bin:/usr/bin"


@pytest.mark.anyio
async def test_sensitive_runner_does_not_log_output(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    canary = "PAIR-SECRET-CANARY-RUNNER"
    runner = ControlledProcessRunner()
    identity = _trusted_test_python(tmp_path)
    with caplog.at_level(logging.DEBUG):
        result = await runner.run(
            identity,
            ("-c", f"print('{canary}')"),
            environment={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
            cwd=tmp_path,
            timeout_seconds=5,
            stdout_limit=128,
            stderr_limit=128,
            sensitive_output=True,
        )
    assert canary.encode() in result.stdout
    assert canary not in caplog.text


@pytest.mark.anyio
async def test_event_loop_remains_schedulable_during_runtime_process(tmp_path: Path) -> None:
    runner = ControlledProcessRunner()
    identity = _trusted_test_python(tmp_path)
    task = asyncio.create_task(
        runner.run(
            identity,
            ("-c", "import time; time.sleep(.1)"),
            environment={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
            cwd=tmp_path,
            timeout_seconds=2,
            stdout_limit=128,
            stderr_limit=128,
        )
    )
    await asyncio.sleep(0)
    assert task.done() is False
    scheduled = await asyncio.wait_for(asyncio.sleep(0, result="scheduled"), timeout=0.1)
    assert scheduled == "scheduled"
    await task
