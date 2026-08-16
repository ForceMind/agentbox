"""Internal Control Plane service for read-only Runtime capability evidence."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Protocol

from agentbox_protocol.runtime_capabilities import (
    RUNTIME_CAPABILITY_CONTRACT_VERSION,
    RUNTIME_CAPABILITY_TTL_SECONDS,
    RuntimeCapabilityOutcome,
    RuntimeCapabilityReport,
    RuntimeCapabilitySet,
    RuntimeEvidenceLifecycle,
    expected_capability_names,
)
from agentbox_protocol.runtime_capabilities import (
    RuntimeType as WireRuntimeType,
)
from sqlalchemy.orm import Session

from agentbox_core.clock import Clock
from agentbox_core.database import Database
from agentbox_core.errors import (
    ProviderMetadataNotFound,
    RuntimeCapabilityEvidenceExpired,
    RuntimeCapabilityReportInvalid,
    RuntimeInstallationRevisionConflict,
)
from agentbox_core.provider_models import RuntimeInstallation, RuntimeType

_RUNTIME_INSTALLATION_ID = re.compile(r"rti_[0-9a-f]{32}")


class RuntimeCapabilityClient(Protocol):
    async def collect_capabilities(
        self,
        request_id: str,
        runtime_installation_id: str,
        runtime_installation_revision: int,
        runtime_type: WireRuntimeType,
        capability_set: RuntimeCapabilitySet,
    ) -> RuntimeCapabilityReport: ...


class AuditRecorder(Protocol):
    def record(
        self,
        session: Session,
        *,
        actor_type: str,
        actor_id: str | None,
        action: str,
        result: str,
        request_id: str | None,
        target_type: str | None = None,
        target_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> object: ...


class RuntimeCapabilityService:
    """Validate one registered Runtime around an exact fresh UDS collection."""

    def __init__(
        self,
        database: Database,
        clock: Clock,
        audit: AuditRecorder,
        *,
        codex_client: RuntimeCapabilityClient,
        claude_client: RuntimeCapabilityClient,
    ) -> None:
        self._database = database
        self._clock = clock
        self._audit = audit
        self._clients = {
            RuntimeType.CODEX: codex_client,
            RuntimeType.CLAUDE: claude_client,
        }

    async def collect(
        self,
        *,
        request_id: str,
        runtime_installation_id: str,
        runtime_installation_revision: int,
        actor_id: str | None = None,
    ) -> RuntimeCapabilityReport:
        if not _RUNTIME_INSTALLATION_ID.fullmatch(runtime_installation_id):
            raise ProviderMetadataNotFound()
        runtime = self._runtime(runtime_installation_id)
        if runtime.revision != runtime_installation_revision:
            raise RuntimeInstallationRevisionConflict()
        runtime_type = WireRuntimeType(runtime.runtime_type.value)
        capability_set = (
            RuntimeCapabilitySet.CODEX_PROVIDER_RUNTIME_V1
            if runtime.runtime_type is RuntimeType.CODEX
            else RuntimeCapabilitySet.CLAUDE_RUNTIME_SESSION_V1
        )
        report = await self._clients[runtime.runtime_type].collect_capabilities(
            request_id,
            runtime.id,
            runtime.revision,
            runtime_type,
            capability_set,
        )
        if (
            report.capability_contract_version != RUNTIME_CAPABILITY_CONTRACT_VERSION
            or report.runtime_installation_id != runtime.id
            or report.runtime_installation_revision != runtime.revision
            or report.runtime_type is not runtime_type
            or report.capability_set is not capability_set
        ):
            raise RuntimeCapabilityReportInvalid()
        expected_names = expected_capability_names(capability_set)
        if (
            tuple(observation.name for observation in report.observations) != expected_names
            or report.expires_at - report.observed_at
            != timedelta(seconds=RUNTIME_CAPABILITY_TTL_SECONDS)
            or any(
                observation.observed_at != report.observed_at
                or observation.expires_at != report.expires_at
                for observation in report.observations
            )
        ):
            raise RuntimeCapabilityReportInvalid()
        now = self._utc(self._clock.now())
        if report.observed_at > now:
            raise RuntimeCapabilityReportInvalid()
        if now >= report.expires_at:
            raise RuntimeCapabilityEvidenceExpired()

        with self._database.transaction() as session:
            current = session.get(RuntimeInstallation, runtime.id)
            if (
                current is None
                or current.revision != runtime.revision
                or current.runtime_type is not runtime.runtime_type
            ):
                raise RuntimeInstallationRevisionConflict()
            supported_count = sum(
                observation.outcome is RuntimeCapabilityOutcome.SUPPORTED
                for observation in report.observations
            )
            unknown_count = sum(
                observation.outcome is RuntimeCapabilityOutcome.UNKNOWN
                for observation in report.observations
            )
            self._audit.record(
                session,
                actor_type="control_plane",
                actor_id=actor_id,
                action="runtime_capabilities.collected",
                result="succeeded",
                request_id=request_id,
                target_type="runtime_installation",
                target_id=runtime.id,
                metadata={
                    "runtime_type": runtime.runtime_type.value,
                    "runtime_revision": runtime.revision,
                    "capability_set": capability_set.value,
                    "contract_version": report.capability_contract_version,
                    "adapter_schema_version": report.adapter_schema_version,
                    "collection_state": report.collection_state.value,
                    "capability_count": len(report.observations),
                    "supported_count": supported_count,
                    "unknown_count": unknown_count,
                    "expired": any(
                        observation.lifecycle is RuntimeEvidenceLifecycle.EXPIRED
                        for observation in report.observations
                    ),
                },
            )
        return report

    def _runtime(self, runtime_installation_id: str) -> RuntimeInstallation:
        with self._database.transaction() as session:
            runtime = session.get(RuntimeInstallation, runtime_installation_id)
            if runtime is None:
                raise ProviderMetadataNotFound()
            session.expunge(runtime)
            return runtime

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
