from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import agentbox_api.waw_control_client as control_subject
import pytest
from agentbox_api.waw_binding import WAWRuntimeBindCoordinator
from agentbox_api.waw_control_client import (
    BoundRuntimePeer,
    RuntimeBindExchange,
    WAWControlClient,
    WAWControlClientError,
    WAWSocketPathIdentity,
)


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
        self.closes = 0

    async def request(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"action": action, **request})
        await asyncio.sleep(0)
        return dict(self.response)

    async def close(self) -> None:
        self.closes += 1


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


class TransportFailureClient(FakeClient):
    def __init__(self) -> None:
        super().__init__(_response())
        self.fail_lifecycle = True
        self.reconnects = 0

    async def request(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"action": action, **request})
        if action == "workspace.workspace.status" and self.fail_lifecycle:
            self.fail_lifecycle = False
            raise WAWControlClientError("RUNTIME_UNAVAILABLE", "transport lost", retryable=True)
        await asyncio.sleep(0)
        return dict(self.response)

    async def reconnect(self) -> None:
        self.reconnects += 1


class EpochClassifier:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, int, str]] = []

    def classify_runtime_epoch(
        self,
        *,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: int,
        observed_runtime_epoch: str,
    ) -> object:
        self.calls.append(
            (
                runtime_host_installation_id,
                runtime_host_installation_revision,
                observed_runtime_epoch,
            )
        )
        if self.error is not None:
            raise self.error
        return "api_restart"


def _coordinator(
    client: FakeClient, *, classifier: EpochClassifier | None = None
) -> WAWRuntimeBindCoordinator:
    return WAWRuntimeBindCoordinator.test_only(
        client,
        api_authority_epoch="7",
        authority_nonce="c" * 32,
        expected_runtime_host_installation_id="wri_" + "2" * 32,
        expected_runtime_host_installation_revision="3",
        expected_host_manifest_digest="a" * 64,
        expected_project_root_manifest_digest="b" * 64,
        expected_runtime_epoch="9",
        request_id_factory=lambda: "wreq_" + "1" * 32,
        runtime_epoch_classifier=classifier,
    )


def _production_exchange(
    client: WAWControlClient,
) -> tuple[RuntimeBindExchange, BoundRuntimePeer, int]:
    retained, writer = os.pipe()
    candidate = BoundRuntimePeer(
        control_subject._RuntimePeerObservation(
            pid=9123,
            uid=os.geteuid(),
            gid=os.getegid(),
            pidfd=retained,
        ),
        WAWSocketPathIdentity(1, 2),
    )
    exchange = RuntimeBindExchange(client, _response(), candidate)
    client._pending_exchange = exchange
    return exchange, candidate, writer


def _production_coordinator(
    client: WAWControlClient,
    *,
    classifier: EpochClassifier | None = None,
) -> WAWRuntimeBindCoordinator:
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
        runtime_epoch_classifier=classifier,
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
async def test_bind_classifies_verified_runtime_epoch_before_publication() -> None:
    client = FakeClient(_response())
    classifier = EpochClassifier()
    coordinator = _coordinator(client, classifier=classifier)

    assert await coordinator.bind() == _response()
    assert classifier.calls == [("wri_" + "2" * 32, 3, "9")]
    assert coordinator.bound is True
    await coordinator.bind()
    assert len(classifier.calls) == 1


@pytest.mark.anyio
async def test_epoch_classification_failure_never_publishes_attestation() -> None:
    client = FakeClient(_response())
    classifier = EpochClassifier(error=RuntimeError("database commit failed"))
    coordinator = _coordinator(client, classifier=classifier)

    with pytest.raises(RuntimeError, match="database commit failed"):
        await coordinator.bind()

    assert classifier.calls == [("wri_" + "2" * 32, 3, "9")]
    assert coordinator.bound is False
    assert coordinator.attestation is None


@pytest.mark.anyio
async def test_production_bind_publishes_peer_only_after_epoch_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = WAWControlClient(
        Path("/unused/control.sock"),
        expected_peer_uid=os.geteuid(),
        expected_peer_gid=os.getegid(),
        expected_socket_uid=os.geteuid(),
        expected_socket_gid=os.getegid(),
    )
    exchange, candidate, writer = _production_exchange(client)
    events: list[str] = []

    class OrderedClassifier(EpochClassifier):
        def classify_runtime_epoch(self, **kwargs: Any) -> object:
            events.append("epoch-committed")
            return super().classify_runtime_epoch(**kwargs)

    classifier = OrderedClassifier()
    original_publish = exchange.publish

    def publish(**kwargs: Any) -> BoundRuntimePeer:
        events.append("peer-published")
        return original_publish(**kwargs)

    async def bind_exchange(_action: str, _request: dict[str, Any]) -> RuntimeBindExchange:
        return exchange

    monkeypatch.setattr(client, "bind_exchange", bind_exchange)
    monkeypatch.setattr(exchange, "publish", publish)
    coordinator = _production_coordinator(client, classifier=classifier)
    try:
        assert await coordinator.bind() == _response()
        assert events == ["epoch-committed", "peer-published"]
        assert coordinator.bound and candidate.current()
    finally:
        await coordinator.close()
        os.close(writer)


