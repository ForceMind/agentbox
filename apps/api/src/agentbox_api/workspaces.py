"""Authenticated read-only metadata routes for Web Agent Workspace."""

from __future__ import annotations

import re
import secrets
from contextlib import suppress
from datetime import datetime
from typing import Literal, Protocol, cast

from agentbox_core.errors import AgentBoxError, RecentAuthenticationRequired, RuntimeGatewayError
from agentbox_core.services import AuthenticatedSession, ControlPlaneServices
from agentbox_core.waw import AgentType, StopResult
from agentbox_core.waw_models import AgentWorkspaceSessionRecord
from agentbox_core.waw_sessions import (
    WorkspaceSessionConflict,
    WorkspaceSessionNotFound,
)
from agentbox_core.waw_tickets import (
    AttachmentAuthority,
    AttachmentTuple,
    AuthenticatedAttachmentContext,
    TicketAuthorityError,
)
from agentbox_protocol.metadata import StrictMetadataModel
from fastapi import APIRouter, Cookie, Header, HTTPException, Request, Response
from pydantic import ConfigDict, ValidationError, field_validator

from agentbox_api.auth import SESSION_COOKIE, _validate_origin, authenticate_request
from agentbox_api.waw_admission import (
    ProtocolRecentAuth,
    WAWAdmissionError,
    WAWAttachmentTicketRequest,
    WAWAttachmentTicketResponse,
    WAWRuntimeReadiness,
    prepare_attachment,
)
from agentbox_api.waw_authorization import (
    SingleAdminWorkspacePolicy,
    WorkspaceAuthorizationPolicy,
)
from agentbox_api.waw_control_client import WAWControlClientError

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])
project_workspaces_router = APIRouter(prefix="/api/v1/projects", tags=["workspaces"])
_WORKSPACE_ID = re.compile(r"\Aaws_[0-9a-f]{32}\Z")
_PROJECT_ID = re.compile(r"\Aprj_[0-9a-f]{32}\Z")


class _WAWLifecycleRequester(Protocol):
    @property
    def attestation(self) -> dict[str, object] | None: ...

    async def request_lifecycle(
        self, action: str, request: dict[str, object]
    ) -> dict[str, object]: ...


class WAWRequestIdError(RuntimeError):
    """Secure WAW correlation-ID generation failed."""


class _WorkspaceIdentityRow(Protocol):
    id: str
    project_id: str
    authorization_scope: str
    agent_type: str
    generation: int
    binding_revision: int
    binding_digest: str


