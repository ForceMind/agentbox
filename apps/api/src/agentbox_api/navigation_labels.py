"""Authenticated, metadata-only navigation label catalog and Project routes."""

from __future__ import annotations

from typing import cast

from agentbox_core.errors import DatabaseNotReady
from agentbox_core.navigation_labels import (
    NavigationLabelState,
    ProjectLabelSetState,
    WorkspaceLabelSetState,
)
from agentbox_core.services import ControlPlaneServices
from agentbox_protocol import (
    NavigationLabelCreateRequest,
    NavigationLabelData,
    NavigationLabelDeleteImpactData,
    NavigationLabelDeleteImpactResponse,
    NavigationLabelDeleteRequest,
    NavigationLabelListData,
    NavigationLabelListResponse,
    NavigationLabelResponse,
    NavigationLabelUpdateRequest,
    ProjectLabelSetData,
    ProjectLabelSetRequest,
    ProjectLabelSetResponse,
    WorkspaceLabelSetData,
    WorkspaceLabelSetResponse,
)
from fastapi import APIRouter, Cookie, Header, Request, Response
from sqlalchemy.exc import OperationalError

from agentbox_api.auth import SESSION_COOKIE, _validate_origin, authenticate_request

router = APIRouter(prefix="/api/v1/project-labels", tags=["projects"])


def _services(request: Request) -> ControlPlaneServices:
    return cast(ControlPlaneServices, request.app.state.services)


def _label(value: NavigationLabelState) -> NavigationLabelData:
    return NavigationLabelData.model_validate(
        {
            "id": value.id,
            "name": value.name,
            "color": value.color,
            "revision": value.revision,
            "updated_at": value.updated_at,
        }
    )


def _project(value: ProjectLabelSetState) -> ProjectLabelSetData:
    return ProjectLabelSetData(
        project_id=value.project_id,
        labels=[_label(label) for label in value.labels],
        revision=value.revision,
        updated_at=value.updated_at,
    )


def _workspace(value: WorkspaceLabelSetState) -> WorkspaceLabelSetData:
    return WorkspaceLabelSetData.model_validate(
        {
            "workspace_id": value.workspace_id,
            "project_id": value.project_id,
            "agent_type": value.agent_type,
            "labels": [_label(label) for label in value.labels],
            "revision": value.revision,
            "updated_at": value.updated_at,
        }
    )


