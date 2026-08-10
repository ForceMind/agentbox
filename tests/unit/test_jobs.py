from __future__ import annotations

from agentbox_core.models import Job
from agentbox_core.services import ControlPlaneServices
from conftest import FakeClock


def project(services: ControlPlaneServices, slug: str) -> str:
    services.projects.reconcile_existing((slug,))
    return services.projects.resolve(slug).id


def enqueue(services: ControlPlaneServices, project_id: str, key: str) -> Job:
    return services.jobs.enqueue(
        job_type="git.pull",
        requested_by="adm_fixture",
        target_type="project",
        target_id=project_id,
        project_id=project_id,
        payload={"project_key": "safe-project"},
        resource_lock_key=f"project:{project_id}",
        idempotency_key=key,
        request_id="req_job_fixture",
    )[0]


def test_jobs_with_same_project_resource_are_serialized(
    initialized_services: ControlPlaneServices,
) -> None:
    project_id = project(initialized_services, "serialize-project")
    first = enqueue(initialized_services, project_id, "job-serialize-first")
    second = enqueue(initialized_services, project_id, "job-serialize-second")

    claimed = initialized_services.jobs.claim_next("worker-one")
    assert claimed is not None and claimed.id == first.id
    assert initialized_services.jobs.claim_next("worker-two") is None

    initialized_services.jobs.succeed(first.id, "completed")
    claimed = initialized_services.jobs.claim_next("worker-two")
    assert claimed is not None and claimed.id == second.id


def test_expired_running_job_recovers_to_needs_attention_without_replay(
    initialized_services: ControlPlaneServices,
    clock: FakeClock,
) -> None:
    job = enqueue(
        initialized_services,
        project(initialized_services, "recovery-project"),
        "job-recovery-fixture",
    )
    claimed = initialized_services.jobs.claim_next("worker-crashed")
    assert claimed is not None
    clock.advance(seconds=121)

    assert initialized_services.jobs.recover_expired() == 1
    recovered = initialized_services.jobs.get(job.id)
    assert recovered is not None
    assert recovered.status == "needs_attention"
    assert recovered.error_code == "JOB_EXECUTION_INTERRUPTED"
    assert initialized_services.jobs.claim_next("worker-restart") is None


def test_running_job_heartbeat_renews_lease_without_creating_progress_noise(
    initialized_services: ControlPlaneServices,
    clock: FakeClock,
) -> None:
    job = enqueue(
        initialized_services,
        project(initialized_services, "heartbeat-project"),
        "job-heartbeat-fixture",
    )
    assert initialized_services.jobs.claim_next("worker-heartbeat") is not None
    events_before = [
        event.event_type for event in initialized_services.jobs.events_after(job.id, 0)
    ]
    clock.advance(seconds=100)
    initialized_services.jobs.heartbeat(job.id)
    clock.advance(seconds=30)
    assert initialized_services.jobs.recover_expired() == 0
    assert [
        event.event_type for event in initialized_services.jobs.events_after(job.id, 0)
    ] == events_before

    clock.advance(seconds=91)
    assert initialized_services.jobs.recover_expired() == 1


def test_job_summaries_are_bounded_redacted_and_raw_output_is_not_persisted(
    initialized_services: ControlPlaneServices,
) -> None:
    job = enqueue(
        initialized_services,
        project(initialized_services, "safe-project"),
        "job-redaction-fixture",
    )
    assert initialized_services.jobs.claim_next("worker-safe") is not None
    initialized_services.jobs.fail(
        job.id,
        code="GIT_PUSH_FAILED",
        summary="token=SECRET-CANARY\n" + "x" * 900,
    )

    stored = initialized_services.jobs.get(job.id)
    assert stored is not None
    assert stored.error_code == "GIT_PUSH_FAILED"
    assert "SECRET-CANARY" not in str(stored.error_summary)
    assert "[REDACTED]" in str(stored.error_summary)
    assert len(str(stored.error_summary)) <= 512
