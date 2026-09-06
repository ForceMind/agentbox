"""Regression coverage for relay lease-clock sampling across one browser frame."""

from __future__ import annotations

import pytest
from agentbox_api.waw_relay import RelayFailure, WAWCiphertextRelay
from agentbox_core.waw_lease import LeaseCleanupState
from agentbox_protocol.abws import FrameType as F
from agentbox_protocol.waw_wire import Leg, encode_wire_frame
from support.waw_admission import Harness

BA, _AB, AR, _RA = tuple(Leg)


class _IncrementingClock:
    """A clock that makes stale same-frame timestamps deterministic."""

    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        self.value += 0.000001
        return self.value


async def _active(clock: _IncrementingClock) -> tuple[Harness, WAWCiphertextRelay]:
    harness = Harness()
    relay = WAWCiphertextRelay(
        harness.coordinator,
        authority=harness.authority,
        claims=harness.ticket.claims,
        context=harness.context,
        browser=harness.browser,
        runtime=harness.runtime,
        audit=harness.audit,
        revalidator=harness.validator,
        input_budget=harness.input_budget,
        clock=clock,
    )
    await harness.coordinator.run()
    admitted = harness.coordinator.queue.read()
    assert admitted is not None
    await harness.browser.send_key_frame(admitted)
    relay._browser_published_next = 4
    relay.lease.begin(
        attachment_id=harness.ticket.claims.attachment_id,
        generation=harness.ticket.claims.generation,
        lease_number=harness.ticket.claims.lease_number,
        owner=relay.owner,
    )
    relay.lease.commit_admission()
    return harness, relay


def _browser_control(relay: WAWCiphertextRelay, kind: F) -> bytes:
    return encode_wire_frame(
        kind,
        BA,
        {
            "protocol_version": 1,
            "attachment_id": relay.claims.attachment_id,
            "lease_number": str(relay.claims.lease_number),
            **({"sent_at_monotonic_tick": "1"} if kind is F.HEARTBEAT else {}),
        },
        relay.wire.expected_sequence(BA),
    )


@pytest.mark.anyio
async def test_relay_samples_lease_clock_after_each_same_frame_permit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _IncrementingClock()
    harness, relay = await _active(clock)
    queued_states: list[LeaseCleanupState] = []
    original_queue_runtime = relay._queue_runtime

    def queue_runtime(raw: bytes, **kwargs: object) -> None:
        queued_states.append(relay.lease.snapshot.state)  # type: ignore[union-attr]
        original_queue_runtime(raw, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(relay, "_queue_runtime", queue_runtime)

    last_activity = relay.last_activity
    relay.browser_frame(harness.browser.delivery(_browser_control(relay, F.HEARTBEAT)))
    heartbeat_snapshot = relay.lease.snapshot
    assert heartbeat_snapshot is not None
    assert heartbeat_snapshot.state is LeaseCleanupState.ACTIVE
    assert relay.last_activity == last_activity

    relay.browser_frame(harness.browser.delivery(_browser_control(relay, F.DETACH)))
    detach_snapshot = relay.lease.snapshot
    assert detach_snapshot is not None
    assert detach_snapshot.state is LeaseCleanupState.DETACHING
    assert queued_states == [LeaseCleanupState.DETACHING]

    await relay.close(RelayFailure("ATTACHMENT_STALE", 4403))
    assert harness.authority.record_count == 0
