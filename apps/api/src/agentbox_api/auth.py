"""Cookie-authenticated Phase 3 API routes."""

from __future__ import annotations

import asyncio
import ipaddress
from typing import cast
from urllib.parse import urlsplit

from agentbox_core.configuration import Settings
from agentbox_core.errors import InvalidOrigin
from agentbox_core.services import (
    AuthenticatedSession,
    AuthService,
    ControlPlaneServices,
    IssuedSession,
)
from agentbox_protocol import (
    AdminView,
    AuthData,
    AuthResponse,
    AuthSessionView,
    LoginRequest,
)
from fastapi import APIRouter, Cookie, Header, Request, Response

SESSION_COOKIE = "agentbox_session"
router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


class BoundedLoginExecutor:
    """Keep synchronous login/Argon2 work off-loop with bounded admission."""

    def __init__(self, auth_service: AuthService, *, max_concurrency: int) -> None:
        self._auth_service = auth_service
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def login(
        self,
        *,
        username: str,
        password: str,
        source_identifier: str,
        request_id: str | None,
        client_label: str | None,
    ) -> IssuedSession:
        # Acquire capacity before submitting work to the default thread pool;
        # excess requests wait as coroutines rather than unbounded thread jobs.
        async with self._semaphore:
            return await asyncio.to_thread(
                self._auth_service.login,
                username=username,
                password=password,
                source_identifier=source_identifier,
                request_id=request_id,
                client_label=client_label,
            )


def _services(request: Request) -> ControlPlaneServices:
    return cast(ControlPlaneServices, request.app.state.services)


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _login_executor(request: Request) -> BoundedLoginExecutor:
    return cast(BoundedLoginExecutor, request.app.state.login_executor)


def _request_id(request: Request) -> str:
    return str(request.state.request_id)


def _validate_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    settings = _settings(request)
    if origin is None or len(origin) > 256 or origin not in settings.allowed_origins:
        raise InvalidOrigin()
    parsed = urlsplit(origin)
    if (
        parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise InvalidOrigin()
    host = request.headers.get("host")
    allowed_hosts = {urlsplit(allowed).netloc for allowed in settings.allowed_origins}
    if host is None or len(host) > 255 or host not in allowed_hosts:
        raise InvalidOrigin()


def _source_identifier(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    settings = _settings(request)
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return peer[:64]

    trusted = any(
        peer_ip in ipaddress.ip_network(network, strict=False)
        for network in settings.trusted_proxies
    )
    if not trusted:
        return peer_ip.compressed

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded is None or len(forwarded) > 256:
        return peer_ip.compressed
    candidate = forwarded.split(",", maxsplit=1)[0].strip()
    try:
        return ipaddress.ip_address(candidate).compressed
    except ValueError:
        return peer_ip.compressed


def _authenticate(
    request: Request,
    raw_session: str | None,
) -> AuthenticatedSession:
    return _services(request).sessions.authenticate(raw_session)


def _auth_response(request: Request, authenticated: AuthenticatedSession) -> AuthResponse:
    return AuthResponse(
        request_id=_request_id(request),
        data=AuthData(
            user=AdminView(id=authenticated.user_id, username=authenticated.username),
            session=AuthSessionView(
                id=authenticated.session_id,
                expires_at=authenticated.expires_at,
            ),
            csrf_token=authenticated.csrf_token,
        ),
    )


@router.post("/login", response_model=AuthResponse)
async def login(request: Request, response: Response, payload: LoginRequest) -> AuthResponse:
    _validate_origin(request)
    issued = await _login_executor(request).login(
        username=payload.username,
        password=payload.password,
        source_identifier=_source_identifier(request),
        request_id=_request_id(request),
        client_label="web",
    )
    response.set_cookie(
        key=SESSION_COOKIE,
        value=issued.token,
        max_age=_settings(request).session_ttl,
        httponly=True,
        secure=_settings(request).cookie_secure,
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    authenticated = AuthenticatedSession(
        session_id=issued.session_id,
        user_id=issued.user_id,
        username=issued.username,
        expires_at=issued.expires_at,
        csrf_token=issued.csrf_token,
    )
    return _auth_response(request, authenticated)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None),
    x_csrf_token: str | None = Header(default=None),
) -> None:
    _validate_origin(request)
    authenticated = _authenticate(request, agentbox_session)
    _services(request).sessions.validate_csrf(authenticated, x_csrf_token)
    _services(request).sessions.revoke(authenticated, request_id=_request_id(request))
    response.delete_cookie(
        SESSION_COOKIE,
        httponly=True,
        secure=_settings(request).cookie_secure,
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


@router.get("/me", response_model=AuthResponse)
async def me(
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None),
) -> AuthResponse:
    authenticated = _authenticate(request, agentbox_session)
    response.headers["Cache-Control"] = "no-store"
    return _auth_response(request, authenticated)
