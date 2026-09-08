"""Fail-closed loader for the fixed, non-secret WAW API deployment profile."""

from __future__ import annotations

import grp
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from agentbox_api.waw_application import WAWMode

WAW_DEPLOYMENT_PROFILE_PATH = Path("/etc/agentbox/waw-api-profile.v1.json")
WAW_DEPLOYMENT_PROFILE_FILENAME = "waw-api-profile.v1.json"
WAW_DEPLOYMENT_PROFILE_SCHEMA = "agentbox-waw-api-profile.v1"
WAW_DEPLOYMENT_PROFILE_MAX_BYTES = 4096
_PROFILE_DIRECTORY_MODE = 0o750
_PROFILE_FILE_MODE = 0o440
_PROFILE_GROUP = "agentbox"
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_DIRECTORY
_FILE_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_READ_BYTES = 1024

_open = os.open
_fstat = os.fstat
_stat = os.stat
_read = os.read
_close = os.close
_getgrnam = grp.getgrnam


class WAWDeploymentProfileError(RuntimeError):
    """The fixed deployment profile could not be proven safe and current."""


class _ProfileValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WAWDeploymentProfileObservation:
    """A process-lifespan profile snapshot; it contains no Secret material."""

    mode: WAWMode
    source: str
    raw_sha256: str | None
    parent_identity: tuple[int, ...]
    file_identity: tuple[int, ...] | None


def load_waw_deployment_profile() -> WAWDeploymentProfileObservation:
    """Load the one fixed profile, treating a safely absent leaf as disabled."""

    try:
        return _load_waw_deployment_profile()
    except (KeyError, OSError, _ProfileValidationError):
        raise WAWDeploymentProfileError("WAW deployment profile is unavailable") from None


def revalidate_waw_deployment_profile(
    observation: WAWDeploymentProfileObservation,
) -> None:
    """Reject a profile that changed between factory construction and startup."""

    if type(observation) is not WAWDeploymentProfileObservation:
        raise TypeError("WAW deployment profile observation is invalid")
    if load_waw_deployment_profile() != observation:
        raise WAWDeploymentProfileError("WAW deployment profile changed before startup")


