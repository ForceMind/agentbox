from __future__ import annotations

import math
from typing import Any, cast

import pytest
from agentbox_core.waw import AgentType
from agentbox_runtime.waw_auth_probe import (
    WAWPublicAuthEvidence,
    WAWPublicAuthProbeCache,
    WAWPublicAuthResult,
)

HOST_ID = "wri_" + "1" * 32
FINGERPRINT = "a" * 64


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
