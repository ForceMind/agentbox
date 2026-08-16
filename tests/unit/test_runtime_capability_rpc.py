from __future__ import annotations

import asyncio
import contextlib
import json
import os
import socket
import struct
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from agentbox_protocol.runtime_capabilities import (
    CLAUDE_CAPABILITY_NAMES,
    CODEX_CAPABILITY_NAMES,
    RuntimeAdapterID,
    RuntimeAuthenticationState,
    RuntimeCapabilityCollectionState,
    RuntimeCapabilityFindingCode,
    RuntimeCapabilityObservation,
    RuntimeCapabilityOutcome,
    RuntimeCapabilityQuery,
    RuntimeCapabilityReport,
    RuntimeCapabilitySet,
    RuntimeConfigOwnershipState,
    RuntimeEvidenceClass,
    RuntimeEvidenceLifecycle,
    RuntimeInstallationType,
    RuntimeRemoteState,
    RuntimeType,
)
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.rpc import MAX_RUNTIME_FRAME, UnixRuntimeCapabilityClient
from agentbox_runtime.server import RuntimeExecutorServer

RUNTIME_ID = "rti_0123456789abcdef0123456789abcdef"


def report_for(
    query: RuntimeCapabilityQuery, *, observed_at: datetime | None = None
) -> RuntimeCapabilityReport:
    now = observed_at or datetime.now(UTC)
    names = (
        CODEX_CAPABILITY_NAMES
        if query.runtime_type is RuntimeType.CODEX
        else CLAUDE_CAPABILITY_NAMES
    )
    observations = tuple(
        RuntimeCapabilityObservation(
            name=name,
            outcome=RuntimeCapabilityOutcome.UNKNOWN,
            lifecycle=RuntimeEvidenceLifecycle.VALIDATED,
            evidence_class=RuntimeEvidenceClass.QUALIFIED_PUBLIC_CONTRACT,
            finding_code=RuntimeCapabilityFindingCode.PUBLIC_CONTRACT_UNQUALIFIED,
            observed_at=now,
            expires_at=now + timedelta(seconds=60),
        )
        for name in names
    )
    return RuntimeCapabilityReport(
        runtime_installation_id=query.runtime_installation_id,
        runtime_installation_revision=query.runtime_installation_revision,
        runtime_type=query.runtime_type,
        capability_set=query.capability_set,
        adapter_id=(
            RuntimeAdapterID.CODEX_RUNTIME_ADAPTER_V1
            if query.runtime_type is RuntimeType.CODEX
            else RuntimeAdapterID.CLAUDE_RUNTIME_ADAPTER_V1
        ),
        collection_state=RuntimeCapabilityCollectionState.COMPLETE,
        runtime_version="0.146.1",
        installation_type=(
            RuntimeInstallationType.STANDALONE
            if query.runtime_type is RuntimeType.CODEX
            else RuntimeInstallationType.NOT_APPLICABLE
        ),
        authentication_state=RuntimeAuthenticationState.UNKNOWN,
        remote_state=RuntimeRemoteState.UNKNOWN,
        config_ownership_state=(
            RuntimeConfigOwnershipState.UNKNOWN
            if query.runtime_type is RuntimeType.CODEX
            else RuntimeConfigOwnershipState.NOT_APPLICABLE
        ),
        managed_session_count=None,
        observed_at=now,
        expires_at=now + timedelta(seconds=60),
        observations=observations,
        findings=(RuntimeCapabilityFindingCode.PUBLIC_CONTRACT_UNQUALIFIED,),
    )


class NoMutationManager:
    async def status(self) -> None:
        raise AssertionError("legacy status must not serve capability query")

    async def start_remote(self) -> None:
        raise AssertionError("capability query must not mutate Codex")

    async def stop_remote(self) -> None:
        raise AssertionError("capability query must not mutate Codex")

    async def generate_pair_code(self) -> None:
        raise AssertionError("capability query must not generate a Pair Code")


class FixedCollector:
    def __init__(self) -> None:
        self.queries: list[RuntimeCapabilityQuery] = []

    async def collect(self, query: RuntimeCapabilityQuery) -> RuntimeCapabilityReport:
        self.queries.append(query)
        return report_for(query)


