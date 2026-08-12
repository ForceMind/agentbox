from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from agentbox_runtime.git import GitAdapter, validate_git_repository_url
from agentbox_runtime.github import (
    MAX_PR_BODY_BYTES,
    GitHubAdapter,
    github_repository_from_remote,
    validate_pr_body,
    validate_pr_title,
)
from agentbox_runtime.models import (
    AuthenticationState,
    GitStatus,
    RuntimeOperationError,
)
from agentbox_runtime.process import (
    ControlledProcessRunner,
    ExecutableIdentity,
    ProcessResult,
    inspect_executable,
)

IDENTITY = ExecutableIdentity(Path("/usr/bin/git"), 1, 2, 0o755, 1, 1)


class RecordingRunner:
    def __init__(self, results: Sequence[tuple[int, bytes, bytes]]) -> None:
        self.results = list(results)
        self.calls: list[dict[str, object]] = []

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
        self.calls.append(
            {
                "arguments": tuple(arguments),
                "environment": dict(environment),
                "cwd": cwd,
                "timeout": timeout_seconds,
                "stdout_limit": stdout_limit,
                "stderr_limit": stderr_limit,
                "sensitive": sensitive_output,
                "stdin": stdin_data,
                "error_prefix": error_prefix,
            }
        )
        if not self.results:
            raise AssertionError("unexpected process invocation")
        exit_code, stdout, stderr = self.results.pop(0)
        return ProcessResult((str(executable.path), *arguments), exit_code, stdout, stderr)


class FakeGit:
    def __init__(self, status: GitStatus) -> None:
        self.value = status
        self.calls: list[Path] = []

    async def status(self, project: Path) -> GitStatus:
        self.calls.append(project)
        return self.value


def repository(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    return project


@pytest.mark.parametrize(
    "value",
    ("https://[", "https://github.com:99999/owner/repo.git"),
)
def test_runtime_repository_url_rejects_malformed_authority(value: str) -> None:
    with pytest.raises(RuntimeOperationError) as raised:
        validate_git_repository_url(value)
    assert raised.value.code == "GIT_REPOSITORY_URL_INVALID"


def git_adapter(
    monkeypatch: pytest.MonkeyPatch,
    runner: RecordingRunner,
) -> GitAdapter:
    adapter = GitAdapter(
        environment={
            "HOME": "/runtime-home",
            "PATH": "/usr/bin:/bin",
            "GIT_CONFIG_GLOBAL": "/hostile/config",
            "GIT_ASKPASS": "/hostile/askpass",
            "SSH_ASKPASS": "/hostile/ssh-askpass",
            "GIT_ALLOW_PROTOCOL": "file:ext:https",
        },
        runner=runner,  # type: ignore[arg-type]
    )
    monkeypatch.setattr(adapter, "executable", lambda: IDENTITY)
    return adapter


@pytest.mark.anyio
async def test_clone_uses_fixed_protocol_submodule_and_lfs_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = RecordingRunner([(0, b"cloned", b"")])
    adapter = git_adapter(monkeypatch, runner)
    destination = tmp_path / "workspace"

    await adapter.clone("https://github.com/owner/repo.git", cwd=tmp_path, destination=destination)

    call = runner.calls[0]
    arguments = call["arguments"]
    environment = call["environment"]
    assert isinstance(arguments, tuple)
    assert isinstance(environment, dict)
    assert arguments[-6:] == (
        "clone",
        "--no-recurse-submodules",
        "--no-hardlinks",
        "--",
        "https://github.com/owner/repo.git",
        str(destination),
    )
    assert "--recurse-submodules" not in arguments
    assert environment["GIT_ALLOW_PROTOCOL"] == "https:ssh"
    assert environment["GIT_LFS_SKIP_SMUDGE"] == "1"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "repository_url",
    [
        "file:///etc",
        "ext::sh -c id",
        "fd::7/repository",
        "../local-repository",
        "https://user:secret@github.com/owner/repo.git",
        "https://github.com/owner/repo.git\n--upload-pack=evil",
    ],
)
async def test_clone_rejects_unsafe_url_before_process_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, repository_url: str
) -> None:
    runner = RecordingRunner([])
    with pytest.raises(RuntimeOperationError) as raised:
        await git_adapter(monkeypatch, runner).clone(
            repository_url, cwd=tmp_path, destination=tmp_path / "workspace"
        )
    assert raised.value.code == "GIT_REPOSITORY_URL_INVALID"
    assert runner.calls == []


