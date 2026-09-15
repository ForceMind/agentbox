from __future__ import annotations

import fcntl
import os
import platform
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from agentbox_core.waw import AgentType, managed_marker, workspace_id
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_auth_lease import WAWAuthLeaseOwner, WAWSealedAuthLease
from agentbox_runtime.waw_fixed_transport import (
    _CGROUP_AUTH_TOKEN,
    LinuxCgroupControlHandle,
    WAWFixedTransport,
    WAWVerifiedExecutionAuthority,
)
from agentbox_runtime.waw_process_inspector import FixedProcessIdentity

PROJECT = "prj_" + "1" * 32
WORKSPACE = workspace_id(PROJECT, AgentType.CODEX)
HOST = "wri_" + "2" * 32
DIGEST = "a" * 64
PROFILE_DIGEST = "b" * 64
WORKSPACE_HASH = "d" * 64
SCRATCH_NAME = "auth-probe-g1"


def fixed_identity() -> FixedProcessIdentity:
    marker = managed_marker(
        runtime_host_installation_id=HOST,
        runtime_host_installation_revision=1,
        project_id=PROJECT,
        agent_type=AgentType.CODEX,
        workspace_id_value=WORKSPACE,
        generation=1,
        binding_revision=1,
        binding_digest=DIGEST,
    )
    return FixedProcessIdentity(
        WORKSPACE,
        PROJECT,
        AgentType.CODEX,
        1,
        WORKSPACE_HASH,
        marker,
        PROFILE_DIGEST,
        HOST,
        "1",
        "2",
    )


def _authority(monkeypatch: pytest.MonkeyPatch) -> WAWVerifiedExecutionAuthority:
    monkeypatch.setattr(WAWVerifiedExecutionAuthority, "authorizes", lambda _self, _identity: True)
    return object.__new__(WAWVerifiedExecutionAuthority)


def _scratch_tree(tmp_path: Path) -> tuple[int, Path]:
    root = tmp_path / "scratch"
    root.mkdir(parents=True)
    root.chmod(0o700)
    workspace = root / WORKSPACE_HASH
    workspace.mkdir()
    workspace.chmod(0o700)
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    return descriptor, workspace


def _cgroup_handle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    identity: FixedProcessIdentity,
    authority: WAWVerifiedExecutionAuthority,
) -> LinuxCgroupControlHandle:
    cgroup_dir = tmp_path / "workload"
    cgroup_dir.mkdir(exist_ok=True)
    descriptor = os.open(cgroup_dir, os.O_RDONLY | os.O_DIRECTORY)
    handle = object.__new__(LinuxCgroupControlHandle)
    handle._descriptor = descriptor
    handle._authority = authority
    handle._identity = identity
    handle._closed = False
    handle._consumed = False
    handle._auth_borrowed = False
    handle._lock = threading.RLock()
    monkeypatch.setattr(LinuxCgroupControlHandle, "populated", lambda _self: 0)
    monkeypatch.setattr(LinuxCgroupControlHandle, "frozen", lambda _self: 0)
    monkeypatch.setattr(
        LinuxCgroupControlHandle,
        "production_qualified_for",
        lambda _self, _authority, _identity: True,
    )
    return handle


def _transport(
    identity: FixedProcessIdentity,
    authority: WAWVerifiedExecutionAuthority,
    handle: LinuxCgroupControlHandle,
    *,
    production: bool = True,
) -> WAWFixedTransport:
    transport = object.__new__(WAWFixedTransport)
    transport._identity = identity
    transport._production = production
    transport._handles = cast(Any, SimpleNamespace(cgroup=handle))
    transport._port = SimpleNamespace(execution_authority=authority)
    transport._start_attempted = False
    transport._closed = False
    transport._aborted_unstarted = False
    transport._auth_lease = None
    transport._auth_poisoned = False
    return transport


@pytest.fixture
def rig(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path]:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    identity = fixed_identity()
    authority = _authority(monkeypatch)
    scratch_fd, workspace = _scratch_tree(tmp_path)
    handle = _cgroup_handle(tmp_path, monkeypatch, identity, authority)
    owner = WAWAuthLeaseOwner(authority, scratch_root=scratch_fd)
    os.close(scratch_fd)
    transport = _transport(identity, authority, handle)
    return owner, transport, handle, workspace


