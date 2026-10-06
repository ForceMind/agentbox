"""Pure classifier fixtures; no socket creation or native qualification."""

from __future__ import annotations

import ast
import asyncio
import importlib
import select
import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import FunctionType, TracebackType
from typing import Any, cast

import a3_currentness_trace as trace
import pytest
import test_a3_native_transport as fixture
from agentbox_core import a3_native_io as io
from agentbox_protocol.a3_content import ContentError
from agentbox_protocol.a3_transport import NativeKind, encode_frame, facts_digest


class MemorySocket:
    def __init__(self) -> None:
        self.raw = encode_frame(
            NativeKind.CURRENT,
            1,
            {"facts_digest": facts_digest(fixture.FACTS), "challenge": "7" * 32},
        )
        self.closed = False

    def recv(self, length: int) -> bytes:
        part, self.raw = self.raw[:length], self.raw[length:]
        return part

    def shutdown(self, _how: int) -> None:
        self.closed = True

    def close(self) -> None:
        self.closed = True


def memory_channel() -> io.NativeChannel:
    channel = io.NativeChannel.__new__(io.NativeChannel)
    channel._socket = cast(Any, MemorySocket())
    channel._current = lambda: None
    channel._send_lock = threading.Lock()
    channel._receive_lock = threading.Lock()
    channel._send_sequence = channel._receive_sequence = 1
    channel._closed = False
    return channel


def memory_client(channel: object) -> fixture.Client:
    client = fixture.Client.__new__(fixture.Client)
    client.channels = {"currentness": cast(Any, channel)}
    client.facts, client.live, client.calls = fixture.FACTS, True, 0
    client.currentness_calls = 1
    client.currentness_failures = []
    client._currentness_failure_lock = threading.Lock()
    return client


def capture_timeout(
    monkeypatch: pytest.MonkeyPatch,
    expiry: int,
    *,
    configure: Callable[[io.NativeChannel], None] | None = None,
) -> tuple[fixture.Client, BaseException]:
    # Keep the actual checker/receive/_wait/_check code and codec. Only the clock,
    # select syscall and socket are controlled in this classifier-only fixture.
    channel = memory_channel()
    if configure is not None:
        configure(channel)
    client = memory_client(channel)
    ticks = iter([0] * expiry + [30_000_000_000])
    monkeypatch.setattr(time, "monotonic_ns", lambda: next(ticks))
    monkeypatch.setattr(select, "select", lambda *_args: ([channel._socket], [], []))
    errors: list[BaseException] = []
    original_record = client.record_currentness_failure

    def record(phase: Any, error: Exception, buckets: Any = None) -> None:
        errors.append(error)
        original_record(phase, error, buckets)

    monkeypatch.setattr(client, "record_currentness_failure", record)
    client.checker()
    assert len(errors) == 1
    return client, errors[0]


@pytest.mark.parametrize(
    "expiry,expected",
    [
        (1, "idle-readiness"),
        (2, "idle-readiness"),
        (4, "receive-wait-deadline-check"),
        (5, "pre-recv-deadline-check"),
        (8, "post-decode-deadline-check"),
    ],
)
def test_actual_whitelisted_call_paths(
    monkeypatch: pytest.MonkeyPatch, expiry: int, expected: str
) -> None:
    client, error = capture_timeout(monkeypatch, expiry)
    assert type(error) is ContentError and error.args == ("PATCH_TIMEOUT",)
    assert trace.classify_checker_timeout(error, fixture.Client.checker.__code__) == expected
    original = ContentError("PATCH_REVOKED")
    client.add_currentness_failure_note(original)
    assert f"Native fixture checker timeout site: {expected}" in original.__notes__


@pytest.mark.parametrize("failure_type", [asyncio.CancelledError, KeyboardInterrupt, SystemExit])
def test_existing_checker_recorder_baseexception_semantics_are_unchanged(
    monkeypatch: pytest.MonkeyPatch, failure_type: type[BaseException]
) -> None:
    original = ContentError("PATCH_TIMEOUT")
    events: list[str] = []

    class Channel:
        def wait_readable(self, _deadline: int) -> None:
            raise original

        def close(self) -> None:
            events.append("close")

    client = memory_client(Channel())
    diagnostic_error = failure_type("diagnostic-canary")

    def broken(*_args: Any) -> None:
        events.append("record")
        raise diagnostic_error

    monkeypatch.setattr(client, "record_currentness_failure", broken)
    with pytest.raises(failure_type) as raised:
        client.checker()
    assert raised.value is diagnostic_error
    assert events == ["record"]