@pytest.mark.anyio
async def test_git_status_parses_porcelain_v2_and_redacts_remote_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = (
        b"# branch.oid 0123456789\0# branch.head feature/safe\0"
        b"# branch.upstream origin/feature/safe\0# branch.ab +2 -3\0"
        b"1 M. N... 100644 100644 100644 a b file\0"
        b"1 .M N... 100644 100644 100644 a b file2\0"
        b"? new-file\0u UU N... 100644 100644 100644 100644 a b c conflict\0"
    )
    runner = RecordingRunner(
        [
            (0, b"", b""),
            (0, raw, b""),
            (0, b"https://user:token@github.com/owner/repo.git?token=bad\n", b""),
        ]
    )
    adapter = git_adapter(monkeypatch, runner)

    status = await adapter.status(repository(tmp_path))

    assert status.branch == "feature/safe"
    assert status.upstream == "origin/feature/safe"
    assert (status.ahead, status.behind) == (2, 3)
    assert (status.staged_count, status.unstaged_count) == (1, 1)
    assert (status.untracked_count, status.conflicted_count) == (1, 1)
    assert status.clean is False
    assert status.remote_url == "https://github.com/owner/repo.git"
    environment = runner.calls[0]["environment"]
    assert isinstance(environment, dict)
    assert environment["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert environment["GIT_ASKPASS"] == "/bin/false"
    assert environment["SSH_ASKPASS"] == "/bin/false"
    assert environment["GIT_ALLOW_PROTOCOL"] == "https:ssh"
    assert environment["GIT_TERMINAL_PROMPT"] == "0"
    assert environment["GIT_PAGER"] == "cat"
    assert environment["PAGER"] == "cat"
    assert environment["GIT_EDITOR"] == "/bin/false"
    assert environment["GIT_SEQUENCE_EDITOR"] == "/bin/false"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("head", "oid", "detached", "unborn"),
    [
        ("(detached)", "deadbeef", True, False),
        ("new-branch", "(initial)", False, True),
    ],
)
async def test_git_status_handles_detached_and_unborn_branches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    head: str,
    oid: str,
    detached: bool,
    unborn: bool,
) -> None:
    raw = f"# branch.oid {oid}\0# branch.head {head}\0".encode()
    runner = RecordingRunner([(0, b"", b""), (0, raw, b""), (2, b"", b"")])
    status = await git_adapter(monkeypatch, runner).status(repository(tmp_path))
    assert status.detached_head is detached
    assert status.unborn_branch is unborn
    assert status.branch is None if detached else status.branch == head


@pytest.mark.anyio
@pytest.mark.parametrize(
    "key",
    [
        "core.hooksPath",
        "core.alternateRefsCommand",
        "core.attributesFile",
        "core.excludesFile",
        "core.pager",
        "pager.branch",
        "core.editor",
        "sequence.editor",
        "core.sshCommand",
        "credential.helper",
        "credential.https://github.com.helper",
        "diff.external",
        "core.fsmonitor",
        "core.worktree",
        "filter.lfs.process",
        "url.file:///tmp/.insteadOf",
        "protocol.file.allow",
        "remote.origin.receivepack",
        "remote.origin.uploadpack",
        "remote.origin.push",
        "remote.origin.pushurl",
        "remote.origin.mirror",
        "push.default",
        "branch.main.pushRemote",
        "branch.main.mergeOptions",
        "http.https://github.com/.extraHeader",
        "http.proxy",
        "http.curloptResolve",
        "interactive.diffFilter",
        "pull.twohead",
        "alias.publish",
        "include.path",
        "includeIf.gitdir:/tmp.path",
    ],
)
async def test_repository_controlled_executable_config_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    runner = RecordingRunner([(0, f"{key}\nevil\0".encode(), b"")])
    with pytest.raises(RuntimeOperationError) as raised:
        await git_adapter(monkeypatch, runner).status(repository(tmp_path))
    assert raised.value.code == "GIT_CONFIG_UNSAFE"
    assert len(runner.calls) == 1
    arguments = runner.calls[0]["arguments"]
    assert isinstance(arguments, tuple)
    assert arguments[-4:] == ("config", "--no-includes", "--null", "--list")


