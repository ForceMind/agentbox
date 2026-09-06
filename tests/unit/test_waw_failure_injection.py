"""Unit tests for the pure-Python rc7 deterministic failure controls."""

from __future__ import annotations

import asyncio
import errno
from pathlib import Path
from typing import cast

import pytest
from support.waw_failure_injection import (
    AdmissionCheckpoint,
    CheckpointFailure,
    CheckpointPlan,
    CheckpointPlanError,
    FakeMonotonicClock,
    ManualPromise,
    ManualPromiseState,
    PartialWritePort,
    PartialWritePortClosed,
    ScriptedPartialWriteSocket,
)


@pytest.mark.anyio
async def test_checkpoint_plan_observes_and_releases_exact_sequence() -> None:
    plan = CheckpointPlan.sequence(
        AdmissionCheckpoint.TICKET_RESERVED,
        AdmissionCheckpoint.RUNTIME_PREPARED,
        AdmissionCheckpoint.TICKET_RESERVED,
    )
    task = asyncio.create_task(plan.arrive(AdmissionCheckpoint.TICKET_RESERVED))

    await plan.observe(AdmissionCheckpoint.TICKET_RESERVED)
    assert plan.arrived == [AdmissionCheckpoint.TICKET_RESERVED]
    assert plan.release(AdmissionCheckpoint.TICKET_RESERVED)
    await task

    task = asyncio.create_task(plan.arrive(AdmissionCheckpoint.RUNTIME_PREPARED))
    await plan.observe(AdmissionCheckpoint.RUNTIME_PREPARED)
    assert plan.release(AdmissionCheckpoint.RUNTIME_PREPARED)
    await task

    task = asyncio.create_task(plan.arrive(AdmissionCheckpoint.TICKET_RESERVED))
    await plan.observe(AdmissionCheckpoint.TICKET_RESERVED, occurrence=2)
    assert plan.release(AdmissionCheckpoint.TICKET_RESERVED, occurrence=2)
    await task
    plan.assert_complete()


@pytest.mark.anyio
async def test_checkpoint_plan_rejects_out_of_order_arrival_and_can_fail() -> None:
    plan = CheckpointPlan.sequence(
        AdmissionCheckpoint.RUNTIME_PREPARED,
        AdmissionCheckpoint.COMMIT_SENT,
    )
    with pytest.raises(CheckpointPlanError, match="expected admission.runtime_prepared"):
        await plan.arrive(AdmissionCheckpoint.COMMIT_SENT)

    task = asyncio.create_task(plan.arrive(AdmissionCheckpoint.RUNTIME_PREPARED))
    await plan.observe(AdmissionCheckpoint.RUNTIME_PREPARED)
    assert plan.fail(AdmissionCheckpoint.RUNTIME_PREPARED)
    with pytest.raises(CheckpointFailure, match="checkpoint gate failed"):
        await task
    assert not plan.release(AdmissionCheckpoint.RUNTIME_PREPARED)
    with pytest.raises(CheckpointPlanError, match="admission.commit_sent"):
        plan.assert_complete()


@pytest.mark.anyio
async def test_manual_promise_cancelled_waiter_is_not_revived_by_late_release() -> None:
    promise = ManualPromise()
    waiter = asyncio.create_task(promise.wait())
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    assert promise.resolve()
    assert promise.state is ManualPromiseState.RESOLVED
    assert waiter.cancelled()
    assert not promise.resolve()


@pytest.mark.anyio
async def test_checkpoint_cancelled_arrival_is_not_revived_by_late_release() -> None:
    plan = CheckpointPlan.single(AdmissionCheckpoint.COMMIT_SENT)
    arrival = asyncio.create_task(plan.arrive(AdmissionCheckpoint.COMMIT_SENT))
    await plan.observe(AdmissionCheckpoint.COMMIT_SENT)
    arrival.cancel()
    with pytest.raises(asyncio.CancelledError):
        await arrival

    with pytest.raises(CheckpointPlanError, match="unsettled"):
        plan.assert_complete()
    assert plan.release(AdmissionCheckpoint.COMMIT_SENT)
    assert arrival.cancelled()
    plan.assert_complete()


@pytest.mark.anyio
async def test_checkpoint_plan_rejects_unknown_pre_release_and_early_completion() -> None:
    with pytest.raises(CheckpointPlanError, match="closed rc7 checkpoint"):
        CheckpointPlan.single(cast(AdmissionCheckpoint, "not.closed"))

    plan = CheckpointPlan.single(AdmissionCheckpoint.COMMIT_SENT)
    with pytest.raises(CheckpointPlanError, match="has not arrived"):
        plan.release(AdmissionCheckpoint.COMMIT_SENT)
    pending = asyncio.create_task(plan.arrive(AdmissionCheckpoint.COMMIT_SENT))
    await plan.observe(AdmissionCheckpoint.COMMIT_SENT)
    with pytest.raises(CheckpointPlanError, match="not departed"):
        plan.assert_complete()
    assert plan.release(AdmissionCheckpoint.COMMIT_SENT)
    await pending
    plan.assert_complete()


