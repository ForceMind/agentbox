from __future__ import annotations

import contextlib
import fcntl
import os
import threading

import pytest
from agentbox_runtime import waw_peer_authority as subject
from agentbox_runtime.waw_peer_authority import (
    WAWPeerAuthority,
    WAWPeerAuthorityError,
    WAWPeerBindStatus,
    WAWPeerCandidate,
    WAWPeerLease,
    WAWPeerTransferPlan,
    WAWRuntimePeerIdentity,
)

UID = 1200
GID = 1300
NONCE_A = b"a" * 32
NONCE_B = b"b" * 32


def _pipe_peer() -> tuple[int, int]:
    read_fd, write_fd = os.pipe()
    os.set_inheritable(read_fd, False)
    os.set_inheritable(write_fd, False)
    return read_fd, write_fd


def _candidate(authority: WAWPeerAuthority, pid: int, pidfd: int) -> WAWPeerCandidate:
    observed = authority.observe_control(pid, UID, GID, pidfd)
    assert type(observed) is WAWPeerCandidate
    return observed


def _bind(
    authority: WAWPeerAuthority,
    pid: int,
    pidfd: int,
    *,
    epoch: str = "9",
    nonce: bytes = NONCE_A,
) -> WAWPeerBindStatus:
    plan = authority.prepare_bind(
        _candidate(authority, pid, pidfd),
        api_authority_epoch=epoch,
        nonce_digest=nonce,
    )
    return authority.commit_bind(plan)


def test_wrong_uid_or_gid_rejects_without_dup_or_poison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    read_fd, write_fd = _pipe_peer()
    calls = 0

    def forbidden_dup(_descriptor: int) -> int:
        nonlocal calls
        calls += 1
        raise AssertionError("wrong identity must not duplicate pidfd")

    monkeypatch.setattr(subject, "_dup", forbidden_dup)
    try:
        assert authority.observe_control(101, UID + 1, GID, read_fd) is None
        assert authority.observe_control(101, UID, GID + 1, read_fd) is None
        assert calls == 0
        assert not authority.poisoned
    finally:
        os.close(read_fd)
        os.close(write_fd)
        authority.close()


def test_first_bind_same_live_exact_bind_and_runtime_peer_view() -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    read_fd, write_fd = _pipe_peer()
    try:
        candidate = _candidate(authority, 101, read_fd)
        assert candidate.fileno() != read_fd
        assert not os.get_inheritable(candidate.fileno())
        plan = authority.prepare_bind(
            candidate,
            api_authority_epoch="9",
            nonce_digest=NONCE_A,
        )
        assert type(plan) is WAWPeerTransferPlan and candidate.closed
        assert authority.commit_bind(plan) is WAWPeerBindStatus.BOUND

        observed = authority.observe_control(101, UID, GID, read_fd)
        assert type(observed) is WAWPeerLease
        assert type(observed.runtime_peer.identity) is WAWRuntimePeerIdentity
        assert observed.runtime_peer.api_authority_epoch == "9"
        assert observed.runtime_peer.current()
        runtime_view = observed.runtime_peer
        exact_identity = observed.runtime_identity
        equal_but_opaque = WAWRuntimePeerIdentity(
            exact_identity.process,
            exact_identity.generation,
        )
        assert equal_but_opaque == exact_identity and equal_but_opaque is not exact_identity
        assert not authority._runtime_peer_current(equal_but_opaque)
        same = authority.prepare_bind(
            observed,
            api_authority_epoch="9",
            nonce_digest=NONCE_A,
        )
        assert not same.revocation_required and same.replaces_generation is None
        assert authority.commit_bind(same) is WAWPeerBindStatus.ALREADY_BOUND
        assert observed.closed and runtime_view.current()
        authority.close()
        assert not runtime_view.current()
    finally:
        authority.close()
        os.close(read_fd)
        os.close(write_fd)


