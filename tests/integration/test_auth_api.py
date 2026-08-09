from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from agentbox_core.models import AdminUser, AuditEvent, ControlPlaneSession
from agentbox_core.services import ControlPlaneServices
from conftest import FakeClock
from sqlalchemy import select

PASSWORD = "a sufficiently long passphrase"


async def login(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    *,
    username: str = "maintainer",
    password: str = PASSWORD,
) -> httpx.Response:
    return await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers=origin_headers,
    )


@pytest.mark.anyio
async def test_login_me_and_cookie_security(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
) -> None:
    response = await login(client, origin_headers)

    assert response.status_code == 200
    assert response.json()["data"]["user"]["username"] == "maintainer"
    csrf_token = response.json()["data"]["csrf_token"]
    assert csrf_token
    cookie = response.headers["set-cookie"]
    assert "agentbox_session=" in cookie
    assert "HttpOnly" in cookie
    assert "Path=/" in cookie
    assert "SameSite=strict" in cookie
    assert "Secure" not in cookie
    assert response.headers["cache-control"] == "no-store"

    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["data"]["csrf_token"] == csrf_token


@pytest.mark.anyio
async def test_invalid_login_errors_do_not_enumerate_users(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
) -> None:
    wrong = await login(client, origin_headers, password="wrong password value")
    missing = await login(
        client,
        origin_headers,
        username="nobody",
        password="wrong password value",
    )

    assert wrong.status_code == missing.status_code == 401
    assert wrong.json()["error"]["code"] == missing.json()["error"]["code"]
    assert wrong.json()["error"]["message"] == missing.json()["error"]["message"]
    assert wrong.json()["error"]["message"] == "Invalid credentials"


@pytest.mark.anyio
async def test_inactive_user_receives_generic_error(
    client: httpx.AsyncClient,
    initialized_services: ControlPlaneServices,
    origin_headers: dict[str, str],
) -> None:
    with initialized_services.database.transaction() as session:
        admin = session.scalar(select(AdminUser))
        assert admin is not None
        admin.is_active = False

    response = await login(client, origin_headers)

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid credentials"


@pytest.mark.anyio
async def test_login_rate_limit_is_deterministic_and_recovers(
    client: httpx.AsyncClient,
    clock: FakeClock,
    origin_headers: dict[str, str],
) -> None:
    for _attempt in range(5):
        response = await login(client, origin_headers, password="wrong password value")
        assert response.status_code == 401

    limited = await login(client, origin_headers)
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0

    clock.advance(seconds=301)
    recovered = await login(client, origin_headers)
    assert recovered.status_code == 200


@pytest.mark.anyio
async def test_login_requires_exact_allowed_origin(client: httpx.AsyncClient) -> None:
    missing = await client.post(
        "/api/v1/auth/login",
        json={"username": "maintainer", "password": PASSWORD},
    )
    hostile = await client.post(
        "/api/v1/auth/login",
        json={"username": "maintainer", "password": PASSWORD},
        headers={"Origin": "https://attacker.invalid"},
    )

    assert missing.status_code == hostile.status_code == 403
    assert missing.json()["error"]["code"] == "AUTH_ORIGIN_INVALID"

    hostile_host = await client.post(
        "/api/v1/auth/login",
        json={"username": "maintainer", "password": PASSWORD},
        headers={"Origin": "http://testserver", "Host": "attacker.invalid"},
    )
    assert hostile_host.status_code == 403


@pytest.mark.anyio
async def test_logout_requires_session_bound_csrf(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
) -> None:
    first = await login(client, origin_headers)
    first_csrf = first.json()["data"]["csrf_token"]
    second = await login(client, origin_headers)
    second_csrf = second.json()["data"]["csrf_token"]
    assert first_csrf != second_csrf

    missing = await client.post("/api/v1/auth/logout", headers=origin_headers)
    wrong_session = await client.post(
        "/api/v1/auth/logout",
        headers={**origin_headers, "X-CSRF-Token": first_csrf},
    )
    valid = await client.post(
        "/api/v1/auth/logout",
        headers={**origin_headers, "X-CSRF-Token": second_csrf},
    )

    assert missing.status_code == wrong_session.status_code == 403
    assert valid.status_code == 204
    assert "Max-Age=0" in valid.headers["set-cookie"]
    assert (await client.get("/api/v1/auth/me")).status_code == 401


