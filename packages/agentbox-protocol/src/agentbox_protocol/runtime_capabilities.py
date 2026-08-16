"""Strict read-only Runtime capability wire contract for Phase 11 Slice 2."""

from __future__ import annotations

import re
from datetime import timedelta
from enum import StrEnum
from typing import Final, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

RUNTIME_CAPABILITY_ACTION: Final[Literal["runtime.capabilities.query"]] = (
    "runtime.capabilities.query"
)
RUNTIME_CAPABILITY_CONTRACT_VERSION: Final[Literal[1]] = 1
RUNTIME_CAPABILITY_TTL_SECONDS = 60
MAX_CAPABILITY_FINDINGS = 32
MAX_CAPABILITY_DEPENDENCIES = 4

_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")
_RUNTIME_INSTALLATION_ID = re.compile(r"rti_[0-9a-f]{32}")
_SAFE_VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}")


class RuntimeType(StrEnum):
    CODEX = "codex"
    CLAUDE = "claude"


class RuntimeCapabilitySet(StrEnum):
    CODEX_PROVIDER_RUNTIME_V1 = "codex_provider_runtime_v1"
    CLAUDE_RUNTIME_SESSION_V1 = "claude_runtime_session_v1"


class RuntimeCapabilityRefreshPolicy(StrEnum):
    FORCE_FRESH_READ_ONLY = "force_fresh_read_only"


class RuntimeAdapterID(StrEnum):
    CODEX_RUNTIME_ADAPTER_V1 = "codex_runtime_adapter_v1"
    CLAUDE_RUNTIME_ADAPTER_V1 = "claude_runtime_adapter_v1"


