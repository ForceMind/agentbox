#!/usr/bin/env python3
"""Fail closed when an rc8 dynamic canary reaches a declared evidence surface."""

from __future__ import annotations

import argparse
import base64
import binascii
import io
import json
import os
import re
import stat
import tarfile
import zipfile
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import IO, Any, NoReturn

_SURFACE = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")
_MAX_SURFACES = 64
_MAX_CANARIES = 16
_MAX_CANARY_BYTES = 4096
_MAX_FILES = 100_000
_MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
_MAX_MEMBER_BYTES = 256 * 1024 * 1024
_MAX_ARCHIVE_DEPTH = 4
_CHUNK = 1024 * 1024


class RehearsalCanaryError(RuntimeError):
    """A fixed-surface scan failure that never renders a canary or path."""

    def __init__(self, surface: str) -> None:
        self.surface = surface
        super().__init__(surface)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for name, item in pairs:
        if name in value:
            _fail("canary input")
        value[name] = item
    return value


def _fail(surface: str) -> NoReturn:
    raise RehearsalCanaryError(surface)


class _Budget:
    def __init__(self) -> None:
        self.total = 0
        self.members = 0

    def member(self, surface: str) -> None:
        self.members += 1
        if self.members > _MAX_FILES:
            _fail(surface)

    def consume(self, amount: int, surface: str) -> None:
        if amount < 0 or amount > _MAX_MEMBER_BYTES:
            _fail(surface)
        self.total += amount
        if self.total > _MAX_TOTAL_BYTES:
            _fail(surface)


def canary_forms(canaries: Iterable[bytes]) -> tuple[bytes, ...]:
    """Encode every dynamic canary in forms likely to reach serialized evidence."""

    values = tuple(canaries)
    if not 1 <= len(values) <= _MAX_CANARIES:
        _fail("canary input")
    forms: set[bytes] = set()
    for value in values:
        if type(value) is not bytes or not 16 <= len(value) <= _MAX_CANARY_BYTES:
            _fail("canary input")
        forms.update(
            {
                value,
                value.hex().encode("ascii"),
                value.hex().upper().encode("ascii"),
                base64.b64encode(value),
                base64.urlsafe_b64encode(value),
                base64.b64encode(value).rstrip(b"="),
                base64.urlsafe_b64encode(value).rstrip(b"="),
            }
        )
    return tuple(sorted(forms, key=lambda item: (-len(item), item)))


def read_canary_file(path: Path) -> tuple[bytes, ...]:
    """Read a 0600 legacy list or the typed rc8 payload/key/ticket registry."""

    try:
        details = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(details.st_mode)
            or details.st_size > _MAX_CANARY_BYTES * _MAX_CANARIES * 4
            or details.st_mode & 0o077
        ):
            _fail("canary input")
        value: Any = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    except RehearsalCanaryError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        _fail("canary input")
    if isinstance(value, dict):
        if set(value) != {"schema_version", "canaries"} or value.get("schema_version") != 1:
            _fail("canary input")
        entries = value.get("canaries")
        if not isinstance(entries, list) or len(entries) != 3:
            _fail("canary input")
        typed: dict[str, str] = {}
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"kind", "value_base64"}:
                _fail("canary input")
            kind = entry.get("kind")
            encoded = entry.get("value_base64")
            if kind not in {"payload", "private_key", "ticket"} or not isinstance(encoded, str):
                _fail("canary input")
            if kind in typed:
                _fail("canary input")
            typed[kind] = encoded
        if set(typed) != {"payload", "private_key", "ticket"}:
            _fail("canary input")
        value = [typed["payload"], typed["private_key"], typed["ticket"]]
        try:
            decoded_typed = [
                base64.b64decode(item.encode("ascii"), validate=True) for item in value
            ]
        except (UnicodeError, binascii.Error):
            _fail("canary input")
        if (
            not 16 <= len(decoded_typed[0]) <= _MAX_CANARY_BYTES
            or len(decoded_typed[1]) != 32
            or not decoded_typed[2].startswith(b"wat_")
        ):
            _fail("canary input")
    if not isinstance(value, list):
        _fail("canary input")
    decoded: list[bytes] = []
    for item in value:
        if type(item) is not str:
            _fail("canary input")
        try:
            decoded.append(base64.b64decode(item.encode("ascii"), validate=True))
        except (UnicodeError, binascii.Error):
            _fail("canary input")
    return tuple(decoded)


