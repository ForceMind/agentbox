"""Synthetic Linux ownership/header policy with real OS descriptors; never exec.

The fixture projects only root-ownership and ancestor permission evidence onto a
temporary tree owned by the test user, and injects a non-root Linux identity.
It does not chown, read Runtime HOME/keys, or qualify a real Linux installation.
Open/no-follow/pread/rename/close operations use actual OS file descriptors.
"""

from __future__ import annotations

import gc
import hashlib
import os
import platform
import stat
import struct
import sys
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, dataclass, field
from pathlib import Path
from typing import cast

import pytest
from agentbox_runtime import waw_executable as subject
from agentbox_runtime.waw_executable import (
    WAWExecutableError,
    WAWExecutableInventory,
    WAWExecutableKind,
    WAWExecutablePin,
)


def _elf() -> bytes:
    # A synthetic ELF64 header, deliberately not an executable program.
    content = bytearray(256)
    content[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HHI", content, 16, 2, 62, 1)
    struct.pack_into("<H", content, 52, 64)
    return bytes(content)


@dataclass
class _SyntheticTree:
    root: Path
    path: Path
    original: bytes
    opened: list[int] = field(default_factory=list)
    live: set[int] = field(default_factory=set)
    overrides: dict[tuple[int, int], dict[str, int]] = field(default_factory=dict)

    def pin(self, *, max_bytes: int = 1024) -> WAWExecutablePin:
        return WAWExecutablePin(self.path, hashlib.sha256(self.original).hexdigest(), max_bytes)

    def inventory(self, *, max_bytes: int = 1024) -> WAWExecutableInventory:
        return WAWExecutableInventory({WAWExecutableKind.CODEX: self.pin(max_bytes=max_bytes)})

    def change_evidence(self, path: Path, **fields: int) -> None:
        details = path.lstat()
        self.overrides[(details.st_dev, details.st_ino)] = fields


@pytest.fixture
def synthetic_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_SyntheticTree]:
    root = tmp_path.resolve()
    parent = root / "immutable" / "bin"
    parent.mkdir(parents=True, mode=0o755)
    path = parent / "native-agent"
    raw = _elf()
    path.write_bytes(raw)
    path.chmod(0o755)
    tree = _SyntheticTree(root, path, raw)
    external = {(p.stat().st_dev, p.stat().st_ino) for p in root.parents}
    real_open, real_fstat, real_stat_at, real_close = (
        subject._open,
        subject._fstat,
        subject._stat_at,
        subject._close,
    )

    def project(details: os.stat_result) -> os.stat_result:
        values = list(details)
        values[stat.ST_UID] = 0  # Synthetic installer ownership, not host evidence.
        if (details.st_dev, details.st_ino) in external:
            values[stat.ST_MODE] = details.st_mode & ~0o022  # Synthetic safe ancestry.
        fields = tree.overrides.get((details.st_dev, details.st_ino), {})
        indexes = {
            "st_mode": stat.ST_MODE,
            "st_uid": stat.ST_UID,
            "st_gid": stat.ST_GID,
            "st_ino": stat.ST_INO,
            "st_dev": stat.ST_DEV,
            "st_size": stat.ST_SIZE,
            "st_nlink": stat.ST_NLINK,
        }
        ns = {
            "st_atime_ns": details.st_atime_ns,
            "st_mtime_ns": details.st_mtime_ns,
            "st_ctime_ns": details.st_ctime_ns,
        }
        for key, value in fields.items():
            if key in indexes:
                values[indexes[key]] = value
            else:
                ns[key] = value
        return os.stat_result(values, ns)

    def tracked_open(name: str, flags: int, *, dir_fd: int | None = None) -> int:
        assert flags & os.O_NOFOLLOW
        assert flags & os.O_CLOEXEC
        assert flags & os.O_NONBLOCK
        assert (name == "/" and dir_fd is None) or ("/" not in name and dir_fd in tree.live)
        descriptor = real_open(name, flags, dir_fd=dir_fd)
        assert not os.get_inheritable(descriptor)
        tree.opened.append(descriptor)
        tree.live.add(descriptor)
        return descriptor

    def tracked_close(descriptor: int) -> None:
        assert descriptor in tree.live
        tree.live.remove(descriptor)
        real_close(descriptor)

    monkeypatch.setattr(subject, "_runtime_identity", lambda: ("linux", "x86_64", 12345))
    monkeypatch.setattr(subject, "_fstat", lambda descriptor: project(real_fstat(descriptor)))
    monkeypatch.setattr(
        subject, "_stat_at", lambda name, parent: project(real_stat_at(name, parent))
    )
    monkeypatch.setattr(subject, "_open", tracked_open)
    monkeypatch.setattr(subject, "_close", tracked_close)
    yield tree
    assert not tree.live, "verifier leaked real descriptors"


