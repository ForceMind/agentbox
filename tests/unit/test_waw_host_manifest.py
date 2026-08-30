from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from agentbox_runtime.waw_host_manifest import (
    WAWRuntimeHostManifestError,
    decode_canonical_waw_runtime_host_manifest,
    load_waw_runtime_host_manifest,
)
from agentbox_runtime.waw_manifest_codecs import RuntimeHostManifest, encode_runtime_host_manifest


def _write_manifest(root: Path, value: dict[str, object]) -> Path:
    parent = root / "var" / "lib" / "agentbox-waw"
    parent.mkdir(parents=True)
    os.chmod(parent, 0o750)
    path = parent / "runtime-host-installation.json"
    path.write_bytes(
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    )
    os.chmod(path, 0o440)
    return path


def _valid() -> dict[str, object]:
    return {
        "enrollment_epoch": "1",
        "enrollment_state": "steady",
        "host_manifest_digest": "a" * 64,
        "project_root_manifest_digest": "b" * 64,
        "runtime_host_installation_id": "wri_" + "c" * 32,
        "runtime_host_installation_revision": "1",
        "schema_version": "waw-runtime-host-installation-v1",
    }


def test_reads_canonical_installer_manifest(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _valid())
    value = load_waw_runtime_host_manifest(
        path, expected_uid=os.geteuid(), expected_gid=os.getegid()
    )
    assert value.runtime_host_installation_id == "wri_" + "c" * 32
    assert value.enrollment_state == "steady"


@pytest.mark.parametrize("field", ["runtime_host_installation_revision", "enrollment_epoch"])
def test_accepts_maximum_uint64_decimal_values(tmp_path: Path, field: str) -> None:
    data = _valid()
    data[field] = str(2**64 - 1)
    path = _write_manifest(tmp_path, data)
    value = load_waw_runtime_host_manifest(
        path, expected_uid=os.geteuid(), expected_gid=os.getegid()
    )
    assert getattr(value, field) == str(2**64 - 1)


@pytest.mark.parametrize("field", ["runtime_host_installation_revision", "enrollment_epoch"])
def test_rejects_uint64_overflow_decimal_values(tmp_path: Path, field: str) -> None:
    data = _valid()
    data[field] = str(2**64)
    path = _write_manifest(tmp_path, data)
    with pytest.raises(WAWRuntimeHostManifestError):
        load_waw_runtime_host_manifest(path, expected_uid=os.geteuid(), expected_gid=os.getegid())


@pytest.mark.parametrize(
    "field,value",
    [
        ("runtime_host_installation_id", "wri_" + "0" * 32),
        ("runtime_host_installation_revision", "01"),
        ("host_manifest_digest", "A" * 64),
        ("enrollment_epoch", "0"),
        ("enrollment_state", "unknown"),
        ("schema_version", "other"),
    ],
)
def test_rejects_invalid_manifest_values(tmp_path: Path, field: str, value: object) -> None:
    data = _valid()
    data[field] = value
    path = _write_manifest(tmp_path, data)
    with pytest.raises(WAWRuntimeHostManifestError):
        load_waw_runtime_host_manifest(path, expected_uid=os.geteuid(), expected_gid=os.getegid())


def test_rejects_extra_key_and_noncanonical_bytes(tmp_path: Path) -> None:
    data = _valid()
    data["extra"] = "forbidden"
    path = _write_manifest(tmp_path, data)
    with pytest.raises(WAWRuntimeHostManifestError):
        load_waw_runtime_host_manifest(path, expected_uid=os.geteuid(), expected_gid=os.getegid())
    path = _write_manifest(tmp_path / "second", _valid())
    payload = path.read_bytes() + b"\n"
    os.chmod(path, 0o600)
    path.write_bytes(payload)
    os.chmod(path, 0o440)
    with pytest.raises(WAWRuntimeHostManifestError):
        load_waw_runtime_host_manifest(path, expected_uid=os.geteuid(), expected_gid=os.getegid())


def test_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _valid())
    payload = path.read_bytes().replace(
        b'"schema_version":"waw-runtime-host-installation-v1"',
        b'"schema_version":"waw-runtime-host-installation-v1",'
        b'"schema_version":"waw-runtime-host-installation-v1"',
    )
    path.chmod(0o600)
    path.write_bytes(payload)
    path.chmod(0o440)
    with pytest.raises(WAWRuntimeHostManifestError):
        load_waw_runtime_host_manifest(path, expected_uid=os.geteuid(), expected_gid=os.getegid())


def test_rejects_symlink_manifest(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _valid())
    target = path.with_name("target.json")
    target.write_bytes(path.read_bytes())
    os.chmod(target, 0o440)
    path.unlink()
    path.symlink_to(target)
    with pytest.raises(WAWRuntimeHostManifestError):
        load_waw_runtime_host_manifest(path, expected_uid=os.geteuid(), expected_gid=os.getegid())


def test_rejects_wrong_parent_or_file_mode(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _valid())
    os.chmod(path.parent, stat.S_IRWXU)
    with pytest.raises(WAWRuntimeHostManifestError):
        load_waw_runtime_host_manifest(path, expected_uid=os.geteuid(), expected_gid=os.getegid())
    os.chmod(path.parent, 0o750)
    os.chmod(path, 0o640)
    with pytest.raises(WAWRuntimeHostManifestError):
        load_waw_runtime_host_manifest(path, expected_uid=os.geteuid(), expected_gid=os.getegid())


def test_strict_decoder_returns_typed_verified_record() -> None:
    raw = encode_runtime_host_manifest(
        RuntimeHostManifest(
            runtime_host_installation_id="wri_" + "1" * 32,
            runtime_host_installation_revision="1",
            runtime_attestation_x25519_fingerprint="a" * 64,
            tmux_fingerprint="b" * 64,
            bridge_fingerprint="c" * 64,
            claude_fingerprint="d" * 64,
            codex_fingerprint="e" * 64,
            attach_supervisor_fingerprint="f" * 64,
            project_root_manifest_path="/var/lib/agentbox-waw/project-root.json",
            project_root_manifest_digest="0" * 64,
            socket_digest="1" * 64,
            config_digest="2" * 64,
            enrollment_epoch="1",
            enrollment_state="steady",
        )
    )
    value = decode_canonical_waw_runtime_host_manifest(raw)
    assert isinstance(value, RuntimeHostManifest)
    assert value.runtime_host_installation_revision == "1"


def test_strict_decoder_rejects_legacy_seven_field_record() -> None:
    with pytest.raises(WAWRuntimeHostManifestError):
        decode_canonical_waw_runtime_host_manifest(
            json.dumps(_valid(), ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
        )
