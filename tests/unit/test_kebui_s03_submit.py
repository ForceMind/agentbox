"""S02-S17: real isolated issuer/owner/consumer and body-independent metadata."""

from __future__ import annotations

import asyncio
import copy
import inspect
import itertools
import json
import os
import pickle
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from types import CoroutineType
from typing import Any, Never, cast

import pytest
from agentbox_protocol.noise_nx import NoiseTransport, NXInitiator
from agentbox_protocol.s03_submit import (
    CONFIRM_DOMAIN,
    READY_DOMAIN,
    S03Error,
    aad,
    build_context,
    decode_frame,
    encode_frame,
)
from agentbox_runtime import kebui_s03_submit as module
from agentbox_runtime.kebui_admission import AdmissionPhase, KebuiAdmissionError
from agentbox_runtime.kebui_content_admission import SyntheticContentHandle, synthetic_pool_usage
from agentbox_runtime.kebui_s03_submit import (
    CHANNEL_RESERVATION_BYTES,
    PYTHON_COPY_LIMITS,
    PYTHON_COPY_SUBTOTAL,
    SyntheticS03Recovery,
    SyntheticS03TestRoot,
    SyntheticSubmitPermit,
    s03_usage,
)

_FIXTURE = Path(__file__).parents[1] / "fixtures/kebui_s03_submit/v1.json"
_NUMBERS = itertools.count(10000)
_BODY_CASES = (
    "minimum",
    "ascii_16k",
    "nul_16k",
    "utf8_4byte_16k",
    "bom",
    "quotes_backslashes",
    "crlf",
    "lf",
    "decomposed",
    "composed",
    "mixed_canary",
)


def body_for_case(case: str) -> bytes:
    # Materialize only this case, after the root reserved its channel. Never
    # retain a global table of all maximum-sized test-oracle plaintexts.
    if case == "ascii_16k":
        return b"x" * 16384
    if case == "nul_16k":
        return b"\0" * 16384
    if case == "utf8_4byte_16k":
        return b"\xf0\x9f\x98\x80" * 4096
    return {
        "minimum": b"x",
        "bom": b"\xef\xbb\xbftext",
        "quotes_backslashes": b'"\\',
        "crlf": b"a\r\n",
        "lf": b"a\n",
        "decomposed": b"e\xcc\x81",
        "composed": b"\xc3\xa9",
        "mixed_canary": b"synthetic S03\r\n\0",
    }[case]


def fresh_context() -> dict[str, str]:
    context: dict[str, str] = json.loads(_FIXTURE.read_text())["context"]
    number = next(_NUMBERS)
    for key, prefix in (
        ("request_id", "kreq_"),
        ("channel_id", "ks03c_"),
        ("source_lease_id", "ks03l_"),
    ):
        context[key] = f"{prefix}{number:032x}"
    return context


class Clock:
    def __init__(self) -> None:
        self.value: object = 100000000000
        self.calls = 0

    def __call__(self) -> int:
        self.calls += 1
        if isinstance(self.value, BaseException):
            raise self.value
        return cast(int, self.value)


@dataclass
class Harness:
    root: SyntheticS03TestRoot
    endpoint: object
    clock: Clock
    fixture: dict[str, str]


@asynccontextmanager
async def harness(directory: Path, *, deadline: int = 112000000000) -> AsyncIterator[Harness]:
    clock = Clock()
    context = fresh_context()
    endpoint = object()
    root = SyntheticS03TestRoot.create_for_test(
        directory=directory,
        endpoint=endpoint,
        context=context,
        clock=clock,
        deadline_ns=deadline,
        enabled=True,
    )
    try:
        yield Harness(root, endpoint, clock, context)
    finally:
        await root.aclose()
        assert root.pool_drained
        assert s03_usage().channel_reserved_bytes == 0


