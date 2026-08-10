from __future__ import annotations

import re
from pathlib import Path

import pytest
from agentbox_runtime import (
    ProjectRegistry,
    RuntimeOperationError,
    managed_session_name,
    validate_project_id,
)


def test_project_registry_lists_only_safe_immediate_real_directories(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    (root / "valid-project").mkdir()
    (root / "项目").mkdir()
    (root / "a file").write_text("not a directory")
    nested = root / "nested"
    nested.mkdir()
    (nested / "child").mkdir()
    (root / "inside-link").symlink_to(root / "valid-project", target_is_directory=True)
    (root / "outside-link").symlink_to(tmp_path, target_is_directory=True)

    registry = ProjectRegistry(root)
    assert [item.project_id for item in registry.list_projects()] == [
        "nested",
        "valid-project",
        "项目",
    ]
    assert registry.resolve("valid-project").path == (root / "valid-project").resolve()
    assert registry.resolve("项目").path == (root / "项目").resolve()


@pytest.mark.parametrize(
    "project_id",
    ["../escape", "/absolute", ".", "..", "nested/child", "bad;rm", " bad", "bad\x00id"],
)
def test_project_identifier_rejects_paths_and_injection(project_id: str) -> None:
    with pytest.raises(RuntimeOperationError) as captured:
        validate_project_id(project_id)
    assert captured.value.code == "CLAUDE_PROJECT_INVALID"


def test_project_registry_rejects_symlinks_files_missing_and_root(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    (root / "file").write_text("x")
    (root / "real").mkdir()
    (root / "inside").symlink_to(root / "real", target_is_directory=True)
    (root / "outside").symlink_to(tmp_path, target_is_directory=True)
    registry = ProjectRegistry(root)

    for project_id in ("file", "inside", "outside", "missing"):
        with pytest.raises(RuntimeOperationError):
            registry.resolve(project_id)
    with pytest.raises(RuntimeOperationError):
        registry.resolve(".")


def test_project_root_symlink_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(RuntimeOperationError) as captured:
        ProjectRegistry(alias).resolve("project")
    assert captured.value.code == "CLAUDE_PROJECT_ROOT_INVALID"


@pytest.mark.parametrize(
    "project_id",
    [
        "normal-project",
        "project with spaces",
        "项目",
        "x" * 500,
        "punctuation;rm -rf",
        "../escape",
    ],
)
def test_session_names_are_stable_bounded_and_ascii(project_id: str) -> None:
    first = managed_session_name(project_id)
    assert first == managed_session_name(project_id)
    assert len(first) <= 80
    assert re.fullmatch(r"[A-Za-z0-9_-]+", first)
    assert ";" not in first and ".." not in first and "/" not in first


def test_session_names_resist_display_name_collisions() -> None:
    assert managed_session_name("duplicate one") != managed_session_name("duplicate-one")
    assert managed_session_name("project") != managed_session_name("Project")
