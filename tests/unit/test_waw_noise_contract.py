from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest
from agentbox_protocol.waw_noise_contract import (
    WAWNoiseContractError,
    WAWNoiseMessage,
    WAWNoiseMessageType,
    WAWNoiseReplayFence,
    WAWNoiseRole,
    WAWNoiseSession,
    WAWNoiseState,
    WAWNoiseTuple,
    accept_message,
    decode_message,
    encode_message,
    start_session,
    tuple_digest,
)

WORKSPACE = "aws_" + "1" * 32
PROJECT = "prj_" + "2" * 32
HOST = "wri_" + "3" * 32
ATTACHMENT = "att_" + "4" * 32
BINDING = "a" * 64
HANDSHAKE = "wsh_" + "5" * 32

SEQUENCE: tuple[tuple[WAWNoiseMessageType, WAWNoiseRole], ...] = (
    (WAWNoiseMessageType.WS_HELLO, WAWNoiseRole.CLIENT),
    (WAWNoiseMessageType.RUNTIME_HELLO, WAWNoiseRole.RUNTIME),
    (WAWNoiseMessageType.KEY_INIT, WAWNoiseRole.CLIENT),
    (WAWNoiseMessageType.HELLO_ACK, WAWNoiseRole.RUNTIME),
    (WAWNoiseMessageType.KEY_ATTEST, WAWNoiseRole.RUNTIME),
    (WAWNoiseMessageType.KEY_CONFIRM, WAWNoiseRole.CLIENT),
    (WAWNoiseMessageType.KEY_CONFIRM_ACK, WAWNoiseRole.RUNTIME),
    (WAWNoiseMessageType.STREAM_READY, WAWNoiseRole.CLIENT),
    (WAWNoiseMessageType.STREAM_READY_ACK, WAWNoiseRole.RUNTIME),
    (WAWNoiseMessageType.ADMISSION_COMMIT, WAWNoiseRole.CLIENT),
    (WAWNoiseMessageType.ADMISSION_COMMIT_ACK, WAWNoiseRole.RUNTIME),
    (WAWNoiseMessageType.ADMITTED, WAWNoiseRole.RUNTIME),
)


def lifecycle_tuple(*, generation: int = 7) -> WAWNoiseTuple:
    return WAWNoiseTuple(
        workspace_id=WORKSPACE,
        project_id=PROJECT,
        agent_type="claude",
        generation=generation,
        runtime_epoch="9",
        runtime_host_installation_id=HOST,
        runtime_host_installation_revision="2",
        binding_revision="3",
        binding_digest=BINDING,
        api_authority_epoch="4",
        auth_epoch="5",
        attachment_id=ATTACHMENT,
    )


def replace_tuple(value: WAWNoiseTuple, **changes: object) -> WAWNoiseTuple:
    return cast(WAWNoiseTuple, replace(cast(Any, value), **changes))


def replace_session(value: WAWNoiseSession, **changes: object) -> WAWNoiseSession:
    return cast(WAWNoiseSession, replace(cast(Any, value), **changes))


def message(
    session: WAWNoiseSession, message_type: WAWNoiseMessageType, role: WAWNoiseRole
) -> WAWNoiseMessage:
    return WAWNoiseMessage(
        protocol_version=1,
        message_type=message_type,
        role=role,
        handshake_id=session.handshake_id,
        sequence=session.next_sequence,
        tuple=session.tuple,
        transcript_digest=session.transcript_digest,
    )


def new_session() -> WAWNoiseSession:
    return start_session(lifecycle_tuple(), HANDSHAKE, replay_fence=WAWNoiseReplayFence())


def test_exact_sequence_reaches_external_handshake_boundary() -> None:
    session = new_session()
    for message_type, role in SEQUENCE:
        session = accept_message(session, message(session, message_type, role))
    assert session.state is WAWNoiseState.READY_FOR_EXTERNAL_HANDSHAKE
    assert session.next_sequence == len(SEQUENCE)


def test_contract_encode_decode_is_canonical_and_closed() -> None:
    session = new_session()
    value = message(session, *SEQUENCE[0])
    encoded = encode_message(value)
    decoded = decode_message(
        {
            "protocol_version": 1,
            "message_type": "WS_HELLO",
            "role": "CLIENT",
            "handshake_id": HANDSHAKE,
            "sequence": 0,
            "tuple": lifecycle_tuple().__dict__,
            "transcript_digest": session.transcript_digest,
        }
    )
    assert encoded == encode_message(decoded)
    assert decoded == value

    with pytest.raises(WAWNoiseContractError, match="fields are not closed"):
        decode_message({**decoded.__dict__, "unexpected": "forbidden"})


