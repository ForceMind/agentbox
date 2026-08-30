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

_DEFAULT_PATH = Path("/var/lib/agentbox-waw/runtime-host-installation.json")
_SCHEMA = "waw-runtime-host-installation-v1"
_MAX_BYTES = 64 * 1024
_ID = re.compile(r"\Awri_[0-9a-f]{32}\Z")
_DECIMAL = re.compile(r"\A[1-9][0-9]{0,19}\Z")
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_STATES = frozenset({"bootstrap", "steady", "rotation"})


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
    path: Path = _DEFAULT_PATH, *, expected_gid: int
) -> WAWRuntimeHostManifest:
    """Read and validate one installer-owned manifest without following links."""

    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError("WAW host manifest path must be absolute")
    if type(expected_gid) is not int or expected_gid < 0:
        raise ValueError("expected_gid must be a non-negative integer")
    try:
        parent = path.parent
        parent_details = os.lstat(parent)
        if (
            not stat.S_ISDIR(parent_details.st_mode)
            or parent_details.st_uid != 0
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
            or first.st_uid != 0
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
        if (
            (first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns)
            != (second.st_dev, second.st_ino, second.st_size, second.st_mtime_ns)
        ):
            raise WAWRuntimeHostManifestError("WAW host manifest changed during read")
    except OSError as exc:
        raise WAWRuntimeHostManifestError("WAW host manifest cannot be read") from exc
    finally:
        os.close(fd)
    try:
        value = json.loads(bytes(payload).decode("utf-8"))
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
        or not _DECIMAL.fullmatch(value["runtime_host_installation_revision"])
        or not _DIGEST.fullmatch(value["host_manifest_digest"])
        or not _DIGEST.fullmatch(value["project_root_manifest_digest"])
        or not _DECIMAL.fullmatch(value["enrollment_epoch"])
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


__all__ = [
    "WAWRuntimeHostManifest",
    "WAWRuntimeHostManifestError",
    "load_waw_runtime_host_manifest",
]