@pytest.mark.anyio
async def test_worktree_config_cannot_execute_repository_controlled_program(
    tmp_path: Path,
) -> None:
    git_path = shutil.which("git")
    if git_path is None:
        pytest.skip("Git is unavailable")
    identity = inspect_executable(Path(git_path).absolute(), error_prefix="GIT")
    runner = ControlledProcessRunner()
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    environment = {
        "HOME": str(home),
        "PATH": os.pathsep.join((str(Path(git_path).parent), "/usr/bin", "/bin")),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
    }
    initialized = await runner.run(
        identity,
        ("init", "--quiet"),
        environment=environment,
        cwd=project,
        timeout_seconds=10,
        stdout_limit=4096,
        stderr_limit=4096,
        error_prefix="GIT",
    )
    assert initialized.exit_code == 0
    canary = tmp_path / "executed-canary"
    executable = tmp_path / "malicious-fsmonitor"
    executable.write_text(f"#!/bin/sh\ntouch {canary}\n", encoding="utf-8")
    executable.chmod(0o700)
    config = project / ".git" / "config"
    with config.open("a", encoding="utf-8") as stream:
        stream.write("\n[extensions]\n\tworktreeConfig = true\n")
    (project / ".git" / "config.worktree").write_text(
        f"[core]\n\tfsmonitor = {executable}\n", encoding="utf-8"
    )
    adapter = GitAdapter(environment=environment)

    with pytest.raises(RuntimeOperationError) as raised:
        await adapter.status(project)

    assert raised.value.code == "GIT_CONFIG_UNSAFE"
    assert not canary.exists()


@pytest.mark.anyio
async def test_repository_ownership_mismatch_fails_closed_without_chown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = RecordingRunner([])
    adapter = git_adapter(monkeypatch, runner)
    project = repository(tmp_path)
    monkeypatch.setattr("agentbox_runtime.git.os.geteuid", lambda: project.stat().st_uid + 1)
    with pytest.raises(RuntimeOperationError) as raised:
        await adapter.status(project)
    assert raised.value.code == "GIT_OWNERSHIP_UNSAFE"
    assert runner.calls == []


@pytest.mark.anyio
async def test_branch_list_is_bounded_and_mutations_use_fixed_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    branch_output = b"".join(
        f"feature/{index}\0{'*' if index == 0 else ''}\n".encode() for index in range(600)
    )
    runner = RecordingRunner(
        [
            (0, b"", b""),
            (0, branch_output, b""),
            (0, b"", b""),
            (0, b"", b""),
            (0, b"", b""),
            (0, b"", b""),
            (1, b"", b"local changes would be overwritten"),
        ]
    )
    adapter = git_adapter(monkeypatch, runner)
    project = repository(tmp_path)

    branches = await adapter.branches(project)
    assert len(branches) == 500
    assert branches[0].current is True
    assert (await adapter.create_branch(project, "feature/literal")).branch == "feature/literal"
    with pytest.raises(RuntimeOperationError) as raised:
        await adapter.switch_branch(project, "feature/other")
    assert raised.value.code == "GIT_SWITCH_BLOCKED"
    assert runner.calls[3]["arguments"] == ("check-ref-format", "--branch", "feature/literal")
    branch_arguments = runner.calls[4]["arguments"]
    switch_arguments = runner.calls[-1]["arguments"]
    assert isinstance(branch_arguments, tuple)
    assert isinstance(switch_arguments, tuple)
    assert branch_arguments[-3:] == ("branch", "--", "feature/literal")
    assert switch_arguments[-3:] == ("switch", "--", "feature/other")


