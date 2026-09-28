"""Bounded, path-metadata-only parser for fixed Git porcelain-v2 output."""

from __future__ import annotations

import hashlib
import json
import re
from typing import cast

from agentbox_runtime.models import (
    GitChangeEntry,
    GitChangeKind,
    GitChangePage,
    RuntimeOperationError,
)

_PAGE_SIZE = 32
_FRAME_DATA_BUDGET = 48 * 1024
_MAX_PATH_BYTES = 4096
_MAX_ENTRIES = 10_000
_CURSOR = re.compile(r"([0-9a-f]{64}):([1-9][0-9]{0,6})\Z")
_ORDINARY = {"M": "modified", "A": "added", "D": "deleted", "T": "typechanged"}


def _invalid() -> RuntimeOperationError:
    return RuntimeOperationError(
        "GIT_CHANGES_INVALID", "Git change metadata is invalid", category="broken"
    )


def validate_git_changes_cursor(cursor: str | None) -> str | None:
    if cursor is not None and (type(cursor) is not str or _CURSOR.fullmatch(cursor) is None):
        raise RuntimeOperationError(
            "GIT_CHANGES_CURSOR_INVALID", "Git changes cursor is invalid", category="validation"
        )
    return cursor


def _path(raw: bytes) -> str:
    if not raw or len(raw) > _MAX_PATH_BYTES:
        raise _invalid()
    try:
        path = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise _invalid() from exc
    if path.startswith("/") or any(part in {"", ".", ".."} for part in path.split("/")):
        raise _invalid()
    return path


def _status(raw: bytes, *, rename: bool = False) -> tuple[str, str]:
    allowed = b".MADTRC" if rename else b".MADT"
    if len(raw) != 2 or any(value not in allowed for value in raw):
        raise _invalid()
    return chr(raw[0]), chr(raw[1])


def _ordinary_kind(x: str, y: str, sub: bytes) -> GitChangeKind:
    for value in ("D", "A", "T", "M"):
        if value in (x, y):
            return cast(GitChangeKind, _ORDINARY[value])
    if len(sub) == 4 and sub.startswith(b"S") and sub[1:] != b"...":
        return "modified"
    raise _invalid()


def _parse(raw: bytes) -> tuple[GitChangeEntry, ...]:
    if not raw:
        return ()
    records = raw.split(b"\0")
    if records[-1] != b"":
        raise _invalid()
    records.pop()
    entries: list[GitChangeEntry] = []
    seen: set[str] = set()
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if record.startswith(b"1 "):
            fields = record.split(b" ", 8)
            if len(fields) != 9:
                raise _invalid()
            x, y = _status(fields[1])
            sub = fields[2]
            if len(sub) != 4 or sub[:1] not in {b"N", b"S"}:
                raise _invalid()
            path = _path(fields[8])
            entry = GitChangeEntry(
                path,
                None,
                _ordinary_kind(x, y, sub),
                x != ".",
                y != "." or (sub.startswith(b"S") and sub[1:] != b"..."),
            )
        elif record.startswith(b"2 "):
            fields = record.split(b" ", 9)
            if len(fields) != 10 or index >= len(records):
                raise _invalid()
            x, y = _status(fields[1], rename=True)
            score = fields[8]
            if re.fullmatch(rb"[RC][0-9]{1,3}", score) is None:
                raise _invalid()
            path = _path(fields[9])
            previous_path = _path(records[index])
            index += 1
            entry = GitChangeEntry(
                path,
                previous_path,
                "renamed" if score.startswith(b"R") else "copied",
                x != ".",
                y != ".",
            )
        elif record.startswith(b"u "):
            fields = record.split(b" ", 10)
            if len(fields) != 11:
                raise _invalid()
            path = _path(fields[10])
            entry = GitChangeEntry(path, None, "conflicted", False, True)
        elif record.startswith(b"? "):
            path = _path(record[2:])
            entry = GitChangeEntry(path, None, "untracked", False, True)
        else:
            raise _invalid()
        if entry.path in seen:
            raise _invalid()
        seen.add(entry.path)
        entries.append(entry)
        if len(entries) > _MAX_ENTRIES:
            raise RuntimeOperationError(
                "GIT_CHANGES_LIMIT_EXCEEDED",
                "Git change count exceeds the supported bound",
                category="unavailable",
            )
    return tuple(sorted(entries, key=lambda item: item.path))


def parse_git_change_page(raw: bytes, cursor: str | None) -> GitChangePage:
    """Parse and page one complete bounded snapshot; cursor rejects drift."""

    if type(raw) is not bytes:
        raise TypeError("Git status output must be bytes")
    validate_git_changes_cursor(cursor)
    entries = _parse(raw)
    canonical = json.dumps(
        [entry.to_dict() for entry in entries], ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    offset = 0
    if cursor is not None:
        match = _CURSOR.fullmatch(cursor)
        assert match is not None
        if match.group(1) != digest:
            raise RuntimeOperationError(
                "GIT_CHANGES_STALE", "Git changes changed between pages", category="conflict"
            )
        offset = int(match.group(2))
        if offset >= len(entries):
            raise RuntimeOperationError(
                "GIT_CHANGES_CURSOR_INVALID", "Git changes cursor is invalid", category="validation"
            )
    selected: list[GitChangeEntry] = []
    for entry in entries[offset : offset + _PAGE_SIZE]:
        trial = [*selected, entry]
        estimated = len(
            json.dumps(
                [item.to_dict() for item in trial],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        if estimated > _FRAME_DATA_BUDGET:
            if not selected:
                raise RuntimeOperationError(
                    "GIT_CHANGES_PATH_TOO_LARGE",
                    "Git change path exceeds the response budget",
                    category="unavailable",
                )
            break
        selected.append(entry)
    next_offset = offset + len(selected)
    return GitChangePage(
        True,
        tuple(selected),
        len(entries),
        f"{digest}:{next_offset}" if next_offset < len(entries) else None,
    )


__all__ = ["parse_git_change_page", "validate_git_changes_cursor"]
