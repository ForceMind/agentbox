from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import cast

import pytest
from agentbox_runtime.models import (
    AuthenticationState,
    CapabilityState,
    ClaudeCapabilities,
    ClaudeSession,
    ClaudeSessionActionResult,
    ClaudeSessionOutput,
    ClaudeSessionState,
    ClaudeStatus,
    CodexCapabilities,
    CodexStatus,
    InstallationType,
    PairCodeResult,
    RemoteActionResult,
    RemoteState,
    RuntimeOperationError,
    WorkspaceState,
)
from agentbox_runtime.rpc import (
    DEFAULT_CODEX_MUTATION_RPC_TIMEOUT_SECONDS,
    DEFAULT_CODEX_STATUS_RPC_TIMEOUT_SECONDS,
    UnixClaudeRuntimeClient,
    UnixCodexRuntimeClient,
)
from agentbox_runtime.server import RuntimeExecutorServer

CANARY = "PAIR-SECRET-CANARY-RPC-4D8P"


class FakeManager:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def status(self) -> CodexStatus:
        self.actions.append("status")
        return CodexStatus(
            installed=True,
            version="fixture",
            selected_executable="/fixture/codex",
            installation_type=InstallationType.UNKNOWN,
            authentication=AuthenticationState.UNKNOWN,
            capabilities=CodexCapabilities(pair=CapabilityState.SUPPORTED),
            remote_state=RemoteState.UNKNOWN,
        )

    async def start_remote(self) -> RemoteActionResult:
        self.actions.append("start")
        return RemoteActionResult("started", RemoteState.RUNNING)

    async def stop_remote(self) -> RemoteActionResult:
        self.actions.append("stop")
        return RemoteActionResult("stopped", RemoteState.STOPPED)

    async def generate_pair_code(self) -> PairCodeResult:
        self.actions.append("pair")
        return PairCodeResult(CANARY)


class FakeClaudeManager:
    def __init__(self) -> None:
        self.actions: list[str] = []

    @staticmethod
    def session_value(state: ClaudeSessionState) -> ClaudeSession:
        return ClaudeSession(
            project_id="project-a",
            display_name="Project A",
            state=state,
            managed=True,
            session_name="agentbox-claude-project-a-fixture",
            attach_command="tmux attach-session -t =agentbox-claude-project-a-fixture",
            workspace_state=WorkspaceState.UNKNOWN,
            tmux_running=state is not ClaudeSessionState.STOPPED,
        )

    async def status(self) -> ClaudeStatus:
        self.actions.append("status")
        return ClaudeStatus(
            installed=True,
            version="fixture",
            authentication=AuthenticationState.UNKNOWN,
            capabilities=ClaudeCapabilities(remote_control=CapabilityState.SUPPORTED),
            tmux_installed=True,
            tmux_version="fixture",
            managed_sessions=0,
            unmanaged_sessions=0,
            workspace_interaction_warnings=0,
        )

    async def list_sessions(self) -> tuple[ClaudeSession, ...]:
        self.actions.append("list")
        return (self.session_value(ClaudeSessionState.STOPPED),)

    async def session(self, project_id: str) -> ClaudeSession:
        self.actions.append(f"session:{project_id}")
        return self.session_value(ClaudeSessionState.STOPPED)

    async def start(self, project_id: str) -> ClaudeSessionActionResult:
        self.actions.append(f"start:{project_id}")
        return ClaudeSessionActionResult("started", self.session_value(ClaudeSessionState.STARTING))

    async def stop(self, project_id: str) -> ClaudeSessionActionResult:
        self.actions.append(f"stop:{project_id}")
        return ClaudeSessionActionResult("stopped", self.session_value(ClaudeSessionState.STOPPED))

    async def recent_output(self, project_id: str) -> ClaudeSessionOutput:
        self.actions.append(f"output:{project_id}")
        return ClaudeSessionOutput(
            "project-a",
            "agentbox-claude-project-a-fixture",
            "safe fixture",
            truncated=False,
        )


