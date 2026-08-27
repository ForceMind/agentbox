from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, timedelta
from pathlib import Path

import pytest
from agentbox_core.errors import (
    AdminAlreadyInitialized,
    DatabaseNotReady,
    InvalidCredentials,
    InvalidSession,
    LoginRateLimited,
    PasswordPolicyViolation,
)
from agentbox_core.models import (
    AdminUser,
    AuditEvent,
    ControlPlaneSession,
    Job,
    LoginRateLimitBucket,
)
from agentbox_core.security import PasswordManager, sanitize_metadata
from agentbox_core.services import ControlPlaneServices, IssuedSession, build_services
from agentbox_core.utc import aware_utc
from conftest import FakeClock
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session


def test_first_admin_initialization_is_hashed_and_second_is_rejected(
    services: ControlPlaneServices,
) -> None:
    password = "a sufficiently long passphrase"
    admin = services.admin.initialize("maintainer", password, request_id="req_init")

    assert admin.password_hash != password
    assert PasswordManager(time_cost=1, memory_cost=8192, parallelism=1).verify(
        admin.password_hash, password
    )
    with services.database.transaction() as session:
        stored = session.get(AdminUser, admin.id)
        assert stored is not None
        assert stored.password_hash.startswith("$argon2id$")
        event = session.scalar(select(AuditEvent).where(AuditEvent.action == "admin_initialized"))
        assert event is not None
        assert event.request_id == "req_init"

    with pytest.raises(AdminAlreadyInitialized):
        services.admin.initialize("another", "another sufficiently long passphrase")


def test_admin_bootstrap_race_creates_exactly_one_admin(
    services: ControlPlaneServices,
) -> None:
    def initialize(username: str) -> str:
        try:
            services.admin.initialize(username, "a sufficiently long passphrase")
            return "created"
        except AdminAlreadyInitialized:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(initialize, ("first", "second")))

    assert sorted(results) == ["created", "rejected"]
    with services.database.transaction() as session:
        assert len(session.scalars(select(AdminUser)).all()) == 1


@pytest.mark.parametrize(
    "password",
    ["short", "passwordpassword", "123456789012", "x" * 1025],
)
def test_weak_password_policy_is_rejected(
    services: ControlPlaneServices,
    password: str,
) -> None:
    with pytest.raises(PasswordPolicyViolation):
        services.admin.initialize("maintainer", password)


def test_session_token_is_hashed_at_rest(
    initialized_services: ControlPlaneServices,
) -> None:
    issued = initialized_services.auth.login(
        username="maintainer",
        password="a sufficiently long passphrase",
        source_identifier="127.0.0.1",
        request_id="req_login",
    )

    with initialized_services.database.transaction() as session:
        stored = session.get(ControlPlaneSession, issued.session_id)
        assert stored is not None
        assert stored.token_hash != issued.token
        assert issued.token not in repr(stored.__dict__)
        assert stored.csrf_hash != issued.csrf_token

    database_path = Path(initialized_services.database.engine.url.database or "")
    persistent_bytes = b"".join(
        path.read_bytes() for path in database_path.parent.glob(f"{database_path.name}*")
    )
    assert issued.token.encode() not in persistent_bytes
    assert issued.csrf_token.encode() not in persistent_bytes


def test_database_constraints_enforce_single_admin_and_session_foreign_key(
    initialized_services: ControlPlaneServices,
    clock: FakeClock,
) -> None:
    with pytest.raises(IntegrityError), initialized_services.database.transaction() as session:
        session.add(
            AdminUser(
                id="adm_second",
                username="second",
                username_normalized="second",
                password_hash="$argon2id$invalid",
                is_active=True,
                created_at=clock.now(),
                updated_at=clock.now(),
            )
        )

    with pytest.raises(IntegrityError), initialized_services.database.transaction() as session:
        now = aware_utc(clock.now())
        session.add(
            ControlPlaneSession(
                id="ses_orphan",
                user_id="adm_missing",
                token_hash="a" * 64,
                csrf_hash="b" * 64,
                created_at=now,
                recent_authenticated_at=now,
                auth_epoch=1,
                last_seen_at=now,
                idle_expires_at=now + timedelta(minutes=5),
                expires_at=now + timedelta(hours=1),
            )
        )


