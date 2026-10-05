"""Separate exec processes, real SO_PEERCRED/pidfd/Git/Noise/END software evidence.

Temporary UDS listeners only. These tests do not qualify installed host services,
real accounts, physical browsers, production key custody or support readiness.
"""

from __future__ import annotations

import os
import socket
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from a3_native_client import NativeBrowser, login, observe
from a3_native_fixture import PROJECT_ID, A3NativeFixture


@pytest.fixture
def native(tmp_path: Path) -> Iterator[A3NativeFixture]:
    if not hasattr(os, "pidfd_open") or not hasattr(socket, "SO_PEERCRED"):
        pytest.skip("Linux native process identities required")
    probe = None
    try:
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.bind(str(tmp_path / "probe.sock"))
    except PermissionError:
        if os.environ.get("CI"):
            raise
        pytest.skip("execution environment blocks temporary AF_UNIX bind")
    finally:
        if probe is not None:
            probe.close()
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("synthetic static isolation probe")
    fixture = A3NativeFixture(
        tmp_path / "fixture", origin="https://127.0.0.1:44443", static_root=static
    )
    try:
        yield fixture
    finally:
        fixture.close()


def wait_for(
    native: A3NativeFixture, field: str, value: object, timeout: float = 3
) -> dict[str, Any]:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result: dict[str, Any] = native.call("runtime-status")
        if result[field] == value:
            return result
        time.sleep(0.025)
    raise AssertionError(f"native fixture {field} did not settle")


def test_real_separate_process_metadata_crypto_end_retains_original_owner(
    native: A3NativeFixture,
) -> None:
    client, csrf = login(native)
    try:
        assert native.proof["api_pid"] != native.proof["runtime_pid"]
        assert native.proof["api_a3_runtime_imports"] == 0
        metadata = observe(client, csrf)
        before = native.call("status")
        assert before["diff_count"] == 0 and before["burned_nonces"] == 0
        browser = NativeBrowser(native, client, csrf, metadata)
        try:
            patch = browser.complete()
            assert b"A3 native complete diff" in patch
            assert b"unstaged-exclusion-canary" not in patch
            assert len(patch) > 24000
            after = native.call("status")
            assert after["active"] == 1 and after["active_bundles"] == 1
            assert after["burned_nonces"] == 1 and after["bundles"] == 2
            assert after["observed_api_pids"] == [native.proof["api_pid"]]
            assert after["diff_count"] > 0
            # END did not close the channel/slot: a fresh held-handle check works.
            time.sleep(0.26)
            browser.current()
        finally:
            browser.close()
        assert wait_for(native, "active", 0)["burned_nonces"] == 1
    finally:
        client.close()


@pytest.mark.parametrize(
    "change", ["revoke", "auth-epoch", "project", "epoch", "peer", "lifecycle"]
)
def test_completed_end_is_fenced_by_exact_currentness_loss(
    native: A3NativeFixture, change: str
) -> None:
    client, csrf = login(native)
    browser = NativeBrowser(native, client, csrf, observe(client, csrf))
    try:
        browser.complete()
        native.call(change)
        assert wait_for(native, "active", 0)["burned_nonces"] == 1
        with pytest.raises((EOFError, ConnectionError, OSError)):
            browser.receive()
    finally:
        browser.close()
        client.close()


@pytest.mark.parametrize("operation", ["pause-api", "exit-api"])
def test_api_pause_or_exit_cleans_runtime_without_releasing_nonce(
    native: A3NativeFixture, operation: str
) -> None:
    client, csrf = login(native)
    browser = NativeBrowser(native, client, csrf, observe(client, csrf))
    try:
        browser.complete()
        native.call(operation)
        state = wait_for(native, "active", 0, timeout=2)
        assert state["burned_nonces"] == 1
    finally:
        if operation == "pause-api":
            native.call("resume-api")
        browser.close()
        client.close()


def test_end_requires_browser_ack_and_cancellation_never_replays_nonce(
    native: A3NativeFixture,
) -> None:
    client, csrf = login(native)
    metadata = observe(client, csrf)
    browser = NativeBrowser(native, client, csrf, metadata)
    nonce = browser.nonce
    try:
        browser.handshake()
        complete = None
        while complete is None:
            raw = browser.record(ack=False)
            complete = browser.crypto.receive_record(raw)
            if complete is None:
                browser.ack(raw)
        assert native.call("runtime-status")["active"] == 1
        browser.close()
        wait_for(native, "active", 0)
        replay = NativeBrowser(native, client, csrf, metadata, nonce=nonce)
        try:
            try:
                error = replay.receive()
                assert error.startswith(b"A3ER\x01")
            except EOFError:
                pass
        finally:
            replay.close()
        assert native.call("runtime-status")["burned_nonces"] == 1
    finally:
        browser.close()
        client.close()


def test_original_selector_deadline_is_not_renewed_by_currentness(native: A3NativeFixture) -> None:
    client, csrf = login(native)
    observed_at = time.monotonic()
    browser = NativeBrowser(native, client, csrf, observe(client, csrf))
    try:
        browser.complete()
        successful = 0
        while time.monotonic() - observed_at < 32:
            time.sleep(0.26)
            try:
                browser.current()
                successful += 1
            except (EOFError, ConnectionError, OSError):
                break
        assert successful > 1
        assert time.monotonic() - observed_at < 31.5
        wait_for(native, "active", 0)
    finally:
        browser.close()
        client.close()


@pytest.mark.parametrize(
    "name,code", [("binary.bin", b"PATCH_UNAVAILABLE_BINARY"), ("large.txt", b"PATCH_TOO_LARGE")]
)
def test_native_preflight_errors_have_only_fixed_code(
    native: A3NativeFixture, name: str, code: bytes
) -> None:
    client, csrf = login(native)
    browser = NativeBrowser(native, client, csrf, observe(client, csrf), filename=name)
    try:
        assert browser.receive() == b"A3ER\x01" + code
        wait_for(native, "active", 0)
    finally:
        browser.close()
        client.close()


def test_staged_metadata_rejects_nonempty_body_and_never_reads_patch(
    native: A3NativeFixture,
) -> None:
    client, csrf = login(native)
    try:
        response = client.post(
            f"/api/v1/projects/{PROJECT_ID}/git/staged-observation",
            headers={"X-CSRF-Token": csrf},
            json={},
        )
        assert response.status_code >= 400
        assert native.call("status")["diff_count"] == 0
    finally:
        client.close()
