from __future__ import annotations

import asyncio
import math
from pathlib import Path
from typing import Any, cast

import pytest
from agentbox_core.waw import AgentType
from agentbox_runtime.waw_auth_probe import (
    WAWPublicAuthEvidence,
    WAWPublicAuthProbe,
    WAWPublicAuthProbeCache,
    WAWPublicAuthProbeError,
    WAWPublicAuthResult,
    WAWVendorPublicAuthBinding,
    WAWVendorPublicAuthProbeAdapter,
    validate_waw_public_auth_probe_evidence,
)
from agentbox_runtime.waw_process_profile import INTERACTIVE_PROFILE_CONSTANTS_V1
from agentbox_runtime.waw_vendor_probe import (
    WAWIsolatedProbeCompletion,
    WAWProcessIsolationKind,
    WAWProcessIsolationPort,
    WAWVendorProbeFailure,
    WAWVendorProbeId,
    WAWVendorProbeParserId,
    WAWVendorProbeProfile,
    WAWVendorProbeRunner,
    waw_vendor_probe_output_digest,
)

HOST_ID = "wri_" + "1" * 32
FINGERPRINT = "a" * 64


class _QualifiedProbePort(WAWProcessIsolationPort):
    def __init__(self, outcomes: dict[AgentType, tuple[int, bytes, bytes]]) -> None:
        super().__init__(
            isolation_kind=WAWProcessIsolationKind.PREBIRTH_CGROUP,
            production_qualified=True,
        )
        self.outcomes = outcomes
        self.calls: list[AgentType] = []

    async def execute(
        self,
        profile: WAWVendorProbeProfile,
        arguments: tuple[str, ...],
        *,
        timeout_seconds: float,
        output_limit: int,
        terminate_grace_seconds: float,
    ) -> WAWIsolatedProbeCompletion:
        del arguments, timeout_seconds, output_limit, terminate_grace_seconds
        self.calls.append(profile.agent_type)
        exit_code, stdout, stderr = self.outcomes[profile.agent_type]
        return WAWIsolatedProbeCompletion(
            exit_code,
            stdout,
            stderr,
            WAWVendorProbeFailure.NONE,
            self.cleanup_proof(leader_reaped=True, descendants_remaining=0),
        )


def _vendor_adapter(
    tmp_path: Path, outcomes: dict[AgentType, tuple[int, bytes, bytes]]
) -> tuple[WAWVendorPublicAuthProbeAdapter, _QualifiedProbePort]:
    versions = {AgentType.CLAUDE: "2.1.226", AgentType.CODEX: "0.146.1"}
    fingerprints = {AgentType.CLAUDE: "a" * 64, AgentType.CODEX: "b" * 64}
    port = _QualifiedProbePort(outcomes)
    profiles = {
        AgentType.CLAUDE: WAWVendorProbeProfile(
            str(INTERACTIVE_PROFILE_CONSTANTS_V1["claude"]["profile_id"]),
            AgentType.CLAUDE,
            versions[AgentType.CLAUDE],
            WAWVendorProbeId.CLAUDE_AUTH_STATUS_V1,
            WAWVendorProbeParserId.CLAUDE_EXIT_STATUS_V1,
            tmp_path / "claude",
            tmp_path,
            (("HOME", str(tmp_path)),),
        ),
        AgentType.CODEX: WAWVendorProbeProfile(
            str(INTERACTIVE_PROFILE_CONSTANTS_V1["codex"]["profile_id"]),
            AgentType.CODEX,
            versions[AgentType.CODEX],
            WAWVendorProbeId.CODEX_LOGIN_STATUS_V1,
            WAWVendorProbeParserId.CODEX_EXACT_STATUS_V1,
            tmp_path / "codex",
            tmp_path,
            (("HOME", str(tmp_path)),),
            waw_vendor_probe_output_digest(b"Not logged in\n", b""),
        ),
    }
    bindings = {
        agent_type: WAWVendorPublicAuthBinding(
            agent_type,
            HOST_ID,
            "2",
            fingerprints[agent_type],
            str(INTERACTIVE_PROFILE_CONSTANTS_V1[agent_type.value]["profile_id"]),
            versions[agent_type],
        )
        for agent_type in AgentType
    }
    return WAWVendorPublicAuthProbeAdapter(WAWVendorProbeRunner(profiles, port), bindings), port


