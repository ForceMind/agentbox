"""Opt-in, value-free timing observations for the real native fixture only."""

from __future__ import annotations

import gc
import threading
from collections import deque
from collections.abc import Callable
from contextlib import suppress
from time import monotonic_ns, process_time_ns, thread_time_ns
from typing import Any, Literal

Phase = Literal[
    "runtime-send", "runtime-receive", "checker-wait", "checker-receive", "checker-send"
]
Bucket = Literal["lt1ms", "1to50ms", "50to200ms", "200to250ms", "ge250ms", "unknown"]
Sample = tuple[int, int, int, int, int]
Failure = tuple[Phase, Bucket, Bucket, Bucket, Bucket, int, bool]


def duration_bucket(duration: int) -> Bucket:
    if duration < 0:
        return "unknown"
    if duration < 1_000_000:
        return "lt1ms"
    if duration < 50_000_000:
        return "1to50ms"
    if duration < 200_000_000:
        return "50to200ms"
    if duration < 250_000_000:
        return "200to250ms"
    return "ge250ms"


class CurrentnessTiming:
    """No exception/frame/object retention and no collection or scheduling policy."""

    def __init__(self) -> None:
        self.failures: list[Failure] = []
        self._failure_lock = threading.Lock()
        self._gc_events: deque[tuple[int, int, int]] = deque(maxlen=8)
        self._gc_active: tuple[int, int] | None = None
        self._gc_completed = 0
        self._gc_revision = 0
        self._observer_epoch = 0
        self._gc_valid = False
        self._enabled = False
        # Retain this exact object for identity-only cleanup and repeated start.
        self._callback = self._gc_event

    @property
    def available(self) -> bool:
        return self._enabled and self._gc_valid and self._observer_epoch < 65535

    def start(self) -> None:
        if self._enabled:
            return
        self._observer_epoch = min(self._observer_epoch + 1, 65535)
        self._gc_events.clear()
        self._gc_active = None
        self._gc_completed = 0
        self._gc_valid = True
        try:
            gc.callbacks.append(self._callback)
            self._enabled = True
        except BaseException:
            self._gc_valid = False
            with suppress(BaseException):
                self.close()
            raise

    def close(self) -> None:
        if self._enabled:
            self._observer_epoch = min(self._observer_epoch + 1, 65535)
        self._enabled = False
        # Never clear/replace the process list or invoke another callback's __eq__.
        for index in range(len(gc.callbacks) - 1, -1, -1):
            if gc.callbacks[index] is self._callback:
                del gc.callbacks[index]

    def _gc_event(self, phase: str, info: dict[str, int]) -> None:
        # No lock: a collection may start inside another diagnostic operation.
        self._gc_revision = (self._gc_revision + 1) % 131072
        try:
            now = monotonic_ns()
            generation = info.get("generation")
            if type(generation) is not int or generation not in (0, 1, 2):
                self._gc_valid = False
                return
            if phase == "start" and self._gc_active is None:
                self._gc_active = now, generation
            elif phase == "stop" and self._gc_active is not None:
                started, original_generation = self._gc_active
                self._gc_active = None
                if generation != original_generation or now < started:
                    self._gc_valid = False
                    return
                self._gc_events.append((started, now, generation))
                self._gc_completed = min(self._gc_completed + 1, 65535)
            else:
                self._gc_valid = False
        except BaseException:
            self._gc_valid = False
        finally:
            self._gc_revision = (self._gc_revision + 1) % 131072

    def _sample(self) -> Sample:
        revision = self._gc_revision
        epoch = self._observer_epoch
        sample = monotonic_ns(), thread_time_ns(), process_time_ns(), self._gc_completed, epoch
        if revision % 2 or revision != self._gc_revision or epoch != self._observer_epoch:
            raise RuntimeError("incomplete diagnostic sample")
        return sample

    def _gc_overlap(self, started: Sample, finished: Sample) -> tuple[Bucket, int, bool]:
        revision = self._gc_revision
        valid = self.available
        epoch = self._observer_epoch
        events = tuple(self._gc_events)
        completed = self._gc_completed
        active = self._gc_active
        if (
            not valid
            or finished[0] < started[0]
            or revision % 2
            or revision != self._gc_revision
            or started[4] != finished[4]
            or started[4] != epoch
            or epoch != self._observer_epoch
        ):
            return "unknown", 0, True
        truncated = completed == 65535 or completed - started[3] > len(events)
        if active is not None:
            events += ((active[0], finished[0], active[1]),)
        overlap, generations = 0, 0
        for begin, end, generation in events:
            duration = max(0, min(end, finished[0]) - max(begin, started[0]))
            if duration:
                overlap += duration
                generations |= 1 << generation
        return duration_bucket(overlap), generations, truncated

    def _record(self, phase: Phase, started: Sample | None) -> None:
        record: Failure = (phase, "unknown", "unknown", "unknown", "unknown", 0, True)
        with suppress(BaseException):
            finished = self._sample()
            if started is not None:
                overlap, generations, truncated = self._gc_overlap(started, finished)
                record = (
                    phase,
                    duration_bucket(finished[0] - started[0]),
                    duration_bucket(finished[1] - started[1]),
                    duration_bucket(finished[2] - started[2]),
                    overlap,
                    generations,
                    truncated,
                )
        with self._failure_lock:
            if len(self.failures) < 4:
                self.failures.append(record)

    def measure(self, phase: Phase, operation: Callable[..., Any]) -> Callable[..., Any]:
        def call(*args: Any, **kwargs: Any) -> Any:
            if not self._enabled:
                return operation(*args, **kwargs)
            started: Sample | None = None
            # Isolate diagnostic cancellation/errors without wrapping native work.
            with suppress(BaseException):
                started = self._sample()
            try:
                return operation(*args, **kwargs)
            except Exception:
                with suppress(BaseException):
                    self._record(phase, started)
                raise

        return call
