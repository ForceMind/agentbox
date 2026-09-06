"""Staged authority invariants; public synthetic identity, no host qualification."""

from __future__ import annotations

from dataclasses import replace
from threading import Barrier, Thread
from typing import Any, cast

import pytest
from agentbox_core.waw import workspace_id
from agentbox_core.waw_tickets import (
    AdmissionStage as S,
)
from agentbox_core.waw_tickets import (
    AttachmentAuthority,
    AuthenticatedAttachmentContext,
    IssuedAttachmentTicket,
    StagedAttachment,
    TicketAuthorityError,
)


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def context(user: str = "admin") -> AuthenticatedAttachmentContext:
    return AuthenticatedAttachmentContext(
        "session", user, "admin", "https://agentbox.invalid", "2", 3
    )


def issue(
    authority: AttachmentAuthority, number: int = 1, user: str = "admin"
) -> IssuedAttachmentTicket:
    project = f"prj_{number:032x}"
    return authority.issue(
        workspace_id=workspace_id(project, "codex"),
        project_id=project,
        agent_type="codex",
        attachment_id=f"att_{number:032x}",
        generation=1,
        auth_epoch=3,
        runtime_host_installation_id="wri_" + "a" * 32,
        runtime_host_installation_revision=1,
        binding_revision=1,
        binding_digest="b" * 64,
        context=context(user),
    )


def reserve(authority: AttachmentAuthority, ticket: IssuedAttachmentTicket) -> StagedAttachment:
    return authority.reserve(
        ticket.ticket, ticket.claims, context=context(), connection_id=object(), started_at=100.0
    )


class Publication:
    def __init__(self) -> None:
        self.released = False
        self.discarded = False

    def release(self) -> None:
        self.released = True

    def discard(self) -> None:
        self.discarded = True
        self.released = False

    def take(self) -> bytes | None:
        return b"metadata" if self.released and not self.discarded else None


def advance_all(authority: AttachmentAuthority, handle: StagedAttachment) -> None:
    for stage in tuple(S)[1:8]:
        authority.advance(handle, stage)


def test_only_atomic_release_creates_active_writer() -> None:
    authority = AttachmentAuthority(clock=Clock(), authority_epoch=4)
    ticket = issue(authority)
    handle = reserve(authority, ticket)
    assert authority.record_count == 1
    assert authority.pending_count == authority.active_count == 0
    publication = Publication()
    for stage in tuple(S)[1:8]:
        assert not authority.is_active(ticket.claims, context=context())
        assert authority.read_published(handle, publication) is None
        authority.advance(handle, stage)
    lease = authority.activate_with_publication(handle, publication)
    assert lease.claims == ticket.claims
    assert authority.active_count == 1
    assert authority.record_count == 1
    assert authority.read_published(handle, publication) == b"metadata"


@pytest.mark.parametrize("stage", tuple(S)[2:])
def test_skipping_a_phase_fences_and_never_activates(stage: S) -> None:
    authority = AttachmentAuthority(clock=Clock())
    handle = reserve(authority, issue(authority))
    with pytest.raises(TicketAuthorityError):
        authority.advance(handle, stage)
    assert authority.stage(handle) == S.FENCED
    assert authority.active_count == 0


@pytest.mark.parametrize("change", ["tuple", "session", "user", "scope", "epoch", "origin"])
def test_wrong_tuple_or_api_context_burns_ticket(change: str) -> None:
    authority = AttachmentAuthority(clock=Clock())
    ticket = issue(authority)
    claims, auth = ticket.claims, context()
    if change == "tuple":
        claims = replace(claims, generation=2)
    else:
        fields = {
            "session": "session_id",
            "user": "user_id",
            "scope": "authorization_scope",
            "epoch": "runtime_epoch",
            "origin": "origin",
        }
        auth = replace(auth, **{fields[change]: "9" if change == "epoch" else "wrong"})  # type: ignore[arg-type]
    with pytest.raises(TicketAuthorityError):
        authority.reserve(
            ticket.ticket, claims, context=auth, connection_id=object(), started_at=100
        )
    with pytest.raises(TicketAuthorityError, match="REPLAYED"):
        reserve(authority, ticket)
    assert authority.active_count == authority.record_count == 0


