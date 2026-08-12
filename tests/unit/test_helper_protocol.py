from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest
from agentbox_helper.actions import ActionResult, action_argv
from agentbox_helper.protocol import MAX_HELPER_FRAME, HelperAction, HelperRequest
from agentbox_helper.server import HelperServer


def _request(**changes: object) -> bytes:
    value: dict[str, object] = {
        "protocol_version": 1,
        "request_id": "req_helper_fixture_001",
        "action": "systemd.restart_agentbox",
    }
    value.update(changes)
    return json.dumps(value).encode() + b"\n"


@pytest.mark.parametrize(
    "changes",
    [
        {"protocol_version": 2},
        {"action": "systemd.restart_service"},
        {"request_id": "bad\nrequest"},
        {"service": "ssh.service"},
        {"path": "/etc/shadow"},
        {"argv": ["/bin/sh"]},
        {"command": "id"},
        {"executable": "/bin/bash"},
    ],
)
def test_helper_protocol_rejects_unknown_fields_actions_and_injection(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        HelperRequest.decode(_request(**changes))


def test_helper_protocol_rejects_malformed_and_oversized_frames() -> None:
    for raw in (b"{malformed}\n", b"{}", b"x" * MAX_HELPER_FRAME + b"\n"):
        with pytest.raises(ValueError):
            HelperRequest.decode(raw)


def test_helper_actions_map_only_to_fixed_agentbox_units() -> None:
    rendered = repr({action.value: action_argv(action) for action in HelperAction})
    assert "ssh.service" not in rendered
    assert "shell" not in rendered
    assert "agentbox-api.service" in rendered
    assert all(argv[0] == "/usr/bin/systemctl" for argv in map(action_argv, HelperAction))


async def _exchange(socket_path: Path, payload: bytes) -> dict[str, object]:
    reader, writer = await asyncio.open_unix_connection(socket_path)
    writer.write(payload)
    await writer.drain()
    value = json.loads(await reader.readline())
    writer.close()
    await writer.wait_closed()
    assert isinstance(value, dict)
    return value


@pytest.mark.anyio
async def test_helper_rejects_invalid_peer_uid(tmp_path: Path) -> None:
    socket_path = tmp_path / "helper.sock"

    async def runner(action: HelperAction) -> ActionResult:
        raise AssertionError(action)

    helper = HelperServer(allowed_peer_uids=frozenset({os.geteuid() + 1}), runner=runner)
    server = await asyncio.start_unix_server(helper.handle, path=socket_path)
    async with server:
        response = await _exchange(socket_path, _request())

    assert response["code"] == "HELPER_PEER_FORBIDDEN"


@pytest.mark.anyio
async def test_helper_executes_one_typed_request_and_closes_connection(tmp_path: Path) -> None:
    socket_path = tmp_path / "helper.sock"
    actions: list[HelperAction] = []

    async def runner(action: HelperAction) -> ActionResult:
        actions.append(action)
        return ActionResult(True, "HELPER_ACTION_SUCCEEDED", "AgentBox action completed")

    helper = HelperServer(allowed_peer_uids=frozenset({os.geteuid()}), runner=runner)
    server = await asyncio.start_unix_server(helper.handle, path=socket_path)
    async with server:
        response = await _exchange(socket_path, _request())

    assert response["ok"] is True
    assert actions == [HelperAction.SYSTEMD_RESTART_AGENTBOX]


@pytest.mark.anyio
async def test_helper_enforces_concurrent_request_cap(tmp_path: Path) -> None:
    socket_path = tmp_path / "helper.sock"
    entered = asyncio.Event()
    release = asyncio.Event()

    async def runner(action: HelperAction) -> ActionResult:
        del action
        entered.set()
        await release.wait()
        return ActionResult(True, "HELPER_ACTION_SUCCEEDED", "AgentBox action completed")

    helper = HelperServer(
        allowed_peer_uids=frozenset({os.geteuid()}), runner=runner, max_concurrent_requests=1
    )
    server = await asyncio.start_unix_server(helper.handle, path=socket_path)
    async with server:
        first = asyncio.create_task(_exchange(socket_path, _request()))
        await entered.wait()
        second = await _exchange(
            socket_path,
            _request(request_id="req_helper_fixture_002"),
        )
        release.set()
        await first

    assert second["code"] == "HELPER_BUSY"


@pytest.mark.anyio
async def test_helper_bounds_action_timeout(tmp_path: Path) -> None:
    socket_path = tmp_path / "helper.sock"

    async def runner(action: HelperAction) -> ActionResult:
        del action
        await asyncio.sleep(10)
        raise AssertionError("unreachable")

    helper = HelperServer(
        allowed_peer_uids=frozenset({os.geteuid()}),
        runner=runner,
        action_timeout_seconds=0.01,
    )
    server = await asyncio.start_unix_server(helper.handle, path=socket_path)
    async with server:
        response = await _exchange(socket_path, _request())

    assert response["code"] == "HELPER_ACTION_TIMEOUT"
