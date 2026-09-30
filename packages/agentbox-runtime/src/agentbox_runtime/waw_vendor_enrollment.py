"""Fixed, non-secret Runtime enrollment input for WAW vendor auth probes.

Only the installer-owned file at the fixed path is a production source. The
record is bound to the already verified v2 manifest before its values may be
used by a production provider. This module neither probes a CLI nor reads a
vendor HOME, credential, or Provider Secret.
"""

from __future__ import annotations

import grp
import hashlib
import json
import os
import pwd
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from agentbox_runtime.waw_fixed_transport import WAWVerifiedExecutionAuthority
from agentbox_runtime.waw_manifest_codecs import CrossManifestPinV2

_FIXED_PATH = Path("/var/lib/agentbox-waw/vendor-enrollment.v1.json")
_RUNTIME_GROUP = "agentbox-runtime"
_SCHEMA = "agentbox-waw-vendor-enrollment.v1"
_MAX_BYTES = 1024
_PARENT_MODE = 0o750
_FILE_MODE = 0o440
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_HOST_ID = re.compile(r"\Awri_[0-9a-f]{32}\Z")
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_POSITIVE_U64 = re.compile(r"\A[1-9][0-9]{0,19}\Z")
_VERSION = re.compile(r"\A[!-~]{1,96}\Z")
_STATES = frozenset({"bootstrap", "steady", "rotation"})
_VALUE_KEYS = (
    "claude_vendor_version",
    "codex_vendor_version",
    "codex_unauthenticated_output_sha256",
)
_KEYS = frozenset(
    {
        "schema_version",
        "runtime_host_installation_id",
        "runtime_host_installation_revision",
        "host_manifest_digest",
        "enrollment_epoch",
        "enrollment_state",
        *_VALUE_KEYS,
    }
)


class WAWVendorEnrollmentError(RuntimeError):
    """The fixed installed enrollment input is missing, unsafe, or stale."""


def _identity(details: os.stat_result) -> tuple[int, ...]:
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
    return _identity(details)[:5]


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise WAWVendorEnrollmentError("vendor enrollment has duplicate fields")
        result[key] = value
    return result


def _positive_u64(value: object) -> bool:
    return (
        type(value) is str
        and _POSITIVE_U64.fullmatch(value) is not None
        and int(value) <= 2**64 - 1
    )


@dataclass(frozen=True, slots=True, repr=False)
class WAWVendorEnrollmentRecord:
    runtime_host_installation_id: str
    runtime_host_installation_revision: str
    host_manifest_digest: str
    enrollment_epoch: str
    enrollment_state: str
    values: Mapping[str, str]
    raw_sha256: str
    parent_identity: tuple[int, ...]
    file_identity: tuple[int, ...]

    def __repr__(self) -> str:
        return "WAWVendorEnrollmentRecord(<verified>)"

    def require_authority(self, authority: WAWVerifiedExecutionAuthority) -> None:
        """Bind the record to the builder's exact, already-issued authority."""

        if type(authority) is not WAWVerifiedExecutionAuthority:
            raise WAWVendorEnrollmentError("verified Runtime authority is required")
        manifest = authority._manifest
        if type(manifest) is not CrossManifestPinV2 or (
            self.runtime_host_installation_id != authority.runtime_host_installation_id
            or self.runtime_host_installation_revision
            != authority.runtime_host_installation_revision
            or self.host_manifest_digest != authority.host_manifest_digest
            or self.enrollment_epoch != manifest.runtime.enrollment_epoch
            or self.enrollment_state != manifest.runtime.enrollment_state
        ):
            raise WAWVendorEnrollmentError("vendor enrollment is not bound to Runtime authority")