def status_results(*, upstream: bool = True) -> list[tuple[int, bytes, bytes]]:
    raw = b"# branch.oid abc\0# branch.head main\0"
    if upstream:
        raw += b"# branch.upstream origin/main\0# branch.ab +0 -0\0"
    return [(0, b"", b""), (0, raw, b""), (0, b"", b"")]


def approved_upstream_results() -> list[tuple[int, bytes, bytes]]:
    return [
        (0, b"origin\n", b""),
        (0, b"refs/heads/main\n", b""),
        (0, b"https://github.com/owner/repo.git\0", b""),
    ]


@pytest.mark.anyio
async def test_pull_is_fast_forward_only_and_never_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = RecordingRunner(
        [*status_results(), *approved_upstream_results(), (0, b"updated", b"")]
    )
    result = await git_adapter(monkeypatch, runner).pull(repository(tmp_path))
    assert result.outcome == "pulled"
    arguments = runner.calls[-1]["arguments"]
    assert isinstance(arguments, tuple)
    assert arguments[-8:] == (
        "pull",
        "--ff-only",
        "--no-rebase",
        "--no-tags",
        "--no-recurse-submodules",
        "--no-verify",
        "origin",
        "refs/heads/main",
    )
    assert "merge" not in arguments and "rebase" not in arguments


@pytest.mark.anyio
async def test_pull_divergence_and_missing_upstream_are_normalized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = repository(tmp_path)
    diverged = RecordingRunner(
        [
            *status_results(),
            *approved_upstream_results(),
            (1, b"", b"fatal: Not possible to fast-forward, aborting."),
        ]
    )
    with pytest.raises(RuntimeOperationError) as raised:
        await git_adapter(monkeypatch, diverged).pull(project)
    assert raised.value.code == "GIT_PULL_REQUIRES_RECONCILIATION"

    missing = RecordingRunner(status_results(upstream=False))
    with pytest.raises(RuntimeOperationError) as raised:
        await git_adapter(monkeypatch, missing).pull(project)
    assert raised.value.code == "GIT_UPSTREAM_MISSING"
    for call in missing.calls:
        arguments = call["arguments"]
        assert isinstance(arguments, tuple)
        assert "pull" not in arguments


@pytest.mark.anyio
async def test_push_has_no_force_surface_and_auth_errors_do_not_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    canary = "https://user:SECRET-CANARY@github.com/owner/repo.git"
    runner = RecordingRunner(
        [
            *status_results(),
            *approved_upstream_results(),
            (1, b"", f"could not read Username for '{canary}'".encode()),
        ]
    )
    with caplog.at_level(logging.DEBUG), pytest.raises(RuntimeOperationError) as raised:
        await git_adapter(monkeypatch, runner).push(repository(tmp_path))
    assert raised.value.code == "GIT_AUTH_REQUIRED"
    assert raised.value.message == "Git authentication is required"
    assert "SECRET-CANARY" not in caplog.text
    arguments = runner.calls[-1]["arguments"]
    assert isinstance(arguments, tuple)
    assert arguments[-5:] == (
        "push",
        "--no-verify",
        "--porcelain",
        "origin",
        "refs/heads/main:refs/heads/main",
    )
    assert not any("force" in value for value in arguments)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("remote", "merge_ref", "origin_url", "expected"),
    [
        (
            "attacker",
            "refs/heads/main",
            "https://github.com/owner/repo.git\0",
            "GIT_UPSTREAM_UNSAFE",
        ),
        (
            "origin",
            "+refs/heads/main",
            "https://github.com/owner/repo.git\0",
            "GIT_UPSTREAM_UNSAFE",
        ),
        ("origin", "refs/heads/main", "file:///tmp/repository\0", "GIT_REMOTE_UNSAFE"),
        (
            "origin",
            "refs/heads/main",
            "https://github.com/owner/one.git\0https://github.com/owner/two.git\0",
            "GIT_REMOTE_UNSAFE",
        ),
    ],
)
async def test_network_mutations_reject_unsafe_upstream_and_remote_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    remote: str,
    merge_ref: str,
    origin_url: str,
    expected: str,
) -> None:
    runner = RecordingRunner(
        [
            *status_results(),
            (0, f"{remote}\n".encode(), b""),
            (0, f"{merge_ref}\n".encode(), b""),
            (0, origin_url.encode(), b""),
        ]
    )
    with pytest.raises(RuntimeOperationError) as raised:
        await git_adapter(monkeypatch, runner).push(repository(tmp_path))
    assert raised.value.code == expected
    for call in runner.calls:
        arguments = call["arguments"]
        assert isinstance(arguments, tuple)
        assert "push" not in arguments


