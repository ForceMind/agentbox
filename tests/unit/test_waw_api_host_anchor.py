from __future__ import annotations

import dataclasses
import hashlib
import os
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from agentbox_api import waw_host_anchor as subject
from agentbox_api.waw_host_anchor import (
    API_HOST_ANCHOR_V2_FILENAME,
    API_HOST_ANCHOR_V2_MAX_BYTES,
    WAWAPIHostAnchorError,
    WAWAPIHostAnchorV2,
    load_waw_api_host_anchor_v2,
)
from agentbox_runtime.waw_manifest_codecs import (
    RUNTIME_HOST_MANIFEST_SCHEMA_V2,
    APIHostAnchorV2,
    encode_api_host_anchor,
    encode_api_host_anchor_v2,
)


@dataclasses.dataclass(frozen=True)
class _Stat:
    st_dev: int
    st_ino: int
    st_mode: int
    st_uid: int
    st_gid: int
    st_nlink: int
    st_size: int
    st_mtime_ns: int
    st_ctime_ns: int


def _root_stat(
    details: os.stat_result, *, unsafe_directory_inode: int | None = None, **changes: int
) -> _Stat:
    mode = details.st_mode
    if stat.S_ISDIR(mode):
        permissions = 0o777 if details.st_ino == unsafe_directory_inode else 0o755
        mode = stat.S_IFDIR | permissions
    elif stat.S_ISREG(mode):
        mode = stat.S_IFREG | 0o444
    values = _Stat(
        st_dev=details.st_dev,
        st_ino=details.st_ino,
        st_mode=mode,
        st_uid=0,
        st_gid=0,
        st_nlink=details.st_nlink,
        st_size=details.st_size,
        st_mtime_ns=details.st_mtime_ns,
        st_ctime_ns=details.st_ctime_ns,
    )
    return dataclasses.replace(values, **changes)


def _anchor_bytes() -> bytes:
    return encode_api_host_anchor_v2(
        {
            "runtime_host_installation_id": "wri_" + "1" * 32,
            "runtime_host_installation_revision": "3",
            "runtime_attestation_x25519_fingerprint": "a" * 64,
            "runtime_manifest_schema": RUNTIME_HOST_MANIFEST_SCHEMA_V2,
            "host_manifest_digest": "b" * 64,
            "project_root_manifest_digest": "c" * 64,
            "enrollment_epoch": "7",
            "enrollment_state": "steady",
        }
    )


def _write_anchor(tmp_path: Path, raw: bytes | None = None) -> Path:
    path = tmp_path / API_HOST_ANCHOR_V2_FILENAME
    path.write_bytes(_anchor_bytes() if raw is None else raw)
    path.chmod(0o444)
    return path


def _mock_root_tree(
    monkeypatch: pytest.MonkeyPatch, *, unsafe_directory_inode: int | None = None
) -> None:
    real_fstat = subject._fstat
    real_stat = subject._stat

    def root_fstat(descriptor: int) -> _Stat:
        return _root_stat(real_fstat(descriptor), unsafe_directory_inode=unsafe_directory_inode)

    def root_stat(path: str, *, dir_fd: int, follow_symlinks: bool) -> _Stat:
        return _root_stat(
            real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks),
            unsafe_directory_inode=unsafe_directory_inode,
        )

    monkeypatch.setattr(subject, "_fstat", root_fstat)
    monkeypatch.setattr(subject, "_stat", root_stat)


def test_valid_anchor_returns_frozen_typed_record_and_raw_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_anchor(tmp_path)
    raw = path.read_bytes()
    _mock_root_tree(monkeypatch)

    loaded = load_waw_api_host_anchor_v2(path)

    assert type(loaded) is WAWAPIHostAnchorV2
    assert type(loaded.anchor) is APIHostAnchorV2
    assert loaded.anchor.runtime_host_installation_revision == "3"
    assert loaded.raw_sha256 == hashlib.sha256(raw).hexdigest()
    with pytest.raises(dataclasses.FrozenInstanceError):
        loaded.raw_sha256 = "0" * 64  # type: ignore[misc]


def test_open_is_exact_read_only_nofollow_nonblocking_file_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_anchor(tmp_path)
    _mock_root_tree(monkeypatch)
    real_open = subject._open
    calls: list[tuple[str | Path, int, int | None]] = []

    def checked_open(candidate: str | Path, flags: int, *, dir_fd: int | None = None) -> int:
        calls.append((candidate, flags, dir_fd))
        return real_open(candidate, flags, dir_fd=dir_fd)

    monkeypatch.setattr(subject, "_open", checked_open)
    load_waw_api_host_anchor_v2(path)

    leaf = [call for call in calls if call[0] == API_HOST_ANCHOR_V2_FILENAME]
    assert len(leaf) == 1 and leaf[0][2] is not None
    assert leaf[0][1] & os.O_NOFOLLOW
    assert leaf[0][1] & os.O_NONBLOCK
    assert leaf[0][1] & os.O_CLOEXEC
    assert leaf[0][1] & os.O_ACCMODE == os.O_RDONLY
    assert all(call[1] & os.O_DIRECTORY for call in calls[:-1])