def query_payload(runtime_type: RuntimeType = RuntimeType.CODEX) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "action": "runtime.capabilities.query",
        "request_id": "req_runtime_capability_rpc",
        "capability_contract_version": 1,
        "runtime_installation_id": RUNTIME_ID,
        "runtime_installation_revision": 2,
        "runtime_type": runtime_type.value,
        "capability_set": (
            "codex_provider_runtime_v1"
            if runtime_type is RuntimeType.CODEX
            else "claude_runtime_session_v1"
        ),
        "refresh_policy": "force_fresh_read_only",
    }


async def send(socket_path: Path, raw: bytes) -> dict[str, Any]:
    reader, writer = await asyncio.open_unix_connection(socket_path)
    writer.write(raw)
    await writer.drain()
    response = cast(dict[str, Any], json.loads(await reader.readline()))
    writer.close()
    await writer.wait_closed()
    return response


@pytest.mark.anyio
async def test_capability_action_reuses_existing_peer_authenticated_uds(tmp_path: Path) -> None:
    socket_path = tmp_path / "runtime.sock"
    collector = FixedCollector()
    server = RuntimeExecutorServer(
        socket_path,
        NoMutationManager(),  # type: ignore[arg-type]
        allowed_peer_uids=frozenset({os.geteuid()}),
        allowed_peer_gids=frozenset({os.getegid()}),
        capability_collector=collector,  # type: ignore[arg-type]
    )
    await server.start()
    try:
        client = UnixRuntimeCapabilityClient(socket_path, timeout_seconds=2)
        codex = await client.collect_capabilities(
            "req_codex_rpc",
            RUNTIME_ID,
            2,
            RuntimeType.CODEX,
            RuntimeCapabilitySet.CODEX_PROVIDER_RUNTIME_V1,
        )
        claude = await client.collect_capabilities(
            "req_claude_rpc",
            RUNTIME_ID,
            2,
            RuntimeType.CLAUDE,
            RuntimeCapabilitySet.CLAUDE_RUNTIME_SESSION_V1,
        )
        assert tuple(item.name for item in codex.observations) == CODEX_CAPABILITY_NAMES
        assert tuple(item.name for item in claude.observations) == CLAUDE_CAPABILITY_NAMES
        assert [item.runtime_type for item in collector.queries] == [
            RuntimeType.CODEX,
            RuntimeType.CLAUDE,
        ]
        assert socket_path.stat().st_mode & 0o777 == 0o660
    finally:
        await server.close()
    assert not socket_path.exists()


@pytest.mark.anyio
async def test_capability_request_schema_fails_closed_before_collection(tmp_path: Path) -> None:
    socket_path = tmp_path / "runtime.sock"
    collector = FixedCollector()
    server = RuntimeExecutorServer(
        socket_path,
        NoMutationManager(),  # type: ignore[arg-type]
        allowed_peer_uids=frozenset({os.geteuid()}),
        allowed_peer_gids=frozenset({os.getegid()}),
        capability_collector=collector,  # type: ignore[arg-type]
        read_timeout_seconds=0.02,
    )
    await server.start()
    valid = query_payload()
    invalid_payloads = (
        {**valid, "protocol_version": 2},
        {**valid, "capability_contract_version": 2},
        {**valid, "action": "runtime.probe"},
        {**valid, "capability_set": "arbitrary"},
        {
            **valid,
            "runtime_type": "claude",
            "capability_set": "codex_provider_runtime_v1",
        },
        {**valid, "runtime_installation_id": "ses_0123456789abcdef0123456789abcdef"},
        {**valid, "runtime_installation_revision": 0},
        {**valid, "runtime_installation_revision": True},
        {key: value for key, value in valid.items() if key != "refresh_policy"},
        {**valid, "command": "id"},
    )
    try:
        for payload in invalid_payloads:
            response = await send(
                socket_path,
                json.dumps(payload, separators=(",", ":")).encode() + b"\n",
            )
            assert response["error"]["code"] == "RUNTIME_PROTOCOL_INVALID"
        for raw in (
            b'{"protocol_version":1,"protocol_version":1,"action":'
            b'"runtime.capabilities.query","request_id":"req_duplicate"}\n',
            b"\xff\n",
            json.dumps({**valid, "runtime_installation_id": "\ud800"}).encode() + b"\n",
            json.dumps(valid).encode() + b"\n" + json.dumps(valid).encode() + b"\n",
            b"x" * (MAX_RUNTIME_FRAME + 1) + b"\n",
        ):
            response = await send(socket_path, raw)
            assert response["error"]["code"] == "RUNTIME_PROTOCOL_INVALID"

        reader, writer = await asyncio.open_unix_connection(socket_path)
        writer.write(json.dumps(valid).encode())
        await writer.drain()
        response = json.loads(await reader.readline())
        assert response["error"]["code"] == "RUNTIME_PROTOCOL_INVALID"
        writer.close()
        await writer.wait_closed()
        assert collector.queries == []
    finally:
        await server.close()


