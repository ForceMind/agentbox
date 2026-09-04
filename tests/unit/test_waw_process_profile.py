from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, cast

import pytest
import rfc8785
from agentbox_runtime.waw_process_profile import (
    EXECUTABLE_POLICIES_V1,
    INTERACTIVE_PROFILE_CONSTANTS_V1,
    ExecutableInventoryV1,
    InteractiveProfileBundleV1,
    WAWProcessProfileError,
    decode_codex_managed_policy_bundle_v1,
    decode_executable_inventory_v1,
    decode_interactive_profile_bundle_v1,
    encode_codex_managed_policy_bundle_v1,
    encode_executable_inventory_v1,
    encode_interactive_profile_bundle_v1,
    verify_codex_managed_policy_bundle_v1,
)


def executable_inventory() -> dict[str, object]:
    entries: list[dict[str, object]] = []
    for index, policy in enumerate(EXECUTABLE_POLICIES_V1, start=1):
        entries.append(
            {
                "kind": policy.kind,
                "path": policy.fixed_path or f"/opt/vendor/{policy.kind}",
                "sha256": f"{index:x}" * 64,
                "max_bytes": policy.max_bytes,
                "version_identity": policy.version_identity,
                "version_probe_id": policy.version_probe_id,
            }
        )
    return {"executables": entries}


def interactive_profiles() -> dict[str, object]:
    profiles: list[dict[str, object]] = []
    for index, agent_type in enumerate(("claude", "codex"), start=10):
        profile = dict(INTERACTIVE_PROFILE_CONSTANTS_V1[agent_type])
        for field in ("workspace_argv", "version_argv", "auth_probe_argv", "local_login_argv"):
            profile[field] = list(cast(tuple[str, ...], profile[field]))
        profile["managed_policy_digest"] = f"{index:x}" * 64
        profiles.append(profile)
    return {"profiles": profiles}


def test_exact_six_inventory_round_trips_as_canonical_typed_record() -> None:
    raw = encode_executable_inventory_v1(executable_inventory())
    assert raw == rfc8785.dumps(json.loads(raw))
    decoded = decode_executable_inventory_v1(raw)
    assert isinstance(decoded, ExecutableInventoryV1)
    assert tuple(item.kind for item in decoded.executables) == tuple(
        policy.kind for policy in EXECUTABLE_POLICIES_V1
    )
    assert decode_executable_inventory_v1(encode_executable_inventory_v1(decoded)) == decoded


@pytest.mark.parametrize("operation", ["missing", "extra", "reordered", "duplicate"])
def test_inventory_requires_exact_six_ordered_kinds(operation: str) -> None:
    value = executable_inventory()
    entries = value["executables"]
    assert isinstance(entries, list)
    if operation == "missing":
        entries.pop()
    elif operation == "extra":
        entries.append(dict(entries[-1]))
    elif operation == "reordered":
        entries[0], entries[1] = entries[1], entries[0]
    else:
        entries[1] = dict(entries[0])
    with pytest.raises(WAWProcessProfileError):
        encode_executable_inventory_v1(value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("path", "relative"),
        ("sha256", "0" * 64),
        ("max_bytes", 1),
        ("version_identity", "caller-version"),
        ("version_probe_id", "caller-probe"),
    ],
)
def test_inventory_rejects_unfixed_path_digest_limit_and_version_fields(
    field: str, value: object
) -> None:
    manifest = executable_inventory()
    entries = manifest["executables"]
    assert isinstance(entries, list)
    entries[0][field] = value
    with pytest.raises(WAWProcessProfileError):
        encode_executable_inventory_v1(manifest)


@pytest.mark.parametrize("forbidden", ["argv", "env", "command", "api_key", "caller_path"])
def test_inventory_rejects_secret_command_and_caller_fields(forbidden: str) -> None:
    manifest = executable_inventory()
    entries = manifest["executables"]
    assert isinstance(entries, list)
    entries[-1][forbidden] = "rejected"
    with pytest.raises(WAWProcessProfileError, match="closed"):
        encode_executable_inventory_v1(manifest)


def test_inventory_rejects_one_path_reused_for_two_kinds() -> None:
    manifest = executable_inventory()
    entries = manifest["executables"]
    assert isinstance(entries, list)
    entries[-1]["path"] = entries[-2]["path"]
    with pytest.raises(WAWProcessProfileError, match="distinct"):
        encode_executable_inventory_v1(manifest)