def test_leaf_symlink_and_non_regular_file_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.write_bytes(_anchor_bytes())
    target.chmod(0o444)
    link = tmp_path / API_HOST_ANCHOR_V2_FILENAME
    link.symlink_to(target)
    _mock_root_tree(monkeypatch)
    with pytest.raises(WAWAPIHostAnchorError):
        load_waw_api_host_anchor_v2(link)

    link.unlink()
    link.mkdir(mode=0o755)
    with pytest.raises(WAWAPIHostAnchorError):
        load_waw_api_host_anchor_v2(link)


@pytest.mark.parametrize(
    "changes",
    [
        {"st_uid": 1},
        {"st_gid": 1},
        {"st_mode": stat.S_IFREG | 0o440},
        {"st_mode": stat.S_IFREG | 0o644},
    ],
)
def test_owner_group_and_mode_are_fixed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changes: dict[str, int]
) -> None:
    path = _write_anchor(tmp_path)
    _mock_root_tree(monkeypatch)
    rooted_fstat = cast(Callable[[int], _Stat], subject._fstat)

    def changed_file_fstat(descriptor: int) -> _Stat:
        observed = rooted_fstat(descriptor)
        return (
            dataclasses.replace(observed, **changes) if stat.S_ISREG(observed.st_mode) else observed
        )

    monkeypatch.setattr(
        subject,
        "_fstat",
        changed_file_fstat,
    )

    with pytest.raises(WAWAPIHostAnchorError):
        load_waw_api_host_anchor_v2(path)


def test_parent_symlink_is_rejected_during_descriptor_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_parent = tmp_path / "real-public"
    real_parent.mkdir()
    _write_anchor(real_parent)
    alias = tmp_path / "public-alias"
    alias.symlink_to(real_parent, target_is_directory=True)
    _mock_root_tree(monkeypatch)

    with pytest.raises(WAWAPIHostAnchorError):
        load_waw_api_host_anchor_v2(alias / API_HOST_ANCHOR_V2_FILENAME)


def test_world_writable_ancestor_and_nonexact_public_mode_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unsafe = tmp_path / "unsafe"
    unsafe.mkdir()
    path = _write_anchor(unsafe)
    _mock_root_tree(monkeypatch, unsafe_directory_inode=unsafe.stat().st_ino)
    with pytest.raises(WAWAPIHostAnchorError):
        load_waw_api_host_anchor_v2(path)

    monkeypatch.undo()
    _mock_root_tree(monkeypatch)
    rooted_fstat = cast(Callable[[int], _Stat], subject._fstat)
    parent_inode = path.parent.stat().st_ino

    def wrong_final_mode(descriptor: int) -> _Stat:
        observed = rooted_fstat(descriptor)
        if observed.st_ino == parent_inode and stat.S_ISDIR(observed.st_mode):
            return dataclasses.replace(observed, st_mode=stat.S_IFDIR | 0o750)
        return observed

    monkeypatch.setattr(subject, "_fstat", wrong_final_mode)
    with pytest.raises(WAWAPIHostAnchorError):
        load_waw_api_host_anchor_v2(path)


def test_hardlinked_leaf_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source-anchor"
    source.write_bytes(_anchor_bytes())
    source.chmod(0o444)
    path = tmp_path / API_HOST_ANCHOR_V2_FILENAME
    os.link(source, path)
    _mock_root_tree(monkeypatch)

    with pytest.raises(WAWAPIHostAnchorError):
        load_waw_api_host_anchor_v2(path)


def test_leaf_directory_entry_replacement_during_read_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_anchor(tmp_path)
    _mock_root_tree(monkeypatch)
    real_read = subject._read
    replaced = False

    def replace_after_read(descriptor: int, size: int) -> bytes:
        nonlocal replaced
        chunk = real_read(descriptor, size)
        if chunk and not replaced:
            replaced = True
            path.unlink()
            path.write_bytes(_anchor_bytes())
            path.chmod(0o444)
        return chunk

    monkeypatch.setattr(subject, "_read", replace_after_read)
    with pytest.raises(WAWAPIHostAnchorError):
        load_waw_api_host_anchor_v2(path)
    assert replaced


