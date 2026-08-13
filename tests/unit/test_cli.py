from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from agentbox_cli.main import create_parser, main
from agentbox_core import __version__
from agentbox_core.configuration import Settings
from agentbox_core.services import build_services
from agentbox_runtime import (
    AuthenticationState,
    CapabilityState,
    ClaudeCapabilities,
    ClaudeSession,
    ClaudeSessionActionResult,
    ClaudeSessionOutput,
    ClaudeSessionState,
    ClaudeStatus,
    CodexCapabilities,
    CodexStatus,
    GitBranch,
    GitHubProjectStatus,
    GitHubStatus,
    GitStatus,
    InstallationType,
    PairCodeResult,
    ProjectWorkspace,
    RemoteActionResult,
    RemoteState,
    RuntimeOperationError,
    WorkspaceState,
)
from conftest import migrate_database


@pytest.fixture
def cli_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> str:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'cli.db'}"
    monkeypatch.setenv("AGENTBOX_ENV", "test")
    monkeypatch.setenv("AGENTBOX_DATABASE_URL", database_url)
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_SECRET_KEY", "cli-test-secret-that-is-at-least-thirty-two-bytes")
    migrate_database(database_url)
    return database_url


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == __version__


def test_system_recover_is_an_explicit_root_lifecycle_command() -> None:
    args = create_parser().parse_args(["system", "recover"])

    assert args.command == "system"
    assert args.system_command == "recover"


