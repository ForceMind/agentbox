"""AgentBox authenticated control plane with capability-aware Runtime access."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from agentbox_core import __version__
from agentbox_core.configuration import Settings
from agentbox_core.errors import AgentBoxError
from agentbox_core.logging import configure_logging, log_event
from agentbox_core.services import ControlPlaneServices, build_services
from agentbox_protocol import (
    ErrorBody,
    ErrorResponse,
    HealthResponse,
    MetaResponse,
    ReadinessResponse,
)
from agentbox_runtime import (
    ClaudeRuntimeClient,
    CodexRuntimeClient,
    ProjectRuntimeClient,
    UnixClaudeRuntimeClient,
    UnixCodexRuntimeClient,
    UnixProjectRuntimeClient,
)
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from agentbox_api.auth import BoundedLoginExecutor
from agentbox_api.auth import router as auth_router
from agentbox_api.claude import router as claude_router
from agentbox_api.codex import router as codex_router
from agentbox_api.doctor import router as doctor_router
from agentbox_api.jobs import router as jobs_router
from agentbox_api.middleware import ControlPlaneHttpMiddleware
from agentbox_api.projects import github_router
from agentbox_api.projects import router as projects_router

logger = logging.getLogger("agentbox.api")


class ImmutableStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "req_unknown"))


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    category: str,
    message: str,
    retryable: bool = False,
    details: dict[str, object] | None = None,
    retry_after: int | None = None,
) -> JSONResponse:
    envelope = ErrorResponse(
        request_id=_request_id(request),
        error=ErrorBody(
            code=code,
            category=category,
            message=message,
            retryable=retryable,
            details=details or {},
        ),
    )
    headers = {"Cache-Control": "no-store"}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
        headers=headers,
    )


def create_app(
    settings: Settings | None = None,
    services: ControlPlaneServices | None = None,
    codex_runtime: CodexRuntimeClient | None = None,
    claude_runtime: ClaudeRuntimeClient | None = None,
    project_runtime: ProjectRuntimeClient | None = None,
) -> FastAPI:
    """Build the API without applying schema migrations or system changes."""
    actual_settings = settings or Settings()
    actual_services = services or build_services(actual_settings)
    actual_codex_runtime = codex_runtime or UnixCodexRuntimeClient(actual_settings.runtime_socket)
    actual_claude_runtime = claude_runtime or UnixClaudeRuntimeClient(
        actual_settings.runtime_socket
    )
    actual_project_runtime = project_runtime or UnixProjectRuntimeClient(
        actual_settings.runtime_socket
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        del application
        log_event(logger, logging.INFO, "api_started", "Control plane API started")
        try:
            yield
        finally:
            actual_services.database.close()
            log_event(logger, logging.INFO, "api_stopped", "Control plane API stopped")

    application = FastAPI(
        title="AgentBox",
        version=__version__,
        description="AgentBox capability-aware control plane",
        lifespan=lifespan,
        debug=False,
    )
    application.state.settings = actual_settings
    application.state.services = actual_services
    application.state.codex_runtime = actual_codex_runtime
    application.state.claude_runtime = actual_claude_runtime
    application.state.project_runtime = actual_project_runtime
    application.state.login_executor = BoundedLoginExecutor(
        actual_services.auth,
        max_concurrency=actual_settings.argon2_max_concurrency,
    )
    application.add_middleware(
        ControlPlaneHttpMiddleware,
        max_body_bytes=actual_settings.request_body_limit,
    )

    @application.exception_handler(AgentBoxError)
    async def handle_agentbox_error(request: Request, exc: AgentBoxError) -> JSONResponse:
        return _error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            category=exc.category,
            message=exc.message,
            retryable=exc.retryable,
            retry_after=exc.retry_after,
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        fields = [
            {
                "field": ".".join(str(part) for part in error["loc"] if part != "body")[:128],
                "type": str(error["type"])[:64],
            }
            for error in exc.errors()[:16]
        ]
        return _error_response(
            request,
            status_code=422,
            code="REQUEST_VALIDATION_FAILED",
            category="validation",
            message="Request validation failed",
            details={"fields": fields},
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        del exc
        logger.error(
            "Unhandled API exception",
            extra={"event": "unhandled_exception", "request_id": _request_id(request)},
        )
        return _error_response(
            request,
            status_code=500,
            code="INTERNAL_ERROR",
            category="internal",
            message="The request could not be completed",
        )

    @application.get("/healthz", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse()

    @application.get("/readyz", response_model=ReadinessResponse, tags=["system"])
    async def readiness() -> JSONResponse | ReadinessResponse:
        checks = {
            "database": actual_services.database.check_connection(),
            "migrations": actual_services.database.migrations_current(),
        }
        ready = all(checks.values())
        payload = ReadinessResponse(status="ready" if ready else "not_ready", checks=checks)
        if ready:
            return payload
        return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))

    @application.get("/api/v1/meta", response_model=MetaResponse, tags=["system"])
    async def metadata() -> MetaResponse:
        return MetaResponse(version=__version__, environment=actual_settings.env.value)

    application.include_router(auth_router)
    application.include_router(codex_router)
    application.include_router(claude_router)
    application.include_router(projects_router)
    application.include_router(github_router)
    application.include_router(jobs_router)
    application.include_router(doctor_router)
    static_root = actual_settings.static_dir
    if static_root is not None:
        _register_static_web(application, static_root)
    return application


def _register_static_web(application: FastAPI, static_root: Path) -> None:
    """Serve one immutable frontend artifact without exposing other filesystem roots."""
    root = static_root.resolve(strict=True)
    if static_root.is_symlink() or not root.is_dir() or not (root / "index.html").is_file():
        raise RuntimeError("configured frontend artifact is unavailable or unsafe")
    assets = root / "assets"
    if assets.is_dir() and not assets.is_symlink():
        application.mount("/assets", ImmutableStaticFiles(directory=assets), name="frontend-assets")

    @application.get("/{frontend_path:path}", include_in_schema=False)
    async def frontend(frontend_path: str) -> FileResponse:
        if frontend_path.startswith(("api/", "healthz/", "readyz/")):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = root / frontend_path
        try:
            resolved = candidate.resolve(strict=True)
        except (FileNotFoundError, OSError):
            resolved = root / "index.html"
        if not resolved.is_relative_to(root) or resolved.is_symlink() or not resolved.is_file():
            resolved = root / "index.html"
        return FileResponse(
            resolved,
            headers={
                "Cache-Control": (
                    "no-cache"
                    if resolved.name == "index.html"
                    else "public, max-age=31536000, immutable"
                )
            },
        )


app = create_app()


def run() -> None:
    """Run a foreground development server on the configured loopback address."""
    import uvicorn

    configure_logging()
    settings = Settings()
    uvicorn.run(
        create_app(settings),
        host=settings.bind_host,
        port=settings.bind_port,
        access_log=False,
    )