def test_parent_identity_change_during_read_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_anchor(tmp_path)
    _mock_root_tree(monkeypatch)
    rooted_fstat = cast(Callable[[int], _Stat], subject._fstat)
    parent_inode = path.parent.stat().st_ino
    parent_calls = 0

    def changed_parent_fstat(descriptor: int) -> _Stat:
        nonlocal parent_calls
        observed = rooted_fstat(descriptor)
        if observed.st_ino == parent_inode and stat.S_ISDIR(observed.st_mode):
            parent_calls += 1
            if parent_calls == 3:
                return dataclasses.replace(observed, st_ctime_ns=0)
        return observed

    monkeypatch.setattr(subject, "_fstat", changed_parent_fstat)
    with pytest.raises(WAWAPIHostAnchorError):
        load_waw_api_host_anchor_v2(path)


def test_unexpected_assertion_is_not_hidden_as_anchor_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_anchor(tmp_path)
    _mock_root_tree(monkeypatch)

    def programming_error(_descriptor: int, _size: int) -> bytes:
        raise AssertionError("programming defect")

    monkeypatch.setattr(subject, "_read", programming_error)
    with pytest.raises(AssertionError, match="programming defect"):
        load_waw_api_host_anchor_v2(path)


def test_oversize_is_rejected_before_any_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_anchor(tmp_path, b"x" * (API_HOST_ANCHOR_V2_MAX_BYTES + 1))
    _mock_root_tree(monkeypatch)
    read_calls = 0

    def forbidden_read(_descriptor: int, _size: int) -> bytes:
        nonlocal read_calls
        read_calls += 1
        return b""

    monkeypatch.setattr(subject, "_read", forbidden_read)
    with pytest.raises(WAWAPIHostAnchorError):
        load_waw_api_host_anchor_v2(path)
    assert read_calls == 0


def test_chunked_reads_are_completed_but_early_eof_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_anchor(tmp_path)
    _mock_root_tree(monkeypatch)
    real_read = subject._read
    monkeypatch.setattr(
        subject,
        "_read",
        lambda descriptor, size: real_read(descriptor, min(size, 7)),
    )
    assert load_waw_api_host_anchor_v2(path).anchor.runtime_host_installation_revision == "3"

    calls = 0

    def truncated_read(descriptor: int, size: int) -> bytes:
        nonlocal calls
        calls += 1
        return real_read(descriptor, min(size, 7)) if calls == 1 else b""

    monkeypatch.setattr(subject, "_read", truncated_read)
    with pytest.raises(WAWAPIHostAnchorError):
        load_waw_api_host_anchor_v2(path)


def test_descriptor_identity_change_after_read_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_anchor(tmp_path)
    _mock_root_tree(monkeypatch)
    rooted_fstat = cast(Callable[[int], _Stat], subject._fstat)
    file_calls = 0

    def changed_fstat(descriptor: int) -> Any:
        nonlocal file_calls
        observed = rooted_fstat(descriptor)
        if stat.S_ISREG(observed.st_mode):
            file_calls += 1
            if file_calls == 2:
                return dataclasses.replace(observed, st_mtime_ns=0)
        return observed

    monkeypatch.setattr(subject, "_fstat", changed_fstat)
    with pytest.raises(WAWAPIHostAnchorError):
        load_waw_api_host_anchor_v2(path)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"invalid":"CANARY-CONTENT"}',
        encode_api_host_anchor(
            {
                "runtime_host_installation_id": "wri_" + "1" * 32,
                "runtime_host_installation_revision": "3",
                "runtime_attestation_x25519_fingerprint": "a" * 64,
                "host_manifest_digest": "b" * 64,
                "project_root_manifest_digest": "c" * 64,
                "enrollment_epoch": "7",
                "enrollment_state": "steady",
            }
        ),
    ],
)
def test_malformed_and_v1_records_fail_without_echoing_path_or_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw: bytes
) -> None:
    path = _write_anchor(tmp_path, raw)
    _mock_root_tree(monkeypatch)

    with pytest.raises(WAWAPIHostAnchorError) as raised:
        load_waw_api_host_anchor_v2(path)

    rendered = repr(raised.value)
    assert str(path) not in rendered
    assert "CANARY-CONTENT" not in rendered
    assert raised.value.__cause__ is None


@pytest.mark.parametrize(
    "path",
    [
        Path("api-host-anchor.v2.json"),
        Path("/tmp/allowed/../api-host-anchor.v2.json"),
        Path("/tmp/not-the-anchor.json"),
    ],
)
def test_nonabsolute_traversal_and_wrong_filename_are_rejected_before_open(
    path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_calls = 0

    def forbidden_open(_path: Path, _flags: int) -> int:
        nonlocal open_calls
        open_calls += 1
        raise OSError("unexpected open")

    monkeypatch.setattr(subject, "_open", forbidden_open)
    with pytest.raises(WAWAPIHostAnchorError):
        load_waw_api_host_anchor_v2(path)
    assert open_calls == 0