class WorkspaceMetadata(StrictMetadataModel):
    """Non-secret durable metadata; terminal bytes and tickets are excluded."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    project_id: str
    agent_type: str
    state: str
    reconciliation_state: str
    generation: int
    revision: int
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime
    exit_code: int | None
    failure_code: str | None


class WorkspaceListData(StrictMetadataModel):
    workspaces: list[WorkspaceMetadata]


class WorkspaceListResponse(StrictMetadataModel):
    request_id: str
    data: WorkspaceListData


class WorkspaceResponse(StrictMetadataModel):
    request_id: str
    data: WorkspaceMetadata


class WorkspaceAttachmentCapacity(StrictMetadataModel):
    """Bounded attachment counters; no ticket or bearer material crosses API."""

    admitted: str
    pending: str
    limit: str


class WorkspaceRuntimeStatus(StrictMetadataModel):
    """Runtime evidence for one workspace; no terminal bytes or tickets."""

    workspace_id: str
    project_id: str
    agent_type: str
    generation: str
    binding_revision: str
    binding_digest: str
    state: str
    reconciliation_state: str
    runtime_epoch: str
    process_state: str
    exit_code: int | None
    attachment_capacity: WorkspaceAttachmentCapacity


class WorkspaceRuntimeStatusResponse(StrictMetadataModel):
    request_id: str
    data: WorkspaceRuntimeStatus


class EmptyWorkspaceBody(StrictMetadataModel):
    """Exact empty JSON object used by start/reconnect mutations."""

    model_config = ConfigDict(extra="forbid", strict=True)


class WorkspaceStartResponse(StrictMetadataModel):
    request_id: str
    workspace_id: str
    project_id: str
    agent_type: Literal["claude"]
    state: str
    generation: str


class WorkspaceStopRequest(StrictMetadataModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    generation: str

    @field_validator("generation")
    @classmethod
    def _generation(cls, value: str) -> str:
        if not re.fullmatch(r"[1-9][0-9]{0,19}", value) or int(value) > 2**64 - 1:
            raise ValueError("generation must be a positive uint64 decimal string")
        return value


class WorkspaceStopResponse(StrictMetadataModel):
    request_id: str
    workspace_id: str
    project_id: str
    agent_type: Literal["claude"]
    generation: str
    stop_operation_id: str
    state: str


class WorkspaceDetachRequest(StrictMetadataModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    attachment_id: str
    generation: str
    lease_number: str

    @field_validator("attachment_id")
    @classmethod
    def _attachment_id(cls, value: str) -> str:
        if not re.fullmatch(r"att_[0-9a-f]{32}", value):
            raise ValueError("attachment_id is invalid")
        return value

    @field_validator("generation", "lease_number")
    @classmethod
    def _positive_decimal(cls, value: str) -> str:
        if not re.fullmatch(r"[1-9][0-9]{0,19}", value) or int(value) > 2**64 - 1:
            raise ValueError("value must be a positive uint64 decimal string")
        return value


class WorkspaceDetachResponse(StrictMetadataModel):
    request_id: str
    detach_operation_id: str
    workspace_id: str
    attachment_id: str
    generation: str
    lease_number: str
    result: Literal["detached", "already_detached"]
    cleanup_state: Literal["ATTACH_PTY_CLOSED"]
    state: str


def _services(request: Request) -> ControlPlaneServices:
    return cast(ControlPlaneServices, request.app.state.services)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "req_unknown"))


def _waw_request_id() -> str:
    """Generate a private WAW correlation ID unrelated to client headers."""

    try:
        return f"wreq_{secrets.token_hex(16)}"
    except Exception as exc:
        raise WAWRequestIdError("secure WAW request-id randomness is unavailable") from exc


def _workspace_policy(request: Request) -> WorkspaceAuthorizationPolicy:
    configured = getattr(request.app.state, "waw_authorization_policy", None)
    if configured is None:
        return SingleAdminWorkspacePolicy()
    if not callable(getattr(configured, "allows", None)):
        raise RuntimeError("invalid WAW authorization policy")
    return cast(WorkspaceAuthorizationPolicy, configured)


def _workspace_id_or_404(workspace_id: str) -> None:
    if not _WORKSPACE_ID.fullmatch(workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")


def _project_id_or_404(project_id: str) -> None:
    if not _PROJECT_ID.fullmatch(project_id):
        raise HTTPException(status_code=404, detail="Project not found")


def _authorize_workspace(
    request: Request,
    authenticated: AuthenticatedSession,
    row: _WorkspaceIdentityRow,
) -> None:
    # Unknown and unauthorized workspace identities deliberately collapse to
    # the same 404 response to prevent metadata enumeration.
    if not _workspace_policy(request).allows(authenticated, cast(AgentWorkspaceSessionRecord, row)):
        raise HTTPException(status_code=404, detail="Workspace not found")


def _waw_coordinator(request: Request) -> _WAWLifecycleRequester:
    coordinator = getattr(request.app.state, "waw_bind_coordinator", None)
    if coordinator is None or not callable(getattr(coordinator, "request_lifecycle", None)):
        raise WAWControlClientError(
            "RUNTIME_INSTALLATION_UNTRUSTED",
            "WAW Runtime binding is not configured",
            retryable=True,
        )
    return cast(_WAWLifecycleRequester, coordinator)


def _recent_authenticator(request: Request) -> ProtocolRecentAuth:
    """Adapt the database-backed recent-auth marker to admission's narrow port."""

    services = _services(request)
    max_age = int(request.app.state.settings.recent_auth_ttl)

    class _Adapter:
        def is_recently_authenticated(self, authenticated: AuthenticatedSession) -> bool:
            return services.sessions.is_recently_authenticated(
                authenticated, max_age_seconds=max_age
            )

    return _Adapter()


