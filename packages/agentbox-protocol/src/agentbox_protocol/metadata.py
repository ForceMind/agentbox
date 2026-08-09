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


class CodexDoctorSummary(StrictMetadataModel):
    installed: bool | None
    version: str | None
    installation_type: Literal["standalone", "npm", "conflict", "unknown"]
    remote_control: Literal["supported", "unsupported", "unknown"]
    remote_state: Literal["running", "stopped", "broken", "unknown"]
    findings: list[str]


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
    codex: CodexDoctorSummary


class DoctorResponse(StrictMetadataModel):
    api_version: Literal["v1"] = "v1"
    request_id: str
    data: DoctorData


class CodexCapabilityView(StrictMetadataModel):
    remote_control: Literal["supported", "unsupported", "unknown"]
    start: Literal["supported", "unsupported", "unknown"]
    stop: Literal["supported", "unsupported", "unknown"]
    pair: Literal["supported", "unsupported", "unknown"]
    status: Literal["supported", "unsupported", "unknown"]


class CodexDiagnosticView(StrictMetadataModel):
    code: str
    severity: Literal["critical", "high", "medium", "low", "warning", "info"]
    summary: str
    remediation: str | None = None


class CodexStatusData(StrictMetadataModel):
    installed: bool
    version: str | None
    selected_executable: str | None
    alternatives: list[str]
    installation_type: Literal["standalone", "npm", "conflict", "unknown"]
    conflict_detected: bool
    authentication: Literal["authenticated", "unauthenticated", "unknown"]
    capabilities: CodexCapabilityView
    remote_state: Literal["running", "stopped", "broken", "unknown"]
    remote_confidence: Literal["reported", "inferred", "agentbox_observed", "unknown"]
    diagnostics: list[CodexDiagnosticView]


class CodexStatusResponse(StrictMetadataModel):
    api_version: Literal["v1"] = "v1"
    request_id: str
    data: CodexStatusData


class CodexRemoteActionData(StrictMetadataModel):
    outcome: Literal["started", "stopped", "already_running", "already_stopped"]
    remote_state: Literal["running", "stopped", "broken", "unknown"]


class CodexRemoteActionResponse(StrictMetadataModel):
    api_version: Literal["v1"] = "v1"
    request_id: str
    data: CodexRemoteActionData


class CodexPairData(StrictMetadataModel):
    pair_code: str
    expires_at: str | None
    display_once: Literal[True] = True


class CodexPairResponse(StrictMetadataModel):
    api_version: Literal["v1"] = "v1"
    request_id: str
    data: CodexPairData
