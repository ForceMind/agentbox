from __future__ import annotations

from pathlib import Path

import pytest
from agentbox_core.configuration import Environment, Settings
from pydantic import SecretStr, ValidationError


def test_secure_development_defaults_are_loopback_and_ephemeral(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings()

    assert settings.bind_host == "127.0.0.1"
    assert settings.bind_port == 8787
    assert settings.env == Environment.DEVELOPMENT
    assert settings.ephemeral_secret is True
    assert settings.cookie_secure is False
    assert settings.argon2_max_concurrency == 2


@pytest.mark.parametrize("value", [0, 5])
def test_argon2_concurrency_is_strictly_bounded(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(argon2_max_concurrency=value)


def test_environment_overrides_optional_local_toml(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / ".agentbox-dev"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text("bind_port = 9001\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENTBOX_BIND_PORT", "9002")

    assert Settings().bind_port == 9002


@pytest.mark.parametrize("bind_host", ["0.0.0.0", "192.0.2.10"])
def test_production_rejects_non_loopback_bind(bind_host: str, tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="loopback"):
        Settings(
            env=Environment.PRODUCTION,
            bind_host=bind_host,
            secret_key=SecretStr("x" * 48),
            data_dir=tmp_path,
            database_url=f"sqlite+pysqlite:///{tmp_path / 'agentbox.db'}",
            allowed_origins=("https://agentbox.example",),
        )


def test_production_rejects_missing_or_short_secret(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(
            env=Environment.PRODUCTION,
            data_dir=tmp_path,
            database_url=f"sqlite+pysqlite:///{tmp_path / 'agentbox.db'}",
        )

    with pytest.raises(ValidationError, match="32 bytes"):
        Settings(
            env=Environment.PRODUCTION,
            secret_key=SecretStr("short"),
            data_dir=tmp_path,
            database_url=f"sqlite+pysqlite:///{tmp_path / 'agentbox.db'}",
        )


def test_production_rejects_database_outside_data_dir() -> None:
    with pytest.raises(ValidationError, match="beneath"):
        Settings(
            env=Environment.PRODUCTION,
            secret_key=SecretStr("x" * 48),
            data_dir=Path("/var/lib/agentbox"),
            database_url="sqlite+pysqlite:////srv/agentbox.db",
            allowed_origins=("https://agentbox.example",),
        )


def test_production_cookie_policy_is_secure() -> None:
    settings = Settings(
        env=Environment.PRODUCTION,
        secret_key=SecretStr("x" * 48),
        data_dir=Path("/var/lib/agentbox"),
        database_url="sqlite+pysqlite:////var/lib/agentbox/agentbox.db",
        runtime_socket=Path("/run/agentbox/runtime.sock"),
        allowed_origins=("https://agentbox.example",),
    )

    assert settings.cookie_secure is True


def test_production_rejects_non_https_remote_origin() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            env=Environment.PRODUCTION,
            secret_key=SecretStr("x" * 48),
            data_dir=Path("/var/lib/agentbox"),
            database_url="sqlite+pysqlite:////var/lib/agentbox/agentbox.db",
            allowed_origins=("http://agentbox.example",),
        )


def test_safe_summary_never_includes_secret_or_database_path(settings: Settings) -> None:
    summary = settings.safe_summary()
    rendered = repr(summary)

    assert settings.secret_key.get_secret_value() not in rendered
    assert settings.database_url not in rendered
    assert summary["database_backend"] == "sqlite"


def test_non_sqlite_database_is_rejected() -> None:
    with pytest.raises(ValidationError, match="SQLite"):
        Settings(database_url="postgresql://localhost/agentbox")