@pytest.mark.anyio
async def test_concrete_coordinator_replaces_retired_client_and_fences_old_borrow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = WAWControlClient(
        Path("/unused/control.sock"),
        expected_peer_uid=os.geteuid(),
        expected_peer_gid=os.getegid(),
        expected_socket_uid=os.geteuid(),
        expected_socket_gid=os.getegid(),
    )
    second = WAWControlClient(
        Path("/unused/control.sock"),
        expected_peer_uid=os.geteuid(),
        expected_peer_gid=os.getegid(),
        expected_socket_uid=os.geteuid(),
        expected_socket_gid=os.getegid(),
    )
    first_exchange, first_peer, first_writer = _production_exchange(first)
    second_exchange, second_peer, second_writer = _production_exchange(second)

    async def first_bind(_action: str, _request: dict[str, Any]) -> RuntimeBindExchange:
        return first_exchange

    async def second_bind(_action: str, _request: dict[str, Any]) -> RuntimeBindExchange:
        return second_exchange

    monkeypatch.setattr(first, "bind_exchange", first_bind)
    monkeypatch.setattr(second, "bind_exchange", second_bind)
    monkeypatch.setattr(first, "replacement_after_close", lambda: second)
    monkeypatch.setattr("agentbox_api.waw_control_client.socket.SO_PEERCRED", 17, raising=False)
    coordinator = _production_coordinator(first, classifier=EpochClassifier())

    class PeerSocket:
        def getsockopt(self, _level: int, _option: int, _size: int) -> bytes:
            import struct

            return struct.pack("3i", 9123, os.geteuid(), os.getegid())

    try:
        await coordinator.bind()
        old_borrow = coordinator.borrow_runtime_peer(PeerSocket())
        assert old_borrow.current()
        first_peer.poison()

        await coordinator.bind()

        assert first.closed and not old_borrow.current()
        assert coordinator.bound and second_peer.current()
        assert coordinator._bound_peer is second_peer
        old_borrow.close()
    finally:
        await coordinator.close()
        os.close(first_writer)
        os.close(second_writer)


@pytest.mark.anyio
async def test_concrete_close_immediately_fences_peer_and_new_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = WAWControlClient(
        Path("/unused/control.sock"),
        expected_peer_uid=os.geteuid(),
        expected_peer_gid=os.getegid(),
        expected_socket_uid=os.geteuid(),
        expected_socket_gid=os.getegid(),
    )
    exchange, peer, writer = _production_exchange(client)

    async def bind_exchange(_action: str, _request: dict[str, Any]) -> RuntimeBindExchange:
        return exchange

    monkeypatch.setattr(client, "bind_exchange", bind_exchange)
    monkeypatch.setattr("agentbox_api.waw_control_client.socket.SO_PEERCRED", 17, raising=False)
    coordinator = _production_coordinator(client, classifier=EpochClassifier())

    class PeerSocket:
        def getsockopt(self, _level: int, _option: int, _size: int) -> bytes:
            import struct

            return struct.pack("3i", 9123, os.geteuid(), os.getegid())

    entered = asyncio.Event()
    release = asyncio.Event()

    async def blocked_request(
        _action: str, _request: dict[str, Any], bound_peer: BoundRuntimePeer
    ) -> dict[str, Any]:
        entered.set()
        await release.wait()
        if not bound_peer.current():
            raise WAWControlClientError("RUNTIME_UNAVAILABLE", "peer fenced")
        return _response()

    try:
        await coordinator.bind()
        borrow = coordinator.borrow_runtime_peer(PeerSocket())
        monkeypatch.setattr(client, "request_bound", blocked_request)
        request = {
            "protocol_version": 1,
            "request_id": "wreq_" + "2" * 32,
            "action": "workspace.workspace.status",
        }
        active = asyncio.create_task(
            coordinator.request_lifecycle("workspace.workspace.status", request)
        )
        await entered.wait()

        close_wait = coordinator.close()

        assert not borrow.current()
        with pytest.raises(WAWControlClientError):
            coordinator.borrow_runtime_peer(PeerSocket())
        with pytest.raises(WAWControlClientError):
            await coordinator.bind()
        with pytest.raises(WAWControlClientError):
            await coordinator.request_lifecycle("workspace.workspace.status", request)
        release.set()
        with pytest.raises(WAWControlClientError):
            await active
        await close_wait
        borrow.close()
        assert coordinator.bound is False and client.closed
    finally:
        release.set()
        if not coordinator._closed:
            await coordinator.close()
        os.close(writer)