@pytest.mark.parametrize(("epoch", "nonce"), [("8", NONCE_A), ("9", NONCE_B)])
def test_live_same_process_changed_epoch_or_nonce_is_rejected(epoch: str, nonce: bytes) -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    read_fd, write_fd = _pipe_peer()
    try:
        assert _bind(authority, 101, read_fd) is WAWPeerBindStatus.BOUND
        lease = authority.borrow()
        assert lease is not None
        with pytest.raises(WAWPeerAuthorityError) as raised:
            authority.prepare_bind(
                lease,
                api_authority_epoch=epoch,
                nonce_digest=nonce,
            )
        assert raised.value.code == "AUTHORITY_CONFLICT"
        assert lease.current()
        lease.close()
    finally:
        authority.close()
        os.close(read_fd)
        os.close(write_fd)


def test_pid_reuse_or_other_live_process_is_candidate_then_bind_conflict() -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    first_read, first_write = _pipe_peer()
    second_read, second_write = _pipe_peer()
    try:
        _bind(authority, 101, first_read)
        reused_pid = authority.observe_control(101, UID, GID, second_read)
        assert type(reused_pid) is WAWPeerCandidate
        with pytest.raises(WAWPeerAuthorityError) as raised:
            authority.prepare_bind(
                reused_pid,
                api_authority_epoch="9",
                nonce_digest=NONCE_A,
            )
        assert raised.value.code == "AUTHORITY_CONFLICT"
        reused_pid.close()
    finally:
        authority.close()
        for descriptor in (first_read, first_write, second_read, second_write):
            os.close(descriptor)


def test_cross_authority_leases_are_rejected_before_either_authority_lock() -> None:
    first = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    second = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    first_read, first_write = _pipe_peer()
    second_read, second_write = _pipe_peer()
    _bind(first, 101, first_read)
    _bind(second, 202, second_read)
    first_lease = first.borrow()
    second_lease = second.borrow()
    assert first_lease is not None and second_lease is not None
    barrier = threading.Barrier(3)
    errors: list[str] = []

    def cross(
        authority: WAWPeerAuthority,
        lease: WAWPeerLease,
    ) -> None:
        barrier.wait()
        try:
            authority.prepare_bind(
                lease,
                api_authority_epoch="9",
                nonce_digest=NONCE_A,
            )
        except WAWPeerAuthorityError as exc:
            errors.append(exc.code)

    threads = [
        threading.Thread(target=cross, args=(first, second_lease)),
        threading.Thread(target=cross, args=(second, first_lease)),
    ]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=1)
    try:
        assert all(not thread.is_alive() for thread in threads)
        assert sorted(errors) == ["PEER_INVALID", "PEER_INVALID"]
    finally:
        first_lease.close()
        second_lease.close()
        first.close()
        second.close()
        for descriptor in (first_read, first_write, second_read, second_write):
            os.close(descriptor)


def test_borrow_duplicates_only_retained_pidfd(monkeypatch: pytest.MonkeyPatch) -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    read_fd, write_fd = _pipe_peer()
    real_dup = subject._dup
    calls: list[int] = []

    def recorded_dup(descriptor: int) -> int:
        calls.append(descriptor)
        return real_dup(descriptor)

    monkeypatch.setattr(subject, "_dup", recorded_dup)
    try:
        _bind(authority, 101, read_fd)
        calls.clear()
        retained = authority._current
        assert retained is not None
        lease = authority.borrow()
        assert lease is not None
        assert calls == [retained.pidfd]
        assert lease.fileno() != retained.pidfd
        lease.close()
    finally:
        authority.close()
        os.close(read_fd)
        os.close(write_fd)


