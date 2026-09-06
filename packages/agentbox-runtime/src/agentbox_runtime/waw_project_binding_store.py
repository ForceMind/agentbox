"""Descriptor-held Runtime Project binding verification and durable current heads.

The control plane owns the monotonic binding ledger.  Runtime owns the local
filesystem proof and persists the most recently accepted exact binding for each
formal Project so a Runtime restart can reject an impossible revision instead of
inventing a predecessor.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import rfc8785
from agentbox_protocol.waw_control import WAWControlError, validate_relative_key

_PROJECT_ID = re.compile(r"\Aprj_[0-9a-f]{32}\Z")
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_DECIMAL = re.compile(r"\A[1-9][0-9]{0,19}\Z")
_MAX_U64 = 2**64 - 1
_MAX_BINDINGS = 256
_MAX_RECORD_BYTES = 4096
_TEST_ONLY_TOKEN = object()


class WAWProjectBindingStoreError(RuntimeError):
    """Bounded local binding-store failure; details never reach a caller."""


class WAWProjectBindingVerifierError(RuntimeError):
    """A Project root/path identity cannot support a WAW binding."""


@dataclass(frozen=True)
class WAWDurableProjectBinding:
    project_id: str
    relative_key: str
    project_revision: str
    binding_revision: str
    binding_digest: str
    previous_binding_revision: str | None
    previous_binding_digest: str | None
    runtime_host_installation_id: str
    runtime_host_installation_revision: str

    def __post_init__(self) -> None:
        _project_id(self.project_id)
        _relative_key(self.relative_key)
        for value, field in (
            (self.project_revision, "project_revision"),
            (self.binding_revision, "binding_revision"),
            (self.runtime_host_installation_revision, "runtime_host_installation_revision"),
        ):
            _u64(value, field)
        _digest(self.binding_digest, "binding_digest")
        if self.binding_revision == "1":
            if (
                self.previous_binding_revision is not None
                or self.previous_binding_digest is not None
            ):
                raise WAWProjectBindingStoreError("first binding cannot have a predecessor")
        else:
            if self.previous_binding_revision is None or self.previous_binding_digest is None:
                raise WAWProjectBindingStoreError("binding predecessor is unavailable")
            previous = _u64(self.previous_binding_revision, "previous_binding_revision")
            _digest(self.previous_binding_digest, "previous_binding_digest")
            if int(previous) + 1 != int(self.binding_revision):
                raise WAWProjectBindingStoreError("binding predecessor is invalid")
        if not isinstance(self.runtime_host_installation_id, str) or not re.fullmatch(
            r"wri_[0-9a-f]{32}", self.runtime_host_installation_id
        ):
            raise WAWProjectBindingStoreError("runtime host identity is invalid")

    def to_record(self) -> dict[str, str | None]:
        return {
            "binding_digest": self.binding_digest,
            "binding_revision": self.binding_revision,
            "previous_binding_digest": self.previous_binding_digest,
            "previous_binding_revision": self.previous_binding_revision,
            "project_id": self.project_id,
            "project_revision": self.project_revision,
            "relative_key": self.relative_key,
            "runtime_host_installation_id": self.runtime_host_installation_id,
            "runtime_host_installation_revision": self.runtime_host_installation_revision,
            "schema_version": "waw-runtime-project-binding-v1",
        }

    @classmethod
    def from_record(cls, value: object) -> WAWDurableProjectBinding:
        if not isinstance(value, dict) or set(value) != {
            "binding_digest",
            "binding_revision",
            "previous_binding_digest",
            "previous_binding_revision",
            "project_id",
            "project_revision",
            "relative_key",
            "runtime_host_installation_id",
            "runtime_host_installation_revision",
            "schema_version",
        }:
            raise WAWProjectBindingStoreError("binding record is invalid")
        if value["schema_version"] != "waw-runtime-project-binding-v1":
            raise WAWProjectBindingStoreError("binding schema is invalid")
        required = (
            "project_id",
            "relative_key",
            "project_revision",
            "binding_revision",
            "binding_digest",
            "runtime_host_installation_id",
            "runtime_host_installation_revision",
        )
        if any(not isinstance(value[field], str) for field in required):
            raise WAWProjectBindingStoreError("binding record is invalid")
        previous_revision = value["previous_binding_revision"]
        previous_digest = value["previous_binding_digest"]
        if previous_revision is not None and not isinstance(previous_revision, str):
            raise WAWProjectBindingStoreError("binding record is invalid")
        if previous_digest is not None and not isinstance(previous_digest, str):
            raise WAWProjectBindingStoreError("binding record is invalid")
        return cls(
            project_id=value["project_id"],
            relative_key=value["relative_key"],
            project_revision=value["project_revision"],
            binding_revision=value["binding_revision"],
            binding_digest=value["binding_digest"],
            previous_binding_revision=previous_revision,
            previous_binding_digest=previous_digest,
            runtime_host_installation_id=value["runtime_host_installation_id"],
            runtime_host_installation_revision=value["runtime_host_installation_revision"],
        )


def _project_id(value: object) -> str:
    if not isinstance(value, str) or _PROJECT_ID.fullmatch(value) is None:
        raise WAWProjectBindingStoreError("project identity is invalid")
    return value


def _relative_key(value: object) -> str:
    try:
        return validate_relative_key(value)
    except WAWControlError as exc:
        raise WAWProjectBindingStoreError("Project key is invalid") from exc


def _u64(value: object, field: str) -> str:
    if not isinstance(value, str) or _DECIMAL.fullmatch(value) is None:
        raise WAWProjectBindingStoreError(f"{field} is invalid")
    if int(value) > _MAX_U64:
        raise WAWProjectBindingStoreError(f"{field} is invalid")
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise WAWProjectBindingStoreError(f"{field} is invalid")
    return value


def _directory_identity(details: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        details.st_dev,
        details.st_ino,
        details.st_uid,
        details.st_gid,
        stat.S_IMODE(details.st_mode),
    )


class WAWProjectBindingVerifier:
    """Hold the trusted Project-root descriptor across local binding checks."""

    def __init__(
        self,
        root: Path,
        *,
        expected_uid: int,
        expected_gid: int,
        _test_only_token: object | None = None,
    ) -> None:
        if not root.is_absolute():
            raise ValueError("WAW Project root must be absolute")
        if type(expected_uid) is not int or expected_uid < 0:
            raise ValueError("WAW Project root uid is invalid")
        if type(expected_gid) is not int or expected_gid < 0:
            raise ValueError("WAW Project root gid is invalid")
        self._test_only = _test_only_token is _TEST_ONLY_TOKEN
        self._expected_uid = expected_uid
        self._expected_gid = expected_gid
        self._root_path = root
        self._root_fd = self._open_root()
        self._root_identity = _directory_identity(os.fstat(self._root_fd))
        # Retain one descriptor per exact relative key.  The held descriptor
        # prevents an unlink/recreate cycle from recycling an inode between two
        # registrations in the same Runtime epoch.
        self._project_descriptors: dict[str, tuple[int, tuple[int, int, int, int, int]]] = {}
        self._closed = False

    @classmethod
    def test_only(cls, root: Path) -> WAWProjectBindingVerifier:
        return cls(
            root,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
            _test_only_token=_TEST_ONLY_TOKEN,
        )

    def _open_root(self) -> int:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            descriptor = os.open(self._root_path, flags)
        except OSError as exc:
            raise WAWProjectBindingVerifierError("Project root is unavailable") from exc
        try:
            self._validate_directory(os.fstat(descriptor))
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    def _validate_directory(self, details: os.stat_result) -> None:
        if (
            not stat.S_ISDIR(details.st_mode)
            or details.st_uid != self._expected_uid
            or details.st_gid != self._expected_gid
            or details.st_mode & 0o022
        ):
            raise WAWProjectBindingVerifierError("Project path provenance is invalid")

    def _revalidate_root(self) -> None:
        if self._closed:
            raise WAWProjectBindingVerifierError("Project verifier is closed")
        details = os.fstat(self._root_fd)
        self._validate_directory(details)
        if _directory_identity(details) != self._root_identity:
            raise WAWProjectBindingVerifierError("Project root identity changed")
        try:
            named = os.stat(self._root_path, follow_symlinks=False)
        except OSError as exc:
            raise WAWProjectBindingVerifierError("Project root is unavailable") from exc
        self._validate_directory(named)
        if _directory_identity(named) != self._root_identity:
            raise WAWProjectBindingVerifierError("Project root identity changed")

    def binding_digest(self, request: Mapping[str, object]) -> str:
        """Return the RFC 8785 digest of one descriptor-verified Project binding."""

        try:
            project_id = _project_id(request["project_id"])
            relative_key = _relative_key(request["relative_key"])
            project_revision = _u64(request["project_revision"], "project_revision")
        except (KeyError, TypeError, WAWProjectBindingStoreError) as exc:
            raise WAWProjectBindingVerifierError("Project binding request is invalid") from exc
        self._revalidate_root()
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            project_fd = os.open(relative_key, flags, dir_fd=self._root_fd)
        except OSError as exc:
            raise WAWProjectBindingVerifierError("Project path is unavailable") from exc
        try:
            details = os.fstat(project_fd)
            self._validate_directory(details)
            named = os.stat(relative_key, dir_fd=self._root_fd, follow_symlinks=False)
            self._validate_directory(named)
            project_identity = _directory_identity(details)
            if project_identity != _directory_identity(named):
                raise WAWProjectBindingVerifierError("Project path identity changed")
            held = self._project_descriptors.get(relative_key)
            if held is not None:
                held_fd, held_identity = held
                try:
                    held_details = os.fstat(held_fd)
                except OSError as exc:
                    raise WAWProjectBindingVerifierError(
                        "Project path descriptor is unavailable"
                    ) from exc
                self._validate_directory(held_details)
                if (
                    _directory_identity(held_details) != held_identity
                    or project_identity != held_identity
                ):
                    raise WAWProjectBindingVerifierError("Project path identity changed")
            self._revalidate_root()
            final_named = os.stat(relative_key, dir_fd=self._root_fd, follow_symlinks=False)
            self._validate_directory(final_named)
            if _directory_identity(final_named) != project_identity:
                raise WAWProjectBindingVerifierError("Project path identity changed")
            self._revalidate_root()
            path_fingerprint = _canonical_sha256(
                {
                    "project_device": str(details.st_dev),
                    "project_gid": str(details.st_gid),
                    "project_inode": str(details.st_ino),
                    "project_mode": f"{stat.S_IMODE(details.st_mode):04o}",
                    "project_uid": str(details.st_uid),
                    "root_device": str(self._root_identity[0]),
                    "root_inode": str(self._root_identity[1]),
                    "schema_version": "waw-project-path-v1",
                }
            )
            digest = _canonical_sha256(
                {
                    "path_fingerprint": path_fingerprint,
                    "project_id": project_id,
                    "project_revision": project_revision,
                    "relative_key": relative_key,
                    "schema_version": "waw-project-binding-v1",
                }
            )
            if held is None:
                if len(self._project_descriptors) >= _MAX_BINDINGS:
                    raise WAWProjectBindingVerifierError(
                        "Project binding descriptor capacity exceeded"
                    )
                self._project_descriptors[relative_key] = (project_fd, project_identity)
                project_fd = -1
            return digest
        finally:
            if project_fd >= 0:
                os.close(project_fd)

    def close(self) -> None:
        if self._closed:
            return
        descriptor, self._root_fd = self._root_fd, -1
        project_descriptors = tuple(fd for fd, _identity in self._project_descriptors.values())
        self._project_descriptors.clear()
        self._closed = True
        failure: OSError | None = None
        for candidate in (descriptor, *project_descriptors):
            if candidate < 0:
                continue
            try:
                os.close(candidate)
            except OSError as exc:
                if failure is None:
                    failure = exc
        if failure is not None:
            raise WAWProjectBindingVerifierError("Project verifier close failed") from failure


class WAWProjectBindingStore:
    """Persist one exact current binding per Project with atomic replacement."""

    def __init__(
        self,
        directory: Path,
        *,
        expected_uid: int,
        expected_gid: int,
        create: bool = False,
        _test_only_token: object | None = None,
    ) -> None:
        if not directory.is_absolute():
            raise ValueError("binding store directory must be absolute")
        self._test_only = _test_only_token is _TEST_ONLY_TOKEN
        self._expected_uid = expected_uid
        self._expected_gid = expected_gid
        self._directory_path = directory
        if create:
            if not self._test_only:
                raise ValueError("production binding store directory must be installer-created")
            directory.mkdir(mode=0o700, parents=False, exist_ok=False)
        self._directory_fd = self._open_directory()
        self._closed = False

    @classmethod
    def test_only(cls, directory: Path) -> WAWProjectBindingStore:
        return cls(
            directory,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
            create=True,
            _test_only_token=_TEST_ONLY_TOKEN,
        )

    def _open_directory(self) -> int:
        try:
            descriptor = os.open(
                self._directory_path,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
        except OSError as exc:
            raise WAWProjectBindingStoreError("binding store is unavailable") from exc
        try:
            self._validate_directory(os.fstat(descriptor))
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    def _validate_directory(self, details: os.stat_result) -> None:
        if (
            not stat.S_ISDIR(details.st_mode)
            or details.st_uid != self._expected_uid
            or details.st_gid != self._expected_gid
            or details.st_mode & 0o077
        ):
            raise WAWProjectBindingStoreError("binding store provenance is invalid")

    def _require_open(self) -> None:
        if self._closed or self._directory_fd < 0:
            raise WAWProjectBindingStoreError("binding store is closed")
        self._validate_directory(os.fstat(self._directory_fd))

    @staticmethod
    def _name(project_id: str) -> str:
        return project_id + ".json"

    def _read(self, project_id: str) -> WAWDurableProjectBinding | None:
        self._require_open()
        name = self._name(project_id)
        try:
            descriptor = os.open(
                name,
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=self._directory_fd,
            )
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise WAWProjectBindingStoreError("binding record is unavailable") from exc
        try:
            details = os.fstat(descriptor)
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_uid != self._expected_uid
                or details.st_gid != self._expected_gid
                or stat.S_IMODE(details.st_mode) != 0o600
                or details.st_nlink != 1
                or details.st_size < 1
                or details.st_size > _MAX_RECORD_BYTES
            ):
                raise WAWProjectBindingStoreError("binding record provenance is invalid")
            raw = os.read(descriptor, _MAX_RECORD_BYTES + 1)
            if len(raw) != details.st_size:
                raise WAWProjectBindingStoreError("binding record changed during read")
        finally:
            os.close(descriptor)
        return _decode_record(raw)

    def get(self, project_id: str) -> WAWDurableProjectBinding | None:
        return self._read(_project_id(project_id))

    def list_current(self) -> tuple[WAWDurableProjectBinding, ...]:
        self._require_open()
        try:
            names = tuple(os.listdir(self._directory_fd))
        except OSError as exc:
            raise WAWProjectBindingStoreError("binding store is unavailable") from exc
        if len(names) > _MAX_BINDINGS:
            raise WAWProjectBindingStoreError("binding store capacity is invalid")
        values: list[WAWDurableProjectBinding] = []
        for name in sorted(names):
            if not name.endswith(".json"):
                raise WAWProjectBindingStoreError("binding store inventory is invalid")
            project_id = name[:-5]
            value = self._read(project_id)
            if value is None or value.project_id != project_id:
                raise WAWProjectBindingStoreError("binding store inventory is invalid")
            values.append(value)
        return tuple(values)

    def commit(self, value: WAWDurableProjectBinding) -> WAWDurableProjectBinding:
        self._require_open()
        if type(value) is not WAWDurableProjectBinding:
            raise TypeError("binding store requires an exact durable binding")
        current = self._read(value.project_id)
        if current is not None:
            if current == value:
                return current
            if int(value.binding_revision) != int(current.binding_revision) + 1:
                raise WAWProjectBindingStoreError("binding revision is not next")
            if (
                value.previous_binding_revision != current.binding_revision
                or value.previous_binding_digest != current.binding_digest
            ):
                raise WAWProjectBindingStoreError("binding predecessor is stale")
        elif value.binding_revision != "1":
            raise WAWProjectBindingStoreError("binding bootstrap is unavailable")
        elif len(self.list_current()) >= _MAX_BINDINGS:
            raise WAWProjectBindingStoreError("binding store capacity is exhausted")
        raw = _canonical_record(value.to_record())
        name = self._name(value.project_id)
        temporary = "." + name + ".tmp-" + secrets.token_hex(16)
        descriptor = -1
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                0o600,
                dir_fd=self._directory_fd,
            )
            written = os.write(descriptor, raw)
            if written != len(raw):
                raise WAWProjectBindingStoreError("binding record write was incomplete")
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            os.replace(
                temporary,
                name,
                src_dir_fd=self._directory_fd,
                dst_dir_fd=self._directory_fd,
            )
            os.fsync(self._directory_fd)
        except WAWProjectBindingStoreError:
            raise
        except OSError as exc:
            raise WAWProjectBindingStoreError("binding record persistence failed") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                os.unlink(temporary, dir_fd=self._directory_fd)
            except FileNotFoundError:
                pass
            except OSError:
                pass
        result = self._read(value.project_id)
        if result != value:
            raise WAWProjectBindingStoreError("binding record did not persist exactly")
        return result

    def close(self) -> None:
        if self._closed:
            return
        descriptor, self._directory_fd = self._directory_fd, -1
        self._closed = True
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError as exc:
                raise WAWProjectBindingStoreError("binding store close failed") from exc


def _canonical_sha256(value: Mapping[str, str]) -> str:
    try:
        raw = rfc8785.dumps(dict(value))
    except (TypeError, ValueError, rfc8785.CanonicalizationError) as exc:
        raise WAWProjectBindingVerifierError("Project binding cannot be canonicalized") from exc
    return hashlib.sha256(raw).hexdigest()


def _canonical_record(value: Mapping[str, str | None]) -> bytes:
    try:
        raw = rfc8785.dumps(dict(value))
    except (TypeError, ValueError, rfc8785.CanonicalizationError) as exc:
        raise WAWProjectBindingStoreError("binding record cannot be canonicalized") from exc
    if not 1 <= len(raw) <= _MAX_RECORD_BYTES:
        raise WAWProjectBindingStoreError("binding record is oversized")
    return raw


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise WAWProjectBindingStoreError("binding record has duplicate fields")
        value[key] = item
    return value


def _decode_record(raw: bytes) -> WAWDurableProjectBinding:
    try:
        decoded = json.loads(raw, object_pairs_hook=_no_duplicates)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise WAWProjectBindingStoreError("binding record is invalid") from exc
    if _canonical_record(decoded) != raw:
        raise WAWProjectBindingStoreError("binding record is not canonical")
    return WAWDurableProjectBinding.from_record(decoded)


__all__ = [
    "WAWDurableProjectBinding",
    "WAWProjectBindingStore",
    "WAWProjectBindingStoreError",
    "WAWProjectBindingVerifier",
    "WAWProjectBindingVerifierError",
]
