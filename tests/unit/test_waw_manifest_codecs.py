from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict
from typing import Any, cast

import pytest
import rfc8785
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
    verify_api_host_anchor_cross_manifest,
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
        "cgroup_delegation_policy_digest": manifest_sha256(
            encode_cgroup_delegation_manifest(_cgroup())
        ),
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
    expected = factory()
    if "controllers" in expected:
        expected["controllers"] = tuple(cast(list[str], expected["controllers"]))
    assert asdict(cast(Any, decode(payload))) == expected


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


def test_deterministic_manifest_vectors() -> None:
    vectors = (
        (
            encode_cgroup_delegation_manifest,
            decode_cgroup_delegation_manifest,
            _cgroup,
            b'{"cgroup_mount_device":"0:31","cgroup_mount_filesystem_id":"host-cgroup2-1",'
            b'"cgroup_mount_type":"cgroup2","cgroup_schema_identity":"cgroup-v2",'
            b'"controllers":["cpu","memory","pids"],"cpu_quota_percent":400,'
            b'"cpu_quota_period_usec":100000,"delegate":true,'
            b'"delegate_subgroup":"agentbox-runtime-supervisor","kill_mode":"process",'
            b'"memory_max":536870912,"memory_swap_max":0,"policy_template_digest":"'
            + _HEX_A.encode()
            + b'","protect_control_groups":"private","schema_version":"waw-cgroup-delegation-v1",'
            b'"service_unit":"agentbox-runtime.service","tasks_max":256}',
            "bf51d4a1a2af8420a65e4403bedd9864c00ee566eeda1da34af84652aa7a56f7",
        ),
        (
            encode_api_host_anchor,
            decode_api_host_anchor,
            _anchor,
            b'{"enrollment_epoch":"7","enrollment_state":"steady","host_manifest_digest":"'
            + _HEX_B.encode()
            + b'","project_root_manifest_digest":"'
            + _HEX_A.encode()
            + b'","runtime_attestation_x25519_fingerprint":"'
            + _HEX_A.encode()
            + b'","runtime_host_installation_id":"wri_'
            + b"1" * 32
            + b'","runtime_host_installation_revision":"3","schema_version":"'
            b'waw-api-host-anchor-v1"}',
            "90255756640b41ff6ff9093b8858fc35c007b85f7e6b776ef35de8c34df5ad0b",
        ),
        (
            encode_runtime_host_manifest,
            decode_runtime_host_manifest,
            _runtime,
            b'{"attach_supervisor_fingerprint":"'
            + _HEX_A.encode()
            + b'","bridge_fingerprint":"'
            + _HEX_B.encode()
            + b'","cgroup_delegation_policy_digest":"'
            + b"bf51d4a1a2af8420a65e4403bedd9864c00ee566eeda1da34af84652aa7a56f7"
            + b'","claude_fingerprint":"'
            + _HEX_A.encode()
            + b'","codex_fingerprint":"'
            + _HEX_B.encode()
            + b'","config_digest":"'
            + _HEX_B.encode()
            + b'","enrollment_epoch":"7","enrollment_state":"steady",'
            b'"project_root_manifest_digest":"'
            + _HEX_B.encode()
            + b'","project_root_manifest_path":"/usr/share/agentbox/waw/project-root.v1",'
            b'"runtime_attestation_x25519_fingerprint":"'
            + _HEX_A.encode()
            + b'","runtime_host_installation_id":"wri_'
            + b"1" * 32
            + b'","runtime_host_installation_revision":"3","schema_version":"'
            b'waw-runtime-host-installation-v1",'
            b'"socket_digest":"'
            + _HEX_A.encode()
            + b'","tmux_fingerprint":"'
            + _HEX_A.encode()
            + b'"}',
            "bd811d9d26f213655cd14259f7c1e9d923dd77f189d33e02fac90fce2e205d4d",
        ),
    )
    for encoder, decoder, factory, expected, expected_digest in vectors:
        payload = encoder(factory())
        assert payload == expected
        assert manifest_sha256(payload) == expected_digest
        decoded = asdict(cast(Any, decoder(expected)))
        expected_fields = factory()
        if "controllers" in expected_fields:
            expected_fields["controllers"] = tuple(cast(list[str], expected_fields["controllers"]))
        assert decoded == expected_fields


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


