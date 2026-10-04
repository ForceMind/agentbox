"""Descriptor-held Project/Git provenance for the internal staged reader.

This module opens no Git process and returns no file or patch bytes. It
checks fixed nodes and a bounded local object inventory; it is not a
browser or API content authorization.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from types import TracebackType

from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.project import validate_project_id

_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_DIRECTORIES = ("root", "project", "git", "objects", "info", "pack")
_FILES = ("index", "config", "head")
_MAX_OBJECT_NODES = 20_000
_MAX_OBJECT_DEPTH = 4


def _unsafe() -> RuntimeOperationError:
    return RuntimeOperationError(
        "GIT_CONTENT_ROOT_UNSAFE",
        "Git content repository provenance is unsafe",
        category="forbidden",
    )


def _unavailable() -> RuntimeOperationError:
    return RuntimeOperationError(
        "GIT_CONTENT_ROOT_UNAVAILABLE",
        "Git content repository is unavailable",
        category="unavailable",
    )


def _identity(details: os.stat_result, *, file: bool) -> tuple[int, ...]:
    return (
        details.st_dev,
        details.st_ino,
        details.st_uid,
        details.st_gid,
        details.st_mode,
        *((details.st_size, details.st_mtime_ns, details.st_ctime_ns) if file else ()),
    )


def _validate(details: os.stat_result, *, file: bool, uid: int, gid: int) -> None:
    kind_ok = stat.S_ISREG(details.st_mode) if file else stat.S_ISDIR(details.st_mode)
    if (
        not kind_ok
        or details.st_uid != uid
        or details.st_gid != gid
        or details.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        or (file and details.st_nlink != 1)
    ):
        raise _unsafe()


def _open(parent: int | None, name: str | Path, *, file: bool) -> int:
    try:
        if parent is None:
            return os.open(name, _FILE_FLAGS if file else _DIRECTORY_FLAGS)
        return os.open(name, _FILE_FLAGS if file else _DIRECTORY_FLAGS, dir_fd=parent)
    except OSError as exc:
        raise _unavailable() from exc


def _named(parent: int | None, name: str | Path) -> os.stat_result:
    try:
        if parent is None:
            return os.stat(name, follow_symlinks=False)
        return os.stat(name, dir_fd=parent, follow_symlinks=False)
    except OSError as exc:
        raise _unavailable() from exc


class GitContentRoot:
    """Hold and recheck one same-owner, nonsymlink, nonshared Git repository.

    No descriptor is returned to an API or browser caller. The internal
    staged reader may lend the held Project descriptor only to the fixed
    child-cwd runner. Construction alone authorizes no Git execution or read.
    """

    def __init__(
        self,
        *,
        root_path: Path,
        relative_key: str,
        expected_uid: int,
        expected_gid: int,
    ) -> None:
        if (
            not root_path.is_absolute()
            or root_path == Path("/")
            or ".." in root_path.parts
            or type(expected_uid) is not int
            or type(expected_gid) is not int
            or expected_uid < 0
            or expected_gid < 0
        ):
            raise _unsafe()
        try:
            validate_project_id(relative_key)
        except RuntimeOperationError as exc:
            raise _unsafe() from exc
        self._root_path = root_path
        self._relative_key = relative_key
        self._uid = expected_uid
        self._gid = expected_gid
        self._fds: dict[str, int] = {}
        self._identities: dict[str, tuple[int, ...]] = {}
        self._object_snapshot: tuple[tuple[str, tuple[int, ...]], ...] = ()
        try:
            self._take("root", None, root_path)
            self._take("project", "root", relative_key)
            self._take("git", "project", ".git")
            self._take("objects", "git", "objects")
            self._take("info", "objects", "info")
            self._take("pack", "objects", "pack")
            self._take("index", "git", "index", file=True)
            self._take("config", "git", "config", file=True)
            self._take("head", "git", "HEAD", file=True)
            self._object_snapshot = self._scan_objects()
            self.revalidate()
        except BaseException:
            self.close()
            raise

    @property
    def project_path(self) -> Path:
        """Named Project path for rechecking a descriptor-bound child cwd."""

        return self._root_path / self._relative_key

    def _take(
        self, role: str, parent_role: str | None, name: str | Path, *, file: bool = False
    ) -> None:
        parent = self._fds[parent_role] if parent_role is not None else None
        descriptor = _open(parent, name, file=file)
        self._fds[role] = descriptor
        try:
            details = os.fstat(descriptor)
        except OSError as exc:
            raise _unavailable() from exc
        _validate(details, file=file, uid=self._uid, gid=self._gid)
        named = _named(parent, name)
        _validate(named, file=file, uid=self._uid, gid=self._gid)
        identity = _identity(details, file=file)
        if identity != _identity(named, file=file):
            raise _unsafe()
        self._identities[role] = identity

    def _check_absent(self, parent_role: str, name: str) -> None:
        try:
            os.stat(name, dir_fd=self._fds[parent_role], follow_symlinks=False)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise _unavailable() from exc
        raise _unsafe()

    def _scan_objects(self) -> tuple[tuple[str, tuple[int, ...]], ...]:
        """Snapshot bounded local object nodes without following any symlink.

        This checks provenance, not object bytes. A later reader must still
        double-observe its selected patch and discard output on any drift.
        """

        observed: list[tuple[str, tuple[int, ...]]] = []

        def visit(directory_fd: int, prefix: str, depth: int) -> None:
            if depth > _MAX_OBJECT_DEPTH:
                raise _unsafe()
            try:
                with os.scandir(directory_fd) as iterator:
                    names: list[str] = []
                    for entry in iterator:
                        names.append(entry.name)
                        if len(names) + len(observed) > _MAX_OBJECT_NODES:
                            raise _unavailable()
            except OSError as exc:
                raise _unavailable() from exc
            for name in sorted(names):
                try:
                    details = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except OSError as exc:
                    raise _unavailable() from exc
                regular = stat.S_ISREG(details.st_mode)
                _validate(details, file=regular, uid=self._uid, gid=self._gid)
                path = f"{prefix}/{name}"
                observed.append((path, _identity(details, file=True)))
                if len(observed) > _MAX_OBJECT_NODES:
                    raise _unavailable()
                if not regular:
                    child_fd = _open(directory_fd, name, file=False)
                    try:
                        held = os.fstat(child_fd)
                        if _identity(held, file=True) != _identity(details, file=True):
                            raise _unsafe()
                        visit(child_fd, path, depth + 1)
                    finally:
                        os.close(child_fd)

        visit(self._fds["objects"], "objects", 0)
        return tuple(observed)

    def revalidate(self) -> None:
        """Reject renamed/replaced roots, Git stores, metadata files and alternates."""

        if len(self._fds) != len(_DIRECTORIES) + len(_FILES):
            raise _unavailable()
        names: tuple[tuple[str, str | None, str | Path], ...] = (
            ("root", None, self._root_path),
            ("project", "root", self._relative_key),
            ("git", "project", ".git"),
            ("objects", "git", "objects"),
            ("info", "objects", "info"),
            ("pack", "objects", "pack"),
            ("index", "git", "index"),
            ("config", "git", "config"),
            ("head", "git", "HEAD"),
        )
        for role, parent_role, name in names:
            file = role in _FILES
            parent = self._fds[parent_role] if parent_role is not None else None
            try:
                held = os.fstat(self._fds[role])
            except OSError as exc:
                raise _unavailable() from exc
            named = _named(parent, name)
            _validate(held, file=file, uid=self._uid, gid=self._gid)
            _validate(named, file=file, uid=self._uid, gid=self._gid)
            identity = self._identities[role]
            if _identity(held, file=file) != identity or _identity(named, file=file) != identity:
                raise _unsafe()
        self._check_absent("git", "commondir")
        self._check_absent("info", "alternates")
        self._check_absent("info", "http-alternates")
        if self._scan_objects() != self._object_snapshot:
            raise _unsafe()

    def close(self) -> None:
        while self._fds:
            _, descriptor = self._fds.popitem()
            os.close(descriptor)

    def __enter__(self) -> GitContentRoot:
        try:
            self.revalidate()
            return self
        except BaseException:
            self.close()
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


__all__ = ["GitContentRoot"]
