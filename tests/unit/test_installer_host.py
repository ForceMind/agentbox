from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agentbox_installer.host import HostOperations
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
        "AGENTBOX_ENV=production\nAGENTBOX_SECRET_KEY=fixture-secret-not-output\n",
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
