"""Durable single-host Job queue with explicit transitions and safe summaries."""

from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any, cast

from sqlalchemy import select, text

from agentbox_core.clock import Clock
from agentbox_core.configuration import Settings
from agentbox_core.database import Database
from agentbox_core.models import Job, JobEvent
from agentbox_core.security import keyed_digest, new_identifier, redact_text

TERMINAL_JOB_STATES = frozenset({"succeeded", "failed", "cancelled", "needs_attention"})
_IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9._:-]{8,128}")
_JOB_TYPES = frozenset(
    {
        "project.create",
        "project.clone",
        "git.pull",
        "git.push",
        "git.branch.create",
        "git.branch.switch",
        "github.pr.create",
    }
)


class JobService:
    def __init__(self, database: Database, settings: Settings, clock: Clock) -> None:
        self._database = database
        self._clock = clock
        self._lease_seconds = settings.job_lease_seconds
        self._secret = settings.secret_key.get_secret_value()

    def enqueue(
        self,
        *,
        job_type: str,
        requested_by: str,
        target_type: str,
        target_id: str | None,
        project_id: str | None,
        payload: dict[str, Any],
        resource_lock_key: str,
        idempotency_key: str,
        request_id: str | None,
        idempotency_scope: str | None = None,
    ) -> tuple[Job, bool]:
        if job_type not in _JOB_TYPES:
            raise ValueError("job type is not allowlisted")
        if not _IDEMPOTENCY_KEY.fullmatch(idempotency_key):
            raise ValueError("idempotency key is invalid")
        self._validate_payload(payload)
        digest = self._digest(
            requested_by, job_type, idempotency_scope or target_id or "", idempotency_key
        )
        now = self._clock.now()
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            existing = session.scalar(select(Job).where(Job.idempotency_key_digest == digest))
            if existing is not None:
                return existing, False
            job = Job(
                id=new_identifier("job"),
                type=job_type,
                status="queued",
                created_at=now,
                requested_by=requested_by[:80],
                target_type=target_type[:32],
                target_id=target_id[:80] if target_id else None,
                project_id=project_id,
                progress=0,
                phase="queued",
                payload_schema_version=1,
                payload_json=payload,
                idempotency_key_digest=digest,
                resource_lock_key=resource_lock_key[:96],
                attempt=0,
                max_attempts=1,
                request_id=request_id[:72] if request_id else None,
            )
            session.add(job)
            session.flush()
            self._event(session, job, "job.queued", "Job queued")
            return job, True

    def find_idempotent(
        self,
        *,
        job_type: str,
        requested_by: str,
        scope: str,
        idempotency_key: str,
    ) -> Job | None:
        if not _IDEMPOTENCY_KEY.fullmatch(idempotency_key):
            raise ValueError("idempotency key is invalid")
        digest = self._digest(requested_by, job_type, scope, idempotency_key)
        with self._database.transaction() as session:
            return session.scalar(select(Job).where(Job.idempotency_key_digest == digest))

    def list(self, *, limit: int = 100) -> tuple[Job, ...]:
        with self._database.transaction() as session:
            return tuple(session.scalars(select(Job).order_by(Job.created_at.desc()).limit(limit)))

    def get(self, job_id: str) -> Job | None:
        with self._database.transaction() as session:
            return session.get(Job, job_id)

    def events_after(self, job_id: str, sequence: int, *, limit: int = 100) -> tuple[JobEvent, ...]:
        with self._database.transaction() as session:
            return tuple(
                session.scalars(
                    select(JobEvent)
                    .where(JobEvent.job_id == job_id, JobEvent.sequence > sequence)
                    .order_by(JobEvent.sequence.asc())
                    .limit(limit)
                )
            )

    def recover_expired(self) -> int:
        now = self._clock.now()
        recovered = 0
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            jobs = tuple(
                session.scalars(
                    select(Job).where(
                        Job.status == "running",
                        Job.lease_expires_at.is_not(None),
                        Job.lease_expires_at <= now,
                    )
                )
            )
            for job in jobs:
                job.status = "needs_attention"
                job.finished_at = now
                job.phase = "recovery_required"
                job.error_code = "JOB_EXECUTION_INTERRUPTED"
                job.error_summary = "Job execution was interrupted and was not replayed"
                self._event(session, job, "job.needs_attention", job.error_summary)
                recovered += 1
        return recovered

    def claim_next(self, worker_id: str) -> Job | None:
        now = self._clock.now()
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            running_locks = select(Job.resource_lock_key).where(Job.status == "running")
            job = session.scalar(
                select(Job)
                .where(Job.status == "queued", Job.resource_lock_key.not_in(running_locks))
                .order_by(Job.created_at.asc())
                .limit(1)
            )
            if job is None:
                return None
            job.status = "running"
            job.started_at = job.started_at or now
            job.attempt += 1
            job.lease_owner = worker_id[:80]
            job.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
            job.heartbeat_at = now
            job.progress = 10
            job.phase = "running"
            self._event(session, job, "job.started", "Job started")
            session.flush()
            return job

    def progress(self, job_id: str, *, progress: int | None, phase: str, summary: str) -> None:
        with self._database.transaction() as session:
            job = self._running(session, job_id)
            job.progress = progress
            job.phase = phase[:48]
            job.heartbeat_at = self._clock.now()
            job.lease_expires_at = job.heartbeat_at + timedelta(seconds=self._lease_seconds)
            self._event(session, job, "job.progress", summary)

    def succeed(self, job_id: str, summary: str) -> None:
        self._finish(job_id, "succeeded", summary=summary)

    def fail(self, job_id: str, *, code: str, summary: str) -> None:
        self._finish(job_id, "failed", code=code, summary=summary)

    def needs_attention(self, job_id: str, *, code: str, summary: str) -> None:
        self._finish(job_id, "needs_attention", code=code, summary=summary)

    def _finish(
        self,
        job_id: str,
        status: str,
        *,
        summary: str,
        code: str | None = None,
    ) -> None:
        if status not in TERMINAL_JOB_STATES:
            raise ValueError("invalid terminal Job state")
        with self._database.transaction() as session:
            job = self._running(session, job_id)
            safe_summary = redact_text(summary, limit=512)
            job.status = status
            job.finished_at = self._clock.now()
            job.progress = 100 if status == "succeeded" else job.progress
            job.phase = status
            job.lease_owner = None
            job.lease_expires_at = None
            if status == "succeeded":
                job.result_summary = safe_summary
            else:
                job.error_code = (code or "JOB_FAILED")[:80]
                job.error_summary = safe_summary
            self._event(session, job, f"job.{status}", safe_summary)

    def _running(self, session: Any, job_id: str) -> Job:
        job = session.get(Job, job_id)
        if job is None or job.status != "running":
            raise RuntimeError("Job is not running")
        return cast(Job, job)

    def _event(self, session: Any, job: Job, event_type: str, summary: str | None) -> None:
        session.add(
            JobEvent(
                job_id=job.id,
                event_type=event_type[:40],
                status=job.status,
                progress=job.progress,
                phase=job.phase,
                summary=redact_text(summary, limit=512) if summary else None,
                created_at=self._clock.now(),
            )
        )

    @staticmethod
    def _validate_payload(payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        if len(encoded) > 24 * 1024 or len(payload) > 12:
            raise ValueError("job payload is too large")
        forbidden = {"path", "argv", "shell", "environment", "token", "password", "secret"}
        for key, value in payload.items():
            if key.casefold() in forbidden or not isinstance(key, str) or len(key) > 64:
                raise ValueError("job payload key is forbidden")
            if not isinstance(value, (str, int, bool, type(None))) or (
                isinstance(value, str) and len(value.encode()) > 16 * 1024
            ):
                raise ValueError("job payload value is invalid")

    def _digest(self, requested_by: str, job_type: str, scope: str, key: str) -> str:
        return keyed_digest(
            self._secret,
            "job-idempotency",
            f"{requested_by}\0{job_type}\0{scope}\0{key}",
        )
