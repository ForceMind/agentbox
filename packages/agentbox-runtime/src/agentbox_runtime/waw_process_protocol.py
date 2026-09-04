"""Closed software codecs for the fixed WAW process boundary.

This module does not discover executables, build argument vectors, read secrets,
or start processes.  It validates the canonical launch record, the ordered
``SCM_RIGHTS`` descriptor set, and the fixed-size WBR resize protocol used by a
future native launcher.
"""

from __future__ import annotations

import array
import fcntl
import json
import math
import os
import re
import socket
import stat
import struct
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, NoReturn, Protocol, Self

import rfc8785

LAUNCH_SCHEMA = "agentbox-waw-launch-v1"
LAUNCH_TYPE = "interactive"
MAX_LAUNCH_DESCRIPTOR_BYTES = 2048

MAX_UINT64 = 2**64 - 1
MAX_UID_GID = 2**32 - 2
MIN_COLUMNS = 8
MAX_COLUMNS = 240
MIN_ROWS = 1
MAX_ROWS = 200

WBR_MAGIC = b"WBR1"
WBR_VERSION = 1
WBR_FRAME_BYTES = 64
WBR_ACK_DEADLINE_SECONDS = 1.0

_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_POSITIVE_DECIMAL = re.compile(r"\A[1-9][0-9]{0,19}\Z")
_LAUNCH_FIELDS = frozenset(
    {
        "agent",
        "fd_role_bitmap",
        "generation",
        "initial_geometry",
        "profile_digest",
        "runtime_gid",
        "runtime_uid",
        "schema",
        "type",
        "workspace_hash",
    }
)
_GEOMETRY_FIELDS = frozenset({"columns", "rows"})
_WBR = struct.Struct("!4sBBHQQHHB35s")
_FD_ARRAY_ITEM_SIZE = array.array("i").itemsize
_TRUNCATION_FLAGS = socket.MSG_TRUNC | socket.MSG_CTRUNC


class WAWProcessProtocolError(ValueError):
    """The launch or WBR process-boundary protocol is invalid."""


class LaunchFDRole(IntEnum):
    """The exact order of descriptors carried by one launch record."""

    PROJECT_DIRECTORY = 0
    SELECTED_HOME_DIRECTORY = 1
    TEMP_DIRECTORY = 2
    BRIDGE_EXECUTABLE = 3
    VENDOR_EXECUTABLE = 4
    POLICY_DIRECTORY = 5
    WBR_ENDPOINT = 6


LAUNCH_FD_ROLES = tuple(LaunchFDRole)
LAUNCH_FD_COUNT = len(LAUNCH_FD_ROLES)
LAUNCH_FD_ROLE_BITMAP = sum(1 << role.value for role in LAUNCH_FD_ROLES)


class WBRMessageType(IntEnum):
    RESIZE = 1
    ACK = 2


@dataclass(frozen=True)
class LaunchGeometry:
    columns: int
    rows: int

    def __post_init__(self) -> None:
        _validate_geometry(self.columns, self.rows)


@dataclass(frozen=True)
class WAWLaunchDescriptor:
    agent: str
    workspace_hash: str
    generation: str
    profile_digest: str
    initial_geometry: LaunchGeometry
    runtime_uid: int
    runtime_gid: int
    fd_role_bitmap: int = LAUNCH_FD_ROLE_BITMAP
    schema: str = LAUNCH_SCHEMA
    type: str = LAUNCH_TYPE

    def __post_init__(self) -> None:
        _validate_launch_descriptor(self)


@dataclass(frozen=True)
class WBRMessage:
    message_type: WBRMessageType
    sequence: int
    generation: int
    columns: int
    rows: int
    flags: int = 0

    def __post_init__(self) -> None:
        _validate_wbr_message(self)


DescriptorValidator = Callable[[LaunchFDRole, int], None]
CloseDescriptor = Callable[[int], None]
CloseEndpoint = Callable[[], None]
Clock = Callable[[], float]


class RecvmsgSocket(Protocol):
    def recvmsg(
        self, buffer_size: int, ancillary_buffer_size: int, flags: int = 0
    ) -> tuple[bytes, list[tuple[int, int, bytes]], int, Any]: ...