def _runtime_error(exc: WAWControlClientError) -> RuntimeGatewayError:
    category = "conflict"
    if exc.code in {
        "RUNTIME_UNAVAILABLE",
        "RUNTIME_INSTALLATION_UNTRUSTED",
        "RUNTIME_INSTALLATION_MISMATCH",
        "WAW_SOCKET_SET_INCOMPLETE",
        "WAW_SOCKET_PROVENANCE_INVALID",
    }:
        category = "unavailable"
    elif exc.code == "PROTOCOL_INVALID":
        category = "validation"
    return RuntimeGatewayError(
        code=exc.code,
        category=category,
        message="WAW Runtime request failed",
        retryable=exc.retryable,
    )


def _admission_error(exc: WAWAdmissionError) -> RuntimeGatewayError:
    category = "conflict"
    if exc.code in {
        "RUNTIME_UNAVAILABLE",
        "RUNTIME_INSTALLATION_MISMATCH",
        "RANDOMNESS_UNAVAILABLE",
    }:
        category = "unavailable"
    elif exc.code == "ORIGIN_INVALID":
        category = "forbidden"
    return RuntimeGatewayError(
        code=exc.code,
        category=category,
        message="WAW attachment is not available",
        retryable=exc.code in {"RUNTIME_UNAVAILABLE"},
    )


def _validate_runtime_status_identity(
    status: WorkspaceRuntimeStatus, row: _WorkspaceIdentityRow
) -> None:
    """Fence Runtime metadata to the exact URL/DB workspace tuple."""

    expected = (
        row.id,
        row.project_id,
        row.agent_type,
        str(row.generation),
        str(row.binding_revision),
        row.binding_digest,
    )
    observed = (
        status.workspace_id,
        status.project_id,
        status.agent_type,
        status.generation,
        status.binding_revision,
        status.binding_digest,
    )
    if observed != expected:
        raise WAWControlClientError(
            "PROJECT_IDENTITY_CHANGED", "WAW Runtime status identity does not match workspace"
        )


def _validate_runtime_status_epoch(
    status: WorkspaceRuntimeStatus, coordinator: _WAWLifecycleRequester
) -> None:
    """Reject observations from a Runtime epoch other than the bound peer."""

    attestation = getattr(coordinator, "attestation", None)
    if not isinstance(attestation, dict):
        raise WAWControlClientError(
            "RUNTIME_INSTALLATION_UNTRUSTED",
            "WAW Runtime status requires a verified bind attestation",
        )
    expected_epoch = attestation.get("runtime_epoch")
    if not isinstance(expected_epoch, str) or not expected_epoch:
        raise WAWControlClientError(
            "RUNTIME_INSTALLATION_UNTRUSTED",
            "WAW Runtime bind attestation has no valid epoch",
        )
    if status.runtime_epoch != expected_epoch:
        raise WAWControlClientError(
            "RUNTIME_INSTALLATION_MISMATCH", "WAW Runtime status epoch is stale"
        )


def _metadata(row: AgentWorkspaceSessionRecord) -> WorkspaceMetadata:
    return WorkspaceMetadata(
        id=row.id,
        project_id=row.project_id,
        agent_type=row.agent_type,
        state=row.state,
        reconciliation_state=row.reconciliation_state,
        generation=row.generation,
        revision=row.revision,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_seen_at=row.last_seen_at,
        exit_code=row.exit_code,
        failure_code=row.failure_code,
    )


