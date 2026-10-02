"""Recoverable APT service-start suppression, without replacing another policy."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable

from agentbox_installer.waw_manifest_install import WAWManifestInstallError, WAWManifestIssuer

_NAME = "policy-rc.d"
_ALLOWED_DEPENDENCIES = frozenset({"tmux", "bubblewrap", "nginx", "certbot"})
_PHASES = frozenset({"preparing", "armed"})
_RAW = b"#!/bin/sh\n# AgentBox temporary offline package guard v1\nexit 101\n"


def _guard_raw(dependencies: tuple[str, ...], phase: str) -> bytes:
    if (
        phase not in _PHASES
        or not dependencies
        or tuple(sorted(set(dependencies))) != dependencies
        or any(name not in _ALLOWED_DEPENDENCIES for name in dependencies)
    ):
        raise WAWManifestInstallError("package guard state is invalid")
    return (
        "#!/bin/sh\n"
        "# AgentBox temporary offline package guard v2\n"
        f"# phase={phase}\n"
        f"# dependencies={','.join(dependencies)}\n"
        "exit 101\n"
    ).encode("ascii")


def _decode_guard(raw: bytes) -> tuple[str, tuple[str, ...]] | None:
    if raw == _RAW:
        return "legacy", ()
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    lines = text.splitlines()
    if len(lines) != 5 or lines[:2] != [
        "#!/bin/sh",
        "# AgentBox temporary offline package guard v2",
    ]:
        return None
    if not lines[2].startswith("# phase=") or not lines[3].startswith("# dependencies="):
        return None
    phase = lines[2][len("# phase=") :]
    dependencies = tuple(filter(None, lines[3][len("# dependencies=") :].split(",")))
    try:
        expected = _guard_raw(dependencies, phase)
    except WAWManifestInstallError:
        return None
    if expected != raw or lines[4] != "exit 101":
        return None
    return phase, dependencies


class WAWPackageStartGuard:
    def __init__(self, issuer: WAWManifestIssuer) -> None:
        self.issuer = issuer

    def _existing(self, parent: int) -> tuple[bytes, tuple[str, tuple[str, ...]] | None] | None:
        try:
            fd = os.open(
                _NAME,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                dir_fd=parent,
            )
        except FileNotFoundError:
            return None
        try:
            facts = os.fstat(fd)
            if (
                not stat.S_ISREG(facts.st_mode)
                or facts.st_uid != self.issuer.owner_uid
                or facts.st_gid != self.issuer.root_gid
                or stat.S_IMODE(facts.st_mode) != 0o755
                or facts.st_nlink != 1
                or not 0 < facts.st_size <= 512
            ):
                return b"", None
            raw = os.read(fd, 513)
            if len(raw) != facts.st_size:
                return b"", None
            return raw, _decode_guard(raw)
        finally:
            os.close(fd)

    def recover_interrupted(
        self,
        *,
        recover: bool = False,
        restore: Callable[[tuple[str, ...]], None] | None = None,
    ) -> tuple[str, ...] | None:
        """Recover only an exact AgentBox guard, before removing its global policy."""
        with self.issuer._directory("/usr/sbin") as parent:
            existing = self._existing(parent)
            if existing is None:
                return None
            raw, decoded = existing
            if decoded is None:
                if recover:
                    raise WAWManifestInstallError("existing package guard is foreign or unsafe")
                return None
            phase, dependencies = decoded
            if not recover:
                raise WAWManifestInstallError("interrupted package guard requires --recover")
            if phase == "legacy":
                # v1 never carried enough information to mutate package-owned units.
                # It can only remove the exact historical AgentBox service-start guard.
                self.issuer._require_bytes(parent, _NAME, _RAW, 0o755, self.issuer.root_gid)
            else:
                expected = _guard_raw(dependencies, phase)
                self.issuer._require_bytes(
                    parent, _NAME, expected, 0o755, self.issuer.root_gid
                )
                if phase == "armed":
                    if restore is None:
                        raise WAWManifestInstallError(
                            "armed package guard recovery requires dependency restoration"
                        )
                    restore(dependencies)
                    self.issuer._require_bytes(
                        parent, _NAME, expected, 0o755, self.issuer.root_gid
                    )
            os.unlink(_NAME, dir_fd=parent)
            os.fsync(parent)
            return dependencies

    def run(
        self,
        install: Callable[[], None],
        *,
        dependencies: tuple[str, ...],
        prepare: Callable[[tuple[str, ...]], None],
        restore: Callable[[tuple[str, ...]], None],
        recover: bool = False,
    ) -> None:
        dependencies = tuple(sorted(set(dependencies)))
        preparing = _guard_raw(dependencies, "preparing")
        armed = _guard_raw(dependencies, "armed")
        self.recover_interrupted(recover=recover, restore=restore)
        with self.issuer._directory("/usr/sbin") as parent:
            self.issuer._create_file(
                parent, _NAME, preparing, 0o755, self.issuer.root_gid, allow_existing=False
            )
            try:
                prepare(dependencies)
                self.issuer._require_bytes(
                    parent, _NAME, preparing, 0o755, self.issuer.root_gid
                )
                os.unlink(_NAME, dir_fd=parent)
                os.fsync(parent)
                self.issuer._create_file(
                    parent, _NAME, armed, 0o755, self.issuer.root_gid, allow_existing=False
                )
                install()
            except BaseException:
                # An armed guard is durable recovery intent. A preparing guard means
                # APT has not started and can be removed safely.
                current = self._existing(parent)
                if current is not None and current[0] == preparing:
                    self.issuer._require_bytes(
                        parent, _NAME, preparing, 0o755, self.issuer.root_gid
                    )
                    os.unlink(_NAME, dir_fd=parent)
                    os.fsync(parent)
                raise
            self.issuer._require_bytes(parent, _NAME, armed, 0o755, self.issuer.root_gid)
            os.unlink(_NAME, dir_fd=parent)
            os.fsync(parent)