@router.get("", response_model=NavigationLabelListResponse)
async def list_labels(
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> NavigationLabelListResponse:
    authenticated = authenticate_request(request, agentbox_session)
    try:
        labels = _services(request).navigation_labels.list_catalog(authenticated.user_id)
    except OperationalError as exc:
        raise DatabaseNotReady() from exc
    response.headers["Cache-Control"] = "no-store"
    return NavigationLabelListResponse(
        request_id=str(request.state.request_id),
        data=NavigationLabelListData(labels=[_label(label) for label in labels]),
    )


@router.post("", response_model=NavigationLabelResponse)
async def create_label(
    payload: NavigationLabelCreateRequest,
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
) -> NavigationLabelResponse:
    _validate_origin(request)
    authenticated = authenticate_request(request, agentbox_session)
    services = _services(request)
    services.sessions.validate_csrf(authenticated, x_csrf_token)
    try:
        value = services.navigation_labels.create(
            authenticated.user_id,
            name=payload.name,
            color=payload.color,
            request_id=str(request.state.request_id),
        )
    except OperationalError as exc:
        raise DatabaseNotReady() from exc
    response.headers["Cache-Control"] = "no-store"
    return NavigationLabelResponse(request_id=str(request.state.request_id), data=_label(value))


@router.put("/{label_id}", response_model=NavigationLabelResponse)
async def update_label(
    label_id: str,
    payload: NavigationLabelUpdateRequest,
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
) -> NavigationLabelResponse:
    _validate_origin(request)
    authenticated = authenticate_request(request, agentbox_session)
    services = _services(request)
    services.sessions.validate_csrf(authenticated, x_csrf_token)
    try:
        value = services.navigation_labels.update(
            authenticated.user_id,
            label_id,
            name=payload.name,
            color=payload.color,
            expected_revision=payload.expected_revision,
            request_id=str(request.state.request_id),
        )
    except OperationalError as exc:
        raise DatabaseNotReady() from exc
    response.headers["Cache-Control"] = "no-store"
    return NavigationLabelResponse(request_id=str(request.state.request_id), data=_label(value))


@router.get("/{label_id}/delete-impact", response_model=NavigationLabelDeleteImpactResponse)
async def inspect_delete_label(
    label_id: str,
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> NavigationLabelDeleteImpactResponse:
    authenticated = authenticate_request(request, agentbox_session)
    try:
        affected = _services(request).navigation_labels.inspect_delete(
            authenticated.user_id, label_id
        )
    except OperationalError as exc:
        raise DatabaseNotReady() from exc
    response.headers["Cache-Control"] = "no-store"
    return NavigationLabelDeleteImpactResponse(
        request_id=str(request.state.request_id),
        data=NavigationLabelDeleteImpactData(
            label_id=label_id,
            affected_project_count=affected.affected_project_count,
            affected_workspace_count=affected.affected_workspace_count,
        ),
    )


@router.post("/{label_id}/delete", response_model=NavigationLabelDeleteImpactResponse)
async def delete_label(
    label_id: str,
    payload: NavigationLabelDeleteRequest,
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
) -> NavigationLabelDeleteImpactResponse:
    _validate_origin(request)
    authenticated = authenticate_request(request, agentbox_session)
    services = _services(request)
    services.sessions.validate_csrf(authenticated, x_csrf_token)
    try:
        affected = services.navigation_labels.delete(
            authenticated.user_id,
            label_id,
            expected_revision=payload.expected_revision,
            expected_affected_project_count=payload.expected_affected_project_count,
            expected_affected_workspace_count=payload.expected_affected_workspace_count,
            request_id=str(request.state.request_id),
        )
    except OperationalError as exc:
        raise DatabaseNotReady() from exc
    response.headers["Cache-Control"] = "no-store"
    return NavigationLabelDeleteImpactResponse(
        request_id=str(request.state.request_id),
        data=NavigationLabelDeleteImpactData(
            label_id=label_id,
            affected_project_count=affected.affected_project_count,
            affected_workspace_count=affected.affected_workspace_count,
        ),
    )


@router.get("/projects/{project_id}", response_model=ProjectLabelSetResponse)
async def get_project_labels(
    project_id: str,
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> ProjectLabelSetResponse:
    authenticated = authenticate_request(request, agentbox_session)
    try:
        value = _services(request).navigation_labels.get_project(authenticated.user_id, project_id)
    except OperationalError as exc:
        raise DatabaseNotReady() from exc
    response.headers["Cache-Control"] = "no-store"
    return ProjectLabelSetResponse(request_id=str(request.state.request_id), data=_project(value))


@router.put("/projects/{project_id}/{label_id}", response_model=ProjectLabelSetResponse)
async def set_project_label(
    project_id: str,
    label_id: str,
    payload: ProjectLabelSetRequest,
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
) -> ProjectLabelSetResponse:
    _validate_origin(request)
    authenticated = authenticate_request(request, agentbox_session)
    services = _services(request)
    services.sessions.validate_csrf(authenticated, x_csrf_token)
    try:
        value = services.navigation_labels.set_project(
            authenticated.user_id,
            project_id,
            label_id,
            assigned=payload.assigned,
            expected_revision=payload.expected_revision,
            request_id=str(request.state.request_id),
        )
    except OperationalError as exc:
        raise DatabaseNotReady() from exc
    response.headers["Cache-Control"] = "no-store"
    return ProjectLabelSetResponse(request_id=str(request.state.request_id), data=_project(value))


@router.get("/workspaces/{project_id}/{agent_type}", response_model=WorkspaceLabelSetResponse)
async def get_workspace_labels(
    project_id: str,
    agent_type: str,
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> WorkspaceLabelSetResponse:
    authenticated = authenticate_request(request, agentbox_session)
    try:
        value = _services(request).navigation_labels.get_workspace(
            authenticated.user_id, project_id, agent_type
        )
    except OperationalError as exc:
        raise DatabaseNotReady() from exc
    response.headers["Cache-Control"] = "no-store"
    return WorkspaceLabelSetResponse(
        request_id=str(request.state.request_id), data=_workspace(value)
    )


@router.put(
    "/workspaces/{project_id}/{agent_type}/{label_id}", response_model=WorkspaceLabelSetResponse
)
async def set_workspace_label(
    project_id: str,
    agent_type: str,
    label_id: str,
    payload: ProjectLabelSetRequest,
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
) -> WorkspaceLabelSetResponse:
    _validate_origin(request)
    authenticated = authenticate_request(request, agentbox_session)
    services = _services(request)
    services.sessions.validate_csrf(authenticated, x_csrf_token)
    try:
        value = services.navigation_labels.set_workspace(
            authenticated.user_id,
            project_id,
            agent_type,
            label_id,
            assigned=payload.assigned,
            expected_revision=payload.expected_revision,
            request_id=str(request.state.request_id),
        )
    except OperationalError as exc:
        raise DatabaseNotReady() from exc
    response.headers["Cache-Control"] = "no-store"
    return WorkspaceLabelSetResponse(
        request_id=str(request.state.request_id), data=_workspace(value)
    )
