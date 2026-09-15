"""Sealed production auth owner: probe, freshness cache, and lease custody.

One owner is sealed to one verified execution authority.  It constructs its
own public-auth probe cache and vendor adapter internally, serializes probes
per workspace, and guarantees that every borrowed transport lease is either
released through the full ceremony or poisoned, even across cancellation.
The owner retains metadata only; it never sees argv, environment, probe
output, credential material, or key material.
"""

from __future__ import annotations

import contextlib
import math
import threading
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from agentbox_core.waw import AgentType

from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_auth_lease import WAWAuthLeaseOwner, WAWSealedAuthLease
from agentbox_runtime.waw_auth_probe import (
    WAWPublicAuthEvidence,
    WAWPublicAuthProbeCache,
    WAWPublicAuthProbeError,
    WAWPublicAuthResult,
    WAWVendorPublicAuthBinding,
    WAWVendorPublicAuthProbeAdapter,
    _validate_probe_request,
    validate_waw_public_auth_probe_evidence,
)
from agentbox_runtime.waw_fixed_transport import WAWFixedTransport, WAWVerifiedExecutionAuthority
from agentbox_runtime.waw_process_inspector import FixedProcessIdentity
from agentbox_runtime.waw_vendor_probe import WAWVendorProbeProfile, WAWVendorProbeRunner

if TYPE_CHECKING:
    # Lazy at runtime: the native port module imports the fixed transport and
    # sealed lease modules this module already depends on.
    from agentbox_runtime.waw_auth_native_port import WAWNativeAuthProbePortFactory


def _poisoned_failure() -> RuntimeOperationError:
    return RuntimeOperationError(
        "WAW_AUTH_LEASE_POISONED",
        "Production auth owner is poisoned",
        category="conflict",
    )