class RuntimeCapabilityCollectionState(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    ADAPTER_UNAVAILABLE = "adapter_unavailable"
    BROKEN = "broken"
    UNKNOWN = "unknown"


class RuntimeInstallationType(StrEnum):
    STANDALONE = "standalone"
    NPM = "npm"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class RuntimeAuthenticationState(StrEnum):
    AUTHENTICATED = "authenticated"
    UNAUTHENTICATED = "unauthenticated"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class RuntimeRemoteState(StrEnum):
    RUNNING = "running"
    STOPPED = "stopped"
    BROKEN = "broken"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class RuntimeConfigOwnershipState(StrEnum):
    UNMANAGED = "unmanaged"
    MANAGED = "managed"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class RuntimeCapabilityOutcome(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"
    UNAUTHENTICATED = "unauthenticated"
    BROKEN = "broken"
    UNKNOWN = "unknown"


class RuntimeEvidenceLifecycle(StrEnum):
    UNKNOWN = "unknown"
    DETECTED = "detected"
    VALIDATED = "validated"
    EXPIRED = "expired"


class RuntimeEvidenceClass(StrEnum):
    PUBLIC_VERSION = "public_version"
    PUBLIC_HELP = "public_help"
    PUBLIC_STATUS = "public_status"
    AGENTBOX_MANAGED_STATE = "agentbox_managed_state"
    AGENTBOX_BUILD = "agentbox_build"
    QUALIFIED_PUBLIC_CONTRACT = "qualified_public_contract"
    NO_ACCEPTABLE_EVIDENCE = "no_acceptable_evidence"


class RuntimeCapabilityFindingCode(StrEnum):
    RUNTIME_NOT_INSTALLED = "RUNTIME_NOT_INSTALLED"
    VERSION_UNAVAILABLE = "VERSION_UNAVAILABLE"
    INSTALLATION_CONFLICT = "INSTALLATION_CONFLICT"
    PUBLIC_CONTRACT_UNQUALIFIED = "PUBLIC_CONTRACT_UNQUALIFIED"
    ADAPTER_NOT_IMPLEMENTED = "ADAPTER_NOT_IMPLEMENTED"
    AUTH_STATUS_UNAVAILABLE = "AUTH_STATUS_UNAVAILABLE"
    REMOTE_STATUS_UNAVAILABLE = "REMOTE_STATUS_UNAVAILABLE"
    CONFIG_OWNERSHIP_NOT_IMPLEMENTED = "CONFIG_OWNERSHIP_NOT_IMPLEMENTED"
    MANAGED_SESSION_EVIDENCE_UNAVAILABLE = "MANAGED_SESSION_EVIDENCE_UNAVAILABLE"
    PROBE_TIMEOUT = "PROBE_TIMEOUT"
    PROBE_OUTPUT_INVALID = "PROBE_OUTPUT_INVALID"
    PROBE_OUTPUT_TOO_LARGE = "PROBE_OUTPUT_TOO_LARGE"
    RUNTIME_MANAGER_UNAVAILABLE = "RUNTIME_MANAGER_UNAVAILABLE"
    TMUX_UNAVAILABLE = "TMUX_UNAVAILABLE"


class RuntimeCapabilityName(StrEnum):
    CODEX_INSTALLED = "codex.installed"
    CODEX_VERSION_DETECTABLE = "codex.version.detectable"
    CODEX_INSTALLATION_CLASSIFIABLE = "codex.installation.classifiable"
    CODEX_AUTHENTICATION_OBSERVABLE = "codex.authentication.observable"
    CODEX_REMOTE_CONTROL_AVAILABLE = "codex.remote_control.available"
    CODEX_REMOTE_START = "codex.remote.start"
    CODEX_REMOTE_STOP = "codex.remote.stop"
    CODEX_REMOTE_PAIR = "codex.remote.pair"
    CODEX_REMOTE_STATUS = "codex.remote.status"
    CODEX_PROVIDER_ADAPTER_AVAILABLE = "codex.provider_adapter.available"
    CODEX_PROVIDER_PROFILE_VALIDATE = "codex.provider_profile.validate"
    CODEX_CONFIG_OWNERSHIP_OBSERVE = "codex.config_ownership.observe"
    CODEX_ACTIVE_WRITER_OBSERVE = "codex.active_writer.observe"
    CODEX_SESSION_RESUME_OBSERVE = "codex.session.resume.observe"
    CODEX_SESSION_DISCOVERY_OBSERVE = "codex.session.discovery.observe"
    CLAUDE_INSTALLED = "claude.installed"
    CLAUDE_VERSION_DETECTABLE = "claude.version.detectable"
    CLAUDE_AUTHENTICATION_OBSERVABLE = "claude.authentication.observable"
    CLAUDE_REMOTE_CONTROL_AVAILABLE = "claude.remote_control.available"
    CLAUDE_REMOTE_START = "claude.remote.start"
    TMUX_AVAILABLE = "tmux.available"
    CLAUDE_SESSION_INSPECT_MANAGED = "claude.session.inspect_managed"


CODEX_CAPABILITY_NAMES = (
    RuntimeCapabilityName.CODEX_INSTALLED,
    RuntimeCapabilityName.CODEX_VERSION_DETECTABLE,
    RuntimeCapabilityName.CODEX_INSTALLATION_CLASSIFIABLE,
    RuntimeCapabilityName.CODEX_AUTHENTICATION_OBSERVABLE,
    RuntimeCapabilityName.CODEX_REMOTE_CONTROL_AVAILABLE,
    RuntimeCapabilityName.CODEX_REMOTE_START,
    RuntimeCapabilityName.CODEX_REMOTE_STOP,
    RuntimeCapabilityName.CODEX_REMOTE_PAIR,
    RuntimeCapabilityName.CODEX_REMOTE_STATUS,
    RuntimeCapabilityName.CODEX_PROVIDER_ADAPTER_AVAILABLE,
    RuntimeCapabilityName.CODEX_PROVIDER_PROFILE_VALIDATE,
    RuntimeCapabilityName.CODEX_CONFIG_OWNERSHIP_OBSERVE,
    RuntimeCapabilityName.CODEX_ACTIVE_WRITER_OBSERVE,
    RuntimeCapabilityName.CODEX_SESSION_RESUME_OBSERVE,
    RuntimeCapabilityName.CODEX_SESSION_DISCOVERY_OBSERVE,
)

CLAUDE_CAPABILITY_NAMES = (
    RuntimeCapabilityName.CLAUDE_INSTALLED,
    RuntimeCapabilityName.CLAUDE_VERSION_DETECTABLE,
    RuntimeCapabilityName.CLAUDE_AUTHENTICATION_OBSERVABLE,
    RuntimeCapabilityName.CLAUDE_REMOTE_CONTROL_AVAILABLE,
    RuntimeCapabilityName.CLAUDE_REMOTE_START,
    RuntimeCapabilityName.TMUX_AVAILABLE,
    RuntimeCapabilityName.CLAUDE_SESSION_INSPECT_MANAGED,
)


def expected_capability_names(
    capability_set: RuntimeCapabilitySet,
) -> tuple[RuntimeCapabilityName, ...]:
    if capability_set is RuntimeCapabilitySet.CODEX_PROVIDER_RUNTIME_V1:
        return CODEX_CAPABILITY_NAMES
    return CLAUDE_CAPABILITY_NAMES


class StrictRuntimeCapabilityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class RuntimeCapabilityQuery(StrictRuntimeCapabilityModel):
    protocol_version: Literal[1] = 1
    action: Literal["runtime.capabilities.query"] = RUNTIME_CAPABILITY_ACTION
    request_id: str = Field(min_length=1, max_length=64)
    capability_contract_version: Literal[1] = RUNTIME_CAPABILITY_CONTRACT_VERSION
    runtime_installation_id: str = Field(min_length=36, max_length=36)
    runtime_installation_revision: int = Field(ge=1)
    runtime_type: RuntimeType
    capability_set: RuntimeCapabilitySet
    refresh_policy: RuntimeCapabilityRefreshPolicy

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, value: str) -> str:
        if not _REQUEST_ID.fullmatch(value):
            raise ValueError("request_id is invalid")
        return value

    @field_validator("runtime_installation_id")
    @classmethod
    def validate_runtime_installation_id(cls, value: str) -> str:
        if not _RUNTIME_INSTALLATION_ID.fullmatch(value):
            raise ValueError("runtime_installation_id is invalid")
        return value

    @model_validator(mode="after")
    def validate_runtime_capability_set(self) -> Self:
        expected = (
            RuntimeCapabilitySet.CODEX_PROVIDER_RUNTIME_V1
            if self.runtime_type is RuntimeType.CODEX
            else RuntimeCapabilitySet.CLAUDE_RUNTIME_SESSION_V1
        )
        if self.capability_set is not expected:
            raise ValueError("runtime_type and capability_set do not match")
        return self


class RuntimeCapabilityObservation(StrictRuntimeCapabilityModel):
    name: RuntimeCapabilityName
    outcome: RuntimeCapabilityOutcome
    lifecycle: RuntimeEvidenceLifecycle
    evidence_class: RuntimeEvidenceClass
    finding_code: RuntimeCapabilityFindingCode | None = None
    dependencies: tuple[RuntimeCapabilityName, ...] = Field(
        default=(), max_length=MAX_CAPABILITY_DEPENDENCIES
    )
    observed_at: AwareDatetime
    expires_at: AwareDatetime

    @field_validator("observed_at", "expires_at")
    @classmethod
    def validate_utc_timestamp(cls, value: AwareDatetime) -> AwareDatetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("capability timestamps must be UTC")
        return value

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        if self.expires_at - self.observed_at != timedelta(seconds=RUNTIME_CAPABILITY_TTL_SECONDS):
            raise ValueError("capability observation TTL is invalid")
        if len(set(self.dependencies)) != len(self.dependencies) or self.name in self.dependencies:
            raise ValueError("capability dependencies are invalid")
        return self


class RuntimeCapabilityReport(StrictRuntimeCapabilityModel):
    capability_contract_version: Literal[1] = RUNTIME_CAPABILITY_CONTRACT_VERSION
    runtime_installation_id: str = Field(min_length=36, max_length=36)
    runtime_installation_revision: int = Field(ge=1)
    runtime_type: RuntimeType
    capability_set: RuntimeCapabilitySet
    adapter_id: RuntimeAdapterID
    adapter_schema_version: Literal[1] = 1
    collection_state: RuntimeCapabilityCollectionState
    runtime_version: str | None = Field(default=None, max_length=64)
    installation_type: RuntimeInstallationType
    authentication_state: RuntimeAuthenticationState
    remote_state: RuntimeRemoteState
    config_ownership_state: RuntimeConfigOwnershipState
    managed_session_count: int | None = Field(default=None, ge=0, le=10_000)
    observed_at: AwareDatetime
    expires_at: AwareDatetime
    observations: tuple[RuntimeCapabilityObservation, ...] = Field(min_length=7, max_length=15)
    findings: tuple[RuntimeCapabilityFindingCode, ...] = Field(
        default=(), max_length=MAX_CAPABILITY_FINDINGS
    )

    @field_validator("runtime_installation_id")
    @classmethod
    def validate_runtime_installation_id(cls, value: str) -> str:
        if not _RUNTIME_INSTALLATION_ID.fullmatch(value):
            raise ValueError("runtime_installation_id is invalid")
        return value

    @field_validator("runtime_version")
    @classmethod
    def validate_runtime_version(cls, value: str | None) -> str | None:
        if value is not None and not _SAFE_VERSION.fullmatch(value):
            raise ValueError("runtime_version is invalid")
        return value

    @field_validator("observed_at", "expires_at")
    @classmethod
    def validate_utc_timestamp(cls, value: AwareDatetime) -> AwareDatetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("capability timestamps must be UTC")
        return value

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        expected_set = (
            RuntimeCapabilitySet.CODEX_PROVIDER_RUNTIME_V1
            if self.runtime_type is RuntimeType.CODEX
            else RuntimeCapabilitySet.CLAUDE_RUNTIME_SESSION_V1
        )
        expected_adapter = (
            RuntimeAdapterID.CODEX_RUNTIME_ADAPTER_V1
            if self.runtime_type is RuntimeType.CODEX
            else RuntimeAdapterID.CLAUDE_RUNTIME_ADAPTER_V1
        )
        if self.capability_set is not expected_set or self.adapter_id is not expected_adapter:
            raise ValueError("report Runtime identity does not match its contract")
        if self.expires_at - self.observed_at != timedelta(seconds=RUNTIME_CAPABILITY_TTL_SECONDS):
            raise ValueError("capability report TTL is invalid")
        expected_names = expected_capability_names(self.capability_set)
        actual_names = tuple(observation.name for observation in self.observations)
        if actual_names != expected_names:
            raise ValueError("capability observations are incomplete or out of order")
        expected_name_set = frozenset(expected_names)
        for observation in self.observations:
            if (
                observation.observed_at != self.observed_at
                or observation.expires_at != self.expires_at
            ):
                raise ValueError("capability timestamps do not match the report")
            if not frozenset(observation.dependencies).issubset(expected_name_set):
                raise ValueError("capability dependency is outside the capability set")
        expected_findings = tuple(
            dict.fromkeys(
                observation.finding_code
                for observation in self.observations
                if observation.finding_code is not None
            )
        )
        if self.findings != expected_findings or len(set(self.findings)) != len(self.findings):
            raise ValueError("report findings are inconsistent")
        if self.runtime_type is RuntimeType.CODEX and self.managed_session_count is not None:
            raise ValueError("Codex capability reports cannot expose a managed session count")
        if (
            self.runtime_type is RuntimeType.CLAUDE
            and self.config_ownership_state is not RuntimeConfigOwnershipState.NOT_APPLICABLE
        ):
            raise ValueError("Claude config ownership is not a Provider capability")
        return self
