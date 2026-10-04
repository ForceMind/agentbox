from __future__ import annotations

import asyncio
import base64
import dataclasses
import os
import struct
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from agentbox_runtime.git_changes import parse_git_change_page
from agentbox_runtime.git_staged_reader import GitStagedPatchReader
from agentbox_runtime.git_staged_selection import observe_staged_snapshot
from agentbox_runtime.git_staged_selectors import GitStagedSelectors, StagedSelectorContext
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_lifecycle import WAWProjectBinding
from test_git_staged_reader import LocalGitRunner, reader, repository, stage

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="staged view is Linux-only")
_PROJECT = "prj_" + "a" * 32
_SCOPE = b"s" * 32


class Context:
    """Explicit fixture, not production READY/active-session admission.

    Echoing scope lets cross-scope tests isolate token binding. The separate
    revoke case exercises resolver denial; real session admission is uncomposed.
    """

    def __init__(self) -> None:
        self.current: StagedSelectorContext | None = StagedSelectorContext(
            WAWProjectBinding(
                _PROJECT, "formal-project", "1", "1", "b" * 64, "wri_" + "c" * 32, "1"
            ),
            "1",
            _SCOPE,
        )
        self.calls = 0
        self.on_call: Callable[[], None] | None = None

    def __call__(self, project: str, scope: bytes) -> StagedSelectorContext | None:
        self.calls += 1
        if self.on_call is not None:
            self.on_call()
        if self.current is None:
            return None
        return dataclasses.replace(self.current, session_scope=scope)


def setup(
    tmp_path: Path, runner: LocalGitRunner | None = None
) -> tuple[GitStagedSelectors, Path, LocalGitRunner, Context, GitStagedPatchReader]:
    root, project = repository(tmp_path)
    (project / "modified.txt").write_text("staged secret-canary content\n", encoding="utf-8")
    stage(project, "modified.txt")
    runner = runner or LocalGitRunner()
    reader_ = reader(root, runner)
    context = Context()
    return GitStagedSelectors(reader_, context=context), project, runner, context, reader_


async def token(owner: GitStagedSelectors) -> str:
    result = await owner.observe(_PROJECT, _SCOPE)
    assert result.schema_version == "runtime-staged-observation-v2"
    selected = next(entry for entry in result.entries if entry.path == "modified.txt")
    assert selected.selection_id is not None
    assert len(selected.selection_id) == 156
    assert selected.selection_id not in repr(result)
    return selected.selection_id


async def stale(
    owner: GitStagedSelectors, selection: str, *, scope: bytes = _SCOPE, project: str = _PROJECT
) -> None:
    with pytest.raises(RuntimeOperationError) as raised:
        await owner.read(project, scope, selection)
    assert raised.value.code == "PATCH_STALE"
    assert selection not in str(raised.value)


@pytest.mark.anyio
@pytest.mark.parametrize("native", [False, True])
async def test_roundtrip_staged_only_no_logs_or_token_in_git(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, native: bool
) -> None:
    owner, project, runner, _, _ = setup(tmp_path, LocalGitRunner(native=native))
    selection = await token(owner)
    assert not any("--patch" in command for command in runner.argv)
    (project / "modified.txt").write_text("unstaged must not appear\n", encoding="utf-8")
    result = await owner.read(_PROJECT, _SCOPE, selection)
    assert "staged secret-canary content" in result.patch
    assert "unstaged must not appear" not in result.patch
    assert runner.diff_count == 2
    assert selection not in repr(runner.argv)
    assert selection not in caplog.text and "secret-canary" not in caplog.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "delta,valid",
    [(0, True), (29_999_999_999, True), (30_000_000_000, False), (30_000_000_001, False)],
)
async def test_exact_monotonic_expiry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, delta: int, valid: bool
) -> None:
    now = [100_000_000_000]
    monkeypatch.setattr(time, "monotonic_ns", lambda: now[0])
    owner, _, runner, _, _ = setup(tmp_path)
    selection = await token(owner)
    now[0] += delta
    if valid:
        assert (await owner.read(_PROJECT, _SCOPE, selection)).selection.path == "modified.txt"
    else:
        await stale(owner, selection)
        assert runner.diff_count == 0


