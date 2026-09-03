"""Adversarial asynchronous ports exercise actual R6 flow, using synthetic keys.

No Noise verification or real Runtime/PTY/host qualification is claimed here.
"""

from __future__ import annotations

import asyncio
import gc
from dataclasses import replace
from typing import Any

import pytest
from agentbox_api.waw_admission import wire_admission_tuple
from agentbox_api.waw_admission_coordinator import (
    AdmissionAuditAction as A,
)
from agentbox_api.waw_admission_coordinator import (
    AdmissionAuditEvent,
    AdmissionFailure,
    BoundedAdmissionQueue,
    PendingAdmissionBudget,
    RuntimeCleanupProof,
    RuntimeCleanupRequest,
    RuntimePrepared,
    RuntimePrepareRequest,
    WAWAdmissionCoordinator,
)
from agentbox_core.waw import workspace_id
from agentbox_core.waw_tickets import AdmissionStage as S
from agentbox_core.waw_tickets import (
    AttachmentAuthority,
    AttachmentTuple,
    AuthenticatedAttachmentContext,
)
from agentbox_protocol.abws import FrameType as F
from agentbox_protocol.awce import encode_awce_header
from agentbox_protocol.waw_crypto_context import derive_context
from agentbox_protocol.waw_wire import Leg, decode_wire_frame, encode_wire_frame

BA, AB, AR, RA = tuple(Leg)


class Clock:
    def __init__(self) -> None:
        self.ns = 100_000_000_000

    def __call__(self) -> int:
        return self.ns


class Validator:
    valid = True

    def current(self, claims: AttachmentTuple, context: AuthenticatedAttachmentContext) -> bool:
        return self.valid


class Audit:
    def __init__(self) -> None:
        self.events: list[AdmissionAuditEvent] = []
        self.block: A | None = None
        self.entered = asyncio.Event()
        self.resume = asyncio.Event()
        self.fail: A | None = None

    async def persist(self, event: AdmissionAuditEvent) -> None:
        if event.action == self.block:
            self.entered.set()
            await self.resume.wait()
        if event.action == self.fail:
            raise RuntimeError("AUDIT-PRIVATE-CANARY")
        self.events.append(event)
        await asyncio.sleep(0)


class Browser:
    def __init__(self, harness: Harness) -> None:
        self.h = harness
        self.incoming: asyncio.Queue[bytes] = asyncio.Queue(maxsize=8)
        self.sent: list[bytes] = []
        self.closed: int | None = None

    async def receive(self) -> bytes:
        return await self.incoming.get()

    async def send_key_frame(self, frame: bytes) -> None:
        self.sent.append(frame)
        kind = decode_wire_frame(frame, AB).frame_type
        if kind == F.KEY_ATTEST:
            self.incoming.put_nowait(self.h.frame(F.KEY_CONFIRM, BA, 3))
        await asyncio.sleep(0)

    def close(self, code: int) -> None:
        self.closed = code