@pytest.mark.parametrize("failure_type", [asyncio.CancelledError, KeyboardInterrupt, SystemExit])
def test_real_checker_baseexception_propagates_original(
    monkeypatch: pytest.MonkeyPatch, failure_type: type[BaseException]
) -> None:
    original = failure_type("original-canary")
    events: list[str] = []

    class Channel:
        def wait_readable(self, _deadline: int) -> None:
            raise original

        def close(self) -> None:
            events.append("close")

    client = memory_client(Channel())
    with pytest.raises(failure_type) as raised:
        client.checker()
    assert raised.value is original
    assert events == []
    assert client.currentness_failures == []


def test_guard_timeout_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def guard() -> None:
        raise ContentError("PATCH_TIMEOUT")

    _, error = capture_timeout(monkeypatch, 8, configure=lambda c: setattr(c, "_current", guard))
    assert trace.classify_checker_timeout(error, fixture.Client.checker.__code__) == "unknown"


def test_send_deadline_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    client, error = capture_timeout(monkeypatch, 10)
    assert type(error) is ContentError and error.args == ("PATCH_TIMEOUT",)
    assert client.calls == 1
    assert trace.classify_checker_timeout(error, fixture._CHECKER_CODE) == "unknown"


def test_equal_but_untrusted_code_object_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    original = io.NativeChannel._check
    copied = original.__code__.replace()
    assert copied == original.__code__ and copied is not original.__code__
    counterfeit = FunctionType(copied, original.__globals__)
    monkeypatch.setattr(io.NativeChannel, "_check", counterfeit)
    _, error = capture_timeout(monkeypatch, 1)
    assert trace.classify_checker_timeout(error, fixture.Client.checker.__code__) == "unknown"


def test_unraised_or_wrong_error_is_unknown() -> None:
    for error in (ContentError("PATCH_TIMEOUT"), ContentError("secret-canary"), RuntimeError()):
        assert trace.classify_checker_timeout(error, fixture.Client.checker.__code__) == "unknown"


def rebuild_trace(nodes: list[tuple[TracebackType, int]]) -> TracebackType | None:
    result = None
    for node, line in reversed(nodes):
        result = TracebackType(result, node.tb_frame, node.tb_lasti, line)
    return result


def trace_nodes(error: BaseException) -> list[tuple[TracebackType, int]]:
    nodes = []
    cursor = error.__traceback__
    while cursor is not None:
        nodes.append((cursor, cursor.tb_lineno))
        cursor = cursor.tb_next
    return nodes


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_each_exact_callsite_and_raise_site_is_required(
    monkeypatch: pytest.MonkeyPatch, index: int
) -> None:
    _, error = capture_timeout(monkeypatch, 4)
    nodes = trace_nodes(error)
    node, line = nodes[index]
    nodes[index] = node, line + 1
    error.__traceback__ = rebuild_trace(nodes)
    assert trace.classify_checker_timeout(error, fixture.Client.checker.__code__) == "unknown"


