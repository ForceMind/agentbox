from __future__ import annotations

import asyncio
import grp
import os
import pwd
import signal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from agentbox_runtime import waw_production as subject
from agentbox_runtime.models import ClaudeSessionState, CodexStatus, RemoteState
from agentbox_runtime.waw_conflicts import WAWLegacyClaudeState, WAWLegacyCodexState
from agentbox_runtime.waw_runtime_profile import WAWRuntimeMode


class _Codex:
    def __init__(self, state: RemoteState, confidence: str = "reported") -> None:
        self.state = state
        self.confidence = confidence

    async def status(self) -> CodexStatus:
        return CodexStatus(
            installed=True,
            version="test",
            selected_executable="/test/codex",
            remote_state=self.state,
            remote_confidence=self.confidence,
        )


class _Claude:
    async def session(self, key: str) -> Any:
        assert key == "project-key"
        return SimpleNamespace(state=ClaudeSessionState.STOPPED)


class _Executor:
    def __init__(self) -> None:
        self.key: str | None = "project-key"

    def relative_key_for_formal_project(self, project_id: str) -> str | None:
        assert project_id == "formal-project"
        return self.key


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("state", "confidence", "expected"),
    [
        (RemoteState.STOPPED, "reported", WAWLegacyCodexState.STOPPED),
        (RemoteState.STOPPED, "inferred", WAWLegacyCodexState.UNKNOWN),
        (RemoteState.UNKNOWN, "unknown", WAWLegacyCodexState.UNKNOWN),
        (RemoteState.RUNNING, "inferred", WAWLegacyCodexState.RUNNING),
        (RemoteState.BROKEN, "reported", WAWLegacyCodexState.BROKEN),
    ],
)
async def test_codex_conflict_requires_positive_stopped_evidence(
    state: RemoteState, confidence: str, expected: WAWLegacyCodexState
) -> None:
    probe = subject._ProductionConflictProbe(
        cast(Any, _Codex(state, confidence)), cast(Any, _Claude())
    )
    assert await asyncio.to_thread(probe.legacy_codex_remote) is expected


@pytest.mark.anyio
async def test_conflict_probe_refuses_event_loop_thread_without_leaking_coroutine() -> None:
    probe = subject._ProductionConflictProbe(
        cast(Any, _Codex(RemoteState.UNKNOWN)), cast(Any, _Claude())
    )
    with pytest.raises(RuntimeError, match="start worker"):
        probe.legacy_codex_remote()


@pytest.mark.anyio
async def test_claude_conflict_rechecks_binding_after_observation() -> None:
    executor = _Executor()

    class ChangingClaude(_Claude):
        async def session(self, key: str) -> Any:
            result = await super().session(key)
            executor.key = None
            return result

    probe = subject._ProductionConflictProbe(
        cast(Any, _Codex(RemoteState.UNKNOWN)), cast(Any, ChangingClaude())
    )
    assert (
        await asyncio.to_thread(probe.legacy_claude, "formal-project")
        is WAWLegacyClaudeState.UNKNOWN
    )
    probe.bind(cast(Any, executor))
    assert (
        await asyncio.to_thread(probe.legacy_claude, "formal-project")
        is WAWLegacyClaudeState.UNKNOWN
    )
    with pytest.raises(RuntimeError, match="already bound"):
        probe.bind(cast(Any, executor))


@pytest.mark.anyio
async def test_claude_stopped_observation_uses_formal_binding() -> None:
    probe = subject._ProductionConflictProbe(
        cast(Any, _Codex(RemoteState.UNKNOWN)), cast(Any, _Claude())
    )
    probe.bind(cast(Any, _Executor()))
    assert (
        await asyncio.to_thread(probe.legacy_claude, "formal-project")
        is WAWLegacyClaudeState.STOPPED
    )


class _Application:
    def __init__(self, *, fail_start: bool = False, fail_serve: bool = False) -> None:
        self.entered = asyncio.Event()
        self.closed = False
        self.fail_start = fail_start
        self.fail_serve = fail_serve

    async def start(self) -> None:
        if self.fail_start:
            raise RuntimeError("start failure")

    async def serve_forever(self) -> None:
        self.entered.set()
        if self.fail_serve:
            raise RuntimeError("serve failure")
        await asyncio.Event().wait()

    async def close(self) -> None:
        self.closed = True


def _signals(monkeypatch: pytest.MonkeyPatch) -> dict[signal.Signals, Any]:
    loop = asyncio.get_running_loop()
    handlers: dict[signal.Signals, Any] = {}
    monkeypatch.setattr(
        loop, "add_signal_handler", lambda number, callback: handlers.__setitem__(number, callback)
    )
    monkeypatch.setattr(loop, "remove_signal_handler", lambda number: handlers.pop(number, None))
    return handlers


@pytest.mark.anyio
async def test_systemd_termination_closes_application_and_removes_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handlers = _signals(monkeypatch)
    application = _Application()
    operation = asyncio.create_task(subject._serve_application(cast(Any, application)))
    await asyncio.wait_for(application.entered.wait(), timeout=1)
    handlers[signal.SIGTERM]()
    await asyncio.wait_for(operation, timeout=1)
    assert application.closed
    assert not handlers


