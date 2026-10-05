"""Real Git diff fixture checks without browser, socket, account or host access."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from a3_native_fixture import _fixture_environment, _populate_patch_project


@pytest.fixture
def project(tmp_path: Path) -> Path:
    result = tmp_path / "synthetic-project"
    _populate_patch_project(result)
    return result


def git(project: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(project), *arguments],
        check=True,
        capture_output=True,
        env=_fixture_environment(),
    ).stdout


def patch(project: Path, filename: str) -> bytes:
    return git(project, "diff", "--cached", "--full-index", "--no-color", "--", filename)


def test_native_fixture_has_real_added_modified_deleted_staged_git(project: Path) -> None:
    assert git(project, "diff", "--cached", "--name-status").splitlines() == [
        b"A\t.env",
        b"A\tbinary.bin",
        b"M\tcrlf.txt",
        b"D\tdelete.txt",
        b"A\tlarge.txt",
        b"A\tlong-line.txt",
        b"M\tmodify.txt",
        b"M\tmultiple-hunks.txt",
        b"M\tno-final-newline.txt",
        b"A\tsuccess.txt",
    ]
    # Baseline commit identity is synthetic and not installed in local/global config.
    assert git(project, "log", "-1", "--format=%an <%ae>") == (
        b"AgentBox synthetic fixture <fixture@example.invalid>\n"
    )
    assert b"user.name=" not in git(project, "config", "--local", "--list")
    assert b"user.email=" not in git(project, "config", "--local", "--list")


def test_native_success_fixture_remains_complete_inert_bounded_and_staged(project: Path) -> None:
    raw = patch(project, "success.txt")
    assert len(raw) > 24000
    assert b"@@ -0,0 +1,9 @@\n" in raw
    assert b"<img src=x onerror=window.a3Executed=true>" in raw
    assert b'<a href="https://example.invalid/a3">inert link</a>' in raw
    assert b"<script>window.a3Executed=true</script>" in raw
    assert "🌍".encode() in raw
    assert b"unstaged-exclusion-canary" not in raw
    assert b"unstaged-exclusion-canary" in (project / "success.txt").read_bytes()
    assert max(len(line.encode("utf-16-le")) // 2 for line in raw.decode().split("\n")) <= 8192
    assert git(project, "status", "--porcelain").endswith(b"?? unstaged-only.txt\n")


@pytest.mark.parametrize(
    ("filename", "body"),
    [
        (
            "modify.txt",
            "@@ -1,3 +1,3 @@\n 上下文 α\n-old value\n+new value 🌍\n 尾部 Ω\n",
        ),
        ("delete.txt", "@@ -1,2 +0,0 @@\n-removed first\n-删除第二行 🌍\n"),
        (
            "multiple-hunks.txt",
            "@@ -1,5 +1,5 @@\n context 01\n-context 02\n+first changed 🌍\n"
            " context 03\n context 04\n context 05\n"
            "@@ -26,5 +26,5 @@ context 25\n context 26\n context 27\n context 28\n"
            "-context 29\n+last changed 中文\n context 30\n",
        ),
        (
            "crlf.txt",
            "@@ -1,3 +1,3 @@\n CRLF context\r\n-old CRLF\r\n+new CRLF\r\n CRLF tail\r\n",
        ),
        (
            "no-final-newline.txt",
            "@@ -1,2 +1,2 @@\n line one\n-old tail\n\\ No newline at end of file\n"
            "+新尾 🌍\n\\ No newline at end of file\n",
        ),
    ],
)
def test_native_real_git_patch_matches_expected_unified_rows(
    project: Path, filename: str, body: str
) -> None:
    raw = patch(project, filename)
    assert raw[raw.index(b"@@ ") :] == body.encode()
    assert raw.count(b"diff --git ") == 1
    assert len(raw) < 256 * 1024


def test_native_long_line_fixture_is_complete_above_renderer_line_limit(project: Path) -> None:
    raw = patch(project, "long-line.txt")
    assert b"+" + b"L" * 9000 + b"\n" in raw
    assert raw.endswith("+完整末尾 🌍\n".encode())
    assert len(raw) < 256 * 1024
    assert len(raw.split(b"\n")) < 4000