class _FakePublicAuthProbe:
    """Synthetic adapter; it never executes a vendor command or reads files."""

    def __init__(self, result: WAWPublicAuthResult) -> None:
        self._result = result

    async def probe(
        self,
        *,
        agent_type: AgentType,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: str,
        executable_fingerprint: str,
        checked_at_monotonic: float,
    ) -> WAWPublicAuthEvidence:
        return WAWPublicAuthEvidence(
            agent_type=agent_type,
            runtime_host_installation_id=runtime_host_installation_id,
            runtime_host_installation_revision=runtime_host_installation_revision,
            executable_fingerprint=executable_fingerprint,
            checked_at_monotonic=checked_at_monotonic,
            result=self._result,
        )


def _evidence(
    *, result: WAWPublicAuthResult = WAWPublicAuthResult.AUTHENTICATED
) -> WAWPublicAuthEvidence:
    return WAWPublicAuthEvidence(
        agent_type=AgentType.CLAUDE,
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision="2",
        executable_fingerprint=FINGERPRINT,
        checked_at_monotonic=100.0,
        result=result,
    )


def test_cache_requires_matching_fresh_authenticated_evidence() -> None:
    cache = WAWPublicAuthProbeCache()
    cache.record(_evidence())
    assert (
        cache.fresh(
            agent_type=AgentType.CLAUDE,
            runtime_host_installation_id=HOST_ID,
            runtime_host_installation_revision="2",
            executable_fingerprint=FINGERPRINT,
            now_monotonic=129.9,
        )
        == _evidence()
    )
    assert (
        cache.fresh(
            agent_type=AgentType.CLAUDE,
            runtime_host_installation_id=HOST_ID,
            runtime_host_installation_revision="2",
            executable_fingerprint=FINGERPRINT,
            now_monotonic=130.0,
        )
        is None
    )


@pytest.mark.anyio
@pytest.mark.parametrize("result", list(WAWPublicAuthResult))
async def test_public_auth_probe_protocol_and_evidence_binding(
    result: WAWPublicAuthResult,
) -> None:
    probe: WAWPublicAuthProbe = _FakePublicAuthProbe(result)
    evidence = await probe.probe(
        agent_type=AgentType.CLAUDE,
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision="2",
        executable_fingerprint=FINGERPRINT,
        checked_at_monotonic=100.0,
    )
    assert (
        validate_waw_public_auth_probe_evidence(
            evidence,
            agent_type=AgentType.CLAUDE,
            runtime_host_installation_id=HOST_ID,
            runtime_host_installation_revision="2",
            executable_fingerprint=FINGERPRINT,
        )
        == evidence
    )


@pytest.mark.anyio
async def test_public_auth_probe_rejects_identity_drift() -> None:
    evidence = await _FakePublicAuthProbe(WAWPublicAuthResult.AUTHENTICATED).probe(
        agent_type=AgentType.CLAUDE,
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision="2",
        executable_fingerprint=FINGERPRINT,
        checked_at_monotonic=100.0,
    )
    with pytest.raises(WAWPublicAuthProbeError, match="identity"):
        validate_waw_public_auth_probe_evidence(
            evidence,
            agent_type=AgentType.CLAUDE,
            runtime_host_installation_id=HOST_ID,
            runtime_host_installation_revision="3",
            executable_fingerprint=FINGERPRINT,
        )


@pytest.mark.anyio
async def test_cache_refreshes_from_bounded_probe_and_applies_freshness() -> None:
    cache = WAWPublicAuthProbeCache()
    evidence = await cache.refresh_from_probe(
        _FakePublicAuthProbe(WAWPublicAuthResult.AUTHENTICATED),
        agent_type=AgentType.CLAUDE,
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision="2",
        executable_fingerprint=FINGERPRINT,
        checked_at_monotonic=100.0,
    )
    assert evidence == _evidence()
    assert (
        cache.fresh(
            agent_type=AgentType.CLAUDE,
            runtime_host_installation_id=HOST_ID,
            runtime_host_installation_revision="2",
            executable_fingerprint=FINGERPRINT,
            now_monotonic=101.0,
        )
        == evidence
    )


