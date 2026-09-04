from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Callable
from pathlib import Path
from typing import cast

import agentbox_runtime.waw_host_manifest as subject
import pytest
from agentbox_runtime.waw_host_manifest import (
    WAW_PUBLIC_MANIFEST_FILENAMES_V2,
    WAWCanonicalManifestBundle,
    WAWCanonicalManifestBundleV2,
    WAWRuntimeHostManifestDevelopmentOnlyError,
    WAWRuntimeHostManifestError,
    decode_canonical_waw_runtime_host_manifest,
    decode_canonical_waw_runtime_host_manifest_v2,
    load_canonical_waw_manifest_bundle,
    load_canonical_waw_manifest_bundle_v2,
    load_canonical_waw_runtime_host_manifest,
    load_canonical_waw_runtime_host_manifest_v2,
    load_verified_canonical_waw_manifest_bundle_v2,
    load_waw_runtime_host_manifest_development_only,
)
from agentbox_runtime.waw_manifest_codecs import (
    RUNTIME_HOST_MANIFEST_V2_PATHS,
    RuntimeHostManifest,
    RuntimeHostManifestV2,
    encode_runtime_host_manifest,
    encode_runtime_host_manifest_v2,
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
            cgroup_delegation_policy_digest="9" * 64,
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


def _write_manifest_bundle(root: Path) -> tuple[Path, dict[str, bytes]]:
    directory = root / "bundle"
    directory.mkdir()
    os.chmod(directory, 0o750)
    payloads = {
        "api-host-anchor.v1": b"anchor-bytes",
        "runtime-host-installation.v1": b"runtime-bytes",
        "project-root.v1": b"project-bytes",
        "cgroup-delegation.v1": b"cgroup-bytes",
    }
    for name, payload in payloads.items():
        path = directory / name
        path.write_bytes(payload)
        os.chmod(path, 0o440)
    return directory, payloads


def _load_bundle(directory: Path) -> WAWCanonicalManifestBundle:
    return load_canonical_waw_manifest_bundle(
        directory,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )


def test_bundle_loader_reads_fixed_files_from_one_directory(tmp_path: Path) -> None:
    directory, payloads = _write_manifest_bundle(tmp_path)
    value = _load_bundle(directory)
    assert value == WAWCanonicalManifestBundle(
        api_host_anchor=payloads["api-host-anchor.v1"],
        runtime_host_installation=payloads["runtime-host-installation.v1"],
        project_root=payloads["project-root.v1"],
        cgroup_delegation=payloads["cgroup-delegation.v1"],
    )


@pytest.mark.parametrize(
    "filename",
    [
        "api-host-anchor.v1",
        "runtime-host-installation.v1",
        "project-root.v1",
        "cgroup-delegation.v1",
    ],
)
def test_bundle_loader_rejects_symlink_file(tmp_path: Path, filename: str) -> None:
    directory, _ = _write_manifest_bundle(tmp_path)
    target = directory / filename
    target.unlink()
    (directory / filename).symlink_to(tmp_path / "outside")
    (tmp_path / "outside").write_bytes(b"not trusted")
    os.chmod(tmp_path / "outside", 0o440)
    with pytest.raises(WAWRuntimeHostManifestError):
        _load_bundle(directory)


def test_bundle_loader_rejects_missing_fixed_file(tmp_path: Path) -> None:
    directory, _ = _write_manifest_bundle(tmp_path)
    (directory / "project-root.v1").unlink()
    with pytest.raises(WAWRuntimeHostManifestError):
        _load_bundle(directory)


def test_bundle_loader_rejects_unsafe_directory_mode(tmp_path: Path) -> None:
    directory, _ = _write_manifest_bundle(tmp_path)
    os.chmod(directory, 0o770)
    with pytest.raises(WAWRuntimeHostManifestError):
        _load_bundle(directory)


def _strict_runtime_bytes() -> bytes:
    return encode_runtime_host_manifest(
        RuntimeHostManifest(
            runtime_host_installation_id="wri_" + "1" * 32,
            runtime_host_installation_revision="1",
            runtime_attestation_x25519_fingerprint="a" * 64,
            tmux_fingerprint="b" * 64,
            bridge_fingerprint="c" * 64,
            claude_fingerprint="d" * 64,
            codex_fingerprint="e" * 64,
            attach_supervisor_fingerprint="f" * 64,
            cgroup_delegation_policy_digest="9" * 64,
            project_root_manifest_path="/var/lib/agentbox-waw/project-root.json",
            project_root_manifest_digest="a" * 64,
            socket_digest="1" * 64,
            config_digest="2" * 64,
            enrollment_epoch="1",
            enrollment_state="steady",
        )
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
    regular_calls = 0

    def mutate_after_first(fd: int) -> os.stat_result:
        nonlocal regular_calls
        result = original(fd)
        if stat.S_ISREG(result.st_mode):
            regular_calls += 1
        if stat.S_ISREG(result.st_mode) and regular_calls == 2:
            return os.stat_result(
                tuple(result[index] + (1 if index == 8 else 0) for index in range(len(result)))
            )
        return result

    monkeypatch.setattr(os, "fstat", mutate_after_first)
    with pytest.raises(WAWRuntimeHostManifestError, match="changed during read"):
        _load_strict(path, raw)


def test_strict_loader_pins_trusted_root_when_manifest_is_direct_child(tmp_path: Path) -> None:
    raw = _strict_runtime_bytes()
    tmp_path.chmod(0o750)
    path = tmp_path / "runtime-host-installation.json"
    path.write_bytes(raw)
    path.chmod(0o440)
    value = load_canonical_waw_runtime_host_manifest(
        path,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
        expected_parent_mode=0o750,
        expected_host_manifest_digest=hashlib.sha256(raw).hexdigest(),
        trusted_root=tmp_path,
    )
    assert value.runtime_host_installation_id == "wri_" + "1" * 32
    tmp_path.chmod(0o700)
    with pytest.raises(WAWRuntimeHostManifestError, match="ancestor mode"):
        load_canonical_waw_runtime_host_manifest(
            path,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
            expected_parent_mode=0o750,
            expected_host_manifest_digest=hashlib.sha256(raw).hexdigest(),
            trusted_root=tmp_path,
        )


@pytest.mark.parametrize(
    ("expected_parent_mode", "expected_file_mode"),
    [(0o770, 0o440), (0o750, 0o640), (0o1750, 0o440)],
)
def test_strict_loader_rejects_weak_mode_policy(
    tmp_path: Path, expected_parent_mode: int, expected_file_mode: int
) -> None:
    path, raw = _write_strict_manifest(tmp_path)
    with pytest.raises(WAWRuntimeHostManifestError, match="unsafe|invalid"):
        load_canonical_waw_runtime_host_manifest(
            path,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
            expected_parent_mode=expected_parent_mode,
            expected_file_mode=expected_file_mode,
            expected_host_manifest_digest=hashlib.sha256(raw).hexdigest(),
            trusted_root=tmp_path,
        )


def _strict_runtime_v2_bytes() -> bytes:
    return encode_runtime_host_manifest_v2(
        {
            "runtime_host_installation_id": "wri_" + "1" * 32,
            "runtime_host_installation_revision": "1",
            "runtime_attestation_x25519_fingerprint": "a" * 64,
            **RUNTIME_HOST_MANIFEST_V2_PATHS,
            "project_root_manifest_digest": "b" * 64,
            "cgroup_delegation_manifest_digest": "c" * 64,
            "executable_inventory_digest": "d" * 64,
            "interactive_profile_bundle_digest": "e" * 64,
            "tmux_config_digest": "f" * 64,
            "sandbox_policy_bundle_digest": "1" * 64,
            "socket_policy_digest": "2" * 64,
            "enrollment_epoch": "1",
            "enrollment_state": "steady",
        }
    )


def test_v2_decoder_and_filesystem_loader_reject_v1_downgrade(tmp_path: Path) -> None:
    v1 = _strict_runtime_bytes()
    v2 = _strict_runtime_v2_bytes()
    assert isinstance(decode_canonical_waw_runtime_host_manifest_v2(v2), RuntimeHostManifestV2)
    with pytest.raises(WAWRuntimeHostManifestError):
        decode_canonical_waw_runtime_host_manifest_v2(v1)

    parent = tmp_path / "var" / "lib" / "agentbox-waw"
    parent.mkdir(parents=True)
    parent.chmod(0o750)
    path = parent / "runtime-host-installation.v2.json"
    path.write_bytes(v2)
    path.chmod(0o440)
    loaded = load_canonical_waw_runtime_host_manifest_v2(
        path,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
        expected_host_manifest_digest=hashlib.sha256(v2).hexdigest(),
        trusted_root=tmp_path,
    )
    assert isinstance(loaded, RuntimeHostManifestV2)

    path.chmod(0o600)
    path.write_bytes(v1)
    path.chmod(0o440)
    with pytest.raises(WAWRuntimeHostManifestError, match="v2 codec"):
        load_canonical_waw_runtime_host_manifest_v2(
            path,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
            expected_host_manifest_digest=hashlib.sha256(v1).hexdigest(),
            trusted_root=tmp_path,
        )


def _write_public_v2_bundle(root: Path) -> tuple[Path, dict[str, bytes]]:
    directory = root / "usr" / "share" / "agentbox" / "waw"
    directory.mkdir(parents=True)
    directory.chmod(0o755)
    payloads = {name: f"fixed:{name}".encode("ascii") for name in WAW_PUBLIC_MANIFEST_FILENAMES_V2}
    for name, payload in payloads.items():
        path = directory / name
        path.write_bytes(payload)
        path.chmod(0o444)
    return directory, payloads


def test_v2_public_bundle_loader_reads_only_the_exact_file_set(tmp_path: Path) -> None:
    directory, payloads = _write_public_v2_bundle(tmp_path)
    loaded = load_canonical_waw_manifest_bundle_v2(
        directory,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )
    assert loaded == WAWCanonicalManifestBundleV2(
        *(payloads[name] for name in WAW_PUBLIC_MANIFEST_FILENAMES_V2)
    )


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_v2_public_bundle_loader_rejects_missing_or_extra_files(
    tmp_path: Path, mutation: str
) -> None:
    directory, _payloads = _write_public_v2_bundle(tmp_path)
    if mutation == "missing":
        (directory / WAW_PUBLIC_MANIFEST_FILENAMES_V2[-1]).unlink()
    else:
        extra = directory / "caller-controlled.json"
        extra.write_bytes(b"rejected")
        extra.chmod(0o444)
    with pytest.raises(WAWRuntimeHostManifestError, match="file set is not exact"):
        load_canonical_waw_manifest_bundle_v2(
            directory,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
        )


@pytest.mark.parametrize(
    "filename",
    [
        "sandbox-policies.v1.json",
        "socket-policy.v1.json",
        "claude-managed-policy.v1.json",
        "codex-managed-policy.v1.json",
    ],
)
def test_v2_public_bundle_loader_never_follows_policy_symlinks(
    tmp_path: Path, filename: str
) -> None:
    directory, _payloads = _write_public_v2_bundle(tmp_path)
    target = directory / filename
    target.unlink()
    outside = tmp_path / f"outside-{filename}"
    outside.write_bytes(b"substitution")
    outside.chmod(0o444)
    target.symlink_to(outside)
    with pytest.raises(WAWRuntimeHostManifestError, match="cannot be read"):
        load_canonical_waw_manifest_bundle_v2(
            directory,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
        )


def test_verified_v2_loader_passes_all_exact_policy_bytes_to_cross_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory, payloads = _write_public_v2_bundle(tmp_path)
    anchor = type("Anchor", (), {"host_manifest_digest": "a" * 64})()
    runtime = object()
    sentinel = object()
    observed: list[tuple[object, ...]] = []
    monkeypatch.setattr(subject, "decode_api_host_anchor_v2", lambda raw: anchor)
    monkeypatch.setattr(
        subject, "load_canonical_waw_runtime_host_manifest_v2", lambda *a, **k: runtime
    )

    def verify(*values: object) -> object:
        observed.append(values)
        return sentinel

    monkeypatch.setattr(subject, "verify_api_host_anchor_v2_cross_manifest", verify)
    assert (
        load_verified_canonical_waw_manifest_bundle_v2(
            tmp_path / "runtime-host-installation.v2.json",
            directory,
            expected_runtime_gid=os.getegid(),
            expected_public_uid=os.geteuid(),
            expected_public_gid=os.getegid(),
        )
        is sentinel
    )
    assert observed == [
        (
            anchor,
            runtime,
            *(payloads[name] for name in WAW_PUBLIC_MANIFEST_FILENAMES_V2[1:]),
        )
    ]
