"""Source snapshot policy tests. No UID change, sockets, or dependency installation."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from a3_native_fixture import FixtureChildError
from a3_native_sources import (
    FIXTURE_FILES,
    PACKAGE_DIRS,
    copy_sources,
    inventory_digest,
    prepare_sources,
    probe_sources,
    source_inventory,
    verify_root_snapshot,
)


@pytest.fixture
def checkout(tmp_path: Path) -> Any:
    root = tmp_path / "checkout"
    for relative in PACKAGE_DIRS:
        folder = root / relative
        folder.mkdir(parents=True)
        (folder / "__init__.py").write_text("# synthetic public source\n")
    for relative in FIXTURE_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# synthetic fixture\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "--", "."], check=True)
    try:
        yield root
    finally:
        # Only these test-created snapshot directories are made removable.
        for directory, _, _ in os.walk(tmp_path):
            os.chmod(directory, 0o755)


def test_exact_fixed_snapshot_preserves_bytes_and_read_only_modes(
    checkout: Path, tmp_path: Path
) -> None:
    inventory = source_inventory(checkout)
    before = inventory_digest(inventory)
    destination = tmp_path / "source"
    assert copy_sources(checkout, destination, inventory) == before
    assert source_inventory(destination, tuple(inventory)) == inventory
    assert len(inventory) == len(PACKAGE_DIRS) + len(FIXTURE_FILES)
    for path in inventory:
        assert stat.S_IMODE((destination / path).stat().st_mode) == 0o444
    assert stat.S_IMODE(destination.stat().st_mode) == 0o555
    assert stat.S_IMODE(checkout.stat().st_mode) != 0o555


@pytest.mark.parametrize("kind", ["symlink", "fifo", "hardlink"])
def test_source_snapshot_refuses_symlinks_and_special_files(
    checkout: Path, tmp_path: Path, kind: str
) -> None:
    target = checkout / PACKAGE_DIRS[0] / "__init__.py"
    target.unlink()
    if kind == "symlink":
        target.symlink_to(tmp_path / "outside")
    elif kind == "hardlink":
        outside = tmp_path / "outside"
        outside.write_text("do-not-copy-linked-canary")
        os.link(outside, target)
    else:
        os.mkfifo(target)
    with pytest.raises((ValueError, OSError)):
        source_inventory(checkout)


def test_changed_source_is_detected_before_snapshot_becomes_read_only(
    checkout: Path, tmp_path: Path
) -> None:
    inventory = source_inventory(checkout)
    (checkout / FIXTURE_FILES[0]).write_text("changed\n")
    with pytest.raises(ValueError, match="digest mismatch"):
        copy_sources(checkout, tmp_path / "source", inventory)


def test_readable_checkout_never_triggers_copy(
    checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("a3_native_sources.os.geteuid", lambda: 0)
    monkeypatch.setattr("a3_native_sources.probe_sources", lambda *args: True)
    selected, proof = prepare_sources(checkout, tmp_path, {})
    assert selected == checkout and proof["source_staged"] is False
    assert not (tmp_path / "source").exists()


def test_only_measured_source_permission_failure_can_trigger_copy(
    checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("a3_native_sources.os.geteuid", lambda: 0)
    calls: list[tuple[Path, int]] = []

    def probe(root: Path, inventory: Any, uid: int, *args: Any) -> bool:
        calls.append((root, uid))
        return root != checkout

    monkeypatch.setattr("a3_native_sources.probe_sources", probe)
    verified: list[Path] = []
    monkeypatch.setattr(
        "a3_native_sources.verify_root_snapshot", lambda root, paths: verified.append(root)
    )
    selected, proof = prepare_sources(checkout, tmp_path, {})
    assert selected == tmp_path / "source" and proof["source_staged"] is True
    assert verified == [selected]
    assert calls == [(checkout, 61131), (checkout, 61132), (selected, 61131), (selected, 61132)]


@pytest.mark.parametrize(
    "reply,denied",
    [
        ({"readable": True}, False),
        ({"readable": False, "phase": "source-access", "code": "PermissionError"}, True),
    ],
)
def test_probe_accepts_only_exact_readability_result(
    checkout: Path, monkeypatch: pytest.MonkeyPatch, reply: dict[str, Any], denied: bool
) -> None:
    manifest = tuple(source_inventory(checkout))
    monkeypatch.setattr("a3_native_sources.tracked_manifest", lambda root: manifest)
    monkeypatch.setattr(
        "a3_native_sources.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(reply).encode()),
    )
    assert (
        probe_sources(checkout, source_inventory(checkout), 61131, 61131, "api", {}) is not denied
    )


@pytest.mark.parametrize(
    "phase,code", [("dependency-access", "PermissionError"), ("source-access", "FileNotFoundError")]
)
def test_dependency_or_missing_source_failure_is_not_a_copy_fallback(
    checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str, code: str
) -> None:
    monkeypatch.setattr("a3_native_sources.os.geteuid", lambda: 0)
    reply = {"readable": False, "phase": phase, "code": code}
    manifest = tuple(source_inventory(checkout))
    monkeypatch.setattr("a3_native_sources.tracked_manifest", lambda root: manifest)
    monkeypatch.setattr(
        "a3_native_sources.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(reply).encode()),
    )
    with pytest.raises(FixtureChildError) as failure:
        prepare_sources(checkout, tmp_path, {})
    assert failure.value.phase == phase and failure.value.code == code
    assert not (tmp_path / "source").exists()


def test_non_source_and_untracked_canaries_are_never_copied(checkout: Path, tmp_path: Path) -> None:
    package = checkout / PACKAGE_DIRS[0]
    for name in (".env", "private.key", "data.db", "debug.log"):
        (package / name).write_text("private-canary-absent-from-snapshot")
    subprocess.run(["git", "-C", str(checkout), "add", "--", "."], check=True)
    (package / "untracked.py").write_text("untracked-canary")
    inventory = source_inventory(checkout)
    assert not any(b"canary" in raw for raw in inventory.values())
    target = tmp_path / "snapshot"
    copy_sources(checkout, target, inventory)
    for name in (".env", "private.key", "data.db", "debug.log", "untracked.py"):
        assert not (target / PACKAGE_DIRS[0] / name).exists()


@pytest.mark.parametrize(
    "error,code",
    [
        (PermissionError(), "PermissionError"),
        (subprocess.TimeoutExpired("fixed-probe", 5), "TimeoutError"),
    ],
)
def test_probe_launch_and_timeout_errors_are_bounded_not_copy_fallback(
    checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: BaseException, code: str
) -> None:
    monkeypatch.setattr("a3_native_sources.os.geteuid", lambda: 0)

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise error

    monkeypatch.setattr("a3_native_sources.subprocess.run", fail)
    monkeypatch.setattr("a3_native_sources.tracked_manifest", lambda root: tuple(FIXTURE_FILES))
    with pytest.raises(FixtureChildError) as failure:
        prepare_sources(checkout, tmp_path, {})
    assert failure.value.phase == "source-probe" and failure.value.code == code
    assert not (tmp_path / "source").exists()


def test_snapshot_publish_checks_filesystem_owner_instead_of_euid(
    checkout: Path, tmp_path: Path
) -> None:
    inventory = source_inventory(checkout)
    target = tmp_path / "source"
    copy_sources(checkout, target, inventory)
    if target.stat().st_uid == 0:
        verify_root_snapshot(target, tuple(inventory))
        target.chmod(0o755)
    with pytest.raises(PermissionError, match="owner or mode"):
        verify_root_snapshot(target, tuple(inventory))