def test_terminal_transfer_fences_old_and_failed_plan_does_not_restore() -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    old_read, old_write = _pipe_peer()
    new_read, new_write = _pipe_peer()
    later_read, later_write = _pipe_peer()
    old_lease: WAWPeerLease | None = None
    later_candidate: WAWPeerCandidate | None = None
    try:
        _bind(authority, 101, old_read, epoch="900")
        old_lease = authority.borrow()
        assert old_lease is not None
        retained = authority._current
        assert retained is not None
        retained_fd = retained.pidfd
        os.close(old_write)

        plan = authority.prepare_bind(
            _candidate(authority, 202, new_read),
            api_authority_epoch="1",
            nonce_digest=NONCE_B,
        )
        assert plan.revocation_required
        assert plan.replaces_generation == old_lease.runtime_identity.generation
        assert authority._current is None
        assert authority.retired_epochs == ("900",)
        assert not old_lease.runtime_peer.current()
        with pytest.raises(OSError):
            os.fstat(retained_fd)
        later_candidate = _candidate(authority, 303, later_read)
        authority.fail_bind(plan)
        assert authority.poisoned
        for operation in (
            lambda: authority.observe_control(303, UID, GID, later_read),
            authority.borrow,
            lambda: authority.prepare_bind(
                later_candidate,
                api_authority_epoch="2",
                nonce_digest=NONCE_A,
            ),
            lambda: authority.commit_bind(plan),
        ):
            with pytest.raises(WAWPeerAuthorityError) as raised:
                operation()
            assert raised.value.code == "AUTHORITY_POISONED"
    finally:
        if later_candidate is not None:
            later_candidate.close()
        if old_lease is not None:
            old_lease.close()
        authority.close()
        for descriptor in (old_read, new_read, new_write, later_read, later_write):
            os.close(descriptor)


def test_retired_epoch_cannot_replay_after_successful_smaller_transfer() -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    first_read, first_write = _pipe_peer()
    second_read, second_write = _pipe_peer()
    third_read, third_write = _pipe_peer()
    third: WAWPeerCandidate | None = None
    try:
        _bind(authority, 101, first_read, epoch="900")
        os.close(first_write)
        replacement = authority.prepare_bind(
            _candidate(authority, 202, second_read),
            api_authority_epoch="1",
            nonce_digest=NONCE_B,
        )
        assert replacement.revocation_required
        assert authority.commit_bind(replacement) is WAWPeerBindStatus.BOUND
        os.close(second_write)
        third = _candidate(authority, 303, third_read)
        with pytest.raises(WAWPeerAuthorityError) as raised:
            authority.prepare_bind(
                third,
                api_authority_epoch="900",
                nonce_digest=NONCE_A,
            )
        assert raised.value.code == "EPOCH_RETIRED"
        assert not authority.poisoned
    finally:
        if third is not None:
            third.close()
        authority.close()
        for descriptor in (first_read, second_read, third_read, third_write):
            os.close(descriptor)


def test_candidate_must_remain_current_until_commit() -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    read_fd, write_fd = _pipe_peer()
    retry_read, retry_write = _pipe_peer()
    try:
        plan = authority.prepare_bind(
            _candidate(authority, 101, read_fd),
            api_authority_epoch="7",
            nonce_digest=NONCE_A,
        )
        os.close(write_fd)
        with pytest.raises(WAWPeerAuthorityError) as raised:
            authority.commit_bind(plan)
        assert raised.value.code == "PEER_NOT_CURRENT"
        assert plan.closed and authority.borrow() is None
        assert not authority.poisoned
        assert _bind(authority, 202, retry_read, epoch="6") is WAWPeerBindStatus.BOUND
    finally:
        authority.close()
        os.close(read_fd)
        os.close(retry_read)
        os.close(retry_write)


def test_failed_already_bound_plan_is_retryable() -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    read_fd, write_fd = _pipe_peer()
    try:
        _bind(authority, 101, read_fd)
        lease = authority.borrow()
        assert lease is not None
        plan = authority.prepare_bind(
            lease,
            api_authority_epoch="9",
            nonce_digest=NONCE_A,
        )
        authority.fail_bind(plan)
        assert not authority.poisoned
        retry = authority.borrow()
        assert retry is not None and retry.current()
        retry.close()
    finally:
        authority.close()
        os.close(read_fd)
        os.close(write_fd)