def test_expired_and_revoked_sessions_are_rejected_and_cleaned(
    initialized_services: ControlPlaneServices,
    clock: FakeClock,
) -> None:
    issued = initialized_services.auth.login(
        username="maintainer",
        password="a sufficiently long passphrase",
        source_identifier="127.0.0.1",
        request_id="req_login",
    )
    authenticated = initialized_services.sessions.authenticate(issued.token)
    initialized_services.sessions.revoke(authenticated, request_id="req_logout")
    clock.advance(seconds=61)

    assert initialized_services.sessions.cleanup() == 1
    with initialized_services.database.transaction() as session:
        assert session.get(ControlPlaneSession, issued.session_id) is None


def test_expired_session_cleanup_uses_retention(
    initialized_services: ControlPlaneServices,
    clock: FakeClock,
) -> None:
    issued = initialized_services.auth.login(
        username="maintainer",
        password="a sufficiently long passphrase",
        source_identifier="127.0.0.1",
        request_id="req_login",
    )
    with initialized_services.database.transaction() as session:
        stored = session.get(ControlPlaneSession, issued.session_id)
        assert stored is not None
        stored.expires_at = aware_utc(clock.now()) - timedelta(seconds=61)

    assert initialized_services.sessions.cleanup() == 1


def test_session_authority_timestamps_round_trip_as_aware_utc6(
    initialized_services: ControlPlaneServices,
    clock: FakeClock,
) -> None:
    issued = initialized_services.auth.login(
        username="maintainer",
        password="a sufficiently long passphrase",
        source_identifier="127.0.0.1",
        request_id="req_login_utc6",
    )
    with initialized_services.database.transaction() as session:
        stored = session.get(ControlPlaneSession, issued.session_id)
        assert stored is not None
        assert stored.created_at.tzinfo is UTC
        assert stored.created_at.utcoffset() == timedelta(0)
    with initialized_services.database.engine.connect() as connection:
        raw = connection.exec_driver_sql(
            "SELECT created_at FROM sessions WHERE id=?", (issued.session_id,)
        ).scalar_one()
    assert len(raw) == 26
    assert raw[4] == raw[7] == "-"
    assert raw[10] == " " and raw[19] == "."
    assert "+" not in raw and not raw.endswith("Z")

    with pytest.raises(StatementError), initialized_services.database.transaction() as session:
        stored = session.get(ControlPlaneSession, issued.session_id)
        assert stored is not None
        stored.expires_at = clock.now()


def test_session_cleanup_race_preserves_an_active_session(
    initialized_services: ControlPlaneServices,
) -> None:
    issued = initialized_services.auth.login(
        username="maintainer",
        password="a sufficiently long passphrase",
        source_identifier="127.0.0.1",
        request_id="req_active_cleanup_race",
    )

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(initialized_services.sessions.authenticate, issued.token)
            for _index in range(12)
        ] + [executor.submit(initialized_services.sessions.cleanup) for _index in range(12)]
        results = [future.result() for future in futures]

    assert 0 in results
    assert initialized_services.sessions.authenticate(issued.token).session_id == issued.session_id


