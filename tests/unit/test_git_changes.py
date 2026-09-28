from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from agentbox_protocol import GitChangePageData
from agentbox_runtime.git import GitAdapter
from agentbox_runtime.git_changes import parse_git_change_page
from agentbox_runtime.models import RuntimeOperationError


def test_git_changes_parse_tracked_rename_conflict_untracked_and_submodule() -> None:
    raw = (
        b"1 M. N... 100644 100644 100644 a b src/modified.py\0"
        b"2 R. N... 100644 100644 100644 a b R100 src/renamed.py\0src/old.py\0"
        b"u UU N... 100644 100644 100644 100644 a b c src/conflict.py\0"
        b"? src/new file.py\0"
        b"1 .. S.M. 160000 160000 160000 a b vendor/module\0"
    )
    page = parse_git_change_page(raw, None)
    assert page.is_repository is True
    assert page.total_count == 5
    assert page.next_cursor is None
    assert [(item.path, item.kind) for item in page.files] == [
        ("src/conflict.py", "conflicted"),
        ("src/modified.py", "modified"),
        ("src/new file.py", "untracked"),
        ("src/renamed.py", "renamed"),
        ("vendor/module", "modified"),
    ]
    renamed = page.files[3]
    assert renamed.previous_path == "src/old.py"
    assert renamed.staged and not renamed.unstaged
    assert page.files[-1].unstaged
    assert GitChangePageData.model_validate(page.to_dict()).total_count == 5


def test_git_changes_cursor_survives_git_output_order_but_rejects_drift() -> None:
    records = [f"? file-{index:02d}.txt".encode() for index in range(40)]
    raw = b"\0".join(records) + b"\0"
    first = parse_git_change_page(raw, None)
    assert len(first.files) == 32
    assert first.total_count == 40
    assert first.next_cursor is not None
    reordered = b"\0".join(reversed(records)) + b"\0"
    second = parse_git_change_page(reordered, first.next_cursor)
    assert [item.path for item in second.files] == [
        f"file-{index:02d}.txt" for index in range(32, 40)
    ]
    assert second.next_cursor is None

    changed = raw + b"? new.txt\0"
    with pytest.raises(RuntimeOperationError) as raised:
        parse_git_change_page(changed, first.next_cursor)
    assert raised.value.code == "GIT_CHANGES_STALE"


def test_git_changes_pages_long_paths_within_runtime_frame_budget() -> None:
    prefix = b"dir/" * 900
    raw = b"".join(b"? " + prefix + f"file-{index:02d}".encode() + b"\0" for index in range(32))
    cursor: str | None = None
    observed: list[str] = []
    while True:
        page = parse_git_change_page(raw, cursor)
        assert len(page.files) <= 32
        observed.extend(item.path for item in page.files)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert observed == [(prefix + f"file-{index:02d}".encode()).decode() for index in range(32)]


@pytest.mark.parametrize(
    "raw",
    [
        b"? not-terminated",
        b"? ../escape\0",
        b"? /absolute\0",
        b"? bad/./path\0",
        b"? bad//path\0",
        b"? invalid-\xff\0",
        b"? same\0? same\0",
        b"2 R. N... 100644 100644 100644 a b R100 new\0",
        b"1 .. N... 100644 100644 100644 a b unchanged\0",
    ],
)
def test_git_changes_rejects_malformed_or_nonrepresentable_paths(raw: bytes) -> None:
    with pytest.raises(RuntimeOperationError) as raised:
        parse_git_change_page(raw, None)
    assert raised.value.code == "GIT_CHANGES_INVALID"


def test_git_changes_rejects_invalid_cursor_and_retains_empty_repository() -> None:
    empty = parse_git_change_page(b"", None)
    assert empty.is_repository and empty.total_count == 0 and empty.files == ()
    with pytest.raises(RuntimeOperationError) as raised:
        parse_git_change_page(b"", "not-a-cursor")
    assert raised.value.code == "GIT_CHANGES_CURSOR_INVALID"


def test_git_changes_reports_explicit_error_above_ten_thousand_entries() -> None:
    raw = b"".join(b"? " + f"file-{index:05d}".encode() + b"\0" for index in range(10_001))
    with pytest.raises(RuntimeOperationError) as raised:
        parse_git_change_page(raw, None)
    assert raised.value.code == "GIT_CHANGES_LIMIT_EXCEEDED"
    assert raised.value.category == "unavailable"


@pytest.mark.anyio
async def test_git_changes_reads_real_repository_metadata_without_file_bodies(
    tmp_path: Path,
) -> None:
    git = shutil.which("git")
    if git is None:
        pytest.skip("Git is unavailable")
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run([git, "init", "-q", str(project)], check=True, capture_output=True)
    original = project / "original.txt"
    original.write_text("tracked\n", encoding="utf-8")
    subprocess.run([git, "-C", str(project), "add", "original.txt"], check=True)
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
            "fixture",
        ],
        check=True,
    )
    original.rename(project / "renamed.txt")
    subprocess.run([git, "-C", str(project), "add", "-A"], check=True)
    (project / "new.txt").write_text("UNTRACKED-BODY-CANARY\n", encoding="utf-8")

    page = await GitAdapter().changes(project, None)
    assert [(item.path, item.kind, item.previous_path) for item in page.files] == [
        ("new.txt", "untracked", None),
        ("renamed.txt", "renamed", "original.txt"),
    ]
    assert "UNTRACKED-BODY-CANARY" not in str(page.to_dict())
