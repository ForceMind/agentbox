from __future__ import annotations

from pathlib import Path

import pytest
from conftest import downgrade_database, migrate_database  # type: ignore[import-not-found]
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

PROJECT_ID = "prj_" + "1" * 32
HOST_ID = "wri_" + "2" * 32
WORKSPACE_ID = "aws_" + "3" * 32
TERMINAL_WORKSPACE_ID = "aws_" + "4" * 32
PENDING_STOP_ID = "wso_" + "5" * 32
TERMINAL_STOP_ID = "wso_" + "6" * 32


def _url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path}"


@pytest.mark.parametrize("terminal_state", ("STOPPED", "EXITED"))
def test_0009_upgrade_fences_only_nonterminal_legacy_workspace_and_stop(
    tmp_path: Path, terminal_state: str
) -> None:
    database_url = _url(tmp_path / "legacy-waw.db")
    migrate_database(database_url, "0008_waw_runtime_epoch_fence")
    engine = create_engine(database_url)
    timestamp = "2026-09-05 00:00:00.000000"
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO projects "
                    "(id,slug,display_name,relative_path,source_type,repository_url,"
                    "default_branch,state,archived_at,created_at,updated_at) VALUES "
                    "(:id,'demo','Demo','demo','empty',NULL,NULL,'ready',NULL,:now,:now)"
                ),
                {"id": PROJECT_ID, "now": timestamp},
            )
            connection.execute(
                text(
                    "INSERT INTO waw_runtime_host_installations "
                    "(id,revision,runtime_type,created_at,updated_at,last_runtime_epoch) "
                    "VALUES (:id,1,'agentbox-runtime-linux-v1',:now,:now,NULL)"
                ),
                {"id": HOST_ID, "now": timestamp},
            )
            connection.execute(
                text(
                    "INSERT INTO waw_agent_workspace_sessions "
                    "(id,project_id,authorization_scope,runtime_host_installation_id,"
                    "runtime_host_installation_revision,runtime_type,agent_type,state,"
                    "runtime_session_name,runtime_marker,executable_fingerprint,generation,"
                    "binding_revision,binding_digest,revision,created_at,updated_at,last_seen_at,"
                    "exit_code,failure_code,reconciliation_state) VALUES "
                    "(:workspace,:project,'admin',:host,1,'agentbox-runtime-linux-v1',"
                    "'claude','RUNNING','agentbox-waw-claude-1111111111111111',"
                    "'waw-v1:fixture',:fingerprint,1,1,:digest,1,:now,:now,:now,NULL,NULL,"
                    "'authoritative')"
                ),
                {
                    "workspace": WORKSPACE_ID,
                    "project": PROJECT_ID,
                    "host": HOST_ID,
                    "fingerprint": "b" * 64,
                    "digest": "a" * 64,
                    "now": timestamp,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO waw_agent_workspace_sessions "
                    "(id,project_id,authorization_scope,runtime_host_installation_id,"
                    "runtime_host_installation_revision,runtime_type,agent_type,state,"
                    "runtime_session_name,runtime_marker,executable_fingerprint,generation,"
                    "binding_revision,binding_digest,revision,created_at,updated_at,last_seen_at,"
                    "exit_code,failure_code,reconciliation_state) VALUES "
                    "(:workspace,:project,'admin',:host,1,'agentbox-runtime-linux-v1',"
                    "'codex',:state,'agentbox-waw-codex-1111111111111111',"
                    "'waw-v1:terminal',:fingerprint,1,1,:digest,7,:now,:now,:now,NULL,NULL,"
                    "'authoritative')"
                ),
                {
                    "workspace": TERMINAL_WORKSPACE_ID,
                    "project": PROJECT_ID,
                    "host": HOST_ID,
                    "state": terminal_state,
                    "fingerprint": "d" * 64,
                    "digest": "c" * 64,
                    "now": timestamp,
                },
            )
            for stop_id, workspace_id, agent_type, digest in (
                (PENDING_STOP_ID, WORKSPACE_ID, "claude", "a" * 64),
                (TERMINAL_STOP_ID, TERMINAL_WORKSPACE_ID, "codex", "c" * 64),
            ):
                connection.execute(
                    text(
                        "INSERT INTO waw_workspace_stop_operations "
                        "(id,workspace_id,project_id,agent_type,generation,binding_revision,"
                        "binding_digest,runtime_host_installation_id,"
                        "runtime_host_installation_revision,result,failure_code,created_at,"
                        "updated_at) VALUES "
                        "(:id,:workspace,:project,:agent,1,1,:digest,:host,1,'PENDING',NULL,"
                        ":now,:now)"
                    ),
                    {
                        "id": stop_id,
                        "workspace": workspace_id,
                        "project": PROJECT_ID,
                        "agent": agent_type,
                        "digest": digest,
                        "host": HOST_ID,
                        "now": timestamp,
                    },
                )
    finally:
        engine.dispose()

    migrate_database(database_url)
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT revision FROM projects WHERE id=:id"), {"id": PROJECT_ID}
                ).scalar_one()
                == 1
            )
            assert (
                connection.execute(text("SELECT count(*) FROM waw_project_bindings")).scalar_one()
                == 0
            )
            migrated = connection.execute(
                text(
                    "SELECT state,reconciliation_state,failure_code,revision,"
                    "executable_fingerprint,executable_evidence_state,"
                    "executable_evidence_generation,executable_evidence_runtime_epoch "
                    "FROM waw_agent_workspace_sessions WHERE id=:id"
                ),
                {"id": WORKSPACE_ID},
            ).one()
            assert migrated == (
                "UNKNOWN",
                "reconciliation_required",
                "SCHEMA_MIGRATION_REQUIRED",
                2,
                "b" * 64,
                "STALE",
                None,
                None,
            )
            terminal = connection.execute(
                text(
                    "SELECT state,reconciliation_state,failure_code,revision,"
                    "executable_fingerprint,executable_evidence_state "
                    "FROM waw_agent_workspace_sessions WHERE id=:id"
                ),
                {"id": TERMINAL_WORKSPACE_ID},
            ).one()
            assert terminal == (
                terminal_state,
                "authoritative",
                None,
                7,
                "d" * 64,
                "STALE",
            )
            active_stop = connection.execute(
                text(
                    "SELECT result,failure_code FROM waw_workspace_stop_operations " "WHERE id=:id"
                ),
                {"id": PENDING_STOP_ID},
            ).one()
            assert active_stop == (
                "RECONCILIATION_REQUIRED",
                "SCHEMA_MIGRATION_REQUIRED",
            )
            terminal_stop = connection.execute(
                text(
                    "SELECT result,failure_code FROM waw_workspace_stop_operations " "WHERE id=:id"
                ),
                {"id": TERMINAL_STOP_ID},
            ).one()
            assert terminal_stop == ("PENDING", None)
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="WAW_0009_DOWNGRADE_UNSAFE"):
        downgrade_database(database_url, "0008_waw_runtime_epoch_fence")