@pytest.mark.anyio
async def test_runtime_socket_accepts_only_typed_actions(tmp_path: Path) -> None:
    socket_path = tmp_path / "runtime.sock"
    manager = FakeManager()
    server = RuntimeExecutorServer(
        socket_path,
        manager,  # type: ignore[arg-type]
        allowed_peer_uids=frozenset({os.geteuid()}),
    )
    await server.start()
    try:
        client = UnixCodexRuntimeClient(
            socket_path, status_timeout_seconds=2, mutation_timeout_seconds=2
        )
        assert (await client.status("req_rpc-status")).installed is True
        assert (await client.start_remote("req_rpc-start")).outcome == "started"
        assert (await client.stop_remote("req_rpc-stop")).outcome == "stopped"
        assert (await client.generate_pair_code("req_rpc-pair")).code == CANARY
        assert manager.actions == ["status", "start", "stop", "pair"]
    finally:
        await server.close()
    assert not socket_path.exists()


@pytest.mark.anyio
async def test_runtime_socket_rejects_extra_fields_and_unknown_action(tmp_path: Path) -> None:
    socket_path = tmp_path / "runtime.sock"
    manager = FakeManager()
    server = RuntimeExecutorServer(
        socket_path,
        manager,  # type: ignore[arg-type]
        allowed_peer_uids=frozenset({os.geteuid()}),
    )
    await server.start()
    try:
        for payload in (
            {
                "protocol_version": 1,
                "action": "codex.status",
                "request_id": "req_extra",
                "argv": ["anything"],
            },
            {
                "protocol_version": 1,
                "action": "shell.exec",
                "request_id": "req_unknown",
            },
        ):
            reader, writer = await asyncio.open_unix_connection(socket_path)
            writer.write(json.dumps(payload).encode() + b"\n")
            await writer.drain()
            response = json.loads(await reader.readline())
            writer.close()
            await writer.wait_closed()
            assert response["error"]["code"] == "RUNTIME_PROTOCOL_INVALID"
        assert manager.actions == []
    finally:
        await server.close()


@pytest.mark.anyio
async def test_runtime_socket_accepts_only_typed_claude_project_actions(tmp_path: Path) -> None:
    socket_path = tmp_path / "runtime.sock"
    claude = FakeClaudeManager()
    server = RuntimeExecutorServer(
        socket_path,
        FakeManager(),  # type: ignore[arg-type]
        allowed_peer_uids=frozenset({os.geteuid()}),
        claude_manager=claude,  # type: ignore[arg-type]
    )
    await server.start()
    try:
        client = UnixClaudeRuntimeClient(
            socket_path, status_timeout_seconds=2, mutation_timeout_seconds=2
        )
        assert (await client.status("req_claude_status")).installed is True
        assert len(await client.list_sessions("req_claude_list")) == 1
        assert (await client.session("req_claude_session", "project-a")).project_id == "project-a"
        assert (await client.start_session("req_claude_start", "project-a")).outcome == "started"
        assert (await client.stop_session("req_claude_stop", "project-a")).outcome == "stopped"
        assert (
            await client.recent_output("req_claude_output", "project-a")
        ).output == "safe fixture"
        assert claude.actions == [
            "status",
            "list",
            "session:project-a",
            "start:project-a",
            "stop:project-a",
            "output:project-a",
        ]
    finally:
        await server.close()


@pytest.mark.anyio
async def test_runtime_rejects_claude_paths_argv_and_missing_project_ids(tmp_path: Path) -> None:
    socket_path = tmp_path / "runtime.sock"
    claude = FakeClaudeManager()
    server = RuntimeExecutorServer(
        socket_path,
        FakeManager(),  # type: ignore[arg-type]
        allowed_peer_uids=frozenset({os.geteuid()}),
        claude_manager=claude,  # type: ignore[arg-type]
    )
    await server.start()
    try:
        for payload in (
            {
                "protocol_version": 1,
                "action": "claude.session.start",
                "request_id": "req_missing",
            },
            {
                "protocol_version": 1,
                "action": "claude.session.start",
                "request_id": "req_path",
                "project_id": "../etc",
            },
            {
                "protocol_version": 1,
                "action": "claude.session.stop",
                "request_id": "req_argv",
                "project_id": "project-a",
                "argv": ["kill-server"],
            },
        ):
            reader, writer = await asyncio.open_unix_connection(socket_path)
            writer.write(json.dumps(payload).encode() + b"\n")
            await writer.drain()
            response = json.loads(await reader.readline())
            writer.close()
            await writer.wait_closed()
            assert response["error"]["code"] == "RUNTIME_PROTOCOL_INVALID"
        assert claude.actions == []
    finally:
        await server.close()


