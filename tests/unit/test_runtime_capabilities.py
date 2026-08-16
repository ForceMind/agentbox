from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import agentbox_runtime.capabilities as capability_module
import pytest
from agentbox_protocol.runtime_capabilities import (
    CLAUDE_CAPABILITY_NAMES,
    CODEX_CAPABILITY_NAMES,
    RuntimeCapabilityCollectionState,
    RuntimeCapabilityFindingCode,
    RuntimeCapabilityName,
    RuntimeCapabilityObservation,
    RuntimeCapabilityOutcome,
    RuntimeCapabilityQuery,
    RuntimeCapabilityRefreshPolicy,
    RuntimeCapabilityReport,
    RuntimeCapabilitySet,
    RuntimeEvidenceLifecycle,
    RuntimeInstallationType,
    RuntimeType,
)
from agentbox_runtime.capabilities import RuntimeCapabilityCollector
from agentbox_runtime.models import (
    AuthenticationState,
    CapabilityState,
    ClaudeCapabilities,
    ClaudeCapabilityStatus,
    CodexCapabilities,
    CodexStatus,
    DiagnosticFinding,
    InstallationType,
    RemoteState,
    RuntimeOperationError,
)

RUNTIME_ID = "rti_0123456789abcdef0123456789abcdef"
CANARIES = (
    "SELECTED-EXECUTABLE-CANARY",
    "ALTERNATIVE-EXECUTABLE-CANARY",
    "ABSOLUTE-PATH-CANARY-/private/runtime",
    "RUNTIME-HOME-CANARY",
    "CONFIG-PATH-CANARY",
    "AUTH-PATH-CANARY",
    "SOCKET-PATH-CANARY",
    "TMUX-SOCKET-CANARY",
    "SESSION-NAME-CANARY",
    "ATTACH-COMMAND-CANARY",
    "PANE-OUTPUT-CANARY",
    "PROCESS-ARGV-CANARY",
    "PID-LIST-CANARY",
    "ENVIRONMENT-CANARY",
    "RAW-STDOUT-CANARY",
    "RAW-STDERR-CANARY",
    "RAW-CONFIG-CANARY",
    "TOML-CANARY",
    "JSONL-CANARY",
    "ROLLOUT-CANARY",
    "PROMPT-CANARY",
    "COMPLETION-CANARY",
    "CONVERSATION-CANARY",
    "PAIR-CODE-CANARY",
    "TOKEN-CANARY",
    "SECRET-CANARY",
    "AUTHORIZATION-CANARY",
    "COOKIE-CANARY",
    "HEADER-CANARY",
    "PROVIDER-RESPONSE-CANARY",
)


class FixedClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 16, 3, 4, 5, tzinfo=UTC)

    def now(self) -> datetime:
        return self.value


class CodexSource:
    def __init__(self, status: CodexStatus | RuntimeOperationError) -> None:
        self.value = status
        self.calls = 0
        self.mutations: list[str] = []

    async def status(self) -> CodexStatus:
        self.calls += 1
        if isinstance(self.value, RuntimeOperationError):
            raise self.value
        return self.value

    async def start_remote(self) -> None:
        self.mutations.append("start_remote")

    async def stop_remote(self) -> None:
        self.mutations.append("stop_remote")

    async def generate_pair_code(self) -> None:
        self.mutations.append("generate_pair_code")


class ClaudeSource:
    def __init__(self, status: ClaudeCapabilityStatus) -> None:
        self.value = status
        self.calls = 0
        self.mutations: list[str] = []

    async def capability_status(self) -> ClaudeCapabilityStatus:
        self.calls += 1
        return self.value

    async def start(self) -> None:
        self.mutations.append("start")

    async def stop(self) -> None:
        self.mutations.append("stop")

    async def recent_output(self) -> None:
        self.mutations.append("recent_output")


class BlockingCodexSource(CodexSource):
    def __init__(self, status: CodexStatus) -> None:
        super().__init__(status)
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def status(self) -> CodexStatus:
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        assert isinstance(self.value, CodexStatus)
        return self.value


