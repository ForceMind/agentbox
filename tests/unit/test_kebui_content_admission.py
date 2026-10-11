"""Bounded process-wide synthetic custody; no production consumer or source."""

from __future__ import annotations

import asyncio
import copy
import os
import pickle
import secrets
import threading
from pathlib import Path
from typing import Any, cast

import pytest
from agentbox_runtime import kebui_content_admission as content_module
from agentbox_runtime.kebui_admission import (
    AdmissionPhase,
    KebuiAdmissionError,
    KebuiTestAdmissionOwner,
    SyntheticTerminalReceipt,
)
from agentbox_runtime.kebui_content_admission import (
    MAX_BODY_BYTES,
    MAX_BODY_LEDGER_BYTES,
    MAX_ENTRIES,
    MAX_RETAINED_BYTES,
    MAX_VALIDATION_WORKSPACE_BYTES,
    SyntheticBodyConsumer,
    SyntheticContentHandle,
    SyntheticContentIssuer,
    synthetic_pool_usage,
)
from test_kebui_admission import Harness, assert_safe, request
from test_kebui_admission import h as h


class BytesSubclass(bytes):
    pass


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        "text",
        bytearray(b"x"),
        memoryview(b"x"),
        BytesSubclass(b"x"),
        b"",
        b"x" * 16385,
        b"\xff",
        b"\xed\xa0\x80",
        b"\xc0\xaf",
        b"\xf4\x90\x80\x80",
    ],
    ids=[
        "none",
        "bool",
        "str",
        "bytearray",
        "memoryview",
        "subclass",
        "empty",
        "oversize",
        "invalid",
        "surrogate",
        "overlong",
        "above-unicode",
    ],
)
def test_only_bounded_exact_strict_utf8_bytes(h: Harness, value: object) -> None:
    before = synthetic_pool_usage()
    with pytest.raises(KebuiAdmissionError, match="invalid_content") as caught:
        h.issuer.prepare(request(2).request_id, h.item.scope, cast(bytes, value))
    assert_safe(caught.value)
    assert synthetic_pool_usage() == before


@pytest.mark.parametrize(
    "body",
    [b"x", b"x" * 16384, "😀".encode() * 4096, b"\x00"],
    ids=["minimum", "maximum", "multibyte-maximum", "nul"],
)
def test_valid_extremes_keep_original_exact_object(h: Harness, body: bytes) -> None:
    async def run() -> None:
        handle = h.prepare(2, body)
        result = await h.gate.submit(handle.request, handle)
        assert result.phase is AdmissionPhase.ACKNOWLEDGED
        assert h.dispatch.consumer.last_body_identity == id(body)
        assert h.dispatch.consumer.byte_count == len(body)

    asyncio.run(run())


@pytest.mark.parametrize(
    "left,right",
    [(b"a\n", b"a\r\n"), ("é".encode(), "é".encode()), (b"text", b"text "), (b"one", b"two")],
    ids=["line-ending", "unicode-normalization", "whitespace", "bytes"],
)
def test_exact_equality_never_normalizes(h: Harness, left: bytes, right: bytes) -> None:
    handle = h.prepare(2, left)
    assert h.prepare(2, left) is handle
    before = synthetic_pool_usage()
    with pytest.raises(KebuiAdmissionError, match="conflict") as caught:
        h.prepare(2, right)
    assert_safe(caught.value)
    assert synthetic_pool_usage() == before
    assert h.dispatch.consumer.calls == 0


def test_issuer_mints_ref_and_captures_execution_only_under_current_guard(h: Harness) -> None:
    assert h.item.content_admission_ref != request().content_admission_ref
    assert not hasattr(h.handle, "body")
    assert not hasattr(h.handle, "load")
    assert not hasattr(h.handle, "read")
    assert repr(h.handle) == "<SyntheticContentHandle>"
    h.owner.execution_id = "kexe_" + "2" * 32
    with pytest.raises(KebuiAdmissionError, match="conflict"):
        h.issuer.prepare(h.item.request_id, h.item.scope, h.body)
    assert synthetic_pool_usage().entries == 1


