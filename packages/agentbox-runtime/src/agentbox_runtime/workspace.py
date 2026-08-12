"""Controlled Project Workspace creation, clone staging, and typed Git operations."""

from __future__ import annotations

import contextlib
import ctypes
import errno
import hashlib
import os
import shutil
import stat
import unicodedata
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
_RENAME_NOREPLACE = 1


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
        self._projects.resolved_root(required=True)
        return tuple(
            ProjectWorkspace(project.project_id, project.display_name)
            for project in self._projects.list_projects()
        )

    async def create(self, project_key: str, operation_id: str) -> GitActionResult:
        key = validate_project_id(project_key)
        operation_id = validate_operation_id(operation_id)
        root, operation_dir, workspace = self._staging(operation_id)
        final = root / key
        try:
            self._assert_final_absent(final)
            workspace.mkdir(mode=0o750)
            self._write_marker(
                workspace / _PROJECT_MARKER, self._project_marker_value("empty", operation_id)
            )
            self._activate_noreplace(operation_id, operation_dir, workspace, root, final)
            return GitActionResult("created")
        except Exception:
            if self._project_marker_kind(final / _PROJECT_MARKER, operation_id) is None:
                self._cleanup_operation(operation_dir, operation_id)
            raise

    async def clone(
        self, project_key: str, operation_id: str, repository_url: str
    ) -> GitActionResult:
        key = validate_project_id(project_key)
        operation_id = validate_operation_id(operation_id)
        root, operation_dir, workspace = self._staging(operation_id)
        final = root / key
        try:
            self._assert_final_absent(final)
            await self._git.clone(repository_url, cwd=operation_dir, destination=workspace)
            if not (workspace / ".git").is_dir() or (workspace / ".git").is_symlink():
                raise RuntimeOperationError("GIT_CLONE_FAILED", "Cloned repository is invalid")
            self._write_marker(
                workspace / _PROJECT_MARKER, self._project_marker_value("clone", operation_id)
            )
            self._activate_noreplace(operation_id, operation_dir, workspace, root, final)
            status = await self._git.status(final)
            return GitActionResult("cloned", status.branch)
        except Exception:
            if self._project_marker_kind(final / _PROJECT_MARKER, operation_id) is None:
                self._cleanup_operation(operation_dir, operation_id)
            raise

    def finalize(self, project_key: str, operation_id: str) -> GitActionResult:
        project = self._projects.resolve(validate_project_id(project_key))
        operation_id = validate_operation_id(operation_id)
        marker = project.path / _PROJECT_MARKER
        if self._project_marker_kind(marker, operation_id) is None:
            raise RuntimeOperationError(
                "PROJECT_FINALIZE_INVALID",
                "Project finalization marker is invalid",
                category="conflict",
            )
        marker.unlink()
        self._remove_operation_parent(operation_id)
        return GitActionResult("finalized")

    def rollback(self, project_key: str, operation_id: str) -> GitActionResult:
        key = validate_project_id(project_key)
        operation_id = validate_operation_id(operation_id)
        root = self._projects.resolved_root(required=True)
        assert root is not None
        operation_dir = self._operation_dir(root, operation_id)
        candidate = root / key
        if not candidate.exists() and not candidate.is_symlink():
            if not self._cleanup_operation(operation_dir, operation_id):
                raise RuntimeOperationError(
                    "PROJECT_ROLLBACK_INVALID",
                    "Project rollback staging identity is invalid",
                    category="forbidden",
                )
            return GitActionResult("rolled_back")
        if not self._marker_matches(operation_dir / _OPERATION_MARKER, operation_id):
            raise RuntimeOperationError(
                "PROJECT_ROLLBACK_INVALID",
                "Project rollback staging identity is invalid",
                category="forbidden",
            )
        project = self._projects.resolve(key)
        marker = project.path / _PROJECT_MARKER
        kind = self._project_marker_kind(marker, operation_id)
        if kind is None:
            raise RuntimeOperationError(
                "PROJECT_ROLLBACK_INVALID",
                "Project rollback marker is invalid",
                category="forbidden",
            )
        if kind == "empty":
            try:
                entries = tuple(project.path.iterdir())
            except OSError as exc:
                raise RuntimeOperationError(
                    "PROJECT_CLEANUP_UNSAFE", "Project cleanup requires manual attention"
                ) from exc
            if entries != (marker,):
                raise RuntimeOperationError(
                    "PROJECT_CLEANUP_UNSAFE",
                    "Non-empty Project rollback requires manual attention",
                    category="conflict",
                )
            marker_value = self._project_marker_value(kind, operation_id)
            marker.unlink()
            try:
                project.path.rmdir()
            except OSError as exc:
                with contextlib.suppress(OSError):
                    self._write_marker(marker, marker_value)
                raise RuntimeOperationError(
                    "PROJECT_CLEANUP_UNSAFE", "Project cleanup requires manual attention"
                ) from exc
        else:
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
        if not temporary_root.exists() and not temporary_root.is_symlink():
            with contextlib.suppress(FileExistsError):
                temporary_root.mkdir(mode=0o700)
        self._assert_owned_directory(temporary_root, code="PROJECT_TEMP_ROOT_INVALID")
        operation_dir = self._operation_dir(root, operation_id)
        try:
            operation_dir.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise RuntimeOperationError(
                "PROJECT_OPERATION_CONFLICT",
                "Project operation staging already exists and requires review",
                category="conflict",
            ) from exc
        self._write_marker(operation_dir / _OPERATION_MARKER, operation_id)
        return root, operation_dir, operation_dir / "workspace"

    def _activate_noreplace(
        self,
        operation_id: str,
        operation_dir: Path,
        workspace: Path,
        root: Path,
        final: Path,
    ) -> None:
        if not self._marker_matches(operation_dir / _OPERATION_MARKER, operation_id):
            raise RuntimeOperationError(
                "PROJECT_OPERATION_INVALID",
                "Project operation identity changed",
                category="forbidden",
            )
        self._assert_owned_directory(operation_dir, code="PROJECT_OPERATION_INVALID")
        self._assert_owned_directory(workspace, code="PROJECT_PATH_INVALID", allow_group_read=True)
        self._rename_noreplace(operation_dir, workspace.name, root, final.name)

    @staticmethod
    def _rename_noreplace(
        source_directory: Path,
        source_name: str,
        destination_directory: Path,
        destination_name: str,
    ) -> None:
        """Atomically activate one child without ever replacing a destination."""
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
        source_descriptor: int | None = None
        destination_descriptor: int | None = None
        workspace_descriptor: int | None = None
        try:
            source_descriptor = os.open(source_directory, directory_flags)
            destination_descriptor = os.open(destination_directory, directory_flags)
            workspace_descriptor = os.open(source_name, directory_flags, dir_fd=source_descriptor)
            source_details = os.fstat(source_descriptor)
            destination_details = os.fstat(destination_descriptor)
            workspace_details = os.fstat(workspace_descriptor)
            if (
                not stat.S_ISDIR(source_details.st_mode)
                or source_details.st_uid != os.geteuid()
                or source_details.st_mode & 0o077
                or not stat.S_ISDIR(destination_details.st_mode)
                or destination_details.st_uid != os.geteuid()
                or destination_details.st_mode & 0o022
                or not stat.S_ISDIR(workspace_details.st_mode)
                or workspace_details.st_uid != os.geteuid()
                or workspace_details.st_mode & 0o022
            ):
                raise RuntimeOperationError(
                    "PROJECT_ACTIVATION_FAILED",
                    "Project activation directories are unsafe",
                    category="forbidden",
                )
            os.fsync(workspace_descriptor)
            live_workspace_details = os.stat(
                source_name, dir_fd=source_descriptor, follow_symlinks=False
            )
            if (live_workspace_details.st_dev, live_workspace_details.st_ino) != (
                workspace_details.st_dev,
                workspace_details.st_ino,
            ):
                raise RuntimeOperationError(
                    "PROJECT_ACTIVATION_FAILED",
                    "Project workspace identity changed during activation",
                    category="conflict",
                )
            renameat2 = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
            if renameat2 is None:
                raise RuntimeOperationError(
                    "PROJECT_ATOMIC_ACTIVATION_UNAVAILABLE",
                    "Atomic no-replace Project activation is unavailable",
                    category="unavailable",
                )
            renameat2.argtypes = (
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            )
            renameat2.restype = ctypes.c_int
            result = renameat2(
                source_descriptor,
                os.fsencode(source_name),
                destination_descriptor,
                os.fsencode(destination_name),
                _RENAME_NOREPLACE,
            )
            if result != 0:
                error_number = ctypes.get_errno()
                if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
                    raise RuntimeOperationError(
                        "PROJECT_PATH_COLLISION",
                        "Project workspace already exists",
                        category="conflict",
                    )
                if error_number in {errno.EINVAL, errno.ENOSYS, errno.ENOTSUP}:
                    raise RuntimeOperationError(
                        "PROJECT_ATOMIC_ACTIVATION_UNAVAILABLE",
                        "Atomic no-replace Project activation is unavailable",
                        category="unavailable",
                    )
                raise RuntimeOperationError(
                    "PROJECT_ACTIVATION_FAILED",
                    "Project workspace activation failed",
                    category="conflict",
                )
            try:
                os.fsync(destination_descriptor)
            except OSError as exc:
                raise RuntimeOperationError(
                    "PROJECT_ACTIVATION_DURABILITY_UNKNOWN",
                    "Project activation durability requires review",
                    category="conflict",
                ) from exc
        except OSError as exc:
            raise RuntimeOperationError(
                "PROJECT_ACTIVATION_FAILED",
                "Project workspace activation failed",
                category="conflict",
            ) from exc
        finally:
            if workspace_descriptor is not None:
                os.close(workspace_descriptor)
            if destination_descriptor is not None:
                os.close(destination_descriptor)
            if source_descriptor is not None:
                os.close(source_descriptor)

    @staticmethod
    def _assert_final_absent(final: Path) -> None:
        collision_key = unicodedata.normalize("NFC", final.name).casefold()
        try:
            collision = any(
                unicodedata.normalize("NFC", entry.name).casefold() == collision_key
                for entry in final.parent.iterdir()
            )
        except OSError as exc:
            raise RuntimeOperationError(
                "PROJECT_PATH_INVALID",
                "Project root could not be inspected",
                category="unavailable",
            ) from exc
        if collision:
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
    def _project_marker_value(kind: str, operation_id: str) -> str:
        if kind not in {"empty", "clone"}:
            raise ValueError("invalid Project marker kind")
        return f"{kind}:{operation_id}"

    @classmethod
    def _project_marker_kind(cls, path: Path, operation_id: str) -> str | None:
        for kind in ("empty", "clone"):
            if cls._marker_matches(path, cls._project_marker_value(kind, operation_id)):
                return kind
        return None

    @staticmethod
    def _marker_matches(path: Path, expected: str) -> bool:
        try:
            details = path.lstat()
            if not stat.S_ISREG(details.st_mode) or details.st_uid != os.geteuid():
                return False
            return path.read_text(encoding="ascii") == expected
        except (OSError, UnicodeError):
            return False

    def _cleanup_operation(self, operation_dir: Path, operation_id: str) -> bool:
        if not operation_dir.exists() and not operation_dir.is_symlink():
            return True
        if not self._marker_matches(operation_dir / _OPERATION_MARKER, operation_id):
            return False
        self._safe_tree(operation_dir)
        shutil.rmtree(operation_dir)
        return True

    def _remove_operation_parent(self, operation_id: str) -> None:
        root = self._projects.resolved_root(required=True)
        assert root is not None
        operation_dir = self._operation_dir(root, operation_id)
        if not self._cleanup_operation(operation_dir, operation_id):
            raise RuntimeOperationError(
                "PROJECT_OPERATION_INVALID",
                "Project operation cleanup identity is invalid",
                category="forbidden",
            )

    @staticmethod
    def _operation_dir(root: Path, operation_id: str) -> Path:
        name = f"op-{hashlib.sha256(operation_id.encode()).hexdigest()[:20]}"
        return root / ".agentbox-tmp" / name

    @staticmethod
    def _assert_owned_directory(path: Path, *, code: str, allow_group_read: bool = False) -> None:
        try:
            details = path.lstat()
        except OSError as exc:
            raise RuntimeOperationError(code, "Project directory is invalid") from exc
        forbidden_mode = 0o022 if allow_group_read else 0o077
        if (
            not stat.S_ISDIR(details.st_mode)
            or stat.S_ISLNK(details.st_mode)
            or details.st_uid != os.geteuid()
            or details.st_mode & forbidden_mode
        ):
            raise RuntimeOperationError(code, "Project directory is invalid", category="forbidden")

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
