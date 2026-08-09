"""Authenticated, read-only control-plane and safe Runtime diagnostics."""

from __future__ import annotations

from agentbox_protocol import (
    CodexDoctorSummary,
    DoctorChecks,
    DoctorData,
    DoctorPolicy,
    DoctorResponse,
)
from agentbox_runtime import RuntimeOperationError
from fastapi import APIRouter, Cookie, Request, Response

from agentbox_api.auth import SESSION_COOKIE, authenticate_request

router = APIRouter(prefix="/api/v1", tags=["diagnostics"])


@router.get("/doctor", response_model=DoctorResponse)
async def doctor(
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> DoctorResponse:
    """Return safe control-plane readiness, policy, and Codex summary data."""
    authenticate_request(request, agentbox_session)
    services = request.app.state.services
    settings = request.app.state.settings

    database_reachable = services.database.check_connection()
    migrations_current = services.database.migrations_current()
    admin_initialized, _username = services.admin.status()
    control_plane_ready = database_reachable and migrations_current and admin_initialized
    try:
        codex_status = await request.app.state.codex_runtime.status(str(request.state.request_id))
        codex_summary = CodexDoctorSummary(
            installed=codex_status.installed,
            version=codex_status.version,
            installation_type=codex_status.installation_type.value,
            remote_control=codex_status.capabilities.remote_control.value,
            remote_state=codex_status.remote_state.value,
            findings=[finding.code for finding in codex_status.diagnostics[:16]],
        )
    except RuntimeOperationError as exc:
        codex_summary = CodexDoctorSummary(
            installed=None,
            version=None,
            installation_type="unknown",
            remote_control="unknown",
            remote_state="unknown",
            findings=[exc.code],
        )
    response.headers["Cache-Control"] = "no-store"
    return DoctorResponse(
        request_id=str(request.state.request_id),
        data=DoctorData(
            status="ready" if control_plane_ready else "not_ready",
            checks=DoctorChecks(
                configuration_valid=True,
                database_reachable=database_reachable,
                migrations_current=migrations_current,
                admin_initialized=admin_initialized,
                control_plane_ready=control_plane_ready,
            ),
            policy=DoctorPolicy(
                environment=settings.env.value,
                bind_host=settings.bind_host,
                bind_port=settings.bind_port,
                session_ttl_seconds=settings.session_ttl,
                session_idle_ttl_seconds=settings.session_idle_ttl,
                login_rate_limit=settings.login_rate_limit,
                login_rate_window_seconds=settings.login_rate_window,
                login_lock_duration_seconds=settings.login_lock_duration,
            ),
            codex=codex_summary,
        ),
    )