def test_active_session_limit_revokes_the_oldest_session(
    initialized_services: ControlPlaneServices,
) -> None:
    issued_ids: list[str] = []
    with initialized_services.database.transaction() as session:
        admin = session.scalar(select(AdminUser))
        assert admin is not None
        for _index in range(11):
            issued = initialized_services.sessions.issue(session, admin, "test")
            issued_ids.append(issued.session_id)

    with initialized_services.database.transaction() as session:
        oldest = session.get(ControlPlaneSession, issued_ids[0])
        assert oldest is not None and oldest.revoked_at is not None
        active_count = len(
            session.scalars(
                select(ControlPlaneSession).where(ControlPlaneSession.revoked_at.is_(None))
            ).all()
        )
        assert active_count == 10
        assert session.scalar(select(AuditEvent).where(AuditEvent.action == "session_revoked"))


def test_local_password_change_requires_current_password_and_revokes_sessions(
    initialized_services: ControlPlaneServices,
) -> None:
    first = initialized_services.auth.login(
        username="maintainer",
        password="a sufficiently long passphrase",
        source_identifier="127.0.0.1",
        request_id="req_first_session",
    )
    second = initialized_services.auth.login(
        username="maintainer",
        password="a sufficiently long passphrase",
        source_identifier="127.0.0.2",
        request_id="req_second_session",
    )

    with pytest.raises(InvalidCredentials):
        initialized_services.admin.change_password(
            "incorrect current passphrase",
            "a different sufficiently long passphrase",
        )

    assert (
        initialized_services.admin.change_password(
            "a sufficiently long passphrase",
            "a different sufficiently long passphrase",
            request_id="req_password_change",
        )
        == 2
    )
    for issued in (first, second):
        with pytest.raises(InvalidSession):
            initialized_services.sessions.authenticate(issued.token)
    with pytest.raises(InvalidCredentials):
        initialized_services.auth.login(
            username="maintainer",
            password="a sufficiently long passphrase",
            source_identifier="127.0.0.3",
            request_id="req_old_password",
        )
    assert initialized_services.auth.login(
        username="maintainer",
        password="a different sufficiently long passphrase",
        source_identifier="127.0.0.3",
        request_id="req_new_password",
    )
    with initialized_services.database.transaction() as session:
        event = session.scalar(
            select(AuditEvent).where(AuditEvent.action == "admin_password_changed")
        )
        assert event is not None
        assert event.metadata_json == {"revoked_count": 2}


