"""Authenticated read-only metadata routes for Web Agent Workspace."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Protocol, cast

from agentbox_core.services import ControlPlaneServices
from agentbox_core.waw_models import AgentWorkspaceSessionRecord
from agentbox_core.waw_sessions import WorkspaceSessionNotFound
from agentbox_protocol.metadata import StrictMetadataModel
from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import ConfigDict, ValidationError

from agentbox_api.auth import SESSION_COOKIE, authenticate_request
from agentbox_api.waw_control_client import WAWControlClientError

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


class _WAWLifecycleRequester(Protocol):
    async def request_lifecycle(
        self, action: str, request: dict[str, object]
    ) -> dict[str, object]: ...


class _WorkspaceIdentityRow(Protocol):
    id: str
    project_id: str
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


def _services(request: Request) -> ControlPlaneServices:
    return cast(ControlPlaneServices, request.app.state.services)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "req_unknown"))


def _waw_request_id() -> str:
    """Generate a private WAW correlation ID unrelated to client headers."""

    return f"wreq_{secrets.token_hex(16)}"


def _waw_coordinator(request: Request) -> _WAWLifecycleRequester:
    coordinator = getattr(request.app.state, "waw_bind_coordinator", None)
    if coordinator is None or not callable(getattr(coordinator, "request_lifecycle", None)):
        raise WAWControlClientError(
            "RUNTIME_INSTALLATION_UNTRUSTED",
            "WAW Runtime binding is not configured",
            retryable=True,
        )
    return cast(_WAWLifecycleRequester, coordinator)


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
    authenticate_request(request, agentbox_session)
    with _services(request).database.transaction() as session:
        rows = tuple(
            session.query(AgentWorkspaceSessionRecord)
            .order_by(AgentWorkspaceSessionRecord.created_at, AgentWorkspaceSessionRecord.id)
            .limit(32)
            .all()
        )
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
    authenticate_request(request, agentbox_session)
    try:
        row = _services(request).workspaces.get(workspace_id)
    except WorkspaceSessionNotFound as exc:
        raise HTTPException(status_code=404, detail="Workspace not found") from exc
    payload = {
        "protocol_version": 1,
        "request_id": _waw_request_id(),
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
    authenticate_request(request, agentbox_session)
    try:
        row = _services(request).workspaces.get(workspace_id)
    except WorkspaceSessionNotFound as exc:
        raise HTTPException(status_code=404, detail="Workspace not found") from exc
    response.headers["Cache-Control"] = "no-store"
    return WorkspaceResponse(request_id=_request_id(request), data=_metadata(row))
