#!/usr/bin/env python3
"""Install and exercise an RC using only its public bundle files."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path, PurePosixPath
from typing import cast


def _run(
    argv: tuple[str, ...],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    capture: bool = False,
) -> str:
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"release smoke command failed: {Path(argv[0]).name}")
    return result.stdout.decode("utf-8", "strict") if capture else ""


def _extract_regular_archive(artifact: Path, destination: Path) -> None:
    destination.mkdir(mode=0o755)
    observed: set[str] = set()
    with tarfile.open(artifact, "r:gz") as archive:
        for member in archive:
            relative = PurePosixPath(member.name)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or member.name in observed
                or not (member.isfile() or member.isdir())
            ):
                raise RuntimeError("release smoke archive is unsafe")
            observed.add(member.name)
            target = destination.joinpath(*relative.parts)
            if member.isdir():
                target.mkdir(mode=0o755, parents=True, exist_ok=True)
                continue
            target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            stream = archive.extractfile(member)
            if stream is None:
                raise RuntimeError("release smoke member is unavailable")
            with stream, target.open("xb") as output:
                while chunk := stream.read(1024 * 1024):
                    output.write(chunk)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _http_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310 - fixed loopback URL
        return cast(dict[str, object], json.loads(response.read()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--checksums", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    args = parser.parse_args()
    manifest_value = json.loads(args.manifest.read_text(encoding="utf-8"))
    version = manifest_value["version"]
    digest = next(
        line.split()[0]
        for line in args.checksums.read_text(encoding="ascii").splitlines()
        if line.endswith(f"  {args.artifact.name}")
    )

    with tempfile.TemporaryDirectory(prefix="agentbox-rc-smoke-") as temporary:
        root = Path(temporary)
        release = root / "release"
        _extract_regular_archive(args.artifact, release)
        install_script = release / "install.sh"
        bootstrap_trace = root / "no-venv-bootstrap.trace"
        bootstrap_python = root / "python-without-venv-ensurepip-or-global-pip"
        bootstrap_python.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' \"$*\" >> {shlex.quote(str(bootstrap_trace))}\n"
            "if [ \"${1:-}\" = '-m' ] && "
            "{ [ \"${2:-}\" = 'venv' ] || [ \"${2:-}\" = 'ensurepip' ]; }; then\n"
            "  exit 97\n"
            "fi\n"
            "if [ \"${1:-}\" = '-m' ] && [ \"${2:-}\" = 'pip' ]; then\n"
            '  case "${PYTHONPATH:-}" in *bootstrap/pip-26.2.1-py3-none-any.whl*) ;; '
            "*) exit 96 ;; esac\n"
            "fi\n"
            f'exec {shlex.quote(sys.executable)} -S "$@"\n',
            encoding="ascii",
        )
        bootstrap_python.chmod(0o700)
        bootstrap_env = {
            **os.environ,
            "AGENTBOX_INSTALLER_TEST_MODE": "1",
            "AGENTBOX_RELEASE_BOOTSTRAP_PYTHON": str(bootstrap_python),
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "PIP_INDEX_URL": "http://127.0.0.1:9/forbidden",
            "PIP_NO_INDEX": "1",
            "PYTHONNOUSERSITE": "1",
        }
        _run(("/usr/bin/bash", "-n", str(install_script)), cwd=release)
        _run(
            (
                str(install_script),
                "verify-artifact",
                "--artifact",
                str(args.artifact.resolve()),
                "--checksums",
                str(args.checksums.resolve()),
                "--manifest",
                str(args.manifest.resolve()),
                "--sbom",
                str(args.sbom.resolve()),
            ),
            cwd=release,
            env=bootstrap_env,
        )
        trace = bootstrap_trace.read_text(encoding="utf-8")
        if "-m venv" in trace or "-m ensurepip" in trace or "-m pip install" not in trace:
            raise RuntimeError("bundled install.sh used a forbidden host bootstrap dependency")
        if "--no-index" not in trace or "--target" not in trace:
            raise RuntimeError("bundled install.sh did not enforce its offline target bootstrap")

        venv = root / "venv"
        _run((sys.executable, "-m", "venv", str(venv)), cwd=root)
        smoke_env = {
            # Deliberately omit host Node/npm/pnpm: the installed control plane
            # and prebuilt static Web must not require them.
            "PATH": str(venv / "bin"),
            "LANG": "C.UTF-8",
            "PYTHONNOUSERSITE": "1",
        }
        _run(
            (
                str(venv / "bin/pip"),
                "install",
                "--no-index",
                "--disable-pip-version-check",
                "--find-links",
                str(release / "wheelhouse"),
                f"agentbox=={version}",
            ),
            cwd=release,
            env=smoke_env,
        )
        _run((str(venv / "bin/agentbox"), "--version"), cwd=release, env=smoke_env)
        for command in ("status", "doctor", "codex", "claude", "project", "github", "system"):
            _run((str(venv / "bin/agentbox"), command, "--help"), cwd=release, env=smoke_env)

        database = root / "smoke.db"
        app_env = {
            **smoke_env,
            "AGENTBOX_ENV": "test",
            "AGENTBOX_DATABASE_URL": f"sqlite+pysqlite:///{database}",
            "AGENTBOX_DATA_DIR": str(root),
            "AGENTBOX_STATIC_DIR": str(release / "web/dist"),
            "AGENTBOX_SECRET_KEY": "release-smoke-secret-value-with-256-bits-minimum",
            "AGENTBOX_ALEMBIC_INI": str(release / "alembic.ini"),
        }
        _run(
            (str(venv / "bin/alembic"), "-c", str(release / "alembic.ini"), "upgrade", "head"),
            cwd=release,
            env=app_env,
        )
        port = _free_port()
        app_env["AGENTBOX_BIND_PORT"] = str(port)
        process = subprocess.Popen(
            (str(venv / "bin/agentbox-api"),),
            cwd=release,
            env=app_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    health = _http_json(f"http://127.0.0.1:{port}/healthz")
                    readiness = _http_json(f"http://127.0.0.1:{port}/readyz")
                    metadata = _http_json(f"http://127.0.0.1:{port}/api/v1/meta")
                    break
                except Exception as exc:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError("release API smoke did not become ready") from exc
                    time.sleep(0.1)
            if health != {"status": "ok"} or readiness.get("status") != "ready":
                raise RuntimeError("release health/readiness smoke failed")
            if metadata.get("version") != version:
                raise RuntimeError("release API version smoke failed")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)

        for identifier, release_version in (("ubuntu", "24.04"), ("debian", "12")):
            platform_root = root / f"fixture-{identifier}"
            (platform_root / "etc").mkdir(parents=True)
            (platform_root / "etc/os-release").write_text(
                f'ID="{identifier}"\nVERSION_ID="{release_version}"\n', encoding="utf-8"
            )
            platform_common = (
                str(install_script),
                "--fixture-root",
                str(platform_root),
            )
            platform_artifact_arguments = (
                "--artifact",
                str(args.artifact.resolve()),
                "--sha256",
                digest,
                "--json",
            )
            platform_plan = json.loads(
                _run(
                    platform_common + ("plan",) + platform_artifact_arguments,
                    cwd=release,
                    env=bootstrap_env,
                    capture=True,
                )
            )
            if "python3-venv" not in platform_plan.get("package_changes", []):
                raise RuntimeError(f"{identifier} no-venv fixture did not detect python3-venv")
            _run(
                platform_common + ("apply",) + platform_artifact_arguments,
                cwd=release,
                env=bootstrap_env,
            )
            if not (platform_root / "var/lib/agentbox/install-receipt.json").is_file():
                raise RuntimeError(f"{identifier} no-venv fixture apply did not complete")

        fixture_root = root / "fixture-root"
        (fixture_root / "etc").mkdir(parents=True)
        (fixture_root / "etc/os-release").write_text(
            'ID="opencloudos"\nVERSION_ID="9.4"\n', encoding="utf-8"
        )
        fixture_env = {
            **bootstrap_env,
        }
        common = (
            str(install_script),
            "--fixture-root",
            str(fixture_root),
        )
        artifact_arguments = (
            "--artifact",
            str(args.artifact.resolve()),
            "--sha256",
            digest,
            "--json",
        )
        plan = json.loads(
            _run(
                common + ("plan",) + artifact_arguments, cwd=release, env=fixture_env, capture=True
            )
        )
        if plan.get("version") != version:
            raise RuntimeError("bundled install.sh did not forward plan arguments")
        _run(common + ("apply",) + artifact_arguments, cwd=release, env=fixture_env)
        environment_path = fixture_root / "etc/agentbox/environment"
        secret_before = environment_path.read_bytes()
        project = fixture_root / "srv/agentbox/projects/release-smoke-project"
        project.write_text("preserved", encoding="utf-8")
        runtime_auth = fixture_root / "home/agentbox-runtime/.codex"
        runtime_auth.mkdir()
        (runtime_auth / "identity").write_text("preserved", encoding="utf-8")
        database = fixture_root / "var/lib/agentbox/agentbox.db"
        with subprocess.Popen(
            (
                str(venv / "bin/python"),
                "-c",
                (
                    "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); "
                    "c.execute('CREATE TABLE release_admin_canary(value TEXT)'); "
                    "c.execute(\"INSERT INTO release_admin_canary VALUES ('preserved')\"); "
                    "c.commit()"
                ),
                str(database),
            ),
            cwd=release,
            env=smoke_env,
        ) as process:
            if process.wait(timeout=30) != 0:
                raise RuntimeError("release data-preservation canary setup failed")
        _run(common + ("apply",) + artifact_arguments, cwd=release, env=fixture_env)
        _run(common + ("apply",) + artifact_arguments, cwd=release, env=fixture_env)
        assert environment_path.read_bytes() == secret_before
        result = json.loads(
            _run(common + ("uninstall", "--json"), cwd=release, env=fixture_env, capture=True)
        )
        assert result["database"] == "preserved"
        assert result["projects"] == "preserved"
        assert result["runtime_home"] == "preserved"
        assert project.read_text(encoding="utf-8") == "preserved"
        assert (runtime_auth / "identity").read_text(encoding="utf-8") == "preserved"
        database_check = _run(
            (
                str(venv / "bin/python"),
                "-c",
                (
                    "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute("
                    "'SELECT value FROM release_admin_canary').fetchone()[0])"
                ),
                str(database),
            ),
            cwd=release,
            env=smoke_env,
            capture=True,
        )
        assert database_check.strip() == "preserved"

    print(
        f"Release smoke passed for AgentBox {version}: bundled install.sh verification and "
        "no-venv Ubuntu 24.04/Debian 12 offline bootstrap, migration, CLI, static API, "
        "triple install, and "
        "data-preserving uninstall."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