class Runtime:
    def __init__(self, harness: Harness) -> None:
        self.h = harness
        self.connection_id = object()
        self.incoming: asyncio.Queue[bytes] = asyncio.Queue(maxsize=8)
        self.sent: list[bytes] = []
        self.prepares = 0
        self.commits = 0
        self.cleanup_requests: list[RuntimeCleanupRequest] = []
        self.cleanup_positive = True
        self.cleanup_wrong_tuple = False
        self.cleanup_wrong_connection = False
        self.aborted = False
        self.drop_commits = 0
        self.reject_commit = False
        self.extra_outputs = 0
        self.output_size = 1
        self.block: F | str | None = None
        self.entered = asyncio.Event()
        self.resume = asyncio.Event()
        self.mutate_response: F | None = None

    async def _barrier(self, action: F | str) -> None:
        if action == self.block:
            self.entered.set()
            await self.resume.wait()
        await asyncio.sleep(0)

    async def prepare(self, request: RuntimePrepareRequest) -> RuntimePrepared:
        self.prepares += 1
        await self._barrier("prepare")
        return RuntimePrepared(request.claims, request.runtime_epoch, self.connection_id, "c" * 64)

    async def send(self, frame: bytes) -> None:
        decoded = decode_wire_frame(frame, AR)
        self.sent.append(frame)
        await self._barrier(decoded.frame_type)
        if decoded.frame_type == F.KEY_INIT:
            self._reply(F.HELLO_ACK, 1)
            self._reply(F.KEY_ATTEST, 2)
        elif decoded.frame_type == F.KEY_CONFIRM:
            self._reply(F.KEY_CONFIRM_ACK, 3)
        elif decoded.frame_type == F.STREAM_READY:
            self._reply(F.STREAM_READY_ACK, 4)
        elif decoded.frame_type == F.ADMISSION_COMMIT:
            self.commits += 1
            if self.drop_commits > 0:
                self.drop_commits -= 1
                return
            payload = self.h.payload(F.ADMISSION_COMMIT_ACK)
            if self.reject_commit:
                payload.update(result="rejected", reason_code="ATTACHMENT_STALE")
            self.incoming.put_nowait(encode_wire_frame(F.ADMISSION_COMMIT_ACK, RA, payload, 5))
            for number in range(self.extra_outputs):
                raw = encode_awce_header(
                    crypto_envelope_version=1,
                    direction_id=2,
                    flags=0,
                    crypto_sequence=number + 1,
                    stream_cursor=number + 1,
                    context_id=bytes.fromhex("e" * 32),
                    ciphertext_length=self.output_size + 16,
                ) + b"x" * (self.output_size + 16)
                self.incoming.put_nowait(encode_wire_frame(F.OUTPUT, RA, raw, 6 + number))

    def _reply(self, kind: F, seq: int) -> None:
        payload = self.h.payload(kind)
        if kind == self.mutate_response:
            payload["runtime_epoch"] = "999"
        self.incoming.put_nowait(encode_wire_frame(kind, RA, payload, seq))

    async def receive(self) -> bytes:
        return await self.incoming.get()

    async def close_and_cleanup(self, request: RuntimeCleanupRequest) -> RuntimeCleanupProof:
        self.cleanup_requests.append(request)
        await asyncio.sleep(0)
        return RuntimeCleanupProof(
            replace(request.claims, generation=9) if self.cleanup_wrong_tuple else request.claims,
            request.runtime_epoch,
            object() if self.cleanup_wrong_connection else request.connection_id,
            "detached" if self.cleanup_positive else "rejected",
            "ATTACH_PTY_CLOSED" if self.cleanup_positive else "UNKNOWN",
        )

    def abort(self) -> None:
        self.aborted = True


