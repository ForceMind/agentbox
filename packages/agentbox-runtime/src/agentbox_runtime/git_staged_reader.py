"""Runtime-internal bounded staged Git patch observation.

No RPC, API or browser route imports this module. A future encrypted content
action must separately bind formal Project/session/selector authority before
it may invoke this reader or release its plaintext result.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import unicodedata
from dataclasses import dataclass

from agentbox_runtime.git import _SAFE_CONFIG, GitAdapter, _unsafe_config_key
from agentbox_runtime.git_content_root import GitContentRoot
from agentbox_runtime.git_staged_selection import (
    StagedSelection,
    select_staged_change,
    validate_patch_path,
)
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.process import ExecutableIdentity, ProcessResult
from agentbox_runtime.project import ProjectRegistry

_MAX_PATCH_BYTES = 256 * 1024
_MAX_PATCH_LINES = 4096
_MAX_STATUS_BYTES = 1024 * 1024
_MAX_CONFIG_BYTES = 128 * 1024
_GIT_GLOBAL = (
    "--no-optional-locks",
    "--no-replace-objects",
    "--literal-pathspecs",
    "--no-pager",
)
_STATUS = (
    "status",
    "--porcelain=v2",
    "-z",
    "--untracked-files=all",
    "--renames",
)
_DIFF = (
    "diff",
    "--cached",
    "--patch",
    "--no-ext-diff",
    "--no-textconv",
    "--no-color",
    "--no-renames",
    "--full-index",
    "--unified=3",
    "--src-prefix=a/",
    "--dst-prefix=b/",
)
_INDEX_HEADER = re.compile(
    r"index ([0-9a-f]{40}|[0-9a-f]{64})\.\.([0-9a-f]{40}|[0-9a-f]{64})(?: [0-7]{6})?\Z"
)


def _error(code: str, *, category: str = "unavailable") -> RuntimeOperationError:
    return RuntimeOperationError(code, "Staged patch could not be read safely", category=category)


@dataclass(frozen=True)
class StagedPatchObservation:
    selection: StagedSelection
    patch: str
    sha256: str
    byte_count: int
    line_count: int


class GitStagedPatchReader:
    """Read one current index change under the fixed Runtime Project root."""

    def __init__(self, projects: ProjectRegistry, git: GitAdapter) -> None:
        if type(projects) is not ProjectRegistry or type(git) is not GitAdapter:
            raise TypeError("fixed Project registry and Git adapter are required")
        self._projects = projects
        self._git = git

    async def read(self, relative_key: str, path: str) -> StagedPatchObservation:
        """Return only a complete stable UTF-8 patch for an eligible staged row.

        ``relative_key`` is a registered Runtime Project key, never a browser
        path. The caller remains responsible for formal Project/session and
        selector authority. No partial patch is returned on any failure.
        """

        validate_patch_path(path)
        try:
            project = self._projects.resolve(relative_key)
            resolved_root = self._projects.resolved_root(required=True)
        except RuntimeOperationError as exc:
            raise _error("PATCH_UNAVAILABLE_REPOSITORY", category="forbidden") from exc
        assert resolved_root is not None
        try:
            executable = self._git._require_executable()
        except RuntimeOperationError as exc:
            raise _error("PATCH_UNAVAILABLE_GIT") from exc
        try:
            root = GitContentRoot(
                root_path=resolved_root,
                relative_key=project.project_id,
                expected_uid=os.geteuid(),
                expected_gid=os.getegid(),
            )
        except RuntimeOperationError as exc:
            raise _error("PATCH_UNAVAILABLE_REPOSITORY", category="forbidden") from exc
        try:
            await self._safe_config(executable, root)
            before = await self._status(executable, root)
            selected = select_staged_change(before, path)
            first = await self._patch(executable, root, selected)
            self._revalidate(root)
            middle = await self._status(executable, root)
            if middle != before or select_staged_change(middle, path) != selected:
                raise _error("PATCH_STALE", category="conflict")
            second = await self._patch(executable, root, selected)
            self._revalidate(root)
            after = await self._status(executable, root)
            if after != before or second != first:
                raise _error("PATCH_STALE", category="conflict")
            if select_staged_change(after, path) != selected:
                raise _error("PATCH_STALE", category="conflict")
            self._revalidate(root)
            return StagedPatchObservation(
                selection=selected,
                patch=first,
                sha256=hashlib.sha256(first.encode("utf-8")).hexdigest(),
                byte_count=len(first.encode("utf-8")),
                line_count=len(first.splitlines()),
            )
        finally:
            root.close()

    @staticmethod
    def _revalidate(root: GitContentRoot) -> None:
        try:
            root.revalidate()
        except RuntimeOperationError as exc:
            raise _error("PATCH_STALE", category="conflict") from exc

    async def _run(
        self,
        executable: ExecutableIdentity,
        root: GitContentRoot,
        arguments: tuple[str, ...],
        *,
        stdout_limit: int,
        limit_code: str = "PATCH_TOO_LARGE",
    ) -> ProcessResult:
        self._revalidate(root)
        try:
            # The descriptor remains owned by GitContentRoot across the await;
            # the process runner duplicates and checks it before/after the child.
            result = await self._git._runner.run_with_cwd_fd(
                executable,
                arguments,
                environment=self._git._environment,
                cwd=root.project_path,
                cwd_directory_fd=root._fds["project"],
                timeout_seconds=5,
                stdout_limit=stdout_limit,
                stderr_limit=4096,
                sensitive_output=True,
                error_prefix="GIT",
            )
        except RuntimeOperationError as exc:
            if exc.code == "GIT_OUTPUT_LIMIT_EXCEEDED":
                raise _error(limit_code) from exc
            if exc.code == "GIT_COMMAND_TIMEOUT":
                raise _error("PATCH_TIMEOUT", category="timeout") from exc
            if exc.code == "GIT_WORKING_DIRECTORY_CHANGED":
                raise _error("PATCH_STALE", category="conflict") from exc
            raise _error("PATCH_UNAVAILABLE_GIT") from exc
        except asyncio.CancelledError:
            # The runner terminates/reaps the exact process before propagating.
            raise
        self._revalidate(root)
        if result.exit_code != 0:
            raise _error("PATCH_UNAVAILABLE_GIT")
        return result

    async def _safe_config(self, executable: ExecutableIdentity, root: GitContentRoot) -> None:
        result = await self._run(
            executable,
            root,
            (*_GIT_GLOBAL, "config", "--no-includes", "--null", "--list"),
            stdout_limit=_MAX_CONFIG_BYTES + 1,
            limit_code="PATCH_UNAVAILABLE_CONFIG",
        )
        if len(result.stdout) > _MAX_CONFIG_BYTES:
            raise _error("PATCH_UNAVAILABLE_CONFIG")
        try:
            records = result.stdout.decode("utf-8", errors="strict").split("\0")
        except UnicodeDecodeError as exc:
            raise _error("PATCH_UNAVAILABLE_CONFIG") from exc
        for record in records:
            if not record:
                continue
            key, separator, value = record.partition("\n")
            lowered = key.casefold()
            if (
                not separator
                or not key
                or _unsafe_config_key(key)
                or (lowered.startswith("extensions.") and lowered != "extensions.objectformat")
                or (lowered == "core.bare" and value.casefold() == "true")
                or lowered.endswith(".promisor")
                or lowered.endswith(".partialclonefilter")
            ):
                raise _error("PATCH_UNAVAILABLE_CONFIG", category="forbidden")

    async def _status(self, executable: ExecutableIdentity, root: GitContentRoot) -> bytes:
        result = await self._run(
            executable,
            root,
            (*_GIT_GLOBAL, *_SAFE_CONFIG, *_STATUS),
            stdout_limit=_MAX_STATUS_BYTES + 1,
            limit_code="PATCH_UNAVAILABLE_STATUS",
        )
        if len(result.stdout) > _MAX_STATUS_BYTES:
            raise _error("PATCH_UNAVAILABLE_STATUS")
        return result.stdout

    async def _patch(
        self, executable: ExecutableIdentity, root: GitContentRoot, selected: StagedSelection
    ) -> str:
        result = await self._run(
            executable,
            root,
            (*_GIT_GLOBAL, *_SAFE_CONFIG, *_DIFF, "--", selected.path),
            stdout_limit=_MAX_PATCH_BYTES + 1,
        )
        raw = result.stdout
        if len(raw) > _MAX_PATCH_BYTES:
            raise _error("PATCH_TOO_LARGE")
        if not raw:
            raise _error("PATCH_STALE", category="conflict")
        if b"\0" in raw or b"\nBinary files " in raw or b"\nGIT binary patch\n" in raw:
            raise _error("PATCH_UNAVAILABLE_BINARY", category="unsupported")
        try:
            patch = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise _error("PATCH_UNAVAILABLE_ENCODING", category="unsupported") from exc
        if any(
            unicodedata.category(character).startswith("C") and character not in "\t\n\r"
            for character in patch
        ):
            raise _error("PATCH_UNAVAILABLE_ENCODING", category="unsupported")
        headers = [line for line in patch.splitlines() if line.startswith("diff --git ")]
        indexes = [line for line in patch.splitlines() if line.startswith("index ")]
        if len(headers) != 1 or len(indexes) != 1:
            raise _error("PATCH_STALE", category="conflict")
        match = _INDEX_HEADER.fullmatch(indexes[0])
        if (
            match is None
            or match.group(1) != selected.head_oid
            or match.group(2) != selected.index_oid
        ):
            raise _error("PATCH_STALE", category="conflict")
        line_count = len(patch.splitlines())
        if line_count > _MAX_PATCH_LINES:
            raise _error("PATCH_TOO_LARGE")
        return patch


__all__ = ["GitStagedPatchReader", "StagedPatchObservation"]