@pytest.mark.anyio
async def test_probe_identity_drift_cannot_replace_existing_cache_entry() -> None:
    class DriftingProbe:
        async def probe(
            self,
            *,
            agent_type: AgentType,
            runtime_host_installation_id: str,
            runtime_host_installation_revision: str,
            executable_fingerprint: str,
            checked_at_monotonic: float,
        ) -> WAWPublicAuthEvidence:
            del (
                agent_type,
                runtime_host_installation_id,
                runtime_host_installation_revision,
                executable_fingerprint,
                checked_at_monotonic,
            )
            return _evidence()

    cache = WAWPublicAuthProbeCache()
    cache.record(_evidence(result=WAWPublicAuthResult.UNAUTHENTICATED))
    with pytest.raises(WAWPublicAuthProbeError, match="identity"):
        await cache.refresh_from_probe(
            DriftingProbe(),
            agent_type=AgentType.CLAUDE,
            runtime_host_installation_id=HOST_ID,
            runtime_host_installation_revision="3",
            executable_fingerprint=FINGERPRINT,
            checked_at_monotonic=101.0,
        )
    assert (
        cache.fresh(
            agent_type=AgentType.CLAUDE,
            runtime_host_installation_id=HOST_ID,
            runtime_host_installation_revision="2",
            executable_fingerprint=FINGERPRINT,
            now_monotonic=101.0,
        )
        is None
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("runtime_host_installation_id", "bad"),
        ("runtime_host_installation_revision", "01"),
        ("executable_fingerprint", "A" * 64),
        ("checked_at_monotonic", math.nan),
    ],
)
@pytest.mark.anyio
async def test_invalid_probe_request_is_rejected_before_adapter_call(
    field: str, value: object
) -> None:
    class CountingProbe:
        def __init__(self) -> None:
            self.calls = 0

        async def probe(
            self,
            *,
            agent_type: AgentType,
            runtime_host_installation_id: str,
            runtime_host_installation_revision: str,
            executable_fingerprint: str,
            checked_at_monotonic: float,
        ) -> WAWPublicAuthEvidence:
            self.calls += 1
            return _evidence()

    probe = CountingProbe()
    request: dict[str, object] = {
        "agent_type": AgentType.CLAUDE,
        "runtime_host_installation_id": HOST_ID,
        "runtime_host_installation_revision": "2",
        "executable_fingerprint": FINGERPRINT,
        "checked_at_monotonic": 100.0,
    }
    request[field] = value
    with pytest.raises(WAWPublicAuthProbeError):
        await WAWPublicAuthProbeCache().refresh_from_probe(probe, **cast(Any, request))
    assert probe.calls == 0


@pytest.mark.parametrize(
    "result",
    [
        WAWPublicAuthResult.UNAUTHENTICATED,
        WAWPublicAuthResult.UNKNOWN,
        WAWPublicAuthResult.UNSUPPORTED,
    ],
)
def test_non_authenticated_results_never_admit(result: WAWPublicAuthResult) -> None:
    cache = WAWPublicAuthProbeCache()
    cache.record(_evidence(result=result))
    assert (
        cache.fresh(
            agent_type=AgentType.CLAUDE,
            runtime_host_installation_id=HOST_ID,
            runtime_host_installation_revision="2",
            executable_fingerprint=FINGERPRINT,
            now_monotonic=101.0,
        )
        is None
    )


def test_host_or_executable_rotation_invalidates_evidence() -> None:
    cache = WAWPublicAuthProbeCache()
    cache.record(_evidence())
    assert (
        cache.fresh(
            agent_type=AgentType.CLAUDE,
            runtime_host_installation_id="wri_" + "2" * 32,
            runtime_host_installation_revision="2",
            executable_fingerprint=FINGERPRINT,
            now_monotonic=101.0,
        )
        is None
    )
    assert (
        cache.fresh(
            agent_type=AgentType.CLAUDE,
            runtime_host_installation_id=HOST_ID,
            runtime_host_installation_revision="2",
            executable_fingerprint="b" * 64,
            now_monotonic=101.0,
        )
        is None
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"runtime_host_installation_id": "bad"},
        {"runtime_host_installation_revision": "01"},
        {"executable_fingerprint": "A" * 64},
        {"checked_at_monotonic": -1.0},
        {"checked_at_monotonic": math.nan},
        {"checked_at_monotonic": True},
    ],
)
def test_evidence_rejects_untrusted_values(changes: dict[str, object]) -> None:
    values = {
        "agent_type": AgentType.CLAUDE,
        "runtime_host_installation_id": HOST_ID,
        "runtime_host_installation_revision": "2",
        "executable_fingerprint": FINGERPRINT,
        "checked_at_monotonic": 100.0,
        "result": WAWPublicAuthResult.AUTHENTICATED,
    }
    values.update(changes)
    with pytest.raises(ValueError):
        WAWPublicAuthEvidence(**cast(dict[str, Any], values))


