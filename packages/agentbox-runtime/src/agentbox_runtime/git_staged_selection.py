"""Runtime-only eligibility check for a staged Git patch selection.

This module returns index metadata, never object or patch bytes. A future
reader must still revalidate the held repository and status snapshot before
and after extracting content; this check is not a content authorization.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from agentbox_runtime.git_changes import parse_git_change_page
from agentbox_runtime.models import RuntimeOperationError

_OID = re.compile(rb"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_REGULAR_MODES = {b"100644", b"100755"}
_PRIVATE_DIRECTORIES = {
    ".agentbox",
    ".git",
    ".ssh",
    ".aws",
    ".azure",
    ".config",
    ".docker",
    ".kube",
    ".gnupg",
    ".pki",
    ".terraform",
    ".codex",
    ".claude",
    "provider-secrets",
}
_PRIVATE_NAMES = {
    ".netrc",
    ".npmrc",
    ".pypirc",
    "credentials",
    "credentials.json",
    "secrets.json",
    "token.json",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "id_dsa",
    "authorized_keys",
}
_PRIVATE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".kdbx", ".tfstate", ".tfstate.backup")


def _reject(code: str) -> RuntimeOperationError:
    category = (
        "forbidden"
        if code in {"PATCH_UNAVAILABLE_PATH", "PATCH_UNAVAILABLE_SENSITIVE_PATH"}
        else (
            "unsupported"
            if code in {"PATCH_UNAVAILABLE_KIND", "PATCH_UNAVAILABLE_MODE"}
            else "unavailable"
        )
    )
    return RuntimeOperationError(code, "Staged patch is unavailable", category=category)


def validate_patch_path(path: str) -> str:
    """Reject credential classes and ambiguous paths before any Git execution."""

    if type(path) is not str or not path:
        raise _reject("PATCH_UNAVAILABLE_PATH")
    try:
        encoded = path.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise _reject("PATCH_UNAVAILABLE_PATH") from exc
    if len(encoded) > 4096:
        raise _reject("PATCH_UNAVAILABLE_PATH")
    if path.startswith(("/", ":(", ":!", ":^")) or "\\" in path:
        raise _reject("PATCH_UNAVAILABLE_PATH")
    parts = path.split("/")
    if any(
        part in {"", ".", ".."} or any(unicodedata.category(char).startswith("C") for char in part)
        for part in parts
    ):
        raise _reject("PATCH_UNAVAILABLE_PATH")
    folded = [part.casefold() for part in parts]
    if any(part in _PRIVATE_DIRECTORIES or part.startswith(".env") for part in folded[:-1]):
        raise _reject("PATCH_UNAVAILABLE_SENSITIVE_PATH")
    name = folded[-1]
    if (
        name in _PRIVATE_DIRECTORIES
        or name.startswith(".env")
        or name in _PRIVATE_NAMES
        or name.endswith(_PRIVATE_SUFFIXES)
    ):
        raise _reject("PATCH_UNAVAILABLE_SENSITIVE_PATH")
    return path


@dataclass(frozen=True)
class StagedSelection:
    path: str
    kind: str
    head_oid: str
    index_oid: str
    head_mode: str
    index_mode: str


def select_staged_change(status: bytes, path: str) -> StagedSelection:
    """Select one eligible tracked regular index entry from complete porcelain v2.

    The caller cannot supply an OID or Git option. The selected path must be
    re-observed from the same descriptor-held repository before content read.
    """

    validate_patch_path(path)
    if type(status) is not bytes or len(status) > 1024 * 1024:
        raise _reject("PATCH_UNAVAILABLE_STATUS")
    # Validate the entire snapshot, including duplicate paths and malformed
    # records, before considering one selected row.
    parse_git_change_page(status, None)
    encoded = path.encode("utf-8")
    selected: StagedSelection | None = None
    for row in status.split(b"\0"):
        if row.startswith(b"2 ") and row.split(b" ", 9)[-1] == encoded:
            raise _reject("PATCH_UNAVAILABLE_KIND")
        if row.startswith(b"u ") and row.split(b" ", 10)[-1] == encoded:
            raise _reject("PATCH_UNAVAILABLE_KIND")
        if row == b"? " + encoded:
            raise _reject("PATCH_UNAVAILABLE_KIND")
        if not row.startswith(b"1 "):
            continue
        fields = row.split(b" ", 8)
        if len(fields) != 9 or fields[8] != encoded:
            continue
        if selected is not None:
            raise _reject("PATCH_UNAVAILABLE_STATUS")
        x = fields[1][:1]
        if x not in {b"M", b"A", b"D"}:
            raise _reject("PATCH_UNAVAILABLE_KIND")
        if fields[2] != b"N...":
            raise _reject("PATCH_UNAVAILABLE_MODE")
        head_mode, index_mode = fields[3:5]
        head_oid, index_oid = fields[6:8]
        if not _OID.fullmatch(head_oid) or not _OID.fullmatch(index_oid):
            raise _reject("PATCH_UNAVAILABLE_STATUS")
        zero = b"0" * len(head_oid)
        if len(head_oid) != len(index_oid):
            raise _reject("PATCH_UNAVAILABLE_STATUS")
        if x == b"A":
            valid = (
                head_mode == b"000000"
                and head_oid == zero
                and index_mode in _REGULAR_MODES
                and index_oid != zero
            )
        elif x == b"D":
            valid = (
                head_mode in _REGULAR_MODES
                and head_oid != zero
                and index_mode == b"000000"
                and index_oid == zero
            )
        else:
            valid = (
                head_mode in _REGULAR_MODES
                and index_mode in _REGULAR_MODES
                and head_oid != zero
                and index_oid != zero
            )
        if not valid:
            raise _reject("PATCH_UNAVAILABLE_MODE")
        selected = StagedSelection(
            path,
            {b"M": "modified", b"A": "added", b"D": "deleted"}[x],
            head_oid.decode("ascii"),
            index_oid.decode("ascii"),
            head_mode.decode("ascii"),
            index_mode.decode("ascii"),
        )
    if selected is None:
        raise RuntimeOperationError("PATCH_STALE", "Staged selection changed", category="conflict")
    return selected


__all__ = ["StagedSelection", "select_staged_change", "validate_patch_path"]