def test_synthetic_inventory_pins_and_holds_real_descriptor_chain(
    synthetic_tree: _SyntheticTree,
) -> None:
    tree = synthetic_tree
    with tree.inventory().open(WAWExecutableKind.CODEX) as verified:
        identity = verified.identity
        assert identity.path == tree.path
        assert identity.sha256 == hashlib.sha256(tree.original).hexdigest()
        assert identity.uid == 0  # Projected ownership, not an assertion about this host.
        assert identity.size == len(tree.original)
        assert identity.inode == tree.path.stat().st_ino
        assert len(tree.live) == len(tree.path.parts)
        assert verified.revalidate() is identity
        with pytest.raises(FrozenInstanceError):
            identity.sha256 = "b" * 64  # type: ignore[misc]
    assert verified.closed
    verified.close()
    with pytest.raises(WAWExecutableError, match="closed"):
        verified.revalidate()
    with pytest.raises(WAWExecutableError, match="closed"):
        verified.__enter__()


def test_inventory_copies_trusted_pins_and_requires_closed_kinds(
    synthetic_tree: _SyntheticTree,
) -> None:
    pins = {WAWExecutableKind.CODEX: synthetic_tree.pin()}
    inventory = WAWExecutableInventory(pins)
    pins.clear()
    with inventory.open(WAWExecutableKind.CODEX):
        pass
    for kind in (WAWExecutableKind.CLAUDE, "codex", None, 1):
        with pytest.raises(WAWExecutableError):
            inventory.open(cast(WAWExecutableKind, kind))


@pytest.mark.parametrize(
    "path",
    [
        "not-a-Path",
        Path("relative"),
        Path("/"),
        Path("//root/bin"),
        Path("/root/../bin"),
        Path("/a/\x00"),
        Path("/" + "a" * 4096),
        Path("/" + "/".join(["a"] * 129)),
    ],
)
def test_inventory_rejects_malformed_paths(path: object) -> None:
    with pytest.raises(WAWExecutableError):
        WAWExecutablePin(cast(Path, path), "a" * 64)


@pytest.mark.parametrize("digest", [None, "", "a" * 63, "A" * 64, "a" * 64 + "\n", 1])
def test_inventory_rejects_unknown_digest_types_and_values(digest: object) -> None:
    with pytest.raises(WAWExecutableError):
        WAWExecutablePin(Path("/opt/fixed/native"), cast(str, digest))


@pytest.mark.parametrize("limit", [True, None, 0, 63, 256 * 1024 * 1024 + 1, 128.0])
def test_inventory_byte_limit_is_strict_and_capped(limit: object) -> None:
    with pytest.raises(WAWExecutableError):
        WAWExecutablePin(Path("/opt/fixed/native"), "a" * 64, cast(int, limit))


def test_inventory_rejects_untyped_entries() -> None:
    for pins in (
        None,
        {"codex": WAWExecutablePin(Path("/opt/fixed/native"), "a" * 64)},
        {WAWExecutableKind.CODEX: {"path": "/opt/fixed/native"}},
    ):
        with pytest.raises(WAWExecutableError):
            WAWExecutableInventory(cast(dict[WAWExecutableKind, WAWExecutablePin], pins))


@pytest.mark.parametrize(
    "identity",
    [
        ("darwin", "arm64", 501),
        ("linux", "aarch64", 12345),
        ("linux", "x86_64", 0),
    ],
)
def test_unsupported_runtime_fails_before_open(
    synthetic_tree: _SyntheticTree, monkeypatch: pytest.MonkeyPatch, identity: tuple[str, str, int]
) -> None:
    monkeypatch.setattr(subject, "_runtime_identity", lambda: identity)
    with pytest.raises(WAWExecutableError, match="non-root Linux x86_64"):
        synthetic_tree.inventory().open(WAWExecutableKind.CODEX)
    assert not synthetic_tree.opened


