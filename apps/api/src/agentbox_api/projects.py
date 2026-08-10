"""Formal Project Workspace, Git, and GitHub control-plane routes."""

from __future__ import annotations

from typing import Literal, cast

from agentbox_core.errors import ProjectValidationError, RuntimeGatewayError
from agentbox_core.models import Job, Project
from agentbox_core.projects import (
    normalize_project_name,
    project_slug,
    repository_name_from_url,
    validate_repository_url,
)
from agentbox_core.services import AuthenticatedSession, ControlPlaneServices
from agentbox_protocol import (
    BranchRequest,
    DraftPullRequestRequest,
    GitBranchData,
    GitBranchListData,
    GitBranchListResponse,
    GitHubGlobalData,
    GitHubGlobalResponse,
    GitHubProjectData,
    GitStatusData,
    JobResponse,
    ProjectCloneRequest,
    ProjectCreateRequest,
    ProjectData,
    ProjectJobData,
    ProjectJobResponse,
    ProjectListData,
    ProjectListResponse,
    ProjectResponse,
)
from agentbox_runtime import (
    GitHubProjectStatus,
    GitStatus,
    ProjectRuntimeClient,
    RuntimeOperationError,
    validate_branch_name,
)
from fastapi import APIRouter, Cookie, Header, Request, Response, status

from agentbox_api.auth import SESSION_COOKIE, _validate_origin, authenticate_request
from agentbox_api.jobs import job_data

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])
github_router = APIRouter(prefix="/api/v1/github", tags=["github"])


def _services(request: Request) -> ControlPlaneServices:
    return cast(ControlPlaneServices, request.app.state.services)


def _runtime(request: Request) -> ProjectRuntimeClient:
    return cast(ProjectRuntimeClient, request.app.state.project_runtime)


def _translate(exc: RuntimeOperationError) -> RuntimeGatewayError:
    return RuntimeGatewayError(
        code=exc.code,
        category=exc.category,
        message=exc.message,
        retryable=exc.retryable,
        retry_after=exc.retry_after,
    )


def _git_data(value: GitStatus | None) -> GitStatusData | None:
    if value is None:
        return None
    return GitStatusData(**value.to_dict())


def _github_data(value: GitHubProjectStatus | None) -> GitHubProjectData | None:
    if value is None:
        return None
    checks = value.checks if value.checks in {"pass", "fail", "pending", "unknown"} else "unknown"
    return GitHubProjectData(
        available=value.available,
        repository=value.repository,
        pull_request_number=value.pull_request_number,
        pull_request_title=value.pull_request_title,
        pull_request_state=value.pull_request_state,
        pull_request_draft=value.pull_request_draft,
        pull_request_url=value.pull_request_url,
        checks=cast(Literal["pass", "fail", "pending", "unknown"], checks),
    )


def project_data(
    project: Project,
    *,
    git: GitStatus | None = None,
    github: GitHubProjectStatus | None = None,
) -> ProjectData:
    return ProjectData(
        id=project.id,
        slug=project.slug,
        display_name=project.display_name,
        source_type=cast(Literal["empty", "git_clone", "existing"], project.source_type),
        state=cast(Literal["creating", "ready", "error", "archived"], project.state),
        repository_url=project.repository_url,
        default_branch=project.default_branch,
        created_at=project.created_at,
        updated_at=project.updated_at,
        git=_git_data(git),
        github=_github_data(github),
    )


async def _reconcile(request: Request) -> tuple[Project, ...]:
    try:
        workspaces = await _runtime(request).list_workspaces(str(request.state.request_id))
    except RuntimeOperationError:
        return _services(request).projects.list()
    return _services(request).projects.reconcile_existing(
        tuple(workspace.project_key for workspace in workspaces)
    )


def _authenticate_mutation(
    request: Request, raw_session: str | None, csrf_token: str | None
) -> AuthenticatedSession:
    _validate_origin(request)
    authenticated = authenticate_request(request, raw_session)
    _services(request).sessions.validate_csrf(authenticated, csrf_token)
    return authenticated


def _idempotency(value: str | None) -> str:
    if value is None:
        raise ProjectValidationError()
    return value


def _audit(
    request: Request,
    authenticated: AuthenticatedSession,
    *,
    action: str,
    project_id: str,
    result: str,
    job_id: str | None = None,
) -> None:
    metadata: dict[str, object] = {"project_id": project_id}
    if job_id:
        metadata["job_id"] = job_id
    services = _services(request)
    with services.database.transaction() as session:
        services.audit.record(
            session,
            actor_type="admin",
            actor_id=authenticated.user_id,
            action=action,
            result=result,
            request_id=str(request.state.request_id),
            target_type="project",
            target_id=project_id,
            metadata=metadata,
        )


