"""Cookie-authenticated Phase 3 API routes."""

from __future__ import annotations

import asyncio
import ipaddress
from collections.abc import Callable, Coroutine
from contextvars import copy_context
from functools import partial
from typing import cast
from urllib.parse import urlsplit

from agentbox_core.configuration import Settings
from agentbox_core.errors import InvalidOrigin, InvalidSession, ReauthenticationInvalidSession
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
    ReauthenticateRequest,
)
from fastapi import APIRouter, Cookie, Header, Request, Response

SESSION_COOKIE = "agentbox_session"
router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


class BoundedLoginExecutor:
    """Keep synchronous login/Argon2 work off-loop with bounded admission."""

    def __init__(self, auth_service: AuthService, *, max_concurrency: int) -> None:
        self._auth_service = auth_service
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._workers: set[asyncio.Future[IssuedSession]] = set()
        self._closing = False
        self._closed = False
        self._close_task: asyncio.Task[None] | None = None

    @property
    def shutdown_clean(self) -> bool:
        operation = self._close_task
        return (
            self._closed
            and not self._workers
            and operation is not None
            and operation.done()
            and not operation.cancelled()
            and operation.exception() is None
        )

    async def _run(self, operation: Callable[[], IssuedSession]) -> IssuedSession:
        # Admit before submitting to the default pool; queued requests remain
        # coroutines. Copy the caller context just as asyncio.to_thread does.
        if self._closing or self._closed:
            raise RuntimeError("login executor is closed")
        await self._semaphore.acquire()
        try:
            if self._closing or self._closed:
                raise RuntimeError("login executor is closed")
            loop = asyncio.get_running_loop()
            completed: asyncio.Future[None] = loop.create_future()
            worker = loop.run_in_executor(None, copy_context().run, operation)
        except BaseException:
            self._semaphore.release()
            raise
        self._workers.add(worker)
        worker.add_done_callback(partial(self._worker_finished, completed=completed))
        # Cancelling a request cannot stop an already running thread. Keep its
        # capacity until the executor Future completes, without delaying cancel.
        # Shield a non-raising completion signal: Python 3.14 otherwise logs
        # late worker exceptions even when our callback already retrieved them.
        await asyncio.shield(completed)
        return worker.result()

    def close(self) -> Coroutine[object, object, None]:
        self._closing = True
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._perform_close())
        return self._await_close(self._close_task)

    async def _perform_close(self) -> None:
        while self._workers:
            await asyncio.gather(*tuple(self._workers), return_exceptions=True)
        self._closed = True

    async def _await_close(self, operation: asyncio.Task[None]) -> None:
        interrupted = False
        while True:
            try:
                await asyncio.shield(operation)
                break
            except asyncio.CancelledError:
                if operation.cancelled():
                    raise
                interrupted = True
        if interrupted:
            raise asyncio.CancelledError

    def _worker_finished(
        self, worker: asyncio.Future[IssuedSession], *, completed: asyncio.Future[None]
    ) -> None:
        self._workers.discard(worker)
        self._semaphore.release()
        if not worker.cancelled():
            # Retrieve errors even when the caller has gone away. Awaiting
            # callers still receive the same exception from worker.result().
            worker.exception()
        completed.set_result(None)

    async def login(
        self,
        *,
        username: str,
        password: str,
        source_identifier: str,
        request_id: str | None,
        client_label: str | None,
    ) -> IssuedSession:
        return await self._run(
            partial(
                self._auth_service.login,
                username=username,
                password=password,
                source_identifier=source_identifier,
                request_id=request_id,
                client_label=client_label,
            )
        )

    async def reauthenticate(
        self,
        authenticated: AuthenticatedSession,
        *,
        password: str,
        source_identifier: str,
        request_id: str | None,
    ) -> IssuedSession:
        return await self._run(
            partial(
                self._auth_service.reauthenticate,
                authenticated,
                password=password,
                source_identifier=source_identifier,
                request_id=request_id,
            )
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


def authenticate_request(
    request: Request,
    raw_session: str | None,
) -> AuthenticatedSession:
    """Authenticate a cookie for another versioned control-plane route."""
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
        authenticated_at=issued.authenticated_at,
        auth_epoch=issued.auth_epoch,
        csrf_token=issued.csrf_token,
    )
    return _auth_response(request, authenticated)


@router.post("/reauthenticate", response_model=AuthResponse)
async def reauthenticate(
    request: Request,
    response: Response,
    payload: ReauthenticateRequest,
    agentbox_session: str | None = Cookie(default=None),
    x_csrf_token: str | None = Header(default=None),
) -> AuthResponse:
    _validate_origin(request)
    try:
        authenticated = authenticate_request(request, agentbox_session)
    except InvalidSession as exc:
        raise ReauthenticationInvalidSession() from exc
    _services(request).sessions.validate_csrf(authenticated, x_csrf_token)
    issued = await _login_executor(request).reauthenticate(
        authenticated,
        password=payload.password,
        source_identifier=_source_identifier(request),
        request_id=_request_id(request),
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
    return _auth_response(
        request,
        AuthenticatedSession(
            session_id=issued.session_id,
            user_id=issued.user_id,
            username=issued.username,
            expires_at=issued.expires_at,
            authenticated_at=issued.authenticated_at,
            auth_epoch=issued.auth_epoch,
            csrf_token=issued.csrf_token,
        ),
    )


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None),
    x_csrf_token: str | None = Header(default=None),
) -> None:
    _validate_origin(request)
    authenticated = authenticate_request(request, agentbox_session)
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
    authenticated = authenticate_request(request, agentbox_session)
    response.headers["Cache-Control"] = "no-store"
    return _auth_response(request, authenticated)