@pytest.mark.anyio
async def test_epoch_commit_failure_closes_unpublished_candidate_and_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = WAWControlClient(
        Path("/unused/control.sock"),
        expected_peer_uid=os.geteuid(),
        expected_peer_gid=os.getegid(),
        expected_socket_uid=os.geteuid(),
        expected_socket_gid=os.getegid(),
    )
    exchange, candidate, writer = _production_exchange(client)

    async def bind_exchange(_action: str, _request: dict[str, Any]) -> RuntimeBindExchange:
        return exchange

    monkeypatch.setattr(client, "bind_exchange", bind_exchange)
    coordinator = _production_coordinator(
        client,
        classifier=EpochClassifier(error=RuntimeError("database commit failed")),
    )
    try:
        with pytest.raises(RuntimeError, match="database commit failed"):
            await coordinator.bind()
        assert not coordinator.bound and coordinator.attestation is None
        assert client.poisoned and candidate.poisoned and not candidate.current()
        with pytest.raises(WAWControlClientError):
            exchange.publish(generation=1, owner_current=lambda _peer, _generation: True)
    finally:
        await coordinator.close()
        os.close(writer)


@pytest.mark.anyio
async def test_lifecycle_request_allows_only_typed_waw_actions() -> None:
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
    start_request = {**request, "action": "workspace.workspace.start"}
    assert (
        await coordinator.request_lifecycle("workspace.workspace.start", start_request)
        == _response()
    )
    with pytest.raises(WAWControlClientError) as raised:
        await coordinator.request_lifecycle("workspace.workspace.unknown", request)
    assert raised.value.code == "PROTOCOL_INVALID"
    assert len(client.calls) == 3


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
    assert client.reconnects == 0
    assert await coordinator.bind() == _response()
    assert coordinator.bound is True


@pytest.mark.anyio
async def test_transport_failure_invalidates_binding_before_safe_rebind() -> None:
    client = TransportFailureClient()
    coordinator = _coordinator(client)
    request = {
        "protocol_version": 1,
        "request_id": "wreq_" + "2" * 32,
        "action": "workspace.workspace.status",
    }
    with pytest.raises(WAWControlClientError) as raised:
        await coordinator.request_lifecycle("workspace.workspace.status", request)
    assert raised.value.code == "RUNTIME_UNAVAILABLE"
    assert coordinator.bound is False
    assert client.reconnects == 0
    assert await coordinator.bind() == _response()
    assert coordinator.bound is True


@pytest.mark.anyio
async def test_lifecycle_requests_are_serialized_across_rebind() -> None:
    client = FakeClient(_response())
    coordinator = _coordinator(client)
    request = {
        "protocol_version": 1,
        "request_id": "wreq_" + "2" * 32,
        "action": "workspace.workspace.status",
    }
    await asyncio.gather(
        coordinator.request_lifecycle("workspace.workspace.status", request),
        coordinator.request_lifecycle("workspace.workspace.status", request),
    )
    assert [call["action"] for call in client.calls] == [
        "workspace.api_authority.bind",
        "workspace.workspace.status",
        "workspace.workspace.status",
    ]


def test_production_constructor_rejects_metadata_only_transport() -> None:
    with pytest.raises(TypeError, match="production"):
        WAWRuntimeBindCoordinator(
            FakeClient(_response()),
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
async def test_coordinator_close_is_irreversible_and_idempotent() -> None:
    client = FakeClient(_response())
    coordinator = _coordinator(client)
    await coordinator.bind()

    await coordinator.close()
    await coordinator.close()

    assert client.closes == 1
    assert coordinator.bound is False and coordinator.attestation is None
    with pytest.raises(WAWControlClientError) as raised:
        await coordinator.bind()
    assert raised.value.code == "RUNTIME_UNAVAILABLE"


@pytest.mark.anyio
async def test_cancelled_close_keeps_one_owned_close_operation() -> None:
    class BlockingCloseClient(FakeClient):
        def __init__(self) -> None:
            super().__init__(_response())
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def close(self) -> None:
            self.closes += 1
            self.entered.set()
            await self.release.wait()

    client = BlockingCloseClient()
    coordinator = _coordinator(client)
    await coordinator.bind()
    first = asyncio.create_task(coordinator.close())
    await client.entered.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    client.release.set()
    await coordinator.close()
    await coordinator.close()
    assert client.closes == 1
    assert not coordinator.bound
