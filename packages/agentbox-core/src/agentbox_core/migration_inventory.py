"""Frozen structural inventory for the reviewed 0004/0005 SQLite boundary.

Expected values are checked-in literals exported from empty canonical revisions,
not from the database being admitted. SQL tokenization preserves literal bytes;
only whitespace and identifier quoting/case are presentation differences.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL, Connection
from sqlalchemy.exc import SQLAlchemyError

from agentbox_core.migration_inventory_v1 import INVENTORIES

_SQL_TOKEN = re.compile(
    r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`[^`]*`|\[[^]]*\]|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|<>|!=|>=|<=|==|\|\||[^\s]",
    re.DOTALL,
)


def sql_tokens(value: str | None) -> str:
    tokens = []
    for token in _SQL_TOKEN.findall(value or ""):
        if token.startswith("'"):
            tokens.append(token)
        elif token.startswith(('"', "`", "[")):
            tokens.append(token[1:-1].lower())
        else:
            tokens.append(token.lower())
    return " ".join(tokens)


def structural_inventory(connection: Connection, tables: set[str]) -> dict[str, Any]:
    inspector = inspect(connection)
    inventory: dict[str, Any] = {}
    for table in sorted(tables):
        if not inspector.has_table(table):
            continue
        inventory[table] = {
            "index_semantics": index_semantics(connection, table),
            "columns": [
                [c["name"], str(c["type"]).upper(), c["nullable"], sql_tokens(c["default"])]
                for c in inspector.get_columns(table)
            ],
            "pk": inspector.get_pk_constraint(table)["constrained_columns"],
            "fk": sorted(
                [
                    [
                        f["name"],
                        f["constrained_columns"],
                        f["referred_table"],
                        f["referred_columns"],
                        f.get("options", {}),
                    ]
                    for f in inspector.get_foreign_keys(table)
                ],
                key=repr,
            ),
            "unique": sorted(
                [[u["name"], u["column_names"]] for u in inspector.get_unique_constraints(table)],
                key=repr,
            ),
            "checks": sorted(
                [
                    [c["name"], sql_tokens(c["sqltext"])]
                    for c in inspector.get_check_constraints(table)
                ],
                key=repr,
            ),
            "indexes": sorted(
                [
                    [
                        i["name"],
                        i["column_names"],
                        bool(i["unique"]),
                        sql_tokens(str(i.get("dialect_options", {}).get("sqlite_where", ""))),
                    ]
                    for i in inspector.get_indexes(table)
                ],
                key=repr,
            ),
            "triggers": [
                [row[0], sql_tokens(row[1])]
                for row in connection.exec_driver_sql(
                    "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND "
                    "tbl_name=? ORDER BY name",
                    (table,),
                )
            ],
        }
    return inventory


def verify_phase11_inventory(connection: Connection, revision: str, error: str) -> None:
    expected = INVENTORIES[revision]
    tables = set(expected)
    if structural_inventory(connection, tables) != expected:
        raise RuntimeError(error)
    # Unknown children of a rebuilt parent, or leftover rebuild/new objects, are
    # relevant drift. SQLite-owned objects and unrelated application tables are not.
    for table in inspect(connection).get_table_names():
        if table in tables or table.startswith("sqlite_") or table == "alembic_version":
            continue
        if table in {
            "confirmation_challenges",
            "provider_secret_provisioning_attempts",
        } or table in {
            f"{parent}_{suffix}"
            for parent in ("sessions", "provider_credentials", "runtime_provider_profiles")
            for suffix in ("new", "old")
        }:
            raise RuntimeError(error)
        if any(
            f["referred_table"] in {"sessions", "provider_credentials", "runtime_provider_profiles"}
            for f in inspect(connection).get_foreign_keys(table)
        ):
            raise RuntimeError(error)


def verify_phase11_database(path: Path, expected_revision: str) -> bool:
    """Read-only installer activation/restore gate for exact reviewed schemas."""
    engine = create_engine(
        URL.create("sqlite+pysqlite", database=f"file:{path}", query={"mode": "ro", "uri": "true"})
    )
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA query_only=ON")
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.exec_driver_sql("BEGIN")
            if tuple(
                connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalars()
            ) != (expected_revision,):
                return False
            verify_phase11_inventory(
                connection, expected_revision, "PHASE11_0005_RESTORE_INVENTORY_FAILED"
            )
            return connection.exec_driver_sql("PRAGMA foreign_key_check").all() == [] and [
                tuple(row) for row in connection.exec_driver_sql("PRAGMA quick_check")
            ] == [("ok",)]
    except (RuntimeError, SQLAlchemyError):
        return False
    finally:
        engine.dispose()


def index_semantics(connection: Connection, table: str) -> list[object]:
    """Include implicit PK/UNIQUE indexes, sort order, expressions and collation."""
    indexes = []
    for row in connection.exec_driver_sql(f'PRAGMA index_list("{table}")'):
        name = str(row[1]).replace('"', '""')
        columns = [
            list(column)[1:]
            for column in connection.exec_driver_sql(f'PRAGMA index_xinfo("{name}")')
        ]
        indexes.append([row[2], row[3], row[4], columns])
    # Autoindex names and enumeration order are SQLite implementation details.
    return sorted(indexes, key=repr)
