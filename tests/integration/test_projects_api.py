from __future__ import annotations

import httpx
import pytest
from agentbox_core.services import ControlPlaneServices
from agentbox_worker.main import execute_job
from conftest import FakeProjectRuntime

PASSWORD = "a sufficiently long passphrase"


async def login(client: httpx.AsyncClient, origin: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "maintainer", "password": PASSWORD},
        headers=origin,
    )
    return str(response.json()["data"]["csrf_token"])


@pytest.mark.anyio
async def test_project_create_is_formal_idempotent_and_never_accepts_a_path(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
) -> None:
    assert (await client.get("/api/v1/projects")).status_code == 401
    csrf = await login(client, origin_headers)
    headers = {
        **origin_headers,
        "X-CSRF-Token": csrf,
        "Idempotency-Key": "project-create-fixture-001",
    }
    created = await client.post("/api/v1/projects", json={"name": "Safe Project"}, headers=headers)
    repeated = await client.post("/api/v1/projects", json={"name": "Safe Project"}, headers=headers)
    assert created.status_code == repeated.status_code == 202
    assert created.json()["data"]["project"]["id"].startswith("prj_")
    assert created.json()["data"]["job"]["id"] == repeated.json()["data"]["job"]["id"]
    assert "relative_path" not in created.text
    invalid = await client.post(
        "/api/v1/projects",
        json={"name": "Escape", "slug": "../escape", "path": "/etc"},
        headers={**headers, "Idempotency-Key": "project-create-fixture-002"},
    )
    assert invalid.status_code == 422


@pytest.mark.anyio
async def test_clone_and_git_mutations_are_queued_without_raw_runtime_output(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    initialized_services: ControlPlaneServices,
    project_runtime: FakeProjectRuntime,
) -> None:
    csrf = await login(client, origin_headers)
    headers = {
        **origin_headers,
        "X-CSRF-Token": csrf,
        "Idempotency-Key": "project-clone-fixture-001",
    }
    rejected = await client.post(
        "/api/v1/projects/clone", json={"repository_url": "file:///tmp/repo"}, headers=headers
    )
    assert rejected.status_code == 422
    clone = await client.post(
        "/api/v1/projects/clone",
        json={"repository_url": "https://github.com/ForceMind/agentbox.git"},
        headers=headers,
    )
    assert clone.status_code == 202
    project_id = clone.json()["data"]["project"]["id"]
    initialized_services.projects.mark_ready(project_id, default_branch="main")
    pull = await client.post(
        f"/api/v1/projects/{project_id}/git/pull",
        headers={**headers, "Idempotency-Key": "project-pull-fixture-001"},
    )
    assert pull.status_code == 202
    assert project_runtime.calls == []
    assert pull.headers["cache-control"] == "no-store"


@pytest.mark.anyio
async def test_project_detail_and_github_status_are_authenticated_no_store(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
) -> None:
    await login(client, origin_headers)
    projects = await client.get("/api/v1/projects")
    project_id = projects.json()["data"]["projects"][0]["id"]
    detail = await client.get(f"/api/v1/projects/{project_id}")
    github = await client.get("/api/v1/github")
    assert detail.status_code == github.status_code == 200
    assert detail.headers["cache-control"] == github.headers["cache-control"] == "no-store"
    assert detail.json()["data"]["git"]["branch"] == "main"
    assert github.json()["data"]["authentication"] == "authenticated"


@pytest.mark.anyio
async def test_worker_executes_typed_project_job_and_marks_project_ready(
    initialized_services: ControlPlaneServices,
    project_runtime: FakeProjectRuntime,
) -> None:
    project = initialized_services.projects.reserve(
        name="Worker Project", slug=None, source_type="empty"
    )
    job, _created = initialized_services.jobs.enqueue(
        job_type="project.create",
        requested_by="adm_fixture",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        payload={"project_key": project.relative_path},
        resource_lock_key=f"project:{project.id}",
        idempotency_key="worker-project-fixture-001",
        request_id="req_worker_fixture",
    )
    claimed = initialized_services.jobs.claim_next("worker-fixture")
    assert claimed is not None and claimed.id == job.id
    await execute_job(initialized_services, project_runtime, claimed)
    assert initialized_services.projects.get(project.id, ready=True).state == "ready"
    assert initialized_services.jobs.get(job.id).status == "succeeded"  # type: ignore[union-attr]
