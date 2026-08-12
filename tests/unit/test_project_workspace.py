from __future__ import annotations

from pathlib import Path

import pytest
from agentbox_runtime.models import GitStatus, RuntimeOperationError
from agentbox_runtime.project import ProjectRegistry
from agentbox_runtime.workspace import ProjectWorkspaceManager

OPERATION_ID = "job_0123456789abcdef0123456789abcdef"


class FakeGit:
    def __init__(self, *, fail_clone: bool = False) -> None:
        self.fail_clone = fail_clone
        self.clone_calls: list[tuple[str, Path, Path]] = []

    async def clone(self, repository_url: str, *, cwd: Path, destination: Path) -> None:
        self.clone_calls.append((repository_url, cwd, destination))
        destination.mkdir()
        (destination / "partial").write_text("owned by this operation", encoding="utf-8")
        if self.fail_clone:
            raise RuntimeOperationError("GIT_CLONE_FAILED", "Repository clone failed")
        (destination / ".git").mkdir()

    async def status(self, project: Path) -> GitStatus:
        assert (project / ".git").is_dir()
        return GitStatus(True, branch="main", clean=True)


class UnusedGitHub:
    pass


def manager(root: Path, git: FakeGit) -> ProjectWorkspaceManager:
    return ProjectWorkspaceManager(
        ProjectRegistry(root),
        git,  # type: ignore[arg-type]
        UnusedGitHub(),  # type: ignore[arg-type]
    )


