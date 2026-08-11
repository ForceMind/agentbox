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
    "-c",
    "sequence.editor=false",
    "-c",
    "merge.autoStash=false",
    "-c",
    "rebase.autoStash=false",
    "-c",
    "pull.rebase=false",
    "-c",
    "pull.ff=only",
    "-c",
    "merge.ff=only",
    "-c",
    "fetch.recurseSubmodules=false",
    "-c",
    "submodule.recurse=false",
    "-c",
    "fetch.prune=false",
    "-c",
    "fetch.pruneTags=false",
    "-c",
    "fetch.parallel=1",
    "-c",
    "submodule.fetchJobs=1",
    "-c",
    "gc.auto=0",
)
_DANGEROUS_CONFIG = (
    "alias.",
    "credential.",
    "filter.",
    "http.",
    "protocol.",
    "pager.",
    "pull.",
    "push.",
    "url.",
    "core.askpass",
    "core.alternaterefscommand",
    "core.attributesfile",
    "core.excludesfile",
    "core.fsmonitor",
    "core.gitproxy",
    "core.hookspath",
    "core.sshcommand",
    "core.worktree",
    "core.pager",
    "core.editor",
    "diff.external",
    "interactive.difffilter",
    "include.path",
    "includeif.",
    "sequence.editor",
)


