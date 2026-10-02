"""Recoverable APT service-start suppression, without replacing another policy."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable

from agentbox_installer.waw_manifest_install import WAWManifestInstallError, WAWManifestIssuer

_NAME = "policy-rc.d"
_RAW = b"#!/bin/sh\n# AgentBox temporary offline package guard v1\nexit 101\n"


class WAWPackageStartGuard:
    def __init__(self, issuer: WAWManifestIssuer) -> None:
        self.issuer = issuer

    def recover_interrupted(self, *, recover: bool = False) -> bool:
        """Remove only an exact stale AgentBox guard when recovery is explicit."""
        with self.issuer._directory("/usr/sbin") as parent:
            try:
                facts = os.stat(_NAME, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                return False
            exact_metadata = (
                stat.S_ISREG(facts.st_mode)
                and facts.st_uid == self.issuer.owner_uid
                and facts.st_gid == self.issuer.root_gid
                and stat.S_IMODE(facts.st_mode) == 0o755
                and facts.st_nlink == 1
                and facts.st_size == len(_RAW)
            )
            if not exact_metadata:
                if recover:
                    raise WAWManifestInstallError(
                        "existing package guard is foreign or unsafe"
                    )
                return False
            try:
                self.issuer._require_bytes(
                    parent, _NAME, _RAW, 0o755, self.issuer.root_gid
                )
            except WAWManifestInstallError:
                if recover:
                    raise
                return False
            if not recover:
                raise WAWManifestInstallError(
                    "interrupted package guard requires --recover"
                )
            os.unlink(_NAME, dir_fd=parent)
            os.fsync(parent)
            return True

    def run(self, install: Callable[[], None], *, recover: bool = False) -> None:
        self.recover_interrupted(recover=recover)
        with self.issuer._directory("/usr/sbin") as parent:
            self.issuer._create_file(
                parent, _NAME, _RAW, 0o755, self.issuer.root_gid, allow_existing=False
            )
            try:
                install()
            finally:
                self.issuer._require_bytes(parent, _NAME, _RAW, 0o755, self.issuer.root_gid)
                os.unlink(_NAME, dir_fd=parent)
                os.fsync(parent)