@pytest.mark.parametrize("mode", ["000", "644", "777", "888", "0755", "70"])
def test_project_root_mode_requires_safe_canonical_octal(mode: str) -> None:
    data = _project()
    data["root_mode"] = mode
    with pytest.raises(WAWManifestCodecError):
        encode_project_root_manifest(data)


@pytest.mark.parametrize(
    "subgroup", ["", ".", "..", "/waw", "waw/child", "waw child", "waw\tchild"]
)
def test_cgroup_subgroup_is_one_safe_component(subgroup: str) -> None:
    data = _cgroup()
    data["delegate_subgroup"] = subgroup
    with pytest.raises(WAWManifestCodecError):
        encode_cgroup_delegation_manifest(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tasks_max", 0),
        ("tasks_max", 257),
        ("memory_max", 1),
        ("memory_max", 536870913),
        ("memory_swap_max", 1),
        ("cpu_quota_percent", 0),
        ("cpu_quota_percent", 401),
        ("cpu_quota_period_usec", 99999),
        ("cpu_quota_period_usec", 100001),
        ("tasks_max", 2**64),
        ("memory_max", "536870912"),
    ],
)
def test_cgroup_service_limits_are_fixed_and_bounded(field: str, value: object) -> None:
    data = _cgroup()
    data[field] = value
    with pytest.raises(WAWManifestCodecError, match="approved service limit|invalid"):
        encode_cgroup_delegation_manifest(data)


@pytest.mark.parametrize(
    ("encoder", "factory", "field"),
    [
        (encode_project_root_manifest, _project, "no_shell_executable_digest"),
        (encode_cgroup_delegation_manifest, _cgroup, "policy_template_digest"),
        (encode_api_host_anchor, _anchor, "host_manifest_digest"),
        (encode_runtime_host_manifest, _runtime, "codex_fingerprint"),
    ],
)
def test_identity_digests_reject_zero_sentinel(
    encoder: Encoder, factory: Factory, field: str
) -> None:
    data = factory()
    data[field] = "0" * 64
    with pytest.raises(WAWManifestCodecError):
        encoder(data)


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


def _cross_pin_inputs() -> tuple[bytes, bytes, bytes, bytes]:
    project_raw = encode_project_root_manifest(_project())
    cgroup_raw = encode_cgroup_delegation_manifest(_cgroup())
    runtime_data = _runtime()
    runtime_data["project_root_manifest_digest"] = manifest_sha256(project_raw)
    runtime_data["cgroup_delegation_policy_digest"] = manifest_sha256(cgroup_raw)
    runtime_raw = encode_runtime_host_manifest(runtime_data)
    anchor_data = _anchor()
    anchor_data["host_manifest_digest"] = manifest_sha256(runtime_raw)
    anchor_data["project_root_manifest_digest"] = manifest_sha256(project_raw)
    anchor_raw = encode_api_host_anchor(anchor_data)
    return anchor_raw, runtime_raw, project_raw, cgroup_raw


def test_cross_manifest_pin_accepts_exact_bytes_and_typed_records() -> None:
    anchor_raw, runtime_raw, project_raw, cgroup_raw = _cross_pin_inputs()
    result = verify_api_host_anchor_cross_manifest(anchor_raw, runtime_raw, project_raw, cgroup_raw)
    assert result.anchor == decode_api_host_anchor(anchor_raw)
    assert result.runtime == decode_runtime_host_manifest(runtime_raw)
    assert result.project_root == decode_project_root_manifest(project_raw)
    assert result.cgroup == decode_cgroup_delegation_manifest(cgroup_raw)
    assert result.runtime_manifest_digest == manifest_sha256(runtime_raw)
    assert result.project_root_manifest_digest == manifest_sha256(project_raw)
    assert result.cgroup_manifest_digest == manifest_sha256(cgroup_raw)

    typed_result = verify_api_host_anchor_cross_manifest(
        result.anchor, result.runtime, result.project_root, result.cgroup
    )
    assert typed_result == result


