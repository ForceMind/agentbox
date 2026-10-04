"""Actual staged Git + selector/admission + Noise + opaque in-memory pipeline."""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from agentbox_protocol.a3_content import ContentError, context_digest, encode_message
from agentbox_protocol.a3_crypto import A3Browser, decode_key, decode_record
from agentbox_runtime.a3_content_session import serve_admitted_staged_read
from agentbox_runtime.git_staged_selectors import AdmittedStagedRead, GitStagedSelectors
from agentbox_runtime.models import RuntimeOperationError
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from test_git_staged_reader import LocalGitRunner, stage
from test_git_staged_selectors import _PROJECT, _SCOPE, setup, token

KEY = bytes(range(32))  # Published synthetic test key only.
PIN = hashlib.sha256(
    X25519PrivateKey.from_private_bytes(KEY).public_key().public_bytes_raw()
).hexdigest()


class Relay:
    """Opaque bounded fixture relay. No plaintext/context/key object is accepted."""

    def __init__(self) -> None:
        self.to_runtime: asyncio.Queue[bytes] = asyncio.Queue(1)
        self.to_browser: asyncio.Queue[bytes] = asyncio.Queue(1)
        self.records: list[bytes] = []
        self.closed = False
        self.fail_send = False

    async def receive(self) -> bytes:
        raw = await self.to_runtime.get()
        assert type(raw) is bytes and len(raw) <= 24576
        return raw

    async def send(self, raw: bytes, check_current: Callable[[], None]) -> None:
        assert not self.closed and type(raw) is bytes and len(raw) <= 24576
        if self.fail_send:
            raise OSError("synthetic uncertain write")
        # Only opaque known envelopes, no parsed plaintext.
        (decode_key if b'"data":' in raw else decode_record)(raw)
        # Fixture capacity reservation: when full, wait without publishing.
        while self.to_browser.full():
            await asyncio.sleep(0)
        check_current()
        assert not self.closed
        self.records.append(raw)
        self.to_browser.put_nowait(raw)

    def close(self) -> None:
        self.closed = True


async def browser_read(
    admitted: AdmittedStagedRead, selection: str, relay: Relay, *, lose_page: bool = False
) -> bytes:
    context = admitted.context
    browser = A3Browser(
        context,
        expected_pin=lambda: PIN,
        clock_ms=lambda: time.monotonic_ns() // 1_000_000,
        current=lambda: context,
        deadline_ms=admitted.expires_ns // 1_000_000,
    )
    try:
        await relay.to_runtime.put(browser.start())
        await relay.to_runtime.put(browser.receive_attest(await relay.to_browser.get()))
        browser.receive_ack(await relay.to_browser.get())
        request = encode_message(
            {
                "protocol_id": "agentbox-a3-content/v1",
                "protocol_version": 1,
                "context_digest": context_digest(context),
                "request_nonce": context["request_nonce"],
                "kind": "PATCH_READ",
                "selection_id": selection,
            }
        )
        await relay.to_runtime.put(browser.encrypt_read(request))
        while True:
            raw = await relay.to_browser.get()
            if lose_page and decode_record(raw)["kind"] == "PATCH_PAGE":
                lose_page = False
                continue
            result = browser.receive_record(raw)
            if result is not None:
                return result
    finally:
        browser.close()


@pytest.mark.anyio
@pytest.mark.parametrize("native", [False, True])
async def test_git_through_same_held_read_preflight_noise_opaque_relay(
    tmp_path: Path, native: bool
) -> None:
    owner, project, runner, _, _ = setup(tmp_path, LocalGitRunner(native=native))
    selection = await token(owner)
    (project / "modified.txt").write_text("unstaged must never reach channel\n")
    relay = Relay()
    async with owner.admit(_PROJECT, _SCOPE, selection, b"n" * 32) as admitted:
        browser = asyncio.create_task(browser_read(admitted, selection, relay))
        await serve_admitted_staged_read(admitted, KEY, relay)
        result = await browser
    assert b"+staged secret-canary content" in result
    assert b"unstaged must never" not in result
    assert runner.diff_count == 2
    assert relay.closed and owner._active == 0
    assert len(owner._burned_nonces) == 1
    assert all(b"secret-canary" not in raw and b"selection_id" not in raw for raw in relay.records)
    with pytest.raises(RuntimeOperationError):
        async with owner.admit(_PROJECT, _SCOPE, selection, b"n" * 32):
            pytest.fail("nonce replay admitted")


@pytest.mark.anyio
async def test_lost_page_destroys_without_partial_result(tmp_path: Path) -> None:
    owner, _, _, _, _ = setup(tmp_path)
    selection = await token(owner)
    relay = Relay()
    async with owner.admit(_PROJECT, _SCOPE, selection, b"n" * 32) as admitted:
        browser = asyncio.create_task(browser_read(admitted, selection, relay, lose_page=True))
        await serve_admitted_staged_read(admitted, KEY, relay)
        with pytest.raises(ContentError):
            await browser
    assert relay.closed and owner._active == 0