def _enqueue(
    request: Request,
    authenticated: AuthenticatedSession,
    project: Project,
    *,
    job_type: str,
    payload: dict[str, object],
    idempotency_key: str,
) -> tuple[Job, bool]:
    try:
        return _services(request).jobs.enqueue(
            job_type=job_type,
            requested_by=authenticated.user_id,
            target_type="project",
            target_id=project.id,
            project_id=project.id,
            payload=payload,
            resource_lock_key=f"project:{project.id}",
            idempotency_key=idempotency_key,
            request_id=str(request.state.request_id),
        )
    except ValueError as exc:
        raise ProjectValidationError() from exc


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> ProjectListResponse:
    authenticate_request(request, agentbox_session)
    projects = await _reconcile(request)
    response.headers["Cache-Control"] = "no-store"
    return ProjectListResponse(
        request_id=str(request.state.request_id),
        data=ProjectListData(projects=[project_data(project) for project in projects]),
    )


async def _create_project_job(
    request: Request,
    authenticated: AuthenticatedSession,
    *,
    name: str,
    slug: str | None,
    source_type: str,
    repository_url: str | None,
    idempotency_key: str,
) -> ProjectJobResponse:
    display_name = normalize_project_name(name)
    normalized_slug = project_slug(display_name, slug)
    job_type = "project.clone" if source_type == "git_clone" else "project.create"
    existing = _services(request).jobs.find_idempotent(
        job_type=job_type,
        requested_by=authenticated.user_id,
        scope=normalized_slug,
        idempotency_key=idempotency_key,
    )
    if existing is not None and existing.project_id is not None:
        project = _services(request).projects.get(existing.project_id)
        return ProjectJobResponse(
            request_id=str(request.state.request_id),
            data=ProjectJobData(project=project_data(project), job=job_data(existing)),
        )
    project = _services(request).projects.reserve(
        name=display_name,
        slug=normalized_slug,
        source_type=source_type,
        repository_url=repository_url,
    )
    payload: dict[str, object] = {"project_key": project.relative_path}
    if repository_url is not None:
        payload["repository_url"] = repository_url
    try:
        job, _created = _services(request).jobs.enqueue(
            job_type=job_type,
            requested_by=authenticated.user_id,
            target_type="project",
            target_id=project.id,
            project_id=project.id,
            payload=payload,
            resource_lock_key=f"project:{project.id}",
            idempotency_key=idempotency_key,
            idempotency_scope=normalized_slug,
            request_id=str(request.state.request_id),
        )
    except Exception:
        _services(request).projects.discard_reservation(project.id)
        raise
    action = "project_clone_requested" if source_type == "git_clone" else "project_created"
    _audit(
        request,
        authenticated,
        action=action,
        project_id=project.id,
        result="requested",
        job_id=job.id,
    )
    return ProjectJobResponse(
        request_id=str(request.state.request_id),
        data=ProjectJobData(project=project_data(project), job=job_data(job)),
    )