@pytest.mark.anyio
async def test_regressing_clock_and_closed_owner_are_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [100_000_000_000]
    monkeypatch.setattr(time, "monotonic_ns", lambda: now[0])
    owner, _, _, _, _ = setup(tmp_path)
    selection = await token(owner)
    now[0] -= 1
    await stale(owner, selection)
    now[0] += 2
    await stale(owner, selection)
    owner.close()
    with pytest.raises(RuntimeOperationError):
        await owner.observe(_PROJECT, _SCOPE)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "changed",
    [
        "scope",
        "project",
        "epoch",
        "binding",
        "revision",
        "relative_key",
        "host",
        "revoke",
        "restart",
        "fork",
    ],
)
async def test_context_mismatches_fail_before_patch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    owner, _, runner, context, reader_ = setup(tmp_path)
    selection = await token(owner)
    assert context.current is not None
    kwargs: dict[str, bytes | str] = {}
    if changed == "scope":
        kwargs["scope"] = b"t" * 32
    elif changed == "project":
        kwargs["project"] = "prj_" + "d" * 32
    elif changed == "epoch":
        context.current = dataclasses.replace(context.current, runtime_epoch="2")
    elif changed == "revoke":
        context.current = None
    elif changed == "restart":
        owner = GitStagedSelectors(reader_, context=context)
    elif changed == "fork":
        monkeypatch.setattr(os, "getpid", lambda: -1)
    else:
        key, value = {
            "binding": ("binding_digest", "f" * 64),
            "revision": ("binding_revision", "2"),
            "relative_key": ("relative_key", "other"),
            "host": ("runtime_host_installation_revision", "2"),
        }[changed]
        context.current = dataclasses.replace(
            context.current, binding=dataclasses.replace(context.current.binding, **{key: value})
        )
    await stale(
        owner,
        selection,
        scope=cast(bytes, kwargs.get("scope", _SCOPE)),
        project=cast(str, kwargs.get("project", _PROJECT)),
    )
    assert runner.diff_count == 0


@pytest.mark.anyio
@pytest.mark.parametrize(
    "mutation",
    [
        "version",
        "issued",
        "expiry",
        "entry",
        "snapshot",
        "context",
        "mac",
        "short",
        "long",
        "padding",
        "alphabet",
    ],
)
async def test_tampered_fixed_token_rejected(tmp_path: Path, mutation: str) -> None:
    owner, _, runner, _, _ = setup(tmp_path)
    selection = await token(owner)
    raw = bytearray(base64.urlsafe_b64decode(selection))
    offsets = {
        "version": 0,
        "issued": 1,
        "expiry": 9,
        "entry": 17,
        "snapshot": 21,
        "context": 53,
        "mac": 85,
    }
    if mutation in offsets:
        raw[offsets[mutation]] ^= 1
        selection = base64.urlsafe_b64encode(raw).decode("ascii")
    else:
        selection = {
            "short": selection[:-1],
            "long": selection + "A",
            "padding": selection[:-1] + "=",
            "alphabet": "!" + selection[1:],
        }[mutation]
    await stale(owner, selection)
    assert runner.diff_count == 0


@pytest.mark.anyio
@pytest.mark.parametrize("other", [False, True])
async def test_index_content_change_with_identical_v1_display_metadata_invalidates(
    tmp_path: Path, other: bool
) -> None:
    owner, project, runner, _, _ = setup(tmp_path)
    if other:
        (project / "added.txt").write_text("first\n", encoding="utf-8")
        stage(project, "added.txt")
    selection = await token(owner)
    path = "added.txt" if other else "modified.txt"
    (project / path).write_text("second\n", encoding="utf-8")
    stage(project, path)
    await stale(owner, selection)
    assert runner.diff_count == 0


def test_full_digest_includes_every_row_and_field_and_is_sorted() -> None:
    first = b"1 M. N... 100644 100644 100644 " + b"a" * 40 + b" " + b"b" * 40 + b" a.txt\0"
    second = first.replace(b"a.txt", b".env")
    observed = observe_staged_snapshot(first + second)
    assert observed == observe_staged_snapshot(second + first)
    assert observed.entries[0].selection is None
    assert observed.entries[0].unavailable_code == "PATCH_UNAVAILABLE_SENSITIVE_PATH"
    for changed in (
        first.replace(b"b" * 40, b"c" * 40),
        first.replace(b"a" * 40, b"c" * 40),
        first.replace(b"100644", b"100755", 1),
        first.replace(b"100644 100644 100644", b"100644 100755 100755"),
        first.replace(b"a.txt", b"z.txt"),
    ):
        assert observe_staged_snapshot(changed + second).sha256 != observed.sha256
    changed = first.replace(b"b" * 40, b"c" * 40)
    assert parse_git_change_page(first, None) == parse_git_change_page(changed, None)
    assert observe_staged_snapshot(first).sha256 != observe_staged_snapshot(changed).sha256
    assert (
        observe_staged_snapshot(first + second.replace(b"b" * 40, b"d" * 40)).sha256
        != observed.sha256
    )


