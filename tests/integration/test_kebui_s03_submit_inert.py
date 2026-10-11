"""Inert fresh S03 transport -> exact unchanged admission -> fixed body effect.

The cross-language consumer test is scripts/check-kebui-s03-submit-interop.mjs.
These integration tests additionally inspect ownership, actual waiter cancel,
last-readiness expiry, original-journal recovery and exception/metadata paths.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import itertools
import json
import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from types import FrameType
from typing import Any

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
from agentbox_runtime.kebui_admission import (
    AdmissionPhase,
    KebuiAdmissionError,
    SyntheticTerminalReceipt,
)
from agentbox_runtime.kebui_content_admission import synthetic_pool_usage
from agentbox_runtime.kebui_s03_submit import SyntheticS03Recovery, SyntheticS03TestRoot

_FIXTURE = Path(__file__).parents[1] / "fixtures/kebui_s03_submit/v1.json"
_COUNTER = itertools.count(0x10000)
_CANARY = b"synthetic S03\r\n\x00"
_CASES = (
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


def _body(case: str) -> bytes:
    if case == "ascii_16k":
        return b"x" * 16384
    if case == "nul_16k":
        return bytes(16384)
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
        "mixed_canary": _CANARY,
    }[case]


class _Clock:
    now = 100_000_000_000

    def __call__(self) -> int:
        return self.now


def _context() -> dict[str, str]:
    fixture: dict[str, Any] = json.loads(_FIXTURE.read_text())
    suffix = f"{next(_COUNTER):032x}"
    return {
        **fixture["context"],
        "request_id": "kreq_" + suffix,
        "channel_id": "ks03c_" + suffix,
        "source_lease_id": "ks03l_" + suffix,
    }


@dataclass
class _Composition:
    root: SyntheticS03TestRoot
    clock: _Clock
    endpoint: object
    context: dict[str, str]
    transport: NoiseTransport

    def frame(self, body: bytes) -> bytes:
        context = build_context(self.context)
        ciphertext = self.transport.send.encrypt(
            body, aad(context.digest, self.transport.handshake_hash, 0, 5, 1)
        )
        assert self.transport.send.nonce == 2
        return encode_frame(context.cd, "SUBMIT", 1, ciphertext)


@asynccontextmanager
async def _composition(tmp_path: Path) -> AsyncIterator[_Composition]:
    directory = tmp_path / "journal"
    directory.mkdir(mode=0o700)
    context, clock, endpoint = _context(), _Clock(), object()
    root = SyntheticS03TestRoot.create_for_test(
        directory=directory,
        endpoint=endpoint,
        context=context,
        clock=clock,
        deadline_ns=112_000_000_000,
        enabled=True,
    )
    transport = None
    try:
        # This initiator, like the actual Web harness, does not inject keys.
        bound = build_context(context)
        initiator = NXInitiator(bound.prologue)
        root.open(endpoint)
        attest = root.receive_handshake(
            encode_frame(bound.cd, "KEY_INIT", 0, initiator.write_message1()), endpoint
        )
        assert len(attest) == 296
        assert initiator.read_message2(decode_frame(attest, bound.cd, "KEY_ATTEST", 0)) == b""
        transport = initiator.take_transport()
        initiator.destroy()
        assert transport.remote_static_public_key == bound.runtime_pin
        hh = transport.handshake_hash
        ready = root.receive_handshake(
            encode_frame(
                bound.cd,
                "KEY_CONFIRM",
                0,
                transport.send.encrypt(
                    CONFIRM_DOMAIN + bound.digest + hh, aad(bound.digest, hh, 0, 3, 0)
                ),
            ),
            endpoint,
        )
        assert len(ready) == 313
        assert (
            transport.receive.decrypt(
                decode_frame(ready, bound.cd, "KEY_READY", 0), aad(bound.digest, hh, 1, 4, 0)
            )
            == READY_DOMAIN + bound.digest + hh
        )
        assert transport.send.nonce == transport.receive.nonce == 1
        yield _Composition(root, clock, endpoint, context, transport)
    finally:
        if transport is not None:
            transport.destroy()
        await root.aclose()
        assert root.pool_drained


@pytest.mark.anyio
@pytest.mark.parametrize("case", _CASES)
async def test_original_decrypt_object_and_exact_bytes_reach_consumer(
    tmp_path: Path, case: str
) -> None:
    async with _composition(tmp_path) as c:
        body = _body(case)
        expected_count = len(body)
        frame = c.frame(body)
        body = b""
        if expected_count == 16384:
            assert len(frame) == 22031
        handle = c.root.receive_submit_and_prepare(frame, c.endpoint, oracle_case=case)
        frame = b""
        assert c.root.state == "CLOSED"
        assert c.root.original_identity_match
        assert c.root.consumer.calls == 0
        record = await c.root.submit_prepared(handle)
        assert record.phase is AdmissionPhase.ACKNOWLEDGED
        assert c.root.consumer.calls == 1
        assert c.root.consumer.byte_count == expected_count
        assert c.root.consumer.last_body_identity == c.root.decrypted_identity
        c.root.revoke_source()
        assert c.root.owner.read(handle.request) == record
        assert record.receipt_ref is not None
        terminal = c.root.owner.acknowledge_terminal(
            handle.request,
            expected_revision=record.record_revision,
            receipt=SyntheticTerminalReceipt("completed", record.receipt_ref),
        )
        assert terminal.phase is AdmissionPhase.TERMINAL
        assert c.root.consumer.calls == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body", (b"", b"\xc0\x80", b"\xed\xa0\x80", b"\xf0\x9f\x98", b"\xf4\x90\x80\x80", b"\xff")
)
async def test_invalid_exact_utf8_never_creates_effect(tmp_path: Path, body: bytes) -> None:
    async with _composition(tmp_path) as c:
        with pytest.raises((S03Error, KebuiAdmissionError)):
            c.root.receive_submit_and_prepare(c.frame(body), c.endpoint)
        assert c.root.consumer.calls == 0
        assert synthetic_pool_usage().entries == 0
        assert synthetic_pool_usage().retained_bytes == 0


@pytest.mark.anyio
async def test_actual_waiter_cancel_does_not_cancel_accepted_worker(tmp_path: Path) -> None:
    async with _composition(tmp_path) as c:
        handle = c.root.receive_submit_and_prepare(
            c.frame(_CANARY), c.endpoint, oracle_case="mixed_canary"
        )
        c.root.readiness.hold()
        coroutine = c.root.submit_prepared(handle)
        waiter = asyncio.create_task(coroutine)
        await c.root.readiness.entered.wait()
        frame = getattr(coroutine, "cr_frame", None)
        assert isinstance(frame, FrameType)
        assert not any(
            isinstance(value, (bytes, bytearray, memoryview)) for value in frame.f_locals.values()
        )
        before = synthetic_pool_usage()
        assert before.retained_bytes == len(_CANARY) and before.worker_slots == 1
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert synthetic_pool_usage().retained_bytes == len(_CANARY)
        assert c.root.consumer.calls == 0
        c.root.readiness.release()
        await c.root.owner.wait_for_idle()
        assert c.root.consumer.calls == 1
        observed = c.root.owner.read(handle.request)
        assert observed is not None and observed.phase is AdmissionPhase.ACKNOWLEDGED
        with pytest.raises(S03Error):
            await c.root.submit_prepared(handle)
        assert c.root.consumer.calls == 1


@pytest.mark.anyio
@pytest.mark.parametrize("change", ("source", "expiry", "execution", "scope"))
async def test_last_readiness_boundary_preserves_unknown_and_zero_effect(
    tmp_path: Path, change: str
) -> None:
    async with _composition(tmp_path) as c:
        handle = c.root.receive_submit_and_prepare(
            c.frame(_CANARY), c.endpoint, oracle_case="mixed_canary"
        )
        c.root.readiness.hold()
        waiter = asyncio.create_task(c.root.submit_prepared(handle))
        await c.root.readiness.entered.wait()
        if change == "source":
            c.root.revoke_source()
        elif change == "expiry":
            c.clock.now = 112_000_000_000
            c.root.deadlines.fire_for_test()
            assert c.root.deadlines.expired.done()
        elif change == "execution":
            c.root.replace_current_for_test(execution_id="kexe_" + "f" * 32)
            c.root.readiness.release()
        else:
            c.root.replace_current_for_test(scope=replace(c.root.context.scope, auth_epoch="99"))
            c.root.readiness.release()
        record = await waiter
        assert record.phase is AdmissionPhase.UNKNOWN
        assert c.root.consumer.calls == 0
        assert c.root.journal.read(handle.request) == record
        if change in {"source", "expiry"}:
            assert c.root.owner.read(handle.request) == record
        assert synthetic_pool_usage().worker_slots == 0


@pytest.mark.anyio
async def test_original_journal_recovery_is_metadata_only_and_rejects_missing_catalog(
    tmp_path: Path,
) -> None:
    async with _composition(tmp_path) as c:
        handle = c.root.receive_submit_and_prepare(
            c.frame(_CANARY), c.endpoint, oracle_case="mixed_canary"
        )
        acknowledged = await c.root.submit_prepared(handle)
        assert acknowledged.phase is AdmissionPhase.ACKNOWLEDGED
        catalog = c.root.recovery_catalog("lost_ack_recovery", handle.request)
        context = dict(c.context)
        assert len(json.dumps(catalog, separators=(",", ":"))) <= 4096
        assert _CANARY not in (tmp_path / "journal/admission.json").read_bytes()
        assert (
            hashlib.sha256(_CANARY).hexdigest().encode()
            not in (tmp_path / "journal/admission.json").read_bytes()
        )
    directory = tmp_path / "journal"
    for bad in (
        None,
        {},
        {**catalog, "inode": -1},
        {**catalog, "scenario": "foreign"},
        {**catalog, "directory": str(tmp_path / "absent")},
    ):
        with pytest.raises(S03Error):
            SyntheticS03Recovery.open(
                bad, directory=directory, context=context, scenario="lost_ack_recovery"
            )
    replacement = tmp_path / "replacement"
    replacement.mkdir(mode=0o700)
    with pytest.raises(S03Error):
        SyntheticS03Recovery.open(
            catalog, directory=replacement, context=context, scenario="lost_ack_recovery"
        )
    assert not (replacement / "admission.json").exists()
    recovery = SyntheticS03Recovery.open(
        catalog, directory=directory, context=context, scenario="lost_ack_recovery"
    )
    try:
        record = recovery.read()
        assert record is not None and record.phase is AdmissionPhase.UNKNOWN
        assert not hasattr(recovery, "issuer") and not hasattr(recovery, "submit")
        with pytest.raises(KebuiAdmissionError):
            recovery.journal.accept(
                replace(recovery.request, request_id="kreq_" + "f" * 32),
                context["execution_id"],
            )
        # Repeated metadata recovery must neither fabricate a source nor lose UNKNOWN.
        assert recovery.read() == record
    finally:
        recovery.close()


@pytest.mark.anyio
async def test_oracle_failure_discards_unaccepted_staging(tmp_path: Path) -> None:
    async with _composition(tmp_path) as c:
        with pytest.raises(S03Error):
            c.root.receive_submit_and_prepare(c.frame(_CANARY), c.endpoint, oracle_case="minimum")
        assert synthetic_pool_usage().entries == 0
        assert synthetic_pool_usage().retained_bytes == 0
        assert c.root.consumer.calls == 0


@pytest.mark.anyio
async def test_corrupt_tag_is_redacted_and_does_not_retain_payload_traceback(
    tmp_path: Path,
) -> None:
    async with _composition(tmp_path) as c:
        frame = bytearray(c.frame(_CANARY))
        position = frame.index(b'"data":"') + len(b'"data":"')
        frame[position] = ord("A") if frame[position] != ord("A") else ord("B")
        error: BaseException | None = None
        try:
            c.root.receive_submit_and_prepare(bytes(frame), c.endpoint)
        except S03Error as caught:
            error = caught
        assert error is not None
        assert error.args == ("s03_invalid",)
        assert error.__cause__ is None and error.__context__ is None
        rendered = "".join(traceback.format_exception(error))
        assert "synthetic S03" not in rendered
        assert hashlib.sha256(_CANARY).hexdigest() not in rendered
        trace = error.__traceback__
        while trace is not None:
            if trace.tb_frame.f_code.co_filename.endswith("kebui_s03_submit.py"):
                local = trace.tb_frame.f_locals
                assert local.get("raw") is None and local.get("body") is None
            trace = trace.tb_next
        assert c.root.consumer.calls == 0
        assert c.root.pool_drained


@pytest.mark.anyio
async def test_sealed_permit_copy_cannot_create_second_endpoint(tmp_path: Path) -> None:
    async with _composition(tmp_path) as c:
        with pytest.raises(S03Error):
            copy.copy(c.root.permit)
        with pytest.raises(S03Error):
            c.root.receive_submit_and_prepare(c.frame(_CANARY), object())
        assert c.root.consumer.calls == 0


def test_rejected_inner_json_design_arithmetic() -> None:
    assert len(json.dumps("\0" * 16384, ensure_ascii=True, separators=(",", ":")).encode()) == 98306
    assert 98306 > 65535


@pytest.mark.anyio
@pytest.mark.parametrize("fault", ("accept_after_commit", "witness", "retain", "callback", "ack"))
async def test_new_source_preserves_original_uncertainty_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    async with _composition(tmp_path) as c:
        handle = c.root.receive_submit_and_prepare(
            c.frame(_CANARY), c.endpoint, oracle_case="mixed_canary"
        )
        canary = "private-secondary-S03-canary"
        if fault == "accept_after_commit":
            original_accept = c.root.journal.accept

            def after_accept(*args: Any, **kwargs: Any) -> Any:
                original_accept(*args, **kwargs)
                raise RuntimeError(canary)

            monkeypatch.setattr(c.root.journal, "accept", after_accept)
        elif fault in {"witness", "retain", "callback"}:
            target = c.root.issuer if fault == "witness" else c.root.owner
            attribute = {
                "witness": "_accept_witness",
                "retain": "_retain_worker",
                "callback": "_register_worker",
            }[fault]

            def failure(*args: Any, **kwargs: Any) -> Any:
                raise RuntimeError(canary)

            monkeypatch.setattr(target, attribute, failure)
        else:
            original_transition = c.root.journal.transition

            def fail_ack(*args: Any, **kwargs: Any) -> Any:
                if args[2] is AdmissionPhase.ACKNOWLEDGED:
                    raise RuntimeError(canary)
                return original_transition(*args, **kwargs)

            monkeypatch.setattr(c.root.journal, "transition", fail_ack)
        error: BaseException | None = None
        try:
            await c.root.submit_prepared(handle)
        except (S03Error, KebuiAdmissionError) as caught:
            error = caught
        await c.root.owner.wait_for_idle()
        if error is not None:
            assert error.__cause__ is None and error.__context__ is None
            assert canary not in str(error.args)
            assert canary not in "".join(traceback.format_exception(error))
        observed = c.root.owner.read(handle.request)
        expected = (
            AdmissionPhase.ACCEPTED if fault == "accept_after_commit" else AdmissionPhase.UNKNOWN
        )
        assert observed is not None and observed.phase is expected
        if fault == "accept_after_commit":
            assert isinstance(error, KebuiAdmissionError)
            assert error.args == ("store_unavailable",)
            catalog = c.root.recovery_catalog("commit_return_loss", handle.request)
            context = dict(c.context)
            with pytest.raises(KebuiAdmissionError):
                c.root.journal.accept(
                    replace(handle.request, request_id="kreq_" + "f" * 32),
                    c.root.context.execution_id,
                )
        assert c.root.consumer.calls == (1 if fault == "ack" else 0)
        # Once durable admission might exist, transport or source replacement
        # cannot turn this into a fresh submission or release the occupied slot.
        with pytest.raises(S03Error):
            await c.root.submit_prepared(handle)
        assert c.root.consumer.calls <= 1
        journal = (tmp_path / "journal/admission.json").read_bytes()
        assert canary.encode() not in journal and _CANARY not in journal

    if fault == "accept_after_commit":
        # The frozen owner cannot know accept() committed before its return was
        # lost. Its live ACCEPTED is occupied, not permission to retry. This is
        # the original behavior, preserved by the explicit contract clarification.
        replacement = tmp_path / "second"
        replacement.mkdir(mode=0o700)
        with pytest.raises(S03Error):
            SyntheticS03TestRoot.create_for_test(
                directory=replacement,
                endpoint=object(),
                context=context,
                clock=_Clock(),
                deadline_ns=112_000_000_000,
                enabled=True,
            )
        assert not (replacement / "admission.json").exists()
        recovery = SyntheticS03Recovery.open(
            catalog,
            directory=tmp_path / "journal",
            context=context,
            scenario="commit_return_loss",
        )
        try:
            recovered = recovery.read()
            assert recovered is not None and recovered.phase is AdmissionPhase.UNKNOWN
        finally:
            recovery.close()
