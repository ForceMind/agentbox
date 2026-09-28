from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from agentbox_runtime.git_staged_selection import select_staged_change, validate_patch_path
from agentbox_runtime.models import RuntimeOperationError


def code(status: bytes, path: str) -> str:
    with pytest.raises(RuntimeOperationError) as raised:
        select_staged_change(status, path)
    return raised.value.code


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/normal.py", None),
        ("-option.txt", None),
        ("src/file with spaces.ts", None),
        (".env", "PATCH_UNAVAILABLE_SENSITIVE_PATH"),
        ("src/.ENV.production", "PATCH_UNAVAILABLE_SENSITIVE_PATH"),
        (".env.local/source.ts", "PATCH_UNAVAILABLE_SENSITIVE_PATH"),
        (".ssh/id_rsa", "PATCH_UNAVAILABLE_SENSITIVE_PATH"),
        ("src/CLIENT.PEM", "PATCH_UNAVAILABLE_SENSITIVE_PATH"),
        ("config/.npmrc", "PATCH_UNAVAILABLE_SENSITIVE_PATH"),
        ("src/.agentbox/state", "PATCH_UNAVAILABLE_SENSITIVE_PATH"),
        ("src/credentials.json", "PATCH_UNAVAILABLE_SENSITIVE_PATH"),
        ("src/config.json", None),
        ("../escape", "PATCH_UNAVAILABLE_PATH"),
        ("/absolute", "PATCH_UNAVAILABLE_PATH"),
        (":(top)file", "PATCH_UNAVAILABLE_PATH"),
        ("bad\nname", "PATCH_UNAVAILABLE_PATH"),
        ("dir//file", "PATCH_UNAVAILABLE_PATH"),
        ("dir\\file", "PATCH_UNAVAILABLE_PATH"),
    ],
)
def test_path_policy(path: str, expected: str | None) -> None:
    if expected is None:
        assert validate_patch_path(path) == path
    else:
        with pytest.raises(RuntimeOperationError) as raised:
            validate_patch_path(path)
        assert raised.value.code == expected


def test_staged_selection_real_git_add_modify_delete_and_both_sides(tmp_path: Path) -> None:
    git = shutil.which("git")
    if git is None:
        pytest.skip("Git is unavailable")
    repo = tmp_path / "repo"
    repo.mkdir()

    def run(*args: str) -> bytes:
        return subprocess.run([git, "-C", str(repo), *args], check=True, capture_output=True).stdout

    run("init", "-q")
    (repo / "modified.txt").write_text("old\n", encoding="utf-8")
    (repo / "deleted.txt").write_text("old\n", encoding="utf-8")
    run("add", "modified.txt", "deleted.txt")
    run(
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        "base",
    )
    (repo / "modified.txt").write_text("staged\n", encoding="utf-8")
    (repo / "added.txt").write_text("added\n", encoding="utf-8")
    (repo / "deleted.txt").unlink()
    run("add", "-A")
    (repo / "modified.txt").write_text("unstaged\n", encoding="utf-8")
    status = run(
        "--no-optional-locks",
        "status",
        "--porcelain=v2",
        "-z",
        "--untracked-files=all",
        "--renames",
    )
    assert select_staged_change(status, "modified.txt").kind == "modified"
    assert select_staged_change(status, "added.txt").kind == "added"
    assert select_staged_change(status, "deleted.txt").kind == "deleted"
    assert code(status, "not-changed.txt") == "PATCH_STALE"
    assert code(status, "modified.txt/../other") == "PATCH_UNAVAILABLE_PATH"


def test_rejects_unsupported_modes_kinds_and_malformed_oids() -> None:
    old = b"a" * 40
    new = b"b" * 40
    regular = b"1 M. N... 100644 100644 100644 " + old + b" " + new + b" src/file.txt\0"
    selected = select_staged_change(regular, "src/file.txt")
    assert selected.head_oid == "a" * 40 and selected.index_oid == "b" * 40
    assert code(regular, "src/missing.txt") == "PATCH_STALE"
    assert (
        code(regular.replace(b"100644 100644", b"100644 120000"), "src/file.txt")
        == "PATCH_UNAVAILABLE_MODE"
    )
    assert code(regular.replace(old, b"z" * 40), "src/file.txt") == "PATCH_UNAVAILABLE_STATUS"
    assert code(regular.replace(b"1 M.", b"1 T."), "src/file.txt") == "PATCH_UNAVAILABLE_KIND"
    assert code(b"? src/file.txt\0", "src/file.txt") == "PATCH_UNAVAILABLE_KIND"
    rename = (
        b"2 R. N... 100644 100644 100644 " + old + b" " + new + b" R100 src/file.txt\0src/old.txt\0"
    )
    assert code(rename, "src/file.txt") == "PATCH_UNAVAILABLE_KIND"


def test_failure_categories_do_not_treat_unsupported_content_as_authorized() -> None:
    for status, path, category in (
        (b"", ".env.local", "forbidden"),
        (b"? src/file.txt\0", "src/file.txt", "unsupported"),
        (b"1 M. N... 100644 100644 100644 bad bad src/file.txt\0", "src/file.txt", "unavailable"),
        (b"", "src/file.txt", "conflict"),
    ):
        with pytest.raises(RuntimeOperationError) as raised:
            select_staged_change(status, path)
        assert raised.value.category == category
