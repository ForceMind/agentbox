from __future__ import annotations

import os
from pathlib import Path

import pytest
from agentbox_core.waw import workspace_id
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.process import ExecutableIdentity
from agentbox_runtime.project import ProjectRegistry
from agentbox_runtime.waw_command import build_claude_command

PROJECT_ID = "demo"
WORKSPACE_ID = workspace_id("prj_" + "1" * 32, "claude")


def _executable(tmp_path: Path) -> ExecutableIdentity:
    path = tmp_path / "claude"
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


def test_builds_exact_fixed_claude_command(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    project = root / PROJECT_ID
    project.mkdir(parents=True)
    registry = ProjectRegistry(root)
    command = build_claude_command(
        registry=registry,
        project_id=PROJECT_ID,
        workspace_id=WORKSPACE_ID,
        executable=_executable(tmp_path),
        managed_marker="waw-v1:marker",
    )
    assert command.cwd == project
    assert command.argv == ("remote-control",)
    assert command.workspace_id == WORKSPACE_ID


@pytest.mark.parametrize("project_id", ["../escape", "/tmp/escape", "demo/child", ""])
def test_project_identity_cannot_escape_registry(tmp_path: Path, project_id: str) -> None:
    root = tmp_path / "projects"
    (root / PROJECT_ID).mkdir(parents=True)
    with pytest.raises(RuntimeOperationError):
        build_claude_command(
            registry=ProjectRegistry(root),
            project_id=project_id,
            workspace_id=WORKSPACE_ID,
            executable=_executable(tmp_path),
            managed_marker="waw-v1:marker",
        )


def test_symlink_project_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, root / PROJECT_ID)
    with pytest.raises(RuntimeOperationError):
        build_claude_command(
            registry=ProjectRegistry(root),
            project_id=PROJECT_ID,
            workspace_id=WORKSPACE_ID,
            executable=_executable(tmp_path),
            managed_marker="waw-v1:marker",
        )
