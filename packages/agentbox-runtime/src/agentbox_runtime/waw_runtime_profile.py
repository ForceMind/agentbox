"""Fixed, non-secret production mode profile for the Runtime process."""

from __future__ import annotations

import grp
import hashlib
import os
import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

_PROFILE_PATH = Path("/var/lib/agentbox-waw/runtime-profile.v1.json")
_RUNTIME_GROUP = "agentbox-runtime"
_PROFILE_MODE = 0o440
_PARENT_MODE = 0o750
_MAX_BYTES = 256
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
DISABLED_PROFILE_BYTES = b'{"mode":"disabled","schema_version":"agentbox-waw-runtime-profile.v1"}\n'
FILESYSTEM_V2_PROFILE_BYTES = (
    b'{"mode":"filesystem-v2","schema_version":"agentbox-waw-runtime-profile.v1"}\n'
)


class WAWRuntimeMode(StrEnum):
    DISABLED = "disabled"
    FILESYSTEM_V2 = "filesystem-v2"


class WAWRuntimeProfileError(RuntimeError):
    """The fixed Runtime deployment profile is unavailable or untrusted."""


@dataclass(frozen=True, slots=True)
class WAWRuntimeProfileObservation:
    mode: WAWRuntimeMode
    source: str
    raw_sha256: str | None
    parent_identity: tuple[int, ...]
    file_identity: tuple[int, ...] | None


def load_waw_runtime_profile() -> WAWRuntimeProfileObservation:
    """Read only the fixed installed path; a proven absent leaf stays disabled."""

    try:
        runtime_gid = grp.getgrnam(_RUNTIME_GROUP).gr_gid
        if type(runtime_gid) is not int or runtime_gid < 0:
            raise ValueError("Runtime group is invalid")
        return _load_profile_at(_PROFILE_PATH, root=Path("/"), root_uid=0, runtime_gid=runtime_gid)
    except (KeyError, OSError, ValueError, WAWRuntimeProfileError):
        raise WAWRuntimeProfileError("WAW Runtime deployment profile is unavailable") from None


def revalidate_waw_runtime_profile(observation: WAWRuntimeProfileObservation) -> None:
    if type(observation) is not WAWRuntimeProfileObservation:
        raise TypeError("Runtime profile observation is invalid")
    if load_waw_runtime_profile() != observation:
        raise WAWRuntimeProfileError("WAW Runtime profile changed before startup")


def _directory_identity(details: os.stat_result) -> tuple[int, ...]:
    return (
        details.st_dev,
        details.st_ino,
        details.st_mode,
        details.st_uid,
        details.st_gid,
    )


def _file_identity(details: os.stat_result) -> tuple[int, ...]:
    return (
        *_directory_identity(details),
        details.st_nlink,
        details.st_size,
        details.st_mtime_ns,
        details.st_ctime_ns,
    )


def _require_directory(
    details: os.stat_result, *, owner_uid: int, gid: int | None, exact_mode: int | None
) -> None:
    mode = stat.S_IMODE(details.st_mode)
    if (
        not stat.S_ISDIR(details.st_mode)
        or details.st_uid != owner_uid
        or (gid is not None and details.st_gid != gid)
        or mode & 0o022
        or (exact_mode is not None and mode != exact_mode)
    ):
        raise WAWRuntimeProfileError("Runtime profile parent provenance is invalid")


def _require_file(details: os.stat_result, *, root_uid: int, runtime_gid: int) -> None:
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_uid != root_uid
        or details.st_gid != runtime_gid
        or stat.S_IMODE(details.st_mode) != _PROFILE_MODE
        or details.st_nlink != 1
        or not 0 < details.st_size <= _MAX_BYTES
    ):
        raise WAWRuntimeProfileError("Runtime profile file provenance is invalid")


def _revalidate_parents(
    descriptors: list[int], observations: list[os.stat_result], components: tuple[str, ...]
) -> None:
    if len(descriptors) != len(observations) or len(components) != len(descriptors) - 1:
        raise AssertionError("Runtime profile directory observations changed")
    for index, descriptor in enumerate(descriptors):
        observed = _directory_identity(observations[index])
        if _directory_identity(os.fstat(descriptor)) != observed:
            raise WAWRuntimeProfileError("Runtime profile parent changed")
        if index > 0:
            entry = os.stat(
                components[index - 1], dir_fd=descriptors[index - 1], follow_symlinks=False
            )
            if _directory_identity(entry) != observed:
                raise WAWRuntimeProfileError("Runtime profile parent entry changed")


