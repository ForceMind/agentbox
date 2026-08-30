from __future__ import annotations

import pytest
from agentbox_core.waw_lease import (
    LeaseCleanupError,
    LeaseCleanupFence,
    LeaseCleanupState,
)


class Clock:
    value = 100.0

    def __call__(self) -> float:
        return self.value


def _fence(clock: Clock) -> LeaseCleanupFence:
    return LeaseCleanupFence(clock=clock, stale_after_seconds=30, grace_seconds=60)


def test_cleanup_requires_admission_commit_and_positive_ack_to_release_slot() -> None:
    clock = Clock()
    fence = _fence(clock)
    assert fence.begin(attachment_id="att_1", generation=1, lease_number=2).state == (
        LeaseCleanupState.ADMITTING
    )
    with pytest.raises(LeaseCleanupError) as invalid:
        fence.request_detach()
    assert invalid.value.code == "ATTACHMENT_STATE_INVALID"
    assert fence.commit_admission().state is LeaseCleanupState.ACTIVE
    assert fence.request_detach().state is LeaseCleanupState.DETACHING
    assert fence.snapshot is not None and fence.snapshot.writer_slot_reserved
    with pytest.raises(LeaseCleanupError) as proof:
        fence.acknowledge_cleanup(cleanup_state="PTY_CLOSED")
    assert proof.value.code == "DETACH_ACK_INVALID"
    assert fence.acknowledge_cleanup(cleanup_state="ATTACH_PTY_CLOSED").state == (
        LeaseCleanupState.DETACHED
    )
    assert fence.snapshot is not None and not fence.snapshot.writer_slot_reserved


def test_stale_then_grace_expiry_preserves_slot_until_cleanup_ack() -> None:
    clock = Clock()
    fence = _fence(clock)
    fence.begin(attachment_id="att_1", generation=1, lease_number=2)
    fence.commit_admission()
    clock.value = 130
    assert fence.tick().state is LeaseCleanupState.STALE
    clock.value = 189
    assert fence.tick().state is LeaseCleanupState.STALE
    clock.value = 190
    expired = fence.tick()
    assert expired.state is LeaseCleanupState.EXPIRED
    assert expired.writer_slot_reserved
    assert fence.request_detach().state is LeaseCleanupState.DETACHING


def test_heartbeat_resets_stale_and_grace_deadlines_only_while_active() -> None:
    clock = Clock()
    fence = _fence(clock)
    fence.begin(attachment_id="att_1", generation=1, lease_number=2)
    fence.commit_admission()
    clock.value = 129
    renewed = fence.heartbeat()
    assert renewed.last_heartbeat == 129
    assert renewed.stale_at == 159
    clock.value = 159
    assert fence.tick().state is LeaseCleanupState.STALE
    with pytest.raises(LeaseCleanupError) as stale:
        fence.heartbeat()
    assert stale.value.code == "ATTACHMENT_STALE"


def test_detach_timeout_requires_reconciliation_but_does_not_release_writer_slot() -> None:
    clock = Clock()
    fence = _fence(clock)
    fence.begin(attachment_id="att_1", generation=1, lease_number=2)
    fence.commit_admission()
    fence.request_detach()
    clock.value = 101
    closed = fence.tick()
    assert closed.state is LeaseCleanupState.RECONCILIATION_REQUIRED
    assert closed.writer_slot_reserved
    assert fence.request_detach().state is LeaseCleanupState.RECONCILIATION_REQUIRED


def test_new_attachment_is_blocked_until_positive_detach_ack() -> None:
    clock = Clock()
    fence = _fence(clock)
    fence.begin(attachment_id="att_1", generation=1, lease_number=2)
    fence.commit_admission()
    fence.request_detach()
    with pytest.raises(LeaseCleanupError) as busy:
        fence.begin(attachment_id="att_2", generation=1, lease_number=3)
    assert busy.value.code == "ATTACHMENT_BUSY"
    fence.acknowledge_cleanup(cleanup_state="ATTACH_PTY_CLOSED")
    assert fence.begin(attachment_id="att_2", generation=2, lease_number=3).state == (
        LeaseCleanupState.ADMITTING
    )
