from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from agentbox_api.main import create_app
from agentbox_core.configuration import Environment, Settings
from agentbox_core.services import build_services
from conftest import FakeClaudeRuntime, FakeCodexRuntime, FakeProjectRuntime, migrate_database
from pydantic import SecretStr


@pytest.mark.anyio
async def test_production_static_artifact_serves_spa_and_keeps_api_404_json(
    tmp_path: Path,
) -> None:
    static = tmp_path / "web"
    assets = static / "assets"
    assets.mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>AgentBox fixture</title>")
    (assets / "app.js").write_text("console.log('fixture')")
    database_url = f"sqlite+pysqlite:///{tmp_path / 'agentbox.db'}"
    migrate_database(database_url)
    settings = Settings(
        env=Environment.TEST,
        database_url=database_url,
        data_dir=tmp_path,
        secret_key=SecretStr("static-fixture-secret-that-is-long-enough"),
        static_dir=static,
    )
    services = build_services(settings)
    app = create_app(
        settings,
        services,
        codex_runtime=FakeCodexRuntime(),
        claude_runtime=FakeClaudeRuntime(),
        project_runtime=FakeProjectRuntime(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        root = await client.get("/")
        route = await client.get("/projects/example")
        asset = await client.get("/assets/app.js")
        missing_api = await client.get("/api/v1/not-a-route")

    assert "AgentBox fixture" in root.text
    assert "AgentBox fixture" in route.text
    assert asset.text == "console.log('fixture')"
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert missing_api.status_code == 404
    assert missing_api.headers["content-type"].startswith("application/json")
    assert "frame-ancestors 'none'" in root.headers["content-security-policy"]


def test_static_root_symlink_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "index.html").write_text("fixture")
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    settings = Settings(
        env=Environment.TEST,
        database_url="sqlite+pysqlite:///:memory:",
        data_dir=tmp_path,
        secret_key=SecretStr("static-fixture-secret-that-is-long-enough"),
        static_dir=linked,
    )

    with pytest.raises(RuntimeError, match="unsafe"):
        create_app(settings)
