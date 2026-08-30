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
