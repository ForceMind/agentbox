"""Inert admission consumers: synthetic metadata, private tmp files, no vendor.

These tests exercise the candidate through a fake dispatch port, including actual
child-process death. They do not qualify content equality, Runtime authority,
provider behavior, host power loss, or an application route.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
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

_EXECUTION = "kexe_" + "7" * 32
_FIXTURE = Path(__file__).parents[1] / "fixtures/kebui_observation/v1.json"


def _request(number: int = 1, **scope_changes: str) -> AdmissionRequest:
    source = json.loads(_FIXTURE.read_text())["base"]["scope"]
    source["turn_id"] = "ktr_" + f"{number:032x}"
    source.update(scope_changes)
    return AdmissionRequest(
        request_id="kreq_" + f"{number:032x}",
        scope=parse_scope(source),
        adapter_profile=SYNTHETIC_ADAPTER_PROFILE,
        content_admission_ref="ksyn_" + f"{number:032x}",
    )


class _CurrentOwner:
    """A test premise, not a source of production authority or writer rights."""

    def __init__(self, *requests: AdmissionRequest) -> None:
        self.scopes = {request.scope for request in requests}
        self.available = True
        self.tui_writer = False
        self.execution_id = _EXECUTION

    @contextmanager
    def guard(self, scope: ConversationScope) -> Iterator[SyntheticOwnerContext]:
        if not self.available or self.tui_writer or scope not in self.scopes:
            raise ValueError("synthetic owner unavailable")
        yield SyntheticOwnerContext(scope=scope, execution_id=self.execution_id)
        if not self.available or self.tui_writer or scope not in self.scopes:
            raise ValueError("synthetic owner changed")


class _SyntheticEquality:
    """No prompt/body equality: only the fixture's immutable reference mapping."""

    def __init__(self, *requests: AdmissionRequest) -> None:
        self.requests = {request.request_id: request for request in requests}

    def validate(self, request: AdmissionRequest) -> bool:
        return self.requests.get(request.request_id) == request


class _Dispatch:
    def __init__(self, *, blocked: bool = False) -> None:
        self.calls: list[tuple[AdmissionRequest, str]] = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        if not blocked:
            self.release.set()

    async def dispatch(
        self, request: AdmissionRequest, execution_id: str
    ) -> SyntheticDispatchReceipt:
        self.calls.append((request, execution_id))
        self.entered.set()
        await self.release.wait()
        return SyntheticDispatchReceipt(receipt_ref="krcp_" + request.request_id[5:])


def _journal(directory: Path) -> KebuiAdmissionJournal:
    directory.mkdir(mode=0o700)
    return KebuiAdmissionJournal.initialize_for_test(
        directory, expected_uid=os.geteuid(), expected_gid=os.getegid()
    )


def _owner(
    journal: KebuiAdmissionJournal,
    current: _CurrentOwner,
    equality: _SyntheticEquality,
    dispatch: _Dispatch,
) -> KebuiTestAdmissionOwner:
    return KebuiTestAdmissionOwner(journal, current, equality, dispatch, enabled=True)


@pytest.mark.anyio
async def test_fake_dispatch_receipt_and_terminal_are_reused_without_effect(tmp_path: Path) -> None:
    request = _request()
    journal = _journal(tmp_path / "journal")
    dispatch = _Dispatch()
    owner = _owner(journal, _CurrentOwner(request), _SyntheticEquality(request), dispatch)
    acknowledged = await owner.submit(request)
    assert acknowledged.phase is AdmissionPhase.ACKNOWLEDGED
    assert len(dispatch.calls) == 1
    assert owner.read(request) == acknowledged
    assert await owner.submit(request) == acknowledged
    assert acknowledged.receipt_ref is not None
    terminal = owner.acknowledge_terminal(
        request,
        expected_revision=acknowledged.record_revision,
        receipt=SyntheticTerminalReceipt(status="completed", receipt_ref=acknowledged.receipt_ref),
    )
    assert terminal.phase is AdmissionPhase.TERMINAL
    assert await owner.submit(request) == terminal
    assert len(dispatch.calls) == 1
    journal.close()


