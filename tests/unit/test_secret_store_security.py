from __future__ import annotations

import ast
import inspect
import os
import sqlite3
import sys
from pathlib import Path

import pytest
from agentbox_helper.protocol import HelperAction
from agentbox_installer.backup import create_sqlite_backup
from agentbox_runtime.secret_store import (
    PRODUCTION_SECRET_STORE_ROOT,
    RuntimeSecretStore,
)
from agentbox_runtime.secret_store_cli import main
from agentbox_runtime.secret_store_models import SecretStoreInitializeResult

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_SOURCE = ROOT / "packages/agentbox-runtime/src/agentbox_runtime"
CONTROL_PLANE_ROOTS = (
    ROOT / "apps/api/src",
    ROOT / "apps/cli/src",
    ROOT / "apps/worker/src",
    ROOT / "packages/agentbox-core/src",
    ROOT / "packages/agentbox-protocol/src",
)


def _foundation(tmp_path: Path) -> RuntimeSecretStore:
    home = tmp_path / "runtime-home"
    home.mkdir(mode=0o700)
    os.chmod(home, 0o700)
    return RuntimeSecretStore._for_test(home)


class NoReadStdin:
    def isatty(self) -> bool:
        return True

    def read(self, *_args: object, **_kwargs: object) -> str:
        raise AssertionError("initialize attempted to read stdin")

    def readline(self, *_args: object, **_kwargs: object) -> str:
        raise AssertionError("initialize attempted to read stdin")


class PipedNoReadStdin(NoReadStdin):
    def isatty(self) -> bool:
        return False


def test_initialize_cli_accepts_only_fixed_empty_store_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    store = _foundation(tmp_path)
    monkeypatch.setattr(sys, "stdin", NoReadStdin())

    assert main(["initialize"], _store=store) == 0
    assert capsys.readouterr().out == "INITIALIZED\n"
    assert main(["initialize"], _store=store) == 0
    assert capsys.readouterr().out == "ALREADY_INITIALIZED\n"


def test_initialize_cli_rejects_redirected_stdin_without_reading_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    store = _foundation(tmp_path)
    monkeypatch.setattr(sys, "stdin", PipedNoReadStdin())

    with pytest.raises(SystemExit) as raised:
        main(["initialize"], _store=store)

    assert raised.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "SECRET_STORE_INVALID_ARGUMENTS\n"
    assert store.health().state.value == "UNINITIALIZED"


@pytest.mark.parametrize(
    "argv",
    (
        [],
        ["provision"],
        ["get"],
        ["list"],
        ["reveal"],
        ["initialize", "extra"],
        ["initialize", "--path", "/tmp/store"],
        ["initialize", "--secret", "value"],
        ["initialize", "--file", "value"],
        ["initialize", "--key", "value"],
        ["initialize", "PROVIDER-SECRET-FOUNDATION-CANARY"],
    ),
)
def test_initialize_cli_rejects_every_other_operation_and_option(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(argv, _store=object())  # type: ignore[arg-type]
    assert raised.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "SECRET_STORE_INVALID_ARGUMENTS\n"
    assert all(argument not in captured.err for argument in argv)


def test_production_store_path_is_fixed_and_test_seam_is_private() -> None:
    assert str(PRODUCTION_SECRET_STORE_ROOT) == (
        "/home/agentbox-runtime/.local/share/agentbox/provider-secrets/v1"
    )
    parameters = inspect.signature(RuntimeSecretStore).parameters
    assert set(parameters) == {
        "_runtime_home",
        "_identity_verifier",
        "_entropy",
        "_fault",
    }
    assert all(name.startswith("_") for name in parameters)


def test_control_plane_protocol_and_helper_do_not_import_or_expose_secret_store() -> None:
    for source_root in CONTROL_PLANE_ROOTS:
        source = "\n".join(
            path.read_text(encoding="utf-8") for path in sorted(source_root.rglob("*.py"))
        )
        assert "agentbox_runtime.secret_store" not in source
        assert "provider-secrets" not in source
        assert "secret.store" not in source
    assert {action.value for action in HelperAction} == {
        "systemd.daemon_reload",
        "systemd.start_agentbox",
        "systemd.stop_agentbox",
        "systemd.restart_agentbox",
        "systemd.enable_agentbox",
        "systemd.disable_agentbox",
    }


def test_secret_store_source_has_no_network_runtime_config_or_mutation_bridge() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            RUNTIME_SOURCE / "secret_crypto.py",
            RUNTIME_SOURCE / "secret_store.py",
            RUNTIME_SOURCE / "secret_store_cli.py",
            RUNTIME_SOURCE / "secret_store_models.py",
        )
    )
    tree = ast.parse(source)
    imported = {
        node.names[0].name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import) and node.names
    }
    imported |= {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imported.isdisjoint(
        {
            "httpx",
            "requests",
            "urllib",
            "socket",
            "agentbox_protocol",
            "agentbox_helper",
            "agentbox_core",
        }
    )
    assert "codex" not in source.casefold()
    assert "claude" not in source.casefold()
    assert "provider_credentials" not in source
    assert "RuntimeBinding" not in source


def test_no_secret_store_uds_action_public_api_frontend_or_alembic_migration() -> None:
    application_source = "\n".join(
        path.read_text(encoding="utf-8")
        for source_root in CONTROL_PLANE_ROOTS
        for path in sorted(source_root.rglob("*.py"))
    )
    frontend_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "apps/web/src").rglob("*"))
        if path.is_file()
    )
    assert "agentbox-runtime-provider-secret" not in application_source
    assert "agentbox-runtime-provider-secret" not in frontend_source
    assert "provider-secrets" not in application_source
    assert "provider-secrets" not in frontend_source
    migrations = {path.name for path in (ROOT / "migrations/versions").glob("*.py")}
    assert any(name.startswith("0004_phase11_provider_core") for name in migrations)
    assert any(
        name.startswith("0005_phase11_control_plane_ownership_approval") for name in migrations
    )
    assert not any(name.startswith("0006") for name in migrations)