def test_fake_monotonic_clock_advances_and_rejects_rollback() -> None:
    clock = FakeMonotonicClock(10_000_000_000)
    assert clock.nanoseconds() == 10_000_000_000
    assert clock.seconds() == 10.0
    assert clock.advance_ns(250_000_000) == 10_250_000_000
    assert clock.advance_to(11_000_000_000) == 11_000_000_000
    with pytest.raises(ValueError, match="cannot advance backwards"):
        clock.advance_ns(-1)
    with pytest.raises(ValueError, match="cannot move backwards"):
        clock.advance_to(10_999_999_999)
    assert clock.nanoseconds() == 11_000_000_000
    for invalid in (True, 1.5, float("nan")):
        with pytest.raises(ValueError):
            FakeMonotonicClock(cast(int, invalid))
        with pytest.raises(ValueError):
            clock.advance_ns(cast(int, invalid))
        with pytest.raises(ValueError):
            clock.advance_to(cast(int, invalid))


@pytest.mark.anyio
async def test_partial_write_requires_the_caller_to_recheck_its_guard() -> None:
    port = PartialWritePort(maximum_write=2)
    guard_checks = 0

    async def guarded_write(payload: bytes) -> None:
        nonlocal guard_checks
        guard_checks += 1
        result = await port.write(payload)
        if result.guard_recheck_required:
            guard_checks += 1

    await guarded_write(b"abcd")
    assert [(item.requested, item.written) for item in port.write_log] == [(4, 2)]
    assert port.take_written() == (b"ab",)
    assert port.take_written() == ()
    assert guard_checks == 2


def test_partial_write_controls_reject_non_integer_limits_and_steps() -> None:
    for invalid in (True, 1.5):
        with pytest.raises(ValueError, match="maximum_write"):
            PartialWritePort(maximum_write=cast(int, invalid))
        with pytest.raises(TypeError, match="steps"):
            ScriptedPartialWriteSocket(cast(int, invalid))


@pytest.mark.anyio
async def test_partial_write_blocks_resumes_and_close_rejects_waiter() -> None:
    port = PartialWritePort(maximum_write=3)
    port.block()
    pending = asyncio.create_task(port.write(b"abc"))
    await asyncio.sleep(0)
    assert not pending.done()

    assert port.resume()
    result = await pending
    assert result.written == 3
    assert not result.guard_recheck_required
    assert [(item.requested, item.written) for item in port.write_log] == [(3, 3)]
    assert port.take_written() == (b"abc",)

    port.block()
    blocked = asyncio.create_task(port.write(b"z"))
    await asyncio.sleep(0)
    port.close()
    with pytest.raises(PartialWritePortClosed, match="closed"):
        await blocked
    with pytest.raises(PartialWritePortClosed, match="closed"):
        await port.write(b"later")
    port.assert_drained()


def test_scripted_socket_records_only_metadata_and_requires_guard_recheck() -> None:
    socket = ScriptedPartialWriteSocket(2, BlockingIOError(errno.EAGAIN, "blocked"), 0)
    assert socket.send(b"abcd") == 2
    assert socket.write_log[0].guard_recheck_required
    with pytest.raises(BlockingIOError):
        socket.send(b"remaining")
    assert socket.send(b"remaining") == 0
    assert socket.write_log[-1].guard_recheck_required
    assert all(not hasattr(entry, "payload") for entry in socket.write_log)
    socket.close()
    socket.assert_drained()
    with pytest.raises(PartialWritePortClosed, match="closed"):
        socket.send(b"late")


def test_rc7_controls_have_no_production_import_edge() -> None:
    """Keep failure controls test-only even as the production tree evolves."""

    repository = Path(__file__).resolve().parents[2]
    source_roots = (
        repository / "apps" / "api" / "src",
        repository / "apps" / "cli" / "src",
        repository / "apps" / "worker" / "src",
        repository / "apps" / "web" / "src",
        repository / "packages",
    )
    forbidden = ("waw_failure_injection", "wawRc7TestHarness", "WAW_RC7")
    offenders: list[str] = []
    for root in source_roots:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"}:
                continue
            if ".test." in path.name or path.name == "wawRc7TestHarness.ts":
                continue
            source = path.read_text(encoding="utf-8")
            if any(marker in source for marker in forbidden):
                offenders.append(str(path.relative_to(repository)))

    assert offenders == []
