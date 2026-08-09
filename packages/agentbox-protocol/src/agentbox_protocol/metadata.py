"""Safe control-plane liveness, metadata, and diagnostic contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class StrictMetadataModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(StrictMetadataModel):
    """Minimal liveness response."""

    status: Literal["ok"] = "ok"


class MetaResponse(StrictMetadataModel):
    """Build and API-version metadata."""

    name: Literal["AgentBox"] = "AgentBox"
    version: str
    api_version: Literal["v1"] = "v1"
    environment: Literal["development", "test", "production"]


class DoctorChecks(StrictMetadataModel):
    configuration_valid: bool
    database_reachable: bool
    migrations_current: bool
    admin_initialized: bool
    control_plane_ready: bool


class DoctorPolicy(StrictMetadataModel):
    environment: Literal["development", "test", "production"]
    bind_host: str
    bind_port: int
    session_ttl_seconds: int
    session_idle_ttl_seconds: int
    login_rate_limit: int
    login_rate_window_seconds: int
    login_lock_duration_seconds: int


class DoctorData(StrictMetadataModel):
    status: Literal["ready", "not_ready"]
    checks: DoctorChecks
    policy: DoctorPolicy


class DoctorResponse(StrictMetadataModel):
    api_version: Literal["v1"] = "v1"
    request_id: str
    data: DoctorData