class TimeoutThenSuccessCodexSource(CodexSource):
    def __init__(self, status: CodexStatus, *, timeouts: int) -> None:
        super().__init__(status)
        self._timeouts = timeouts
        self.active = 0
        self.max_active = 0
        self.cancellations = 0

    async def status(self) -> CodexStatus:
        self.calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.calls <= self._timeouts:
                await asyncio.Event().wait()
            assert isinstance(self.value, CodexStatus)
            return self.value
        except asyncio.CancelledError:
            self.cancellations += 1
            await asyncio.sleep(0)
            raise
        finally:
            self.active -= 1


def codex_status(
    *,
    installed: bool = True,
    version: str | None = "0.146.1",
    installation_type: InstallationType = InstallationType.STANDALONE,
    authentication: AuthenticationState = AuthenticationState.AUTHENTICATED,
    remote_control: CapabilityState = CapabilityState.SUPPORTED,
    start: CapabilityState = CapabilityState.SUPPORTED,
    stop: CapabilityState = CapabilityState.SUPPORTED,
    pair: CapabilityState = CapabilityState.SUPPORTED,
    status: CapabilityState = CapabilityState.UNKNOWN,
) -> CodexStatus:
    return CodexStatus(
        installed=installed,
        version=version,
        selected_executable=CANARIES[0],
        alternatives=(CANARIES[1], CANARIES[2]),
        installation_type=installation_type,
        conflict_detected=installation_type is InstallationType.CONFLICT,
        authentication=authentication,
        capabilities=CodexCapabilities(
            remote_control=remote_control,
            start=start,
            stop=stop,
            pair=pair,
            status=status,
        ),
        remote_state=RemoteState.UNKNOWN,
        diagnostics=(
            DiagnosticFinding(
                code="SAFE_FINDING",
                severity="warning",
                summary=" ".join(CANARIES[3:]),
                remediation=CANARIES[-1],
            ),
        ),
    )


def claude_status(
    *,
    installed: bool = True,
    version: str | None = "1.2.3",
    authentication: AuthenticationState = AuthenticationState.UNKNOWN,
    remote_control: CapabilityState = CapabilityState.SUPPORTED,
    remote_start: CapabilityState = CapabilityState.SUPPORTED,
    tmux: bool = True,
    managed_count: int | None = 2,
    evidence: bool = True,
) -> ClaudeCapabilityStatus:
    return ClaudeCapabilityStatus(
        installed=installed,
        version=version,
        authentication=authentication,
        capabilities=ClaudeCapabilities(
            remote_control=remote_control,
            remote_start=remote_start,
            version=CapabilityState.SUPPORTED,
        ),
        tmux_installed=tmux,
        managed_session_count=managed_count,
        managed_session_evidence_available=evidence,
    )


def capability_query(runtime_type: RuntimeType = RuntimeType.CODEX) -> RuntimeCapabilityQuery:
    return RuntimeCapabilityQuery(
        request_id="req_runtime_capabilities",
        runtime_installation_id=RUNTIME_ID,
        runtime_installation_revision=7,
        runtime_type=runtime_type,
        capability_set=(
            RuntimeCapabilitySet.CODEX_PROVIDER_RUNTIME_V1
            if runtime_type is RuntimeType.CODEX
            else RuntimeCapabilitySet.CLAUDE_RUNTIME_SESSION_V1
        ),
        refresh_policy=RuntimeCapabilityRefreshPolicy.FORCE_FRESH_READ_ONLY,
    )


def by_name(
    report: RuntimeCapabilityReport, name: RuntimeCapabilityName
) -> RuntimeCapabilityObservation:
    return next(item for item in report.observations if item.name is name)