@pytest.mark.anyio
async def test_no_validate_then_reopen_or_snapshot_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, project, runner, _, reader_ = setup(tmp_path)
    selection = await token(owner)
    original = reader_._read_observed
    entered = 0

    async def swapped(*args: object, **kwargs: object) -> object:
        nonlocal entered
        entered += 1
        (project / "modified.txt").write_text("race replacement\n", encoding="utf-8")
        stage(project, "modified.txt")
        return await original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(reader_, "_read_observed", swapped)
    await stale(owner, selection)
    assert entered == 1 and runner.diff_count == 0


@pytest.mark.anyio
async def test_expiry_during_observation_denies_actual_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [100_000_000_000]
    monkeypatch.setattr(time, "monotonic_ns", lambda: now[0])
    owner, _, runner, _, _ = setup(tmp_path)
    selection = await token(owner)
    runner.before_first_status = lambda: now.__setitem__(0, now[0] + 30_000_000_000)
    await stale(owner, selection)
    assert runner.diff_count == 0


@pytest.mark.anyio
@pytest.mark.parametrize("mutation", ["revoke", "epoch", "close", "expiry"])
async def test_inflight_changes_discard_plaintext(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    now = [100_000_000_000]
    monkeypatch.setattr(time, "monotonic_ns", lambda: now[0])
    owner, _, runner, context, _ = setup(tmp_path)
    selection = await token(owner)

    def change() -> None:
        if mutation == "revoke":
            context.current = None
        elif mutation == "epoch":
            assert context.current is not None
            context.current = dataclasses.replace(context.current, runtime_epoch="2")
        elif mutation == "close":
            owner.close()
        else:
            now[0] += 30_000_000_000

    runner.after_first_diff = change
    await stale(owner, selection)
    assert runner.diff_count == 1


@pytest.mark.anyio
async def test_concurrency_cancel_cleanup_and_capacity_reuse(tmp_path: Path) -> None:
    owner, _, runner, _, _ = setup(tmp_path)
    selection = await token(owner)
    runner.block_on_diff = True
    baseline = set(os.listdir("/proc/self/fd"))
    tasks = [asyncio.create_task(owner.read(_PROJECT, _SCOPE, selection)) for _ in range(4)]
    for _ in range(100):
        if len([cmd for cmd in runner.argv if "--patch" in cmd]) == 4:
            break
        await asyncio.sleep(0.01)
    assert len([cmd for cmd in runner.argv if "--patch" in cmd]) == 4
    with pytest.raises(RuntimeOperationError) as raised:
        await owner.read(_PROJECT, _SCOPE, selection)
    assert raised.value.code == "PATCH_UNAVAILABLE_BUSY"
    for task in tasks:
        task.cancel()
    for task in tasks:
        with pytest.raises(asyncio.CancelledError):
            await task
    assert set(os.listdir("/proc/self/fd")) == baseline
    runner.block_on_diff = False
    assert (await owner.read(_PROJECT, _SCOPE, selection)).selection.path == "modified.txt"


def test_no_public_api_worker_or_wire_composition() -> None:
    root = Path(__file__).parents[2]
    for directory in (root / "apps", root / "packages/agentbox-protocol"):
        for path in directory.rglob("*.py"):
            assert "git_staged_selectors" not in path.read_text(encoding="utf-8")
    assert struct.calcsize(">BQQI32s32s") + 32 == 117


@pytest.mark.anyio
async def test_unsupported_entries_receive_no_selector(tmp_path: Path) -> None:
    owner, project, _, _, _ = setup(tmp_path)
    (project / ".env").write_text("sensitive\n", encoding="utf-8")
    (project / "link").symlink_to("modified.txt")
    os.chmod(project / "deleted.txt", 0o755)
    stage(project, ".env", "link", "deleted.txt")
    result = await owner.observe(_PROJECT, _SCOPE)
    entries = {entry.path: entry for entry in result.entries}
    assert entries[".env"].unavailable_code == "PATCH_UNAVAILABLE_SENSITIVE_PATH"
    assert entries["link"].unavailable_code == "PATCH_UNAVAILABLE_MODE"
    assert entries["deleted.txt"].unavailable_code == "PATCH_UNAVAILABLE_MODE"
    assert all(entries[path].selection_id is None for path in (".env", "link", "deleted.txt"))


@pytest.mark.anyio
@pytest.mark.parametrize("scope", [b"", b"short", b"x" * 33, "cookie=value", None, 32])
async def test_untrusted_scope_shape_has_no_git_execution(tmp_path: Path, scope: object) -> None:
    owner, _, runner, _, _ = setup(tmp_path)
    with pytest.raises(RuntimeOperationError):
        await owner.observe(_PROJECT, cast(bytes, scope))
    assert runner.argv == []


@pytest.mark.anyio
async def test_binding_drift_during_metadata_observation(tmp_path: Path) -> None:
    owner, _, runner, context, _ = setup(tmp_path)

    def change() -> None:
        assert context.current is not None
        context.current = dataclasses.replace(context.current, runtime_epoch="2")

    runner.before_first_status = change
    with pytest.raises(RuntimeOperationError) as raised:
        await owner.observe(_PROJECT, _SCOPE)
    assert raised.value.code == "PATCH_STALE"
    assert runner.diff_count == 0


@pytest.mark.anyio
async def test_cancel_observation_releases_view_and_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, _, _, _, reader_ = setup(tmp_path)
    original = reader_._status
    blocked = asyncio.Event()
    release = asyncio.Event()
    baseline = set(os.listdir("/proc/self/fd"))

    async def status(*args: object) -> bytes:
        result = await original(*args)  # type: ignore[arg-type]
        blocked.set()
        await release.wait()
        return result

    monkeypatch.setattr(reader_, "_status", status)
    task = asyncio.create_task(owner.observe(_PROJECT, _SCOPE))
    await blocked.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert set(os.listdir("/proc/self/fd")) == baseline
    monkeypatch.setattr(reader_, "_status", original)
    assert await token(owner)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure,expected",
    [("GIT_COMMAND_TIMEOUT", "PATCH_TIMEOUT"), ("GIT_OUTPUT_LIMIT_EXCEEDED", "PATCH_TOO_LARGE")],
)
async def test_reader_failure_cleans_selector_resources(
    tmp_path: Path, failure: str, expected: str
) -> None:
    owner, _, runner, _, _ = setup(tmp_path)
    selection = await token(owner)
    baseline = set(os.listdir("/proc/self/fd"))
    runner.fail_diff_code = failure
    with pytest.raises(RuntimeOperationError) as raised:
        await owner.read(_PROJECT, _SCOPE, selection)
    assert raised.value.code == expected
    assert set(os.listdir("/proc/self/fd")) == baseline


