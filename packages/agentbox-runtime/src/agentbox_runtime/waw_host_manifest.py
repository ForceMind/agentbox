"""Fail-closed reader for the non-secret WAW Runtime host manifest.

The manifest is installer-owned.  Runtime may read it, but it never creates,
rewrites, or repairs the file.  A caller must provide the expected Runtime
group because the API and Worker identities must not be able to traverse the
manifest's parent directory.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from agentbox_runtime.waw_manifest_codecs import (
    CrossManifestPinV2,
    WAWManifestCodecError,
    decode_api_host_anchor_v2,
    decode_runtime_host_manifest,
    decode_runtime_host_manifest_v2,
    verify_api_host_anchor_v2_cross_manifest,
)
from agentbox_runtime.waw_manifest_codecs import (
    RuntimeHostManifest as StrictRuntimeHostManifest,
)
from agentbox_runtime.waw_manifest_codecs import (
    RuntimeHostManifestV2 as StrictRuntimeHostManifestV2,
)

_DEFAULT_PATH = Path("/var/lib/agentbox-waw/runtime-host-installation.json")
_DEFAULT_V2_PATH = Path("/var/lib/agentbox-waw/runtime-host-installation.v2.json")
_DEFAULT_BUNDLE_DIRECTORY = Path("/var/lib/agentbox-waw")
_DEFAULT_PUBLIC_V2_DIRECTORY = Path("/usr/share/agentbox/waw")
_BUNDLE_FILENAMES = (
    "api-host-anchor.v1",
    "runtime-host-installation.v1",
    "project-root.v1",
    "cgroup-delegation.v1",
)
WAW_PUBLIC_MANIFEST_FILENAMES_V2 = (
    "api-host-anchor.v2.json",
    "project-root.v1.json",
    "cgroup-delegation.v1.json",
    "executable-inventory.v1.json",
    "interactive-profiles.v1.json",
    "tmux.conf",
    "sandbox-policies.v1.json",
    "socket-policy.v1.json",
    "claude-managed-policy.v1.json",
    "codex-managed-policy.v1.json",
    "codex-requirements.toml",
    "codex-managed-config.toml",
)
_SCHEMA = "waw-runtime-host-installation-v1"
_MAX_BYTES = 64 * 1024
_MAX_U64 = 2**64 - 1
_ID = re.compile(r"\Awri_[0-9a-f]{32}\Z")
_DECIMAL = re.compile(r"\A[1-9][0-9]{0,19}\Z")
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_STATES = frozenset({"bootstrap", "steady", "rotation"})
_OPEN_FLAGS = os.O_RDONLY | os.O_CLOEXEC
_DIRECTORY_FLAGS = _OPEN_FLAGS | os.O_DIRECTORY


def _is_uint64_decimal(value: str) -> bool:
    """Return whether value is a canonical positive uint64 decimal string."""

    return _DECIMAL.fullmatch(value) is not None and int(value) <= _MAX_U64


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


class WAWRuntimeHostManifestDevelopmentOnlyError(RuntimeError):
    """The legacy synthetic WAW host manifest is missing or unsafe.

    Production bootstrap callers must use the strict codec boundary and its
    ``WAWManifestCodecError`` failures instead.
    """


class WAWRuntimeHostManifestError(RuntimeError):
    """The strict Runtime host manifest codec boundary rejected the record."""


@dataclass(frozen=True)
class WAWCanonicalManifestBundle:
    """Canonical, installer-owned bytes read from one trusted directory.

    This is deliberately a raw-byte container.  Cross-manifest decoding and
    pin verification remain the responsibility of the strict codec/bootstrap
    boundary, while this loader only establishes file provenance.
    """

    api_host_anchor: bytes
    runtime_host_installation: bytes
    project_root: bytes
    cgroup_delegation: bytes


@dataclass(frozen=True)
class WAWCanonicalManifestBundleV2:
    """Exact root-owned public v2 artifact set, held as verified bytes."""

    api_host_anchor: bytes
    project_root: bytes
    cgroup_delegation: bytes
    executable_inventory: bytes
    interactive_profiles: bytes
    tmux_config: bytes
    sandbox_policy_bundle: bytes
    socket_policy: bytes
    claude_managed_policy: bytes
    codex_managed_policy: bytes
    codex_requirements_policy: bytes
    codex_managed_config_policy: bytes


@dataclass(frozen=True)
class WAWRuntimeHostManifestDevelopmentOnly:
    runtime_host_installation_id: str
    runtime_host_installation_revision: str
    host_manifest_digest: str
    project_root_manifest_digest: str
    enrollment_epoch: str
    enrollment_state: str


def load_waw_runtime_host_manifest_development_only(
    path: Path = _DEFAULT_PATH, *, expected_uid: int = 0, expected_gid: int
) -> WAWRuntimeHostManifestDevelopmentOnly:
    """Read the legacy synthetic manifest without following links.

    This compatibility reader is retained for existing development fixtures.
    It is not a production bootstrap trust boundary: production callers must
    use :func:`decode_canonical_waw_runtime_host_manifest` on the complete
    ``runtime-host-installation.v1`` bytes before constructing Runtime state.
    """

    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError("WAW host manifest path must be absolute")
    if type(expected_uid) is not int or expected_uid < 0:
        raise ValueError("expected_uid must be a non-negative integer")
    if type(expected_gid) is not int or expected_gid < 0:
        raise ValueError("expected_gid must be a non-negative integer")
    try:
        parent = path.parent
        parent_details = os.lstat(parent)
        if (
            not stat.S_ISDIR(parent_details.st_mode)
            or parent_details.st_uid != expected_uid
            or parent_details.st_gid != expected_gid
            or stat.S_IMODE(parent_details.st_mode) != 0o750
        ):
            raise WAWRuntimeHostManifestDevelopmentOnlyError(
                "WAW host manifest parent provenance is invalid"
            )
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except (OSError, ValueError) as exc:
        raise WAWRuntimeHostManifestDevelopmentOnlyError(
            "WAW host manifest is unavailable"
        ) from exc
    try:
        first = os.fstat(fd)
        if (
            not stat.S_ISREG(first.st_mode)
            or first.st_uid != expected_uid
            or first.st_gid != expected_gid
            or stat.S_IMODE(first.st_mode) != 0o440
            or first.st_size > _MAX_BYTES
        ):
            raise WAWRuntimeHostManifestDevelopmentOnlyError(
                "WAW host manifest provenance is invalid"
            )
        payload = bytearray()
        while len(payload) <= _MAX_BYTES:
            chunk = os.read(fd, min(8192, _MAX_BYTES + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        if len(payload) > _MAX_BYTES:
            raise WAWRuntimeHostManifestDevelopmentOnlyError("WAW host manifest is too large")
        second = os.fstat(fd)
        if (first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns) != (
            second.st_dev,
            second.st_ino,
            second.st_size,
            second.st_mtime_ns,
        ):
            raise WAWRuntimeHostManifestDevelopmentOnlyError(
                "WAW host manifest changed during read"
            )
    except OSError as exc:
        raise WAWRuntimeHostManifestDevelopmentOnlyError(
            "WAW host manifest cannot be read"
        ) from exc
    finally:
        os.close(fd)
    try:
        value = json.loads(bytes(payload).decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise WAWRuntimeHostManifestDevelopmentOnlyError(
            "WAW host manifest JSON is invalid"
        ) from exc
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "runtime_host_installation_id",
        "runtime_host_installation_revision",
        "host_manifest_digest",
        "project_root_manifest_digest",
        "enrollment_epoch",
        "enrollment_state",
    }:
        raise WAWRuntimeHostManifestDevelopmentOnlyError("WAW host manifest keys are invalid")
    if value["schema_version"] != _SCHEMA:
        raise WAWRuntimeHostManifestDevelopmentOnlyError("WAW host manifest schema is invalid")
    for key in (
        "runtime_host_installation_id",
        "runtime_host_installation_revision",
        "host_manifest_digest",
        "project_root_manifest_digest",
        "enrollment_epoch",
        "enrollment_state",
    ):
        if not isinstance(value[key], str):
            raise WAWRuntimeHostManifestDevelopmentOnlyError("WAW host manifest value is invalid")
    if (
        not _ID.fullmatch(value["runtime_host_installation_id"])
        or not _is_uint64_decimal(value["runtime_host_installation_revision"])
        or not _DIGEST.fullmatch(value["host_manifest_digest"])
        or not _DIGEST.fullmatch(value["project_root_manifest_digest"])
        or not _is_uint64_decimal(value["enrollment_epoch"])
        or value["enrollment_state"] not in _STATES
        or value["runtime_host_installation_id"] == "wri_" + "0" * 32
    ):
        raise WAWRuntimeHostManifestDevelopmentOnlyError("WAW host manifest value is invalid")
    canonical = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "ascii"
    )
    if bytes(payload) != canonical:
        raise WAWRuntimeHostManifestDevelopmentOnlyError("WAW host manifest is not canonical")
    return WAWRuntimeHostManifestDevelopmentOnly(
        runtime_host_installation_id=value["runtime_host_installation_id"],
        runtime_host_installation_revision=value["runtime_host_installation_revision"],
        host_manifest_digest=value["host_manifest_digest"],
        project_root_manifest_digest=value["project_root_manifest_digest"],
        enrollment_epoch=value["enrollment_epoch"],
        enrollment_state=value["enrollment_state"],
    )


def decode_canonical_waw_runtime_host_manifest(raw: bytes) -> StrictRuntimeHostManifest:
    """Decode the complete canonical Runtime host manifest data record.

    The returned dataclass is produced only after the strict codec has checked
    the closed schema, value grammar, and canonical RFC 8785 representation.
    This is data validation only, not host provenance or attestation; the
    caller must establish those gates separately.  No file discovery or
    secrets are involved.
    """

    try:
        return decode_runtime_host_manifest(raw)
    except WAWManifestCodecError as exc:
        raise WAWRuntimeHostManifestError(
            "WAW Runtime host manifest codec validation failed"
        ) from exc


def decode_canonical_waw_runtime_host_manifest_v2(raw: bytes) -> StrictRuntimeHostManifestV2:
    """Decode only the production Runtime host manifest v2 schema.

    This explicit entry point is the downgrade fence for R10 production
    composition.  The separate v1 decoder remains available only so existing
    stored records and development tests can be inspected during migration.
    """

    try:
        return decode_runtime_host_manifest_v2(raw)
    except WAWManifestCodecError as exc:
        raise WAWRuntimeHostManifestError(
            "WAW Runtime host manifest v2 codec validation failed"
        ) from exc


def _directory_provenance(
    details: os.stat_result,
    *,
    expected_uid: int,
    expected_gid: int,
    expected_mode: int | None,
    require_expected_owner: bool = False,
) -> None:
    """Reject a directory that is not an installer-owned traversal anchor."""

    if not stat.S_ISDIR(details.st_mode):
        raise WAWRuntimeHostManifestError("WAW manifest ancestor is not a directory")
    owner_is_expected = details.st_uid == expected_uid and details.st_gid == expected_gid
    owner_is_root = details.st_uid == 0 and details.st_gid == 0
    if (require_expected_owner and not owner_is_expected) or (
        not require_expected_owner and not (owner_is_expected or owner_is_root)
    ):
        raise WAWRuntimeHostManifestError("WAW manifest ancestor owner is invalid")
    mode = stat.S_IMODE(details.st_mode)
    # Ancestors must never be group/other writable, even when synthetic tests
    # use a platform-specific mode.  An exact mode can additionally be
    # requested for a test or a tightly controlled host installation.
    if mode & ~0o777 or mode & 0o022:
        raise WAWRuntimeHostManifestError("WAW manifest ancestor mode is unsafe")
    if expected_mode is not None and mode != expected_mode:
        raise WAWRuntimeHostManifestError("WAW manifest ancestor mode is invalid")


def _validate_loader_argument(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise WAWRuntimeHostManifestError(f"{name} is invalid")
    return value


def _open_ancestor_chain(
    path: Path,
    *,
    expected_uid: int,
    expected_gid: int,
    expected_ancestor_mode: int | None,
    expected_parent_mode: int,
    trusted_root: Path | None,
) -> tuple[int, str]:
    """Open every path component with ``O_NOFOLLOW`` and return parent/name.

    Descriptor-relative traversal makes the provenance check and final open
    refer to the same directory objects; a later pathname replacement cannot
    redirect the read to a different tree.
    """

    if not path.is_absolute() or (trusted_root is not None and not trusted_root.is_absolute()):
        raise WAWRuntimeHostManifestError("WAW manifest path must be absolute")
    if trusted_root is not None:
        try:
            relative = os.path.relpath(path, trusted_root)
        except ValueError as exc:
            raise WAWRuntimeHostManifestError("WAW manifest path is invalid") from exc
        if (
            relative == os.curdir
            or relative == os.pardir
            or relative.startswith(os.pardir + os.sep)
        ):
            raise WAWRuntimeHostManifestError("WAW manifest is outside trusted root")
        components = Path(relative).parts
    else:
        components = path.parts
        if not components or components[0] != "/" or len(components) < 2:
            raise WAWRuntimeHostManifestError("WAW manifest path must be absolute")
    try:
        if trusted_root is None:
            current_fd = os.open("/", _DIRECTORY_FLAGS)
        else:
            root_details = os.lstat(trusted_root)
            _directory_provenance(
                root_details,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
                expected_mode=expected_ancestor_mode,
            )
            current_fd = os.open(trusted_root, _DIRECTORY_FLAGS | os.O_NOFOLLOW)
            opened_root = os.fstat(current_fd)
            if any(
                getattr(root_details, field) != getattr(opened_root, field)
                for field in ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid")
            ):
                raise WAWRuntimeHostManifestError("WAW manifest root changed during open")
    except OSError as exc:
        raise WAWRuntimeHostManifestError("WAW manifest root is unavailable") from exc
    try:
        # The host root itself is an OS boundary rather than an installer-owned
        # manifest directory, so validate all descendants while allowing its
        # normal 0755 mode.  Every opened component is still O_NOFOLLOW.
        start = 1 if trusted_root is None else 0
        directory_components = components[start:-1]
        if not directory_components and trusted_root is not None:
            # A trusted root may itself be the manifest's parent.  It still
            # requires the exact final-parent owner/mode pin; otherwise a
            # caller could provide a merely safe but unintended directory.
            _directory_provenance(
                os.fstat(current_fd),
                expected_uid=expected_uid,
                expected_gid=expected_gid,
                expected_mode=expected_parent_mode,
                require_expected_owner=True,
            )
        for index, component in enumerate(directory_components):
            if component in {"", ".", ".."}:
                raise WAWRuntimeHostManifestError("WAW manifest path is invalid")
            next_fd = os.open(component, _DIRECTORY_FLAGS | os.O_NOFOLLOW, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
            details = os.fstat(current_fd)
            _directory_provenance(
                details,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
                expected_mode=(
                    expected_parent_mode
                    if index == len(directory_components) - 1
                    else expected_ancestor_mode
                ),
                require_expected_owner=index == len(directory_components) - 1,
            )
        return current_fd, components[-1]
    except (OSError, ValueError, WAWRuntimeHostManifestError) as exc:
        with suppress(OSError):
            os.close(current_fd)
        if isinstance(exc, WAWRuntimeHostManifestError):
            raise
        raise WAWRuntimeHostManifestError("WAW manifest ancestor cannot be opened") from exc


def _load_canonical_waw_runtime_host_manifest(
    path: Path,
    *,
    expected_uid: int = 0,
    expected_gid: int,
    expected_ancestor_mode: int | None = None,
    expected_parent_mode: int = 0o750,
    expected_file_mode: int = 0o440,
    expected_max_bytes: int = _MAX_BYTES,
    expected_host_manifest_digest: str,
    require_v2: bool,
    trusted_root: Path | None = None,
) -> StrictRuntimeHostManifest | StrictRuntimeHostManifestV2:
    """Read and verify an installer-owned canonical Runtime host manifest.

    The file is opened only through descriptor-relative, ``O_NOFOLLOW``
    traversal.  Every directory in the selected path, the regular file, and
    both pre/post-read ``fstat`` snapshots are checked before strict codec
    decoding.  The caller supplies the external installer anchor digest; it
    is compared in constant time to the digest of the bytes actually read.
    All read, provenance, codec, and digest failures are normalized to
    :class:`WAWRuntimeHostManifestError`.  This function never returns the
    legacy development-only dataclass.

    ``expected_ancestor_mode`` is optional because ordinary production
    ancestors commonly use different safe modes (for example 0755 and 0750).
    Passing it is useful for synthetic fixtures that want an exact mode for
    every descendant directory.
    """

    try:
        if not isinstance(path, Path) or not path.is_absolute():
            raise WAWRuntimeHostManifestError("WAW manifest path must be absolute")
        if trusted_root is not None and (
            not isinstance(trusted_root, Path) or not trusted_root.is_absolute()
        ):
            raise WAWRuntimeHostManifestError("trusted_root must be absolute")
        uid = _validate_loader_argument(expected_uid, "expected_uid")
        gid = _validate_loader_argument(expected_gid, "expected_gid")
        file_mode = _validate_loader_argument(expected_file_mode, "expected_file_mode")
        parent_mode = _validate_loader_argument(expected_parent_mode, "expected_parent_mode")
        max_bytes = _validate_loader_argument(expected_max_bytes, "expected_max_bytes")
        if max_bytes == 0 or max_bytes > _MAX_BYTES:
            raise WAWRuntimeHostManifestError("expected_max_bytes is invalid")
        if expected_ancestor_mode is not None:
            _validate_loader_argument(expected_ancestor_mode, "expected_ancestor_mode")
            if expected_ancestor_mode & ~0o777:
                raise WAWRuntimeHostManifestError("expected_ancestor_mode is invalid")
            if expected_ancestor_mode & 0o022:
                raise WAWRuntimeHostManifestError("expected_ancestor_mode is unsafe")
        if expected_parent_mode & ~0o777 or expected_parent_mode & 0o022:
            raise WAWRuntimeHostManifestError("expected_parent_mode is unsafe")
        if expected_file_mode & ~0o777 or expected_file_mode & 0o222:
            raise WAWRuntimeHostManifestError("expected_file_mode is unsafe")
        if (
            not isinstance(expected_host_manifest_digest, str)
            or _DIGEST.fullmatch(expected_host_manifest_digest) is None
            or expected_host_manifest_digest == "0" * 64
        ):
            raise WAWRuntimeHostManifestError("expected host manifest digest is invalid")
        parent_fd, filename = _open_ancestor_chain(
            path,
            expected_uid=uid,
            expected_gid=gid,
            expected_ancestor_mode=expected_ancestor_mode,
            expected_parent_mode=parent_mode,
            trusted_root=trusted_root,
        )
    except WAWRuntimeHostManifestError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise WAWRuntimeHostManifestError("WAW manifest provenance is unavailable") from exc

    fd: int | None = None
    try:
        fd = os.open(filename, _OPEN_FLAGS | os.O_NOFOLLOW, dir_fd=parent_fd)
        first = os.fstat(fd)
        if (
            not stat.S_ISREG(first.st_mode)
            or first.st_uid != uid
            or first.st_gid != gid
            or stat.S_IMODE(first.st_mode) != file_mode
            or first.st_size < 0
            or first.st_size > max_bytes
        ):
            raise WAWRuntimeHostManifestError("WAW manifest file provenance is invalid")
        payload = bytearray()
        while len(payload) <= max_bytes:
            chunk = os.read(fd, min(8192, max_bytes + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        if len(payload) > max_bytes:
            raise WAWRuntimeHostManifestError("WAW manifest is too large")
        second = os.fstat(fd)
        provenance_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_uid",
            "st_gid",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if any(getattr(first, field) != getattr(second, field) for field in provenance_fields):
            raise WAWRuntimeHostManifestError("WAW manifest changed during read")
    except WAWRuntimeHostManifestError:
        raise
    except OSError as exc:
        raise WAWRuntimeHostManifestError("WAW manifest cannot be read") from exc
    finally:
        if fd is not None:
            with suppress(OSError):
                os.close(fd)
        with suppress(OSError):
            os.close(parent_fd)

    raw = bytes(payload)
    try:
        manifest = (
            decode_runtime_host_manifest_v2(raw)
            if require_v2
            else decode_runtime_host_manifest(raw)
        )
        actual_digest = hashlib.sha256(raw).hexdigest()
        if not hmac.compare_digest(actual_digest, expected_host_manifest_digest):
            raise WAWRuntimeHostManifestError("WAW manifest digest mismatch")
        return manifest
    except WAWRuntimeHostManifestError:
        raise
    except WAWManifestCodecError as exc:
        raise WAWRuntimeHostManifestError(
            "WAW Runtime host manifest v2 codec validation failed"
            if require_v2
            else "WAW Runtime host manifest codec validation failed"
        ) from exc
    except (TypeError, ValueError) as exc:
        raise WAWRuntimeHostManifestError("WAW Runtime host manifest validation failed") from exc


def load_canonical_waw_runtime_host_manifest(
    path: Path = _DEFAULT_PATH,
    *,
    expected_uid: int = 0,
    expected_gid: int,
    expected_ancestor_mode: int | None = None,
    expected_parent_mode: int = 0o750,
    expected_file_mode: int = 0o440,
    expected_max_bytes: int = _MAX_BYTES,
    expected_host_manifest_digest: str,
    trusted_root: Path | None = None,
) -> StrictRuntimeHostManifest:
    """Load the compatibility v1 record; production R10 must call the v2 loader."""

    result = _load_canonical_waw_runtime_host_manifest(
        path,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        expected_ancestor_mode=expected_ancestor_mode,
        expected_parent_mode=expected_parent_mode,
        expected_file_mode=expected_file_mode,
        expected_max_bytes=expected_max_bytes,
        expected_host_manifest_digest=expected_host_manifest_digest,
        require_v2=False,
        trusted_root=trusted_root,
    )
    if type(result) is not StrictRuntimeHostManifest:
        raise WAWRuntimeHostManifestError("WAW Runtime host manifest schema dispatch failed")
    return result


def load_canonical_waw_runtime_host_manifest_v2(
    path: Path = _DEFAULT_V2_PATH,
    *,
    expected_uid: int = 0,
    expected_gid: int,
    expected_ancestor_mode: int | None = None,
    expected_parent_mode: int = 0o750,
    expected_file_mode: int = 0o440,
    expected_max_bytes: int = _MAX_BYTES,
    expected_host_manifest_digest: str,
    trusted_root: Path | None = None,
) -> StrictRuntimeHostManifestV2:
    """Load the installer-owned v2 record and reject every v1 downgrade."""

    result = _load_canonical_waw_runtime_host_manifest(
        path,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        expected_ancestor_mode=expected_ancestor_mode,
        expected_parent_mode=expected_parent_mode,
        expected_file_mode=expected_file_mode,
        expected_max_bytes=expected_max_bytes,
        expected_host_manifest_digest=expected_host_manifest_digest,
        require_v2=True,
        trusted_root=trusted_root,
    )
    if type(result) is not StrictRuntimeHostManifestV2:
        raise WAWRuntimeHostManifestError("WAW Runtime host manifest v2 schema dispatch failed")
    return result


def _load_canonical_waw_bundle_files(
    directory: Path,
    *,
    filenames: tuple[str, ...],
    require_exact_set: bool,
    expected_uid: int = 0,
    expected_gid: int,
    expected_ancestor_mode: int | None = None,
    expected_directory_mode: int = 0o750,
    expected_file_mode: int = 0o440,
    expected_max_bytes: int = _MAX_BYTES,
) -> tuple[bytes, ...]:
    """Read fixed files from one installer-owned descriptor-held directory.

    The directory is opened once through the existing descriptor-relative
    ``O_NOFOLLOW`` traversal.  Each fixed filename is then opened relative to
    that same directory descriptor and checked for regular-file type,
    installer ownership, exact mode, bounded size, and stable pre/post-read
    provenance.  No caller-provided filename is accepted, so traversal and
    symlink substitution are rejected before codec/bootstrap verification.

    This function establishes non-secret filesystem provenance only; it does
    not decode records, consume an enrollment epoch, execute commands, or
    start Runtime services.
    """

    if not isinstance(directory, Path) or not directory.is_absolute():
        raise WAWRuntimeHostManifestError("WAW manifest bundle directory must be absolute")
    uid = _validate_loader_argument(expected_uid, "expected_uid")
    gid = _validate_loader_argument(expected_gid, "expected_gid")
    directory_mode = _validate_loader_argument(expected_directory_mode, "expected_directory_mode")
    file_mode = _validate_loader_argument(expected_file_mode, "expected_file_mode")
    max_bytes = _validate_loader_argument(expected_max_bytes, "expected_max_bytes")
    if max_bytes == 0 or max_bytes > _MAX_BYTES:
        raise WAWRuntimeHostManifestError("expected_max_bytes is invalid")
    if directory_mode & ~0o777 or directory_mode & 0o022:
        raise WAWRuntimeHostManifestError("expected_directory_mode is unsafe")
    if expected_ancestor_mode is not None:
        _validate_loader_argument(expected_ancestor_mode, "expected_ancestor_mode")
        if expected_ancestor_mode & ~0o777 or expected_ancestor_mode & 0o022:
            raise WAWRuntimeHostManifestError("expected_ancestor_mode is unsafe")
    if file_mode & ~0o777 or file_mode & 0o222:
        raise WAWRuntimeHostManifestError("expected_file_mode is unsafe")

    # Use the strict existing traversal to establish the directory descriptor
    # and its exact final-parent provenance.  The placeholder name is never
    # opened; all actual reads below use fixed basenames and dir_fd.
    directory_fd, _ = _open_ancestor_chain(
        directory / filenames[0],
        expected_uid=uid,
        expected_gid=gid,
        expected_ancestor_mode=expected_ancestor_mode,
        expected_parent_mode=directory_mode,
        trusted_root=directory,
    )
    try:
        parent_before = os.fstat(directory_fd)
        _directory_provenance(
            parent_before,
            expected_uid=uid,
            expected_gid=gid,
            expected_mode=directory_mode,
            require_expected_owner=True,
        )
        if require_exact_set:
            observed_names = os.listdir(directory_fd)
            if len(observed_names) != len(filenames) or set(observed_names) != set(filenames):
                raise WAWRuntimeHostManifestError(
                    "WAW manifest bundle directory file set is not exact"
                )
        payloads: list[bytes] = []
        for filename in filenames:
            fd: int | None = None
            try:
                fd = os.open(
                    filename,
                    _OPEN_FLAGS | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=directory_fd,
                )
                first = os.fstat(fd)
                if (
                    not stat.S_ISREG(first.st_mode)
                    or first.st_uid != uid
                    or first.st_gid != gid
                    or stat.S_IMODE(first.st_mode) != file_mode
                    or first.st_size < 0
                    or first.st_size > max_bytes
                ):
                    raise WAWRuntimeHostManifestError(
                        f"WAW manifest bundle file provenance is invalid: {filename}"
                    )
                payload = bytearray()
                while len(payload) <= max_bytes:
                    chunk = os.read(fd, min(8192, max_bytes + 1 - len(payload)))
                    if not chunk:
                        break
                    payload.extend(chunk)
                if len(payload) > max_bytes:
                    raise WAWRuntimeHostManifestError(
                        f"WAW manifest bundle file is too large: {filename}"
                    )
                second = os.fstat(fd)
                file_fields = (
                    "st_dev",
                    "st_ino",
                    "st_mode",
                    "st_uid",
                    "st_gid",
                    "st_size",
                    "st_mtime_ns",
                    "st_ctime_ns",
                )
                if any(getattr(first, field) != getattr(second, field) for field in file_fields):
                    raise WAWRuntimeHostManifestError(
                        f"WAW manifest bundle file changed during read: {filename}"
                    )
                payloads.append(bytes(payload))
            except WAWRuntimeHostManifestError:
                raise
            except OSError as exc:
                raise WAWRuntimeHostManifestError(
                    f"WAW manifest bundle file cannot be read: {filename}"
                ) from exc
            finally:
                if fd is not None:
                    with suppress(OSError):
                        os.close(fd)
        parent_after = os.fstat(directory_fd)
        parent_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_uid",
            "st_gid",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if any(
            getattr(parent_before, field) != getattr(parent_after, field) for field in parent_fields
        ):
            raise WAWRuntimeHostManifestError("WAW manifest bundle directory changed during read")
    except WAWRuntimeHostManifestError:
        raise
    except OSError as exc:
        raise WAWRuntimeHostManifestError("WAW manifest bundle cannot be read") from exc
    finally:
        with suppress(OSError):
            os.close(directory_fd)
    return tuple(payloads)


def load_canonical_waw_manifest_bundle(
    directory: Path = _DEFAULT_BUNDLE_DIRECTORY,
    *,
    expected_uid: int = 0,
    expected_gid: int,
    expected_ancestor_mode: int | None = None,
    expected_directory_mode: int = 0o750,
    expected_file_mode: int = 0o440,
    expected_max_bytes: int = _MAX_BYTES,
) -> WAWCanonicalManifestBundle:
    """Read the compatibility v1 four-file bundle without changing its behavior."""

    payloads = _load_canonical_waw_bundle_files(
        directory,
        filenames=_BUNDLE_FILENAMES,
        require_exact_set=False,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        expected_ancestor_mode=expected_ancestor_mode,
        expected_directory_mode=expected_directory_mode,
        expected_file_mode=expected_file_mode,
        expected_max_bytes=expected_max_bytes,
    )
    return WAWCanonicalManifestBundle(*payloads)


def load_canonical_waw_manifest_bundle_v2(
    directory: Path = _DEFAULT_PUBLIC_V2_DIRECTORY,
    *,
    expected_uid: int = 0,
    expected_gid: int = 0,
    expected_ancestor_mode: int | None = None,
    expected_directory_mode: int = 0o755,
    expected_file_mode: int = 0o444,
    expected_max_bytes: int = _MAX_BYTES,
) -> WAWCanonicalManifestBundleV2:
    """Read the exact public v2 artifact set with descriptor-held provenance."""

    payloads = _load_canonical_waw_bundle_files(
        directory,
        filenames=WAW_PUBLIC_MANIFEST_FILENAMES_V2,
        require_exact_set=True,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        expected_ancestor_mode=expected_ancestor_mode,
        expected_directory_mode=expected_directory_mode,
        expected_file_mode=expected_file_mode,
        expected_max_bytes=expected_max_bytes,
    )
    return WAWCanonicalManifestBundleV2(*payloads)


def load_verified_canonical_waw_manifest_bundle_v2(
    runtime_manifest_path: Path = _DEFAULT_V2_PATH,
    public_directory: Path = _DEFAULT_PUBLIC_V2_DIRECTORY,
    *,
    expected_runtime_uid: int = 0,
    expected_runtime_gid: int,
    expected_public_uid: int = 0,
    expected_public_gid: int = 0,
    runtime_trusted_root: Path | None = None,
    expected_runtime_parent_mode: int = 0o750,
    expected_runtime_file_mode: int = 0o440,
    expected_public_directory_mode: int = 0o755,
    expected_public_file_mode: int = 0o444,
    expected_max_bytes: int = _MAX_BYTES,
) -> CrossManifestPinV2:
    """Load both v2 trust roots and return only a completely cross-pinned bundle."""

    bundle = load_canonical_waw_manifest_bundle_v2(
        public_directory,
        expected_uid=expected_public_uid,
        expected_gid=expected_public_gid,
        expected_directory_mode=expected_public_directory_mode,
        expected_file_mode=expected_public_file_mode,
        expected_max_bytes=expected_max_bytes,
    )
    try:
        anchor = decode_api_host_anchor_v2(bundle.api_host_anchor)
    except WAWManifestCodecError as exc:
        raise WAWRuntimeHostManifestError("WAW API host anchor v2 is invalid") from exc
    runtime = load_canonical_waw_runtime_host_manifest_v2(
        runtime_manifest_path,
        expected_uid=expected_runtime_uid,
        expected_gid=expected_runtime_gid,
        expected_parent_mode=expected_runtime_parent_mode,
        expected_file_mode=expected_runtime_file_mode,
        expected_max_bytes=expected_max_bytes,
        expected_host_manifest_digest=anchor.host_manifest_digest,
        trusted_root=runtime_trusted_root,
    )
    try:
        return verify_api_host_anchor_v2_cross_manifest(
            anchor,
            runtime,
            bundle.project_root,
            bundle.cgroup_delegation,
            bundle.executable_inventory,
            bundle.interactive_profiles,
            bundle.tmux_config,
            bundle.sandbox_policy_bundle,
            bundle.socket_policy,
            bundle.claude_managed_policy,
            bundle.codex_managed_policy,
            bundle.codex_requirements_policy,
            bundle.codex_managed_config_policy,
        )
    except WAWManifestCodecError as exc:
        raise WAWRuntimeHostManifestError("WAW manifest v2 cross-pin validation failed") from exc


__all__ = [
    "WAWCanonicalManifestBundle",
    "WAWCanonicalManifestBundleV2",
    "WAW_PUBLIC_MANIFEST_FILENAMES_V2",
    "WAWRuntimeHostManifestError",
    "decode_canonical_waw_runtime_host_manifest",
    "decode_canonical_waw_runtime_host_manifest_v2",
    "load_canonical_waw_manifest_bundle",
    "load_canonical_waw_manifest_bundle_v2",
    "load_canonical_waw_runtime_host_manifest",
    "load_canonical_waw_runtime_host_manifest_v2",
    "load_verified_canonical_waw_manifest_bundle_v2",
]
