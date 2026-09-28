from __future__ import annotations

import httpx
import pytest
from agentbox_core.models import AuditEvent
from agentbox_core.services import ControlPlaneServices
from conftest import FakeProjectRuntime
from sqlalchemy import select
from sqlalchemy.exc import OperationalError


async def login(client: httpx.AsyncClient, origin: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "maintainer", "password": "a sufficiently long passphrase"},
        headers=origin,
    )
    assert response.status_code == 200
    return str(response.json()["data"]["csrf_token"])


@pytest.mark.anyio
async def test_favorite_api_uses_current_session_cas_and_never_calls_runtime(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    initialized_services: ControlPlaneServices,
    project_runtime: FakeProjectRuntime,
) -> None:
    project = initialized_services.projects.reserve(
        name="Favorite API fixture", slug=None, source_type="empty"
    )
    url = f"/api/v1/project-favorites/{project.id}"
    assert (await client.get("/api/v1/project-favorites")).status_code == 401
    csrf = await login(client, origin_headers)
    headers = {**origin_headers, "X-CSRF-Token": csrf}
    empty = await client.get("/api/v1/project-favorites")
    assert empty.status_code == 200
    assert empty.headers["cache-control"] == "no-store"
    assert empty.json()["data"]["favorites"] == []

    created = await client.put(
        url, json={"favorite": True, "expected_revision": 0}, headers=headers
    )
    assert created.status_code == 200
    assert created.headers["cache-control"] == "no-store"
    assert created.json()["data"]["project_id"] == project.id
    assert created.json()["data"]["favorite"] is True
    assert created.json()["data"]["revision"] == 1
    assert "Favorite API fixture" not in created.text
    assert "relative_path" not in created.text
    same = await client.put(url, json={"favorite": True, "expected_revision": 1}, headers=headers)
    assert same.status_code == 200 and same.json()["data"]["revision"] == 1
    stale = await client.put(url, json={"favorite": False, "expected_revision": 0}, headers=headers)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "PROJECT_FAVORITE_CONFLICT"
    observed = await client.get("/api/v1/project-favorites")
    assert observed.json()["data"]["favorites"][0]["revision"] == 1
    removed = await client.put(
        url, json={"favorite": False, "expected_revision": 1}, headers=headers
    )
    assert removed.status_code == 200 and removed.json()["data"]["revision"] == 2
    assert removed.json()["data"]["favorite"] is False
    assert project_runtime.calls == []
    with initialized_services.database.transaction() as session:
        audit = tuple(
            session.scalars(select(AuditEvent).where(AuditEvent.action == "project.favorite.set"))
        )
    assert len(audit) == 3
    assert all(row.target_id == project.id for row in audit)


@pytest.mark.anyio
async def test_favorite_api_rejects_foreign_origin_csrf_unknown_project_and_extra_body(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    initialized_services: ControlPlaneServices,
    project_runtime: FakeProjectRuntime,
) -> None:
    project = initialized_services.projects.reserve(
        name="Favorite rejection", slug=None, source_type="empty"
    )
    csrf = await login(client, origin_headers)
    url = f"/api/v1/project-favorites/{project.id}"
    body = {"favorite": True, "expected_revision": 0}
    foreign = await client.put(url, json=body, headers={"Origin": "https://evil.invalid"})
    assert foreign.status_code == 403
    missing_csrf = await client.put(url, json=body, headers=origin_headers)
    assert missing_csrf.status_code == 403
    invalid = await client.put(
        url,
        json={**body, "path": "/etc/passwd"},
        headers={**origin_headers, "X-CSRF-Token": csrf},
    )
    assert invalid.status_code == 422
    missing = await client.put(
        f"/api/v1/project-favorites/prj_{'f' * 32}",
        json=body,
        headers={**origin_headers, "X-CSRF-Token": csrf},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PROJECT_NOT_FOUND"
    assert project_runtime.calls == []


@pytest.mark.anyio
async def test_favorite_api_reports_database_unavailability_without_detail(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    initialized_services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = initialized_services.projects.reserve(
        name="Favorite unavailable", slug=None, source_type="empty"
    )
    csrf = await login(client, origin_headers)
    failure = OperationalError("SELECT private table", {}, RuntimeError("private database detail"))

    def fail(*args: object, **kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(initialized_services.favorites, "list", fail)
    observed = await client.get("/api/v1/project-favorites")
    assert observed.status_code == 503
    assert observed.json()["error"]["code"] == "CONTROL_PLANE_NOT_READY"
    assert "private database detail" not in observed.text
    monkeypatch.setattr(initialized_services.favorites, "set", fail)
    changed = await client.put(
        f"/api/v1/project-favorites/{project.id}",
        json={"favorite": True, "expected_revision": 0},
        headers={**origin_headers, "X-CSRF-Token": csrf},
    )
    assert changed.status_code == 503
    assert changed.json()["error"]["code"] == "CONTROL_PLANE_NOT_READY"
    assert "private database detail" not in changed.text