@pytest.mark.parametrize(
    "message_type,role",
    [
        (WAWNoiseMessageType.RUNTIME_HELLO, WAWNoiseRole.RUNTIME),
        (WAWNoiseMessageType.WS_HELLO, WAWNoiseRole.RUNTIME),
    ],
)
def test_wrong_order_or_role_fails_closed(
    message_type: WAWNoiseMessageType, role: WAWNoiseRole
) -> None:
    session = new_session()
    with pytest.raises(WAWNoiseContractError) as exc_info:
        accept_message(session, message(session, message_type, role))
    assert exc_info.value.code == "HANDSHAKE_ORDER_INVALID"


@pytest.mark.parametrize(
    "field,value",
    [
        ("generation", 8),
        ("runtime_epoch", "10"),
        ("binding_digest", "b" * 64),
        ("runtime_host_installation_revision", "3"),
    ],
)
def test_tuple_mutation_fails_closed(field: str, value: object) -> None:
    session = new_session()
    altered_tuple = replace_tuple(session.tuple, **{field: value})
    altered = replace(message(session, *SEQUENCE[0]), tuple=altered_tuple)
    with pytest.raises(WAWNoiseContractError) as exc_info:
        accept_message(session, altered)
    assert exc_info.value.code == "WAW_TUPLE_MISMATCH"


def test_sequence_replay_skip_and_transcript_replay_fail_closed() -> None:
    session = new_session()
    first = message(session, *SEQUENCE[0])
    advanced = accept_message(session, first)
    replayed = replace(message(advanced, *SEQUENCE[1]), sequence=0)
    with pytest.raises(WAWNoiseContractError) as exc_info:
        accept_message(advanced, replayed)
    assert exc_info.value.code == "HANDSHAKE_SEQUENCE_INVALID"

    skipped = replace(message(advanced, *SEQUENCE[1]), sequence=3)
    with pytest.raises(WAWNoiseContractError) as exc_info:
        accept_message(advanced, skipped)
    assert exc_info.value.code == "HANDSHAKE_SEQUENCE_INVALID"

    stale_transcript = replace(
        message(advanced, *SEQUENCE[1]), transcript_digest=session.transcript_digest
    )
    with pytest.raises(WAWNoiseContractError) as exc_info:
        accept_message(advanced, stale_transcript)
    assert exc_info.value.code == "TRANSCRIPT_MISMATCH"


def test_replay_fence_rejects_same_handshake_id_across_sessions() -> None:
    fence = WAWNoiseReplayFence()
    start_session(lifecycle_tuple(), HANDSHAKE, replay_fence=fence)
    with pytest.raises(WAWNoiseContractError) as exc_info:
        start_session(lifecycle_tuple(), HANDSHAKE, replay_fence=fence)
    assert exc_info.value.code == "HANDSHAKE_REPLAY"


def test_replay_fence_fails_closed_when_capacity_is_exhausted() -> None:
    fence = WAWNoiseReplayFence(capacity=1)
    start_session(lifecycle_tuple(), HANDSHAKE, replay_fence=fence)
    with pytest.raises(WAWNoiseContractError) as exc_info:
        start_session(
            lifecycle_tuple(),
            "wsh_" + "6" * 32,
            replay_fence=fence,
        )
    assert exc_info.value.code == "HANDSHAKE_REPLAY_WINDOW_EXHAUSTED"


def test_malformed_session_state_and_sequence_fail_closed() -> None:
    session_value = new_session()
    with pytest.raises(WAWNoiseContractError) as exc_info:
        accept_message(
            replace_session(session_value, state="INIT"),
            message(session_value, *SEQUENCE[0]),
        )
    assert exc_info.value.code == "PROTOCOL_INVALID"

    with pytest.raises(WAWNoiseContractError) as exc_info:
        accept_message(
            replace_session(session_value, next_sequence=-1),
            message(session_value, *SEQUENCE[0]),
        )
    assert exc_info.value.code == "PROTOCOL_INVALID"


