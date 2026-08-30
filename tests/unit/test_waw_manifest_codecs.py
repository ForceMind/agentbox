from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any, cast

import pytest
from agentbox_runtime.waw_manifest_codecs import (
    APIHostAnchor,
    CgroupDelegationManifest,
    ProjectRootManifest,
    RuntimeHostManifest,
    WAWManifestCodecError,
    decode_api_host_anchor,
    decode_cgroup_delegation_manifest,
    decode_project_root_manifest,
    decode_runtime_host_manifest,
    encode_api_host_anchor,
    encode_cgroup_delegation_manifest,
    encode_project_root_manifest,
    encode_runtime_host_manifest,
    manifest_sha256,
)

_HEX_A = "a" * 64
_HEX_B = "b" * 64

Encoder = Callable[[object], bytes]
Decoder = Callable[[bytes], object]
Factory = Callable[[], dict[str, object]]
Mutator = Callable[[bytes], bytes]


def _project() -> dict[str, object]:
    return {
        "manifest_revision": "1",
        "configured_root": "/srv/agentbox/projects",
        "root_device": "2049",
        "root_mount_id": "42",
        "root_filesystem_id": "host-filesystem-1",
        "root_uid": "0",
        "root_gid": "0",
        "root_mode": "755",
        "relative_key_grammar_version": "one-component-v1",
        "binding_digest_algorithm": "sha256-rfc8785",
        "no_shell_executable_path": "/bin/false",
        "no_shell_executable_digest": _HEX_A,
    }


def _cgroup() -> dict[str, object]:
    return {
        "service_unit": "agentbox-runtime.service",
        "cgroup_mount_type": "cgroup2",
        "cgroup_mount_device": "0:31",
        "cgroup_mount_filesystem_id": "host-cgroup2-1",
        "cgroup_schema_identity": "cgroup-v2",
        "delegate": True,
        "delegate_subgroup": "agentbox-runtime-supervisor",
        "protect_control_groups": "private",
        "kill_mode": "process",
        "controllers": ["cpu", "memory", "pids"],
        "tasks_max": 256,
        "memory_max": 536870912,
        "memory_swap_max": 0,
        "cpu_quota_percent": 400,
        "cpu_quota_period_usec": 100000,
        "policy_template_digest": _HEX_A,
    }


def _anchor() -> dict[str, object]:
    return {
        "runtime_host_installation_id": "wri_" + "1" * 32,
        "runtime_host_installation_revision": "3",
        "runtime_attestation_x25519_fingerprint": _HEX_A,
        "host_manifest_digest": _HEX_B,
        "project_root_manifest_digest": _HEX_A,
        "enrollment_epoch": "7",
        "enrollment_state": "steady",
    }


def _runtime() -> dict[str, object]:
    return {
        "runtime_host_installation_id": "wri_" + "1" * 32,
        "runtime_host_installation_revision": "3",
        "runtime_attestation_x25519_fingerprint": _HEX_A,
        "tmux_fingerprint": _HEX_A,
        "bridge_fingerprint": _HEX_B,
        "claude_fingerprint": _HEX_A,
        "codex_fingerprint": _HEX_B,
        "attach_supervisor_fingerprint": _HEX_A,
        "project_root_manifest_path": "/usr/share/agentbox/waw/project-root.v1",
        "project_root_manifest_digest": _HEX_B,
        "socket_digest": _HEX_A,
        "config_digest": _HEX_B,
        "enrollment_epoch": "7",
        "enrollment_state": "steady",
    }


@pytest.mark.parametrize(
    ("encode", "decode", "factory"),
    [
        (encode_project_root_manifest, decode_project_root_manifest, _project),
        (encode_cgroup_delegation_manifest, decode_cgroup_delegation_manifest, _cgroup),
        (encode_api_host_anchor, decode_api_host_anchor, _anchor),
        (encode_runtime_host_manifest, decode_runtime_host_manifest, _runtime),
    ],
)
def test_codec_round_trip_is_canonical(encode: Encoder, decode: Decoder, factory: Factory) -> None:
    payload = encode(factory())
    assert payload == encode(json.loads(payload))
    assert decode(payload) == decode(payload)