def handshake(h: Harness) -> NoiseTransport:
    context = h.root.context
    initiator = NXInitiator(context.prologue)  # fresh ephemerals, no injection
    if not h.root._opened:
        h.root.open(h.endpoint)
    attest = h.root.receive_handshake(
        encode_frame(context.cd, "KEY_INIT", 0, initiator.write_message1()), h.endpoint
    )
    assert initiator.read_message2(decode_frame(attest, context.cd, "KEY_ATTEST", 0)) == b""
    web = initiator.take_transport()
    assert web.remote_static_public_key == context.runtime_pin
    confirm = web.send.encrypt(
        CONFIRM_DOMAIN + context.digest + web.handshake_hash,
        aad(context.digest, web.handshake_hash, 0, 3, 0),
    )
    ready = h.root.receive_handshake(
        encode_frame(context.cd, "KEY_CONFIRM", 0, confirm), h.endpoint
    )
    plaintext = web.receive.decrypt(
        decode_frame(ready, context.cd, "KEY_READY", 0),
        aad(context.digest, web.handshake_hash, 1, 4, 0),
    )
    assert plaintext == READY_DOMAIN + context.digest + web.handshake_hash
    return web


def submit_frame(h: Harness, web: NoiseTransport, body: bytes) -> bytes:
    context = h.root.context
    data = web.send.encrypt(body, aad(context.digest, web.handshake_hash, 0, 5, 1))
    return encode_frame(context.cd, "SUBMIT", 1, data)


def assert_safe(error: BaseException) -> None:
    assert error.__cause__ is error.__context__ is None
    rendered = "".join(traceback.format_exception(error))
    assert "private-s03" not in rendered
    assert "private-s03" not in repr(error.args)


@pytest.mark.parametrize("case", _BODY_CASES)
def test_original_bytes_reach_unchanged_consumer_once(tmp_path: Path, case: str) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            body = body_for_case(case)
            web = handshake(h)
            raw = submit_frame(h, web, body)
            handle = h.root.receive_submit_and_prepare(raw, h.endpoint, oracle_case=case)
            raw = b""
            assert h.root.state == "CLOSED"
            assert not h.root._source_revoked
            assert all(
                h.root.copy_live[k] == 0
                for k in ("wire", "base64", "plaintext", "ciphertext", "oracle")
            )
            result = await h.root.submit_prepared(handle)
            assert result.phase is AdmissionPhase.ACKNOWLEDGED
            assert h.root.consumer.calls == 1
            assert h.root.consumer.byte_count == len(body)
            assert h.root.consumer.last_body_identity == h.root.decrypted_identity
            assert h.root.original_identity_match
            assert h.root.owner.read(handle.request) == result
            with pytest.raises(S03Error):
                await h.root.submit_prepared(handle)
            assert h.root.consumer.calls == 1
            journal = (tmp_path / "admission.json").read_bytes()
            if case == "mixed_canary":
                assert body not in journal

    asyncio.run(run())


@pytest.mark.parametrize(
    "body", [b"\xff", b"\xed\xa0\x80", b"\xc0\xaf", b"\xf0\x9f", b"\xf4\x90\x80\x80"]
)
def test_invalid_utf8_cleans_prepared_staging_and_exception_payload(
    tmp_path: Path, body: bytes
) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            raw = submit_frame(h, handshake(h), body)
            with pytest.raises(KebuiAdmissionError, match="invalid_content") as caught:
                h.root.receive_submit_and_prepare(raw, h.endpoint)
            assert_safe(caught.value)
            assert h.root.pool_drained
            assert h.root.consumer.calls == 0
            assert h.root.state == "CLOSED"
            tb = caught.value.__traceback__
            while tb:
                if tb.tb_frame.f_code.co_name == "receive_submit_and_prepare":
                    assert tb.tb_frame.f_locals["raw"] is tb.tb_frame.f_locals["body"] is None
                tb = tb.tb_next

    asyncio.run(run())


