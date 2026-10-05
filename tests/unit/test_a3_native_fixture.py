"""Unprivileged cleanup regressions; no browser, UDS, key or real account access."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from a3_native_fixture import FixtureDirectory


def directory(tmp_path: Path) -> tuple[Path, FixtureDirectory]:
    root = tmp_path / "a3n-cleanup"
    static = root / "static"
    static.mkdir(parents=True)
    (static / "index.html").write_text("synthetic fixture index")
    (root / "processes" / "api").mkdir(parents=True)
    (root / "processes" / "runtime").mkdir()
    (root / "processes" / "runtime" / "synthetic.txt").write_text("fixture")
    static.chmod(0o555)
    return root, FixtureDirectory(root, static)


def test_supervisor_cleanup_waits_for_exit_then_removes_only_processes(tmp_path: Path) -> None:
    root, owner = directory(tmp_path)
    exited = False

    def close() -> None:
        nonlocal exited
        assert (root / "processes" / "runtime").is_dir()
        exited = True

    process = SimpleNamespace(poll=lambda: 0 if exited else None)
    fixture: Any = SimpleNamespace(close=close, api=SimpleNamespace(process=process), runtime=None)
    owner.close(fixture)
    assert exited and not (root / "processes").exists()
    assert (root / "static" / "index.html").read_text() == "synthetic fixture index"
    assert stat.S_IMODE((root / "static").stat().st_mode) == 0o755
    # A repeated close cannot delete a new directory created after successful cleanup.
    (root / "processes").mkdir()
    owner.close(fixture)
    assert (root / "processes").is_dir()


def test_supervisor_cleanup_is_bound_to_retained_root_not_replaced_path(tmp_path: Path) -> None:
    root, owner = directory(tmp_path)
    retained = root.with_name("retained")
    root.rename(retained)
    (root / "processes").mkdir(parents=True)
    (root / "processes" / "unrelated.txt").write_text("preserve")
    owner.close(None)
    assert not (retained / "processes").exists()
    assert (root / "processes" / "unrelated.txt").read_text() == "preserve"


def test_supervisor_cleanup_does_not_follow_nested_symlink(tmp_path: Path) -> None:
    root, owner = directory(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "unrelated.txt").write_text("preserve")
    (root / "processes" / "link").symlink_to(outside, target_is_directory=True)
    owner.close(None)
    assert (outside / "unrelated.txt").read_text() == "preserve"


def test_supervisor_cleanup_rejects_top_level_processes_symlink(tmp_path: Path) -> None:
    root, owner = directory(tmp_path)
    moved = root / "saved-processes"
    (root / "processes").rename(moved)
    (root / "processes").symlink_to(moved, target_is_directory=True)
    with pytest.raises(ExceptionGroup):
        owner.close(None)
    assert (moved / "runtime" / "synthetic.txt").read_text() == "fixture"
    assert stat.S_IMODE((root / "static").stat().st_mode) == 0o755


def test_setup_failure_before_process_creation_still_restores_static(tmp_path: Path) -> None:
    root, owner = directory(tmp_path)
    # Let the real implementation remove its fixed child once, then exercise the
    # absent-child setup failure through a new resource owner.
    owner.close(None)
    static = root / "static"
    static.chmod(0o555)
    owner = FixtureDirectory(root, static)
    owner.close(None)
    assert stat.S_IMODE(static.stat().st_mode) == 0o755


def test_cleanup_error_still_releases_fds_and_restores_static(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, owner = directory(tmp_path)
    descriptor = owner._root

    def denied(*args: Any, **kwargs: Any) -> None:
        assert args == ("processes",)
        assert kwargs == {"dir_fd": descriptor}
        raise PermissionError("synthetic cleanup denial")

    monkeypatch.setattr("a3_native_fixture.shutil.rmtree", denied)
    with pytest.raises(ExceptionGroup):
        owner.close(None)
    assert stat.S_IMODE((root / "static").stat().st_mode) == 0o755
    with pytest.raises(OSError):
        os.fstat(descriptor)


def test_live_children_refuse_filesystem_cleanup(tmp_path: Path) -> None:
    root, owner = directory(tmp_path)
    fixture: Any = SimpleNamespace(
        close=lambda: None,
        api=SimpleNamespace(process=SimpleNamespace(poll=lambda: None)),
        runtime=None,
    )
    with pytest.raises(RuntimeError, match="still live"):
        owner.close(fixture)
    assert (root / "processes" / "runtime" / "synthetic.txt").is_file()


def test_fixture_directory_rejects_symlink_static(tmp_path: Path) -> None:
    root = tmp_path / "a3n-invalid"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "index.html").write_text("preserve")
    (root / "static").symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        FixtureDirectory(root, root / "static")
    assert (outside / "index.html").read_text() == "preserve"


def test_failed_constructor_retains_live_owner_and_refuses_recursive_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    from a3_native_fixture import A3NativeFixture

    root, owner = directory(tmp_path)
    shutil.rmtree(root / "processes")
    retained: list[A3NativeFixture] = []

    class Child:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.process = SimpleNamespace(poll=lambda: None)

        def call(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("synthetic setup failure")

        def close(self) -> None:
            raise RuntimeError("synthetic child remains live")

    class Port:
        def __enter__(self) -> Port:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def bind(self, *args: Any) -> None:
            pass

        def getsockname(self) -> tuple[str, int]:
            return "127.0.0.1", 12345

    monkeypatch.setattr("a3_native_fixture._Child", Child)
    monkeypatch.setattr("a3_native_fixture.socket.socket", Port)
    with pytest.raises(BaseExceptionGroup):
        A3NativeFixture(
            root / "processes",
            origin="https://127.0.0.1:12345",
            static_root=root / "static",
            retain=retained.append,
        )
    assert len(retained) == 1 and retained[0].api is not None
    deletions: list[object] = []
    monkeypatch.setattr(
        "a3_native_fixture.shutil.rmtree", lambda *args, **kwargs: deletions.append(args)
    )
    with pytest.raises(RuntimeError, match="still live"):
        owner.close(retained[0])
    assert deletions == []
    assert (root / "processes" / "api").exists()


@pytest.mark.parametrize("kind", ["hardlink", "fifo"])
def test_static_index_must_be_unique_regular_file(tmp_path: Path, kind: str) -> None:
    root = tmp_path / "a3n-invalid-index"
    static = root / "static"
    static.mkdir(parents=True)
    original = tmp_path / "original"
    original.write_text("preserve")
    if kind == "hardlink":
        os.link(original, static / "index.html")
    else:
        os.mkfifo(static / "index.html")
    with pytest.raises(ValueError, match="unique regular"):
        FixtureDirectory(root, static)
    assert original.read_text() == "preserve"


def test_each_static_descriptor_restores_its_own_original_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, owner = directory(tmp_path)
    index, static = owner._index, owner._static
    monkeypatch.setattr(owner, "_index_owner", SimpleNamespace(st_uid=123, st_gid=456))
    monkeypatch.setattr(owner, "_owner", SimpleNamespace(st_uid=789, st_gid=987))
    restored: list[tuple[int, int, int]] = []
    monkeypatch.setattr("a3_native_fixture.os.geteuid", lambda: 0)
    monkeypatch.setattr(
        "a3_native_fixture.os.fchown", lambda fd, uid, gid: restored.append((fd, uid, gid))
    )
    owner.close(None)
    assert restored == [(index, 123, 456), (static, 789, 987)]
    assert not (root / "processes").exists()


@pytest.mark.parametrize(
    "code", ["patch plaintext canary", "A" * 8192, {"patch": "canary"}, b"canary"]
)
def test_child_error_diagnostics_never_reflect_unexpected_values(code: object) -> None:
    from a3_native_fixture import FixtureChildError

    error = FixtureChildError("runtime", "control", code)
    assert error.code == "ChildError"
    assert str(error) == "runtime:control:ChildError"


def test_grouped_setup_failure_keeps_primary_child_diagnostic_without_values() -> None:
    from a3_native_fixture import FixtureChildError, fixture_error_diagnostic

    primary = FixtureChildError("api", "control", "ImportError")
    error = ExceptionGroup(
        "sensitive group value",
        [
            ExceptionGroup("another sensitive value", [primary]),
            RuntimeError("sensitive cleanup value"),
        ],
    )
    assert fixture_error_diagnostic(error) == {
        "code": "ExceptionGroup",
        "primary_code": "FixtureChildError",
        "role": "api",
        "phase": "control",
        "child_code": "ImportError",
        "cleanup_failed": True,
    }


@pytest.mark.parametrize("cause", ["live-child", "rmtree"])
def test_failed_cleanup_can_never_be_acknowledged_on_second_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cause: str
) -> None:
    root, owner = directory(tmp_path)
    fixture: Any = None
    if cause == "live-child":
        fixture = SimpleNamespace(
            close=lambda: None,
            api=SimpleNamespace(process=SimpleNamespace(poll=lambda: None)),
            runtime=None,
        )
    else:

        def denied(*args: Any, **kwargs: Any) -> None:
            raise PermissionError("synthetic filesystem denial")

        monkeypatch.setattr("a3_native_fixture.shutil.rmtree", denied)
    with pytest.raises((RuntimeError, ExceptionGroup)) as first:
        owner.close(fixture)
    with pytest.raises((RuntimeError, ExceptionGroup)) as repeated:
        owner.close(fixture)
    assert repeated.value is first.value
    assert (root / "processes" / "runtime" / "synthetic.txt").is_file()


def test_fixture_revoke_uses_real_utc6_transaction_time(initialized_services: Any) -> None:
    from a3_native_fixture import _revoke_fixture_sessions
    from agentbox_core.errors import InvalidSession
    from agentbox_core.models import ControlPlaneSession

    services = initialized_services
    issued = services.auth.login(
        username="maintainer",
        password="a sufficiently long passphrase",
        source_identifier="fixture",
        request_id=None,
    )
    authenticated = services.sessions.authenticate(issued.token)
    _revoke_fixture_sessions(services)
    with pytest.raises(InvalidSession):
        services.sessions.authenticate(issued.token)
    with services.database.transaction() as session:
        row = session.get(ControlPlaneSession, authenticated.session_id)
        assert row and row.revoked_at is not None and row.revoked_at.tzinfo is not None


def test_self_contained_bootstrap_reports_source_failure_without_raw_path(tmp_path: Path) -> None:
    import json
    import subprocess
    import sys

    from a3_native_fixture import _CHILD_BOOTSTRAP

    missing = tmp_path / "do-not-reflect-source-canary.py"
    result = subprocess.run(
        [sys.executable, "-c", _CHILD_BOOTSTRAP, str(missing), "runtime"],
        capture_output=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout) == {"error": "FileNotFoundError", "phase": "source-access"}
    assert b"canary" not in result.stdout


def test_self_contained_bootstrap_preserves_existing_child_protocol(tmp_path: Path) -> None:
    import json
    import subprocess
    import sys

    from a3_native_fixture import _CHILD_BOOTSTRAP

    source = tmp_path / "source.py"
    source.write_text('import json, sys\nprint(json.dumps({"role": sys.argv[1]}))\n')
    result = subprocess.run(
        [sys.executable, "-c", _CHILD_BOOTSTRAP, str(source), "api"],
        capture_output=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"role": "api"}


def test_bootstrap_eof_diagnostic_keeps_bounded_exit_code() -> None:
    from a3_native_fixture import FixtureChildError, fixture_error_diagnostic

    assert fixture_error_diagnostic(
        FixtureChildError("runtime", "bootstrap-eof", "ChildExited", -15)
    ) == {
        "code": "FixtureChildError",
        "role": "runtime",
        "phase": "bootstrap-eof",
        "child_code": "ChildExited",
        "exit_code": -15,
    }
    assert "exit_code" not in fixture_error_diagnostic(
        FixtureChildError("api", "bootstrap-eof", "ChildExited", "do not echo")
    )


def _isolated_import_environment() -> dict[str, str]:
    from a3_native_fixture import REPOSITORY, _fixture_environment
    from a3_native_sources import PACKAGE_DIRS

    environment = _fixture_environment()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(REPOSITORY / Path(path).parent) for path in PACKAGE_DIRS] + [str(REPOSITORY / "tests")]
    )
    return environment


def test_unconfigured_main_import_reproduces_private_child_read_only_failure(
    tmp_path: Path,
) -> None:
    import json
    import subprocess
    import sys

    if os.geteuid() == 0:
        pytest.skip("read-only directory reproduction requires an unprivileged caller")
    checkout = tmp_path / "readonly-checkout"
    checkout.mkdir(mode=0o555)
    script = """
