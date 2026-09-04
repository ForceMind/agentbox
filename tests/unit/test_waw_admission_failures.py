"""Actual R6 wire/authority with explicitly synthetic browser/Runtime ports."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from agentbox_api.waw_admission_coordinator import AdmissionAuditAction as A
from agentbox_api.waw_admission_coordinator import AdmissionFailure
from agentbox_core.waw_tickets import AdmissionStage
from agentbox_protocol.abws import FrameType as F
from agentbox_protocol.waw_wire import WireFrame, decode_wire_frame, encode_wire_frame
from support.waw_admission import AB, RA, Harness


def negative(sequence: int, *, request_id: str | None = "wreq_" + "f" * 32) -> bytes:
    return encode_wire_frame(
        F.ERROR,
        RA,
        {
            "protocol_version": 1,
            "code": "KEY_CONFIRM_FAILED",
            "retryable": False,
            "request_id": request_id,
        },
        sequence,
        trusted_context=request_id is not None,
    )


def frames(h: Harness) -> list[WireFrame]:
    return [decode_wire_frame(raw, AB) for raw in h.browser.sent]


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        (F.HELLO_ACK, [F.ERROR]),
        (F.KEY_ATTEST, [F.ERROR]),
        (F.KEY_CONFIRM_ACK, [F.KEY_ATTEST, F.ERROR, F.CLOSE]),
        (F.STREAM_READY_ACK, [F.KEY_ATTEST, F.KEY_CONFIRM_ACK, F.ERROR, F.CLOSE]),
    ],
)
def test_valid_runtime_error_reaches_browser_in_its_actual_phase(
    monkeypatch: pytest.MonkeyPatch, stage: F, expected: list[F]
) -> None:
    async def scenario() -> None:
        h = Harness()
        reply = h.runtime._reply
        failed = False

        def inject(kind: F, sequence: int) -> None:
            nonlocal failed
            if failed:
                return
            if kind == stage:
                failed = True
                h.runtime.incoming.put_nowait(negative(sequence))
            else:
                reply(kind, sequence)

        monkeypatch.setattr(h.runtime, "_reply", inject)
        with pytest.raises(AdmissionFailure):
            await h.coordinator.run()
        received = frames(h)
        assert [f.frame_type for f in received] == expected
        assert [f.hop_sequence for f in received] == list(range(1, len(expected) + 1))
        error = next(f for f in received if f.frame_type == F.ERROR)
        body = error.json_payload
        original = decode_wire_frame(negative(1), RA).json_payload
        assert body is not None and original is not None
        assert body["request_id"] != original["request_id"]
        assert {k: v for k, v in body.items() if k != "request_id"} == {
            k: v for k, v in original.items() if k != "request_id"
        }
        assert h.browser.closed == 1013
        assert h.runtime.cleanup_requests and h.runtime.aborted
        assert h.audit.events[-1].action == A.DETACHED
        assert h.coordinator.queue.read() is None

    asyncio.run(scenario())


def test_bound_runtime_null_request_id_is_not_forwarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        h = Harness()

        def inject(kind: F, sequence: int) -> None:
            if sequence == 1:
                h.runtime.incoming.put_nowait(negative(1, request_id=None))

        monkeypatch.setattr(h.runtime, "_reply", inject)
        with pytest.raises(AdmissionFailure):
            await h.coordinator.run()
        # The API already emitted RUNTIME_HELLO, so its observer has a bound
        # context even if Runtime failed before returning HELLO_ACK.
        assert h.browser.sent == []
        assert h.runtime.cleanup_requests and h.runtime.aborted

    asyncio.run(scenario())


def test_negative_state_is_translated_without_internal_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        h = Harness()
        reply = h.runtime._reply

        def inject(kind: F, sequence: int) -> None:
            if kind == F.KEY_CONFIRM_ACK:
                h.runtime.incoming.put_nowait(
                    encode_wire_frame(
                        F.STATE,
                        RA,
                        {
                            "protocol_version": 1,
                            "workspace_id": h.a["workspace_id"],
                            "project_id": h.a["project_id"],
                            "agent_type": h.a["agent_type"],
                            "generation": h.a["generation"],
                            "state": "UNKNOWN",
                            "reason_code": "RECONCILIATION_REQUIRED",
                            "runtime_epoch": "2",
                        },
                        sequence,
                    )
                )
            else:
                reply(kind, sequence)

        monkeypatch.setattr(h.runtime, "_reply", inject)
        with pytest.raises(AdmissionFailure):
            await h.coordinator.run()
        received = frames(h)
        assert [f.frame_type for f in received] == [F.KEY_ATTEST, F.STATE, F.CLOSE]
        assert received[1].json_payload is not None
        assert "runtime_epoch" not in received[1].json_payload
        assert received[-1].json_payload is not None
        assert received[-1].json_payload["workspace_state_at_close"] == "UNKNOWN"

    asyncio.run(scenario())


def test_rejected_commit_translates_without_admitted_publication() -> None:
    async def scenario() -> None:
        h = Harness()
        h.runtime.reject_commit = True
        with pytest.raises(AdmissionFailure):
            await h.coordinator.run()
        assert [f.frame_type for f in frames(h)] == [
            F.KEY_ATTEST,
            F.KEY_CONFIRM_ACK,
            F.ERROR,
            F.CLOSE,
        ]
        error = frames(h)[-2].json_payload
        assert error is not None and error["code"] == "ADMITTED_DELIVERY_FAILED"
        assert all(event.action != A.ADMITTED for event in h.audit.events)

    asyncio.run(scenario())


def test_uncertain_key_write_gets_no_appended_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        h = Harness()
        entered = asyncio.Event()

        async def blocked(raw: bytes) -> None:
            h.browser.sent.append(raw)  # Synthetic partial/uncertain transport write.
            entered.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(h.browser, "send_key_frame", blocked)
        task = asyncio.create_task(h.coordinator.run())
        await asyncio.wait_for(entered.wait(), 1)
        h.runtime.incoming.put_nowait(negative(3))
        with pytest.raises(AdmissionFailure):
            await asyncio.wait_for(task, 2)
        assert [f.frame_type for f in frames(h)] == [F.KEY_ATTEST]
        assert h.browser.closed == 1013
        assert h.audit.events[-1].action == A.DETACHED

    asyncio.run(scenario())


def test_invalid_runtime_error_is_not_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        h = Harness()

        def inject(kind: F, sequence: int) -> None:
            if sequence == 1:
                h.runtime.incoming.put_nowait(negative(1)[:-1] + b"!")

        monkeypatch.setattr(h.runtime, "_reply", inject)
        with pytest.raises(AdmissionFailure):
            await h.coordinator.run()
        assert h.browser.sent == []
        assert h.audit.events[-1].action == A.DETACHED

    asyncio.run(scenario())


def test_failed_metadata_write_does_not_skip_cleanup_or_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        h = Harness()
        h.runtime.reject_commit = True
        send = h.browser.send_key_frame

        async def blocked(raw: bytes) -> None:
            if decode_wire_frame(raw, AB).frame_type == F.ERROR:
                await asyncio.Event().wait()
            await send(raw)

        monkeypatch.setattr(h.browser, "send_key_frame", blocked)
        with pytest.raises(AdmissionFailure):
            await asyncio.wait_for(h.coordinator.run(), 1.5)
        assert [f.frame_type for f in frames(h)] == [F.KEY_ATTEST, F.KEY_CONFIRM_ACK]
        assert h.runtime.cleanup_requests and h.runtime.aborted
        assert h.audit.events[-1].action == A.DETACHED
        assert h.browser.closed == 1013

    asyncio.run(scenario())


def test_revoked_auth_suppresses_failure_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        h = Harness()
        h.runtime.reject_commit = True
        signal = h.coordinator._signal

        def revoke(error: AdmissionFailure) -> None:
            signal(error)
            h.validator.valid = False

        monkeypatch.setattr(h.coordinator, "_signal", revoke)
        with pytest.raises(AdmissionFailure):
            await h.coordinator.run()
        assert [f.frame_type for f in frames(h)] == [F.KEY_ATTEST, F.KEY_CONFIRM_ACK]
        assert h.runtime.cleanup_requests and h.runtime.aborted
        assert h.audit.events[-1].action == A.DETACHED

    asyncio.run(scenario())


def test_cancellation_resistant_failure_writer_keeps_reservation_fenced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        h = Harness()
        h.runtime.reject_commit = True
        send = h.browser.send_key_frame
        release, finished = asyncio.Event(), asyncio.Event()

        async def resistant(raw: bytes) -> None:
            if decode_wire_frame(raw, AB).frame_type == F.ERROR:
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    await release.wait()
                finally:
                    finished.set()
                # This synthetic port enforces the required close fence.
                if h.browser.closed is not None:
                    raise ConnectionError("closed")
            await send(raw)

        monkeypatch.setattr(h.browser, "send_key_frame", resistant)
        with pytest.raises(AdmissionFailure):
            await asyncio.wait_for(h.coordinator.run(), 1.5)
        handle = h.coordinator.reservation
        assert handle is not None and h.authority.stage(handle) == AdmissionStage.FENCED
        assert h.authority.record_count == 1
        assert h.audit.events[-1].action == A.DETACHED
        assert h.runtime.cleanup_requests and h.runtime.aborted
        release.set()
        await asyncio.wait_for(finished.wait(), 1)
        await asyncio.sleep(0)
        assert [f.frame_type for f in frames(h)] == [F.KEY_ATTEST, F.KEY_CONFIRM_ACK]
        assert h.authority.stage(handle) == AdmissionStage.FENCED

    asyncio.run(scenario())


def test_cancellation_during_notification_does_not_skip_cleanup_or_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        h = Harness()
        h.runtime.reject_commit = True
        entered = asyncio.Event()

        async def pending(deadline: float) -> None:
            entered.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(h.coordinator, "_publish_runtime_failure", pending)
        task = asyncio.create_task(h.coordinator.run())
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(AdmissionFailure):
            await asyncio.wait_for(task, 1.5)
        assert h.runtime.cleanup_requests and h.runtime.aborted
        assert h.audit.events[-1].action == A.DETACHED
        assert h.browser.closed == 1013

    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["revoke", "epoch", "deadline", "clock_rollback"])
def test_failure_frames_each_require_a_current_permission(
    monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    async def scenario() -> None:
        h = Harness()
        h.runtime.reject_commit = True
        send = h.browser.send_key_frame

        async def after_error(raw: bytes) -> None:
            await send(raw)
            if decode_wire_frame(raw, AB).frame_type == F.ERROR:
                if change == "revoke":
                    h.validator.valid = False
                elif change == "epoch":
                    h.runtime.connection_id = object()
                elif change == "deadline":
                    h.clock.ns += 5_000_000_000
                else:
                    h.clock.ns -= 1

        monkeypatch.setattr(h.browser, "send_key_frame", after_error)
        with pytest.raises(AdmissionFailure):
            await h.coordinator.run()
        assert [f.frame_type for f in frames(h)] == [F.KEY_ATTEST, F.KEY_CONFIRM_ACK, F.ERROR]
        assert h.browser.closed == 1013
        assert h.runtime.cleanup_requests and h.runtime.aborted
        assert h.audit.events[-1].action == A.DETACHED

    asyncio.run(scenario())


@pytest.mark.parametrize("entry", ["failure", "cancel"])
def test_authority_fence_failure_finishes_cleanup_and_retains_record(
    monkeypatch: pytest.MonkeyPatch, entry: str
) -> None:
    async def scenario() -> None:
        h = Harness()
        fence_error = RuntimeError("synthetic authority fence failure")
        fence_calls = 0
        if entry == "failure":
            h.audit.fail = A.ADMITTED
        else:
            h.runtime.block = "prepare"

        def fail_fence(_handle: Any) -> None:
            nonlocal fence_calls
            fence_calls += 1
            raise fence_error

        monkeypatch.setattr(h.authority, "fence", fail_fence)
        running = asyncio.create_task(h.coordinator.run())
        if entry == "cancel":
            await asyncio.wait_for(h.runtime.entered.wait(), 1)
            running.cancel()
            h.runtime.resume.set()
        with pytest.raises(RuntimeError) as raised:
            await running
        assert raised.value is fence_error
        assert fence_calls == len(h.runtime.cleanup_requests) == 1
        assert [event.action for event in h.audit.events].count(A.DETACHED) == 1
        assert h.runtime.aborted and h.browser.closed == (1013 if entry == "failure" else 4403)
        assert h.input_budget.closed and h.coordinator.wire_session.closed
        assert h.coordinator.queue.read() is None and h.authority.record_count == 1
        cleanup_task = h.coordinator._cleanup_task
        with pytest.raises(RuntimeError) as repeated:
            await h.coordinator._cleanup(AdmissionFailure())
        assert repeated.value is fence_error
        assert h.coordinator._cleanup_task is cleanup_task
        assert fence_calls == len(h.runtime.cleanup_requests) == 1

    asyncio.run(scenario())


def test_fence_error_precedes_secondary_cleanup_and_audit_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        h = Harness()
        h.audit.fail = A.ADMITTED
        fence_error = RuntimeError("synthetic authority fence failure")
        cleanup_error = RuntimeError("secondary Runtime cleanup failure")
        audit_error = RuntimeError("secondary Audit failure")
        detached_attempts = 0
        original_audit = h.audit.persist

        def fail_fence(_handle: Any) -> None:
            raise fence_error

        async def fail_cleanup(request: Any) -> Any:
            h.runtime.cleanup_requests.append(request)
            raise cleanup_error

        async def fail_detached_audit(event: Any) -> None:
            nonlocal detached_attempts
            if event.action == A.DETACHED:
                detached_attempts += 1
                raise audit_error
            await original_audit(event)

        monkeypatch.setattr(h.authority, "fence", fail_fence)
        monkeypatch.setattr(h.runtime, "close_and_cleanup", fail_cleanup)
        monkeypatch.setattr(h.audit, "persist", fail_detached_audit)
        with pytest.raises(RuntimeError) as raised:
            await h.coordinator.run()
        assert raised.value is fence_error
        assert len(h.runtime.cleanup_requests) == detached_attempts == 1
        assert h.runtime.aborted and h.browser.closed == 1013
        assert h.input_budget.closed and h.coordinator.wire_session.closed
        assert h.coordinator.queue.read() is None and h.authority.record_count == 1

    asyncio.run(scenario())


def test_positive_cleanup_and_audit_release_once_and_repeat_is_idempotent() -> None:
    async def scenario() -> None:
        h = Harness()
        h.audit.fail = A.ADMITTED
        with pytest.raises(AdmissionFailure):
            await h.coordinator.run()
        cleanup_task = h.coordinator._cleanup_task
        assert cleanup_task is not None and cleanup_task.done()
        assert len(h.runtime.cleanup_requests) == 1
        assert [event.action for event in h.audit.events] == [A.PREPARED, A.DETACHED]
        assert h.authority.record_count == 0
        await h.coordinator._cleanup(AdmissionFailure())
        assert h.coordinator._cleanup_task is cleanup_task
        assert len(h.runtime.cleanup_requests) == 1
        assert [event.action for event in h.audit.events] == [A.PREPARED, A.DETACHED]

    asyncio.run(scenario())
