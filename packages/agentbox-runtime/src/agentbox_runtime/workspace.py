"""Controlled Project Workspace creation, clone staging, and typed Git operations."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
from pathlib import Path

from agentbox_runtime.git import GitAdapter
from agentbox_runtime.github import GitHubAdapter
from agentbox_runtime.models import (
    GitActionResult,
    GitBranch,
    GitHubProjectStatus,
    GitHubPullRequestResult,
    GitHubStatus,
    GitInstallationStatus,
    GitStatus,
    ProjectWorkspace,
    RuntimeOperationError,
)
from agentbox_runtime.project import ProjectRegistry, validate_project_id

_OPERATION_MARKER = ".agentbox-operation"
_PROJECT_MARKER = ".agentbox-project"


def validate_operation_id(value: str) -> str:
    if (
        not value.startswith("job_")
        or len(value) != 36
        or any(character not in "0123456789abcdef" for character in value[4:])
    ):
        raise RuntimeOperationError(
            "PROJECT_OPERATION_INVALID", "Project operation is invalid", category="validation"
        )
    return value


class ProjectWorkspaceManager:
    def __init__(
        self,
        projects: ProjectRegistry,
        git: GitAdapter,
        github: GitHubAdapter,
    ) -> None:
        self._projects = projects
        self._git = git
        self._github = github

    def list_workspaces(self) -> tuple[ProjectWorkspace, ...]:
        return tuple(
            ProjectWorkspace(project.project_id, project.display_name)
            for project in self._projects.list_projects()
        )

    async def create(self, project_key: str, operation_id: str) -> GitActionResult:
        key = validate_project_id(project_key)
        operation_id = validate_operation_id(operation_id)
        root, operation_dir, workspace = self._staging(operation_id)
        final = root / key
        self._assert_final_absent(final)
        try:
            workspace.mkdir(mode=0o750)
            self._write_marker(workspace / _PROJECT_MARKER, operation_id)
            os.replace(workspace, final)
            return GitActionResult("created")
        except Exception:
            self._cleanup_operation(operation_dir, operation_id)
            raise

    async def clone(
        self, project_key: str, operation_id: str, repository_url: str
    ) -> GitActionResult:
        key = validate_project_id(project_key)
        operation_id = validate_operation_id(operation_id)
        root, operation_dir, workspace = self._staging(operation_id)
        final = root / key
        self._assert_final_absent(final)
        try:
            await self._git.clone(repository_url, cwd=operation_dir, destination=workspace)
            if not (workspace / ".git").is_dir() or (workspace / ".git").is_symlink():
                raise RuntimeOperationError("GIT_CLONE_FAILED", "Cloned repository is invalid")
            self._write_marker(workspace / _PROJECT_MARKER, operation_id)
            os.replace(workspace, final)
            status = await self._git.status(final)
            return GitActionResult("cloned", status.branch)
        except Exception:
            self._cleanup_operation(operation_dir, operation_id)
            raise

    def finalize(self, project_key: str, operation_id: str) -> GitActionResult:
        project = self._projects.resolve(validate_project_id(project_key))
        operation_id = validate_operation_id(operation_id)
        marker = project.path / _PROJECT_MARKER
        if not self._marker_matches(marker, operation_id):
            raise RuntimeOperationError(
                "PROJECT_FINALIZE_INVALID",
                "Project finalization marker is invalid",
                category="conflict",
            )
        marker.unlink()
        self._remove_operation_parent(operation_id)
        return GitActionResult("finalized")

    def rollback(self, project_key: str, operation_id: str) -> GitActionResult:
        project = self._projects.resolve(validate_project_id(project_key))
        operation_id = validate_operation_id(operation_id)
        marker = project.path / _PROJECT_MARKER
        if not self._marker_matches(marker, operation_id):
            raise RuntimeOperationError(
                "PROJECT_ROLLBACK_INVALID",
                "Project rollback marker is invalid",
                category="forbidden",
            )
        self._safe_tree(project.path)
        shutil.rmtree(project.path)
        self._remove_operation_parent(operation_id)
        return GitActionResult("rolled_back")

    async def git_status(self, project_key: str) -> GitStatus:
        return await self._git.status(self._projects.resolve(project_key).path)

    async def git_global_status(self) -> GitInstallationStatus:
        return await self._git.installation_status()

    async def branches(self, project_key: str) -> tuple[GitBranch, ...]:
        return await self._git.branches(self._projects.resolve(project_key).path)

    async def create_branch(self, project_key: str, branch: str) -> GitActionResult:
        return await self._git.create_branch(self._projects.resolve(project_key).path, branch)

    async def switch_branch(self, project_key: str, branch: str) -> GitActionResult:
        return await self._git.switch_branch(self._projects.resolve(project_key).path, branch)

    async def pull(self, project_key: str) -> GitActionResult:
        return await self._git.pull(self._projects.resolve(project_key).path)

    async def push(self, project_key: str) -> GitActionResult:
        return await self._git.push(self._projects.resolve(project_key).path)

    async def github_status(self, project_key: str) -> GitHubProjectStatus:
        return await self._github.project_status(self._projects.resolve(project_key).path)

    async def github_global_status(self) -> GitHubStatus:
        return await self._github.status()

    async def create_draft_pr(
        self,
        project_key: str,
        *,
        title: str,
        body: str,
        base: str | None,
    ) -> GitHubPullRequestResult:
        return await self._github.create_draft_pull_request(
            self._projects.resolve(project_key).path,
            title=title,
            body=body,
            base=base,
        )

    def _staging(self, operation_id: str) -> tuple[Path, Path, Path]:
        root = self._projects.resolved_root(required=True)
        assert root is not None
        temporary_root = root / ".agentbox-tmp"
        if temporary_root.exists():
            details = temporary_root.lstat()
            if (
                not stat.S_ISDIR(details.st_mode)
                or stat.S_ISLNK(details.st_mode)
                or details.st_uid != os.geteuid()
            ):
                raise RuntimeOperationError(
                    "PROJECT_TEMP_ROOT_INVALID",
                    "Project temporary root is invalid",
                    category="forbidden",
                )
        else:
            temporary_root.mkdir(mode=0o700)
        name = f"op-{hashlib.sha256(operation_id.encode()).hexdigest()[:20]}"
        operation_dir = temporary_root / name
        operation_dir.mkdir(mode=0o700)
        self._write_marker(operation_dir / _OPERATION_MARKER, operation_id)
        return root, operation_dir, operation_dir / "workspace"

    @staticmethod
    def _assert_final_absent(final: Path) -> None:
        if final.exists() or final.is_symlink():
            raise RuntimeOperationError(
                "PROJECT_PATH_COLLISION",
                "Project workspace already exists",
                category="conflict",
            )

    @staticmethod
    def _write_marker(path: Path, value: str) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.write(descriptor, value.encode("ascii"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _marker_matches(path: Path, expected: str) -> bool:
        try:
            details = path.lstat()
            if not stat.S_ISREG(details.st_mode) or details.st_uid != os.geteuid():
                return False
            return path.read_text(encoding="ascii") == expected
        except (OSError, UnicodeError):
            return False

    def _cleanup_operation(self, operation_dir: Path, operation_id: str) -> None:
        if not operation_dir.exists() or not self._marker_matches(
            operation_dir / _OPERATION_MARKER, operation_id
        ):
            return
        self._safe_tree(operation_dir)
        shutil.rmtree(operation_dir)

    def _remove_operation_parent(self, operation_id: str) -> None:
        root = self._projects.resolved_root(required=True)
        assert root is not None
        name = f"op-{hashlib.sha256(operation_id.encode()).hexdigest()[:20]}"
        operation_dir = root / ".agentbox-tmp" / name
        if self._marker_matches(operation_dir / _OPERATION_MARKER, operation_id):
            self._safe_tree(operation_dir)
            shutil.rmtree(operation_dir)

    @staticmethod
    def _safe_tree(root: Path) -> None:
        details = root.lstat()
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise RuntimeOperationError(
                "PROJECT_CLEANUP_UNSAFE", "Project cleanup requires manual attention"
            )
        device = details.st_dev
        for current, directories, _files in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            current_details = current_path.lstat()
            if current_details.st_dev != device or os.path.ismount(current_path):
                raise RuntimeOperationError(
                    "PROJECT_CLEANUP_UNSAFE", "Project cleanup requires manual attention"
                )
            directories[:] = [
                name for name in directories if not (current_path / name).is_symlink()
            ]