def test_fake_handle_cannot_advance_or_cleanup_original() -> None:
    authority = AttachmentAuthority(clock=Clock())
    handle = reserve(authority, issue(authority))
    forged = replace(handle)
    with pytest.raises(TicketAuthorityError):
        authority.advance(forged, S.RUNTIME_PREPARED)
    with pytest.raises(TicketAuthorityError):
        authority.fence(forged)
    assert authority.stage(handle) == S.RESERVED


@pytest.mark.parametrize("at", [100.0, 104.999, 105.0, 200.0])
def test_revocation_is_permanent_at_every_deadline_position(at: float) -> None:
    clock = Clock()
    authority = AttachmentAuthority(clock=clock)
    handle = reserve(authority, issue(authority))
    advance_all(authority, handle)
    authority.revoke_session(session_id="session", auth_epoch=3)
    clock.now = at
    with pytest.raises(TicketAuthorityError):
        authority.activate_with_publication(handle, Publication())
    assert authority.stage(handle) == S.FENCED
    assert authority.record_count == 1


def test_five_seconds_is_original_deadline_and_ticket_expiry_can_only_shorten_it() -> None:
    clock = Clock()
    authority = AttachmentAuthority(clock=clock, ticket_ttl_seconds=2)
    ticket = issue(authority)
    clock.now = 101.5
    handle = authority.reserve(
        ticket.ticket, ticket.claims, context=context(), connection_id=object(), started_at=101
    )
    assert handle.deadline_monotonic == 102
    clock.now = 102
    with pytest.raises(TicketAuthorityError):
        authority.check_reserved(handle)
    assert authority.stage(handle) == S.FENCED


def test_only_exact_positive_cleanup_plus_durable_failure_releases_fenced_slot() -> None:
    authority = AttachmentAuthority(clock=Clock())
    ticket = issue(authority)
    handle = reserve(authority, ticket)
    authority.fence(handle)
    for connection, state, audit in [
        (object(), "ATTACH_PTY_CLOSED", True),
        (handle.connection_id, "UNKNOWN", True),
        (handle.connection_id, "ATTACH_PTY_CLOSED", False),
    ]:
        with pytest.raises(TicketAuthorityError):
            authority.acknowledge_staged_cleanup(
                handle, connection_id=connection, cleanup_state=state, failure_audited=audit
            )
    with pytest.raises(TicketAuthorityError):
        authority.acknowledge_cleanup(ticket.claims, cleanup_state="ATTACH_PTY_CLOSED")
    with pytest.raises(TicketAuthorityError, match="WRITER_BUSY"):
        issue(authority)
    unrelated = issue(authority, 2)
    assert unrelated.claims.workspace_id != handle.claims.workspace_id
    authority.acknowledge_staged_cleanup(
        handle,
        connection_id=handle.connection_id,
        cleanup_state="ATTACH_PTY_CLOSED",
        failure_audited=True,
    )
    replacement = reserve(authority, issue(authority))
    with pytest.raises(TicketAuthorityError):
        authority.fence(handle)
    assert authority.stage(replacement) == S.RESERVED


@pytest.mark.parametrize("fault", ["raise", "revoke", "deadline"])
def test_publication_faults_do_not_escape_authority_lock(fault: str) -> None:
    clock = Clock()
    authority = AttachmentAuthority(clock=clock)
    handle = reserve(authority, issue(authority))
    advance_all(authority, handle)

    class Failing(Publication):
        def release(self) -> None:
            super().release()
            if fault == "raise":
                raise RuntimeError("private-payload")
            if fault == "revoke":
                authority.revoke_session(session_id="session", auth_epoch=3)
            if fault == "deadline":
                clock.now = 105

    publication = Failing()
    with pytest.raises((RuntimeError, TicketAuthorityError)):
        authority.activate_with_publication(handle, publication)
    assert publication.discarded
    assert authority.read_published(handle, publication) is None
    assert authority.stage(handle) == S.FENCED


