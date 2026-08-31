from __future__ import annotations

import asyncio
import json
import os
import socket
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
    GitActionResult,
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
    UnixProjectRuntimeClient,
)
from agentbox_runtime.server import RuntimeExecutorServer, _main
from agentbox_runtime.waw_epoch import WAWRuntimeEpochStore

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


class ActiveClaudeManager(FakeClaudeManager):
    async def session(self, project_id: str) -> ClaudeSession:
        self.actions.append(f"session:{project_id}")
        return self.session_value(ClaudeSessionState.RUNNING)


class FakeProjectManager:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def switch_branch(self, project_key: str, branch: str) -> GitActionResult:
        self.actions.append(f"switch:{project_key}:{branch}")
        return GitActionResult("switched", branch)

    async def pull(self, project_key: str) -> GitActionResult:
        self.actions.append(f"pull:{project_key}")
        return GitActionResult("pulled", "main")


class FakeWAWControlServer:
    def __init__(self) -> None:
        self.started = 0
        self.closed = 0

    async def start(self) -> None:
        self.started += 1

    async def close(self) -> None:
        self.closed += 1


def _runtime_epoch_store(tmp_path: Path) -> WAWRuntimeEpochStore:
    directory = tmp_path / "runtime-epoch"
    directory.mkdir(mode=0o700)
    path = directory / "epoch.json"
    path.write_text('{"epoch":"1","schema_version":"waw-runtime-epoch-v1"}')
    path.chmod(0o600)
    return WAWRuntimeEpochStore(
        directory,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )


@pytest.mark.anyio
async def test_runtime_server_consumes_epoch_before_serving(tmp_path: Path) -> None:
    socket_path = tmp_path / "runtime.sock"
    store = _runtime_epoch_store(tmp_path)
    server = RuntimeExecutorServer(
        socket_path,
        FakeManager(),  # type: ignore[arg-type]
        allowed_peer_uids=frozenset({os.geteuid()}),
        waw_epoch_store=store,
    )

    await server.start()
    try:
        assert server.waw_runtime_epoch == 2
        assert json.loads((tmp_path / "runtime-epoch" / "epoch.json").read_text())["epoch"] == "2"
    finally:
        await server.close()


@pytest.mark.anyio
async def test_runtime_server_does_not_reconsume_epoch_on_restart(tmp_path: Path) -> None:
    socket_path = tmp_path / "runtime.sock"
    store = _runtime_epoch_store(tmp_path)
    server = RuntimeExecutorServer(
        socket_path,
        FakeManager(),  # type: ignore[arg-type]
        allowed_peer_uids=frozenset({os.geteuid()}),
        waw_epoch_store=store,
    )

    await server.start()
    await server.close()
    await server.start()
    try:
        assert server.waw_runtime_epoch == 2
        assert json.loads((tmp_path / "runtime-epoch" / "epoch.json").read_text())["epoch"] == "2"
    finally:
        await server.close()


@pytest.mark.anyio
async def test_runtime_server_wires_optional_waw_control_lifecycle(tmp_path: Path) -> None:
    control = FakeWAWControlServer()
    server = RuntimeExecutorServer(
        tmp_path / "runtime.sock",
        FakeManager(),  # type: ignore[arg-type]
        allowed_peer_uids=frozenset({os.geteuid()}),
        waw_control_server=control,  # type: ignore[arg-type]
    )

    await server.start()
    assert control.started == 1
    await server.close()
    assert control.closed == 1


@pytest.mark.anyio
async def test_runtime_main_rejects_unknown_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTBOX_ENV", "prodution")
    with pytest.raises(RuntimeError, match="AGENTBOX_ENV"):
        await _main()


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
async def test_runtime_server_replaces_only_same_uid_stale_socket(tmp_path: Path) -> None:
    socket_path = tmp_path / "runtime.sock"
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(socket_path))
    stale.close()
    server = RuntimeExecutorServer(
        socket_path,
        FakeManager(),  # type: ignore[arg-type]
        allowed_peer_uids=frozenset({os.geteuid()}),
    )

    await server.start()
    try:
        client = UnixCodexRuntimeClient(socket_path, status_timeout_seconds=2)
        assert (await client.status("req_stale-recovery")).installed is True
    finally:
        await server.close()


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
async def test_runtime_protocol_fuzz_cases_fail_closed_before_dispatch(tmp_path: Path) -> None:
    socket_path = tmp_path / "runtime.sock"
    manager = FakeManager()
    server = RuntimeExecutorServer(
        socket_path,
        manager,  # type: ignore[arg-type]
        allowed_peer_uids=frozenset({os.geteuid()}),
        allowed_peer_gids=frozenset({os.getegid()}),
    )
    await server.start()
    payloads = (
        b'{"protocol_version":1,"protocol_version":1,'
        b'"action":"codex.status","request_id":"req_duplicate"}\n',
        b'{"protocol_version":true,"action":"codex.status","request_id":"req_boolean"}\n',
        b'{"protocol_version":1,"action":"codex.status","request_id":null}\n',
        b'{"protocol_version":1,"action":"codex.status","request_id":"bad\\ncorrelation"}\n',
        b"\xff\n",
        (b"[" * 1100) + (b"]" * 1100) + b"\n",
        (
            b'{"protocol_version":1,"action":"codex.status",'
            b'"request_id":"req_first"}\n'
            b'{"protocol_version":1,"action":"codex.status",'
            b'"request_id":"req_second"}\n'
        ),
    )
    try:
        for payload in payloads:
            reader, writer = await asyncio.open_unix_connection(socket_path)
            writer.write(payload)
            await writer.drain()
            response = json.loads(await reader.readline())
            writer.close()
            await writer.wait_closed()
            assert response["error"]["code"] == "RUNTIME_PROTOCOL_INVALID"
        assert manager.actions == []
    finally:
        await server.close()


