"""Formal Project Workspace metadata and conservative input validation."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agentbox_core.clock import Clock
from agentbox_core.database import Database
from agentbox_core.errors import (
    ProjectConflict,
    ProjectNotFound,
    ProjectNotReady,
    ProjectValidationError,
)
from agentbox_core.models import Project
from agentbox_core.security import new_identifier
from agentbox_core.waw_models import AgentWorkspaceSessionRecord

_SLUG = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")
_LEGACY_KEY = re.compile(r"[^/\\\x00-\x1f\x7f]{1,80}")
_GITHUB_SSH = re.compile(
    r"git@github\.com:(?P<owner>[A-Za-z0-9_.-]{1,100})/"
    r"(?P<repo>[A-Za-z0-9_.-]{1,100})(?P<dotgit>\.git)?"
)
_RESERVED_SLUGS = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
)
_PROJECT_FENCE_EXCLUDED_WORKSPACE_STATES = ("EXITED", "STOPPED", "STOPPING")
_MAX_SQLITE_SEQUENCE = 2**63 - 1


@dataclass(frozen=True)
class ProjectInput:
    display_name: str
    slug: str
    relative_path: str


def normalize_project_name(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).strip()
    if (
        normalized != value.strip()
        or not 1 <= len(normalized) <= 128
        or any(unicodedata.category(character).startswith("C") for character in normalized)
    ):
        raise ProjectValidationError()
    return normalized


def project_slug(name: str, supplied: str | None = None) -> str:
    if supplied is not None:
        normalized = unicodedata.normalize("NFC", supplied).strip().casefold()
        if (
            normalized != supplied.strip().casefold()
            or not _SLUG.fullmatch(normalized)
            or normalized in _RESERVED_SLUGS
        ):
            raise ProjectValidationError()
        return normalized
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-")[:56].rstrip("-")
    if not slug:
        slug = f"project-{hashlib.sha256(name.encode()).hexdigest()[:10]}"
    if not _SLUG.fullmatch(slug) or slug in _RESERVED_SLUGS:
        raise ProjectValidationError()
    return slug


def validate_repository_url(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 512 or value != value.strip():
        raise ProjectValidationError()
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise ProjectValidationError()
    ssh = _GITHUB_SSH.fullmatch(value)
    if ssh:
        if (
            ssh.group("owner").startswith("-")
            or ssh.group("repo").startswith("-")
            or ssh.group("owner") in {".", ".."}
            or ssh.group("repo").removesuffix(".git") in {".", ".."}
        ):
            raise ProjectValidationError()
        return value
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
        username = parsed.username
        password = parsed.password
    except ValueError as exc:
        raise ProjectValidationError() from exc
    if (
        parsed.scheme != "https"
        or hostname != "github.com"
        or port is not None
        or username is not None
        or password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ProjectValidationError()
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        raise ProjectValidationError()
    owner, repository = parts
    repository_name = repository[:-4] if repository.endswith(".git") else repository
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", owner) or not re.fullmatch(
        r"[A-Za-z0-9_.-]{1,100}", repository_name
    ):
        raise ProjectValidationError()
    if (
        owner.startswith("-")
        or repository_name.startswith("-")
        or owner in {".", ".."}
        or repository_name in {".", ".."}
        or parsed.path != f"/{owner}/{repository}"
    ):
        raise ProjectValidationError()
    return urlunsplit(("https", "github.com", f"/{owner}/{repository}", "", ""))


def repository_name_from_url(value: str) -> str:
    ssh = _GITHUB_SSH.fullmatch(value)
    raw = ssh.group("repo") if ssh else value.rstrip("/").rsplit("/", 1)[-1]
    return raw[:-4] if raw.endswith(".git") else raw


class ProjectService:
    def __init__(self, database: Database, clock: Clock) -> None:
        self._database = database
        self._clock = clock

    def list(self, *, include_archived: bool = False) -> tuple[Project, ...]:
        with self._database.transaction() as session:
            query = select(Project)
            if not include_archived:
                query = query.where(Project.archived_at.is_(None))
            return tuple(session.scalars(query.order_by(Project.display_name.collate("NOCASE"))))

    def get(self, project_id: str, *, ready: bool = False) -> Project:
        with self._database.transaction() as session:
            project = session.get(Project, project_id)
            if project is None or project.archived_at is not None:
                raise ProjectNotFound()
            if ready and project.state != "ready":
                raise ProjectNotReady()
            return project

    def resolve(self, reference: str, *, ready: bool = False) -> Project:
        """Resolve only a formal opaque ID or normalized slug, never a path."""
        with self._database.transaction() as session:
            project = session.scalar(
                select(Project).where(
                    (Project.id == reference) | (Project.slug == reference),
                    Project.archived_at.is_(None),
                )
            )
            if project is None:
                raise ProjectNotFound()
            if ready and project.state != "ready":
                raise ProjectNotReady()
            return project

    def reserve(
        self,
        *,
        name: str,
        slug: str | None,
        source_type: str,
        repository_url: str | None = None,
    ) -> Project:
        display_name = normalize_project_name(name)
        storage_key = project_slug(display_name, slug)
        if source_type not in {"empty", "git_clone"}:
            raise ProjectValidationError()
        now = self._clock.now()
        project = Project(
            id=new_identifier("prj"),
            slug=storage_key,
            display_name=display_name,
            relative_path=storage_key,
            source_type=source_type,
            repository_url=repository_url,
            state="creating",
            revision=1,
            created_at=now,
            updated_at=now,
        )
        try:
            with self._database.transaction() as session:
                session.execute(text("BEGIN IMMEDIATE"))
                session.add(project)
                session.flush()
                return project
        except IntegrityError as exc:
            raise ProjectConflict() from exc

    def discard_reservation(self, project_id: str, *, expected_revision: int | None = None) -> None:
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            project = session.get(Project, project_id)
            if project is None:
                return
            self._validate_expected_revision(project, expected_revision)
            if project.state == "creating":
                session.delete(project)

    def reconcile_existing(self, relative_paths: tuple[str, ...]) -> tuple[Project, ...]:
        """Create formal records for Phase 6 immediate-child references without moving them."""
        now = self._clock.now()
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            existing = {
                project.relative_path: project for project in session.scalars(select(Project))
            }
            used_slugs = {project.slug for project in existing.values()}
            for relative_path in relative_paths:
                if relative_path in existing or not self._valid_legacy_key(relative_path):
                    continue
                base = project_slug(relative_path)
                slug = base
                if slug in used_slugs:
                    suffix = hashlib.sha256(relative_path.encode()).hexdigest()[:8]
                    slug = f"{base[:53].rstrip('-')}-{suffix}"
                project = Project(
                    id=new_identifier("prj"),
                    slug=slug,
                    display_name=relative_path,
                    relative_path=relative_path,
                    source_type="existing",
                    state="ready",
                    revision=1,
                    created_at=now,
                    updated_at=now,
                )
                session.add(project)
                used_slugs.add(slug)
            session.flush()
            return tuple(
                session.scalars(
                    select(Project)
                    .where(Project.archived_at.is_(None))
                    .order_by(Project.display_name.collate("NOCASE"))
                )
            )

    def mark_ready(
        self,
        project_id: str,
        *,
        default_branch: str | None = None,
        expected_revision: int | None = None,
    ) -> None:
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            project = session.get(Project, project_id)
            if project is None:
                raise ProjectNotFound()
            self._validate_expected_revision(project, expected_revision)
            normalized_branch = default_branch[:128] if default_branch else None
            if project.state == "ready" and project.default_branch == normalized_branch:
                return
            self._cas_project(
                session,
                project,
                state="ready",
                default_branch=normalized_branch,
            )

    def mark_error(self, project_id: str, *, expected_revision: int | None = None) -> None:
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            project = session.get(Project, project_id)
            if project is None:
                return
            self._validate_expected_revision(project, expected_revision)
            if project.state == "error":
                return
            self._cas_project(session, project, state="error")

    @staticmethod
    def _validate_expected_revision(project: Project, expected_revision: int | None) -> None:
        if expected_revision is None:
            return
        if type(expected_revision) is not int or expected_revision < 1:
            raise ProjectConflict()
        if project.revision != expected_revision:
            raise ProjectConflict()

    def _cas_project(self, session: Session, project: Project, **values: object) -> None:
        if project.revision >= _MAX_SQLITE_SEQUENCE:
            raise ProjectConflict()
        now = self._clock.now()
        statement = (
            update(Project)
            .where(Project.id == project.id, Project.revision == project.revision)
            .values(
                **values,
                revision=project.revision + 1,
                updated_at=now,
            )
        )
        updated_id = session.execute(statement.returning(Project.id)).scalar_one_or_none()
        if updated_id != project.id:
            raise ProjectConflict()
        self._fence_nonterminal_workspaces(session, project.id, now)

    @staticmethod
    def _fence_nonterminal_workspaces(session: Session, project_id: str, now: datetime) -> None:
        """Atomically retire active generations when formal Project identity changes."""

        base = AgentWorkspaceSessionRecord.state.not_in(_PROJECT_FENCE_EXCLUDED_WORKSPACE_STATES)
        exhausted = session.scalar(
            select(AgentWorkspaceSessionRecord.id)
            .where(
                AgentWorkspaceSessionRecord.project_id == project_id,
                base,
                AgentWorkspaceSessionRecord.revision >= _MAX_SQLITE_SEQUENCE,
            )
            .limit(1)
        )
        if exhausted is not None:
            raise ProjectConflict()
        session.execute(
            update(AgentWorkspaceSessionRecord)
            .where(AgentWorkspaceSessionRecord.project_id == project_id, base)
            .values(
                state="UNKNOWN",
                reconciliation_state="reconciliation_required",
                failure_code="PROJECT_BINDING_STALE",
                revision=AgentWorkspaceSessionRecord.revision + 1,
                updated_at=now,
                last_seen_at=now,
            )
        )

    @staticmethod
    def _valid_legacy_key(value: str) -> bool:
        return (
            bool(_LEGACY_KEY.fullmatch(value))
            and value == unicodedata.normalize("NFC", value)
            and value not in {".", ".."}
            and not value.startswith(".")
            and value == value.strip()
        )
