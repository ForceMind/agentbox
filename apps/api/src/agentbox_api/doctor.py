"""Authenticated, read-only control-plane and safe Runtime diagnostics."""

from __future__ import annotations

import asyncio
from typing import Literal

from agentbox_protocol import (
    ClaudeDoctorSummary,
    CodexDoctorSummary,
    DoctorChecks,
    DoctorData,
    DoctorPolicy,
    DoctorResponse,
    ProjectDoctorSummary,
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
    """Return safe control-plane readiness and bounded Runtime summaries."""
    authenticate_request(request, agentbox_session)
    services = request.app.state.services
    settings = request.app.state.settings

    database_reachable = services.database.check_connection()
    migrations_current = services.database.migrations_current()
    admin_initialized, _username = services.admin.status()
    control_plane_ready = database_reachable and migrations_current and admin_initialized
    request_id = str(request.state.request_id)

    async def probe_codex() -> CodexDoctorSummary:
        try:
            value = await request.app.state.codex_runtime.status(request_id)
            return CodexDoctorSummary(
                installed=value.installed,
                version=value.version,
                installation_type=value.installation_type.value,
                remote_control=value.capabilities.remote_control.value,
                remote_state=value.remote_state.value,
                findings=[finding.code for finding in value.diagnostics[:16]],
            )
        except RuntimeOperationError as exc:
            return CodexDoctorSummary(
                installed=None,
                version=None,
                installation_type="unknown",
                remote_control="unknown",
                remote_state="unknown",
                findings=[exc.code],
            )

    async def probe_claude() -> ClaudeDoctorSummary:
        try:
            value = await request.app.state.claude_runtime.status(request_id)
            return ClaudeDoctorSummary(
                installed=value.installed,
                version=value.version,
                authentication=value.authentication.value,
                remote_control=value.capabilities.remote_control.value,
                tmux_installed=value.tmux_installed,
                tmux_version=value.tmux_version,
                managed_sessions=value.managed_sessions,
                unmanaged_sessions=value.unmanaged_sessions,
                workspace_interaction_warnings=value.workspace_interaction_warnings,
                findings=[finding.code for finding in value.diagnostics[:16]],
            )
        except RuntimeOperationError as exc:
            return ClaudeDoctorSummary(
                installed=None,
                version=None,
                authentication="unknown",
                remote_control="unknown",
                tmux_installed=None,
                tmux_version=None,
                managed_sessions=0,
                unmanaged_sessions=0,
                workspace_interaction_warnings=0,
                findings=[exc.code],
            )

    async def probe_git() -> tuple[bool | None, str | None, list[str]]:
        try:
            value = await request.app.state.project_runtime.git_global_status(request_id)
            return value.installed, value.version, []
        except RuntimeOperationError as exc:
            return None, None, [exc.code]

    async def probe_github() -> (
        tuple[bool | None, Literal["authenticated", "unauthenticated", "unknown"], list[str]]
    ):
        try:
            value = await request.app.state.project_runtime.github_status(request_id)
            return value.installed, value.authentication.value, []
        except RuntimeOperationError as exc:
            return None, "unknown", [exc.code]

    async def probe_workspaces() -> tuple[set[str] | None, list[str]]:
        try:
            values = await request.app.state.project_runtime.list_workspaces(request_id)
            return {value.project_key for value in values}, []
        except RuntimeOperationError as exc:
            return None, [exc.code]

    codex_summary, claude_summary, git_probe, github_probe, workspace_probe = await asyncio.gather(
        probe_codex(), probe_claude(), probe_git(), probe_github(), probe_workspaces()
    )
    projects = services.projects.list()
    workspace_findings = list(workspace_probe[1])
    ready_keys = {project.relative_path for project in projects if project.state == "ready"}
    if workspace_probe[0] is not None and not ready_keys.issubset(workspace_probe[0]):
        workspace_findings.append("PROJECT_WORKSPACE_UNAVAILABLE")
    project_status = ProjectDoctorSummary(
        project_root=str(settings.project_root),
        project_count=len(projects),
        git_installed=git_probe[0],
        git_version=git_probe[1],
        github_cli_installed=github_probe[0],
        github_authentication=github_probe[1],
        findings=[*workspace_findings, *git_probe[2], *github_probe[2]][:16],
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
            claude=claude_summary,
            projects=project_status,
        ),
    )