def test_unbound_issuer_cannot_prepare(tmp_path: Path) -> None:
    issuer = SyntheticContentIssuer(deadline_ns=100, clock=lambda: 1)
    try:
        with pytest.raises(KebuiAdmissionError, match="content_unavailable"):
            issuer.prepare(request().request_id, request().scope, b"x")
        assert synthetic_pool_usage().entries == 0
    finally:
        issuer.close()


@pytest.mark.parametrize(
    "clock",
    [True, -1, 2**64, 1.5, float("nan"), None],
    ids=["bool", "negative", "overflow", "float", "nan", "none"],
)
def test_source_creation_rejects_non_u64_clock(clock: object) -> None:
    with pytest.raises(KebuiAdmissionError, match="content_unavailable") as caught:
        SyntheticContentIssuer(deadline_ns=100, clock=lambda: cast(int, clock))
    assert_safe(caught.value)
    assert synthetic_pool_usage().entries == 0


@pytest.mark.parametrize(
    "deadline",
    [True, 0, -1, 2**64, 1.5, None, 1],
    ids=["bool", "zero", "negative", "overflow", "float", "none", "equal-now"],
)
def test_source_creation_rejects_invalid_or_nonfuture_deadline(deadline: object) -> None:
    with pytest.raises(KebuiAdmissionError, match="content_unavailable"):
        SyntheticContentIssuer(deadline_ns=cast(int, deadline), clock=lambda: 1)


@pytest.mark.parametrize(
    "tick",
    [True, -1, 2**64, 1.5, float("nan"), None, RuntimeError("private-port-canary"), 0, 10000],
    ids=["bool", "negative", "overflow", "float", "nan", "none", "raises", "rollback", "deadline"],
)
def test_clock_failures_and_expiry_sticky_close(h: Harness, tick: object) -> None:
    h.clock.now = tick
    with pytest.raises(KebuiAdmissionError, match="content_unavailable") as caught:
        h.issuer.prepare(h.item.request_id, h.item.scope, h.body)
    assert_safe(caught.value)
    h.clock.now = 2
    with pytest.raises(KebuiAdmissionError, match="content_unavailable"):
        h.issuer.prepare(h.item.request_id, h.item.scope, h.body)
    assert synthetic_pool_usage().entries == 0


def test_duplicate_never_extends_original_source_deadline(h: Harness) -> None:
    h.clock.now = 9999
    assert h.issuer.prepare(h.item.request_id, h.item.scope, h.body) is h.handle
    h.clock.now = 10000
    with pytest.raises(KebuiAdmissionError, match="content_unavailable"):
        h.issuer.prepare(h.item.request_id, h.item.scope, h.body)
    assert synthetic_pool_usage().entries == 0


def test_max_u64_deadline_accepts_zero_tick() -> None:
    issuer = SyntheticContentIssuer(deadline_ns=2**64 - 1, clock=lambda: 0)
    issuer.close()


def test_single_live_issuer_cannot_reset_pool(h: Harness) -> None:
    with pytest.raises(KebuiAdmissionError, match="busy"):
        SyntheticContentIssuer(deadline_ns=20000, clock=h.clock)
    assert synthetic_pool_usage().entries == 1


@pytest.mark.parametrize(
    "operation", [copy.copy, copy.deepcopy, pickle.dumps], ids=["copy", "deepcopy", "pickle"]
)
@pytest.mark.parametrize("target", ["issuer", "handle"])
def test_issuer_and_handle_cannot_transfer(h: Harness, operation: Any, target: str) -> None:
    with pytest.raises(KebuiAdmissionError, match="content_unavailable") as caught:
        operation(getattr(h, target))
    assert_safe(caught.value)


def test_forked_issuer_and_new_issuer_cannot_rebase_inherited_pool(h: Harness) -> None:
    child = os.fork()
    if child == 0:
        passed = 0
        for action in (
            lambda: h.issuer.prepare(h.item.request_id, h.item.scope, h.body),
            lambda: SyntheticContentIssuer(deadline_ns=10000, clock=lambda: 1),
            h.issuer.close,
        ):
            try:
                action()
            except KebuiAdmissionError:
                passed += 1
        os._exit(0 if passed == 3 else 10)
    _, status = os.waitpid(child, 0)
    assert os.waitstatus_to_exitcode(status) == 0
    assert synthetic_pool_usage().entries == 1