@pytest.mark.anyio
async def test_session_fixation_value_is_replaced(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
) -> None:
    client.cookies.set("agentbox_session", "attacker-controlled")
    response = await login(client, origin_headers)

    assert response.status_code == 200
    assert response.cookies["agentbox_session"] != "attacker-controlled"


@pytest.mark.anyio
async def test_expired_and_revoked_sessions_are_rejected(
    client: httpx.AsyncClient,
    clock: FakeClock,
    initialized_services: ControlPlaneServices,
    origin_headers: dict[str, str],
) -> None:
    response = await login(client, origin_headers)
    token = response.cookies["agentbox_session"]
    clock.advance(seconds=601)
    assert (await client.get("/api/v1/auth/me")).status_code == 401

    clock.advance(seconds=-601)
    response = await login(client, origin_headers)
    token = response.cookies["agentbox_session"]
    csrf = response.json()["data"]["csrf_token"]
    assert (
        await client.post(
            "/api/v1/auth/logout",
            headers={**origin_headers, "X-CSRF-Token": csrf},
        )
    ).status_code == 204
    client.cookies.set("agentbox_session", token)
    assert (await client.get("/api/v1/auth/me")).status_code == 401

    with initialized_services.database.transaction() as session:
        assert session.scalar(
            select(ControlPlaneSession).where(ControlPlaneSession.revoked_at.is_not(None))
        )


@pytest.mark.anyio
async def test_sliding_idle_updates_do_not_extend_absolute_expiry(
    client: httpx.AsyncClient,
    clock: FakeClock,
    origin_headers: dict[str, str],
) -> None:
    assert (await login(client, origin_headers)).status_code == 200
    for _step in range(6):
        clock.advance(seconds=500)
        assert (await client.get("/api/v1/auth/me")).status_code == 200

    clock.advance(seconds=601)
    assert (await client.get("/api/v1/auth/me")).status_code == 401


@pytest.mark.anyio
async def test_malformed_cookie_and_sql_injection_style_username_are_safe(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
) -> None:
    client.cookies.set("agentbox_session", "x" * 129)
    assert (await client.get("/api/v1/auth/me")).status_code == 401

    response = await login(client, origin_headers, username="' OR 1=1 --")
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid credentials"


@pytest.mark.anyio
async def test_oversized_and_unknown_login_inputs_are_bounded(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
) -> None:
    oversized_username = "user" + ("x" * 100)
    validation = await login(client, origin_headers, username=oversized_username)
    assert validation.status_code == 422
    assert oversized_username not in validation.text

    unknown = await client.post(
        "/api/v1/auth/login",
        json={"username": "maintainer", "password": PASSWORD, "command": "id"},
        headers=origin_headers,
    )
    assert unknown.status_code == 422
    assert "command" in unknown.text

    huge = await client.post(
        "/api/v1/auth/login",
        content=b"x" * 20_000,
        headers={**origin_headers, "Content-Type": "application/json"},
    )
    assert huge.status_code == 413
    assert huge.json()["error"]["code"] == "REQUEST_BODY_TOO_LARGE"

    async def chunked_body() -> AsyncIterator[bytes]:
        yield b"x" * 9000
        yield b"y" * 9000

    chunked = await client.post(
        "/api/v1/auth/login",
        content=chunked_body(),
        headers={**origin_headers, "Content-Type": "application/json"},
    )
    assert chunked.status_code == 413
    assert chunked.json()["error"]["code"] == "REQUEST_BODY_TOO_LARGE"


@pytest.mark.anyio
async def test_password_and_session_values_never_enter_audit_metadata(
    client: httpx.AsyncClient,
    initialized_services: ControlPlaneServices,
    origin_headers: dict[str, str],
) -> None:
    canary = "audit-password-canary"
    await login(client, origin_headers, password=canary)
    success = await login(client, origin_headers)
    raw_session = success.cookies["agentbox_session"]
    raw_csrf = success.json()["data"]["csrf_token"]

    with initialized_services.database.transaction() as session:
        rendered = "\n".join(
            repr(event.metadata_json) for event in session.scalars(select(AuditEvent)).all()
        )

    assert canary not in rendered
    assert raw_session not in rendered
    assert raw_csrf not in rendered
