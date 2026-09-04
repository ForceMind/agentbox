"""API-only loader for the root-owned public WAW v2 host anchor."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from agentbox_runtime.waw_manifest_codecs import (
    APIHostAnchorV2,
    WAWManifestCodecError,
    decode_api_host_anchor_v2,
)

API_HOST_ANCHOR_V2_FILENAME = "api-host-anchor.v2.json"
API_HOST_ANCHOR_V2_MAX_BYTES = 64 * 1024
API_HOST_ANCHOR_V2_PUBLIC_DIRECTORY_MODE = 0o755

_DIRECTORY_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_DIRECTORY
_FILE_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_READ_BYTES = 8192
_MAX_PATH_COMPONENTS = 32
_open = os.open
_fstat = os.fstat
_stat = os.stat
_read = os.read
_close = os.close


class WAWAPIHostAnchorError(RuntimeError):
    """The public host anchor could not be proven safe and valid."""


class _WAWAPIHostAnchorValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WAWAPIHostAnchorV2:
    """Strict public anchor fields bound to the digest of the exact file bytes."""

    anchor: APIHostAnchorV2
    raw_sha256: str


def load_waw_api_host_anchor_v2(path: Path) -> WAWAPIHostAnchorV2:
    """Read exactly one public v2 anchor without touching Runtime-private state."""

    try:
        return _load_waw_api_host_anchor_v2(path)
    except (OSError, WAWManifestCodecError, _WAWAPIHostAnchorValidationError):
        raise WAWAPIHostAnchorError("WAW API host anchor is unavailable") from None


def _load_waw_api_host_anchor_v2(path: Path) -> WAWAPIHostAnchorV2:
    _validate_path(path)
    directory_descriptors, directory_identities = _open_directory_chain(path.parent)
    descriptor: int | None = None
    try:
        parent_descriptor = directory_descriptors[-1]
        parent_before = _fstat(parent_descriptor)
        _validate_directory(parent_before, final=True)
        descriptor = _open(
            API_HOST_ANCHOR_V2_FILENAME,
            _FILE_FLAGS,
            dir_fd=parent_descriptor,
        )
        before = _fstat(descriptor)
        _validate_file(before)
        entry_before = _stat(
            API_HOST_ANCHOR_V2_FILENAME,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        _validate_file(entry_before)
        if _file_identity(before) != _file_identity(entry_before):
            raise _WAWAPIHostAnchorValidationError(
                "anchor descriptor does not match directory entry"
            )
        expected_size = before.st_size
        payload = bytearray()
        while len(payload) < expected_size:
            requested = min(_READ_BYTES, expected_size - len(payload))
            chunk = _read(descriptor, requested)
            if type(chunk) is not bytes or not chunk or len(chunk) > requested:
                raise _WAWAPIHostAnchorValidationError(
                    "anchor read did not match its declared size"
                )
            payload.extend(chunk)
        trailing = _read(descriptor, 1)
        if type(trailing) is not bytes or trailing:
            raise _WAWAPIHostAnchorValidationError("anchor grew while being read")
        after = _fstat(descriptor)
        _validate_file(after)
        entry_after = _stat(
            API_HOST_ANCHOR_V2_FILENAME,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        _validate_file(entry_after)
        parent_after = _fstat(parent_descriptor)
        _validate_directory(parent_after, final=True)
        if _file_identity(before) != _file_identity(after):
            raise _WAWAPIHostAnchorValidationError("anchor identity changed while being read")
        if _file_identity(entry_before) != _file_identity(entry_after) or _file_identity(
            after
        ) != _file_identity(entry_after):
            raise _WAWAPIHostAnchorValidationError(
                "anchor directory entry changed while being read"
            )
        if _directory_identity(parent_before) != _directory_identity(parent_after):
            raise _WAWAPIHostAnchorValidationError("anchor parent changed while being read")
        _revalidate_directory_chain(directory_descriptors, directory_identities)
        raw = bytes(payload)
        anchor = decode_api_host_anchor_v2(raw)
        return WAWAPIHostAnchorV2(anchor=anchor, raw_sha256=hashlib.sha256(raw).hexdigest())
    finally:
        descriptors = (
            directory_descriptors if descriptor is None else (*directory_descriptors, descriptor)
        )
        _close_descriptors(descriptors)


def _validate_path(path: Path) -> None:
    if (
        not isinstance(path, Path)
        or not path.is_absolute()
        or path.anchor != "/"
        or path.name != API_HOST_ANCHOR_V2_FILENAME
        or ".." in path.parts
        or "\x00" in str(path)
        or len(os.fsencode(path)) > 4096
    ):
        raise _WAWAPIHostAnchorValidationError("anchor path is invalid")


def _open_directory_chain(parent: Path) -> tuple[tuple[int, ...], tuple[tuple[int, ...], ...]]:
    components = parent.parts[1:]
    if len(components) > _MAX_PATH_COMPONENTS:
        raise _WAWAPIHostAnchorValidationError("anchor path has too many components")
    descriptors: list[int] = []
    identities: list[tuple[int, ...]] = []
    try:
        root_descriptor = _open("/", _DIRECTORY_FLAGS)
        descriptors.append(root_descriptor)
        root = _fstat(root_descriptor)
        _validate_directory(root, final=not components)
        identities.append(_directory_identity(root))
        for index, component in enumerate(components):
            descriptor = _open(component, _DIRECTORY_FLAGS, dir_fd=descriptors[-1])
            descriptors.append(descriptor)
            details = _fstat(descriptor)
            _validate_directory(details, final=index == len(components) - 1)
            identities.append(_directory_identity(details))
        return tuple(descriptors), tuple(identities)
    except BaseException:
        _close_descriptors(tuple(descriptors))
        raise


def _revalidate_directory_chain(
    descriptors: tuple[int, ...], identities: tuple[tuple[int, ...], ...]
) -> None:
    if len(descriptors) != len(identities):
        raise AssertionError("directory descriptor identity count changed")
    for index, (descriptor, identity) in enumerate(zip(descriptors, identities, strict=True)):
        details = _fstat(descriptor)
        _validate_directory(details, final=index == len(descriptors) - 1)
        if _directory_identity(details) != identity:
            raise _WAWAPIHostAnchorValidationError("anchor directory chain changed")


def _validate_directory(details: os.stat_result, *, final: bool) -> None:
    mode = stat.S_IMODE(details.st_mode)
    if (
        not stat.S_ISDIR(details.st_mode)
        or details.st_uid != 0
        or details.st_gid != 0
        or mode & 0o022
        or (final and mode != API_HOST_ANCHOR_V2_PUBLIC_DIRECTORY_MODE)
    ):
        raise _WAWAPIHostAnchorValidationError("anchor directory provenance is invalid")


def _validate_file(details: os.stat_result) -> None:
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_uid != 0
        or details.st_gid != 0
        or stat.S_IMODE(details.st_mode) != 0o444
        or details.st_nlink != 1
        or type(details.st_size) is not int
        or not 0 < details.st_size <= API_HOST_ANCHOR_V2_MAX_BYTES
    ):
        raise _WAWAPIHostAnchorValidationError("anchor file provenance is invalid")


def _file_identity(details: os.stat_result) -> tuple[int, ...]:
    return (
        details.st_dev,
        details.st_ino,
        details.st_mode,
        details.st_uid,
        details.st_gid,
        details.st_nlink,
        details.st_size,
        details.st_mtime_ns,
        details.st_ctime_ns,
    )


def _directory_identity(details: os.stat_result) -> tuple[int, ...]:
    return (
        details.st_dev,
        details.st_ino,
        details.st_mode,
        details.st_uid,
        details.st_gid,
        details.st_nlink,
        details.st_mtime_ns,
        details.st_ctime_ns,
    )


def _close_descriptors(descriptors: tuple[int, ...]) -> None:
    first_error: OSError | None = None
    for descriptor in reversed(descriptors):
        try:
            _close(descriptor)
        except OSError as exc:
            if first_error is None:
                first_error = exc
    if first_error is not None:
        raise first_error


__all__ = [
    "API_HOST_ANCHOR_V2_FILENAME",
    "API_HOST_ANCHOR_V2_MAX_BYTES",
    "API_HOST_ANCHOR_V2_PUBLIC_DIRECTORY_MODE",
    "WAWAPIHostAnchorError",
    "WAWAPIHostAnchorV2",
    "load_waw_api_host_anchor_v2",
]