@pytest.mark.parametrize("anchor_typed", [False, True])
@pytest.mark.parametrize("runtime_typed", [False, True])
@pytest.mark.parametrize("project_typed", [False, True])
@pytest.mark.parametrize("cgroup_typed", [False, True])
def test_cross_manifest_pin_accepts_mixed_wire_and_typed_inputs(
    anchor_typed: bool, runtime_typed: bool, project_typed: bool, cgroup_typed: bool
) -> None:
    anchor_raw, runtime_raw, project_raw, cgroup_raw = _cross_pin_inputs()
    anchor_record = decode_api_host_anchor(anchor_raw)
    runtime_record = decode_runtime_host_manifest(runtime_raw)
    project_record = decode_project_root_manifest(project_raw)
    anchor: APIHostAnchor | bytes = anchor_record if anchor_typed else anchor_raw
    runtime: RuntimeHostManifest | bytes = runtime_record if runtime_typed else runtime_raw
    project: ProjectRootManifest | bytes = project_record if project_typed else project_raw

    cgroup_record = decode_cgroup_delegation_manifest(cgroup_raw)
    cgroup: CgroupDelegationManifest | bytes = cgroup_record if cgroup_typed else cgroup_raw
    result = verify_api_host_anchor_cross_manifest(anchor, runtime, project, cgroup)
    assert result.anchor == anchor_record
    assert result.runtime == runtime_record
    assert result.project_root == project_record
    assert result.cgroup == cgroup_record
    assert result.runtime_manifest_digest == manifest_sha256(runtime_raw)
    assert result.project_root_manifest_digest == manifest_sha256(project_raw)


@pytest.mark.parametrize(
    ("decoder", "raw", "needle", "replacement"),
    [
        (
            decode_project_root_manifest,
            encode_project_root_manifest(_project()),
            b'"root_mode":"755"',
            b'"root_mode":"644"',
        ),
        (
            decode_cgroup_delegation_manifest,
            encode_cgroup_delegation_manifest(_cgroup()),
            b'"delegate_subgroup":"agentbox-runtime-supervisor"',
            b'"delegate_subgroup":"agentbox-runtime/subgroup"',
        ),
        (
            decode_project_root_manifest,
            encode_project_root_manifest(_project()),
            b'"no_shell_executable_digest":"' + _HEX_A.encode() + b'"',
            b'"no_shell_executable_digest":"' + b"0" * 64 + b'"',
        ),
        (
            decode_cgroup_delegation_manifest,
            encode_cgroup_delegation_manifest(_cgroup()),
            b'"policy_template_digest":"' + _HEX_A.encode() + b'"',
            b'"policy_template_digest":"' + b"0" * 64 + b'"',
        ),
        (
            decode_api_host_anchor,
            encode_api_host_anchor(_anchor()),
            b'"host_manifest_digest":"' + _HEX_B.encode() + b'"',
            b'"host_manifest_digest":"' + b"0" * 64 + b'"',
        ),
        (
            decode_runtime_host_manifest,
            encode_runtime_host_manifest(_runtime()),
            b'"codex_fingerprint":"' + _HEX_B.encode() + b'"',
            b'"codex_fingerprint":"' + b"0" * 64 + b'"',
        ),
    ],
)
def test_decoders_reject_canonical_wire_values_for_unsafe_fields(
    decoder: Decoder, raw: bytes, needle: bytes, replacement: bytes
) -> None:
    # The substitutions preserve the canonical object ordering and JSON
    # grammar, proving rejection comes from field validation rather than the
    # non-canonical-wire guard.
    assert raw.count(needle) == 1
    malformed = raw.replace(needle, replacement)
    assert malformed != raw
    assert rfc8785.dumps(json.loads(malformed)) == malformed
    with pytest.raises(WAWManifestCodecError):
        decoder(malformed)


