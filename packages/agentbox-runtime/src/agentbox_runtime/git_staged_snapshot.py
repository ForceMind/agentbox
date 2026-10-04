"""Private staged-only Git inputs; index/config inputs sealed, object inodes held.

No object body is copied or written. The generated directory contains only
fixed configuration, ref metadata and links to Runtime-owned descriptors.
Held object content remains mutable and is revalidated before/after children.
"""

from __future__ import annotations

import fcntl
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

from agentbox_runtime.git_content_root import (
    GitContentRoot,
    _identity,
    _named,
    _open,
    _validate,
)
from agentbox_runtime.models import RuntimeOperationError

# Stable Linux UAPI values (linux/fcntl.h); some Python builds omit names.
_F_ADD_SEALS = 1033
_F_SEALS = 0x0001 | 0x0002 | 0x0004 | 0x0008
_MAX_HELD_FDS = 512
_MAX_OBJECT_FILES = 256
_MAX_OBJECT_BYTES = 64 * 1024 * 1024
_MAX_INDEX_BYTES = 8 * 1024 * 1024
_MAX_METADATA_BYTES = 128 * 1024
_MAX_REF_NODES = 128
_OID = re.compile(rb"[0-9a-f]{40}\n?\Z")
_REF = re.compile(rb"ref: (refs/[A-Za-z0-9_./-]+)\n?\Z")
_LOOSE = re.compile(r"objects/[0-9a-f]{2}/[0-9a-f]{38}\Z")
_PACK = re.compile(r"objects/pack/pack-[0-9a-f]{40}\.(?:pack|idx|rev|bitmap)\Z")


def _unavailable() -> RuntimeOperationError:
    return RuntimeOperationError(
        "PATCH_UNAVAILABLE_REPOSITORY", "Staged Git inputs are unavailable", category="forbidden"
    )


