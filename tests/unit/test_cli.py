from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from agentbox_cli.main import main
from agentbox_core import __version__
from conftest import migrate_database


@pytest.fixture
def cli_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> str:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'cli.db'}"
    monkeypatch.setenv("AGENTBOX_ENV", "test")
    monkeypatch.setenv("AGENTBOX_DATABASE_URL", database_url)
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_SECRET_KEY", "cli-test-secret-that-is-at-least-thirty-two-bytes")
    migrate_database(database_url)
    return database_url


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == __version__


def test_cli_status_json_reports_control_plane_only(
    cli_environment: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del cli_environment
    assert main(["status", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "status"
    assert payload["execution_mode"] == "local_read_only"
    assert payload["data"] == {
        "admin": "not_initialized",
        "configuration": "valid",
        "database": "reachable",
        "environment": "test",
        "migrations": "current",
    }


def test_admin_init_requires_tty(
    cli_environment: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del cli_environment
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    assert main(["admin", "init", "--username", "maintainer"]) == 13
    assert "ADMIN_INIT_TTY_REQUIRED" in capsys.readouterr().err


def test_admin_init_prompts_without_password_argv_and_refuses_second_admin(
    cli_environment: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del cli_environment
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    prompts: list[str] = []

    def fake_getpass(prompt: str) -> str:
        prompts.append(prompt)
        return "a sufficiently long passphrase"

    monkeypatch.setattr("agentbox_cli.main.getpass.getpass", fake_getpass)

    assert main(["admin", "init", "--username", "maintainer"]) == 0
    assert len(prompts) == 2
    assert "initialized" in capsys.readouterr().out

    assert main(["admin", "init", "--username", "other"]) == 14
    assert "ADMIN_ALREADY_INITIALIZED" in capsys.readouterr().err


def test_secret_generate_outputs_random_value_without_file_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["secret", "generate"]) == 0

    generated = capsys.readouterr().out.strip()
    assert len(generated) >= 64
    assert list(tmp_path.iterdir()) == []
