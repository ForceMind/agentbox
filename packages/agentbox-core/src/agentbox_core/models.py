"""Phase 3 control-plane persistence models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from agentbox_core.utc import UTC6DateTime

_UTC6_GLOB = (
    "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] "
    "[0-9][0-9]:[0-9][0-9]:[0-9][0-9]."
    "[0-9][0-9][0-9][0-9][0-9][0-9]"
)


def _utc6(column: str) -> str:
    year = f"CAST(substr({column},1,4) AS INTEGER)"
    month = f"CAST(substr({column},6,2) AS INTEGER)"
    day = f"CAST(substr({column},9,2) AS INTEGER)"
    max_day = (
        f"CASE WHEN {month} IN (1,3,5,7,8,10,12) THEN 31 "
        f"WHEN {month} IN (4,6,9,11) THEN 30 WHEN {month}=2 THEN "
        f"CASE WHEN ({year}%4=0 AND ({year}%100<>0 OR {year}%400=0)) "
        "THEN 29 ELSE 28 END ELSE 0 END"
    )
    return (
        f"length({column})=26 AND {column} GLOB '{_UTC6_GLOB}' "
        f"AND {year} BETWEEN 1 AND 9999 AND {month} BETWEEN 1 AND 12 "
        f"AND {day} BETWEEN 1 AND ({max_day}) "
        f"AND CAST(substr({column},12,2) AS INTEGER) BETWEEN 0 AND 23 "
        f"AND CAST(substr({column},15,2) AS INTEGER) BETWEEN 0 AND 59 "
        f"AND CAST(substr({column},18,2) AS INTEGER) BETWEEN 0 AND 59"
    )


class Base(DeclarativeBase):
    """Declarative metadata used only by Alembic and ORM mapping."""


class AdminUser(Base):
    __tablename__ = "admin_users"
    __table_args__ = (
        Index(
            "uq_admin_users_single_active",
            "is_active",
            unique=True,
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    username_normalized: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list[ControlPlaneSession]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class ControlPlaneSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_sessions_id_user"),
        CheckConstraint("auth_epoch >= 1", name="ck_sessions_auth_epoch"),
        CheckConstraint(
            "recent_authenticated_at >= created_at AND " "recent_authenticated_at <= last_seen_at",
            name="ck_sessions_recent_auth_bounds",
        ),
        CheckConstraint(
            " AND ".join(
                _utc6(column)
                for column in (
                    "created_at",
                    "recent_authenticated_at",
                    "last_seen_at",
                    "idle_expires_at",
                    "expires_at",
                )
            )
            + " AND (revoked_at IS NULL OR ("
            + _utc6("revoked_at")
            + "))",
            name="ck_sessions_utc6",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC6DateTime(), nullable=False)
    recent_authenticated_at: Mapped[datetime] = mapped_column(UTC6DateTime(), nullable=False)
    auth_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_seen_at: Mapped[datetime] = mapped_column(UTC6DateTime(), nullable=False)
    idle_expires_at: Mapped[datetime] = mapped_column(UTC6DateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTC6DateTime(), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTC6DateTime(), index=True)
    client_label: Mapped[str | None] = mapped_column(String(80))

    user: Mapped[AdminUser] = relationship(back_populates="sessions")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[str | None] = mapped_column(String(80))
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(72), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class LoginRateLimitBucket(Base):
    """Restart-persistent pseudonymous login-throttle state.

    Keys are application-secret-derived digests.  Neither account names nor
    source addresses are stored in this table.
    """

    __tablename__ = "login_rate_limit_buckets"

    key_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    failure_timestamps: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class Project(Base):
    """Formal Project Workspace metadata; paths remain relative to the configured root."""

    __tablename__ = "projects"
    __table_args__ = (
        Index("uq_projects_slug_active", "slug", unique=True),
        Index("uq_projects_relative_path", "relative_path", unique=True),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(80), nullable=False)
    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    repository_url: Mapped[str | None] = mapped_column(String(512))
    default_branch: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    jobs: Mapped[list[Job]] = relationship(back_populates="project")


class Job(Base):
    """Durable, typed single-host work item with sanitized summaries only."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_by: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(80), index=True)
    project_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    progress: Mapped[int | None] = mapped_column(Integer)
    phase: Mapped[str | None] = mapped_column(String(48))
    result_summary: Mapped[str | None] = mapped_column(String(512))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_summary: Mapped[str | None] = mapped_column(String(512))
    payload_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    idempotency_key_digest: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    resource_lock_key: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    lease_owner: Mapped[str | None] = mapped_column(String(80))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_id: Mapped[str | None] = mapped_column(String(72), index=True)

    project: Mapped[Project | None] = relationship(back_populates="jobs")
    events: Mapped[list[JobEvent]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="JobEvent.sequence"
    )


class JobEvent(Base):
    __tablename__ = "job_events"

    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    progress: Mapped[int | None] = mapped_column(Integer)
    phase: Mapped[str | None] = mapped_column(String(48))
    summary: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    job: Mapped[Job] = relationship(back_populates="events")
