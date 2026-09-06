"""Deterministic, test-only controls for composed WAW failure tests.

These helpers deliberately have no environment-variable, network, filesystem,
or production-code integration.  Tests opt in by passing an instance directly
to the component under test.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import cast


class CheckpointPlanError(RuntimeError):
    """A test reached checkpoints in an order different from its declared plan."""


class CheckpointFailure(RuntimeError):
    """A test-directed checkpoint failure."""


class ManualPromiseState(StrEnum):
    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"


class AdmissionCheckpoint(StrEnum):
    TICKET_RESERVED = "admission.ticket_reserved"
    RUNTIME_PREPARED = "admission.runtime_prepared"
    KEY_ATTEST_PUBLISHED = "admission.key_attest_published"
    PREPARED_AUDIT_PERSISTED = "admission.prepared_audit_persisted"
    READY_RECEIVED = "admission.ready_received"
    COMMIT_SENT = "admission.commit_sent"
    COMMIT_ACKED = "admission.commit_acked"
    ADMITTED_AUDIT_PERSISTED = "admission.admitted_audit_persisted"


class StreamCheckpoint(StrEnum):
    INPUT_PUBLISHED = "stream.input_published"
    OUTPUT_PUBLICATION_PENDING = "stream.output_publication_pending"
    RESIZE_PENDING = "stream.resize_pending"
    HEARTBEAT_PENDING = "stream.heartbeat_pending"


class ApplicationCheckpoint(StrEnum):
    API_RESTART = "application.api_restart"
    RUNTIME_RESTART = "application.runtime_restart"
    SHUTDOWN_DRAIN = "application.shutdown_drain"


class StopCheckpoint(StrEnum):
    DETACH_PENDING = "stop.detach_pending"
    STOP_PENDING = "stop.stop_pending"


class BrowserLifecycleCheckpoint(StrEnum):
    PAGEHIDE = "browser.pagehide"
    FREEZE = "browser.freeze"
    PROVIDER_LOSS = "browser.provider_loss"


CheckpointName = (
    AdmissionCheckpoint
    | StreamCheckpoint
    | ApplicationCheckpoint
    | StopCheckpoint
    | BrowserLifecycleCheckpoint
)


class ManualPromise:
    """A cancellation-safe, void-only test gate.

    Gates intentionally carry neither caller values nor arbitrary exception
    objects.  That keeps rc7 orchestration from retaining test plaintext,
    tickets or provider errors after a scenario reaches its fence.
    """

    def __init__(self) -> None:
        self._state = ManualPromiseState.PENDING
        self._waiters: set[asyncio.Future[None]] = set()

    @property
    def state(self) -> ManualPromiseState:
        return self._state

    @property
    def settled(self) -> bool:
        return self._state is not ManualPromiseState.PENDING

    async def wait(self) -> None:
        if self._state is ManualPromiseState.RESOLVED:
            return
        if self._state is ManualPromiseState.FAILED:
            raise CheckpointFailure("checkpoint gate failed")

        waiter: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._waiters.add(waiter)
        try:
            # Shield prevents task cancellation from cancelling shared control state.
            return await asyncio.shield(waiter)
        finally:
            self._waiters.discard(waiter)

    def resolve(self) -> bool:
        if self.settled:
            return False
        self._state = ManualPromiseState.RESOLVED
        for waiter in tuple(self._waiters):
            if not waiter.done():
                waiter.set_result(None)
        return True

    def fail(self) -> bool:
        if self.settled:
            return False
        self._state = ManualPromiseState.FAILED
        for waiter in tuple(self._waiters):
            if not waiter.done():
                waiter.set_exception(CheckpointFailure("checkpoint gate failed"))
        return True


@dataclass(frozen=True)
class CheckpointSpec:
    """One required checkpoint arrival, in exact declared order."""

    name: CheckpointName


@dataclass
class CheckpointPlan:
    """A named, sequential async checkpoint plan for one test scenario."""

    checkpoints: tuple[CheckpointSpec, ...]
    arrived: list[CheckpointName] = field(default_factory=list, init=False)
    released: list[CheckpointName] = field(default_factory=list, init=False)
    departed: list[CheckpointName] = field(default_factory=list, init=False)
    _gates: list[ManualPromise] = field(default_factory=list, init=False)
    _reached: list[ManualPromise] = field(default_factory=list, init=False)
    _arrived: list[bool] = field(default_factory=list, init=False)
    _released: list[bool] = field(default_factory=list, init=False)
    _departed: list[bool] = field(default_factory=list, init=False)
    _next_index: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if type(self.checkpoints) is not tuple or not self.checkpoints:
            raise ValueError("checkpoint plan must contain at least one checkpoint")
        for spec in self.checkpoints:
            if type(spec) is not CheckpointSpec:
                raise TypeError("checkpoint plan entries must be CheckpointSpec")
            _require_checkpoint(spec.name)
        self._gates = [ManualPromise() for _ in self.checkpoints]
        self._reached = [ManualPromise() for _ in self.checkpoints]
        self._arrived = [False] * len(self.checkpoints)
        self._released = [False] * len(self.checkpoints)
        self._departed = [False] * len(self.checkpoints)

    @classmethod
    def single(cls, name: CheckpointName) -> CheckpointPlan:
        return cls((CheckpointSpec(name),))

    @classmethod
    def sequence(cls, *names: CheckpointName) -> CheckpointPlan:
        return cls(tuple(CheckpointSpec(name) for name in names))

    @property
    def complete(self) -> bool:
        return all(
            departed and gate.settled
            for departed, gate in zip(self._departed, self._gates, strict=True)
        )

    async def arrive(self, name: CheckpointName) -> None:
        index = self._claim(name)
        self._reached[index].resolve()
        try:
            await self._gates[index].wait()
        finally:
            self._departed[index] = True
            self.departed.append(self.checkpoints[index].name)

    async def observe(self, name: CheckpointName, *, occurrence: int = 1) -> None:
        index = self._index_for(name, occurrence)
        await self._reached[index].wait()

    def release(self, name: CheckpointName, *, occurrence: int = 1) -> bool:
        index = self._index_for(name, occurrence)
        self._require_arrived(index)
        released = self._gates[index].resolve()
        if released:
            self._released[index] = True
            self.released.append(self.checkpoints[index].name)
        return released

    def fail(
        self,
        name: CheckpointName,
        *,
        occurrence: int = 1,
    ) -> bool:
        index = self._index_for(name, occurrence)
        self._require_arrived(index)
        failed = self._gates[index].fail()
        if failed:
            self._released[index] = True
            self.released.append(self.checkpoints[index].name)
        return failed

    def assert_complete(self) -> None:
        if not self.complete:
            remaining = ", ".join(
                spec.name
                for index, spec in enumerate(self.checkpoints)
                if not self._departed[index] or not self._gates[index].settled
            )
            raise CheckpointPlanError(
                f"checkpoint plan incomplete; not departed or unsettled: {remaining}"
            )

    def _claim(self, name: CheckpointName) -> int:
        _require_checkpoint(name)
        if self.complete:
            raise CheckpointPlanError(f"unexpected checkpoint after plan completion: {name}")
        if self._next_index == len(self.checkpoints):
            raise CheckpointPlanError(f"unexpected checkpoint after plan arrival: {name}")
        index = self._next_index
        expected = self.checkpoints[index].name
        if name != expected:
            raise CheckpointPlanError(f"checkpoint order mismatch: expected {expected}, got {name}")
        self._next_index += 1
        self._arrived[index] = True
        self.arrived.append(name)
        return index

    def _index_for(self, name: CheckpointName, occurrence: int) -> int:
        _require_checkpoint(name)
        if type(occurrence) is not int or occurrence < 1:
            raise ValueError("checkpoint occurrence must be at least one")
        matched = [index for index, spec in enumerate(self.checkpoints) if spec.name == name]
        if len(matched) < occurrence:
            raise CheckpointPlanError(f"checkpoint is not in plan: {name}#{occurrence}")
        return matched[occurrence - 1]

    def _require_arrived(self, index: int) -> None:
        if not self._arrived[index]:
            raise CheckpointPlanError("checkpoint has not arrived")


_CHECKPOINT_ENUMS = (
    AdmissionCheckpoint,
    StreamCheckpoint,
    ApplicationCheckpoint,
    StopCheckpoint,
    BrowserLifecycleCheckpoint,
)


def _require_checkpoint(value: object) -> CheckpointName:
    if type(value) not in _CHECKPOINT_ENUMS:
        raise CheckpointPlanError("checkpoint is not a closed rc7 checkpoint")
    return cast(CheckpointName, value)


@dataclass
class FakeMonotonicClock:
    """One non-decreasing integer-nanosecond clock for rc7 test timelines."""

    initial_ns: int = 0

    def __post_init__(self) -> None:
        if type(self.initial_ns) is not int or self.initial_ns < 0:
            raise ValueError("monotonic clock must start non-negative")
        self._now_ns = self.initial_ns

    def nanoseconds(self) -> int:
        return self._now_ns

    def seconds(self) -> float:
        return self._now_ns / 1_000_000_000

    def advance_ns(self, amount: int) -> int:
        if type(amount) is not int or amount < 0:
            raise ValueError("monotonic clock cannot advance backwards")
        self._now_ns += amount
        return self._now_ns

    def advance_to(self, value: int) -> int:
        if type(value) is not int or value < self._now_ns:
            raise ValueError("monotonic clock cannot move backwards")
        self._now_ns = value
        return self._now_ns


class PartialWritePortClosed(RuntimeError):
    """The synthetic write port was closed before a write could finish."""


@dataclass(frozen=True)
class PartialWrite:
    """One controlled write result, including its mandatory caller signal."""

    requested: int
    written: int

    @property
    def guard_recheck_required(self) -> bool:
        return self.written != self.requested


@dataclass(frozen=True)
class PartialWriteObservation:
    """Non-secret write metadata; bytes require explicit one-shot extraction."""

    requested: int
    written: int
    sha256: str


class PartialWritePort:
    """An in-memory async port that writes at most a configured byte prefix."""

    def __init__(self, *, maximum_write: int) -> None:
        if type(maximum_write) is not int or maximum_write < 1:
            raise ValueError("maximum_write must be at least one")
        self.maximum_write = maximum_write
        self.write_log: list[PartialWriteObservation] = []
        self._written: list[bytearray] = []
        self.closed = False
        self.blocked = False
        self._resume_gate = ManualPromise()

    def block(self) -> None:
        if self.closed:
            raise PartialWritePortClosed("cannot block a closed partial write port")
        if not self.blocked:
            self.blocked = True
            self._resume_gate = ManualPromise()

    def resume(self) -> bool:
        if not self.blocked:
            return False
        self.blocked = False
        return self._resume_gate.resolve()

    def close(self) -> None:
        self.closed = True
        self.blocked = False
        self._scrub_written()
        self.write_log.clear()
        self._resume_gate.resolve()

    async def write(self, data: bytes) -> PartialWrite:
        self._ensure_open()
        if self.blocked:
            await self._resume_gate.wait()
            self._ensure_open()
        written = min(len(data), self.maximum_write)
        prefix = data[:written]
        if prefix:
            self._written.append(bytearray(prefix))
        self.write_log.append(
            PartialWriteObservation(
                requested=len(data),
                written=written,
                sha256=hashlib.sha256(prefix).hexdigest(),
            )
        )
        return PartialWrite(requested=len(data), written=written)

    def take_written(self) -> tuple[bytes, ...]:
        """Return test bytes once, then zero the internal prefix copies."""

        values = tuple(bytes(value) for value in self._written)
        self._scrub_written()
        return values

    def assert_drained(self) -> None:
        if self._written:
            raise AssertionError("partial write port retained test bytes")

    def _scrub_written(self) -> None:
        for value in self._written:
            value[:] = b"\x00" * len(value)
        self._written.clear()

    def _ensure_open(self) -> None:
        if self.closed:
            raise PartialWritePortClosed("partial write port is closed")


@dataclass(frozen=True)
class ScriptedSocketWrite:
    """Non-secret result of one synchronous socket send attempt."""

    requested: int
    returned: int
    digest: str

    @property
    def guard_recheck_required(self) -> bool:
        return self.returned != self.requested


class ScriptedPartialWriteSocket:
    """Closed test-only synchronous socket script for real writer adapters.

    Each step is an exact byte count, ``BlockingIOError`` or another ``OSError``.
    No payload is retained in the public transcript.
    """

    def __init__(self, *steps: int | OSError) -> None:
        if any(type(step) is not int and not isinstance(step, OSError) for step in steps):
            raise TypeError("scripted partial socket steps must be integers or OSError instances")
        self._steps = list(steps)
        self.closed = False
        self.write_log: list[ScriptedSocketWrite] = []

    def send(self, data: bytes) -> int:
        if self.closed:
            raise PartialWritePortClosed("scripted partial socket is closed")
        if not self._steps:
            raise AssertionError("scripted partial socket has no remaining step")
        step = self._steps.pop(0)
        if isinstance(step, OSError):
            raise step
        if type(step) is not int or step < 0 or step > len(data):
            raise AssertionError("scripted partial socket step is outside requested bytes")
        self.write_log.append(
            ScriptedSocketWrite(
                requested=len(data),
                returned=step,
                digest=hashlib.sha256(data[:step]).hexdigest(),
            )
        )
        return step

    def close(self) -> None:
        self.closed = True
        self._steps.clear()
        self.write_log.clear()

    def assert_drained(self) -> None:
        if self._steps:
            raise AssertionError("scripted partial socket retained pending steps")
