from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import pytest
from agentbox_core.errors import AdminAlreadyInitialized, PasswordPolicyViolation
from agentbox_core.models import AdminUser, AuditEvent, ControlPlaneSession
from agentbox_core.security import PasswordManager, sanitize_metadata
from agentbox_core.services import ControlPlaneServices
from conftest import FakeClock
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


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
        session.add(
            ControlPlaneSession(
                id="ses_orphan",
                user_id="adm_missing",
                token_hash="a" * 64,
                csrf_hash="b" * 64,
                created_at=clock.now(),
                last_seen_at=clock.now(),
                idle_expires_at=clock.now() + timedelta(minutes=5),
                expires_at=clock.now() + timedelta(hours=1),
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
        stored.expires_at = clock.now() - timedelta(seconds=61)

    assert initialized_services.sessions.cleanup() == 1


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


def test_audit_metadata_rejects_sensitive_keys_and_log_injection() -> None:
    with pytest.raises(ValueError, match="forbidden"):
        sanitize_metadata({"password": "do-not-store"})
    with pytest.raises(ValueError, match="forbidden"):
        sanitize_metadata({"csrf_token": "do-not-store"})

    assert sanitize_metadata({"reason": "bad\nline"}) == {"reason": "bad line"}
