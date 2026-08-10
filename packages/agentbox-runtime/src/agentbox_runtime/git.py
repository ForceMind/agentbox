"""Typed Git operations with fixed argv, sanitized environment, and no shell."""

from __future__ import annotations

import os
import re
import shutil
import unicodedata
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from agentbox_runtime.models import (
    GitActionResult,
    GitBranch,
    GitInstallationStatus,
    GitStatus,
    RuntimeOperationError,
)
from agentbox_runtime.process import (
    ControlledProcessRunner,
    ExecutableIdentity,
    ProcessResult,
    inspect_executable,
    minimal_runtime_environment,
)

_GITHUB_SSH = re.compile(
    r"git@github\.com:(?P<owner>[A-Za-z0-9_.-]{1,100})/"
    r"(?P<repo>[A-Za-z0-9_.-]{1,100})(?:\.git)?"
)
_BRANCH = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._/-]{0,126}[A-Za-z0-9])?")
_SAFE_CONFIG = (
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "core.pager=cat",
    "-c",
    "pager.status=false",
    "-c",
    "diff.external=",
    "-c",
    "core.editor=false",
)
_DANGEROUS_CONFIG = (
    "alias.",
    "credential.helper",
    "core.hookspath",
    "core.sshcommand",
    "core.pager",
    "core.editor",
    "diff.external",
    "include.path",
    "includeif.",
)


