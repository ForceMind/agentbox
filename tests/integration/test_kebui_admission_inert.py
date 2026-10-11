"""Inert source custody -> metadata journal -> fixed synchronous fake effect.

Only synthetic UTF-8 bytes and private tmp metadata files are used. No provider,
CLI, authenticated S03 source, production owner, or power-loss qualification.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from agentbox_core.kebui_observation import ConversationScope, parse_scope
from agentbox_runtime.kebui_admission import (
    SYNTHETIC_ADAPTER_PROFILE,
    AdmissionPhase,
    AdmissionRequest,
    KebuiAdmissionError,
    KebuiTestAdmissionOwner,
    SyntheticDispatchReceipt,
    SyntheticOwnerContext,
    SyntheticTerminalReceipt,
)
from agentbox_runtime.kebui_admission_journal import KebuiAdmissionJournal
from agentbox_runtime.kebui_content_admission import (
    SyntheticBodyConsumer,
    SyntheticContentHandle,
    SyntheticContentIssuer,
)

_EXECUTION = "kexe_" + "7" * 32
_BODY = b"synthetic message for inert custody only\n"
_FIXTURE = Path(__file__).parents[1] / "fixtures/kebui_observation/v1.json"


def _template(number: int = 1, **scope_changes: str) -> AdmissionRequest:
    source = json.loads(_FIXTURE.read_text())["base"]["scope"]
    source["turn_id"] = "ktr_" + f"{number:032x}"
    source.update(scope_changes)
    # This template's ref must never become the source-issued admission ref.
    return AdmissionRequest(
        request_id="kreq_" + f"{number:032x}",
        scope=parse_scope(source),
        adapter_profile=SYNTHETIC_ADAPTER_PROFILE,
        content_admission_ref="ksyn_" + "0" * 32,
    )


class _CurrentOwner:
    """Explicit fake current-owner premise; not production authentication."""

    def __init__(self, *templates: AdmissionRequest) -> None:
        self.scopes = {item.scope for item in templates}
        self.available = True
        self.tui_writer = False
        self.execution_id = _EXECUTION
        self.lock = threading.RLock()

    @contextmanager
    def guard(self, scope: ConversationScope) -> Iterator[SyntheticOwnerContext]:
        with self.lock:
            if not self.available or self.tui_writer or scope not in self.scopes:
                raise RuntimeError("synthetic owner unavailable")
            yield SyntheticOwnerContext(scope=scope, execution_id=self.execution_id)
            if not self.available or self.tui_writer or scope not in self.scopes:
                raise RuntimeError("synthetic owner changed")


class _Clock:
    now = 1

    def __call__(self) -> int:
        return self.now


class _Dispatch:
    """Readiness only: effect is the exact fixed consumer after this await."""

    def __init__(self, *, blocked: bool = False) -> None:
        self.consumer = SyntheticBodyConsumer()
        self.arrivals: list[tuple[AdmissionRequest, str]] = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        if not blocked:
            self.release.set()

    async def dispatch(
        self, request: AdmissionRequest, execution_id: str, handle: SyntheticContentHandle
    ) -> None:
        self.arrivals.append((request, execution_id))
        self.entered.set()
        await self.release.wait()


def _journal(directory: Path) -> KebuiAdmissionJournal:
    directory.mkdir(mode=0o700)
    return KebuiAdmissionJournal.initialize_for_test(
        directory, expected_uid=os.geteuid(), expected_gid=os.getegid()
    )


@dataclass
class _Composition:
    gate: KebuiTestAdmissionOwner
    issuer: SyntheticContentIssuer
    current: _CurrentOwner
    dispatch: _Dispatch
    clock: _Clock
    journal: KebuiAdmissionJournal

    def prepare(
        self, template: AdmissionRequest, body: bytes = _BODY
    ) -> tuple[AdmissionRequest, SyntheticContentHandle]:
        handle = self.issuer.prepare(template.request_id, template.scope, body)
        assert handle.request.content_admission_ref != template.content_admission_ref
        return handle.request, handle


@asynccontextmanager
async def _composition(
    tmp_path: Path, *templates: AdmissionRequest, blocked: bool = False
) -> AsyncIterator[_Composition]:
    journal = _journal(tmp_path / "journal")
    current, clock, dispatch = _CurrentOwner(*templates), _Clock(), _Dispatch(blocked=blocked)
    issuer = SyntheticContentIssuer(deadline_ns=100, clock=clock)
    gate = KebuiTestAdmissionOwner(journal, current, issuer, dispatch, enabled=True)
    try:
        yield _Composition(gate, issuer, current, dispatch, clock, journal)
    finally:
        issuer.close()
        dispatch.release.set()
        try:
            await gate.wait_for_idle()
        finally:
            journal.close()


@pytest.mark.anyio
async def test_fixed_consumer_uses_the_original_bytes_once(tmp_path: Path) -> None:
    template = _template()
    async with _composition(tmp_path, template) as c:
        body = "synthetic café / 合成内容\n".encode()
        request, handle = c.prepare(template, body)
        acknowledged = await c.gate.submit(request, handle)
        assert acknowledged.phase is AdmissionPhase.ACKNOWLEDGED
        assert c.dispatch.consumer.calls == 1
        assert c.dispatch.consumer.byte_count == len(body)
        assert c.dispatch.consumer.last_body_identity == id(body)
        assert (
            c.issuer.prepare(template.request_id, template.scope, bytes(bytearray(body))) is handle
        )
        assert await c.gate.submit(request, handle) == acknowledged
        assert c.gate.read(request) == acknowledged
        assert acknowledged.receipt_ref is not None
        terminal = c.gate.acknowledge_terminal(
            request,
            expected_revision=acknowledged.record_revision,
            receipt=SyntheticTerminalReceipt("completed", acknowledged.receipt_ref),
        )
        assert await c.gate.submit(request, handle) == terminal
        assert c.dispatch.consumer.calls == 1
        assert body not in (tmp_path / "journal/admission.json").read_bytes()


@pytest.mark.anyio
@pytest.mark.parametrize("different", (b"same length B", "e\u0301".encode(), b"line\r\n"))
async def test_changed_body_never_reuses_an_accepted_key(tmp_path: Path, different: bytes) -> None:
    template = _template()
    original = {
        b"same length B": b"same length A",
        "e\u0301".encode(): "é".encode(),
        b"line\r\n": b"line\n",
    }[different]
    async with _composition(tmp_path, template) as c:
        request, handle = c.prepare(template, original)
        acknowledged = await c.gate.submit(request, handle)
        with pytest.raises(KebuiAdmissionError):
            c.issuer.prepare(template.request_id, template.scope, different)
        assert c.gate.read(request) == acknowledged
        assert c.dispatch.consumer.calls == 1
        assert c.dispatch.consumer.last_body_identity == id(original)


@pytest.mark.anyio
async def test_waiter_cancel_retains_one_effect_and_busy_slot(tmp_path: Path) -> None:
    one, two = _template(), _template(2)
    async with _composition(tmp_path, one, two, blocked=True) as c:
        request, handle = c.prepare(one)
        another, second_handle = c.prepare(two, b"synthetic second")
        first = asyncio.create_task(c.gate.submit(request, handle))
        await asyncio.wait_for(c.dispatch.entered.wait(), 3)
        duplicate = asyncio.create_task(c.gate.submit(request, handle))
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        with pytest.raises(KebuiAdmissionError):
            await c.gate.submit(another, second_handle)
        assert c.dispatch.consumer.calls == 0
        c.dispatch.release.set()
        await c.gate.wait_for_idle()
        await duplicate
        assert c.dispatch.consumer.calls == 1
        record = c.gate.read(request)
        assert record is not None and record.phase is AdmissionPhase.ACKNOWLEDGED


@pytest.mark.anyio
@pytest.mark.parametrize(
    "revocation", ("unavailable", "tui_writer", "execution", "source", "expiry")
)
async def test_last_await_revocation_has_no_body_effect(tmp_path: Path, revocation: str) -> None:
    template = _template()
    async with _composition(tmp_path, template, blocked=True) as c:
        request, handle = c.prepare(template)
        pending = asyncio.create_task(c.gate.submit(request, handle))
        await asyncio.wait_for(c.dispatch.entered.wait(), 3)
        if revocation == "unavailable":
            c.current.available = False
        elif revocation == "tui_writer":
            c.current.tui_writer = True
        elif revocation == "execution":
            c.current.execution_id = "kexe_" + "8" * 32
        elif revocation == "source":
            c.issuer.close()
        else:
            c.clock.now = 100
        c.dispatch.release.set()
        result = await pending
        assert result.phase is AdmissionPhase.UNKNOWN
        assert c.dispatch.consumer.calls == 0
        assert c.journal.read(request) == result
        if revocation in ("source", "expiry"):
            assert c.gate.read(request) == result
            with pytest.raises(KebuiAdmissionError):
                await c.gate.submit(request, handle)


@pytest.mark.anyio
async def test_expiry_does_not_block_metadata_terminal_or_forge_bodyproof(tmp_path: Path) -> None:
    template = _template()
    async with _composition(tmp_path, template) as c:
        request, handle = c.prepare(template)
        acknowledged = await c.gate.submit(request, handle)
        c.clock.now = 100
        assert c.gate.read(request) == acknowledged
        assert acknowledged.receipt_ref is not None
        terminal = c.gate.acknowledge_terminal(
            request,
            expected_revision=acknowledged.record_revision,
            receipt=SyntheticTerminalReceipt("completed", acknowledged.receipt_ref),
        )
        assert c.gate.read(request) == terminal
        with pytest.raises(KebuiAdmissionError):
            await c.gate.submit(request, handle)
        assert c.dispatch.consumer.calls == 1


@pytest.mark.anyio
async def test_observer_does_not_recover_a_live_dispatch(tmp_path: Path) -> None:
    template = _template()
    async with _composition(tmp_path, template, blocked=True) as c:
        request, handle = c.prepare(template)
        pending = asyncio.create_task(c.gate.submit(request, handle))
        await asyncio.wait_for(c.dispatch.entered.wait(), 3)
        observer = KebuiAdmissionJournal.open_existing(
            tmp_path / "journal",
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
            recover=False,
        )
        try:
            observed = observer.read(request)
            assert observed is not None and observed.phase is AdmissionPhase.DISPATCH_FENCED
            c.dispatch.release.set()
            acknowledged = await pending
            assert observer.read(request) == acknowledged
            assert c.dispatch.consumer.calls == 1
        finally:
            observer.close()


@pytest.mark.anyio
async def test_current_read_rejects_replaced_execution_identity(tmp_path: Path) -> None:
    template = _template()
    async with _composition(tmp_path, template) as c:
        request, handle = c.prepare(template)
        acknowledged = await c.gate.submit(request, handle)
        c.current.execution_id = "kexe_" + "8" * 32
        with pytest.raises(KebuiAdmissionError):
            c.gate.read(request)
        assert c.journal.read(request) == acknowledged
        assert c.dispatch.consumer.calls == 1


@pytest.mark.anyio
async def test_expired_body_does_not_allow_receipt_replacement(tmp_path: Path) -> None:
    template = _template()
    async with _composition(tmp_path, template) as c:
        request, handle = c.prepare(template)
        acknowledged = await c.gate.submit(request, handle)
        c.issuer.close()
        with pytest.raises(KebuiAdmissionError):
            c.gate.acknowledge_terminal(
                request,
                expected_revision=acknowledged.record_revision,
                receipt=SyntheticTerminalReceipt("completed", "krcp_" + "f" * 32),
            )
        assert c.gate.read(request) == acknowledged
        assert c.dispatch.consumer.calls == 1


@pytest.mark.anyio
async def test_restart_loses_bodyproof_but_preserves_readable_unknown(tmp_path: Path) -> None:
    template = _template()
    async with _composition(tmp_path, template) as c:
        request, handle = c.prepare(template)
        acknowledged = await c.gate.submit(request, handle)
        assert acknowledged.phase is AdmissionPhase.ACKNOWLEDGED
        assert c.dispatch.consumer.calls == 1
    recovered = KebuiAdmissionJournal.open_existing(
        tmp_path / "journal", expected_uid=os.geteuid(), expected_gid=os.getegid()
    )
    current = _CurrentOwner(template)
    dispatch, clock = _Dispatch(), _Clock()
    fresh = SyntheticContentIssuer(deadline_ns=100, clock=clock)
    owner = KebuiTestAdmissionOwner(recovered, current, fresh, dispatch, enabled=True)
    try:
        result = owner.read(request)
        assert result is not None and result.phase is AdmissionPhase.UNKNOWN
        with pytest.raises(KebuiAdmissionError):
            await owner.submit(request, handle)  # A still-referenced old handle is not authority.
        with pytest.raises(KebuiAdmissionError):
            offered = fresh.prepare(template.request_id, template.scope, _BODY)
            await owner.submit(offered.request, offered)
        assert owner.read(request) == result
        assert dispatch.consumer.calls == 0
        assert _BODY not in (tmp_path / "journal/admission.json").read_bytes()
    finally:
        fresh.close()
        dispatch.release.set()
        await owner.wait_for_idle()
        recovered.close()


_CRASH_STAGES = (
    "before_accept",
    "after_accept",
    "before_fence",
    "after_fence",
    "before_effect",
    "after_effect",
    "after_ack",
    "before_terminal",
    "after_terminal",
)


def _kill_here(stage: str, expected: str) -> None:
    if stage == expected:
        os.kill(os.getpid(), signal.SIGKILL)
        raise AssertionError("child should have stopped")


def _crash_child(directory: Path, stage: str) -> None:
    class CheckpointJournal(KebuiAdmissionJournal):
        def accept(self, *args: Any, **kwargs: Any) -> Any:
            _kill_here(stage, "before_accept")
            result = super().accept(*args, **kwargs)
            _kill_here(stage, "after_accept")
            return result

        def transition(self, *args: Any, **kwargs: Any) -> Any:
            phase = kwargs.get("phase")
            if phase is None and len(args) >= 3:
                phase = args[2]
            if phase is AdmissionPhase.DISPATCH_FENCED:
                _kill_here(stage, "before_fence")
            if phase is AdmissionPhase.TERMINAL:
                _kill_here(stage, "before_terminal")
            result = super().transition(*args, **kwargs)
            if phase is AdmissionPhase.DISPATCH_FENCED:
                _kill_here(stage, "after_fence")
            if phase is AdmissionPhase.ACKNOWLEDGED:
                _kill_here(stage, "after_ack")
            if phase is AdmissionPhase.TERMINAL:
                _kill_here(stage, "after_terminal")
            return result

    original_consume = SyntheticBodyConsumer._consume

    def consume_checkpoint(self: SyntheticBodyConsumer, body: bytes) -> SyntheticDispatchReceipt:
        # Test-only fault injection at the exact synchronous consumer, no product hook.
        _kill_here(stage, "before_effect")
        assert body is _BODY
        receipt = original_consume(self, body)
        fd = os.open(directory / "effects", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, b"synthetic-effect\n")  # No body, hash or exception is persisted.
            os.fsync(fd)
        finally:
            os.close(fd)
        _kill_here(stage, "after_effect")
        return receipt

    patcher = pytest.MonkeyPatch()
    patcher.setattr(SyntheticBodyConsumer, "_consume", consume_checkpoint)

    async def run() -> None:
        template = _template()
        ledger_path = directory / "journal"
        ledger_path.mkdir(mode=0o700)
        journal = CheckpointJournal.initialize_for_test(
            ledger_path, expected_uid=os.geteuid(), expected_gid=os.getegid()
        )
        current, dispatch = _CurrentOwner(template), _Dispatch()
        issuer = SyntheticContentIssuer(deadline_ns=100, clock=_Clock())
        owner = KebuiTestAdmissionOwner(journal, current, issuer, dispatch, enabled=True)
        handle = issuer.prepare(template.request_id, template.scope, _BODY)
        acknowledged = await owner.submit(handle.request, handle)
        assert acknowledged.receipt_ref is not None
        owner.acknowledge_terminal(
            handle.request,
            expected_revision=acknowledged.record_revision,
            receipt=SyntheticTerminalReceipt("completed", acknowledged.receipt_ref),
        )
        raise AssertionError("crash checkpoint was not reached")

    asyncio.run(run())


def _persisted_request(directory: Path) -> AdmissionRequest:
    # Test metadata reconstruction is not source admission or body-proof recovery.
    records = json.loads((directory / "admission.json").read_text())["records"]
    if not records:
        return _template()
    value = records[0]["request"]
    return AdmissionRequest(
        request_id=value["request_id"],
        scope=parse_scope(value["scope"]),
        adapter_profile=value["adapter_profile"],
        content_admission_ref=value["content_admission_ref"],
        operation=value["operation"],
    )


@pytest.mark.skipif(os.name != "posix", reason="local process-crash test uses POSIX SIGKILL")
@pytest.mark.parametrize("stage", _CRASH_STAGES)
def test_real_child_crash_never_replays_on_reopen(tmp_path: Path, stage: str) -> None:
    root = Path(__file__).parents[2]
    paths = [str(path) for path in root.glob("packages/*/src")]
    paths.extend(str(root / path) for path in ("apps/api/src", "apps/cli/src", "apps/worker/src"))
    paths.extend((str(root / "helper/src"), str(root / "installer/src")))
    child = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), str(tmp_path), stage],
        cwd=tmp_path,
        env={"PYTHONPATH": os.pathsep.join(paths), "HOME": str(tmp_path), "LANG": "C.UTF-8"},
        check=False,
        capture_output=True,
        timeout=20,
    )
    assert child.returncode == -signal.SIGKILL, (child.returncode, child.stderr.decode())
    effect_file = tmp_path / "effects"
    before = effect_file.read_bytes() if effect_file.exists() else b""
    assert before in (b"", b"synthetic-effect\n")
    request = _persisted_request(tmp_path / "journal")
    recovered = KebuiAdmissionJournal.open_existing(
        tmp_path / "journal", expected_uid=os.geteuid(), expected_gid=os.getegid()
    )
    try:
        record = recovered.read(request)
        if stage == "before_accept":
            assert record is None  # NOT_OBSERVED is not proof of no earlier delivery.
        elif stage == "after_terminal":
            assert record is not None and record.phase is AdmissionPhase.TERMINAL
        else:
            assert record is not None and record.phase is AdmissionPhase.UNKNOWN
        assert (effect_file.read_bytes() if effect_file.exists() else b"") == before
        assert _BODY not in (tmp_path / "journal/admission.json").read_bytes()
    finally:
        recovered.close()


if __name__ == "__main__":
    _crash_child(Path(sys.argv[1]), sys.argv[2])
