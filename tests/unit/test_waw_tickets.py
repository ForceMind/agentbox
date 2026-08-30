from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier
from typing import Any

import pytest
from agentbox_core.waw import AgentType, WAWDomainError, workspace_id
from agentbox_core.waw_tickets import (
    AttachmentAuthority,
    AttachmentTuple,
    IssuedAttachmentTicket,
    TicketAuthorityError,
    TicketErrorCode,
)

PROJECT_ID = "prj_" + "0" * 32
WORKSPACE_ID = workspace_id(PROJECT_ID, AgentType.CLAUDE)
HOST_ID = "wri_" + "1" * 32
BINDING_DIGEST = "a" * 64


class FakeMonotonic:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _authority(clock: FakeMonotonic, **kwargs: Any) -> AttachmentAuthority:
    return AttachmentAuthority(
        clock=clock,
        authority_epoch=11,
        lease_seed=20,
        **kwargs,
    )


def _issue(
    authority: AttachmentAuthority, *, attachment_id: str = "att_" + "2" * 32
) -> IssuedAttachmentTicket:
    return authority.issue(
        workspace_id=WORKSPACE_ID,
        project_id=PROJECT_ID,
        agent_type=AgentType.CLAUDE,
        attachment_id=attachment_id,
        generation=1,
        auth_epoch=4,
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision=3,
        binding_revision=2,
        binding_digest=BINDING_DIGEST,
        expires_at=datetime(2030, 1, 1),
    )


def _tuple(ticket: IssuedAttachmentTicket) -> AttachmentTuple:
    return ticket.claims


def test_issue_stores_only_bounded_pending_record_and_server_lease_number() -> None:
    clock = FakeMonotonic()
    authority = _authority(clock)
    issued = _issue(authority)
    assert issued.ticket.startswith("wat_")
    assert issued.claims.lease_number == 20
    assert issued.claims.api_authority_epoch == 11
    assert authority.pending_count == 1
    # The plaintext bearer exists only in the transient return value; authority
    # internals contain only its digest and metadata.
    assert all(issued.ticket not in repr(value) for value in authority.__dict__.values())


def test_consume_is_single_use_and_binds_every_tuple_field() -> None:
    clock = FakeMonotonic()
    authority = _authority(clock)
    issued = _issue(authority)
    active = authority.consume(issued.ticket, _tuple(issued))
    assert authority.active_count == 1
    assert active.claims == issued.claims
    with pytest.raises(TicketAuthorityError) as replay:
        authority.consume(issued.ticket, _tuple(issued))
    assert replay.value.code is TicketErrorCode.REPLAYED

    second = _issue(authority, attachment_id="att_" + "3" * 32)
    altered = AttachmentTuple(
        **{
            **second.claims.__dict__,
            "generation": 2,
        }
    )
    with pytest.raises(TicketAuthorityError) as stale:
        authority.consume(second.ticket, altered)
    assert stale.value.code is TicketErrorCode.STALE
    assert authority.pending_count == 0


def test_expiry_uses_monotonic_clock_and_burns_ticket() -> None:
    clock = FakeMonotonic()
    authority = _authority(clock, ticket_ttl_seconds=3)
    issued = _issue(authority)
    clock.advance(3)
    with pytest.raises(TicketAuthorityError) as expired:
        authority.consume(issued.ticket, _tuple(issued))
    assert expired.value.code is TicketErrorCode.EXPIRED
    with pytest.raises(TicketAuthorityError) as replay:
        authority.consume(issued.ticket, _tuple(issued))
    assert replay.value.code is TicketErrorCode.REPLAYED


def test_single_writer_admission_rejects_second_live_writer_but_allows_after_detach() -> None:
    clock = FakeMonotonic()
    authority = _authority(clock)
    first = _issue(authority)
    authority.consume(first.ticket, _tuple(first))
    second = _issue(authority, attachment_id="att_" + "3" * 32)
    with pytest.raises(TicketAuthorityError) as busy:
        authority.consume(second.ticket, _tuple(second))
    assert busy.value.code is TicketErrorCode.WRITER_BUSY
    assert authority.pending_count == 0
    with pytest.raises(TicketAuthorityError) as mismatch:
        authority.detach(second.claims)
    assert mismatch.value.code is TicketErrorCode.LEASE_MISMATCH
    authority.detach(first.claims)
    third = _issue(authority, attachment_id="att_" + "4" * 32)
    assert authority.consume(third.ticket, _tuple(third)).claims.attachment_id == "att_" + "4" * 32


