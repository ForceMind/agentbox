"""Authenticated read-only metadata routes for Web Agent Workspace."""

from __future__ import annotations

from datetime import datetime
from typing import cast

from agentbox_core.services import ControlPlaneServices
from agentbox_core.waw_models import AgentWorkspaceSessionRecord
from agentbox_core.waw_sessions import WorkspaceSessionNotFound
from agentbox_protocol.metadata import StrictMetadataModel
from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import ConfigDict

from agentbox_api.auth import SESSION_COOKIE, authenticate_request

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


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
    runtime_host_installation_id: str
    runtime_host_installation_revision: int
    runtime_type: str
    binding_revision: int
    binding_digest: str
    runtime_session_name: str
    executable_fingerprint: str
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


def _services(request: Request) -> ControlPlaneServices:
    return cast(ControlPlaneServices, request.app.state.services)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "req_unknown"))


def _metadata(row: AgentWorkspaceSessionRecord) -> WorkspaceMetadata:
    return WorkspaceMetadata(
        id=row.id,
        project_id=row.project_id,
        agent_type=row.agent_type,
        state=row.state,
        reconciliation_state=row.reconciliation_state,
        generation=row.generation,
        revision=row.revision,
        runtime_host_installation_id=row.runtime_host_installation_id,
        runtime_host_installation_revision=row.runtime_host_installation_revision,
        runtime_type=row.runtime_type,
        binding_revision=row.binding_revision,
        binding_digest=row.binding_digest,
        runtime_session_name=row.runtime_session_name,
        executable_fingerprint=row.executable_fingerprint,
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
            .all()
        )
    response.headers["Cache-Control"] = "no-store"
    return WorkspaceListResponse(
        request_id=_request_id(request),
        data=WorkspaceListData(workspaces=[_metadata(row) for row in rows]),
    )


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