def test_retired_epoch_capacity_is_bounded() -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID, max_retired_epochs=1)
    first_read, first_write = _pipe_peer()
    second_read, second_write = _pipe_peer()
    third_read, third_write = _pipe_peer()
    try:
        _bind(authority, 101, first_read, epoch="9")
        os.close(first_write)
        second = authority.prepare_bind(
            _candidate(authority, 202, second_read),
            api_authority_epoch="1",
            nonce_digest=NONCE_B,
        )
        authority.commit_bind(second)
        os.close(second_write)
        third = _candidate(authority, 303, third_read)
        with pytest.raises(WAWPeerAuthorityError) as raised:
            authority.prepare_bind(
                third,
                api_authority_epoch="2",
                nonce_digest=NONCE_A,
            )
        assert raised.value.code == "RETIRED_EPOCHS_FULL"
        third.close()
    finally:
        authority.close()
        for descriptor in (first_read, second_read, third_read, third_write):
            os.close(descriptor)


def test_commit_plan_has_one_cas_winner_under_concurrency() -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    read_fd, write_fd = _pipe_peer()
    plan = authority.prepare_bind(
        _candidate(authority, 101, read_fd),
        api_authority_epoch="5",
        nonce_digest=NONCE_A,
    )
    barrier = threading.Barrier(3)
    outcomes: list[str] = []

    def commit() -> None:
        barrier.wait()
        try:
            outcomes.append(authority.commit_bind(plan).value)
        except WAWPeerAuthorityError as exc:
            outcomes.append(exc.code)

    threads = [threading.Thread(target=commit) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=1)
    try:
        assert sorted(outcomes) == ["BOUND", "TRANSFER_STALE"]
    finally:
        authority.close()
        os.close(read_fd)
        os.close(write_fd)


def test_concurrent_prepare_has_one_plan_winner() -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    read_fd, write_fd = _pipe_peer()
    candidates = [_candidate(authority, 101, read_fd) for _ in range(2)]
    barrier = threading.Barrier(3)
    plans: list[WAWPeerTransferPlan] = []
    errors: list[str] = []

    def prepare(candidate: WAWPeerCandidate) -> None:
        barrier.wait()
        try:
            plans.append(
                authority.prepare_bind(
                    candidate,
                    api_authority_epoch="5",
                    nonce_digest=NONCE_A,
                )
            )
        except WAWPeerAuthorityError as exc:
            errors.append(exc.code)

    threads = [threading.Thread(target=prepare, args=(candidate,)) for candidate in candidates]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=1)
    try:
        assert len(plans) == 1
        assert errors == ["TRANSFER_IN_PROGRESS"]
        authority.fail_bind(plans[0])
    finally:
        for candidate in candidates:
            candidate.close()
        authority.close()
        os.close(read_fd)
        os.close(write_fd)


@pytest.mark.parametrize("epoch", ["", "0", "01", str(2**64), "1.0"])
def test_epoch_is_protocol_canonical(epoch: str) -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    read_fd, write_fd = _pipe_peer()
    candidate = _candidate(authority, 101, read_fd)
    try:
        with pytest.raises(WAWPeerAuthorityError) as raised:
            authority.prepare_bind(
                candidate,
                api_authority_epoch=epoch,
                nonce_digest=NONCE_A,
            )
        assert raised.value.code == "EPOCH_INVALID"
    finally:
        candidate.close()
        authority.close()
        os.close(read_fd)
        os.close(write_fd)


@pytest.mark.parametrize("nonce", [b"", b"a" * 31, b"a" * 33, "a" * 64])
def test_nonce_digest_is_exactly_32_bytes(nonce: object) -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    read_fd, write_fd = _pipe_peer()
    candidate = _candidate(authority, 101, read_fd)
    try:
        with pytest.raises(WAWPeerAuthorityError) as raised:
            authority.prepare_bind(
                candidate,
                api_authority_epoch="1",
                nonce_digest=nonce,  # type: ignore[arg-type]
            )
        assert raised.value.code == "NONCE_DIGEST_INVALID"
    finally:
        candidate.close()
        authority.close()
        os.close(read_fd)
        os.close(write_fd)


