from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Any

import pytest
from agentbox_api.waw_binding import WAWRuntimeBindCoordinator
from agentbox_api.waw_control_client import WAWControlClient
from agentbox_runtime.waw_activation import WAWActivatedSockets
from agentbox_runtime.waw_bootstrap import (
    build_waw_control_server,
    create_waw_lifecycle_registry,
)
from agentbox_runtime.waw_epoch import WAWRuntimeEpochStore
from agentbox_runtime.waw_host_manifest import WAWRuntimeHostManifest
from agentbox_runtime.waw_lifecycle import (
    WAWLifecycleIdentity,
    WAWLifecycleObservation,
)

HOST = "wri_" + "1" * 32
PROJECT = "prj_" + "2" * 32
WORKSPACE = "aws_" + "3" * 32
DIGEST = "a" * 64


class FakeExecutor:
    def __init__(self, runtime_epoch: str) -> None:
        self.runtime_epoch = runtime_epoch
        self.calls: list[str] = []

    async def start(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        del identity
        self.calls.append("start")
        return WAWLifecycleObservation(state="RUNNING", runtime_epoch=self.runtime_epoch)

    async def stop(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        del identity
        self.calls.append("stop")
        return WAWLifecycleObservation(
            state="STOPPED", process_state="STOPPED", runtime_epoch=self.runtime_epoch
        )

    async def status(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        del identity
        self.calls.append("status")
        return WAWLifecycleObservation(state="RUNNING", runtime_epoch=self.runtime_epoch)

    async def reconcile(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        del identity
        self.calls.append("reconcile")
        return WAWLifecycleObservation(state="RUNNING", runtime_epoch=self.runtime_epoch)


def _listen(path: Path) -> socket.socket:
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen(8)
    listener.set_inheritable(False)
    path.chmod(0o660)
    return listener


def _manifest() -> WAWRuntimeHostManifest:
    return WAWRuntimeHostManifest(
        runtime_host_installation_id=HOST,
        runtime_host_installation_revision="1",
        host_manifest_digest="b" * 64,
        project_root_manifest_digest="c" * 64,
        enrollment_epoch="1",
        enrollment_state="steady",
    )


def _request(action: str, request_id: str, **fields: str | None) -> dict[str, Any]:
    value: dict[str, Any] = {
        "protocol_version": 1,
        "request_id": request_id,
        "action": action,
    }
    value.update(fields)
    return value


@pytest.mark.anyio
async def test_prebound_runtime_control_round_trip_uses_consumed_epoch(tmp_path: Path) -> None:
    epoch_dir = tmp_path / "epoch"
    epoch_dir.mkdir(mode=0o700)
    store = WAWRuntimeEpochStore(
        epoch_dir,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )
    assert store.bootstrap() == 1
    executors: list[FakeExecutor] = []

    def executor_factory(epoch: str) -> FakeExecutor:
        value = FakeExecutor(epoch)
        executors.append(value)
        return value

    registry, consumed = create_waw_lifecycle_registry(
        manifest=_manifest(),
        epoch_store=store,
        executor_factory=executor_factory,
        binding_digest_factory=lambda _request: DIGEST,
    )
    assert consumed == "2"

    control_socket = _listen(tmp_path / "control.sock")
    stream_socket = _listen(tmp_path / "stream.sock")
    sockets = WAWActivatedSockets(control=control_socket, stream=stream_socket)
    server = build_waw_control_server(
        sockets=sockets,
        registry=registry,
        expected_peer_uid=os.geteuid(),
        expected_peer_gid=os.getegid(),
    )
    await server.start()
    try:
        client = WAWControlClient(
            tmp_path / "control.sock",
            expected_peer_uid=os.geteuid(),
            expected_peer_gid=os.getegid(),
            expected_socket_uid=os.geteuid(),
            expected_socket_gid=os.getegid(),
        )
        coordinator = WAWRuntimeBindCoordinator(
            client,
            api_authority_epoch="7",
            authority_nonce="d" * 32,
            expected_runtime_host_installation_id=HOST,
            expected_runtime_host_installation_revision="1",
            expected_host_manifest_digest="b" * 64,
            expected_project_root_manifest_digest="c" * 64,
            expected_runtime_epoch="2",
            request_id_factory=lambda: "wreq_" + "1" * 32,
        )
        attestation = await coordinator.bind()
        assert attestation["runtime_epoch"] == "2"

        register = _request(
            "workspace.project_binding.register",
            "wreq_" + "2" * 32,
            project_id=PROJECT,
            relative_key="project-a",
            project_revision="1",
            binding_revision="1",
            previous_binding_revision=None,
            previous_binding_digest=None,
            schema_version="waw-project-binding-v1",
            runtime_host_installation_id=HOST,
            runtime_host_installation_revision="1",
        )
        registered = await client.request("workspace.project_binding.register", register)
        assert registered["binding_digest"] == DIGEST

        lifecycle_fields = {
            "workspace_id": WORKSPACE,
            "project_id": PROJECT,
            "agent_type": "claude",
            "generation": "1",
            "binding_revision": "1",
            "binding_digest": DIGEST,
            "runtime_host_installation_id": HOST,
            "runtime_host_installation_revision": "1",
        }
        started = await client.request(
            "workspace.workspace.start",
            _request("workspace.workspace.start", "wreq_" + "3" * 32, **lifecycle_fields),
        )
        assert started["state"] == "RUNNING"
        status = await coordinator.request_lifecycle(
            "workspace.workspace.status",
            _request("workspace.workspace.status", "wreq_" + "4" * 32, **lifecycle_fields),
        )
        assert status["runtime_epoch"] == "2"
        assert status["attachment_capacity"] == {"admitted": "0", "pending": "0", "limit": "32"}
        assert executors[0].calls == ["start", "status"]
        assert "terminal" not in status
        assert "ticket" not in status
    finally:
        await server.close()
        sockets.close()