def test_new_issuer_same_request_and_bytes_never_recovers_old_acceptance(h: Harness) -> None:
    async def run() -> None:
        original = await h.submit()
        h.issuer.close()
        new = SyntheticContentIssuer(deadline_ns=20000, clock=h.clock)
        try:
            gate = KebuiTestAdmissionOwner(h.journal, h.owner, new, h.dispatch, enabled=True)
            fresh = new.prepare(h.item.request_id, h.item.scope, h.body)
            with pytest.raises(KebuiAdmissionError, match="content_unavailable"):
                await gate.submit(h.item, h.handle)
            with pytest.raises(KebuiAdmissionError, match="conflict"):
                await gate.submit(fresh.request, fresh)
            assert gate.read(h.item) == original
            assert h.dispatch.consumer.calls == 1
        finally:
            new.close()

    asyncio.run(run())


def test_255_retained_plus_one_staging_and_validation_workspace(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Retire the original prepared object without resetting pool accounting.
    h.issuer._discard_prepared(h.handle)
    body = b"x" * MAX_BODY_BYTES
    peaks: list[tuple[int, int, int]] = []
    original = content_module._valid_utf8

    def inspect(payload: bytes) -> bool:
        usage = synthetic_pool_usage()
        peaks.append((usage.retained_bytes, usage.staging_bytes, usage.validation_workspace_bytes))
        return original(payload)

    monkeypatch.setattr(content_module, "_valid_utf8", inspect)
    handles = [h.prepare(number, body) for number in range(1, MAX_ENTRIES + 1)]
    usage = synthetic_pool_usage()
    assert usage.entries == 255
    assert usage.retained_bytes == MAX_RETAINED_BYTES == 4177920
    assert h.issuer.prepare(handles[-1].request.request_id, h.item.scope, body) is handles[-1]
    with pytest.raises(KebuiAdmissionError, match="capacity"):
        h.prepare(256, body)
    assert max(retained + staging for retained, staging, _ in peaks) == MAX_BODY_LEDGER_BYTES
    assert max(workspace for _, _, workspace in peaks) == MAX_VALIDATION_WORKSPACE_BYTES == 81920
    assert synthetic_pool_usage() == usage


def test_staging_contention_immediately_busy_and_no_decode_overlap(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered, release, done = threading.Event(), threading.Event(), threading.Event()
    errors: list[str] = []
    original = content_module._valid_utf8

    def blocked(body: bytes) -> bool:
        entered.set()
        assert release.wait(3)
        return original(body)

    monkeypatch.setattr(content_module, "_valid_utf8", blocked)

    def first() -> None:
        try:
            h.prepare(2)
        except Exception:
            errors.append("first")

    def second() -> None:
        try:
            h.prepare(3)
        except KebuiAdmissionError as error:
            errors.append(str(error))
        finally:
            done.set()

    a = threading.Thread(target=first)
    a.start()
    assert entered.wait(3)
    b = threading.Thread(target=second)
    b.start()
    try:
        assert done.wait(1), "staging contender queued behind a held current-owner guard"
        assert errors == ["busy"]
    finally:
        release.set()
        a.join(3)
        b.join(3)
    assert synthetic_pool_usage().entries == 2


def test_busy_failed_submissions_do_not_accumulate_prepared_resources(h: Harness) -> None:
    async def run() -> None:
        await h.submit()
        for number in range(2, 270):
            handle = h.prepare(number)
            with pytest.raises(KebuiAdmissionError, match="busy"):
                await h.gate.submit(handle.request, handle)
            assert synthetic_pool_usage().entries == 1
            assert synthetic_pool_usage().worker_slots == 0

    asyncio.run(run())


def test_closed_worker_retains_global_charge_across_issuer_replacement(h: Harness) -> None:
    async def run() -> None:
        h.dispatch.release.clear()
        task = asyncio.create_task(h.submit())
        await h.dispatch.entered.wait()
        h.issuer.close()
        before = synthetic_pool_usage()
        assert before.entries == before.worker_slots == 1
        new = SyntheticContentIssuer(deadline_ns=20000, clock=h.clock)
        try:
            gate = KebuiTestAdmissionOwner(h.journal, h.owner, new, h.dispatch, enabled=True)
            handles = [
                new.prepare(request(i).request_id, h.item.scope, b"x") for i in range(2, 256)
            ]
            assert len(handles) == 254
            with pytest.raises(KebuiAdmissionError, match="capacity"):
                new.prepare(request(256).request_id, h.item.scope, b"x")
            h.dispatch.release.set()
            assert (await task).phase is AdmissionPhase.UNKNOWN
            assert h.dispatch.consumer.calls == 0
            assert synthetic_pool_usage().entries == 254
            assert gate.read(h.item) is not None
        finally:
            new.close()

    asyncio.run(run())


def test_close_cannot_release_body_during_fixed_synchronous_consumer(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered, attempted, closed = threading.Event(), threading.Event(), threading.Event()
    errors: list[str] = []
    original = SyntheticBodyConsumer._consume

    def effect(self: SyntheticBodyConsumer, body: bytes) -> Any:
        assert body is h.body
        entered.set()
        assert attempted.wait(3)
        assert not closed.wait(0.05)
        usage = synthetic_pool_usage()
        assert usage.retained_bytes == len(body) and usage.worker_slots == 1
        return original(self, body)

    monkeypatch.setattr(SyntheticBodyConsumer, "_consume", effect)

    def close() -> None:
        if not entered.wait(3):
            errors.append("no_effect")
            return
        attempted.set()
        h.issuer.close()
        closed.set()

    thread = threading.Thread(target=close)
    thread.start()
    try:
        asyncio.run(h.submit())
    finally:
        thread.join(3)
    assert not errors
    assert closed.is_set()
    assert h.dispatch.consumer.calls == 1
    assert synthetic_pool_usage().entries == 0


def test_failed_decode_chain_and_journal_never_store_body_or_hash(h: Harness) -> None:
    bad = b"x" * (MAX_BODY_BYTES - 1) + b"\xff"
    for _ in range(20):
        with pytest.raises(KebuiAdmissionError, match="invalid_content") as caught:
            h.prepare(2, bad)
        assert_safe(caught.value)
        assert caught.value.args == ("invalid_content",)
        assert synthetic_pool_usage().validation_workspace_bytes == 0

    async def run() -> None:
        record = await h.submit()
        assert record.receipt_ref is not None
        h.gate.acknowledge_terminal(
            h.item,
            record.record_revision,
            SyntheticTerminalReceipt("completed", record.receipt_ref),
        )

    asyncio.run(run())
    import hashlib

    snapshot = (h.journal._directory / "admission.json").read_bytes()
    assert h.body not in snapshot
    assert hashlib.sha256(h.body).hexdigest().encode() not in snapshot


def test_new_issuer_even_same_ref_and_bytes_rejects_before_accept(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def run() -> None:
        original = await h.submit()
        h.issuer.close()
        new = SyntheticContentIssuer(deadline_ns=20000, clock=h.clock)
        try:
            gate = KebuiTestAdmissionOwner(h.journal, h.owner, new, h.dispatch, enabled=True)
            monkeypatch.setattr(
                secrets,
                "token_hex",
                lambda length: h.item.content_admission_ref[-32:],
            )
            handle = new.prepare(h.item.request_id, h.item.scope, h.body)
            assert handle.request == h.item and handle is not h.handle
            calls = 0

            def no_accept(*args: object) -> None:
                nonlocal calls
                calls += 1
                raise AssertionError("accept must not be invoked")

            monkeypatch.setattr(h.journal, "accept", no_accept)
            with pytest.raises(KebuiAdmissionError, match="content_unavailable"):
                await gate.submit(handle.request, handle)
            assert calls == 0
            assert gate.read(h.item) == original
            assert h.dispatch.consumer.calls == 1
        finally:
            new.close()

    asyncio.run(run())


def test_handle_seal_rejects_constructor_and_owner_copy_before_accept(h: Harness) -> None:
    with pytest.raises(KebuiAdmissionError, match="content_unavailable"):
        SyntheticContentHandle(h.item, object())
    duplicate = copy.copy(h.gate)

    async def run() -> None:
        with pytest.raises(KebuiAdmissionError, match="content_unavailable"):
            await duplicate.submit(h.item, h.handle)
        assert h.journal.read(h.item) is None
        assert h.dispatch.consumer.calls == 0

    asyncio.run(run())