def _unsafe_config_key(key: str) -> bool:
    lowered = key.casefold()
    if any(lowered == item or lowered.startswith(item) for item in _DANGEROUS_CONFIG):
        return True
    if lowered.startswith("remote.") and lowered.endswith(
        (
            ".mirror",
            ".proxy",
            ".prune",
            ".prunetags",
            ".push",
            ".pushurl",
            ".receivepack",
            ".skipdefaultupdate",
            ".tagopt",
            ".uploadpack",
            ".vcs",
        )
    ):
        return True
    if lowered.startswith("branch.") and lowered.endswith((".mergeoptions", ".pushremote")):
        return True
    if lowered.startswith(("difftool.", "mergetool.")):
        return True
    return lowered.startswith(("diff.", "merge.")) and lowered.endswith(
        (".command", ".driver", ".textconv")
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
        if (
            ssh.group("owner").startswith("-")
            or ssh.group("repo").startswith("-")
            or ssh.group("owner") in {".", ".."}
            or ssh.group("repo").removesuffix(".git") in {".", ".."}
        ):
            raise RuntimeOperationError(
                "GIT_REPOSITORY_URL_INVALID", "Repository URL is invalid", category="validation"
            )
        return value
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
        username = parsed.username
        password = parsed.password
    except ValueError as exc:
        raise RuntimeOperationError(
            "GIT_REPOSITORY_URL_INVALID", "Repository URL is invalid", category="validation"
        ) from exc
    if (
        parsed.scheme != "https"
        or hostname != "github.com"
        or port is not None
        or username is not None
        or password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeOperationError(
            "GIT_REPOSITORY_URL_INVALID", "Repository URL is invalid", category="validation"
        )
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        raise RuntimeOperationError(
            "GIT_REPOSITORY_URL_INVALID", "Repository URL is invalid", category="validation"
        )
    owner, repository = parts
    repository_name = repository.removesuffix(".git")
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", owner)
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", repository_name)
        or owner.startswith("-")
        or repository_name.startswith("-")
        or owner in {".", ".."}
        or repository_name in {".", ".."}
        or parsed.path != f"/{owner}/{repository}"
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
    if len(value) > 4096:
        return None
    value = value.strip()
    if any(unicodedata.category(character).startswith("C") for character in value):
        return None
    ssh = _GITHUB_SSH.fullmatch(value)
    if ssh:
        repository = ssh.group("repo").removesuffix(".git")
        return f"git@github.com:{ssh.group('owner')}/{repository}.git"
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme not in {"https", "ssh"} or not hostname:
        return None
    host = hostname
    if port:
        host = f"{host}:{port}"
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
                "GIT_EDITOR": "/bin/false",
                "GIT_ASKPASS": "/bin/false",
                "GIT_PAGER": "cat",
                "GIT_SEQUENCE_EDITOR": "/bin/false",
                "SSH_ASKPASS": "/bin/false",
                "GIT_LFS_SKIP_SMUDGE": "1",
                "GIT_ALLOW_PROTOCOL": "https:ssh",
                "PAGER": "cat",
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
        repository_state = self._repository_state(project)
        if repository_state == "missing":
            return GitStatus(is_repository=False)
        if repository_state == "unsafe":
            raise RuntimeOperationError(
                "GIT_OWNERSHIP_UNSAFE",
                "Repository ownership or structure is unsafe",
                category="forbidden",
            )
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
        status = await self.status(project)
        if status.detached_head:
            raise RuntimeOperationError(
                "GIT_DETACHED_HEAD",
                "Pull is unavailable in detached HEAD state",
                category="conflict",
            )
        branch, remote_branch = await self._upstream_target(identity, project, status)
        result = await self._run(
            identity,
            (
                *_SAFE_CONFIG,
                "pull",
                "--ff-only",
                "--no-rebase",
                "--no-tags",
                "--no-recurse-submodules",
                "--no-verify",
                "origin",
                f"refs/heads/{remote_branch}",
            ),
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
        return GitActionResult("pulled", branch)

    async def push(self, project: Path) -> GitActionResult:
        identity = self._require_repository(project)
        status = await self.status(project)
        if status.detached_head:
            raise RuntimeOperationError(
                "GIT_DETACHED_HEAD",
                "Push is unavailable in detached HEAD state",
                category="conflict",
            )
        branch, remote_branch = await self._upstream_target(identity, project, status)
        refspec = f"refs/heads/{branch}:refs/heads/{remote_branch}"
        result = await self._run(
            identity,
            (*_SAFE_CONFIG, "push", "--no-verify", "--porcelain", "origin", refspec),
            cwd=project,
            timeout=300,
            stdout_limit=64 * 1024,
            stderr_limit=64 * 1024,
        )
        if result.exit_code != 0:
            self._raise_network_failure(result, "GIT_PUSH_FAILED", "Push failed")
        return GitActionResult("pushed", branch)

    async def _upstream_target(
        self, identity: ExecutableIdentity, project: Path, status: GitStatus
    ) -> tuple[str, str]:
        """Resolve one existing origin upstream into explicit, non-forcing refs."""
        if status.branch is None or status.upstream is None:
            raise RuntimeOperationError(
                "GIT_UPSTREAM_MISSING", "Current branch has no upstream", category="conflict"
            )
        try:
            branch = validate_branch_name(status.branch)
        except RuntimeOperationError as exc:
            raise RuntimeOperationError(
                "GIT_UPSTREAM_UNSAFE",
                "Current branch upstream is invalid",
                category="forbidden",
            ) from exc
        remote = await self._local_config_value(identity, project, f"branch.{branch}.remote")
        merge_ref = await self._local_config_value(identity, project, f"branch.{branch}.merge")
        if remote is None or merge_ref is None:
            raise RuntimeOperationError(
                "GIT_UPSTREAM_MISSING", "Current branch has no upstream", category="conflict"
            )
        prefix = "refs/heads/"
        if remote != "origin" or not merge_ref.startswith(prefix):
            raise RuntimeOperationError(
                "GIT_UPSTREAM_UNSAFE",
                "Current branch upstream is not an approved origin branch",
                category="forbidden",
            )
        try:
            remote_branch = validate_branch_name(merge_ref.removeprefix(prefix))
        except RuntimeOperationError as exc:
            raise RuntimeOperationError(
                "GIT_UPSTREAM_UNSAFE",
                "Current branch upstream is invalid",
                category="forbidden",
            ) from exc
        if status.upstream != f"origin/{remote_branch}":
            raise RuntimeOperationError(
                "GIT_UPSTREAM_UNSAFE",
                "Current branch upstream is inconsistent",
                category="forbidden",
            )
        await self._assert_safe_origin(identity, project)
        return branch, remote_branch

    async def _local_config_value(
        self, identity: ExecutableIdentity, project: Path, key: str
    ) -> str | None:
        result = await self._run(
            identity,
            (
                "--no-optional-locks",
                "config",
                "--no-includes",
                "--get",
                key,
            ),
            cwd=project,
            stdout_limit=4096,
            stderr_limit=4096,
        )
        if result.exit_code == 1:
            return None
        if result.exit_code != 0:
            raise RuntimeOperationError("GIT_CONFIG_UNSAFE", "Repository configuration is unsafe")
        value = result.stdout.decode("utf-8", errors="replace").rstrip("\n")
        if not value or "\n" in value or "\x00" in value or len(value) > 512:
            raise RuntimeOperationError("GIT_CONFIG_UNSAFE", "Repository configuration is unsafe")
        return value

    async def _assert_safe_origin(self, identity: ExecutableIdentity, project: Path) -> None:
        result = await self._run(
            identity,
            (
                "--no-optional-locks",
                "config",
                "--no-includes",
                "--null",
                "--get-all",
                "remote.origin.url",
            ),
            cwd=project,
            stdout_limit=4096,
            stderr_limit=4096,
        )
        if result.exit_code != 0:
            raise RuntimeOperationError(
                "GIT_REMOTE_UNSAFE", "Origin remote is unavailable", category="forbidden"
            )
        urls = [
            value
            for value in result.stdout.decode("utf-8", errors="replace").split("\x00")
            if value
        ]
        if len(urls) != 1:
            raise RuntimeOperationError(
                "GIT_REMOTE_UNSAFE",
                "Origin remote is not uniquely configured",
                category="forbidden",
            )
        try:
            validate_git_repository_url(urls[0])
        except RuntimeOperationError as exc:
            raise RuntimeOperationError(
                "GIT_REMOTE_UNSAFE",
                "Origin remote is not an approved GitHub transport",
                category="forbidden",
            ) from exc

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
            (
                "--no-optional-locks",
                "config",
                "--no-includes",
                "--null",
                "--list",
            ),
            cwd=project,
            stdout_limit=128 * 1024,
            stderr_limit=4096,
        )
        if result.exit_code not in {0, 1}:
            raise RuntimeOperationError("GIT_CONFIG_UNSAFE", "Repository configuration is unsafe")
        for record in result.stdout.decode("utf-8", errors="replace").split("\x00"):
            key = record.partition("\n")[0].casefold()
            if _unsafe_config_key(key):
                raise RuntimeOperationError(
                    "GIT_CONFIG_UNSAFE",
                    "Repository configuration contains an unsafe executable setting",
                    category="forbidden",
                )

    def _require_repository(self, project: Path) -> ExecutableIdentity:
        identity = self._require_executable()
        repository_state = self._repository_state(project)
        if repository_state == "unsafe":
            raise RuntimeOperationError(
                "GIT_OWNERSHIP_UNSAFE",
                "Repository ownership or structure is unsafe",
                category="forbidden",
            )
        if repository_state == "missing":
            raise RuntimeOperationError(
                "GIT_NOT_REPOSITORY", "Project is not a Git repository", category="conflict"
            )
        return identity

    @staticmethod
    def _repository_state(project: Path) -> str:
        dot_git = project / ".git"
        try:
            if not project.exists():
                return "missing"
            if (
                not project.is_dir()
                or project.is_symlink()
                or project.stat().st_uid != os.geteuid()
            ):
                return "unsafe"
            if not dot_git.exists() and not dot_git.is_symlink():
                return "missing"
            if (
                not dot_git.is_dir()
                or dot_git.is_symlink()
                or dot_git.stat().st_uid != os.geteuid()
            ):
                return "unsafe"
            return "valid"
        except OSError:
            return "unsafe"

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