@pytest.mark.parametrize("location", ["file", "parent", "ancestor", "root"])
@pytest.mark.parametrize("change", ["owner", "group-write", "world-write"])
def test_unsafe_file_or_any_ancestor_is_rejected(
    synthetic_tree: _SyntheticTree, location: str, change: str
) -> None:
    tree = synthetic_tree
    path = {
        "file": tree.path,
        "parent": tree.path.parent,
        "ancestor": tree.root,
        "root": Path("/"),
    }[location]
    if change == "owner":
        tree.change_evidence(path, st_uid=12345)
    else:
        mode = path.stat().st_mode & ~0o022
        tree.change_evidence(path, st_mode=mode | (0o020 if change == "group-write" else 0o002))
    with pytest.raises(WAWExecutableError, match="unsafe"):
        tree.inventory().open(WAWExecutableKind.CODEX)


@pytest.mark.parametrize("mode", [0o644, 0o754, 0o751, 0o4755, 0o2755])
def test_executable_requires_read_execute_and_no_special_privilege(
    synthetic_tree: _SyntheticTree, mode: int
) -> None:
    # Special mode bits may be stripped by the macOS test filesystem. This is
    # explicitly synthetic permission evidence and never sets a privileged file.
    synthetic_tree.change_evidence(synthetic_tree.path, st_mode=stat.S_IFREG | mode)
    with pytest.raises(WAWExecutableError):
        synthetic_tree.inventory().open(WAWExecutableKind.CODEX)


@pytest.mark.parametrize("level", ["file", "parent", "ancestor"])
def test_real_symlinks_are_not_followed(synthetic_tree: _SyntheticTree, level: str) -> None:
    tree = synthetic_tree
    path = {"file": tree.path, "parent": tree.path.parent, "ancestor": tree.path.parent.parent}[
        level
    ]
    moved = path.with_name(path.name + "-real")
    path.rename(moved)
    path.symlink_to(moved)
    with pytest.raises(WAWExecutableError):
        tree.inventory().open(WAWExecutableKind.CODEX)


@pytest.mark.parametrize("file_type", ["directory", "fifo"])
def test_non_regular_files_are_rejected_without_reading(
    synthetic_tree: _SyntheticTree, monkeypatch: pytest.MonkeyPatch, file_type: str
) -> None:
    path = synthetic_tree.path
    path.unlink()
    if file_type == "directory":
        path.mkdir()
    else:
        os.mkfifo(path)

    def forbidden_read(fd: int, length: int, offset: int) -> bytes:
        pytest.fail("non-regular path must never reach a read")

    monkeypatch.setattr(subject, "_pread", forbidden_read)
    with pytest.raises(WAWExecutableError):
        synthetic_tree.inventory().open(WAWExecutableKind.CODEX)


@pytest.mark.parametrize(
    "offset,replacement",
    [
        (0, b"#!/bin/sh"),
        (0, b"\xcf\xfa\xed\xfe"),
        (4, b"\x01"),
        (5, b"\x02"),
        (6, b"\x00"),
        (7, b"\xff"),
        (8, b"\x01"),
        (16, b"\x01\x00"),
        (18, b"\xb7\x00"),
        (20, b"\x00\x00\x00\x00"),
        (52, b"\x00\x00"),
    ],
)
def test_pinned_shebang_foreign_and_invalid_elf_headers_fail_closed(
    synthetic_tree: _SyntheticTree, offset: int, replacement: bytes
) -> None:
    tree = synthetic_tree
    raw = bytearray(tree.original)
    raw[offset : offset + len(replacement)] = replacement
    tree.original = bytes(raw)
    tree.path.write_bytes(tree.original)
    with pytest.raises(WAWExecutableError, match="Linux x86_64 ELF"):
        tree.inventory().open(WAWExecutableKind.CODEX)


def test_pie_header_is_supported_without_runnability_claim(synthetic_tree: _SyntheticTree) -> None:
    raw = bytearray(synthetic_tree.original)
    struct.pack_into("<H", raw, 16, 3)
    synthetic_tree.original = bytes(raw)
    synthetic_tree.path.write_bytes(synthetic_tree.original)
    with synthetic_tree.inventory().open(WAWExecutableKind.CODEX):
        pass


def test_wrong_digest_and_oversize_close_every_descriptor(synthetic_tree: _SyntheticTree) -> None:
    tree = synthetic_tree
    tree.path.write_bytes(tree.original[:-1] + b"x")
    with pytest.raises(WAWExecutableError, match="pin does not match"):
        tree.inventory().open(WAWExecutableKind.CODEX)
    assert not tree.live
    with pytest.raises(WAWExecutableError, match="size"):
        tree.inventory(max_bytes=64).open(WAWExecutableKind.CODEX)


