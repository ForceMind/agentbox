from __future__ import annotations

import asyncio
import grp
import hashlib
import inspect
import os
import pwd
import stat
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from agentbox_runtime import waw_static_key as static_key_subject
from agentbox_runtime.waw_fixed_transport import _issue_verified_execution_authority
from agentbox_runtime.waw_static_key import (
    WAWRuntimeStaticKeyConstructionCleanupError,
    WAWRuntimeStaticKeyError,
    _open_waw_runtime_static_key,
    _open_waw_runtime_static_key_test_only,
    _StaticKeySyscalls,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from test_waw_bootstrap import _verified_v2_pin

KEY = b"private-key-canary-0123456789ABC"


def _fingerprint(raw: bytes = KEY) -> str:
    public = X25519PrivateKey.from_private_bytes(raw).public_key().public_bytes_raw()
    return hashlib.sha256(public).hexdigest()


def _authority(fingerprint: str | None = None) -> Any:
    pin = _verified_v2_pin()
    runtime = replace(
        pin.runtime,
        runtime_attestation_x25519_fingerprint=fingerprint or _fingerprint(),
    )
    return _issue_verified_execution_authority(replace(pin, runtime=runtime))


def _fixture_tree(tmp_path: Path, raw: bytes = KEY) -> Path:
    root = tmp_path / "root"
    root.mkdir(mode=0o700, parents=True)
    parent = root / "var"
    parent.mkdir(mode=0o755)
    parent = parent / "lib"
    parent.mkdir(mode=0o755)
    parent = parent / "agentbox-waw"
    parent.mkdir(mode=0o750)
    parent = parent / "keys-v1"
    parent.mkdir(mode=0o700)
    key = parent / "static-x25519.key"
    key.write_bytes(raw)
    key.chmod(0o600)
    return root


def _key_path(root: Path) -> Path:
    return root / "var/lib/agentbox-waw/keys-v1/static-x25519.key"


def test_production_factory_has_no_configurable_path_or_identity() -> None:
    assert inspect.signature(_open_waw_runtime_static_key).parameters == {}


def test_production_factory_uses_only_fixed_system_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, Any] = {}
    account_names: list[str] = []
    group_names: list[str] = []
    sentinel = object()

    def passwd(name: str) -> Any:
        account_names.append(name)
        return SimpleNamespace(pw_uid=1201, pw_gid=1202)

    def group(name: str) -> Any:
        group_names.append(name)
        return SimpleNamespace(gr_gid=1202)

    def open_fixed_key(**kwargs: Any) -> Any:
        observed.update(kwargs)
        return sentinel

    monkeypatch.setattr(pwd, "getpwnam", passwd)
    monkeypatch.setattr(grp, "getgrnam", group)
    monkeypatch.setattr(
        os,
        "getresuid",
        lambda: (1201, 1201, 1201),
        raising=False,
    )
    monkeypatch.setattr(
        os,
        "getresgid",
        lambda: (1202, 1202, 1202),
        raising=False,
    )
    monkeypatch.setattr(static_key_subject, "_open_fixed_key", open_fixed_key)

    assert _open_waw_runtime_static_key() is sentinel
    assert account_names == ["agentbox-runtime"]
    assert group_names == ["agentbox-runtime"]
    assert observed == {
        "root": Path("/"),
        "runtime_uid": 1201,
        "runtime_gid": 1202,
        "ancestor_uid": 0,
        "syscalls": static_key_subject._SYSCALLS,
    }


@pytest.mark.parametrize(
    ("account_uid", "account_gid", "group_gid", "uids", "gids"),
    [
        (0, 1202, 1202, (0, 0, 0), (1202, 1202, 1202)),
        (1201, 1203, 1202, (1201, 1201, 1201), (1202, 1202, 1202)),
        (1201, 1202, 1202, (1201, 1201, 0), (1202, 1202, 1202)),
        (1201, 1202, 1202, (1201, 1201, 1201), (1202, 1202, 0)),
    ],
    ids=["root", "passwd-group-mismatch", "saved-uid", "saved-gid"],
)
def test_production_factory_rejects_non_exact_system_identity(
    monkeypatch: pytest.MonkeyPatch,
    account_uid: int,
    account_gid: int,
    group_gid: int,
    uids: tuple[int, int, int],
    gids: tuple[int, int, int],
) -> None:
    monkeypatch.setattr(
        pwd,
        "getpwnam",
        lambda _name: SimpleNamespace(pw_uid=account_uid, pw_gid=account_gid),
    )
    monkeypatch.setattr(
        grp,
        "getgrnam",
        lambda _name: SimpleNamespace(gr_gid=group_gid),
    )
    monkeypatch.setattr(os, "getresuid", lambda: uids, raising=False)
    monkeypatch.setattr(os, "getresgid", lambda: gids, raising=False)
    monkeypatch.setattr(
        static_key_subject,
        "_open_fixed_key",
        lambda **_kwargs: pytest.fail("invalid identity must not open the fixed key"),
    )

    with pytest.raises(WAWRuntimeStaticKeyError, match="identity is invalid"):
        _open_waw_runtime_static_key()


