"""Isolated synthetic bytes/metadata composition, with real failure windows."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from agentbox_core.kebui_observation import ConversationScope, parse_scope
from agentbox_runtime.kebui_admission import (
    SYNTHETIC_ADAPTER_PROFILE,
    AdmissionPhase,
    AdmissionRecord,
    AdmissionRequest,
    KebuiAdmissionError,
    KebuiTestAdmissionOwner,
    SyntheticOwnerContext,
    SyntheticTerminalReceipt,
)
from agentbox_runtime.kebui_admission_journal import KebuiAdmissionJournal
from agentbox_runtime.kebui_content_admission import (
    SyntheticBodyConsumer,
    SyntheticContentHandle,
    SyntheticContentIssuer,
    synthetic_pool_usage,
)


def request(number: int = 1) -> AdmissionRequest:
    scope = json.loads(
        (Path(__file__).parents[1] / "fixtures/kebui_observation/v1.json").read_text()
    )["base"]["scope"]
    return AdmissionRequest(
        f"kreq_{number:032x}", parse_scope(scope), SYNTHETIC_ADAPTER_PROFILE, f"ksyn_{number:032x}"
    )


class Clock:
    now: object = 1

    def __call__(self) -> int:
        if isinstance(self.now, Exception):
            raise self.now
        return cast(int, self.now)


class FakeOwner:
    def __init__(self, item: AdmissionRequest) -> None:
        self.scope = item.scope
        self.execution_id = "kexe_" + "1" * 32
        self.current = True
        self.tui = False
        self.lock = threading.RLock()
        self.fail: str | None = None

    @contextmanager
    def guard(self, scope: object) -> Iterator[SyntheticOwnerContext]:
        with self.lock:
            if self.fail == "entry":
                raise RuntimeError("private-port-canary")
            if not self.current or self.tui or scope != self.scope:
                raise KebuiAdmissionError("owner_unavailable")
            yield SyntheticOwnerContext(self.scope, self.execution_id)
            if self.fail == "exit":
                raise RuntimeError("private-port-canary")


class FakeDispatch:
    def __init__(self) -> None:
        self.calls = 0  # Readiness arrivals, not effects.
        self.consumer = SyntheticBodyConsumer()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()
        self.fail = False

    async def dispatch(
        self, item: AdmissionRequest, execution_id: str, handle: SyntheticContentHandle
    ) -> None:
        assert item is handle.request
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        if self.fail:
            raise RuntimeError("body-canary-not-for-error")


class Harness:
    def __init__(self, directory: Path) -> None:
        self.clock = Clock()
        self.owner = FakeOwner(request())
        self.journal = KebuiAdmissionJournal.initialize_for_test(
            directory, expected_uid=os.getuid(), expected_gid=os.getgid()
        )
        self.issuer = SyntheticContentIssuer(deadline_ns=10000, clock=self.clock)
        self.dispatch = FakeDispatch()
        self.gate = KebuiTestAdmissionOwner(
            self.journal, self.owner, self.issuer, self.dispatch, enabled=True
        )
        self.body = b"synthetic immutable UTF-8\r\n"
        self.handle = self.issuer.prepare(request().request_id, self.owner.scope, self.body)
        self.item = self.handle.request

    async def submit(self) -> AdmissionRecord:
        return await self.gate.submit(self.item, self.handle)

    def prepare(self, number: int, body: bytes = b"next") -> SyntheticContentHandle:
        return self.issuer.prepare(request(number).request_id, self.owner.scope, body)

    def record(self) -> AdmissionRecord:
        record = self.journal.read(self.item)
        assert record is not None
        return record

    def close(self) -> None:
        self.issuer.close()
        self.journal.close()


@pytest.fixture
def h(tmp_path: Path) -> Iterator[Harness]:
    harness = Harness(tmp_path)
    try:
        yield harness
    finally:
        harness.close()
        usage = synthetic_pool_usage()
        assert usage.entries == usage.retained_bytes == usage.worker_slots == 0
        assert usage.staging_bytes == usage.validation_workspace_bytes == 0


def assert_safe(error: BaseException) -> None:
    assert error.__cause__ is None
    assert error.__context__ is None
    rendered = "".join(traceback.format_exception(error))
    assert "private-port-canary" not in rendered
    assert "body-canary-not-for-error" not in rendered


def test_disabled_default_does_not_accept(h: Harness) -> None:
    async def run() -> None:
        reader = KebuiTestAdmissionOwner(h.journal, h.owner, None, h.dispatch)
        with pytest.raises(KebuiAdmissionError, match="disabled"):
            await reader.submit(h.item, h.handle)
        assert h.journal.read(h.item) is None
        assert h.dispatch.consumer.calls == 0

    asyncio.run(run())


def test_exact_duplicate_consumes_original_once_and_terminal_is_separate(h: Harness) -> None:
    async def run() -> None:
        first = await h.submit()
        assert first.phase is AdmissionPhase.ACKNOWLEDGED
        assert h.dispatch.consumer.last_body_identity == id(h.body)
        assert h.dispatch.consumer.byte_count == len(h.body)
        assert h.issuer.prepare(h.item.request_id, h.item.scope, h.body) is h.handle
        assert await h.submit() == first
        assert h.dispatch.consumer.calls == 1
        second = h.prepare(2)
        with pytest.raises(KebuiAdmissionError, match="busy"):
            await h.gate.submit(second.request, second)
        assert synthetic_pool_usage().entries == 1
        assert first.receipt_ref is not None
        terminal = h.gate.acknowledge_terminal(
            h.item, first.record_revision, SyntheticTerminalReceipt("completed", first.receipt_ref)
        )
        assert terminal.phase is AdmissionPhase.TERMINAL
        assert await h.submit() == terminal

    asyncio.run(run())


def test_waiter_cancellation_keeps_owned_body_and_worker(h: Harness) -> None:
    async def run() -> None:
        h.dispatch.release.clear()
        task = asyncio.create_task(h.submit())
        await h.dispatch.entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert h.record().phase is AdmissionPhase.DISPATCH_FENCED
        assert synthetic_pool_usage().worker_slots == 1
        assert synthetic_pool_usage().retained_bytes == len(h.body)
        assert h.dispatch.consumer.calls == 0
        h.dispatch.release.set()
        await h.gate.wait_for_idle()
        assert h.record().phase is AdmissionPhase.ACKNOWLEDGED
        assert h.dispatch.consumer.calls == 1

    asyncio.run(run())


def test_rejected_queued_worker_never_consumes(h: Harness) -> None:
    async def run() -> None:
        task = asyncio.create_task(h.submit())
        await asyncio.sleep(0)
        accepted = h.record()
        assert accepted.phase is AdmissionPhase.ACCEPTED
        rejected = h.gate.reject_before_dispatch(h.item, accepted.record_revision)
        assert await task == rejected
        assert h.dispatch.consumer.calls == 0
        assert h.gate.read(h.item) == rejected

    asyncio.run(run())


def test_dispatch_failure_unknown_retains_execution_but_releases_body(h: Harness) -> None:
    async def run() -> None:
        h.dispatch.fail = True
        result = await h.submit()
        assert result.phase is AdmissionPhase.UNKNOWN
        assert h.gate.read(h.item) == result
        assert synthetic_pool_usage().entries == 0
        assert h.dispatch.consumer.calls == 0
        with pytest.raises(KebuiAdmissionError, match="content_unavailable"):
            await h.submit()
        with pytest.raises(KebuiAdmissionError, match="busy"):
            h.journal.accept(request(2), h.owner.execution_id)

    asyncio.run(run())


@pytest.mark.parametrize("field", tuple(request().scope.__dataclass_fields__))
def test_sixteen_scope_changes_after_acceptance_block_effect(h: Harness, field: str) -> None:
    async def run() -> None:
        task = asyncio.create_task(h.submit())
        await asyncio.sleep(0)
        h.owner.scope = replace(h.owner.scope, **{field: cast(Any, "changed-context")})
        assert (await task).phase is AdmissionPhase.UNKNOWN
        assert h.dispatch.consumer.calls == 0

    asyncio.run(run())


@pytest.mark.parametrize("reason", ["tui", "owner", "execution", "source", "expiry"])
def test_last_await_rechecks_every_authority(h: Harness, reason: str) -> None:
    async def run() -> None:
        h.dispatch.release.clear()
        task = asyncio.create_task(h.submit())
        await h.dispatch.entered.wait()
        if reason == "tui":
            h.owner.tui = True
        elif reason == "owner":
            h.owner.current = False
        elif reason == "execution":
            h.owner.execution_id = "kexe_" + "2" * 32
        elif reason == "source":
            h.issuer.close()
            assert synthetic_pool_usage().retained_bytes == len(h.body)
        else:
            h.clock.now = 10000
        h.dispatch.release.set()
        assert (await task).phase is AdmissionPhase.UNKNOWN
        assert h.dispatch.consumer.calls == 0
        assert synthetic_pool_usage().entries == 0

    asyncio.run(run())


def test_metadata_read_terminal_and_rejection_survive_source_loss(h: Harness) -> None:
    async def run() -> None:
        first = await h.submit()
        h.issuer.close()
        h.clock.now = RuntimeError("body-canary-not-for-error")
        assert h.gate.read(h.item) == first
        assert first.receipt_ref is not None
        terminal = h.gate.acknowledge_terminal(
            h.item, first.record_revision, SyntheticTerminalReceipt("completed", first.receipt_ref)
        )
        assert terminal.phase is AdmissionPhase.TERMINAL
        next_item = request(2)
        accepted, _ = h.journal.accept(next_item, h.owner.execution_id)
        rejected = h.gate.reject_before_dispatch(next_item, accepted.record_revision)
        assert rejected.phase is AdmissionPhase.REJECTED_BEFORE_DISPATCH

    asyncio.run(run())


def test_concurrent_duplicate_uses_one_witness_and_worker(h: Harness) -> None:
    async def run() -> None:
        results = await asyncio.gather(*(h.submit() for _ in range(30)))
        assert h.dispatch.consumer.calls == 1
        assert {row.phase for row in results} <= {
            AdmissionPhase.ACCEPTED,
            AdmissionPhase.DISPATCH_FENCED,
            AdmissionPhase.ACKNOWLEDGED,
        }
        assert synthetic_pool_usage().entries == 1

    asyncio.run(run())


def test_terminal_during_readiness_prevents_late_effect(h: Harness) -> None:
    async def run() -> None:
        h.dispatch.release.clear()
        task = asyncio.create_task(h.submit())
        await h.dispatch.entered.wait()
        fenced = h.record()
        terminal = h.gate.acknowledge_terminal(
            h.item,
            fenced.record_revision,
            SyntheticTerminalReceipt("completed", "krcp_" + "2" * 32),
        )
        h.dispatch.release.set()
        assert await task == terminal
        assert h.dispatch.consumer.calls == 0
        assert h.gate.read(h.item) == terminal

    asyncio.run(run())


@pytest.mark.parametrize(
    "field", ["request_id", "content_admission_ref", "adapter_profile", "operation"]
)
@pytest.mark.parametrize(
    "value",
    [None, True, 1, "", "é" * 4096, "body-canary"],
    ids=["none", "bool", "int", "empty", "utf8", "canary"],
)
def test_closed_metadata_rejects_noncanonical_fields(field: str, value: object) -> None:
    with pytest.raises(KebuiAdmissionError, match="invalid_metadata") as caught:
        replace(request(), **{field: cast(Any, value)})
    assert_safe(caught.value)


@pytest.mark.parametrize("method", ["submit", "read", "reject", "terminal"])
@pytest.mark.parametrize("position", ["entry", "exit"])
def test_guard_errors_have_no_body_exception_chain(h: Harness, method: str, position: str) -> None:
    async def run() -> None:
        h.owner.fail = position
        if method == "submit" and position == "exit":
            assert (await h.submit()).phase is AdmissionPhase.UNKNOWN
        else:
            with pytest.raises(KebuiAdmissionError, match="owner_unavailable") as caught:
                if method == "submit":
                    await h.submit()
                elif method == "read":
                    h.gate.read(h.item)
                elif method == "reject":
                    h.gate.reject_before_dispatch(h.item, "1")
                else:
                    h.gate.acknowledge_terminal(
                        h.item, "1", SyntheticTerminalReceipt("completed", "krcp_" + "1" * 32)
                    )
            assert_safe(caught.value)
        assert h.dispatch.consumer.calls == 0

    asyncio.run(run())


@pytest.mark.parametrize("method", ["submit", "read", "reject", "terminal"])
def test_request_type_checked_before_scope_access(h: Harness, method: str) -> None:
    async def run() -> None:
        invalid = cast(AdmissionRequest, None)
        with pytest.raises(KebuiAdmissionError, match="invalid_metadata") as caught:
            if method == "submit":
                await h.gate.submit(invalid, h.handle)
            elif method == "read":
                h.gate.read(invalid)
            elif method == "reject":
                h.gate.reject_before_dispatch(invalid, "1")
            else:
                h.gate.acknowledge_terminal(
                    invalid, "1", SyntheticTerminalReceipt("completed", "krcp_" + "1" * 32)
                )
        assert_safe(caught.value)

    asyncio.run(run())


@pytest.mark.parametrize("window", ["witness", "create", "retain", "callback"])
@pytest.mark.parametrize("eager", [False, True])
def test_post_acceptance_failures_never_arm_effect(
    h: Harness, monkeypatch: pytest.MonkeyPatch, window: str, eager: bool
) -> None:
    async def run() -> None:
        loop = asyncio.get_running_loop()
        if eager:
            factory = getattr(asyncio, "eager_task_factory", None)
            if factory is None:
                pytest.skip("eager task factories require Python 3.12+")
            loop.set_task_factory(factory)

        def fail(*args: object, **kwargs: object) -> None:
            raise RuntimeError("body-canary-not-for-error")

        target, name = {
            "witness": (h.issuer, "_accept_witness"),
            "create": (asyncio, "create_task"),
            "retain": (h.gate, "_retain_worker"),
            "callback": (h.gate, "_register_worker"),
        }[window]
        with monkeypatch.context() as patch:
            patch.setattr(target, name, fail)
            result = await h.submit()
        loop.set_task_factory(None)
        assert result.phase is AdmissionPhase.UNKNOWN
        assert h.dispatch.consumer.calls == h.dispatch.calls == 0
        assert synthetic_pool_usage().worker_slots == 0
        assert synthetic_pool_usage().entries == 0
        assert not h.gate._workers

    asyncio.run(run())


@pytest.mark.parametrize("window", ["before", "after_commit", "live_add"])
def test_accept_failure_cannot_mint_witness(
    h: Harness, monkeypatch: pytest.MonkeyPatch, window: str
) -> None:
    async def run() -> None:
        original = h.journal.accept
        if window == "live_add":

            class BrokenSet(set[str]):
                def add(self, item: str) -> None:
                    raise RuntimeError("body-canary-not-for-error")

            monkeypatch.setattr(h.journal, "_live", BrokenSet())
        else:

            def fail(item: AdmissionRequest, execution: str) -> tuple[AdmissionRecord, bool]:
                if window == "after_commit":
                    original(item, execution)
                raise RuntimeError("body-canary-not-for-error")

            monkeypatch.setattr(h.journal, "accept", fail)
        with pytest.raises(KebuiAdmissionError, match="store_unavailable") as caught:
            await h.submit()
        assert_safe(caught.value)
        assert h.dispatch.consumer.calls == 0
        assert synthetic_pool_usage().entries == 0
        if window != "before":
            assert h.record().phase is AdmissionPhase.ACCEPTED
            assert h.gate.read(h.item) is not None

    asyncio.run(run())


def test_secondary_journal_error_cannot_inherit_dispatch_body(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def run() -> None:
        h.dispatch.release.clear()
        h.dispatch.fail = True
        task = asyncio.create_task(h.submit())
        await h.dispatch.entered.wait()

        def fail(item: AdmissionRequest) -> None:
            raise RuntimeError("private-port-canary")

        monkeypatch.setattr(h.journal, "read", fail)
        h.dispatch.release.set()
        with pytest.raises(KebuiAdmissionError, match="store_unavailable") as caught:
            await task
        assert_safe(caught.value)
        assert h.dispatch.consumer.calls == 0

    asyncio.run(run())


def test_fresh_journal_and_second_owner_rejected_before_accept(
    h: Harness, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    second_dir = tmp_path / "second"
    second_dir.mkdir(mode=0o700)
    second = KebuiAdmissionJournal.initialize_for_test(
        second_dir, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    try:
        with pytest.raises(KebuiAdmissionError, match="content_unavailable"):
            KebuiTestAdmissionOwner(second, h.owner, h.issuer, h.dispatch, enabled=True)
        assert second.read(h.item) is None
        reader = KebuiTestAdmissionOwner(second, h.owner, None, h.dispatch, enabled=True)

        async def run() -> None:
            with pytest.raises(KebuiAdmissionError, match="content_unavailable"):
                await reader.submit(h.item, h.handle)

        asyncio.run(run())
        assert second.read(h.item) is None
    finally:
        second.close()


def test_final_guard_exit_failure_after_effect_is_unknown_without_replay(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = SyntheticBodyConsumer._consume

    def effect(self: SyntheticBodyConsumer, body: bytes) -> Any:
        receipt = original(self, body)
        h.owner.fail = "exit"
        return receipt

    monkeypatch.setattr(SyntheticBodyConsumer, "_consume", effect)

    async def run() -> None:
        result = await h.submit()
        assert result.phase is AdmissionPhase.UNKNOWN
        assert h.dispatch.consumer.calls == 1
        assert synthetic_pool_usage().entries == 0
        h.owner.fail = None
        assert h.gate.read(h.item) == result
        with pytest.raises(KebuiAdmissionError, match="content_unavailable"):
            await h.submit()
        renewed = h.issuer.prepare(h.item.request_id, h.item.scope, h.body)
        with pytest.raises(KebuiAdmissionError, match="conflict"):
            await h.gate.submit(renewed.request, renewed)
        with pytest.raises(KebuiAdmissionError, match="busy"):
            h.journal.accept(request(2), h.owner.execution_id)
        assert h.dispatch.consumer.calls == 1

    asyncio.run(run())


def test_current_guard_cannot_suppress_journal_cas_failure(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    @contextmanager
    def suppressing(scope: ConversationScope) -> Iterator[SyntheticOwnerContext]:
        try:
            yield SyntheticOwnerContext(scope, h.owner.execution_id)
        except Exception:
            return

    monkeypatch.setattr(h.owner, "guard", suppressing)
    accepted, _ = h.journal.accept(h.item, h.owner.execution_id)
    with pytest.raises(KebuiAdmissionError, match="cas_conflict") as caught:
        h.gate.reject_before_dispatch(h.item, "999")
    assert_safe(caught.value)
    assert h.gate.read(h.item) == accepted
    assert h.dispatch.consumer.calls == 0


def test_original_byte_proof_does_not_mint_witness_for_external_duplicate(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    accepted, _ = h.journal.accept(h.item, h.owner.execution_id)
    calls = 0
    original = h.journal.accept

    def observe(item: AdmissionRequest, execution: str) -> tuple[AdmissionRecord, bool]:
        nonlocal calls
        calls += 1
        return original(item, execution)

    monkeypatch.setattr(h.journal, "accept", observe)

    async def run() -> None:
        with pytest.raises(KebuiAdmissionError, match="content_unavailable"):
            await h.submit()

    asyncio.run(run())
    assert calls == 0
    assert h.gate.read(h.item) == accepted
    assert h.dispatch.consumer.calls == 0


def test_metadata_reads_still_require_exact_current_execution(h: Harness) -> None:
    async def run() -> None:
        await h.submit()
        h.issuer.close()
        h.owner.execution_id = "kexe_" + "2" * 32
        with pytest.raises(KebuiAdmissionError, match="owner_unavailable"):
            h.gate.read(h.item)

    asyncio.run(run())


def test_all_255_worker_slots_reserved_and_retired_with_their_bodies(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    @contextmanager
    def guard(scope: ConversationScope) -> Iterator[SyntheticOwnerContext]:
        with h.owner.lock:
            yield SyntheticOwnerContext(scope, h.owner.execution_id)

    monkeypatch.setattr(h.owner, "guard", guard)
    h.issuer._discard_prepared(h.handle)
    handles = [
        h.issuer.prepare(
            request(number).request_id,
            replace(h.item.scope, project_id=f"prj_{number:032x}"),
            b"x",
        )
        for number in range(1, 256)
    ]

    async def run() -> None:
        h.dispatch.release.clear()
        tasks = [asyncio.create_task(h.gate.submit(handle.request, handle)) for handle in handles]
        while h.dispatch.calls < 255:
            await asyncio.sleep(0)
        usage = synthetic_pool_usage()
        assert usage.worker_slots == usage.entries == usage.retained_bytes == 255
        assert sum(claim is not None for claim in h.gate._claims) == 255
        h.issuer.close()
        assert synthetic_pool_usage() == usage
        h.dispatch.release.set()
        results = await asyncio.gather(*tasks)
        assert all(record.phase is AdmissionPhase.UNKNOWN for record in results)
        assert h.dispatch.consumer.calls == 0
        assert synthetic_pool_usage().worker_slots == synthetic_pool_usage().entries == 0

    asyncio.run(run())


def test_created_false_never_mints_witness_even_after_an_unseen_accept(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = h.journal.accept

    def unseen_accept(item: AdmissionRequest, execution: str) -> tuple[AdmissionRecord, bool]:
        record, _ = original(item, execution)
        return record, False

    monkeypatch.setattr(h.journal, "accept", unseen_accept)

    async def run() -> None:
        with pytest.raises(KebuiAdmissionError, match="content_unavailable"):
            await h.submit()
        assert h.record().phase is AdmissionPhase.ACCEPTED
        assert h.dispatch.calls == h.dispatch.consumer.calls == 0
        assert synthetic_pool_usage().entries == synthetic_pool_usage().worker_slots == 0

    asyncio.run(run())


def test_deadline_expiring_during_commit_never_binds_live_witness(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = h.journal.accept

    def expire(item: AdmissionRequest, execution: str) -> tuple[AdmissionRecord, bool]:
        result = original(item, execution)
        h.clock.now = 10000
        return result

    monkeypatch.setattr(h.journal, "accept", expire)

    async def run() -> None:
        assert (await h.submit()).phase is AdmissionPhase.UNKNOWN
        assert h.dispatch.calls == h.dispatch.consumer.calls == 0
        assert synthetic_pool_usage().entries == synthetic_pool_usage().worker_slots == 0

    asyncio.run(run())


@pytest.mark.parametrize("reason", ["tui", "owner", "content"])
def test_unavailable_prerequisites_prevent_acceptance(h: Harness, reason: str) -> None:
    async def run() -> None:
        if reason == "tui":
            h.owner.tui = True
        elif reason == "owner":
            h.owner.current = False
        else:
            h.issuer.close()
        with pytest.raises(KebuiAdmissionError):
            await h.submit()
        assert h.journal.read(h.item) is None
        assert h.dispatch.calls == h.dispatch.consumer.calls == 0

    asyncio.run(run())


def test_changed_request_binding_conflicts_without_replacing_witness(h: Harness) -> None:
    async def run() -> None:
        result = await h.submit()
        altered = replace(h.item, content_admission_ref="ksyn_" + "2" * 32)
        with pytest.raises(KebuiAdmissionError, match="conflict"):
            await h.gate.submit(altered, h.handle)
        assert await h.submit() == result
        assert h.dispatch.consumer.calls == 1

    asyncio.run(run())


def test_queued_execution_replacement_never_enters_readiness(h: Harness) -> None:
    async def run() -> None:
        task = asyncio.create_task(h.submit())
        await asyncio.sleep(0)
        h.owner.execution_id = "kexe_" + "2" * 32
        assert (await task).phase is AdmissionPhase.UNKNOWN
        assert h.dispatch.calls == h.dispatch.consumer.calls == 0

    asyncio.run(run())
