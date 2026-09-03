"""Pure attachment lease-cleanup fence for the future WAW transport.

The fence models the volatile attachment lifecycle without opening sockets,
touching Runtime, or releasing a writer slot on an unproven cleanup result.
It is intentionally an adapter-free contract used by tests and later
transport implementations.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from threading import RLock

from agentbox_core.waw_recovery import RecoveryIdentity


class LeaseCleanupState(StrEnum):
    PENDING = "PENDING"
    ADMITTING = "ADMITTING"
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    DETACHING = "DETACHING"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    DETACHED = "DETACHED"
    CLOSED = "CLOSED"


class LeaseCleanupError(RuntimeError):
    """A bounded lease-cleanup state transition rejection."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class LeaseOwner:
    """Exact immutable attachment lease owner required for cleanup proof."""

    identity: RecoveryIdentity

    def __post_init__(self) -> None:
        if not isinstance(self.identity, RecoveryIdentity):
            raise LeaseCleanupError(
                "LEASE_OWNER_INVALID", "validated recovery identity is required"
            )

    @property
    def attachment_id(self) -> str:
        return self.identity.attachment_id

    @property
    def generation(self) -> int:
        return self.identity.generation

    @property
    def lease_number(self) -> int:
        return self.identity.lease_number


@dataclass(frozen=True)
class LeaseCleanupSnapshot:
    attachment_id: str
    generation: int
    lease_number: int
    state: LeaseCleanupState
    last_heartbeat: float
    stale_at: float
    grace_until: float
    detach_deadline: float | None
    cleanup_state: str | None

    @property
    def writer_slot_reserved(self) -> bool:
        """Only positive cleanup proof releases the writer slot."""

        return self.state is not LeaseCleanupState.DETACHED


