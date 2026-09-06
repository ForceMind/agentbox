"""RC7 composed admission failures over the real R6 coordinator.

Each fixture port is synthetic, but the coordinator, ticket authority, queue,
wire framing and cleanup path are the production implementation.  The named
test controls live under ``tests.support`` only.
"""

from __future__ import annotations

import asyncio

import pytest
from agentbox_api.waw_admission_coordinator import AdmissionAuditAction as A
from agentbox_api.waw_admission_coordinator import AdmissionFailure, RuntimeCleanupProof
from agentbox_core.waw_tickets import AdmissionStage, TicketAuthorityError
from agentbox_protocol.abws import FrameType as F
from agentbox_protocol.waw_wire import decode_wire_frame
from support.waw_admission import AB, AR, RA, Harness
from support.waw_failure_injection import AdmissionCheckpoint, CheckpointPlan


def _wire_checkpoint(
    h: Harness,
    plan: CheckpointPlan,
    checkpoint: AdmissionCheckpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pause immediately after one real coordinator boundary has completed."""

    if checkpoint is AdmissionCheckpoint.TICKET_RESERVED:
        original_prepare = h.runtime.prepare

        async def prepare(request):  # type: ignore[no-untyped-def]
            # The coordinator reserved/burned the ticket before it enters its
            # first Runtime await; this lets revocation race that exact state.
            await plan.arrive(checkpoint)
            return await original_prepare(request)

        monkeypatch.setattr(h.runtime, "prepare", prepare)
        return

    if checkpoint is AdmissionCheckpoint.RUNTIME_PREPARED:
        original_prepare = h.runtime.prepare

        async def prepare(request):  # type: ignore[no-untyped-def]
            prepared = await original_prepare(request)
            await plan.arrive(checkpoint)
            return prepared

        monkeypatch.setattr(h.runtime, "prepare", prepare)
        return

    if checkpoint is AdmissionCheckpoint.KEY_ATTEST_PUBLISHED:
        original_browser_send = h.browser.send_key_frame

        async def send_key_frame(raw: bytes) -> None:
            await original_browser_send(raw)
            if decode_wire_frame(raw, AB).frame_type is F.KEY_ATTEST:
                await plan.arrive(checkpoint)

        monkeypatch.setattr(h.browser, "send_key_frame", send_key_frame)
        return

    if checkpoint in {
        AdmissionCheckpoint.PREPARED_AUDIT_PERSISTED,
        AdmissionCheckpoint.ADMITTED_AUDIT_PERSISTED,
    }:
        original_audit_persist = h.audit.persist
        action = (
            A.PREPARED if checkpoint is AdmissionCheckpoint.PREPARED_AUDIT_PERSISTED else A.ADMITTED
        )

        async def persist(event):  # type: ignore[no-untyped-def]
            await original_audit_persist(event)
            if event.action is action:
                await plan.arrive(checkpoint)

        monkeypatch.setattr(h.audit, "persist", persist)
        return

    if checkpoint is AdmissionCheckpoint.COMMIT_SENT:
        original_runtime_send = h.runtime.send

        async def send(raw: bytes) -> None:
            await original_runtime_send(raw)
            if decode_wire_frame(raw, AR).frame_type is F.ADMISSION_COMMIT:
                await plan.arrive(checkpoint)

        monkeypatch.setattr(h.runtime, "send", send)
        return

    if checkpoint in {
        AdmissionCheckpoint.READY_RECEIVED,
        AdmissionCheckpoint.COMMIT_ACKED,
    }:
        original_receive = h.runtime.receive
        expected = (
            F.STREAM_READY_ACK
            if checkpoint is AdmissionCheckpoint.READY_RECEIVED
            else F.ADMISSION_COMMIT_ACK
        )

        async def receive() -> bytes:
            raw = await original_receive()
            if decode_wire_frame(raw, RA).frame_type is expected:
                await plan.arrive(checkpoint)
            return raw

        monkeypatch.setattr(h.runtime, "receive", receive)
        return

    raise AssertionError(f"unsupported admission checkpoint: {checkpoint}")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "checkpoint",
    (
        AdmissionCheckpoint.TICKET_RESERVED,
        AdmissionCheckpoint.RUNTIME_PREPARED,
        AdmissionCheckpoint.KEY_ATTEST_PUBLISHED,
        AdmissionCheckpoint.PREPARED_AUDIT_PERSISTED,
        AdmissionCheckpoint.READY_RECEIVED,
        AdmissionCheckpoint.COMMIT_SENT,
        AdmissionCheckpoint.COMMIT_ACKED,
        AdmissionCheckpoint.ADMITTED_AUDIT_PERSISTED,
    ),
)
async def test_rc7_revoke_at_composed_admission_boundaries_never_activates_writer(
    checkpoint: AdmissionCheckpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = Harness()
    plan = CheckpointPlan.single(checkpoint)
    _wire_checkpoint(h, plan, checkpoint, monkeypatch)
    proofs: list[RuntimeCleanupProof] = []
    original_cleanup = h.runtime.close_and_cleanup

    async def close_and_cleanup(request):  # type: ignore[no-untyped-def]
        proof = await original_cleanup(request)
        proofs.append(proof)
        return proof

    monkeypatch.setattr(h.runtime, "close_and_cleanup", close_and_cleanup)
    running = asyncio.create_task(h.coordinator.run())

    await asyncio.wait_for(plan.observe(checkpoint), 1)
    assert not h.active()
    assert h.authority.active_count == 0
    assert h.coordinator.queue.read() is None
    h.validator.valid = False
    assert plan.release(checkpoint)

    with pytest.raises(AdmissionFailure):
        await asyncio.wait_for(running, 1)
    plan.assert_complete()
    assert not h.active() and h.authority.active_count == h.authority.record_count == 0
    assert h.coordinator.queue.read() is None
    assert h.runtime.aborted and len(h.runtime.cleanup_requests) == 1
    assert h.runtime.cleanup_requests[0].claims == h.ticket.claims
    assert proofs == [
        RuntimeCleanupProof(
            h.ticket.claims,
            h.context.runtime_epoch,
            h.runtime.connection_id,
            "detached",
            "ATTACH_PTY_CLOSED",
        )
    ]
    assert h.audit.events[-1].action is A.DETACHED
    assert all(decode_wire_frame(raw, AB).frame_type is not F.ADMITTED for raw in h.browser.sent)
    with pytest.raises(TicketAuthorityError):
        h.authority.consume(h.ticket.ticket, h.ticket.claims, context=h.context)

    replacement = h.authority.issue(
        workspace_id=h.ticket.claims.workspace_id,
        project_id=h.ticket.claims.project_id,
        agent_type=h.ticket.claims.agent_type,
        attachment_id="att_" + "f" * 32,
        generation=h.ticket.claims.generation + 1,
        auth_epoch=h.context.auth_epoch,
        runtime_host_installation_id=h.ticket.claims.runtime_host_installation_id,
        runtime_host_installation_revision=h.ticket.claims.runtime_host_installation_revision,
        binding_revision=h.ticket.claims.binding_revision,
        binding_digest=h.ticket.claims.binding_digest,
        context=h.context,
    )
    replacement_lease = h.authority.consume(
        replacement.ticket, replacement.claims, context=h.context
    )
    assert replacement_lease.claims == replacement.claims
    h.authority.detach(replacement.claims, context=h.context)
    assert h.authority.record_count == 0


@pytest.mark.anyio
async def test_rc7_commit_response_loss_retries_once_with_exact_bytes_on_same_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = Harness()
    plan = CheckpointPlan.sequence(
        AdmissionCheckpoint.COMMIT_SENT,
        AdmissionCheckpoint.COMMIT_SENT,
    )
    commits: list[bytes] = []
    original_send = h.runtime.send
    h.runtime.drop_commits = 1
    connection = h.runtime.connection_id

    async def send(raw: bytes) -> None:
        if decode_wire_frame(raw, AR).frame_type is F.ADMISSION_COMMIT:
            commits.append(bytes(raw))
            await plan.arrive(AdmissionCheckpoint.COMMIT_SENT)
        await original_send(raw)

    monkeypatch.setattr(h.runtime, "send", send)
    running = asyncio.create_task(h.coordinator.run())

    await asyncio.wait_for(plan.observe(AdmissionCheckpoint.COMMIT_SENT), 1)
    assert not h.active() and h.coordinator.queue.read() is None and h.runtime.incoming.empty()
    assert plan.release(AdmissionCheckpoint.COMMIT_SENT)
    await asyncio.wait_for(plan.observe(AdmissionCheckpoint.COMMIT_SENT, occurrence=2), 1)
    assert commits == [commits[0], commits[0]]
    assert h.runtime.incoming.empty()
    assert plan.release(AdmissionCheckpoint.COMMIT_SENT, occurrence=2)
    lease = await asyncio.wait_for(running, 1)

    plan.assert_complete()
    assert lease.claims == h.ticket.claims
    assert h.active() and h.runtime.commits == 2
    assert h.runtime.connection_id is connection and h.runtime.incoming.empty()


@pytest.mark.anyio
async def test_rc7_missing_positive_cleanup_keeps_composed_obligation_fenced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = Harness()
    plan = CheckpointPlan.single(AdmissionCheckpoint.ADMITTED_AUDIT_PERSISTED)
    _wire_checkpoint(h, plan, AdmissionCheckpoint.ADMITTED_AUDIT_PERSISTED, monkeypatch)
    h.runtime.cleanup_positive = False
    running = asyncio.create_task(h.coordinator.run())

    await asyncio.wait_for(plan.observe(AdmissionCheckpoint.ADMITTED_AUDIT_PERSISTED), 1)
    h.validator.valid = False
    assert plan.release(AdmissionCheckpoint.ADMITTED_AUDIT_PERSISTED)
    with pytest.raises(AdmissionFailure):
        await asyncio.wait_for(running, 1)
    plan.assert_complete()

    handle = h.coordinator.reservation
    assert handle is not None
    assert h.authority.stage(handle) is AdmissionStage.FENCED
    assert h.authority.record_count == 1 and not h.active()
    assert h.runtime.cleanup_requests and h.audit.events[-1].action is A.DETACHED
