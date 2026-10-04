from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest
from agentbox_runtime.git import GitAdapter
from agentbox_runtime.git_content_root import GitContentRoot
from agentbox_runtime.git_staged_reader import GitStagedPatchReader
from agentbox_runtime.git_staged_snapshot import StagedGitSnapshot
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.process import ControlledProcessRunner, ExecutableIdentity, ProcessResult
from agentbox_runtime.project import ProjectRegistry

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="sealed staged inputs are Linux-only"
)


class LocalGitRunner:
    """Test-only Linux Git child: exercise the staged reader policy.

    Production uses ControlledProcessRunner.run_with_cwd_fd on Linux. This
    shim executes the same fixed argv, but is not descriptor-cwd evidence.
    """

    def __init__(
        self,
        after_first_diff: Callable[[], None] | None = None,
        *,
        before_first_status: Callable[[], None] | None = None,
        native: bool = False,
        change_second_diff: bool = False,
        change_index_oid: bool = False,
        block_on_diff: bool = False,
        fail_diff_code: str | None = None,
    ) -> None:
        self.native = native
        self.argv: list[tuple[str, ...]] = []
        self.after_first_diff = after_first_diff
        self.before_first_status = before_first_status
        self.change_second_diff = change_second_diff
        self.change_index_oid = change_index_oid
        self.diff_count = 0
        self.block_on_diff = block_on_diff
        self.fail_diff_code = fail_diff_code
        self.reached_diff = asyncio.Event()
        self.project_fd: int | None = None
        self._release = asyncio.Event()

    async def run_with_cwd_fd(
        self,
        executable: ExecutableIdentity,
        arguments: Sequence[str],
        *,
        environment: Mapping[str, str],
        cwd: Path,
        cwd_directory_fd: int,
        timeout_seconds: float,
        stdout_limit: int,
        stderr_limit: int,
        sensitive_output: bool = False,
        stdin_data: bytes | None = None,
        error_prefix: str = "GIT",
        staged_git_inputs: StagedGitSnapshot | None = None,
    ) -> ProcessResult:
        assert environment["GIT_ALLOW_PROTOCOL"] == ""
        assert environment["HOME"] == environment["XDG_CONFIG_HOME"] == "/dev/null"
        assert arguments[0] == "--git-dir=."
        assert os.fstat(cwd_directory_fd).st_ino == cwd.stat().st_ino
        argv = (str(executable.path), *arguments)
        self.argv.append(argv)
        if "--patch" in arguments and self.fail_diff_code is not None:
            raise RuntimeOperationError(self.fail_diff_code, "test-only child failure")
        if "--patch" in arguments and self.block_on_diff:
            self.project_fd = cwd_directory_fd
            self.reached_diff.set()
            await self._release.wait()
        if "--raw" in arguments and self.before_first_status is not None:
            mutation = self.before_first_status
            self.before_first_status = None
            mutation()
        if self.native:
            native_result = await ControlledProcessRunner().run_with_cwd_fd(
                executable,
                arguments,
                environment=environment,
                cwd=cwd,
                cwd_directory_fd=cwd_directory_fd,
                timeout_seconds=timeout_seconds,
                stdout_limit=stdout_limit,
                stderr_limit=stderr_limit,
                sensitive_output=sensitive_output,
                stdin_data=stdin_data,
                error_prefix=error_prefix,
                staged_git_inputs=staged_git_inputs,
            )
            stdout, stderr, exit_code = (
                native_result.stdout,
                native_result.stderr,
                native_result.exit_code,
            )
        else:
            finished = subprocess.run(
                argv,
                cwd=cwd,
                env=dict(environment),
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
                pass_fds=() if staged_git_inputs is None else staged_git_inputs.input_fds,
            )
            stdout, stderr, exit_code = finished.stdout, finished.stderr, finished.returncode
        if len(stdout) > stdout_limit or len(stderr) > stderr_limit:
            raise RuntimeOperationError("GIT_OUTPUT_LIMIT_EXCEEDED", "bounded test child")
        if "--patch" in arguments:
            self.diff_count += 1
            if self.after_first_diff is not None:
                mutation = self.after_first_diff
                self.after_first_diff = None
                mutation()
            if self.change_second_diff and self.diff_count == 2:
                stdout += b"+drift\n"
            if self.change_index_oid and self.diff_count == 1:
                stdout = b"".join(
                    b"index " + b"f" * 40 + line[46:] if line.startswith(b"index ") else line
                    for line in stdout.splitlines(keepends=True)
                )
        return ProcessResult(argv, exit_code, stdout, stderr)


