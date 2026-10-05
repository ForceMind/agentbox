"""Authenticated, bounded Control Plane windows for the read-only work overview."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import NoReturn

import httpx
import pytest
from agentbox_api import projects as project_routes
from agentbox_core.models import ControlPlaneSession, Job, Project
from agentbox_core.services import ControlPlaneServices
from conftest import FakeClock
from sqlalchemy import select

_ENDPOINTS = ("/api/v1/jobs?scope=mine", "/api/v1/projects/recent")
_STATES = ("queued", "running", "succeeded", "failed", "cancelled", "needs_attention")


def _unexpected_call(*_args: object, **_kwargs: object) -> NoReturn:
    pytest.fail("overview reads must not observe Runtime, reconcile, or enqueue work")


@pytest.fixture(autouse=True)
def forbid_runtime_and_mutation(
    monkeypatch: pytest.MonkeyPatch,
    initialized_services: ControlPlaneServices,
) -> None:
    monkeypatch.setattr(project_routes, "_runtime", _unexpected_call)
    monkeypatch.setattr(project_routes, "_claude_runtime", _unexpected_call)
    monkeypatch.setattr(project_routes, "_reconcile", _unexpected_call)
    monkeypatch.setattr(initialized_services.projects, "reconcile_existing", _unexpected_call)
    monkeypatch.setattr(initialized_services.jobs, "enqueue", _unexpected_call)


async def _login(client: httpx.AsyncClient, origin: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "maintainer", "password": "a sufficiently long passphrase"},
        headers=origin,
    )
    assert response.status_code == 200
    return str(response.json()["data"]["user"]["id"])


def _job(index: int, user_id: str, created_at: datetime) -> Job:
    return Job(
        id=f"job_{index:032x}",
        type="git.pull",
        status=_STATES[index % len(_STATES)],
        requested_by=user_id,
        created_at=created_at,
        target_type="project",
        target_id=None,
        project_id=None,
        progress=0,
        phase="fixture",
        payload_json={"project_key": "PRIVATE-PAYLOAD-CANARY"},
        idempotency_key_digest=f"{index:064x}",
        resource_lock_key=f"fixture:{index}",
    )


def _project(index: int, created_at: datetime, updated_at: datetime) -> Project:
    return Project(
        id=f"prj_{index:032x}",
        slug=f"project-{index}",
        display_name=f"Project {index}",
        relative_path=f"private-path-{index}",
        source_type="empty",
        state=("ready", "creating", "error")[index % 3],
        created_at=created_at,
        updated_at=updated_at,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", _ENDPOINTS)
@pytest.mark.parametrize("cookie", (None, "invalid-session-canary"))
async def test_overview_windows_authenticate_before_metadata_reads(
    client: httpx.AsyncClient,
    initialized_services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
    cookie: str | None,
) -> None:
    monkeypatch.setattr(initialized_services.jobs, "list", _unexpected_call)
    monkeypatch.setattr(initialized_services.projects, "list_recent", _unexpected_call)
    if cookie is not None:
        client.cookies.set("agentbox_session", cookie)
    response = await client.get(endpoint)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", _ENDPOINTS)
@pytest.mark.parametrize("invalidation", ("expired", "revoked"))
async def test_overview_windows_reject_stale_sessions(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    initialized_services: ControlPlaneServices,
    clock: FakeClock,
    endpoint: str,
    invalidation: str,
) -> None:
    await _login(client, origin_headers)
    if invalidation == "expired":
        clock.advance(seconds=601)
    else:
        with initialized_services.database.transaction() as session:
            stored = session.scalar(select(ControlPlaneSession))
            assert stored is not None
            stored.revoked_at = clock.now().replace(tzinfo=UTC)
    response = await client.get(endpoint)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.anyio
async def test_mine_jobs_filters_before_fixed_bound_and_orders_ties_deterministically(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    initialized_services: ControlPlaneServices,
    clock: FakeClock,
) -> None:
    user_id = await _login(client, origin_headers)
    mine = [
        _job(index, user_id, clock.now() + timedelta(seconds=index // 2)) for index in range(105)
    ]
    other = [
        _job(index, "adm_previous-owner", clock.now() + timedelta(days=1))
        for index in range(200, 305)
    ]
    with initialized_services.database.transaction() as session:
        session.add_all([*mine, *other])

    # Newer foreign rows must not crowd the user's rows out before SQL LIMIT.
    # Query identities, offsets, and limits cannot replace the current Session or bound.
    response = await client.get(
        "/api/v1/jobs?scope=mine",
        params={
            "scope": "mine",
            "requested_by": "adm_previous-owner",
            "user_id": "adm_previous-owner",
            "limit": "10000",
            "offset": "100",
        },
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()["data"]
    assert set(data) == {"jobs"}
    assert [job["id"] for job in data["jobs"]] == [job.id for job in reversed(mine[5:])]
    assert {job["status"] for job in data["jobs"]} == set(_STATES)
    assert "PRIVATE-PAYLOAD-CANARY" not in response.text
    assert "adm_previous-owner" not in response.text
    assert "requested_by" not in response.text
    repeated = await client.get("/api/v1/jobs?scope=mine")
    assert repeated.json()["data"] == data

    # Existing callers without a scope keep the administrator-wide recent window.
    default = await client.get("/api/v1/jobs")
    assert default.status_code == 200
    assert [job["id"] for job in default.json()["data"]["jobs"]] == [
        job.id for job in reversed(other[5:])
    ]
    assert len(initialized_services.jobs.list(limit=1000)) == 210


@pytest.mark.anyio
async def test_mine_jobs_empty_window_does_not_expose_other_requesters(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    initialized_services: ControlPlaneServices,
    clock: FakeClock,
) -> None:
    await _login(client, origin_headers)
    with initialized_services.database.transaction() as session:
        session.add(_job(1, "adm_previous-owner", clock.now()))
    response = await client.get("/api/v1/jobs?scope=mine")
    assert response.status_code == 200
    assert response.json()["data"] == {"jobs": []}


@pytest.mark.anyio
@pytest.mark.parametrize("scope", ("all", "other", "adm_previous-owner", ""))
async def test_jobs_scope_accepts_only_the_fixed_mine_selector(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    scope: str,
) -> None:
    await _login(client, origin_headers)
    response = await client.get("/api/v1/jobs", params={"scope": scope})
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.anyio
async def test_recent_projects_are_bounded_stored_metadata_without_runtime_or_reconcile(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    initialized_services: ControlPlaneServices,
    clock: FakeClock,
) -> None:
    await _login(client, origin_headers)
    # Creation/name ordering differs from update ordering; pairs tie on updated_at.
    projects = [
        _project(
            index,
            clock.now() - timedelta(days=index),
            clock.now() - timedelta(seconds=index // 2),
        )
        for index in range(9)
    ]
    timestamp_archived = _project(100, clock.now(), clock.now() + timedelta(days=1))
    timestamp_archived.archived_at = clock.now()
    state_archived = _project(101, clock.now(), clock.now() + timedelta(days=1))
    state_archived.state = "archived"
    with initialized_services.database.transaction() as session:
        session.add_all([*projects, timestamp_archived, state_archived])
    before = [
        (project.id, project.revision, project.created_at, project.updated_at, project.state)
        for project in initialized_services.projects.list(include_archived=True)
    ]

    response = await client.get(
        "/api/v1/projects/recent", params={"limit": "1000", "include_archived": "true"}
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()["data"]
    assert set(data) == {"projects"}
    expected = [projects[index] for index in (1, 0, 3, 2, 5, 4)]
    assert [project["id"] for project in data["projects"]] == [project.id for project in expected]
    assert {project["state"] for project in data["projects"]} == {"ready", "creating", "error"}
    for observed, stored in zip(data["projects"], expected, strict=True):
        assert datetime.fromisoformat(observed["created_at"]) == stored.created_at.replace(
            tzinfo=UTC
        )
        assert datetime.fromisoformat(observed["updated_at"]) == stored.updated_at.replace(
            tzinfo=UTC
        )
        assert observed["git"] is observed["github"] is observed["claude_state"] is None
    assert "private-path" not in response.text
    assert "relative_path" not in response.text
    repeated = await client.get("/api/v1/projects/recent")
    assert repeated.json()["data"] == data
    after = [
        (project.id, project.revision, project.created_at, project.updated_at, project.state)
        for project in initialized_services.projects.list(include_archived=True)
    ]
    assert after == before


@pytest.mark.anyio
async def test_recent_projects_reobserve_real_metadata_updates_without_recording_visits(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    initialized_services: ControlPlaneServices,
    clock: FakeClock,
) -> None:
    await _login(client, origin_headers)
    first = initialized_services.projects.reserve(name="First", slug=None, source_type="empty")
    clock.advance(seconds=10)
    second = initialized_services.projects.reserve(name="Second", slug=None, source_type="empty")
    initial = await client.get("/api/v1/projects/recent")
    assert [project["id"] for project in initial.json()["data"]["projects"]] == [
        second.id,
        first.id,
    ]
    clock.advance(seconds=10)
    initialized_services.projects.mark_ready(first.id, default_branch="main")
    updated_at = clock.now().replace(tzinfo=UTC)
    clock.advance(seconds=10)
    refreshed = await client.get("/api/v1/projects/recent")
    observed = refreshed.json()["data"]["projects"]
    assert [project["id"] for project in observed] == [first.id, second.id]
    assert datetime.fromisoformat(observed[0]["updated_at"]) == updated_at
    assert datetime.fromisoformat(observed[0]["created_at"]) == first.created_at.replace(tzinfo=UTC)
    assert observed[0]["state"] == "ready"
    assert observed[0]["default_branch"] == "main"


@pytest.mark.anyio
async def test_recent_projects_empty_catalog_stays_empty_without_runtime_discovery(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    initialized_services: ControlPlaneServices,
) -> None:
    await _login(client, origin_headers)
    response = await client.get("/api/v1/projects/recent")
    assert response.status_code == 200
    assert response.json()["data"] == {"projects": []}
    assert initialized_services.projects.list(include_archived=True) == ()