import json, traceback
try:
    import agentbox_api.main
except PermissionError as error:
    frames = traceback.extract_tb(error.__traceback__)
    prepared = any(frame.name == "_prepare_parent_directory" for frame in frames)
    print(json.dumps({"denied": True, "database_prepare": prepared}))
else:
    raise AssertionError("unconfigured import unexpectedly wrote to a read-only cwd")
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=checkout,
            env=_isolated_import_environment(),
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        assert json.loads(result.stdout) == {"denied": True, "database_prepare": True}
        assert not (checkout / ".agentbox-dev").exists()
    finally:
        checkout.chmod(0o755)


def test_api_import_configuration_precedes_default_app_and_excludes_outer_harness(
    tmp_path: Path,
) -> None:
    import json
    import subprocess
    import sys

    checkout = tmp_path / "readonly-checkout"
    checkout.mkdir()
    development = checkout / ".agentbox-dev"
    development.mkdir()
    (development / "config.toml").write_text("not valid TOML; this must never be read")
    before = (development / "config.toml").read_bytes()
    checkout.chmod(0o555)
    private = tmp_path / "api-owned"
    private.mkdir(mode=0o700)
    outer = tmp_path / "outer-harness"
    outer.mkdir()
    poison = outer / "config.toml"
    poison.write_text("not valid outer TOML; this must never be read")
    environment = _isolated_import_environment()
    environment.update(
        {
            "AGENTBOX_ENV": "production",
            "AGENTBOX_DATA_DIR": str(outer),
            "AGENTBOX_DATABASE_URL": f"sqlite+pysqlite:///{outer}/wrong.db",
            "AGENTBOX_PROJECT_ROOT": str(outer / "wrong-projects"),
            "AGENTBOX_TOML_FILE": str(poison),
            "AGENTBOX_SECRET_KEY": "outer-harness-secret-must-not-be-adopted",
            "AGENTBOX_STATIC_DIR": str(outer / "wrong-static"),
            "aGeNtBoX_StAtIc_DiR": str(outer / "mixed-case-static"),
            "AGENTBOX_E2E_USERNAME": "outer-harness-identity",
        }
    )
    script = """
import json, os, sys
from pathlib import Path
from a3_native_fixture import _configure_api_import_environment, SYNTHETIC_SECRET
root = Path(sys.argv[1])
_configure_api_import_environment({
    "root": str(root), "origin": "https://127.0.0.1:44321",
    "api_origin": "http://127.0.0.1:43210",
})
import agentbox_api.main as main
settings = main._installed_settings
assert settings.env.value == "test"
assert settings.data_dir == root and settings.project_root == root / "empty-projects"
assert settings.database_url == f"sqlite+pysqlite:///{root}/fixture.db"
assert settings.runtime_socket == root / "unavailable-runtime.sock"
assert settings.secret_key.get_secret_value() == SYNTHETIC_SECRET
assert settings.static_dir is None and "AGENTBOX_E2E_USERNAME" not in os.environ
assert "aGeNtBoX_StAtIc_DiR" not in os.environ
assert os.environ["AGENTBOX_TOML_FILE"] == str(root / "fixture-import.toml")
assert settings.allowed_origins == ("https://127.0.0.1:44321", "http://127.0.0.1:43210")
main.app.state.services.database.close()
print(json.dumps({"imported": True, "private_test_config": True}))
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", script, str(private)],
            cwd=checkout,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        assert json.loads(result.stdout) == {"imported": True, "private_test_config": True}
        assert sorted(path.name for path in outer.iterdir()) == ["config.toml"]
        assert sorted(path.name for path in development.iterdir()) == ["config.toml"]
        assert (development / "config.toml").read_bytes() == before
        assert (private / "fixture-import.toml").read_bytes() == b""
    finally:
        checkout.chmod(0o755)