def test_0009_empty_database_can_downgrade_and_upgrade_again(tmp_path: Path) -> None:
    database_url = _url(tmp_path / "empty-waw.db")
    migrate_database(database_url)
    downgrade_database(database_url, "0008_waw_runtime_epoch_fence")
    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        assert "waw_project_bindings" not in inspector.get_table_names()
        assert "revision" not in {column["name"] for column in inspector.get_columns("projects")}
    finally:
        engine.dispose()
    migrate_database(database_url)


def test_0009_binding_history_triggers_are_fail_closed(tmp_path: Path) -> None:
    database_url = _url(tmp_path / "binding-trigger.db")
    migrate_database(database_url)
    engine = create_engine(database_url)
    timestamp = "2026-09-05 00:00:00.000000"
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO projects "
                    "(id,slug,display_name,relative_path,source_type,repository_url,default_branch,"
                    "state,revision,archived_at,created_at,updated_at) VALUES "
                    "(:id,'demo','Demo','demo','empty',NULL,NULL,'ready',1,NULL,:now,:now)"
                ),
                {"id": PROJECT_ID, "now": timestamp},
            )
            connection.execute(
                text(
                    "INSERT INTO waw_runtime_host_installations "
                    "(id,revision,runtime_type,created_at,updated_at,last_runtime_epoch) "
                    "VALUES (:id,1,'agentbox-runtime-linux-v1',:now,:now,NULL)"
                ),
                {"id": HOST_ID, "now": timestamp},
            )
            connection.execute(
                text(
                    "INSERT INTO waw_project_bindings "
                    "(project_id,binding_revision,relative_key,project_revision,binding_digest,"
                    "previous_binding_revision,previous_binding_digest,"
                    "runtime_host_installation_id,runtime_host_installation_revision,status,"
                    "created_at,updated_at) VALUES "
                    "(:project,1,'demo',1,:digest,NULL,NULL,:host,1,'CURRENT',:now,:now)"
                ),
                {
                    "project": PROJECT_ID,
                    "host": HOST_ID,
                    "digest": "a" * 64,
                    "now": timestamp,
                },
            )
        with pytest.raises(IntegrityError, match="immutable"), engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE waw_project_bindings SET relative_key='other' "
                    "WHERE project_id=:project"
                ),
                {"project": PROJECT_ID},
            )
        with pytest.raises(IntegrityError, match="immutable"), engine.begin() as connection:
            connection.execute(
                text("DELETE FROM waw_project_bindings WHERE project_id=:project"),
                {"project": PROJECT_ID},
            )
    finally:
        engine.dispose()