@pytest.mark.anyio
async def test_vendor_adapter_binds_exact_identity_and_maps_qualified_results(
    tmp_path: Path,
) -> None:
    adapter, port = _vendor_adapter(
        tmp_path,
        {
            AgentType.CLAUDE: (0, b"", b""),
            AgentType.CODEX: (17, b"unexpected", b""),
        },
    )
    cache = WAWPublicAuthProbeCache()
    claude = await cache.refresh_from_probe(
        adapter,
        agent_type=AgentType.CLAUDE,
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision="2",
        executable_fingerprint="a" * 64,
        checked_at_monotonic=100.0,
    )
    codex = await cache.refresh_from_probe(
        adapter,
        agent_type=AgentType.CODEX,
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision="2",
        executable_fingerprint="b" * 64,
        checked_at_monotonic=101.0,
    )

    assert claude.result is WAWPublicAuthResult.AUTHENTICATED
    assert codex.result is WAWPublicAuthResult.UNKNOWN
    assert port.calls == [AgentType.CLAUDE, AgentType.CODEX]
    assert (
        cache.fresh(
            agent_type=AgentType.CLAUDE,
            runtime_host_installation_id=HOST_ID,
            runtime_host_installation_revision="2",
            executable_fingerprint="a" * 64,
            now_monotonic=101.0,
        )
        == claude
    )


@pytest.mark.anyio
async def test_vendor_adapter_rejects_identity_drift_before_vendor_execution(
    tmp_path: Path,
) -> None:
    adapter, port = _vendor_adapter(
        tmp_path,
        {
            AgentType.CLAUDE: (0, b"", b""),
            AgentType.CODEX: (0, b"", b""),
        },
    )
    with pytest.raises(WAWPublicAuthProbeError, match="identity"):
        await adapter.probe(
            agent_type=AgentType.CLAUDE,
            runtime_host_installation_id=HOST_ID,
            runtime_host_installation_revision="2",
            executable_fingerprint="c" * 64,
            checked_at_monotonic=100.0,
        )
    assert port.calls == []


@pytest.mark.anyio
async def test_slow_older_probe_cannot_replace_newer_cached_evidence() -> None:
    release_old = asyncio.Event()

    class OrderedProbe:
        def __init__(self, result: WAWPublicAuthResult, *, wait: bool) -> None:
            self.result = result
            self.wait = wait

        async def probe(self, **request: Any) -> WAWPublicAuthEvidence:
            if self.wait:
                await release_old.wait()
            return WAWPublicAuthEvidence(result=self.result, **request)

    cache = WAWPublicAuthProbeCache()
    older = asyncio.create_task(
        cache.refresh_from_probe(
            OrderedProbe(WAWPublicAuthResult.UNAUTHENTICATED, wait=True),
            agent_type=AgentType.CLAUDE,
            runtime_host_installation_id=HOST_ID,
            runtime_host_installation_revision="2",
            executable_fingerprint=FINGERPRINT,
            checked_at_monotonic=100.0,
        )
    )
    newer = await cache.refresh_from_probe(
        OrderedProbe(WAWPublicAuthResult.AUTHENTICATED, wait=False),
        agent_type=AgentType.CLAUDE,
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision="2",
        executable_fingerprint=FINGERPRINT,
        checked_at_monotonic=101.0,
    )
    release_old.set()
    await older

    assert (
        cache.fresh(
            agent_type=AgentType.CLAUDE,
            runtime_host_installation_id=HOST_ID,
            runtime_host_installation_revision="2",
            executable_fingerprint=FINGERPRINT,
            now_monotonic=102.0,
        )
        == newer
    )
