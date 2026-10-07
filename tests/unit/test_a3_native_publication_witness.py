"""Pure fixture evidence/deadline checks; no child processes, sockets or AF_UNIX."""

from __future__ import annotations

import inspect
import io
import json
import threading
from types import SimpleNamespace
from typing import Any

import pytest
from a3_native_fixture import A3NativeFixture, _Child, _PublicationWitness


@pytest.mark.parametrize("role", ["api", "runtime"])
def test_publication_snapshot_is_fixed_bounded_scalar_copy(role: str) -> None:
    witness = _PublicationWitness(role)
    fields = _PublicationWitness.FIELDS[role]
    assert witness.snapshot() == dict.fromkeys(fields, 0)
    for field in fields:
        witness.add(field)
    snapshot = witness.snapshot()
    assert snapshot == dict.fromkeys(fields, 1)
    assert all(type(value) is int and 0 <= value <= 65535 for value in snapshot.values())
    assert json.loads(json.dumps(snapshot)) == snapshot
    snapshot[fields[0]] = 999
    assert witness.snapshot() == dict.fromkeys(fields, 1)


@pytest.mark.parametrize(
    "role,field",
    [(role, field) for role, fields in _PublicationWitness.FIELDS.items() for field in fields],
)
def test_every_publication_counter_overflow_latches_failure(role: str, field: str) -> None:
    witness = _PublicationWitness(role)
    witness._counts[field] = witness.LIMIT - 1
    witness.add(field)
    assert witness.snapshot()[field] == witness.LIMIT
    # Updating evidence never raises into the original native method. Reporting
    # a saturated value as successful coverage is nevertheless forbidden.
    witness.add(field)
    witness.add(field)
    with pytest.raises(RuntimeError, match="^fixture publication witness invalid$"):
        witness.snapshot()


@pytest.mark.parametrize("sequence", [0, 2, -1, True, "1", b"payload-canary", {"key": "canary"}])
def test_bad_publication_sequence_latches_without_exporting_values(sequence: object) -> None:
    witness = _PublicationWitness("api")
    witness.add("checked_matches", sequence=sequence)
    with pytest.raises(RuntimeError, match="^fixture publication witness invalid$"):
        witness.snapshot()


def test_unknown_field_and_mismatch_are_fixed_failures_without_payload_export() -> None:
    witness = _PublicationWitness("runtime")
    witness.add("ciphertext-key-identity-exception-value-canary")
    with pytest.raises(RuntimeError, match="^fixture publication witness invalid$"):
        witness.snapshot()
    assert all("canary" not in field for field in witness._counts)

    witness = _PublicationWitness("runtime")
    witness.add("precheck_active", matched=False)
    witness.add("precheck_active")
    assert witness._counts["precheck_active"] == 0
    with pytest.raises(RuntimeError, match="^fixture publication witness invalid$"):
        witness.snapshot()


def test_sequence_matching_is_contiguous_and_default_fixture_is_off() -> None:
    witness = _PublicationWitness("api")
    witness.add("ack_matches", sequence=1)
    witness.add("ack_matches", sequence=2)
    assert witness.snapshot()["ack_matches"] == 2
    assert inspect.signature(A3NativeFixture).parameters["publication_witnesses"].default is False


@pytest.mark.parametrize(
    "field,payload",
    [
        ("checked_matches", {"record_sequence": 1, "record_sha256": "a" * 64}),
        ("live_matches", {"observation_sequence": 0, "challenge": "7" * 32}),
    ],
)
def test_actual_reply_matches_scoped_request_without_export(
    field: str,
    payload: dict[str, object],
) -> None:
    witness, channel = _PublicationWitness("api"), object()
    with witness.reply_scope(field, channel, payload):
        assert witness.snapshot()[field] == 0  # Scope/None return alone is not receipt.
        encoded = json.dumps(witness.snapshot())
        assert all(value not in encoded for value in payload.values() if isinstance(value, str))
        witness.received_reply(field, channel, payload.copy())
        assert witness.snapshot()[field] == 1
    assert witness._pending_reply is None


@pytest.mark.parametrize("field", ["checked_matches", "live_matches"])
@pytest.mark.parametrize("change", ["sequence", "value", "extra", "channel", "kind", "boolean"])
def test_wrong_actual_native_reply_latches_failure(field: str, change: str) -> None:
    checked = field == "checked_matches"
    sequence_key = "record_sequence" if checked else "observation_sequence"
    value_key = "record_sha256" if checked else "challenge"
    payload: dict[str, object] = {
        sequence_key: 1 if checked else 0,
        value_key: "a" * (64 if checked else 32),
    }
    reply = payload.copy()
    witness, channel = _PublicationWitness("api"), object()
    if change == "sequence":
        reply[sequence_key] = 2
    elif change == "value":
        reply[value_key] = "b" * (64 if checked else 32)
    elif change == "extra":
        reply["unapproved"] = "ciphertext-identity-canary"
    elif change == "boolean":
        reply[sequence_key] = bool(payload[sequence_key])
    received_field = (
        ("live_matches" if checked else "checked_matches") if change == "kind" else field
    )
    with witness.reply_scope(field, channel, payload):
        witness.received_reply(received_field, object() if change == "channel" else channel, reply)
        # A subsequent correct reply cannot erase an earlier mismatch.
        witness.received_reply(field, channel, payload)
    assert witness._pending_reply is None
    with pytest.raises(RuntimeError, match="^fixture publication witness invalid$"):
        witness.snapshot()