class Harness:
    def __init__(self, *, queue: BoundedAdmissionQueue | None = None) -> None:
        # Collect prior cyclic fake ports before entering the 5 ms wire CPU budget.
        gc.collect()
        self.clock = Clock()
        self.authority = AttachmentAuthority(
            clock=lambda: self.clock.ns / 1_000_000_000, authority_epoch=4
        )
        self.context = AuthenticatedAttachmentContext(
            "private-session", "admin", "scope", "https://agentbox.invalid", "2", 3
        )
        project = "prj_" + "1" * 32
        self.ticket = self.authority.issue(
            workspace_id=workspace_id(project, "codex"),
            project_id=project,
            agent_type="codex",
            attachment_id="att_" + "2" * 32,
            generation=1,
            auth_epoch=3,
            runtime_host_installation_id="wri_" + "a" * 32,
            runtime_host_installation_revision=1,
            binding_revision=1,
            binding_digest="b" * 64,
            context=self.context,
        )
        self.a = wire_admission_tuple(self.ticket.claims)
        self.c = derive_context(self.a, "2")
        self.runtime, self.browser, self.audit = Runtime(self), Browser(self), Audit()
        self.validator = Validator()
        self.budget = PendingAdmissionBudget()
        self.coordinator = WAWAdmissionCoordinator(
            authority=self.authority,
            claims=self.ticket.claims,
            context=self.context,
            runtime=self.runtime,
            browser=self.browser,
            audit=self.audit,
            revalidator=self.validator,
            budget=self.budget,
            source="source",
            started_at_ns=self.clock.ns,
            clock_ns=self.clock,
            queue=queue,
        )
        self.browser.incoming.put_nowait(self.frame(F.WS_HELLO, BA, 1))
        self.browser.incoming.put_nowait(self.frame(F.KEY_INIT, BA, 2))

    def payload(self, kind: F) -> dict[str, Any]:
        base: dict[str, Any] = {"protocol_version": 1}
        common = {**base, **self.a, "runtime_epoch": "2"}
        if kind == F.WS_HELLO:
            return {
                **common,
                "ticket": self.ticket.ticket,
                "resume_cursor": None,
                "previous_runtime_epoch": None,
            }
        if kind in (F.KEY_INIT, F.KEY_ATTEST):
            extra = (
                {"browser_ephemeral_public_key": "A" * 43, "noise_message_1": "A" * 43}
                if kind == F.KEY_INIT
                else {
                    "runtime_attestation_x25519_fingerprint": "d" * 64,
                    "runtime_ephemeral_public_key": "A" * 43,
                    "noise_message_2": "A" * 171,
                }
            )
            return {
                **common,
                "noise_protocol": "Noise_NX_25519_AESGCM_SHA256",
                "crypto_envelope_version": 1,
                **extra,
            }
        if kind in (F.KEY_CONFIRM, F.KEY_CONFIRM_ACK):
            return {
                **base,
                **self.c,
                "noise_protocol": "Noise_NX_25519_AESGCM_SHA256",
                "ciphertext": "A" * 64,
                **(
                    {"status": "verified", "transcript_context_hash": "e" * 64}
                    if kind == F.KEY_CONFIRM_ACK
                    else {}
                ),
            }
        if kind in (F.HELLO_ACK, F.STREAM_READY_ACK):
            return {
                **common,
                "state": "RUNNING",
                "output_cursor": "0",
                **(
                    {"input_limit": 16384, "output_limit": 32768}
                    if kind == F.HELLO_ACK
                    else {"admission_fence": "f" * 64}
                ),
            }
        if kind == F.ADMISSION_COMMIT_ACK:
            return {**common, "result": "committed", "reason_code": None}
        raise AssertionError(kind)

    def frame(self, kind: F, leg: Leg, seq: int) -> bytes:
        return encode_wire_frame(kind, leg, self.payload(kind), seq)

    def active(self) -> bool:
        return self.authority.is_active(self.ticket.claims, context=self.context)