@pytest.mark.parametrize("size", [31, 33])
def test_key_rejects_wrong_exact_size(tmp_path: Path, size: int) -> None:
    root = _fixture_tree(tmp_path, b"k" * size)
    with pytest.raises(WAWRuntimeStaticKeyError):
        _open_waw_runtime_static_key_test_only(root)


def test_key_rejects_missing_leaf(tmp_path: Path) -> None:
    root = _fixture_tree(tmp_path)
    _key_path(root).unlink()
    with pytest.raises(WAWRuntimeStaticKeyError):
        _open_waw_runtime_static_key_test_only(root)


def test_key_accepts_exact_raw_32_bytes_and_binds_once(tmp_path: Path) -> None:
    root = _fixture_tree(tmp_path)
    port = _open_waw_runtime_static_key_test_only(root)
    authority = _authority()
    try:
        port.preflight()
        with pytest.raises(WAWRuntimeStaticKeyError, match="not bound"):
            port.private_key()
        port.bind_authority(authority)
        assert authority.runtime_attestation_x25519_fingerprint == _fingerprint()
        assert port.private_key() == KEY
        with pytest.raises(WAWRuntimeStaticKeyError, match="already bound"):
            port.bind_authority(authority)
        with pytest.raises(WAWRuntimeStaticKeyError, match="unavailable"):
            port.private_key()
    finally:
        assert port.close()
        assert port.close()


class _MetadataOverride(_StaticKeySyscalls):
    def __init__(self, **changes: int) -> None:
        self._changes = changes

    def _replace_regular(self, details: Any) -> Any:
        if not stat.S_ISREG(details.st_mode):
            return details
        values = {
            name: getattr(details, name)
            for name in (
                "st_dev",
                "st_ino",
                "st_mode",
                "st_uid",
                "st_gid",
                "st_nlink",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
            )
        }
        values.update(self._changes)
        return SimpleNamespace(**values)

    def fstat(self, fd: int) -> Any:
        return self._replace_regular(super().fstat(fd))

    def stat(self, name: str, *, dir_fd: int) -> Any:
        return self._replace_regular(super().stat(name, dir_fd=dir_fd))


class _DirectoryMetadataOverride(_StaticKeySyscalls):
    def __init__(self, target_mode: int, **changes: int) -> None:
        self._target_mode = target_mode
        self._changes = changes

    def _replace_directory(self, details: Any) -> Any:
        if not stat.S_ISDIR(details.st_mode) or stat.S_IMODE(details.st_mode) != self._target_mode:
            return details
        values = {
            name: getattr(details, name)
            for name in (
                "st_dev",
                "st_ino",
                "st_mode",
                "st_uid",
                "st_gid",
                "st_nlink",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
            )
        }
        values.update(self._changes)
        return SimpleNamespace(**values)

    def fstat(self, fd: int) -> Any:
        return self._replace_directory(super().fstat(fd))

    def stat(self, name: str, *, dir_fd: int) -> Any:
        return self._replace_directory(super().stat(name, dir_fd=dir_fd))


@pytest.mark.parametrize(
    "changes",
    [
        {"st_uid": os.geteuid() + 1},
        {"st_gid": os.getegid() + 1},
        {"st_mode": stat.S_IFREG | 0o640},
        {"st_mode": stat.S_IFCHR | 0o600},
    ],
    ids=["owner", "gid", "mode", "device"],
)
def test_key_rejects_wrong_leaf_provenance(tmp_path: Path, changes: dict[str, int]) -> None:
    root = _fixture_tree(tmp_path)
    with pytest.raises(WAWRuntimeStaticKeyError):
        _open_waw_runtime_static_key_test_only(root, syscalls=_MetadataOverride(**changes))