@pytest.mark.anyio
async def test_codex_collection_is_complete_fresh_sanitized_and_read_only() -> None:
    codex = CodexSource(codex_status())
    claude = ClaudeSource(claude_status())
    clock = FixedClock()
    report = await RuntimeCapabilityCollector(codex, claude, clock=clock).collect(
        capability_query()
    )

    assert codex.calls == 1
    assert codex.mutations == []
    assert tuple(item.name for item in report.observations) == CODEX_CAPABILITY_NAMES
    assert report.observed_at == clock.value
    assert report.expires_at == clock.value + timedelta(seconds=60)
    assert report.installation_type is RuntimeInstallationType.STANDALONE
    assert report.managed_session_count is None
    serialized = report.model_dump_json()
    assert all(canary not in serialized for canary in CANARIES)
    assert "selected_executable" not in serialized
    assert "alternatives" not in serialized
    assert "diagnostics" not in serialized
    assert (
        by_name(report, RuntimeCapabilityName.CODEX_PROVIDER_ADAPTER_AVAILABLE).finding_code
        is RuntimeCapabilityFindingCode.ADAPTER_NOT_IMPLEMENTED
    )
    assert (
        by_name(report, RuntimeCapabilityName.CODEX_PROVIDER_PROFILE_VALIDATE).outcome
        is RuntimeCapabilityOutcome.UNAVAILABLE
    )
    for name in (
        RuntimeCapabilityName.CODEX_ACTIVE_WRITER_OBSERVE,
        RuntimeCapabilityName.CODEX_SESSION_RESUME_OBSERVE,
        RuntimeCapabilityName.CODEX_SESSION_DISCOVERY_OBSERVE,
    ):
        observation = by_name(report, name)
        assert observation.outcome is RuntimeCapabilityOutcome.UNKNOWN
        assert observation.lifecycle is RuntimeEvidenceLifecycle.VALIDATED


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "expected_installation", "expected_outcome"),
    (
        (
            codex_status(installation_type=InstallationType.NPM),
            RuntimeInstallationType.NPM,
            RuntimeCapabilityOutcome.SUPPORTED,
        ),
        (
            codex_status(installation_type=InstallationType.CONFLICT),
            RuntimeInstallationType.CONFLICT,
            RuntimeCapabilityOutcome.BROKEN,
        ),
        (
            codex_status(installation_type=InstallationType.UNKNOWN),
            RuntimeInstallationType.UNKNOWN,
            RuntimeCapabilityOutcome.UNKNOWN,
        ),
    ),
)
async def test_codex_installation_classification_is_independent(
    status: CodexStatus,
    expected_installation: RuntimeInstallationType,
    expected_outcome: RuntimeCapabilityOutcome,
) -> None:
    report = await RuntimeCapabilityCollector(
        CodexSource(status), ClaudeSource(claude_status()), clock=FixedClock()
    ).collect(capability_query())
    assert report.installation_type is expected_installation
    assert (
        by_name(report, RuntimeCapabilityName.CODEX_INSTALLATION_CLASSIFIABLE).outcome
        is expected_outcome
    )


@pytest.mark.anyio
async def test_not_installed_and_malformed_version_fail_closed() -> None:
    missing = await RuntimeCapabilityCollector(
        CodexSource(codex_status(installed=False, version=None)),
        ClaudeSource(claude_status()),
        clock=FixedClock(),
    ).collect(capability_query())
    assert all(
        item.outcome is RuntimeCapabilityOutcome.UNAVAILABLE for item in missing.observations
    )

    malformed = await RuntimeCapabilityCollector(
        CodexSource(codex_status(version="0.146.1 /root/TOKEN-CANARY")),
        ClaudeSource(claude_status()),
        clock=FixedClock(),
    ).collect(capability_query())
    assert malformed.runtime_version is None
    assert malformed.collection_state is RuntimeCapabilityCollectionState.PARTIAL
    assert (
        by_name(malformed, RuntimeCapabilityName.CODEX_VERSION_DETECTABLE).outcome
        is RuntimeCapabilityOutcome.UNKNOWN
    )
    assert (
        by_name(malformed, RuntimeCapabilityName.CODEX_PROVIDER_ADAPTER_AVAILABLE).outcome
        is RuntimeCapabilityOutcome.UNAVAILABLE
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("authentication", "outcome"),
    (
        (AuthenticationState.AUTHENTICATED, RuntimeCapabilityOutcome.SUPPORTED),
        (AuthenticationState.UNAUTHENTICATED, RuntimeCapabilityOutcome.UNAUTHENTICATED),
        (AuthenticationState.UNKNOWN, RuntimeCapabilityOutcome.UNKNOWN),
    ),
)
async def test_codex_authentication_states_are_honest(
    authentication: AuthenticationState, outcome: RuntimeCapabilityOutcome
) -> None:
    report = await RuntimeCapabilityCollector(
        CodexSource(codex_status(authentication=authentication)),
        ClaudeSource(claude_status()),
        clock=FixedClock(),
    ).collect(capability_query())
    assert by_name(report, RuntimeCapabilityName.CODEX_AUTHENTICATION_OBSERVABLE).outcome is outcome