def repository(tmp_path: Path) -> tuple[Path, Path]:
    git = shutil.which("git")
    if git is None:
        pytest.skip("Git is unavailable")
    root = tmp_path / "projects"
    project = root / "formal-project"
    project.mkdir(parents=True)
    subprocess.run([git, "init", "-q", str(project)], check=True, capture_output=True)
    (project / "modified.txt").write_text("original\n", encoding="utf-8")
    (project / "deleted.txt").write_text("deleted\n", encoding="utf-8")
    subprocess.run([git, "-C", str(project), "add", "modified.txt", "deleted.txt"], check=True)
    subprocess.run(
        [
            git,
            "-C",
            str(project),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "base",
        ],
        check=True,
    )
    return root, project


def stage(project: Path, *paths: str) -> None:
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "-C", str(project), "add", "--", *paths], check=True)


def reader(root: Path, runner: LocalGitRunner) -> GitStagedPatchReader:
    return GitStagedPatchReader(
        ProjectRegistry(root), GitAdapter(runner=cast(ControlledProcessRunner, runner))
    )


async def code(reader_: GitStagedPatchReader, path: str) -> str:
    with pytest.raises(RuntimeOperationError) as raised:
        await reader_.read("formal-project", path)
    return raised.value.code


@pytest.mark.anyio
async def test_reads_only_staged_regular_patch_with_fixed_git_argv(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    target = project / "modified.txt"
    target.write_text("staged\n", encoding="utf-8")
    stage(project, "modified.txt")
    target.write_text("unstaged-private\n", encoding="utf-8")
    runner = LocalGitRunner()
    observed = await reader(root, runner).read("formal-project", "modified.txt")
    assert observed.selection.kind == "modified"
    assert "+staged" in observed.patch
    assert "unstaged-private" not in observed.patch
    assert observed.byte_count == len(observed.patch.encode("utf-8"))
    assert len(observed.sha256) == 64
    assert len([args for args in runner.argv if "--patch" in args]) == 2
    for argv in runner.argv:
        assert "--no-optional-locks" in argv
        assert "--no-replace-objects" in argv
        assert "--literal-pathspecs" in argv
        if "--patch" in argv:
            assert argv[-2:] == ("--", "modified.txt")
            assert {"--cached", "--no-ext-diff", "--no-textconv", "--no-renames"} <= set(argv)


@pytest.mark.anyio
async def test_reads_staged_add_delete_and_option_like_name(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    (project / "-option.txt").write_text("new\n", encoding="utf-8")
    stage(project, "-option.txt")
    (project / "deleted.txt").unlink()
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "-C", str(project), "rm", "--", "deleted.txt"], check=True)
    active = reader(root, LocalGitRunner())
    added = await active.read("formal-project", "-option.txt")
    deleted = await active.read("formal-project", "deleted.txt")
    assert added.selection.kind == "added" and "+new" in added.patch
    assert deleted.selection.kind == "deleted" and "-deleted" in deleted.patch


@pytest.mark.anyio
async def test_rejects_binary_sensitive_and_oversize_without_partial_success(
    tmp_path: Path,
) -> None:
    root, project = repository(tmp_path)
    (project / "binary.dat").write_bytes(b"\0\1\2\3")
    (project / "large.txt").write_text("x" * (257 * 1024) + "\n", encoding="utf-8")
    (project / ".env.private").write_text("secret\n", encoding="utf-8")
    stage(project, "binary.dat", "large.txt", ".env.private")
    runner = LocalGitRunner()
    active = reader(root, runner)
    assert await code(active, "binary.dat") == "PATCH_UNAVAILABLE_BINARY"
    assert await code(active, "large.txt") == "PATCH_TOO_LARGE"
    count = len(runner.argv)
    assert await code(active, ".env.private") == "PATCH_UNAVAILABLE_SENSITIVE_PATH"
    assert len(runner.argv) == count