def test_key_rejects_symlink_hardlink_and_fifo(tmp_path: Path) -> None:
    for kind in ("symlink", "hardlink", "fifo"):
        case = tmp_path / kind
        case.mkdir()
        root = _fixture_tree(case)
        key = _key_path(root)
        if kind == "symlink":
            target = case / "target"
            target.write_bytes(KEY)
            key.unlink()
            key.symlink_to(target)
        elif kind == "hardlink":
            os.link(key, case / "second-link")
        else:
            key.unlink()
            os.mkfifo(key, 0o600)
        with pytest.raises(WAWRuntimeStaticKeyError):
            _open_waw_runtime_static_key_test_only(root)


@pytest.mark.parametrize(
    ("relative", "mode"),
    [
        ("var", 0o775),
        ("var/lib/agentbox-waw", 0o755),
        ("var/lib/agentbox-waw/keys-v1", 0o750),
    ],
)
def test_key_rejects_parent_permission_drift(tmp_path: Path, relative: str, mode: int) -> None:
    root = _fixture_tree(tmp_path)
    (root / relative).chmod(mode)
    with pytest.raises(WAWRuntimeStaticKeyError):
        _open_waw_runtime_static_key_test_only(root)


@pytest.mark.parametrize(
    "changes",
    [{"st_uid": os.geteuid() + 1}, {"st_gid": os.getegid() + 1}],
    ids=["owner", "gid"],
)
def test_key_rejects_parent_identity_drift(tmp_path: Path, changes: dict[str, int]) -> None:
    root = _fixture_tree(tmp_path)
    with pytest.raises(WAWRuntimeStaticKeyError):
        _open_waw_runtime_static_key_test_only(
            root,
            syscalls=_DirectoryMetadataOverride(0o750, **changes),
        )


def test_key_detects_replaced_entry_and_in_place_change(tmp_path: Path) -> None:
    replace_root = _fixture_tree(tmp_path / "replace")
    replaced = _open_waw_runtime_static_key_test_only(replace_root)
    replaced.preflight()
    replacement = _key_path(replace_root).with_name("replacement")
    replacement.write_bytes(KEY)
    replacement.chmod(0o600)
    os.replace(replacement, _key_path(replace_root))
    with pytest.raises(WAWRuntimeStaticKeyError):
        replaced.bind_authority(_authority())
    assert replaced.close()

    inplace_root = _fixture_tree(tmp_path / "inplace")
    inplace = _open_waw_runtime_static_key_test_only(inplace_root)
    inplace.preflight()
    _key_path(inplace_root).write_bytes(b"z" * 32)
    with pytest.raises(WAWRuntimeStaticKeyError):
        inplace.bind_authority(_authority())
    assert inplace.close()


@pytest.mark.parametrize("mutation", ["in-place", "replace"])
def test_bound_key_rejects_leaf_drift_and_remains_poisoned_after_close(
    tmp_path: Path,
    mutation: str,
) -> None:
    root = _fixture_tree(tmp_path)
    port = _open_waw_runtime_static_key_test_only(root)
    port.preflight()
    port.bind_authority(_authority())
    key = _key_path(root)
    if mutation == "in-place":
        key.write_bytes(b"z" * 32)
    else:
        replacement = key.with_name("replacement")
        replacement.write_bytes(b"z" * 32)
        replacement.chmod(0o600)
        os.replace(replacement, key)

    with pytest.raises(WAWRuntimeStaticKeyError):
        port.private_key()
    with pytest.raises(WAWRuntimeStaticKeyError, match="unavailable"):
        port.private_key()
    assert port.close()
    with pytest.raises(WAWRuntimeStaticKeyError, match="unavailable"):
        port.private_key()


def test_key_detects_renamed_and_replaced_key_directory(tmp_path: Path) -> None:
    root = _fixture_tree(tmp_path)
    port = _open_waw_runtime_static_key_test_only(root)
    port.preflight()
    waw_root = root / "var/lib/agentbox-waw"
    original = waw_root / "keys-v1"
    retained = waw_root / "keys-retained"
    original.rename(retained)
    replacement = waw_root / "keys-v1"
    replacement.mkdir(mode=0o700)
    replacement_key = replacement / "static-x25519.key"
    replacement_key.write_bytes(KEY)
    replacement_key.chmod(0o600)
    with pytest.raises(WAWRuntimeStaticKeyError, match="parent entry changed"):
        port.bind_authority(_authority())
    assert port.close()


