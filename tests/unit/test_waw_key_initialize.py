from __future__ import annotations

import grp
import json
import os
import platform
import pwd
from pathlib import Path

import pytest
from agentbox_runtime import waw_key_initialize as command
from agentbox_runtime import waw_static_key as keys
from agentbox_runtime.waw_static_key import WAWRuntimeStaticKeyError
from test_waw_static_key import _fixture_tree, _key_path


def _open(root: Path, *, recover: bool = False) -> keys._WAWRuntimeStaticKey:
    return keys._open_fixed_key(
        root=root,
        runtime_uid=os.geteuid(),
        runtime_gid=os.getegid(),
        ancestor_uid=os.geteuid(),
        syscalls=keys._StaticKeySyscalls(),
        initialize=True,
        recover=recover,
    )


def test_initialization_creates_one_private_key_and_returns_only_public_pin(tmp_path: Path) -> None:
    root = _fixture_tree(tmp_path)
    _key_path(root).unlink()
    key = _open(root)
    try:
        with pytest.raises(WAWRuntimeStaticKeyError, match="preflight"):
            key.public_fingerprint()
        key.preflight()
        fingerprint = key.public_fingerprint()
        assert len(fingerprint) == 64 and all(
            character in "0123456789abcdef" for character in fingerprint
        )
        assert _key_path(root).stat().st_mode & 0o777 == 0o600
        assert _key_path(root).stat().st_size == 32
        assert _key_path(root).stat().st_nlink == 1
        assert not _key_path(root).with_name("static-x25519.initial-v1.pending").exists()
        with pytest.raises(WAWRuntimeStaticKeyError, match="not bound"):
            key.private_key()
    finally:
        assert key.close()
    current = _key_path(root).stat()
    reopened = _open(root)
    try:
        reopened.preflight()
        assert reopened.public_fingerprint() == fingerprint
        assert _key_path(root).stat().st_ino == current.st_ino
    finally:
        assert reopened.close()


@pytest.mark.parametrize("partial_size", [0, 7, 31, 32])
def test_unpublished_pending_key_requires_explicit_recovery(
    tmp_path: Path, partial_size: int
) -> None:
    root = _fixture_tree(tmp_path)
    final = _key_path(root)
    final.unlink()
    pending = final.with_name("static-x25519.initial-v1.pending")
    pending.write_bytes(bytes(range(partial_size)))
    pending.chmod(0o600)
    with pytest.raises(WAWRuntimeStaticKeyError):
        _open(root)
    assert not final.exists() and pending.stat().st_size == partial_size
    key = _open(root, recover=True)
    try:
        key.preflight()
        assert len(key.public_fingerprint()) == 64
        assert final.stat().st_size == 32 and final.stat().st_nlink == 1
        assert not pending.exists()
        if partial_size == 32:
            assert final.read_bytes() == bytes(range(32))
    finally:
        key.close()


def test_recovery_completes_only_exact_create_only_hardlink_pair(tmp_path: Path) -> None:
    root = _fixture_tree(tmp_path)
    final = _key_path(root)
    pending = final.with_name("static-x25519.initial-v1.pending")
    os.link(final, pending)
    original = final.read_bytes()
    with pytest.raises(WAWRuntimeStaticKeyError):
        _open(root)
    key = _open(root, recover=True)
    try:
        key.preflight()
        assert final.read_bytes() == original and final.stat().st_nlink == 1
        assert not pending.exists()
    finally:
        key.close()


@pytest.mark.parametrize("kind", ["different", "symlink", "wrong_mode", "extra_link"])
def test_recovery_rejects_unowned_or_ambiguous_pending_key(tmp_path: Path, kind: str) -> None:
    root = _fixture_tree(tmp_path)
    final = _key_path(root)
    pending = final.with_name("static-x25519.initial-v1.pending")
    if kind == "different":
        pending.write_bytes(b"x" * 32)
        pending.chmod(0o600)
    elif kind == "symlink":
        pending.symlink_to(final)
    else:
        os.link(final, pending)
        if kind == "wrong_mode":
            final.chmod(0o644)
        else:
            os.link(final, final.with_name("unrelated"))
    before = final.read_bytes()
    with pytest.raises(WAWRuntimeStaticKeyError):
        _open(root, recover=True)
    assert final.read_bytes() == before


