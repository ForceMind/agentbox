from __future__ import annotations

import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from agentbox_installer.host import HostMutationError, HostOperations, WAWVendorObservation
from agentbox_runtime.waw_vendor_probe import waw_vendor_probe_output_digest


def _host(monkeypatch: pytest.MonkeyPatch) -> HostOperations:
    host = HostOperations(real_host=True)
    monkeypatch.setattr(host, "require_root", lambda: None)
    monkeypatch.setattr(
        "agentbox_installer.host.pwd.getpwnam",
        lambda name: (
            SimpleNamespace(pw_uid=19002, pw_gid=19002)
            if name == "agentbox-runtime"
            else pytest.fail("unexpected identity")
        ),
    )
    original_lstat = Path.lstat

    def lstat(path: Path) -> object:
        if str(path) in {"/usr/local/bin/claude", "/usr/local/bin/codex"}:
            return SimpleNamespace(
                st_mode=stat.S_IFREG | 0o755,
                st_uid=0,
                st_gid=0,
                st_nlink=1,
            )
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", lstat)
    monkeypatch.setattr("agentbox_installer.host.os.chown", lambda *_args: None)
    return host


def test_runtime_vendor_observation_uses_framed_codex_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _host(monkeypatch)
    codex_stdout = b""
    codex_stderr = b"Not logged in\n"

    def run(
        kind: str,
        executable: Path,
        arguments: tuple[str, ...],
        _home: Path,
        _scratch: Path,
    ) -> tuple[int, bytes, bytes]:
        if kind == "claude":
            assert str(executable) == "/usr/local/bin/claude"
            assert arguments == ("--version",)
            return 0, b"2.1.286 (Claude Code)\n", b"bounded version diagnostic\n"
        if arguments == ("--version",):
            return 0, b"codex-cli 0.159.3\n", b""
        assert arguments == ("login", "status")
        return 1, codex_stdout, codex_stderr

    monkeypatch.setattr(host, "_run_waw_vendor_observation", run)

    observed = host.observe_waw_vendors()

    assert observed == WAWVendorObservation(
        claude_vendor_version="2.1.286 (Claude Code)",
        codex_vendor_version="codex-cli 0.159.3",
        codex_unauthenticated_output_sha256=waw_vendor_probe_output_digest(
            codex_stdout, codex_stderr
        ),
    )


def test_runtime_vendor_observation_rejects_non_unauthenticated_codex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _host(monkeypatch)

    def run(
        kind: str,
        executable: Path,
        arguments: tuple[str, ...],
        _home: Path,
        _scratch: Path,
    ) -> tuple[int, bytes, bytes]:
        if kind == "claude":
            assert str(executable) == "/usr/local/bin/claude"
            return 0, b"2.1.286 (Claude Code)\n", b""
        if arguments == ("--version",):
            return 0, b"codex-cli 0.159.3\n", b""
        return 0, b"Logged in\n", b""

    monkeypatch.setattr(host, "_run_waw_vendor_observation", run)

    with pytest.raises(HostMutationError, match="unauthenticated"):
        host.observe_waw_vendors()
