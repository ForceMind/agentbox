"""SQLite engine, transaction, pragma, and migration-state infrastructure."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from agentbox_core.configuration import Environment, Settings


class Database:
    """Own a SQLite engine and short SQLAlchemy transaction boundaries."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._sqlite_path = self._get_sqlite_path()
        self._prepare_parent_directory()
        self.engine = self._create_engine()
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    def _prepare_parent_directory(self) -> None:
        if self._sqlite_path is None:
            return
        parent = self._sqlite_path.parent
        if parent.exists():
            if self.settings.env == Environment.PRODUCTION:
                if parent.is_symlink() or not parent.is_dir():
                    raise RuntimeError("production database directory must be a real directory")
                if parent.stat().st_mode & 0o077:
                    raise RuntimeError(
                        "production database directory must not be group/world accessible"
                    )
                if self._sqlite_path.is_symlink():
                    raise RuntimeError("production database file must not be a symbolic link")
            return
        if self.settings.env == Environment.PRODUCTION:
            raise RuntimeError("production database directory must be created by the installer")
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with suppress(OSError):
            os.chmod(parent, 0o700)

    def _create_engine(self) -> Engine:
        timeout_seconds = self.settings.database_busy_timeout_ms / 1000
        engine = create_engine(
            self.settings.database_url,
            connect_args={"check_same_thread": False, "timeout": timeout_seconds},
            pool_pre_ping=True,
        )

        @event.listens_for(engine, "connect")
        def configure_sqlite(dbapi_connection: object, connection_record: object) -> None:
            del connection_record
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute(f"PRAGMA busy_timeout={self.settings.database_busy_timeout_ms}")
                cursor.execute("PRAGMA journal_mode=WAL")
            finally:
                cursor.close()
            self._restrict_sqlite_files()

        return engine

    def _get_sqlite_path(self) -> Path | None:
        url = make_url(self.settings.database_url)
        if not url.database or url.database == ":memory:":
            return None
        return Path(url.database).expanduser()

    def _restrict_sqlite_files(self) -> None:
        if self._sqlite_path is None:
            return
        for suffix in ("", "-wal", "-shm"):
            path = Path(f"{self._sqlite_path}{suffix}")
            if not path.exists():
                continue
            try:
                os.chmod(path, 0o600)
            except OSError:
                if self.settings.env == Environment.PRODUCTION:
                    raise RuntimeError("production database files must be mode 0600") from None

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        """Provide one explicit, bounded commit/rollback boundary."""
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            self._restrict_sqlite_files()

    def check_connection(self) -> bool:
        if self._sqlite_path is not None and not self._sqlite_path.exists():
            return False
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def pragma_state(self) -> dict[str, int | str]:
        with self.engine.connect() as connection:
            return {
                "journal_mode": str(connection.execute(text("PRAGMA journal_mode")).scalar_one()),
                "foreign_keys": int(connection.execute(text("PRAGMA foreign_keys")).scalar_one()),
                "busy_timeout": int(connection.execute(text("PRAGMA busy_timeout")).scalar_one()),
            }

    def migration_state(self, alembic_ini: str | Path | None = None) -> tuple[str | None, str]:
        config = Config(str(alembic_ini or self.settings.alembic_ini))
        script = ScriptDirectory.from_config(config)
        expected = script.get_current_head()
        if expected is None:
            raise RuntimeError("Alembic has no migration head")
        with self.engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
        return current, expected

    def migrations_current(self, alembic_ini: str | Path | None = None) -> bool:
        if self._sqlite_path is not None and not self._sqlite_path.exists():
            return False
        try:
            current, expected = self.migration_state(alembic_ini)
            return current == expected
        except Exception:
            return False

    def close(self) -> None:
        self.engine.dispose()
