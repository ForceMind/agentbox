from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from agentbox_api.main import create_app
from agentbox_core.clock import Clock
from agentbox_core.configuration import Environment, Settings
from agentbox_core.security import PasswordManager
from agentbox_core.services import ControlPlaneServices, build_services
from alembic import command
from alembic.config import Config
from pydantic import SecretStr


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@dataclass
class FakeClock(Clock):
    current: datetime = datetime(2026, 8, 9, 0, 0, 0)

    def now(self) -> datetime:
        return self.current

    def advance(self, *, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


def migrate_database(database_url: str, revision: str = "head") -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, revision)


def downgrade_database(database_url: str, revision: str = "-1") -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.downgrade(config, revision)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    return Settings(
        env=Environment.TEST,
        database_url=f"sqlite+pysqlite:///{data_dir / 'agentbox.db'}",
        data_dir=data_dir,
        secret_key=SecretStr("test-only-secret-key-with-at-least-thirty-two-bytes"),
        session_ttl=3600,
        session_idle_ttl=600,
        session_retention=60,
        login_rate_limit=5,
        login_rate_window=300,
        login_lock_duration=300,
        allowed_origins=("http://testserver",),
    )


@pytest.fixture
def password_manager() -> PasswordManager:
    return PasswordManager(time_cost=1, memory_cost=8192, parallelism=1)


@pytest.fixture
def services(
    settings: Settings,
    clock: FakeClock,
    password_manager: PasswordManager,
) -> Iterator[ControlPlaneServices]:
    migrate_database(settings.database_url)
    value = build_services(settings, clock=clock, password_manager=password_manager)
    yield value
    value.database.close()


@pytest.fixture
def initialized_services(services: ControlPlaneServices) -> ControlPlaneServices:
    services.admin.initialize("maintainer", "a sufficiently long passphrase")
    return services


@pytest.fixture
async def client(
    settings: Settings,
    initialized_services: ControlPlaneServices,
) -> AsyncIterator[httpx.AsyncClient]:
    application = create_app(settings, initialized_services)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://testserver",
    ) as test_client:
        yield test_client


@pytest.fixture
def origin_headers() -> dict[str, str]:
    return {"Origin": "http://testserver"}
