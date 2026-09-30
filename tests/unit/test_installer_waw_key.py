from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from agentbox_installer.host import HostMutationError, HostOperations

RELEASE = Path("/opt/agentbox/releases/0.3.0rc30")
PUBLIC = {
    "schema_version": "agentbox-runtime-key-public.v1",
    "runtime_attestation_x25519_fingerprint": "a" * 64,
}


class _Process:
    def __init__(self, stdout: bytes, returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode

    def __enter__(self) -> _Process:
        return self

    def __exit__(self, *_args: Any) -> None:
        pass

    def communicate(self, *, timeout: int) -> tuple[bytes, None]:
        assert timeout == 30
        return self.stdout, None


@pytest.mark.parametrize("recover", [False, True])
def test_installer_invokes_only_fixed_runtime_key_owner(
    monkeypatch: pytest.MonkeyPatch, recover: bool
) -> None:
    calls: list[tuple[Any, Any]] = []

    def popen(argv: Any, **kwargs: Any) -> _Process:
        calls.append((argv, kwargs))
        return _Process(json.dumps(PUBLIC).encode())

    monkeypatch.setattr(subprocess, "Popen", popen)
    assert (
        HostOperations(real_host=True).initialize_waw_runtime_key(RELEASE, recover=recover)
        == "a" * 64
    )
    argv, options = calls[0]
    assert argv == (
        "/usr/sbin/runuser",
        "-u",
        "agentbox-runtime",
        "--",
        str(RELEASE / "venv/bin/python"),
        "-I",
        "-m",
        "agentbox_runtime.waw_key_initialize",
        *(("--recover",) if recover else ()),
    )
    assert options["cwd"] == RELEASE and options["start_new_session"] is True
    assert options["stderr"] == subprocess.DEVNULL
    assert set(options["env"]) == {"PATH", "LANG", "HOME"}


@pytest.mark.parametrize(
    "raw",
    [
        b"private-material-canary",
        b"x" * 513,
        json.dumps({**PUBLIC, "secret": "private-material-canary"}).encode(),
        json.dumps({**PUBLIC, "schema_version": "caller"}).encode(),
        json.dumps({**PUBLIC, "runtime_attestation_x25519_fingerprint": "0" * 64}).encode(),
        json.dumps({**PUBLIC, "runtime_attestation_x25519_fingerprint": "A" * 64}).encode(),
        b'{"schema_version":"caller","schema_version":"agentbox-runtime-key-public.v1","runtime_attestation_x25519_fingerprint":"'
        + b"a" * 64
        + b'"}',
    ],
)
def test_installer_rejects_unclosed_or_untrusted_public_output(
    monkeypatch: pytest.MonkeyPatch, raw: bytes
) -> None:
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: _Process(raw))
    with pytest.raises(HostMutationError) as error:
        HostOperations(real_host=True).initialize_waw_runtime_key(RELEASE)
    assert "private-material-canary" not in str(error.value)
    assert error.value.__cause__ is None


@pytest.mark.parametrize(
    "release", [Path("/tmp/caller"), Path("/opt/agentbox/releases/caller"), Path("relative")]
)
def test_installer_has_no_arbitrary_key_program_location(release: Path) -> None:
    with pytest.raises(HostMutationError):
        HostOperations(real_host=True).initialize_waw_runtime_key(release)


def test_fixture_host_never_invents_a_production_fingerprint() -> None:
    with pytest.raises(HostMutationError):
        HostOperations(real_host=False).initialize_waw_runtime_key(RELEASE)
