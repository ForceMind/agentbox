from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

PRODUCTION_PIP_SHA256 = "9655943313a94722b7774661c21049070f6bbb0a1516bf02f7c8d5d9201514cd"
FIXTURE_PIP = b"fixture bootstrap pip wheel"
FIXTURE_PIP_SHA256 = hashlib.sha256(FIXTURE_PIP).hexdigest()


def _release_script(
    tmp_path: Path,
    *,
    version: bool = True,
    wheelhouse: bool = True,
    bootstrap: bool = True,
) -> Path:
    root = Path(__file__).resolve().parents[2]
    release = tmp_path / "release"
    release.mkdir()
    script = release / "install.sh"
    payload = (root / "installer/release-install.sh").read_text(encoding="utf-8")
    payload = payload.replace(PRODUCTION_PIP_SHA256, FIXTURE_PIP_SHA256)
    script.write_text(payload, encoding="utf-8")
    script.chmod(0o755)
    if version:
        (release / "VERSION").write_text("0.3.0rc1\n", encoding="ascii")
    if wheelhouse:
        (release / "wheelhouse").mkdir()
    if bootstrap:
        bootstrap_dir = release / "bootstrap"
        bootstrap_dir.mkdir()
        (bootstrap_dir / "pip-25.3-py3-none-any.whl").write_bytes(FIXTURE_PIP)
    return script


def _fake_python(tmp_path: Path) -> Path:
    executable = tmp_path / "python-without-venv-pip-or-ensurepip"
    executable.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" >> "${AGENTBOX_BOOTSTRAP_TRACE:-/dev/null}"\n'
        'if [ "$1" = "-m" ] && { [ "$2" = "venv" ] || [ "$2" = "ensurepip" ]; }; then\n'
        "  exit 97\n"
        "fi\n"
        'if [ "$1" = "-c" ]; then exit 0; fi\n'
        'if [ "$1" = "-" ]; then exec "${AGENTBOX_REAL_TEST_PYTHON}" "$@"; fi\n'
        'if [ "$1" = "-m" ] && [ "$2" = "pip" ]; then\n'
        '  case "${PYTHONPATH:-}" in *pip-25.3-py3-none-any.whl*) ;; *) exit 96 ;; esac\n'
        '  exit "${AGENTBOX_FAKE_PIP_RESULT:-0}"\n'
        "fi\n"
        'if [ "$1" = "-m" ] && [ "$2" = "agentbox_installer.cli" ]; then\n'
        "  shift 2\n"
        '  if [ -n "${AGENTBOX_UMASK_OUTPUT:-}" ]; then umask > "$AGENTBOX_UMASK_OUTPUT"; fi\n'
        '  if [ -n "${AGENTBOX_ARGUMENT_OUTPUT:-}" ]; then\n'
        '    printf \'%s\\n\' "$@" > "$AGENTBOX_ARGUMENT_OUTPUT"\n'
        "  fi\n"
        '  exit "${AGENTBOX_FAKE_CLI_RESULT:-0}"\n'
        "fi\n"
        "exit 95\n",
        encoding="ascii",
    )
    executable.chmod(0o755)
    return executable


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


def _fake_environment(tmp_path: Path, fake_python: Path) -> dict[str, str]:
    return {
        "AGENTBOX_INSTALLER_TEST_MODE": "1",
        "AGENTBOX_RELEASE_BOOTSTRAP_PYTHON": str(fake_python),
        "AGENTBOX_REAL_TEST_PYTHON": sys.executable,
        "AGENTBOX_BOOTSTRAP_TRACE": str(tmp_path / "trace"),
    }