@pytest.mark.anyio
async def test_remote_capabilities_do_not_infer_provider_capabilities() -> None:
    report = await RuntimeCapabilityCollector(
        CodexSource(
            codex_status(
                remote_control=CapabilityState.SUPPORTED,
                start=CapabilityState.SUPPORTED,
                stop=CapabilityState.UNSUPPORTED,
                pair=CapabilityState.UNKNOWN,
                status=CapabilityState.UNSUPPORTED,
            )
        ),
        ClaudeSource(claude_status()),
        clock=FixedClock(),
    ).collect(capability_query())
    assert (
        by_name(report, RuntimeCapabilityName.CODEX_REMOTE_CONTROL_AVAILABLE).outcome
        is RuntimeCapabilityOutcome.SUPPORTED
    )
    assert (
        by_name(report, RuntimeCapabilityName.CODEX_REMOTE_STOP).outcome
        is RuntimeCapabilityOutcome.UNSUPPORTED
    )
    assert (
        by_name(report, RuntimeCapabilityName.CODEX_REMOTE_PAIR).outcome
        is RuntimeCapabilityOutcome.UNKNOWN
    )
    assert (
        by_name(report, RuntimeCapabilityName.CODEX_PROVIDER_ADAPTER_AVAILABLE).outcome
        is RuntimeCapabilityOutcome.UNAVAILABLE
    )


@pytest.mark.anyio
async def test_claude_set_is_runtime_only_and_exposes_only_managed_count() -> None:
    codex = CodexSource(codex_status())
    claude = ClaudeSource(
        claude_status(
            authentication=AuthenticationState.AUTHENTICATED,
            managed_count=3,
            evidence=True,
        )
    )
    report = await RuntimeCapabilityCollector(codex, claude, clock=FixedClock()).collect(
        capability_query(RuntimeType.CLAUDE)
    )
    assert claude.calls == 1
    assert claude.mutations == []
    assert codex.calls == 0
    assert tuple(item.name for item in report.observations) == CLAUDE_CAPABILITY_NAMES
    assert report.managed_session_count == 3
    assert all("provider" not in item.name.value for item in report.observations)
    inspection = by_name(report, RuntimeCapabilityName.CLAUDE_SESSION_INSPECT_MANAGED)
    assert inspection.outcome is RuntimeCapabilityOutcome.SUPPORTED
    assert inspection.lifecycle is RuntimeEvidenceLifecycle.VALIDATED
    assert inspection.dependencies == (
        RuntimeCapabilityName.CLAUDE_INSTALLED,
        RuntimeCapabilityName.TMUX_AVAILABLE,
    )


