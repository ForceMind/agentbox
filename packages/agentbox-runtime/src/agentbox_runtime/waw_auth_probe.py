"""Non-secret public vendor-auth probe evidence and freshness fence.

This module deliberately does not execute a vendor command or read credential
files.  A separately reviewed Runtime adapter supplies the result of a bounded
public probe; this cache only validates the evidence tuple and its short
monotonic freshness window before Start/Attach admission.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from threading import RLock
from typing import Protocol

from agentbox_core.waw import AgentType, validate_runtime_host_installation_id

_DECIMAL = re.compile(r"\A[1-9][0-9]{0,19}\Z")
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_MAX_U64 = 2**64 - 1


class WAWPublicAuthResult(StrEnum):
    """Closed result set returned by a public vendor auth/capability probe."""

    AUTHENTICATED = "AUTHENTICATED"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"


class WAWPublicAuthProbeError(ValueError):
    """A public auth probe returned evidence outside its requested tuple."""


class WAWPublicAuthProbe(Protocol):
    """Runtime-owned adapter contract for a bounded, metadata-only probe.

    Implementations may call only the separately reviewed vendor-specific
    public status operation.  The interface carries no command, path, argv,
    environment, credential, or probe-output field.
    """

    def probe(
        self,
        *,
        agent_type: AgentType,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: str,
        executable_fingerprint: str,
        checked_at_monotonic: float,
    ) -> WAWPublicAuthEvidence:
        """Return one bounded evidence record for the exact requested tuple."""


def validate_waw_public_auth_probe_evidence(
    evidence: WAWPublicAuthEvidence,
    *,
    agent_type: AgentType,
    runtime_host_installation_id: str,
    runtime_host_installation_revision: str,
    executable_fingerprint: str,
) -> WAWPublicAuthEvidence:
    """Reject adapter evidence that is not bound to the requested identity."""

    if not isinstance(evidence, WAWPublicAuthEvidence):
        raise WAWPublicAuthProbeError("probe evidence type is invalid")
    if (
        evidence.agent_type is not agent_type
        or evidence.runtime_host_installation_id != runtime_host_installation_id
        or evidence.runtime_host_installation_revision != runtime_host_installation_revision
        or evidence.executable_fingerprint != executable_fingerprint
    ):
        raise WAWPublicAuthProbeError("probe evidence identity does not match request")
    return evidence


@dataclass(frozen=True)
class WAWPublicAuthEvidence:
    """Metadata-only result; no probe output or credential material is retained."""

    agent_type: AgentType
    runtime_host_installation_id: str
    runtime_host_installation_revision: str
    executable_fingerprint: str
    checked_at_monotonic: float
    result: WAWPublicAuthResult

    def __post_init__(self) -> None:
        if not isinstance(self.agent_type, AgentType):
            raise ValueError("agent_type is invalid")
        validate_runtime_host_installation_id(self.runtime_host_installation_id)
        if _DECIMAL.fullmatch(self.runtime_host_installation_revision) is None:
            raise ValueError("runtime_host_installation_revision is invalid")
        if int(self.runtime_host_installation_revision) > _MAX_U64:
            raise ValueError("runtime_host_installation_revision is invalid")
        if _DIGEST.fullmatch(self.executable_fingerprint) is None:
            raise ValueError("executable_fingerprint is invalid")
        if (
            isinstance(self.checked_at_monotonic, bool)
            or not isinstance(self.checked_at_monotonic, (int, float))
            or not math.isfinite(float(self.checked_at_monotonic))
            or self.checked_at_monotonic < 0
        ):
            raise ValueError("checked_at_monotonic is invalid")
        if not isinstance(self.result, WAWPublicAuthResult):
            raise ValueError("result is invalid")


class WAWPublicAuthProbeCache:
    """Bounded in-memory freshness cache for one Runtime authority epoch."""

    def __init__(self, *, max_age_seconds: float = 30.0) -> None:
        if (
            isinstance(max_age_seconds, bool)
            or not isinstance(max_age_seconds, (int, float))
            or not math.isfinite(float(max_age_seconds))
            or max_age_seconds <= 0
        ):
            raise ValueError("max_age_seconds must be positive")
        self._max_age = float(max_age_seconds)
        self._entries: dict[AgentType, WAWPublicAuthEvidence] = {}
        self._lock = RLock()

    def record(self, evidence: WAWPublicAuthEvidence) -> None:
        if not isinstance(evidence, WAWPublicAuthEvidence):
            raise TypeError("evidence must be WAWPublicAuthEvidence")
        with self._lock:
            self._entries[evidence.agent_type] = evidence

    def fresh(
        self,
        *,
        agent_type: AgentType,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: str,
        executable_fingerprint: str,
        now_monotonic: float,
    ) -> WAWPublicAuthEvidence | None:
        """Return matching evidence only while it is fresh and authenticated."""

        if not isinstance(agent_type, AgentType):
            raise ValueError("agent_type is invalid")
        validate_runtime_host_installation_id(runtime_host_installation_id)
        if _DECIMAL.fullmatch(runtime_host_installation_revision) is None:
            raise ValueError("runtime_host_installation_revision is invalid")
        if _DIGEST.fullmatch(executable_fingerprint) is None:
            raise ValueError("executable_fingerprint is invalid")
        if (
            isinstance(now_monotonic, bool)
            or not isinstance(now_monotonic, (int, float))
            or not math.isfinite(float(now_monotonic))
            or now_monotonic < 0
        ):
            raise ValueError("now_monotonic is invalid")
        with self._lock:
            evidence = self._entries.get(agent_type)
            if evidence is None:
                return None
            age = float(now_monotonic) - evidence.checked_at_monotonic
            if (
                age < 0
                or age >= self._max_age
                or evidence.runtime_host_installation_id != runtime_host_installation_id
                or evidence.runtime_host_installation_revision != runtime_host_installation_revision
                or evidence.executable_fingerprint != executable_fingerprint
                or evidence.result is not WAWPublicAuthResult.AUTHENTICATED
            ):
                return None
            return evidence

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


__all__ = [
    "WAWPublicAuthEvidence",
    "WAWPublicAuthProbe",
    "WAWPublicAuthProbeCache",
    "WAWPublicAuthProbeError",
    "WAWPublicAuthResult",
    "validate_waw_public_auth_probe_evidence",
]