def _error_code(exc: BaseException) -> str:
    assert isinstance(exc, RuntimeOperationError)
    return exc.code


def _auth_lease_slot(transport: WAWFixedTransport) -> object:
    return transport._auth_lease


def _auth_borrowed(handle: LinuxCgroupControlHandle) -> bool:
    return handle.auth_borrowed


def test_borrow_and_release_round_trip(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
) -> None:
    owner, transport, handle, workspace = rig
    identity = fixed_identity()
    lease = owner.borrow(transport)
    assert type(lease) is WAWSealedAuthLease
    assert lease.identity == identity
    assert transport._auth_lease is lease
    assert handle.auth_borrowed
    scratch = workspace / SCRATCH_NAME
    assert scratch.is_dir()
    assert stat.S_IMODE(scratch.stat().st_mode) == 0o700
    cgroup_fd = lease.cgroup_fd()
    scratch_fd = lease.scratch_fd()
    try:
        assert cgroup_fd >= 64 and scratch_fd >= 64
        assert stat.S_ISDIR(os.fstat(cgroup_fd).st_mode)
        assert stat.S_ISDIR(os.fstat(scratch_fd).st_mode)
    finally:
        os.close(cgroup_fd)
        os.close(scratch_fd)
    (scratch / "vendor.tmp").write_bytes(b"residue")
    (scratch / "vendor.tmp").chmod(0o400)
    (scratch / "empty-sub").mkdir()
    (scratch / "empty-sub").chmod(0o500)

    owner.release(lease)

    assert not scratch.exists()
    assert _auth_lease_slot(transport) is None
    assert not _auth_borrowed(handle)
    assert lease._state == "RELEASED"
    with pytest.raises(RuntimeOperationError) as stale:
        lease.cgroup_fd()
    assert _error_code(stale.value) == "WAW_AUTH_LEASE_STALE"
    with pytest.raises(RuntimeOperationError) as stale_fd:
        lease.scratch_fd()
    assert _error_code(stale_fd.value) == "WAW_AUTH_LEASE_STALE"
    launcher_fd = handle.take_launcher_fd(identity)
    assert launcher_fd >= 64
    os.close(launcher_fd)


def test_borrow_serializes_single_lease(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
) -> None:
    owner, transport, _handle, _workspace = rig
    lease = owner.borrow(transport)
    with pytest.raises(RuntimeOperationError) as busy:
        owner.borrow(transport)
    assert _error_code(busy.value) == "WAW_AUTH_LEASE_BUSY"
    owner.release(lease)


def test_borrowed_transport_blocks_launch_abort_and_launcher(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
) -> None:
    owner, transport, handle, _workspace = rig
    identity = fixed_identity()
    lease = owner.borrow(transport)
    with pytest.raises(RuntimeOperationError) as launcher:
        handle.take_launcher_fd(identity)
    assert _error_code(launcher.value) == "WAW_AUTH_LEASE_BUSY"
    with pytest.raises(RuntimeOperationError) as started:
        transport.start(cast(Any, object()), cast(Any, object()))
    assert _error_code(started.value) == "WAW_AUTH_LEASE_BUSY"
    with pytest.raises(RuntimeOperationError) as aborted:
        transport.abort_unstarted()
    assert _error_code(aborted.value) == "WAW_AUTH_LEASE_BUSY"
    owner.release(lease)