@pytest.mark.parametrize("field", ["host_manifest_digest", "project_root_manifest_digest"])
def test_cross_manifest_pin_rejects_digest_mismatch(field: str) -> None:
    anchor_raw, runtime_raw, project_raw, cgroup_raw = _cross_pin_inputs()
    anchor_data = asdict(decode_api_host_anchor(anchor_raw))
    anchor_data[field] = _HEX_A if anchor_data[field] != _HEX_A else _HEX_B
    with pytest.raises(WAWManifestCodecError, match="does not pin"):
        verify_api_host_anchor_cross_manifest(
            encode_api_host_anchor(anchor_data), runtime_raw, project_raw, cgroup_raw
        )


def test_cross_manifest_pin_rejects_cgroup_manifest_digest_mismatch() -> None:
    anchor_raw, runtime_raw, project_raw, cgroup_raw = _cross_pin_inputs()
    changed_cgroup = _cgroup()
    changed_cgroup["delegate_subgroup"] = "agentbox-runtime-other"
    with pytest.raises(WAWManifestCodecError, match="cgroup delegation"):
        verify_api_host_anchor_cross_manifest(
            anchor_raw,
            runtime_raw,
            project_raw,
            encode_cgroup_delegation_manifest(changed_cgroup),
        )


@pytest.mark.parametrize(
    "field",
    [
        "runtime_host_installation_id",
        "runtime_host_installation_revision",
        "runtime_attestation_x25519_fingerprint",
        "enrollment_epoch",
        "enrollment_state",
    ],
)
def test_cross_manifest_pin_rejects_replayed_identity_context(field: str) -> None:
    anchor_raw, runtime_raw, project_raw, cgroup_raw = _cross_pin_inputs()
    runtime_data = asdict(decode_runtime_host_manifest(runtime_raw))
    if field == "runtime_host_installation_id":
        runtime_data[field] = "wri_" + "2" * 32
    elif field == "runtime_host_installation_revision":
        runtime_data[field] = "4"
    elif field == "runtime_attestation_x25519_fingerprint":
        runtime_data[field] = _HEX_B
    elif field == "enrollment_epoch":
        runtime_data[field] = "8"
    else:
        runtime_data[field] = "rotation"
    changed_runtime_raw = encode_runtime_host_manifest(runtime_data)
    anchor_data = asdict(decode_api_host_anchor(anchor_raw))
    anchor_data["host_manifest_digest"] = manifest_sha256(changed_runtime_raw)
    with pytest.raises(WAWManifestCodecError, match="identity mismatch"):
        verify_api_host_anchor_cross_manifest(
            encode_api_host_anchor(anchor_data), changed_runtime_raw, project_raw, cgroup_raw
        )


@pytest.mark.parametrize(
    "mutator",
    [
        lambda raw: raw + b"\n",
        lambda raw: raw.replace(
            b'"schema_version":"waw-runtime-host-installation-v1"',
            b'"schema_version":"legacy"',
        ),
    ],
)
def test_cross_manifest_pin_rejects_noncanonical_or_legacy_runtime(mutator: Mutator) -> None:
    anchor_raw, runtime_raw, project_raw, cgroup_raw = _cross_pin_inputs()
    with pytest.raises(WAWManifestCodecError):
        verify_api_host_anchor_cross_manifest(
            anchor_raw, mutator(runtime_raw), project_raw, cgroup_raw
        )


def test_cross_manifest_pin_rejects_zero_project_digest_before_epoch_use() -> None:
    anchor_raw, runtime_raw, project_raw, cgroup_raw = _cross_pin_inputs()
    anchor_data = asdict(decode_api_host_anchor(anchor_raw))
    anchor_data["project_root_manifest_digest"] = "0" * 64
    with pytest.raises(WAWManifestCodecError):
        verify_api_host_anchor_cross_manifest(
            encode_api_host_anchor(anchor_data), runtime_raw, project_raw, cgroup_raw
        )
