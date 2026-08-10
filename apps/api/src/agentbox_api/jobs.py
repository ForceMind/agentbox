"""Authenticated durable Job read model and bounded SSE replay."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Literal, cast

from agentbox_core.errors import JobNotFound
from agentbox_core.models import Job
from agentbox_core.services import ControlPlaneServices
from agentbox_protocol import JobData, JobListData, JobListResponse, JobResponse
from fastapi import APIRouter, Cookie, Header, Request, Response
from fastapi.responses import StreamingResponse

from agentbox_api.auth import SESSION_COOKIE, _validate_origin, authenticate_request

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


def _services(request: Request) -> ControlPlaneServices:
    return cast(ControlPlaneServices, request.app.state.services)


def job_data(job: Job) -> JobData:
    status = cast(
        Literal[
            "queued",
            "running",
            "succeeded",
            "failed",
            "cancelled",
            "needs_attention",
        ],
        job.status,
    )
    return JobData(
        id=job.id,
        type=job.type,
        status=status,
        target_type=job.target_type,
        target_id=job.target_id,
        project_id=job.project_id,
        progress=job.progress,
        phase=job.phase,
        result_summary=job.result_summary,
        error_code=job.error_code,
        error_summary=job.error_summary,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.get("", response_model=JobListResponse)
async def list_jobs(
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> JobListResponse:
    authenticate_request(request, agentbox_session)
    response.headers["Cache-Control"] = "no-store"
    return JobListResponse(
        request_id=str(request.state.request_id),
        data=JobListData(jobs=[job_data(job) for job in _services(request).jobs.list()]),
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> JobResponse:
    authenticate_request(request, agentbox_session)
    job = _services(request).jobs.get(job_id)
    if job is None:
        raise JobNotFound()
    response.headers["Cache-Control"] = "no-store"
    return JobResponse(request_id=str(request.state.request_id), data=job_data(job))


@router.get("/{job_id}/events")
async def job_events(
    job_id: str,
    request: Request,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    last_event_id: str | None = Header(default=None),
) -> StreamingResponse:
    _validate_origin(request)
    authenticate_request(request, agentbox_session)
    if _services(request).jobs.get(job_id) is None:
        raise JobNotFound()
    try:
        cursor = max(0, int(last_event_id or "0"))
    except ValueError:
        cursor = 0

    async def stream() -> AsyncIterator[str]:
        nonlocal cursor
        for _iteration in range(120):
            if await request.is_disconnected():
                return
            events = _services(request).jobs.events_after(job_id, cursor)
            for event in events:
                cursor = event.sequence
                payload = json.dumps(
                    {
                        "job_id": event.job_id,
                        "status": event.status,
                        "progress": event.progress,
                        "phase": event.phase,
                        "summary": event.summary,
                        "created_at": event.created_at.isoformat(),
                    },
                    separators=(",", ":"),
                )
                yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {payload}\n\n"
            job = _services(request).jobs.get(job_id)
            if job is None or job.status in {"succeeded", "failed", "cancelled", "needs_attention"}:
                return
            yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