def test_full_flow_publishes_only_after_both_durable_events() -> None:
    async def scenario() -> None:
        h = Harness()
        lease = await h.coordinator.run()
        assert lease.claims == h.ticket.claims and h.active()
        assert [event.action for event in h.audit.events] == [A.PREPARED, A.ADMITTED]
        admitted = h.coordinator.queue.read()
        assert admitted is not None and decode_wire_frame(admitted, AB).frame_type == F.ADMITTED
        assert h.coordinator.queue.read() is None
        assert [decode_wire_frame(frame, AB).frame_type for frame in h.browser.sent] == [
            F.KEY_ATTEST,
            F.KEY_CONFIRM_ACK,
        ]
        assert h.budget.count == 0
        assert h.runtime.commits == 1
        await asyncio.sleep(0)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "barrier",
    [
        "prepare",
        F.RUNTIME_HELLO,
        F.KEY_INIT,
        F.KEY_CONFIRM,
        F.STREAM_READY,
        F.ADMISSION_COMMIT,
        A.PREPARED,
        A.ADMITTED,
    ],
)
def test_no_active_writer_or_quarantine_leak_at_every_await(barrier: F | A | str) -> None:
    async def scenario() -> None:
        h = Harness()
        target = h.audit if isinstance(barrier, A) else h.runtime
        target.block = barrier
        task = asyncio.create_task(h.coordinator.run())
        await asyncio.wait_for(target.entered.wait(), 1)
        assert not h.active()
        assert h.authority.active_count == 0
        assert h.coordinator.queue.read() is None
        target.resume.set()
        await task
        assert h.active()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "barrier",
    [
        "prepare",
        F.RUNTIME_HELLO,
        F.KEY_INIT,
        F.KEY_CONFIRM,
        F.STREAM_READY,
        F.ADMISSION_COMMIT,
        A.PREPARED,
        A.ADMITTED,
    ],
)
@pytest.mark.parametrize("invalidator", ["revoke", "expired", "changed", "cancel", "input"])
def test_revocation_expiry_cancel_and_input_at_every_transition(
    barrier: F | A | str, invalidator: str
) -> None:
    async def scenario() -> None:
        h = Harness()
        target = h.audit if isinstance(barrier, A) else h.runtime
        target.block = barrier
        task = asyncio.create_task(h.coordinator.run())
        await asyncio.wait_for(target.entered.wait(), 1)
        if invalidator == "revoke":
            h.authority.revoke_session(session_id=h.context.session_id, auth_epoch=3)
        elif invalidator == "expired":
            h.clock.ns += 5_000_000_000
        elif invalidator == "changed":
            h.validator.valid = False
        elif invalidator == "cancel":
            task.cancel()
        else:
            # An early complete frame is never retained or assigned an input ACK.
            h.browser.incoming.put_nowait(b"PRIVATE-EARLY-INPUT")
        target.resume.set()
        with pytest.raises((AdmissionFailure, asyncio.CancelledError)):
            await task
        assert not h.active()
        assert h.coordinator.queue.read() is None
        assert all(
            decode_wire_frame(frame, AB).frame_type != F.ADMITTED for frame in h.browser.sent
        )
        assert h.budget.count == 0
        assert h.runtime.aborted
        assert len(h.runtime.cleanup_requests) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "fault", ["prepared_audit", "admitted_audit", "quarantine", "release", "commit_reject"]
)
def test_delivery_failures_close_internal_stream_and_never_publish(fault: str) -> None:
    async def scenario() -> None:
        class FailingQueue(BoundedAdmissionQueue):
            def quarantine(self, admitted: bytes) -> None:
                if fault == "quarantine":
                    raise RuntimeError("PRIVATE-QUEUE-CANARY")
                super().quarantine(admitted)

            def release(self) -> None:
                if fault == "release":
                    raise RuntimeError("PRIVATE-QUEUE-CANARY")
                super().release()

        h = Harness(queue=FailingQueue())
        h.audit.fail = (
            A.PREPARED
            if fault == "prepared_audit"
            else A.ADMITTED if fault == "admitted_audit" else None
        )
        h.runtime.reject_commit = fault == "commit_reject"
        with pytest.raises(AdmissionFailure) as raised:
            await h.coordinator.run()
        assert raised.value.code == "ADMITTED_DELIVERY_FAILED"
        assert h.browser.closed == 1013
        assert not h.active() and h.coordinator.queue.read() is None
        assert h.audit.events[-1].action == A.DETACHED
        close = h.runtime.cleanup_requests[0].close_frame
        assert close is not None
        assert decode_wire_frame(close, AR).json_payload == {
            "protocol_version": 1,
            "code": "INTERNAL_BOUNDED",
            "workspace_state_at_close": "RUNNING",
        }
        assert h.authority.record_count == 0
        assert "PRIVATE" not in repr(raised.value)

    asyncio.run(scenario())


@pytest.mark.parametrize("fault", ["no_proof", "wrong_tuple", "wrong_connection", "failure_audit"])
def test_missing_exact_cleanup_or_durable_failure_retains_fenced_slot(fault: str) -> None:
    async def scenario() -> None:
        h = Harness()
        h.audit.block = A.ADMITTED
        h.runtime.cleanup_positive = fault != "no_proof"
        h.runtime.cleanup_wrong_tuple = fault == "wrong_tuple"
        h.runtime.cleanup_wrong_connection = fault == "wrong_connection"
        if fault == "failure_audit":
            h.audit.fail = A.DETACHED
        task = asyncio.create_task(h.coordinator.run())
        await h.audit.entered.wait()
        h.validator.valid = False
        h.audit.resume.set()
        with pytest.raises(AdmissionFailure):
            await task
        handle = h.coordinator.reservation
        assert handle is not None and h.authority.stage(handle) == S.FENCED
        assert h.authority.record_count == 1
        assert not h.active()

    asyncio.run(scenario())


def test_exact_single_commit_retry_on_same_stream() -> None:
    async def scenario() -> None:
        h = Harness()
        h.runtime.drop_commits = 1
        await h.coordinator.run()
        commits = [
            frame
            for frame in h.runtime.sent
            if decode_wire_frame(frame, AR).frame_type == F.ADMISSION_COMMIT
        ]
        assert len(commits) == 2 and commits[0] == commits[1]
        assert h.runtime.commits == 2
        assert h.active()

    asyncio.run(scenario())


