from __future__ import annotations

import math
from dataclasses import replace
from threading import Barrier, Thread

import pytest
from agentbox_core.waw import workspace_id
from agentbox_core.waw_lease import (
    LeaseCleanupError,
    LeaseCleanupFence,
    LeaseCleanupState,
    LeaseOwner,
)
from agentbox_core.waw_recovery import RecoveryIdentity


class Clock:
    value = 100.0

    def __call__(self) -> float:
        return self.value


ATT1 = "att_" + "1" * 32
ATT2 = "att_" + "2" * 32


def _fence(clock: Clock) -> LeaseCleanupFence:
    return LeaseCleanupFence(clock=clock, stale_after_seconds=30, grace_seconds=60)


def _owner(attachment_id: str = ATT1, generation: int = 1, lease_number: int = 2) -> LeaseOwner:
    return LeaseOwner(
        RecoveryIdentity(
            workspace_id=workspace_id("prj_" + "2" * 32, "claude"),
            project_id="prj_" + "2" * 32,
            agent_type="claude",
            generation=generation,
            binding_revision=1,
            binding_digest="a" * 64,
            runtime_host_installation_id="wri_" + "3" * 32,
            runtime_host_installation_revision=1,
            runtime_epoch=1,
            api_authority_epoch=1,
            attachment_id=attachment_id,
            lease_number=lease_number,
            session_id="ses_1",
            auth_epoch=1,
        )
    )


def test_cleanup_requires_admission_commit_and_positive_ack_to_release_slot() -> None:
    clock = Clock()
    fence = _fence(clock)
    assert fence.begin(attachment_id=ATT1, generation=1, lease_number=2, owner=_owner()).state == (
        LeaseCleanupState.ADMITTING
    )
    with pytest.raises(LeaseCleanupError) as invalid:
        fence.request_detach()
    assert invalid.value.code == "ATTACHMENT_STATE_INVALID"
    assert fence.commit_admission().state is LeaseCleanupState.ACTIVE
    assert fence.request_detach().state is LeaseCleanupState.DETACHING
    assert fence.snapshot is not None and fence.snapshot.writer_slot_reserved
    with pytest.raises(LeaseCleanupError) as proof:
        fence.acknowledge_cleanup(cleanup_state="PTY_CLOSED", owner=_owner())
    assert proof.value.code == "DETACH_ACK_INVALID"
    assert fence.acknowledge_cleanup(cleanup_state="ATTACH_PTY_CLOSED", owner=_owner()).state == (
        LeaseCleanupState.DETACHED
    )
    assert fence.snapshot is not None and not fence.snapshot.writer_slot_reserved


def test_stale_then_grace_expiry_preserves_slot_until_cleanup_ack() -> None:
    clock = Clock()
    fence = _fence(clock)
    fence.begin(attachment_id=ATT1, generation=1, lease_number=2, owner=_owner())
    fence.commit_admission()
    clock.value = 130
    assert fence.tick().state is LeaseCleanupState.STALE
    clock.value = 159
    assert fence.tick().state is LeaseCleanupState.STALE
    clock.value = 160
    expired = fence.tick()
    assert expired.state is LeaseCleanupState.EXPIRED
    assert expired.writer_slot_reserved
    assert fence.request_detach().state is LeaseCleanupState.DETACHING


def test_heartbeat_resets_stale_and_grace_deadlines_only_while_active() -> None:
    clock = Clock()
    fence = _fence(clock)
    fence.begin(attachment_id=ATT1, generation=1, lease_number=2, owner=_owner())
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
    fence.begin(attachment_id=ATT1, generation=1, lease_number=2, owner=_owner())
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
    fence.begin(attachment_id=ATT1, generation=1, lease_number=2, owner=_owner())
    fence.commit_admission()
    fence.request_detach()
    with pytest.raises(LeaseCleanupError) as busy:
        fence.begin(attachment_id=ATT2, generation=1, lease_number=3, owner=_owner(ATT2, 1, 3))
    assert busy.value.code == "ATTACHMENT_BUSY"
    fence.acknowledge_cleanup(cleanup_state="ATTACH_PTY_CLOSED", owner=_owner())
    assert fence.begin(
        attachment_id=ATT2, generation=2, lease_number=3, owner=_owner(ATT2, 2, 3)
    ).state == (LeaseCleanupState.ADMITTING)