@pytest.mark.anyio
async def test_missing_registered_project_is_not_a_path_grant(tmp_path: Path) -> None:
    root, _project = repository(tmp_path)
    fake = LocalGitRunner()
    with pytest.raises(RuntimeOperationError) as raised:
        await reader(root, fake).read("missing-project", "modified.txt")
    assert raised.value.code == "PATCH_UNAVAILABLE_REPOSITORY"
    assert fake.argv == []


@pytest.mark.anyio
async def test_rejects_index_drift_and_external_diff_config(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    target = project / "modified.txt"
    target.write_text("staged\n", encoding="utf-8")
    stage(project, "modified.txt")

    def mutate_index() -> None:
        target.write_text("changed again\n", encoding="utf-8")
        stage(project, "modified.txt")

    assert await code(reader(root, LocalGitRunner(mutate_index)), "modified.txt") == "PATCH_STALE"
    git = shutil.which("git")
    assert git is not None
    marker = tmp_path / "helper-ran"
    subprocess.run(
        [git, "-C", str(project), "config", "diff.evil.command", f"touch {marker}"], check=True
    )
    assert await code(reader(root, LocalGitRunner()), "modified.txt") == "PATCH_UNAVAILABLE_CONFIG"
    assert not marker.exists()


@pytest.mark.anyio
async def test_rejects_partial_clone_config_without_attempting_lazy_fetch(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    (project / "modified.txt").write_text("staged\n", encoding="utf-8")
    stage(project, "modified.txt")
    git = shutil.which("git")
    assert git is not None
    subprocess.run(
        [git, "-C", str(project), "config", "extensions.partialClone", "origin"], check=True
    )
    active = reader(root, LocalGitRunner())
    assert await code(active, "modified.txt") == "PATCH_UNAVAILABLE_CONFIG"


@pytest.mark.anyio
async def test_maps_child_timeout_without_returning_patch(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    (project / "modified.txt").write_text("staged\n", encoding="utf-8")
    stage(project, "modified.txt")
    active = reader(root, LocalGitRunner(fail_diff_code="GIT_COMMAND_TIMEOUT"))
    assert await code(active, "modified.txt") == "PATCH_TIMEOUT"


@pytest.mark.anyio
@pytest.mark.parametrize("native", [False, True])
async def test_reads_staged_patch_from_packed_repository_and_unborn_branch(
    tmp_path: Path, native: bool
) -> None:
    root, project = repository(tmp_path)
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "-C", str(project), "gc", "--prune=now"], check=True)
    (project / "modified.txt").write_text("packed head changed\n", encoding="utf-8")
    stage(project, "modified.txt")
    assert (
        "+packed head changed"
        in (
            await reader(root, LocalGitRunner(native=native)).read("formal-project", "modified.txt")
        ).patch
    )

    unborn_root = tmp_path / "unborn-projects"
    unborn = unborn_root / "formal-project"
    unborn.mkdir(parents=True)
    subprocess.run([git, "init", "-q", str(unborn)], check=True)
    (unborn / "first.txt").write_text("first commit\n", encoding="utf-8")
    stage(unborn, "first.txt")
    assert (
        "+first commit"
        in (
            await reader(unborn_root, LocalGitRunner(native=native)).read(
                "formal-project", "first.txt"
            )
        ).patch
    )


@pytest.mark.anyio
async def test_rejects_rename_symlink_untracked_and_invalid_encoding(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    (project / "modified.txt").rename(project / "renamed.txt")
    (project / "link.txt").symlink_to("renamed.txt")
    (project / "untracked.txt").write_text("not staged\n", encoding="utf-8")
    (project / "invalid.txt").write_bytes(b"\xff\n")
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "-C", str(project), "add", "-A"], check=True)
    (project / "untracked.txt").write_text("not staged\n", encoding="utf-8")
    # Remove just this file from the index to retain its untracked status.
    subprocess.run([git, "-C", str(project), "rm", "--cached", "untracked.txt"], check=True)
    active = reader(root, LocalGitRunner())
    assert await code(active, "renamed.txt") == "PATCH_UNAVAILABLE_KIND"
    assert await code(active, "link.txt") == "PATCH_UNAVAILABLE_MODE"
    assert await code(active, "untracked.txt") == "PATCH_STALE"
    assert await code(active, "invalid.txt") == "PATCH_UNAVAILABLE_ENCODING"


