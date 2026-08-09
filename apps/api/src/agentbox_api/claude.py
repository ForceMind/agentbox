"""Authenticated project-scoped Claude Remote session routes."""

from __future__ import annotations

from typing import Literal, cast

from agentbox_core.errors import RuntimeGatewayError
from agentbox_core.services import AuthenticatedSession, ControlPlaneServices
from agentbox_protocol import (
    ClaudeCapabilityView,
    ClaudeDiagnosticView,
    ClaudeSessionActionData,
    ClaudeSessionActionResponse,
    ClaudeSessionData,
    ClaudeSessionListData,
    ClaudeSessionListResponse,
    ClaudeSessionOutputData,
    ClaudeSessionOutputResponse,
    ClaudeSessionResponse,
    ClaudeStatusData,
    ClaudeStatusResponse,
)
from agentbox_runtime import (
    ClaudeRuntimeClient,
    ClaudeSession,
    ClaudeStatus,
    RuntimeOperationError,
    validate_project_id,
)
from fastapi import APIRouter, Body, Cookie, Header, Request, Response

from agentbox_api.auth import SESSION_COOKIE, _validate_origin, authenticate_request

router = APIRouter(prefix="/api/v1/claude", tags=["claude"])


def _services(request: Request) -> ControlPlaneServices:
    return cast(ControlPlaneServices, request.app.state.services)


def _runtime(request: Request) -> ClaudeRuntimeClient:
    return cast(ClaudeRuntimeClient, request.app.state.claude_runtime)


def _request_id(request: Request) -> str:
    return str(request.state.request_id)


def _translate_error(exc: RuntimeOperationError) -> RuntimeGatewayError:
    return RuntimeGatewayError(
        code=exc.code,
        category=exc.category,
        message=exc.message,
        retryable=exc.retryable,
        retry_after=exc.retry_after,
    )


def _session_data(session: ClaudeSession) -> ClaudeSessionData:
    return ClaudeSessionData(
        project_id=session.project_id,
        display_name=session.display_name,
        state=session.state.value,
        managed=session.managed,
        session_name=session.session_name,
        attach_command=session.attach_command,
        workspace_state=session.workspace_state.value,
        tmux_running=session.tmux_running,
        remote_readiness=cast(Literal["ready", "unknown"], session.remote_readiness),
    )


def _status_data(status: ClaudeStatus) -> ClaudeStatusData:
    return ClaudeStatusData(
        installed=status.installed,
        version=status.version,
        authentication=status.authentication.value,
        capabilities=ClaudeCapabilityView(
            remote_control=status.capabilities.remote_control.value,
            remote_start=status.capabilities.remote_start.value,
            version=status.capabilities.version.value,
        ),
        tmux_installed=status.tmux_installed,
        tmux_version=status.tmux_version,
        managed_sessions=status.managed_sessions,
        unmanaged_sessions=status.unmanaged_sessions,
        workspace_interaction_warnings=status.workspace_interaction_warnings,
        diagnostics=[
            ClaudeDiagnosticView(
                code=finding.code,
                severity=cast(
                    Literal["critical", "high", "medium", "low", "warning", "info"],
                    finding.severity,
                ),
                summary=finding.summary,
                remediation=finding.remediation,
            )
            for finding in status.diagnostics
        ],
    )


def _audit(
    request: Request,
    authenticated: AuthenticatedSession,
    *,
    action: str,
    project_id: str,
    result: str,
    state: str | None = None,
    error_code: str | None = None,
) -> None:
    metadata: dict[str, object] = {"runtime": "claude", "project_id": project_id}
    if state is not None:
        metadata["state"] = state
    if error_code is not None:
        metadata["error_code"] = error_code
    services = _services(request)
    with services.database.transaction() as database_session:
        services.audit.record(
            database_session,
            actor_type="admin",
            actor_id=authenticated.user_id,
            action=action,
            result=result,
            request_id=_request_id(request),
            target_type="claude_project_session",
            target_id=project_id,
            metadata=metadata,
        )


