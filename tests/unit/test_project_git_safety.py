from __future__ import annotations

import os
from pathlib import Path

import pytest
from agentbox_core.errors import ProjectValidationError
from agentbox_core.projects import project_slug, validate_repository_url
from agentbox_runtime import RuntimeOperationError, redact_remote_url, validate_branch_name
from agentbox_runtime.project import ProjectRegistry


@pytest.mark.parametrize(
    "value",
    ["", ".", "..", "../escape", "/absolute", "a/b", "a\\b", "-option", "x\x00y"],
)
def test_project_slugs_reject_path_and_option_injection(value: str) -> None:
    with pytest.raises(ProjectValidationError):
        project_slug("valid", value)


@pytest.mark.parametrize(
    "value",
    [
        "file:///etc/passwd",
        "ext::sh -c id",
        "/tmp/repository",
        "https://user:secret@github.com/owner/repo.git",
        "https://example.com/owner/repo.git",
        "--upload-pack=evil",
    ],
)
def test_repository_urls_reject_protocol_and_credential_injection(value: str) -> None:
    with pytest.raises(ProjectValidationError):
        validate_repository_url(value)


@pytest.mark.parametrize(
    "value",
    ["-force", "HEAD", "@", "feature/../escape", "name@{1}", "bad//name", "bad.lock"],
)
def test_branch_names_reject_ref_and_option_injection(value: str) -> None:
    with pytest.raises(RuntimeOperationError):
        validate_branch_name(value)


def test_remote_url_credentials_are_redacted() -> None:
    assert (
        redact_remote_url("https://user:token@github.com/owner/repo.git?token=bad")
        == "https://github.com/owner/repo.git"
    )
    assert redact_remote_url("file:///tmp/private") is None
    assert redact_remote_url("git@github.com:owner/repo.git") == "git@github.com:owner/repo.git"


def test_registry_rejects_root_and_project_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "valid").mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)
    registry = ProjectRegistry(root)
    assert [project.project_id for project in registry.list_projects()] == ["valid"]
    with pytest.raises(RuntimeOperationError):
        registry.resolve("escape")

    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(root, target_is_directory=True)
    with pytest.raises(RuntimeOperationError):
        ProjectRegistry(linked_root).resolved_root(required=True)


def test_registry_does_not_accept_foreign_owned_repository_simulation(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    project = root / "project"
    project.mkdir()
    assert project.stat().st_uid == os.geteuid()
