from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from agentbox_installer.host import HostMutationError, HostOperations
from pytest import MonkeyPatch


def test_migration_injects_fixed_production_database_url(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    release = tmp_path / "release"
    executable = release / "venv/bin/alembic"
    executable.parent.mkdir(parents=True)
    executable.write_text("fixture", encoding="utf-8")
    executable.chmod(0o755)
    (release / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
    environment_file = tmp_path / "environment"
    environment_file.write_text(
        (
            "AGENTBOX_ENV=production\n"
            "AGENTBOX_TOML_FILE=/etc/agentbox/agentbox.toml\n"
            "AGENTBOX_SECRET_KEY=fixture-secret-not-output\n"
            "AGENTBOX_STATIC_DIR=/opt/agentbox/current/web/dist\n"
        ),
        encoding="utf-8",
    )
    observed: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        observed.update(kwargs)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("agentbox_installer.host.subprocess.run", fake_run)

    HostOperations(real_host=True).migrate(release, environment_file)

    environment = observed["env"]
    assert isinstance(environment, dict)
    assert environment["AGENTBOX_DATABASE_URL"] == (
        "sqlite+pysqlite:////var/lib/agentbox/agentbox.db"
    )


@pytest.mark.parametrize(
    "injection",
    [
        "LD_PRELOAD=/tmp/inject.so\n",
        "AGENTBOX_DATABASE_URL=sqlite:////etc/shadow\n",
        "AGENTBOX_SECRET_KEY=$(id)\n",
        "AGENTBOX_SECRET_KEY='quoted value'\n",
    ],
)
def test_migration_environment_rejects_unknown_keys_and_shell_syntax(
    tmp_path: Path, injection: str
) -> None:
    release = tmp_path / "release"
    executable = release / "venv/bin/alembic"
    executable.parent.mkdir(parents=True)
    executable.write_text("fixture", encoding="utf-8")
    executable.chmod(0o755)
    environment_file = tmp_path / "environment"
    environment_file.write_text(
        (
            "AGENTBOX_ENV=production\n"
            "AGENTBOX_TOML_FILE=/etc/agentbox/agentbox.toml\n"
            "AGENTBOX_SECRET_KEY=safe-fixture-secret-value\n"
            "AGENTBOX_STATIC_DIR=/opt/agentbox/current/web/dist\n"
            f"{injection}"
        ),
        encoding="utf-8",
    )

    with pytest.raises(HostMutationError, match="environment file"):
        HostOperations(real_host=True).migrate(release, environment_file)