def test_cli_status_json_reports_control_plane_only(
    cli_environment: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del cli_environment
    assert main(["status", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "status"
    assert payload["execution_mode"] == "local_read_only"
    assert payload["data"] == {
        "admin": "not_initialized",
        "configuration": "valid",
        "database": "reachable",
        "environment": "test",
        "migrations": "current",
    }


def test_admin_init_requires_tty(
    cli_environment: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del cli_environment
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    assert main(["admin", "init", "--username", "maintainer"]) == 13
    assert "ADMIN_INIT_TTY_REQUIRED" in capsys.readouterr().err


def test_admin_init_prompts_without_password_argv_and_refuses_second_admin(
    cli_environment: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del cli_environment
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    prompts: list[str] = []

    def fake_getpass(prompt: str) -> str:
        prompts.append(prompt)
        return "a sufficiently long passphrase"

    monkeypatch.setattr("agentbox_cli.main.getpass.getpass", fake_getpass)

    assert main(["admin", "init", "--username", "maintainer"]) == 0
    assert len(prompts) == 2
    assert "initialized" in capsys.readouterr().out

    assert main(["admin", "init", "--username", "other"]) == 14
    assert "ADMIN_ALREADY_INITIALIZED" in capsys.readouterr().err


def test_admin_password_and_sessions_are_tty_only_and_never_accept_password_argv(
    cli_environment: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings()
    services = build_services(settings)
    services.admin.initialize("maintainer", "a sufficiently long passphrase")
    services.auth.login(
        username="maintainer",
        password="a sufficiently long passphrase",
        source_identifier="127.0.0.1",
        request_id="req_cli_session",
    )
    services.database.close()
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    prompts = iter(
        (
            "a sufficiently long passphrase",
            "a different sufficiently long passphrase",
            "a different sufficiently long passphrase",
        )
    )
    monkeypatch.setattr("agentbox_cli.main.getpass.getpass", lambda _prompt: next(prompts))

    assert main(["admin", "password"]) == 0
    output = capsys.readouterr().out
    assert "password changed" in output
    assert "a sufficiently" not in output

    monkeypatch.setattr(
        "agentbox_cli.main.getpass.getpass",
        lambda _prompt: "a different sufficiently long passphrase",
    )
    assert main(["admin", "sessions", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["sessions"] == []

    parser = create_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["admin", "password", "--password", "forbidden"])


def test_admin_session_revocation_requires_tty(
    cli_environment: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del cli_environment
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    assert main(["admin", "revoke-sessions"]) == 13
    assert "ADMIN_REVOKE_SESSIONS_TTY_REQUIRED" in capsys.readouterr().err


def test_secret_generate_outputs_random_value_without_file_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["secret", "generate"]) == 0

    generated = capsys.readouterr().out.strip()
    assert len(generated) >= 64
    assert list(tmp_path.iterdir()) == []


class FakeRuntimeClient:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.calls: list[str] = []

    async def status(self, request_id: str) -> CodexStatus:
        assert request_id.startswith("req_cli-")
        return CodexStatus(
            installed=True,
            version="0.cli.fixture",
            selected_executable="/fixture/codex",
            installation_type=InstallationType.STANDALONE,
            authentication=AuthenticationState.UNKNOWN,
            capabilities=CodexCapabilities(
                remote_control=CapabilityState.SUPPORTED,
                start=CapabilityState.SUPPORTED,
                stop=CapabilityState.SUPPORTED,
                pair=CapabilityState.SUPPORTED,
            ),
            remote_state=RemoteState.UNKNOWN,
        )

    async def start_remote(self, request_id: str) -> RemoteActionResult:
        del request_id
        return RemoteActionResult("started", RemoteState.RUNNING)

    async def stop_remote(self, request_id: str) -> RemoteActionResult:
        del request_id
        return RemoteActionResult("stopped", RemoteState.STOPPED)

    async def generate_pair_code(self, request_id: str) -> PairCodeResult:
        del request_id
        return PairCodeResult("PAIR-SECRET-CANARY-CLI-6R2M")


class FakeClaudeRuntimeClient:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    @staticmethod
    def session_value(state: ClaudeSessionState = ClaudeSessionState.RUNNING) -> ClaudeSession:
        return ClaudeSession(
            project_id="project-a",
            display_name="Project A",
            state=state,
            managed=True,
            session_name="agentbox-claude-project-a-123456789abc",
            attach_command=("tmux attach-session -t =agentbox-claude-project-a-123456789abc"),
            workspace_state=WorkspaceState.UNKNOWN,
            tmux_running=state is not ClaudeSessionState.STOPPED,
            remote_readiness=("ready" if state is ClaudeSessionState.RUNNING else "unknown"),
        )

    async def status(self, request_id: str) -> ClaudeStatus:
        assert request_id.startswith("req_cli-")
        return ClaudeStatus(
            installed=True,
            version="1.cli.fixture",
            authentication=AuthenticationState.UNKNOWN,
            capabilities=ClaudeCapabilities(
                remote_control=CapabilityState.SUPPORTED,
                remote_start=CapabilityState.SUPPORTED,
                version=CapabilityState.SUPPORTED,
            ),
            tmux_installed=True,
            tmux_version="3.cli.fixture",
            managed_sessions=1,
            unmanaged_sessions=1,
            workspace_interaction_warnings=0,
        )

    async def list_sessions(self, request_id: str) -> tuple[ClaudeSession, ...]:
        del request_id
        return (self.session_value(),)

    async def session(self, request_id: str, project_id: str) -> ClaudeSession:
        del request_id
        assert project_id == "project-a"
        return self.session_value()

    async def start_session(self, request_id: str, project_id: str) -> ClaudeSessionActionResult:
        del request_id, project_id
        return ClaudeSessionActionResult("started", self.session_value())

    async def stop_session(self, request_id: str, project_id: str) -> ClaudeSessionActionResult:
        del request_id, project_id
        return ClaudeSessionActionResult("stopped", self.session_value(ClaudeSessionState.STOPPED))

    async def recent_output(self, request_id: str, project_id: str) -> ClaudeSessionOutput:
        del request_id, project_id
        session = self.session_value()
        return ClaudeSessionOutput(
            session.project_id,
            session.session_name,
            "CLAUDE-OUTPUT-CANARY",
            truncated=False,
        )


class FakeProjectRuntimeClient:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    async def list_workspaces(self, request_id: str) -> tuple[ProjectWorkspace, ...]:
        del request_id
        return (ProjectWorkspace("project-a", "Project A"),)

    async def git_status(self, request_id: str, project_key: str) -> GitStatus:
        del request_id
        assert project_key == "project-a"
        return GitStatus(
            True,
            branch="main",
            upstream="origin/main",
            remote_url="https://github.com/owner/repo.git",
        )

    async def branches(self, request_id: str, project_key: str) -> tuple[GitBranch, ...]:
        del request_id
        assert project_key == "project-a"
        return (GitBranch("main", True), GitBranch("feature/safe", False))

    async def github_status(self, request_id: str) -> GitHubStatus:
        del request_id
        return GitHubStatus(True, "2.fixture", AuthenticationState.AUTHENTICATED)

    async def github_project_status(self, request_id: str, project_key: str) -> GitHubProjectStatus:
        del request_id
        assert project_key == "project-a"
        return GitHubProjectStatus(
            True,
            repository="owner/repo",
            pull_request_number=7,
            pull_request_title="Draft",
            pull_request_state="open",
            pull_request_draft=True,
            pull_request_url="https://github.com/owner/repo/pull/7",
            pull_request_base="main",
            pull_request_head="feature/safe",
            mergeability="blocked",
            checks="pending",
        )


class FailingProjectRuntimeClient(FakeProjectRuntimeClient):
    async def git_status(self, request_id: str, project_key: str) -> GitStatus:
        del request_id, project_key
        raise RuntimeOperationError("RUNTIME_TIMEOUT", "Runtime timed out", category="timeout")

    async def branches(self, request_id: str, project_key: str) -> tuple[GitBranch, ...]:
        del request_id, project_key
        raise RuntimeOperationError(
            "RUNTIME_FORBIDDEN", "Runtime operation forbidden", category="forbidden"
        )

    async def github_status(self, request_id: str) -> GitHubStatus:
        del request_id
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE", "Runtime unavailable", category="unavailable"
        )

    async def github_project_status(self, request_id: str, project_key: str) -> GitHubProjectStatus:
        del request_id, project_key
        raise RuntimeOperationError(
            "RUNTIME_CONFLICT", "Runtime operation conflicted", category="conflict"
        )


def _formal_project_id() -> str:
    services = build_services(Settings())
    try:
        return services.projects.reconcile_existing(("project-a",))[0].id
    finally:
        services.database.close()


def test_codex_status_json_uses_typed_runtime_client(
    cli_environment: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del cli_environment
    monkeypatch.setattr("agentbox_cli.main.UnixCodexRuntimeClient", FakeRuntimeClient)

    assert main(["codex", "status", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "codex.status"
    assert payload["execution_mode"] == "runtime_socket"
    assert payload["data"]["version"] == "0.cli.fixture"
    assert "argv" not in payload["data"]


def test_codex_mutations_use_only_fixed_commands_and_pair_requires_tty(
    cli_environment: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del cli_environment
    monkeypatch.setattr("agentbox_cli.main.UnixCodexRuntimeClient", FakeRuntimeClient)
    assert main(["codex", "start"]) == 0
    assert "started" in capsys.readouterr().out
    assert main(["codex", "stop"]) == 0
    assert "stopped" in capsys.readouterr().out

    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    assert main(["codex", "pair"]) == 13
    assert "CODEX_PAIR_TTY_REQUIRED" in capsys.readouterr().err


def test_codex_pair_is_single_display_and_json_is_forbidden(
    cli_environment: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del cli_environment
    monkeypatch.setattr("agentbox_cli.main.UnixCodexRuntimeClient", FakeRuntimeClient)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    assert main(["codex", "pair"]) == 0
    output = capsys.readouterr().out
    assert output.count("PAIR-SECRET-CANARY-CLI-6R2M") == 1
    assert "Sensitive temporary code" in output

    assert main(["--json", "codex", "pair"]) == 13
    assert "CODEX_PAIR_JSON_FORBIDDEN" in capsys.readouterr().err


def test_claude_status_and_list_support_json_without_paths(
    cli_environment: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del cli_environment
    formal_id = _formal_project_id()
    monkeypatch.setattr("agentbox_cli.main.UnixClaudeRuntimeClient", FakeClaudeRuntimeClient)
    assert main(["claude", "status", "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["data"]["version"] == "1.cli.fixture"
    assert status["data"]["authentication"] == "unknown"

    assert main(["claude", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["data"]["sessions"][0]["project_id"] == formal_id
    assert listed["data"]["sessions"][0]["display_name"] == "project-a"
    assert "path" not in listed["data"]["sessions"][0]


def test_claude_start_stop_and_sensitive_output_use_typed_project_id(
    cli_environment: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del cli_environment
    formal_id = _formal_project_id()
    monkeypatch.setattr("agentbox_cli.main.UnixClaudeRuntimeClient", FakeClaudeRuntimeClient)
    assert main(["claude", "start", formal_id]) == 0
    assert "started" in capsys.readouterr().out
    assert main(["claude", "stop", formal_id]) == 0
    assert "stopped" in capsys.readouterr().out
    assert main(["claude", "output", formal_id]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "CLAUDE-OUTPUT-CANARY"
    assert "Sensitive Claude session output" in captured.err


def test_claude_attach_requires_tty_and_execs_only_exact_generated_name(
    cli_environment: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del cli_environment
    formal_id = _formal_project_id()
    monkeypatch.setattr("agentbox_cli.main.UnixClaudeRuntimeClient", FakeClaudeRuntimeClient)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert main(["claude", "attach", formal_id]) == 13
    assert "CLAUDE_ATTACH_TTY_REQUIRED" in capsys.readouterr().err

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr("agentbox_cli.main.shutil.which", lambda _name: "/usr/bin/tmux")
    executed: list[tuple[str, list[str]]] = []

    def capture_exec(path: str, argv: list[str]) -> None:
        executed.append((path, argv))
        raise RuntimeError("exec intercepted")

    monkeypatch.setattr("agentbox_cli.main.os.execv", capture_exec)
    with pytest.raises(RuntimeError, match="exec intercepted"):
        main(["claude", "attach", formal_id])
    assert executed == [
        (
            "/usr/bin/tmux",
            [
                "/usr/bin/tmux",
                "attach-session",
                "-t",
                "=agentbox-claude-project-a-123456789abc",
            ],
        )
    ]


def test_project_cli_reconciles_formal_ids_and_supports_read_only_json(
    cli_environment: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del cli_environment
    monkeypatch.setattr("agentbox_cli.main.UnixProjectRuntimeClient", FakeProjectRuntimeClient)

    assert main(["project", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    formal_id = listed["data"]["projects"][0]["id"]
    assert formal_id.startswith("prj_")
    assert listed["data"]["projects"][0]["slug"] == "project-a"

    assert main(["project", "status", formal_id, "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["data"]["branch"] == "main"
    assert "argv" not in status["data"]

    assert main(["project", "branch", "list", formal_id, "--json"]) == 0
    branches = json.loads(capsys.readouterr().out)
    assert branches["data"]["branches"] == [
        {"current": True, "name": "main"},
        {"current": False, "name": "feature/safe"},
    ]


def test_project_and_github_cli_queue_only_typed_operations(
    cli_environment: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del cli_environment
    formal_id = _formal_project_id()
    monkeypatch.setattr("agentbox_cli.main.UnixProjectRuntimeClient", FakeProjectRuntimeClient)

    assert main(["project", "pull", formal_id]) == 0
    assert "queued" in capsys.readouterr().out
    assert main(["github", "status", "--json"]) == 0
    github = json.loads(capsys.readouterr().out)
    assert github["data"]["authentication"] == "authenticated"
    assert main(["github", "pr", "status", formal_id, "--json"]) == 0
    pull_request = json.loads(capsys.readouterr().out)
    assert pull_request["data"]["pull_request_number"] == 7

    assert (
        main(
            [
                "github",
                "pr",
                "create",
                formal_id,
                "--title",
                "bad\ntitle",
            ]
        )
        == 15
    )
    assert "GITHUB_PR_INPUT_INVALID" in capsys.readouterr().err

    services = build_services(Settings())
    try:
        jobs = services.jobs.list()
        assert [job.type for job in jobs] == ["git.pull"]
        assert all("argv" not in job.payload_json for job in jobs)
    finally:
        services.database.close()


@pytest.mark.parametrize(
    ("arguments", "expected_exit", "expected_code"),
    [
        (["project", "status", "{project}"], 16, "RUNTIME_TIMEOUT"),
        (["project", "branch", "list", "{project}"], 13, "RUNTIME_FORBIDDEN"),
        (["github", "status"], 10, "RUNTIME_UNAVAILABLE"),
        (["github", "pr", "status", "{project}"], 14, "RUNTIME_CONFLICT"),
    ],
)
def test_project_and_github_cli_map_runtime_failure_exit_codes(
    cli_environment: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
    expected_exit: int,
    expected_code: str,
) -> None:
    del cli_environment
    formal_id = _formal_project_id()
    monkeypatch.setattr("agentbox_cli.main.UnixProjectRuntimeClient", FailingProjectRuntimeClient)

    resolved_arguments = [
        formal_id if argument == "{project}" else argument for argument in arguments
    ]
    assert main(resolved_arguments) == expected_exit
    assert expected_code in capsys.readouterr().err
