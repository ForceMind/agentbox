"""RC7 cross-surface canary acceptance for admission and active failure.

Browser storage, DOM and browser-task retention are covered by the Web rc7
suite.  This module owns only API/Runtime typed-path, durable control-plane and
diagnostic surfaces.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from pathlib import Path
from typing import Any

import pytest
from agentbox_api.waw_admission_coordinator import AdmissionAuditAction as A
from agentbox_api.waw_relay import DurableAdmissionAudit, RelayFailure, WAWCiphertextRelay
from agentbox_core.configuration import Settings
from agentbox_core.models import AuditEvent, Job, JobEvent
from agentbox_core.services import ControlPlaneServices
from agentbox_core.waw_tickets import TicketAuthorityError
from agentbox_installer.diagnostics import export_diagnostics
from agentbox_protocol.abws import FrameType as F
from agentbox_protocol.abws import encode_frame
from agentbox_protocol.awce import encode_awce_header
from agentbox_protocol.waw_wire import Leg, decode_wire_frame
from sqlalchemy import select
from sqlalchemy.engine import make_url
from support.waw_admission import Harness
from support.waw_failure_injection import CheckpointPlan, StreamCheckpoint

BA, _AB, AR, _RA = tuple(Leg)


class _CanaryHarness(Harness):
    """Put a per-run public-key canary through the real typed handshake."""

    def __init__(self, key_canary: str) -> None:
        self._key_canary = key_canary
        super().__init__()

    def payload(self, kind: F) -> dict[str, Any]:
        body = super().payload(kind)
        if kind is F.KEY_INIT:
            body["browser_ephemeral_public_key"] = self._key_canary
            body["noise_message_1"] = self._key_canary
        return body


def _input_with_canary(relay: WAWCiphertextRelay, payload_canary: bytes) -> bytes:
    ciphertext = payload_canary + secrets.token_bytes(16)
    envelope = (
        encode_awce_header(
            crypto_envelope_version=1,
            direction_id=1,
            flags=0,
            crypto_sequence=1,
            stream_cursor=0,
            context_id=bytes.fromhex("e" * 32),
            ciphertext_length=len(ciphertext),
        )
        + ciphertext
    )
    return encode_frame(F.INPUT, envelope, relay.wire.expected_sequence(BA))


def _serialized_records(
    audits: tuple[AuditEvent, ...],
    jobs: tuple[Job, ...],
    job_events: tuple[JobEvent, ...],
) -> bytes:
    payload = {
        "audit": [
            {
                "id": event.id,
                "actor_type": event.actor_type,
                "actor_id": event.actor_id,
                "action": event.action,
                "target_type": event.target_type,
                "target_id": event.target_id,
                "result": event.result,
                "request_id": event.request_id,
                "created_at": event.created_at.isoformat(),
                "metadata": event.metadata_json,
            }
            for event in audits
        ],
        "jobs": [
            {
                "id": job.id,
                "type": job.type,
                "status": job.status,
                "created_at": job.created_at.isoformat(),
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                "requested_by": job.requested_by,
                "target_type": job.target_type,
                "target_id": job.target_id,
                "project_id": job.project_id,
                "progress": job.progress,
                "phase": job.phase,
                "result_summary": job.result_summary,
                "error_code": job.error_code,
                "error_summary": job.error_summary,
                "payload_schema_version": job.payload_schema_version,
                "payload": job.payload_json,
                "idempotency_key_digest": job.idempotency_key_digest,
                "resource_lock_key": job.resource_lock_key,
                "attempt": job.attempt,
                "max_attempts": job.max_attempts,
                "lease_owner": job.lease_owner,
                "lease_expires_at": (
                    job.lease_expires_at.isoformat() if job.lease_expires_at else None
                ),
                "heartbeat_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
                "request_id": job.request_id,
            }
            for job in jobs
        ],
        "job_events": [
            {
                "sequence": event.sequence,
                "job_id": event.job_id,
                "event_type": event.event_type,
                "status": event.status,
                "progress": event.progress,
                "phase": event.phase,
                "summary": event.summary,
                "created_at": event.created_at.isoformat(),
            }
            for event in job_events
        ],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _reject_canaries(surface: str, content: bytes, canaries: tuple[bytes, ...]) -> None:
    if any(canary in content for canary in canaries):
        pytest.fail(f"{surface} retained a WAW canary", pytrace=False)


@pytest.mark.anyio
async def test_rc7_dynamic_canaries_leave_no_durable_or_diagnostic_trace_after_active_failure(
    services: ControlPlaneServices,
    settings: Settings,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload_canary = ("rc7-payload-" + secrets.token_urlsafe(24)).encode()
    key_canary = secrets.token_urlsafe(32)
    harness = _CanaryHarness(key_canary)
    ticket_canary = harness.ticket.ticket.encode()
    canaries = (payload_canary, key_canary.encode(), ticket_canary)
    durable_audit = DurableAdmissionAudit(services, "usr_rc7_canary_acceptance")
    persisted_actions: list[str] = []
    original_persist = durable_audit.persist

    async def persist(event: Any) -> None:
        await original_persist(event)
        persisted_actions.append(event.action)

    monkeypatch.setattr(durable_audit, "persist", persist)
    harness.coordinator._audit = durable_audit

    input_attempts = 0
    plan = CheckpointPlan.single(StreamCheckpoint.INPUT_PUBLISHED)
    original_send = harness.runtime.send

    async def fail_active_input(raw: bytes) -> None:
        nonlocal input_attempts
        if decode_wire_frame(raw, AR).frame_type is F.INPUT:
            input_attempts += 1
            await plan.arrive(StreamCheckpoint.INPUT_PUBLISHED)
            raise RuntimeError("rc7 controlled active Runtime write failure")
        await original_send(raw)

    monkeypatch.setattr(harness.runtime, "send", fail_active_input)

    with caplog.at_level(logging.DEBUG):
        lease = await asyncio.wait_for(harness.coordinator.run(), timeout=2)
        if lease.claims != harness.ticket.claims:
            pytest.fail("admission returned the wrong authority lease", pytrace=False)
        admitted = harness.coordinator.queue.read()
        if admitted is None:
            pytest.fail("admission did not publish its bounded handoff", pytrace=False)
        await asyncio.wait_for(harness.browser.send_key_frame(admitted), timeout=1)

        relay = WAWCiphertextRelay(
            harness.coordinator,
            authority=harness.authority,
            claims=harness.ticket.claims,
            context=harness.context,
            browser=harness.browser,
            runtime=harness.runtime,
            audit=durable_audit,
            revalidator=harness.validator,
            input_budget=harness.input_budget,
            clock=lambda: harness.clock.ns / 1_000_000_000,
        )
        relay._browser_published_next = 4
        relay.lease.begin(
            attachment_id=harness.ticket.claims.attachment_id,
            generation=harness.ticket.claims.generation,
            lease_number=harness.ticket.claims.lease_number,
            owner=relay.owner,
        )
        relay.lease.commit_admission()
        relay.browser_frame(harness.browser.delivery(_input_with_canary(relay, payload_canary)))
        writing = asyncio.create_task(relay._writer(relay._runtime_queue, browser=False))

        await asyncio.wait_for(plan.observe(StreamCheckpoint.INPUT_PUBLISHED), timeout=1)
        if not plan.release(StreamCheckpoint.INPUT_PUBLISHED):
            pytest.fail("active failure checkpoint was already released", pytrace=False)
        with pytest.raises(RuntimeError, match="controlled active Runtime write failure"):
            await asyncio.wait_for(writing, timeout=1)
        plan.assert_complete()
        await asyncio.wait_for(
            relay.close(relay._failure or RelayFailure("ATTACHMENT_STALE", 4403)),
            timeout=1,
        )

        if input_attempts != 1:
            pytest.fail("uncertain INPUT was retried", pytrace=False)
        if len(harness.runtime.cleanup_requests) != 1:
            pytest.fail("active failure did not perform exactly one Runtime cleanup", pytrace=False)
        cleanup = harness.runtime.cleanup_requests[0]
        if cleanup.claims != harness.ticket.claims:
            pytest.fail("Runtime cleanup targeted the wrong authority tuple", pytrace=False)
        if harness.authority.record_count or harness.authority.active_count:
            pytest.fail("positive cleanup did not release the writer authority", pytrace=False)
        if not harness.input_budget.closed or not relay.wire.closed:
            pytest.fail("active failure left a stream owner open", pytrace=False)
        with pytest.raises(TicketAuthorityError):
            harness.authority.consume(
                harness.ticket.ticket,
                harness.ticket.claims,
                context=harness.context,
            )

        services.projects.reconcile_existing(("rc7-canary-surface",))
        project = services.projects.resolve("rc7-canary-surface")
        job, created = services.jobs.enqueue(
            job_type="git.pull",
            requested_by="usr_rc7_canary_acceptance",
            target_type="project",
            target_id=project.id,
            project_id=project.id,
            payload={"project_key": "rc7-canary-surface"},
            resource_lock_key=f"project:{project.id}",
            idempotency_key="rc7-canary-surface-job",
            request_id="req_rc7_canary_surface",
        )
        if not created or services.jobs.claim_next("rc7-canary-worker") is None:
            pytest.fail("Jobs scan fixture did not reach running state", pytrace=False)
        services.jobs.fail(
            job.id,
            code="RUNTIME_UNAVAILABLE",
            summary="Controlled WAW acceptance fixture failure",
        )

        with services.database.transaction() as session:
            audits = tuple(
                session.scalars(
                    select(AuditEvent)
                    .where(AuditEvent.action.like("workspace.attachment_%"))
                    .order_by(AuditEvent.created_at, AuditEvent.id)
                ).all()
            )
        actions = tuple(event.action for event in audits)
        expected_actions = (A.PREPARED.value, A.ADMITTED.value, A.DETACHED.value)
        if tuple(persisted_actions) != expected_actions:
            pytest.fail("durable WAW Audit sequence is incomplete", pytrace=False)
        if len(actions) != len(expected_actions) or set(actions) != set(expected_actions):
            pytest.fail("durable WAW Audit records are incomplete", pytrace=False)
        jobs = services.jobs.list()
        job_events = services.jobs.events_after(job.id, 0)
        records = _serialized_records(audits, jobs, job_events)

        diagnostic = tmp_path / "rc7-canary-diagnostics.json"
        export_diagnostics(
            diagnostic,
            {
                "schema_version": 1,
                "control_plane": {"database": "reachable", "migrations": "current"},
                "waw_acceptance": {
                    "audit_event_count": len(audits),
                    "job_event_count": len(job_events),
                    "failure_code": "RUNTIME_UNAVAILABLE",
                    "cleanup_state": "ATTACH_PTY_CLOSED",
                },
                "sharing_warning": "Review this diagnostic report before sharing.",
            },
        )

    _reject_canaries("captured logs", caplog.text.encode(), canaries)
    _reject_canaries("serialized Audit and Jobs records", records, canaries)
    _reject_canaries("diagnostic export", diagnostic.read_bytes(), canaries)

    database = Path(make_url(settings.database_url).database or "")
    sqlite_surfaces = (database, Path(f"{database}-wal"), Path(f"{database}-shm"))
    if any(not path.exists() for path in sqlite_surfaces):
        pytest.fail("required SQLite/WAL/SHM scan surface is unavailable", pytrace=False)
    for path in sqlite_surfaces:
        _reject_canaries(f"SQLite surface {path.name}", path.read_bytes(), canaries)
    services.database.engine.dispose()
    for path in sqlite_surfaces:
        if path.exists():
            _reject_canaries(f"closed SQLite surface {path.name}", path.read_bytes(), canaries)