@pytest.mark.parametrize("count,size,success", [(1, 32768, True), (2, 32768, False), (2, 1, True)])
def test_committed_output_is_quarantined_bounded_and_ordered(
    count: int, size: int, success: bool
) -> None:
    async def scenario() -> None:
        h = Harness()
        h.runtime.extra_outputs, h.runtime.output_size = count, size
        h.audit.block = A.ADMITTED
        task = asyncio.create_task(h.coordinator.run())
        if success:
            await h.audit.entered.wait()
            assert h.coordinator.queue.read() is None and not h.active()
            h.audit.resume.set()
            await task
            frames = [h.coordinator.queue.read() for _ in range(count + 1)]
            assert all(frame is not None for frame in frames)
            assert [decode_wire_frame(frame, AB).frame_type for frame in frames] == [F.ADMITTED] + [
                F.OUTPUT
            ] * count
        else:
            with pytest.raises(AdmissionFailure):
                await task
            assert not h.active() and h.coordinator.queue.read() is None

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", [F.HELLO_ACK, F.KEY_ATTEST, F.KEY_CONFIRM_ACK, F.STREAM_READY_ACK])
def test_nominal_success_wrong_epoch_never_advances_authority(kind: F) -> None:
    async def scenario() -> None:
        h = Harness()
        h.runtime.mutate_response = kind
        with pytest.raises(AdmissionFailure):
            await h.coordinator.run()
        assert not h.active() and h.coordinator.queue.read() is None
        assert A.ADMITTED not in [event.action for event in h.audit.events]

    asyncio.run(scenario())


def test_budget_is_bounded_and_invalid_ticket_never_prepares_runtime() -> None:
    async def scenario() -> None:
        h = Harness()
        hello = h.payload(F.WS_HELLO)
        hello["ticket"] = "wat_" + "0" * 32
        h.browser.incoming.get_nowait()
        h.browser.incoming.get_nowait()
        h.browser.incoming.put_nowait(encode_wire_frame(F.WS_HELLO, BA, hello, 1))
        with pytest.raises(AdmissionFailure):
            await h.coordinator.run()
        assert h.runtime.prepares == 0 and h.budget.count == 0

    asyncio.run(scenario())
    budget = PendingAdmissionBudget(maximum=2, per_source=1)
    first = budget.acquire("a")
    with pytest.raises(AdmissionFailure):
        budget.acquire("a")
    second = budget.acquire("b")
    with pytest.raises(AdmissionFailure):
        budget.acquire("c")
    budget.release(first)
    budget.release(second)
    assert budget.count == 0


def test_audit_and_repr_never_contain_private_material() -> None:
    async def scenario() -> None:
        h = Harness()
        await h.coordinator.run()
        for value in [repr(h.audit.events), repr(h.coordinator), repr(h.coordinator.reservation)]:
            for private in [
                h.ticket.ticket,
                "private-session",
                "c" * 64,
                "e" * 64,
                "f" * 64,
                "A" * 64,
                "b" * 64,
            ]:
                assert private not in value

    asyncio.run(scenario())


def test_cancel_resistant_late_prepare_cannot_free_or_reactivate_slot() -> None:
    async def scenario() -> None:
        h = Harness()
        entered, finish = asyncio.Event(), asyncio.Event()

        async def late_prepare(request: RuntimePrepareRequest) -> RuntimePrepared:
            h.runtime.prepares += 1
            entered.set()
            try:
                await finish.wait()
            except asyncio.CancelledError:
                await finish.wait()
            return RuntimePrepared(
                request.claims, request.runtime_epoch, request.connection_id, "c" * 64
            )

        h.runtime.prepare = late_prepare  # type: ignore[method-assign]
        task = asyncio.create_task(h.coordinator.run())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        handle = h.coordinator.reservation
        assert handle is not None and h.authority.stage(handle) == S.FENCED
        assert h.authority.record_count == 1
        finish.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert h.authority.stage(handle) == S.FENCED
        assert h.coordinator.queue.read() is None
        assert h.runtime.commits == 0
        assert len(h.runtime.cleanup_requests) == 1

    asyncio.run(scenario())


