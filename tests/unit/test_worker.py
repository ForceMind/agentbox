from agentbox_core.services import ControlPlaneServices
from agentbox_worker.main import check_worker


def test_worker_health_uses_database_and_migration_state(
    services: ControlPlaneServices,
) -> None:
    assert check_worker(services)


def test_worker_session_cleanup_is_bounded(
    initialized_services: ControlPlaneServices,
) -> None:
    assert initialized_services.sessions.cleanup() == 0