@router.get("", response_model=WorkspaceListResponse)
async def list_workspaces(
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> WorkspaceListResponse:
    authenticated = authenticate_request(request, agentbox_session)
    policy = _workspace_policy(request)
    with _services(request).database.transaction() as session:
        # Apply the authorization policy before the bounded response cap.  A
        # policy may depend on more than a single SQL column, so filtering is
        # deliberately performed on hydrated rows while ``yield_per`` keeps
        # the scan bounded in memory.  This avoids hiding authorized rows
        # behind the first 32 unauthorized records.
        rows_list: list[AgentWorkspaceSessionRecord] = []
        query = session.query(AgentWorkspaceSessionRecord).order_by(
            AgentWorkspaceSessionRecord.created_at, AgentWorkspaceSessionRecord.id
        )
        for row in query.yield_per(64):
            if policy.allows(authenticated, row):
                rows_list.append(row)
                if len(rows_list) == 32:
                    break
        rows = tuple(rows_list)
    response.headers["Cache-Control"] = "no-store"
    return WorkspaceListResponse(
        request_id=_request_id(request),
        data=WorkspaceListData(workspaces=[_metadata(row) for row in rows]),
    )


@router.get("/{workspace_id}/status", response_model=WorkspaceRuntimeStatusResponse)
async def get_runtime_status(
    workspace_id: str,
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> WorkspaceRuntimeStatusResponse:
    _workspace_id_or_404(workspace_id)
    authenticated = authenticate_request(request, agentbox_session)
    try:
        row = _services(request).workspaces.get(workspace_id)
    except WorkspaceSessionNotFound as exc:
        raise HTTPException(status_code=404, detail="Workspace not found") from exc
    _authorize_workspace(request, authenticated, row)
    try:
        waw_request_id = _waw_request_id()
    except WAWRequestIdError as exc:
        raise HTTPException(status_code=503, detail="WAW Runtime status unavailable") from exc
    payload = {
        "protocol_version": 1,
        "request_id": waw_request_id,
        "action": "workspace.workspace.status",
        "workspace_id": row.id,
        "project_id": row.project_id,
        "agent_type": row.agent_type,
        "generation": str(row.generation),
        "binding_revision": str(row.binding_revision),
        "binding_digest": row.binding_digest,
        "runtime_host_installation_id": row.runtime_host_installation_id,
        "runtime_host_installation_revision": str(row.runtime_host_installation_revision),
    }
    try:
        coordinator = _waw_coordinator(request)
        runtime = await coordinator.request_lifecycle("workspace.workspace.status", payload)
    except WAWControlClientError as exc:
        status_code = 503 if exc.retryable or exc.code.startswith("RUNTIME_") else 502
        raise HTTPException(
            status_code=status_code, detail="WAW Runtime status unavailable"
        ) from exc
    try:
        status = WorkspaceRuntimeStatus.model_validate(runtime)
    except ValidationError as exc:
        raise HTTPException(
            status_code=502, detail="WAW Runtime status response is invalid"
        ) from exc
    try:
        _validate_runtime_status_epoch(status, coordinator)
        _validate_runtime_status_identity(status, row)
    except WAWControlClientError as exc:
        raise HTTPException(status_code=502, detail="WAW Runtime status identity mismatch") from exc
    response.headers["Cache-Control"] = "no-store"
    return WorkspaceRuntimeStatusResponse(request_id=_request_id(request), data=status)


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> WorkspaceResponse:
    _workspace_id_or_404(workspace_id)
    authenticated = authenticate_request(request, agentbox_session)
    try:
        row = _services(request).workspaces.get(workspace_id)
    except WorkspaceSessionNotFound as exc:
        raise HTTPException(status_code=404, detail="Workspace not found") from exc
    _authorize_workspace(request, authenticated, row)
    response.headers["Cache-Control"] = "no-store"
    return WorkspaceResponse(request_id=_request_id(request), data=_metadata(row))


@project_workspaces_router.post(
    "/{project_id}/workspaces/{agent_type}/start",
    response_model=WorkspaceStartResponse,
)
async def start_workspace(
    project_id: str,
    agent_type: Literal["claude"],
    request: Request,
    response: Response,
    _body: EmptyWorkspaceBody,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
) -> WorkspaceStartResponse:
    """Start one exact Project/AgentType workspace generation.

    The route intentionally requires a pre-registered durable workspace.  A
    future installer/Runtime binding flow may create that row, but the API
    never invents executable or filesystem provenance in a browser request.
    """

    _validate_origin(request)
    _project_id_or_404(project_id)
    authenticated = authenticate_request(request, agentbox_session)
    _services(request).sessions.validate_csrf(authenticated, x_csrf_token)
    if not _services(request).sessions.is_recently_authenticated(
        authenticated, max_age_seconds=int(request.app.state.settings.recent_auth_ttl)
    ):
        raise RecentAuthenticationRequired()
    try:
        project = _services(request).projects.get(project_id, ready=True)
    except Exception as exc:
        # ProjectService already maps its own typed errors; avoid leaking a
        # path or ORM detail if a malformed identifier reaches this boundary.
        if isinstance(exc, AgentBoxError):
            raise
        raise RuntimeGatewayError(
            code="WORKSPACE_NOT_READY", category="conflict", message="Project is not ready"
        ) from exc
    if agent_type != "claude":
        raise RuntimeGatewayError(
            code="WAW_AGENT_UNSUPPORTED", category="validation", message="Agent type is unsupported"
        )
    workspace_id_value = _workspace_id_for(project.id, agent_type)
    try:
        row = _services(request).workspaces.get(workspace_id_value)
    except WorkspaceSessionNotFound as exc:
        raise RuntimeGatewayError(
            code="WORKSPACE_NOT_READY",
            category="conflict",
            message="Workspace binding is not registered",
        ) from exc
    if row.project_id != project.id or row.agent_type != agent_type:
        raise RuntimeGatewayError(
            code="PROJECT_IDENTITY_CHANGED",
            category="conflict",
            message="Workspace identity changed",
        )
    if row.state == "RUNNING":
        response.headers.update({"Cache-Control": "no-store", "Pragma": "no-cache"})
        return WorkspaceStartResponse(
            request_id=_request_id(request),
            workspace_id=row.id,
            project_id=row.project_id,
            agent_type="claude",
            state=row.state,
            generation=str(row.generation),
        )
    if row.state == "STARTING":
        expected_revision = row.revision
    else:
        try:
            row = _services(request).workspaces.begin_start(row.id, expected_revision=row.revision)
        except WorkspaceSessionConflict as exc:
            raise RuntimeGatewayError(
                code="WORKSPACE_START_IN_PROGRESS",
                category="conflict",
                message="Workspace start is already in progress",
            ) from exc
        expected_revision = row.revision
    payload = _lifecycle_payload(row, request, action="workspace.workspace.start")
    try:
        runtime = await _waw_coordinator(request).request_lifecycle(
            "workspace.workspace.start", payload
        )
    except WAWControlClientError as exc:
        raise _runtime_error(exc) from exc
    state = runtime.get("state")
    if not isinstance(state, str) or state not in {
        "RUNNING",
        "NEEDS_INTERACTION",
        "TRUST_REQUIRED",
        "LOGIN_REQUIRED",
    }:
        raise RuntimeGatewayError(
            code="RUNTIME_INSTALLATION_MISMATCH",
            category="unavailable",
            message="Invalid Runtime state",
        )
    try:
        row = _services(request).workspaces.transition(
            row.id,
            expected_revision=expected_revision,
            state=state,
            reconciliation_state="authoritative",
        )
    except WorkspaceSessionConflict as exc:
        raise RuntimeGatewayError(
            code="PROJECT_IDENTITY_CHANGED",
            category="conflict",
            message="Workspace revision is stale",
        ) from exc
    response.headers.update({"Cache-Control": "no-store", "Pragma": "no-cache"})
    return WorkspaceStartResponse(
        request_id=_request_id(request),
        workspace_id=row.id,
        project_id=row.project_id,
        agent_type="claude",
        state=row.state,
        generation=str(row.generation),
    )


@router.post("/{workspace_id}/attachments", response_model=WAWAttachmentTicketResponse)
async def issue_attachment_ticket(
    workspace_id: str,
    request: Request,
    response: Response,
    payload: WAWAttachmentTicketRequest,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
) -> WAWAttachmentTicketResponse:
    _workspace_id_or_404(workspace_id)
    _validate_origin(request)
    authenticated = authenticate_request(request, agentbox_session)
    _services(request).sessions.validate_csrf(authenticated, x_csrf_token)
    try:
        row = _services(request).workspaces.get(workspace_id)
    except WorkspaceSessionNotFound as exc:
        raise HTTPException(status_code=404, detail="Workspace not found") from exc
    _authorize_workspace(request, authenticated, row)
    coordinator = _waw_coordinator(request)
    attestation = coordinator.attestation
    if not isinstance(attestation, dict):
        raise RuntimeGatewayError(
            code="RUNTIME_INSTALLATION_UNTRUSTED",
            category="unavailable",
            message="Runtime is not bound",
            retryable=True,
        )
    try:
        runtime = WAWRuntimeReadiness(
            runtime_host_installation_id=str(attestation["runtime_host_installation_id"]),
            runtime_host_installation_revision=int(
                attestation["runtime_host_installation_revision"]
            ),
            runtime_epoch=str(attestation["runtime_epoch"]),
            ready=True,
        )
        origin = request.headers.get("origin", "")
        issued = prepare_attachment(
            authenticated=authenticated,
            row=row,
            policy=_workspace_policy(request),
            recent_authenticator=_recent_authenticator(request),
            runtime=runtime,
            bound_runtime_epoch=str(attestation["runtime_epoch"]),
            authority=_attachment_authority(request),
            origin=origin,
            allowed_origins=request.app.state.settings.allowed_origins,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeGatewayError(
            code="RUNTIME_INSTALLATION_UNTRUSTED",
            category="unavailable",
            message="Runtime attestation is invalid",
            retryable=True,
        ) from exc
    except WAWAdmissionError as exc:
        raise _admission_error(exc) from exc
    response.headers.update({"Cache-Control": "no-store", "Pragma": "no-cache"})
    return WAWAttachmentTicketResponse.from_issued(
        _waw_request_id(), issued, runtime_epoch=runtime.runtime_epoch
    )


@router.post("/{workspace_id}/reconnect", response_model=WAWAttachmentTicketResponse)
async def reconnect_workspace(
    workspace_id: str,
    request: Request,
    response: Response,
    _body: EmptyWorkspaceBody,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
) -> WAWAttachmentTicketResponse:
    """Reconnect always issues a fresh ticket; old bearers are never reused."""

    return await issue_attachment_ticket(
        workspace_id,
        request,
        response,
        WAWAttachmentTicketRequest(mode="writer"),
        agentbox_session,
        x_csrf_token,
    )


@router.post("/{workspace_id}/stop", response_model=WorkspaceStopResponse)
async def stop_workspace(
    workspace_id: str,
    request: Request,
    response: Response,
    payload: WorkspaceStopRequest,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
) -> WorkspaceStopResponse:
    """Stop exactly the caller-selected durable workspace generation."""

    _workspace_id_or_404(workspace_id)
    _validate_origin(request)
    authenticated = authenticate_request(request, agentbox_session)
    _services(request).sessions.validate_csrf(authenticated, x_csrf_token)
    if not _services(request).sessions.is_recently_authenticated(
        authenticated, max_age_seconds=int(request.app.state.settings.recent_auth_ttl)
    ):
        raise RecentAuthenticationRequired()
    try:
        row = _services(request).workspaces.get(workspace_id)
    except WorkspaceSessionNotFound as exc:
        raise HTTPException(status_code=404, detail="Workspace not found") from exc
    _authorize_workspace(request, authenticated, row)
    if int(payload.generation) != row.generation:
        raise RuntimeGatewayError(
            code="ATTACHMENT_STALE", category="conflict", message="Workspace generation is stale"
        )
    try:
        operation = _services(request).workspaces.begin_stop(row.id, expected_revision=row.revision)
    except WorkspaceSessionConflict as exc:
        raise RuntimeGatewayError(
            code="RECONCILIATION_REQUIRED", category="conflict", message="Workspace stop is fenced"
        ) from exc
    try:
        runtime = await _waw_coordinator(request).request_lifecycle(
            "workspace.workspace.stop",
            _lifecycle_payload(row, request, action="workspace.workspace.stop"),
        )
    except WAWControlClientError as exc:
        with suppress(Exception):
            _services(request).workspaces.complete_stop(
                operation.id, result=StopResult.RECONCILIATION_REQUIRED
            )
        raise _runtime_error(exc) from exc
    state = runtime.get("state")
    if state == "STOPPED":
        try:
            _services(request).workspaces.complete_stop(operation.id, result=StopResult.STOPPED)
        except WorkspaceSessionConflict as exc:
            raise RuntimeGatewayError(
                code="RECONCILIATION_REQUIRED",
                category="conflict",
                message="Stop completion is stale",
            ) from exc
    else:
        with suppress(WorkspaceSessionConflict):
            _services(request).workspaces.complete_stop(
                operation.id, result=StopResult.TIMEOUT, failure_code="STOP_TIMEOUT"
            )
        raise RuntimeGatewayError(
            code="STOP_TIMEOUT",
            category="conflict",
            message="Runtime stop is not confirmed",
            retryable=True,
        )
    response.headers.update({"Cache-Control": "no-store", "Pragma": "no-cache"})
    return WorkspaceStopResponse(
        request_id=_request_id(request),
        workspace_id=row.id,
        project_id=row.project_id,
        agent_type="claude",
        generation=str(row.generation),
        stop_operation_id=operation.id,
        state="STOPPED",
    )


@router.post("/{workspace_id}/detach", response_model=WorkspaceDetachResponse)
async def detach_workspace(
    workspace_id: str,
    request: Request,
    response: Response,
    payload: WorkspaceDetachRequest,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
) -> WorkspaceDetachResponse:
    """Close one PTY attachment, releasing the writer slot only after Runtime ACK."""

    _workspace_id_or_404(workspace_id)
    _validate_origin(request)
    authenticated = authenticate_request(request, agentbox_session)
    _services(request).sessions.validate_csrf(authenticated, x_csrf_token)
    try:
        row = _services(request).workspaces.get(workspace_id)
    except WorkspaceSessionNotFound as exc:
        raise HTTPException(status_code=404, detail="Workspace not found") from exc
    _authorize_workspace(request, authenticated, row)
    if int(payload.generation) != row.generation:
        raise RuntimeGatewayError(
            code="ATTACHMENT_STALE", category="conflict", message="Attachment generation is stale"
        )
    coordinator = _waw_coordinator(request)
    attestation = coordinator.attestation
    authority = _attachment_authority(request)
    if not isinstance(attestation, dict):
        raise RuntimeGatewayError(
            code="RUNTIME_INSTALLATION_UNTRUSTED",
            category="unavailable",
            message="Runtime is not bound",
            retryable=True,
        )
    try:
        runtime_epoch = str(attestation["runtime_epoch"])
        runtime_host_id = str(attestation["runtime_host_installation_id"])
        runtime_host_revision = str(attestation["runtime_host_installation_revision"])
        tuple_value = AttachmentTuple(
            workspace_id=row.id,
            project_id=row.project_id,
            agent_type=row.agent_type,
            attachment_id=payload.attachment_id,
            lease_number=int(payload.lease_number),
            generation=row.generation,
            auth_epoch=authenticated.auth_epoch,
            api_authority_epoch=authority.authority_epoch,
            runtime_host_installation_id=runtime_host_id,
            runtime_host_installation_revision=int(runtime_host_revision),
            binding_revision=row.binding_revision,
            binding_digest=row.binding_digest,
        )
        runtime = await coordinator.request_lifecycle(
            "workspace.attach.detach",
            {
                "protocol_version": 1,
                "request_id": _waw_request_id(),
                "action": "workspace.attach.detach",
                "workspace_id": row.id,
                "project_id": row.project_id,
                "agent_type": row.agent_type,
                "attachment_id": payload.attachment_id,
                "mode": "writer",
                "lease_number": payload.lease_number,
                "generation": str(row.generation),
                "binding_revision": str(row.binding_revision),
                "binding_digest": row.binding_digest,
                "auth_epoch": str(authenticated.auth_epoch),
                "api_authority_epoch": str(authority.authority_epoch),
                "runtime_host_installation_id": runtime_host_id,
                "runtime_host_installation_revision": runtime_host_revision,
                "runtime_epoch": runtime_epoch,
            },
        )
        if runtime.get("cleanup_state") != "ATTACH_PTY_CLOSED":
            raise RuntimeGatewayError(
                code="DETACH_FAILED",
                category="unavailable",
                message="Runtime did not confirm attachment cleanup",
                retryable=True,
            )
        authority.detach(
            tuple_value,
            context=AuthenticatedAttachmentContext(
                session_id=authenticated.session_id,
                user_id=authenticated.user_id,
                authorization_scope=row.authorization_scope,
                origin=request.headers.get("origin", ""),
                runtime_epoch=runtime_epoch,
                auth_epoch=authenticated.auth_epoch,
            ),
        )
    except WAWControlClientError as exc:
        raise _runtime_error(exc) from exc
    except TicketAuthorityError as exc:
        raise RuntimeGatewayError(
            code="ATTACHMENT_STALE", category="conflict", message="Attachment lease is stale"
        ) from exc
    except RuntimeGatewayError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeGatewayError(
            code="ATTACHMENT_STALE", category="conflict", message="Attachment tuple is invalid"
        ) from exc
    response.headers.update({"Cache-Control": "no-store", "Pragma": "no-cache"})
    return WorkspaceDetachResponse(
        request_id=_request_id(request),
        detach_operation_id=f"wdo_{secrets.token_hex(16)}",
        workspace_id=row.id,
        attachment_id=payload.attachment_id,
        generation=str(row.generation),
        lease_number=payload.lease_number,
        result="detached",
        cleanup_state="ATTACH_PTY_CLOSED",
        state=row.state,
    )


def _workspace_id_for(project_id: str, agent_type: str) -> str:
    from agentbox_core.waw import workspace_id

    return workspace_id(project_id, AgentType(agent_type))


def _lifecycle_payload(
    row: AgentWorkspaceSessionRecord, request: Request, *, action: str
) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "request_id": _waw_request_id(),
        "action": action,
        "workspace_id": row.id,
        "project_id": row.project_id,
        "agent_type": row.agent_type,
        "generation": str(row.generation),
        "binding_revision": str(row.binding_revision),
        "binding_digest": row.binding_digest,
        "runtime_host_installation_id": row.runtime_host_installation_id,
        "runtime_host_installation_revision": str(row.runtime_host_installation_revision),
    }


def _attachment_authority(request: Request) -> AttachmentAuthority:
    authority = getattr(request.app.state, "waw_attachment_authority", None)
    if not isinstance(authority, AttachmentAuthority):
        raise RuntimeGatewayError(
            code="ATTACHMENT_TICKET_UNAVAILABLE",
            category="unavailable",
            message="WAW attachment authority is unavailable",
            retryable=True,
        )
    return authority
