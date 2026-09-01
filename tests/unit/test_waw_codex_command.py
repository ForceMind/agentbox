from __future__ import annotations

import os
from pathlib import Path

import pytest
from agentbox_core.waw import workspace_id
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.process import ExecutableIdentity
from agentbox_runtime.project import ProjectRegistry
from agentbox_runtime.waw_codex_command import WAWCodexCommand, build_codex_command

PROJECT_ID = "prj_" + "1" * 32
WORKSPACE_ID = workspace_id(PROJECT_ID, "codex")
MARKER = "waw-v1:wri_" + "2" * 32 + ":" + "3" * 32


def _executable(tmp_path: Path, name: str = "codex") -> ExecutableIdentity:
    path = tmp_path / name
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    details = path.stat()
    return ExecutableIdentity(
        path=path,
        device=details.st_dev,
        inode=details.st_ino,
        mode=details.st_mode,
        size=details.st_size,
        modified_ns=details.st_mtime_ns,
    )


def test_builds_project_scoped_codex_command(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    project = root / PROJECT_ID
    project.mkdir(parents=True)
    command = build_codex_command(
        registry=ProjectRegistry(root),
        project_id=PROJECT_ID,
        workspace_id=WORKSPACE_ID,
        executable=_executable(tmp_path),
        managed_marker=MARKER,
    )
    assert isinstance(command, WAWCodexCommand)
    assert command.cwd == project
    assert command.argv == ()
    assert command.workspace_id == WORKSPACE_ID


@pytest.mark.parametrize(
    ("workspace", "argv", "marker"),
    [
        (workspace_id(PROJECT_ID, "claude"), (), MARKER),
        (WORKSPACE_ID, ("--project", "other"), MARKER),
        (WORKSPACE_ID, (), "waw-v1:wri_" + "2" * 32 + ":../escape"),
    ],
)
def test_codex_command_rejects_identity_arguments_and_marker(
    tmp_path: Path, workspace: str, argv: tuple[str, ...], marker: str
) -> None:
    root = tmp_path / "projects"
    project = root / PROJECT_ID
    project.mkdir(parents=True)
    with pytest.raises(RuntimeOperationError):
        WAWCodexCommand(
            workspace_id=workspace,
            project_id=PROJECT_ID,
            cwd=project,
            executable=_executable(tmp_path),
            argv=argv,
            managed_marker=marker,
        )


def test_codex_executable_name_is_closed(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    project = root / PROJECT_ID
    project.mkdir(parents=True)
    with pytest.raises(RuntimeOperationError):
        build_codex_command(
            registry=ProjectRegistry(root),
            project_id=PROJECT_ID,
            workspace_id=WORKSPACE_ID,
            executable=_executable(tmp_path, "claude"),
            managed_marker=MARKER,
        )


def test_symlink_project_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, root / PROJECT_ID)
    with pytest.raises(RuntimeOperationError):
        build_codex_command(
            registry=ProjectRegistry(root),
            project_id=PROJECT_ID,
            workspace_id=WORKSPACE_ID,
            executable=_executable(tmp_path),
            managed_marker=MARKER,
        )
