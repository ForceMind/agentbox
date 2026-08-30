from __future__ import annotations

import json

import pytest
from agentbox_protocol.waw_control import (
    WAWControlError,
    decode_control_request,
    decode_control_response,
    encode_control_request,
    encode_control_response,
)


def _request(action: str, **fields: object) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "request_id": "wreq_" + "1" * 32,
        "action": action,
        **fields,
    }


def test_authority_bind_round_trips_strict_single_lf() -> None:
    request = _request(
        "workspace.api_authority.bind",
        api_authority_epoch="7",
        authority_nonce="a" * 32,
    )
    encoded = encode_control_request(request)
    assert encoded.endswith(b"\n")
    assert decode_control_request(encoded) == request


def test_workspace_start_requires_closed_identity_tuple() -> None:
    request = _request(
        "workspace.workspace.start",
        workspace_id="aws_" + "2" * 32,
        project_id="prj_" + "3" * 32,
        agent_type="claude",
        generation="1",
        binding_revision="1",
        binding_digest="a" * 64,
        runtime_host_installation_id="wri_" + "4" * 32,
        runtime_host_installation_revision="1",
    )
    assert decode_control_request(encode_control_request(request)) == request

    with pytest.raises(WAWControlError):
        encode_control_request({**request, "cwd": "/tmp"})


def test_attach_prepare_validates_decimal_replay_hints() -> None:
    request = _request(
        "workspace.attach.prepare",
        workspace_id="aws_" + "2" * 32,
        project_id="prj_" + "3" * 32,
        agent_type="claude",
        attachment_id="att_" + "5" * 32,
        mode="writer",
        lease_number="8",
        generation="1",
        binding_revision="1",
        binding_digest="a" * 64,
        auth_epoch="9",
        api_authority_epoch="10",
        runtime_host_installation_id="wri_" + "4" * 32,
        runtime_host_installation_revision="1",
        runtime_epoch="11",
        resume_cursor="0",
        previous_runtime_epoch=None,
    )
    assert decode_control_request(encode_control_request(request)) == request
    with pytest.raises(WAWControlError):
        encode_control_request({**request, "runtime_epoch": "011"})


def test_register_requires_null_predecessor_for_first_revision() -> None:
    request = _request(
        "workspace.project_binding.register",
        project_id="prj_" + "3" * 32,
        relative_key="safe-project",
        project_revision="1",
        binding_revision="1",
        previous_binding_revision=None,
        previous_binding_digest=None,
        schema_version="waw-project-binding-v1",
        runtime_host_installation_id="wri_" + "4" * 32,
        runtime_host_installation_revision="1",
    )
    assert decode_control_request(encode_control_request(request)) == request
    with pytest.raises(WAWControlError):
        encode_control_request({**request, "previous_binding_revision": 0})
    successor = {
        **request,
        "binding_revision": "2",
        "previous_binding_revision": "2",
        "previous_binding_digest": "b" * 64,
    }
    with pytest.raises(WAWControlError, match="predecessor"):
        encode_control_request(successor)


def test_decoder_rejects_duplicate_keys_constants_and_trailing_data() -> None:
    duplicate = b'{"protocol_version":1,"protocol_version":1}\n'
    with pytest.raises(WAWControlError, match="duplicate"):
        decode_control_request(duplicate)
    with pytest.raises(WAWControlError):
        decode_control_request(
            json.dumps(
                _request(
                    "workspace.api_authority.bind",
                    api_authority_epoch="1",
                    authority_nonce="a" * 32,
                )
            ).encode()
        )
    with pytest.raises(WAWControlError):
        decode_control_request(
            encode_control_request(
                _request(
                    "workspace.api_authority.bind",
                    api_authority_epoch="1",
                    authority_nonce="a" * 32,
                )
            )
            + b"x"
        )


def test_decoder_rejects_oversized_control_envelope_before_action() -> None:
    request = _request(
        "workspace.api_authority.bind",
        api_authority_epoch="1",
        authority_nonce="a" * 64,
    )
    oversized = json.dumps({**request, "padding": "x" * 5000}).encode() + b"\n"
    with pytest.raises(WAWControlError, match="exceeds"):
        decode_control_request(oversized)


def test_start_response_round_trips_decimal_uint64_and_rejects_extra_fields() -> None:
    response = {
        "protocol_version": 1,
        "request_id": "wreq_" + "1" * 32,
        "status": "STARTED",
        "workspace_id": "aws_" + "2" * 32,
        "project_id": "prj_" + "3" * 32,
        "agent_type": "claude",
        "generation": "1",
        "state": "RUNNING",
        "runtime_host_installation_id": "wri_" + "4" * 32,
        "runtime_host_installation_revision": "1",
    }
    assert (
        decode_control_response(
            encode_control_response(response, "workspace.workspace.start"),
            "workspace.workspace.start",
        )
        == response
    )
    with pytest.raises(WAWControlError):
        encode_control_response({**response, "path": "/tmp"}, "workspace.workspace.start")
    with pytest.raises(WAWControlError):
        encode_control_response({**response, "generation": 1}, "workspace.workspace.start")


