from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from agentbox_core.waw import AgentType, workspace_id
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_process_inspector import (
    FixedLaunchHandles,
    FixedLaunchRequest,
    FixedProcessBinding,
    FixedProcessIdentity,
    FixedStartProof,
    FixedStartState,
    WAWProcessInspector,
)
from agentbox_runtime.waw_pty import PtyGeometry
from agentbox_runtime.waw_supervisor import (
    RuntimeProbeEvidence,
    RuntimeProbeState,
    RuntimeStopEvidence,
)

PROJECT = "prj_" + "2" * 32
WORKSPACE = workspace_id(PROJECT, AgentType.CODEX)
HOST = "wri_" + "3" * 32
MARKER = f"waw-v1:{HOST}:" + "4" * 32


def identity(epoch: str = "2") -> FixedProcessIdentity:
    return FixedProcessIdentity(
        WORKSPACE,
        PROJECT,
        AgentType.CODEX,
        7,
        "d" * 64,
        MARKER,
        "a" * 64,
        HOST,
        "5",
        epoch,
    )


def handles() -> FixedLaunchHandles:
    return FixedLaunchHandles(*(object() for _ in range(8)))


def binding(item: FixedProcessIdentity | None = None) -> FixedProcessBinding:
    return FixedProcessBinding(item or identity(), object(), object(), object())


class FakePort:
    def __init__(self) -> None:
        self.stop_calls = 0
        self.destroy_calls = 0
        self.probe_calls = 0
        self.probe_evidence = RuntimeProbeEvidence(WORKSPACE, 7, MARKER, RuntimeProbeState.RUNNING)

    def start(self, request: FixedLaunchRequest) -> FixedStartProof:
        return FixedStartProof(request, FixedStartState.RUNNING, binding(request.identity), 1)

    def open_attachment(self, request: Any) -> Any:
        raise AssertionError("unused")

    def probe(self, process: FixedProcessBinding) -> RuntimeProbeEvidence:
        self.probe_calls += 1
        assert process.identity.workspace_id == WORKSPACE
        return self.probe_evidence

    def stop(self, process: FixedProcessBinding) -> RuntimeStopEvidence:
        self.stop_calls += 1
        return RuntimeStopEvidence(WORKSPACE, 7, MARKER, True, 0)

    def destroy_fenced(self, process: FixedProcessBinding) -> RuntimeStopEvidence:
        self.destroy_calls += 1
        return RuntimeStopEvidence(WORKSPACE, 7, MARKER, True, 0)


def test_login_required_proves_no_process_and_stop_has_no_os_effect() -> None:
    port = FakePort()
    inspector = WAWProcessInspector(identity(), port)
    request = FixedLaunchRequest(identity(), handles(), PtyGeometry(80, 24))
    proof = FixedStartProof(request, FixedStartState.LOGIN_REQUIRED, None, 0)
    inspector.accept_start(proof, request)

    assert inspector.probe().state is RuntimeProbeState.LOGIN_REQUIRED
    stopped = inspector.stop()
    assert stopped.closed and stopped.remaining_members == 0
    assert port.stop_calls == 0


def test_running_binding_requires_exact_probe_and_populated_zero_stop() -> None:
    port = FakePort()
    item = identity()
    inspector = WAWProcessInspector(item, port)
    request = FixedLaunchRequest(item, handles(), PtyGeometry(80, 24))
    inspector.accept_start(port.start(request), request)
    assert inspector.probe().state is RuntimeProbeState.RUNNING

    port.probe_evidence = replace(port.probe_evidence, generation=8)
    with pytest.raises(RuntimeOperationError, match="not exact"):
        inspector.probe()

    port.probe_evidence = replace(port.probe_evidence, generation=7)
    stopped = inspector.stop()
    assert stopped.remaining_members == 0
    assert port.stop_calls == 1


def test_start_proof_must_echo_the_exact_request_object() -> None:
    port = FakePort()
    item = identity()
    inspector = WAWProcessInspector(item, port)
    request = FixedLaunchRequest(item, handles(), PtyGeometry(80, 24))
    copied = FixedLaunchRequest(item, request.handles, request.initial_geometry)
    proof = FixedStartProof(copied, FixedStartState.RUNNING, binding(item), 1)
    with pytest.raises(RuntimeOperationError, match="not exact"):
        inspector.accept_start(proof, request)


def test_restart_never_adopts_and_destroy_requires_authenticated_old_binding() -> None:
    port = FakePort()
    inspector = WAWProcessInspector(identity(), port)
    inspector.quarantine_restart(None)
    assert inspector.fenced
    with pytest.raises(RuntimeOperationError, match="authenticated native handle"):
        inspector.destroy_fenced()
    assert port.destroy_calls == 0

    old = binding(identity("1"))
    inspector.quarantine_restart(old)
    assert inspector.fenced
    assert inspector.probe().state is RuntimeProbeState.UNKNOWN
    assert port.probe_calls == 0
    with pytest.raises(RuntimeOperationError, match="fenced destroy"):
        inspector.stop()
    assert inspector.destroy_fenced().remaining_members == 0
    assert port.destroy_calls == 1


def test_fenced_destroy_keeps_quarantine_on_unpopulated_failure() -> None:
    port = FakePort()
    item = identity("1")
    inspector = WAWProcessInspector(identity("2"), port)
    old = binding(item)
    inspector.quarantine_restart(old)

    def incomplete(_binding: FixedProcessBinding) -> RuntimeStopEvidence:
        return RuntimeStopEvidence(WORKSPACE, 7, MARKER, True, 1)

    port.destroy_fenced = incomplete  # type: ignore[assignment]
    with pytest.raises(RuntimeOperationError, match="populated=0"):
        inspector.destroy_fenced()
    assert inspector.fenced


@pytest.mark.parametrize("state", list(FixedStartState))
def test_start_proof_process_presence_is_closed(state: FixedStartState) -> None:
    request = FixedLaunchRequest(identity(), handles(), PtyGeometry(80, 24))
    if state is FixedStartState.LOGIN_REQUIRED:
        with pytest.raises(ValueError, match="no process"):
            FixedStartProof(request, state, binding(), 1)
    else:
        with pytest.raises(ValueError, match="lacks"):
            FixedStartProof(request, state, None, 0)