def test_key_rejects_wrong_fingerprint_and_non_v2_authority_without_leak(
    tmp_path: Path,
) -> None:
    canary = KEY.decode("ascii")
    root = _fixture_tree(tmp_path / "mismatch")
    mismatch = _open_waw_runtime_static_key_test_only(root)
    mismatch.preflight()
    with pytest.raises(WAWRuntimeStaticKeyError) as mismatch_error:
        mismatch.bind_authority(_authority("0" * 64))
    assert canary not in str(mismatch_error.value)
    assert canary not in repr(mismatch)
    assert mismatch.close()

    v1_root = _fixture_tree(tmp_path / "v1")
    v1 = _open_waw_runtime_static_key_test_only(v1_root)
    v1.preflight()
    invalid_authority: Any = SimpleNamespace(runtime_attestation_x25519_fingerprint=_fingerprint())
    with pytest.raises(WAWRuntimeStaticKeyError, match="authority is invalid"):
        v1.bind_authority(invalid_authority)
    assert v1.close()


def test_take_consumes_source_and_transfers_descriptor_ownership(tmp_path: Path) -> None:
    root = _fixture_tree(tmp_path)
    source = _open_waw_runtime_static_key_test_only(root)
    owned = source.take()
    for operation in (source.preflight, source.private_key, source.take):
        with pytest.raises(WAWRuntimeStaticKeyError, match="unavailable"):
            operation()
    assert source.close()
    owned.preflight()
    owned.bind_authority(_authority())
    assert owned.private_key() == KEY
    assert owned.close()


class _CancelledRead(_StaticKeySyscalls):
    def pread(self, fd: int, length: int, offset: int) -> bytes:
        raise asyncio.CancelledError


def test_cancelled_read_poisoned_and_cleanup_remains_available(tmp_path: Path) -> None:
    port = _open_waw_runtime_static_key_test_only(
        _fixture_tree(tmp_path), syscalls=_CancelledRead()
    )
    with pytest.raises(asyncio.CancelledError):
        port.preflight()
    with pytest.raises(WAWRuntimeStaticKeyError, match="unavailable"):
        port.preflight()
    assert port.close()


class _AmbiguousClose(_StaticKeySyscalls):
    def __init__(self) -> None:
        self.calls = 0

    def close(self, fd: int) -> None:
        self.calls += 1
        super().close(fd)
        if self.calls == 1:
            raise OSError("synthetic ambiguous close")


def test_close_failure_is_sticky_and_descriptor_is_not_retried(tmp_path: Path) -> None:
    syscalls = _AmbiguousClose()
    port = _open_waw_runtime_static_key_test_only(_fixture_tree(tmp_path), syscalls=syscalls)
    assert port.close() is False
    calls = syscalls.calls
    assert calls == 6
    assert port.close() is False
    assert syscalls.calls == calls


class _LateValidationAndAmbiguousClose(_StaticKeySyscalls):
    def __init__(self) -> None:
        self.fstat_calls = 0
        self.close_calls: list[int] = []

    def fstat(self, fd: int) -> Any:
        self.fstat_calls += 1
        details = super().fstat(fd)
        if self.fstat_calls != 12:
            return details
        return SimpleNamespace(
            st_dev=details.st_dev,
            st_ino=details.st_ino,
            st_mode=stat.S_IFREG | 0o640,
            st_uid=details.st_uid,
            st_gid=details.st_gid,
            st_nlink=details.st_nlink,
            st_size=details.st_size,
            st_mtime_ns=details.st_mtime_ns,
            st_ctime_ns=details.st_ctime_ns,
        )

    def close(self, fd: int) -> None:
        self.close_calls.append(fd)
        super().close(fd)
        if len(self.close_calls) == 1:
            raise OSError(f"synthetic ambiguous close {KEY.decode('ascii')}")


def test_construction_validation_failure_reports_incomplete_cleanup_without_leak(
    tmp_path: Path,
) -> None:
    root = _fixture_tree(tmp_path)
    syscalls = _LateValidationAndAmbiguousClose()
    with pytest.raises(WAWRuntimeStaticKeyConstructionCleanupError) as captured:
        _open_waw_runtime_static_key_test_only(root, syscalls=syscalls)

    error = captured.value
    assert str(error) == "Runtime static key construction cleanup is incomplete"
    assert type(error.original_failure) is WAWRuntimeStaticKeyError
    assert str(error.original_failure) == "Runtime static key provenance is invalid"
    assert error.__cause__ is error.original_failure
    assert len(syscalls.close_calls) == 6
    assert len(set(syscalls.close_calls)) == 6
    for descriptor in syscalls.close_calls:
        with pytest.raises(OSError):
            os.fstat(descriptor)
    rendered = repr(error) + repr(error.original_failure)
    assert str(root) not in rendered
    assert KEY.decode("ascii") not in rendered