def test_borrow_requires_empty_cgroup(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, transport, _handle, _workspace = rig
    monkeypatch.setattr(LinuxCgroupControlHandle, "populated", lambda _self: 1)
    with pytest.raises(RuntimeOperationError) as populated:
        owner.borrow(transport)
    assert _error_code(populated.value) == "WAW_AUTH_LEASE_BUSY"
    monkeypatch.setattr(LinuxCgroupControlHandle, "populated", lambda _self: 0)
    monkeypatch.setattr(LinuxCgroupControlHandle, "frozen", lambda _self: 1)
    with pytest.raises(RuntimeOperationError) as frozen:
        owner.borrow(transport)
    assert _error_code(frozen.value) == "WAW_AUTH_LEASE_BUSY"


def test_borrow_rejects_existing_scratch_residue(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
) -> None:
    owner, transport, _handle, workspace = rig
    (workspace / SCRATCH_NAME).mkdir()
    with pytest.raises(RuntimeOperationError) as busy:
        owner.borrow(transport)
    assert _error_code(busy.value) == "WAW_AUTH_LEASE_BUSY"
    assert transport._auth_lease is None


def test_borrow_rejects_missing_or_mismode_workspace_root(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
) -> None:
    owner, transport, _handle, workspace = rig
    workspace.rmdir()
    with pytest.raises(RuntimeOperationError) as missing:
        owner.borrow(transport)
    assert _error_code(missing.value) == "WAW_AUTH_LEASE_STALE"
    workspace.mkdir()
    workspace.chmod(0o700)
    workspace.chmod(0o750)
    with pytest.raises(RuntimeOperationError) as mismode:
        owner.borrow(transport)
    assert _error_code(mismode.value) == "WAW_AUTH_LEASE_STALE"


def test_borrow_rejects_unqualified_transport(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
) -> None:
    owner, transport, handle, _workspace = rig
    identity = fixed_identity()
    development = _transport(identity, handle._authority, handle, production=False)
    with pytest.raises(RuntimeOperationError) as nonproduction:
        owner.borrow(development)
    assert _error_code(nonproduction.value) == "WAW_AUTH_LEASE_STALE"
    foreign = object.__new__(WAWVerifiedExecutionAuthority)
    drifted = _transport(identity, foreign, handle)
    with pytest.raises(RuntimeOperationError) as wrong_authority:
        owner.borrow(drifted)
    assert _error_code(wrong_authority.value) == "WAW_AUTH_LEASE_STALE"
    transport._start_attempted = True
    with pytest.raises(RuntimeOperationError) as started:
        owner.borrow(transport)
    assert _error_code(started.value) == "WAW_AUTH_LEASE_BUSY"
    with pytest.raises(TypeError):
        owner.borrow(cast(Any, object()))


def test_borrow_failure_rolls_back_without_poison(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, transport, handle, workspace = rig
    real_fcntl = fcntl.fcntl

    def failing_fcntl(descriptor: int, command: int, *args: Any) -> int:
        if command == fcntl.F_DUPFD_CLOEXEC and descriptor == handle._descriptor:
            raise OSError("dup failed")
        return cast(int, real_fcntl(descriptor, command, *args))

    monkeypatch.setattr(fcntl, "fcntl", failing_fcntl)
    with pytest.raises(RuntimeOperationError) as stale:
        owner.borrow(transport)
    assert _error_code(stale.value) == "WAW_AUTH_LEASE_STALE"
    assert not (workspace / SCRATCH_NAME).exists()
    assert transport._auth_lease is None
    assert not handle.auth_borrowed
    assert not owner.poisoned
    assert not transport._auth_poisoned


def test_borrow_rollback_failure_poisons_transport_and_owner(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, transport, handle, _workspace = rig
    real_fcntl = fcntl.fcntl

    def failing_fcntl(descriptor: int, command: int, *args: Any) -> int:
        if command == fcntl.F_DUPFD_CLOEXEC and descriptor == handle._descriptor:
            raise OSError("dup failed")
        return cast(int, real_fcntl(descriptor, command, *args))

    def failing_rmdir(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("rmdir failed")

    monkeypatch.setattr(fcntl, "fcntl", failing_fcntl)
    monkeypatch.setattr(os, "rmdir", failing_rmdir)
    with pytest.raises(RuntimeOperationError) as stale:
        owner.borrow(transport)
    assert _error_code(stale.value) == "WAW_AUTH_LEASE_STALE"
    assert owner.poisoned
    assert transport._auth_poisoned


def test_release_with_live_cgroup_poisons_lease_transport_owner(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, transport, _handle, _workspace = rig
    lease = owner.borrow(transport)
    monkeypatch.setattr(LinuxCgroupControlHandle, "populated", lambda _self: 1)
    with pytest.raises(RuntimeOperationError) as poisoned:
        owner.release(lease)
    assert _error_code(poisoned.value) == "WAW_AUTH_LEASE_POISONED"
    assert lease._state == "POISONED"
    assert transport._auth_poisoned
    assert owner.poisoned
    with pytest.raises(RuntimeOperationError) as lease_fd:
        lease.cgroup_fd()
    assert _error_code(lease_fd.value) == "WAW_AUTH_LEASE_POISONED"
    with pytest.raises(RuntimeOperationError) as borrow:
        owner.borrow(transport)
    assert _error_code(borrow.value) == "WAW_AUTH_LEASE_POISONED"
    with pytest.raises(RuntimeOperationError) as again:
        owner.release(lease)
    assert _error_code(again.value) == "WAW_AUTH_LEASE_POISONED"
    with pytest.raises(RuntimeOperationError) as started:
        transport.start(cast(Any, object()), cast(Any, object()))
    assert _error_code(started.value) == "WAW_AUTH_LEASE_POISONED"
    with pytest.raises(RuntimeOperationError) as aborted:
        transport.abort_unstarted()
    assert _error_code(aborted.value) == "WAW_AUTH_LEASE_POISONED"


def test_release_with_symlink_poisons(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
) -> None:
    owner, transport, _handle, workspace = rig
    lease = owner.borrow(transport)
    (workspace / SCRATCH_NAME / "linked").symlink_to("target")
    with pytest.raises(RuntimeOperationError) as poisoned:
        owner.release(lease)
    assert _error_code(poisoned.value) == "WAW_AUTH_LEASE_POISONED"
    assert lease._state == "POISONED"
    assert transport._auth_poisoned
    assert owner.poisoned


def test_release_with_nested_content_poisons(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
) -> None:
    owner, transport, _handle, workspace = rig
    lease = owner.borrow(transport)
    nested = workspace / SCRATCH_NAME / "sub" / "inner"
    nested.mkdir(parents=True)
    with pytest.raises(RuntimeOperationError) as poisoned:
        owner.release(lease)
    assert _error_code(poisoned.value) == "WAW_AUTH_LEASE_POISONED"
    assert lease._state == "POISONED"
    assert transport._auth_poisoned
    assert owner.poisoned


def test_double_release_poisons(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
) -> None:
    owner, transport, _handle, _workspace = rig
    lease = owner.borrow(transport)
    owner.release(lease)
    with pytest.raises(RuntimeOperationError) as poisoned:
        owner.release(lease)
    assert _error_code(poisoned.value) == "WAW_AUTH_LEASE_POISONED"
    assert lease._state == "POISONED"
    assert transport._auth_poisoned
    assert owner.poisoned


def test_foreign_release_poisons_calling_owner(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, transport, _handle, _workspace = rig
    other_fd, _other_workspace = _scratch_tree(tmp_path / "other")
    other = WAWAuthLeaseOwner(owner.authority, scratch_root=other_fd)
    os.close(other_fd)
    lease = owner.borrow(transport)
    with pytest.raises(RuntimeOperationError) as poisoned:
        other.release(lease)
    assert _error_code(poisoned.value) == "WAW_AUTH_LEASE_POISONED"
    assert other.poisoned
    assert lease._state == "POISONED"
    assert transport._auth_poisoned
    assert not owner.poisoned


def test_owner_close_is_idempotent_and_terminal(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
) -> None:
    owner, transport, _handle, _workspace = rig
    owner.close()
    owner.close()
    assert owner.closed
    with pytest.raises(RuntimeOperationError) as closed:
        owner.borrow(transport)
    assert _error_code(closed.value) == "WAW_AUTH_LEASE_POISONED"


def test_cgroup_auth_borrow_token_gate(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
) -> None:
    owner, transport, handle, _workspace = rig
    with pytest.raises(RuntimeOperationError) as sealed:
        handle._set_auth_borrowed(object(), True)
    assert _error_code(sealed.value) == "RUNTIME_UNAVAILABLE"
    lease = owner.borrow(transport)
    with pytest.raises(RuntimeOperationError) as busy:
        handle._set_auth_borrowed(_CGROUP_AUTH_TOKEN, True)
    assert _error_code(busy.value) == "WAW_AUTH_LEASE_BUSY"
    owner.release(lease)


def test_constructor_rejects_invalid_scratch_root(tmp_path: Path) -> None:
    authority = object.__new__(WAWVerifiedExecutionAuthority)
    with pytest.raises(TypeError):
        WAWAuthLeaseOwner(cast(Any, object()), scratch_root=0)
    with pytest.raises(TypeError):
        WAWAuthLeaseOwner(authority, scratch_root=cast(Any, "fd"))
    regular = tmp_path / "file"
    regular.write_bytes(b"x")
    file_fd = os.open(regular, os.O_RDONLY)
    try:
        with pytest.raises(RuntimeOperationError) as not_dir:
            WAWAuthLeaseOwner(authority, scratch_root=file_fd)
        assert _error_code(not_dir.value) == "WAW_AUTH_LEASE_STALE"
    finally:
        os.close(file_fd)
    writable = tmp_path / "writable"
    writable.mkdir()
    writable.chmod(0o770)
    writable_fd = os.open(writable, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(RuntimeOperationError) as group_writable:
            WAWAuthLeaseOwner(authority, scratch_root=writable_fd)
        assert _error_code(group_writable.value) == "WAW_AUTH_LEASE_STALE"
    finally:
        os.close(writable_fd)


def test_lease_is_not_caller_constructible(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
) -> None:
    owner, transport, handle, _workspace = rig
    with pytest.raises(RuntimeOperationError) as sealed:
        WAWSealedAuthLease(
            object(),
            identity=fixed_identity(),
            owner=owner,
            transport=transport,
            cgroup=handle,
            cgroup_fd=0,
            workspace_fd=0,
            scratch_name=SCRATCH_NAME,
            scratch_fd=0,
        )
    assert _error_code(sealed.value) == "RUNTIME_UNAVAILABLE"


def test_release_poisons_on_special_scratch_entry(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
) -> None:
    owner, transport, _handle, workspace = rig
    lease = owner.borrow(transport)
    os.mkfifo(workspace / SCRATCH_NAME / "vendor-fifo")
    with pytest.raises(RuntimeOperationError) as poisoned:
        owner.release(lease)
    assert _error_code(poisoned.value) == "WAW_AUTH_LEASE_POISONED"
    assert owner.poisoned
    assert lease._state == "POISONED"
    assert transport._auth_poisoned


def test_owner_close_with_outstanding_lease_is_fail_closed(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
) -> None:
    owner, transport, handle, _workspace = rig
    lease = owner.borrow(transport)
    owner.close()
    assert owner.closed
    with pytest.raises(RuntimeOperationError) as closed_release:
        owner.release(lease)
    assert _error_code(closed_release.value) == "WAW_AUTH_LEASE_POISONED"
    with pytest.raises(RuntimeOperationError) as closed_borrow:
        owner.borrow(transport)
    assert _error_code(closed_borrow.value) == "WAW_AUTH_LEASE_POISONED"
    assert transport._auth_lease is lease
    assert handle.auth_borrowed
    with pytest.raises(RuntimeOperationError) as busy:
        handle.take_launcher_fd(fixed_identity())
    assert _error_code(busy.value) == "WAW_AUTH_LEASE_BUSY"


def test_stop_during_outstanding_lease_is_refused(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
) -> None:
    owner, transport, _handle, _workspace = rig
    lease = owner.borrow(transport)
    with pytest.raises(RuntimeOperationError) as busy:
        transport.stop()
    assert _error_code(busy.value) == "WAW_AUTH_LEASE_BUSY"
    owner.release(lease)


def test_borrow_serializes_concurrent_borrows(
    rig: tuple[WAWAuthLeaseOwner, WAWFixedTransport, LinuxCgroupControlHandle, Path],
) -> None:
    owner, transport, _handle, _workspace = rig

    def borrow() -> WAWSealedAuthLease | None:
        try:
            return owner.borrow(transport)
        except RuntimeOperationError:
            return None

    with ThreadPoolExecutor(max_workers=8) as workers:
        leases = tuple(workers.map(lambda _index: borrow(), range(32)))
    issued = tuple(lease for lease in leases if lease is not None)
    assert len(issued) == 1
    assert transport._auth_lease is issued[0]
    owner.release(issued[0])
