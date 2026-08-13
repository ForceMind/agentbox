from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from agentbox_api.main import create_app
from agentbox_core.configuration import Environment, Settings
from agentbox_core.models import (
    AdminUser,
    AuditEvent,
    ControlPlaneSession,
    LoginRateLimitBucket,
)
from agentbox_core.security import PasswordManager, source_fingerprint
from agentbox_core.services import ControlPlaneServices, build_services
from conftest import (
    FakeClaudeRuntime,
    FakeClock,
    FakeCodexRuntime,
    FakeProjectRuntime,
    migrate_database,
)
from pydantic import SecretStr
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
async def test_argon2_verify_runs_outside_request_event_loop(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    password_manager: PasswordManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_loop_thread = threading.get_ident()
    verify_threads: list[int] = []
    original_verify = password_manager.verify

    def tracked_verify(encoded_hash: str, password: str) -> bool:
        verify_threads.append(threading.get_ident())
        return original_verify(encoded_hash, password)

    monkeypatch.setattr(password_manager, "verify", tracked_verify)

    response = await login(client, origin_headers)

    assert response.status_code == 200
    assert verify_threads
    assert all(thread_id != event_loop_thread for thread_id in verify_threads)


@pytest.mark.anyio
async def test_argon2_login_work_has_bounded_concurrency(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    password_manager: PasswordManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_verify = password_manager.verify
    state_lock = threading.Lock()
    two_entered = threading.Event()
    release = threading.Event()
    active = 0
    calls = 0
    maximum_active = 0

    def tracked_verify(encoded_hash: str, password: str) -> bool:
        nonlocal active, calls, maximum_active
        with state_lock:
            active += 1
            calls += 1
            maximum_active = max(maximum_active, active)
            if active == 2:
                two_entered.set()
        try:
            if not release.wait(timeout=2):
                raise AssertionError("test did not release bounded Argon2 work")
            return original_verify(encoded_hash, password)
        finally:
            with state_lock:
                active -= 1

    monkeypatch.setattr(password_manager, "verify", tracked_verify)
    requests = [
        asyncio.create_task(
            login(
                client,
                origin_headers,
                username=f"missing-{index}",
                password="wrong password value",
            )
        )
        for index in range(3)
    ]

    reached_capacity = await asyncio.to_thread(two_entered.wait, 2)
    with state_lock:
        calls_before_release = calls
        maximum_before_release = maximum_active
    release.set()
    responses = await asyncio.gather(*requests)

    assert reached_capacity is True
    assert calls_before_release == 2
    assert maximum_before_release == 2
    assert calls == 3
    assert maximum_active == 2
    assert all(response.status_code == 401 for response in responses)


@pytest.mark.anyio
async def test_rate_limited_login_skips_argon2_verify(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    password_manager: PasswordManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_verify = password_manager.verify
    verify_calls = 0

    def tracked_verify(encoded_hash: str, password: str) -> bool:
        nonlocal verify_calls
        verify_calls += 1
        return original_verify(encoded_hash, password)

    monkeypatch.setattr(password_manager, "verify", tracked_verify)
    for _attempt in range(5):
        assert (
            await login(client, origin_headers, password="wrong password value")
        ).status_code == 401

    calls_before_lock_rejection = verify_calls
    limited = await login(client, origin_headers)

    assert limited.status_code == 429
    assert calls_before_lock_rejection == 5
    assert verify_calls == calls_before_lock_rejection


@pytest.mark.anyio
async def test_missing_user_uses_dummy_verify_when_not_rate_limited(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    password_manager: PasswordManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_verify = password_manager.verify
    event_loop_thread = threading.get_ident()
    verified_calls: list[tuple[str, int]] = []

    def tracked_verify(encoded_hash: str, password: str) -> bool:
        verified_calls.append((encoded_hash, threading.get_ident()))
        return original_verify(encoded_hash, password)

    monkeypatch.setattr(password_manager, "verify", tracked_verify)

    response = await login(
        client,
        origin_headers,
        username="missing-admin",
        password="wrong password value",
    )

    assert response.status_code == 401
    assert len(verified_calls) == 1
    assert verified_calls[0][0] == password_manager.dummy_hash
    assert verified_calls[0][1] != event_loop_thread


@pytest.mark.anyio
async def test_password_rehash_runs_outside_request_event_loop(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    password_manager: PasswordManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_loop_thread = threading.get_ident()
    hash_threads: list[int] = []
    original_hash = password_manager.hash

    def tracked_hash(password: str) -> str:
        hash_threads.append(threading.get_ident())
        return original_hash(password)

    monkeypatch.setattr(password_manager, "needs_rehash", lambda encoded_hash: True)
    monkeypatch.setattr(password_manager, "hash", tracked_hash)

    response = await login(client, origin_headers)

    assert response.status_code == 200
    assert hash_threads
    assert all(thread_id != event_loop_thread for thread_id in hash_threads)


@pytest.mark.anyio
async def test_event_loop_remains_schedulable_while_argon2_verify_runs(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    password_manager: PasswordManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_verify = password_manager.verify
    verify_started = threading.Event()
    release_verify = threading.Event()

    def blocking_verify(encoded_hash: str, password: str) -> bool:
        verify_started.set()
        if not release_verify.wait(timeout=2):
            raise AssertionError("event loop did not release test Argon2 work")
        return original_verify(encoded_hash, password)

    monkeypatch.setattr(password_manager, "verify", blocking_verify)
    login_request = asyncio.create_task(
        login(client, origin_headers, password="wrong password value")
    )
    started = await asyncio.to_thread(verify_started.wait, 2)

    try:
        health = await asyncio.wait_for(client.get("/healthz"), timeout=1)
    finally:
        release_verify.set()
    response = await login_request

    assert started is True
    assert health.status_code == 200
    assert response.status_code == 401


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
async def test_missing_inactive_wrong_and_locked_accounts_do_not_enumerate(
    client: httpx.AsyncClient,
    initialized_services: ControlPlaneServices,
    origin_headers: dict[str, str],
) -> None:
    wrong = await login(client, origin_headers, password="wrong password value")
    missing = await login(
        client,
        origin_headers,
        username="missing-account",
        password="wrong password value",
    )
    with initialized_services.database.transaction() as session:
        admin = session.scalar(select(AdminUser))
        assert admin is not None
        admin.is_active = False
    inactive = await login(client, origin_headers)
    with initialized_services.database.transaction() as session:
        admin = session.scalar(select(AdminUser))
        assert admin is not None
        admin.is_active = True

    public_errors = [response.json()["error"] for response in (wrong, missing, inactive)]
    assert [response.status_code for response in (wrong, missing, inactive)] == [401, 401, 401]
    assert all(error == public_errors[0] for error in public_errors)
    assert public_errors[0]["code"] == "AUTH_INVALID_CREDENTIALS"

    for username in ("maintainer", "missing-account"):
        for index in range(5):
            initialized_services.rate_limits.register_failure(username, f"198.51.100.{100 + index}")
    locked_existing = await login(client, origin_headers)
    locked_missing = await login(
        client,
        origin_headers,
        username="missing-account",
        password="wrong password value",
    )
    assert locked_existing.status_code == locked_missing.status_code == 429
    assert locked_existing.json()["error"] == locked_missing.json()["error"]


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
    await login(client, origin_headers)
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
async def test_local_password_change_invalidates_old_sessions_csrf_and_password(
    client: httpx.AsyncClient,
    initialized_services: ControlPlaneServices,
    origin_headers: dict[str, str],
) -> None:
    first = await login(client, origin_headers)
    first_token = first.cookies["agentbox_session"]
    first_csrf = first.json()["data"]["csrf_token"]
    second = await login(client, origin_headers)
    second_token = second.cookies["agentbox_session"]
    second_csrf = second.json()["data"]["csrf_token"]

    assert (
        initialized_services.admin.change_password(
            PASSWORD,
            "a different sufficiently long passphrase",
            request_id="req_password_session_regression",
        )
        == 2
    )

    for token, csrf in ((first_token, first_csrf), (second_token, second_csrf)):
        client.cookies.set("agentbox_session", token)
        assert (await client.get("/api/v1/auth/me")).status_code == 401
        rejected_csrf = await client.post(
            "/api/v1/auth/logout",
            headers={**origin_headers, "X-CSRF-Token": csrf},
        )
        assert rejected_csrf.status_code == 401

    assert (await login(client, origin_headers, password=PASSWORD)).status_code == 401
    assert (
        await login(
            client,
            origin_headers,
            password="a different sufficiently long passphrase",
        )
    ).status_code == 200


@pytest.mark.anyio
async def test_password_change_wins_against_login_that_verified_the_old_hash(
    client: httpx.AsyncClient,
    initialized_services: ControlPlaneServices,
    origin_headers: dict[str, str],
    password_manager: PasswordManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = "127.0.0.1"
    initialized_services.rate_limits.register_failure("maintainer", source)
    account_key, source_key, combined_key = initialized_services.rate_limits._keys(
        "maintainer", source
    )
    original_verify = password_manager.verify
    original_register_success = initialized_services.rate_limits.register_success
    old_password_verified = threading.Event()
    release_stale_login = threading.Event()
    coordination_lock = threading.Lock()
    login_verify_intercepted = False
    registered_successes: list[tuple[str, str]] = []

    def pause_first_successful_old_password_verify(
        encoded_hash: str, supplied_password: str
    ) -> bool:
        nonlocal login_verify_intercepted
        verified = original_verify(encoded_hash, supplied_password)
        should_pause = False
        if verified and supplied_password == PASSWORD:
            with coordination_lock:
                if not login_verify_intercepted:
                    login_verify_intercepted = True
                    should_pause = True
        if should_pause:
            old_password_verified.set()
            if not release_stale_login.wait(timeout=5):
                raise AssertionError("test did not release the stale Login")
        return verified

    def track_register_success(username: str, source_identifier: str) -> None:
        registered_successes.append((username, source_identifier))
        original_register_success(username, source_identifier)

    monkeypatch.setattr(password_manager, "verify", pause_first_successful_old_password_verify)
    monkeypatch.setattr(
        initialized_services.rate_limits, "register_success", track_register_success
    )
    stale_login = asyncio.create_task(login(client, origin_headers))
    assert await asyncio.to_thread(old_password_verified.wait, 5)

    changed = await asyncio.to_thread(
        initialized_services.admin.change_password,
        PASSWORD,
        "a different sufficiently long passphrase",
        request_id="req_password_change_wins",
    )
    assert changed == 0
    release_stale_login.set()
    stale_response = await asyncio.wait_for(stale_login, timeout=5)

    assert stale_response.status_code == 401
    assert stale_response.json()["error"] == {
        "code": "AUTH_INVALID_CREDENTIALS",
        "message": "Invalid credentials",
        "category": "unauthenticated",
        "retryable": False,
        "details": {},
    }
    assert registered_successes == []
    with initialized_services.database.transaction() as session:
        assert session.scalar(
            select(ControlPlaneSession).where(ControlPlaneSession.revoked_at.is_(None))
        ) is None
        account_bucket = session.get(LoginRateLimitBucket, account_key)
        combined_bucket = session.get(LoginRateLimitBucket, combined_key)
        assert account_bucket is not None
        assert combined_bucket is not None
        assert len(account_bucket.failure_timestamps) == 2
        assert len(combined_bucket.failure_timestamps) == 2
        source_bucket = session.get(LoginRateLimitBucket, source_key)
        assert source_bucket is not None
        assert len(source_bucket.failure_timestamps) == 2
        login_events = tuple(
            session.scalars(
                select(AuditEvent).where(
                    AuditEvent.action.in_(("login_failed", "login_succeeded"))
                )
            )
        )
        assert [event.action for event in login_events] == ["login_failed"]
        assert login_events[0].metadata_json.keys() == {
            "reason",
            "source_fingerprint",
            "username_fingerprint",
        }
        assert "password" not in repr(login_events[0].metadata_json).casefold()
        assert "argon2" not in repr(login_events[0].metadata_json).casefold()

    assert (await login(client, origin_headers, password=PASSWORD)).status_code == 401
    assert (
        await login(
            client,
            origin_headers,
            password="a different sufficiently long passphrase",
        )
    ).status_code == 200
    assert registered_successes == [("maintainer", source)]


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


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("trusted_proxies", "expected_source"),
    [
        ((), "127.0.0.1"),
        (("127.0.0.1/32",), "198.51.100.77"),
    ],
)
async def test_proxy_source_and_secure_cookie_semantics_are_explicit(
    tmp_path: Path,
    trusted_proxies: tuple[str, ...],
    expected_source: str,
) -> None:
    data_dir = tmp_path / ("trusted" if trusted_proxies else "untrusted")
    data_dir.mkdir(mode=0o700)
    database_url = f"sqlite+pysqlite:///{data_dir / 'agentbox.db'}"
    migrate_database(database_url)
    secret = "proxy-test-secret-that-is-at-least-thirty-two-bytes"
    settings = Settings(
        env=Environment.TEST,
        database_url=database_url,
        data_dir=data_dir,
        secret_key=SecretStr(secret),
        runtime_socket=Path("/run/agentbox/runtime.sock"),
        project_root=Path("/srv/agentbox/projects"),
        # Static serving has its own production integration tests. Keep this
        # proxy/Cookie fixture independent from a host installation layout.
        static_dir=None,
        alembic_ini=Path.cwd() / "alembic.ini",
        allowed_origins=("https://agentbox.example",),
        trusted_proxies=trusted_proxies,
    )
    services = build_services(
        settings,
        password_manager=PasswordManager(time_cost=1, memory_cost=8192, parallelism=1),
    )
    services.admin.initialize("maintainer", PASSWORD)
    # Database fixture paths are intentionally temporary; switch only the cookie
    # policy after service construction so the request exercises production semantics.
    settings.env = Environment.PRODUCTION
    application = create_app(
        settings,
        services,
        FakeCodexRuntime(),
        FakeClaudeRuntime(),
        FakeProjectRuntime(),
    )
    try:
        transport = httpx.ASGITransport(app=application, client=("127.0.0.1", 44000))
        async with httpx.AsyncClient(
            transport=transport, base_url="https://agentbox.example"
        ) as proxy_client:
            headers = {
                "Origin": "https://agentbox.example",
                "X-Forwarded-For": "198.51.100.77, 203.0.113.9",
                "X-Forwarded-Proto": "http",
            }
            failed = await login(proxy_client, headers, password="wrong password value")
            assert failed.status_code == 401
            succeeded = await login(proxy_client, headers)
            assert succeeded.status_code == 200
            assert "Secure" in succeeded.headers["set-cookie"]
        with services.database.transaction() as session:
            failure = session.scalar(
                select(AuditEvent)
                .where(AuditEvent.action == "login_failed")
                .order_by(AuditEvent.created_at.desc())
            )
            assert failure is not None
            assert failure.metadata_json["source_fingerprint"] == source_fingerprint(
                secret, expected_source
            )
    finally:
        services.database.close()


@pytest.mark.anyio
async def test_mutation_models_reject_type_coercion(
    client: httpx.AsyncClient, origin_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": 1, "password": PASSWORD},
        headers=origin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_FAILED"
    assert "input" not in response.json()["error"]