def test_attach_prepare_response_capability_and_error_shape() -> None:
    response = {
        "protocol_version": 1,
        "request_id": "wreq_" + "1" * 32,
        "status": "PREPARED",
        "workspace_id": "aws_" + "2" * 32,
        "project_id": "prj_" + "3" * 32,
        "agent_type": "claude",
        "attachment_id": "att_" + "5" * 32,
        "mode": "writer",
        "lease_number": "8",
        "generation": "1",
        "binding_revision": "1",
        "binding_digest": "a" * 64,
        "auth_epoch": "9",
        "api_authority_epoch": "10",
        "runtime_host_installation_id": "wri_" + "4" * 32,
        "runtime_host_installation_revision": "1",
        "runtime_epoch": "11",
        "resume_cursor": "0",
        "previous_runtime_epoch": None,
        "capability": "b" * 64,
    }
    assert (
        decode_control_response(
            encode_control_response(response, "workspace.attach.prepare"),
            "workspace.attach.prepare",
        )
        == response
    )
    with pytest.raises(WAWControlError):
        encode_control_response({**response, "capability": "b" * 63}, "workspace.attach.prepare")
    not_running = {key: value for key, value in response.items() if key != "capability"}
    not_running["status"] = "WORKSPACE_NOT_RUNNING"
    assert (
        decode_control_response(
            encode_control_response(not_running, "workspace.attach.prepare"),
            "workspace.attach.prepare",
        )
        == not_running
    )
    error = {
        "protocol_version": 1,
        "request_id": response["request_id"],
        "status": "ERROR",
        "error_code": "WORKSPACE_NOT_RUNNING",
        "retryable": True,
    }
    assert (
        decode_control_response(
            encode_control_response(error, "workspace.attach.prepare"), "workspace.attach.prepare"
        )
        == error
    )
    with pytest.raises(WAWControlError):
        decode_control_response(
            encode_control_response(error, "workspace.attach.prepare"),
            "workspace.attach.prepare",
            expected_request_id="wreq_" + "2" * 32,
        )
    for value in (True, 1.0):
        with pytest.raises(WAWControlError):
            encode_control_response(
                {**error, "protocol_version": value}, "workspace.attach.prepare"
            )


def test_status_response_enforces_capacity_and_detach_cleanup_contract() -> None:
    base = {
        "protocol_version": 1,
        "request_id": "wreq_" + "1" * 32,
        "workspace_id": "aws_" + "2" * 32,
        "project_id": "prj_" + "3" * 32,
        "agent_type": "claude",
        "generation": "1",
        "binding_revision": "1",
        "binding_digest": "a" * 64,
        "state": "RUNNING",
        "reconciliation_state": "authoritative",
        "runtime_epoch": "11",
        "process_state": "RUNNING",
        "exit_code": None,
        "attachment_capacity": {"admitted": "1", "pending": "0", "limit": "32"},
        "status": "STATUS",
    }
    assert (
        decode_control_response(
            encode_control_response(base, "workspace.workspace.status"),
            "workspace.workspace.status",
        )
        == base
    )
    with pytest.raises(WAWControlError):
        encode_control_response(
            {**base, "attachment_capacity": {"admitted": "33", "pending": "32", "limit": "32"}},
            "workspace.workspace.status",
        )


def test_control_uint64_wire_values_are_canonical_decimal_strings() -> None:
    request = _request(
        "workspace.api_authority.bind",
        api_authority_epoch="1",
        authority_nonce="a" * 32,
    )
    with pytest.raises(WAWControlError):
        encode_control_request({**request, "api_authority_epoch": 1})
    with pytest.raises(WAWControlError):
        encode_control_request({**request, "api_authority_epoch": "01"})
    with pytest.raises(WAWControlError):
        encode_control_request({**request, "api_authority_epoch": "0"})


def test_protocol_version_requires_json_integer_and_relative_key_nfc() -> None:
    request = _request(
        "workspace.api_authority.bind",
        api_authority_epoch="1",
        authority_nonce="a" * 32,
    )
    for value in (True, 1.0):
        with pytest.raises(WAWControlError):
            encode_control_request({**request, "protocol_version": value})
    binding = _request(
        "workspace.project_binding.register",
        project_id="prj_" + "3" * 32,
        relative_key="safe-project",
        project_revision="1",
        binding_revision="1",
        previous_binding_revision=None,
        previous_binding_digest=None,
        schema_version="waw-project-binding-v1",
        runtime_host_installation_id="wri_" + "4" * 32,
        runtime_host_installation_revision="1",
    )
    with pytest.raises(WAWControlError):
        encode_control_request({**binding, "relative_key": "Å"})


def test_control_decoder_rejects_crlf() -> None:
    request = _request(
        "workspace.api_authority.bind",
        api_authority_epoch="1",
        authority_nonce="a" * 32,
    )
    with pytest.raises(WAWControlError):
        decode_control_request(encode_control_request(request)[:-1] + b"\r\n")
