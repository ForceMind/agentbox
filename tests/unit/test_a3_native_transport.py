"""Exact native codec/I/O and same-process lifecycle tests, not host qualification."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import socket
import struct
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Literal, cast

import pytest
from a3_currentness_diagnostics import CurrentnessTiming
from agentbox_core import a3_native_io as io
from agentbox_core.a3_native_io import NATIVE_IO_DEADLINE, NativeChannel, deadline_after
from agentbox_core.services import ControlPlaneServices
from agentbox_protocol.a3_admission import A3CurrentAdmission
from agentbox_protocol.a3_content import ERROR_CODES, ContentError, context_digest, encode_message
from agentbox_protocol.a3_crypto import A3Browser
from agentbox_protocol.a3_transport import (
    NativeKind,
    decode_frame,
    decode_header,
    encode_frame,
    facts_digest,
    facts_from_wire,
    facts_to_wire,
)
from agentbox_runtime.a3_native_transport import A3NativeReadOwner
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_peer_authority import WAWPeerAuthority
from test_a3_admission import KEY, PIN, runtime

FACTS = A3CurrentAdmission(
    "prj_" + "a" * 32, "project", "1", "1", "b" * 64, "wri_" + "c" * 32, "1", "1", b"s" * 32, 1
)

CurrentnessBuckets = tuple[
    Literal["none", "active", "expired"],
    Literal["expired", "lt50ms", "50to200ms", "ge200ms"],
    Literal["lt50ms", "50to200ms", "200to250ms", "ge250ms"],
]


def raw_frame(kind: NativeKind, body: bytes, *, sequence: int = 1) -> bytes:
    return struct.pack(">4sBII", b"A3N1", kind, sequence, len(body)) + body


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def test_exact_facts_and_all_native_frame_families() -> None:
    facts = facts_to_wire(FACTS)
    assert facts_from_wire(facts) == FACTS
    assert facts_digest(FACTS) == hashlib.sha256(canonical(facts)).hexdigest()
    payloads: dict[NativeKind, dict[str, object] | bytes] = {
        NativeKind.HELLO: {"bundle_id": "1" * 32, "role": "command", "facts_digest": "2" * 64},
        NativeKind.OBSERVE: {"facts": facts},
        NativeKind.OPEN: {"facts": facts, "selection_id": "a" * 156, "request_nonce": "3" * 64},
        NativeKind.METADATA: {"snapshot_sha256": "4" * 64, "entries": []},
        NativeKind.PUBLISH_CHECK: {"record_sequence": 1, "record_sha256": "5" * 64},
        NativeKind.CURRENT: {"facts_digest": "6" * 64, "challenge": "7" * 32},
        NativeKind.CURRENT_REPLY: {
            "facts_digest": "6" * 64,
            "challenge": "7" * 32,
            "current": True,
        },
        NativeKind.LIVE: {"observation_sequence": 0, "challenge": "8" * 32},
        NativeKind.ERROR: {"code": "PATCH_REVOKED"},
        NativeKind.RECORD: b"opaque",
    }
    payloads[NativeKind.HELLO_ACK] = payloads[NativeKind.HELLO]
    for kind in (NativeKind.CHECKED, NativeKind.PUBLISHED, NativeKind.ACK):
        payloads[kind] = payloads[NativeKind.PUBLISH_CHECK]
    payloads[NativeKind.LIVE_REPLY] = payloads[NativeKind.LIVE]
    for kind in (NativeKind.OWNED, NativeKind.COMPLETE, NativeKind.CLOSE, NativeKind.READY):
        payloads[kind] = {}
    assert set(payloads) == set(NativeKind)
    for kind, payload in payloads.items():
        raw = encode_frame(kind, 1, payload)
        frame = decode_frame(raw)
        assert (frame.kind, frame.sequence, frame.payload) == (kind, 1, payload)
        assert "opaque" not in repr(frame)
        with pytest.raises(ContentError):
            decode_frame(raw + b"x")
        with pytest.raises(ContentError):
            decode_frame(raw[:-1])


@pytest.mark.parametrize("value", [True, 1, 0, "0", "01", "+1", "1.0", "18446744073709551616"])
def test_facts_never_coerce_auth_epoch(value: object) -> None:
    facts = facts_to_wire(FACTS)
    facts["auth_epoch"] = value
    with pytest.raises(ContentError):
        facts_from_wire(facts)


@pytest.mark.parametrize(
    "body",
    [
        b"{ }",
        b'{"x":1}',
        b'{"x":1,"x":1}',
        b"[]",
        b"null",
        b'{"x":NaN}',
        b"{}\n",
        b'{"x":Infinity}',
        b"\xff",
    ],
)
def test_json_noncanonical_unknown_duplicate_rejected(body: bytes) -> None:
    with pytest.raises(ContentError):
        decode_frame(raw_frame(NativeKind.CLOSE, body))


@pytest.mark.parametrize(
    "kind,length",
    [
        (NativeKind.OPEN, 8193),
        (NativeKind.RECORD, 24577),
        (NativeKind.METADATA, 2 * 1024 * 1024 + 1),
    ],
)
def test_header_rejects_size_before_any_body(kind: NativeKind, length: int) -> None:
    with pytest.raises(ContentError):
        decode_header(struct.pack(">4sBII", b"A3N1", kind, 1, length))


@pytest.mark.parametrize("change", ["session", "extra", "relative", "project", "host", "epoch"])
def test_facts_exact_scope_and_known_identifiers(change: str) -> None:
    facts = facts_to_wire(FACTS)
    if change == "session":
        facts["session_scope"] = "a" * 63
    elif change == "extra":
        facts["cookie"] = "never accepted"
    elif change == "relative":
        facts["relative_key"] = "../project"
    elif change == "epoch":
        facts["runtime_epoch"] = "01"
    else:
        facts["project_id" if change == "project" else "runtime_host_installation_id"] = "wrong"
    with pytest.raises(ContentError):
        facts_from_wire(facts)


@pytest.mark.parametrize("sequence", [True, 0, -1, 2**32, 1.0])
def test_record_sequence_does_not_coerce(sequence: object) -> None:
    with pytest.raises(ContentError):
        encode_frame(
            NativeKind.PUBLISH_CHECK, 1, {"record_sequence": sequence, "record_sha256": "0" * 64}
        )


def test_metadata_is_dedicated_and_never_patch_or_path_authority() -> None:
    entry: dict[str, object] = {
        "path": "中文.txt",
        "kind": "modified",
        "side": "staged",
        "selection_id": "a" * 156,
        "unavailable_code": None,
    }
    data: dict[str, object] = {"entries": [entry], "snapshot_sha256": "a" * 64}
    assert decode_frame(encode_frame(NativeKind.METADATA, 1, data)).payload == data
    for altered in (
        {**entry, "patch": "secret"},
        {**entry, "kind": "renamed"},
        {**entry, "selection_id": None},
        {**entry, "unavailable_code": "PATCH_REVOKED"},
    ):
        with pytest.raises(ContentError):
            encode_frame(NativeKind.METADATA, 1, {**data, "entries": [altered]})
    with pytest.raises(ContentError):
        encode_frame(NativeKind.METADATA, 1, {**data, "entries": [entry, entry]})


def channel_pair() -> tuple[NativeChannel, NativeChannel]:
    a, b = socket.socketpair()
    channels = NativeChannel(a, lambda: None), NativeChannel(b, lambda: None)
    for sock in (a, b):
        assert not sock.get_inheritable()
        assert not sock.getblocking()
        for option in (socket.SO_SNDBUF, socket.SO_RCVBUF):
            assert 0 < sock.getsockopt(socket.SOL_SOCKET, option) <= 65536
    return channels


@pytest.mark.anyio
async def test_partial_io_and_sequence_replay_close() -> None:
    sender, receiver = channel_pair()
    try:
        raw = encode_frame(NativeKind.RECORD, 1, b"ciphertext")

        async def fragmented() -> None:
            for byte in raw:
                sender._socket.send(bytes([byte]))
                await asyncio.sleep(0)

        task = asyncio.create_task(fragmented())
        frame = await receiver.areceive(
            frozenset({NativeKind.RECORD}), deadline_ns=deadline_after(1)
        )
        await task
        assert frame.payload == b"ciphertext"
        sender._socket.send(raw)
        with pytest.raises(ContentError):
            await receiver.areceive(frozenset({NativeKind.RECORD}), deadline_ns=deadline_after(1))
        assert receiver.closed
    finally:
        sender.close()
        receiver.close()


@pytest.mark.anyio
async def test_partial_frame_has_one_deadline_and_concurrent_read_fences() -> None:
    sender, receiver = channel_pair()
    try:
        sender._socket.send(encode_frame(NativeKind.RECORD, 1, b"ciphertext")[:14])
        begin = time.monotonic()
        with pytest.raises(ContentError, match="PATCH_TIMEOUT"):
            await receiver.areceive(
                frozenset({NativeKind.RECORD}), deadline_ns=deadline_after(0.03)
            )
        assert time.monotonic() - begin < 0.3
    finally:
        sender.close()
        receiver.close()
    sender, receiver = channel_pair()
    first = asyncio.create_task(
        receiver.areceive(frozenset({NativeKind.RECORD}), deadline_ns=deadline_after(1))
    )
    await asyncio.sleep(0)
    with pytest.raises(ContentError):
        await receiver.areceive(frozenset({NativeKind.RECORD}), deadline_ns=deadline_after(1))
    with pytest.raises(ContentError):
        await first
    sender.close()


@pytest.mark.anyio
async def test_close_holds_registered_fd_until_old_watch_removed() -> None:
    sender, receiver = channel_pair()
    old_fd = receiver._socket.fileno()
    task = asyncio.create_task(
        receiver.areceive(frozenset({NativeKind.RECORD}), deadline_ns=deadline_after(1))
    )
    await asyncio.sleep(0)
    receiver.close()
    # Synchronous shutdown, but no reusable descriptor until exact watcher cleanup.
    assert receiver._socket.fileno() == old_fd
    extra = socket.socket()
    assert extra.fileno() != old_fd
    with pytest.raises(ContentError):
        await task
    assert receiver._socket.fileno() == -1
    replacement_sender, replacement_receiver = channel_pair()
    try:
        await replacement_sender.asend(NativeKind.RECORD, b"new", deadline_ns=deadline_after(1))
        got = await replacement_receiver.areceive(
            frozenset({NativeKind.RECORD}), deadline_ns=deadline_after(1)
        )
        assert got.payload == b"new"
    finally:
        extra.close()
        sender.close()
        replacement_sender.close()
        replacement_receiver.close()


@pytest.mark.anyio
async def test_after_decode_deadline_and_final_guard_are_rechecked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender, receiver = channel_pair()
    original = decode_frame

    def expired(raw: bytes) -> Any:
        result = original(raw)
        receiver.close()
        return result

    monkeypatch.setattr(io, "decode_frame", expired)
    await sender.asend(NativeKind.RECORD, b"ciphertext", deadline_ns=deadline_after(1))
    with pytest.raises(ContentError):
        await receiver.areceive(frozenset({NativeKind.RECORD}), deadline_ns=deadline_after(1))
    sender.close()


class TestKey:
    __test__ = False

    @contextlib.contextmanager
    def borrow(self, facts: A3CurrentAdmission) -> Iterator[bytes]:
        assert type(facts) is A3CurrentAdmission
        yield KEY


async def native_owner(tmp_path: Path, services: ControlPlaneServices) -> tuple[Any, ...]:
    old, adapter, _, lifecycle, executor, _, _, _, reader = await runtime(tmp_path, services)
    old.close()
    authority = WAWPeerAuthority(expected_uid=os.getuid(), expected_gid=os.getgid())
    pidfd = os.pidfd_open(os.getpid())
    try:
        candidate = authority.observe_control(os.getpid(), os.getuid(), os.getgid(), pidfd)
        assert candidate is not None
        authority.commit_bind(
            authority.prepare_bind(candidate, api_authority_epoch="1", nonce_digest=b"n" * 32)
        )
    finally:
        os.close(pidfd)
    lease = authority.borrow()
    assert lease is not None
    lifecycle._peer_authority = authority
    lifecycle._peer_authority_identity = lease.runtime_peer.identity
    lease.close()
    # Existing API fixture has another formal Project id.
    from test_waw_api_application import PROJECT_ID

    facts = adapter.current(PROJECT_ID, adapter.session_scope)
    assert facts is not None
    owner = A3NativeReadOwner(reader, lifecycle, executor, TestKey())
    return owner, facts, authority, lifecycle


class Client:
    """Same-process socketpair test driver, deliberately not separate-process evidence."""

    def __init__(self, owner: A3NativeReadOwner, facts: A3CurrentAdmission) -> None:
        self.facts, self.live, self.calls = facts, True, 0
        sockets = [socket.socketpair() for _ in range(3)]
        self.channels = {
            name: NativeChannel(pair[0], lambda: None)
            for name, pair in zip(("command", "opaque", "currentness"), sockets, strict=True)
        }
        self.bundle = owner.reserve().accept(*(pair[1] for pair in sockets))
        self.thread: threading.Thread | None = None
        self.currentness_failures: (
            list[tuple[str, str, int, int, CurrentnessBuckets | None]] | None
        ) = None
        self._currentness_failure_lock = threading.Lock()
        self.currentness_calls = 0
        self.currentness_timing: CurrentnessTiming | None = None

    def diagnose_currentness_failures(self) -> None:
        """Opt-in, failure-only fixture evidence; never change the native outcome."""
        previous = getattr(self, "currentness_timing", None)
        if previous is not None:
            with contextlib.suppress(BaseException):
                previous.start()
            return
        timing = CurrentnessTiming()
        self.currentness_timing = timing
        self.currentness_failures = []
        # The guard-budget companion wraps the same real reservation on another loop.
        bundle = cast(Any, getattr(self.bundle, "actual", self.bundle))
        current = bundle.current

        def diagnosed_current() -> A3CurrentAdmission:
            self.currentness_calls = min(self.currentness_calls + 1, 65535)
            try:
                return cast(A3CurrentAdmission, current())
            except Exception as error:
                with contextlib.suppress(BaseException):
                    self.record_currentness_failure("runtime-currentness", error)
                raise

        bundle.current = diagnosed_current

        def diagnosed_io(
            phase: Literal["runtime-send", "runtime-receive"], operation: Callable[..., Any]
        ) -> Callable[..., Any]:
            def call(*args: Any, **kwargs: Any) -> Any:
                entry: tuple[int, int | None] | None = None
                with contextlib.suppress(BaseException):
                    entry = time.monotonic_ns(), NATIVE_IO_DEADLINE.get()
                try:
                    return operation(*args, **kwargs)
                except Exception as error:
                    with contextlib.suppress(BaseException):
                        buckets = (
                            None
                            if entry is None
                            else self.currentness_io_buckets(
                                entry[0], kwargs["deadline_ns"], entry[1], time.monotonic_ns()
                            )
                        )
                        self.record_currentness_failure(phase, error, buckets)
                    raise

            return call

        channel = bundle._channels["currentness"]
        channel.send = diagnosed_io("runtime-send", timing.measure("runtime-send", channel.send))
        channel.receive = diagnosed_io(
            "runtime-receive", timing.measure("runtime-receive", channel.receive)
        )
        checker = cast(Any, self.channels["currentness"])
        checker.wait_readable = timing.measure("checker-wait", checker.wait_readable)
        checker.receive = timing.measure("checker-receive", checker.receive)
        checker.send = timing.measure("checker-send", checker.send)
        with contextlib.suppress(BaseException):
            timing.start()

    def stop_currentness_diagnostics(self) -> None:
        timing = getattr(self, "currentness_timing", None)
        if timing is not None:
            with contextlib.suppress(BaseException):
                timing.close()

    @staticmethod
    def currentness_io_buckets(
        started: int, deadline: int, inherited: int | None, finished: int
    ) -> CurrentnessBuckets:
        inherited_kind: Literal["none", "active", "expired"] = (
            "none" if inherited is None else "expired" if inherited <= started else "active"
        )
        remaining, elapsed = deadline - started, finished - started
        budget: Literal["expired", "lt50ms", "50to200ms", "ge200ms"]
        if remaining <= 0:
            budget = "expired"
        elif remaining < 50_000_000:
            budget = "lt50ms"
        elif remaining < 200_000_000:
            budget = "50to200ms"
        else:
            budget = "ge200ms"
        duration: Literal["lt50ms", "50to200ms", "200to250ms", "ge250ms"]
        if elapsed < 50_000_000:
            duration = "lt50ms"
        elif elapsed < 200_000_000:
            duration = "50to200ms"
        elif elapsed < 250_000_000:
            duration = "200to250ms"
        else:
            duration = "ge250ms"
        return inherited_kind, budget, duration

    def record_currentness_failure(
        self,
        phase: Literal["runtime-currentness", "fixture-checker", "runtime-send", "runtime-receive"],
        error: Exception,
        buckets: CurrentnessBuckets | None = None,
    ) -> None:
        failures = self.currentness_failures
        if failures is None:
            return
        reason = "unexpected-error"
        if type(error) is ContentError and len(error.args) == 1:
            code = error.args[0]
            if type(code) is str and code in ERROR_CODES:
                reason = code
        elif type(error) is AssertionError:
            reason = "assertion-error"
        elif isinstance(error, OSError):
            reason = "os-error"
        with self._currentness_failure_lock:
            if len(failures) < 4:
                failures.append(
                    (phase, reason, min(self.calls, 65535), self.currentness_calls, buckets)
                )

    def add_currentness_failure_note(self, error: Exception) -> None:
        with contextlib.suppress(BaseException):
            error.add_note(f"Native fixture currentness failures: {self.currentness_failures!r}")
        with contextlib.suppress(BaseException):
            timing = getattr(self, "currentness_timing", None)
            if timing is not None:
                error.add_note(
                    f"Native fixture timing gc_observation_available={timing.available!r} "
                    "(phase, wall, thread_cpu, process_cpu, "
                    f"gc_overlap, generation_mask, truncated): {timing.failures!r}"
                )

    async def start(self, *, mixed: bool = False) -> None:
        try:
            await self._start(mixed=mixed)
        except BaseException:
            self.stop_currentness_diagnostics()
            raise

    async def _start(self, *, mixed: bool = False) -> None:
        digest = facts_digest(self.facts)
        for role, channel in self.channels.items():
            await channel.asend(
                NativeKind.HELLO,
                {
                    "bundle_id": "1" * 32 if not mixed or role == "command" else "2" * 32,
                    "role": role,
                    "facts_digest": digest,
                },
                deadline_ns=deadline_after(1),
            )
        for channel in self.channels.values():
            await channel.areceive(frozenset({NativeKind.HELLO_ACK}), deadline_ns=deadline_after(1))
        self.thread = threading.Thread(target=self.checker, daemon=True)
        self.thread.start()

    def checker(self) -> None:
        channel = self.channels["currentness"]
        try:
            while True:
                channel.wait_readable(deadline_after(30))
                frame = channel.receive(
                    frozenset({NativeKind.CURRENT}), deadline_ns=deadline_after(0.25)
                )
                data = cast(dict[str, object], frame.payload)
                assert data["facts_digest"] == facts_digest(self.facts)
                self.calls += 1
                channel.send(
                    NativeKind.CURRENT_REPLY,
                    {**data, "current": self.live},
                    deadline_ns=deadline_after(0.25),
                )
        except Exception as error:
            with contextlib.suppress(BaseException):
                self.record_currentness_failure("fixture-checker", error)
            channel.close()

    async def rpc(
        self, kind: NativeKind, payload: dict[str, object], response: NativeKind
    ) -> dict[str, object]:
        channel = self.channels["command"]
        await channel.asend(kind, payload, deadline_ns=deadline_after(1))
        frame = await channel.areceive(frozenset({response}), deadline_ns=deadline_after(5))
        return cast(dict[str, object], frame.payload)

    async def close(self) -> None:
        try:
            await self._close()
        finally:
            self.stop_currentness_diagnostics()

    async def _close(self) -> None:
        for channel in self.channels.values():
            channel.close()
        self.bundle.close()
        await asyncio.wait_for(self.bundle.wait_closed(), 2)
        if self.thread is not None:
            self.thread.join(timeout=1)
            assert not self.thread.is_alive()


def test_fixture_currentness_diagnostics_are_bounded_and_value_free() -> None:
    client = Client.__new__(Client)
    client.calls, client.currentness_calls = 70000, 65535
    client.currentness_failures = []
    client._currentness_failure_lock = threading.Lock()
    for error in (
        ContentError("PATCH_TIMEOUT"),
        ContentError("secret-canary-not-a-fixed-code"),
        AssertionError("secret-canary-assertion"),
        OSError("secret-canary-path"),
        RuntimeError("secret-canary-discarded"),
    ):
        client.record_currentness_failure("fixture-checker", error)
    assert client.currentness_failures == [
        ("fixture-checker", "PATCH_TIMEOUT", 65535, 65535, None),
        ("fixture-checker", "unexpected-error", 65535, 65535, None),
        ("fixture-checker", "assertion-error", 65535, 65535, None),
        ("fixture-checker", "os-error", 65535, 65535, None),
    ]
    original = ContentError("PATCH_REVOKED")
    client.add_currentness_failure_note(original)
    assert "secret-canary" not in repr(original.__notes__)


def test_fixture_currentness_budget_bucket_boundaries() -> None:
    for value, budget, elapsed in (
        (-1, "expired", "lt50ms"),
        (0, "expired", "lt50ms"),
        (1, "lt50ms", "lt50ms"),
        (49_999_999, "lt50ms", "lt50ms"),
        (50_000_000, "50to200ms", "50to200ms"),
        (199_999_999, "50to200ms", "50to200ms"),
        (200_000_000, "ge200ms", "200to250ms"),
        (249_999_999, "ge200ms", "200to250ms"),
        (250_000_000, "ge200ms", "ge250ms"),
    ):
        assert Client.currentness_io_buckets(0, value, None, value) == ("none", budget, elapsed)
    for inherited, expected in ((-1, "expired"), (0, "expired"), (1, "active")):
        assert Client.currentness_io_buckets(0, 250_000_000, inherited, 1)[0] == expected


def test_fixture_diagnostic_failure_preserves_original_exception(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
    diagnostic_error_type: type[BaseException] = RuntimeError,
) -> None:
    original = ContentError("PATCH_TIMEOUT")

    class Channel:
        def send(self, **_kwargs: object) -> None:
            raise original

        receive = send
        wait_readable = send

    class Bundle:
        def __init__(self) -> None:
            self._channels = {"currentness": Channel()}

        def current(self) -> A3CurrentAdmission:
            raise original

    def broken(*_args: object) -> None:
        raise diagnostic_error_type("diagnostic failure must not replace the original")

    client = Client.__new__(Client)
    client.calls, client.currentness_calls = 7, 0
    client.bundle = cast(Any, Bundle())
    client.channels = cast(Any, {"currentness": Channel()})
    client.diagnose_currentness_failures()
    # This codec-only fixture has no bundle lifecycle; close its diagnostic hook.
    request.addfinalizer(client.stop_currentness_diagnostics)
    monkeypatch.setattr(client, "record_currentness_failure", broken)
    monkeypatch.setattr(original, "add_note", broken)
    with pytest.raises(ContentError) as raised:
        try:
            client.bundle.current()
        except ContentError as error:
            client.add_currentness_failure_note(error)
            raise
    assert raised.value is original
    assert client.currentness_calls == 1
    channel = cast(Any, client.bundle._channels["currentness"])
    for operation in (channel.send, channel.receive):
        with pytest.raises(ContentError) as raised:
            operation(deadline_ns=deadline_after(0.25))
        assert raised.value is original


@pytest.mark.anyio
async def test_four_slots_include_incomplete_bundles_and_default_context_unavailable(
    tmp_path: Path,
    initialized_services: ControlPlaneServices,
) -> None:
    owner, facts, authority, _ = await native_owner(tmp_path, initialized_services)
    try:
        with pytest.raises(RuntimeOperationError):
            await owner.selectors.observe(facts.project_id, facts.session_scope)
        reservations = [owner.reserve() for _ in range(4)]
        with pytest.raises(ContentError, match="PATCH_UNAVAILABLE_BUSY"):
            owner.reserve()
        for reservation in reservations:
            reservation.close()
        await owner.wait_closed()
        assert owner.active_bundles == 0
    finally:
        owner.close()
        await owner.wait_closed()
        authority.close()


@pytest.mark.anyio
async def test_bundle_role_mixing_closes_before_git(
    tmp_path: Path,
    initialized_services: ControlPlaneServices,
) -> None:
    owner, facts, authority, _ = await native_owner(tmp_path, initialized_services)
    client = Client(owner, facts)
    try:
        with pytest.raises(ContentError):
            await client.start(mixed=True)
        assert owner.selectors._active == 0
        assert not owner.selectors._burned_nonces
    finally:
        await client.close()
        owner.close()
        await owner.wait_closed()
        authority.close()


@pytest.mark.anyio
async def test_native_records_hold_admission_through_publication_complete_and_revoke(
    tmp_path: Path,
    initialized_services: ControlPlaneServices,
) -> None:
    owner, facts, authority, _ = await native_owner(tmp_path, initialized_services)
    observer = Client(owner, facts)
    client: Client | None = None
    try:
        await observer.start()
        metadata = await observer.rpc(
            NativeKind.OBSERVE, {"facts": facts_to_wire(facts)}, NativeKind.METADATA
        )
        entries = cast(list[dict[str, object]], metadata["entries"])
        selection = cast(
            str, next(entry["selection_id"] for entry in entries if entry["path"] == "modified.txt")
        )
        await observer.close()
        client = Client(owner, facts)
        client.diagnose_currentness_failures()
        await client.start()
        await client.rpc(
            NativeKind.OPEN,
            {"facts": facts_to_wire(facts), "selection_id": selection, "request_nonce": "6" * 64},
            NativeKind.OWNED,
        )
        opaque = client.channels["opaque"]
        try:
            await opaque.areceive(frozenset({NativeKind.READY}), deadline_ns=deadline_after(5))
        except ContentError as error:
            client.add_currentness_failure_note(error)
            raise
        assert owner.selectors._active == 1
        live = {"observation_sequence": 0, "challenge": "7" * 32}
        assert await client.rpc(NativeKind.LIVE, live, NativeKind.LIVE_REPLY) == live
        from agentbox_protocol.a3_content import selector_commitment

        context = {
            "protocol_id": "agentbox-a3-content/v1",
            "protocol_version": 1,
            **{
                key: value
                for key, value in facts_to_wire(facts).items()
                if key not in {"relative_key", "auth_epoch"}
            },
            "selector_commitment": selector_commitment(selection),
            "side": "staged",
            "request_nonce": "6" * 64,
        }
        browser = A3Browser(
            cast(Any, context),
            expected_pin=lambda: PIN,
            clock_ms=lambda: time.monotonic_ns() // 1_000_000,
            current=lambda: cast(Any, context),
            deadline_ms=time.monotonic_ns() // 1_000_000 + 30000,
        )
        sequence = 0

        async def send(record: bytes) -> None:
            await opaque.asend(NativeKind.RECORD, record, deadline_ns=deadline_after(1))

        async def receive() -> bytes:
            nonlocal sequence
            frame = await opaque.areceive(
                frozenset({NativeKind.RECORD}), deadline_ns=deadline_after(1)
            )
            sequence += 1
            record = cast(bytes, frame.payload)
            publication = {
                "record_sequence": sequence,
                "record_sha256": hashlib.sha256(record).hexdigest(),
            }
            assert owner.selectors._active == 1
            assert (
                await client.rpc(NativeKind.PUBLISH_CHECK, publication, NativeKind.CHECKED)
                == publication
            )
            assert (
                await client.rpc(NativeKind.PUBLISHED, publication, NativeKind.ACK) == publication
            )
            return record

        await send(browser.start())
        await send(browser.receive_attest(await receive()))
        browser.receive_ack(await receive())
        await send(
            browser.encrypt_read(
                encode_message(
                    {
                        "protocol_id": "agentbox-a3-content/v1",
                        "protocol_version": 1,
                        "context_digest": context_digest(cast(Any, context)),
                        "request_nonce": "6" * 64,
                        "kind": "PATCH_READ",
                        "selection_id": selection,
                    }
                )
            )
        )
        complete = None
        while complete is None:
            complete = browser.receive_record(await receive())
        assert b"staged secret-canary content" in complete
        await opaque.areceive(frozenset({NativeKind.COMPLETE}), deadline_ns=deadline_after(1))
        assert owner.selectors._active == 1 and owner.active_bundles == 1
        assert len(owner.selectors._burned_nonces) == 1
        before = client.calls
        await asyncio.sleep(0.1)
        assert client.calls > before
        assert owner.selectors._active == 1
        client.live = False
        await asyncio.wait_for(client.bundle.wait_closed(), 1)
        assert owner.selectors._active == 0 and len(owner.selectors._burned_nonces) == 1
    finally:
        await observer.close()
        if client is not None:
            await client.close()
        owner.close()
        await owner.wait_closed()
        authority.close()


@pytest.mark.anyio
async def test_observation_cancel_cleanup_keeps_bundle_slot(
    tmp_path: Path,
    initialized_services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, facts, authority, _ = await native_owner(tmp_path, initialized_services)
    client = Client(owner, facts)
    started, cleanup_started, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def blocked_observation(*_args: object) -> Any:
        started.set()
        try:
            await asyncio.Future()
        finally:
            cleanup_started.set()
            await release.wait()

    monkeypatch.setattr(owner.selectors, "observe", blocked_observation)
    try:
        await client.start()
        request = asyncio.create_task(
            client.rpc(NativeKind.OBSERVE, {"facts": facts_to_wire(facts)}, NativeKind.METADATA)
        )
        await started.wait()
        client.bundle.close()
        await cleanup_started.wait()
        await asyncio.sleep(0.05)
        assert owner.active_bundles == 1
        assert not client.bundle._cleanup.is_set()
        # Repeated close cannot cancel the already-running cleanup a second time.
        client.bundle.close()
        await asyncio.sleep(0.05)
        assert owner.active_bundles == 1
        release.set()
        await asyncio.wait_for(client.bundle.wait_closed(), 1)
        assert owner.active_bundles == 0
        with pytest.raises(ContentError):
            await request
    finally:
        release.set()
        await client.close()
        owner.close()
        await owner.wait_closed()
        authority.close()


@pytest.mark.anyio
async def test_preflight_error_is_fixed_error_and_never_ready(
    tmp_path: Path,
    initialized_services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agentbox_runtime import a3_content_session

    owner, facts, authority, _ = await native_owner(tmp_path, initialized_services)
    observer = Client(owner, facts)
    client: Client | None = None

    def too_large(*_args: object) -> Any:
        raise ContentError("PATCH_TOO_LARGE")

    try:
        await observer.start()
        metadata = await observer.rpc(
            NativeKind.OBSERVE, {"facts": facts_to_wire(facts)}, NativeKind.METADATA
        )
        entries = cast(list[dict[str, object]], metadata["entries"])
        selection = cast(
            str, next(entry["selection_id"] for entry in entries if entry["path"] == "modified.txt")
        )
        await observer.close()
        monkeypatch.setattr(a3_content_session, "prepare_pages", too_large)
        client = Client(owner, facts)
        await client.start()
        await client.rpc(
            NativeKind.OPEN,
            {"facts": facts_to_wire(facts), "selection_id": selection, "request_nonce": "5" * 64},
            NativeKind.OWNED,
        )
        frame = await client.channels["opaque"].areceive(
            frozenset({NativeKind.ERROR}), deadline_ns=deadline_after(5)
        )
        assert frame.payload == {"code": "PATCH_TOO_LARGE"}
        assert not client.bundle.closed
        await asyncio.wait_for(client.bundle.wait_closed(), 2)
        assert owner.selectors._active == 0 and len(owner.selectors._burned_nonces) == 1
    finally:
        await observer.close()
        if client is not None:
            await client.close()
        owner.close()
        await owner.wait_closed()
        authority.close()


@pytest.mark.anyio
async def test_backpressure_rechecks_guard_before_any_later_write() -> None:
    sender, receiver = channel_pair()
    sender._socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024)
    live = True

    def guard() -> None:
        if not live:
            raise ContentError("PATCH_REVOKED")

    sending = asyncio.create_task(
        sender.asend(NativeKind.RECORD, b"x" * 24576, deadline_ns=deadline_after(1), guard=guard)
    )
    await asyncio.sleep(0.03)
    assert not sending.done()
    live = False
    accepted_before_revocation = receiver._socket.recv(30000)
    assert 0 < len(accepted_before_revocation) < 24576
    with pytest.raises(ContentError, match="PATCH_REVOKED"):
        await sending
    assert receiver._socket.recv(30000) == b""
    receiver.close()


@pytest.mark.anyio
async def test_body_parse_cannot_publish_after_absolute_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender, receiver = channel_pair()
    original = decode_frame

    def slow(raw: bytes) -> Any:
        result = original(raw)
        time.sleep(0.04)
        return result

    await sender.asend(NativeKind.RECORD, b"ciphertext", deadline_ns=deadline_after(1))
    monkeypatch.setattr(io, "decode_frame", slow)
    with pytest.raises(ContentError, match="PATCH_TIMEOUT"):
        await receiver.areceive(frozenset({NativeKind.RECORD}), deadline_ns=deadline_after(0.02))
    sender.close()


@pytest.mark.anyio
async def test_reservation_expiry_releases_unassembled_slot(
    tmp_path: Path,
    initialized_services: ControlPlaneServices,
) -> None:
    owner, _, authority, _ = await native_owner(tmp_path, initialized_services)
    reservation = owner.reserve()
    try:
        await asyncio.wait_for(reservation.wait_closed(), 1.3)
        assert owner.active_bundles == 0 and reservation.closed
    finally:
        owner.close()
        await owner.wait_closed()
        authority.close()


@pytest.mark.anyio
async def test_unbound_actual_peer_is_not_authorized_by_same_uid_or_pid(
    tmp_path: Path,
    initialized_services: ControlPlaneServices,
) -> None:
    owner, _, authority, _ = await native_owner(tmp_path, initialized_services)
    sockets = [socket.socketpair() for _ in range(3)]
    authority.close()
    reservation = owner.reserve()
    try:
        with pytest.raises(ContentError):
            reservation.accept(*(pair[1] for pair in sockets))
        await asyncio.wait_for(reservation.wait_closed(), 1)
        assert owner.active_bundles == 0 and owner.selectors._active == 0
    finally:
        for pair in sockets:
            for sock in pair:
                sock.close()
        owner.close()
        await owner.wait_closed()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure", ["revoked", "wrong_record", "duplicate_check", "unchecked_ack", "missing_ack"]
)
async def test_publication_pending_record_is_exact_one_use_and_fail_closed(
    tmp_path: Path,
    initialized_services: ControlPlaneServices,
    failure: str,
) -> None:
    from agentbox_protocol.a3_content import selector_commitment

    owner, facts, authority, _ = await native_owner(tmp_path, initialized_services)
    observer = Client(owner, facts)
    client: Client | None = None
    try:
        await observer.start()
        metadata = await observer.rpc(
            NativeKind.OBSERVE, {"facts": facts_to_wire(facts)}, NativeKind.METADATA
        )
        entries = cast(list[dict[str, object]], metadata["entries"])
        selection = cast(
            str, next(entry["selection_id"] for entry in entries if entry["path"] == "modified.txt")
        )
        await observer.close()
        client = Client(owner, facts)
        await client.start()
        await client.rpc(
            NativeKind.OPEN,
            {"facts": facts_to_wire(facts), "selection_id": selection, "request_nonce": "9" * 64},
            NativeKind.OWNED,
        )
        opaque = client.channels["opaque"]
        await opaque.areceive(frozenset({NativeKind.READY}), deadline_ns=deadline_after(5))
        context = {
            "protocol_id": "agentbox-a3-content/v1",
            "protocol_version": 1,
            **{
                key: value
                for key, value in facts_to_wire(facts).items()
                if key not in {"relative_key", "auth_epoch"}
            },
            "selector_commitment": selector_commitment(selection),
            "side": "staged",
            "request_nonce": "9" * 64,
        }
        browser = A3Browser(
            cast(Any, context),
            expected_pin=lambda: PIN,
            clock_ms=lambda: time.monotonic_ns() // 1_000_000,
            current=lambda: cast(Any, context),
            deadline_ms=time.monotonic_ns() // 1_000_000 + 30000,
        )
        await opaque.asend(NativeKind.RECORD, browser.start(), deadline_ns=deadline_after(1))
        frame = await opaque.areceive(frozenset({NativeKind.RECORD}), deadline_ns=deadline_after(1))
        record = cast(bytes, frame.payload)
        payload: dict[str, object] = {
            "record_sequence": 1,
            "record_sha256": hashlib.sha256(record).hexdigest(),
        }
        assert owner.selectors._active == 1
        if failure == "missing_ack":
            await asyncio.wait_for(client.bundle.wait_closed(), 1.5)
        else:
            kind, reply = NativeKind.PUBLISH_CHECK, NativeKind.CHECKED
            if failure == "revoked":
                client.live = False
            elif failure == "wrong_record":
                payload["record_sha256"] = "0" * 64
            elif failure == "duplicate_check":
                assert await client.rpc(kind, payload, reply) == payload
            elif failure == "unchecked_ack":
                kind, reply = NativeKind.PUBLISHED, NativeKind.ACK
            with pytest.raises(ContentError):
                await client.rpc(kind, payload, reply)
            await asyncio.wait_for(client.bundle.wait_closed(), 1.5)
        assert owner.selectors._active == 0
        assert len(owner.selectors._burned_nonces) == 1
    finally:
        await observer.close()
        if client is not None:
            await client.close()
        owner.close()
        await owner.wait_closed()
        authority.close()


@pytest.mark.anyio
async def test_bundle_rejects_distinct_fd_aliases_of_one_stream(
    tmp_path: Path, initialized_services: ControlPlaneServices
) -> None:
    owner, _facts, authority, _ = await native_owner(tmp_path, initialized_services)
    left, right = socket.socketpair()
    aliases = (
        left,
        socket.socket(fileno=os.dup(left.fileno())),
        socket.socket(fileno=os.dup(left.fileno())),
    )
    reservation = owner.reserve()
    try:
        with pytest.raises(ContentError, match="PATCH_REVOKED"):
            reservation.accept(*aliases)
        await reservation.wait_closed()
        assert owner.active_bundles == 0
        assert not owner.selectors._burned_nonces
    finally:
        right.close()
        for alias in aliases:
            alias.close()
        owner.close()
        await owner.wait_closed()
        authority.close()


@pytest.mark.anyio
@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("condition", ["revoke", "expiry"])
async def test_readiness_only_return_performs_final_full_fence(
    monkeypatch: pytest.MonkeyPatch,
    asynchronous: bool,
    condition: str,
) -> None:
    sender, receiver = channel_pair()
    live = True

    def guard() -> None:
        if not live:
            raise ContentError("PATCH_REVOKED")

    sender._socket.send(b"x")
    deadline = deadline_after(0.1)
    original_wait, original_await = receiver._wait, receiver._await

    def after_ready() -> None:
        nonlocal live
        if condition == "revoke":
            live = False
        else:
            # Let readiness succeed, then expire before it is exposed to caller.
            time.sleep(max(0, (deadline - time.monotonic_ns()) / 1_000_000_000) + 0.01)

    def waiting(write: bool, end: int, check: Any) -> None:
        original_wait(write, end, check)
        after_ready()

    async def awaiting(write: bool, end: int, check: Any) -> None:
        await original_await(write, end, check)
        after_ready()

    monkeypatch.setattr(receiver, "_wait", waiting)
    monkeypatch.setattr(receiver, "_await", awaiting)
    try:
        with pytest.raises(
            ContentError, match="PATCH_REVOKED" if condition == "revoke" else "PATCH_TIMEOUT"
        ):
            if asynchronous:
                await receiver.await_readable(deadline, guard)
            else:
                receiver.wait_readable(deadline, guard)
        assert receiver.closed and receiver.shutdown_complete
    finally:
        sender.close()
        receiver.close()


@pytest.mark.anyio
@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("operation", ["send", "header", "body"])
async def test_every_actual_syscall_rechecks_after_readiness(
    monkeypatch: pytest.MonkeyPatch,
    asynchronous: bool,
    operation: str,
) -> None:
    sender, receiver = channel_pair()
    channel = sender if operation == "send" else receiver
    live = True
    syscalls = 0
    waits = 0
    original_socket = channel._socket
    original_wait, original_await = channel._wait, channel._await

    class CheckedSocket:
        def __getattr__(self, name: str) -> Any:
            return getattr(original_socket, name)

        def send(self, raw: Any) -> int:
            nonlocal syscalls
            assert live, "send syscall ran after queued revocation"
            syscalls += 1
            return original_socket.send(raw)

        def recv(self, size: int) -> bytes:
            nonlocal syscalls
            assert live, "recv syscall ran after queued revocation"
            syscalls += 1
            return original_socket.recv(size)

    def guard() -> None:
        if not live:
            raise ContentError("PATCH_REVOKED")

    def after_ready() -> None:
        nonlocal waits, live
        waits += 1
        if waits == (2 if operation == "body" else 1):
            live = False

    def waiting(write: bool, end: int, check: Any) -> None:
        original_wait(write, end, check)
        after_ready()

    async def awaiting(write: bool, end: int, check: Any) -> None:
        await original_await(write, end, check)
        after_ready()

    monkeypatch.setattr(channel, "_socket", CheckedSocket())
    monkeypatch.setattr(channel, "_wait", waiting)
    monkeypatch.setattr(channel, "_await", awaiting)
    if operation != "send":
        sender._socket.send(encode_frame(NativeKind.RECORD, 1, b"opaque"))
    try:
        with pytest.raises(ContentError, match="PATCH_REVOKED"):
            if operation == "send":
                if asynchronous:
                    await channel.asend(
                        NativeKind.RECORD, b"opaque", deadline_ns=deadline_after(1), guard=guard
                    )
                else:
                    channel.send(
                        NativeKind.RECORD, b"opaque", deadline_ns=deadline_after(1), guard=guard
                    )
            elif asynchronous:
                await channel.areceive(
                    frozenset({NativeKind.RECORD}), deadline_ns=deadline_after(1), guard=guard
                )
            else:
                channel.receive(
                    frozenset({NativeKind.RECORD}), deadline_ns=deadline_after(1), guard=guard
                )
        assert syscalls == (1 if operation == "body" else 0)
        assert channel.closed and channel.shutdown_complete
    finally:
        sender.close()
        receiver.close()


@pytest.mark.anyio
@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("partial_header", [False, True])
async def test_idle_and_partial_read_revalidate_within_original_idle_tick(
    asynchronous: bool,
    partial_header: bool,
) -> None:
    sender, receiver = channel_pair()
    live = True
    checks = 0

    def revoke() -> None:
        nonlocal live
        live = False

    def guard() -> None:
        nonlocal checks
        checks += 1
        if not live:
            raise ContentError("PATCH_REVOKED")

    if partial_header:
        sender._socket.send(encode_frame(NativeKind.RECORD, 1, b"opaque")[:13])
    timer = threading.Timer(0.02, revoke)
    timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(ContentError, match="PATCH_REVOKED"):
            if asynchronous:
                await receiver.areceive(
                    frozenset({NativeKind.RECORD}), deadline_ns=deadline_after(1), guard=guard
                )
            else:
                receiver.receive(
                    frozenset({NativeKind.RECORD}), deadline_ns=deadline_after(1), guard=guard
                )
        assert checks >= 2
        assert time.monotonic() - started < 0.2
        assert receiver.closed and receiver.shutdown_complete
    finally:
        timer.cancel()
        timer.join(timeout=1)
        sender.close()
        receiver.close()