@pytest.mark.parametrize("value", ["", "bad\x00title", "e\u0301"])
def test_pr_title_validation_rejects_control_and_normalization(value: str) -> None:
    with pytest.raises(RuntimeOperationError):
        validate_pr_title(value)


def test_pr_body_is_bounded_and_github_identity_is_conservative() -> None:
    assert validate_pr_body("x" * MAX_PR_BODY_BYTES) == "x" * MAX_PR_BODY_BYTES
    with pytest.raises(RuntimeOperationError):
        validate_pr_body("x" * (MAX_PR_BODY_BYTES + 1))
    assert github_repository_from_remote("https://github.com/owner/repo.git") == "owner/repo"
    assert github_repository_from_remote("git@github.com:owner/repo.git") == "owner/repo"
    assert github_repository_from_remote("https://example.com/owner/repo.git") is None
    assert github_repository_from_remote("http://github.com/owner/repo.git") is None
    assert github_repository_from_remote("ssh://git@github.com/owner/repo.git") is None
    assert github_repository_from_remote("https://user:token@github.com/owner/repo.git") is None
    assert github_repository_from_remote("https://github.com/owner/repo.git?token=bad") is None


def github_adapter(
    monkeypatch: pytest.MonkeyPatch,
    runner: RecordingRunner,
    git: FakeGit,
) -> GitHubAdapter:
    adapter = GitHubAdapter(
        git,  # type: ignore[arg-type]
        environment={"HOME": "/runtime-home", "PATH": "/usr/bin:/bin"},
        runner=runner,  # type: ignore[arg-type]
    )
    monkeypatch.setattr(adapter, "executable", lambda: IDENTITY)
    return adapter


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("exit_code", "stderr", "expected"),
    [
        (0, b"Logged in", AuthenticationState.AUTHENTICATED),
        (1, b"You are not logged into any GitHub hosts", AuthenticationState.UNAUTHENTICATED),
        (1, b"unexpected failure", AuthenticationState.UNKNOWN),
    ],
)
async def test_github_auth_detection_is_public_and_noninteractive(
    monkeypatch: pytest.MonkeyPatch,
    exit_code: int,
    stderr: bytes,
    expected: AuthenticationState,
) -> None:
    runner = RecordingRunner([(0, b"gh version 2.50.0\n", b""), (exit_code, b"", stderr)])
    adapter = github_adapter(monkeypatch, runner, FakeGit(GitStatus(False)))
    status = await adapter.status()
    assert status.authentication is expected
    assert runner.calls[-1]["arguments"] == (
        "auth",
        "status",
        "--hostname",
        "github.com",
    )
    environment = runner.calls[-1]["environment"]
    assert isinstance(environment, dict)
    assert environment["GH_PROMPT_DISABLED"] == "1"
    assert environment["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert environment["GIT_ASKPASS"] == "/bin/false"
    assert environment["SSH_ASKPASS"] == "/bin/false"
    assert environment["GIT_ALLOW_PROTOCOL"] == "https:ssh"


@pytest.mark.anyio
async def test_github_project_status_parses_pr_and_check_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = (
        b'{"number":42,"title":"Safe PR","state":"OPEN","isDraft":true,'
        b'"url":"https://github.com/owner/repo/pull/42",'
        b'"baseRefName":"main","headRefName":"feature/safe",'
        b'"mergeStateStatus":"CLEAN",'
        b'"statusCheckRollup":[{"status":"COMPLETED","conclusion":"SUCCESS"}]}'
    )
    runner = RecordingRunner([(0, b"gh version 2.50.0", b""), (0, b"ok", b""), (0, payload, b"")])
    git = FakeGit(
        GitStatus(
            True,
            branch="feature",
            upstream="origin/feature",
            remote_url="https://github.com/owner/repo.git",
        )
    )
    status = await github_adapter(monkeypatch, runner, git).project_status(tmp_path)
    assert status.repository == "owner/repo"
    assert status.pull_request_number == 42
    assert status.pull_request_draft is True
    assert status.pull_request_base == "main"
    assert status.pull_request_head == "feature/safe"
    assert status.mergeability == "clean"
    assert status.checks == "pass"


def test_github_check_summary_distinguishes_failure_pending_and_unknown() -> None:
    assert GitHubAdapter._checks([{"status": "COMPLETED", "conclusion": "FAILURE"}]) == "fail"
    assert GitHubAdapter._checks([{"status": "IN_PROGRESS", "conclusion": ""}]) == "pending"
    assert GitHubAdapter._checks([]) == "unknown"


@pytest.mark.anyio
async def test_github_malformed_output_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = RecordingRunner(
        [(0, b"gh version 2.50.0", b""), (0, b"ok", b""), (0, b"not-json", b"")]
    )
    git = FakeGit(
        GitStatus(
            True,
            branch="feature",
            upstream="origin/feature",
            remote_url="https://github.com/owner/repo.git",
        )
    )
    with pytest.raises(RuntimeOperationError) as raised:
        await github_adapter(monkeypatch, runner, git).project_status(tmp_path)
    assert raised.value.code == "GITHUB_OUTPUT_INVALID"


@pytest.mark.anyio
async def test_draft_pr_uses_fixed_argv_and_body_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    title = 'Literal "quoted" \' $(touch never) ; title'
    body = "Literal body\n$(touch never)\nTOKENISH=not-a-secret"
    runner = RecordingRunner(
        [
            (0, b"gh version 2.50.0", b""),
            (0, b"ok", b""),
            (0, b"https://github.com/owner/repo/pull/77\n", b""),
        ]
    )
    git = FakeGit(
        GitStatus(
            True,
            branch="feature",
            upstream="origin/feature",
            remote_url="https://github.com/owner/repo.git",
        )
    )
    result = await github_adapter(monkeypatch, runner, git).create_draft_pull_request(
        tmp_path, title=title, body=body, base="develop"
    )
    assert result.number == 77 and result.draft is True
    call = runner.calls[-1]
    assert call["arguments"] == (
        "pr",
        "create",
        "--draft",
        "--title",
        title,
        "--body-file",
        "-",
        "--base",
        "develop",
    )
    assert call["stdin"] == body.encode()
    assert call["sensitive"] is True


@pytest.mark.anyio
async def test_draft_pr_rejects_unpublished_branch_before_gh_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = RecordingRunner([(0, b"gh version 2.50.0", b""), (0, b"ok", b"")])
    git = FakeGit(GitStatus(True, branch="feature", remote_url="https://github.com/owner/repo.git"))
    with pytest.raises(RuntimeOperationError) as raised:
        await github_adapter(monkeypatch, runner, git).create_draft_pull_request(
            tmp_path, title="Safe title", body="bounded markdown", base=None
        )
    assert raised.value.code == "GIT_UPSTREAM_MISSING"
    for call in runner.calls:
        arguments = call["arguments"]
        assert isinstance(arguments, tuple)
        assert arguments[:2] != ("pr", "create")
