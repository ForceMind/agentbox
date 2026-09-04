from __future__ import annotations

import array
import fcntl
import json
import os
import socket
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

import pytest
from agentbox_runtime.waw_process_protocol import (
    LAUNCH_FD_COUNT,
    LAUNCH_FD_ROLE_BITMAP,
    LAUNCH_FD_ROLES,
    LAUNCH_SCHEMA,
    LAUNCH_TYPE,
    MAX_UINT64,
    LaunchFDRole,
    LaunchGeometry,
    ReceivedLaunchDescriptors,
    WAWLaunchDescriptor,
    WAWProcessProtocolError,
    WBRMessage,
    WBRMessageType,
    WBRResizeStateMachine,
    decode_launch_descriptor,
    decode_wbr_message,
    encode_launch_descriptor,
    encode_wbr_ack,
    encode_wbr_message,
    receive_launch_descriptor,
    validate_launch_ancillary,
    validate_launch_fd_role,
)


def _launch(**changes: object) -> WAWLaunchDescriptor:
    values: dict[str, object] = {
        "agent": "claude",
        "workspace_hash": "1" * 64,
        "generation": "7",
        "profile_digest": "2" * 64,
        "initial_geometry": LaunchGeometry(columns=80, rows=24),
        "runtime_uid": 1001,
        "runtime_gid": 1002,
    }
    values.update(changes)
    return WAWLaunchDescriptor(**values)  # type: ignore[arg-type]


def _launch_raw() -> bytes:
    return encode_launch_descriptor(_launch())


def _rights_payload(descriptors: list[int]) -> bytes:
    values = array.array("i", descriptors)
    return values.tobytes()


@contextmanager
def _open_descriptors(count: int = LAUNCH_FD_COUNT) -> Iterator[tuple[list[int], list[int]]]:
    reads: list[int] = []
    writes: list[int] = []
    try:
        for _ in range(count):
            read_fd, write_fd = os.pipe()
            reads.append(read_fd)
            writes.append(write_fd)
        yield reads, writes
    finally:
        for descriptor in reads + writes:
            with suppress(OSError):
                os.close(descriptor)


def _ack(request_raw: bytes, **changes: object) -> bytes:
    request = decode_wbr_message(request_raw)
    values: dict[str, object] = {
        "message_type": WBRMessageType.ACK,
        "sequence": request.sequence,
        "generation": request.generation,
        "columns": request.columns,
        "rows": request.rows,
    }
    values.update(changes)
    return encode_wbr_message(WBRMessage(**values))  # type: ignore[arg-type]


def _accept_synthetic_descriptor(_role: LaunchFDRole, _descriptor: int) -> None:
    pass


def test_launch_descriptor_has_exact_canonical_closed_schema() -> None:
    raw = _launch_raw()
    assert raw == (
        b'{"agent":"claude","fd_role_bitmap":127,"generation":"7",'
        b'"initial_geometry":{"columns":80,"rows":24},'
        b'"profile_digest":"' + b"2" * 64 + b'","runtime_gid":1002,"runtime_uid":1001,'
        b'"schema":"agentbox-waw-launch-v1","type":"interactive",'
        b'"workspace_hash":"' + b"1" * 64 + b'"}'
    )
    assert decode_launch_descriptor(raw) == _launch()
    assert LAUNCH_SCHEMA.encode() in raw and LAUNCH_TYPE.encode() in raw
    for forbidden in (b"argv", b"secret", b"credential", b"browser", b"ticket", b"path"):
        assert forbidden not in raw.lower()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw + b"\n",
        lambda raw: raw.replace(b'{"agent":', b'{"unknown":1,"agent":'),
        lambda raw: raw.replace(b'{"agent":"claude"', b'{"agent":"claude","agent":"claude"'),
        lambda raw: raw.replace(b'{"columns":80', b'{"columns":80,"columns":80'),
        lambda raw: raw.replace(b'{"agent":', b'{ "agent":'),
        lambda raw: b"\xff" + raw,
        lambda _raw: b"",
    ],
)
def test_launch_decoder_rejects_noncanonical_unknown_duplicate_and_invalid_bytes(
    mutate: Callable[[bytes], bytes],
) -> None:
    with pytest.raises(WAWProcessProtocolError):
        decode_launch_descriptor(mutate(_launch_raw()))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("agent", "shell"),
        ("workspace_hash", "0" * 64),
        ("workspace_hash", "A" * 64),
        ("generation", "0"),
        ("generation", "01"),
        ("generation", str(2**64)),
        ("profile_digest", "x" * 64),
        ("runtime_uid", 0),
        ("runtime_uid", True),
        ("runtime_gid", 2**32 - 1),
        ("fd_role_bitmap", 126),
        ("schema", "waw-launch-v1"),
        ("type", "login"),
    ],
)
def test_launch_descriptor_rejects_values_outside_closed_contract(
    field: str, value: object
) -> None:
    with pytest.raises(WAWProcessProtocolError):
        _launch(**{field: value})


