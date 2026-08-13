from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest
from agentbox_core.configuration import Settings
from agentbox_core.services import ControlPlaneServices
from conftest import FakeClaudeRuntime, FakeCodexRuntime
from sqlalchemy.engine import make_url

PASSWORD = "a sufficiently long passphrase"


@pytest.mark.anyio
async def test_phase9_full_system_secret_canaries_remain_ephemeral_or_redacted(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    initialized_services: ControlPlaneServices,
    settings: Settings,
    codex_runtime: FakeCodexRuntime,
    claude_runtime: FakeClaudeRuntime,
    caplog: pytest.LogCaptureFixture,
) -> None:
    password_canary = "PHASE9-WRONG-PASSWORD-CANARY"
    git_url_canary = "https://oauth2:PHASE9-GIT-CREDENTIAL-CANARY@example.invalid/repo.git"
    gh_token_canary = "".join(("gh", "p_", "PHASE9FAKETOKEN1234567890123456789012"))

    with caplog.at_level(logging.DEBUG):
        failed = await client.post(
            "/api/v1/auth/login",
            json={"username": "maintainer", "password": password_canary},
            headers=origin_headers,
        )
        assert failed.status_code == 401
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": "maintainer", "password": PASSWORD},
            headers=origin_headers,
        )
        assert login.status_code == 200
        csrf = str(login.json()["data"]["csrf_token"])
        raw_session = login.cookies["agentbox_session"]

        pair = await client.post(
            "/api/v1/codex/pair-codes",
            headers={**origin_headers, "X-CSRF-Token": csrf},
        )
        assert pair.json()["data"]["pair_code"] == codex_runtime.pair_code

        sessions = await client.get("/api/v1/claude/sessions")
        project_id = next(
            item["project_id"]
            for item in sessions.json()["data"]["sessions"]
            if item["display_name"] == "project-a"
        )
        output = await client.get(f"/api/v1/claude/sessions/{project_id}/output")
        assert output.json()["data"]["output"] == claude_runtime.output_canary

        initialized_services.projects.reconcile_existing(("canary-project",))
        formal_project = initialized_services.projects.resolve("canary-project")
        job, _created = initialized_services.jobs.enqueue(
            job_type="git.push",
            requested_by="adm_fixture",
            target_type="project",
            target_id=formal_project.id,
            project_id=formal_project.id,
            payload={"project_key": "canary-project"},
            resource_lock_key=f"project:{formal_project.id}",
            idempotency_key="phase9-secret-canary-job",
            request_id="req_phase9_secret_scan",
        )
        assert initialized_services.jobs.claim_next("phase9-worker") is not None
        initialized_services.jobs.fail(
            job.id,
            code="GIT_PUSH_FAILED",
            summary=f"{git_url_canary} Authorization: Bearer {gh_token_canary}",
        )

    canaries = (
        password_canary,
        PASSWORD,
        raw_session,
        csrf,
        settings.secret_key.get_secret_value(),
        git_url_canary,
        gh_token_canary,
        codex_runtime.pair_code,
        claude_runtime.output_canary,
    )
    assert all(canary not in caplog.text for canary in canaries)

    initialized_services.database.engine.dispose()
    database = Path(make_url(initialized_services.database.engine.url).database or "")
    storage = b"".join(
        candidate.read_bytes()
        for candidate in (database, Path(f"{database}-wal"), Path(f"{database}-shm"))
        if candidate.exists()
    )
    for canary in canaries:
        assert canary.encode() not in storage