def test_default_off_root_and_nontransferable_permit(tmp_path: Path) -> None:
    with pytest.raises(S03Error, match="s03_unavailable"):
        SyntheticS03TestRoot()
    with pytest.raises(S03Error):
        SyntheticS03TestRoot.create_for_test(
            directory=tmp_path,
            endpoint=object(),
            context=fresh_context(),
            clock=Clock(),
            deadline_ns=112000000000,
        )

    async def run() -> None:
        async with harness(tmp_path) as h:
            for item in (h.root, h.root.permit):
                for operation in (copy.copy, copy.deepcopy, pickle.dumps):
                    with pytest.raises(S03Error):
                        operation(item)
            with pytest.raises(S03Error):
                SyntheticSubmitPermit(h.root, h.endpoint, object())
            with pytest.raises(S03Error):
                type("SubPermit", (SyntheticSubmitPermit,), {})
            with pytest.raises(S03Error):
                h.root.receive_handshake(b"x", object())
            assert h.root.consumer.calls == 0

    asyncio.run(run())


def test_snapshot_root_and_endpoint_identity(tmp_path: Path) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            original = h.root.context.request_id
            h.fixture["request_id"] = "kreq_" + "f" * 32
            assert h.root.context.request_id == original
            with pytest.raises(S03Error):
                h.root.open(object())
            assert h.root.state == "CLOSED"

    asyncio.run(run())


def test_whole_channel_reserved_before_context_copy_and_across_idle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: list[int] = []
    build = build_context

    def guarded(value: object) -> Any:
        observed.append(s03_usage().channel_reserved_bytes)
        return build(value)

    monkeypatch.setattr(module, "build_context", guarded)

    async def run() -> None:
        async with harness(tmp_path) as h:
            assert observed == [CHANNEL_RESERVATION_BYTES]
            h.root.open(h.endpoint)
            await asyncio.sleep(0)
            assert s03_usage().channel_reserved_bytes == CHANNEL_RESERVATION_BYTES
            other = tmp_path / "other"
            other.mkdir(mode=0o700)
            with pytest.raises(S03Error, match="s03_busy"):
                SyntheticS03TestRoot.create_for_test(
                    directory=other,
                    endpoint=object(),
                    context=fresh_context(),
                    clock=Clock(),
                    deadline_ns=112000000000,
                    enabled=True,
                )
            assert observed == [CHANNEL_RESERVATION_BYTES]
            handshake(h)
            assert s03_usage().channel_reserved_bytes == CHANNEL_RESERVATION_BYTES
            assert PYTHON_COPY_SUBTOTAL == 686106 <= CHANNEL_RESERVATION_BYTES
            assert all(h.root.copy_peaks[k] <= limit for k, limit in PYTHON_COPY_LIMITS.items())

    asyncio.run(run())


@pytest.mark.parametrize("change", ["scope", "execution", "endpoint", "context"])
def test_current_binding_changes_prevent_prepare(tmp_path: Path, change: str) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            raw = submit_frame(h, handshake(h), b"x")
            endpoint = h.endpoint
            if change == "scope":
                h.root._scope = build_context(fresh_context()).scope
                h.root._current_valid = False
            elif change == "execution":
                h.root._execution_id = "kexe_" + "f" * 32
            elif change == "endpoint":
                endpoint = object()
            else:
                h.root.context = build_context(h.fixture)
            with pytest.raises((S03Error, KebuiAdmissionError)):
                h.root.receive_submit_and_prepare(raw, endpoint)
            assert h.root.pool_drained
            assert h.root.consumer.calls == 0

    asyncio.run(run())


@pytest.mark.parametrize(
    "value",
    [
        True,
        -1,
        1.0,
        float("nan"),
        2**64,
        "100",
        RuntimeError("private-s03-clock-canary"),
        99999999999,
    ],
)
def test_bad_source_clock_is_sticky_but_metadata_guard_remains_live(
    tmp_path: Path, value: object
) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            handle = h.root.receive_submit_and_prepare(
                submit_frame(h, handshake(h), b"x"), h.endpoint
            )
            result = await h.root.submit_prepared(handle)
            h.clock.value = value
            h.root.deadlines.fire_for_test()
            count = h.clock.calls
            assert h.root.owner.read(handle.request) == result
            assert h.clock.calls == count
            h.clock.value = 100000000001
            with pytest.raises(S03Error):
                h.root._check_source()
            assert h.root._source_revoked
            assert h.root.consumer.calls == 1

    asyncio.run(run())