class WAWProductionAuthOwner:
    """One authority-bound sealed production auth provider."""

    def __init__(
        self,
        authority: WAWVerifiedExecutionAuthority,
        *,
        runner: WAWVendorProbeRunner,
        bindings: Mapping[AgentType, WAWVendorPublicAuthBinding],
        lease_owner: WAWAuthLeaseOwner,
        clock: Callable[[], float],
        max_age_seconds: float = 30.0,
        native_port_factory: WAWNativeAuthProbePortFactory | None = None,
        profiles: Mapping[AgentType, WAWVendorProbeProfile] | None = None,
    ) -> None:
        if type(authority) is not WAWVerifiedExecutionAuthority:
            raise TypeError("verified execution authority is required")
        if type(runner) is not WAWVendorProbeRunner:
            raise TypeError("runner must be WAWVendorProbeRunner")
        if type(lease_owner) is not WAWAuthLeaseOwner:
            raise TypeError("lease owner must be WAWAuthLeaseOwner")
        if lease_owner.authority is not authority:
            raise WAWPublicAuthProbeError("auth lease owner is not bound to the authority")
        if lease_owner.poisoned or lease_owner.closed:
            raise WAWPublicAuthProbeError("auth lease owner is terminal")
        if not callable(clock):
            raise TypeError("clock must be callable")
        first = clock()
        second = clock()
        for sample in (first, second):
            if (
                isinstance(sample, bool)
                or not isinstance(sample, (int, float))
                or not math.isfinite(float(sample))
                or sample < 0
            ):
                raise WAWPublicAuthProbeError("auth owner clock is invalid")
        if float(second) < float(first):
            raise WAWPublicAuthProbeError("auth owner clock is not monotonic")
        adapter = WAWVendorPublicAuthProbeAdapter(runner, bindings)
        for agent_type, binding in bindings.items():
            if (
                binding.runtime_host_installation_id != authority.runtime_host_installation_id
                or binding.runtime_host_installation_revision
                != authority.runtime_host_installation_revision
                or binding.executable_fingerprint
                != authority.vendor_executable_fingerprint(agent_type)
            ):
                raise WAWPublicAuthProbeError(
                    "public-auth binding does not match the execution authority"
                )
        if (native_port_factory is None) != (profiles is None):
            raise WAWPublicAuthProbeError(
                "native port factory and probe profiles must be configured together"
            )
        native_profiles: dict[AgentType, WAWVendorProbeProfile] | None = None
        if native_port_factory is not None:
            from agentbox_runtime.waw_auth_native_port import (
                WAWNativeAuthProbePortFactory as _NativePortFactory,
            )

            if type(native_port_factory) is not _NativePortFactory:
                raise TypeError("native port factory must be WAWNativeAuthProbePortFactory")
            if native_port_factory.authority is not authority:
                raise WAWPublicAuthProbeError(
                    "native port factory is not bound to the execution authority"
                )
            if not isinstance(profiles, Mapping):
                raise TypeError("native probe profiles must be a mapping")
            copied_profiles = dict(profiles)
            # Same profile discipline as the bounded vendor runner.
            if set(copied_profiles) != set(AgentType):
                raise WAWPublicAuthProbeError("one native probe profile per AgentType is required")
            for profile_agent, profile in copied_profiles.items():
                if (
                    type(profile_agent) is not AgentType
                    or type(profile) is not WAWVendorProbeProfile
                ):
                    raise WAWPublicAuthProbeError("native probe profile entry is invalid")
                profile.__post_init__()
                if profile.agent_type is not profile_agent:
                    raise WAWPublicAuthProbeError(
                        "native probe profile key does not match AgentType"
                    )
            native_profiles = copied_profiles
        self._authority = authority
        self._adapter = adapter
        self._cache = WAWPublicAuthProbeCache(max_age_seconds=max_age_seconds)
        self._lease_owner = lease_owner
        self._clock = clock
        self._native_port_factory = native_port_factory
        self._profiles = native_profiles
        self._poisoned = False
        self._inflight: set[str] = set()
        self._lock = threading.RLock()

    @property
    def authority(self) -> WAWVerifiedExecutionAuthority:
        return self._authority

    @property
    def poisoned(self) -> bool:
        return self._poisoned

    def authenticated(self, identity: FixedProcessIdentity) -> bool:
        """Fail-closed cached gate used by the production native port."""

        try:
            if (
                self._poisoned
                or self._lease_owner.poisoned
                or self._lease_owner.closed
                or type(identity) is not FixedProcessIdentity
            ):
                return False
            if not self._authority.authorizes(identity):
                return False
            evidence = self._cache.fresh(
                agent_type=identity.agent_type,
                runtime_host_installation_id=self._authority.runtime_host_installation_id,
                runtime_host_installation_revision=(
                    self._authority.runtime_host_installation_revision
                ),
                executable_fingerprint=self._authority.vendor_executable_fingerprint(
                    identity.agent_type
                ),
                now_monotonic=self._clock(),
            )
        except Exception:
            return False
        return evidence is not None

    async def probe(
        self,
        *,
        agent_type: AgentType,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: str,
        executable_fingerprint: str,
        checked_at_monotonic: float,
    ) -> WAWPublicAuthEvidence:
        """Always-live probe; the executor requires an exact checked_at echo."""

        if self._poisoned or self._lease_owner.poisoned or self._lease_owner.closed:
            raise _poisoned_failure()
        return await self._cache.refresh_from_probe(
            self._adapter,
            agent_type=agent_type,
            runtime_host_installation_id=runtime_host_installation_id,
            runtime_host_installation_revision=runtime_host_installation_revision,
            executable_fingerprint=executable_fingerprint,
            checked_at_monotonic=checked_at_monotonic,
        )

    async def probe_with_lease(
        self,
        transport: WAWFixedTransport,
        *,
        agent_type: AgentType,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: str,
        executable_fingerprint: str,
        checked_at_monotonic: float,
    ) -> WAWPublicAuthEvidence:
        """Run one serialized probe while holding the transport auth lease.

        A cache hit still performs the complete release ceremony for the
        unused lease, and the returned cached evidence keeps its original
        ``checked_at_monotonic`` rather than the request sample.  On any
        failure or cancellation the lease is released; an uncertain release
        poisons the lease, transport, and lease owner while the original
        exception keeps propagating.
        """

        if self._poisoned or self._lease_owner.poisoned or self._lease_owner.closed:
            raise _poisoned_failure()
        _validate_probe_request(
            agent_type=agent_type,
            runtime_host_installation_id=runtime_host_installation_id,
            runtime_host_installation_revision=runtime_host_installation_revision,
            executable_fingerprint=executable_fingerprint,
            checked_at_monotonic=checked_at_monotonic,
        )
        if (
            runtime_host_installation_id != self._authority.runtime_host_installation_id
            or runtime_host_installation_revision
            != self._authority.runtime_host_installation_revision
            or executable_fingerprint != self._authority.vendor_executable_fingerprint(agent_type)
        ):
            raise WAWPublicAuthProbeError("probe request does not match the execution authority")
        if type(transport) is not WAWFixedTransport:
            raise TypeError("exact fixed transport is required")
        identity = transport.process_identity
        if identity.agent_type is not agent_type:
            raise WAWPublicAuthProbeError("probe agent_type does not match the transport identity")
        with self._lock:
            if identity.workspace_id in self._inflight:
                raise RuntimeOperationError(
                    "WAW_AUTH_PROBE_BUSY",
                    "A probe is already in flight for this workspace",
                    category="conflict",
                )
            self._inflight.add(identity.workspace_id)
        try:
            lease = self._lease_owner.borrow(transport)
            try:
                cached = self._cache.fresh(
                    agent_type=agent_type,
                    runtime_host_installation_id=runtime_host_installation_id,
                    runtime_host_installation_revision=runtime_host_installation_revision,
                    executable_fingerprint=executable_fingerprint,
                    now_monotonic=self._clock(),
                )
                if cached is not None:
                    self._lease_owner.release(lease)
                    return cached
                if self._native_port_factory is not None:
                    evidence = await self._probe_native(
                        lease,
                        agent_type=agent_type,
                        runtime_host_installation_id=runtime_host_installation_id,
                        runtime_host_installation_revision=runtime_host_installation_revision,
                        executable_fingerprint=executable_fingerprint,
                        checked_at_monotonic=checked_at_monotonic,
                    )
                else:
                    evidence = await self._adapter.probe(
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
                self._lease_owner.release(lease)
                self._cache.record(validated)
                return validated
            except BaseException:
                if lease._state == "OWNED":
                    with contextlib.suppress(BaseException):
                        self._lease_owner.release(lease)
                raise
        finally:
            with self._lock:
                self._inflight.discard(identity.workspace_id)

    async def _probe_native(
        self,
        lease: WAWSealedAuthLease,
        *,
        agent_type: AgentType,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: str,
        executable_fingerprint: str,
        checked_at_monotonic: float,
    ) -> WAWPublicAuthEvidence:
        """Run one bounded native probe through the sealed per-lease port.

        A fresh runner owns the fresh single-use port; the runner defaults
        carry the fixed 5.0s/0.25s/4096-byte budgets.  The port is closed
        after every outcome, and the vendor evidence is re-validated with the
        same discipline as the public adapter before the public mapping keeps
        the caller's monotonic echo.
        """

        if self._native_port_factory is None or self._profiles is None:
            raise WAWPublicAuthProbeError("native probe path is not configured")
        binding = self._adapter._bindings[agent_type]
        port = self._native_port_factory.port_for_lease(lease)
        try:
            runner = WAWVendorProbeRunner(self._profiles, port)
            vendor = await runner.probe(
                agent_type=agent_type,
                observed_vendor_version=binding.vendor_version,
            )
        finally:
            port.close()
        WAWVendorPublicAuthProbeAdapter._validate_vendor_evidence(vendor, binding)
        return WAWPublicAuthEvidence(
            agent_type=agent_type,
            runtime_host_installation_id=runtime_host_installation_id,
            runtime_host_installation_revision=runtime_host_installation_revision,
            executable_fingerprint=executable_fingerprint,
            checked_at_monotonic=checked_at_monotonic,
            result=WAWPublicAuthResult(vendor.result.value),
        )

    def _poison(self) -> None:
        """Enter the terminal poisoned state and poison the lease owner."""

        self._poisoned = True
        self._lease_owner._poison()


__all__ = [
    "WAWProductionAuthOwner",
]