@pytest.mark.anyio
@pytest.mark.parametrize("stage", ["start", "serve"])
async def test_application_failure_propagates_after_cleanup(
    stage: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    handlers = _signals(monkeypatch)
    application = _Application(fail_start=stage == "start", fail_serve=stage == "serve")
    with pytest.raises(RuntimeError, match=f"{stage} failure"):
        await subject._serve_application(cast(Any, application))
    assert application.closed
    assert not handlers


@pytest.mark.anyio
async def test_application_cancellation_closes_application(monkeypatch: pytest.MonkeyPatch) -> None:
    handlers = _signals(monkeypatch)
    application = _Application()
    operation = asyncio.create_task(subject._serve_application(cast(Any, application)))
    await asyncio.wait_for(application.entered.wait(), timeout=1)
    operation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert application.closed
    assert not handlers


class _Handle:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> bool:
        self.closed = True
        return True


@pytest.mark.anyio
@pytest.mark.parametrize("failure", [None, "identity", "key", "sockets", "builder", "profile"])
async def test_production_entry_pins_resources_and_cleans_failure(
    failure: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pathlib import Path

    monkeypatch.setenv("INVOCATION_ID", "1" * 32)

    runtime_uid, runtime_gid, control_uid, control_gid, ipc_gid = 19002, 19002, 19001, 19001, 19003
    accounts = {
        "agentbox-runtime": SimpleNamespace(pw_uid=runtime_uid, pw_gid=runtime_gid),
        "agentbox": SimpleNamespace(pw_uid=control_uid, pw_gid=control_gid),
    }
    groups = {
        "agentbox-runtime": runtime_gid,
        "agentbox": control_gid,
        "agentbox-runtime-ipc": ipc_gid,
    }
    monkeypatch.setattr(pwd, "getpwnam", accounts.__getitem__)
    monkeypatch.setattr(grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=groups[name]))
    monkeypatch.setattr(os, "getresuid", lambda: (runtime_uid,) * 3, raising=False)
    monkeypatch.setattr(os, "getresgid", lambda: (runtime_gid,) * 3, raising=False)
    profile = SimpleNamespace(mode=WAWRuntimeMode.FILESYSTEM_V2)
    key, provider, sockets = _Handle(), _Handle(), _Handle()
    application = _Application()
    application.executor = cast(Any, _Executor())  # type: ignore[attr-defined]
    built: list[dict[str, Any]] = []
    revalidated = 0

    def revalidate(observed: Any) -> None:
        nonlocal revalidated
        assert observed is profile
        revalidated += 1
        if failure == "profile" and revalidated == 2:
            raise RuntimeError("profile drift")

    monkeypatch.setattr(subject, "revalidate_waw_runtime_profile", revalidate)
    monkeypatch.setattr(subject, "load_waw_vendor_enrollment", lambda: "enrollment")

    def build_provider(**kwargs: Any) -> _Handle:
        assert kwargs["enrollment"] == "enrollment"
        assert kwargs["geometry"].columns == 80
        assert kwargs["geometry"].rows == 24
        assert kwargs["attachment_validator"](object()) is False
        return provider

    monkeypatch.setattr(subject, "build_waw_deferred_production_executor_provider", build_provider)

    def open_key() -> _Handle:
        if failure == "key":
            raise RuntimeError("key failure")
        return key

    def activate(**kwargs: Any) -> _Handle:
        assert kwargs == {"expected_uid": runtime_uid, "expected_gid": ipc_gid}
        if failure == "sockets":
            raise RuntimeError("sockets failure")
        return sockets

    monkeypatch.setattr(subject, "_open_waw_runtime_static_key", open_key)
    monkeypatch.setattr(subject, "load_waw_activated_sockets", activate)

    async def build(**kwargs: Any) -> Any:
        built.append(kwargs)
        if failure == "builder":
            raise RuntimeError("builder failure")
        return application

    async def serve(observed: Any) -> None:
        assert observed is application

    monkeypatch.setattr(subject, "build_waw_runtime_application_from_filesystem_v2", build)
    monkeypatch.setattr(subject, "_serve_application", serve)
    operation = subject.run_waw_production(
        socket_path=Path("/run/agentbox/runtime.sock"),
        codex_manager=cast(Any, _Codex(RemoteState.UNKNOWN)),
        claude_manager=cast(Any, _Claude()),
        projects=cast(Any, object()),
        project_manager=cast(Any, object()),
        allowed_uids=frozenset({0 if failure == "identity" else control_uid}),
        allowed_gids=frozenset({control_gid}),
        profile=cast(Any, profile),
    )
    if failure:
        with pytest.raises(RuntimeError):
            await operation
    else:
        await operation

    if failure == "identity":
        assert not built and revalidated == 0
    elif failure == "key":
        assert provider.closed and not built
    elif failure == "sockets":
        assert key.closed and provider.closed and not built
    elif failure == "builder":
        assert key.closed and provider.closed and sockets.closed
    else:
        assert application.closed
        assert len(built) == 1
        kwargs = built[0]
        assert kwargs["runtime_manifest_path"] == Path(
            "/var/lib/agentbox-waw/runtime-host-installation.v2.json"
        )
        assert kwargs["public_directory"] == Path("/usr/share/agentbox/waw")
        assert kwargs["expected_runtime_gid"] == runtime_gid
        assert kwargs["waw_control_peer_uid"] == control_uid
        assert kwargs["waw_control_peer_gid"] == control_gid
        assert kwargs["executor_provider"] is provider
        assert kwargs["key_port"] is key
        assert kwargs["activated_sockets"] is sockets
        assert kwargs["attestation_store"]._directory == Path("/var/lib/agentbox-waw/workspaces-v1")
        assert kwargs["cgroup_attestation_store"]._directory == Path(
            "/var/lib/agentbox-waw/cgroups-v1"
        )
        assert kwargs["cgroup_attestation_factory"]._store is kwargs["cgroup_attestation_store"]
