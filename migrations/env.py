"""Alembic environment for the AgentBox control-plane database."""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from agentbox_core.models import Base
from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def configured_database_url() -> str:
    url = os.environ.get("AGENTBOX_DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    if not url:
        raise RuntimeError("database URL is required")
    parsed = make_url(url)
    database = parsed.database
    if parsed.get_backend_name() == "sqlite" and database is not None and database != ":memory:":
        parent = Path(database).expanduser().parent
        if not parent.exists():
            if os.environ.get("AGENTBOX_ENV", "development") == "production":
                raise RuntimeError("production database directory must be created by the installer")
            parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    return url


def run_migrations_offline() -> None:
    url = configured_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    config.set_main_option("sqlalchemy.url", configured_database_url().replace("%", "%%"))
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