def test_hash_handles_short_reads_and_exact_limit(
    synthetic_tree: _SyntheticTree, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_read = subject._pread
    reads: list[tuple[int, int]] = []

    def short_read(fd: int, length: int, offset: int) -> bytes:
        reads.append((length, offset))
        return original_read(fd, min(length, 13), offset)

    monkeypatch.setattr(subject, "_pread", short_read)
    with synthetic_tree.inventory(max_bytes=256).open(WAWExecutableKind.CODEX) as verified:
        assert verified.revalidate() == verified.identity
    assert reads[-1] == (1, 256)
    assert all(0 < length <= 257 for length, _ in reads)


def test_growth_during_hash_is_bounded_and_closes_descriptors(
    synthetic_tree: _SyntheticTree, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_read = subject._pread
    reads: list[int] = []

    def grow(fd: int, length: int, offset: int) -> bytes:
        reads.append(length)
        if offset == 0:
            with synthetic_tree.path.open("ab") as stream:
                stream.write(b"x" * 1000)
        return original_read(fd, length, offset)

    monkeypatch.setattr(subject, "_pread", grow)
    with pytest.raises(WAWExecutableError, match="byte limit"):
        synthetic_tree.inventory(max_bytes=256).open(WAWExecutableKind.CODEX)
    assert sum(reads) <= 257


@pytest.mark.parametrize(
    "mutation", ["replace", "rewrite", "truncate", "chmod", "unlink", "parent"]
)
def test_revalidation_detects_drift_and_permanently_closes_handle(
    synthetic_tree: _SyntheticTree, mutation: str
) -> None:
    tree = synthetic_tree
    verified = tree.inventory().open(WAWExecutableKind.CODEX)
    if mutation == "replace":
        replacement = tree.path.with_name("replacement")
        replacement.write_bytes(tree.original)
        replacement.chmod(0o755)
        replacement.replace(tree.path)
    elif mutation == "rewrite":
        tree.path.write_bytes(tree.original[:-1] + b"x")
    elif mutation == "truncate":
        tree.path.write_bytes(tree.original[:64])
    elif mutation == "chmod":
        tree.path.chmod(0o777)
    elif mutation == "unlink":
        tree.path.unlink()
    else:
        old = tree.path.parent.with_name("previous-bin")
        tree.path.parent.rename(old)
        tree.path.parent.mkdir(mode=0o755)
        tree.path.write_bytes(tree.original)
        tree.path.chmod(0o755)
    with pytest.raises(WAWExecutableError):
        verified.revalidate()
    assert verified.closed
    assert not tree.live
    with pytest.raises(WAWExecutableError, match="closed"):
        verified.revalidate()


def test_ctime_and_digest_fence_rewrite_even_if_mtime_restored(
    synthetic_tree: _SyntheticTree,
) -> None:
    tree = synthetic_tree
    verified = tree.inventory().open(WAWExecutableKind.CODEX)
    before = tree.path.stat()
    tree.path.write_bytes(tree.original[:-1] + b"x")
    os.utime(tree.path, ns=(before.st_atime_ns, before.st_mtime_ns))
    with pytest.raises(WAWExecutableError):
        verified.revalidate()
    assert verified.closed


def test_mutation_after_hash_is_caught_by_repeated_fstat(
    synthetic_tree: _SyntheticTree, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_read = subject._pread

    def modify_after_read(fd: int, length: int, offset: int) -> bytes:
        raw = original_read(fd, length, offset)
        if not raw:
            synthetic_tree.path.chmod(0o700)
        return raw

    monkeypatch.setattr(subject, "_pread", modify_after_read)
    with pytest.raises(WAWExecutableError):
        synthetic_tree.inventory().open(WAWExecutableKind.CODEX)


def test_same_size_mutation_is_hashed_again_despite_synthetic_unchanged_stat(
    synthetic_tree: _SyntheticTree,
) -> None:
    tree = synthetic_tree
    verified = tree.inventory().open(WAWExecutableKind.CODEX)
    observed = verified.identity
    tree.path.write_bytes(tree.original[:-1] + b"x")
    tree.change_evidence(
        tree.path, st_mtime_ns=observed.modified_ns, st_ctime_ns=observed.changed_ns
    )
    with pytest.raises(WAWExecutableError, match="pin does not match"):
        verified.revalidate()


def test_path_swap_between_stat_and_open_is_rejected(
    synthetic_tree: _SyntheticTree, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree = synthetic_tree
    original_open = subject._open

    def swap(name: str, flags: int, *, dir_fd: int | None = None) -> int:
        if name == tree.path.name:
            replacement = tree.path.with_name("replacement")
            replacement.write_bytes(tree.original)
            replacement.chmod(0o755)
            replacement.replace(tree.path)
        return original_open(name, flags, dir_fd=dir_fd)

    monkeypatch.setattr(subject, "_open", swap)
    with pytest.raises(WAWExecutableError, match="changed while opening"):
        tree.inventory().open(WAWExecutableKind.CODEX)


@pytest.mark.parametrize("failure", ["root-open", "leaf-open", "fstat", "read", "interrupt"])
def test_os_errors_and_interrupts_release_partial_descriptor_chain(
    synthetic_tree: _SyntheticTree, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    original_open = subject._open

    def fail_open(name: str, flags: int, *, dir_fd: int | None = None) -> int:
        if name == ("/" if failure == "root-open" else synthetic_tree.path.name):
            raise PermissionError("synthetic open failure")
        return original_open(name, flags, dir_fd=dir_fd)

    def fail_stat(fd: int) -> os.stat_result:
        raise OSError("synthetic fstat failure")

    def fail_read(fd: int, length: int, offset: int) -> bytes:
        if failure == "interrupt":
            raise KeyboardInterrupt
        raise OSError("synthetic read failure")

    if failure in ("root-open", "leaf-open"):
        monkeypatch.setattr(subject, "_open", fail_open)
    elif failure == "fstat":
        monkeypatch.setattr(subject, "_fstat", fail_stat)
    else:
        monkeypatch.setattr(subject, "_pread", fail_read)
    with pytest.raises(KeyboardInterrupt if failure == "interrupt" else WAWExecutableError):
        synthetic_tree.inventory().open(WAWExecutableKind.CODEX)
    assert not synthetic_tree.live


def test_close_and_revalidate_are_serialized_without_recycled_descriptor_reads(
    synthetic_tree: _SyntheticTree, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree = synthetic_tree
    verified = tree.inventory().open(WAWExecutableKind.CODEX)
    reading = threading.Event()
    resume = threading.Event()
    closing = threading.Event()
    original_read = subject._pread

    def blocked_read(fd: int, length: int, offset: int) -> bytes:
        reading.set()
        assert resume.wait(5)
        assert fd in tree.live
        return original_read(fd, length, offset)

    def close() -> None:
        closing.set()
        verified.close()

    monkeypatch.setattr(subject, "_pread", blocked_read)
    with ThreadPoolExecutor(max_workers=2) as pool:
        checked = pool.submit(verified.revalidate)
        try:
            assert reading.wait(5)
            closed = pool.submit(close)
            assert closing.wait(5)
            assert not closed.done()
            assert tree.live
        finally:
            resume.set()
        assert checked.result(timeout=5) == verified.identity
        closed.result(timeout=5)
    assert verified.closed
    assert not tree.live


def test_context_exception_and_abandoned_handle_close_descriptors(
    synthetic_tree: _SyntheticTree,
) -> None:
    with (
        pytest.raises(ValueError, match="context body"),
        synthetic_tree.inventory().open(WAWExecutableKind.CODEX),
    ):
        raise ValueError("context body")
    assert not synthetic_tree.live
    handle = synthetic_tree.inventory().open(WAWExecutableKind.CODEX)
    assert not handle.closed
    del handle
    gc.collect()
    assert not synthetic_tree.live


@pytest.mark.skipif(
    sys.platform != "linux" or platform.machine() != "x86_64" or os.geteuid() == 0,
    reason="read-only native Linux x86_64 non-root descriptor check; never execute",
)
def test_read_only_linux_system_elf_without_synthetic_ownership() -> None:
    path = Path("/usr/bin/true")
    if not path.exists():
        pytest.skip("optional native read-only fixture is absent")
    # /usr/bin/true is a public OS fixture, not a Runtime inventory/source of trust.
    # This locally computed pin exercises read-only verification only.
    pin = WAWExecutablePin(path, hashlib.sha256(path.read_bytes()).hexdigest())
    with WAWExecutableInventory({WAWExecutableKind.CODEX: pin}).open(
        WAWExecutableKind.CODEX
    ) as handle:
        assert handle.identity.uid == 0
        assert handle.revalidate() == handle.identity