class ReceivedLaunchDescriptors:
    """Own a validated launch descriptor set until each role is released.

    ``close`` is the fail-closed cleanup seam.  A caller may transfer one role
    at a time with ``release``; every descriptor still owned by this object is
    closed on context exit.
    """

    def __init__(
        self,
        descriptors: Sequence[int],
        *,
        close_descriptor: CloseDescriptor = os.close,
    ) -> None:
        if len(descriptors) != LAUNCH_FD_COUNT:
            raise WAWProcessProtocolError("launch descriptor count is invalid")
        self._descriptors = {
            role: descriptor for role, descriptor in zip(LAUNCH_FD_ROLES, descriptors, strict=True)
        }
        self._close_descriptor = close_descriptor
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def fileno(self, role: LaunchFDRole) -> int:
        if type(role) is not LaunchFDRole or self._closed or role not in self._descriptors:
            raise WAWProcessProtocolError("launch descriptor role is not owned")
        return self._descriptors[role]

    def release(self, role: LaunchFDRole) -> int:
        if type(role) is not LaunchFDRole or self._closed or role not in self._descriptors:
            raise WAWProcessProtocolError("launch descriptor role is not owned")
        return self._descriptors.pop(role)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        descriptors = tuple(self._descriptors.values())
        self._descriptors.clear()
        first_error: BaseException | None = None
        for descriptor in descriptors:
            try:
                self._close_descriptor(descriptor)
            except BaseException as exc:  # every remaining descriptor still gets a close attempt
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise WAWProcessProtocolError("launch descriptor cleanup failed") from first_error

    def __enter__(self) -> Self:
        if self._closed:
            raise WAWProcessProtocolError("launch descriptor set is closed")
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def encode_launch_descriptor(descriptor: WAWLaunchDescriptor) -> bytes:
    """Encode one canonical closed launch record.

    The record has no command, argv, environment, path, secret, ticket, browser,
    or terminal-payload field.  Unknown data cannot be represented by this API.
    """

    _validate_launch_descriptor(descriptor)
    value: dict[str, Any] = {
        "agent": descriptor.agent,
        "fd_role_bitmap": descriptor.fd_role_bitmap,
        "generation": descriptor.generation,
        "initial_geometry": {
            "columns": descriptor.initial_geometry.columns,
            "rows": descriptor.initial_geometry.rows,
        },
        "profile_digest": descriptor.profile_digest,
        "runtime_gid": descriptor.runtime_gid,
        "runtime_uid": descriptor.runtime_uid,
        "schema": descriptor.schema,
        "type": descriptor.type,
        "workspace_hash": descriptor.workspace_hash,
    }
    try:
        encoded = rfc8785.dumps(value)
    except (rfc8785.CanonicalizationError, TypeError, ValueError) as exc:
        raise WAWProcessProtocolError("launch descriptor cannot be canonicalized") from exc
    if not isinstance(encoded, bytes) or not encoded or len(encoded) > MAX_LAUNCH_DESCRIPTOR_BYTES:
        raise WAWProcessProtocolError("launch descriptor is too large")
    return encoded


def decode_launch_descriptor(raw: bytes) -> WAWLaunchDescriptor:
    """Decode only an exact canonical launch record."""

    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_LAUNCH_DESCRIPTOR_BYTES:
        raise WAWProcessProtocolError("launch descriptor size is invalid")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise WAWProcessProtocolError("launch descriptor JSON is invalid") from exc
    if not isinstance(value, dict) or set(value) != _LAUNCH_FIELDS:
        raise WAWProcessProtocolError("launch descriptor fields are invalid")
    geometry = value["initial_geometry"]
    if not isinstance(geometry, dict) or set(geometry) != _GEOMETRY_FIELDS:
        raise WAWProcessProtocolError("launch geometry fields are invalid")
    try:
        canonical = rfc8785.dumps(value)
    except (rfc8785.CanonicalizationError, TypeError, ValueError) as exc:
        raise WAWProcessProtocolError("launch descriptor cannot be canonicalized") from exc
    if canonical != raw:
        raise WAWProcessProtocolError("launch descriptor is not canonical")
    try:
        return WAWLaunchDescriptor(
            agent=value["agent"],
            workspace_hash=value["workspace_hash"],
            generation=value["generation"],
            profile_digest=value["profile_digest"],
            initial_geometry=LaunchGeometry(
                columns=geometry["columns"],
                rows=geometry["rows"],
            ),
            runtime_uid=value["runtime_uid"],
            runtime_gid=value["runtime_gid"],
            fd_role_bitmap=value["fd_role_bitmap"],
            schema=value["schema"],
            type=value["type"],
        )
    except (TypeError, WAWProcessProtocolError) as exc:
        raise WAWProcessProtocolError("launch descriptor value is invalid") from exc


