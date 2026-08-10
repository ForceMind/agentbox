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


class ClaudeDoctorSummary(StrictMetadataModel):
    installed: bool | None
    version: str | None
    authentication: Literal["authenticated", "unauthenticated", "unknown"]
    remote_control: Literal["supported", "unsupported", "unknown"]
    tmux_installed: bool | None
    tmux_version: str | None
    managed_sessions: int
    unmanaged_sessions: int
    workspace_interaction_warnings: int
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
    claude: ClaudeDoctorSummary


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
    remote_confidence: Literal["reported", "inferred", "unknown"]
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


class ClaudeCapabilityView(StrictMetadataModel):
    remote_control: Literal["supported", "unsupported", "unknown"]
    remote_start: Literal["supported", "unsupported", "unknown"]
    version: Literal["supported", "unsupported", "unknown"]


class ClaudeDiagnosticView(StrictMetadataModel):
    code: str
    severity: Literal["critical", "high", "medium", "low", "warning", "info"]
    summary: str
    remediation: str | None = None


class ClaudeStatusData(StrictMetadataModel):
    installed: bool
    version: str | None
    authentication: Literal["authenticated", "unauthenticated", "unknown"]
    capabilities: ClaudeCapabilityView
    tmux_installed: bool
    tmux_version: str | None
    managed_sessions: int
    unmanaged_sessions: int
    workspace_interaction_warnings: int
    diagnostics: list[ClaudeDiagnosticView]


class ClaudeStatusResponse(StrictMetadataModel):
    api_version: Literal["v1"] = "v1"
    request_id: str
    data: ClaudeStatusData


class ClaudeSessionData(StrictMetadataModel):
    project_id: str
    display_name: str
    state: Literal["running", "stopped", "starting", "needs_interaction", "broken", "unknown"]
    managed: bool
    session_name: str
    attach_command: str
    workspace_state: Literal["unknown", "requires_user_confirmation", "initialized_by_agentbox"]
    tmux_running: bool
    remote_readiness: Literal["ready", "unknown"]


class ClaudeSessionResponse(StrictMetadataModel):
    api_version: Literal["v1"] = "v1"
    request_id: str
    data: ClaudeSessionData


class ClaudeSessionListData(StrictMetadataModel):
    sessions: list[ClaudeSessionData]


class ClaudeSessionListResponse(StrictMetadataModel):
    api_version: Literal["v1"] = "v1"
    request_id: str
    data: ClaudeSessionListData


class ClaudeSessionActionData(StrictMetadataModel):
    outcome: Literal["started", "stopped", "already_running", "already_stopped"]
    session: ClaudeSessionData


class ClaudeSessionActionResponse(StrictMetadataModel):
    api_version: Literal["v1"] = "v1"
    request_id: str
    data: ClaudeSessionActionData


class ClaudeSessionOutputData(StrictMetadataModel):
    project_id: str
    session_name: str
    output: str
    truncated: bool
    sensitive: Literal[True] = True


class ClaudeSessionOutputResponse(StrictMetadataModel):
    api_version: Literal["v1"] = "v1"
    request_id: str
    data: ClaudeSessionOutputData
