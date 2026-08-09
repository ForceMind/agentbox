"""Authenticated Codex Runtime read and mutation routes."""

from __future__ import annotations

from typing import Literal, cast

from agentbox_core.errors import RecentAuthenticationRequired, RuntimeGatewayError
from agentbox_core.services import AuthenticatedSession, ControlPlaneServices
from agentbox_protocol import (
    CodexCapabilityView,
    CodexDiagnosticView,
    CodexPairData,
    CodexPairResponse,
    CodexRemoteActionData,
    CodexRemoteActionResponse,
    CodexStatusData,
    CodexStatusResponse,
)
from agentbox_runtime import CodexRuntimeClient, CodexStatus, RuntimeOperationError
from fastapi import APIRouter, Cookie, Header, Request, Response

from agentbox_api.auth import (
    SESSION_COOKIE,
    _validate_origin,
    authenticate_request,
)

router = APIRouter(prefix="/api/v1/codex", tags=["codex"])


def _services(request: Request) -> ControlPlaneServices:
    return cast(ControlPlaneServices, request.app.state.services)


def _runtime(request: Request) -> CodexRuntimeClient:
    return cast(CodexRuntimeClient, request.app.state.codex_runtime)


def _request_id(request: Request) -> str:
    return str(request.state.request_id)


def _authenticate(request: Request, raw_session: str | None) -> AuthenticatedSession:
    return authenticate_request(request, raw_session)


def _status_data(status: CodexStatus) -> CodexStatusData:
    return CodexStatusData(
        installed=status.installed,
        version=status.version,
        selected_executable=status.selected_executable,
        alternatives=list(status.alternatives),
        installation_type=status.installation_type.value,
        conflict_detected=status.conflict_detected,
        authentication=status.authentication.value,
        capabilities=CodexCapabilityView(
            **{key: value.value for key, value in status.capabilities.__dict__.items()}
        ),
        remote_state=status.remote_state.value,
        remote_confidence=cast(
            Literal["reported", "inferred", "agentbox_observed", "unknown"],
            status.remote_confidence,
        ),
        diagnostics=[
            CodexDiagnosticView(
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


def _translate_error(exc: RuntimeOperationError) -> RuntimeGatewayError:
    return RuntimeGatewayError(
        code=exc.code,
        category=exc.category,
        message=exc.message,
        retryable=exc.retryable,
        retry_after=exc.retry_after,
    )


def _audit_action(
    request: Request,
    authenticated: AuthenticatedSession,
    *,
    action: str,
    result: str,
    error_code: str | None = None,
) -> None:
    metadata: dict[str, object] = {"runtime": "codex"}
    if error_code is not None:
        metadata["error_code"] = error_code
    services = _services(request)
    with services.database.transaction() as session:
        services.audit.record(
            session,
            actor_type="admin",
            actor_id=authenticated.user_id,
            action=action,
            result=result,
            request_id=_request_id(request),
            target_type="runtime",
            target_id="codex",
            metadata=metadata,
        )


@router.get("/status", response_model=CodexStatusResponse)
async def codex_status(
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> CodexStatusResponse:
    _authenticate(request, agentbox_session)
    try:
        status = await _runtime(request).status(_request_id(request))
    except RuntimeOperationError as exc:
        raise _translate_error(exc) from exc
    response.headers["Cache-Control"] = "no-store"
    return CodexStatusResponse(request_id=_request_id(request), data=_status_data(status))


async def _remote_action(
    request: Request,
    response: Response,
    raw_session: str | None,
    csrf_token: str | None,
    *,
    operation: str,
) -> CodexRemoteActionResponse:
    _validate_origin(request)
    authenticated = _authenticate(request, raw_session)
    _services(request).sessions.validate_csrf(authenticated, csrf_token)
    audit_prefix = f"codex_remote_{operation}"
    _audit_action(request, authenticated, action=f"{audit_prefix}_requested", result="requested")
    try:
        runtime = _runtime(request)
        result = (
            await runtime.start_remote(_request_id(request))
            if operation == "start"
            else await runtime.stop_remote(_request_id(request))
        )
    except RuntimeOperationError as exc:
        _audit_action(
            request,
            authenticated,
            action=f"{audit_prefix}_failed",
            result="failed",
            error_code=exc.code,
        )
        raise _translate_error(exc) from exc
    _audit_action(request, authenticated, action=f"{audit_prefix}_succeeded", result="succeeded")
    response.headers["Cache-Control"] = "no-store"
    return CodexRemoteActionResponse(
        request_id=_request_id(request),
        data=CodexRemoteActionData(
            outcome=cast(
                Literal["started", "stopped", "already_running", "already_stopped"],
                result.outcome,
            ),
            remote_state=result.remote_state.value,
        ),
    )


@router.post("/remote/start", response_model=CodexRemoteActionResponse)
async def start_remote(
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
) -> CodexRemoteActionResponse:
    return await _remote_action(
        request, response, agentbox_session, x_csrf_token, operation="start"
    )


@router.post("/remote/stop", response_model=CodexRemoteActionResponse)
async def stop_remote(
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
) -> CodexRemoteActionResponse:
    return await _remote_action(request, response, agentbox_session, x_csrf_token, operation="stop")


@router.post("/pair-codes", response_model=CodexPairResponse)
async def pair_code(
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
) -> CodexPairResponse:
    _validate_origin(request)
    authenticated = _authenticate(request, agentbox_session)
    _services(request).sessions.validate_csrf(authenticated, x_csrf_token)
    if not _services(request).sessions.is_recently_authenticated(
        authenticated, max_age_seconds=request.app.state.settings.recent_auth_ttl
    ):
        raise RecentAuthenticationRequired()
    _audit_action(request, authenticated, action="codex_pair_requested", result="requested")
    try:
        pair = await _runtime(request).generate_pair_code(_request_id(request))
    except RuntimeOperationError as exc:
        _audit_action(
            request,
            authenticated,
            action="codex_pair_failed",
            result="failed",
            error_code=exc.code,
        )
        raise _translate_error(exc) from exc
    _audit_action(request, authenticated, action="codex_pair_succeeded", result="succeeded")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return CodexPairResponse(
        request_id=_request_id(request),
        data=CodexPairData(
            pair_code=pair.code,
            expires_at=pair.expires_at,
            display_once=True,
        ),
    )