def _decode(
    raw: bytes, parent: tuple[int, ...], leaf: tuple[int, ...]
) -> WAWVendorEnrollmentRecord:
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise WAWVendorEnrollmentError("vendor enrollment content is invalid") from exc
    if type(data) is not dict or set(data) != _KEYS:
        raise WAWVendorEnrollmentError("vendor enrollment fields are invalid")
    canonical = (
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode()
    if raw != canonical or data["schema_version"] != _SCHEMA:
        raise WAWVendorEnrollmentError("vendor enrollment encoding is invalid")
    host = data["runtime_host_installation_id"]
    revision = data["runtime_host_installation_revision"]
    digest = data["host_manifest_digest"]
    epoch = data["enrollment_epoch"]
    state = data["enrollment_state"]
    if (
        type(host) is not str
        or _HOST_ID.fullmatch(host) is None
        or not _positive_u64(revision)
        or type(digest) is not str
        or _DIGEST.fullmatch(digest) is None
        or not _positive_u64(epoch)
        or type(state) is not str
        or state not in _STATES
    ):
        raise WAWVendorEnrollmentError("vendor enrollment authority fields are invalid")
    values: dict[str, str] = {}
    for key in _VALUE_KEYS:
        value = data[key]
        if (
            type(value) is not str
            or (_DIGEST.fullmatch(value) if key.endswith("sha256") else _VERSION.fullmatch(value))
            is None
        ):
            raise WAWVendorEnrollmentError("vendor enrollment value is invalid")
        values[key] = value
    return WAWVendorEnrollmentRecord(
        host,
        revision,
        digest,
        epoch,
        state,
        MappingProxyType(values),
        hashlib.sha256(raw).hexdigest(),
        parent,
        leaf,
    )


def encode_waw_vendor_enrollment(values: Mapping[str, object]) -> bytes:
    """Encode validated non-secret fields without reading or writing host state.

    Installer enrollment can use the same bounded schema as the Runtime reader.
    Encoding does not establish target observations or confer Runtime authority.
    """

    if not isinstance(values, Mapping) or len(values) != len(_KEYS):
        raise WAWVendorEnrollmentError("vendor enrollment fields are invalid")
    data = dict(values)
    if set(data) != _KEYS:
        raise WAWVendorEnrollmentError("vendor enrollment fields are invalid")
    # All admitted fields are short ASCII strings. Check the shape before JSON
    # serialization so an installer input cannot allocate an unbounded payload.
    if any(
        type(value) is not str or len(value) > 96 or not value.isascii() for value in data.values()
    ):
        raise WAWVendorEnrollmentError("vendor enrollment value is invalid")
    raw = (
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode()
    if len(raw) > _MAX_BYTES:
        raise WAWVendorEnrollmentError("vendor enrollment content is too large")
    _decode(raw, (), ())
    return raw


def _load_at(
    path: Path, *, root: Path, owner_uid: int, runtime_gid: int
) -> WAWVendorEnrollmentRecord:
    """Private fixture seam; production always uses the fixed root and path."""

    if (
        not root.is_absolute()
        or not path.is_absolute()
        or not path.is_relative_to(root)
        or path.name != _FIXED_PATH.name
        or ".." in root.parts
        or ".." in path.parts
        or type(owner_uid) is not int
        or type(runtime_gid) is not int
        or owner_uid < 0
        or runtime_gid < 0
    ):
        raise ValueError("vendor enrollment fixture boundary is invalid")
    components = path.relative_to(root).parts[:-1]
    if not components:
        raise ValueError("vendor enrollment parent is missing")
    directories: list[int] = []
    observations: list[os.stat_result] = []
    leaf: int | None = None
    close_failed = False
    try:
        base = os.open(root, _DIR_FLAGS)
        directories.append(base)
        first = os.fstat(base)
        _require_directory(first, owner_uid, None, None)
        observations.append(first)
        for index, component in enumerate(components):
            final = index == len(components) - 1
            expected_gid = runtime_gid if final else None
            expected_mode = _PARENT_MODE if final else None
            before = os.stat(component, dir_fd=directories[-1], follow_symlinks=False)
            _require_directory(before, owner_uid, expected_gid, expected_mode)
            child = os.open(component, _DIR_FLAGS, dir_fd=directories[-1])
            directories.append(child)
            opened = os.fstat(child)
            after = os.stat(component, dir_fd=directories[-2], follow_symlinks=False)
            for details in (opened, after):
                _require_directory(details, owner_uid, expected_gid, expected_mode)
                if _directory_identity(details) != _directory_identity(before):
                    raise WAWVendorEnrollmentError("vendor enrollment parent changed")
            observations.append(opened)
        parent = directories[-1]
        leaf = os.open(path.name, _FILE_FLAGS, dir_fd=parent)
        before = os.fstat(leaf)
        entry = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        for details in (before, entry):
            _require_file(details, owner_uid, runtime_gid)
            if _identity(details) != _identity(before):
                raise WAWVendorEnrollmentError("vendor enrollment entry changed")
        raw = bytearray()
        while len(raw) < before.st_size:
            chunk = os.read(leaf, before.st_size - len(raw))
            if not chunk:
                raise WAWVendorEnrollmentError("vendor enrollment read is incomplete")
            raw.extend(chunk)
        if os.read(leaf, 1):
            raise WAWVendorEnrollmentError("vendor enrollment grew during read")
        after = os.fstat(leaf)
        entry_after = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if _identity(after) != _identity(before) or _identity(entry_after) != _identity(before):
            raise WAWVendorEnrollmentError("vendor enrollment changed during read")
        for index, descriptor in enumerate(directories):
            if _directory_identity(os.fstat(descriptor)) != _directory_identity(
                observations[index]
            ):
                raise WAWVendorEnrollmentError("vendor enrollment ancestor changed")
            if index > 0:
                current = os.stat(
                    components[index - 1], dir_fd=directories[index - 1], follow_symlinks=False
                )
                if _directory_identity(current) != _directory_identity(observations[index]):
                    raise WAWVendorEnrollmentError("vendor enrollment ancestor entry changed")
        return _decode(bytes(raw), _directory_identity(observations[-1]), _identity(before))
    except (OSError, ValueError, TypeError, WAWVendorEnrollmentError) as exc:
        if isinstance(exc, WAWVendorEnrollmentError):
            raise
        raise WAWVendorEnrollmentError("vendor enrollment file is unavailable") from exc
    finally:
        if leaf is not None:
            try:
                os.close(leaf)
            except OSError:
                close_failed = True
        for descriptor in reversed(directories):
            try:
                os.close(descriptor)
            except OSError:
                close_failed = True
        if close_failed:
            raise WAWVendorEnrollmentError("vendor enrollment cleanup is uncertain")


def _require_directory(
    details: os.stat_result, owner_uid: int, group_gid: int | None, mode: int | None
) -> None:
    if (
        not stat.S_ISDIR(details.st_mode)
        or details.st_uid != owner_uid
        or (group_gid is not None and details.st_gid != group_gid)
        or stat.S_IMODE(details.st_mode) & 0o022
        or (mode is not None and stat.S_IMODE(details.st_mode) != mode)
    ):
        raise WAWVendorEnrollmentError("vendor enrollment parent provenance is invalid")


def _require_file(details: os.stat_result, owner_uid: int, runtime_gid: int) -> None:
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_uid != owner_uid
        or details.st_gid != runtime_gid
        or stat.S_IMODE(details.st_mode) != _FILE_MODE
        or details.st_nlink != 1
        or not 0 < details.st_size <= _MAX_BYTES
    ):
        raise WAWVendorEnrollmentError("vendor enrollment file provenance is invalid")


def load_waw_vendor_enrollment() -> WAWVendorEnrollmentRecord:
    """Read the fixed installer-owned record; absence is never defaulted."""

    try:
        runtime_account = pwd.getpwnam(_RUNTIME_GROUP)
        runtime_gid = grp.getgrnam(_RUNTIME_GROUP).gr_gid
        if runtime_account.pw_uid == 0 or runtime_account.pw_gid != runtime_gid:
            raise WAWVendorEnrollmentError("vendor enrollment Runtime identity is invalid")
        uids = (
            os.getresuid()
            if hasattr(os, "getresuid")
            else (os.getuid(), os.geteuid(), os.geteuid())
        )
        gids = (
            os.getresgid()
            if hasattr(os, "getresgid")
            else (os.getgid(), os.getegid(), os.getegid())
        )
        if any(uid != runtime_account.pw_uid for uid in uids) or any(
            gid != runtime_gid for gid in gids
        ):
            raise WAWVendorEnrollmentError("vendor enrollment Runtime process is invalid")
        return _load_at(_FIXED_PATH, root=Path("/"), owner_uid=0, runtime_gid=runtime_gid)
    except (KeyError, OSError, ValueError, WAWVendorEnrollmentError):
        raise WAWVendorEnrollmentError("vendor enrollment is unavailable") from None


def revalidate_waw_vendor_enrollment(observed: WAWVendorEnrollmentRecord) -> None:
    if type(observed) is not WAWVendorEnrollmentRecord:
        raise TypeError("vendor enrollment observation is invalid")
    if load_waw_vendor_enrollment() != observed:
        raise WAWVendorEnrollmentError("vendor enrollment changed before startup")


__all__ = [
    "WAWVendorEnrollmentError",
    "WAWVendorEnrollmentRecord",
    "encode_waw_vendor_enrollment",
    "load_waw_vendor_enrollment",
    "revalidate_waw_vendor_enrollment",
]
