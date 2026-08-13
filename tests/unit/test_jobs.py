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


def test_backward_clock_skew_never_replays_or_reassigns_a_running_job(
    initialized_services: ControlPlaneServices,
    clock: FakeClock,
) -> None:
    job = enqueue(
        initialized_services,
        project(initialized_services, "skew-project"),
        "job-skew-backward",
    )
    claimed = initialized_services.jobs.claim_next("worker-original")
    assert claimed is not None and claimed.id == job.id
    clock.advance(seconds=-3600)

    assert initialized_services.jobs.recover_expired() == 0
    assert initialized_services.jobs.claim_next("worker-duplicate") is None
    observed = initialized_services.jobs.get(job.id)
    assert observed is not None
    assert observed.status == "running"
    assert observed.lease_owner == "worker-original"


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
        summary=(
            "token=SECRET-CANARY\n"
            "https://oauth2:URL-CREDENTIAL-CANARY@github.com/owner/repo.git\x1b[31m " + "x" * 900
        ),
    )

    stored = initialized_services.jobs.get(job.id)
    assert stored is not None
    assert stored.error_code == "GIT_PUSH_FAILED"
    assert "SECRET-CANARY" not in str(stored.error_summary)
    assert "URL-CREDENTIAL-CANARY" not in str(stored.error_summary)
    assert "\x1b" not in str(stored.error_summary)
    assert "https://github.com/owner/repo.git" in str(stored.error_summary)
    assert "[REDACTED]" in str(stored.error_summary)
    assert len(str(stored.error_summary)) <= 512


def test_url_credentials_are_redacted_before_summary_truncation(
    initialized_services: ControlPlaneServices,
) -> None:
    job = enqueue(
        initialized_services,
        project(initialized_services, "credential-boundary-project"),
        "credential-boundary-001",
    )
    claimed = initialized_services.jobs.claim_next("worker-test")
    assert claimed is not None and claimed.id == job.id
    canary = "URL-CREDENTIAL-CANARY-" * 40

    initialized_services.jobs.fail(
        job.id,
        code="GIT_PUSH_FAILED",
        summary=(
            f"https://oauth2:{canary}@github.com/owner/repo.git "
            "https://TOKEN-ONLY-CANARY@github.com/owner/other.git"
        ),
    )

    stored = initialized_services.jobs.get(job.id)
    assert stored is not None
    assert "URL-CREDENTIAL-CANARY" not in str(stored.error_summary)
    assert "TOKEN-ONLY-CANARY" not in str(stored.error_summary)
    assert stored.error_summary == (
        "https://github.com/owner/repo.git https://github.com/owner/other.git"
    )
