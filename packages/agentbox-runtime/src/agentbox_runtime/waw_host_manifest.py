"""Fail-closed reader for the non-secret WAW Runtime host manifest.

The manifest is installer-owned.  Runtime may read it, but it never creates,
rewrites, or repairs the file.  A caller must provide the expected Runtime
group because the API and Worker identities must not be able to traverse the
manifest's parent directory.
"""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from agentbox_runtime.waw_manifest_codecs import (
    RuntimeHostManifest as StrictRuntimeHostManifest,
)
from agentbox_runtime.waw_manifest_codecs import (
    WAWManifestCodecError,
    decode_runtime_host_manifest,
)

_DEFAULT_PATH = Path("/var/lib/agentbox-waw/runtime-host-installation.json")
_SCHEMA = "waw-runtime-host-installation-v1"
_MAX_BYTES = 64 * 1024
_MAX_U64 = 2**64 - 1
_ID = re.compile(r"\Awri_[0-9a-f]{32}\Z")
_DECIMAL = re.compile(r"\A[1-9][0-9]{0,19}\Z")
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_STATES = frozenset({"bootstrap", "steady", "rotation"})


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


class WAWRuntimeHostManifestError(RuntimeError):
    """The WAW host manifest is missing, malformed, or unsafe."""


@dataclass(frozen=True)
class WAWRuntimeHostManifest:
    runtime_host_installation_id: str
    runtime_host_installation_revision: str
    host_manifest_digest: str
    project_root_manifest_digest: str
    enrollment_epoch: str
    enrollment_state: str


def load_waw_runtime_host_manifest(
    path: Path = _DEFAULT_PATH, *, expected_uid: int = 0, expected_gid: int
) -> WAWRuntimeHostManifest:
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
            raise WAWRuntimeHostManifestError("WAW host manifest parent provenance is invalid")
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except (OSError, ValueError) as exc:
        raise WAWRuntimeHostManifestError("WAW host manifest is unavailable") from exc
    try:
        first = os.fstat(fd)
        if (
            not stat.S_ISREG(first.st_mode)
            or first.st_uid != expected_uid
            or first.st_gid != expected_gid
            or stat.S_IMODE(first.st_mode) != 0o440
            or first.st_size > _MAX_BYTES
        ):
            raise WAWRuntimeHostManifestError("WAW host manifest provenance is invalid")
        payload = bytearray()
        while len(payload) <= _MAX_BYTES:
            chunk = os.read(fd, min(8192, _MAX_BYTES + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        if len(payload) > _MAX_BYTES:
            raise WAWRuntimeHostManifestError("WAW host manifest is too large")
        second = os.fstat(fd)
        if (first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns) != (
            second.st_dev,
            second.st_ino,
            second.st_size,
            second.st_mtime_ns,
        ):
            raise WAWRuntimeHostManifestError("WAW host manifest changed during read")
    except OSError as exc:
        raise WAWRuntimeHostManifestError("WAW host manifest cannot be read") from exc
    finally:
        os.close(fd)
    try:
        value = json.loads(bytes(payload).decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise WAWRuntimeHostManifestError("WAW host manifest JSON is invalid") from exc
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "runtime_host_installation_id",
        "runtime_host_installation_revision",
        "host_manifest_digest",
        "project_root_manifest_digest",
        "enrollment_epoch",
        "enrollment_state",
    }:
        raise WAWRuntimeHostManifestError("WAW host manifest keys are invalid")
    if value["schema_version"] != _SCHEMA:
        raise WAWRuntimeHostManifestError("WAW host manifest schema is invalid")
    for key in (
        "runtime_host_installation_id",
        "runtime_host_installation_revision",
        "host_manifest_digest",
        "project_root_manifest_digest",
        "enrollment_epoch",
        "enrollment_state",
    ):
        if not isinstance(value[key], str):
            raise WAWRuntimeHostManifestError("WAW host manifest value is invalid")
    if (
        not _ID.fullmatch(value["runtime_host_installation_id"])
        or not _is_uint64_decimal(value["runtime_host_installation_revision"])
        or not _DIGEST.fullmatch(value["host_manifest_digest"])
        or not _DIGEST.fullmatch(value["project_root_manifest_digest"])
        or not _is_uint64_decimal(value["enrollment_epoch"])
        or value["enrollment_state"] not in _STATES
        or value["runtime_host_installation_id"] == "wri_" + "0" * 32
    ):
        raise WAWRuntimeHostManifestError("WAW host manifest value is invalid")
    canonical = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "ascii"
    )
    if bytes(payload) != canonical:
        raise WAWRuntimeHostManifestError("WAW host manifest is not canonical")
    return WAWRuntimeHostManifest(
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


__all__ = [
    "WAWRuntimeHostManifest",
    "WAWRuntimeHostManifestError",
    "decode_canonical_waw_runtime_host_manifest",
    "load_waw_runtime_host_manifest",
]