def test_concurrent_begin_serializes_writer_slot_reservation() -> None:
    clock = Clock()
    fence = _fence(clock)
    barrier = Barrier(2)
    outcomes: list[str] = []

    def attempt(attachment_id: str) -> None:
        barrier.wait()
        try:
            fence.begin(
                attachment_id=attachment_id,
                generation=1,
                lease_number=1,
                owner=_owner(attachment_id, 1, 1),
            )
        except LeaseCleanupError as error:
            outcomes.append(error.code)
        else:
            outcomes.append("ADMITTED")

    first = Thread(target=attempt, args=(ATT1,))
    second = Thread(target=attempt, args=(ATT2,))
    first.start()
    second.start()
    first.join()
    second.join()

    assert sorted(outcomes) == ["ADMITTED", "ATTACHMENT_BUSY"]
    assert fence.snapshot is not None
    assert fence.snapshot.state is LeaseCleanupState.ADMITTING


def test_cleanup_ack_requires_exact_owner_when_bound() -> None:
    clock = Clock()
    fence = _fence(clock)
    owner = _owner()
    fence.begin(attachment_id=ATT1, generation=1, lease_number=2, owner=owner)
    fence.commit_admission()
    fence.request_detach()
    with pytest.raises(LeaseCleanupError) as stale:
        fence.acknowledge_cleanup(cleanup_state="ATTACH_PTY_CLOSED", owner=_owner(ATT2, 1, 2))
    assert stale.value.code == "DETACH_ACK_STALE"
    assert fence.snapshot is not None and fence.snapshot.writer_slot_reserved
    assert (
        fence.acknowledge_cleanup(cleanup_state="ATTACH_PTY_CLOSED", owner=owner).state
        is LeaseCleanupState.DETACHED
    )


@pytest.mark.parametrize(
    "stale_identity",
    [
        replace(_owner().identity, runtime_epoch=2),
        replace(_owner().identity, api_authority_epoch=2),
        replace(_owner().identity, binding_digest="b" * 64),
        replace(_owner().identity, session_id="ses_2"),
        replace(_owner().identity, auth_epoch=2),
    ],
)
def test_cleanup_ack_rejects_identity_namespace_changes(stale_identity: RecoveryIdentity) -> None:
    clock = Clock()
    fence = _fence(clock)
    owner = _owner()
    fence.begin(attachment_id=ATT1, generation=1, lease_number=2, owner=owner)
    fence.commit_admission()
    fence.request_detach()
    stale = LeaseOwner(stale_identity)
    with pytest.raises(LeaseCleanupError) as error:
        fence.acknowledge_cleanup(cleanup_state="ATTACH_PTY_CLOSED", owner=stale)
    assert error.value.code == "DETACH_ACK_STALE"


def test_begin_rejects_owner_identity_mismatch() -> None:
    fence = _fence(Clock())
    with pytest.raises(LeaseCleanupError) as error:
        fence.begin(
            attachment_id=ATT1,
            generation=1,
            lease_number=1,
            owner=_owner(ATT2, 2, 9),
        )
    assert error.value.code == "LEASE_OWNER_MISMATCH"


def test_lease_owner_rejects_noncanonical_and_non_u64_values() -> None:
    with pytest.raises(ValueError):
        _owner("att_bad", 1, 1)
    with pytest.raises(ValueError):
        _owner(ATT1, 2**64, 1)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, True, "1"])
def test_lease_rejects_invalid_clock(value: object) -> None:
    clock = Clock()
    fence = _fence(clock)
    fence.begin(attachment_id=ATT1, generation=1, lease_number=2, owner=_owner())
    with pytest.raises(LeaseCleanupError, match="finite"):
        fence.tick(now=value)  # type: ignore[arg-type]


def test_lease_requires_grace_window_at_least_stale_window() -> None:
    with pytest.raises(ValueError):
        LeaseCleanupFence(clock=Clock(), stale_after_seconds=30, grace_seconds=29)