@pytest.mark.anyio
async def test_runtime_socket_rejects_unapproved_peer_gid(tmp_path: Path) -> None:
    socket_path = tmp_path / "runtime.sock"
    server = RuntimeExecutorServer(
        socket_path,
        FakeManager(),  # type: ignore[arg-type]
        allowed_peer_uids=frozenset({os.geteuid()}),
        allowed_peer_gids=frozenset({os.getegid() + 1}),
    )
    await server.start()
    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)
        writer.write(
            b'{"protocol_version":1,"action":"codex.status","request_id":"req_peer_gid"}\n'
        )
        await writer.drain()
        response = json.loads(await reader.readline())
        writer.close()
        await writer.wait_closed()
        assert response["error"]["code"] == "RUNTIME_PEER_FORBIDDEN"
    finally:
        await server.close()


@pytest.mark.anyio
async def test_runtime_client_rejects_invalid_request_id_before_connect(tmp_path: Path) -> None:
    client = UnixCodexRuntimeClient(tmp_path / "absent.sock")

    with pytest.raises(RuntimeOperationError) as raised:
        await client.status("bad\ncorrelation")

    assert raised.value.code == "RUNTIME_REQUEST_ID_INVALID"


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
async def test_project_runtime_rejects_paths_argv_environment_and_git_config(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "runtime.sock"
    project = FakeProjectManager()
    server = RuntimeExecutorServer(
        socket_path,
        FakeManager(),  # type: ignore[arg-type]
        allowed_peer_uids=frozenset({os.geteuid()}),
        project_manager=project,  # type: ignore[arg-type]
    )
    await server.start()
    try:
        for field, value in (
            ("path", "/tmp/escape"),
            ("argv", ["--force"]),
            ("environment", {"GIT_ALLOW_PROTOCOL": "file"}),
            ("config", {"core.sshCommand": "evil"}),
        ):
            reader, writer = await asyncio.open_unix_connection(socket_path)
            writer.write(
                json.dumps(
                    {
                        "protocol_version": 1,
                        "action": "git.pull",
                        "request_id": f"req_project_{field}",
                        "project_key": "project-a",
                        field: value,
                    }
                ).encode()
                + b"\n"
            )
            await writer.drain()
            response = json.loads(await reader.readline())
            writer.close()
            await writer.wait_closed()
            assert response["error"]["code"] == "RUNTIME_PROTOCOL_INVALID"
        assert project.actions == []
    finally:
        await server.close()


@pytest.mark.anyio
async def test_active_claude_session_blocks_pull_and_branch_switch(tmp_path: Path) -> None:
    socket_path = tmp_path / "runtime.sock"
    project = FakeProjectManager()
    claude = ActiveClaudeManager()
    server = RuntimeExecutorServer(
        socket_path,
        FakeManager(),  # type: ignore[arg-type]
        allowed_peer_uids=frozenset({os.geteuid()}),
        claude_manager=claude,  # type: ignore[arg-type]
        project_manager=project,  # type: ignore[arg-type]
    )
    await server.start()
    try:
        client = UnixProjectRuntimeClient(socket_path)
        with pytest.raises(RuntimeOperationError) as pull_error:
            await client.pull("req_active_pull", "project-a")
        assert pull_error.value.code == "PROJECT_RUNTIME_ACTIVE"
        with pytest.raises(RuntimeOperationError) as switch_error:
            await client.switch_branch("req_active_switch", "project-a", "feature/safe")
        assert switch_error.value.code == "PROJECT_RUNTIME_ACTIVE"
        assert project.actions == []
        assert claude.actions == ["session:project-a", "session:project-a"]
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
async def test_project_runtime_client_rejects_non_object_error_envelope(tmp_path: Path) -> None:
    socket_path = tmp_path / "malformed-error.sock"

    async def malformed_error(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = json.loads(await reader.readline())
        writer.write(
            json.dumps(
                {
                    "protocol_version": 1,
                    "request_id": request["request_id"],
                    "data": {"installed": True, "version": "untrusted"},
                    "error": "ignored unless fail-closed",
                }
            ).encode()
            + b"\n"
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(malformed_error, path=socket_path)
    try:
        client = UnixProjectRuntimeClient(socket_path)
        with pytest.raises(RuntimeOperationError) as raised:
            await client.git_global_status("req_project_malformed")
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