@pytest.mark.anyio
async def test_entry_index_is_from_full_sorted_snapshot(tmp_path: Path) -> None:
    owner, project, _, _, _ = setup(tmp_path)
    (project / "aaa.txt").write_text("new first entry\n", encoding="utf-8")
    stage(project, "aaa.txt")
    result = await owner.observe(_PROJECT, _SCOPE)
    assert [entry.entry_index for entry in result.entries] == [0, 1]
    for entry in result.entries:
        assert entry.selection_id is not None
        patch = await owner.read(_PROJECT, _SCOPE, entry.selection_id)
        assert patch.selection.path == entry.path


@pytest.mark.parametrize("mutation", [b"g" * 40, b"1", b"a" * 64])
def test_malformed_full_rows_rejected_even_if_sensitive(mutation: bytes) -> None:
    raw = b"1 M. N... 100644 100644 100644 " + mutation + b" " + b"b" * 40 + b" .env\0"
    with pytest.raises(RuntimeOperationError) as raised:
        observe_staged_snapshot(raw)
    assert raised.value.code == "PATCH_UNAVAILABLE_STATUS"


def test_full_snapshot_digest_extends_beyond_v1_first_page() -> None:
    template = b"1 M. N... 100644 100644 100644 " + b"a" * 40 + b" " + b"b" * 40 + b" "
    rows = [template + f"file-{index:03}.txt".encode() + b"\0" for index in range(40)]
    before = b"".join(rows)
    rows[-1] = rows[-1].replace(b"b" * 40, b"c" * 40)
    after = b"".join(rows)
    assert parse_git_change_page(before, None) == parse_git_change_page(after, None)
    assert len(observe_staged_snapshot(before).entries) == 40
    assert observe_staged_snapshot(before).sha256 != observe_staged_snapshot(after).sha256


@pytest.mark.anyio
async def test_new_entry_changes_sorted_index_and_invalidates_old_selector(tmp_path: Path) -> None:
    owner, project, runner, _, _ = setup(tmp_path)
    selection = await token(owner)
    (project / "aaa.txt").write_text("new entry before selected path\n", encoding="utf-8")
    stage(project, "aaa.txt")
    await stale(owner, selection)
    assert runner.diff_count == 0
    fresh = await token(owner)
    assert (await owner.read(_PROJECT, _SCOPE, fresh)).selection.path == "modified.txt"