class StagedGitSnapshot:
    """Bounded private Git view, never a caller-controlled filesystem grant."""

    def __init__(self, root: GitContentRoot) -> None:
        self._root = root
        self._fds: list[int] = []
        self._child_fds: list[int] = []
        self._sources: list[tuple[int, int, str, tuple[int, ...]]] = []
        self._absent: list[tuple[int, str]] = []
        self._metadata_bytes = 0
        self._ref_nodes = 0
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        if sys.platform != "linux" or not hasattr(os, "memfd_create"):
            raise _unavailable()
        try:
            self._temporary = tempfile.TemporaryDirectory(prefix="agentbox-staged-")
            self.path = Path(self._temporary.name)
            (self.path / "objects" / "info").mkdir(parents=True)
            (self.path / "objects" / "pack").mkdir()
            (self.path / "refs").mkdir()
            (self.path / "config").write_text(
                "[core]\nrepositoryformatversion = 0\nbare = true\n", encoding="ascii"
            )
            self._write_ref("HEAD", self._read(root._fds["head"], 1024))
            config = self._read(root._fds["config"], _MAX_METADATA_BYTES)
            self._count_metadata(config)
            self.config_fd = self._seal(config)
            index_fd = self._seal(self._read(root._fds["index"], _MAX_INDEX_BYTES))
            (self.path / "index").symlink_to(f"/proc/self/fd/{index_fd}")
            self._copy_refs(root._fds["git"], "refs", "refs", 0)
            packed = self._source(root._fds["git"], "packed-refs", optional=True)
            if packed is not None:
                raw = self._read(packed, _MAX_METADATA_BYTES)
                self._count_metadata(raw)
                for line in raw.splitlines():
                    if line.startswith(b"#") or not line:
                        continue
                    if line.startswith(b"^"):
                        if not _OID.fullmatch(line[1:]):
                            raise _unavailable()
                        continue
                    oid, separator, ref = line.partition(b" ")
                    if not separator or not _OID.fullmatch(oid):
                        raise _unavailable()
                    self._ref_name(ref)
                (self.path / "packed-refs").write_bytes(raw)
            # Shallow boundaries and replacement/alternate storage are not
            # silently dropped from the source repository's interpretation.
            self._require_absent(root._fds["git"], "shallow")
            self._require_absent(root._fds["git"], "config.worktree")
            self._require_absent(root._fds["git"], "reftable")
            info = self._source(root._fds["git"], "info", directory=True, optional=True)
            if info is not None:
                self._require_absent(info, "grafts")
            with os.scandir(root._fds["git"]) as entries:
                for count, entry in enumerate(entries):
                    if count >= 1024 or entry.name.startswith("sharedindex."):
                        raise _unavailable()
            object_count = 0
            object_bytes = 0
            object_names = {name for name, _ in root._object_snapshot}
            for name in object_names:
                if name.endswith(".pack") and name[:-5] + ".idx" not in object_names:
                    raise _unavailable()
                if name.endswith((".idx", ".rev", ".bitmap")) and (
                    name.rsplit(".", 1)[0] + ".pack" not in object_names
                ):
                    raise _unavailable()
            for name, identity in root._object_snapshot:
                if not stat.S_ISREG(identity[4]):
                    continue
                if name in {"objects/info/packs", "objects/info/commit-graph"} or (
                    re.fullmatch(r"objects/pack/pack-[0-9a-f]{40}\.keep", name)
                ):
                    continue
                if not (_LOOSE.fullmatch(name) or _PACK.fullmatch(name)):
                    # Git may interpret promisor/alternate/commit-graph files;
                    # this v1 supports only ordinary SHA-1 loose/pack storage.
                    raise _unavailable()
                object_count += 1
                object_bytes += identity[5]
                if object_count > _MAX_OBJECT_FILES or object_bytes > _MAX_OBJECT_BYTES:
                    raise _unavailable()
                parts = name.split("/")
                parent = root._fds["objects"]
                for part in parts[1:-1]:
                    opened = self._source(parent, part, directory=True)
                    assert opened is not None
                    parent = opened
                source = self._source(parent, parts[-1])
                assert source is not None
                self._child_fds.append(source)
                destination = self.path / name
                destination.parent.mkdir(exist_ok=True)
                destination.symlink_to(f"/proc/self/fd/{source}")
            self.directory_fd = self._hold(
                os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            )
            self.revalidate()
        except BaseException:
            self.close()
            raise

    def _hold(self, fd: int) -> int:
        if len(self._fds) >= _MAX_HELD_FDS:
            os.close(fd)
            raise _unavailable()
        self._fds.append(fd)
        return fd

    def _count_metadata(self, raw: bytes) -> None:
        self._metadata_bytes += len(raw)
        if self._metadata_bytes > _MAX_METADATA_BYTES:
            raise _unavailable()

    @property
    def input_fds(self) -> tuple[int, ...]:
        # Directory FDs are not exposed to the child; only fixed input files.
        return tuple(self._child_fds)

    def _read(self, fd: int, limit: int) -> bytes:
        details = os.fstat(fd)
        if details.st_size > limit:
            raise _unavailable()
        chunks: list[bytes] = []
        offset = 0
        while offset <= limit:
            chunk = os.pread(fd, min(65536, limit + 1 - offset), offset)
            if not chunk:
                break
            chunks.append(chunk)
            offset += len(chunk)
        if offset > limit or _identity(details, file=True) != _identity(os.fstat(fd), file=True):
            raise _unavailable()
        return b"".join(chunks)

    def _seal(self, raw: bytes) -> int:
        fd = self._hold(
            os.memfd_create("agentbox-staged-input", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        )
        self._child_fds.append(fd)
        offset = 0
        while offset < len(raw):
            written = os.write(fd, raw[offset:])
            if written <= 0:
                raise _unavailable()
            offset += written
        fcntl.fcntl(
            fd,
            _F_ADD_SEALS,
            _F_SEALS,
        )
        return fd

    def _source(
        self, parent: int, name: str, *, directory: bool = False, optional: bool = False
    ) -> int | None:
        try:
            named = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            if optional:
                self._absent.append((parent, name))
                return None
            raise _unavailable() from None
        _validate(named, file=not directory, uid=self._root._uid, gid=self._root._gid)
        fd = self._hold(_open(parent, name, file=not directory))
        identity = _identity(named, file=True)
        if _identity(os.fstat(fd), file=True) != identity:
            raise _unavailable()
        self._sources.append((fd, parent, name, identity))
        return fd

    def _require_absent(self, parent: int, name: str) -> None:
        try:
            os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            self._absent.append((parent, name))
            return
        raise _unavailable()

    @staticmethod
    def _ref_name(raw: bytes) -> str:
        try:
            name = raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise _unavailable() from exc
        if (
            not name.startswith("refs/")
            or not re.fullmatch(r"[A-Za-z0-9_./-]+", name)
            or any(part in {"", ".", ".."} or part.endswith(".lock") for part in name.split("/"))
            or ".." in name
        ):
            raise _unavailable()
        return name

    def _write_ref(self, name: str, raw: bytes) -> None:
        self._count_metadata(raw)
        if not _OID.fullmatch(raw):
            match = _REF.fullmatch(raw)
            if match is None:
                raise _unavailable()
            self._ref_name(match.group(1))
        (self.path / name).write_bytes(raw)

    def _copy_refs(self, parent: int, name: str, relative: str, depth: int) -> None:
        if depth > 8:
            raise _unavailable()
        fd = self._source(parent, name, directory=True, optional=depth == 0)
        if fd is None:
            return
        with os.scandir(fd) as entries:
            for entry in entries:
                self._ref_nodes += 1
                if self._ref_nodes > _MAX_REF_NODES:
                    raise _unavailable()
                path = self._ref_name(f"{relative}/{entry.name}".encode())
                if entry.is_dir(follow_symlinks=False):
                    (self.path / path).mkdir()
                    self._copy_refs(fd, entry.name, path, depth + 1)
                else:
                    source = self._source(fd, entry.name)
                    assert source is not None
                    self._write_ref(path, self._read(source, 1024))

    def revalidate(self) -> None:
        self._root.revalidate()
        for fd, parent, name, identity in self._sources:
            if (
                _identity(os.fstat(fd), file=True) != identity
                or _identity(_named(parent, name), file=True) != identity
            ):
                raise _unavailable()
        for parent, name in self._absent:
            try:
                os.stat(name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise _unavailable()

    def close(self) -> None:
        try:
            if self._temporary is not None:
                self._temporary.cleanup()
                self._temporary = None
        finally:
            self._child_fds.clear()
            while self._fds:
                os.close(self._fds.pop())