@pytest.mark.parametrize(("columns", "rows"), [(7, 24), (241, 24), (80, 0), (80, 201)])
def test_launch_geometry_rejects_out_of_range_without_clamping(columns: int, rows: int) -> None:
    with pytest.raises(WAWProcessProtocolError):
        LaunchGeometry(columns=columns, rows=rows)


def test_fd_roles_and_bitmap_are_exact_and_ordered() -> None:
    assert LAUNCH_FD_COUNT == 7
    assert LAUNCH_FD_ROLE_BITMAP == 0x7F
    assert LAUNCH_FD_ROLES == (
        LaunchFDRole.PROJECT_DIRECTORY,
        LaunchFDRole.SELECTED_HOME_DIRECTORY,
        LaunchFDRole.TEMP_DIRECTORY,
        LaunchFDRole.BRIDGE_EXECUTABLE,
        LaunchFDRole.VENDOR_EXECUTABLE,
        LaunchFDRole.POLICY_DIRECTORY,
        LaunchFDRole.WBR_ENDPOINT,
    )


def test_valid_ancillary_maps_roles_sets_cloexec_and_closes_unreleased_descriptors() -> None:
    with _open_descriptors() as (reads, _writes):
        for descriptor in reads:
            fcntl.fcntl(descriptor, fcntl.F_SETFD, 0)
        seen: list[tuple[LaunchFDRole, int]] = []
        owned = validate_launch_ancillary(
            [(socket.SOL_SOCKET, socket.SCM_RIGHTS, _rights_payload(reads))],
            0,
            fd_role_bitmap=LAUNCH_FD_ROLE_BITMAP,
            descriptor_validator=lambda role, descriptor: seen.append((role, descriptor)),
        )
        assert seen == list(zip(LAUNCH_FD_ROLES, reads, strict=True))
        assert all(fcntl.fcntl(fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC for fd in reads)
        released = owned.release(LaunchFDRole.WBR_ENDPOINT)
        owned.close()
        owned.close()
        assert fcntl.fcntl(released, fcntl.F_GETFD) & fcntl.FD_CLOEXEC
        for descriptor in reads[:-1]:
            with pytest.raises(OSError):
                os.fstat(descriptor)


@pytest.mark.parametrize("role", [0, False, True, 6])
def test_received_descriptors_reject_int_and_bool_role_aliases(role: object) -> None:
    closed: list[int] = []
    owned = ReceivedLaunchDescriptors(
        list(range(10, 10 + LAUNCH_FD_COUNT)), close_descriptor=closed.append
    )
    with pytest.raises(WAWProcessProtocolError, match="role"):
        owned.fileno(role)  # type: ignore[arg-type]
    with pytest.raises(WAWProcessProtocolError, match="role"):
        owned.release(role)  # type: ignore[arg-type]
    owned.close()
    assert closed == list(range(10, 10 + LAUNCH_FD_COUNT))


@pytest.mark.parametrize(
    ("ancillary", "flags", "bitmap", "expected_closed"),
    [
        ([], 0, LAUNCH_FD_ROLE_BITMAP, []),
        (
            [(socket.SOL_SOCKET, socket.SCM_RIGHTS, _rights_payload(list(range(10, 16))))],
            0,
            LAUNCH_FD_ROLE_BITMAP,
            list(range(10, 16)),
        ),
        (
            [(socket.SOL_SOCKET, socket.SCM_RIGHTS, _rights_payload(list(range(10, 18))))],
            0,
            LAUNCH_FD_ROLE_BITMAP,
            list(range(10, 18)),
        ),
        (
            [(socket.SOL_SOCKET, socket.SCM_RIGHTS, _rights_payload(list(range(10, 17))))],
            socket.MSG_TRUNC,
            LAUNCH_FD_ROLE_BITMAP,
            list(range(10, 17)),
        ),
        (
            [(socket.SOL_SOCKET, socket.SCM_RIGHTS, _rights_payload(list(range(10, 17))))],
            socket.MSG_CTRUNC,
            LAUNCH_FD_ROLE_BITMAP,
            list(range(10, 17)),
        ),
        (
            [(socket.SOL_SOCKET, socket.SCM_RIGHTS, _rights_payload(list(range(10, 17))))],
            0,
            0x3F,
            list(range(10, 17)),
        ),
        (
            [
                (socket.SOL_SOCKET, socket.SCM_RIGHTS, _rights_payload(list(range(10, 17)))),
                (999, 999, b"unknown"),
            ],
            0,
            LAUNCH_FD_ROLE_BITMAP,
            list(range(10, 17)),
        ),
        (
            [(socket.SOL_SOCKET, socket.SCM_RIGHTS, _rights_payload([10] * 7))],
            0,
            LAUNCH_FD_ROLE_BITMAP,
            [10],
        ),
    ],
)
def test_ancillary_rejection_closes_every_discoverable_rights_fd(
    ancillary: list[tuple[int, int, bytes]],
    flags: int,
    bitmap: int,
    expected_closed: list[int],
) -> None:
    closed: list[int] = []
    with pytest.raises(WAWProcessProtocolError):
        validate_launch_ancillary(
            ancillary,
            flags,
            fd_role_bitmap=bitmap,
            close_descriptor=closed.append,
        )
    assert closed == expected_closed


def test_misaligned_rights_payload_still_closes_every_discoverable_descriptor() -> None:
    payload = _rights_payload(list(range(10, 17))) + b"x"
    closed: list[int] = []
    with pytest.raises(WAWProcessProtocolError):
        validate_launch_ancillary(
            [(socket.SOL_SOCKET, socket.SCM_RIGHTS, payload)],
            0,
            fd_role_bitmap=LAUNCH_FD_ROLE_BITMAP,
            close_descriptor=closed.append,
        )
    assert closed == list(range(10, 17))


def test_role_validator_failure_closes_all_descriptors() -> None:
    with _open_descriptors() as (reads, _writes):
        closed: list[int] = []

        def reject_vendor(role: LaunchFDRole, _descriptor: int) -> None:
            if role is LaunchFDRole.VENDOR_EXECUTABLE:
                raise RuntimeError("wrong object")

        with pytest.raises(WAWProcessProtocolError, match="role validation"):
            validate_launch_ancillary(
                [(socket.SOL_SOCKET, socket.SCM_RIGHTS, _rights_payload(reads))],
                0,
                fd_role_bitmap=LAUNCH_FD_ROLE_BITMAP,
                descriptor_validator=reject_vendor,
                close_descriptor=closed.append,
            )
        assert closed == reads


def test_received_descriptor_cleanup_attempts_every_role_after_close_error() -> None:
    with _open_descriptors() as (reads, _writes):
        attempted: list[int] = []

        def close_with_failure(descriptor: int) -> None:
            attempted.append(descriptor)
            if descriptor == reads[0]:
                raise OSError("injected")

        owned = validate_launch_ancillary(
            [(socket.SOL_SOCKET, socket.SCM_RIGHTS, _rights_payload(reads))],
            0,
            fd_role_bitmap=LAUNCH_FD_ROLE_BITMAP,
            descriptor_validator=_accept_synthetic_descriptor,
            close_descriptor=close_with_failure,
        )
        with pytest.raises(WAWProcessProtocolError, match="cleanup failed"):
            owned.close()
        assert attempted == reads
        assert owned.closed


@pytest.mark.skipif(not hasattr(socket.socket, "sendmsg"), reason="sendmsg is unavailable")
def test_receive_launch_descriptor_uses_one_record_and_owns_received_fds() -> None:
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    with left, right, _open_descriptors() as (reads, _writes):
        left.sendmsg(
            [_launch_raw()],
            [(socket.SOL_SOCKET, socket.SCM_RIGHTS, _rights_payload(reads))],
        )
        descriptor, owned = receive_launch_descriptor(
            right, descriptor_validator=_accept_synthetic_descriptor
        )
        assert descriptor == _launch()
        received = [owned.fileno(role) for role in LAUNCH_FD_ROLES]
        assert len(set(received)) == 7
        assert not set(received) & set(reads)
        owned.close()
        for descriptor_fd in received:
            with pytest.raises(OSError):
                os.fstat(descriptor_fd)


@pytest.mark.skipif(not hasattr(socket.socket, "sendmsg"), reason="sendmsg is unavailable")
def test_receive_invalid_payload_closes_received_fds() -> None:
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    with left, right, _open_descriptors() as (reads, _writes):
        left.sendmsg(
            [_launch_raw() + b"\n"],
            [(socket.SOL_SOCKET, socket.SCM_RIGHTS, _rights_payload(reads))],
        )
        before = set(os.listdir("/dev/fd"))
        with pytest.raises(WAWProcessProtocolError, match="canonical"):
            receive_launch_descriptor(right, descriptor_validator=_accept_synthetic_descriptor)
        after = set(os.listdir("/dev/fd"))
        assert after == before


def test_default_role_validation_rejects_wrong_object_and_closes_every_fd() -> None:
    with _open_descriptors() as (reads, _writes):
        with pytest.raises(WAWProcessProtocolError, match="role validation"):
            validate_launch_ancillary(
                [(socket.SOL_SOCKET, socket.SCM_RIGHTS, _rights_payload(reads))],
                0,
                fd_role_bitmap=LAUNCH_FD_ROLE_BITMAP,
            )
        for descriptor in reads:
            with pytest.raises(OSError):
                os.fstat(descriptor)


@pytest.mark.skipif(
    not hasattr(os, "O_PATH") or not hasattr(socket, "SOCK_SEQPACKET"),
    reason="native launch descriptor roles require Linux O_PATH and Unix SOCK_SEQPACKET",
)
def test_native_linux_role_validator_accepts_exact_objects(tmp_path: Path) -> None:
    directories = [tmp_path / name for name in ("project", "home", "tmp", "policy")]
    for directory in directories:
        directory.mkdir()
    executables = [tmp_path / name for name in ("bridge", "vendor")]
    for executable in executables:
        executable.write_bytes(b"synthetic executable fixture")
        executable.chmod(0o755)
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    descriptors = [
        os.open(directories[0], os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC),
        os.open(directories[1], os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC),
        os.open(directories[2], os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC),
        os.open(executables[0], os.O_RDONLY | os.O_CLOEXEC),
        os.open(executables[1], os.O_RDONLY | os.O_CLOEXEC),
        os.open(directories[3], os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC),
        os.dup(right.fileno()),
    ]
    try:
        for role, descriptor in zip(LAUNCH_FD_ROLES, descriptors, strict=True):
            validate_launch_fd_role(role, descriptor)
    finally:
        for descriptor in descriptors:
            with suppress(OSError):
                os.close(descriptor)
        left.close()
        right.close()


def test_wbr_exact_network_order_resize_and_ack_vectors() -> None:
    resize = WBRMessage(WBRMessageType.RESIZE, 0x0102030405060708, 9, 80, 24)
    raw = encode_wbr_message(resize)
    assert len(raw) == 64
    assert raw[:4] == b"WBR1"
    assert raw[4:8] == bytes.fromhex("01010000")
    assert raw[8:16] == bytes.fromhex("0102030405060708")
    assert raw[16:24] == bytes.fromhex("0000000000000009")
    assert raw[24:29] == bytes.fromhex("0050001800")
    assert raw[29:] == b"\x00" * 35
    assert decode_wbr_message(raw) == resize

    ack = encode_wbr_ack(resize)
    assert ack[5] == 2 and ack[28] == 1 and ack[29:] == b"\x00" * 35
    assert decode_wbr_message(ack) == WBRMessage(WBRMessageType.ACK, resize.sequence, 9, 80, 24)


@pytest.mark.parametrize(
    ("offset", "value"),
    [
        (0, 0),
        (4, 2),
        (5, 3),
        (6, 1),
        (7, 1),
        (15, 0),
        (23, 0),
        (25, 7),
        (27, 0),
        (28, 1),
        (29, 1),
        (63, 1),
    ],
)
def test_wbr_decoder_rejects_identity_range_flags_marker_and_reserved_mutations(
    offset: int, value: int
) -> None:
    raw = bytearray(encode_wbr_message(WBRMessage(WBRMessageType.RESIZE, 1, 1, 80, 24)))
    raw[offset] = value
    with pytest.raises(WAWProcessProtocolError):
        decode_wbr_message(bytes(raw))


@pytest.mark.parametrize("raw", [b"", b"x" * 63, b"x" * 65])
def test_wbr_decoder_rejects_non_exact_size(raw: bytes) -> None:
    with pytest.raises(WAWProcessProtocolError, match="size"):
        decode_wbr_message(raw)


def test_resize_state_machine_accepts_exact_ack_then_advances_without_reuse() -> None:
    closed: list[str] = []
    state = WBRResizeStateMachine(generation=7, close_endpoint=lambda: closed.append("closed"))
    first = state.begin_resize(80, 24, now=10.0)
    assert decode_wbr_message(first).sequence == 1
    assert state.accept_ack(_ack(first), now=10.999).sequence == 1
    second = state.begin_resize(100, 40, now=11.0)
    assert decode_wbr_message(second).sequence == 2
    assert state.accept_ack(_ack(second), now=11.1).sequence == 2
    assert not state.closed and closed == []


def test_resize_state_machine_closes_at_exact_one_second_deadline() -> None:
    closed: list[str] = []
    state = WBRResizeStateMachine(generation=1, close_endpoint=lambda: closed.append("closed"))
    state.begin_resize(80, 24, now=5.0)
    with pytest.raises(WAWProcessProtocolError, match="deadline"):
        state.check_deadline(now=6.0)
    assert state.closed and closed == ["closed"]


def test_resize_state_machine_rejects_second_outstanding_and_closes() -> None:
    state = WBRResizeStateMachine(generation=1)
    state.begin_resize(80, 24, now=1.0)
    with pytest.raises(WAWProcessProtocolError, match="outstanding"):
        state.begin_resize(81, 25, now=1.1)
    assert state.closed


def test_resize_state_machine_rejects_replayed_ack_and_closes_once() -> None:
    closed: list[str] = []
    state = WBRResizeStateMachine(generation=1, close_endpoint=lambda: closed.append("closed"))
    request = state.begin_resize(80, 24, now=1.0)
    acknowledgment = _ack(request)
    state.accept_ack(acknowledgment, now=1.1)
    with pytest.raises(WAWProcessProtocolError, match="replayed"):
        state.accept_ack(acknowledgment, now=1.2)
    state.close()
    assert state.closed and closed == ["closed"]


@pytest.mark.parametrize(
    "changes",
    [
        {"message_type": WBRMessageType.RESIZE},
        {"sequence": 2},
        {"generation": 2},
        {"columns": 81},
        {"rows": 25},
    ],
)
def test_resize_state_machine_closes_on_nonmatching_ack(changes: dict[str, object]) -> None:
    state = WBRResizeStateMachine(generation=1)
    request = state.begin_resize(80, 24, now=1.0)
    with pytest.raises(WAWProcessProtocolError, match="ACK"):
        state.accept_ack(_ack(request, **changes), now=1.1)
    assert state.closed


def test_resize_state_machine_closes_before_sequence_wrap() -> None:
    state = WBRResizeStateMachine(generation=1, last_sequence=MAX_UINT64)
    with pytest.raises(WAWProcessProtocolError, match="wrap"):
        state.begin_resize(80, 24, now=1.0)
    assert state.closed


@pytest.mark.parametrize("now", [float("nan"), float("inf"), -1.0])
def test_resize_state_machine_closes_on_invalid_clock(now: float) -> None:
    state = WBRResizeStateMachine(generation=1)
    with pytest.raises(WAWProcessProtocolError, match="clock"):
        state.begin_resize(80, 24, now=now)
    assert state.closed


def test_resize_state_machine_closes_when_explicit_clock_moves_backward() -> None:
    closed: list[str] = []
    state = WBRResizeStateMachine(generation=1, close_endpoint=lambda: closed.append("closed"))
    request = state.begin_resize(80, 24, now=10.0)
    state.accept_ack(_ack(request), now=10.5)
    with pytest.raises(WAWProcessProtocolError, match="backward"):
        state.begin_resize(81, 25, now=10.499)
    assert state.closed and closed == ["closed"]


def test_resize_state_machine_closes_when_injected_clock_moves_backward() -> None:
    values = iter((5.0, 4.999))
    state = WBRResizeStateMachine(generation=1, clock=lambda: next(values))
    request = state.begin_resize(80, 24)
    with pytest.raises(WAWProcessProtocolError, match="backward"):
        state.accept_ack(_ack(request))
    assert state.closed


def test_native_header_matches_python_wire_constants() -> None:
    header = (
        Path(__file__).parents[2] / "native" / "waw" / "include" / "agentbox_waw_protocol.h"
    ).read_text()
    assert '#define AGENTBOX_WAW_LAUNCH_SCHEMA "agentbox-waw-launch-v1"' in header
    assert '#define AGENTBOX_WAW_LAUNCH_TYPE "interactive"' in header
    assert "AGENTBOX_WAW_FD_COUNT = 7" in header
    assert "AGENTBOX_WAW_FD_ROLE_BITMAP UINT32_C(0x7f)" in header
    assert "AGENTBOX_WBR_FRAME_BYTES UINT32_C(64)" in header
    assert "AGENTBOX_WBR_ACK_DEADLINE_MS UINT32_C(1000)" in header
    for offset, name in (
        (0, "MAGIC"),
        (4, "VERSION"),
        (5, "MESSAGE_TYPE"),
        (6, "FLAGS"),
        (8, "SEQUENCE"),
        (16, "GENERATION"),
        (24, "COLUMNS"),
        (26, "ROWS"),
        (28, "REQUEST_OR_ACK"),
        (29, "RESERVED"),
    ):
        assert f"AGENTBOX_WBR_OFFSET_{name} UINT32_C({offset})" in header


def test_raw_launch_record_cannot_add_browser_or_secret_data() -> None:
    value: dict[str, Any] = json.loads(_launch_raw())
    value["browser_ticket"] = "secret"
    with pytest.raises(WAWProcessProtocolError, match="fields"):
        decode_launch_descriptor(json.dumps(value, separators=(",", ":"), sort_keys=True).encode())