@pytest.mark.parametrize(
    "marker", ["runtime-host-installation.v2.json", "vendor-enrollment.v1.json", "public_anchor"]
)
def test_missing_enrolled_key_never_rotates_silently(tmp_path: Path, marker: str) -> None:
    root = _fixture_tree(tmp_path)
    final = _key_path(root)
    final.unlink()
    if marker == "public_anchor":
        path = root / "usr/share/agentbox/waw/api-host-anchor.v2.json"
        path.parent.mkdir(parents=True)
    else:
        path = final.parent.parent / marker
    path.write_bytes(b"existing enrollment")
    with pytest.raises(WAWRuntimeStaticKeyError, match="operator recovery"):
        _open(root, recover=True)
    assert not final.exists()


def test_local_command_stdout_contains_public_fingerprint_only(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(command, "initialize_runtime_key", lambda **_kwargs: "a" * 64)
    assert command.main([]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert json.loads(output.out) == {
        "schema_version": "agentbox-runtime-key-public.v1",
        "runtime_attestation_x25519_fingerprint": "a" * 64,
    }


def test_local_command_does_not_print_internal_secret_errors(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(**_kwargs: object) -> str:
        raise WAWRuntimeStaticKeyError("private-material-canary")

    monkeypatch.setattr(command, "initialize_runtime_key", fail)
    assert command.main(["--recover"]) == 1
    output = capsys.readouterr()
    assert output.out == "" and "private-material-canary" not in output.err


def test_local_command_has_no_caller_path_or_identity() -> None:
    with pytest.raises(SystemExit):
        command.main(["--path", "/tmp/caller"])


def test_parent_replacement_during_creation_never_publishes_a_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_tree(tmp_path)
    final = _key_path(root)
    final.unlink()
    old = final.parent.with_name("moved-key-root")
    original_write = os.write

    def replace_parent(fd: int, data: bytes) -> int:
        final.parent.rename(old)
        final.parent.mkdir(mode=0o700)
        monkeypatch.setattr(os, "write", original_write)
        return original_write(fd, data)

    monkeypatch.setattr(os, "write", replace_parent)
    with pytest.raises(WAWRuntimeStaticKeyError, match="parent entry changed"):
        _open(root)
    assert not final.exists()
    assert not (old / final.name).exists()


@pytest.mark.parametrize("disabled,recover", [(True, False), (True, True), (False, False)])
def test_fixed_command_selects_creation_only_for_disabled_runtime(
    monkeypatch: pytest.MonkeyPatch, disabled: bool, recover: bool
) -> None:
    from types import SimpleNamespace

    from agentbox_runtime.waw_runtime_profile import WAWRuntimeMode

    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        pwd, "getpwnam", lambda _name: SimpleNamespace(pw_uid=19002, pw_gid=19002)
    )
    monkeypatch.setattr(grp, "getgrnam", lambda _name: SimpleNamespace(gr_gid=19002))
    monkeypatch.setattr(
        command,
        "_require_exact_process_identity",
        lambda uid, gid: None if (uid, gid) == (19002, 19002) else pytest.fail("identity drift"),
    )
    profile = SimpleNamespace(
        mode=WAWRuntimeMode.DISABLED if disabled else WAWRuntimeMode.FILESYSTEM_V2
    )
    monkeypatch.setattr(command, "load_waw_runtime_profile", lambda: profile)
    checked: list[object] = []
    monkeypatch.setattr(command, "revalidate_waw_runtime_profile", checked.append)
    calls: list[dict[str, object]] = []

    class Key:
        closed = False

        def preflight(self) -> None:
            pass

        def public_fingerprint(self) -> str:
            return "a" * 64

        def private_key(self) -> bytes:
            pytest.fail("initializer must not export private bytes")

        def close(self) -> bool:
            self.closed = True
            return True

    key = Key()

    def open_key(**kwargs: object) -> Key:
        calls.append(kwargs)
        return key

    monkeypatch.setattr(command, "_open_fixed_key", open_key)
    assert command.initialize_runtime_key(recover=recover) == "a" * 64
    assert key.closed and checked == [profile, profile]
    assert calls[0]["root"] == Path("/")
    assert calls[0]["initialize"] is disabled and calls[0]["recover"] is recover
    assert calls[0]["runtime_uid"] == 19002 and calls[0]["runtime_gid"] == 19002
