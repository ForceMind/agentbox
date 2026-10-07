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
from agentbox_protocol.a3_content import context_digest, encode_message


@pytest.fixture
def native(tmp_path: Path, request: pytest.FixtureRequest) -> Iterator[A3NativeFixture]:
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
        tmp_path / "fixture",
        origin="https://127.0.0.1:44443",
        static_root=static,
        publication_witnesses=getattr(request, "param", False),
    )
    try:
        yield fixture
    finally:
        fixture.close()


def wait_for(
    native: A3NativeFixture,
    field: str,
    value: object,
    timeout: float = 3,
    *,
    deadline: float | None = None,
) -> dict[str, Any]:
    end = time.monotonic() + timeout if deadline is None else deadline
    while time.monotonic() < end:
        result: dict[str, Any] = native.call("runtime-status", deadline=deadline)
        if result[field] == value and (deadline is None or time.monotonic() < end):
            return result
        time.sleep(0.025 if deadline is None else min(0.025, max(0, end - time.monotonic())))
    raise AssertionError(f"native fixture {field} did not settle")


@pytest.mark.parametrize("native", [True], indirect=True)
def test_separate_process_publication_complete_retains_owner_until_session_revoke(
    native: A3NativeFixture,
) -> None:
    """Additive counterpart to the unchanged direct-native publication regression.

    This real API revokes its DB session and closes the checker/transport; the
    original unit test and guard-budget companion retain current=False coverage.
    Native COMPLETE reception is a separate witness, never inferred from END.
    """
    client, csrf = login(native)
    browser: NativeBrowser | None = None
    try:
        assert native.proof["api_pid"] != native.proof["runtime_pid"]
        assert native.proof["api_a3_runtime_imports"] == 0
        metadata = observe(client, csrf)
        browser = NativeBrowser(
            native, client, csrf, metadata, filename="modified.txt", nonce="6" * 64
        )
        assert browser.receive(deadline=time.monotonic() + 5) == b"A3RD\x01"
        assert native.call("runtime-status", deadline=time.monotonic() + 1)["active"] == 1
        browser.current(deadline=time.monotonic() + 1, challenge=bytes.fromhex("7" * 32))
        browser.send(browser.crypto.start(), deadline=time.monotonic() + 1)
        browser.send(
            browser.crypto.receive_attest(browser.record(deadline=time.monotonic() + 1)),
            deadline=time.monotonic() + 1,
        )
        browser.crypto.receive_ack(browser.record(deadline=time.monotonic() + 1))
        browser.send(
            browser.crypto.encrypt_read(
                encode_message(
                    {
                        "protocol_id": "agentbox-a3-content/v1",
                        "protocol_version": 1,
                        "context_digest": context_digest(browser.context),
                        "request_nonce": "6" * 64,
                        "kind": "PATCH_READ",
                        "selection_id": browser.selection,
                    }
                )
            ),
            deadline=time.monotonic() + 1,
        )
        patch = None
        while patch is None:
            patch = browser.crypto.receive_record(browser.record(deadline=time.monotonic() + 1))
        assert b"staged secret-canary content" in patch
        assert b"unstaged-exclusion-canary" not in patch

        complete_deadline = time.monotonic() + 1
        while True:
            evidence = native.call("publication-status", deadline=complete_deadline)
            if evidence["api"]["complete_received"] == 1:
                break
            time.sleep(min(0.005, max(0, complete_deadline - time.monotonic())))
        assert time.monotonic() < complete_deadline
        after = native.call("runtime-status", deadline=time.monotonic() + 1)
        assert after["active"] == after["active_bundles"] == after["burned_nonces"] == 1
        api, runtime = evidence["api"], evidence["runtime"]
        assert api["a3_runtime_imports_absent"] is True
        assert api["ready_received"] == api["live_received"] == api["live_matches"] == 1
        records = browser.ack_sequence
        assert records >= 4
        assert api["records_received"] == records
        assert api["checked_received"] == api["checked_matches"] == records
        assert api["ack_received"] == api["ack_matches"] == records
        assert all(value == records for value in runtime.values())
        assert api["current_received"] >= api["current_replied"] > 0

        before = api["current_received"]
        replied_before = api["current_replied"]
        time.sleep(0.1)
        evidence = native.call("publication-status", deadline=time.monotonic() + 1)
        assert evidence["api"]["current_received"] > before
        assert evidence["api"]["current_replied"] > replied_before
        assert native.call("runtime-status", deadline=time.monotonic() + 1)["active"] == 1

        revoke_deadline = time.monotonic() + 1
        native.call("revoke", deadline=revoke_deadline)
        retired = wait_for(native, "active_bundles", 0, deadline=revoke_deadline)
        assert retired["active"] == 0 and retired["burned_nonces"] == 1
        while native.call("publication-status", deadline=revoke_deadline)["api"]["open_bundles"]:
            time.sleep(min(0.005, max(0, revoke_deadline - time.monotonic())))
        assert time.monotonic() < revoke_deadline
    finally:
        if browser is not None:
            browser.close()
        client.close()

    # Both owners verify channel/thread retirement before releasing bundle slots.
    # Child.close raises on TERM/KILL fallback; only ordinary zero exits qualify.
    assert native.api is not None and native.runtime is not None
    children = (native.api, native.runtime)
    pipes = [pipe for child in children for pipe in (child.process.stdin, child.process.stdout)]
    descriptors = [pipe.fileno() for pipe in pipes if pipe is not None]
    native.close()
    assert all(child.process.returncode == 0 for child in children)
    assert all(pipe is not None and pipe.closed for pipe in pipes)
    for fd in descriptors:
        with pytest.raises(OSError):
            os.fstat(fd)


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