@pytest.mark.anyio
async def test_clone_stages_then_atomically_finalizes_owned_workspace(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    workspace = manager(root, FakeGit())

    result = await workspace.clone(
        "safe-project", OPERATION_ID, "https://github.com/owner/repo.git"
    )

    final = root / "safe-project"
    assert result.outcome == "cloned" and result.branch == "main"
    assert final.is_dir()
    assert (final / ".agentbox-project").read_text(encoding="ascii") == (f"clone:{OPERATION_ID}")
    assert not any((root / ".agentbox-tmp").glob("*/workspace"))

    assert workspace.finalize("safe-project", OPERATION_ID).outcome == "finalized"
    assert not (final / ".agentbox-project").exists()
    assert list((root / ".agentbox-tmp").iterdir()) == []


@pytest.mark.anyio
async def test_failed_clone_removes_only_marker_bound_partial_staging(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    workspace = manager(root, FakeGit(fail_clone=True))

    with pytest.raises(RuntimeOperationError) as raised:
        await workspace.clone("safe-project", OPERATION_ID, "https://github.com/owner/repo.git")

    assert raised.value.code == "GIT_CLONE_FAILED"
    assert not (root / "safe-project").exists()
    assert list((root / ".agentbox-tmp").iterdir()) == []


@pytest.mark.anyio
async def test_collision_cleans_staging_without_touching_existing_target(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    outside = tmp_path / "outside"
    outside.mkdir()
    target = root / "safe-project"
    target.symlink_to(outside, target_is_directory=True)
    workspace = manager(root, FakeGit())

    with pytest.raises(RuntimeOperationError) as raised:
        await workspace.create("safe-project", OPERATION_ID)

    assert raised.value.code == "PROJECT_PATH_COLLISION"
    assert target.is_symlink()
    assert outside.is_dir()
    assert list((root / ".agentbox-tmp").iterdir()) == []


@pytest.mark.anyio
async def test_case_normalized_filesystem_collision_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    existing = root / "Safe-Project"
    existing.mkdir()
    (existing / "canary").write_text("preserve", encoding="utf-8")

    with pytest.raises(RuntimeOperationError) as raised:
        await manager(root, FakeGit()).create("safe-project", OPERATION_ID)

    assert raised.value.code == "PROJECT_PATH_COLLISION"
    assert (existing / "canary").read_text(encoding="utf-8") == "preserve"
    assert not (root / "safe-project").exists()


@pytest.mark.anyio
async def test_existing_file_collision_is_preserved(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    target = root / "safe-project"
    target.write_text("preserve", encoding="utf-8")

    with pytest.raises(RuntimeOperationError) as raised:
        await manager(root, FakeGit()).create("safe-project", OPERATION_ID)

    assert raised.value.code == "PROJECT_PATH_COLLISION"
    assert target.read_text(encoding="utf-8") == "preserve"


@pytest.mark.anyio
async def test_activation_race_never_replaces_new_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    workspace = manager(root, FakeGit())
    original = workspace._rename_noreplace

    def create_collision_then_activate(
        source_directory: Path,
        source_name: str,
        destination_directory: Path,
        destination_name: str,
    ) -> None:
        collision = destination_directory / destination_name
        collision.mkdir()
        (collision / "canary").write_text("must survive", encoding="utf-8")
        original(source_directory, source_name, destination_directory, destination_name)

    monkeypatch.setattr(workspace, "_rename_noreplace", create_collision_then_activate)
    with pytest.raises(RuntimeOperationError) as raised:
        await workspace.create("safe-project", OPERATION_ID)

    assert raised.value.code == "PROJECT_PATH_COLLISION"
    assert (root / "safe-project" / "canary").read_text(encoding="utf-8") == "must survive"
    assert list((root / ".agentbox-tmp").iterdir()) == []


@pytest.mark.anyio
async def test_activation_failure_cleans_only_operation_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    workspace = manager(root, FakeGit())

    def fail_activation(*_args: object) -> None:
        raise RuntimeOperationError("PROJECT_ACTIVATION_FAILED", "simulated rename failure")

    monkeypatch.setattr(workspace, "_rename_noreplace", fail_activation)
    with pytest.raises(RuntimeOperationError) as raised:
        await workspace.create("safe-project", OPERATION_ID)

    assert raised.value.code == "PROJECT_ACTIVATION_FAILED"
    assert not (root / "safe-project").exists()
    assert list((root / ".agentbox-tmp").iterdir()) == []


@pytest.mark.anyio
async def test_post_rename_failure_preserves_rollback_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    workspace = manager(root, FakeGit())
    original = workspace._rename_noreplace

    def activate_then_report_uncertain(
        source_directory: Path,
        source_name: str,
        destination_directory: Path,
        destination_name: str,
    ) -> None:
        original(source_directory, source_name, destination_directory, destination_name)
        raise RuntimeOperationError(
            "PROJECT_ACTIVATION_DURABILITY_UNKNOWN", "simulated directory fsync failure"
        )

    monkeypatch.setattr(workspace, "_rename_noreplace", activate_then_report_uncertain)
    with pytest.raises(RuntimeOperationError) as raised:
        await workspace.create("safe-project", OPERATION_ID)

    assert raised.value.code == "PROJECT_ACTIVATION_DURABILITY_UNKNOWN"
    operation_dir = workspace._operation_dir(root, OPERATION_ID)
    assert operation_dir.is_dir()
    assert (root / "safe-project" / ".agentbox-project").is_file()
    assert workspace.rollback("safe-project", OPERATION_ID).outcome == "rolled_back"
    assert not (root / "safe-project").exists()


@pytest.mark.anyio
async def test_rollback_requires_exact_identity_marker_and_preserves_mismatch(
    tmp_path: Path,
) -> None:
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    workspace = manager(root, FakeGit())
    await workspace.create("safe-project", OPERATION_ID)
    marker = root / "safe-project" / ".agentbox-project"
    marker.write_text("job_ffffffffffffffffffffffffffffffff", encoding="ascii")

    with pytest.raises(RuntimeOperationError) as raised:
        workspace.rollback("safe-project", OPERATION_ID)

    assert raised.value.code == "PROJECT_ROLLBACK_INVALID"
    assert (root / "safe-project").is_dir()


@pytest.mark.anyio
async def test_rollback_requires_present_identity_marker(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    workspace = manager(root, FakeGit())
    await workspace.create("safe-project", OPERATION_ID)
    final = root / "safe-project"
    (final / ".agentbox-project").unlink()

    with pytest.raises(RuntimeOperationError) as raised:
        workspace.rollback("safe-project", OPERATION_ID)

    assert raised.value.code == "PROJECT_ROLLBACK_INVALID"
    assert final.is_dir()


@pytest.mark.anyio
async def test_empty_project_rollback_refuses_new_content_and_preserves_identity(
    tmp_path: Path,
) -> None:
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    workspace = manager(root, FakeGit())
    await workspace.create("safe-project", OPERATION_ID)
    final = root / "safe-project"
    (final / "user-content").write_text("preserve", encoding="utf-8")

    with pytest.raises(RuntimeOperationError) as raised:
        workspace.rollback("safe-project", OPERATION_ID)

    assert raised.value.code == "PROJECT_CLEANUP_UNSAFE"
    assert (final / "user-content").read_text(encoding="utf-8") == "preserve"
    assert (final / ".agentbox-project").read_text(encoding="ascii") == (f"empty:{OPERATION_ID}")


@pytest.mark.anyio
async def test_clone_rollback_removes_only_exact_marker_bound_workspace(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    workspace = manager(root, FakeGit())
    await workspace.clone("safe-project", OPERATION_ID, "https://github.com/owner/repo.git")

    assert workspace.rollback("safe-project", OPERATION_ID).outcome == "rolled_back"
    assert not (root / "safe-project").exists()
    assert list((root / ".agentbox-tmp").iterdir()) == []


def test_rollback_without_final_cleans_only_owned_staging(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    workspace = manager(root, FakeGit())
    _root, operation_dir, staging = workspace._staging(OPERATION_ID)
    staging.mkdir()
    (staging / "partial").write_text("owned", encoding="utf-8")

    assert workspace.rollback("safe-project", OPERATION_ID).outcome == "rolled_back"
    assert not operation_dir.exists()


def test_rollback_without_final_rejects_mismatched_staging_marker(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    workspace = manager(root, FakeGit())
    _root, operation_dir, _staging = workspace._staging(OPERATION_ID)
    (operation_dir / ".agentbox-operation").write_text(
        "job_ffffffffffffffffffffffffffffffff", encoding="ascii"
    )

    with pytest.raises(RuntimeOperationError) as raised:
        workspace.rollback("safe-project", OPERATION_ID)

    assert raised.value.code == "PROJECT_ROLLBACK_INVALID"
    assert operation_dir.is_dir()


@pytest.mark.anyio
async def test_rollback_with_final_validates_staging_before_workspace_delete(
    tmp_path: Path,
) -> None:
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    workspace = manager(root, FakeGit())
    await workspace.clone("safe-project", OPERATION_ID, "https://github.com/owner/repo.git")
    operation_dir = workspace._operation_dir(root, OPERATION_ID)
    (operation_dir / ".agentbox-operation").write_text(
        "job_ffffffffffffffffffffffffffffffff", encoding="ascii"
    )

    with pytest.raises(RuntimeOperationError) as raised:
        workspace.rollback("safe-project", OPERATION_ID)

    assert raised.value.code == "PROJECT_ROLLBACK_INVALID"
    assert (root / "safe-project" / ".git").is_dir()


@pytest.mark.anyio
async def test_stale_staging_is_not_replayed_or_blindly_deleted(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    workspace = manager(root, FakeGit())
    _root, operation_dir, _staging = workspace._staging(OPERATION_ID)

    with pytest.raises(RuntimeOperationError) as raised:
        await workspace.create("safe-project", OPERATION_ID)

    assert raised.value.code == "PROJECT_OPERATION_CONFLICT"
    assert (operation_dir / ".agentbox-operation").read_text(encoding="ascii") == OPERATION_ID


def test_project_root_group_writable_and_symlink_roots_fail_closed(tmp_path: Path) -> None:
    unsafe = tmp_path / "unsafe"
    unsafe.mkdir(mode=0o770)
    unsafe.chmod(0o770)
    with pytest.raises(RuntimeOperationError):
        ProjectRegistry(unsafe).resolved_root(required=True)

    safe = tmp_path / "safe"
    safe.mkdir(mode=0o700)
    linked = tmp_path / "linked"
    linked.symlink_to(safe, target_is_directory=True)
    with pytest.raises(RuntimeOperationError):
        ProjectRegistry(linked).resolved_root(required=True)


@pytest.mark.anyio
async def test_group_writable_workspace_and_temporary_root_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    unsafe_project = root / "unsafe-project"
    unsafe_project.mkdir(mode=0o770)
    unsafe_project.chmod(0o770)
    registry = ProjectRegistry(root)
    assert registry.list_projects() == ()
    with pytest.raises(RuntimeOperationError):
        registry.resolve("unsafe-project")

    unsafe_project.chmod(0o700)
    temporary_root = root / ".agentbox-tmp"
    temporary_root.mkdir(mode=0o770)
    temporary_root.chmod(0o770)
    with pytest.raises(RuntimeOperationError) as raised:
        await manager(root, FakeGit()).create("safe-project", OPERATION_ID)
    assert raised.value.code == "PROJECT_TEMP_ROOT_INVALID"
