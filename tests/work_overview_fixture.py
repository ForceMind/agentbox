"""Synthetic durable metadata for the formal App's read-only overview E2E."""

from datetime import UTC, datetime, timedelta

from agentbox_core.models import AdminUser, Job, Project
from agentbox_core.services import ControlPlaneServices
from sqlalchemy import select


def seed_work_overview(services: ControlPlaneServices) -> None:
    """Only called by the isolated test application, never a production route."""
    base = datetime(2026, 10, 5, 8, tzinfo=UTC)
    with services.database.transaction() as session:
        admin = session.scalar(select(AdminUser).where(AdminUser.is_active.is_(True)))
        if admin is None:
            raise RuntimeError("overview fixture requires its isolated administrator")
        projects = []
        for index, name in enumerate(("工作台示例", "资料站 · 文档", "界面组件 🚀"), start=1):
            project = Project(
                id=f"prj_{index + 9000:032x}",
                slug=f"overview-fixture-{index}",
                relative_path=f"overview-fixture-{index}",
                display_name=name,
                source_type="empty",
                state="ready",
                revision=1,
                created_at=base - timedelta(days=3),
                updated_at=base + timedelta(minutes=index),
            )
            session.add(project)
            projects.append(project)
        session.flush()
        for index, status in enumerate(
            ("needs_attention", "running", "queued", "succeeded", "failed"), start=1
        ):
            project = projects[(index - 1) % len(projects)]
            session.add(
                Job(
                    id=f"job_{index + 9000:032x}",
                    type="git.pull" if index == 1 else "project.clone",
                    status=status,
                    requested_by=admin.id,
                    target_type="project",
                    target_id=project.id,
                    project_id=project.id,
                    created_at=base + timedelta(minutes=index),
                    progress=42,
                    phase="OVERVIEW-PRIVATE-PHASE",
                    result_summary="OVERVIEW-PRIVATE-RESULT",
                    error_summary="OVERVIEW-PRIVATE-ERROR",
                    error_code="JOB_EXECUTION_INTERRUPTED" if index == 1 else None,
                    payload_json={},
                    idempotency_key_digest=f"{index + 9000:064x}",
                    resource_lock_key=f"overview-fixture:{index}",
                )
            )
        session.add(
            Job(
                id="job_" + "f" * 32,
                type="project.clone",
                status="needs_attention",
                requested_by="adm_other_fixture_user",
                target_type="project",
                created_at=base + timedelta(days=1),
                payload_json={},
                idempotency_key_digest="f" * 64,
                resource_lock_key="overview-fixture:other",
            )
        )