@pytest.mark.parametrize("version", ("3.11", "3.12", "3.13"))
def test_release_install_accepts_supported_artifact_python_versions(
    tmp_path: Path, version: str
) -> None:
    result = _run(
        _release_script(tmp_path),
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
    result = _run(
        _release_script(tmp_path),
        env={
            "AGENTBOX_INSTALLER_TEST_MODE": "1",
            "AGENTBOX_RELEASE_PLATFORM_CHECK_ONLY": "1",
            "AGENTBOX_RELEASE_PLATFORM_TEST_OVERRIDE": f"Linux:x86_64:{version}",
        },
    )

    assert result.returncode == 18
    assert "requires Python 3.11, 3.12, or 3.13" in result.stderr


def test_release_install_rejects_unsupported_architecture(tmp_path: Path) -> None:
    result = _run(
        _release_script(tmp_path),
        env={
            "AGENTBOX_INSTALLER_TEST_MODE": "1",
            "AGENTBOX_RELEASE_PLATFORM_CHECK_ONLY": "1",
            "AGENTBOX_RELEASE_PLATFORM_TEST_OVERRIDE": "Linux:aarch64:3.12",
        },
    )

    assert result.returncode == 18
    assert "supports x86_64 only" in result.stderr


@pytest.mark.parametrize(
    ("version", "wheelhouse", "bootstrap"),
    ((False, True, True), (True, False, True), (True, True, False)),
)
def test_release_install_rejects_incomplete_payload(
    tmp_path: Path, version: bool, wheelhouse: bool, bootstrap: bool
) -> None:
    result = _run(
        _release_script(
            tmp_path,
            version=version,
            wheelhouse=wheelhouse,
            bootstrap=bootstrap,
        )
    )

    assert result.returncode == 16
    assert "payload is incomplete" in result.stderr


def test_release_install_rejects_malformed_version(tmp_path: Path) -> None:
    script = _release_script(tmp_path)
    (script.parent / "VERSION").write_text("0.3-rc-one\n", encoding="ascii")

    result = _run(script)

    assert result.returncode == 16
    assert "VERSION is invalid" in result.stderr


def test_release_install_rejects_bootstrap_wheel_digest_mismatch(tmp_path: Path) -> None:
    script = _release_script(tmp_path)
    (script.parent / "bootstrap/pip-25.3-py3-none-any.whl").write_bytes(b"tampered")

    result = _run(script)

    assert result.returncode == 16
    assert "checksum mismatch" in result.stderr


def test_release_install_bootstrap_never_invokes_venv_ensurepip_or_global_pip(
    tmp_path: Path,
) -> None:
    script = _release_script(tmp_path)
    fake_python = _fake_python(tmp_path)
    environment = _fake_environment(tmp_path, fake_python)

    result = _run(script, env=environment)

    assert result.returncode == 0
    trace = (tmp_path / "trace").read_text(encoding="utf-8")
    assert "-m venv" not in trace
    assert "-m ensurepip" not in trace
    assert "-m pip install" in trace
    assert "--no-index" in trace
    assert "--target" in trace


def test_release_install_cleans_bootstrap_directory_after_offline_pip_failure(
    tmp_path: Path,
) -> None:
    script = _release_script(tmp_path)
    fake_python = _fake_python(tmp_path)
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    environment = {
        **_fake_environment(tmp_path, fake_python),
        "AGENTBOX_FAKE_PIP_RESULT": "41",
        "TMPDIR": str(temporary),
    }

    result = _run(script, env=environment)

    assert result.returncode == 41
    assert list(temporary.iterdir()) == []


def test_release_install_cleans_bootstrap_directory_after_installer_failure(
    tmp_path: Path,
) -> None:
    script = _release_script(tmp_path)
    fake_python = _fake_python(tmp_path)
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    environment = {
        **_fake_environment(tmp_path, fake_python),
        "AGENTBOX_FAKE_CLI_RESULT": "42",
        "TMPDIR": str(temporary),
    }

    result = _run(script, env=environment)

    assert result.returncode == 42
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
    fake_python = _fake_python(tmp_path)
    umask_output = tmp_path / "umask"
    argument_output = tmp_path / "arguments"
    environment = {
        **_fake_environment(tmp_path, fake_python),
        "AGENTBOX_UMASK_OUTPUT": str(umask_output),
        "AGENTBOX_ARGUMENT_OUTPUT": str(argument_output),
    }

    result = _run(
        script,
        env=environment,
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