def validate_launch_ancillary(
    ancillary: Sequence[tuple[int, int, bytes]],
    message_flags: int,
    *,
    fd_role_bitmap: int,
    descriptor_validator: DescriptorValidator | None = None,
    close_descriptor: CloseDescriptor = os.close,
) -> ReceivedLaunchDescriptors:
    """Validate and take ownership of the exact ordered ``SCM_RIGHTS`` set.

    Every received rights descriptor that can be decoded is closed if any
    ancillary, bitmap, count, duplicate, CLOEXEC, or role-specific check fails.
    The caller-provided validator is a software seam for platform-specific
    ``fstat``/``O_PATH`` checks; this module does not use any descriptor to run a
    process.
    """

    discovered: list[int] = []
    rights_records: list[bytes] = []
    unknown_record = False
    for level, control_type, payload in ancillary:
        if level == socket.SOL_SOCKET and control_type == socket.SCM_RIGHTS:
            rights_records.append(payload)
            discovered.extend(_decode_discoverable_fds(payload))
        else:
            unknown_record = True

    def reject(message: str, cause: BaseException | None = None) -> NoReturn:
        _close_unique(discovered, close_descriptor)
        if cause is None:
            raise WAWProcessProtocolError(message)
        raise WAWProcessProtocolError(message) from cause

    if message_flags & _TRUNCATION_FLAGS:
        reject("launch message is truncated")
    if unknown_record or len(ancillary) != 1 or len(rights_records) != 1:
        reject("launch ancillary records are invalid")
    payload = rights_records[0]
    if len(payload) != LAUNCH_FD_COUNT * _FD_ARRAY_ITEM_SIZE:
        reject("launch SCM_RIGHTS size is invalid")
    if fd_role_bitmap != LAUNCH_FD_ROLE_BITMAP:
        reject("launch descriptor bitmap is invalid")
    if len(discovered) != LAUNCH_FD_COUNT or len(set(discovered)) != LAUNCH_FD_COUNT:
        reject("launch descriptors are missing, extra, or duplicated")
    if any(descriptor < 0 for descriptor in discovered):
        reject("launch descriptor number is invalid")

    try:
        for role, descriptor in zip(LAUNCH_FD_ROLES, discovered, strict=True):
            current_flags = fcntl.fcntl(descriptor, fcntl.F_GETFD)
            if not current_flags & fcntl.FD_CLOEXEC:
                fcntl.fcntl(descriptor, fcntl.F_SETFD, current_flags | fcntl.FD_CLOEXEC)
            validator = descriptor_validator or validate_launch_fd_role
            validator(role, descriptor)
    except BaseException as exc:
        reject("launch descriptor role validation failed", exc)

    return ReceivedLaunchDescriptors(discovered, close_descriptor=close_descriptor)


def receive_launch_descriptor(
    connection: RecvmsgSocket,
    *,
    descriptor_validator: DescriptorValidator | None = None,
    close_descriptor: CloseDescriptor = os.close,
) -> tuple[WAWLaunchDescriptor, ReceivedLaunchDescriptors]:
    """Receive exactly one bounded launch record and its seven descriptors."""

    receive_flags = getattr(socket, "MSG_CMSG_CLOEXEC", 0)
    raw, ancillary, message_flags, _address = connection.recvmsg(
        MAX_LAUNCH_DESCRIPTOR_BYTES + 1,
        socket.CMSG_SPACE(LAUNCH_FD_COUNT * _FD_ARRAY_ITEM_SIZE),
        receive_flags,
    )
    descriptors = validate_launch_ancillary(
        ancillary,
        message_flags,
        fd_role_bitmap=LAUNCH_FD_ROLE_BITMAP,
        descriptor_validator=descriptor_validator,
        close_descriptor=close_descriptor,
    )
    try:
        descriptor = decode_launch_descriptor(raw)
        if descriptor.fd_role_bitmap != LAUNCH_FD_ROLE_BITMAP:
            raise WAWProcessProtocolError("launch descriptor bitmap is invalid")
        return descriptor, descriptors
    except BaseException:
        descriptors.close()
        raise


def encode_wbr_message(message: WBRMessage) -> bytes:
    """Encode an exact 64-byte network-order WBR RESIZE or ACK message."""

    _validate_wbr_message(message)
    request_or_ack = 0 if message.message_type is WBRMessageType.RESIZE else 1
    return _WBR.pack(
        WBR_MAGIC,
        WBR_VERSION,
        int(message.message_type),
        message.flags,
        message.sequence,
        message.generation,
        message.columns,
        message.rows,
        request_or_ack,
        b"\x00" * 35,
    )