def test_rpc_exception_preserves_identity_and_clears_native_reply_expectation() -> None:
    witness, channel = _PublicationWitness("api"), object()
    payload = {"record_sequence": 1, "record_sha256": "a" * 64}
    original = ValueError("private exception-value-canary")
    with (
        pytest.raises(ValueError) as raised,
        witness.reply_scope("checked_matches", channel, payload),
    ):
        raise original
    assert raised.value is original
    assert witness._pending_reply is None
    assert witness.snapshot()["checked_matches"] == 0
    witness.received_reply("checked_matches", channel, payload)
    with pytest.raises(RuntimeError, match="^fixture publication witness invalid$"):
        witness.snapshot()


def test_reply_expectation_copies_fixed_scalars_and_rejects_unbounded_input() -> None:
    witness, channel = _PublicationWitness("api"), object()
    payload: dict[str, object] = {"record_sequence": 1, "record_sha256": "a" * 64}
    with witness.reply_scope("checked_matches", channel, payload):
        payload["record_sha256"] = "b" * 64
        witness.received_reply(
            "checked_matches", channel, {"record_sequence": 1, "record_sha256": "a" * 64}
        )
    assert witness.snapshot()["checked_matches"] == 1
    payload["record_sha256"] = "large-payload-canary" * 8192
    with witness.reply_scope("checked_matches", channel, payload):
        assert witness._pending_reply is None
    with pytest.raises(RuntimeError, match="^fixture publication witness invalid$"):
        witness.snapshot()


def test_reentrant_reply_scope_latches_but_does_not_stop_original_work() -> None:
    witness, channel = _PublicationWitness("api"), object()
    payload = {"record_sequence": 1, "record_sha256": "a" * 64}
    progressed = False
    with (
        witness.reply_scope("checked_matches", channel, payload),
        witness.reply_scope("checked_matches", channel, payload),
    ):
        progressed = True
    assert progressed and witness._pending_reply is None
    with pytest.raises(RuntimeError, match="^fixture publication witness invalid$"):
        witness.snapshot()


def control_child(monkeypatch: pytest.MonkeyPatch, response: bytes) -> tuple[_Child, list[float]]:
    """In-memory control transport; no descriptor or process is allocated."""
    child = _Child.__new__(_Child)
    child.role = "api"
    child._lock = threading.Lock()
    output = SimpleNamespace(fileno=lambda: 123, readline=lambda size: response[:size])
    child.process = SimpleNamespace(stdin=io.BytesIO(), stdout=output)  # type: ignore[assignment]
    waits: list[float] = []

    def readable(
        read: list[object], write: list[object], error: list[object], timeout: float
    ) -> Any:
        waits.append(timeout)
        return read, write, error

    monkeypatch.setattr("a3_native_fixture.select.select", readable)
    monkeypatch.setattr("a3_native_fixture.os.read", lambda fd, size: response[:size])
    return child, waits


def test_default_control_timeout_stays_ten_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    child, waits = control_child(monkeypatch, b'{"ok":true}\n')
    assert child.call({"op": "status"}) == {"ok": True}
    assert waits == [10]


def test_expired_control_request_is_not_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    child, waits = control_child(monkeypatch, b'{"ok":true}\n')
    monkeypatch.setattr("a3_native_fixture.time.monotonic", lambda: 11.0)
    with pytest.raises(TimeoutError):
        child.call({"op": "status"}, deadline=11.0)
    assert waits == []
    assert child.process.stdin is not None
    assert child.process.stdin.tell() == 0


def test_late_decoded_control_result_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    child, waits = control_child(monkeypatch, b'{"ok":true}\n')
    now = [10.0]
    original_loads = json.loads

    def decode(value: bytes | bytearray) -> Any:
        result = original_loads(value)
        now[0] = 11.0
        return result

    monkeypatch.setattr("a3_native_fixture.time.monotonic", lambda: now[0])
    monkeypatch.setattr("a3_native_fixture.json.loads", decode)
    with pytest.raises(TimeoutError):
        child.call({"op": "publication-status"}, deadline=11.0)
    assert waits == [1.0]


def test_partial_control_line_does_not_renew_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    child, waits = control_child(monkeypatch, b'{"ok":')
    now = [10.0]

    def read(fd: int, size: int) -> bytes:
        now[0] = 11.0
        return b'{"ok":'

    monkeypatch.setattr("a3_native_fixture.time.monotonic", lambda: now[0])
    monkeypatch.setattr("a3_native_fixture.os.read", read)
    with pytest.raises(TimeoutError):
        child.call({"op": "publication-status"}, deadline=11.0)
    assert waits == [1.0]
