"""Exact-owner accounting for opaque, encoded browser INPUT frames.

Tokens are process-local capabilities.  They are never serialized, logged or
included in a wire object; a redacted repr prevents accidental payload/identity
disclosure while tests can still inspect aggregate accounting.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from agentbox_protocol.abws import FrameType

INPUT_BUDGET_LIMIT = 65536


class InputBudgetOwner(StrEnum):
    NATIVE_READY = "native-ready"
    BROWSER_DELIVERY = "browser-delivery"
    RELAY_RUNTIME_PENDING = "relay-runtime-pending"
    RUNTIME_SEND_INFLIGHT = "runtime-send-inflight"


class InputBudgetError(RuntimeError):
    """A fixed diagnostic which contains no token, identity or frame bytes."""

    def __init__(self) -> None:
        super().__init__("WAW INPUT budget violation")


class InputBudgetOverflow(InputBudgetError):
    """The first encoded-byte ceiling violation for this attachment."""


class InputBudgetToken:
    """Opaque identity-bound credit; mutation is owned by ``InputBudget``."""

    __slots__ = (
        "_attachment_id",
        "_budget_id",
        "_connection_id",
        "_live",
        "_owner",
        "_runtime_epoch",
        "_serial",
        "_size",
    )

    def __init__(
        self,
        *,
        budget_id: object,
        connection_id: object,
        attachment_id: str,
        runtime_epoch: str,
        serial: int,
        size: int,
        owner: InputBudgetOwner,
    ) -> None:
        self._budget_id = budget_id
        self._connection_id = connection_id
        self._attachment_id = attachment_id
        self._runtime_epoch = runtime_epoch
        self._serial = serial
        self._size = size
        self._owner = owner
        self._live = True

    @property
    def size(self) -> int:
        return self._size

    @property
    def owner(self) -> InputBudgetOwner:
        return self._owner

    @property
    def live(self) -> bool:
        return self._live

    def __repr__(self) -> str:
        return "<InputBudgetToken redacted>"


@dataclass(frozen=True, repr=False)
class BrowserDelivery:
    """A complete browser message and its optional process-local INPUT credit."""

    wire_bytes: bytes = field(repr=False)
    input_token: InputBudgetToken | None = field(default=None, repr=False)

    def __repr__(self) -> str:
        return "<BrowserDelivery redacted>"


def is_encoded_input(raw: bytes | bytearray | memoryview) -> bool:
    """Recognize the fixed ABWS kind byte without allocating or decoding."""

    return len(raw) >= 6 and raw[5] == FrameType.INPUT


class InputBudget:
    """One connection/attachment/epoch encoded INPUT byte ledger."""

    def __init__(self, *, connection_id: object, attachment_id: str, runtime_epoch: str) -> None:
        if (
            connection_id is None
            or type(attachment_id) is not str
            or not attachment_id
            or type(runtime_epoch) is not str
            or not runtime_epoch
        ):
            raise InputBudgetError()
        self._budget_id = object()
        self._connection_id = connection_id
        self._attachment_id = attachment_id
        self._runtime_epoch = runtime_epoch
        self._tokens: dict[int, InputBudgetToken] = {}
        self._owner_bytes = {owner: 0 for owner in InputBudgetOwner}
        self._reserved_bytes = 0
        self._serial = 0
        self._closed = self._overflowed = False
        self._overflow_fence: Callable[[], None] | None = None
        self._lock = threading.RLock()
        self.peak_bytes = 0

    def __repr__(self) -> str:
        return "<InputBudget redacted>"

    @property
    def reserved_bytes(self) -> int:
        with self._lock:
            return self._reserved_bytes

    @property
    def live_count(self) -> int:
        with self._lock:
            return len(self._tokens)

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    @property
    def owner_bytes(self) -> dict[InputBudgetOwner, int]:
        with self._lock:
            return dict(self._owner_bytes)

    def assert_identity(
        self, *, connection_id: object, attachment_id: str, runtime_epoch: str
    ) -> None:
        with self._lock:
            if (
                connection_id is not self._connection_id
                or attachment_id != self._attachment_id
                or runtime_epoch != self._runtime_epoch
            ):
                raise InputBudgetError()

    def install_overflow_fence(self, fence: Callable[[], None]) -> None:
        if not callable(fence):
            raise InputBudgetError()
        with self._lock:
            if self._closed or self._overflow_fence is not None:
                raise InputBudgetError()
            self._overflow_fence = fence

    def reserve_native(self, size: int) -> InputBudgetToken:
        callback: Callable[[], None] | None = None
        with self._lock:
            if (
                self._closed
                or self._overflowed
                or type(size) is not int
                or not 1 <= size <= INPUT_BUDGET_LIMIT
            ):
                raise InputBudgetError()
            if self._reserved_bytes + size > INPUT_BUDGET_LIMIT:
                self._overflowed = True
                callback = self._overflow_fence
            else:
                self._serial += 1
                token = InputBudgetToken(
                    budget_id=self._budget_id,
                    connection_id=self._connection_id,
                    attachment_id=self._attachment_id,
                    runtime_epoch=self._runtime_epoch,
                    serial=self._serial,
                    size=size,
                    owner=InputBudgetOwner.NATIVE_READY,
                )
                self._tokens[token._serial] = token
                self._reserved_bytes += size
                self._owner_bytes[InputBudgetOwner.NATIVE_READY] += size
                self.peak_bytes = max(self.peak_bytes, self._reserved_bytes)
                return token
        if callback is not None:
            callback()
        raise InputBudgetOverflow()

    def transfer(
        self,
        token: InputBudgetToken,
        *,
        source: InputBudgetOwner,
        target: InputBudgetOwner,
    ) -> None:
        if source == target:
            raise InputBudgetError()
        with self._lock:
            self._validate(token, source)
            token._owner = target
            self._owner_bytes[source] -= token._size
            self._owner_bytes[target] += token._size
            self._check_invariant()

    def release(self, token: InputBudgetToken, *, owner: InputBudgetOwner) -> bool:
        with self._lock:
            if not self._matches(token) or not token._live or token._owner != owner:
                return False
            if self._tokens.get(token._serial) is not token:
                return False
            del self._tokens[token._serial]
            token._live = False
            self._reserved_bytes -= token._size
            self._owner_bytes[owner] -= token._size
            self._check_invariant()
            return True

    def close(self) -> None:
        """Invalidate this exact ledger; stale token releases stay idempotent."""

        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._overflow_fence = None
            for token in self._tokens.values():
                token._live = False
            self._tokens.clear()
            self._reserved_bytes = 0
            for owner in InputBudgetOwner:
                self._owner_bytes[owner] = 0

    def _matches(self, token: InputBudgetToken) -> bool:
        return (
            type(token) is InputBudgetToken
            and token._budget_id is self._budget_id
            and token._connection_id is self._connection_id
            and token._attachment_id == self._attachment_id
            and token._runtime_epoch == self._runtime_epoch
        )

    def _validate(self, token: InputBudgetToken, owner: InputBudgetOwner) -> None:
        if (
            not self._matches(token)
            or not token._live
            or token._owner != owner
            or self._tokens.get(token._serial) is not token
        ):
            raise InputBudgetError()

    def _check_invariant(self) -> None:
        if (
            self._reserved_bytes < 0
            or self._reserved_bytes > INPUT_BUDGET_LIMIT
            or any(value < 0 for value in self._owner_bytes.values())
            or sum(self._owner_bytes.values()) != self._reserved_bytes
            or sum(token._size for token in self._tokens.values()) != self._reserved_bytes
        ):
            raise InputBudgetError()
