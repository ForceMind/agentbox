from __future__ import annotations

import ast
from pathlib import Path

from agentbox_core.models import Base
from agentbox_helper.protocol import HelperAction

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_COLLECTOR = ROOT / "packages/agentbox-runtime/src/agentbox_runtime/capabilities.py"
CONTROL_SERVICE = ROOT / "packages/agentbox-core/src/agentbox_core/runtime_capabilities.py"
PROTOCOL = ROOT / "packages/agentbox-protocol/src/agentbox_protocol/runtime_capabilities.py"
RUNTIME_SERVER = ROOT / "packages/agentbox-runtime/src/agentbox_runtime/server.py"


def called_attributes(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    return {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }


def test_runtime_capability_collector_has_no_mutation_or_privileged_calls() -> None:
    calls = called_attributes(RUNTIME_COLLECTOR)
    forbidden = {
        "start_remote",
        "stop_remote",
        "generate_pair_code",
        "login",
        "logout",
        "install",
        "upgrade",
        "write_text",
        "write_bytes",
        "open",
        "unlink",
        "mkdir",
        "start",
        "stop",
        "recent_output",
        "capture_pane",
        "send_keys",
        "create_session",
        "kill_session",
    }
    assert calls.isdisjoint(forbidden)
    source = RUNTIME_COLLECTOR.read_text()
    for forbidden_text in (
        "httpx",
        "requests",
        "urllib",
        "systemctl",
        "sudo",
        "subprocess",
        "agentbox_helper",
        "provider_credentials",
        "runtime_secret_ref",
        "config.toml",
        ".jsonl",
    ):
        assert forbidden_text not in source


def test_control_plane_service_does_not_create_persistence_or_product_surface() -> None:
    assert "runtime_capabilities" not in Base.metadata.tables
    assert not any("capabilit" in table for table in Base.metadata.tables)
    source = CONTROL_SERVICE.read_text()
    assert "session.add(" not in source
    assert "Provider(" not in source
    assert "RuntimeProvider" not in source
    assert "httpx" not in source
    assert "agentbox_api" not in source

    api_source = "\n".join(
        path.read_text() for path in sorted((ROOT / "apps/api/src/agentbox_api").glob("*.py"))
    )
    cli_source = "\n".join(
        path.read_text() for path in sorted((ROOT / "apps/cli/src").rglob("*.py"))
    )
    web_paths = tuple((ROOT / "apps/web/src").rglob("*.ts")) + tuple(
        (ROOT / "apps/web/src").rglob("*.tsx")
    )
    web_source = "\n".join(path.read_text() for path in sorted(web_paths))
    assert "runtime.capabilities.query" not in api_source
    assert "runtime.capabilities.query" not in cli_source
    assert "runtime.capabilities.query" not in web_source


def test_root_helper_action_authority_is_unchanged() -> None:
    assert {action.value for action in HelperAction} == {
        "systemd.daemon_reload",
        "systemd.start_agentbox",
        "systemd.stop_agentbox",
        "systemd.restart_agentbox",
        "systemd.enable_agentbox",
        "systemd.disable_agentbox",
    }
    assert all(
        "capabil" not in action.value and "provider" not in action.value for action in HelperAction
    )


def test_capability_action_reuses_the_single_runtime_unix_socket() -> None:
    source = RUNTIME_SERVER.read_text()
    assert source.count("asyncio.start_unix_server") == 1
    assert "asyncio.start_server" not in source
    assert "AF_INET" not in source
    assert "agentbox_helper" not in source


def test_wire_contract_contains_no_generic_privileged_payload_field() -> None:
    tree = ast.parse(PROTOCOL.read_text())
    field_names = {
        node.target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert field_names.isdisjoint(
        {
            "command",
            "argv",
            "path",
            "environment",
            "metadata",
            "payload",
            "details",
            "headers",
            "config",
            "timeout",
            "parser",
            "token",
            "secret",
            "authorization",
        }
    )


def test_slice_32a_migration_is_present_without_a_later_runtime_slice() -> None:
    migration_names = {path.name for path in (ROOT / "migrations/versions").glob("*.py")}
    assert any(name.startswith("0004_phase11_provider_core") for name in migration_names)
    assert any(
        name.startswith("0005_phase11_control_plane_ownership_approval") for name in migration_names
    )
    assert not any(name.startswith("0006") for name in migration_names)