def test_source_expiry_wakes_held_readiness_to_unknown_without_clock_in_metadata(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            h.root.readiness.hold()
            handle = h.root.receive_submit_and_prepare(
                submit_frame(h, handshake(h), b"x"), h.endpoint
            )
            task = asyncio.create_task(h.root.submit_prepared(handle))
            await h.root.readiness.entered.wait()
            h.clock.value = 112000000000
            h.root.deadlines.fire_for_test()
            result = await asyncio.wait_for(task, 1)
            assert result.phase is AdmissionPhase.UNKNOWN
            assert h.root.consumer.calls == 0
            assert h.root.pool_drained
            calls = h.clock.calls
            assert h.root.owner.read(handle.request) == result
            assert h.clock.calls == calls

    asyncio.run(run())


def test_canceled_waiter_retains_original_worker_then_normal_close_allows_effect(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            h.root.readiness.hold()
            handle = h.root.receive_submit_and_prepare(
                submit_frame(h, handshake(h), b"x"), h.endpoint
            )
            task = asyncio.create_task(h.root.submit_prepared(handle))
            await h.root.readiness.entered.wait()
            frame = cast("CoroutineType[Any, Any, Any]", task.get_coro()).cr_frame
            assert frame is not None
            assert set(frame.f_locals) <= {"self", "handle", "task"}
            assert all(not isinstance(value, bytes) for value in frame.f_locals.values())
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert synthetic_pool_usage().worker_slots == 1
            assert synthetic_pool_usage().retained_bytes == 1
            h.root.close_transport()
            assert not h.root._source_revoked
            h.root.readiness.release()
            await h.root.owner.wait_for_idle()
            assert h.root.consumer.calls == 1
            assert h.root.owner.read(handle.request).phase is AdmissionPhase.ACKNOWLEDGED  # type: ignore[union-attr]

    asyncio.run(run())


def test_cancellation_before_admission_discards_prepared(tmp_path: Path) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            handle = h.root.receive_submit_and_prepare(
                submit_frame(h, handshake(h), b"x"), h.endpoint
            )
            task = asyncio.current_task()
            assert task is not None
            task.cancel()
            with pytest.raises(S03Error):
                await h.root.submit_prepared(handle)
            task.uncancel()
            with suppress(asyncio.CancelledError):
                await asyncio.sleep(0)
            assert h.root.pool_drained
            assert h.root.owner.read(handle.request) is None

    asyncio.run(run())


@pytest.mark.parametrize("phase", ["KEY_INIT", "KEY_CONFIRM", "SUBMIT"])
def test_missing_inbound_record_expires_without_new_message(tmp_path: Path, phase: str) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            h.root.open(h.endpoint)
            if phase == "KEY_CONFIRM":
                initiator = NXInitiator(h.root.context.prologue)
                h.root.receive_handshake(
                    encode_frame(h.root.context.cd, "KEY_INIT", 0, initiator.write_message1()),
                    h.endpoint,
                )
            elif phase == "SUBMIT":
                handshake(h)
            waiter = asyncio.create_task(h.root.deadlines.wait_io(asyncio.Event().wait()))
            await asyncio.sleep(0)
            assert s03_usage().active_waiters == 1
            h.clock.value = 112000000000 if phase == "SUBMIT" else 102000000000
            h.root.deadlines.fire_for_test()
            with pytest.raises((S03Error, asyncio.CancelledError)):
                await waiter
            assert h.root.state == "CLOSED"
            assert h.root._session is None
            assert not h.root.deadlines.waiting
            assert h.root.consumer.calls == 0
            assert s03_usage().channel_reserved_bytes == CHANNEL_RESERVATION_BYTES

    asyncio.run(run())


def test_real_scheduled_source_timer_wakes_without_polling(tmp_path: Path) -> None:
    async def run() -> None:
        start = time.monotonic_ns()
        context, endpoint = fresh_context(), object()

        def clock() -> int:
            return 100000000000 + time.monotonic_ns() - start

        root = SyntheticS03TestRoot.create_for_test(
            directory=tmp_path,
            endpoint=endpoint,
            context=context,
            clock=clock,
            deadline_ns=100030000000,
            enabled=True,
        )
        try:
            root.open(endpoint)
            with pytest.raises((S03Error, asyncio.CancelledError)):
                await asyncio.wait_for(root.deadlines.wait_io(asyncio.Event().wait()), 1)
            assert root._source_revoked and root.state == "CLOSED"
            assert not root.deadlines.scheduled
        finally:
            await root.aclose()

    asyncio.run(run())


def test_delayed_channel_creation_does_not_renew_original_lease(tmp_path: Path) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            h.clock.value = 111900000000
            web = handshake(h)
            assert h.root.deadlines._target == 112000000000
            h.clock.value = 112000000000
            raw = submit_frame(h, web, b"x")
            with pytest.raises(S03Error, match="s03_revoked"):
                h.root.receive_submit_and_prepare(raw, h.endpoint)
            assert h.root.pool_drained and h.root.consumer.calls == 0

    asyncio.run(run())


def test_bad_io_error_does_not_retain_original_exception_in_public_traceback(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:

            async def bad() -> bytes:
                raise ValueError("private-s03-io-canary")

            with pytest.raises(S03Error) as caught:
                await h.root.deadlines.wait_io(bad())
            assert_safe(caught.value)
            tb = caught.value.__traceback__
            while tb:
                if tb.tb_frame.f_code.co_name == "wait_io":
                    for name in ("task", "done", "pending", "result", "operation"):
                        assert tb.tb_frame.f_locals[name] is None
                tb = tb.tb_next
            assert not h.root.deadlines.waiting

    asyncio.run(run())


def test_pending_io_retains_reservation_until_cancellation_really_drains(tmp_path: Path) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            entered, release = asyncio.Event(), asyncio.Event()

            async def stubborn() -> None:
                entered.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    await release.wait()

            waiter = asyncio.create_task(h.root.deadlines.wait_io(stubborn()))
            await entered.wait()
            h.root.revoke_source()
            await asyncio.sleep(0)
            assert h.root.deadlines.waiting
            assert s03_usage().channel_reserved_bytes == CHANNEL_RESERVATION_BYTES
            release.set()
            with pytest.raises((S03Error, asyncio.CancelledError)):
                await waiter
            assert not h.root.deadlines.waiting

    asyncio.run(run())


def test_duplicate_frame_and_wrong_aad_are_terminal(tmp_path: Path) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            web = handshake(h)
            data = web.send.encrypt(b"x", b"foreign-domain")
            raw = encode_frame(h.root.context.cd, "SUBMIT", 1, data)
            with pytest.raises(S03Error) as caught:
                h.root.receive_submit_and_prepare(raw, h.endpoint)
            assert_safe(caught.value)
            with pytest.raises(S03Error):
                h.root.receive_submit_and_prepare(raw, h.endpoint)
            assert h.root.consumer.calls == 0 and h.root.pool_drained

    asyncio.run(run())


def test_no_ephemeral_injection_or_body_reader_in_admitted_api() -> None:
    assert "ephemeral" not in str(inspect.signature(SyntheticS03TestRoot.create_for_test))
    assert "ephemeral" not in str(inspect.signature(SyntheticS03TestRoot.open))
    assert not hasattr(SyntheticS03TestRoot, "decrypt")
    assert not hasattr(SyntheticS03TestRoot, "body")


def test_fresh_actual_handshakes_have_distinct_ephemerals(tmp_path: Path) -> None:
    async def run() -> None:
        values = []
        for index in range(2):
            directory = tmp_path / str(index)
            directory.mkdir(mode=0o700)
            async with harness(directory) as h:
                initiator = NXInitiator(h.root.context.prologue)
                response = h.root.receive_handshake(
                    encode_frame(h.root.context.cd, "KEY_INIT", 0, initiator.write_message1()),
                    h.endpoint,
                )
                values.append(decode_frame(response, h.root.context.cd, "KEY_ATTEST", 0)[:32])
        assert values[0] != values[1]
        assert all(
            value
            != bytes.fromhex("50bb406cf2cc8b70ffaf66973d06c7324549d29f77602828dadad475021b107a")
            for value in values
        )

    asyncio.run(run())


def test_thread_current_guard_revoke_serializes_with_prepare(tmp_path: Path) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            raw = submit_frame(h, handshake(h), b"x")
            entered = threading.Event()
            done = threading.Event()

            def revoke() -> None:
                entered.set()
                h.root.revoke_source()
                done.set()

            with h.root.guard(h.root.context.scope):
                thread = threading.Thread(target=revoke)
                thread.start()
                assert entered.wait(1)
                assert not done.wait(0.02)
                handle = h.root.receive_submit_and_prepare(raw, h.endpoint)
            thread.join(1)
            assert done.is_set()
            with pytest.raises(S03Error):
                await h.root.submit_prepared(handle)
            assert h.root.consumer.calls == 0

    asyncio.run(run())


def test_fork_pid_mismatch_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            real = os.getpid()
            with monkeypatch.context() as patch:
                patch.setattr(os, "getpid", lambda: real + 1)
                with pytest.raises(S03Error):
                    h.root.open(h.endpoint)
            assert h.root.consumer.calls == 0

    asyncio.run(run())


def test_recovery_requires_original_bounded_catalog_and_never_mints_source(tmp_path: Path) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            handle = h.root.receive_submit_and_prepare(
                submit_frame(h, handshake(h), b"x"), h.endpoint
            )
            await h.root.submit_prepared(handle)
            catalog = h.root.recovery_catalog("lost_ack_recovery", handle.request)
            context = h.fixture
        for bad in [
            None,
            {},
            {**catalog, "inode": 0},
            {**catalog, "scenario": "other"},
            {**catalog, "directory": "/missing"},
        ]:
            with pytest.raises(S03Error, match="s03_unavailable"):
                SyntheticS03Recovery.open(
                    bad, directory=tmp_path, context=context, scenario="lost_ack_recovery"
                )
        recovery = SyntheticS03Recovery.open(
            catalog, directory=tmp_path, context=context, scenario="lost_ack_recovery"
        )
        try:
            assert recovery.read().phase is AdmissionPhase.UNKNOWN  # type: ignore[union-attr]
            assert recovery.owner._content is None
            with pytest.raises(KebuiAdmissionError):
                await recovery.owner.submit(recovery.request)
        finally:
            recovery.close()

    asyncio.run(run())


async def _capacity_scenario() -> None:
    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)
        first: dict[str, str] | None = None
        for index in range(255):
            target = directory / str(index)
            target.mkdir(mode=0o700)
            async with harness(target) as h:
                if first is None:
                    first = h.fixture
        assert s03_usage().tombstones == 255
        target = directory / "overflow"
        target.mkdir(mode=0o700)
        with pytest.raises(S03Error, match="s03_busy"):
            SyntheticS03TestRoot.create_for_test(
                directory=target,
                endpoint=object(),
                context=fresh_context(),
                clock=Clock(),
                deadline_ns=112000000000,
                enabled=True,
            )
        assert s03_usage().tombstone_reserved_bytes == 261120


def test_process_lifetime_255_tombstones_no_reset() -> None:
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "capacity"],
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout == b"capacity verified\n"
    assert completed.stderr == b""


def test_late_handshake_timer_is_not_an_expiry_bypass(tmp_path: Path) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            context = h.root.context
            initiator = NXInitiator(context.prologue)
            raw = h.root.receive_handshake(
                encode_frame(context.cd, "KEY_INIT", 0, initiator.write_message1()),
                h.endpoint,
            )
            initiator.read_message2(decode_frame(raw, context.cd, "KEY_ATTEST", 0))
            web = initiator.take_transport()
            data = web.send.encrypt(
                CONFIRM_DOMAIN + context.digest + web.handshake_hash,
                aad(context.digest, web.handshake_hash, 0, 3, 0),
            )
            h.clock.value = 102000000000  # Do NOT dispatch the timer callback.
            with pytest.raises(S03Error, match="s03_revoked"):
                h.root.receive_handshake(
                    encode_frame(context.cd, "KEY_CONFIRM", 0, data), h.endpoint
                )
            assert h.root.state == "CLOSED"
            assert not h.root._source_revoked
            assert h.root.consumer.calls == 0

    asyncio.run(run())


def test_context_buffers_retire_even_through_retained_permit(tmp_path: Path) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            captured = h.root.context
            permit = h.root.permit
            assert captured.encoded and captured.runtime_pin
            scope = captured.scope
        assert captured.encoded == captured.runtime_pin == captured.digest == b""
        assert permit._context.encoded == b""
        assert captured.scope == scope
        assert s03_usage().channel_reserved_bytes == 0

    asyncio.run(run())


def test_catalog_values_bounded_before_encoder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            handle = h.root.receive_submit_and_prepare(
                submit_frame(h, handshake(h), b"x"), h.endpoint
            )
            await h.root.submit_prepared(handle)
            catalog = h.root.recovery_catalog("lost_ack_recovery", handle.request)
            context = h.fixture
        calls = 0
        dumps = json.dumps

        def tracked(*args: Any, **kwargs: Any) -> str:
            nonlocal calls
            calls += 1
            return dumps(*args, **kwargs)

        monkeypatch.setattr(json, "dumps", tracked)
        for key, value in (
            ("content_admission_ref", "x" * 8192),
            ("scope", {"scope": "x" * 8192}),
            ("inode", 2**64),
            ("device", True),
            ("scope", []),
        ):
            with pytest.raises(S03Error):
                SyntheticS03Recovery.open(
                    {**catalog, key: value},
                    directory=tmp_path,
                    context=context,
                    scenario="lost_ack_recovery",
                )
        assert calls == 0

    asyncio.run(run())


def test_failed_request_and_used_channel_lease_tombstones_never_reopen(tmp_path: Path) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            original = dict(h.fixture)
            with pytest.raises(S03Error):
                h.root.receive_handshake(b"bad", h.endpoint)
        for index, binding in enumerate(
            (
                original,
                {**fresh_context(), "channel_id": original["channel_id"]},
                {**fresh_context(), "source_lease_id": original["source_lease_id"]},
            )
        ):
            directory = tmp_path / str(index)
            directory.mkdir(mode=0o700)
            with pytest.raises(S03Error, match="s03_revoked"):
                SyntheticS03TestRoot.create_for_test(
                    directory=directory,
                    endpoint=object(),
                    context=binding,
                    clock=Clock(),
                    deadline_ns=112000000000,
                    enabled=True,
                )

    asyncio.run(run())


def test_nested_execution_mutation_cannot_be_captured_by_issuer_prepare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            raw = submit_frame(h, handshake(h), b"x")
            original = h.root.issuer.prepare

            def changed(*args: Any) -> SyntheticContentHandle:
                h.root._execution_id = "kexe_" + "f" * 32
                return original(*args)

            monkeypatch.setattr(h.root.issuer, "prepare", changed)
            with pytest.raises(KebuiAdmissionError, match="owner_unavailable"):
                h.root.receive_submit_and_prepare(raw, h.endpoint)
            assert h.root.pool_drained and h.root.consumer.calls == 0

    asyncio.run(run())


def test_simultaneous_ingress_is_busy_before_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            web = handshake(h)
            raw = submit_frame(h, web, b"x")
            entered, release = threading.Event(), threading.Event()
            original = h.root.issuer.prepare
            holder: list[SyntheticContentHandle] = []

            def delayed(*args: Any) -> SyntheticContentHandle:
                entered.set()
                assert release.wait(2)
                return original(*args)

            monkeypatch.setattr(h.root.issuer, "prepare", delayed)

            def first() -> None:
                holder.append(h.root.receive_submit_and_prepare(raw, h.endpoint))

            thread = threading.Thread(target=first)
            thread.start()
            assert entered.wait(1)
            before = dict(h.root.copy_live)
            try:
                with pytest.raises(S03Error, match="s03_busy"):
                    h.root.receive_submit_and_prepare(raw, h.endpoint)
                assert h.root.copy_live == before
            finally:
                release.set()
                thread.join(2)
            assert len(holder) == 1
            result = await h.root.submit_prepared(holder[0])
            assert result.phase is AdmissionPhase.ACKNOWLEDGED
            assert h.root.consumer.calls == 1

    asyncio.run(run())


def test_thread_source_revoke_wakes_registered_readiness_safely(tmp_path: Path) -> None:
    async def run() -> None:
        asyncio.get_running_loop().set_debug(True)
        async with harness(tmp_path) as h:
            h.root.readiness.hold()
            handle = h.root.receive_submit_and_prepare(
                submit_frame(h, handshake(h), b"x"), h.endpoint
            )
            waiter = asyncio.create_task(h.root.submit_prepared(handle))
            await h.root.readiness.entered.wait()
            await asyncio.sleep(0)
            failures: list[bool] = []

            def close_from_thread() -> None:
                try:
                    h.root.revoke_source()
                except Exception:
                    failures.append(True)

            thread = threading.Thread(target=close_from_thread)
            thread.start()
            thread.join(1)
            if failures:
                h.root.readiness.release()  # Only cleanup of the intentionally failing probe.
            result = await asyncio.wait_for(waiter, 1)
            assert result.phase is AdmissionPhase.UNKNOWN
            assert h.root.consumer.calls == 0
            assert not failures

    asyncio.run(run())


@pytest.mark.parametrize("field", list(json.loads(_FIXTURE.read_text())["context"]))
def test_every_valid_context_mutation_fails_before_prepare(tmp_path: Path, field: str) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            changed = dict(h.fixture)
            value = changed[field]
            if field == "agent_type":
                changed[field] = "claude"
            elif field in {"execution_kind", "adapter_profile"}:
                changed[field] = "unavailable-profile"
            elif field in {
                "auth_epoch",
                "project_revision",
                "binding_revision",
                "host_revision",
                "runtime_epoch",
                "api_authority_epoch",
                "conversation_revision",
                "generation",
            }:
                changed[field] = str(int(value) + 1)
            else:
                changed[field] = value[:-1] + ("e" if value[-1] != "e" else "f")
            if field in {"execution_kind", "adapter_profile"}:
                with pytest.raises(S03Error):
                    build_context(changed)
                return
            foreign = build_context(changed)
            initiator = NXInitiator(foreign.prologue)
            with pytest.raises(S03Error):
                h.root.receive_handshake(
                    encode_frame(foreign.cd, "KEY_INIT", 0, initiator.write_message1()), h.endpoint
                )
            assert h.root.pool_drained and h.root.consumer.calls == 0

    asyncio.run(run())


def test_overflowing_handshake_tick_rejected_without_rebasing(tmp_path: Path) -> None:
    async def run() -> None:
        endpoint = object()
        root = SyntheticS03TestRoot.create_for_test(
            directory=tmp_path,
            endpoint=endpoint,
            context=fresh_context(),
            clock=lambda: 2**64 - 2,
            deadline_ns=2**64 - 1,
            enabled=True,
        )
        try:
            with pytest.raises(S03Error):
                root.open(endpoint)
            assert root._source_revoked and root.state == "CLOSED"
        finally:
            await root.aclose()

    asyncio.run(run())


def test_oversize_rejected_before_base64_or_crypto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def run() -> None:
        async with harness(tmp_path) as h:
            called = False

            def forbidden(*args: Any, **kwargs: Any) -> Never:
                nonlocal called
                called = True
                raise AssertionError("unexpected decoder")

            monkeypatch.setattr("agentbox_protocol.s03_submit.base64.b64decode", forbidden)
            with pytest.raises(S03Error):
                h.root.receive_handshake(b"x" * 22032, h.endpoint)
            assert not called
            assert all(h.root.copy_peaks[k] == 0 for k in ("wire", "base64", "plaintext"))

    asyncio.run(run())


if __name__ == "__main__":
    if sys.argv[1:] == ["capacity"]:
        asyncio.run(_capacity_scenario())
        print("capacity verified")
    else:
        raise SystemExit(2)