@pytest.mark.anyio
async def test_two_waiters_share_one_dispatch_and_cancel_does_not_release(tmp_path: Path) -> None:
    request, another = _request(), _request(2)
    journal = _journal(tmp_path / "journal")
    current = _CurrentOwner(request, another)
    equality = _SyntheticEquality(request, another)
    dispatch = _Dispatch(blocked=True)
    owner = _owner(journal, current, equality, dispatch)
    first = asyncio.create_task(owner.submit(request))
    await asyncio.wait_for(dispatch.entered.wait(), 3)
    duplicate = asyncio.create_task(owner.submit(request))
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    with pytest.raises(KebuiAdmissionError, match="^busy$"):
        await owner.submit(another)
    dispatch.release.set()
    await owner.wait_for_idle()
    await duplicate
    assert len(dispatch.calls) == 1
    observed = owner.read(request)
    assert observed is not None and observed.phase is AdmissionPhase.ACKNOWLEDGED
    journal.close()


@pytest.mark.anyio
async def test_foreign_scope_and_synthetic_tui_writer_never_dispatch(tmp_path: Path) -> None:
    request = _request()
    journal = _journal(tmp_path / "journal")
    current = _CurrentOwner(request)
    dispatch = _Dispatch()
    owner = _owner(journal, current, _SyntheticEquality(request), dispatch)
    current.tui_writer = True
    with pytest.raises(KebuiAdmissionError, match="^owner_unavailable$"):
        await owner.submit(request)
    current.tui_writer = False
    changed = _request(auth_epoch="99")
    with pytest.raises(KebuiAdmissionError, match="^owner_unavailable$"):
        await owner.submit(changed)
    assert dispatch.calls == []
    journal.close()


@pytest.mark.anyio
async def test_recovery_retains_unknown_slot_across_conversation_and_epoch(tmp_path: Path) -> None:
    request = _request()
    directory = tmp_path / "journal"
    journal = _journal(directory)
    journal.accept(request, _EXECUTION)
    journal.close()
    recovered = KebuiAdmissionJournal.open_existing(
        directory, expected_uid=os.geteuid(), expected_gid=os.getegid()
    )
    recovered_record = recovered.read(request)
    assert recovered_record is not None and recovered_record.phase is AdmissionPhase.UNKNOWN
    another = _request(2, conversation_id="kcv_" + "8" * 32, runtime_epoch="77", generation="88")
    dispatch = _Dispatch()
    owner = _owner(
        recovered, _CurrentOwner(request, another), _SyntheticEquality(request, another), dispatch
    )
    assert (await owner.submit(request)).phase is AdmissionPhase.UNKNOWN
    with pytest.raises(KebuiAdmissionError, match="^busy$"):
        await owner.submit(another)
    assert dispatch.calls == []
    recovered.close()


@pytest.mark.anyio
async def test_observer_read_does_not_recover_a_live_dispatch(tmp_path: Path) -> None:
    request = _request()
    directory = tmp_path / "journal"
    journal = _journal(directory)
    dispatch = _Dispatch(blocked=True)
    owner = _owner(journal, _CurrentOwner(request), _SyntheticEquality(request), dispatch)
    pending = asyncio.create_task(owner.submit(request))
    await asyncio.wait_for(dispatch.entered.wait(), 3)
    observer = KebuiAdmissionJournal.open_existing(
        directory, expected_uid=os.geteuid(), expected_gid=os.getegid(), recover=False
    )
    observed = observer.read(request)
    assert observed is not None and observed.phase is AdmissionPhase.DISPATCH_FENCED
    dispatch.release.set()
    acknowledged = await pending
    assert acknowledged.phase is AdmissionPhase.ACKNOWLEDGED
    assert observer.read(request) == acknowledged
    assert len(dispatch.calls) == 1
    observer.close()
    journal.close()


@pytest.mark.anyio
async def test_terminal_cannot_replace_an_acknowledged_receipt(tmp_path: Path) -> None:
    request = _request()
    journal = _journal(tmp_path / "journal")
    dispatch = _Dispatch()
    owner = _owner(journal, _CurrentOwner(request), _SyntheticEquality(request), dispatch)
    acknowledged = await owner.submit(request)
    with pytest.raises(KebuiAdmissionError):
        owner.acknowledge_terminal(
            request,
            expected_revision=acknowledged.record_revision,
            receipt=SyntheticTerminalReceipt(status="completed", receipt_ref="krcp_" + "f" * 32),
        )
    assert owner.read(request) == acknowledged
    assert len(dispatch.calls) == 1
    journal.close()


