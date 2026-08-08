"""Minimal FastAPI application for engineering-skeleton validation."""

from agentbox_core import __version__
from agentbox_protocol import HealthResponse, MetaResponse
from fastapi import FastAPI

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787


def create_app() -> FastAPI:
    """Create the Phase 2 application with no product routes."""
    application = FastAPI(
        title="AgentBox",
        version=__version__,
        description="AgentBox engineering skeleton",
    )

    @application.get("/healthz", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse()

    @application.get("/api/v1/meta", response_model=MetaResponse, tags=["system"])
    async def metadata() -> MetaResponse:
        return MetaResponse(version=__version__)

    return application


app = create_app()


def run() -> None:
    """Run the development server on the architecture-approved loopback address."""
    import uvicorn

    uvicorn.run("agentbox_api.main:app", host=DEFAULT_HOST, port=DEFAULT_PORT)
