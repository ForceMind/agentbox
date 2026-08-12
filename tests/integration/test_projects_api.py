from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from agentbox_core.models import AuditEvent, Job, Project
from agentbox_core.services import ControlPlaneServices
from agentbox_runtime import GitActionResult, RuntimeOperationError
from agentbox_runtime.github import MAX_PR_BODY_BYTES
from agentbox_worker.main import execute_job
from conftest import FakeProjectRuntime
from sqlalchemy import select

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
async def test_duplicate_git_mutation_idempotency_key_never_replays_job(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    initialized_services: ControlPlaneServices,
) -> None:
    csrf = await login(client, origin_headers)
    project = initialized_services.projects.reconcile_existing(("project-a",))[0]
    headers = {
        **origin_headers,
        "X-CSRF-Token": csrf,
        "Idempotency-Key": "duplicate-push-fixture-001",
    }
    first = await client.post(f"/api/v1/projects/{project.id}/git/push", headers=headers)
    second = await client.post(f"/api/v1/projects/{project.id}/git/push", headers=headers)

    assert first.status_code == second.status_code == 202
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert len([job for job in initialized_services.jobs.list() if job.type == "git.push"]) == 1


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
async def test_draft_pr_api_rejects_invalid_title_body_and_base_before_queue(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    initialized_services: ControlPlaneServices,
) -> None:
    csrf = await login(client, origin_headers)
    project = initialized_services.projects.reconcile_existing(("project-a",))[0]
    headers = {
        **origin_headers,
        "X-CSRF-Token": csrf,
        "Idempotency-Key": "draft-pr-input-fixture-001",
    }
    for payload in (
        {"title": "bad\ntitle", "body": "", "base": None},
        {"title": "Safe", "body": "x" * (MAX_PR_BODY_BYTES + 1), "base": None},
        {"title": "Safe", "body": "", "base": "--repo"},
    ):
        response = await client.post(
            f"/api/v1/projects/{project.id}/github/pull-requests",
            json=payload,
            headers=headers,
        )
        assert response.status_code == 422
    assert initialized_services.jobs.list() == ()


@pytest.mark.anyio
async def test_draft_pr_max_body_fits_inside_http_request_limit(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    initialized_services: ControlPlaneServices,
) -> None:
    csrf = await login(client, origin_headers)
    project = initialized_services.projects.reconcile_existing(("project-a",))[0]
    response = await client.post(
        f"/api/v1/projects/{project.id}/github/pull-requests",
        json={"title": "Safe", "body": "\t" * MAX_PR_BODY_BYTES, "base": "main"},
        headers={
            **origin_headers,
            "X-CSRF-Token": csrf,
            "Idempotency-Key": "draft-pr-max-body-fixture-001",
        },
    )

    assert response.status_code == 202
    assert response.json()["data"]["type"] == "github.pr.create"


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
    with initialized_services.database.transaction() as session:
        actions = tuple(session.scalars(select(AuditEvent.action)))
    assert "project_created" in actions


