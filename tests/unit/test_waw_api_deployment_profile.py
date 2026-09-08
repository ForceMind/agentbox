from __future__ import annotations

import dataclasses
import os
import stat
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from agentbox_api import waw_deployment_profile as subject
from agentbox_api.waw_application import WAWMode
from agentbox_api.waw_deployment_profile import (
    WAWDeploymentProfileError,
    load_waw_deployment_profile,
    revalidate_waw_deployment_profile,
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


def _raw(mode: WAWMode) -> bytes:
    return (
        b'{"mode":"disabled","schema_version":"agentbox-waw-api-profile.v1"}\n'
        if mode is WAWMode.DISABLED
        else b'{"mode":"filesystem-v2","schema_version":"agentbox-waw-api-profile.v1"}\n'
    )


def _path(tmp_path: Path) -> Path:
    parent = tmp_path / "etc" / "agentbox"
    parent.mkdir(parents=True)
    return parent / subject.WAW_DEPLOYMENT_PROFILE_FILENAME


def _mock_safe_tree(monkeypatch: pytest.MonkeyPatch, profile: Path) -> None:
    real_fstat = subject._fstat
    real_stat = subject._stat
    parent_inode = profile.parent.stat().st_ino

    def rooted(details: os.stat_result) -> _Stat:
        if stat.S_ISDIR(details.st_mode):
            mode = stat.S_IFDIR | (0o750 if details.st_ino == parent_inode else 0o755)
            gid = 4242 if details.st_ino == parent_inode else 0
        else:
            mode = stat.S_IFREG | 0o440
            gid = 4242
        return _Stat(
            details.st_dev,
            details.st_ino,
            mode,
            0,
            gid,
            details.st_nlink,
            details.st_size,
            details.st_mtime_ns,
            details.st_ctime_ns,
        )

    monkeypatch.setattr(subject, "WAW_DEPLOYMENT_PROFILE_PATH", profile)
    monkeypatch.setattr(subject, "_getgrnam", lambda _name: SimpleNamespace(gr_gid=4242))
    monkeypatch.setattr(subject, "_fstat", lambda descriptor: rooted(real_fstat(descriptor)))
    monkeypatch.setattr(
        subject,
        "_stat",
        lambda name, *, dir_fd, follow_symlinks: rooted(
            real_stat(name, dir_fd=dir_fd, follow_symlinks=follow_symlinks)
        ),
    )


@pytest.mark.parametrize("mode", [WAWMode.DISABLED, WAWMode.FILESYSTEM_V2])
def test_loads_only_the_two_canonical_profiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: WAWMode
) -> None:
    profile = _path(tmp_path)
    profile.write_bytes(_raw(mode))
    _mock_safe_tree(monkeypatch, profile)

    observed = load_waw_deployment_profile()

    assert observed.mode is mode
    assert observed.source == "installed_profile"
    assert observed.raw_sha256 is not None
    revalidate_waw_deployment_profile(observed)
    revalidate_waw_deployment_profile(observed)


def test_safely_absent_leaf_defaults_to_disabled_and_appearance_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _path(tmp_path)
    _mock_safe_tree(monkeypatch, profile)
    observed = load_waw_deployment_profile()
    assert observed.mode is WAWMode.DISABLED
    assert observed.source == "missing_default"

    profile.write_bytes(_raw(WAWMode.FILESYSTEM_V2))
    with pytest.raises(WAWDeploymentProfileError):
        revalidate_waw_deployment_profile(observed)


@pytest.mark.parametrize("replacement", ["deleted", "same_bytes", "modified"])
def test_revalidation_rejects_leaf_deletion_replacement_and_mutation(
    replacement: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _path(tmp_path)
    profile.write_bytes(_raw(WAWMode.DISABLED))
    _mock_safe_tree(monkeypatch, profile)
    observed = load_waw_deployment_profile()
    if replacement == "deleted":
        profile.unlink()
    else:
        profile.unlink()
        profile.write_bytes(
            _raw(WAWMode.DISABLED if replacement == "same_bytes" else WAWMode.FILESYSTEM_V2)
        )
    with pytest.raises(WAWDeploymentProfileError):
        revalidate_waw_deployment_profile(observed)


@pytest.mark.parametrize("change", ["leaf_group", "parent_mode"])
def test_revalidation_rejects_leaf_group_and_parent_provenance_change(
    change: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _path(tmp_path)
    profile.write_bytes(_raw(WAWMode.DISABLED))
    _mock_safe_tree(monkeypatch, profile)
    observed = load_waw_deployment_profile()
    rooted_fstat = cast(Callable[[int], _Stat], subject._fstat)
    parent_inode = profile.parent.stat().st_ino

    def changed_fstat(descriptor: int) -> _Stat:
        details = rooted_fstat(descriptor)
        if change == "leaf_group" and stat.S_ISREG(details.st_mode):
            return dataclasses.replace(details, st_gid=9)
        if change == "parent_mode" and details.st_ino == parent_inode:
            return dataclasses.replace(details, st_mode=stat.S_IFDIR | 0o755)
        return details

    monkeypatch.setattr(subject, "_fstat", changed_fstat)
    with pytest.raises(WAWDeploymentProfileError):
        revalidate_waw_deployment_profile(observed)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\xff",
        b'{"mode":"disabled","schema_version":"agentbox-waw-api-profile.v1"}',
        b'{"schema_version":"agentbox-waw-api-profile.v1","mode":"disabled"}\n',
        b'{"mode":false,"schema_version":"agentbox-waw-api-profile.v1"}\n',
        b'{"mode":"disabled","schema_version":1}\n',
        b'{"mode":"DISABLED","schema_version":"agentbox-waw-api-profile.v1"}\n',
        b'{"mode":"disabled","schema_version":"agentbox-waw-api-profile.v1","x":1}\n',
        b"\xef\xbb\xbf" + _raw(WAWMode.DISABLED),
        _raw(WAWMode.DISABLED) + b" ",
        b"x" * 4096,
        b"x" * 4097,
    ],
)
def test_rejects_noncanonical_or_out_of_bounds_profile_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw: bytes
) -> None:
    profile = _path(tmp_path)
    profile.write_bytes(raw)
    _mock_safe_tree(monkeypatch, profile)
    with pytest.raises(WAWDeploymentProfileError):
        load_waw_deployment_profile()


