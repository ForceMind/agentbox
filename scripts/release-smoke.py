#!/usr/bin/env python3
"""Install and exercise an RC using only its public bundle files."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from agentbox_installer.artifact import extract_verified_tar, verify_release_bundle
from agentbox_installer.host import HostOperations
from agentbox_installer.layout import InstallLayout
from agentbox_installer.lifecycle import AgentBoxInstaller


def _run(argv: tuple[str, ...], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"release smoke command failed: {Path(argv[0]).name}")


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _http_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310 - fixed loopback URL
        return json.loads(response.read())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--checksums", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    args = parser.parse_args()
    manifest = verify_release_bundle(args.artifact, args.checksums, args.manifest, args.sbom)
    digest = next(
        line.split()[0]
        for line in args.checksums.read_text(encoding="ascii").splitlines()
        if line.endswith(f"  {args.artifact.name}")
    )

    with tempfile.TemporaryDirectory(prefix="agentbox-rc-smoke-") as temporary:
        root = Path(temporary)
        release = root / "release"
        extract_verified_tar(args.artifact, release)

        venv = root / "venv"
        _run((os.sys.executable, "-m", "venv", str(venv)), cwd=root)
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
                f"agentbox=={manifest.version}",
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
            if metadata.get("version") != manifest.version:
                raise RuntimeError("release API version smoke failed")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)

        fixture_root = root / "fixture-root"
        (fixture_root / "etc").mkdir(parents=True)
        (fixture_root / "etc/os-release").write_text(
            'ID="opencloudos"\nVERSION_ID="9.4"\n', encoding="utf-8"
        )
        layout = InstallLayout(fixture_root)
        installer = AgentBoxInstaller(layout, HostOperations(real_host=False))
        installer.apply(args.artifact, digest)
        secret_before = layout.map("/etc/agentbox/environment").read_bytes()
        project = layout.map("/srv/agentbox/projects/release-smoke-project")
        project.write_text("preserved", encoding="utf-8")
        runtime_auth = layout.map("/home/agentbox-runtime/.codex")
        runtime_auth.mkdir()
        (runtime_auth / "identity").write_text("preserved", encoding="utf-8")
        with sqlite3.connect(layout.database) as connection:
            connection.execute("CREATE TABLE release_admin_canary(value TEXT)")
            connection.execute("INSERT INTO release_admin_canary VALUES ('preserved')")
        assert installer.apply(args.artifact, digest).changed is False
        assert installer.apply(args.artifact, digest).changed is False
        assert layout.map("/etc/agentbox/environment").read_bytes() == secret_before
        result = installer.uninstall()
        assert result["database"] == "preserved"
        assert result["projects"] == "preserved"
        assert result["runtime_home"] == "preserved"
        assert project.read_text(encoding="utf-8") == "preserved"
        assert (runtime_auth / "identity").read_text(encoding="utf-8") == "preserved"
        with sqlite3.connect(layout.database) as connection:
            assert connection.execute("SELECT value FROM release_admin_canary").fetchone() == (
                "preserved",
            )

    print(
        f"Release smoke passed for AgentBox {manifest.version}: offline wheel install, "
        "migration, CLI, static API, triple install, and data-preserving uninstall."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
