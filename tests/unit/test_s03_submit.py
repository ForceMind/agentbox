"""S01/S03-S07/S15: bounded public vectors, codecs and domain separation."""

from __future__ import annotations

import base64
import json
import traceback
from pathlib import Path
from typing import Any

import pytest
from agentbox_protocol.noise_nx import NXInitiator, NXResponder
from agentbox_protocol.s03_submit import (
    AAD_DOMAIN,
    CONFIRM_DOMAIN,
    CONTEXT_FIELDS,
    MAX_BODY_BYTES,
    MAX_CONTEXT_BYTES,
    MAX_FRAME_BYTES,
    READY_DOMAIN,
    S03Error,
    aad,
    build_context,
    decode_frame,
    encode_frame,
)

FIXTURE = Path(__file__).parents[1] / "fixtures/kebui_s03_submit/v1.json"


def fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text())  # type: ignore[no-any-return]


def test_frozen_public_known_answer_all_five_records() -> None:
    value = fixture()
    context = build_context(value["context"])
    vectors = value["vectors"]
    assert context.encoded.hex() == vectors["context_hex"]
    assert context.cd == vectors["cd"]
    assert context.prologue.hex() == vectors["prologue_hex"]
    initiator = NXInitiator(context.prologue, ephemeral_private_key=b"\xd1" * 32)
    responder = NXResponder(context.prologue, b"\xd0" * 32, ephemeral_private_key=b"\xd2" * 32)
    message1 = initiator.write_message1()
    assert responder.read_message1(message1) == b""
    message2 = responder.write_message2()
    assert initiator.read_message2(message2) == b""
    web, runtime = initiator.take_transport(), responder.take_transport()
    assert web.remote_static_public_key == context.runtime_pin
    hh = web.handshake_hash
    assert hh == runtime.handshake_hash
    assert hh.hex() == vectors["handshake_hash"]
    ac, ar, ass = (aad(context.digest, hh, *item) for item in [(0, 3, 0), (1, 4, 0), (0, 5, 1)])
    assert len(ac) == len(ar) == len(ass) == 101
    assert ac.hex() == vectors["aad_confirm_hex"]
    assert ar.hex() == vectors["aad_ready_hex"]
    assert ass.hex() == vectors["aad_submit_hex"]
    confirm = web.send.encrypt(CONFIRM_DOMAIN + context.digest + hh, ac)
    assert runtime.receive.decrypt(confirm, ac) == CONFIRM_DOMAIN + context.digest + hh
    ready = runtime.send.encrypt(READY_DOMAIN + context.digest + hh, ar)
    assert web.receive.decrypt(ready, ar) == READY_DOMAIN + context.digest + hh
    body = bytes.fromhex(value["bodies"]["vector_hex"])
    submit = web.send.encrypt(body, ass)
    assert runtime.receive.decrypt(submit, ass) == body
    for kind, data, seq, size in (
        ("KEY_INIT", message1, 0, 209),
        ("KEY_ATTEST", message2, 0, 296),
        ("KEY_CONFIRM", confirm, 0, 317),
        ("KEY_READY", ready, 0, 313),
        ("SUBMIT", submit, 1, 0),
    ):
        raw = encode_frame(context.cd, kind, seq, data)
        assert raw.hex() == vectors["frames"][kind]
        assert decode_frame(raw, context.cd, kind, seq) == data
        if size:
            assert len(raw) == size
    assert (web.send.nonce, web.receive.nonce, runtime.send.nonce, runtime.receive.nonce) == (
        2,
        1,
        1,
        2,
    )
    assert not hasattr(context, "prepare")


def test_exact_maximum_and_rejected_json_body_arithmetic() -> None:
    record = fixture()["context"]
    for key in (
        "auth_epoch",
        "project_revision",
        "binding_revision",
        "host_revision",
        "runtime_epoch",
        "api_authority_epoch",
        "conversation_revision",
        "generation",
    ):
        record[key] = str(2**64 - 1)
    record["agent_type"] = "claude"
    context = build_context(record)
    assert len(context.encoded) == MAX_CONTEXT_BYTES == 739
    assert len(context.prologue) == 777
    assert len(encode_frame(context.cd, "SUBMIT", 1, b"x" * 16400)) == MAX_FRAME_BYTES == 22031
    assert len(json.dumps("\0" * MAX_BODY_BYTES)) == 98306
    assert sum([4194304, 81920, 1048576, 1048576, 262144, 261120, 261120]) == 7157760


@pytest.mark.parametrize("field", CONTEXT_FIELDS + ("runtime_pin",))
def test_all_context_fields_are_present_bounded_exact_strings(field: str) -> None:
    record = fixture()["context"]
    record[field] = "x" * 1025
    with pytest.raises(S03Error, match="s03_invalid"):
        build_context(record)
    record[field] = True
    with pytest.raises(S03Error):
        build_context(record)


@pytest.mark.parametrize("number", ["0", "01", "-1", "+1", " 1", "1 ", "１", "1.0", str(2**64)])
def test_positive_u64_never_coerces(number: str) -> None:
    record = fixture()["context"]
    record["generation"] = number
    with pytest.raises(S03Error):
        build_context(record)