class LeaseCleanupFence:
    """Serialize one attachment's stale/grace/detach cleanup lifecycle."""

    def __init__(
        self,
        *,
        clock: Callable[[], float],
        stale_after_seconds: float = 30.0,
        grace_seconds: float = 60.0,
        detach_timeout_seconds: float = 1.0,
    ) -> None:
        durations = (stale_after_seconds, grace_seconds, detach_timeout_seconds)
        if (
            any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value <= 0
                for value in durations
            )
            or grace_seconds < stale_after_seconds
        ):
            raise ValueError("lease cleanup durations must be positive")
        self._clock = clock
        self._stale_after = stale_after_seconds
        self._grace = grace_seconds
        self._detach_timeout = detach_timeout_seconds
        self._snapshot: LeaseCleanupSnapshot | None = None
        self._owner: LeaseOwner | None = None
        self._last_observed: float | None = None
        self._lock = RLock()

    @property
    def snapshot(self) -> LeaseCleanupSnapshot | None:
        with self._lock:
            return self._snapshot

    def begin(
        self, *, attachment_id: str, generation: int, lease_number: int, owner: LeaseOwner
    ) -> LeaseCleanupSnapshot:
        with self._lock:
            if not isinstance(owner, LeaseOwner):
                raise LeaseCleanupError("LEASE_OWNER_INVALID", "typed lease owner is required")
            if (
                owner.attachment_id != attachment_id
                or owner.generation != generation
                or owner.lease_number != lease_number
            ):
                raise LeaseCleanupError(
                    "LEASE_OWNER_MISMATCH", "lease owner does not match attachment"
                )
            if self._snapshot is not None and self._snapshot.writer_slot_reserved:
                raise LeaseCleanupError("ATTACHMENT_BUSY", "attachment cleanup is already reserved")
            now = self._observe_now(None)
            self._snapshot = LeaseCleanupSnapshot(
                attachment_id=attachment_id,
                generation=generation,
                lease_number=lease_number,
                state=LeaseCleanupState.ADMITTING,
                last_heartbeat=now,
                stale_at=now + self._stale_after,
                # The recovery grace window is measured from the last
                # heartbeat.  With the architecture defaults, a lease is
                # stale at +30s and expires at +60s (not +90s).
                grace_until=now + self._grace,
                detach_deadline=None,
                cleanup_state=None,
            )
            self._owner = owner
            return self._snapshot

    def commit_admission(self) -> LeaseCleanupSnapshot:
        with self._lock:
            snapshot = self._require()
            if snapshot.state is not LeaseCleanupState.ADMITTING:
                raise LeaseCleanupError("ATTACHMENT_STATE_INVALID", "attachment is not admitting")
            self._snapshot = replace(snapshot, state=LeaseCleanupState.ACTIVE)
            return self._snapshot

    def heartbeat(self, *, now: float | None = None) -> LeaseCleanupSnapshot:
        with self._lock:
            snapshot = self._advance(now)
            if snapshot.state is not LeaseCleanupState.ACTIVE:
                raise LeaseCleanupError("ATTACHMENT_STALE", "stale attachment cannot renew")
            current = self._last_observed
            assert current is not None
            self._snapshot = replace(
                snapshot,
                last_heartbeat=current,
                stale_at=current + self._stale_after,
                grace_until=current + self._grace,
            )
            return self._snapshot

    def request_detach(self, *, now: float | None = None) -> LeaseCleanupSnapshot:
        with self._lock:
            snapshot = self._advance(now)
            if snapshot.state in {
                LeaseCleanupState.DETACHING,
                LeaseCleanupState.DETACHED,
                LeaseCleanupState.CLOSED,
                LeaseCleanupState.RECONCILIATION_REQUIRED,
            }:
                return snapshot
            if snapshot.state not in {
                LeaseCleanupState.ACTIVE,
                LeaseCleanupState.STALE,
                LeaseCleanupState.EXPIRED,
            }:
                raise LeaseCleanupError("ATTACHMENT_STATE_INVALID", "attachment cannot detach")
            current = self._last_observed
            assert current is not None
            self._snapshot = replace(
                snapshot,
                state=LeaseCleanupState.DETACHING,
                detach_deadline=current + self._detach_timeout,
            )
            return self._snapshot

    def acknowledge_cleanup(
        self, *, cleanup_state: str, now: float | None = None, owner: LeaseOwner
    ) -> LeaseCleanupSnapshot:
        with self._lock:
            snapshot = self._advance(now)
            if snapshot.state not in {
                LeaseCleanupState.DETACHING,
                LeaseCleanupState.RECONCILIATION_REQUIRED,
            }:
                raise LeaseCleanupError(
                    "DETACH_ACK_UNEXPECTED", "cleanup acknowledgement is unexpected"
                )
            if self._owner is not None and owner != self._owner:
                raise LeaseCleanupError(
                    "DETACH_ACK_STALE", "cleanup proof does not match the exact attachment owner"
                )
            if cleanup_state != "ATTACH_PTY_CLOSED":
                raise LeaseCleanupError(
                    "DETACH_ACK_INVALID", "positive PTY cleanup proof is required"
                )
            self._snapshot = replace(
                snapshot,
                state=LeaseCleanupState.DETACHED,
                cleanup_state=cleanup_state,
                detach_deadline=None,
            )
            return self._snapshot

    def tick(self, *, now: float | None = None) -> LeaseCleanupSnapshot:
        with self._lock:
            return self._advance(now)

    def _advance(self, now: float | None) -> LeaseCleanupSnapshot:
        snapshot = self._require()
        current = self._observe_now(now)
        if snapshot.state is LeaseCleanupState.ACTIVE and current >= snapshot.stale_at:
            snapshot = replace(snapshot, state=LeaseCleanupState.STALE)
        if snapshot.state is LeaseCleanupState.STALE and current >= snapshot.grace_until:
            snapshot = replace(snapshot, state=LeaseCleanupState.EXPIRED)
        if (
            snapshot.state is LeaseCleanupState.DETACHING
            and snapshot.detach_deadline is not None
            and current >= snapshot.detach_deadline
        ):
            snapshot = replace(snapshot, state=LeaseCleanupState.RECONCILIATION_REQUIRED)
        self._snapshot = snapshot
        return snapshot

    def _observe_now(self, requested: float | None) -> float:
        current = self._clock() if requested is None else requested
        if (
            isinstance(current, bool)
            or not isinstance(current, (int, float))
            or not math.isfinite(float(current))
        ):
            raise LeaseCleanupError("CLOCK_INVALID", "lease cleanup clock must be finite")
        if self._last_observed is not None and current < self._last_observed:
            raise LeaseCleanupError("CLOCK_ROLLBACK", "lease cleanup clock moved backwards")
        self._last_observed = current
        return current

    def _require(self) -> LeaseCleanupSnapshot:
        if self._snapshot is None:
            raise LeaseCleanupError("ATTACHMENT_NOT_FOUND", "attachment cleanup record is absent")
        return self._snapshot


__all__ = [
    "LeaseCleanupError",
    "LeaseCleanupFence",
    "LeaseCleanupSnapshot",
    "LeaseCleanupState",
    "LeaseOwner",
]