def validate_git_repository_url(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 512 or value != value.strip():
        raise RuntimeOperationError(
            "GIT_REPOSITORY_URL_INVALID", "Repository URL is invalid", category="validation"
        )
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise RuntimeOperationError(
            "GIT_REPOSITORY_URL_INVALID", "Repository URL is invalid", category="validation"
        )
    ssh = _GITHUB_SSH.fullmatch(value)
    if ssh:
        if ssh.group("owner").startswith("-") or ssh.group("repo").startswith("-"):
            raise RuntimeOperationError(
                "GIT_REPOSITORY_URL_INVALID", "Repository URL is invalid", category="validation"
            )
        return value
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeOperationError(
            "GIT_REPOSITORY_URL_INVALID", "Repository URL is invalid", category="validation"
        )
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or any(
        not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", part.removesuffix(".git")) for part in parts
    ):
        raise RuntimeOperationError(
            "GIT_REPOSITORY_URL_INVALID", "Repository URL is invalid", category="validation"
        )
    return value


def validate_branch_name(value: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not _BRANCH.fullmatch(value)
        or value.startswith("-")
        or value in {"HEAD", "@"}
        or ".." in value
        or "@{" in value
        or "//" in value
        or value.endswith(("/", ".", ".lock"))
    ):
        raise RuntimeOperationError(
            "GIT_BRANCH_INVALID", "Branch name is invalid", category="validation"
        )
    return value


def redact_remote_url(value: str) -> str | None:
    """Remove userinfo/query/fragment; invalid or local transports are not displayed."""
    value = value.strip()
    ssh = _GITHUB_SSH.fullmatch(value)
    if ssh:
        repository = ssh.group("repo").removesuffix(".git")
        return f"git@github.com:{ssh.group('owner')}/{repository}.git"
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme not in {"https", "ssh"} or not parsed.hostname:
        return None
    host = parsed.hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


class GitAdapter:
    def __init__(
        self,
        *,
        environment: Mapping[str, str] | None = None,
        runner: ControlledProcessRunner | None = None,
    ) -> None:
        self._environment = minimal_runtime_environment(environment or os.environ)
        self._environment.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "GCM_INTERACTIVE": "Never",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_ASKPASS": "/bin/false",
                "SSH_ASKPASS": "/bin/false",
                "GIT_LFS_SKIP_SMUDGE": "1",
                "GIT_ALLOW_PROTOCOL": "https:ssh",
            }
        )
        self._runner = runner or ControlledProcessRunner()

    def executable(self) -> ExecutableIdentity | None:
        selected = shutil.which("git", path=self._environment.get("PATH", ""))
        if selected is None:
            return None
        try:
            return inspect_executable(Path(selected).absolute(), error_prefix="GIT")
        except RuntimeOperationError:
            return None

    async def version(self) -> str | None:
        identity = self._require_executable()
        result = await self._run(identity, ("--version",), cwd=Path(self._environment["HOME"]))
        match = re.search(r"git version\s+([^\s]+)", self._text(result), re.I)
        return match.group(1)[:64] if result.exit_code == 0 and match else None

    async def installation_status(self) -> GitInstallationStatus:
        identity = self.executable()
        if identity is None:
            return GitInstallationStatus(False, None)
        return GitInstallationStatus(True, await self.version())

    async def clone(self, repository_url: str, *, cwd: Path, destination: Path) -> None:
        url = validate_git_repository_url(repository_url)
        if destination.parent != cwd or destination.exists():
            raise RuntimeOperationError(
                "GIT_CLONE_DESTINATION_INVALID",
                "Clone destination is invalid",
                category="validation",
            )
        identity = self._require_executable()
        result = await self._run(
            identity,
            (
                *_SAFE_CONFIG,
                "clone",
                "--no-recurse-submodules",
                "--no-hardlinks",
                "--",
                url,
                str(destination),
            ),
            cwd=cwd,
            timeout=300,
            stdout_limit=64 * 1024,
            stderr_limit=64 * 1024,
        )
        if result.exit_code != 0:
            self._raise_network_failure(result, "GIT_CLONE_FAILED", "Repository clone failed")

    async def status(self, project: Path) -> GitStatus:
        identity = self._require_executable()
        if not self._repository_owned(project):
            return GitStatus(is_repository=False)
        await self._assert_safe_repository_config(identity, project)
        result = await self._run(
            identity,
            (
                "--no-optional-locks",
                *_SAFE_CONFIG,
                "status",
                "--porcelain=v2",
                "--branch",
                "-z",
                "--untracked-files=normal",
            ),
            cwd=project,
            stdout_limit=256 * 1024,
        )
        if result.exit_code != 0:
            raise RuntimeOperationError("GIT_STATUS_FAILED", "Git status failed")
        return await self._parse_status(identity, project, result.stdout)

    async def branches(self, project: Path) -> tuple[GitBranch, ...]:
        identity = self._require_repository(project)
        await self._assert_safe_repository_config(identity, project)
        result = await self._run(
            identity,
            (
                "--no-optional-locks",
                *_SAFE_CONFIG,
                "for-each-ref",
                "--format=%(refname:short)%00%(HEAD)",
                "refs/heads",
            ),
            cwd=project,
            stdout_limit=128 * 1024,
        )
        if result.exit_code != 0:
            raise RuntimeOperationError("GIT_BRANCH_LIST_FAILED", "Branch list failed")
        branches: list[GitBranch] = []
        for line in result.stdout.decode("utf-8", errors="replace").splitlines()[:500]:
            name, _, marker = line.partition("\x00")
            if name and len(name) <= 128:
                branches.append(GitBranch(name=name, current=marker.strip() == "*"))
        return tuple(branches)

    async def create_branch(self, project: Path, branch: str) -> GitActionResult:
        branch = validate_branch_name(branch)
        identity = self._require_repository(project)
        await self._assert_safe_repository_config(identity, project)
        checked = await self._run(identity, ("check-ref-format", "--branch", branch), cwd=project)
        if checked.exit_code != 0:
            raise RuntimeOperationError(
                "GIT_BRANCH_INVALID", "Branch name is invalid", category="validation"
            )
        result = await self._run(identity, (*_SAFE_CONFIG, "branch", "--", branch), cwd=project)
        if result.exit_code != 0:
            raise RuntimeOperationError(
                "GIT_BRANCH_EXISTS", "Branch could not be created", category="conflict"
            )
        return GitActionResult("created", branch)

    async def switch_branch(self, project: Path, branch: str) -> GitActionResult:
        branch = validate_branch_name(branch)
        identity = self._require_repository(project)
        await self._assert_safe_repository_config(identity, project)
        result = await self._run(identity, (*_SAFE_CONFIG, "switch", "--", branch), cwd=project)
        if result.exit_code != 0:
            raise RuntimeOperationError(
                "GIT_SWITCH_BLOCKED",
                "Branch switch was blocked; the working tree was not changed by AgentBox",
                category="conflict",
            )
        return GitActionResult("switched", branch)

    async def pull(self, project: Path) -> GitActionResult:
        identity = self._require_repository(project)
        await self._assert_safe_repository_config(identity, project)
        status = await self.status(project)
        if status.detached_head:
            raise RuntimeOperationError(
                "GIT_DETACHED_HEAD",
                "Pull is unavailable in detached HEAD state",
                category="conflict",
            )
        if status.upstream is None:
            raise RuntimeOperationError(
                "GIT_UPSTREAM_MISSING", "Current branch has no upstream", category="conflict"
            )
        result = await self._run(
            identity,
            (*_SAFE_CONFIG, "pull", "--ff-only", "--no-rebase"),
            cwd=project,
            timeout=300,
            stdout_limit=64 * 1024,
            stderr_limit=64 * 1024,
        )
        if result.exit_code != 0:
            output = self._text(result).casefold()
            if "not possible to fast-forward" in output or "diverg" in output:
                raise RuntimeOperationError(
                    "GIT_PULL_REQUIRES_RECONCILIATION",
                    "Pull requires manual reconciliation",
                    category="conflict",
                )
            self._raise_network_failure(result, "GIT_PULL_FAILED", "Pull failed")
        return GitActionResult("pulled", status.branch)

    async def push(self, project: Path) -> GitActionResult:
        identity = self._require_repository(project)
        await self._assert_safe_repository_config(identity, project)
        status = await self.status(project)
        if status.detached_head:
            raise RuntimeOperationError(
                "GIT_DETACHED_HEAD",
                "Push is unavailable in detached HEAD state",
                category="conflict",
            )
        if status.upstream is None:
            raise RuntimeOperationError(
                "GIT_UPSTREAM_MISSING", "Current branch has no upstream", category="conflict"
            )
        result = await self._run(
            identity,
            (*_SAFE_CONFIG, "push"),
            cwd=project,
            timeout=300,
            stdout_limit=64 * 1024,
            stderr_limit=64 * 1024,
        )
        if result.exit_code != 0:
            self._raise_network_failure(result, "GIT_PUSH_FAILED", "Push failed")
        return GitActionResult("pushed", status.branch)

    async def _parse_status(
        self, identity: ExecutableIdentity, project: Path, raw: bytes
    ) -> GitStatus:
        branch = upstream = None
        detached = unborn = False
        ahead = behind = staged = unstaged = untracked = conflicted = 0
        for record in raw.decode("utf-8", errors="replace").split("\x00"):
            if record.startswith("# branch.head "):
                value = record.removeprefix("# branch.head ")[:128]
                detached = value == "(detached)"
                branch = None if detached else value
            elif record.startswith("# branch.upstream "):
                upstream = record.removeprefix("# branch.upstream ")[:128]
            elif record.startswith("# branch.ab "):
                match = re.fullmatch(r"# branch\.ab \+(\d+) -(\d+)", record)
                if match:
                    ahead, behind = int(match.group(1)), int(match.group(2))
            elif record.startswith("# branch.oid (initial)"):
                unborn = True
            elif record.startswith(("1 ", "2 ")):
                fields = record.split(" ", 2)
                xy = fields[1] if len(fields) > 1 else ".."
                staged += xy[0] != "."
                unstaged += len(xy) > 1 and xy[1] != "."
            elif record.startswith("u "):
                conflicted += 1
            elif record.startswith("? "):
                untracked += 1
        remote_url = await self._remote_url(identity, project)
        return GitStatus(
            is_repository=True,
            branch=branch,
            detached_head=detached,
            unborn_branch=unborn,
            upstream=upstream,
            ahead=ahead,
            behind=behind,
            staged_count=staged,
            unstaged_count=unstaged,
            untracked_count=untracked,
            conflicted_count=conflicted,
            clean=not any((staged, unstaged, untracked, conflicted)),
            remote_url=remote_url,
            submodules_detected=(project / ".gitmodules").is_file(),
        )

    async def _remote_url(self, identity: ExecutableIdentity, project: Path) -> str | None:
        result = await self._run(
            identity,
            ("--no-optional-locks", *_SAFE_CONFIG, "remote", "get-url", "origin"),
            cwd=project,
            stdout_limit=4096,
            stderr_limit=4096,
        )
        if result.exit_code != 0:
            return None
        return redact_remote_url(result.stdout.decode("utf-8", errors="replace")[:4096])

    async def _assert_safe_repository_config(
        self, identity: ExecutableIdentity, project: Path
    ) -> None:
        result = await self._run(
            identity,
            ("--no-optional-locks", "config", "--local", "--null", "--list"),
            cwd=project,
            stdout_limit=128 * 1024,
            stderr_limit=4096,
        )
        if result.exit_code not in {0, 1}:
            raise RuntimeOperationError("GIT_CONFIG_UNSAFE", "Repository configuration is unsafe")
        for record in result.stdout.decode("utf-8", errors="replace").split("\x00"):
            key = record.partition("\n")[0].casefold()
            if any(key == item or key.startswith(item) for item in _DANGEROUS_CONFIG):
                raise RuntimeOperationError(
                    "GIT_CONFIG_UNSAFE",
                    "Repository configuration contains an unsafe executable setting",
                    category="forbidden",
                )

    def _require_repository(self, project: Path) -> ExecutableIdentity:
        identity = self._require_executable()
        if not self._repository_owned(project):
            raise RuntimeOperationError(
                "GIT_NOT_REPOSITORY", "Project is not a Git repository", category="conflict"
            )
        return identity

    @staticmethod
    def _repository_owned(project: Path) -> bool:
        dot_git = project / ".git"
        try:
            return (
                project.is_dir()
                and not project.is_symlink()
                and project.stat().st_uid == os.geteuid()
                and dot_git.is_dir()
                and not dot_git.is_symlink()
                and dot_git.stat().st_uid == os.geteuid()
            )
        except OSError:
            return False

    def _require_executable(self) -> ExecutableIdentity:
        identity = self.executable()
        if identity is None:
            raise RuntimeOperationError(
                "GIT_NOT_INSTALLED", "Git is unavailable", category="unavailable"
            )
        return identity

    async def _run(
        self,
        identity: ExecutableIdentity,
        arguments: tuple[str, ...],
        *,
        cwd: Path,
        timeout: float = 10,
        stdout_limit: int = 32 * 1024,
        stderr_limit: int = 16 * 1024,
    ) -> ProcessResult:
        return await self._runner.run(
            identity,
            arguments,
            environment=self._environment,
            cwd=cwd,
            timeout_seconds=timeout,
            stdout_limit=stdout_limit,
            stderr_limit=stderr_limit,
            error_prefix="GIT",
        )

    @staticmethod
    def _text(result: ProcessResult) -> str:
        return (result.stdout + b"\n" + result.stderr).decode("utf-8", errors="replace")

    @classmethod
    def _raise_network_failure(cls, result: ProcessResult, code: str, message: str) -> None:
        lowered = cls._text(result).casefold()
        if any(
            hint in lowered
            for hint in (
                "authentication failed",
                "could not read username",
                "permission denied (publickey)",
                "terminal prompts disabled",
            )
        ):
            raise RuntimeOperationError(
                "GIT_AUTH_REQUIRED", "Git authentication is required", category="unauthenticated"
            )
        raise RuntimeOperationError(code, message)