@pytest.mark.anyio
async def test_runtime_socket_rejects_unapproved_peer_uid(tmp_path: Path) -> None:
    socket_path = tmp_path / "runtime.sock"
    server = RuntimeExecutorServer(
        socket_path,
        FakeManager(),  # type: ignore[arg-type]
        allowed_peer_uids=frozenset({os.geteuid() + 1}),
    )
    await server.start()
    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)
        writer.write(b'{"protocol_version":1,"action":"codex.status","request_id":"req_peer"}\n')
        await writer.drain()
        response = json.loads(await reader.readline())
        writer.close()
        await writer.wait_closed()
        assert response["error"]["code"] == "RUNTIME_PEER_FORBIDDEN"
    finally:
        await server.close()


@pytest.mark.anyio
async def test_runtime_client_normalizes_response_timeout(tmp_path: Path) -> None:
    socket_path = tmp_path / "timeout.sock"
    connection_closed = asyncio.Event()

    async def never_reply(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.readline()
            await asyncio.sleep(0.05)
        finally:
            writer.close()
            await writer.wait_closed()
            connection_closed.set()

    server = await asyncio.start_unix_server(never_reply, path=socket_path)
    try:
        client = UnixCodexRuntimeClient(socket_path, status_timeout_seconds=0.01)
        with pytest.raises(RuntimeOperationError) as raised:
            await client.status("req_timeout")
        assert raised.value.code == "CODEX_RUNTIME_TIMEOUT"
        assert raised.value.retryable is True
        await asyncio.wait_for(connection_closed.wait(), timeout=1)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.anyio
async def test_runtime_client_rejects_mismatched_request_id(tmp_path: Path) -> None:
    socket_path = tmp_path / "mismatch.sock"

    async def wrong_id(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readline()
        writer.write(b'{"protocol_version":1,"request_id":"req_other","data":{},"error":null}\n')
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(wrong_id, path=socket_path)
    try:
        client = UnixCodexRuntimeClient(socket_path, status_timeout_seconds=1)
        with pytest.raises(RuntimeOperationError) as raised:
            await client.status("req_expected")
        assert raised.value.code == "RUNTIME_PROTOCOL_INVALID"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.anyio
async def test_runtime_client_uses_full_operation_specific_timeout_budgets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = UnixCodexRuntimeClient(tmp_path / "unused.sock")
    observed: list[tuple[str, float]] = []
    manager = FakeManager()

    async def fake_request(
        action: str, request_id: str, *, timeout_seconds: float
    ) -> dict[str, object]:
        del request_id
        observed.append((action, timeout_seconds))
        if action == "codex.status":
            return cast(
                dict[str, object], json.loads(json.dumps((await manager.status()).to_dict()))
            )
        if action == "codex.pair":
            return (await manager.generate_pair_code()).to_dict()
        if action == "codex.remote.start":
            return (await manager.start_remote()).to_dict()
        return (await manager.stop_remote()).to_dict()

    monkeypatch.setattr(client, "_request", fake_request)

    await client.status("req_budget_status")
    await client.start_remote("req_budget_start")
    await client.stop_remote("req_budget_stop")
    await client.generate_pair_code("req_budget_pair")

    assert observed == [
        ("codex.status", DEFAULT_CODEX_STATUS_RPC_TIMEOUT_SECONDS),
        ("codex.remote.start", DEFAULT_CODEX_MUTATION_RPC_TIMEOUT_SECONDS),
        ("codex.remote.stop", DEFAULT_CODEX_MUTATION_RPC_TIMEOUT_SECONDS),
        ("codex.pair", DEFAULT_CODEX_MUTATION_RPC_TIMEOUT_SECONDS),
    ]
    assert DEFAULT_CODEX_STATUS_RPC_TIMEOUT_SECONDS > 58
    assert DEFAULT_CODEX_MUTATION_RPC_TIMEOUT_SECONDS > 88