def test_context_rejects_subclass_extra_and_snapshot_mutation() -> None:
    class Exotic(dict[str, Any]):
        pass

    record = fixture()["context"]
    context = build_context(record)
    record["request_id"] = "kreq_" + "f" * 32
    assert context.request_id != record["request_id"]
    invalid: list[object] = [Exotic(record), {**record, "extra": "x"}, [], None]
    for value in invalid:
        with pytest.raises(S03Error):
            build_context(value)


@pytest.mark.parametrize("sequence", [-1, 2, 1.0, True, "1", 2**64])
def test_aad_and_outer_sequence_types(sequence: Any) -> None:
    context = build_context(fixture()["context"])
    with pytest.raises(S03Error):
        aad(context.digest, b"h" * 32, 0, 5, sequence)
    with pytest.raises(S03Error):
        encode_frame(context.cd, "SUBMIT", sequence, b"x" * 17)


@pytest.mark.parametrize(
    "direction,kind,seq", [(1, 3, 0), (0, 4, 0), (1, 5, 1), (0, 5, 0), (0, 3, 1)]
)
def test_aad_only_three_fixed_direction_kind_nonce_tuples(
    direction: int, kind: int, seq: int
) -> None:
    with pytest.raises(S03Error):
        aad(b"d" * 32, b"h" * 32, direction, kind, seq)
    assert AAD_DOMAIN != b"agentbox-a3/aad/v1\0"


def malformed(raw: bytes) -> list[bytes]:
    return [
        raw + b"\n",
        b" " + raw,
        b"\xef\xbb\xbf" + raw,
        raw + raw,
        raw.replace(b'"version":1', b'"version":1,"version":1'),
        raw.replace(b'"version":1', b'"version":1,"extra":0'),
        raw.replace(b'"version":1', b'"version":2'),
        raw.replace(b'"seq":0', b'"seq":-1'),
        raw.replace(b'"seq":0', b'"seq":2'),
        raw.replace(b'"seq":0', b'"seq":0.0'),
        raw.replace(b'"seq":0', b'"seq":"0"'),
        raw.replace(b'"seq":0', b'"seq":00'),
        raw.replace(b'"seq":0', b'"seq":18446744073709551616'),
        raw.replace(b'"data":"', b'"data":["'),
        raw.replace(b'"context"', b'"contex\\u0074"'),
        raw.replace(b'"domain":"agentbox-s03-submit/frame/v1"', b'"domain":"agentbox-a3/frame/v1"'),
        b"[]",
        b"null",
        b"",
        b"x" * (MAX_FRAME_BYTES + 1),
        raw[:-1],
    ]


def test_complete_raw_bound_and_exact_canonical_scanner() -> None:
    context = build_context(fixture()["context"])
    raw = encode_frame(context.cd, "KEY_INIT", 0, b"x" * 32)
    for value in malformed(raw) + [bytearray(raw), memoryview(raw), None]:
        with pytest.raises(S03Error) as caught:
            decode_frame(value, context.cd, "KEY_INIT", 0)
        assert caught.value.__cause__ is caught.value.__context__ is None


def test_noncanonical_base64_padbits_padding_modulus_and_alphabet() -> None:
    context = build_context(fixture()["context"])
    data = base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=")
    raw = encode_frame(context.cd, "KEY_INIT", 0, b"x" * 32)
    assert data[-1:] == b"g"
    for invalid in [data + b"=", data[:-1] + b"h", b"A", data[:-1] + b"+", data[:-1] + b"/"]:
        with pytest.raises(S03Error):
            decode_frame(raw.replace(data, invalid), context.cd, "KEY_INIT", 0)


@pytest.mark.parametrize("kind", ["KEY_INIT", "KEY_ATTEST", "KEY_CONFIRM", "KEY_READY", "SUBMIT"])
def test_all_five_wrong_expected_phase_or_context_rejected(kind: str) -> None:
    vectors = fixture()["vectors"]
    raw = bytes.fromhex(vectors["frames"][kind])
    with pytest.raises(S03Error):
        decode_frame(raw, "f" * 64, kind, int(kind == "SUBMIT"))
    for wrong in {"KEY_INIT", "KEY_ATTEST", "KEY_CONFIRM", "KEY_READY", "SUBMIT"} - {kind}:
        with pytest.raises(S03Error):
            decode_frame(raw, vectors["cd"], wrong, int(wrong == "SUBMIT"))


def test_error_surface_contains_only_fixed_code_and_static_locations() -> None:
    canary = b"private-s03-wire-canary"
    with pytest.raises(S03Error) as caught:
        decode_frame(canary, "0" * 64, "SUBMIT", 1)
    error = caught.value
    assert error.args == ("s03_invalid",)
    assert error.__context__ is error.__cause__ is None
    assert canary.decode() not in "".join(traceback.format_exception(error))
    assert "private-s03-wire-canary" not in repr(error)
    tb = error.__traceback__
    while tb:
        if tb.tb_frame.f_code.co_name == "decode_frame":
            assert tb.tb_frame.f_locals["raw"] is None
        tb = tb.tb_next