def test_high_numbered_pidfd_poll_and_cloexec(monkeypatch: pytest.MonkeyPatch) -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    read_fd, write_fd = _pipe_peer()

    def high_dup(descriptor: int) -> int:
        return fcntl.fcntl(descriptor, fcntl.F_DUPFD_CLOEXEC, 2048)

    monkeypatch.setattr(subject, "_dup", high_dup)
    try:
        try:
            candidate = _candidate(authority, 101, read_fd)
        except WAWPeerAuthorityError as exc:
            assert exc.code == "PEER_INVALID"
            pytest.skip("process file descriptor limit does not permit a high fd")
        assert candidate.fileno() >= 2048
        assert not os.get_inheritable(candidate.fileno())
        assert candidate.current()
        candidate.close()
    finally:
        authority.close()
        os.close(read_fd)
        os.close(write_fd)


def test_candidate_lease_and_plan_close_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    read_fd, write_fd = _pipe_peer()
    real_close = subject._close
    closed: list[int] = []

    def recorded_close(descriptor: int) -> None:
        closed.append(descriptor)
        real_close(descriptor)

    monkeypatch.setattr(subject, "_close", recorded_close)
    candidate = _candidate(authority, 101, read_fd)
    descriptor = candidate.fileno()
    candidate.close()
    candidate.close()
    try:
        assert closed.count(descriptor) == 1
        replacement = _candidate(authority, 101, read_fd)
        plan = authority.prepare_bind(
            replacement,
            api_authority_epoch="1",
            nonce_digest=NONCE_A,
        )
        plan_descriptor = plan.fileno()
        before_plan_close = len(closed)
        authority.fail_bind(plan)
        plan.close()
        assert closed[before_plan_close:] == [plan_descriptor]

        _bind(authority, 101, read_fd, epoch="2")
        lease = authority.borrow()
        assert lease is not None
        lease_descriptor = lease.fileno()
        before_lease_close = len(closed)
        lease.close()
        lease.close()
        assert closed[before_lease_close:] == [lease_descriptor]
    finally:
        authority.close()
        os.close(read_fd)
        os.close(write_fd)


def test_lease_current_and_close_do_not_deadlock_or_reuse_fd() -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    read_fd, write_fd = _pipe_peer()
    _bind(authority, 101, read_fd)
    lease = authority.borrow()
    assert lease is not None
    barrier = threading.Barrier(3)
    observations: list[bool] = []

    def observe() -> None:
        barrier.wait()
        for _ in range(1000):
            observations.append(lease.current())

    def close() -> None:
        barrier.wait()
        lease.close()

    threads = [threading.Thread(target=observe), threading.Thread(target=close)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=1)
    try:
        assert all(not thread.is_alive() for thread in threads)
        assert observations and not lease.current()
    finally:
        authority.close()
        os.close(read_fd)
        os.close(write_fd)


def test_terminal_fence_close_failure_is_single_attempt_and_poisons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    old_read, old_write = _pipe_peer()
    new_read, new_write = _pipe_peer()
    candidate: WAWPeerCandidate | None = None
    retained_fd: int | None = None
    real_close = subject._close
    calls: list[int] = []
    try:
        _bind(authority, 101, old_read)
        retained = authority._current
        assert retained is not None
        retained_fd = retained.pidfd
        os.close(old_write)
        candidate = _candidate(authority, 202, new_read)

        def fail_retained(descriptor: int) -> None:
            calls.append(descriptor)
            if descriptor == retained_fd:
                raise OSError("private close failure")
            real_close(descriptor)

        monkeypatch.setattr(subject, "_close", fail_retained)
        with pytest.raises(WAWPeerAuthorityError) as raised:
            authority.prepare_bind(
                candidate,
                api_authority_epoch="1",
                nonce_digest=NONCE_B,
            )
        assert raised.value.code == "PEER_CLOSE_FAILED"
        assert calls.count(retained_fd) == 1
        assert authority._current is None and authority.poisoned
        with pytest.raises(WAWPeerAuthorityError) as poisoned:
            authority.borrow()
        assert poisoned.value.code == "AUTHORITY_POISONED"
        with pytest.raises(WAWPeerAuthorityError) as closed:
            authority.close()
        assert closed.value is raised.value
    finally:
        if candidate is not None:
            candidate.close()
        with contextlib.suppress(WAWPeerAuthorityError):
            authority.close()
        if retained_fd is not None:
            os.close(retained_fd)
        os.close(old_read)
        os.close(new_read)
        os.close(new_write)


