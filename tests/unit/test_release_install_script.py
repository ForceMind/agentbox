from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def _release_script(tmp_path: Path, *, version: bool = True, wheelhouse: bool = True) -> Path:
    root = Path(__file__).resolve().parents[2]
    release = tmp_path / "release"
    release.mkdir()
    script = release / "install.sh"
    script.write_bytes((root / "installer/release-install.sh").read_bytes())
    script.chmod(0o755)
    if version:
        (release / "VERSION").write_text("0.3.0rc1\n", encoding="ascii")
    if wheelhouse:
        (release / "wheelhouse").mkdir()
    return script


def _run(
    script: Path,
    *,
    env: dict[str, str] | None = None,
    arguments: tuple[str, ...] = ("verify-artifact",),
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (str(script), *arguments),
        cwd=script.parent,
        env={**os.environ, **(env or {})},
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize("version", ("3.11", "3.12", "3.13"))
def test_release_install_accepts_supported_artifact_python_versions(
    tmp_path: Path, version: str
) -> None:
    script = _release_script(tmp_path)
    result = _run(
        script,
        env={
            "AGENTBOX_INSTALLER_TEST_MODE": "1",
            "AGENTBOX_RELEASE_PLATFORM_CHECK_ONLY": "1",
            "AGENTBOX_RELEASE_PLATFORM_TEST_OVERRIDE": f"Linux:x86_64:{version}",
        },
    )

    assert result.returncode == 0


@pytest.mark.parametrize("version", ("3.10", "3.14"))
def test_release_install_rejects_unsupported_artifact_python_before_bootstrap(
    tmp_path: Path, version: str
) -> None:
    script = _release_script(tmp_path)
    result = _run(
        script,
        env={
            "AGENTBOX_INSTALLER_TEST_MODE": "1",
            "AGENTBOX_RELEASE_PLATFORM_CHECK_ONLY": "1",
            "AGENTBOX_RELEASE_PLATFORM_TEST_OVERRIDE": f"Linux:x86_64:{version}",
        },
    )

    assert result.returncode == 18
    assert "requires Python 3.11, 3.12, or 3.13" in result.stderr


@pytest.mark.parametrize(
    ("version", "wheelhouse"),
    ((False, True), (True, False)),
)
def test_release_install_rejects_incomplete_payload(
    tmp_path: Path, version: bool, wheelhouse: bool
) -> None:
    result = _run(_release_script(tmp_path, version=version, wheelhouse=wheelhouse))

    assert result.returncode == 16
    assert "payload is incomplete" in result.stderr


def test_release_install_cleans_bootstrap_directory_after_venv_failure(tmp_path: Path) -> None:
    script = _release_script(tmp_path)
    fake_python = tmp_path / "fake-python"
    fake_python.write_text(
        '#!/bin/sh\nif [ "$1" = "-c" ]; then exit 0; fi\nexit 42\n',
        encoding="ascii",
    )
    fake_python.chmod(0o755)
    temporary = tmp_path / "temporary"
    temporary.mkdir()

    result = _run(
        script,
        env={
            "AGENTBOX_INSTALLER_TEST_MODE": "1",
            "AGENTBOX_RELEASE_BOOTSTRAP_PYTHON": str(fake_python),
            "TMPDIR": str(temporary),
        },
    )

    assert result.returncode == 42
    assert list(temporary.iterdir()) == []


def test_release_install_cleans_bootstrap_directory_after_offline_pip_failure(
    tmp_path: Path,
) -> None:
    script = _release_script(tmp_path)
    fake_python = tmp_path / "fake-python"
    fake_python.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "-c" ]; then exit 0; fi\n'
        'if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then\n'
        '  mkdir -p "$3/bin"\n'
        "  printf '#!/bin/sh\\nexit 41\\n' > \"$3/bin/pip\"\n"
        '  chmod 755 "$3/bin/pip"\n'
        "  exit 0\n"
        "fi\n"
        "exit 42\n",
        encoding="ascii",
    )
    fake_python.chmod(0o755)
    temporary = tmp_path / "temporary"
    temporary.mkdir()

    result = _run(
        script,
        env={
            "AGENTBOX_INSTALLER_TEST_MODE": "1",
            "AGENTBOX_RELEASE_BOOTSTRAP_PYTHON": str(fake_python),
            "TMPDIR": str(temporary),
        },
    )

    assert result.returncode == 41
    assert list(temporary.iterdir()) == []


def test_release_install_rejects_bootstrap_override_outside_test_mode(tmp_path: Path) -> None:
    result = _run(
        _release_script(tmp_path),
        env={"AGENTBOX_RELEASE_BOOTSTRAP_PYTHON": "/bin/false"},
    )

    assert result.returncode == 18
    assert "only in explicit test mode" in result.stderr


def test_release_install_restores_managed_umask_and_forwards_arguments(tmp_path: Path) -> None:
    script = _release_script(tmp_path)
    fake_python = tmp_path / "fake-python"
    fake_python.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "-c" ]; then exit 0; fi\n'
        'if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then\n'
        '  mkdir -p "$3/bin"\n'
        "  cat > \"$3/bin/pip\" <<'PIP'\n"
        "#!/bin/sh\n"
        'target="$(dirname "$0")/agentbox-install"\n'
        "cat > \"$target\" <<'INSTALLER'\n"
        "#!/bin/sh\n"
        'umask > "$AGENTBOX_UMASK_OUTPUT"\n'
        'printf \'%s\\n\' "$@" > "$AGENTBOX_ARGUMENT_OUTPUT"\n'
        "INSTALLER\n"
        'chmod 755 "$target"\n'
        "PIP\n"
        '  chmod 755 "$3/bin/pip"\n'
        "  exit 0\n"
        "fi\n"
        "exit 42\n",
        encoding="ascii",
    )
    fake_python.chmod(0o755)
    umask_output = tmp_path / "umask"
    argument_output = tmp_path / "arguments"

    result = _run(
        script,
        env={
            "AGENTBOX_INSTALLER_TEST_MODE": "1",
            "AGENTBOX_RELEASE_BOOTSTRAP_PYTHON": str(fake_python),
            "AGENTBOX_UMASK_OUTPUT": str(umask_output),
            "AGENTBOX_ARGUMENT_OUTPUT": str(argument_output),
        },
        arguments=("plan", "--artifact", "/tmp/candidate", "--sha256", "abc"),
    )

    assert result.returncode == 0
    assert umask_output.read_text(encoding="ascii").strip() in {"0022", "022"}
    assert argument_output.read_text(encoding="ascii").splitlines() == [
        "plan",
        "--artifact",
        "/tmp/candidate",
        "--sha256",
        "abc",
    ]