@pytest.mark.anyio
async def test_current_read_rejects_replaced_execution_identity(tmp_path: Path) -> None:
    request = _request()
    journal = _journal(tmp_path / "journal")
    current = _CurrentOwner(request)
    dispatch = _Dispatch()
    owner = _owner(journal, current, _SyntheticEquality(request), dispatch)
    acknowledged = await owner.submit(request)
    current.execution_id = "kexe_" + "8" * 32
    with pytest.raises(KebuiAdmissionError):
        owner.read(request)
    assert journal.read(request) == acknowledged  # Internal history is not rewritten.
    assert len(dispatch.calls) == 1
    journal.close()


@pytest.mark.anyio
@pytest.mark.parametrize("revocation", ("unavailable", "tui_writer", "execution_changed"))
async def test_fake_effect_rechecks_held_owner_after_await(tmp_path: Path, revocation: str) -> None:
    request = _request()
    journal = _journal(tmp_path / "journal")
    current = _CurrentOwner(request)

    class GuardedEffect(_Dispatch):
        async def dispatch(
            self, request: AdmissionRequest, execution_id: str
        ) -> SyntheticDispatchReceipt:
            # The fake consumer explicitly honors the injected guard contract.
            # Merely entering a Python context manager would not exclude writers.
            self.entered.set()
            await self.release.wait()
            if not current.available or current.tui_writer or current.execution_id != execution_id:
                raise RuntimeError("synthetic owner revoked before effect")
            return await super().dispatch(request, execution_id)

    dispatch = GuardedEffect(blocked=True)
    owner = _owner(journal, current, _SyntheticEquality(request), dispatch)
    pending = asyncio.create_task(owner.submit(request))
    await asyncio.wait_for(dispatch.entered.wait(), 3)
    if revocation == "unavailable":
        current.available = False
    elif revocation == "tui_writer":
        current.tui_writer = True
    else:
        current.execution_id = "kexe_" + "8" * 32
    dispatch.release.set()
    result = await pending
    assert result.phase is AdmissionPhase.UNKNOWN
    assert dispatch.calls == []
    assert journal.read(request) == result
    journal.close()


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
    """Executed only by this test's own child, never by a vendor process."""

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

    class Effect(_Dispatch):
        async def dispatch(
            self, request: AdmissionRequest, execution_id: str
        ) -> SyntheticDispatchReceipt:
            _kill_here(stage, "before_effect")
            fd = os.open(directory / "effects", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, b"synthetic-effect\n")
                os.fsync(fd)
            finally:
                os.close(fd)
            _kill_here(stage, "after_effect")
            return await super().dispatch(request, execution_id)

    async def run() -> None:
        request = _request()
        ledger_path = directory / "journal"
        ledger_path.mkdir(mode=0o700)
        journal = CheckpointJournal.initialize_for_test(
            ledger_path, expected_uid=os.geteuid(), expected_gid=os.getegid()
        )
        owner = _owner(journal, _CurrentOwner(request), _SyntheticEquality(request), Effect())
        acknowledged = await owner.submit(request)
        assert acknowledged.receipt_ref is not None
        owner.acknowledge_terminal(
            request,
            expected_revision=acknowledged.record_revision,
            receipt=SyntheticTerminalReceipt(
                status="completed", receipt_ref=acknowledged.receipt_ref
            ),
        )
        raise AssertionError("crash checkpoint was not reached")

    asyncio.run(run())


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
    recovered = KebuiAdmissionJournal.open_existing(
        tmp_path / "journal", expected_uid=os.geteuid(), expected_gid=os.getegid()
    )
    record = recovered.read(_request())
    if stage == "before_accept":
        assert record is None  # NOT_OBSERVED is not proof of no earlier delivery.
    elif stage == "after_terminal":
        assert record is not None and record.phase is AdmissionPhase.TERMINAL
    else:
        assert record is not None and record.phase is AdmissionPhase.UNKNOWN
    assert (effect_file.read_bytes() if effect_file.exists() else b"") == before
    recovered.close()


if __name__ == "__main__":
    _crash_child(Path(sys.argv[1]), sys.argv[2])
