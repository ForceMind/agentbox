"""Typed AgentBox configuration with secure environment-specific validation."""

from __future__ import annotations

import ipaddress
import os
import secrets
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import Field, PrivateAttr, SecretStr, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)
from sqlalchemy.engine import make_url


class Environment(StrEnum):
    """Supported control-plane execution environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """AgentBox configuration.

    Explicit environment variables take precedence over the optional local
    development TOML file. Production validation fails closed instead of
    silently accepting development-only defaults.
    """

    model_config = SettingsConfigDict(
        env_prefix="AGENTBOX_",
        case_sensitive=False,
        extra="forbid",
        toml_file=Path(".agentbox-dev/config.toml"),
    )

    env: Environment = Environment.DEVELOPMENT
    bind_host: str = "127.0.0.1"
    bind_port: int = Field(default=8787, ge=1, le=65535)
    database_url: str = "sqlite+pysqlite:///./.agentbox-dev/agentbox.db"
    alembic_ini: Path = Path("alembic.ini")
    secret_key: SecretStr = SecretStr("")
    session_ttl: int = Field(default=8 * 60 * 60, ge=300, le=30 * 24 * 60 * 60)
    session_idle_ttl: int = Field(default=30 * 60, ge=60, le=24 * 60 * 60)
    session_retention: int = Field(default=24 * 60 * 60, ge=0, le=90 * 24 * 60 * 60)
    max_active_sessions: int = Field(default=10, ge=1, le=100)
    login_rate_limit: int = Field(default=5, ge=1, le=100)
    login_rate_window: int = Field(default=5 * 60, ge=10, le=24 * 60 * 60)
    login_lock_duration: int = Field(default=5 * 60, ge=10, le=24 * 60 * 60)
    argon2_max_concurrency: int = Field(default=2, ge=1, le=4)
    codex_pair_cooldown: int = Field(default=10, ge=5, le=300)
    recent_auth_ttl: int = Field(default=10 * 60, ge=60, le=60 * 60)
    runtime_socket: Path = Path(".agentbox-dev/runtime.sock")
    project_root: Path = Path(".agentbox-dev/projects")
    data_dir: Path = Path(".agentbox-dev")
    static_dir: Path | None = None
    job_lease_seconds: int = Field(default=120, ge=30, le=3600)
    job_poll_interval: float = Field(default=1.0, ge=0.1, le=60.0)
    database_busy_timeout_ms: int = Field(default=5000, ge=100, le=60_000)
    request_body_limit: int = Field(default=16 * 1024, ge=1024, le=1024 * 1024)
    trusted_proxies: tuple[str, ...] = ()
    allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1:8787",
        "http://localhost:8787",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )

    _ephemeral_secret: bool = PrivateAttr(default=False)

    @model_validator(mode="before")
    @classmethod
    def production_project_root_default(cls, values: Any) -> Any:
        """Select the documented production root unless an explicit value was supplied."""
        if isinstance(values, dict) and values.get("env") in {
            Environment.PRODUCTION,
            Environment.PRODUCTION.value,
        }:
            values.setdefault("project_root", Path("/srv/agentbox/projects"))
            values.setdefault("static_dir", Path("/opt/agentbox/current/web/dist"))
            values.setdefault("alembic_ini", Path("/opt/agentbox/current/alembic.ini"))
        return values

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Order sources as environment, explicit construction, local TOML, defaults."""
        del dotenv_settings
        return (
            env_settings,
            init_settings,
            TomlConfigSettingsSource(
                settings_cls,
                toml_file=Path(os.environ.get("AGENTBOX_TOML_FILE", ".agentbox-dev/config.toml")),
            ),
            file_secret_settings,
        )

    @field_validator("bind_host")
    @classmethod
    def validate_bind_host(cls, value: str) -> str:
        try:
            ipaddress.ip_address(value)
        except ValueError as exc:
            raise ValueError("bind_host must be an IP address") from exc
        return value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        try:
            url = make_url(value)
        except Exception as exc:
            raise ValueError("database_url must be a valid SQLAlchemy URL") from exc
        if url.get_backend_name() != "sqlite":
            raise ValueError("Phase 3 supports SQLite databases only")
        return value

    @field_validator("trusted_proxies")
    @classmethod
    def validate_trusted_proxies(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            try:
                ipaddress.ip_network(value, strict=False)
            except ValueError as exc:
                raise ValueError("trusted_proxies must contain IP networks") from exc
        return values

    @field_validator("allowed_origins")
    @classmethod
    def validate_allowed_origins(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            if value == "*" or not value.startswith(("http://", "https://")):
                raise ValueError("allowed_origins must contain exact HTTP(S) origins")
            if value.endswith("/"):
                raise ValueError("allowed_origins must not end with a slash")
        return values

    @model_validator(mode="after")
    def validate_environment_safety(self) -> Settings:
        if self.session_idle_ttl > self.session_ttl:
            raise ValueError("session_idle_ttl cannot exceed session_ttl")

        key = self.secret_key.get_secret_value()
        if not key:
            if self.env == Environment.PRODUCTION:
                raise ValueError("AGENTBOX_SECRET_KEY is required in production")
            self.secret_key = SecretStr(secrets.token_urlsafe(48))
            self._ephemeral_secret = True

        if self.env == Environment.PRODUCTION:
            self._validate_production()
        return self

    def _validate_production(self) -> None:
        key_bytes = self.secret_key.get_secret_value().encode("utf-8")
        if len(key_bytes) < 32:
            raise ValueError("AGENTBOX_SECRET_KEY must contain at least 32 bytes")

        if not ipaddress.ip_address(self.bind_host).is_loopback:
            raise ValueError("production Web/API must bind to a loopback address")

        for origin in self.allowed_origins:
            parsed_origin = urlsplit(origin)
            if parsed_origin.scheme != "https":
                raise ValueError("production authentication origins must use HTTPS")

        data_dir = self.data_dir.expanduser()
        if not data_dir.is_absolute() or data_dir.is_relative_to(Path("/tmp")):
            raise ValueError("production AGENTBOX_DATA_DIR must be an absolute non-temporary path")

        url = make_url(self.database_url)
        if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
            raise ValueError("production requires a file-backed SQLite database")
        database_path = Path(url.database).expanduser()
        if not database_path.is_absolute() or not database_path.is_relative_to(data_dir):
            raise ValueError("production SQLite database must be beneath AGENTBOX_DATA_DIR")
        if not self.runtime_socket.is_absolute() or self.runtime_socket.parent != Path(
            "/run/agentbox"
        ):
            raise ValueError("production Runtime socket must be beneath /run/agentbox")
        if self.project_root != Path("/srv/agentbox/projects"):
            raise ValueError("production project root must be /srv/agentbox/projects")
        if self.static_dir is None or not self.static_dir.is_absolute():
            raise ValueError("production AGENTBOX_STATIC_DIR must be an absolute path")
        if not self.alembic_ini.is_absolute():
            raise ValueError("production Alembic configuration path must be absolute")

    @property
    def cookie_secure(self) -> bool:
        """Require secure cookies outside loopback-only development/test HTTP."""
        return self.env == Environment.PRODUCTION

    @property
    def ephemeral_secret(self) -> bool:
        """Whether this process generated a non-persistent development secret."""
        return self._ephemeral_secret

    def safe_summary(self) -> dict[str, Any]:
        """Return diagnostics that cannot disclose secret or filesystem values."""
        return {
            "environment": self.env.value,
            "bind_host": self.bind_host,
            "bind_port": self.bind_port,
            "database_backend": make_url(self.database_url).get_backend_name(),
            "secret_source": "ephemeral" if self.ephemeral_secret else "configured",
            "cookie_secure": self.cookie_secure,
            "argon2_max_concurrency": self.argon2_max_concurrency,
        }