def decode_wbr_message(raw: bytes) -> WBRMessage:
    """Decode an exact WBR message, rejecting all nonzero reserved bits/bytes."""

    if not isinstance(raw, bytes) or len(raw) != WBR_FRAME_BYTES:
        raise WAWProcessProtocolError("WBR message size is invalid")
    magic, version, message_type, flags, sequence, generation, columns, rows, marker, reserved = (
        _WBR.unpack(raw)
    )
    if magic != WBR_MAGIC or version != WBR_VERSION:
        raise WAWProcessProtocolError("WBR identity is invalid")
    try:
        typed_message = WBRMessageType(message_type)
    except ValueError as exc:
        raise WAWProcessProtocolError("WBR message type is invalid") from exc
    expected_marker = 0 if typed_message is WBRMessageType.RESIZE else 1
    if marker != expected_marker or flags != 0 or reserved != b"\x00" * 35:
        raise WAWProcessProtocolError("WBR flags or reserved bytes are invalid")
    try:
        return WBRMessage(
            message_type=typed_message,
            sequence=sequence,
            generation=generation,
            columns=columns,
            rows=rows,
            flags=flags,
        )
    except WAWProcessProtocolError as exc:
        raise WAWProcessProtocolError("WBR message value is invalid") from exc


def encode_wbr_resize(*, sequence: int, generation: int, columns: int, rows: int) -> bytes:
    return encode_wbr_message(
        WBRMessage(
            message_type=WBRMessageType.RESIZE,
            sequence=sequence,
            generation=generation,
            columns=columns,
            rows=rows,
        )
    )


def encode_wbr_ack(request: WBRMessage) -> bytes:
    if request.message_type is not WBRMessageType.RESIZE:
        raise WAWProcessProtocolError("WBR ACK source is not a RESIZE request")
    return encode_wbr_message(
        WBRMessage(
            message_type=WBRMessageType.ACK,
            sequence=request.sequence,
            generation=request.generation,
            columns=request.columns,
            rows=request.rows,
        )
    )