@pytest.mark.anyio
async def test_project_reservation_rolls_back_when_job_persistence_fails(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    initialized_services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    csrf = await login(client, origin_headers)

    def fail_enqueue(**_kwargs: Any) -> None:
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(initialized_services.jobs, "enqueue", fail_enqueue)
    with pytest.raises(RuntimeError, match="simulated database failure"):
        await client.post(
            "/api/v1/projects",
            json={"name": "Reservation Must Roll Back"},
            headers={
                **origin_headers,
                "X-CSRF-Token": csrf,
                "Idempotency-Key": "project-reservation-failure-001",
            },
        )
    assert all(
        item.display_name != "Reservation Must Roll Back"
        for item in initialized_services.projects.list()
    )


async def queued_create(services: ControlPlaneServices, name: str) -> tuple[Project, Job]:
    project = services.projects.reserve(name=name, slug=None, source_type="empty")
    job, _created = services.jobs.enqueue(
        job_type="project.create",
        requested_by="adm_fixture",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        payload={"project_key": project.relative_path},
        resource_lock_key=f"project:{project.id}",
        idempotency_key=f"worker-{project.slug}-fixture",
        request_id="req_worker_failure_fixture",
    )
    claimed = services.jobs.claim_next("worker-fixture")
    assert claimed is not None and claimed.id == job.id
    return project, claimed


@pytest.mark.anyio
async def test_workspace_failure_rolls_back_and_records_explicit_failure_audit(
    initialized_services: ControlPlaneServices,
    project_runtime: FakeProjectRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, claimed = await queued_create(initialized_services, "Filesystem Failure")
    rollbacks: list[str] = []

    async def fail_create(_request_id: str, _key: str, _operation: str) -> GitActionResult:
        raise RuntimeOperationError("PROJECT_PATH_INVALID", "Workspace creation failed")

    async def rollback(_request_id: str, _key: str, operation: str) -> GitActionResult:
        rollbacks.append(operation)
        return GitActionResult("rolled_back")

    monkeypatch.setattr(project_runtime, "create_workspace", fail_create)
    monkeypatch.setattr(project_runtime, "rollback_workspace", rollback)
    await execute_job(initialized_services, project_runtime, claimed)

    stored = initialized_services.jobs.get(claimed.id)
    assert stored is not None and stored.status == "failed"
    assert stored.error_code == "PROJECT_PATH_INVALID"
    assert initialized_services.projects.get(project.id).state == "error"
    assert rollbacks == [claimed.id]
    with initialized_services.database.transaction() as session:
        actions = tuple(session.scalars(select(AuditEvent.action)))
    assert "project_create_failed" in actions


@pytest.mark.anyio
async def test_database_failure_after_workspace_creation_triggers_runtime_rollback(
    initialized_services: ControlPlaneServices,
    project_runtime: FakeProjectRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, claimed = await queued_create(initialized_services, "Database Failure")
    rollbacks: list[str] = []

    def fail_mark_ready(_project_id: str, *, default_branch: str | None = None) -> None:
        del default_branch
        raise RuntimeError("simulated database failure")

    async def rollback(_request_id: str, _key: str, operation: str) -> GitActionResult:
        rollbacks.append(operation)
        return GitActionResult("rolled_back")

    monkeypatch.setattr(initialized_services.projects, "mark_ready", fail_mark_ready)
    monkeypatch.setattr(project_runtime, "rollback_workspace", rollback)
    await execute_job(initialized_services, project_runtime, claimed)

    stored = initialized_services.jobs.get(claimed.id)
    assert stored is not None and stored.status == "failed"
    assert stored.error_code == "JOB_EXECUTION_FAILED"
    assert initialized_services.projects.get(project.id).state == "error"
    assert rollbacks == [claimed.id]


@pytest.mark.anyio
async def test_finalize_failure_preserves_ready_workspace_without_rollback(
    initialized_services: ControlPlaneServices,
    project_runtime: FakeProjectRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, claimed = await queued_create(initialized_services, "Finalize Failure")
    rollbacks: list[str] = []

    async def fail_finalize(_request_id: str, _key: str, _operation: str) -> GitActionResult:
        raise RuntimeOperationError("PROJECT_FINALIZE_INVALID", "simulated finalize failure")

    async def rollback(_request_id: str, _key: str, operation: str) -> GitActionResult:
        rollbacks.append(operation)
        return GitActionResult("rolled_back")

    monkeypatch.setattr(project_runtime, "finalize_workspace", fail_finalize)
    monkeypatch.setattr(project_runtime, "rollback_workspace", rollback)
    await execute_job(initialized_services, project_runtime, claimed)

    stored = initialized_services.jobs.get(claimed.id)
    assert stored is not None and stored.status == "needs_attention"
    assert stored.error_code == "PROJECT_FINALIZE_REQUIRES_ATTENTION"
    assert initialized_services.projects.get(project.id, ready=True).state == "ready"
    assert rollbacks == []


@pytest.mark.anyio
async def test_rollback_failure_needs_attention_and_records_failure_audit(
    initialized_services: ControlPlaneServices,
    project_runtime: FakeProjectRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, claimed = await queued_create(initialized_services, "Rollback Failure")

    async def fail_create(_request_id: str, _key: str, _operation: str) -> GitActionResult:
        raise RuntimeOperationError("PROJECT_PATH_INVALID", "Workspace creation failed")

    async def fail_rollback(_request_id: str, _key: str, _operation: str) -> GitActionResult:
        raise RuntimeOperationError("PROJECT_PATH_INVALID", "Workspace cleanup failed")

    monkeypatch.setattr(project_runtime, "create_workspace", fail_create)
    monkeypatch.setattr(project_runtime, "rollback_workspace", fail_rollback)
    await execute_job(initialized_services, project_runtime, claimed)

    stored = initialized_services.jobs.get(claimed.id)
    assert stored is not None and stored.status == "needs_attention"
    assert stored.error_code == "PROJECT_ROLLBACK_REQUIRES_ATTENTION"
    assert initialized_services.projects.get(project.id).state == "error"
    with initialized_services.database.transaction() as session:
        event = session.scalar(
            select(AuditEvent).where(AuditEvent.action == "project_create_failed")
        )
    assert event is not None and event.result == "failed"
    assert event.metadata_json["error_code"] == "PROJECT_ROLLBACK_REQUIRES_ATTENTION"


@pytest.mark.anyio
async def test_successful_operation_with_audit_failure_needs_attention_not_double_transition(
    initialized_services: ControlPlaneServices,
    project_runtime: FakeProjectRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, claimed = await queued_create(initialized_services, "Audit Failure")

    def fail_audit(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("simulated audit failure")

    monkeypatch.setattr(initialized_services.audit, "record", fail_audit)
    await execute_job(initialized_services, project_runtime, claimed)

    stored = initialized_services.jobs.get(claimed.id)
    assert stored is not None and stored.status == "needs_attention"
    assert stored.error_code == "JOB_AUDIT_FAILED"
    assert initialized_services.projects.get(project.id, ready=True).state == "ready"


@pytest.mark.anyio
async def test_failed_operation_with_audit_failure_needs_attention_not_worker_crash(
    initialized_services: ControlPlaneServices,
    project_runtime: FakeProjectRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = initialized_services.projects.reconcile_existing(("audit-failure-project",))[0]
    job, _created = initialized_services.jobs.enqueue(
        job_type="git.pull",
        requested_by="adm_fixture",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        payload={"project_key": project.relative_path},
        resource_lock_key=f"project:{project.id}",
        idempotency_key="worker-failure-audit-fixture",
        request_id="req_worker_failure_audit_fixture",
    )
    claimed = initialized_services.jobs.claim_next("worker-failure-audit")
    assert claimed is not None and claimed.id == job.id

    async def fail_pull(_request_id: str, _project_key: str) -> GitActionResult:
        raise RuntimeOperationError("GIT_PULL_FAILED", "Pull failed")

    def fail_audit(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("simulated audit failure")

    monkeypatch.setattr(project_runtime, "pull", fail_pull)
    monkeypatch.setattr(initialized_services.audit, "record", fail_audit)
    await execute_job(initialized_services, project_runtime, claimed)

    stored = initialized_services.jobs.get(job.id)
    assert stored is not None and stored.status == "needs_attention"
    assert stored.error_code == "JOB_AUDIT_FAILED"


@pytest.mark.anyio
async def test_long_runtime_job_renews_durable_lease(
    initialized_services: ControlPlaneServices,
    project_runtime: FakeProjectRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = initialized_services.projects.reconcile_existing(("lease-project",))[0]
    job, _created = initialized_services.jobs.enqueue(
        job_type="git.pull",
        requested_by="adm_fixture",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        payload={"project_key": project.relative_path},
        resource_lock_key=f"project:{project.id}",
        idempotency_key="worker-heartbeat-runtime-fixture",
        request_id="req_worker_heartbeat_fixture",
    )
    claimed = initialized_services.jobs.claim_next("worker-heartbeat")
    assert claimed is not None and claimed.id == job.id
    heartbeats: list[str] = []
    original_heartbeat = initialized_services.jobs.heartbeat

    async def delayed_pull(_request_id: str, _project_key: str) -> GitActionResult:
        await asyncio.sleep(0.035)
        return GitActionResult("pulled", "main")

    def capture_heartbeat(job_id: str) -> None:
        heartbeats.append(job_id)
        original_heartbeat(job_id)

    monkeypatch.setattr(
        type(initialized_services.jobs),
        "heartbeat_interval_seconds",
        property(lambda _service: 0.01),
    )
    monkeypatch.setattr(initialized_services.jobs, "heartbeat", capture_heartbeat)
    monkeypatch.setattr(project_runtime, "pull", delayed_pull)
    await execute_job(initialized_services, project_runtime, claimed)

    assert len(heartbeats) >= 2
    assert set(heartbeats) == {job.id}
    stored = initialized_services.jobs.get(job.id)
    assert stored is not None and stored.status == "succeeded"