def test_local_password_change_is_atomic_when_audit_write_fails(
    initialized_services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issued = initialized_services.auth.login(
        username="maintainer",
        password="a sufficiently long passphrase",
        source_identifier="127.0.0.1",
        request_id="req_atomic_session",
    )

    def fail_audit(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("simulated audit persistence failure")

    original_record = initialized_services.audit.record
    monkeypatch.setattr(initialized_services.audit, "record", fail_audit)
    with pytest.raises(RuntimeError, match="audit persistence"):
        initialized_services.admin.change_password(
            "a sufficiently long passphrase",
            "a different sufficiently long passphrase",
        )
    monkeypatch.setattr(initialized_services.audit, "record", original_record)

    assert initialized_services.sessions.authenticate(issued.token)
    assert initialized_services.auth.login(
        username="maintainer",
        password="a sufficiently long passphrase",
        source_identifier="127.0.0.2",
        request_id="req_atomic_old_password",
    )
    with pytest.raises(InvalidCredentials):
        initialized_services.auth.login(
            username="maintainer",
            password="a different sufficiently long passphrase",
            source_identifier="127.0.0.3",
            request_id="req_atomic_new_password",
        )


def test_login_final_transaction_wins_then_password_change_revokes_its_session(
    initialized_services: ControlPlaneServices,
    password_manager: PasswordManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_issue = initialized_services.sessions.issue
    issue_entered = threading.Event()
    release_issue = threading.Event()

    def pause_issue(
        session: Session,
        user: AdminUser,
        client_label: str | None,
    ) -> IssuedSession:
        issue_entered.set()
        if not release_issue.wait(timeout=5):
            raise AssertionError("test did not release the serialized Login transaction")
        return original_issue(session, user, client_label)

    monkeypatch.setattr(initialized_services.sessions, "issue", pause_issue)
    with ThreadPoolExecutor(max_workers=2) as executor:
        login_future = executor.submit(
            initialized_services.auth.login,
            username="maintainer",
            password="a sufficiently long passphrase",
            source_identifier="127.0.0.10",
            request_id="req_login_transaction_wins",
        )
        assert issue_entered.wait(timeout=5)

        original_hash = password_manager.hash
        password_change_hash_ready = threading.Event()

        def track_password_change_hash(password: str) -> str:
            replacement = original_hash(password)
            if password == "a different sufficiently long passphrase":
                password_change_hash_ready.set()
            return replacement

        monkeypatch.setattr(password_manager, "hash", track_password_change_hash)
        change_future = executor.submit(
            initialized_services.admin.change_password,
            "a sufficiently long passphrase",
            "a different sufficiently long passphrase",
            request_id="req_change_after_login_transaction",
        )
        try:
            assert password_change_hash_ready.wait(timeout=5)
        finally:
            release_issue.set()

        issued = login_future.result(timeout=5)
        assert change_future.result(timeout=5) == 1

    with pytest.raises(InvalidSession):
        initialized_services.sessions.authenticate(issued.token)
    with initialized_services.database.transaction() as session:
        stored = session.get(ControlPlaneSession, issued.session_id)
        assert stored is not None
        assert stored.revoked_at is not None
        actions = tuple(
            session.scalars(
                select(AuditEvent.action).where(
                    AuditEvent.action.in_(("login_succeeded", "admin_password_changed"))
                )
            )
        )
        assert sorted(actions) == ["admin_password_changed", "login_succeeded"]


def test_stale_rehash_cannot_overwrite_a_concurrent_password_change(
    initialized_services: ControlPlaneServices,
    password_manager: PasswordManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_verify = password_manager.verify
    original_hash = password_manager.hash
    old_password_verified = threading.Event()
    release_stale_login = threading.Event()
    coordination_lock = threading.Lock()
    login_verify_intercepted = False
    stale_replacement_hashes: list[str] = []

    def pause_first_successful_old_password_verify(
        encoded_hash: str, supplied_password: str
    ) -> bool:
        nonlocal login_verify_intercepted
        verified = original_verify(encoded_hash, supplied_password)
        should_pause = False
        if verified and supplied_password == "a sufficiently long passphrase":
            with coordination_lock:
                if not login_verify_intercepted:
                    login_verify_intercepted = True
                    should_pause = True
        if should_pause:
            old_password_verified.set()
            if not release_stale_login.wait(timeout=5):
                raise AssertionError("test did not release the stale rehash Login")
        return verified

    def track_replacement_hash(password: str) -> str:
        replacement = original_hash(password)
        if password == "a sufficiently long passphrase":
            stale_replacement_hashes.append(replacement)
        return replacement

    monkeypatch.setattr(password_manager, "verify", pause_first_successful_old_password_verify)
    monkeypatch.setattr(password_manager, "needs_rehash", lambda encoded_hash: True)
    monkeypatch.setattr(password_manager, "hash", track_replacement_hash)

    with ThreadPoolExecutor(max_workers=1) as executor:
        stale_login = executor.submit(
            initialized_services.auth.login,
            username="maintainer",
            password="a sufficiently long passphrase",
            source_identifier="127.0.0.11",
            request_id="req_stale_rehash",
        )
        assert old_password_verified.wait(timeout=5)
        assert (
            initialized_services.admin.change_password(
                "a sufficiently long passphrase",
                "a different sufficiently long passphrase",
                request_id="req_change_wins_rehash",
            )
            == 0
        )
        release_stale_login.set()
        with pytest.raises(InvalidCredentials):
            stale_login.result(timeout=5)

    assert len(stale_replacement_hashes) == 1
    with initialized_services.database.transaction() as session:
        admin = session.scalar(select(AdminUser))
        assert admin is not None
        assert admin.password_hash != stale_replacement_hashes[0]
        assert original_verify(admin.password_hash, "a different sufficiently long passphrase")
        assert not original_verify(admin.password_hash, "a sufficiently long passphrase")
        assert (
            session.scalar(
                select(ControlPlaneSession).where(ControlPlaneSession.revoked_at.is_(None))
            )
            is None
        )
        assert (
            session.scalar(select(AuditEvent).where(AuditEvent.action == "login_succeeded")) is None
        )
        failed = session.scalar(select(AuditEvent).where(AuditEvent.action == "login_failed"))
        assert failed is not None
        assert "password" not in repr(failed.metadata_json).casefold()
        assert "argon2" not in repr(failed.metadata_json).casefold()


def test_local_session_listing_and_revoke_all_expose_metadata_only(
    initialized_services: ControlPlaneServices,
) -> None:
    issued = initialized_services.auth.login(
        username="maintainer",
        password="a sufficiently long passphrase",
        source_identifier="127.0.0.1",
        request_id="req_session_list",
        client_label="fixture-client",
    )

    sessions = initialized_services.admin.sessions("a sufficiently long passphrase")
    assert len(sessions) == 1
    assert sessions[0].session_id == issued.session_id
    assert sessions[0].client_label == "fixture-client"
    assert issued.token not in repr(sessions)
    assert issued.csrf_token not in repr(sessions)

    assert (
        initialized_services.admin.revoke_sessions(
            "a sufficiently long passphrase", request_id="req_revoke_all"
        )
        == 1
    )
    assert initialized_services.admin.sessions("a sufficiently long passphrase") == ()
    assert initialized_services.admin.revoke_sessions("a sufficiently long passphrase") == 0
    with initialized_services.database.transaction() as session:
        event = session.scalar(
            select(AuditEvent).where(AuditEvent.action == "admin_sessions_revoked")
        )
        assert event is not None
        assert event.metadata_json == {"revoked_count": 1}


def test_audit_metadata_rejects_sensitive_keys_and_log_injection() -> None:
    with pytest.raises(ValueError, match="forbidden"):
        sanitize_metadata({"password": "do-not-store"})
    with pytest.raises(ValueError, match="forbidden"):
        sanitize_metadata({"csrf_token": "do-not-store"})

    assert sanitize_metadata({"reason": "bad\nline"}) == {"reason": "bad line"}


def test_login_rate_limit_persists_across_service_restart_without_raw_identity(
    initialized_services: ControlPlaneServices,
    clock: FakeClock,
) -> None:
    username = "unknown-rate-test"
    source = "198.51.100.42"
    for _attempt in range(5):
        with pytest.raises(InvalidCredentials):
            initialized_services.auth.login(
                username=username,
                password="wrong password value",
                source_identifier=source,
                request_id="req_rate_failure",
            )

    settings = initialized_services.database.settings
    restarted = build_services(
        settings,
        clock=clock,
        password_manager=PasswordManager(time_cost=1, memory_cost=8192, parallelism=1),
    )
    try:
        with pytest.raises(LoginRateLimited):
            restarted.auth.login(
                username=username,
                password="wrong password value",
                source_identifier=source,
                request_id="req_after_restart",
            )
        with restarted.database.transaction() as session:
            buckets = tuple(session.scalars(select(LoginRateLimitBucket)))
            assert len(buckets) == 3
            assert all(len(bucket.key_digest) == 64 for bucket in buckets)
        database_path = Path(restarted.database.engine.url.database or "")
        persistent = b"".join(
            path.read_bytes() for path in database_path.parent.glob(f"{database_path.name}*")
        )
        assert username.encode() not in persistent
        assert source.encode() not in persistent

        clock.advance(seconds=601)
        with pytest.raises(InvalidCredentials):
            restarted.auth.login(
                username=username,
                password="wrong password value",
                source_identifier=source,
                request_id="req_after_expiry",
            )
    finally:
        restarted.database.close()


def test_login_rate_limit_cleanup_bounds_expired_rows(
    services: ControlPlaneServices,
    clock: FakeClock,
) -> None:
    services.rate_limits.register_failure("unknown", "203.0.113.7")
    clock.advance(seconds=601)

    assert services.rate_limits.cleanup() == 3
    with services.database.transaction() as session:
        assert session.scalar(select(LoginRateLimitBucket)) is None


def test_login_rate_limit_clock_rollback_does_not_erase_failures(
    services: ControlPlaneServices,
    clock: FakeClock,
) -> None:
    for _attempt in range(3):
        services.rate_limits.register_failure("unknown", "192.0.2.44")
    clock.advance(seconds=-3600)
    for _attempt in range(2):
        services.rate_limits.register_failure("unknown", "192.0.2.44")

    decision = services.rate_limits.check("unknown", "192.0.2.44")

    assert decision.allowed is False
    assert 1 <= decision.retry_after <= 301


def test_login_rate_limit_clock_rollback_cannot_extend_an_existing_lock(
    services: ControlPlaneServices,
    clock: FakeClock,
) -> None:
    for _attempt in range(5):
        services.rate_limits.register_failure("unknown", "192.0.2.45")

    clock.advance(seconds=-10 * 365 * 24 * 60 * 60)
    decision = services.rate_limits.check("unknown", "192.0.2.45")

    assert decision.allowed is False
    assert 1 <= decision.retry_after <= 300


def test_login_rate_limit_cleanup_retains_a_still_locked_bucket(
    services: ControlPlaneServices,
    clock: FakeClock,
) -> None:
    for _attempt in range(5):
        services.rate_limits.register_failure("unknown", "192.0.2.46")

    clock.advance(seconds=299)
    assert services.rate_limits.cleanup() == 0
    assert services.rate_limits.check("unknown", "192.0.2.46").allowed is False


def test_login_rate_limit_success_clears_account_and_combined_but_retains_source(
    services: ControlPlaneServices,
) -> None:
    username = "maintainer"
    source = "198.51.100.60"
    services.rate_limits.register_failure(username, source)
    account, client, combined = services.rate_limits._keys(username, source)

    services.rate_limits.register_success(username, source)

    with services.database.transaction() as session:
        assert session.get(LoginRateLimitBucket, account) is None
        assert session.get(LoginRateLimitBucket, combined) is None
        source_bucket = session.get(LoginRateLimitBucket, client)
        assert source_bucket is not None
        assert len(source_bucket.failure_timestamps) == 1


def test_login_rate_limit_blocks_source_spray_and_distributed_account_attack(
    services: ControlPlaneServices,
) -> None:
    spray_source = "198.51.100.61"
    for index in range(5):
        services.rate_limits.register_failure(f"unknown-{index}", spray_source)
    assert services.rate_limits.check("another-account", spray_source).allowed is False

    account = "one-account"
    for index in range(5):
        services.rate_limits.register_failure(account, f"203.0.113.{index + 1}")
    assert services.rate_limits.check(account, "203.0.113.99").allowed is False


def test_login_rate_limit_serializes_concurrent_failures(
    services: ControlPlaneServices,
) -> None:
    with ThreadPoolExecutor(max_workers=5) as executor:
        list(
            executor.map(
                lambda _index: services.rate_limits.register_failure(
                    "concurrent-account", "198.51.100.62"
                ),
                range(5),
            )
        )

    assert services.rate_limits.check("concurrent-account", "198.51.100.62").allowed is False
    with services.database.transaction() as session:
        buckets = tuple(session.scalars(select(LoginRateLimitBucket)))
        assert len(buckets) == 3
        assert all(len(bucket.failure_timestamps) == 5 for bucket in buckets)


def test_login_rate_limit_row_cap_is_enforced_inside_failure_transaction(
    services: ControlPlaneServices,
) -> None:
    settings = services.database.settings.model_copy(update={"login_rate_max_buckets": 100})
    bounded = build_services(
        settings,
        password_manager=PasswordManager(time_cost=1, memory_cost=8192, parallelism=1),
    )
    try:
        for index in range(33):
            bounded.rate_limits.register_failure(f"unique-account-{index}", f"198.18.0.{index + 1}")
        with pytest.raises(LoginRateLimited):
            bounded.rate_limits.register_failure("overflow-account", "198.18.1.1")
        with bounded.database.transaction() as session:
            assert session.scalar(select(func.count()).select_from(LoginRateLimitBucket)) == 99
    finally:
        bounded.database.close()


def test_login_rate_limit_database_lock_fails_closed(
    services: ControlPlaneServices,
) -> None:
    settings = services.database.settings.model_copy(update={"database_busy_timeout_ms": 100})
    bounded = build_services(
        settings,
        password_manager=PasswordManager(time_cost=1, memory_cost=8192, parallelism=1),
    )
    database_path = Path(bounded.database.engine.url.database or "")
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(DatabaseNotReady):
            bounded.rate_limits.check("maintainer", "198.51.100.63")
    finally:
        connection.rollback()
        connection.close()
        bounded.database.close()


def test_malformed_username_limiter_identity_cannot_collide_with_valid_account(
    services: ControlPlaneServices,
) -> None:
    services.admin.initialize("invalid", "a sufficiently long passphrase")
    for _attempt in range(5):
        with pytest.raises(InvalidCredentials):
            services.auth.login(
                username=" malformed username ",
                password="wrong password value",
                source_identifier="198.51.100.64",
                request_id="req_malformed_rate",
            )

    assert services.auth.login(
        username="invalid",
        password="a sufficiently long passphrase",
        source_identifier="198.51.100.65",
        request_id="req_valid_invalid_account",
    )


def test_retention_cleanup_bounds_terminal_jobs_and_audit_but_preserves_active_work(
    initialized_services: ControlPlaneServices,
    clock: FakeClock,
) -> None:
    terminal, _created = initialized_services.jobs.enqueue(
        job_type="git.pull",
        requested_by="adm_fixture",
        target_type="project",
        target_id="prj_fixture",
        project_id=None,
        payload={"project_key": "fixture"},
        resource_lock_key="project:fixture",
        idempotency_key="retention-terminal",
        request_id="req_retention_old",
    )
    claimed = initialized_services.jobs.claim_next("worker-fixture")
    assert claimed is not None and claimed.id == terminal.id
    initialized_services.jobs.fail(
        terminal.id,
        code="FIXTURE_FAILURE",
        summary="bounded fixture failure",
    )
    initialized_services.rate_limits.register_failure("unknown", "192.0.2.8")
    clock.advance(seconds=100 * 24 * 60 * 60)
    queued, _created = initialized_services.jobs.enqueue(
        job_type="git.pull",
        requested_by="adm_fixture",
        target_type="project",
        target_id="prj_current",
        project_id=None,
        payload={"project_key": "current"},
        resource_lock_key="project:current",
        idempotency_key="retention-current",
        request_id="req_retention_current",
    )
    with initialized_services.database.transaction() as session:
        initialized_services.audit.record(
            session,
            actor_type="system",
            actor_id=None,
            action="retention_fixture_current",
            result="succeeded",
            request_id=None,
        )

    result = initialized_services.retention.cleanup()

    assert result.jobs_deleted == 1
    assert result.audit_events_deleted >= 1
    assert result.rate_limit_buckets_deleted == 3
    with initialized_services.database.transaction() as session:
        assert session.get(Job, terminal.id) is None
        assert session.get(Job, queued.id) is not None
        assert session.scalar(
            select(AuditEvent).where(AuditEvent.action == "retention_fixture_current")
        )
