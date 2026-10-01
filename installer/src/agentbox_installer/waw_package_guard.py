"""Recoverable APT service-start suppression, without replacing another policy."""

from __future__ import annotations

import os
from collections.abc import Callable

from agentbox_installer.waw_manifest_install import WAWManifestInstallError, WAWManifestIssuer

_NAME = "policy-rc.d"
_RAW = b"#!/bin/sh\n# AgentBox temporary offline package guard v1\nexit 101\n"


class WAWPackageStartGuard:
    def __init__(self, issuer: WAWManifestIssuer) -> None:
        self.issuer = issuer

    def run(self, install: Callable[[], None], *, recover: bool = False) -> None:
        with self.issuer._directory("/usr/sbin") as parent:
            try:
                os.stat(_NAME, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                self.issuer._require_bytes(parent, _NAME, _RAW, 0o755, self.issuer.root_gid)
                if not recover:
                    raise WAWManifestInstallError("interrupted package guard requires --recover")
            self.issuer._create_file(
                parent, _NAME, _RAW, 0o755, self.issuer.root_gid, allow_existing=recover
            )
            try:
                install()
            finally:
                self.issuer._require_bytes(parent, _NAME, _RAW, 0o755, self.issuer.root_gid)
                os.unlink(_NAME, dir_fd=parent)
                os.fsync(parent)