@pytest.mark.anyio
@pytest.mark.skipif(sys.platform != "linux", reason="native fd-cwd Git is Linux-only")
async def test_native_linux_child_uses_held_project_descriptor(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    (project / "modified.txt").write_text("native staged\n", encoding="utf-8")
    stage(project, "modified.txt")
    observed = await GitStagedPatchReader(ProjectRegistry(root), GitAdapter()).read(
        "formal-project", "modified.txt"
    )
    assert observed.selection.kind == "modified"
    assert "+native staged" in observed.patch


@pytest.mark.anyio
async def test_discards_mismatched_second_patch(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    (project / "modified.txt").write_text("staged\n", encoding="utf-8")
    stage(project, "modified.txt")

    assert (
        await code(reader(root, LocalGitRunner(change_second_diff=True)), "modified.txt")
        == "PATCH_STALE"
    )
    assert (
        await code(reader(root, LocalGitRunner(change_index_oid=True)), "modified.txt")
        == "PATCH_STALE"
    )


@pytest.mark.anyio
async def test_rejects_patch_above_line_budget(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    (project / "modified.txt").write_text("line\n" * 4100, encoding="utf-8")
    stage(project, "modified.txt")
    assert await code(reader(root, LocalGitRunner()), "modified.txt") == "PATCH_TOO_LARGE"


@pytest.mark.anyio
async def test_cancellation_closes_held_repository_descriptors(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    (project / "modified.txt").write_text("staged\n", encoding="utf-8")
    stage(project, "modified.txt")

    fake = LocalGitRunner(block_on_diff=True)
    operation = asyncio.create_task(reader(root, fake).read("formal-project", "modified.txt"))
    await asyncio.wait_for(fake.reached_diff.wait(), timeout=2)
    assert fake.project_fd is not None
    operation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await operation
    with pytest.raises(OSError):
        os.fstat(fake.project_fd)


@pytest.mark.anyio
@pytest.mark.parametrize("helper", ["fsmonitor", "clean-filter"])
@pytest.mark.parametrize("native", [False, True])
async def test_config_race_never_executes_helper_before_stale_rejection(
    tmp_path: Path, helper: str, native: bool
) -> None:
    root, project = repository(tmp_path)
    target = project / "modified.txt"
    target.write_text("staged\n", encoding="utf-8")
    stage(project, "modified.txt")
    # Same size forces status to inspect content rather than only the stat cache.
    target.write_text("secret\n", encoding="utf-8")
    marker = tmp_path / "helper-ran"
    git = shutil.which("git")
    assert git is not None

    def inject_config_after_check() -> None:
        if helper == "fsmonitor":
            key, command = "core.fsmonitor", f"touch {marker}; echo 0"
        else:
            (project / ".gitattributes").write_text("modified.txt filter=canary\n")
            key, command = "filter.canary.clean", f"touch {marker}; cat"
        subprocess.run([git, "-C", str(project), "config", key, command], check=True)

    fake = LocalGitRunner(before_first_status=inject_config_after_check, native=native)
    assert await code(reader(root, fake), "modified.txt") == "PATCH_STALE"
    assert not marker.exists(), "post-read stale rejection must not follow helper execution"


@pytest.mark.anyio
@pytest.mark.parametrize("storage", ["shallow", "grafts", "promisor", "reftable", "split-index"])
async def test_rejects_unsupported_storage_before_any_git_child(
    tmp_path: Path, storage: str
) -> None:
    root, project = repository(tmp_path)
    git_dir = project / ".git"
    target = {
        "shallow": git_dir / "shallow",
        "grafts": git_dir / "info" / "grafts",
        "promisor": git_dir / "objects" / "pack" / ("pack-" + "a" * 40 + ".promisor"),
        "reftable": git_dir / "reftable",
        "split-index": git_dir / ("sharedindex." + "a" * 40),
    }[storage]
    target.write_bytes(b"unsupported")
    fake = LocalGitRunner()
    assert await code(reader(root, fake), "modified.txt") == "PATCH_UNAVAILABLE_REPOSITORY"
    assert fake.argv == []


@pytest.mark.anyio
@pytest.mark.parametrize("mutation_kind", ["ref", "object"])
async def test_ref_and_object_in_place_mutation_discards_patch(
    tmp_path: Path, mutation_kind: str
) -> None:
    root, project = repository(tmp_path)
    (project / "modified.txt").write_text("staged\n")
    stage(project, "modified.txt")
    git_dir = project / ".git"
    if mutation_kind == "ref":
        ref = (git_dir / "HEAD").read_text().removeprefix("ref: ").strip()
        target = git_dir / ref
    else:
        target = next(p for p in (git_dir / "objects").glob("??/*") if p.is_file())
        target.chmod(0o644)

    def mutate() -> None:
        # Even restoring bytes leaves a changed ctime; held FDs are not immutable.
        original = target.read_bytes()
        target.write_bytes(original + b"drift")
        target.write_bytes(original)

    assert await code(reader(root, LocalGitRunner(mutate)), "modified.txt") == "PATCH_STALE"


@pytest.mark.anyio
async def test_ignores_working_tree_attributes_and_runtime_home(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    (project / "modified.txt").write_text("staged\n")
    stage(project, "modified.txt")
    (project / ".gitattributes").write_text("*.txt -diff\n")
    (project / ".git" / "info" / "attributes").write_text("*.txt -diff\n")
    observed = await reader(root, LocalGitRunner()).read("formal-project", "modified.txt")
    assert "+staged" in observed.patch


@pytest.mark.anyio
async def test_mode_only_change_is_explicitly_unsupported(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    (project / "modified.txt").chmod(0o755)
    stage(project, "modified.txt")
    assert await code(reader(root, LocalGitRunner()), "modified.txt") == "PATCH_UNAVAILABLE_MODE"


def snapshot_root(root: Path) -> GitContentRoot:
    return GitContentRoot(
        root_path=root,
        relative_key="formal-project",
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )


def test_snapshot_seals_index_and_config_but_never_copies_object_bytes(tmp_path: Path) -> None:
    root, _project = repository(tmp_path)
    with snapshot_root(root) as held:
        view = StagedGitSnapshot(held)
        path, descriptors = view.path, tuple(view._fds)
        try:
            assert view.input_fds
            with pytest.raises(OSError):
                os.pwrite(view.config_fd, b"x", 0)
            index_fd = int((path / "index").readlink().name)
            with pytest.raises(OSError):
                os.pwrite(index_fd, b"x", 0)
            regular_files = [
                p.relative_to(path).as_posix()
                for p in path.rglob("*")
                if p.is_file() and not p.is_symlink()
            ]
            assert "config" in regular_files and "HEAD" in regular_files
            assert not any(name.startswith("objects/") for name in regular_files)
            assert all(p.is_symlink() for p in (path / "objects").glob("??/*"))
            assert len(view.input_fds) <= 258
        finally:
            view.close()
        assert not path.exists()
        for fd in descriptors:
            with pytest.raises(OSError):
                os.fstat(fd)


@pytest.mark.parametrize(
    "budget",
    [
        "_MAX_HELD_FDS",
        "_MAX_OBJECT_FILES",
        "_MAX_OBJECT_BYTES",
        "_MAX_INDEX_BYTES",
        "_MAX_METADATA_BYTES",
        "_MAX_REF_NODES",
    ],
)
def test_snapshot_budget_failure_cleans_all_fds_and_private_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, budget: str
) -> None:
    import agentbox_runtime.git_staged_snapshot as module

    root, _project = repository(tmp_path)
    monkeypatch.setattr(module, budget, 0)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with snapshot_root(root) as held:
        before = set(os.listdir("/proc/self/fd"))
        with pytest.raises(RuntimeOperationError):
            StagedGitSnapshot(held)
        assert set(os.listdir("/proc/self/fd")) == before
        assert not list(tmp_path.glob("agentbox-staged-*"))


@pytest.mark.anyio
async def test_cancellation_removes_private_view_and_object_fds(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    (project / "modified.txt").write_text("staged\n")
    stage(project, "modified.txt")
    before = set(os.listdir("/proc/self/fd"))
    fake = LocalGitRunner(block_on_diff=True)
    operation = asyncio.create_task(reader(root, fake).read("formal-project", "modified.txt"))
    await asyncio.wait_for(fake.reached_diff.wait(), timeout=2)
    assert fake.project_fd is not None
    private_path = Path(os.readlink(f"/proc/self/fd/{fake.project_fd}"))
    operation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert not private_path.exists()
    assert set(os.listdir("/proc/self/fd")) == before


def test_packed_refs_counts_toward_combined_metadata_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import agentbox_runtime.git_staged_snapshot as module

    root, project = repository(tmp_path)
    git_dir = project / ".git"
    ref = (git_dir / "HEAD").read_text().removeprefix("ref: ").strip()
    packed = (git_dir / ref).read_bytes().strip() + b" refs/heads/packed\n"
    (git_dir / "packed-refs").write_bytes(packed)
    total = sum((git_dir / name).stat().st_size for name in ("HEAD", "config", ref)) + len(packed)
    monkeypatch.setattr(module, "_MAX_METADATA_BYTES", total - 1)
    with snapshot_root(root) as held, pytest.raises(RuntimeOperationError):
        StagedGitSnapshot(held)


@pytest.mark.anyio
@pytest.mark.parametrize("unsafe_ref", ["symlink", "traversal", "packed-traversal"])
async def test_rejects_unsafe_refs_without_git_execution(tmp_path: Path, unsafe_ref: str) -> None:
    root, project = repository(tmp_path)
    git_dir = project / ".git"
    if unsafe_ref == "symlink":
        (git_dir / "refs" / "heads" / "outside").symlink_to(tmp_path / "canary")
    elif unsafe_ref == "traversal":
        (git_dir / "HEAD").write_text("ref: refs/../../canary\n")
    else:
        (git_dir / "packed-refs").write_text("a" * 40 + " refs/../../canary\n")
    fake = LocalGitRunner()
    assert await code(reader(root, fake), "modified.txt") == "PATCH_UNAVAILABLE_REPOSITORY"
    assert fake.argv == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "key,value", [("extensions.objectformat", "sha1"), ("core.repositoryformatversion", "1")]
)
async def test_rejects_unqualified_repository_formats(tmp_path: Path, key: str, value: str) -> None:
    root, project = repository(tmp_path)
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "-C", str(project), "config", key, value], check=True)
    assert await code(reader(root, LocalGitRunner()), "modified.txt") == "PATCH_UNAVAILABLE_CONFIG"


@pytest.mark.anyio
async def test_rejects_pack_without_index_before_child(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    (project / ".git" / "objects" / "pack" / ("pack-" + "a" * 40 + ".pack")).write_bytes(b"PACK")
    fake = LocalGitRunner()
    assert await code(reader(root, fake), "modified.txt") == "PATCH_UNAVAILABLE_REPOSITORY"
    assert fake.argv == []


@pytest.mark.anyio
async def test_process_only_accepts_fixed_staged_owner_with_matching_cwd(tmp_path: Path) -> None:
    root, _project = repository(tmp_path)
    with snapshot_root(root) as held:
        view = StagedGitSnapshot(held)
        try:
            runner = ControlledProcessRunner()
            executable = GitAdapter()._require_executable()
            with pytest.raises(TypeError):
                await runner.run_with_cwd_fd(
                    executable,
                    ("--version",),
                    environment={},
                    cwd=view.path,
                    cwd_directory_fd=view.directory_fd,
                    timeout_seconds=5,
                    stdout_limit=128,
                    stderr_limit=128,
                    staged_git_inputs=cast(StagedGitSnapshot, (view.config_fd,)),
                )
            with pytest.raises(ValueError):
                await runner.run_with_cwd_fd(
                    executable,
                    ("--version",),
                    environment={},
                    cwd=root,
                    cwd_directory_fd=view.directory_fd,
                    timeout_seconds=5,
                    stdout_limit=128,
                    stderr_limit=128,
                    staged_git_inputs=view,
                )
        finally:
            view.close()