@pytest.mark.anyio
async def test_capacity_preflight_occurs_before_handshake_or_any_send(tmp_path: Path) -> None:
    owner, project, runner, _, _ = setup(tmp_path)
    (project / "modified.txt").write_text("x" * 200000 + "\n")
    stage(project, "modified.txt")
    selection = await token(owner)
    relay = Relay()
    async with owner.admit(_PROJECT, _SCOPE, selection, b"n" * 32) as admitted:
        with pytest.raises(ContentError, match="PATCH_TOO_LARGE"):
            await serve_admitted_staged_read(admitted, KEY, relay)
    assert runner.diff_count == 2
    assert relay.records == [] and relay.closed
    assert owner._active == 0 and len(owner._burned_nonces) == 1


@pytest.mark.anyio
async def test_original_expiry_not_reset_at_admission_or_handshake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [100_000_000_000]
    monkeypatch.setattr(time, "monotonic_ns", lambda: now[0])
    owner, _, runner, _, _ = setup(tmp_path)
    selection = await token(owner)
    now[0] += 29_000_000_000
    async with owner.admit(_PROJECT, _SCOPE, selection, b"n" * 32) as admitted:
        assert admitted.expires_ns == 130_000_000_000
        runner.after_first_diff = lambda: now.__setitem__(0, 130_000_000_000)
        relay = Relay()
        with pytest.raises(RuntimeOperationError, match="Staged selection changed"):
            await serve_admitted_staged_read(admitted, KEY, relay)
        assert relay.closed and not relay.records
    assert owner._active == 0


@pytest.mark.anyio
async def test_live_ledger_full_no_eviction_rebuild_or_early_retirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [100_000_000_000]
    monkeypatch.setattr(time, "monotonic_ns", lambda: now[0])
    owner, _, _, context, reader = setup(tmp_path)
    selection = await token(owner)
    for index in range(128):
        async with owner.admit(_PROJECT, _SCOPE, selection, index.to_bytes(32, "big")):
            pass
    assert len(owner._burned_nonces) == 128 and owner._active == 0
    for nonce, code in [(bytes(32), "PATCH_STALE"), (b"z" * 32, "PATCH_UNAVAILABLE_BUSY")]:
        with pytest.raises(RuntimeOperationError) as error:
            async with owner.admit(_PROJECT, _SCOPE, selection, nonce):
                pytest.fail("ledger admitted")
        assert error.value.code == code
    replacement = GitStagedSelectors(reader, context=context)
    with pytest.raises(RuntimeOperationError):
        async with replacement.admit(_PROJECT, _SCOPE, selection, b"z" * 32):
            pytest.fail("old token survived owner recreation")
    now[0] += 30_000_000_000
    fresh = await token(owner)
    async with owner.admit(_PROJECT, _SCOPE, fresh, b"z" * 32):
        assert len(owner._burned_nonces) == 1
    assert owner._active == 0


@pytest.mark.anyio
async def test_shared_four_active_limit_and_cancelled_admission_cleanup(tmp_path: Path) -> None:
    owner, _, _, _, _ = setup(tmp_path)
    selection = await token(owner)
    scopes = [owner.admit(_PROJECT, _SCOPE, selection, i.to_bytes(32, "big")) for i in range(4)]
    handles = [await scope.__aenter__() for scope in scopes]
    assert owner._active == 4
    with pytest.raises(RuntimeOperationError, match="busy"):
        await owner.read(_PROJECT, _SCOPE, selection)
    with pytest.raises(RuntimeOperationError, match="busy"):
        async with owner.admit(_PROJECT, _SCOPE, selection, b"z" * 32):
            pass
    for scope in scopes:
        await scope.__aexit__(None, None, None)
    for handle in handles:
        with pytest.raises(RuntimeOperationError):
            handle.check()
    assert owner._active == 0
    async with owner.admit(_PROJECT, _SCOPE, selection, b"z" * 32) as admitted:
        relay = Relay()
        task = asyncio.create_task(serve_admitted_staged_read(admitted, KEY, relay))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert relay.closed
    assert owner._active == 0


@pytest.mark.anyio
@pytest.mark.parametrize("mutation", ["revoked", "epoch", "closed", "fork"])
async def test_guard_changes_after_admission_no_read_or_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    owner, _, runner, context, _ = setup(tmp_path)
    selection = await token(owner)
    async with owner.admit(_PROJECT, _SCOPE, selection, b"n" * 32) as admitted:
        assert context.current is not None
        if mutation == "revoked":
            context.current = None
        elif mutation == "epoch":
            context.current = dataclasses.replace(context.current, runtime_epoch="2")
        elif mutation == "closed":
            owner.close()
        else:
            monkeypatch.setattr(os, "getpid", lambda: -1)
        relay = Relay()
        with pytest.raises(RuntimeOperationError):
            await serve_admitted_staged_read(admitted, KEY, relay)
        assert relay.closed and not relay.records and runner.diff_count == 0
    assert owner._active == 0


