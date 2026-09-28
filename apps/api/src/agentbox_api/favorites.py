"""Authenticated, metadata-only Project favorite routes."""

from __future__ import annotations

from typing import cast

from agentbox_core.errors import DatabaseNotReady
from agentbox_core.favorites import ProjectFavoriteState
from agentbox_core.services import ControlPlaneServices
from agentbox_protocol import (
    ProjectFavoriteData,
    ProjectFavoriteListData,
    ProjectFavoriteListResponse,
    ProjectFavoriteResponse,
    ProjectFavoriteSetRequest,
)
from fastapi import APIRouter, Cookie, Header, Request, Response
from sqlalchemy.exc import OperationalError

from agentbox_api.auth import SESSION_COOKIE, _validate_origin, authenticate_request

router = APIRouter(prefix="/api/v1/project-favorites", tags=["projects"])


def _services(request: Request) -> ControlPlaneServices:
    return cast(ControlPlaneServices, request.app.state.services)


def _data(value: ProjectFavoriteState) -> ProjectFavoriteData:
    return ProjectFavoriteData(
        project_id=value.project_id,
        favorite=value.favorite,
        revision=value.revision,
        updated_at=value.updated_at,
    )


@router.get("", response_model=ProjectFavoriteListResponse)
async def list_favorites(
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> ProjectFavoriteListResponse:
    authenticated = authenticate_request(request, agentbox_session)
    try:
        favorites = _services(request).favorites.list(authenticated.user_id)
    except OperationalError as exc:
        raise DatabaseNotReady() from exc
    response.headers["Cache-Control"] = "no-store"
    return ProjectFavoriteListResponse(
        request_id=str(request.state.request_id),
        data=ProjectFavoriteListData(favorites=[_data(value) for value in favorites]),
    )


@router.put("/{project_id}", response_model=ProjectFavoriteResponse)
async def set_favorite(
    project_id: str,
    payload: ProjectFavoriteSetRequest,
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
) -> ProjectFavoriteResponse:
    _validate_origin(request)
    authenticated = authenticate_request(request, agentbox_session)
    services = _services(request)
    services.sessions.validate_csrf(authenticated, x_csrf_token)
    try:
        value = services.favorites.set(
            authenticated.user_id,
            project_id,
            favorite=payload.favorite,
            expected_revision=payload.expected_revision,
            request_id=str(request.state.request_id),
        )
    except OperationalError as exc:
        raise DatabaseNotReady() from exc
    response.headers["Cache-Control"] = "no-store"
    return ProjectFavoriteResponse(
        request_id=str(request.state.request_id),
        data=_data(value),
    )