def _load_profile_at(
    path: Path, *, root: Path, root_uid: int, runtime_gid: int
) -> WAWRuntimeProfileObservation:
    """Private fixture seam; production calls it only with fixed root and path."""

    if (
        not root.is_absolute()
        or not path.is_absolute()
        or not path.is_relative_to(root)
        or ".." in root.parts
        or ".." in path.parts
        or path.name != _PROFILE_PATH.name
        or type(root_uid) is not int
        or root_uid < 0
        or type(runtime_gid) is not int
        or runtime_gid < 0
    ):
        raise ValueError("Runtime profile fixture boundary is invalid")
    parts = path.relative_to(root).parts
    if len(parts) < 2:
        raise ValueError("Runtime profile parent is missing")
    components = parts[:-1]
    directories: list[int] = []
    observations: list[os.stat_result] = []
    leaf: int | None = None
    try:
        base = os.open(root, _DIRECTORY_FLAGS)
        directories.append(base)
        root_details = os.fstat(base)
        _require_directory(root_details, owner_uid=root_uid, gid=None, exact_mode=None)
        observations.append(root_details)
        for index, component in enumerate(components):
            final = index == len(components) - 1
            expected_gid = runtime_gid if final else None
            expected_mode = _PARENT_MODE if final else None
            entry_before = os.stat(component, dir_fd=directories[-1], follow_symlinks=False)
            _require_directory(
                entry_before, owner_uid=root_uid, gid=expected_gid, exact_mode=expected_mode
            )
            descriptor = os.open(component, _DIRECTORY_FLAGS, dir_fd=directories[-1])
            directories.append(descriptor)
            details = os.fstat(descriptor)
            entry_after = os.stat(component, dir_fd=directories[-2], follow_symlinks=False)
            for item in (details, entry_after):
                _require_directory(
                    item, owner_uid=root_uid, gid=expected_gid, exact_mode=expected_mode
                )
                if _directory_identity(item) != _directory_identity(entry_before):
                    raise WAWRuntimeProfileError("Runtime profile parent changed while opening")
            observations.append(details)

        parent = directories[-1]
        parent_identity = _directory_identity(observations[-1])
        try:
            leaf = os.open(parts[-1], _FILE_FLAGS, dir_fd=parent)
        except FileNotFoundError:
            _revalidate_parents(directories, observations, components)
            try:
                os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                return WAWRuntimeProfileObservation(
                    WAWRuntimeMode.DISABLED, "missing_default", None, parent_identity, None
                )
            raise WAWRuntimeProfileError("Runtime profile appeared while reading absence") from None

        before = os.fstat(leaf)
        entry_before = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        for item in (before, entry_before):
            _require_file(item, root_uid=root_uid, runtime_gid=runtime_gid)
        if _file_identity(before) != _file_identity(entry_before):
            raise WAWRuntimeProfileError("Runtime profile descriptor and entry differ")
        raw = bytearray()
        while len(raw) < before.st_size:
            chunk = os.read(leaf, min(1024, before.st_size - len(raw)))
            if not chunk:
                raise WAWRuntimeProfileError("Runtime profile read is incomplete")
            raw.extend(chunk)
        if os.read(leaf, 1):
            raise WAWRuntimeProfileError("Runtime profile grew while reading")
        after = os.fstat(leaf)
        entry_after = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        for item in (after, entry_after):
            _require_file(item, root_uid=root_uid, runtime_gid=runtime_gid)
            if _file_identity(item) != _file_identity(before):
                raise WAWRuntimeProfileError("Runtime profile changed while reading")
        _revalidate_parents(directories, observations, components)
        mode = {
            DISABLED_PROFILE_BYTES: WAWRuntimeMode.DISABLED,
            FILESYSTEM_V2_PROFILE_BYTES: WAWRuntimeMode.FILESYSTEM_V2,
        }.get(bytes(raw))
        if mode is None:
            raise WAWRuntimeProfileError("Runtime profile content is invalid")
        return WAWRuntimeProfileObservation(
            mode,
            "installed_profile",
            hashlib.sha256(raw).hexdigest(),
            parent_identity,
            _file_identity(before),
        )
    finally:
        if leaf is not None:
            os.close(leaf)
        for descriptor in reversed(directories):
            os.close(descriptor)


__all__ = [
    "DISABLED_PROFILE_BYTES",
    "FILESYSTEM_V2_PROFILE_BYTES",
    "WAWRuntimeMode",
    "WAWRuntimeProfileError",
    "WAWRuntimeProfileObservation",
    "load_waw_runtime_profile",
    "revalidate_waw_runtime_profile",
]
