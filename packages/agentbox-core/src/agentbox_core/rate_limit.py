"""Deterministic in-process login throttling with pseudonymous bucket keys."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from agentbox_core.clock import Clock
from agentbox_core.security import keyed_digest


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int = 0


class LoginRateLimiter:
    """Bound failed login attempts by account, source, and their combination.

    State intentionally lives only in the API process for Phase 3. A restart
    clears buckets; this limitation is documented and the interface permits a
    durable replacement without changing authentication behavior.
    """

    def __init__(
        self,
        *,
        secret: str,
        clock: Clock,
        limit: int,
        window_seconds: int,
        lock_seconds: int,
    ) -> None:
        self._secret = secret
        self._clock = clock
        self._limit = limit
        self._window = timedelta(seconds=window_seconds)
        self._lock = timedelta(seconds=lock_seconds)
        self._attempts: dict[str, deque[datetime]] = defaultdict(deque)
        self._locked_until: dict[str, datetime] = {}

    def _keys(self, username: str, source: str) -> tuple[str, str, str]:
        account = keyed_digest(self._secret, "rate-account", username)
        client = keyed_digest(self._secret, "rate-source", source)
        combined = keyed_digest(self._secret, "rate-combined", f"{username}\0{source}")
        return account, client, combined

    def check(self, username: str, source: str) -> RateLimitDecision:
        now = self._clock.now()
        retry_after = 0
        for key in self._keys(username, source):
            locked_until = self._locked_until.get(key)
            if locked_until is not None and locked_until > now:
                retry_after = max(retry_after, int((locked_until - now).total_seconds()) + 1)
            elif locked_until is not None:
                self._locked_until.pop(key, None)
                self._attempts.pop(key, None)
        return RateLimitDecision(allowed=retry_after == 0, retry_after=retry_after)

    def register_failure(self, username: str, source: str) -> None:
        now = self._clock.now()
        cutoff = now - self._window
        for key in self._keys(username, source):
            attempts = self._attempts[key]
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            attempts.append(now)
            if len(attempts) >= self._limit:
                self._locked_until[key] = now + self._lock

    def register_success(self, username: str, source: str) -> None:
        account, _client, combined = self._keys(username, source)
        for key in (account, combined):
            self._attempts.pop(key, None)
            self._locked_until.pop(key, None)