def test_ordinary_control_plane_backup_never_copies_runtime_secret_store(
    tmp_path: Path,
) -> None:
    store = _foundation(tmp_path)
    assert store.initialize() is SecretStoreInitializeResult.INITIALIZED
    runtime_home = store._runtime_home
    secret_canary = b"fake-plaintext-provider-canary"
    key_canary = b"fake-root-key-canary"
    fake = runtime_home / ".local/share/agentbox/provider-secrets/v1/test-only-canary"
    fake.write_bytes(secret_canary + key_canary)
    os.chmod(fake, 0o600)
    secret_parent = fake.parent.parent
    lock = secret_parent / ".initialize.lock"
    lock.write_bytes(key_canary)
    os.chmod(lock, 0o600)
    staging = secret_parent / ".v1.init-11111111111111111111111111111111"
    staging.mkdir(mode=0o700)
    (staging / "test-only-staging-canary").write_bytes(secret_canary)

    database = tmp_path / "agentbox.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE sample(value TEXT)")
    backups = tmp_path / "backups"
    backups.mkdir(mode=0o700)
    result = create_sqlite_backup(
        database,
        backups,
        application_version="0.3.0rc1",
        migration_revision="0004_phase11_provider_core",
        backup_id="secret-exclusion-fixture",
    )
    backup_bytes = b"".join(path.read_bytes() for path in result.path.rglob("*") if path.is_file())
    manifest = (result.path / "manifest.json").read_text(encoding="utf-8")

    assert secret_canary not in backup_bytes
    assert key_canary not in backup_bytes
    assert "provider-secrets" not in manifest
    assert "test-only-canary" not in manifest


def test_secret_canary_never_enters_control_plane_sqlite_health_or_temp_names(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    canary = b"PROVIDER-SECRET-FOUNDATION-CANARY"
    store = _foundation(tmp_path)
    assert store.initialize() is SecretStoreInitializeResult.INITIALIZED

    control_plane_database = tmp_path / "agentbox.db"
    with sqlite3.connect(control_plane_database) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        connection.execute("CREATE TABLE audit_fixture(result_code TEXT NOT NULL)")
        connection.execute("INSERT INTO audit_fixture VALUES ('FOUNDATION_HEALTHY')")
        connection.commit()
        health_rendering = repr(store.health()).encode("utf-8")
        control_plane_files = tuple(tmp_path.glob("agentbox.db*"))
        assert control_plane_files
        assert all(canary not in path.read_bytes() for path in control_plane_files)

    assert canary not in health_rendering
    assert canary.decode("ascii") not in caplog.text
    assert all(canary.decode("ascii") not in path.name for path in tmp_path.rglob("*"))


def test_real_production_store_was_not_initialized_by_tests() -> None:
    try:
        PRODUCTION_SECRET_STORE_ROOT.lstat()
    except FileNotFoundError:
        return
    except PermissionError:
        pytest.skip("the test identity cannot traverse the production Runtime HOME")
    raise AssertionError("a real production Secret Store exists")
