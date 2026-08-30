from __future__ import annotations

import asyncio
from typing import Any

import pytest
from agentbox_api.waw_binding import WAWRuntimeBindCoordinator
from agentbox_api.waw_control_client import WAWControlClientError


def _response() -> dict[str, Any]:
    return {
        "protocol_version": 1,
        "request_id": "wreq_" + "1" * 32,
        "status": "BOUND",
        "api_authority_epoch": "7",
        "runtime_epoch": "9",
        "runtime_host_installation_id": "wri_" + "2" * 32,
        "runtime_host_installation_revision": "3",
        "host_manifest_digest": "a" * 64,
        "project_root_manifest_digest": "b" * 64,
        "enrollment_epoch": "1",
        "enrollment_state": "steady",
    }


class FakeClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def request(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"action": action, **request})
        await asyncio.sleep(0)
        return dict(self.response)


class RestartingClient(FakeClient):
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        super().__init__(responses[0])
        self.responses = responses
        self.reconnects = 0

    async def request(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"action": action, **request})
        response = self.responses.pop(0)
        await asyncio.sleep(0)
        return dict(response)

    async def reconnect(self) -> None:
        self.reconnects += 1


def _coordinator(client: FakeClient) -> WAWRuntimeBindCoordinator:
    return WAWRuntimeBindCoordinator(
        client,
        api_authority_epoch="7",
        authority_nonce="c" * 32,
        expected_runtime_host_installation_id="wri_" + "2" * 32,
        expected_runtime_host_installation_revision="3",
        expected_host_manifest_digest="a" * 64,
        expected_project_root_manifest_digest="b" * 64,
        expected_runtime_epoch="9",
        request_id_factory=lambda: "wreq_" + "1" * 32,
    )


@pytest.mark.anyio
async def test_bind_is_serialized_and_idempotent() -> None:
    client = FakeClient(_response())
    coordinator = _coordinator(client)
    results = await asyncio.gather(coordinator.bind(), coordinator.bind())
    assert results[0] == results[1] == _response()
    assert len(client.calls) == 1
    assert coordinator.bound is True


@pytest.mark.anyio
async def test_failed_attestation_does_not_mark_bound() -> None:
    response = _response()
    response["runtime_epoch"] = "8"
    client = FakeClient(response)
    coordinator = _coordinator(client)
    with pytest.raises(WAWControlClientError) as raised:
        await coordinator.bind()
    assert raised.value.code == "RUNTIME_INSTALLATION_MISMATCH"
    assert coordinator.bound is False


@pytest.mark.anyio
async def test_lifecycle_request_allows_only_read_only_actions() -> None:
    client = FakeClient(_response())
    coordinator = _coordinator(client)
    request = {
        "protocol_version": 1,
        "request_id": "wreq_" + "2" * 32,
        "action": "workspace.workspace.status",
    }
    response = await coordinator.request_lifecycle("workspace.workspace.status", request)
    assert response == _response()
    assert [call["action"] for call in client.calls] == [
        "workspace.api_authority.bind",
        "workspace.workspace.status",
    ]
    with pytest.raises(WAWControlClientError) as raised:
        await coordinator.request_lifecycle("workspace.workspace.start", request)
    assert raised.value.code == "PROTOCOL_INVALID"
    assert len(client.calls) == 2


@pytest.mark.anyio
async def test_lifecycle_request_rejects_a_new_runtime_epoch() -> None:
    response = _response()
    response["runtime_epoch"] = "8"
    client = FakeClient(response)
    coordinator = _coordinator(client)
    with pytest.raises(WAWControlClientError) as raised:
        await coordinator.request_lifecycle(
            "workspace.workspace.status",
            {
                "protocol_version": 1,
                "request_id": "wreq_" + "2" * 32,
                "action": "workspace.workspace.status",
            },
        )
    assert raised.value.code == "RUNTIME_INSTALLATION_MISMATCH"


@pytest.mark.anyio
async def test_runtime_only_restart_invalidates_binding_and_allows_rebind() -> None:
    stale = _response()
    stale["runtime_epoch"] = "8"
    client = RestartingClient([stale, _response(), _response()])
    coordinator = _coordinator(client)
    with pytest.raises(WAWControlClientError) as raised:
        await coordinator.request_lifecycle(
            "workspace.workspace.status",
            {
                "protocol_version": 1,
                "request_id": "wreq_" + "2" * 32,
                "action": "workspace.workspace.status",
            },
        )
    assert raised.value.code == "RUNTIME_INSTALLATION_MISMATCH"
    assert coordinator.bound is False
    assert client.reconnects == 1
    assert await coordinator.bind() == _response()
    assert coordinator.bound is True
