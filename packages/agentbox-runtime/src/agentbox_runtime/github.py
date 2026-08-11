"""Public GitHub CLI adapter with fixed non-interactive operations."""

from __future__ import annotations

import json
import os
import re
import shutil
import unicodedata
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

from agentbox_runtime.git import GitAdapter, validate_branch_name
from agentbox_runtime.models import (
    AuthenticationState,
    GitHubProjectStatus,
    GitHubPullRequestResult,
    GitHubStatus,
    RuntimeOperationError,
)
from agentbox_runtime.process import (
    ControlledProcessRunner,
    ExecutableIdentity,
    ProcessResult,
    inspect_executable,
    minimal_runtime_environment,
)

_PR_URL = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/(\d+)")


def github_repository_from_remote(remote: str | None) -> str | None:
    if not remote:
        return None
    ssh = re.fullmatch(
        r"git@github\.com:([A-Za-z0-9_.-]{1,100})/([A-Za-z0-9_.-]{1,100})(?:\.git)?",
        remote,
    )
    if ssh:
        return f"{ssh.group(1)}/{ssh.group(2).removesuffix('.git')}"
    try:
        parsed = urlsplit(remote)
        hostname = parsed.hostname
        port = parsed.port
        username = parsed.username
        password = parsed.password
    except ValueError:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or hostname != "github.com"
        or port is not None
        or username is not None
        or password is not None
        or parsed.query
        or parsed.fragment
        or len(parts) != 2
    ):
        return None
    owner = parts[0]
    repository = parts[1].removesuffix(".git")
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", owner)
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", repository)
        or owner.startswith("-")
        or repository.startswith("-")
        or owner in {".", ".."}
        or repository in {".", ".."}
        or parsed.path != f"/{parts[0]}/{parts[1]}"
    ):
        return None
    return f"{owner}/{repository}"


def validate_pr_title(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).strip()
    if (
        normalized != value.strip()
        or not 1 <= len(normalized) <= 256
        or any(unicodedata.category(character).startswith("C") for character in normalized)
    ):
        raise RuntimeOperationError(
            "GITHUB_PR_INPUT_INVALID", "Pull request title is invalid", category="validation"
        )
    return normalized


def validate_pr_body(value: str) -> str:
    if not isinstance(value, str) or len(value.encode("utf-8")) > 16 * 1024:
        raise RuntimeOperationError(
            "GITHUB_PR_INPUT_INVALID", "Pull request body is invalid", category="validation"
        )
    normalized = unicodedata.normalize("NFC", value)
    if normalized != value or any(
        unicodedata.category(character).startswith("C") and character not in {"\n", "\t"}
        for character in value
    ):
        raise RuntimeOperationError(
            "GITHUB_PR_INPUT_INVALID", "Pull request body is invalid", category="validation"
        )
    return value