@pytest.mark.anyio
async def test_capability_request_rejects_trailing_frame_data(tmp_path: Path) -> None:
    socket_path = tmp_path / "runtime.sock"
    collector = FixedCollector()
    server = RuntimeExecutorServer(
        socket_path,
        NoMutationManager(),  # type: ignore[arg-type]
        allowed_peer_uids=frozenset({os.geteuid()}),
        capability_collector=collector,  # type: ignore[arg-type]
    )
    await server.start()
    try:
        response = await send(socket_path, json.dumps(query_payload()).encode() + b"\nX")
        assert response["error"]["code"] == "RUNTIME_PROTOCOL_INVALID"
        assert collector.queries == []
    finally:
        await server.close()


def response_envelope(query: RuntimeCapabilityQuery, data: object) -> bytes:
    return (
        json.dumps(
            {
                "protocol_version": 1,
                "request_id": query.request_id,
                "data": data,
                "error": None,
            },
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )


async def run_fake_server(
    socket_path: Path,
    response: bytes | None,
    *,
    delay: float = 0,
) -> asyncio.AbstractServer:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readline()
        if delay:
            await asyncio.sleep(delay)
        if response is not None:
            with contextlib.suppress(ConnectionError):
                writer.write(response)
                await writer.drain()
        writer.close()
        with contextlib.suppress(ConnectionError):
            await writer.wait_closed()

    return await asyncio.start_unix_server(handler, path=socket_path)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "mutation",
    (
        "extra_report_field",
        "missing_report_field",
        "runtime_id",
        "runtime_revision",
        "runtime_type",
        "capability_set",
        "duplicate_capability",
        "missing_capability",
        "unexpected_capability",
        "timestamp_mismatch",
        "invalid_expiry",
        "findings_bound",
    ),
)
async def test_capability_client_rejects_malformed_or_mismatched_reports(
    tmp_path: Path, mutation: str
) -> None:
    query = RuntimeCapabilityQuery.model_validate_json(json.dumps(query_payload()))
    data = report_for(query).model_dump(mode="json")
    observations = list(data["observations"])
    if mutation == "extra_report_field":
        data["path"] = "/root/.codex"
    elif mutation == "missing_report_field":
        del data["adapter_id"]
    elif mutation == "runtime_id":
        data["runtime_installation_id"] = "rti_ffffffffffffffffffffffffffffffff"
    elif mutation == "runtime_revision":
        data["runtime_installation_revision"] = 99
    elif mutation == "runtime_type":
        data["runtime_type"] = "claude"
    elif mutation == "capability_set":
        data["capability_set"] = "claude_runtime_session_v1"
    elif mutation == "duplicate_capability":
        data["observations"] = observations[:-1] + [observations[-2]]
    elif mutation == "missing_capability":
        data["observations"] = observations[:-1]
    elif mutation == "unexpected_capability":
        observations[-1]["name"] = "claude.installed"
        data["observations"] = observations
    elif mutation == "timestamp_mismatch":
        observations[0]["observed_at"] = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
        data["observations"] = observations
    elif mutation == "invalid_expiry":
        data["expires_at"] = (datetime.now(UTC) + timedelta(seconds=70)).isoformat()
    elif mutation == "findings_bound":
        data["findings"] = ["PUBLIC_CONTRACT_UNQUALIFIED"] * 33

    socket_path = tmp_path / f"{mutation}.sock"
    server = await run_fake_server(socket_path, response_envelope(query, data))
    try:
        with pytest.raises(RuntimeOperationError) as raised:
            await UnixRuntimeCapabilityClient(socket_path, timeout_seconds=1).collect_capabilities(
                query.request_id,
                query.runtime_installation_id,
                query.runtime_installation_revision,
                query.runtime_type,
                query.capability_set,
            )
        assert raised.value.code == "RUNTIME_PROTOCOL_INVALID"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.anyio
