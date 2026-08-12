from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from agentbox_installer.host import HostMutationError, HostOperations, IdentityFacts
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


def test_preexisting_service_account_name_without_receipt_is_rejected(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("agentbox_installer.host.os.geteuid", lambda: 0)
    agentbox = SimpleNamespace(
        pw_uid=993,
        pw_gid=994,
        pw_dir="/var/lib/agentbox",
        pw_shell="/usr/sbin/nologin",
    )

    def user(name: str) -> object:
        if name == "agentbox":
            return agentbox
        raise KeyError(name)

    monkeypatch.setattr("agentbox_installer.host.pwd.getpwnam", user)
    monkeypatch.setattr(
        "agentbox_installer.host.grp.getgrnam",
        lambda name: (_ for _ in ()).throw(KeyError(name)),
    )
    host = HostOperations(real_host=True)
    monkeypatch.setattr(host, "_run", lambda _argv: pytest.fail("host was mutated"))

    with pytest.raises(HostMutationError, match="lack an installation receipt"):
        host.ensure_identities()


def test_receipt_bound_service_accounts_require_exact_shape(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("agentbox_installer.host.os.geteuid", lambda: 0)
    users = {
        "agentbox": SimpleNamespace(
            pw_uid=993,
            pw_gid=994,
            pw_dir="/var/lib/agentbox",
            pw_shell="/usr/sbin/nologin",
        ),
        "agentbox-runtime": SimpleNamespace(
            pw_uid=992,
            pw_gid=993,
            pw_dir="/home/agentbox-runtime",
            pw_shell="/usr/sbin/nologin",
        ),
    }
    groups = {
        "agentbox": SimpleNamespace(gr_gid=994, gr_mem=[]),
        "agentbox-runtime": SimpleNamespace(gr_gid=993, gr_mem=[]),
        "agentbox-runtime-ipc": SimpleNamespace(
            gr_gid=992, gr_mem=["agentbox", "agentbox-runtime"]
        ),
    }
    monkeypatch.setattr("agentbox_installer.host.pwd.getpwnam", users.__getitem__)
    monkeypatch.setattr("agentbox_installer.host.grp.getgrnam", groups.__getitem__)
    host = HostOperations(real_host=True)
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(host, "_run", commands.append)
    expected = IdentityFacts(993, 994, 992, 992)

    assert host.ensure_identities(expected) == expected
    assert len(commands) == 2

    users["agentbox-runtime"].pw_dir = "/home/unrelated"
    with pytest.raises(HostMutationError, match="does not match its receipt"):
        host.ensure_identities(expected)