def test_original_deadline_times_out_blocked_port_without_renewal() -> None:
    async def scenario() -> None:
        h = Harness()
        # The WebSocket has already spent 4.98 seconds before the coordinator runs.
        h.coordinator = WAWAdmissionCoordinator(
            authority=h.authority,
            claims=h.ticket.claims,
            context=h.context,
            runtime=h.runtime,
            browser=h.browser,
            audit=h.audit,
            revalidator=h.validator,
            budget=h.budget,
            source="source",
            started_at_ns=h.clock.ns - 4_980_000_000,
            clock_ns=h.clock,
        )
        h.runtime.block = "prepare"
        with pytest.raises(AdmissionFailure) as raised:
            await asyncio.wait_for(h.coordinator.run(), 0.5)
        assert raised.value.code == "ADMISSION_TIMEOUT"
        assert h.browser.closed == 4408
        assert not h.active()
        assert h.runtime.commits == 0

    asyncio.run(scenario())


def test_runtime_state_change_during_admitted_audit_prevents_publication() -> None:
    async def scenario() -> None:
        h = Harness()
        h.audit.block = A.ADMITTED
        task = asyncio.create_task(h.coordinator.run())
        await h.audit.entered.wait()
        h.runtime.incoming.put_nowait(
            encode_wire_frame(
                F.ERROR,
                RA,
                {
                    "protocol_version": 1,
                    "code": "WORKSPACE_EXITED",
                    "retryable": False,
                    "request_id": "wreq_" + "0" * 32,
                },
                6,
            )
        )
        with pytest.raises(AdmissionFailure):
            await task
        assert not h.active() and h.coordinator.queue.read() is None
        assert h.runtime.commits == 1
        assert h.runtime.cleanup_requests[0].close_frame is not None

    asyncio.run(scenario())


def test_precommit_runtime_output_is_rejected_without_admitted_or_input_ack() -> None:
    async def scenario() -> None:
        h = Harness()
        h.audit.block = A.PREPARED
        task = asyncio.create_task(h.coordinator.run())
        await h.audit.entered.wait()
        raw = (
            encode_awce_header(
                crypto_envelope_version=1,
                direction_id=2,
                flags=0,
                crypto_sequence=1,
                stream_cursor=1,
                context_id=bytes.fromhex("e" * 32),
                ciphertext_length=17,
            )
            + b"x" * 17
        )
        h.runtime.incoming.put_nowait(encode_wire_frame(F.OUTPUT, RA, raw, 4))
        with pytest.raises(AdmissionFailure):
            await task
        assert h.runtime.commits == 0
        assert not h.active() and h.coordinator.queue.read() is None

    asyncio.run(scenario())


def test_successful_handoff_preserves_next_browser_and_runtime_message() -> None:
    async def scenario() -> None:
        h = Harness()
        await h.coordinator.run()
        assert h.coordinator.queue.read() is not None
        h.browser.incoming.put_nowait(b"NEXT-BROWSER-FRAME")
        h.runtime.incoming.put_nowait(b"NEXT-RUNTIME-FRAME")
        assert await asyncio.wait_for(h.browser.receive(), 0.1) == b"NEXT-BROWSER-FRAME"
        assert await asyncio.wait_for(h.runtime.receive(), 0.1) == b"NEXT-RUNTIME-FRAME"
        assert h.active()
        assert not h.runtime.aborted

    asyncio.run(scenario())


def test_new_connection_identity_cannot_receive_commit_retry() -> None:
    async def scenario() -> None:
        h = Harness()
        h.runtime.block = F.ADMISSION_COMMIT
        h.runtime.drop_commits = 1
        task = asyncio.create_task(h.coordinator.run())
        await h.runtime.entered.wait()
        h.runtime.connection_id = object()
        h.runtime.resume.set()
        with pytest.raises(AdmissionFailure):
            await task
        assert h.runtime.commits == 1
        assert not h.active()

    asyncio.run(scenario())