class GitHubAdapter:
    def __init__(
        self,
        git: GitAdapter,
        *,
        environment: Mapping[str, str] | None = None,
        runner: ControlledProcessRunner | None = None,
    ) -> None:
        self._git = git
        self._environment = minimal_runtime_environment(environment or os.environ)
        self._environment.update(
            {
                "GH_PROMPT_DISABLED": "1",
                "GH_PAGER": "cat",
                "PAGER": "cat",
                "GIT_TERMINAL_PROMPT": "0",
                "GCM_INTERACTIVE": "Never",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_EDITOR": "/bin/false",
                "GIT_ASKPASS": "/bin/false",
                "GIT_PAGER": "cat",
                "GIT_SEQUENCE_EDITOR": "/bin/false",
                "SSH_ASKPASS": "/bin/false",
                "GIT_LFS_SKIP_SMUDGE": "1",
                "GIT_ALLOW_PROTOCOL": "https:ssh",
            }
        )
        self._runner = runner or ControlledProcessRunner()

    def executable(self) -> ExecutableIdentity | None:
        selected = shutil.which("gh", path=self._environment.get("PATH", ""))
        if selected is None:
            return None
        try:
            return inspect_executable(Path(selected).absolute(), error_prefix="GITHUB")
        except RuntimeOperationError:
            return None

    async def status(self) -> GitHubStatus:
        identity = self.executable()
        if identity is None:
            return GitHubStatus(False, None, AuthenticationState.UNKNOWN)
        version_result = await self._run(identity, ("--version",), cwd=self._home())
        version_match = re.search(r"gh version\s+([^\s]+)", self._text(version_result), re.I)
        version = version_match.group(1)[:64] if version_match else None
        auth = await self._run(
            identity,
            ("auth", "status", "--hostname", "github.com"),
            cwd=self._home(),
            timeout=10,
        )
        if auth.exit_code == 0:
            authentication = AuthenticationState.AUTHENTICATED
        elif re.search(r"not logged|not authenticated|login", self._text(auth), re.I):
            authentication = AuthenticationState.UNAUTHENTICATED
        else:
            authentication = AuthenticationState.UNKNOWN
        return GitHubStatus(True, version, authentication)

    async def project_status(self, project: Path) -> GitHubProjectStatus:
        status = await self._git.status(project)
        repository = github_repository_from_remote(status.remote_url)
        if repository is None:
            return GitHubProjectStatus(False)
        global_status = await self.status()
        if (
            not global_status.installed
            or global_status.authentication is not AuthenticationState.AUTHENTICATED
        ):
            return GitHubProjectStatus(False, repository=repository)
        identity = self._require_executable()
        result = await self._run(
            identity,
            (
                "pr",
                "view",
                "--json",
                "number,title,state,isDraft,url,baseRefName,headRefName,mergeStateStatus,statusCheckRollup",
            ),
            cwd=project,
            timeout=20,
            stdout_limit=64 * 1024,
        )
        if result.exit_code != 0:
            return GitHubProjectStatus(True, repository=repository)
        try:
            payload = json.loads(result.stdout)
            if not isinstance(payload, dict):
                raise ValueError
            title = validate_pr_title(str(payload["title"]))
            return GitHubProjectStatus(
                available=True,
                repository=repository,
                pull_request_number=int(payload["number"]),
                pull_request_title=title,
                pull_request_state=str(payload["state"])[:32].casefold(),
                pull_request_draft=bool(payload["isDraft"]),
                pull_request_url=self._validated_pr_url(str(payload["url"])),
                pull_request_base=self._bounded_ref(payload.get("baseRefName")),
                pull_request_head=self._bounded_ref(payload.get("headRefName")),
                mergeability=self._bounded_mergeability(payload.get("mergeStateStatus")),
                checks=self._checks(payload.get("statusCheckRollup")),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeOperationError(
                "GITHUB_OUTPUT_INVALID", "GitHub CLI returned an invalid response"
            ) from exc

    async def create_draft_pull_request(
        self,
        project: Path,
        *,
        title: str,
        body: str,
        base: str | None,
    ) -> GitHubPullRequestResult:
        title = validate_pr_title(title)
        body = validate_pr_body(body)
        if base is not None:
            base = validate_branch_name(base)
        global_status = await self.status()
        if global_status.authentication is AuthenticationState.UNAUTHENTICATED:
            raise RuntimeOperationError(
                "GITHUB_UNAUTHENTICATED",
                "GitHub CLI authentication is required",
                category="unauthenticated",
            )
        if global_status.authentication is not AuthenticationState.AUTHENTICATED:
            raise RuntimeOperationError(
                "GITHUB_AUTH_UNKNOWN",
                "GitHub CLI authentication is unknown",
                category="unavailable",
            )
        git_status = await self._git.status(project)
        if git_status.detached_head or git_status.branch is None:
            raise RuntimeOperationError(
                "GIT_DETACHED_HEAD",
                "Draft pull request requires a local branch",
                category="conflict",
            )
        if git_status.upstream is None:
            raise RuntimeOperationError(
                "GIT_UPSTREAM_MISSING",
                "Draft pull request requires a published branch",
                category="conflict",
            )
        if github_repository_from_remote(git_status.remote_url) is None:
            raise RuntimeOperationError(
                "GITHUB_REPOSITORY_UNKNOWN",
                "Project is not linked to a supported GitHub repository",
                category="conflict",
            )
        arguments = ["pr", "create", "--draft", "--title", title, "--body-file", "-"]
        if base is not None:
            arguments.extend(("--base", base))
        result = await self._run(
            self._require_executable(),
            tuple(arguments),
            cwd=project,
            timeout=60,
            stdout_limit=8192,
            stderr_limit=16 * 1024,
            stdin_data=body.encode("utf-8"),
        )
        if result.exit_code != 0:
            raise RuntimeOperationError(
                "GITHUB_PR_CREATE_FAILED", "Draft pull request creation failed"
            )
        match = _PR_URL.search(result.stdout.decode("utf-8", errors="replace"))
        if match is None:
            raise RuntimeOperationError(
                "GITHUB_OUTPUT_INVALID", "GitHub CLI returned an invalid response"
            )
        return GitHubPullRequestResult(int(match.group(1)), match.group(0), True)

    def _require_executable(self) -> ExecutableIdentity:
        identity = self.executable()
        if identity is None:
            raise RuntimeOperationError(
                "GITHUB_NOT_INSTALLED", "GitHub CLI is unavailable", category="unavailable"
            )
        return identity

    def _home(self) -> Path:
        return Path(self._environment.get("HOME", "/"))

    async def _run(
        self,
        identity: ExecutableIdentity,
        arguments: tuple[str, ...],
        *,
        cwd: Path,
        timeout: float = 10,
        stdout_limit: int = 32 * 1024,
        stderr_limit: int = 16 * 1024,
        stdin_data: bytes | None = None,
    ) -> ProcessResult:
        return await self._runner.run(
            identity,
            arguments,
            environment=self._environment,
            cwd=cwd,
            timeout_seconds=timeout,
            stdout_limit=stdout_limit,
            stderr_limit=stderr_limit,
            stdin_data=stdin_data,
            sensitive_output=True,
            error_prefix="GITHUB",
        )

    @staticmethod
    def _text(result: ProcessResult) -> str:
        return (result.stdout + b"\n" + result.stderr).decode("utf-8", errors="replace")

    @staticmethod
    def _validated_pr_url(value: str) -> str:
        match = _PR_URL.fullmatch(value)
        if match is None:
            raise ValueError("invalid PR URL")
        return value

    @staticmethod
    def _checks(value: object) -> str:
        if not isinstance(value, list) or not value:
            return "unknown"
        pending = False
        for item in value[:200]:
            if not isinstance(item, dict):
                return "unknown"
            conclusion = str(item.get("conclusion") or "").casefold()
            status = str(item.get("status") or "").casefold()
            if conclusion in {"failure", "error", "cancelled", "timed_out", "action_required"}:
                return "fail"
            if status not in {"completed", "success"} and conclusion not in {
                "success",
                "neutral",
                "skipped",
            }:
                pending = True
        return "pending" if pending else "pass"

    @staticmethod
    def _bounded_ref(value: object) -> str | None:
        if not isinstance(value, str) or not value or len(value) > 128:
            return None
        try:
            return validate_branch_name(value)
        except RuntimeOperationError:
            return None

    @staticmethod
    def _bounded_mergeability(value: object) -> str | None:
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_]{1,32}", value):
            return None
        return value.casefold()