def test_exact_claude_codex_profiles_round_trip_as_canonical_typed_record() -> None:
    raw = encode_interactive_profile_bundle_v1(interactive_profiles())
    assert raw == rfc8785.dumps(json.loads(raw))
    decoded = decode_interactive_profile_bundle_v1(raw)
    assert isinstance(decoded, InteractiveProfileBundleV1)
    assert tuple(profile.agent_type for profile in decoded.profiles) == ("claude", "codex")
    assert decoded.profiles[0].workspace_argv == ()
    assert decoded.profiles[0].auth_probe_argv == ("auth", "status")
    assert decoded.profiles[1].local_login_argv == ("login", "--device-auth")
    assert (
        decode_interactive_profile_bundle_v1(encode_interactive_profile_bundle_v1(decoded))
        == decoded
    )


@pytest.mark.parametrize(
    "field",
    [
        "profile_id",
        "executable_kind",
        "workspace_argv",
        "version_argv",
        "auth_probe_argv",
        "local_login_argv",
        "auth_parser_id",
        "home",
        "state_env_name",
        "state_root",
        "environment_profile_id",
        "managed_policy_path",
        "retention_profile_id",
        "rlimit_profile_id",
        "sandbox_profile_id",
        "trust_mode",
    ],
)
def test_profile_rejects_every_non_digest_constant_mutation(field: str) -> None:
    bundle = interactive_profiles()
    profiles = bundle["profiles"]
    assert isinstance(profiles, list)
    profiles[0][field] = ["other"] if field.endswith("argv") else "other"
    with pytest.raises(WAWProcessProfileError):
        encode_interactive_profile_bundle_v1(bundle)


@pytest.mark.parametrize("forbidden", ["environment", "secret", "credential", "caller", "cwd"])
def test_profile_rejects_freeform_environment_secret_caller_and_path_fields(forbidden: str) -> None:
    bundle = interactive_profiles()
    profiles = bundle["profiles"]
    assert isinstance(profiles, list)
    profiles[0][forbidden] = {"unsafe": "value"}
    with pytest.raises(WAWProcessProfileError, match="closed"):
        encode_interactive_profile_bundle_v1(bundle)


@pytest.mark.parametrize(
    "factory,encoder",
    [
        (executable_inventory, encode_executable_inventory_v1),
        (interactive_profiles, encode_interactive_profile_bundle_v1),
    ],
)
def test_decoder_rejects_duplicate_unknown_and_noncanonical_bytes(
    factory: Any, encoder: Any
) -> None:
    raw = encoder(factory())
    duplicate = raw.replace(b'{"', b'{"schema_version":"duplicate","', 1)
    for invalid in (raw + b"\n", duplicate):
        with pytest.raises(WAWProcessProfileError):
            if encoder is encode_executable_inventory_v1:
                decode_executable_inventory_v1(invalid)
            else:
                decode_interactive_profile_bundle_v1(invalid)


def test_directly_constructed_typed_records_are_revalidated() -> None:
    decoded = decode_executable_inventory_v1(encode_executable_inventory_v1(executable_inventory()))
    data = asdict(decoded)
    data["executables"][0]["version_probe_id"] = "caller-probe"
    with pytest.raises(WAWProcessProfileError):
        encode_executable_inventory_v1(data)


def test_codex_policy_bundle_binds_exact_two_named_files() -> None:
    requirements = b"allow_remote_control = false\n"
    defaults = b'[history]\npersistence = "none"\n'
    raw = encode_codex_managed_policy_bundle_v1(requirements=requirements, managed_config=defaults)
    bundle = verify_codex_managed_policy_bundle_v1(
        raw, requirements=requirements, managed_config=defaults
    )
    assert [item.name for item in bundle.files] == [
        "requirements.toml",
        "managed_config.toml",
    ]
    assert decode_codex_managed_policy_bundle_v1(raw) == bundle
    for changed_requirements, changed_defaults in (
        (requirements + b" ", defaults),
        (requirements, defaults + b" "),
    ):
        with pytest.raises(WAWProcessProfileError, match="digest mismatch"):
            verify_codex_managed_policy_bundle_v1(
                raw,
                requirements=changed_requirements,
                managed_config=changed_defaults,
            )