@router.post("", response_model=ProjectJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_project(
    payload: ProjectCreateRequest,
    request: Request,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> ProjectJobResponse:
    authenticated = _authenticate_mutation(request, agentbox_session, x_csrf_token)
    return await _create_project_job(
        request,
        authenticated,
        name=payload.name,
        slug=payload.slug,
        source_type="empty",
        repository_url=None,
        idempotency_key=_idempotency(idempotency_key),
    )


@router.post("/clone", response_model=ProjectJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def clone_project(
    payload: ProjectCloneRequest,
    request: Request,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> ProjectJobResponse:
    authenticated = _authenticate_mutation(request, agentbox_session, x_csrf_token)
    repository_url = validate_repository_url(payload.repository_url)
    name = payload.name or repository_name_from_url(repository_url)
    return await _create_project_job(
        request,
        authenticated,
        name=name,
        slug=payload.slug,
        source_type="git_clone",
        repository_url=repository_url,
        idempotency_key=_idempotency(idempotency_key),
    )


async def _project_observations(
    request: Request, project: Project
) -> tuple[GitStatus | None, GitHubProjectStatus | None]:
    if project.state != "ready":
        return None, None
    try:
        git = await _runtime(request).git_status(
            str(request.state.request_id), project.relative_path
        )
    except RuntimeOperationError as exc:
        raise _translate(exc) from exc
    try:
        github = await _runtime(request).github_project_status(
            str(request.state.request_id), project.relative_path
        )
    except RuntimeOperationError:
        github = None
    return git, github


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> ProjectResponse:
    authenticate_request(request, agentbox_session)
    project = _services(request).projects.get(project_id)
    git, github = await _project_observations(request, project)
    response.headers["Cache-Control"] = "no-store"
    return ProjectResponse(
        request_id=str(request.state.request_id),
        data=project_data(project, git=git, github=github),
    )


@router.get("/{project_id}/git", response_model=ProjectResponse)
async def git_status(
    project_id: str,
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> ProjectResponse:
    return await get_project(project_id, request, response, agentbox_session)


@router.get("/{project_id}/git/branches", response_model=GitBranchListResponse)
async def list_branches(
    project_id: str,
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> GitBranchListResponse:
    authenticate_request(request, agentbox_session)
    project = _services(request).projects.get(project_id, ready=True)
    try:
        branches = await _runtime(request).branches(
            str(request.state.request_id), project.relative_path
        )
    except RuntimeOperationError as exc:
        raise _translate(exc) from exc
    response.headers["Cache-Control"] = "no-store"
    return GitBranchListResponse(
        request_id=str(request.state.request_id),
        data=GitBranchListData(
            branches=[GitBranchData(name=item.name, current=item.current) for item in branches]
        ),
    )


async def _enqueue_mutation(
    project_id: str,
    request: Request,
    raw_session: str | None,
    csrf_token: str | None,
    idempotency_key: str | None,
    *,
    job_type: str,
    payload: dict[str, object],
    audit_action: str,
) -> JobResponse:
    authenticated = _authenticate_mutation(request, raw_session, csrf_token)
    project = _services(request).projects.get(project_id, ready=True)
    full_payload = {"project_key": project.relative_path, **payload}
    job, _created = _enqueue(
        request,
        authenticated,
        project,
        job_type=job_type,
        payload=full_payload,
        idempotency_key=_idempotency(idempotency_key),
    )
    _audit(
        request,
        authenticated,
        action=audit_action,
        project_id=project.id,
        result="requested",
        job_id=job.id,
    )
    return JobResponse(request_id=str(request.state.request_id), data=job_data(job))


@router.post("/{project_id}/git/pull", response_model=JobResponse, status_code=202)
async def pull(
    project_id: str,
    request: Request,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> JobResponse:
    return await _enqueue_mutation(
        project_id,
        request,
        agentbox_session,
        x_csrf_token,
        idempotency_key,
        job_type="git.pull",
        payload={},
        audit_action="git_pull_requested",
    )


@router.post("/{project_id}/git/push", response_model=JobResponse, status_code=202)
async def push(
    project_id: str,
    request: Request,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> JobResponse:
    return await _enqueue_mutation(
        project_id,
        request,
        agentbox_session,
        x_csrf_token,
        idempotency_key,
        job_type="git.push",
        payload={},
        audit_action="git_push_requested",
    )


@router.post("/{project_id}/git/branches", response_model=JobResponse, status_code=202)
async def create_branch(
    project_id: str,
    payload: BranchRequest,
    request: Request,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> JobResponse:
    try:
        branch = validate_branch_name(payload.branch)
    except RuntimeOperationError as exc:
        raise _translate(exc) from exc
    return await _enqueue_mutation(
        project_id,
        request,
        agentbox_session,
        x_csrf_token,
        idempotency_key,
        job_type="git.branch.create",
        payload={"branch": branch},
        audit_action="git_branch_created",
    )


@router.post("/{project_id}/git/switch", response_model=JobResponse, status_code=202)
async def switch_branch(
    project_id: str,
    payload: BranchRequest,
    request: Request,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> JobResponse:
    try:
        branch = validate_branch_name(payload.branch)
    except RuntimeOperationError as exc:
        raise _translate(exc) from exc
    return await _enqueue_mutation(
        project_id,
        request,
        agentbox_session,
        x_csrf_token,
        idempotency_key,
        job_type="git.branch.switch",
        payload={"branch": branch},
        audit_action="git_branch_switched",
    )


@router.post("/{project_id}/github/pull-requests", response_model=JobResponse, status_code=202)
async def create_pull_request(
    project_id: str,
    payload: DraftPullRequestRequest,
    request: Request,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> JobResponse:
    return await _enqueue_mutation(
        project_id,
        request,
        agentbox_session,
        x_csrf_token,
        idempotency_key,
        job_type="github.pr.create",
        payload={"title": payload.title, "body": payload.body, "base": payload.base},
        audit_action="github_pr_create_requested",
    )


@github_router.get("", response_model=GitHubGlobalResponse)
async def github_status(
    request: Request,
    response: Response,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> GitHubGlobalResponse:
    authenticate_request(request, agentbox_session)
    try:
        observed = await _runtime(request).github_status(str(request.state.request_id))
    except RuntimeOperationError as exc:
        raise _translate(exc) from exc
    response.headers["Cache-Control"] = "no-store"
    return GitHubGlobalResponse(
        request_id=str(request.state.request_id),
        data=GitHubGlobalData(
            installed=observed.installed,
            version=observed.version,
            authentication=observed.authentication.value,
        ),
    )
