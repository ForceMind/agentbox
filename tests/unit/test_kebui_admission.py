"""Only synthetic current-owner/content/dispatch ports, never production wiring."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from agentbox_core.kebui_observation import parse_scope
from agentbox_runtime.kebui_admission import (
    SYNTHETIC_ADAPTER_PROFILE,
    AdmissionPhase,
    AdmissionRecord,
    AdmissionRequest,
    KebuiAdmissionError,
    KebuiTestAdmissionOwner,
    SyntheticDispatchReceipt,
    SyntheticOwnerContext,
    SyntheticTerminalReceipt,
)
from agentbox_runtime.kebui_admission_journal import KebuiAdmissionJournal


def request(number: int = 1) -> AdmissionRequest:
    scope = json.loads(
        (Path(__file__).parents[1] / "fixtures/kebui_observation/v1.json").read_text()
    )["base"]["scope"]
    return AdmissionRequest(
        request_id=f"kreq_{number:032x}",
        scope=parse_scope(scope),
        adapter_profile=SYNTHETIC_ADAPTER_PROFILE,
        content_admission_ref=f"ksyn_{number:032x}",
    )


class FakeOwner:
    def __init__(self, item: AdmissionRequest) -> None:
        self.scope = item.scope
        self.execution_id = "kexe_" + "1" * 32
        self.current = True
        self.tui = False

    @contextmanager
    def guard(self, scope: object) -> Iterator[SyntheticOwnerContext]:
        if not self.current or self.tui or scope != self.scope:
            raise KebuiAdmissionError("owner_unavailable")
        yield SyntheticOwnerContext(self.scope, self.execution_id)


class FakeContent:
    valid = True

    def validate(self, item: AdmissionRequest) -> bool:
        return self.valid


class FakeDispatch:
    def __init__(self) -> None:
        self.calls = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()
        self.fail = False

    async def dispatch(self, item: AdmissionRequest, execution_id: str) -> SyntheticDispatchReceipt:
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        if self.fail:
            raise RuntimeError("body-canary-not-for-error")
        return SyntheticDispatchReceipt("krcp_" + "1" * 32)


def composition(tmp_path: Path, *, enabled: bool = True) -> tuple[
    AdmissionRequest,
    KebuiAdmissionJournal,
    FakeOwner,
    FakeContent,
    FakeDispatch,
    KebuiTestAdmissionOwner,
]:
    item = request()
    journal = KebuiAdmissionJournal.initialize_for_test(
        tmp_path, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    owner, content, dispatch = FakeOwner(item), FakeContent(), FakeDispatch()
    gate = KebuiTestAdmissionOwner(journal, owner, content, dispatch, enabled=enabled)
    return item, journal, owner, content, dispatch, gate


def observed(journal: KebuiAdmissionJournal, item: AdmissionRequest) -> AdmissionRecord:
    record = journal.read(item)
    assert record is not None
    return record


def test_disabled_default_does_not_accept(tmp_path: Path) -> None:
    async def run() -> None:
        item, journal, owner, content, dispatch, _ = composition(tmp_path)
        gate = KebuiTestAdmissionOwner(journal, owner, content, dispatch)
        with pytest.raises(KebuiAdmissionError, match="disabled"):
            await gate.submit(item)
        assert journal.read(item) is None
        assert dispatch.calls == 0

    asyncio.run(run())


def test_exact_duplicate_dispatches_once_ack_is_not_terminal(tmp_path: Path) -> None:
    async def run() -> None:
        item, journal, _, _, dispatch, gate = composition(tmp_path)
        first = await gate.submit(item)
        assert first.phase is AdmissionPhase.ACKNOWLEDGED
        assert first.receipt_ref is not None
        assert await gate.submit(item) == first
        assert dispatch.calls == 1
        with pytest.raises(KebuiAdmissionError, match="busy"):
            await gate.submit(replace(item, request_id="kreq_" + "2" * 32))
        terminal = gate.acknowledge_terminal(
            item, first.record_revision, SyntheticTerminalReceipt("completed", first.receipt_ref)
        )
        assert terminal.phase is AdmissionPhase.TERMINAL
        assert journal.read(item) == terminal

    asyncio.run(run())


def test_cancel_waiter_does_not_release_or_cancel_worker(tmp_path: Path) -> None:
    async def run() -> None:
        item, journal, _, _, dispatch, gate = composition(tmp_path)
        dispatch.release.clear()
        task = asyncio.create_task(gate.submit(item))
        await dispatch.entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert observed(journal, item).phase is AdmissionPhase.DISPATCH_FENCED
        with pytest.raises(KebuiAdmissionError, match="busy"):
            await gate.submit(replace(item, request_id="kreq_" + "2" * 32))
        dispatch.release.set()
        await gate.wait_for_idle()
        assert observed(journal, item).phase is AdmissionPhase.ACKNOWLEDGED
        assert dispatch.calls == 1

    asyncio.run(run())


def test_rejected_queued_worker_cannot_enter_effect(tmp_path: Path) -> None:
    async def run() -> None:
        item, journal, _, _, dispatch, gate = composition(tmp_path)
        task = asyncio.create_task(gate.submit(item))
        await asyncio.sleep(0)  # submit accepted, its child has not run yet
        accepted = observed(journal, item)
        assert accepted.phase is AdmissionPhase.ACCEPTED
        rejected = gate.reject_before_dispatch(item, accepted.record_revision)
        assert rejected.phase is AdmissionPhase.REJECTED_BEFORE_DISPATCH
        result = await task
        assert result == rejected
        assert dispatch.calls == 0

    asyncio.run(run())


def test_dispatch_exception_becomes_unknown_without_error_text(tmp_path: Path) -> None:
    async def run() -> None:
        item, journal, _, _, dispatch, gate = composition(tmp_path)
        dispatch.fail = True
        result = await gate.submit(item)
        assert result.phase is AdmissionPhase.UNKNOWN
        assert await gate.submit(item) == result
        assert dispatch.calls == 1
        assert "body-canary" not in (tmp_path / "admission.json").read_text()
        assert journal.read(item) == result

    asyncio.run(run())


def test_lost_owner_after_await_fences_unknown(tmp_path: Path) -> None:
    async def run() -> None:
        item, journal, owner, _, dispatch, gate = composition(tmp_path)
        dispatch.release.clear()
        task = asyncio.create_task(gate.submit(item))
        await dispatch.entered.wait()
        owner.current = False
        dispatch.release.set()
        assert (await task).phase is AdmissionPhase.UNKNOWN
        assert observed(journal, item).phase is AdmissionPhase.UNKNOWN

    asyncio.run(run())


@pytest.mark.parametrize("field", tuple(request().scope.__dataclass_fields__))
def test_all_sixteen_owner_scope_changes_block_before_effect(tmp_path: Path, field: str) -> None:
    async def run() -> None:
        item, journal, owner, _, dispatch, gate = composition(tmp_path)
        task = asyncio.create_task(gate.submit(item))
        await asyncio.sleep(0)
        assert observed(journal, item).phase is AdmissionPhase.ACCEPTED
        owner.scope = replace(owner.scope, **{field: cast(Any, "changed-synthetic-context")})
        assert (await task).phase is AdmissionPhase.UNKNOWN
        assert dispatch.calls == 0

    asyncio.run(run())


@pytest.mark.parametrize("reason", ["tui", "owner", "content"])
def test_unavailable_prerequisites_prevent_acceptance(tmp_path: Path, reason: str) -> None:
    async def run() -> None:
        item, journal, owner, content, dispatch, gate = composition(tmp_path)
        if reason == "tui":
            owner.tui = True
        elif reason == "owner":
            owner.current = False
        else:
            content.valid = False
        with pytest.raises(KebuiAdmissionError):
            await gate.submit(item)
        assert journal.read(item) is None
        assert dispatch.calls == 0

    asyncio.run(run())


def test_duplicate_changed_binding_is_conflict_and_missing_equality_unavailable(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        item, _, _, content, dispatch, gate = composition(tmp_path)
        await gate.submit(item)
        with pytest.raises(KebuiAdmissionError, match="conflict"):
            await gate.submit(replace(item, content_admission_ref="ksyn_" + "2" * 32))
        content.valid = False
        with pytest.raises(KebuiAdmissionError, match="content_unavailable"):
            await gate.submit(item)
        assert dispatch.calls == 1

    asyncio.run(run())


def test_concurrent_duplicate_has_one_fake_dispatch(tmp_path: Path) -> None:
    async def run() -> None:
        item, _, _, _, dispatch, gate = composition(tmp_path)
        results = await asyncio.gather(*(gate.submit(item) for _ in range(20)))
        assert dispatch.calls == 1
        assert {result.phase for result in results} <= {
            AdmissionPhase.ACCEPTED,
            AdmissionPhase.DISPATCH_FENCED,
            AdmissionPhase.ACKNOWLEDGED,
        }
        assert (await gate.submit(item)).phase is AdmissionPhase.ACKNOWLEDGED

    asyncio.run(run())


def test_effect_observes_durable_dispatch_fence_and_terminal_wins_late_ack(tmp_path: Path) -> None:
    async def run() -> None:
        item, journal, _, _, dispatch, gate = composition(tmp_path)
        dispatch.release.clear()
        task = asyncio.create_task(gate.submit(item))
        await dispatch.entered.wait()
        fenced = observed(journal, item)
        assert fenced.phase is AdmissionPhase.DISPATCH_FENCED
        observer = KebuiAdmissionJournal.open_existing(
            tmp_path, expected_uid=os.getuid(), expected_gid=os.getgid(), recover=False
        )
        assert observer.read(item) == fenced
        terminal = gate.acknowledge_terminal(
            item, fenced.record_revision, SyntheticTerminalReceipt("completed", "krcp_" + "2" * 32)
        )
        dispatch.release.set()
        assert await task == terminal
        assert await gate.submit(item) == terminal
        with pytest.raises(KebuiAdmissionError):
            gate.acknowledge_terminal(
                item,
                terminal.record_revision,
                SyntheticTerminalReceipt("canceled", "krcp_" + "3" * 32),
            )
        assert journal.read(item) == terminal
        assert dispatch.calls == 1
        observer.close()

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
    with pytest.raises(KebuiAdmissionError, match="invalid_metadata") as error:
        replace(request(), **{field: cast(Any, value)})
    assert "body-canary" not in str(error.value)


def test_execution_identity_change_after_acceptance_never_dispatches(tmp_path: Path) -> None:
    async def run() -> None:
        item, _, owner, _, dispatch, gate = composition(tmp_path)
        task = asyncio.create_task(gate.submit(item))
        await asyncio.sleep(0)
        owner.execution_id = "kexe_" + "2" * 32
        assert (await task).phase is AdmissionPhase.UNKNOWN
        assert dispatch.calls == 0

    asyncio.run(run())


@pytest.mark.parametrize("method", ["submit", "read", "reject", "terminal"])
def test_owner_port_errors_are_fixed_safe_codes(tmp_path: Path, method: str) -> None:
    async def run() -> None:
        item, journal, _, content, dispatch, _ = composition(tmp_path)

        class BrokenOwner:
            def guard(self, scope: object) -> AbstractContextManager[SyntheticOwnerContext]:
                raise RuntimeError("private-body-canary")

        gate = KebuiTestAdmissionOwner(journal, BrokenOwner(), content, dispatch, enabled=True)
        with pytest.raises(KebuiAdmissionError, match="^owner_unavailable$"):
            if method == "submit":
                await gate.submit(item)
            elif method == "read":
                gate.read(item)
            elif method == "reject":
                gate.reject_before_dispatch(item, "1")
            else:
                gate.acknowledge_terminal(
                    item, "1", SyntheticTerminalReceipt("completed", "krcp_" + "1" * 32)
                )
        assert journal.read(item) is None
        assert dispatch.calls == 0

    asyncio.run(run())


@pytest.mark.parametrize("position", ["entry", "exit"])
@pytest.mark.parametrize("error_type", [RuntimeError, KebuiAdmissionError])
def test_guard_failure_never_leaks_or_starts_effect(
    tmp_path: Path, position: str, error_type: type[Exception]
) -> None:
    async def run() -> None:
        item, journal, owner, content, dispatch, _ = composition(tmp_path)

        class BrokenOwner:
            @contextmanager
            def guard(self, scope: object) -> Iterator[SyntheticOwnerContext]:
                if position == "entry":
                    raise error_type("private-port-canary")
                yield SyntheticOwnerContext(owner.scope, owner.execution_id)
                raise error_type("private-port-canary")

        gate = KebuiTestAdmissionOwner(journal, BrokenOwner(), content, dispatch, enabled=True)
        with pytest.raises(KebuiAdmissionError, match="^owner_unavailable$"):
            await gate.submit(item)
        await asyncio.sleep(0)
        assert dispatch.calls == 0
        record = journal.read(item)
        if position == "exit":
            assert record is not None
            assert record.phase is AdmissionPhase.ACCEPTED
            with pytest.raises(KebuiAdmissionError, match="busy"):
                journal.accept(request(2), owner.execution_id)
        else:
            assert record is None

    asyncio.run(run())


@pytest.mark.parametrize("method", ["submit", "read", "reject", "terminal"])
def test_public_request_type_is_checked_before_scope_access(tmp_path: Path, method: str) -> None:
    async def run() -> None:
        _, _, _, _, dispatch, gate = composition(tmp_path)
        invalid = cast(AdmissionRequest, None)  # Deliberate runtime boundary negative.
        with pytest.raises(KebuiAdmissionError, match="^invalid_metadata$"):
            if method == "submit":
                await gate.submit(invalid)
            elif method == "read":
                gate.read(invalid)
            elif method == "reject":
                gate.reject_before_dispatch(invalid, "1")
            else:
                gate.acknowledge_terminal(
                    invalid, "1", SyntheticTerminalReceipt("completed", "krcp_" + "1" * 32)
                )
        assert dispatch.calls == 0

    asyncio.run(run())


def test_port_cannot_suppress_journal_cas_failure(tmp_path: Path) -> None:
    async def run() -> None:
        item, journal, owner, content, dispatch, _ = composition(tmp_path)

        class SuppressingOwner:
            @contextmanager
            def guard(self, scope: object) -> Iterator[SyntheticOwnerContext]:
                try:
                    yield SyntheticOwnerContext(owner.scope, owner.execution_id)
                except Exception:
                    return

        gate = KebuiTestAdmissionOwner(journal, SuppressingOwner(), content, dispatch, enabled=True)
        accepted, _ = journal.accept(item, owner.execution_id)
        with pytest.raises(KebuiAdmissionError, match="cas_conflict"):
            gate.reject_before_dispatch(item, "999")
        assert journal.read(item) == accepted
        assert dispatch.calls == 0

    asyncio.run(run())
