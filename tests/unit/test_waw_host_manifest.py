from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from agentbox_runtime.waw_host_manifest import (
    WAWRuntimeHostManifestDevelopmentOnlyError,
    WAWRuntimeHostManifestError,
    decode_canonical_waw_runtime_host_manifest,
    load_canonical_waw_runtime_host_manifest,
    load_waw_runtime_host_manifest_development_only,
)
from agentbox_runtime.waw_manifest_codecs import (
    RuntimeHostManifest,
    encode_runtime_host_manifest,
)


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
    value = load_waw_runtime_host_manifest_development_only(
        path, expected_uid=os.geteuid(), expected_gid=os.getegid()
    )
    assert value.runtime_host_installation_id == "wri_" + "c" * 32
    assert value.enrollment_state == "steady"


@pytest.mark.parametrize("field", ["runtime_host_installation_revision", "enrollment_epoch"])
def test_accepts_maximum_uint64_decimal_values(tmp_path: Path, field: str) -> None:
    data = _valid()
    data[field] = str(2**64 - 1)
    path = _write_manifest(tmp_path, data)
    value = load_waw_runtime_host_manifest_development_only(
        path, expected_uid=os.geteuid(), expected_gid=os.getegid()
    )
    assert getattr(value, field) == str(2**64 - 1)


@pytest.mark.parametrize("field", ["runtime_host_installation_revision", "enrollment_epoch"])
def test_rejects_uint64_overflow_decimal_values(tmp_path: Path, field: str) -> None:
    data = _valid()
    data[field] = str(2**64)
    path = _write_manifest(tmp_path, data)
    with pytest.raises(WAWRuntimeHostManifestDevelopmentOnlyError):
        load_waw_runtime_host_manifest_development_only(
            path, expected_uid=os.geteuid(), expected_gid=os.getegid()
        )


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
    with pytest.raises(WAWRuntimeHostManifestDevelopmentOnlyError):
        load_waw_runtime_host_manifest_development_only(
            path, expected_uid=os.geteuid(), expected_gid=os.getegid()
        )


def test_rejects_extra_key_and_noncanonical_bytes(tmp_path: Path) -> None:
    data = _valid()
    data["extra"] = "forbidden"
    path = _write_manifest(tmp_path, data)
    with pytest.raises(WAWRuntimeHostManifestDevelopmentOnlyError):
        load_waw_runtime_host_manifest_development_only(
            path, expected_uid=os.geteuid(), expected_gid=os.getegid()
        )
    path = _write_manifest(tmp_path / "second", _valid())
    payload = path.read_bytes() + b"\n"
    os.chmod(path, 0o600)
    path.write_bytes(payload)
    os.chmod(path, 0o440)
    with pytest.raises(WAWRuntimeHostManifestDevelopmentOnlyError):
        load_waw_runtime_host_manifest_development_only(
            path, expected_uid=os.geteuid(), expected_gid=os.getegid()
        )


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
    with pytest.raises(WAWRuntimeHostManifestDevelopmentOnlyError):
        load_waw_runtime_host_manifest_development_only(
            path, expected_uid=os.geteuid(), expected_gid=os.getegid()
        )


def test_rejects_symlink_manifest(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _valid())
    target = path.with_name("target.json")
    target.write_bytes(path.read_bytes())
    os.chmod(target, 0o440)
    path.unlink()
    path.symlink_to(target)
    with pytest.raises(WAWRuntimeHostManifestDevelopmentOnlyError):
        load_waw_runtime_host_manifest_development_only(
            path, expected_uid=os.geteuid(), expected_gid=os.getegid()
        )


def test_rejects_wrong_parent_or_file_mode(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _valid())
    os.chmod(path.parent, stat.S_IRWXU)
    with pytest.raises(WAWRuntimeHostManifestDevelopmentOnlyError):
        load_waw_runtime_host_manifest_development_only(
            path, expected_uid=os.geteuid(), expected_gid=os.getegid()
        )
    os.chmod(path.parent, 0o750)
    os.chmod(path, 0o640)
    with pytest.raises(WAWRuntimeHostManifestDevelopmentOnlyError):
        load_waw_runtime_host_manifest_development_only(
            path, expected_uid=os.geteuid(), expected_gid=os.getegid()
        )


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
            project_root_manifest_digest="a" * 64,
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


def test_legacy_manifest_helpers_are_not_package_exports() -> None:
    import agentbox_runtime
    import agentbox_runtime.waw_bootstrap as bootstrap_module
    import agentbox_runtime.waw_host_manifest as manifest_module

    legacy_names = {
        "create_waw_lifecycle_registry",
        "load_waw_runtime_host_manifest",
        "WAWRuntimeHostManifest",
        "WAWRuntimeHostManifestDevelopmentOnly",
        "WAWRuntimeHostManifestDevelopmentOnlyError",
    }
    assert legacy_names.isdisjoint(agentbox_runtime.__all__)
    assert legacy_names.isdisjoint(bootstrap_module.__all__)
    assert legacy_names.isdisjoint(manifest_module.__all__)
    assert "create_waw_lifecycle_registry_development_only" not in agentbox_runtime.__all__
    assert "load_waw_runtime_host_manifest_development_only" not in agentbox_runtime.__all__
    assert "WAWRuntimeHostManifestDevelopmentOnly" not in agentbox_runtime.__all__
    assert "WAWRuntimeHostManifestDevelopmentOnlyError" not in agentbox_runtime.__all__
    assert not hasattr(agentbox_runtime, "create_waw_lifecycle_registry")
    assert not hasattr(agentbox_runtime, "load_waw_runtime_host_manifest")
    assert not hasattr(agentbox_runtime, "WAWRuntimeHostManifest")


