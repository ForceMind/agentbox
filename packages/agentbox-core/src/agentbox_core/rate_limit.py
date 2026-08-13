"""Restart-persistent login throttling with pseudonymous bounded buckets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil

from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from agentbox_core.clock import Clock
from agentbox_core.database import Database
from agentbox_core.errors import DatabaseNotReady, LoginRateLimited
from agentbox_core.models import LoginRateLimitBucket
from agentbox_core.security import keyed_digest


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int = 0


class LoginRateLimiter:
    """Bound failed attempts by account, source, and their combination.

    Bucket keys are HMAC-style digests and the values contain only a bounded
    rolling timestamp list.  SQLite ``BEGIN IMMEDIATE`` serializes check/update
    decisions across API processes and restarts.
    """

    def __init__(
        self,
        *,
        database: Database,
        secret: str,
        clock: Clock,
        limit: int,
        window_seconds: int,
        lock_seconds: int,
        max_rows: int,
    ) -> None:
        self._database = database
        self._secret = secret
        self._clock = clock
        self._limit = limit
        self._window = timedelta(seconds=window_seconds)
        self._lock = timedelta(seconds=lock_seconds)
        self._max_rows = max_rows

    def _keys(self, username: str, source: str) -> tuple[str, str, str]:
        account = keyed_digest(self._secret, "rate-account", username)
        client = keyed_digest(self._secret, "rate-source", source)
        combined = keyed_digest(self._secret, "rate-combined", f"{username}\0{source}")
        return account, client, combined

    def check(self, username: str, source: str) -> RateLimitDecision:
        now = self._clock.now()
        retry_after = 0
        try:
            with self._database.transaction() as session:
                session.execute(text("BEGIN IMMEDIATE"))
                self._delete_expired(session, now)
                keys = self._keys(username, source)
                existing = {
                    bucket.key_digest: bucket
                    for bucket in session.scalars(
                        select(LoginRateLimitBucket).where(
                            LoginRateLimitBucket.key_digest.in_(keys)
                        )
                    )
                }
                row_count = int(
                    session.scalar(select(func.count()).select_from(LoginRateLimitBucket)) or 0
                )
                missing_count = sum(key not in existing for key in keys)
                if missing_count and row_count + missing_count > self._max_rows:
                    return RateLimitDecision(
                        allowed=False,
                        retry_after=max(1, ceil(self._lock.total_seconds())),
                    )
                for bucket in existing.values():
                    if bucket.locked_until is not None and bucket.locked_until > now:
                        remaining = bucket.locked_until - now
                        if remaining > self._lock:
                            # A backwards wall-clock step must not turn a bounded
                            # lock into an arbitrarily long denial of service.
                            remaining = self._lock
                            bucket.locked_until = now + self._lock
                            bucket.updated_at = now
                        retry_after = max(retry_after, max(1, ceil(remaining.total_seconds())))
                        continue
                    attempts = self._pruned_attempts(bucket, now)
                    bucket.failure_timestamps = [value.isoformat() for value in attempts]
                    bucket.locked_until = None
                    bucket.updated_at = now
        except OperationalError as exc:
            # Authentication must fail closed and predictably when SQLite cannot
            # serialize the throttle decision inside its bounded busy timeout.
            raise DatabaseNotReady() from exc
        return RateLimitDecision(allowed=retry_after == 0, retry_after=retry_after)

    def register_failure(self, username: str, source: str) -> None:
        now = self._clock.now()
        try:
            with self._database.transaction() as session:
                session.execute(text("BEGIN IMMEDIATE"))
                self._delete_expired(session, now)
                keys = self._keys(username, source)
                existing = {
                    bucket.key_digest: bucket
                    for bucket in session.scalars(
                        select(LoginRateLimitBucket).where(
                            LoginRateLimitBucket.key_digest.in_(keys)
                        )
                    )
                }
                row_count = int(
                    session.scalar(select(func.count()).select_from(LoginRateLimitBucket)) or 0
                )
                missing_count = sum(key not in existing for key in keys)
                if row_count + missing_count > self._max_rows:
                    raise LoginRateLimited(retry_after=max(1, ceil(self._lock.total_seconds())))
                for key in keys:
                    bucket = existing.get(key)
                    if bucket is None:
                        bucket = LoginRateLimitBucket(
                            key_digest=key,
                            failure_timestamps=[],
                            locked_until=None,
                            updated_at=now,
                        )
                        session.add(bucket)
                    attempts = self._pruned_attempts(bucket, now)
                    attempts.append(now)
                    attempts = attempts[-self._limit :]
                    bucket.failure_timestamps = [value.isoformat() for value in attempts]
                    bucket.updated_at = now
                    if len(attempts) >= self._limit:
                        bucket.locked_until = now + self._lock
        except OperationalError as exc:
            raise DatabaseNotReady() from exc

    def register_success(self, username: str, source: str) -> None:
        account, _client, combined = self._keys(username, source)
        try:
            with self._database.transaction() as session:
                session.execute(text("BEGIN IMMEDIATE"))
                session.execute(
                    delete(LoginRateLimitBucket).where(
                        LoginRateLimitBucket.key_digest.in_((account, combined))
                    )
                )
        except OperationalError as exc:
            raise DatabaseNotReady() from exc

    def cleanup(self) -> int:
        """Delete expired buckets while retaining active spray-defense state."""
        now = self._clock.now()
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            return self._delete_expired(session, now)

    def _delete_expired(self, session: Session, now: datetime) -> int:
        cutoff = now - self._window - self._lock
        result = session.execute(
            delete(LoginRateLimitBucket).where(LoginRateLimitBucket.updated_at <= cutoff)
        )
        assert isinstance(result, CursorResult)
        return int(result.rowcount or 0)

    def _pruned_attempts(self, bucket: LoginRateLimitBucket, now: datetime) -> list[datetime]:
        cutoff = now - self._window
        parsed: list[datetime] = []
        raw_values: object = bucket.failure_timestamps
        if not isinstance(raw_values, list):
            return parsed
        for raw in raw_values[-self._limit :]:
            if not isinstance(raw, str):
                continue
            try:
                value = datetime.fromisoformat(raw)
            except ValueError:
                continue
            if value > now:
                # A backwards wall-clock jump must not erase recent failures
                # and reopen the authentication gate. Clamp future-looking
                # values to the observed time; expiry remains bounded.
                value = now
            if cutoff < value:
                parsed.append(value)
        return parsed