def fresh_attempt(
    h: Harness, *, context: AuthenticatedAttachmentContext | None = None
) -> WAWAdmissionCoordinator:
    h.runtime, h.browser, h.audit = Runtime(h), Browser(h), Audit()
    h.browser.incoming.put_nowait(h.frame(F.WS_HELLO, BA, 1))
    h.browser.incoming.put_nowait(h.frame(F.KEY_INIT, BA, 2))
    return WAWAdmissionCoordinator(
        authority=h.authority,
        claims=h.ticket.claims,
        context=h.context if context is None else context,
        runtime=h.runtime,
        browser=h.browser,
        audit=h.audit,
        revalidator=h.validator,
        budget=h.budget,
        source="source",
        started_at_ns=h.clock.ns,
        clock_ns=h.clock,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("attachment_id", "att_" + "9" * 32),
        ("workspace_id", "aws_" + "9" * 32),
        ("project_id", "prj_" + "9" * 32),
        ("agent_type", "claude"),
        ("runtime_host_installation_id", "wri_" + "9" * 32),
        ("runtime_host_installation_revision", "2"),
        ("auth_epoch", "9"),
        ("api_authority_epoch", "9"),
        ("lease_number", "1"),
        ("generation", "2"),
        ("binding_revision", "2"),
        ("binding_digest", "9" * 64),
        ("runtime_epoch", "9"),
    ],
)
def test_well_shaped_hello_mismatch_burns_before_bound_wire_validation(
    field: str, value: str
) -> None:
    async def scenario() -> None:
        h = Harness()
        body = h.payload(F.WS_HELLO)
        assert body[field] != value
        body[field] = value
        h.browser.incoming.get_nowait()
        h.browser.incoming.get_nowait()
        h.browser.incoming.put_nowait(encode_wire_frame(F.WS_HELLO, BA, body, 1))
        with pytest.raises(AdmissionFailure) as denied:
            await h.coordinator.run()
        assert (denied.value.code, h.browser.closed) == ("ATTACHMENT_STALE", 4403)
        assert h.runtime.prepares == 0
        assert h.authority.pending_count == h.authority.record_count == 0
        assert h.coordinator.wire_session.expected_sequence(BA) == 1
        retry = fresh_attempt(h)
        with pytest.raises(AdmissionFailure) as replayed:
            await retry.run()
        assert replayed.value.code == "ATTACHMENT_TICKET_REPLAYED"
        assert h.runtime.prepares == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "field,value",
    [
        ("session_id", "other-session"),
        ("user_id", "other-admin"),
        ("authorization_scope", "other-scope"),
        ("origin", "https://other.invalid"),
        ("runtime_epoch", "9"),
        ("auth_epoch", 9),
    ],
)
def test_known_ticket_with_changed_api_context_burns_atomically(
    field: str, value: str | int
) -> None:
    async def scenario() -> None:
        h = Harness()
        changed = replace(h.context, **{field: value})  # type: ignore[arg-type]
        attempt = fresh_attempt(h, context=changed)
        with pytest.raises(AdmissionFailure) as denied:
            await attempt.run()
        assert (denied.value.code, h.browser.closed) == ("ATTACHMENT_STALE", 4403)
        assert h.authority.pending_count == 0 and h.runtime.prepares == 0
        retry = fresh_attempt(h)
        with pytest.raises(AdmissionFailure) as replayed:
            await retry.run()
        assert replayed.value.code == "ATTACHMENT_TICKET_REPLAYED"
        assert h.runtime.prepares == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "malformed", ["extra_key", "wrong_mode", "number_epoch", "wrong_first_type", "wrong_sequence"]
)
def test_malformed_first_frame_retains_protocol_failure_semantics(malformed: str) -> None:
    async def scenario() -> None:
        import json
        import struct

        h = Harness()
        body = h.payload(F.WS_HELLO)
        if malformed == "extra_key":
            body["unknown"] = "untrusted"
        elif malformed == "wrong_mode":
            body["mode"] = "viewer"
        elif malformed == "number_epoch":
            body["runtime_epoch"] = 2
        payload = json.dumps(body, separators=(",", ":")).encode()
        raw = (
            struct.pack(
                "!4sBBHIQI",
                b"ABWS",
                1,
                F.WS_HELLO,
                0,
                len(payload),
                2 if malformed == "wrong_sequence" else 1,
                0,
            )
            + payload
        )
        if malformed == "wrong_first_type":
            raw = h.frame(F.KEY_INIT, BA, 1)
        h.browser.incoming.get_nowait()
        h.browser.incoming.get_nowait()
        h.browser.incoming.put_nowait(raw)
        with pytest.raises(AdmissionFailure) as denied:
            await h.coordinator.run()
        assert (denied.value.code, h.browser.closed) == ("PROTOCOL_INVALID", 4400)
        assert h.authority.pending_count == 1 and h.runtime.prepares == 0

    asyncio.run(scenario())