def test_concurrent_consumers_linearize_one_writer() -> None:
    clock = FakeMonotonic()
    authority = _authority(clock)
    first = _issue(authority)
    second = _issue(authority, attachment_id="att_" + "3" * 32)
    gate = Barrier(2)

    def consume(ticket: IssuedAttachmentTicket) -> str:
        gate.wait()
        try:
            return authority.consume(ticket.ticket, ticket.claims).attachment_id
        except TicketAuthorityError as exc:
            return exc.code.value

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(consume, (first, second)))

    assert sum(result.startswith("att_") for result in results) == 1
    assert TicketErrorCode.WRITER_BUSY.value in results
    assert authority.active_count == 1


def test_heartbeat_renews_idle_expiry_without_changing_lease_number() -> None:
    clock = FakeMonotonic()
    authority = _authority(clock, lease_ttl_seconds=5, absolute_lease_seconds=10)
    issued = _issue(authority)
    active = authority.consume(issued.ticket, _tuple(issued))
    clock.advance(4)
    renewed = authority.heartbeat(issued.claims)
    assert renewed.claims.lease_number == active.claims.lease_number
    assert renewed.last_heartbeat_monotonic == 104
    clock.advance(5)
    authority.sweep()
    assert authority.active_count == 0


def test_expired_lease_is_removed_and_stale_detach_cannot_release_replacement() -> None:
    clock = FakeMonotonic()
    authority = _authority(clock, lease_ttl_seconds=2, absolute_lease_seconds=5)
    issued = _issue(authority)
    authority.consume(issued.ticket, _tuple(issued))
    clock.advance(2)
    with pytest.raises(TicketAuthorityError) as expired:
        authority.detach(issued.claims)
    assert expired.value.code is TicketErrorCode.LEASE_EXPIRED
    replacement = _issue(authority, attachment_id="att_" + "3" * 32)
    authority.consume(replacement.ticket, _tuple(replacement))
    with pytest.raises(TicketAuthorityError) as stale:
        authority.detach(issued.claims)
    assert stale.value.code is TicketErrorCode.LEASE_MISMATCH


def test_capacity_counts_pending_and_active_records_and_sweeps_expired_entries() -> None:
    clock = FakeMonotonic()
    authority = _authority(clock, max_records=2, ticket_ttl_seconds=2)
    first = _issue(authority)
    second = _issue(authority, attachment_id="att_" + "3" * 32)
    assert authority.record_count == 2
    with pytest.raises(TicketAuthorityError) as full:
        _issue(authority, attachment_id="att_" + "4" * 32)
    assert full.value.code is TicketErrorCode.CAPACITY
    clock.advance(2)
    authority.sweep()
    assert authority.record_count == 0
    _issue(authority, attachment_id="att_" + "4" * 32)
    assert first.claims.attachment_id != second.claims.attachment_id


def test_authority_restart_invalidation_rejects_all_old_bearers_and_leases() -> None:
    clock = FakeMonotonic()
    authority = _authority(clock)
    issued = _issue(authority)
    authority.consume(issued.ticket, _tuple(issued))
    authority.invalidate_all()
    assert authority.record_count == 0
    with pytest.raises(TicketAuthorityError) as replay:
        authority.consume(issued.ticket, _tuple(issued))
    assert replay.value.code is TicketErrorCode.REPLAYED
    with pytest.raises(TicketAuthorityError) as mismatch:
        authority.heartbeat(issued.claims)
    assert mismatch.value.code is TicketErrorCode.LEASE_MISMATCH


def test_invalid_ticket_and_invalid_tuple_fail_closed() -> None:
    clock = FakeMonotonic()
    authority = _authority(clock)
    with pytest.raises(TicketAuthorityError) as invalid:
        authority.consume(
            "wat_" + "0" * 31 + "!",
            AttachmentTuple(
                workspace_id=WORKSPACE_ID,
                project_id=PROJECT_ID,
                agent_type=AgentType.CLAUDE,
                attachment_id="att_" + "2" * 32,
                lease_number=1,
                generation=1,
                auth_epoch=1,
                api_authority_epoch=11,
                runtime_host_installation_id=HOST_ID,
                runtime_host_installation_revision=1,
                binding_revision=1,
                binding_digest=BINDING_DIGEST,
            ),
        )
    assert invalid.value.code is TicketErrorCode.INVALID
    with pytest.raises((TicketAuthorityError, WAWDomainError)):
        _issue(authority, attachment_id="not-an-attachment")