def test_sequence_exhaustion_is_terminal_before_increment() -> None:
    session_value = replace(new_session(), next_sequence=2**64 - 1)
    final_message = replace(message(session_value, *SEQUENCE[0]), sequence=2**64 - 1)
    with pytest.raises(WAWNoiseContractError) as exc_info:
        accept_message(session_value, final_message)
    assert exc_info.value.code == "HANDSHAKE_SEQUENCE_EXHAUSTED"


def test_mapping_numeric_values_are_not_coerced() -> None:
    session_value = new_session()
    raw = {
        "protocol_version": 1,
        "message_type": "WS_HELLO",
        "role": "CLIENT",
        "handshake_id": HANDSHAKE,
        "sequence": "0",
        "tuple": {**lifecycle_tuple().__dict__, "generation": "07"},
        "transcript_digest": session_value.transcript_digest,
    }
    with pytest.raises(WAWNoiseContractError) as exc_info:
        decode_message(raw)
    assert exc_info.value.code == "PROTOCOL_INVALID"


def test_bool_protocol_version_is_rejected() -> None:
    session_value = new_session()
    raw = {
        "protocol_version": True,
        "message_type": "WS_HELLO",
        "role": "CLIENT",
        "handshake_id": HANDSHAKE,
        "sequence": 0,
        "tuple": lifecycle_tuple().__dict__,
        "transcript_digest": session_value.transcript_digest,
    }
    with pytest.raises(WAWNoiseContractError) as exc_info:
        decode_message(raw)
    assert exc_info.value.code == "PROTOCOL_INVALID"


def test_typed_message_subclass_is_not_accepted() -> None:
    class DerivedMessage(WAWNoiseMessage):
        pass

    session_value = new_session()
    derived = DerivedMessage(**message(session_value, *SEQUENCE[0]).__dict__)
    with pytest.raises(WAWNoiseContractError) as exc_info:
        accept_message(session_value, derived)
    assert exc_info.value.code == "PROTOCOL_INVALID"


def test_typed_tuple_subclass_is_not_accepted() -> None:
    class DerivedTuple(WAWNoiseTuple):
        pass

    with pytest.raises(WAWNoiseContractError) as exc_info:
        tuple_digest(DerivedTuple(**lifecycle_tuple().__dict__))
    assert exc_info.value.code == "PROTOCOL_INVALID"

    session_value = new_session()
    derived_message = replace(
        message(session_value, *SEQUENCE[0]),
        tuple=DerivedTuple(**lifecycle_tuple().__dict__),
    )
    with pytest.raises(WAWNoiseContractError) as exc_info:
        accept_message(session_value, derived_message)
    assert exc_info.value.code == "PROTOCOL_INVALID"


def test_terminal_state_cannot_reenter() -> None:
    session = new_session()
    for message_type, role in SEQUENCE:
        session = accept_message(session, message(session, message_type, role))
    with pytest.raises(WAWNoiseContractError) as exc_info:
        accept_message(
            session, message(session, WAWNoiseMessageType.ADMITTED, WAWNoiseRole.RUNTIME)
        )
    assert exc_info.value.code == "HANDSHAKE_TERMINAL"


@pytest.mark.parametrize(
    "field,value",
    [
        ("message_type", "UNKNOWN"),
        ("role", "SERVER"),
        ("handshake_id", "not-an-id"),
        ("sequence", -1),
        ("transcript_digest", "0" * 64),
    ],
)
def test_malformed_message_is_rejected(field: str, value: object) -> None:
    session = new_session()
    raw = {
        "protocol_version": 1,
        "message_type": "WS_HELLO",
        "role": "CLIENT",
        "handshake_id": HANDSHAKE,
        "sequence": 0,
        "tuple": lifecycle_tuple().__dict__,
        "transcript_digest": session.transcript_digest,
    }
    raw[field] = value
    with pytest.raises(WAWNoiseContractError):
        decode_message(raw)


def test_tuple_digest_changes_when_bound_metadata_changes() -> None:
    original = lifecycle_tuple()
    assert tuple_digest(original) != tuple_digest(replace(original, binding_revision="4"))


def test_unsupported_agent_type_is_rejected_before_session_creation() -> None:
    with pytest.raises(WAWNoiseContractError) as exc_info:
        start_session(
            replace(lifecycle_tuple(), agent_type="codex"),
            HANDSHAKE,
            replay_fence=WAWNoiseReplayFence(),
        )
    assert exc_info.value.code == "WAW_AGENT_UNSUPPORTED"
