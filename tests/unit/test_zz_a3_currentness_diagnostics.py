"""Observer safety tests run after the original suite; native coverage stays real."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

import a3_currentness_diagnostics as diagnosis
import pytest
from a3_currentness_diagnostics import CurrentnessTiming, duration_bucket


@pytest.mark.parametrize("error_type", [asyncio.CancelledError, KeyboardInterrupt, SystemExit])
def test_fixture_diagnostic_baseexception_preserves_original_exception(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
    error_type: type[BaseException],
) -> None:
    from test_a3_native_transport import (
        test_fixture_diagnostic_failure_preserves_original_exception,
    )

    test_fixture_diagnostic_failure_preserves_original_exception(
        monkeypatch, request, diagnostic_error_type=error_type
    )


@pytest.fixture
def probe(monkeypatch: pytest.MonkeyPatch) -> CurrentnessTiming:
    # Isolate callback-list tests, never collect or change actual GC policy.
    monkeypatch.setattr(diagnosis, "gc", SimpleNamespace(callbacks=[]))
    timing = CurrentnessTiming()
    timing.start()
    return timing


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        (-1, "unknown"),
        (0, "lt1ms"),
        (999_999, "lt1ms"),
        (1_000_000, "1to50ms"),
        (49_999_999, "1to50ms"),
        (50_000_000, "50to200ms"),
        (199_999_999, "50to200ms"),
        (200_000_000, "200to250ms"),
        (249_999_999, "200to250ms"),
        (250_000_000, "ge250ms"),
    ],
)
def test_duration_bucket_edges(duration: int, expected: str) -> None:
    assert duration_bucket(duration) == expected


def test_measure_preserves_exact_arguments_result_and_failure_only_output(
    probe: CurrentnessTiming,
) -> None:
    marker = object()
    calls: list[tuple[object, object]] = []

    def operation(argument: object, *, deadline_ns: object) -> object:
        calls.append((argument, deadline_ns))
        return marker

    wrapped = probe.measure("runtime-send", operation)
    assert wrapped(marker, deadline_ns=123) is marker
    assert calls == [(marker, 123)]
    assert probe.failures == []


def test_failure_timing_is_bounded_and_contains_no_exception_values(
    probe: CurrentnessTiming, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = RuntimeError("secret-canary-path-wire-facts")
    ticks = iter([(0, 0, 0, 0, 1), (300_000_000, 50_000, 210_000_000, 0, 1)] * 8)
    monkeypatch.setattr(probe, "_sample", lambda: next(ticks))

    def operation() -> None:
        raise original

    for _ in range(8):
        with pytest.raises(RuntimeError) as raised:
            probe.measure("checker-receive", operation)()
        assert raised.value is original
    assert (
        probe.failures
        == [("checker-receive", "ge250ms", "lt1ms", "200to250ms", "lt1ms", 0, False)] * 4
    )
    assert "secret-canary" not in repr(probe.failures)


@pytest.mark.parametrize("broken_part", ["_sample", "_record", "_gc_overlap"])
@pytest.mark.parametrize(
    "diagnostic_error_type", [AssertionError, asyncio.CancelledError, KeyboardInterrupt, SystemExit]
)
def test_probe_error_never_replaces_or_swallows_operation_error(
    probe: CurrentnessTiming,
    monkeypatch: pytest.MonkeyPatch,
    broken_part: str,
    diagnostic_error_type: type[BaseException],
) -> None:
    original = RuntimeError("original")

    def broken(*_args: object) -> Any:
        raise diagnostic_error_type("diagnostic failure")

    monkeypatch.setattr(probe, broken_part, broken)

    def operation() -> None:
        raise original

    with pytest.raises(RuntimeError) as raised:
        probe.measure("runtime-receive", operation)()
    assert raised.value is original
    if broken_part != "_record":
        assert probe.failures == [
            ("runtime-receive", "unknown", "unknown", "unknown", "unknown", 0, True)
        ]


@pytest.mark.parametrize("error_type", [asyncio.CancelledError, KeyboardInterrupt, SystemExit])
def test_sampling_baseexception_does_not_prevent_successful_native_operation(
    probe: CurrentnessTiming,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[BaseException],
) -> None:
    calls = 0
    marker = object()

    def broken() -> Any:
        raise error_type("diagnostic sampling failure")

    def operation() -> object:
        nonlocal calls
        calls += 1
        return marker

    monkeypatch.setattr(probe, "_sample", broken)
    assert probe.measure("runtime-send", operation)() is marker
    assert calls == 1 and not probe.failures


@pytest.mark.parametrize("error_type", [asyncio.CancelledError, KeyboardInterrupt, SystemExit])
def test_native_operation_baseexception_propagates_as_same_object(
    probe: CurrentnessTiming,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[BaseException],
) -> None:
    original = error_type("native operation cancellation")

    def broken(*_args: object) -> None:
        raise RuntimeError("diagnostic record must not replace native cancellation")

    def operation() -> None:
        raise original

    monkeypatch.setattr(probe, "_record", broken)
    with pytest.raises(error_type) as raised:
        probe.measure("runtime-receive", operation)()
    assert raised.value is original


def test_gc_spans_are_clipped_to_failed_operation_and_include_active_span(
    probe: CurrentnessTiming, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks = iter([0, 40_000_000, 60_000_000, 110_000_000, 140_000_000])
    monkeypatch.setattr(diagnosis, "monotonic_ns", lambda: next(ticks))
    probe._gc_event("start", {"generation": 0})
    probe._gc_event("stop", {"generation": 0})
    probe._gc_event("start", {"generation": 2})
    probe._gc_event("stop", {"generation": 2})
    probe._gc_event("start", {"generation": 1})
    assert probe._gc_overlap((20_000_000, 0, 0, 0, 1), (160_000_000, 0, 0, 2, 1)) == (
        "50to200ms",
        7,
        False,
    )
    assert probe._gc_overlap((110_000_000, 0, 0, 2, 1), (130_000_000, 0, 0, 2, 1)) == (
        "lt1ms",
        0,
        False,
    )


def test_gc_history_overflow_and_saturated_counter_are_explicit(
    probe: CurrentnessTiming, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks = iter(range(20))
    monkeypatch.setattr(diagnosis, "monotonic_ns", lambda: next(ticks))
    for _ in range(10):
        probe._gc_event("start", {"generation": 2})
        probe._gc_event("stop", {"generation": 2})
    assert len(probe._gc_events) == 8
    assert probe._gc_overlap((0, 0, 0, 0, 1), (20, 0, 0, 10, 1))[2]
    probe._gc_completed = 65535
    assert probe._gc_overlap((20, 0, 0, 65535, 1), (21, 0, 0, 65535, 1))[2]


@pytest.mark.parametrize(
    ("phase", "info"),
    [("stop", {"generation": 0}), ("start", {"generation": 3}), ("invalid", {})],
)
def test_missing_or_invalid_gc_evidence_reports_unknown(
    probe: CurrentnessTiming, phase: str, info: dict[str, int]
) -> None:
    probe._gc_event(phase, info)
    assert probe._gc_overlap((0, 0, 0, 0, 1), (1, 0, 0, 0, 1)) == ("unknown", 0, True)


@pytest.mark.parametrize(
    "error_type", [RuntimeError, asyncio.CancelledError, KeyboardInterrupt, SystemExit]
)
def test_gc_clock_failure_is_unknown_and_does_not_escape(
    probe: CurrentnessTiming, monkeypatch: pytest.MonkeyPatch, error_type: type[BaseException]
) -> None:
    def broken() -> int:
        raise error_type("secret-canary")

    monkeypatch.setattr(diagnosis, "monotonic_ns", broken)
    probe._gc_event("start", {"generation": 2})
    assert probe._gc_overlap((0, 0, 0, 0, 1), (1, 0, 0, 0, 1)) == ("unknown", 0, True)


def test_in_progress_gc_callback_cannot_produce_a_partial_snapshot(
    probe: CurrentnessTiming,
) -> None:
    probe._gc_revision = 1
    with pytest.raises(RuntimeError, match="incomplete diagnostic sample"):
        probe._sample()
    assert probe._gc_overlap((0, 0, 0, 0, 1), (1, 0, 0, 0, 1)) == ("unknown", 0, True)


@pytest.mark.parametrize("restart", [False, True])
def test_observer_epoch_change_during_operation_reports_unknown_gc(
    probe: CurrentnessTiming, restart: bool
) -> None:
    original = RuntimeError("original operation error")

    def operation() -> None:
        probe.close()
        if restart:
            probe.start()
        raise original

    with pytest.raises(RuntimeError) as raised:
        probe.measure("checker-receive", operation)()
    assert raised.value is original
    assert len(probe.failures) == 1
    assert probe.failures[0][4:] == ("unknown", 0, True)


def test_callback_cleanup_uses_identity_and_supports_repeated_enable_close(
    probe: CurrentnessTiming,
) -> None:
    class ForeignCallback:
        def __eq__(self, other: object) -> bool:
            raise AssertionError("must not compare callback values")

    foreign = ForeignCallback()
    callbacks = cast(list[Any], cast(Any, diagnosis).gc.callbacks)
    callbacks.insert(0, foreign)
    probe.start()
    assert sum(item is probe._callback for item in callbacks) == 1
    probe.close()
    probe.close()
    assert len(callbacks) == 1 and callbacks[0] is foreign
    probe.start()
    assert sum(item is probe._callback for item in callbacks) == 1
    probe.close()
    assert len(callbacks) == 1 and callbacks[0] is foreign


@pytest.mark.parametrize(
    "error_type", [RuntimeError, asyncio.CancelledError, KeyboardInterrupt, SystemExit]
)
def test_registration_failure_removes_only_own_callback(
    probe: CurrentnessTiming, monkeypatch: pytest.MonkeyPatch, error_type: type[BaseException]
) -> None:
    probe.close()

    class FailingList(list[Callable[..., Any]]):
        def append(self, callback: Callable[..., Any]) -> None:
            super().append(callback)
            raise error_type("registration failed after insertion")

    def foreign(*_args: object) -> None:
        pass

    callbacks = FailingList([foreign])
    monkeypatch.setattr(diagnosis, "gc", SimpleNamespace(callbacks=callbacks))
    with pytest.raises(error_type, match="registration failed"):
        probe.start()
    assert len(callbacks) == 1 and callbacks[0] is foreign
    assert not probe._enabled


@pytest.mark.parametrize("method", ["start", "close"])
@pytest.mark.parametrize(
    "error_type", [RuntimeError, asyncio.CancelledError, KeyboardInterrupt, SystemExit]
)
def test_client_start_and_close_failure_always_remove_diagnostic_callback(
    probe: CurrentnessTiming, method: str, error_type: type[BaseException]
) -> None:
    from test_a3_native_transport import Client

    original = error_type("original lifecycle error")

    async def broken(**_kwargs: object) -> None:
        raise original

    client = Client.__new__(Client)
    client.currentness_timing = probe
    setattr(client, f"_{method}", broken)
    coroutine = getattr(client, method)()
    try:
        # The immediate-raise coroutine needs no event loop or AF_UNIX self-pipe.
        with pytest.raises(error_type) as raised:
            coroutine.send(None)
        assert raised.value is original
    finally:
        coroutine.close()
    assert not any(callback is probe._callback for callback in cast(Any, diagnosis).gc.callbacks)


@pytest.mark.parametrize("method", ["start", "close"])
@pytest.mark.parametrize("error_type", [asyncio.CancelledError, KeyboardInterrupt, SystemExit])
def test_diagnostic_cleanup_baseexception_cannot_replace_native_lifecycle_error(
    probe: CurrentnessTiming,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    error_type: type[BaseException],
) -> None:
    from test_a3_native_transport import Client

    original = RuntimeError("native lifecycle failure")
    close = probe.close

    def diagnostic_close() -> None:
        close()
        raise error_type("diagnostic close failure")

    async def operation(**_kwargs: object) -> None:
        raise original

    monkeypatch.setattr(probe, "close", diagnostic_close)
    client = Client.__new__(Client)
    client.currentness_timing = probe
    setattr(client, f"_{method}", operation)
    coroutine = getattr(client, method)()
    try:
        with pytest.raises(RuntimeError) as raised:
            coroutine.send(None)
        assert raised.value is original
    finally:
        coroutine.close()
    assert not any(callback is probe._callback for callback in cast(Any, diagnosis).gc.callbacks)


def test_client_repeated_diagnosis_does_not_stack_wrappers_or_callbacks(
    probe: CurrentnessTiming,
) -> None:
    from test_a3_native_transport import Client

    probe.close()

    class Channel:
        def send(self, *_args: object, **_kwargs: object) -> None:
            pass

        receive = send
        wait_readable = send

    client = Client.__new__(Client)
    client.bundle = cast(
        Any, SimpleNamespace(current=lambda: None, _channels={"currentness": Channel()})
    )
    client.channels = cast(Any, {"currentness": Channel()})
    try:
        client.diagnose_currentness_failures()
        first = client.bundle._channels["currentness"].receive
        timing = client.currentness_timing
        assert timing is not None
        client.diagnose_currentness_failures()
        assert client.bundle._channels["currentness"].receive is first
        assert sum(item is timing._callback for item in cast(Any, diagnosis).gc.callbacks) == 1
        client.stop_currentness_diagnostics()
        client.diagnose_currentness_failures()
        assert client.bundle._channels["currentness"].receive is first
        assert sum(item is timing._callback for item in cast(Any, diagnosis).gc.callbacks) == 1
    finally:
        client.stop_currentness_diagnostics()