@pytest.mark.anyio
@pytest.mark.parametrize("at", ["queued_send", "backpressure", "ack_deadline", "uncertain"])
async def test_send_publication_fences_after_scheduling_and_backpressure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, at: str
) -> None:
    now = [100_000_000_000]
    monkeypatch.setattr(time, "monotonic_ns", lambda: now[0])
    owner, _, _, context, _ = setup(tmp_path)
    selection = await token(owner)
    entered: list[str] = []
    armed = [False]
    original_wait_for = asyncio.wait_for

    async def scheduled_wait(awaitable: Any, timeout: float) -> Any:
        if armed[0]:
            armed[0] = False
            context.current = None
        return await original_wait_for(awaitable, timeout)

    if at == "queued_send":
        monkeypatch.setattr(asyncio, "wait_for", scheduled_wait)

    class FencedRelay(Relay):
        async def send(self, raw: bytes, check_current: Callable[[], None]) -> None:
            kind = (decode_key if b'"data":' in raw else decode_record)(raw)["kind"]
            entered.append(kind)
            if kind == "A3_KEY_CONFIRM_ACK":
                if at == "backpressure":
                    await asyncio.sleep(0)
                    context.current = None
                if at == "ack_deadline":
                    now[0] += 5_000_000_000
                if at == "uncertain":
                    raise OSError("uncertain write")
            await super().send(raw, check_current)

        async def receive(self) -> bytes:
            raw = await super().receive()
            if at == "queued_send" and b'A3_KEY_CONFIRM"' in raw:
                # Runs before wait_for's new task begins the ACK send.
                armed[0] = True
            return raw

    relay = FencedRelay()
    async with owner.admit(_PROJECT, _SCOPE, selection, b"n" * 32) as admitted:
        browser = asyncio.create_task(browser_read(admitted, selection, relay))
        with pytest.raises((RuntimeOperationError, ContentError, OSError)):
            await serve_admitted_staged_read(admitted, KEY, relay)
        browser.cancel()
        with pytest.raises(asyncio.CancelledError):
            await browser
    assert relay.closed and owner._active == 0
    assert len(relay.records) == 1  # Only ATTEST; ACK never published.
    if at == "queued_send":
        assert entered == ["A3_KEY_ATTEST"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "fault", ["revoke_page", "cancel_receive", "cancel_send", "uncertain_after_insert"]
)
async def test_late_failure_closes_and_burns_nonce_across_new_channels(
    tmp_path: Path, fault: str
) -> None:
    owner, _, _, context, _ = setup(tmp_path)
    selection = await token(owner)
    blocked = asyncio.Event()
    release = asyncio.Event()

    class LateRelay(Relay):
        async def receive(self) -> bytes:
            if fault == "cancel_receive" and len(self.records) == 2:
                blocked.set()
                await release.wait()
            return await super().receive()

        async def send(self, raw: bytes, check_current: Callable[[], None]) -> None:
            if b'"kind":"PATCH_PAGE"' in raw:
                if fault in ("revoke_page", "cancel_send"):
                    blocked.set()
                    await release.wait()
                if fault == "uncertain_after_insert":
                    await super().send(raw, check_current)
                    raise OSError("delivery uncertain after insertion")
            await super().send(raw, check_current)

        def close(self) -> None:
            super().close()
            release.set()

    relay = LateRelay()
    async with owner.admit(_PROJECT, _SCOPE, selection, b"n" * 32) as admitted:
        browser = asyncio.create_task(browser_read(admitted, selection, relay))
        server = asyncio.create_task(serve_admitted_staged_read(admitted, KEY, relay))
        if fault != "uncertain_after_insert":
            await asyncio.wait_for(blocked.wait(), 2)
            if fault == "revoke_page":
                saved = context.current
                context.current = None
                release.set()
            else:
                server.cancel()
        with pytest.raises((asyncio.CancelledError, RuntimeOperationError, ContentError, OSError)):
            await server
        browser.cancel()
        with pytest.raises(asyncio.CancelledError):
            await browser
    assert relay.closed and owner._active == 0
    assert not any(b'"kind":"PATCH_END"' in raw for raw in relay.records)
    if fault == "revoke_page":
        context.current = saved
    with pytest.raises(RuntimeOperationError) as error:
        async with owner.admit(_PROJECT, _SCOPE, selection, b"n" * 32):
            pytest.fail("failed channel replay reopened")
    assert error.value.code == "PATCH_STALE"


@pytest.mark.anyio
async def test_close_during_reader_await_stops_second_patch(tmp_path: Path) -> None:
    owner, _, runner, _, _ = setup(tmp_path)
    selection = await token(owner)
    async with owner.admit(_PROJECT, _SCOPE, selection, b"n" * 32) as admitted:
        runner.after_first_diff = admitted.close
        with pytest.raises(RuntimeOperationError):
            await admitted.read()
    assert runner.diff_count == 1 and owner._active == 0