@pytest.mark.anyio
async def test_claude_tmux_and_managed_evidence_degrade_independently() -> None:
    report = await RuntimeCapabilityCollector(
        CodexSource(codex_status()),
        ClaudeSource(claude_status(tmux=False, managed_count=None, evidence=False)),
        clock=FixedClock(),
    ).collect(capability_query(RuntimeType.CLAUDE))
    assert report.managed_session_count is None
    assert (
        by_name(report, RuntimeCapabilityName.TMUX_AVAILABLE).outcome
        is RuntimeCapabilityOutcome.UNAVAILABLE
    )
    inspection = by_name(report, RuntimeCapabilityName.CLAUDE_SESSION_INSPECT_MANAGED)
    assert inspection.outcome is RuntimeCapabilityOutcome.UNAVAILABLE
    assert inspection.finding_code is RuntimeCapabilityFindingCode.TMUX_UNAVAILABLE


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tmux_installed", "tmux_outcome", "tmux_finding"),
    (
        (True, RuntimeCapabilityOutcome.SUPPORTED, None),
        (
            False,
            RuntimeCapabilityOutcome.UNAVAILABLE,
            RuntimeCapabilityFindingCode.TMUX_UNAVAILABLE,
        ),
    ),
)
async def test_claude_absence_preserves_independent_tmux_evidence(
    tmux_installed: bool,
    tmux_outcome: RuntimeCapabilityOutcome,
    tmux_finding: RuntimeCapabilityFindingCode | None,
) -> None:
    report = await RuntimeCapabilityCollector(
        CodexSource(codex_status()),
        ClaudeSource(
            claude_status(
                installed=False,
                version=None,
                remote_control=CapabilityState.SUPPORTED,
                remote_start=CapabilityState.SUPPORTED,
                tmux=tmux_installed,
                managed_count=None,
                evidence=False,
            )
        ),
        clock=FixedClock(),
    ).collect(capability_query(RuntimeType.CLAUDE))
    for name in CLAUDE_CAPABILITY_NAMES[:5]:
        assert by_name(report, name).outcome is RuntimeCapabilityOutcome.UNAVAILABLE
    tmux = by_name(report, RuntimeCapabilityName.TMUX_AVAILABLE)
    assert tmux.outcome is tmux_outcome
    assert tmux.finding_code is tmux_finding
    inspection = by_name(report, RuntimeCapabilityName.CLAUDE_SESSION_INSPECT_MANAGED)
    assert inspection.outcome is RuntimeCapabilityOutcome.UNAVAILABLE
    assert report.managed_session_count is None


@pytest.mark.anyio
async def test_collector_is_single_flight_without_unbounded_queue() -> None:
    source = BlockingCodexSource(codex_status())
    collector = RuntimeCapabilityCollector(
        source, ClaudeSource(claude_status()), clock=FixedClock()
    )
    first = asyncio.create_task(collector.collect(capability_query()))
    await source.entered.wait()
    second = await collector.collect(capability_query())
    assert second.collection_state is RuntimeCapabilityCollectionState.ADAPTER_UNAVAILABLE
    assert source.calls == 1
    source.release.set()
    assert (await first).collection_state is RuntimeCapabilityCollectionState.COMPLETE


@pytest.mark.anyio
async def test_collection_timeout_completes_cancellation_and_releases_single_flight_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(capability_module, "_CODEX_COLLECTION_TIMEOUT_SECONDS", 0.01)
    source = TimeoutThenSuccessCodexSource(codex_status(), timeouts=2)
    collector = RuntimeCapabilityCollector(
        source, ClaudeSource(claude_status()), clock=FixedClock()
    )

    for _ in range(2):
        timed_out = await collector.collect(capability_query())
        assert timed_out.collection_state is RuntimeCapabilityCollectionState.BROKEN
        assert timed_out.findings == (RuntimeCapabilityFindingCode.PROBE_TIMEOUT,)
        assert source.active == 0

    recovered = await collector.collect(capability_query())
    assert recovered.collection_state is RuntimeCapabilityCollectionState.COMPLETE
    assert source.calls == 3
    assert source.cancellations == 2
    assert source.max_active == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("code", "finding"),
    (
        ("CODEX_COMMAND_TIMEOUT", RuntimeCapabilityFindingCode.PROBE_TIMEOUT),
        ("CODEX_OUTPUT_TOO_LARGE", RuntimeCapabilityFindingCode.PROBE_OUTPUT_TOO_LARGE),
        ("CODEX_OUTPUT_INVALID", RuntimeCapabilityFindingCode.PROBE_OUTPUT_INVALID),
    ),
)
async def test_probe_failures_return_bounded_codes_without_raw_errors(
    code: str, finding: RuntimeCapabilityFindingCode
) -> None:
    canary = "RAW-ERROR-TOKEN-CANARY"
    source = CodexSource(RuntimeOperationError(code, canary, category="broken"))
    report = await RuntimeCapabilityCollector(
        source, ClaudeSource(claude_status()), clock=FixedClock()
    ).collect(capability_query())
    assert report.collection_state is RuntimeCapabilityCollectionState.BROKEN
    assert report.findings == (finding,)
    assert canary not in report.model_dump_json()