def test_handoff_waits_for_single_reader_ports_to_finish_cancellation() -> None:
    async def scenario() -> None:
        h = Harness()
        busy: dict[str, bool] = {"browser": False, "runtime": False}
        originals = {"browser": h.browser.receive, "runtime": h.runtime.receive}

        async def exclusive_receive(name: str) -> bytes:
            assert not busy[name], "concurrent receive at handoff"
            busy[name] = True
            try:
                return await originals[name]()
            finally:
                # A normal cancellation-safe port may asynchronously retire its read.
                await asyncio.sleep(0)
                busy[name] = False

        h.browser.receive = lambda: exclusive_receive("browser")  # type: ignore[method-assign]
        h.runtime.receive = lambda: exclusive_receive("runtime")  # type: ignore[method-assign]
        await h.coordinator.run()
        assert busy == {"browser": False, "runtime": False}
        assert h.active()
        h.browser.incoming.put_nowait(b"NEXT-BROWSER-FRAME")
        h.runtime.incoming.put_nowait(b"NEXT-RUNTIME-FRAME")
        assert await h.browser.receive() == b"NEXT-BROWSER-FRAME"
        assert await h.runtime.receive() == b"NEXT-RUNTIME-FRAME"

    asyncio.run(scenario())


@pytest.mark.parametrize("invalidation", ["revoked", "deadline"])
def test_reader_retirement_remains_quarantined_and_revalidates_before_release(
    invalidation: str,
) -> None:
    async def scenario() -> None:
        h = Harness()
        original = h.browser.receive
        retiring, finish = asyncio.Event(), asyncio.Event()

        async def retiring_receive() -> bytes:
            try:
                return await original()
            except asyncio.CancelledError:
                retiring.set()
                await finish.wait()
                raise

        h.browser.receive = retiring_receive  # type: ignore[method-assign]
        task = asyncio.create_task(h.coordinator.run())
        await asyncio.wait_for(retiring.wait(), 1)
        assert not h.active() and h.coordinator.queue.read() is None
        if invalidation == "revoked":
            h.authority.revoke_session(session_id=h.context.session_id, auth_epoch=3)
        else:
            h.clock.ns += 5_000_000_000
        finish.set()
        with pytest.raises(AdmissionFailure):
            await task
        assert not h.active() and h.coordinator.queue.read() is None

    asyncio.run(scenario())


@pytest.mark.parametrize("runtime_failure", ["raise", "cancel", "timeout"])
def test_runtime_cleanup_failure_still_attempts_required_detached_audit(
    runtime_failure: str,
) -> None:
    async def scenario() -> None:
        h = Harness()
        h.audit.fail = A.ADMITTED
        detached_attempts: list[AdmissionAuditEvent] = []
        original_audit = h.audit.persist

        async def durable_audit(event: AdmissionAuditEvent) -> None:
            if event.action == A.DETACHED:
                detached_attempts.append(event)
                h.audit.events.append(event)
                return
            await original_audit(event)

        async def failed_cleanup(request: RuntimeCleanupRequest) -> RuntimeCleanupProof:
            h.runtime.cleanup_requests.append(request)
            if runtime_failure == "raise":
                raise RuntimeError("PRIVATE-CLEANUP-FAILURE")
            if runtime_failure == "cancel":
                raise asyncio.CancelledError
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        h.audit.persist = durable_audit  # type: ignore[method-assign]
        h.runtime.close_and_cleanup = failed_cleanup  # type: ignore[method-assign]
        with pytest.raises(AdmissionFailure) as failed:
            await asyncio.wait_for(h.coordinator.run(), 1.5)
        assert failed.value.code == "ADMITTED_DELIVERY_FAILED"
        assert len(detached_attempts) == 1
        assert detached_attempts[0].reason_code == "ADMITTED_DELIVERY_FAILED"
        assert [event.action for event in h.audit.events] == [A.PREPARED, A.DETACHED]
        assert h.coordinator.reservation is not None
        assert h.authority.stage(h.coordinator.reservation) == S.FENCED
        assert h.authority.record_count == 1
        assert not h.active() and h.coordinator.queue.read() is None
        assert h.browser.closed == 1013 and h.runtime.aborted
        assert "PRIVATE" not in repr(failed.value)

    asyncio.run(scenario())