def _load_waw_deployment_profile() -> WAWDeploymentProfileObservation:
    path = WAW_DEPLOYMENT_PROFILE_PATH
    if not path.is_absolute() or path.name != WAW_DEPLOYMENT_PROFILE_FILENAME:
        raise _ProfileValidationError("deployment profile path is invalid")
    group_id = _getgrnam(_PROFILE_GROUP).gr_gid
    if type(group_id) is not int or group_id < 0:
        raise _ProfileValidationError("deployment profile group is invalid")

    directory_fds: list[int] = []
    directory_details: list[os.stat_result] = []
    leaf_fd: int | None = None
    try:
        root_fd = _open("/", _DIRECTORY_FLAGS)
        directory_fds.append(root_fd)
        root_before = _fstat(root_fd)
        _validate_directory(root_before, expected_gid=0, expected_mode=None)
        directory_details.append(root_before)
        components = path.parts[1:-1]
        if not components:
            raise _ProfileValidationError("deployment profile parent is invalid")
        for index, component in enumerate(components):
            entry_before = _stat(component, dir_fd=directory_fds[-1], follow_symlinks=False)
            _validate_directory(
                entry_before,
                expected_gid=group_id if index == len(components) - 1 else 0,
                expected_mode=_PROFILE_DIRECTORY_MODE if index == len(components) - 1 else None,
            )
            descriptor = _open(component, _DIRECTORY_FLAGS, dir_fd=directory_fds[-1])
            directory_fds.append(descriptor)
            details = _fstat(descriptor)
            _validate_directory(
                details,
                expected_gid=group_id if index == len(components) - 1 else 0,
                expected_mode=_PROFILE_DIRECTORY_MODE if index == len(components) - 1 else None,
            )
            entry_after = _stat(component, dir_fd=directory_fds[-2], follow_symlinks=False)
            _validate_directory(
                entry_after,
                expected_gid=group_id if index == len(components) - 1 else 0,
                expected_mode=_PROFILE_DIRECTORY_MODE if index == len(components) - 1 else None,
            )
            if _directory_identity(entry_before) != _directory_identity(
                details
            ) or _directory_identity(entry_before) != _directory_identity(entry_after):
                raise _ProfileValidationError(
                    "deployment profile directory entry changed while opening"
                )
            directory_details.append(details)
        parent_fd = directory_fds[-1]
        parent_before = directory_details[-1]
        _validate_directory(
            parent_before, expected_gid=group_id, expected_mode=_PROFILE_DIRECTORY_MODE
        )
        try:
            leaf_fd = _open(WAW_DEPLOYMENT_PROFILE_FILENAME, _FILE_FLAGS, dir_fd=parent_fd)
        except FileNotFoundError:
            _revalidate_directory_chain(directory_fds, directory_details, components, group_id)
            try:
                _stat(WAW_DEPLOYMENT_PROFILE_FILENAME, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise _ProfileValidationError(
                    "deployment profile appeared while reading missing state"
                )
            return WAWDeploymentProfileObservation(
                mode=WAWMode.DISABLED,
                source="missing_default",
                raw_sha256=None,
                parent_identity=_directory_identity(parent_before),
                file_identity=None,
            )
        before = _fstat(leaf_fd)
        _validate_file(before, group_id)
        entry_before = _stat(
            WAW_DEPLOYMENT_PROFILE_FILENAME, dir_fd=parent_fd, follow_symlinks=False
        )
        _validate_file(entry_before, group_id)
        if _file_identity(before) != _file_identity(entry_before):
            raise _ProfileValidationError("deployment profile descriptor does not match entry")
        raw = _read_exact(leaf_fd, before.st_size)
        after = _fstat(leaf_fd)
        entry_after = _stat(
            WAW_DEPLOYMENT_PROFILE_FILENAME, dir_fd=parent_fd, follow_symlinks=False
        )
        _validate_file(after, group_id)
        _validate_file(entry_after, group_id)
        _revalidate_directory_chain(directory_fds, directory_details, components, group_id)
        if (
            _file_identity(before) != _file_identity(after)
            or _file_identity(entry_before) != _file_identity(entry_after)
            or _file_identity(after) != _file_identity(entry_after)
        ):
            raise _ProfileValidationError("deployment profile changed while being read")
        return WAWDeploymentProfileObservation(
            mode=_parse_profile(raw),
            source="installed_profile",
            raw_sha256=hashlib.sha256(raw).hexdigest(),
            parent_identity=_directory_identity(parent_before),
            file_identity=_file_identity(before),
        )
    finally:
        _close_descriptors(leaf_fd, *reversed(directory_fds))


def _read_exact(descriptor: int, expected_size: int) -> bytes:
    if type(expected_size) is not int or not 0 < expected_size <= WAW_DEPLOYMENT_PROFILE_MAX_BYTES:
        raise _ProfileValidationError("deployment profile size is invalid")
    payload = bytearray()
    while len(payload) < expected_size:
        requested = min(_READ_BYTES, expected_size - len(payload))
        chunk = _read(descriptor, requested)
        if type(chunk) is not bytes or not chunk or len(chunk) > requested:
            raise _ProfileValidationError("deployment profile read is invalid")
        payload.extend(chunk)
    if _read(descriptor, 1) != b"":
        raise _ProfileValidationError("deployment profile grew while being read")
    return bytes(payload)


def _parse_profile(raw: bytes) -> WAWMode:
    profiles = {
        b'{"mode":"disabled","schema_version":"agentbox-waw-api-profile.v1"}\n': WAWMode.DISABLED,
        (
            b'{"mode":"filesystem-v2","schema_version":"agentbox-waw-api-profile.v1"}\n'
        ): WAWMode.FILESYSTEM_V2,
    }
    try:
        return profiles[raw]
    except KeyError:
        raise _ProfileValidationError("deployment profile is not canonical") from None


def _revalidate_directory_chain(
    descriptors: list[int],
    observations: list[os.stat_result],
    components: tuple[str, ...],
    group_id: int,
) -> None:
    if len(descriptors) != len(observations) or len(components) != len(descriptors) - 1:
        raise AssertionError("deployment profile directory observations changed")
    for index, (descriptor, before) in enumerate(zip(descriptors, observations, strict=True)):
        final = index == len(descriptors) - 1
        after = _fstat(descriptor)
        _validate_directory(
            after,
            expected_gid=group_id if final else 0,
            expected_mode=_PROFILE_DIRECTORY_MODE if final else None,
        )
        if _directory_identity(before) != _directory_identity(after):
            raise _ProfileValidationError("deployment profile directory changed while being read")
        if index > 0:
            entry = _stat(
                components[index - 1], dir_fd=descriptors[index - 1], follow_symlinks=False
            )
            _validate_directory(
                entry,
                expected_gid=group_id if final else 0,
                expected_mode=_PROFILE_DIRECTORY_MODE if final else None,
            )
            if _directory_identity(before) != _directory_identity(entry):
                raise _ProfileValidationError(
                    "deployment profile directory entry changed while being read"
                )


def _validate_directory(
    details: os.stat_result, *, expected_gid: int, expected_mode: int | None
) -> None:
    mode = stat.S_IMODE(details.st_mode)
    if (
        not stat.S_ISDIR(details.st_mode)
        or details.st_uid != 0
        or details.st_gid != expected_gid
        or mode & 0o022
        or (expected_mode is not None and mode != expected_mode)
    ):
        raise _ProfileValidationError("deployment profile directory provenance is invalid")


def _validate_file(details: os.stat_result, group_id: int) -> None:
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_uid != 0
        or details.st_gid != group_id
        or stat.S_IMODE(details.st_mode) != _PROFILE_FILE_MODE
        or details.st_nlink != 1
        or type(details.st_size) is not int
        or not 0 < details.st_size <= WAW_DEPLOYMENT_PROFILE_MAX_BYTES
    ):
        raise _ProfileValidationError("deployment profile provenance is invalid")


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


def _close_descriptors(*descriptors: int | None) -> None:
    first_error: OSError | None = None
    for descriptor in descriptors:
        if descriptor is None:
            continue
        try:
            _close(descriptor)
        except OSError as exc:
            if first_error is None:
                first_error = exc
    if first_error is not None:
        raise first_error


__all__ = [
    "WAW_DEPLOYMENT_PROFILE_FILENAME",
    "WAW_DEPLOYMENT_PROFILE_MAX_BYTES",
    "WAW_DEPLOYMENT_PROFILE_PATH",
    "WAWDeploymentProfileError",
    "WAWDeploymentProfileObservation",
    "load_waw_deployment_profile",
    "revalidate_waw_deployment_profile",
]
