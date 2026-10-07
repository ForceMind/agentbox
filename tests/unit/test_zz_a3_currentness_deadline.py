"""Real UDS regression for acceptance after the original currentness deadline."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from agentbox_core.a3_native_io import Guard
from agentbox_core.services import ControlPlaneServices
from agentbox_protocol.a3_admission import A3CurrentAdmission
from agentbox_protocol.a3_content import ContentError
from agentbox_protocol.a3_transport import NativeFrame, NativeKind, facts_to_wire
from test_a3_native_transport import Client, native_owner


@pytest.mark.anyio
async def test_currentness_final_peer_proof_cannot_accept_after_original_deadline(
    tmp_path: Path,
    initialized_services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, facts, authority, _ = await native_owner(tmp_path, initialized_services)
    client = Client(owner, facts)
    bundle = client.bundle
    channel = bundle._channels["currentness"]
    real_receive = channel.receive
    real_peer_check = bundle._check_peer
    real_current = bundle.current
    deadline: int | None = None
    reply_before_deadline = False
    delayed = False
    final_peer_after_deadline = False
    returned_late_facts = False
    internal_timeout = False
    metadata_received = False
    closed_before_test_cleanup = False

    def receive(
        expected: frozenset[NativeKind], *, deadline_ns: int, guard: Guard | None = None
    ) -> NativeFrame:
        nonlocal deadline, reply_before_deadline
        frame = real_receive(expected, deadline_ns=deadline_ns, guard=guard)
        if not delayed and expected == frozenset({NativeKind.CURRENT_REPLY}):
            deadline = deadline_ns
            reply_before_deadline = time.monotonic_ns() < deadline_ns
        return frame

    def check_peer() -> None:
        nonlocal delayed, final_peer_after_deadline
        if deadline is not None and not delayed:
            delayed = True
            # The channel already captured its original peer callback. Only this
            # instance's explicit final proof is delayed, once, with the real clock.
            delay = max(0, (deadline - time.monotonic_ns()) / 1_000_000_000) + 0.01
            assert delay <= 0.26
            time.sleep(delay)
            real_peer_check()
            final_peer_after_deadline = time.monotonic_ns() >= deadline
            return
        real_peer_check()

    def current() -> A3CurrentAdmission:
        nonlocal returned_late_facts, internal_timeout
        already_delayed = delayed
        try:
            result = real_current()
        except ContentError as error:
            if delayed and not already_delayed:
                internal_timeout = error.args == ("PATCH_TIMEOUT",)
            raise
        if delayed and not already_delayed:
            assert deadline is not None
            returned_late_facts = time.monotonic_ns() >= deadline
        return result

    monkeypatch.setattr(channel, "receive", receive)
    monkeypatch.setattr(bundle, "_check_peer", check_peer)
    monkeypatch.setattr(bundle, "current", current)
    try:
        await client.start()
        try:
            await client.rpc(
                NativeKind.OBSERVE, {"facts": facts_to_wire(facts)}, NativeKind.METADATA
            )
            metadata_received = True
        except ContentError as error:
            # _resolve may swallow the inner timeout; closure then surfaces EOF.
            assert error.args in (("PATCH_REVOKED",), ("PATCH_TIMEOUT",))
        if not metadata_received:
            await asyncio.wait_for(bundle.wait_closed(), 2)
            closed_before_test_cleanup = (
                bundle.closed
                and not bundle._current_lock.locked()
                and owner.active_bundles == 0
                and owner.selectors._active == 0
                and all(item.shutdown_complete for item in bundle._channels.values())
            )
    finally:
        await client.close()
        owner.close()
        await owner.wait_closed()
        authority.close()

    assert reply_before_deadline and delayed and final_peer_after_deadline
    assert not returned_late_facts, (
        "late-currentness-acceptance: "
        f"reply_before_deadline={reply_before_deadline}, "
        f"final_peer_after_deadline={final_peer_after_deadline}, "
        f"returned_late_facts={returned_late_facts}, "
        f"metadata_received={metadata_received}"
    )
    assert internal_timeout and not metadata_received
    assert closed_before_test_cleanup
    assert owner.active_bundles == 0 and owner.selectors._active == 0
    assert not bundle._current_lock.locked()
    assert all(item.shutdown_complete for item in bundle._channels.values())
    assert all(item.shutdown_complete for item in client.channels.values())
