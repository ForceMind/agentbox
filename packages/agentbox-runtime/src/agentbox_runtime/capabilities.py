"""Read-only Runtime capability collection over existing bounded adapters."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from agentbox_protocol.runtime_capabilities import (
    CLAUDE_CAPABILITY_NAMES,
    CODEX_CAPABILITY_NAMES,
    RUNTIME_CAPABILITY_TTL_SECONDS,
    RuntimeAdapterID,
    RuntimeAuthenticationState,
    RuntimeCapabilityCollectionState,
    RuntimeCapabilityFindingCode,
    RuntimeCapabilityName,
    RuntimeCapabilityObservation,
    RuntimeCapabilityOutcome,
    RuntimeCapabilityQuery,
    RuntimeCapabilityReport,
    RuntimeCapabilitySet,
    RuntimeConfigOwnershipState,
    RuntimeEvidenceClass,
    RuntimeEvidenceLifecycle,
    RuntimeInstallationType,
    RuntimeRemoteState,
    RuntimeType,
)

from agentbox_runtime.models import (
    AuthenticationState,
    CapabilityState,
    ClaudeCapabilityStatus,
    CodexStatus,
    InstallationType,
    RuntimeOperationError,
)

_SAFE_VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}")
_CODEX_COLLECTION_TIMEOUT_SECONDS = 65.0
_CLAUDE_COLLECTION_TIMEOUT_SECONDS = 30.0
ObservationAdder = Callable[
    [
        RuntimeCapabilityName,
        RuntimeCapabilityOutcome,
        RuntimeEvidenceLifecycle,
        RuntimeEvidenceClass,
        RuntimeCapabilityFindingCode | None,
        tuple[RuntimeCapabilityName, ...],
    ],
    None,
]
_CODEX_PARTIAL_FINDINGS = frozenset(
    {
        "CODEX_VERSION_UNAVAILABLE",
        "CODEX_CAPABILITY_PROBE_FAILED",
        "CODEX_NPM_DETECTION_UNKNOWN",
    }
)


class CapabilityClock(Protocol):
    def now(self) -> datetime: ...


class CodexCapabilitySource(Protocol):
    async def status(self) -> CodexStatus: ...


class ClaudeCapabilitySource(Protocol):
    async def capability_status(self) -> ClaudeCapabilityStatus: ...


class SystemCapabilityClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class RuntimeCapabilityCollector:
    """Map one fixed status collection into one complete sanitized capability set."""

    def __init__(
        self,
        codex: CodexCapabilitySource,
        claude: ClaudeCapabilitySource | None,
        *,
        clock: CapabilityClock | None = None,
    ) -> None:
        self._codex = codex
        self._claude = claude
        self._clock = clock or SystemCapabilityClock()
        self._locks = {
            RuntimeType.CODEX: asyncio.Lock(),
            RuntimeType.CLAUDE: asyncio.Lock(),
        }

    async def collect(self, query: RuntimeCapabilityQuery) -> RuntimeCapabilityReport:
        lock = self._locks[query.runtime_type]
        if lock.locked():
            return self._unavailable_report(query)
        async with lock:
            try:
                if query.runtime_type is RuntimeType.CODEX:
                    codex_status = await asyncio.wait_for(
                        self._codex.status(), timeout=_CODEX_COLLECTION_TIMEOUT_SECONDS
                    )
                    return self._codex_report(query, codex_status)
                if self._claude is None:
                    return self._unavailable_report(query)
                claude_status = await asyncio.wait_for(
                    self._claude.capability_status(), timeout=_CLAUDE_COLLECTION_TIMEOUT_SECONDS
                )
                return self._claude_report(query, claude_status)
            except TimeoutError:
                return self._broken_report(query, RuntimeCapabilityFindingCode.PROBE_TIMEOUT)
            except RuntimeOperationError as exc:
                return self._broken_report(query, self._probe_finding(exc))

    def _codex_report(
        self, query: RuntimeCapabilityQuery, status: CodexStatus
    ) -> RuntimeCapabilityReport:
        observed_at, expires_at = self._timestamps()
        observations: list[RuntimeCapabilityObservation] = []

        def add(
            name: RuntimeCapabilityName,
            outcome: RuntimeCapabilityOutcome,
            lifecycle: RuntimeEvidenceLifecycle,
            evidence_class: RuntimeEvidenceClass,
            finding: RuntimeCapabilityFindingCode | None = None,
            dependencies: tuple[RuntimeCapabilityName, ...] = (),
        ) -> None:
            observations.append(
                RuntimeCapabilityObservation(
                    name=name,
                    outcome=outcome,
                    lifecycle=lifecycle,
                    evidence_class=evidence_class,
                    finding_code=finding,
                    dependencies=dependencies,
                    observed_at=observed_at,
                    expires_at=expires_at,
                )
            )

        installed_outcome = (
            RuntimeCapabilityOutcome.SUPPORTED
            if status.installed
            else RuntimeCapabilityOutcome.UNAVAILABLE
        )
        installed_finding = (
            None if status.installed else RuntimeCapabilityFindingCode.RUNTIME_NOT_INSTALLED
        )
        add(
            RuntimeCapabilityName.CODEX_INSTALLED,
            installed_outcome,
            RuntimeEvidenceLifecycle.VALIDATED,
            RuntimeEvidenceClass.AGENTBOX_BUILD,
            installed_finding,
        )
        if not status.installed:
            self._add_unavailable_codex_observations(add, observed_names={observations[0].name})
            return self._report(
                query,
                adapter_id=RuntimeAdapterID.CODEX_RUNTIME_ADAPTER_V1,
                collection_state=RuntimeCapabilityCollectionState.COMPLETE,
                runtime_version=None,
                installation_type=RuntimeInstallationType.UNKNOWN,
                authentication_state=RuntimeAuthenticationState.UNKNOWN,
                remote_state=RuntimeRemoteState.UNKNOWN,
                config_ownership_state=RuntimeConfigOwnershipState.UNKNOWN,
                managed_session_count=None,
                observations=tuple(observations),
            )

        add(
            RuntimeCapabilityName.CODEX_VERSION_DETECTABLE,
            (
                RuntimeCapabilityOutcome.SUPPORTED
                if self._safe_version(status.version) is not None
                else RuntimeCapabilityOutcome.UNKNOWN
            ),
            (
                RuntimeEvidenceLifecycle.VALIDATED
                if self._safe_version(status.version) is not None
                else RuntimeEvidenceLifecycle.DETECTED
            ),
            RuntimeEvidenceClass.PUBLIC_VERSION,
            (
                None
                if self._safe_version(status.version) is not None
                else RuntimeCapabilityFindingCode.VERSION_UNAVAILABLE
            ),
            (RuntimeCapabilityName.CODEX_INSTALLED,),
        )
        installation_type = RuntimeInstallationType(status.installation_type.value)
        add(
            RuntimeCapabilityName.CODEX_INSTALLATION_CLASSIFIABLE,
            (
                RuntimeCapabilityOutcome.BROKEN
                if status.installation_type is InstallationType.CONFLICT
                else (
                    RuntimeCapabilityOutcome.SUPPORTED
                    if status.installation_type
                    in {InstallationType.STANDALONE, InstallationType.NPM}
                    else RuntimeCapabilityOutcome.UNKNOWN
                )
            ),
            (
                RuntimeEvidenceLifecycle.VALIDATED
                if status.installation_type is not InstallationType.UNKNOWN
                else RuntimeEvidenceLifecycle.DETECTED
            ),
            RuntimeEvidenceClass.AGENTBOX_BUILD,
            (
                RuntimeCapabilityFindingCode.INSTALLATION_CONFLICT
                if status.installation_type is InstallationType.CONFLICT
                else (
                    RuntimeCapabilityFindingCode.PUBLIC_CONTRACT_UNQUALIFIED
                    if status.installation_type is InstallationType.UNKNOWN
                    else None
                )
            ),
            (RuntimeCapabilityName.CODEX_INSTALLED,),
        )
        auth_outcome, auth_finding = self._authentication_observation(status.authentication)
        add(
            RuntimeCapabilityName.CODEX_AUTHENTICATION_OBSERVABLE,
            auth_outcome,
            RuntimeEvidenceLifecycle.VALIDATED,
            (
                RuntimeEvidenceClass.PUBLIC_STATUS
                if status.authentication is not AuthenticationState.UNKNOWN
                else RuntimeEvidenceClass.NO_ACCEPTABLE_EVIDENCE
            ),
            auth_finding,
            (RuntimeCapabilityName.CODEX_INSTALLED,),
        )
        remote_mapping = (
            (
                RuntimeCapabilityName.CODEX_REMOTE_CONTROL_AVAILABLE,
                status.capabilities.remote_control,
                None,
                (RuntimeCapabilityName.CODEX_INSTALLED,),
            ),
            (
                RuntimeCapabilityName.CODEX_REMOTE_START,
                status.capabilities.start,
                None,
                (RuntimeCapabilityName.CODEX_REMOTE_CONTROL_AVAILABLE,),
            ),
            (
                RuntimeCapabilityName.CODEX_REMOTE_STOP,
                status.capabilities.stop,
                None,
                (RuntimeCapabilityName.CODEX_REMOTE_CONTROL_AVAILABLE,),
            ),
            (
                RuntimeCapabilityName.CODEX_REMOTE_PAIR,
                status.capabilities.pair,
                None,
                (RuntimeCapabilityName.CODEX_REMOTE_CONTROL_AVAILABLE,),
            ),
            (
                RuntimeCapabilityName.CODEX_REMOTE_STATUS,
                status.capabilities.status,
                RuntimeCapabilityFindingCode.REMOTE_STATUS_UNAVAILABLE,
                (RuntimeCapabilityName.CODEX_REMOTE_CONTROL_AVAILABLE,),
            ),
        )
        for name, state, unknown_finding, dependencies in remote_mapping:
            outcome, lifecycle, finding = self._capability_state(
                state, unknown_finding=unknown_finding
            )
            add(
                name,
                outcome,
                lifecycle,
                RuntimeEvidenceClass.PUBLIC_HELP,
                finding,
                dependencies,
            )

        for name, dependencies, finding in (
            (
                RuntimeCapabilityName.CODEX_PROVIDER_ADAPTER_AVAILABLE,
                (RuntimeCapabilityName.CODEX_INSTALLED,),
                RuntimeCapabilityFindingCode.ADAPTER_NOT_IMPLEMENTED,
            ),
            (
                RuntimeCapabilityName.CODEX_PROVIDER_PROFILE_VALIDATE,
                (RuntimeCapabilityName.CODEX_PROVIDER_ADAPTER_AVAILABLE,),
                RuntimeCapabilityFindingCode.ADAPTER_NOT_IMPLEMENTED,
            ),
            (
                RuntimeCapabilityName.CODEX_CONFIG_OWNERSHIP_OBSERVE,
                (RuntimeCapabilityName.CODEX_INSTALLED,),
                RuntimeCapabilityFindingCode.CONFIG_OWNERSHIP_NOT_IMPLEMENTED,
            ),
        ):
            add(
                name,
                (
                    RuntimeCapabilityOutcome.UNAVAILABLE
                    if finding is RuntimeCapabilityFindingCode.ADAPTER_NOT_IMPLEMENTED
                    else RuntimeCapabilityOutcome.UNKNOWN
                ),
                RuntimeEvidenceLifecycle.VALIDATED,
                RuntimeEvidenceClass.AGENTBOX_BUILD,
                finding,
                dependencies,
            )
        for name in (
            RuntimeCapabilityName.CODEX_ACTIVE_WRITER_OBSERVE,
            RuntimeCapabilityName.CODEX_SESSION_RESUME_OBSERVE,
            RuntimeCapabilityName.CODEX_SESSION_DISCOVERY_OBSERVE,
        ):
            add(
                name,
                RuntimeCapabilityOutcome.UNKNOWN,
                RuntimeEvidenceLifecycle.VALIDATED,
                RuntimeEvidenceClass.QUALIFIED_PUBLIC_CONTRACT,
                RuntimeCapabilityFindingCode.PUBLIC_CONTRACT_UNQUALIFIED,
                (RuntimeCapabilityName.CODEX_INSTALLED,),
            )

        collection_state = (
            RuntimeCapabilityCollectionState.PARTIAL
            if self._safe_version(status.version) is None
            or any(item.code in _CODEX_PARTIAL_FINDINGS for item in status.diagnostics)
            else RuntimeCapabilityCollectionState.COMPLETE
        )
        return self._report(
            query,
            adapter_id=RuntimeAdapterID.CODEX_RUNTIME_ADAPTER_V1,
            collection_state=collection_state,
            runtime_version=self._safe_version(status.version),
            installation_type=installation_type,
            authentication_state=RuntimeAuthenticationState(status.authentication.value),
            remote_state=RuntimeRemoteState(status.remote_state.value),
            config_ownership_state=RuntimeConfigOwnershipState.UNKNOWN,
            managed_session_count=None,
            observations=tuple(observations),
        )

    def _claude_report(
        self, query: RuntimeCapabilityQuery, status: ClaudeCapabilityStatus
    ) -> RuntimeCapabilityReport:
        observed_at, expires_at = self._timestamps()
        observations: list[RuntimeCapabilityObservation] = []

        def add(
            name: RuntimeCapabilityName,
            outcome: RuntimeCapabilityOutcome,
            lifecycle: RuntimeEvidenceLifecycle,
            evidence_class: RuntimeEvidenceClass,
            finding: RuntimeCapabilityFindingCode | None = None,
            dependencies: tuple[RuntimeCapabilityName, ...] = (),
        ) -> None:
            observations.append(
                RuntimeCapabilityObservation(
                    name=name,
                    outcome=outcome,
                    lifecycle=lifecycle,
                    evidence_class=evidence_class,
                    finding_code=finding,
                    dependencies=dependencies,
                    observed_at=observed_at,
                    expires_at=expires_at,
                )
            )

        add(
            RuntimeCapabilityName.CLAUDE_INSTALLED,
            (
                RuntimeCapabilityOutcome.SUPPORTED
                if status.installed
                else RuntimeCapabilityOutcome.UNAVAILABLE
            ),
            RuntimeEvidenceLifecycle.VALIDATED,
            RuntimeEvidenceClass.AGENTBOX_BUILD,
            None if status.installed else RuntimeCapabilityFindingCode.RUNTIME_NOT_INSTALLED,
        )
        if not status.installed:
            for name in CLAUDE_CAPABILITY_NAMES[1:]:
                add(
                    name,
                    RuntimeCapabilityOutcome.UNAVAILABLE,
                    RuntimeEvidenceLifecycle.VALIDATED,
                    RuntimeEvidenceClass.AGENTBOX_BUILD,
                    RuntimeCapabilityFindingCode.RUNTIME_NOT_INSTALLED,
                    (RuntimeCapabilityName.CLAUDE_INSTALLED,),
                )
            return self._report(
                query,
                adapter_id=RuntimeAdapterID.CLAUDE_RUNTIME_ADAPTER_V1,
                collection_state=RuntimeCapabilityCollectionState.COMPLETE,
                runtime_version=None,
                installation_type=RuntimeInstallationType.NOT_APPLICABLE,
                authentication_state=RuntimeAuthenticationState.UNKNOWN,
                remote_state=RuntimeRemoteState.UNKNOWN,
                config_ownership_state=RuntimeConfigOwnershipState.NOT_APPLICABLE,
                managed_session_count=None,
                observations=tuple(observations),
            )
        add(
            RuntimeCapabilityName.CLAUDE_VERSION_DETECTABLE,
            (
                RuntimeCapabilityOutcome.SUPPORTED
                if self._safe_version(status.version) is not None
                else RuntimeCapabilityOutcome.UNKNOWN
            ),
            (
                RuntimeEvidenceLifecycle.VALIDATED
                if self._safe_version(status.version) is not None
                else RuntimeEvidenceLifecycle.DETECTED
            ),
            RuntimeEvidenceClass.PUBLIC_VERSION,
            (
                None
                if self._safe_version(status.version) is not None
                else RuntimeCapabilityFindingCode.VERSION_UNAVAILABLE
            ),
            (RuntimeCapabilityName.CLAUDE_INSTALLED,),
        )
        auth_outcome, auth_finding = self._authentication_observation(status.authentication)
        add(
            RuntimeCapabilityName.CLAUDE_AUTHENTICATION_OBSERVABLE,
            auth_outcome,
            RuntimeEvidenceLifecycle.VALIDATED,
            (
                RuntimeEvidenceClass.PUBLIC_STATUS
                if status.authentication is not AuthenticationState.UNKNOWN
                else RuntimeEvidenceClass.NO_ACCEPTABLE_EVIDENCE
            ),
            auth_finding,
            (RuntimeCapabilityName.CLAUDE_INSTALLED,),
        )
        for name, state, dependencies in (
            (
                RuntimeCapabilityName.CLAUDE_REMOTE_CONTROL_AVAILABLE,
                status.capabilities.remote_control,
                (RuntimeCapabilityName.CLAUDE_INSTALLED,),
            ),
            (
                RuntimeCapabilityName.CLAUDE_REMOTE_START,
                status.capabilities.remote_start,
                (RuntimeCapabilityName.CLAUDE_REMOTE_CONTROL_AVAILABLE,),
            ),
        ):
            outcome, lifecycle, finding = self._capability_state(
                state,
                unknown_finding=RuntimeCapabilityFindingCode.PUBLIC_CONTRACT_UNQUALIFIED,
            )
            add(
                name,
                outcome,
                lifecycle,
                RuntimeEvidenceClass.PUBLIC_HELP,
                finding,
                dependencies,
            )
        add(
            RuntimeCapabilityName.TMUX_AVAILABLE,
            (
                RuntimeCapabilityOutcome.SUPPORTED
                if status.tmux_installed
                else RuntimeCapabilityOutcome.UNAVAILABLE
            ),
            RuntimeEvidenceLifecycle.VALIDATED,
            RuntimeEvidenceClass.AGENTBOX_BUILD,
            None if status.tmux_installed else RuntimeCapabilityFindingCode.TMUX_UNAVAILABLE,
        )
        add(
            RuntimeCapabilityName.CLAUDE_SESSION_INSPECT_MANAGED,
            (
                RuntimeCapabilityOutcome.SUPPORTED
                if status.managed_session_evidence_available
                else RuntimeCapabilityOutcome.UNKNOWN
            ),
            (
                RuntimeEvidenceLifecycle.VALIDATED
                if status.managed_session_evidence_available
                else RuntimeEvidenceLifecycle.DETECTED
            ),
            RuntimeEvidenceClass.AGENTBOX_MANAGED_STATE,
            (
                None
                if status.managed_session_evidence_available
                else RuntimeCapabilityFindingCode.MANAGED_SESSION_EVIDENCE_UNAVAILABLE
            ),
            (RuntimeCapabilityName.TMUX_AVAILABLE,),
        )
        collection_state = (
            RuntimeCapabilityCollectionState.PARTIAL
            if (
                status.installed
                and self._safe_version(status.version) is None
                or status.tmux_installed
                and not status.managed_session_evidence_available
            )
            else RuntimeCapabilityCollectionState.COMPLETE
        )
        return self._report(
            query,
            adapter_id=RuntimeAdapterID.CLAUDE_RUNTIME_ADAPTER_V1,
            collection_state=collection_state,
            runtime_version=self._safe_version(status.version),
            installation_type=RuntimeInstallationType.NOT_APPLICABLE,
            authentication_state=RuntimeAuthenticationState(status.authentication.value),
            remote_state=RuntimeRemoteState.UNKNOWN,
            config_ownership_state=RuntimeConfigOwnershipState.NOT_APPLICABLE,
            managed_session_count=(
                status.managed_session_count if status.managed_session_evidence_available else None
            ),
            observations=tuple(observations),
        )

    def _unavailable_report(self, query: RuntimeCapabilityQuery) -> RuntimeCapabilityReport:
        return self._indeterminate_report(
            query,
            RuntimeCapabilityCollectionState.ADAPTER_UNAVAILABLE,
            RuntimeCapabilityFindingCode.RUNTIME_MANAGER_UNAVAILABLE,
        )

    def _broken_report(
        self, query: RuntimeCapabilityQuery, finding: RuntimeCapabilityFindingCode
    ) -> RuntimeCapabilityReport:
        return self._indeterminate_report(query, RuntimeCapabilityCollectionState.BROKEN, finding)

    def _indeterminate_report(
        self,
        query: RuntimeCapabilityQuery,
        collection_state: RuntimeCapabilityCollectionState,
        finding: RuntimeCapabilityFindingCode,
    ) -> RuntimeCapabilityReport:
        observed_at, expires_at = self._timestamps()
        names = (
            CODEX_CAPABILITY_NAMES
            if query.capability_set is RuntimeCapabilitySet.CODEX_PROVIDER_RUNTIME_V1
            else CLAUDE_CAPABILITY_NAMES
        )
        observations = tuple(
            RuntimeCapabilityObservation(
                name=name,
                outcome=RuntimeCapabilityOutcome.UNKNOWN,
                lifecycle=RuntimeEvidenceLifecycle.UNKNOWN,
                evidence_class=RuntimeEvidenceClass.NO_ACCEPTABLE_EVIDENCE,
                finding_code=finding,
                dependencies=(),
                observed_at=observed_at,
                expires_at=expires_at,
            )
            for name in names
        )
        is_codex = query.runtime_type is RuntimeType.CODEX
        return self._report(
            query,
            adapter_id=(
                RuntimeAdapterID.CODEX_RUNTIME_ADAPTER_V1
                if is_codex
                else RuntimeAdapterID.CLAUDE_RUNTIME_ADAPTER_V1
            ),
            collection_state=collection_state,
            runtime_version=None,
            installation_type=(
                RuntimeInstallationType.UNKNOWN
                if is_codex
                else RuntimeInstallationType.NOT_APPLICABLE
            ),
            authentication_state=RuntimeAuthenticationState.UNKNOWN,
            remote_state=RuntimeRemoteState.UNKNOWN,
            config_ownership_state=(
                RuntimeConfigOwnershipState.UNKNOWN
                if is_codex
                else RuntimeConfigOwnershipState.NOT_APPLICABLE
            ),
            managed_session_count=None,
            observations=observations,
        )

    def _report(
        self,
        query: RuntimeCapabilityQuery,
        *,
        adapter_id: RuntimeAdapterID,
        collection_state: RuntimeCapabilityCollectionState,
        runtime_version: str | None,
        installation_type: RuntimeInstallationType,
        authentication_state: RuntimeAuthenticationState,
        remote_state: RuntimeRemoteState,
        config_ownership_state: RuntimeConfigOwnershipState,
        managed_session_count: int | None,
        observations: tuple[RuntimeCapabilityObservation, ...],
    ) -> RuntimeCapabilityReport:
        findings = tuple(
            dict.fromkeys(
                observation.finding_code
                for observation in observations
                if observation.finding_code is not None
            )
        )
        return RuntimeCapabilityReport(
            runtime_installation_id=query.runtime_installation_id,
            runtime_installation_revision=query.runtime_installation_revision,
            runtime_type=query.runtime_type,
            capability_set=query.capability_set,
            adapter_id=adapter_id,
            collection_state=collection_state,
            runtime_version=runtime_version,
            installation_type=installation_type,
            authentication_state=authentication_state,
            remote_state=remote_state,
            config_ownership_state=config_ownership_state,
            managed_session_count=managed_session_count,
            observed_at=observations[0].observed_at,
            expires_at=observations[0].expires_at,
            observations=observations,
            findings=findings,
        )

    def _add_unavailable_codex_observations(
        self,
        add: ObservationAdder,
        *,
        observed_names: set[RuntimeCapabilityName],
    ) -> None:
        for name in CODEX_CAPABILITY_NAMES:
            if name in observed_names:
                continue
            dependencies = (
                ()
                if name is RuntimeCapabilityName.CODEX_INSTALLED
                else (RuntimeCapabilityName.CODEX_INSTALLED,)
            )
            add(
                name,
                RuntimeCapabilityOutcome.UNAVAILABLE,
                RuntimeEvidenceLifecycle.VALIDATED,
                RuntimeEvidenceClass.AGENTBOX_BUILD,
                RuntimeCapabilityFindingCode.RUNTIME_NOT_INSTALLED,
                dependencies,
            )

    def _timestamps(self) -> tuple[datetime, datetime]:
        observed_at = self._clock.now()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            observed_at = observed_at.replace(tzinfo=UTC)
        else:
            observed_at = observed_at.astimezone(UTC)
        return observed_at, observed_at + timedelta(seconds=RUNTIME_CAPABILITY_TTL_SECONDS)

    @staticmethod
    def _safe_version(value: str | None) -> str | None:
        return value if value is not None and _SAFE_VERSION.fullmatch(value) else None

    @staticmethod
    def _authentication_observation(
        state: AuthenticationState,
    ) -> tuple[RuntimeCapabilityOutcome, RuntimeCapabilityFindingCode | None]:
        if state is AuthenticationState.AUTHENTICATED:
            return RuntimeCapabilityOutcome.SUPPORTED, None
        if state is AuthenticationState.UNAUTHENTICATED:
            return RuntimeCapabilityOutcome.UNAUTHENTICATED, None
        return (
            RuntimeCapabilityOutcome.UNKNOWN,
            RuntimeCapabilityFindingCode.AUTH_STATUS_UNAVAILABLE,
        )

    @staticmethod
    def _capability_state(
        state: CapabilityState,
        *,
        unknown_finding: RuntimeCapabilityFindingCode | None,
    ) -> tuple[
        RuntimeCapabilityOutcome,
        RuntimeEvidenceLifecycle,
        RuntimeCapabilityFindingCode | None,
    ]:
        if state is CapabilityState.SUPPORTED:
            return (
                RuntimeCapabilityOutcome.SUPPORTED,
                RuntimeEvidenceLifecycle.VALIDATED,
                None,
            )
        if state is CapabilityState.UNSUPPORTED:
            return (
                RuntimeCapabilityOutcome.UNSUPPORTED,
                RuntimeEvidenceLifecycle.VALIDATED,
                unknown_finding,
            )
        return (
            RuntimeCapabilityOutcome.UNKNOWN,
            RuntimeEvidenceLifecycle.DETECTED,
            unknown_finding or RuntimeCapabilityFindingCode.PUBLIC_CONTRACT_UNQUALIFIED,
        )

    @staticmethod
    def _probe_finding(error: RuntimeOperationError) -> RuntimeCapabilityFindingCode:
        if "TIMEOUT" in error.code:
            return RuntimeCapabilityFindingCode.PROBE_TIMEOUT
        if "LIMIT" in error.code or "TOO_LARGE" in error.code:
            return RuntimeCapabilityFindingCode.PROBE_OUTPUT_TOO_LARGE
        return RuntimeCapabilityFindingCode.PROBE_OUTPUT_INVALID