async def test_capability_client_rejects_expired_response_timeout_and_bad_framing(
    tmp_path: Path,
) -> None:
    query = RuntimeCapabilityQuery.model_validate_json(json.dumps(query_payload()))
    expired = report_for(query, observed_at=datetime.now(UTC) - timedelta(seconds=120))
    cases = (
        ("expired", response_envelope(query, expired.model_dump(mode="json")), 0.0),
        ("invalid_json", b"not-json\n", 0.0),
        ("no_newline", b"{}", 0.0),
        ("oversized", b"x" * (MAX_RUNTIME_FRAME + 1) + b"\n", 0.0),
        ("timeout", response_envelope(query, report_for(query).model_dump(mode="json")), 0.1),
    )
    for name, response, delay in cases:
        socket_path = tmp_path / f"{name}.sock"
        server = await run_fake_server(socket_path, response, delay=delay)
        try:
            with pytest.raises(RuntimeOperationError):
                await UnixRuntimeCapabilityClient(
                    socket_path, timeout_seconds=0.01 if name == "timeout" else 1
                ).collect_capabilities(
                    query.request_id,
                    query.runtime_installation_id,
                    query.runtime_installation_revision,
                    query.runtime_type,
                    query.capability_set,
                )
        finally:
            if delay:
                await asyncio.sleep(delay + 0.01)
            server.close()
            await server.wait_closed()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "envelope_change",
    ("extra", "missing", "duplicate", "protocol_version", "request_id"),
)
async def test_capability_client_rejects_non_exact_response_envelope(
    tmp_path: Path, envelope_change: str
) -> None:
    query = RuntimeCapabilityQuery.model_validate_json(json.dumps(query_payload()))
    data = report_for(query).model_dump(mode="json")
    envelope: dict[str, object] = {
        "protocol_version": 1,
        "request_id": query.request_id,
        "data": data,
        "error": None,
    }
    if envelope_change == "extra":
        envelope["path"] = "/root/.codex"
        raw = json.dumps(envelope).encode() + b"\n"
    elif envelope_change == "missing":
        del envelope["error"]
        raw = json.dumps(envelope).encode() + b"\n"
    elif envelope_change == "duplicate":
        raw = (
            b'{"protocol_version":1,"protocol_version":1,'
            b'"request_id":"req_runtime_capability_rpc","data":{},"error":null}\n'
        )
    else:
        envelope[envelope_change] = 2 if envelope_change == "protocol_version" else "req_other"
        raw = json.dumps(envelope).encode() + b"\n"
    socket_path = tmp_path / f"envelope-{envelope_change}.sock"
    server = await run_fake_server(socket_path, raw)
    try:
        with pytest.raises(RuntimeOperationError):
            await UnixRuntimeCapabilityClient(socket_path).collect_capabilities(
                query.request_id,
                query.runtime_installation_id,
                query.runtime_installation_revision,
                query.runtime_type,
                query.capability_set,
            )
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.anyio
async def test_capability_client_normalizes_peer_rejection_without_fallback(
    tmp_path: Path,
) -> None:
    query = RuntimeCapabilityQuery.model_validate_json(json.dumps(query_payload()))
    response = (
        json.dumps(
            {
                "protocol_version": 1,
                "request_id": None,
                "data": None,
                "error": {
                    "code": "RUNTIME_PEER_FORBIDDEN",
                    "category": "forbidden",
                    "message": "RAW-PEER-DETAIL-CANARY",
                    "retryable": False,
                    "retry_after": None,
                },
            }
        ).encode()
        + b"\n"
    )
    socket_path = tmp_path / "peer-rejected.sock"
    server = await run_fake_server(socket_path, response)
    try:
        with pytest.raises(RuntimeOperationError) as raised:
            await UnixRuntimeCapabilityClient(socket_path).collect_capabilities(
                query.request_id,
                query.runtime_installation_id,
                query.runtime_installation_revision,
                query.runtime_type,
                query.capability_set,
            )
        assert raised.value.code == "RUNTIME_CAPABILITY_PEER_REJECTED"
        assert "CANARY" not in raised.value.message
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.anyio
async def test_capability_client_reports_unavailable_without_local_fallback(
    tmp_path: Path,
) -> None:
    query = RuntimeCapabilityQuery.model_validate_json(json.dumps(query_payload()))
    with pytest.raises(RuntimeOperationError) as raised:
        await UnixRuntimeCapabilityClient(tmp_path / "missing.sock").collect_capabilities(
            query.request_id,
            query.runtime_installation_id,
            query.runtime_installation_revision,
            query.runtime_type,
            query.capability_set,
        )
    assert raised.value.code == "RUNTIME_CAPABILITY_UNAVAILABLE"
    assert raised.value.category == "unavailable"
    assert raised.value.retryable is True