def _files(
    path: Path,
    forms: tuple[bytes, ...],
    budget: _Budget,
    surface: str,
) -> Iterable[Path]:
    try:
        details = path.lstat()
    except OSError:
        _fail(surface)
    if stat.S_ISLNK(details.st_mode):
        _fail(surface)
    if stat.S_ISREG(details.st_mode):
        budget.member(surface)
        if _contains_text(path.name, forms, surface):
            _fail(surface)
        yield path
        return
    if not stat.S_ISDIR(details.st_mode):
        _fail(surface)
    pending = [path]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name, reverse=True)
        except OSError:
            _fail(surface)
        for entry in entries:
            budget.member(surface)
            try:
                entry_details = entry.stat(follow_symlinks=False)
            except OSError:
                _fail(surface)
            if stat.S_ISLNK(entry_details.st_mode):
                _fail(surface)
            candidate = Path(entry.path)
            if _contains_text(entry.name, forms, surface):
                _fail(surface)
            if stat.S_ISREG(entry_details.st_mode):
                yield candidate
            elif stat.S_ISDIR(entry_details.st_mode):
                pending.append(candidate)
            else:
                _fail(surface)


def _contains_stream(
    stream: IO[bytes], forms: tuple[bytes, ...], budget: _Budget, surface: str
) -> bool:
    tail = b""
    try:
        while True:
            chunk = stream.read(_CHUNK)
            if not chunk:
                return False
            budget.consume(len(chunk), surface)
            combined = tail + chunk
            if any(form in combined for form in forms):
                return True
            tail = combined[-(max(map(len, forms)) - 1) :]
    except RehearsalCanaryError:
        raise
    except OSError:
        _fail(surface)


def _safe_member_name(name: str, surface: str) -> None:
    if not name or "\x00" in name or name.startswith("/"):
        _fail(surface)
    parts = PurePosixPath(name).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        _fail(surface)


def _looks_like_archive(name: str) -> bool:
    lower = name.casefold()
    return lower.endswith((".tar", ".tar.gz", ".tgz", ".zip", ".whl"))


def _contains_bytes(payload: bytes, forms: tuple[bytes, ...]) -> bool:
    return any(form in payload for form in forms)


def _contains_text(value: str, forms: tuple[bytes, ...], surface: str) -> bool:
    try:
        return _contains_bytes(value.encode("utf-8", "strict"), forms)
    except UnicodeError:
        _fail(surface)


def _scan_archive_payload(
    payload: bytes,
    name: str,
    forms: tuple[bytes, ...],
    budget: _Budget,
    surface: str,
    depth: int,
) -> bool:
    if _contains_bytes(payload, forms):
        return True
    if not _looks_like_archive(name):
        return False
    if depth >= _MAX_ARCHIVE_DEPTH:
        _fail(surface)
    buffer = io.BytesIO(payload)
    try:
        if name.casefold().endswith((".zip", ".whl")):
            with zipfile.ZipFile(buffer) as archive:
                return _scan_zip(archive, forms, budget, surface, depth + 1)
        with tarfile.open(fileobj=buffer, mode="r:*") as archive:
            return _scan_tar(archive, forms, budget, surface, depth + 1)
    except (OSError, tarfile.TarError, zipfile.BadZipFile):
        _fail(surface)


def _member_bytes(stream: IO[bytes], budget: _Budget, surface: str) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = stream.read(_CHUNK)
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        budget.consume(len(chunk), surface)
        if total > _MAX_MEMBER_BYTES:
            _fail(surface)
        chunks.append(chunk)


def _scan_tar(
    archive: tarfile.TarFile,
    forms: tuple[bytes, ...],
    budget: _Budget,
    surface: str,
    depth: int,
) -> bool:
    members = archive.getmembers()
    for member in members:
        budget.member(surface)
        _safe_member_name(member.name, surface)
        if (
            _contains_text(member.name, forms, surface)
            or _contains_text(member.linkname, forms, surface)
            or any(
                _contains_text(name, forms, surface) or _contains_text(value, forms, surface)
                for name, value in member.pax_headers.items()
            )
        ):
            return True
        if member.isdir():
            continue
        if (
            not member.isfile()
            or member.issym()
            or member.islnk()
            or member.size > _MAX_MEMBER_BYTES
        ):
            _fail(surface)
        stream = archive.extractfile(member)
        if stream is None:
            _fail(surface)
        with stream:
            if _looks_like_archive(member.name):
                payload = _member_bytes(stream, budget, surface)
                if _scan_archive_payload(payload, member.name, forms, budget, surface, depth):
                    return True
            elif _contains_stream(stream, forms, budget, surface):
                return True
    return False


