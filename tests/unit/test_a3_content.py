"""Pure A3 schema/transcript evidence. No Runtime admission or crypto is exercised."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from agentbox_protocol.a3_content import (
    MAX_PAGE_BYTES,
    ContentError,
    ContentRead,
    application_aad,
    context_bytes,
    context_digest,
    decode_context,
    decode_message,
    encode_message,
    prepare_pages,
    selector_commitment,
    validate_context,
)

VECTOR = json.loads((Path(__file__).parents[1] / "fixtures/a3_content/v1.json").read_text())
CONTEXT = VECTOR["context"]
MESSAGES = [s.encode() for s in VECTOR["messages_json"]]
PATCH = bytes.fromhex(VECTOR["patch_hex"])


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def accept(read: ContentRead, raw: bytes, now: int = 1) -> bytes | None:
    return read.accept(raw, now_ms=now, current_context=CONTEXT)


def started() -> ContentRead:
    read = ContentRead(CONTEXT, now_ms=0, deadline_ms=30_000)
    assert accept(read, MESSAGES[0]) is None
    return read


def test_literal_reference_and_complete_roundtrip() -> None:
    assert context_bytes(CONTEXT) == VECTOR["context_json"].encode()
    assert decode_context(context_bytes(CONTEXT)) == CONTEXT
    assert context_digest(CONTEXT) == VECTOR["context_digest"]
    assert selector_commitment(VECTOR["selector"]) == CONTEXT["selector_commitment"]
    assert application_aad(CONTEXT, "8" * 64, "PATCH_PAGE", 0) == VECTOR["aad_json"].encode()
    for raw in MESSAGES:
        assert encode_message(decode_message(raw)) == raw
    assert prepare_pages(CONTEXT, PATCH, "1791111111111") == tuple(MESSAGES[1:3])
    read = started()
    assert accept(read, MESSAGES[1]) is None
    assert accept(read, MESSAGES[2]) == PATCH
    with pytest.raises(ContentError):
        accept(read, MESSAGES[2])


@pytest.mark.parametrize("raw", VECTOR["invalid_messages"])
def test_shared_negative_vectors(raw: str) -> None:
    with pytest.raises(ContentError):
        decode_message(raw.encode())


@pytest.mark.parametrize("key", list(CONTEXT))
@pytest.mark.parametrize("bad", [None, True, 1, [], {}, "", "bad"])
def test_context_no_coercion_or_defaults(key: str, bad: Any) -> None:
    if CONTEXT[key] == bad and type(CONTEXT[key]) is type(bad):
        return
    with pytest.raises(ContentError):
        validate_context({**CONTEXT, key: bad})


@pytest.mark.parametrize("raw", [b"", b"{}", b"\xff", b"[" * 16_384, b" " * 16_385])
def test_bounded_flat_parser(raw: bytes) -> None:
    with pytest.raises(ContentError):
        decode_message(raw)


def test_context_is_detached_and_complete() -> None:
    value = dict(CONTEXT)
    result = validate_context(value)
    value["request_nonce"] = "9" * 64
    assert result == CONTEXT
    for key in CONTEXT:
        with pytest.raises(ContentError):
            validate_context({k: v for k, v in CONTEXT.items() if k != key})
    with pytest.raises(ContentError):
        validate_context({**CONTEXT, "extra": "x"})
    raw = VECTOR["context_json"].replace(
        '"protocol_version":1', '"protocol_version":1,"protocol_version":1'
    )
    with pytest.raises(ContentError):
        decode_context(raw.encode())


@pytest.mark.parametrize(
    "changes",
    [
        {"sequence": 1},
        {"request_nonce": "9" * 64},
        {"context_digest": "9" * 64},
    ],
)
def test_gap_nonce_and_context_failure_permanently_close(changes: dict[str, object]) -> None:
    read = started()
    bad = {**json.loads(MESSAGES[1]), **changes}
    with pytest.raises(ContentError):
        accept(read, encode_message(bad))
    with pytest.raises(ContentError):
        accept(read, MESSAGES[1])


def test_page_replay_read_replay_and_out_of_order_close() -> None:
    for first, second in [(0, 0), (0, 2), (1, 0), (2, 0), (3, 0)]:
        read = ContentRead(CONTEXT, now_ms=0, deadline_ms=30_000)
        with pytest.raises(ContentError):
            accept(read, MESSAGES[first])
            accept(read, MESSAGES[second])
        with pytest.raises(ContentError):
            accept(read, MESSAGES[0])
    read = started()
    accept(read, MESSAGES[1])
    with pytest.raises(ContentError):
        accept(read, MESSAGES[1])


@pytest.mark.parametrize(
    "key,value",
    [("total_bytes", len(PATCH) + 1), ("patch_digest", "9" * 64), ("observed_at_ms", "2")],
)
def test_end_description_drift_discards(key: str, value: object) -> None:
    read = started()
    accept(read, MESSAGES[1])
    with pytest.raises(ContentError):
        accept(read, encode_message({**json.loads(MESSAGES[2]), key: value}))
    assert read._pages == []


def test_digest_not_just_cross_page_equality() -> None:
    read = started()
    for raw in MESSAGES[1:2]:
        accept(read, encode_message({**json.loads(raw), "patch_digest": "9" * 64}))
    with pytest.raises(ContentError):
        accept(read, encode_message({**json.loads(MESSAGES[2]), "patch_digest": "9" * 64}))


@pytest.mark.parametrize("key", list(CONTEXT))
def test_current_context_change_fences(key: str) -> None:
    read = started()
    with pytest.raises(ContentError):
        read.check(now_ms=2, current_context={**CONTEXT, key: "changed"})
    with pytest.raises(ContentError):
        accept(read, MESSAGES[1])


def test_timeout_regression_close_and_error() -> None:
    for now in [30_000, 30_001, 0, True, 1.5]:
        read = started()
        with pytest.raises(ContentError):
            accept(read, MESSAGES[1], now)  # type: ignore[arg-type]
        assert read._pages == []
    read = started()
    read.close()
    with pytest.raises(ContentError):
        accept(read, MESSAGES[1])
    read = started()
    with pytest.raises(ContentError, match="PATCH_STALE"):
        accept(read, MESSAGES[3])
    with pytest.raises(ContentError):
        accept(read, MESSAGES[1])


def test_exact_transfer_capacity_and_all_or_nothing() -> None:
    # Fixed metadata lengths for this context/time and six-digit total_bytes.
    # 425 bytes of overhead => floor((16384 - 425)*6/8) = 11969 bytes/page.
    probe = prepare_pages(CONTEXT, b"x" * 180_000, "1791111111111")
    import base64

    page = json.loads(probe[0])
    capacity = len(base64.urlsafe_b64decode(page["data"] + "=" * (-len(page["data"]) % 4)))
    assert capacity == 11_969
    limit = capacity * 16
    exact = prepare_pages(CONTEXT, b"x" * limit, "1791111111111")
    assert len(exact) == 17
    assert len(exact[10]) == MAX_PAGE_BYTES
    assert all(len(raw) <= MAX_PAGE_BYTES for raw in exact)
    read = started()
    for raw in exact[:-1]:
        assert accept(read, raw) is None
    assert accept(read, exact[-1]) == b"x" * limit
    for size in [limit + 1, 262_144, 262_145]:
        with pytest.raises(ContentError, match="PATCH_TOO_LARGE"):
            prepare_pages(CONTEXT, b"x" * size, "1791111111111")


@pytest.mark.parametrize("patch", [b"\xff", b"\xed\xa0\x80"])
def test_invalid_utf8(patch: bytes) -> None:
    with pytest.raises(ContentError, match="PATCH_UNAVAILABLE_ENCODING"):
        prepare_pages(CONTEXT, patch, "1")


@pytest.mark.parametrize(
    "separator", ["\n", "\r", "\r\n", "\v", "\f", "\x1c", "\x85", "\u2028", "\u2029"]
)
def test_line_budget(separator: str) -> None:
    prepare_pages(CONTEXT, ("x" + separator).encode() * 4096, "1")
    with pytest.raises(ContentError, match="PATCH_TOO_LARGE"):
        prepare_pages(CONTEXT, ("x" + separator).encode() * 4097, "1")


def test_selector_commitment_and_aad_domains() -> None:
    read = ContentRead(CONTEXT, now_ms=0, deadline_ms=30_000)
    with pytest.raises(ContentError):
        accept(read, encode_message({**json.loads(MESSAGES[0]), "selection_id": "B" * 156}))
    baseline = application_aad(CONTEXT, "8" * 64, "PATCH_PAGE", 0)
    assert b"agentbox-waw" not in baseline
    for kind, sequence in [
        ("PATCH_READ", 0),
        ("PATCH_PAGE", 1),
        ("PATCH_END", 1),
        ("PATCH_ERROR", 0),
    ]:
        assert application_aad(CONTEXT, "8" * 64, kind, sequence) != baseline
    assert application_aad({**CONTEXT, "runtime_epoch": "7"}, "8" * 64, "PATCH_PAGE", 0) != baseline
    for kind, sequence in [
        ("PATCH_READ", 1),
        ("PATCH_ERROR", 1),
        ("PATCH_PAGE", 16),
        ("PATCH_END", 0),
        ("OUTPUT", 0),
    ]:
        with pytest.raises(ContentError):
            application_aad(CONTEXT, "8" * 64, kind, sequence)


@pytest.mark.parametrize("index", range(4))
def test_each_message_field_is_required_and_strict(index: int) -> None:
    message = json.loads(MESSAGES[index])
    invalid_values: list[object] = [None, [], {}, True, 1.0, ""]
    for key, original in message.items():
        for bad in invalid_values:
            if type(original) is type(bad) and original == bad:
                continue
            with pytest.raises(ContentError):
                encode_message({**message, key: bad})
        with pytest.raises(ContentError):
            encode_message({k: v for k, v in message.items() if k != key})
    with pytest.raises(ContentError):
        encode_message({**message, "extra": "x"})


def test_valid_but_different_context_and_scope_fail() -> None:
    for key in ["binding_digest", "session_scope", "selector_commitment", "request_nonce"]:
        changed = {**CONTEXT, key: "9" * 64}
        assert validate_context(changed)
        read = started()
        with pytest.raises(ContentError):
            read.check(now_ms=2, current_context=changed)
    for key in [
        "project_revision",
        "binding_revision",
        "runtime_host_installation_revision",
        "runtime_epoch",
    ]:
        changed = {**CONTEXT, key: "99"}
        read = started()
        with pytest.raises(ContentError):
            read.check(now_ms=2, current_context=changed)


def test_raw_wire_budget_and_uint64_limits() -> None:
    import base64

    page = json.loads(MESSAGES[1])
    with pytest.raises(ContentError):
        encode_message(
            {
                **page,
                "total_bytes": 20_000,
                "data": base64.urlsafe_b64encode(b"x" * 12_288).decode(),
            }
        )
    for value in ["0", "01", "18446744073709551616", "1.0", " 1"]:
        with pytest.raises(ContentError):
            validate_context({**CONTEXT, "runtime_epoch": value})
    # Long integers are rejected without recursive parsing/coercion or echoing values.
    with pytest.raises(ContentError):
        decode_message(
            MESSAGES[0].replace(b'"protocol_version":1', b'"protocol_version":' + b"9" * 5000)
        )


@pytest.mark.parametrize("tail", ["\n", "\r", "\u2028", "\u2029"])
def test_no_trailing_line_terminators(tail: str) -> None:
    for key, value in CONTEXT.items():
        if type(value) is str:
            with pytest.raises(ContentError):
                context_bytes({**CONTEXT, key: value + tail})
    with pytest.raises(ContentError):
        selector_commitment(VECTOR["selector"] + tail)
    with pytest.raises(ContentError):
        application_aad(CONTEXT, "8" * 64 + tail, "PATCH_PAGE", 0)
    for raw in MESSAGES:
        message = json.loads(raw)
        for key, value in message.items():
            if type(value) is str:
                with pytest.raises(ContentError):
                    encode_message({**message, key: value + tail})


def test_no_aad_kind_coercion() -> None:
    class StringSubclass(str):
        pass

    for kind in [["PATCH_PAGE"], StringSubclass("PATCH_PAGE"), 1, True, None]:
        with pytest.raises(ContentError):
            application_aad(CONTEXT, "8" * 64, kind, 0)  # type: ignore[arg-type]


def test_no_production_composition_or_activation() -> None:
    root = Path(__file__).parents[2]
    for directory in ["apps/api", "apps/worker", "packages/agentbox-runtime"]:
        for path in (root / directory).rglob("*.py"):
            assert "a3_content" not in path.read_text()
    for path in (root / "apps/web/src").rglob("*"):
        if path.suffix not in {".ts", ".tsx"} or "content" in path.parts:
            continue
        assert "a3Content" not in path.read_text()


def test_profile_type_check_precedes_object_equality() -> None:
    class UntrustedScalar:
        def __eq__(self, other: object) -> bool:
            raise AssertionError("scalar comparison must not run")

    with pytest.raises(ContentError):
        validate_context({**CONTEXT, "protocol_id": UntrustedScalar()})
    with pytest.raises(ContentError):
        encode_message({**json.loads(MESSAGES[0]), "protocol_id": UntrustedScalar()})
