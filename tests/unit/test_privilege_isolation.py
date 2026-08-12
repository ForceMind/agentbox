from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
from pathlib import Path

import pytest


def _probe_as(uid: int, gid: int, groups: list[int], paths: dict[str, Path]) -> dict[str, bool]:
    read_fd, write_fd = os.pipe()
    process_id = os.fork()
    if process_id == 0:
        try:
            os.close(read_fd)
            os.setgroups(groups)
            os.setgid(gid)
            os.setuid(uid)
            result: dict[str, bool] = {}
            for name, path in paths.items():
                if name == "runtime_socket":
                    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    try:
                        client.connect(str(path))
                    except OSError:
                        result[name] = False
                    else:
                        result[name] = True
                    finally:
                        client.close()
                    continue
                if name.startswith("read_"):
                    try:
                        path.read_bytes()
                    except OSError:
                        result[name] = False
                    else:
                        result[name] = True
                else:
                    try:
                        with path.open("ab"):
                            pass
                    except OSError:
                        result[name] = False
                    else:
                        result[name] = True
            os.write(write_fd, json.dumps(result).encode())
        finally:
            os._exit(0)
    os.close(write_fd)
    payload = os.read(read_fd, 16 * 1024)
    os.close(read_fd)
    _waited, status = os.waitpid(process_id, 0)
    assert os.waitstatus_to_exitcode(status) == 0
    value = json.loads(payload)
    assert isinstance(value, dict)
    return {str(key): bool(item) for key, item in value.items()}


@pytest.mark.skipif(os.geteuid() != 0, reason="requires temporary UID permission probe")
def test_web_and_runtime_unix_identities_enforce_filesystem_boundary(
    request: pytest.FixtureRequest,
) -> None:
    app_uid, runtime_uid, ipc_gid = 61001, 61002, 61003
    probe_root = Path(tempfile.mkdtemp(prefix="agentbox-privilege-", dir="/tmp"))
    request.addfinalizer(lambda: shutil.rmtree(probe_root))
    probe_root.chmod(0o755)
    app_state = probe_root / "app-state"
    runtime_home = probe_root / "runtime-home"
    projects = probe_root / "projects"
    units = probe_root / "agentbox-api.service"
    for directory, uid in (
        (app_state, app_uid),
        (runtime_home, runtime_uid),
        (projects, runtime_uid),
    ):
        directory.mkdir(mode=0o700)
        os.chown(directory, uid, uid)
    app_secret = app_state / "environment"
    app_secret.write_text("AGENTBOX_SECRET_KEY=fixture-not-a-real-secret\n")
    os.chown(app_secret, app_uid, app_uid)
    app_secret.chmod(0o600)
    runtime_credential = runtime_home / "credential-fixture"
    runtime_credential.write_text("runtime-only")
    os.chown(runtime_credential, runtime_uid, runtime_uid)
    runtime_credential.chmod(0o600)
    project_file = projects / "source.py"
    project_file.write_text("fixture")
    os.chown(project_file, runtime_uid, runtime_uid)
    project_file.chmod(0o600)
    units.write_text("[Service]\n")
    units.chmod(0o644)
    runtime_socket = probe_root / "runtime.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(runtime_socket))
    listener.listen(2)
    os.chown(runtime_socket, runtime_uid, ipc_gid)
    runtime_socket.chmod(0o660)
    try:
        app = _probe_as(
            app_uid,
            app_uid,
            [ipc_gid],
            {
                "read_runtime_credential": runtime_credential,
                "write_project": project_file,
                "write_systemd": units,
                "runtime_socket": runtime_socket,
            },
        )
        runtime = _probe_as(
            runtime_uid,
            runtime_uid,
            [ipc_gid],
            {
                "read_app_secret": app_secret,
                "write_systemd": units,
                "runtime_socket": runtime_socket,
            },
        )
    finally:
        listener.close()

    assert app == {
        "read_runtime_credential": False,
        "write_project": False,
        "write_systemd": False,
        "runtime_socket": True,
    }
    assert runtime == {
        "read_app_secret": False,
        "write_systemd": False,
        "runtime_socket": True,
    }