def _scan_zip(
    archive: zipfile.ZipFile,
    forms: tuple[bytes, ...],
    budget: _Budget,
    surface: str,
    depth: int,
) -> bool:
    if _contains_bytes(archive.comment, forms):
        return True
    members = archive.infolist()
    for member in members:
        budget.member(surface)
        _safe_member_name(member.filename, surface)
        if _contains_text(member.filename, forms, surface) or _contains_bytes(member.extra, forms):
            return True
        mode = (member.external_attr >> 16) & 0o170000
        if stat.S_ISLNK(mode) or member.file_size > _MAX_MEMBER_BYTES:
            _fail(surface)
        if member.is_dir():
            continue
        with archive.open(member) as stream:
            if _looks_like_archive(member.filename):
                payload = _member_bytes(stream, budget, surface)
                if _scan_archive_payload(payload, member.filename, forms, budget, surface, depth):
                    return True
            elif _contains_stream(stream, forms, budget, surface):
                return True
    return False


def _open_regular(path: Path, surface: str) -> IO[bytes]:
    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode):
            _fail(surface)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        after = os.fstat(descriptor)
        if (
            not stat.S_ISREG(after.st_mode)
            or before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
        ):
            os.close(descriptor)
            _fail(surface)
        return os.fdopen(descriptor, "rb")
    except RehearsalCanaryError:
        raise
    except OSError:
        _fail(surface)


def _scan_path(path: Path, forms: tuple[bytes, ...], budget: _Budget, surface: str) -> bool:
    try:
        if _contains_text(path.name, forms, surface):
            return True
        with _open_regular(path, surface) as stream:
            if _looks_like_archive(path.name):
                if path.name.casefold().endswith((".zip", ".whl")):
                    with zipfile.ZipFile(stream) as archive:
                        return _scan_zip(archive, forms, budget, surface, 0)
                with tarfile.open(fileobj=stream, mode="r:*") as archive:
                    return _scan_tar(archive, forms, budget, surface, 0)
            return _contains_stream(stream, forms, budget, surface)
    except RehearsalCanaryError:
        raise
    except (OSError, tarfile.TarError, zipfile.BadZipFile):
        _fail(surface)


def scan_surfaces(surfaces: Mapping[str, Path], canaries: Iterable[bytes]) -> None:
    """Reject a dynamic canary on every exact declared file or directory surface."""

    if not 1 <= len(surfaces) <= _MAX_SURFACES:
        _fail("surface input")
    forms = canary_forms(canaries)
    for surface, root in surfaces.items():
        if (
            type(surface) is not str
            or _SURFACE.fullmatch(surface) is None
            or not isinstance(root, Path)
        ):
            _fail("surface input")
        budget = _Budget()
        for path in _files(root, forms, budget, surface):
            if _scan_path(path, forms, budget, surface):
                _fail(surface)


def _surface_argument(value: str) -> tuple[str, Path]:
    name, separator, path = value.partition("=")
    if separator != "=" or _SURFACE.fullmatch(name) is None or not path:
        raise argparse.ArgumentTypeError("surface must be name=path")
    return name, Path(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canary-file", type=Path, required=True)
    parser.add_argument("--surface", action="append", type=_surface_argument, required=True)
    args = parser.parse_args()
    surfaces: dict[str, Path] = {}
    for name, path in args.surface:
        if name in surfaces:
            parser.exit(2, "rc8 canary scan failed: surface input\n")
        surfaces[name] = path
    try:
        scan_surfaces(surfaces, read_canary_file(args.canary_file))
    except RehearsalCanaryError as exc:
        parser.exit(1, f"rc8 canary scan failed: {exc.surface}\n")
    print(f"rc8 canary scan passed ({len(surfaces)} reviewed surfaces).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
