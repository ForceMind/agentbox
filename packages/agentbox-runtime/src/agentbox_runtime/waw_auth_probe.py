"""Non-secret public vendor-auth probe adapter and freshness fence.

The nominal adapter delegates only to the separately reviewed bounded isolation
runner and retains metadata-only evidence. It never reads credential files or
exposes argv, environment, raw output, or credential material to callers.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from threading import RLock
from typing import Protocol, runtime_checkable

from agentbox_core.waw import AgentType, validate_runtime_host_installation_id

from agentbox_runtime.waw_process_profile import INTERACTIVE_PROFILE_CONSTANTS_V1
from agentbox_runtime.waw_vendor_probe import (
    WAWVendorProbeEvidence,
    WAWVendorProbeResult,
    WAWVendorProbeRunner,
)

_DECIMAL = re.compile(r"\A[1-9][0-9]{0,19}\Z")
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_VERSION = re.compile(r"\A[!-~]{1,96}\Z")
_MAX_U64 = 2**64 - 1


class WAWPublicAuthResult(StrEnum):
    """Closed result set returned by a public vendor auth/capability probe."""

    AUTHENTICATED = "AUTHENTICATED"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"


class WAWPublicAuthProbeError(ValueError):
    """A public auth probe returned evidence outside its requested tuple."""


@runtime_checkable
class WAWPublicAuthProbe(Protocol):
    """Runtime-owned adapter contract for a bounded, metadata-only probe.

    Implementations may call only the separately reviewed vendor-specific
    public status operation.  The interface carries no command, path, argv,
    environment, credential, or probe-output field.
    """

    async def probe(
        self,
        *,
        agent_type: AgentType,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: str,
        executable_fingerprint: str,
        checked_at_monotonic: float,
    ) -> WAWPublicAuthEvidence:
        """Return one bounded evidence record for the exact requested tuple."""


@dataclass(frozen=True)
class WAWVendorPublicAuthBinding:
    """Trusted installation/profile identity used by one vendor probe."""

    agent_type: AgentType
    runtime_host_installation_id: str
    runtime_host_installation_revision: str
    executable_fingerprint: str
    profile_id: str
    vendor_version: str

    def __post_init__(self) -> None:
        _validate_probe_request(
            agent_type=self.agent_type,
            runtime_host_installation_id=self.runtime_host_installation_id,
            runtime_host_installation_revision=self.runtime_host_installation_revision,
            executable_fingerprint=self.executable_fingerprint,
            checked_at_monotonic=0.0,
        )
        expected = INTERACTIVE_PROFILE_CONSTANTS_V1[self.agent_type.value]
        if self.profile_id != expected["profile_id"]:
            raise WAWPublicAuthProbeError("probe profile ID does not match AgentType")
        if type(self.vendor_version) is not str or _VERSION.fullmatch(self.vendor_version) is None:
            raise WAWPublicAuthProbeError("probe vendor version is invalid")


class WAWVendorPublicAuthProbeAdapter:
    """Adapt the bounded vendor runner to exact public-auth evidence."""

    def __init__(
        self,
        runner: WAWVendorProbeRunner,
        bindings: Mapping[AgentType, WAWVendorPublicAuthBinding],
    ) -> None:
        if type(runner) is not WAWVendorProbeRunner:
            raise TypeError("runner must be WAWVendorProbeRunner")
        if not isinstance(bindings, Mapping):
            raise TypeError("bindings must be a mapping")
        copied = dict(bindings)
        if set(copied) != set(AgentType):
            raise WAWPublicAuthProbeError("one public-auth binding per AgentType is required")
        for agent_type, binding in copied.items():
            if type(agent_type) is not AgentType or type(binding) is not WAWVendorPublicAuthBinding:
                raise WAWPublicAuthProbeError("public-auth binding is invalid")
            binding.__post_init__()
            if binding.agent_type is not agent_type:
                raise WAWPublicAuthProbeError("public-auth binding key does not match AgentType")
        self._runner = runner
        self._bindings = copied

    async def probe(
        self,
        *,
        agent_type: AgentType,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: str,
        executable_fingerprint: str,
        checked_at_monotonic: float,
    ) -> WAWPublicAuthEvidence:
        _validate_probe_request(
            agent_type=agent_type,
            runtime_host_installation_id=runtime_host_installation_id,
            runtime_host_installation_revision=runtime_host_installation_revision,
            executable_fingerprint=executable_fingerprint,
            checked_at_monotonic=checked_at_monotonic,
        )
        binding = self._bindings[agent_type]
        if (
            binding.runtime_host_installation_id != runtime_host_installation_id
            or binding.runtime_host_installation_revision != runtime_host_installation_revision
            or binding.executable_fingerprint != executable_fingerprint
        ):
            raise WAWPublicAuthProbeError("probe installation identity does not match binding")
        vendor = await self._runner.probe(
            agent_type=agent_type,
            observed_vendor_version=binding.vendor_version,
        )
        self._validate_vendor_evidence(vendor, binding)
        return WAWPublicAuthEvidence(
            agent_type=agent_type,
            runtime_host_installation_id=runtime_host_installation_id,
            runtime_host_installation_revision=runtime_host_installation_revision,
            executable_fingerprint=executable_fingerprint,
            checked_at_monotonic=checked_at_monotonic,
            result=WAWPublicAuthResult(vendor.result.value),
        )

    @staticmethod
    def _validate_vendor_evidence(
        evidence: WAWVendorProbeEvidence, binding: WAWVendorPublicAuthBinding
    ) -> None:
        if (
            type(evidence) is not WAWVendorProbeEvidence
            or evidence.agent_type is not binding.agent_type
            or evidence.profile_id != binding.profile_id
            or evidence.vendor_version != binding.vendor_version
            or type(evidence.result) is not WAWVendorProbeResult
        ):
            raise WAWPublicAuthProbeError("vendor probe evidence does not match binding")


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


def _validate_probe_request(
    *,
    agent_type: AgentType,
    runtime_host_installation_id: str,
    runtime_host_installation_revision: str,
    executable_fingerprint: str,
    checked_at_monotonic: float,
) -> None:
    if not isinstance(agent_type, AgentType):
        raise WAWPublicAuthProbeError("probe agent_type is invalid")
    try:
        validate_runtime_host_installation_id(runtime_host_installation_id)
    except ValueError as exc:
        raise WAWPublicAuthProbeError("probe Runtime installation ID is invalid") from exc
    if _DECIMAL.fullmatch(runtime_host_installation_revision) is None:
        raise WAWPublicAuthProbeError("probe Runtime installation revision is invalid")
    if int(runtime_host_installation_revision) > _MAX_U64:
        raise WAWPublicAuthProbeError("probe Runtime installation revision is invalid")
    if _DIGEST.fullmatch(executable_fingerprint) is None:
        raise WAWPublicAuthProbeError("probe executable fingerprint is invalid")
    if (
        isinstance(checked_at_monotonic, bool)
        or not isinstance(checked_at_monotonic, (int, float))
        or not math.isfinite(float(checked_at_monotonic))
        or checked_at_monotonic < 0
    ):
        raise WAWPublicAuthProbeError("probe monotonic timestamp is invalid")


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
            current = self._entries.get(evidence.agent_type)
            if current is not None:
                if evidence.checked_at_monotonic < current.checked_at_monotonic:
                    return
                if evidence.checked_at_monotonic == current.checked_at_monotonic:
                    if evidence != current:
                        # Equal samples cannot establish completion order. Drop
                        # conflicting evidence rather than choosing a winner.
                        self._entries.pop(evidence.agent_type, None)
                    return
            self._entries[evidence.agent_type] = evidence

    async def refresh_from_probe(
        self,
        probe: WAWPublicAuthProbe,
        *,
        agent_type: AgentType,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: str,
        executable_fingerprint: str,
        checked_at_monotonic: float,
    ) -> WAWPublicAuthEvidence:
        """Run one bounded adapter call and cache only matching evidence.

        The adapter receives the closed identity tuple and a monotonic sample;
        it has no command, path, argv, environment, credential, or output
        channel through this contract.  A mismatched result is rejected before
        it can replace an existing cache entry.
        """

        if not isinstance(probe, WAWPublicAuthProbe):
            raise TypeError("probe must implement WAWPublicAuthProbe")
        _validate_probe_request(
            agent_type=agent_type,
            runtime_host_installation_id=runtime_host_installation_id,
            runtime_host_installation_revision=runtime_host_installation_revision,
            executable_fingerprint=executable_fingerprint,
            checked_at_monotonic=checked_at_monotonic,
        )
        evidence = await probe.probe(
            agent_type=agent_type,
            runtime_host_installation_id=runtime_host_installation_id,
            runtime_host_installation_revision=runtime_host_installation_revision,
            executable_fingerprint=executable_fingerprint,
            checked_at_monotonic=checked_at_monotonic,
        )
        validated = validate_waw_public_auth_probe_evidence(
            evidence,
            agent_type=agent_type,
            runtime_host_installation_id=runtime_host_installation_id,
            runtime_host_installation_revision=runtime_host_installation_revision,
            executable_fingerprint=executable_fingerprint,
        )
        self.record(validated)
        return validated

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


class WAWCachedPublicAuthProbe:
    """Nominal production seam that live-refreshes and records every probe."""

    def __init__(
        self,
        adapter: WAWVendorPublicAuthProbeAdapter,
        cache: WAWPublicAuthProbeCache,
    ) -> None:
        if type(adapter) is not WAWVendorPublicAuthProbeAdapter:
            raise TypeError("adapter must be WAWVendorPublicAuthProbeAdapter")
        if type(cache) is not WAWPublicAuthProbeCache:
            raise TypeError("cache must be WAWPublicAuthProbeCache")
        self._adapter = adapter
        self._cache = cache

    @property
    def cache(self) -> WAWPublicAuthProbeCache:
        return self._cache

    async def probe(
        self,
        *,
        agent_type: AgentType,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: str,
        executable_fingerprint: str,
        checked_at_monotonic: float,
    ) -> WAWPublicAuthEvidence:
        return await self._cache.refresh_from_probe(
            self._adapter,
            agent_type=agent_type,
            runtime_host_installation_id=runtime_host_installation_id,
            runtime_host_installation_revision=runtime_host_installation_revision,
            executable_fingerprint=executable_fingerprint,
            checked_at_monotonic=checked_at_monotonic,
        )


__all__ = [
    "WAWCachedPublicAuthProbe",
    "WAWPublicAuthEvidence",
    "WAWPublicAuthProbe",
    "WAWPublicAuthProbeCache",
    "WAWPublicAuthProbeError",
    "WAWPublicAuthResult",
    "WAWVendorPublicAuthBinding",
    "WAWVendorPublicAuthProbeAdapter",
    "validate_waw_public_auth_probe_evidence",
]