def _strict_runtime_bytes() -> bytes:
    return cast(
        bytes,
        encode_runtime_host_manifest(
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
                project_root_manifest_digest="a" * 64,
                socket_digest="1" * 64,
                config_digest="2" * 64,
                enrollment_epoch="1",
                enrollment_state="steady",
            )
        ),
    )


def _write_strict_manifest(root: Path, raw: bytes | None = None) -> tuple[Path, bytes]:
    parent = root / "var" / "lib" / "agentbox-waw"
    parent.mkdir(parents=True)
    os.chmod(parent, 0o750)
    payload = _strict_runtime_bytes() if raw is None else raw
    path = parent / "runtime-host-installation.json"
    path.write_bytes(payload)
    os.chmod(path, 0o440)
    return path, payload


def _load_strict(
    path: Path,
    raw: bytes,
    *,
    expected_ancestor_mode: int | None = None,
    expected_parent_mode: int = 0o750,
) -> RuntimeHostManifest:
    return load_canonical_waw_runtime_host_manifest(
        path,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
        expected_host_manifest_digest=hashlib.sha256(raw).hexdigest(),
        trusted_root=path.parents[3],
        expected_ancestor_mode=expected_ancestor_mode,
        expected_parent_mode=expected_parent_mode,
    )


def test_strict_loader_checks_descriptor_provenance_and_digest(tmp_path: Path) -> None:
    path, raw = _write_strict_manifest(tmp_path)
    value = _load_strict(path, raw)
    assert isinstance(value, RuntimeHostManifest)
    assert value.runtime_host_installation_id == "wri_" + "1" * 32


@pytest.mark.parametrize("raw", [_strict_runtime_bytes() + b"\n", b"not-json"])
def test_strict_loader_rejects_noncanonical_or_malformed_bytes(tmp_path: Path, raw: bytes) -> None:
    path, _ = _write_strict_manifest(tmp_path, raw)
    with pytest.raises(WAWRuntimeHostManifestError):
        _load_strict(path, raw)


def test_strict_loader_rejects_digest_mismatch(tmp_path: Path) -> None:
    path, raw = _write_strict_manifest(tmp_path)
    with pytest.raises(WAWRuntimeHostManifestError, match="digest mismatch"):
        load_canonical_waw_runtime_host_manifest(
            path,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
            expected_host_manifest_digest="f" * 64,
            trusted_root=tmp_path,
        )


def test_strict_loader_rejects_ancestor_symlink(tmp_path: Path) -> None:
    path, raw = _write_strict_manifest(tmp_path)
    target = tmp_path / "real-var"
    (target / "lib" / "agentbox-waw").mkdir(parents=True)
    os.chmod(target / "lib" / "agentbox-waw", 0o750)
    (target / "lib" / "agentbox-waw" / path.name).write_bytes(raw)
    os.chmod(target / "lib" / "agentbox-waw" / path.name, 0o440)
    path.parents[2].rename(tmp_path / "var-real")
    (tmp_path / "var").symlink_to(target, target_is_directory=True)
    with pytest.raises(WAWRuntimeHostManifestError):
        _load_strict(path, raw)


def test_strict_loader_rejects_path_outside_trusted_root(tmp_path: Path) -> None:
    path, raw = _write_strict_manifest(tmp_path)
    with pytest.raises(WAWRuntimeHostManifestError, match="outside trusted root"):
        load_canonical_waw_runtime_host_manifest(
            path,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
            expected_host_manifest_digest=hashlib.sha256(raw).hexdigest(),
            trusted_root=tmp_path / "other",
        )


def test_strict_loader_rejects_unsafe_or_unexpected_parent_mode(tmp_path: Path) -> None:
    path, raw = _write_strict_manifest(tmp_path)
    os.chmod(path.parent, 0o770)
    with pytest.raises(WAWRuntimeHostManifestError, match="ancestor mode"):
        _load_strict(path, raw)
    os.chmod(path.parent, 0o750)
    with pytest.raises(WAWRuntimeHostManifestError, match="ancestor mode"):
        _load_strict(path, raw, expected_parent_mode=0o700)


def test_strict_loader_rejects_metadata_mutation_between_fstats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, raw = _write_strict_manifest(tmp_path)
    original = cast(Callable[[int], os.stat_result], os.fstat)
    calls: dict[int, int] = {}

    def mutate_after_first(fd: int) -> os.stat_result:
        result = original(fd)
        calls[fd] = calls.get(fd, 0) + 1
        if stat.S_ISREG(result.st_mode) and calls[fd] == 2:
            return os.stat_result(
                tuple(result[index] + (1 if index == 8 else 0) for index in range(len(result)))
            )
        return result

    monkeypatch.setattr(os, "fstat", mutate_after_first)
    with pytest.raises(WAWRuntimeHostManifestError, match="changed during read"):
        _load_strict(path, raw)