def test_parallel_connections_reserve_exactly_one_writer() -> None:
    authority = AttachmentAuthority(clock=Clock())
    tickets = [issue(authority), issue(authority)]
    barrier = Barrier(3)
    successes: list[StagedAttachment] = []
    failures: list[str] = []

    def attempt(ticket: IssuedAttachmentTicket) -> None:
        barrier.wait()
        try:
            successes.append(reserve(authority, ticket))
        except TicketAuthorityError as exc:
            failures.append(str(exc.code))

    threads = [Thread(target=attempt, args=(ticket,)) for ticket in tickets]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()
    assert len(successes) == 1
    assert failures == ["WORKSPACE_WRITER_BUSY"]
    assert authority.active_count == 0


def test_per_admin_and_total_capacity_include_pending_and_fenced_records() -> None:
    authority = AttachmentAuthority(clock=Clock(), max_records=4)
    for number in range(1, 5):
        issue(authority, number)
    with pytest.raises(TicketAuthorityError):
        issue(authority, 5)
    assert authority.record_count == 4
    other = AttachmentAuthority(clock=Clock(), max_writers=1)
    handle = reserve(other, issue(other))
    other.fence(handle)
    with pytest.raises(TicketAuthorityError, match="WRITER_BUSY"):
        reserve(other, issue(other, 2))


def test_shutdown_and_sweep_retain_staged_cleanup_fences() -> None:
    clock = Clock()
    authority = AttachmentAuthority(clock=clock)
    handle = reserve(authority, issue(authority))
    clock.now = 106
    authority.sweep()
    authority.invalidate_all()
    assert authority.stage(handle) == S.FENCED
    assert authority.record_count == 1
    assert authority.active_count == 0


def test_begin_shutdown_fences_staged_writer_until_exact_audit_ack() -> None:
    authority = AttachmentAuthority(clock=Clock())
    ticket = issue(authority)
    handle = reserve(authority, ticket)

    authority.begin_shutdown()

    assert authority.stage(handle) is S.FENCED
    assert authority.record_count == 1
    assert not authority.shutdown_clean
    with pytest.raises(TicketAuthorityError):
        authority.advance(handle, S.RUNTIME_PREPARED)
    with pytest.raises(TicketAuthorityError):
        authority.activate_with_publication(handle, Publication())
    with pytest.raises(TicketAuthorityError):
        reserve(authority, issue(authority, 2))
    with pytest.raises(TicketAuthorityError):
        authority.acknowledge_staged_cleanup(
            handle,
            connection_id=handle.connection_id,
            cleanup_state="ATTACH_PTY_CLOSED",
            failure_audited=False,
        )

    authority.acknowledge_staged_cleanup(
        handle,
        connection_id=handle.connection_id,
        cleanup_state="ATTACH_PTY_CLOSED",
        failure_audited=True,
    )
    assert cast(Any, authority).shutdown_clean
    with pytest.raises(TicketAuthorityError):
        authority.acknowledge_staged_cleanup(
            handle,
            connection_id=handle.connection_id,
            cleanup_state="ATTACH_PTY_CLOSED",
            failure_audited=True,
        )


