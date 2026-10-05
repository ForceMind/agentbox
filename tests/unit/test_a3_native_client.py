"""Strict test-client controls without sockets, browsers or changed A3 deadlines."""

from __future__ import annotations

from typing import Any

import pytest
from a3_native_client import NativeBrowser


class Wire:
    def __init__(self, inbound: bytes) -> None:
        self.inbound = bytearray(inbound)
        self.sent: list[bytes] = []

    def recv(self, size: int) -> bytes:
        # Exercise partial control/application headers and payloads.
        count = min(size, 1)
        result = bytes(self.inbound[:count])
        del self.inbound[:count]
        return result

    def sendall(self, raw: bytes) -> None:
        self.sent.append(raw)

    def settimeout(self, value: float) -> None:
        assert 0 < value <= 3


def browser(raw: bytes) -> tuple[NativeBrowser, Wire]:
    result = NativeBrowser.__new__(NativeBrowser)
    wire = Wire(raw)
    result.socket = wire  # type: ignore[assignment]
    return result, wire


def decode_control(raw: bytes) -> tuple[int, bytes]:
    assert raw[0] in {0x88, 0x8A} and raw[1] & 0x80
    length = raw[1] & 127
    assert length <= 125 and len(raw) == length + 6
    mask = raw[2:6]
    return raw[0], bytes(value ^ mask[i % 4] for i, value in enumerate(raw[6:]))


def test_standard_ping_gets_masked_exact_pong_before_application_reply() -> None:
    peer, wire = browser(b"\x89\x03abc\x82\x04A3CR")
    assert peer.receive() == b"A3CR"
    assert [decode_control(raw) for raw in wire.sent] == [(0x8A, b"abc")]


def test_unsolicited_bounded_pong_does_not_enter_crypto_transcript() -> None:
    peer, wire = browser(b"\x8a\x01x\x82\x02ok")
    assert peer.receive() == b"ok" and wire.sent == []


def test_close_control_is_echoed_then_reported_as_terminal() -> None:
    peer, wire = browser(b"\x88\x02\x03\xe8")
    with pytest.raises(EOFError):
        peer.receive()
    assert decode_control(wire.sent[0]) == (0x88, b"\x03\xe8")


@pytest.mark.parametrize(
    "raw",
    [
        b"\x09\x00",
        b"\xc9\x00",
        b"\x89\x80",
        b"\x89\x7e",
        b"\x88\x01x",
        b"\x88\x02\x03\xed",
        b"\x82\x7e\x00\x01x",
        b"\x82\x7f\x00\x00\x00\x00\x00\x01\x00\x00",
        b"\x8a\x00" * 9,
    ],
)
def test_malformed_or_flooded_controls_fail_closed(raw: bytes) -> None:
    peer, _ = browser(raw)
    with pytest.raises(AssertionError):
        peer.receive()


def test_ping_does_not_restart_receive_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    peer, _ = browser(b"\x89\x00\x82\x02ok")
    ticks: Any = iter([10.0, 10.1, 10.2, 13.1])
    monkeypatch.setattr("a3_native_client.time.monotonic", lambda: next(ticks))
    with pytest.raises(TimeoutError):
        peer.receive()


def test_application_frame_cannot_complete_after_absolute_receive_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    peer, wire = browser(b"\x82\x02ok")
    now = [10.0]
    original = wire.recv

    def delayed(size: int) -> bytes:
        raw = original(size)
        if not wire.inbound:
            now[0] = 13.1
        return raw

    monkeypatch.setattr(wire, "recv", delayed)
    monkeypatch.setattr("a3_native_client.time.monotonic", lambda: now[0])
    with pytest.raises(TimeoutError):
        peer.receive()


def test_control_write_cannot_extend_absolute_receive_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    peer, wire = browser(b"\x89\x00\x82\x02ok")
    now = [10.0]
    original = wire.sendall

    def delayed(raw: bytes) -> None:
        original(raw)
        now[0] = 13.1

    monkeypatch.setattr(wire, "sendall", delayed)
    monkeypatch.setattr("a3_native_client.time.monotonic", lambda: now[0])
    with pytest.raises(TimeoutError):
        peer.receive()
    assert decode_control(wire.sent[0]) == (0x8A, b"")
