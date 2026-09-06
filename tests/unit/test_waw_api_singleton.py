from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from agentbox_api.waw_application import WAWAPIApplicationError, WAWAPIProcessLock


def _assert_acquired(process_lock: WAWAPIProcessLock, expected: bool) -> None:
    assert process_lock.acquired is expected


def test_lock_is_lazy_uses_fixed_flags_and_never_unlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "waw-api.lock"
    process_lock = WAWAPIProcessLock.test_only(path)
    _assert_acquired(process_lock, False)
    assert not path.exists()

    real_open = os.open
    observed: list[int] = []

    def capture_open(target: os.PathLike[str] | str, flags: int, mode: int = 0o777) -> int:
        observed.append(flags)
        return real_open(target, flags, mode)

    monkeypatch.setattr(os, "open", capture_open)
    process_lock.acquire()

    assert observed == [os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW]
    details = path.lstat()
    assert stat.S_ISREG(details.st_mode)
    assert stat.S_IMODE(details.st_mode) == 0o600
    assert details.st_nlink == 1
    _assert_acquired(process_lock, True)

    process_lock.release()
    process_lock.release()
    assert path.exists()
    _assert_acquired(process_lock, False)


def test_second_live_owner_is_rejected_with_fixed_code(tmp_path: Path) -> None:
    path = tmp_path / "waw-api.lock"
    first = WAWAPIProcessLock.test_only(path)
    second = WAWAPIProcessLock.test_only(path)
    first.acquire()
    try:
        with pytest.raises(WAWAPIApplicationError) as raised:
            second.acquire()
        assert raised.value.code == "WAW_API_SINGLETON_UNAVAILABLE"
        _assert_acquired(second, False)
    finally:
        first.release()


def test_symlink_and_multi_link_lock_files_fail_closed(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"")
    target.chmod(0o600)
    symlink = tmp_path / "symlink"
    symlink.symlink_to(target)
    with pytest.raises(WAWAPIApplicationError) as raised:
        WAWAPIProcessLock.test_only(symlink).acquire()
    assert raised.value.code == "WAW_API_SINGLETON_UNSAFE"

    linked = tmp_path / "linked"
    os.link(target, linked)
    with pytest.raises(WAWAPIApplicationError) as raised:
        WAWAPIProcessLock.test_only(target).acquire()
    assert raised.value.code == "WAW_API_SINGLETON_UNSAFE"


def test_wrong_mode_and_identity_replacement_poison_owner(tmp_path: Path) -> None:
    wrong_mode = tmp_path / "wrong-mode.lock"
    wrong_mode.write_bytes(b"")
    wrong_mode.chmod(0o640)
    with pytest.raises(WAWAPIApplicationError) as raised:
        WAWAPIProcessLock.test_only(wrong_mode).acquire()
    assert raised.value.code == "WAW_API_SINGLETON_UNSAFE"

    path = tmp_path / "replace.lock"
    process_lock = WAWAPIProcessLock.test_only(path)
    process_lock.acquire()
    path.unlink()
    path.write_bytes(b"")
    path.chmod(0o600)

    with pytest.raises(WAWAPIApplicationError) as first:
        process_lock.revalidate()
    with pytest.raises(WAWAPIApplicationError) as second:
        process_lock.release()
    assert first.value is second.value
    assert first.value.code == "WAW_API_SINGLETON_UNSAFE"
    assert process_lock.poisoned is True
    assert process_lock.acquired is False


def test_production_constructor_rejects_arbitrary_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="fixed"):
        WAWAPIProcessLock(tmp_path / "not-production.lock")
    assert WAWAPIProcessLock.production().path == Path("/run/agentbox-waw-api/waw-api.v1.lock")


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires POSIX fork")
def test_after_fork_child_closes_inherited_lock_and_cannot_become_owner(tmp_path: Path) -> None:
    path = tmp_path / "fork.lock"
    process_lock = WAWAPIProcessLock.test_only(path)
    process_lock.acquire()
    reader, writer = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(reader)
        result = ""
        try:
            assert process_lock.poisoned and not process_lock.has_owned_fd
            with pytest.raises(WAWAPIApplicationError) as raised:
                process_lock.revalidate()
            assert raised.value.code == "WAW_API_SINGLETON_UNSAFE"
            contender = WAWAPIProcessLock.test_only(path)
            with pytest.raises(WAWAPIApplicationError) as conflict:
                contender.acquire()
            assert conflict.value.code == "WAW_API_SINGLETON_UNAVAILABLE"
            result = "PASS"
        except BaseException as exc:
            result = f"FAIL:{type(exc).__name__}"
        os.write(writer, result.encode("ascii"))
        os.close(writer)
        os._exit(0)
    os.close(writer)
    try:
        assert os.read(reader, 128) == b"PASS"
        waited, status = os.waitpid(child, 0)
        assert waited == child and os.waitstatus_to_exitcode(status) == 0
        assert process_lock.acquired
    finally:
        os.close(reader)
        process_lock.release()