def test_authority_close_detaches_and_attempts_pending_and_current_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    read_fd, write_fd = _pipe_peer()
    _bind(authority, 101, read_fd)
    lease = authority.borrow()
    assert lease is not None
    plan = authority.prepare_bind(
        lease,
        api_authority_epoch="9",
        nonce_digest=NONCE_A,
    )
    current = authority._current
    assert current is not None
    targets = {plan.fileno(), current.pidfd}
    calls: list[int] = []

    def fail_close(descriptor: int) -> None:
        calls.append(descriptor)
        raise OSError("private close failure")

    monkeypatch.setattr(subject, "_close", fail_close)
    try:
        with pytest.raises(WAWPeerAuthorityError) as first:
            authority.close()
        assert first.value.code == "PEER_CLOSE_FAILED"
        assert authority._pending is None and authority._current is None
        assert set(calls) == targets and len(calls) == 2
        with pytest.raises(WAWPeerAuthorityError) as second:
            authority.close()
        assert second.value.code == "PEER_CLOSE_FAILED"
        assert second.value is first.value
        assert len(calls) == 2
    finally:
        for descriptor in targets:
            os.close(descriptor)
        os.close(read_fd)
        os.close(write_fd)


def test_fail_pending_close_error_is_sticky_and_rethrown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    read_fd, write_fd = _pipe_peer()
    plan = authority.prepare_bind(
        _candidate(authority, 101, read_fd),
        api_authority_epoch="1",
        nonce_digest=NONCE_A,
    )
    leaked_fd = plan.fileno()

    def fail_close(descriptor: int) -> None:
        assert descriptor == leaked_fd
        raise OSError("private close failure")

    monkeypatch.setattr(subject, "_close", fail_close)
    try:
        with pytest.raises(WAWPeerAuthorityError) as failed:
            authority.fail_bind(plan)
        assert failed.value.code == "PEER_CLOSE_FAILED" and authority.poisoned
        with pytest.raises(WAWPeerAuthorityError) as closed:
            authority.close()
        assert closed.value is failed.value
    finally:
        os.close(leaked_fd)
        os.close(read_fd)
        os.close(write_fd)


def test_already_bound_plan_close_error_closes_retained_then_rethrows_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    read_fd, write_fd = _pipe_peer()
    _bind(authority, 101, read_fd)
    lease = authority.borrow()
    assert lease is not None
    plan = authority.prepare_bind(
        lease,
        api_authority_epoch="9",
        nonce_digest=NONCE_A,
    )
    leaked_fd = plan.fileno()
    current = authority._current
    assert current is not None
    retained_fd = current.pidfd
    real_close = subject._close
    calls: list[int] = []

    def fail_plan_close(descriptor: int) -> None:
        calls.append(descriptor)
        if descriptor == leaked_fd:
            raise OSError("private close failure")
        real_close(descriptor)

    monkeypatch.setattr(subject, "_close", fail_plan_close)
    try:
        with pytest.raises(WAWPeerAuthorityError) as failed:
            authority.commit_bind(plan)
        assert failed.value.code == "PEER_CLOSE_FAILED" and authority.poisoned
        with pytest.raises(WAWPeerAuthorityError) as closed:
            authority.close()
        assert closed.value is failed.value
        assert calls == [leaked_fd, retained_fd]
    finally:
        os.close(leaked_fd)
        os.close(read_fd)
        os.close(write_fd)


def test_dup_oserror_is_normalized_for_high_fd_path(monkeypatch: pytest.MonkeyPatch) -> None:
    authority = WAWPeerAuthority(expected_uid=UID, expected_gid=GID)
    read_fd, write_fd = _pipe_peer()

    def failed_dup(_descriptor: int) -> int:
        raise OSError("private high-fd failure")

    monkeypatch.setattr(subject, "_dup", failed_dup)
    try:
        with pytest.raises(WAWPeerAuthorityError) as raised:
            authority.observe_control(101, UID, GID, read_fd)
        assert raised.value.code == "PEER_INVALID"
        assert "private" not in str(raised.value)
    finally:
        authority.close()
        os.close(read_fd)
        os.close(write_fd)
