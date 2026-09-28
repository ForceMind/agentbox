from __future__ import annotations

import os
from pathlib import Path

import pytest
from agentbox_runtime.git_content_root import GitContentRoot
from agentbox_runtime.models import RuntimeOperationError


def repository(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "projects"
    project = root / "formal-project"
    git = project / ".git"
    (git / "objects" / "info").mkdir(parents=True)
    (git / "objects" / "pack").mkdir()
    (git / "index").write_bytes(b"DIRC\0")
    (git / "config").write_text("[core]\n", encoding="utf-8")
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="ascii")
    return root, project


def open_root(root: Path) -> GitContentRoot:
    return GitContentRoot(
        root_path=root,
        relative_key="formal-project",
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )


def assert_code(root: Path, code: str) -> None:
    with pytest.raises(RuntimeOperationError) as raised:
        open_root(root)
    assert raised.value.code == code


def test_holds_and_revalidates_exact_project_and_git_nodes(tmp_path: Path) -> None:
    root, _ = repository(tmp_path)
    with open_root(root) as held:
        held.revalidate()
        descriptors = tuple(held._fds.values())
        assert len(descriptors) == 9
        assert all(os.fstat(descriptor).st_ino > 0 for descriptor in descriptors)
    for descriptor in descriptors:
        with pytest.raises(OSError):
            os.fstat(descriptor)
    with pytest.raises(RuntimeOperationError) as raised:
        held.revalidate()
    assert raised.value.code == "GIT_CONTENT_ROOT_UNAVAILABLE"
    held.close()


def test_rejects_project_replacement_after_descriptor_acquisition(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    with open_root(root) as held:
        project.rename(root / "old-project")
        (root / "formal-project").mkdir()
        with pytest.raises(RuntimeOperationError) as raised:
            held.revalidate()
        assert raised.value.code == "GIT_CONTENT_ROOT_UNSAFE"


def test_rejects_root_replacement_and_permissions_changed_during_hold(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    with open_root(root) as held:
        project.chmod(0o770)
        with pytest.raises(RuntimeOperationError) as raised:
            held.revalidate()
        assert raised.value.code == "GIT_CONTENT_ROOT_UNSAFE"
    project.chmod(0o700)
    with open_root(root) as held:
        root.rename(tmp_path / "old-root")
        root.mkdir()
        with pytest.raises(RuntimeOperationError) as raised:
            held.revalidate()
        assert raised.value.code == "GIT_CONTENT_ROOT_UNSAFE"


def test_rejects_git_store_and_index_replacement(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    with open_root(root) as held:
        index = project / ".git" / "index"
        index.rename(project / ".git" / "index.old")
        index.write_bytes(b"DIRC-new")
        with pytest.raises(RuntimeOperationError) as raised:
            held.revalidate()
        assert raised.value.code == "GIT_CONTENT_ROOT_UNSAFE"

    root, project = repository(tmp_path / "second")
    with open_root(root) as held:
        objects = project / ".git" / "objects"
        objects.rename(project / ".git" / "objects.old")
        objects.mkdir()
        with pytest.raises(RuntimeOperationError) as raised:
            held.revalidate()
        assert raised.value.code == "GIT_CONTENT_ROOT_UNSAFE"


def test_failed_context_entry_closes_all_held_descriptors(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    held = open_root(root)
    descriptor = held._fds["project"]
    (project / ".git" / "config").write_text("[core]\n\tchanged = true\n", encoding="utf-8")
    with pytest.raises(RuntimeOperationError) as raised:
        held.__enter__()
    assert raised.value.code == "GIT_CONTENT_ROOT_UNSAFE"
    with pytest.raises(OSError):
        os.fstat(descriptor)


@pytest.mark.parametrize("name", ["alternates", "http-alternates"])
def test_rejects_external_object_store_declaration(tmp_path: Path, name: str) -> None:
    root, project = repository(tmp_path)
    (project / ".git" / "objects" / "info" / name).write_text(
        "/private/other-objects\n", encoding="utf-8"
    )
    assert_code(root, "GIT_CONTENT_ROOT_UNSAFE")


def test_rejects_alternate_store_added_during_hold(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    with open_root(root) as held:
        (project / ".git" / "objects" / "info" / "alternates").write_text(
            "/private/other-objects\n", encoding="utf-8"
        )
        with pytest.raises(RuntimeOperationError) as raised:
            held.revalidate()
        assert raised.value.code == "GIT_CONTENT_ROOT_UNSAFE"


def test_rejects_gitfile_commondir_symlink_and_shared_writes(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    (project / ".git" / "commondir").write_text("../other\n", encoding="utf-8")
    assert_code(root, "GIT_CONTENT_ROOT_UNSAFE")
    (project / ".git" / "commondir").unlink()

    index = project / ".git" / "index"
    index.unlink()
    index.symlink_to(tmp_path / "outside")
    assert_code(root, "GIT_CONTENT_ROOT_UNAVAILABLE")
    index.unlink()
    index.write_bytes(b"DIRC\0")

    project.chmod(0o770)
    assert_code(root, "GIT_CONTENT_ROOT_UNSAFE")
    project.chmod(0o700)
    (project / ".git" / "config").chmod(0o666)
    assert_code(root, "GIT_CONTENT_ROOT_UNSAFE")


def test_rejects_root_alias_or_invalid_project_key(tmp_path: Path) -> None:
    root, _ = repository(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    assert_code(alias, "GIT_CONTENT_ROOT_UNAVAILABLE")
    with pytest.raises(RuntimeOperationError) as raised:
        GitContentRoot(
            root_path=root,
            relative_key="../formal-project",
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
        )
    assert raised.value.code == "GIT_CONTENT_ROOT_UNSAFE"


def test_rejects_gitfile_and_wrong_owner_expectation(tmp_path: Path) -> None:
    root, project = repository(tmp_path)
    with pytest.raises(RuntimeOperationError) as raised:
        GitContentRoot(
            root_path=root,
            relative_key="formal-project",
            expected_uid=os.geteuid() + 1,
            expected_gid=os.getegid(),
        )
    assert raised.value.code == "GIT_CONTENT_ROOT_UNSAFE"

    git = project / ".git"
    for child in (git / "objects" / "info", git / "objects" / "pack"):
        child.rmdir()
    (git / "objects").rmdir()
    for child in (git / "index", git / "config", git / "HEAD"):
        child.unlink()
    git.rmdir()
    git.write_text("gitdir: ../other\n", encoding="utf-8")
    assert_code(root, "GIT_CONTENT_ROOT_UNAVAILABLE")