@pytest.mark.parametrize("change", ["missing-root", "missing-wait", "extra", "excessive"])
def test_only_complete_adjacent_bounded_chain_is_accepted(
    monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    _, error = capture_timeout(monkeypatch, 4)
    nodes = trace_nodes(error)
    if change == "missing-root":
        nodes = nodes[1:]
    elif change == "missing-wait":
        nodes = nodes[:2] + nodes[3:]
    elif change == "extra":
        nodes = nodes[:2] + nodes[1:]
    else:
        nodes = nodes + [nodes[-1]] * 20
    error.__traceback__ = rebuild_trace(nodes)
    assert trace.classify_checker_timeout(error, fixture.Client.checker.__code__) == "unknown"


def test_wrong_checker_code_and_spoofed_name_are_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, error = capture_timeout(monkeypatch, 4)
    copied = fixture.Client.checker.__code__.replace(co_name="checker")
    assert trace.classify_checker_timeout(error, copied) == "unknown"

    def counterfeit(*_args: Any) -> float:
        raise ContentError("PATCH_TIMEOUT")

    counterfeit.__name__ = "_check"
    counterfeit.__code__ = counterfeit.__code__.replace(
        co_name="_check", co_filename="sensitive-path-canary"
    )
    monkeypatch.setattr(io.NativeChannel, "_check", counterfeit)
    _, error = capture_timeout(monkeypatch, 1)
    assert trace.classify_checker_timeout(error, fixture.Client.checker.__code__) == "unknown"


def test_injected_cycle_is_bounded_without_following_other_frame_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Real TracebackType forbids cycles. A controlled metadata double tests the
    # walk bound even if traversal behaves unexpectedly; it never performs I/O.
    class Frame:
        f_code = io.NativeChannel._check.__code__

        def __getattr__(self, _name: str) -> Any:
            raise AssertionError("locals/back/path must not be inspected")

    class Cycle:
        tb_frame = Frame()
        tb_lineno = io.NativeChannel._check.__code__.co_firstlineno + 14
        reads = 0

        @property
        def tb_next(self) -> Cycle:
            self.reads += 1
            assert self.reads <= 8
            return self

    cycle = Cycle()

    class Error:
        args = ("PATCH_TIMEOUT",)
        __traceback__ = cycle

    monkeypatch.setattr(trace, "ContentError", Error)
    monkeypatch.setattr(trace, "TracebackType", Cycle)
    assert trace.classify_checker_timeout(cast(BaseException, Error()), fixture._CHECKER_CODE) == (
        "unknown"
    )
    assert cycle.reads == 8


@pytest.mark.parametrize("failure_type", [asyncio.CancelledError, KeyboardInterrupt, SystemExit])
def test_classifier_baseexception_is_unknown(
    monkeypatch: pytest.MonkeyPatch, failure_type: type[BaseException]
) -> None:
    def broken(*_args: Any) -> str:
        raise failure_type("sensitive-classifier-canary")

    monkeypatch.setattr(trace, "_classify", broken)
    assert trace.classify_checker_timeout(ContentError("PATCH_TIMEOUT"), fixture._CHECKER_CODE) == (
        "unknown"
    )


@pytest.mark.parametrize("failure_type", [asyncio.CancelledError, KeyboardInterrupt, SystemExit])
def test_failed_classifier_call_cannot_skip_checker_record_or_close(
    monkeypatch: pytest.MonkeyPatch, failure_type: type[BaseException]
) -> None:
    def broken(*_args: Any) -> str:
        raise failure_type("sensitive-classifier-canary")

    monkeypatch.setattr(fixture, "classify_checker_timeout", broken)
    client, error = capture_timeout(monkeypatch, 4)
    assert type(error) is ContentError and error.args == ("PATCH_TIMEOUT",)
    assert client.currentness_failures == [("fixture-checker", "PATCH_TIMEOUT", 0, 1, None)]
    assert client.channels["currentness"].closed
    original = ContentError("PATCH_REVOKED")
    client.add_currentness_failure_note(original)
    assert "Native fixture checker timeout site: unknown" in original.__notes__


@pytest.mark.parametrize("failure_type", [asyncio.CancelledError, KeyboardInterrupt, SystemExit])
def test_new_site_note_baseexception_does_not_escape(
    monkeypatch: pytest.MonkeyPatch, failure_type: type[BaseException]
) -> None:
    client = memory_client(object())
    original = ContentError("PATCH_REVOKED")
    original_add_note = original.add_note
    calls = 0

    def broken(note: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            original_add_note(note)
            return
        raise failure_type("sensitive-note-canary")

    monkeypatch.setattr(original, "add_note", broken)
    client.add_currentness_failure_note(original)
    assert original.args == ("PATCH_REVOKED",)
    assert calls == 2
    assert original.__notes__ == ["Native fixture currentness failures: []"]


@pytest.mark.parametrize("failure_type", [asyncio.CancelledError, KeyboardInterrupt, SystemExit])
def test_real_runtime_cancellation_propagates_original(
    failure_type: type[BaseException],
) -> None:
    original = failure_type("original-canary")

    class Channel:
        def send(self, **_kwargs: Any) -> None:
            raise original

        receive = send

    class Bundle:
        _channels = {"currentness": Channel()}

        def current(self) -> Any:
            raise original

    client = memory_client(object())
    client.bundle = cast(Any, Bundle())
    client.diagnose_currentness_failures()

    channel = cast(Any, client.bundle._channels["currentness"])
    for operation in (channel.send, channel.receive):
        with pytest.raises(failure_type) as raised:
            operation()
        assert raised.value is original
    with pytest.raises(failure_type) as raised:
        client.bundle.current()
    assert raised.value is original


def test_no_opt_in_or_success_calls_do_not_classify(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(fixture, "classify_checker_timeout", lambda *args: calls.append(args))

    class Channel:
        def wait_readable(self, _deadline: int) -> None:
            raise ContentError("PATCH_TIMEOUT")

        def close(self) -> None:
            pass

    client = memory_client(Channel())
    client.currentness_failures = None
    client.checker()
    assert calls == []
    assert not hasattr(client, "currentness_checker_site")

    class Bundle:
        _channels = {
            "currentness": cast(Any, type("IO", (), {"send": lambda: 1, "receive": lambda: 2}))
        }

        def current(self) -> Any:
            return fixture.FACTS

    client.bundle = cast(Any, Bundle())
    client.diagnose_currentness_failures()
    assert client.bundle.current() is fixture.FACTS
    channel = cast(Any, client.bundle._channels["currentness"])
    assert channel.send() == 1
    assert channel.receive() == 2
    assert calls == []


def test_failure_output_is_fixed_and_does_not_retain_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, error = capture_timeout(monkeypatch, 8)
    original_trace = error.__traceback__
    error.__cause__ = RuntimeError("sensitive-cause-canary")
    error.__context__ = RuntimeError("sensitive-context-canary")
    assert trace.classify_checker_timeout(error, fixture._CHECKER_CODE) == (
        "post-decode-deadline-check"
    )
    assert error.__traceback__ is original_trace
    assert client.currentness_checker_site == "post-decode-deadline-check"
    assert all(not isinstance(value, TracebackType) for value in vars(client).values())
    client.currentness_checker_site = "sensitive-path-body-id-canary"
    original = ContentError("PATCH_REVOKED")
    client.add_currentness_failure_note(original)
    assert original.__notes__[-1] == "Native fixture checker timeout site: unknown"
    assert "canary" not in repr(original.__notes__)


def test_unavailable_checker_site_and_sensitive_args_remain_unknown() -> None:
    client = memory_client(object())
    original = ContentError("PATCH_REVOKED")
    client.add_currentness_failure_note(original)
    assert original.__notes__[-1] == "Native fixture checker timeout site: unknown"

    class Sensitive:
        def __repr__(self) -> str:
            raise AssertionError("must not inspect body")

        def __eq__(self, _other: object) -> bool:
            raise AssertionError("must not inspect body")

    error = ContentError()
    error.args = (Sensitive(),)
    assert trace.classify_checker_timeout(error, fixture._CHECKER_CODE) == "unknown"


def test_trace_and_workflow_static_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    source = Path(trace.__file__).read_text()
    tree = ast.parse(source)
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not attributes & {
        "f_locals",
        "f_globals",
        "f_back",
        "co_filename",
        "__cause__",
        "__context__",
        "monotonic",
        "monotonic_ns",
        "collect",
        "settrace",
        "setprofile",
    }
    yaml = importlib.import_module("yaml")
    workflow = yaml.safe_load((root / ".github/workflows/backend.yml").read_text())
    assert workflow["jobs"]["quality"]["strategy"]["matrix"]["python-version"] == [
        "3.11",
        "3.12",
        "3.13.15",
    ]
    assert workflow["jobs"]["native"]["steps"][1]["with"]["python-version"] == "3.13"
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["quality"]["steps"][-1] == {"run": "pytest -o faulthandler_timeout=120"}