class WBRResizeStateMachine:
    """Track one outstanding RESIZE with a fixed one-second ACK deadline."""

    def __init__(
        self,
        *,
        generation: int,
        last_sequence: int = 0,
        clock: Clock = time.monotonic,
        close_endpoint: CloseEndpoint | None = None,
    ) -> None:
        if type(generation) is not int or not 1 <= generation <= MAX_UINT64:
            raise WAWProcessProtocolError("WBR generation is invalid")
        if type(last_sequence) is not int or not 0 <= last_sequence <= MAX_UINT64:
            raise WAWProcessProtocolError("WBR last sequence is invalid")
        self._generation = generation
        self._last_sequence = last_sequence
        self._clock = clock
        self._close_endpoint = close_endpoint
        self._outstanding: WBRMessage | None = None
        self._deadline: float | None = None
        self._clock_high_water: float | None = None
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def outstanding(self) -> WBRMessage | None:
        return self._outstanding

    @property
    def last_sequence(self) -> int:
        return self._last_sequence

    def begin_resize(self, columns: int, rows: int, *, now: float | None = None) -> bytes:
        if self._closed:
            raise WAWProcessProtocolError("WBR state machine is closed")
        current = self._time(now)
        self._expire_if_needed(current)
        if self._outstanding is not None:
            self._fail("WBR already has an outstanding RESIZE")
        if self._last_sequence == MAX_UINT64:
            self._fail("WBR sequence would wrap")
        try:
            request = WBRMessage(
                message_type=WBRMessageType.RESIZE,
                sequence=self._last_sequence + 1,
                generation=self._generation,
                columns=columns,
                rows=rows,
            )
        except WAWProcessProtocolError as exc:
            self._fail("WBR RESIZE request is invalid", exc)
        self._last_sequence = request.sequence
        self._outstanding = request
        self._deadline = current + WBR_ACK_DEADLINE_SECONDS
        return encode_wbr_message(request)

    def accept_ack(self, raw: bytes, *, now: float | None = None) -> WBRMessage:
        if self._closed:
            raise WAWProcessProtocolError("WBR state machine is closed")
        current = self._time(now)
        self._expire_if_needed(current)
        request = self._outstanding
        if request is None:
            self._fail("WBR ACK is unsolicited or replayed")
        try:
            acknowledgment = decode_wbr_message(raw)
        except WAWProcessProtocolError as exc:
            self._fail("WBR ACK is invalid", exc)
        if acknowledgment.message_type is not WBRMessageType.ACK or (
            acknowledgment.sequence,
            acknowledgment.generation,
            acknowledgment.columns,
            acknowledgment.rows,
        ) != (request.sequence, request.generation, request.columns, request.rows):
            self._fail("WBR ACK does not match the outstanding RESIZE")
        self._outstanding = None
        self._deadline = None
        return acknowledgment

    def check_deadline(self, *, now: float | None = None) -> None:
        if self._closed:
            raise WAWProcessProtocolError("WBR state machine is closed")
        self._expire_if_needed(self._time(now))

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._outstanding = None
        self._deadline = None
        if self._close_endpoint is not None:
            self._close_endpoint()

    def _time(self, supplied: float | None) -> float:
        current = self._clock() if supplied is None else supplied
        if not isinstance(current, (int, float)) or isinstance(current, bool):
            self._fail("WBR clock is invalid")
        try:
            value = float(current)
        except (OverflowError, TypeError, ValueError) as exc:
            self._fail("WBR clock is invalid", exc)
        if not math.isfinite(value) or value < 0:
            self._fail("WBR clock is invalid")
        if self._clock_high_water is not None and value < self._clock_high_water:
            self._fail("WBR clock moved backward")
        self._clock_high_water = value
        return value

    def _expire_if_needed(self, now: float) -> None:
        if self._deadline is not None and now >= self._deadline:
            self._fail("WBR ACK deadline expired")

    def _fail(self, message: str, cause: BaseException | None = None) -> NoReturn:
        try:
            self.close()
        except BaseException as close_error:
            if cause is None:
                cause = close_error
        if cause is None:
            raise WAWProcessProtocolError(message)
        raise WAWProcessProtocolError(message) from cause


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WAWProcessProtocolError("duplicate launch descriptor key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    raise WAWProcessProtocolError(f"invalid JSON constant: {value}")


def _validate_launch_descriptor(descriptor: WAWLaunchDescriptor) -> None:
    if descriptor.schema != LAUNCH_SCHEMA or descriptor.type != LAUNCH_TYPE:
        raise WAWProcessProtocolError("launch descriptor identity is invalid")
    if descriptor.agent not in {"claude", "codex"}:
        raise WAWProcessProtocolError("launch agent is invalid")
    _validate_nonzero_digest(descriptor.workspace_hash, "workspace hash")
    _validate_nonzero_digest(descriptor.profile_digest, "profile digest")
    if (
        not isinstance(descriptor.generation, str)
        or _POSITIVE_DECIMAL.fullmatch(descriptor.generation) is None
        or int(descriptor.generation) > MAX_UINT64
    ):
        raise WAWProcessProtocolError("launch generation is invalid")
    _validate_uid_gid(descriptor.runtime_uid, "runtime uid")
    _validate_uid_gid(descriptor.runtime_gid, "runtime gid")
    if descriptor.fd_role_bitmap != LAUNCH_FD_ROLE_BITMAP:
        raise WAWProcessProtocolError("launch descriptor bitmap is invalid")
    if not isinstance(descriptor.initial_geometry, LaunchGeometry):
        raise WAWProcessProtocolError("launch geometry is invalid")


def _validate_nonzero_digest(value: object, name: str) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None or value == "0" * 64:
        raise WAWProcessProtocolError(f"{name} is invalid")


def _validate_uid_gid(value: object, name: str) -> None:
    if type(value) is not int or not 1 <= value <= MAX_UID_GID:
        raise WAWProcessProtocolError(f"{name} is invalid")


def _validate_geometry(columns: object, rows: object) -> None:
    if type(columns) is not int or not MIN_COLUMNS <= columns <= MAX_COLUMNS:
        raise WAWProcessProtocolError("terminal columns are invalid")
    if type(rows) is not int or not MIN_ROWS <= rows <= MAX_ROWS:
        raise WAWProcessProtocolError("terminal rows are invalid")


def _decode_discoverable_fds(payload: bytes) -> list[int]:
    aligned = len(payload) - len(payload) % _FD_ARRAY_ITEM_SIZE
    values = array.array("i")
    values.frombytes(payload[:aligned])
    return list(values)


def validate_launch_fd_role(role: LaunchFDRole, descriptor: int) -> None:
    """Validate the descriptor object required by one fixed launch role.

    Provenance, ownership, mount and digest checks remain the caller's separate
    gates.  This check only proves the object class and the descriptor semantics
    required at the handoff boundary.
    """

    try:
        details = os.fstat(descriptor)
        descriptor_flags = fcntl.fcntl(descriptor, fcntl.F_GETFL)
    except OSError as exc:
        raise WAWProcessProtocolError("launch descriptor cannot be inspected") from exc
    if role is LaunchFDRole.PROJECT_DIRECTORY:
        o_path = getattr(os, "O_PATH", None)
        if (
            not isinstance(o_path, int)
            or not stat.S_ISDIR(details.st_mode)
            or descriptor_flags & o_path != o_path
        ):
            raise WAWProcessProtocolError("Project descriptor is not an O_PATH directory")
        return
    if role in {
        LaunchFDRole.SELECTED_HOME_DIRECTORY,
        LaunchFDRole.TEMP_DIRECTORY,
        LaunchFDRole.POLICY_DIRECTORY,
    }:
        if not stat.S_ISDIR(details.st_mode):
            raise WAWProcessProtocolError("launch directory role has the wrong object type")
        return
    if role in {LaunchFDRole.BRIDGE_EXECUTABLE, LaunchFDRole.VENDOR_EXECUTABLE}:
        if not stat.S_ISREG(details.st_mode) or not stat.S_IMODE(details.st_mode) & 0o111:
            raise WAWProcessProtocolError("launch executable role is not executable regular file")
        return
    if role is LaunchFDRole.WBR_ENDPOINT:
        if not stat.S_ISSOCK(details.st_mode):
            raise WAWProcessProtocolError("WBR endpoint is not a socket")
        duplicate = -1
        try:
            duplicate = os.dup(descriptor)
            with socket.socket(fileno=duplicate) as endpoint:
                duplicate = -1
                if (
                    endpoint.family != socket.AF_UNIX
                    or (endpoint.type & 0xF) != socket.SOCK_SEQPACKET
                ):
                    raise WAWProcessProtocolError("WBR endpoint socket type is invalid")
                endpoint.getpeername()
        except (OSError, ValueError) as exc:
            raise WAWProcessProtocolError("WBR endpoint is not connected") from exc
        finally:
            if duplicate >= 0:
                os.close(duplicate)
        return
    raise WAWProcessProtocolError("launch descriptor role is unknown")


def _close_unique(descriptors: Sequence[int], close_descriptor: CloseDescriptor) -> None:
    seen: set[int] = set()
    for descriptor in descriptors:
        if descriptor in seen or descriptor < 0:
            continue
        seen.add(descriptor)
        try:
            close_descriptor(descriptor)
        except BaseException:
            continue


def _validate_wbr_message(message: WBRMessage) -> None:
    if not isinstance(message.message_type, WBRMessageType):
        raise WAWProcessProtocolError("WBR message type is invalid")
    if type(message.flags) is not int or message.flags != 0:
        raise WAWProcessProtocolError("WBR flags are invalid")
    if type(message.sequence) is not int or not 1 <= message.sequence <= MAX_UINT64:
        raise WAWProcessProtocolError("WBR sequence is invalid")
    if type(message.generation) is not int or not 1 <= message.generation <= MAX_UINT64:
        raise WAWProcessProtocolError("WBR generation is invalid")
    _validate_geometry(message.columns, message.rows)


__all__ = [
    "LAUNCH_FD_COUNT",
    "LAUNCH_FD_ROLE_BITMAP",
    "LAUNCH_FD_ROLES",
    "LAUNCH_SCHEMA",
    "LAUNCH_TYPE",
    "MAX_COLUMNS",
    "MAX_LAUNCH_DESCRIPTOR_BYTES",
    "MAX_ROWS",
    "MIN_COLUMNS",
    "MIN_ROWS",
    "ReceivedLaunchDescriptors",
    "LaunchFDRole",
    "LaunchGeometry",
    "WAWLaunchDescriptor",
    "WAWProcessProtocolError",
    "WBR_ACK_DEADLINE_SECONDS",
    "WBR_FRAME_BYTES",
    "WBR_MAGIC",
    "WBR_VERSION",
    "WBRMessage",
    "WBRMessageType",
    "WBRResizeStateMachine",
    "decode_launch_descriptor",
    "decode_wbr_message",
    "encode_launch_descriptor",
    "encode_wbr_ack",
    "encode_wbr_message",
    "encode_wbr_resize",
    "receive_launch_descriptor",
    "validate_launch_ancillary",
    "validate_launch_fd_role",
]