def test_deterministic_project_root_vector() -> None:
    payload = encode_project_root_manifest(_project())
    assert payload == (
        b'{"binding_digest_algorithm":"sha256-rfc8785","configured_root":"/srv/agentbox/projects",'
        b'"manifest_revision":"1","no_shell_executable_digest":"'
        + _HEX_A.encode()
        + b'","no_shell_executable_path":"/bin/false","relative_key_grammar_version":"'
        b'one-component-v1",'
        b'"root_device":"2049","root_filesystem_id":"host-filesystem-1","root_gid":"0",'
        b'"root_mode":"755","root_mount_id":"42","root_uid":"0","schema_version":"waw-project-root-v1"}'
    )
    assert manifest_sha256(payload) == hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize(
    "mutator",
    [
        lambda raw: raw.replace(
            b'"schema_version":"waw-project-root-v1"',
            b'"extra":1,"schema_version":"waw-project-root-v1"',
        ),
        lambda raw: raw.replace(
            b'"schema_version":"waw-project-root-v1"',
            b'"schema_version":"waw-project-root-v1","schema_version":"waw-project-root-v1"',
        ),
        lambda raw: raw + b"\n",
    ],
)
def test_decoder_rejects_unknown_duplicate_and_noncanonical(mutator: Mutator) -> None:
    raw = mutator(encode_project_root_manifest(_project()))
    with pytest.raises(WAWManifestCodecError):
        decode_project_root_manifest(raw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("manifest_revision", "0"),
        ("manifest_revision", str(2**64)),
        ("root_mode", "0755"),
        ("configured_root", "/srv/agentbox/../projects"),
        ("no_shell_executable_path", "/bin/sh"),
        ("no_shell_executable_digest", "A" * 64),
    ],
)
def test_project_rejects_unsafe_values(field: str, value: object) -> None:
    data = _project()
    data[field] = value
    with pytest.raises(WAWManifestCodecError):
        encode_project_root_manifest(data)


def test_closed_schema_does_not_accept_secret_or_terminal_fields() -> None:
    data = _runtime()
    data["api_key"] = "synthetic-only-and-rejected"
    data["terminal_output"] = "synthetic-only-and-rejected"
    with pytest.raises(WAWManifestCodecError):
        encode_runtime_host_manifest(data)


@pytest.mark.parametrize("encoder", [encode_api_host_anchor, encode_runtime_host_manifest])
def test_runtime_host_identity_cannot_use_project_id_namespace(encoder: Encoder) -> None:
    data = _anchor() if encoder is encode_api_host_anchor else _runtime()
    data["runtime_host_installation_id"] = "prj_" + "1" * 32
    with pytest.raises(WAWManifestCodecError):
        encoder(data)


def test_dataclass_values_are_supported() -> None:
    value = ProjectRootManifest(**cast(dict[str, Any], _project()))
    assert decode_project_root_manifest(encode_project_root_manifest(value)) == value
    assert isinstance(
        decode_cgroup_delegation_manifest(
            encode_cgroup_delegation_manifest(
                CgroupDelegationManifest(**cast(dict[str, Any], _cgroup()))
            )
        ),
        CgroupDelegationManifest,
    )
    assert isinstance(
        decode_api_host_anchor(
            encode_api_host_anchor(APIHostAnchor(**cast(dict[str, Any], _anchor())))
        ),
        APIHostAnchor,
    )
    assert isinstance(
        decode_runtime_host_manifest(
            encode_runtime_host_manifest(RuntimeHostManifest(**cast(dict[str, Any], _runtime())))
        ),
        RuntimeHostManifest,
    )