@router.get("", response_model=ClaudeStatusResponse)
async def claude_status(
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> ClaudeStatusResponse:
    authenticate_request(request, agentbox_session)
    try:
        status = await _runtime(request).status(_request_id(request))
    except RuntimeOperationError as exc:
        raise _translate_error(exc) from exc
    response.headers["Cache-Control"] = "no-store"
    return ClaudeStatusResponse(request_id=_request_id(request), data=_status_data(status))


@router.get("/sessions", response_model=ClaudeSessionListResponse)
async def list_sessions(
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> ClaudeSessionListResponse:
    authenticate_request(request, agentbox_session)
    try:
        sessions = await _runtime(request).list_sessions(_request_id(request))
    except RuntimeOperationError as exc:
        raise _translate_error(exc) from exc
    response.headers["Cache-Control"] = "no-store"
    return ClaudeSessionListResponse(
        request_id=_request_id(request),
        data=ClaudeSessionListData(sessions=[_session_data(session) for session in sessions]),
    )


@router.get("/sessions/{project_id}", response_model=ClaudeSessionResponse)
async def session_status(
    project_id: str,
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> ClaudeSessionResponse:
    authenticate_request(request, agentbox_session)
    try:
        validate_project_id(project_id)
        session = await _runtime(request).session(_request_id(request), project_id)
    except RuntimeOperationError as exc:
        raise _translate_error(exc) from exc
    response.headers["Cache-Control"] = "no-store"
    return ClaudeSessionResponse(request_id=_request_id(request), data=_session_data(session))


async def _mutation(
    project_id: str,
    request: Request,
    response: Response,
    raw_session: str | None,
    csrf_token: str | None,
    *,
    operation: Literal["start", "stop"],
) -> ClaudeSessionActionResponse:
    try:
        validate_project_id(project_id)
    except RuntimeOperationError as exc:
        raise _translate_error(exc) from exc
    _validate_origin(request)
    authenticated = authenticate_request(request, raw_session)
    _services(request).sessions.validate_csrf(authenticated, csrf_token)
    prefix = f"claude_session_{operation}"
    _audit(
        request,
        authenticated,
        action=f"{prefix}_requested",
        project_id=project_id,
        result="requested",
    )
    try:
        runtime = _runtime(request)
        result = (
            await runtime.start_session(_request_id(request), project_id)
            if operation == "start"
            else await runtime.stop_session(_request_id(request), project_id)
        )
    except RuntimeOperationError as exc:
        _audit(
            request,
            authenticated,
            action=f"{prefix}_failed",
            project_id=project_id,
            result="failed",
            error_code=exc.code,
        )
        raise _translate_error(exc) from exc
    _audit(
        request,
        authenticated,
        action=f"{prefix}_succeeded",
        project_id=project_id,
        result="succeeded",
        state=result.session.state.value,
    )
    response.headers["Cache-Control"] = "no-store"
    return ClaudeSessionActionResponse(
        request_id=_request_id(request),
        data=ClaudeSessionActionData(
            outcome=cast(
                Literal["started", "stopped", "already_running", "already_stopped"],
                result.outcome,
            ),
            session=_session_data(result.session),
        ),
    )


@router.post("/sessions/{project_id}/start", response_model=ClaudeSessionActionResponse)
async def start_session(
    project_id: str,
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
    _body: None = Body(default=None),
) -> ClaudeSessionActionResponse:
    return await _mutation(
        project_id,
        request,
        response,
        agentbox_session,
        x_csrf_token,
        operation="start",
    )


@router.post("/sessions/{project_id}/stop", response_model=ClaudeSessionActionResponse)
async def stop_session(
    project_id: str,
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
    _body: None = Body(default=None),
) -> ClaudeSessionActionResponse:
    return await _mutation(
        project_id,
        request,
        response,
        agentbox_session,
        x_csrf_token,
        operation="stop",
    )


@router.get("/sessions/{project_id}/output", response_model=ClaudeSessionOutputResponse)
async def recent_output(
    project_id: str,
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> ClaudeSessionOutputResponse:
    authenticated = authenticate_request(request, agentbox_session)
    try:
        validate_project_id(project_id)
        output = await _runtime(request).recent_output(_request_id(request), project_id)
    except RuntimeOperationError as exc:
        raise _translate_error(exc) from exc
    # Deliberately audit only access metadata, never pane output or prompt text.
    _audit(
        request,
        authenticated,
        action="claude_output_viewed",
        project_id=project_id,
        result="succeeded",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return ClaudeSessionOutputResponse(
        request_id=_request_id(request),
        data=ClaudeSessionOutputData(
            project_id=output.project_id,
            session_name=output.session_name,
            output=output.output,
            truncated=output.truncated,
            sensitive=True,
        ),
    )
