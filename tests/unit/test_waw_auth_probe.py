from __future__ import annotations

import math
from typing import Any, cast

import pytest
from agentbox_core.waw import AgentType
from agentbox_runtime.waw_auth_probe import (
    WAWPublicAuthEvidence,
    WAWPublicAuthProbe,
    WAWPublicAuthProbeCache,
    WAWPublicAuthProbeError,
    WAWPublicAuthResult,
    validate_waw_public_auth_probe_evidence,
)

HOST_ID = "wri_" + "1" * 32
FINGERPRINT = "a" * 64


class _FakePublicAuthProbe:
    """Synthetic adapter; it never executes a vendor command or reads files."""

    def __init__(self, result: WAWPublicAuthResult) -> None:
        self._result = result

    def probe(
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


@pytest.mark.parametrize("result", list(WAWPublicAuthResult))
def test_public_auth_probe_protocol_and_evidence_binding(result: WAWPublicAuthResult) -> None:
    probe: WAWPublicAuthProbe = _FakePublicAuthProbe(result)
    evidence = probe.probe(
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


def test_public_auth_probe_rejects_identity_drift() -> None:
    evidence = _FakePublicAuthProbe(WAWPublicAuthResult.AUTHENTICATED).probe(
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


def test_cache_refreshes_from_bounded_probe_and_applies_freshness() -> None:
    cache = WAWPublicAuthProbeCache()
    evidence = cache.refresh_from_probe(
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


def test_probe_identity_drift_cannot_replace_existing_cache_entry() -> None:
    class DriftingProbe:
        def probe(
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
        cache.refresh_from_probe(
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
