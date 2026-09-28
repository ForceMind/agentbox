from __future__ import annotations

import httpx
import pytest
from agentbox_core.services import ControlPlaneServices
from conftest import FakeProjectRuntime
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
async def test_label_api_catalog_assignment_edit_and_delete_are_session_scoped(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    initialized_services: ControlPlaneServices,
    project_runtime: FakeProjectRuntime,
) -> None:
    project = initialized_services.projects.reserve(
        name="Label API fixture", slug=None, source_type="empty"
    )
    base = "/api/v1/project-labels"
    assert (await client.get(base)).status_code == 401
    csrf = await login(client, origin_headers)
    headers = {**origin_headers, "X-CSRF-Token": csrf}
    empty = await client.get(base)
    assert empty.status_code == 200 and empty.json()["data"]["labels"] == []
    assert empty.headers["cache-control"] == "no-store"
    created = await client.post(
        base, json={"name": "  Design\tReview  ", "color": "sky"}, headers=headers
    )
    assert created.status_code == 200
    label = created.json()["data"]
    assert label["name"] == "Design Review" and label["revision"] == 1
    assert label["id"].startswith("lbl_")
    duplicate = await client.post(
        base, json={"name": "design review", "color": "red"}, headers=headers
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "NAVIGATION_LABEL_NAME_TAKEN"
    assert "Label API fixture" not in created.text and "relative_path" not in created.text
    assignment_url = f"{base}/projects/{project.id}/{label['id']}"
    current = await client.get(f"{base}/projects/{project.id}")
    assert current.status_code == 200 and current.json()["data"]["revision"] == 0
    assigned = await client.put(
        assignment_url, json={"assigned": True, "expected_revision": 0}, headers=headers
    )
    assert assigned.status_code == 200
    assert assigned.json()["data"]["labels"][0]["id"] == label["id"]
    assert assigned.json()["data"]["revision"] == 1
    same = await client.put(
        assignment_url, json={"assigned": True, "expected_revision": 1}, headers=headers
    )
    assert same.status_code == 200 and same.json()["data"]["revision"] == 1
    stale = await client.put(
        assignment_url, json={"assigned": False, "expected_revision": 0}, headers=headers
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "PROJECT_LABEL_CONFLICT"
    edited = await client.put(
        f"{base}/{label['id']}",
        json={"name": "DESIGN REVIEW", "color": "red", "expected_revision": 1},
        headers=headers,
    )
    assert edited.status_code == 200 and edited.json()["data"]["revision"] == 2
    stale_edit = await client.put(
        f"{base}/{label['id']}",
        json={"name": "stale", "color": "red", "expected_revision": 1},
        headers=headers,
    )
    assert stale_edit.status_code == 409
    assert stale_edit.json()["error"]["code"] == "NAVIGATION_LABEL_CONFLICT"
    projected = await client.get(f"{base}/projects/{project.id}")
    assert projected.json()["data"]["labels"][0]["name"] == "DESIGN REVIEW"
    impact = await client.get(f"{base}/{label['id']}/delete-impact")
    assert impact.status_code == 200 and impact.json()["data"]["affected_project_count"] == 1
    removed = await client.post(
        f"{base}/{label['id']}/delete", json={"expected_revision": 2}, headers=headers
    )
    assert removed.status_code == 200 and removed.json()["data"]["affected_project_count"] == 1
    old_delete = await client.post(
        f"{base}/{label['id']}/delete", json={"expected_revision": 2}, headers=headers
    )
    assert old_delete.status_code == 404
    cleared = await client.get(f"{base}/projects/{project.id}")
    assert cleared.json()["data"]["revision"] == 2 and cleared.json()["data"]["labels"] == []
    assert project_runtime.calls == []


@pytest.mark.anyio
async def test_label_api_rejects_origin_csrf_extra_fields_and_unknown_project(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    initialized_services: ControlPlaneServices,
    project_runtime: FakeProjectRuntime,
) -> None:
    project = initialized_services.projects.reserve(
        name="Label rejection", slug=None, source_type="empty"
    )
    csrf = await login(client, origin_headers)
    base = "/api/v1/project-labels"
    body = {"name": "Urgent", "color": "red"}
    foreign = await client.post(base, json=body, headers={"Origin": "https://evil.invalid"})
    assert foreign.status_code == 403
    missing_csrf = await client.post(base, json=body, headers=origin_headers)
    assert missing_csrf.status_code == 403
    invalid = await client.post(
        base,
        json={**body, "path": "/etc/passwd"},
        headers={**origin_headers, "X-CSRF-Token": csrf},
    )
    assert invalid.status_code == 422
    created = await client.post(base, json=body, headers={**origin_headers, "X-CSRF-Token": csrf})
    assert created.status_code == 200
    label_id = created.json()["data"]["id"]
    no_assignment_csrf = await client.put(
        f"{base}/projects/{project.id}/{label_id}",
        json={"assigned": True, "expected_revision": 0},
        headers=origin_headers,
    )
    assert no_assignment_csrf.status_code == 403
    foreign_delete = await client.post(
        f"{base}/{label_id}/delete",
        json={"expected_revision": 1},
        headers={"Origin": "https://evil.invalid", "X-CSRF-Token": csrf},
    )
    assert foreign_delete.status_code == 403
    missing = await client.put(
        f"{base}/projects/prj_{'f' * 32}/{label_id}",
        json={"assigned": True, "expected_revision": 0},
        headers={**origin_headers, "X-CSRF-Token": csrf},
    )
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "PROJECT_NOT_FOUND"
    assert (await client.get(f"{base}/projects/{project.id}")).status_code == 200
    assert project_runtime.calls == []


@pytest.mark.anyio
async def test_label_api_hides_database_failure_details(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    initialized_services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    csrf = await login(client, origin_headers)
    failure = OperationalError("SELECT private table", {}, RuntimeError("private database detail"))

    def fail(*args: object, **kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(initialized_services.navigation_labels, "list_catalog", fail)
    observed = await client.get("/api/v1/project-labels")
    assert observed.status_code == 503
    assert observed.json()["error"]["code"] == "CONTROL_PLANE_NOT_READY"
    assert "private database detail" not in observed.text
    monkeypatch.setattr(initialized_services.navigation_labels, "create", fail)
    changed = await client.post(
        "/api/v1/project-labels",
        json={"name": "Safe", "color": "sky"},
        headers={**origin_headers, "X-CSRF-Token": csrf},
    )
    assert changed.status_code == 503 and "private database detail" not in changed.text