def test_rejects_symlink_hardlink_and_parent_or_leaf_provenance_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _path(tmp_path)
    target = tmp_path / "target"
    target.write_bytes(_raw(WAWMode.DISABLED))
    profile.symlink_to(target)
    _mock_safe_tree(monkeypatch, profile)
    with pytest.raises(WAWDeploymentProfileError):
        load_waw_deployment_profile()

    profile.unlink()
    os.link(target, profile)
    with pytest.raises(WAWDeploymentProfileError):
        load_waw_deployment_profile()

    profile.unlink()
    os.mkfifo(profile)
    with pytest.raises(WAWDeploymentProfileError):
        load_waw_deployment_profile()


@pytest.mark.parametrize(
    "changes",
    [
        {"st_uid": 7},
        {"st_gid": 7},
        {"st_mode": stat.S_IFREG | 0o400},
        {"st_mode": stat.S_IFREG | 0o640},
    ],
)
def test_initial_load_rejects_leaf_owner_group_and_mode(
    changes: dict[str, int], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _path(tmp_path)
    profile.write_bytes(_raw(WAWMode.DISABLED))
    _mock_safe_tree(monkeypatch, profile)
    rooted_fstat = cast(Callable[[int], _Stat], subject._fstat)

    def changed_fstat(descriptor: int) -> _Stat:
        details = rooted_fstat(descriptor)
        return dataclasses.replace(details, **changes) if stat.S_ISREG(details.st_mode) else details

    monkeypatch.setattr(subject, "_fstat", changed_fstat)
    with pytest.raises(WAWDeploymentProfileError):
        load_waw_deployment_profile()


@pytest.mark.parametrize("target", ["root", "etc", "intermediate"])
def test_initial_load_rejects_root_and_parent_provenance(
    target: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _path(tmp_path)
    profile.write_bytes(_raw(WAWMode.DISABLED))
    _mock_safe_tree(monkeypatch, profile)
    rooted_fstat = cast(Callable[[int], _Stat], subject._fstat)
    target_inode = {
        "root": os.stat("/").st_ino,
        "etc": profile.parent.parent.stat().st_ino,
        "intermediate": tmp_path.stat().st_ino,
    }[target]

    def changed_fstat(descriptor: int) -> _Stat:
        details = rooted_fstat(descriptor)
        if details.st_ino == target_inode and stat.S_ISDIR(details.st_mode):
            return dataclasses.replace(details, st_mode=stat.S_IFDIR | 0o777)
        return details

    monkeypatch.setattr(subject, "_fstat", changed_fstat)
    with pytest.raises(WAWDeploymentProfileError):
        load_waw_deployment_profile()


def test_initial_load_rejects_missing_group_and_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _path(tmp_path)
    profile.write_bytes(_raw(WAWMode.DISABLED))
    _mock_safe_tree(monkeypatch, profile)
    monkeypatch.setattr(subject, "_getgrnam", lambda _name: (_ for _ in ()).throw(KeyError()))
    with pytest.raises(WAWDeploymentProfileError):
        load_waw_deployment_profile()

    _mock_safe_tree(monkeypatch, profile)
    real_open = subject._open

    def denied_open(name: str, flags: int, *, dir_fd: int | None = None) -> int:
        if name == "agentbox":
            raise PermissionError("synthetic permission failure")
        return real_open(name, flags, dir_fd=dir_fd)

    monkeypatch.setattr(subject, "_open", denied_open)
    with pytest.raises(WAWDeploymentProfileError):
        load_waw_deployment_profile()


def test_rejects_simulated_device_and_wrong_root_owned_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _path(tmp_path)
    profile.write_bytes(_raw(WAWMode.DISABLED))
    _mock_safe_tree(monkeypatch, profile)
    rooted_fstat = cast(Callable[[int], _Stat], subject._fstat)

    def altered_fstat(descriptor: int) -> _Stat:
        details = rooted_fstat(descriptor)
        if stat.S_ISREG(details.st_mode):
            return dataclasses.replace(details, st_mode=stat.S_IFCHR | 0o440)
        return details

    monkeypatch.setattr(subject, "_fstat", altered_fstat)
    with pytest.raises(WAWDeploymentProfileError):
        load_waw_deployment_profile()


def test_rejects_replacement_during_read_and_closes_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _path(tmp_path)
    profile.write_bytes(_raw(WAWMode.DISABLED))
    _mock_safe_tree(monkeypatch, profile)
    real_read = subject._read
    replaced = False
    closed: list[int] = []

    def replace_after_read(descriptor: int, count: int) -> bytes:
        nonlocal replaced
        chunk = real_read(descriptor, count)
        if chunk and not replaced:
            replaced = True
            profile.unlink()
            profile.write_bytes(_raw(WAWMode.DISABLED))
        return chunk

    monkeypatch.setattr(subject, "_read", replace_after_read)
    real_close = subject._close

    def tracked_close(descriptor: int) -> None:
        closed.append(descriptor)
        real_close(descriptor)

    monkeypatch.setattr(subject, "_close", tracked_close)
    with pytest.raises(WAWDeploymentProfileError):
        load_waw_deployment_profile()
    assert replaced and closed


def test_rejects_directory_entry_replacement_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _path(tmp_path)
    profile.write_bytes(_raw(WAWMode.DISABLED))
    _mock_safe_tree(monkeypatch, profile)
    real_read = subject._read
    replaced = False

    def replace_parent_after_read(descriptor: int, count: int) -> bytes:
        nonlocal replaced
        chunk = real_read(descriptor, count)
        if chunk and not replaced:
            replaced = True
            replacement = profile.parent.with_name("agentbox-replacement")
            replacement.mkdir()
            (replacement / subject.WAW_DEPLOYMENT_PROFILE_FILENAME).write_bytes(
                _raw(WAWMode.DISABLED)
            )
            old = profile.parent.with_name("agentbox-old")
            profile.parent.rename(old)
            replacement.rename(profile.parent)
        return chunk

    monkeypatch.setattr(subject, "_read", replace_parent_after_read)
    with pytest.raises(WAWDeploymentProfileError):
        load_waw_deployment_profile()
    assert replaced


def test_safe_missing_rechecks_that_leaf_did_not_appear_before_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _path(tmp_path)
    _mock_safe_tree(monkeypatch, profile)
    rooted_stat = cast(Callable[..., _Stat], subject._stat)
    appeared = False

    def appearance_stat(name: str, *, dir_fd: int, follow_symlinks: bool) -> _Stat:
        nonlocal appeared
        if name == subject.WAW_DEPLOYMENT_PROFILE_FILENAME and not appeared:
            appeared = True
            profile.write_bytes(_raw(WAWMode.DISABLED))
        return rooted_stat(name, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(subject, "_stat", appearance_stat)
    with pytest.raises(WAWDeploymentProfileError):
        load_waw_deployment_profile()
    assert appeared


def test_close_failure_still_attempts_every_descriptor_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _path(tmp_path)
    profile.write_bytes(_raw(WAWMode.DISABLED))
    _mock_safe_tree(monkeypatch, profile)
    real_close = subject._close
    attempted: list[int] = []

    def close_with_one_failure(descriptor: int) -> None:
        attempted.append(descriptor)
        real_close(descriptor)
        if len(attempted) == 1:
            raise OSError("synthetic close failure")

    monkeypatch.setattr(subject, "_close", close_with_one_failure)
    with pytest.raises(WAWDeploymentProfileError):
        load_waw_deployment_profile()
    assert len(attempted) >= 4
    for descriptor in attempted:
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_exact_profile_open_flags_are_not_configurable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _path(tmp_path)
    profile.write_bytes(_raw(WAWMode.DISABLED))
    _mock_safe_tree(monkeypatch, profile)
    real_open = subject._open
    calls: list[tuple[str, int, int | None]] = []

    def tracked_open(name: str, flags: int, *, dir_fd: int | None = None) -> int:
        calls.append((name, flags, dir_fd))
        return real_open(name, flags, dir_fd=dir_fd)

    monkeypatch.setattr(subject, "_open", tracked_open)
    load_waw_deployment_profile()
    leaf = [item for item in calls if item[0] == subject.WAW_DEPLOYMENT_PROFILE_FILENAME]
    assert len(leaf) == 1 and leaf[0][2] is not None
    assert leaf[0][1] & os.O_ACCMODE == os.O_RDONLY
    assert leaf[0][1] & os.O_CLOEXEC and leaf[0][1] & os.O_NOFOLLOW and leaf[0][1] & os.O_NONBLOCK