def test_begin_shutdown_is_idempotent_under_concurrent_callers() -> None:
    authority = AttachmentAuthority(clock=Clock())
    handle = reserve(authority, issue(authority))
    barrier = Barrier(3)
    failures: list[BaseException] = []

    def stop() -> None:
        barrier.wait()
        try:
            authority.begin_shutdown()
        except BaseException as exc:
            failures.append(exc)

    threads = [Thread(target=stop), Thread(target=stop)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert failures == []
    assert authority.stage(handle) is S.FENCED
    assert authority.record_count == 1
    assert not authority.shutdown_clean


def test_shutdown_begin_and_staged_cleanup_ack_have_one_locked_winner() -> None:
    authority = AttachmentAuthority(clock=Clock())
    handle = reserve(authority, issue(authority))
    barrier = Barrier(3)
    results: list[str] = []

    def begin() -> None:
        barrier.wait()
        authority.begin_shutdown()
        results.append("shutdown")

    def acknowledge() -> None:
        barrier.wait()
        try:
            authority.acknowledge_staged_cleanup(
                handle,
                connection_id=handle.connection_id,
                cleanup_state="ATTACH_PTY_CLOSED",
                failure_audited=True,
            )
        except TicketAuthorityError:
            results.append("ack-before-fence")
        else:
            results.append("ack-after-fence")

    threads = [Thread(target=begin), Thread(target=acknowledge)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert "shutdown" in results
    if not authority.shutdown_clean:
        authority.acknowledge_staged_cleanup(
            handle,
            connection_id=handle.connection_id,
            cleanup_state="ATTACH_PTY_CLOSED",
            failure_audited=True,
        )
    assert cast(Any, authority).shutdown_clean


def test_shutdown_acknowledgements_cannot_clear_another_workspace_obligation() -> None:
    authority = AttachmentAuthority(clock=Clock())
    direct_ticket = issue(authority, 1)
    direct = authority.consume(direct_ticket.ticket, direct_ticket.claims, context=context())
    staged_handle = reserve(authority, issue(authority, 2))

    authority.begin_shutdown()
    altered = replace(direct.claims, lease_number=direct.claims.lease_number + 1)
    with pytest.raises(TicketAuthorityError):
        authority.acknowledge_cleanup(altered, cleanup_state="ATTACH_PTY_CLOSED")
    old_handle = replace(staged_handle)
    with pytest.raises(TicketAuthorityError):
        authority.acknowledge_staged_cleanup(
            old_handle,
            connection_id=staged_handle.connection_id,
            cleanup_state="ATTACH_PTY_CLOSED",
            failure_audited=True,
        )
    authority.acknowledge_cleanup(direct.claims, cleanup_state="ATTACH_PTY_CLOSED")
    assert authority.stage(staged_handle) is S.FENCED
    assert not authority.shutdown_clean
    with pytest.raises(TicketAuthorityError):
        authority.acknowledge_cleanup(direct.claims, cleanup_state="ATTACH_PTY_CLOSED")
    authority.acknowledge_staged_cleanup(
        staged_handle,
        connection_id=staged_handle.connection_id,
        cleanup_state="ATTACH_PTY_CLOSED",
        failure_audited=True,
    )
    assert cast(Any, authority).shutdown_clean


def test_sensitive_handles_and_ticket_are_redacted() -> None:
    authority = AttachmentAuthority(clock=Clock())
    ticket = issue(authority)
    handle = reserve(authority, ticket)
    assert ticket.ticket not in repr(ticket)
    assert "session" not in repr(handle)
    assert str(id(handle.connection_id)) not in repr(handle)


def test_synthetic_consume_cannot_steal_headroom_reserved_by_staged_writer() -> None:
    authority = AttachmentAuthority(clock=Clock(), max_writers=1)
    reserve(authority, issue(authority))
    ticket = issue(authority, 2)
    with pytest.raises(TicketAuthorityError, match="WRITER_BUSY"):
        authority.consume(ticket.ticket, ticket.claims, context=context())
    assert authority.active_count == 0


def test_default_global_record_and_writer_ceilings() -> None:
    authority = AttachmentAuthority(clock=Clock())
    for number in range(64):
        issue(authority, number, f"admin-{number // 4}")
    assert authority.record_count == 64
    with pytest.raises(TicketAuthorityError):
        issue(authority, 100, "new-admin")
    writers = AttachmentAuthority(clock=Clock())
    for number in range(32):
        user = f"admin-{number // 4}"
        ticket = issue(writers, number, user)
        writers.reserve(
            ticket.ticket,
            ticket.claims,
            context=context(user),
            connection_id=object(),
            started_at=100,
        )
    next_ticket = issue(writers, 32, "new-admin")
    with pytest.raises(TicketAuthorityError, match="WRITER_BUSY"):
        writers.reserve(
            next_ticket.ticket,
            next_ticket.claims,
            context=context("new-admin"),
            connection_id=object(),
            started_at=100,
        )
    assert writers.record_count == 32
    assert writers.active_count == 0
