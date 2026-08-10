"""Phase 3 Worker lifecycle and expired-session maintenance."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import signal
from collections.abc import Coroutine, Sequence
from typing import Any, TypeVar

from agentbox_core import __version__
from agentbox_core.configuration import Settings
from agentbox_core.models import Job
from agentbox_core.services import ControlPlaneServices, build_services
from agentbox_runtime import ProjectRuntimeClient, RuntimeOperationError, UnixProjectRuntimeClient

_SUCCESS_AUDIT = {
    "project.create": "project_created",
    "project.clone": "project_clone_succeeded",
    "git.pull": "git_pull_succeeded",
    "git.push": "git_push_succeeded",
    "git.branch.create": "git_branch_created",
    "git.branch.switch": "git_branch_switched",
    "github.pr.create": "github_pr_create_succeeded",
}
_FAILURE_AUDIT = {
    "project.create": "project_create_failed",
    "project.clone": "project_clone_failed",
    "git.pull": "git_pull_failed",
    "git.push": "git_push_failed",
    "git.branch.create": "git_branch_create_failed",
    "git.branch.switch": "git_branch_switch_failed",
    "github.pr.create": "github_pr_create_failed",
}
_T = TypeVar("_T")


async def _runtime_call(
    services: ControlPlaneServices, job_id: str, operation: Coroutine[Any, Any, _T]
) -> _T:
    """Keep the durable lease alive while one bounded Runtime RPC is in flight."""
    task = asyncio.create_task(operation)
    try:
        while True:
            try:
                return await asyncio.wait_for(
                    asyncio.shield(task),
                    timeout=services.jobs.heartbeat_interval_seconds,
                )
            except TimeoutError:
                services.jobs.heartbeat(job_id)
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentbox-worker")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--check", action="store_true", help="check database readiness and exit")
    parser.add_argument("--once", action="store_true", help="run one session cleanup pass and exit")
    return parser


def check_worker(services: ControlPlaneServices) -> bool:
    return services.database.check_connection() and services.database.migrations_current()


def _audit_job(
    services: ControlPlaneServices,
    job: Job,
    *,
    action: str,
    result: str,
    error_code: str | None = None,
) -> None:
    metadata: dict[str, object] = {
        "job_id": job.id,
        "project_id": job.project_id,
    }
    if error_code:
        metadata["error_code"] = error_code
    with services.database.transaction() as session:
        services.audit.record(
            session,
            actor_type="admin",
            actor_id=job.requested_by,
            action=action,
            result=result,
            request_id=job.request_id,
            target_type="project",
            target_id=job.project_id,
            metadata=metadata,
        )


def _mark_rollback_attention(
    services: ControlPlaneServices,
    job: Job,
    *,
    job_type: str,
    project_id: str,
) -> None:
    """Persist an uncertain cleanup state and best-effort failure audit."""
    services.jobs.needs_attention(
        job.id,
        code="PROJECT_ROLLBACK_REQUIRES_ATTENTION",
        summary="Workspace cleanup requires review",
    )
    services.projects.mark_error(project_id)
    try:
        _audit_job(
            services,
            job,
            action=_FAILURE_AUDIT[job_type],
            result="failed",
            error_code="PROJECT_ROLLBACK_REQUIRES_ATTENTION",
        )
    except Exception:
        # The Job already advertises an operator-review state. Never obscure the
        # original Runtime failure or attempt another terminal transition here.
        return


def _finish_failure(
    services: ControlPlaneServices,
    job: Job,
    *,
    job_type: str,
    error_code: str,
    summary: str,
) -> None:
    """Audit an operation failure before making its Job terminal."""
    try:
        _audit_job(
            services,
            job,
            action=_FAILURE_AUDIT[job_type],
            result="failed",
            error_code=error_code,
        )
    except Exception:
        services.jobs.needs_attention(
            job.id,
            code="JOB_AUDIT_FAILED",
            summary="Operation failed and audit persistence requires review",
        )
        return
    services.jobs.fail(job.id, code=error_code, summary=summary)


async def execute_job(
    services: ControlPlaneServices, runtime: ProjectRuntimeClient, job: Job
) -> None:
    job_id = job.id
    job_type = job.type
    project_id = str(job.project_id)
    payload = dict(job.payload_json)
    project_key = str(payload.get("project_key", ""))
    request_id = str(job.request_id or f"req_worker-{job_id}")
    try:
        services.jobs.progress(
            job_id, progress=25, phase="executing", summary="Operation executing"
        )
        if job_type == "project.create":
            await _runtime_call(
                services, job_id, runtime.create_workspace(request_id, project_key, job_id)
            )
            services.projects.mark_ready(project_id)
            await _runtime_call(
                services, job_id, runtime.finalize_workspace(request_id, project_key, job_id)
            )
        elif job_type == "project.clone":
            repository_url = str(payload.get("repository_url", ""))
            cloned = await _runtime_call(
                services,
                job_id,
                runtime.clone_workspace(request_id, project_key, job_id, repository_url),
            )
            services.projects.mark_ready(project_id, default_branch=cloned.branch)
            await _runtime_call(
                services, job_id, runtime.finalize_workspace(request_id, project_key, job_id)
            )
        elif job_type == "git.pull":
            await _runtime_call(services, job_id, runtime.pull(request_id, project_key))
        elif job_type == "git.push":
            await _runtime_call(services, job_id, runtime.push(request_id, project_key))
        elif job_type == "git.branch.create":
            await _runtime_call(
                services,
                job_id,
                runtime.create_branch(request_id, project_key, str(payload.get("branch", ""))),
            )
        elif job_type == "git.branch.switch":
            await _runtime_call(
                services,
                job_id,
                runtime.switch_branch(request_id, project_key, str(payload.get("branch", ""))),
            )
        elif job_type == "github.pr.create":
            base_value = payload.get("base")
            await _runtime_call(
                services,
                job_id,
                runtime.create_draft_pr(
                    request_id,
                    project_key,
                    str(payload.get("title", "")),
                    str(payload.get("body", "")),
                    str(base_value) if base_value is not None else None,
                ),
            )
        else:
            raise RuntimeError("Unsupported queued Job type")
        try:
            _audit_job(
                services,
                job,
                action=_SUCCESS_AUDIT[job_type],
                result="succeeded",
            )
        except Exception:
            services.jobs.needs_attention(
                job_id,
                code="JOB_AUDIT_FAILED",
                summary="Operation completed but audit persistence requires review",
            )
            return
        services.jobs.succeed(job_id, "Operation completed")
    except RuntimeOperationError as exc:
        if job_type in {"project.create", "project.clone"}:
            try:
                await _runtime_call(
                    services,
                    job_id,
                    runtime.rollback_workspace(request_id, project_key, job_id),
                )
            except Exception:
                _mark_rollback_attention(
                    services,
                    job,
                    job_type=job_type,
                    project_id=project_id,
                )
                return
            services.projects.mark_error(project_id)
        _finish_failure(
            services,
            job,
            job_type=job_type,
            error_code=exc.code,
            summary=exc.message,
        )
    except Exception:
        if job_type in {"project.create", "project.clone"}:
            try:
                await _runtime_call(
                    services,
                    job_id,
                    runtime.rollback_workspace(request_id, project_key, job_id),
                )
            except Exception:
                _mark_rollback_attention(
                    services,
                    job,
                    job_type=job_type,
                    project_id=project_id,
                )
                return
            services.projects.mark_error(project_id)
        _finish_failure(
            services,
            job,
            job_type=job_type,
            error_code="JOB_EXECUTION_FAILED",
            summary="Operation failed without exposing command output",
        )


async def run_worker(
    services: ControlPlaneServices,
    runtime: ProjectRuntimeClient,
    cleanup_interval: float = 60.0,
    job_poll_interval: float = 1.0,
) -> None:
    """Run bounded maintenance and one durable typed Job at a time."""
    shutdown_requested = asyncio.Event()
    loop = asyncio.get_running_loop()

    for shutdown_signal in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(shutdown_signal, shutdown_requested.set)

    print(f"AgentBox Worker {__version__}: control-plane maintenance ready")
    worker_id = f"worker-{os.getpid()}"
    services.jobs.recover_expired()
    next_cleanup = 0.0
    while not shutdown_requested.is_set():
        now = loop.time()
        if now >= next_cleanup:
            services.sessions.cleanup()
            next_cleanup = now + cleanup_interval
        job = services.jobs.claim_next(worker_id)
        if job is not None:
            await execute_job(services, runtime, job)
            continue
        try:
            await asyncio.wait_for(shutdown_requested.wait(), timeout=job_poll_interval)
        except TimeoutError:
            continue
    print("AgentBox Worker: clean shutdown")


def main(argv: Sequence[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    settings = Settings()
    services = build_services(settings)
    runtime = UnixProjectRuntimeClient(settings.runtime_socket)
    try:
        if args.check:
            ready = check_worker(services)
            print(f"AgentBox Worker: {'ready' if ready else 'not ready'}")
            return 0 if ready else 10
        if args.once:
            if not check_worker(services):
                print("AgentBox Worker: not ready")
                return 10
            deleted = services.sessions.cleanup()
            services.jobs.recover_expired()
            job = services.jobs.claim_next(f"worker-once-{os.getpid()}")
            if job is not None:
                asyncio.run(execute_job(services, runtime, job))
            print(
                "AgentBox Worker: maintenance complete "
                f"({deleted} sessions removed, {'one Job' if job else 'no Jobs'})"
            )
            return 0

        if not check_worker(services):
            print("AgentBox Worker: database or migrations not ready")
            return 10
        asyncio.run(
            run_worker(
                services,
                runtime,
                job_poll_interval=settings.job_poll_interval,
            )
        )
        return 0
    finally:
        services.database.close()