def test_peer_check_fails_closed_when_socket_or_peer_credentials_are_missing(
    tmp_path: Path,
) -> None:
    server = RuntimeExecutorServer(
        tmp_path / "runtime.sock",
        NoMutationManager(),  # type: ignore[arg-type]
        allowed_peer_uids=frozenset({os.geteuid()}),
    )

    class NoSocketWriter:
        def get_extra_info(self, name: str) -> None:
            assert name == "socket"
            return None

    assert server._peer_allowed(NoSocketWriter()) is False  # type: ignore[arg-type]

    class BrokenSocket:
        def getsockopt(self, *_args: object) -> bytes:
            raise OSError("SO_PEERCRED unavailable")

    class BrokenPeerWriter:
        def get_extra_info(self, name: str) -> BrokenSocket:
            assert name == "socket"
            return BrokenSocket()

    assert server._peer_allowed(BrokenPeerWriter()) is False  # type: ignore[arg-type]
    assert server._socket_path == tmp_path / "runtime.sock"


def test_peer_check_requires_both_exact_uid_and_gid(tmp_path: Path) -> None:
    server = RuntimeExecutorServer(
        tmp_path / "runtime.sock",
        NoMutationManager(),  # type: ignore[arg-type]
        allowed_peer_uids=frozenset({1001}),
        allowed_peer_gids=frozenset({1002}),
    )

    class PeerSocket:
        def __init__(self, uid: int, gid: int) -> None:
            self._credentials = struct.pack("3i", 42, uid, gid)

        def getsockopt(self, level: int, option: int, size: int) -> bytes:
            assert (level, option, size) == (
                socket.SOL_SOCKET,
                socket.SO_PEERCRED,
                struct.calcsize("3i"),
            )
            return self._credentials

    class PeerWriter:
        def __init__(self, uid: int, gid: int) -> None:
            self._socket = PeerSocket(uid, gid)

        def get_extra_info(self, name: str) -> PeerSocket:
            assert name == "socket"
            return self._socket

    assert server._peer_allowed(PeerWriter(1001, 1002)) is True  # type: ignore[arg-type]
    assert server._peer_allowed(PeerWriter(9999, 1002)) is False  # type: ignore[arg-type]
    assert server._peer_allowed(PeerWriter(1001, 9999)) is False  # type: ignore[arg-type]


def test_peer_check_fails_closed_without_so_peercred(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = RuntimeExecutorServer(
        tmp_path / "runtime.sock",
        NoMutationManager(),  # type: ignore[arg-type]
        allowed_peer_uids=frozenset({os.geteuid()}),
    )

    class PresentSocketWriter:
        def get_extra_info(self, name: str) -> object:
            assert name == "socket"
            return object()

    monkeypatch.delattr(socket, "SO_PEERCRED")
    assert server._peer_allowed(PresentSocketWriter()) is False  # type: ignore[arg-type]
