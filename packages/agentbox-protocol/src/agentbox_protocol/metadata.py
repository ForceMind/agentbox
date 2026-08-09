"""Safe control-plane liveness and metadata response contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Minimal liveness response."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = "ok"


class MetaResponse(BaseModel):
    """Build and API-version metadata."""

    model_config = ConfigDict(extra="forbid")

    name: Literal["AgentBox"] = "AgentBox"
    version: str
    api_version: Literal["v1"] = "v1"
    environment: Literal["development", "test", "production"]
