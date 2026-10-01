"""Fixed offline WAW configuration transaction; no service or Secret authority."""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import os
import stat
from collections.abc import Callable
from pathlib import Path

from agentbox_runtime.waw_manifest_codecs import CrossManifestPinV2
from agentbox_runtime.waw_vendor_enrollment import _decode

from agentbox_installer.waw_manifest_install import (
    WAWManifestInstallError,
    WAWManifestIssuer,
    _identity,
)

_API_DISABLED = b'{"mode":"disabled","schema_version":"agentbox-waw-api-profile.v1"}\n'
_API_ENABLED = b'{"mode":"filesystem-v2","schema_version":"agentbox-waw-api-profile.v1"}\n'
_RUNTIME_DISABLED = b'{"mode":"disabled","schema_version":"agentbox-waw-runtime-profile.v1"}\n'
_RUNTIME_ENABLED = b'{"mode":"filesystem-v2","schema_version":"agentbox-waw-runtime-profile.v1"}\n'
_JOURNAL = "activation.v1.json"
_PROFILES = (
    ("/var/lib/agentbox-waw", "runtime-profile.v1.json", _RUNTIME_DISABLED, _RUNTIME_ENABLED),
    ("/etc/agentbox", "waw-api-profile.v1.json", _API_DISABLED, _API_ENABLED),
)


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise WAWManifestInstallError("activation record has duplicate fields")
        result[key] = value
    return result


class WAWActivationTransaction:
    """Commit paired profiles only for the exact enrolled fixed installation."""

    def __init__(self, issuer: WAWManifestIssuer, pin: CrossManifestPinV2, *, api_gid: int) -> None:
        self.issuer = issuer
        self.pin = pin
        self.api_gid = api_gid
        self.base = {
            "schema_version": "agentbox-waw-activation.v1",
            "version": issuer.version,
            "runtime_host_installation_id": pin.runtime.runtime_host_installation_id,
            "host_manifest_digest": pin.runtime_manifest_digest,
        }

    def _read(self, parent: int, name: str, *, mode: int, gid: int, maximum: int = 65536) -> bytes:
        fd = os.open(
            name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
        )
        try:
            before = os.fstat(fd)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != self.issuer.owner_uid
                or before.st_gid != gid
                or stat.S_IMODE(before.st_mode) != mode
                or before.st_nlink != 1
                or not 0 < before.st_size <= maximum
            ):
                raise WAWManifestInstallError("activation resource provenance is invalid")
            raw = os.read(fd, maximum + 1)
            if (
                len(raw) != before.st_size
                or _identity(before) != _identity(os.fstat(fd))
                or _identity(before)
                != _identity(os.stat(name, dir_fd=parent, follow_symlinks=False))
            ):
                raise WAWManifestInstallError("activation resource changed during read")
            return raw
        finally:
            os.close(fd)

    def inspect(self, *, recover: bool) -> str | None:
        with self.issuer._directory("/var/lib/agentbox-waw") as parent:
            try:
                raw = self._read(
                    parent, _JOURNAL, mode=0o600, gid=self.issuer.root_gid, maximum=4096
                )
            except FileNotFoundError:
                phase = None
            else:
                value = json.loads(raw, object_pairs_hook=_pairs)
                if (
                    type(value) is not dict
                    or set(value) != {*self.base, "phase"}
                    or any(value[key] != expected for key, expected in self.base.items())
                    or value["phase"] not in {"preparing", "configured", "started"}
                    or raw != self._journal_bytes(str(value["phase"]))
                ):
                    raise WAWManifestInstallError(
                        "activation record does not match this installation"
                    )
                phase = str(value["phase"])
                if phase in {"preparing", "configured"} and not recover:
                    raise WAWManifestInstallError("interrupted activation requires --recover")
            raw = self._read(
                parent, "vendor-enrollment.v1.json", mode=0o440, gid=self.issuer.runtime_gid
            )
            record = _decode(raw, (), ())
            runtime = self.pin.runtime
            if (
                record.runtime_host_installation_id != runtime.runtime_host_installation_id
                or record.runtime_host_installation_revision
                != runtime.runtime_host_installation_revision
                or record.host_manifest_digest != self.pin.runtime_manifest_digest
                or record.enrollment_epoch != runtime.enrollment_epoch
                or record.enrollment_state != runtime.enrollment_state
            ):
                raise WAWManifestInstallError("activation vendor enrollment changed")
        for index, (directory, name, disabled, enabled) in enumerate(_PROFILES):
            with self.issuer._directory(directory) as parent:
                raw = self._read(
                    parent,
                    name,
                    mode=0o440,
                    gid=self.issuer.runtime_gid if index == 0 else self.api_gid,
                )
                allowed = (
                    (disabled,)
                    if phase is None
                    else ((enabled,) if phase == "started" else (disabled, enabled))
                )
                if raw not in allowed:
                    raise WAWManifestInstallError(
                        "activation profile is not the expected fixed mode"
                    )
        # All global policies must already be complete, not merely recoverable.
        self.issuer.prepare_fixed_policies(plan=True)
        for directory, name, source in (
            ("/etc/claude-code", "managed-settings.json", "claude-managed-policy.v1.json"),
            ("/etc/codex", "requirements.toml", "codex-requirements.toml"),
            ("/etc/codex", "managed_config.toml", "codex-managed-config.toml"),
        ):
            expected = self.issuer._read("/usr/share/agentbox/waw/" + source, 65536)
            with self.issuer._directory(directory) as parent:
                self.issuer._require_bytes(parent, name, expected, 0o444, self.issuer.root_gid)
        dropin = self._dropin()
        if hashlib.sha256(dropin).hexdigest() != self.pin.cgroup.policy_template_digest:
            raise WAWManifestInstallError("activation cgroup policy digest changed")
        try:
            with self.issuer._directory("/etc/systemd/system/agentbox-runtime.service.d") as parent:
                facts = os.fstat(parent)
                if (
                    facts.st_gid != self.issuer.root_gid
                    or stat.S_IMODE(facts.st_mode) != 0o755
                    or set(os.listdir(parent)) - {"waw.v1.conf"}
                ):
                    raise WAWManifestInstallError("activation drop-in directory is not closed")
                try:
                    existing = self._read(
                        parent, "waw.v1.conf", mode=0o644, gid=self.issuer.root_gid
                    )
                except FileNotFoundError:
                    pass
                else:
                    if existing != dropin and not (
                        recover and phase == "preparing" and dropin.startswith(existing)
                    ):
                        raise WAWManifestInstallError("activation drop-in changed")
        except FileNotFoundError:
            pass
        return phase

    @staticmethod
    def _dropin() -> bytes:
        return Path(
            str(
                importlib.resources.files("agentbox_installer")
                / "assets/systemd/agentbox-runtime-waw.v1.conf"
            )
        ).read_bytes()

    def _journal_bytes(self, phase: str) -> bytes:
        return (
            json.dumps(self.base | {"phase": phase}, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()

    def _replace(
        self, parent: int, name: str, raw: bytes, *, mode: int, gid: int, recover: bool
    ) -> None:
        pending = (
            "." + name + "." + hashlib.sha256(raw).hexdigest()[:16] + ".waw-activation.pending"
        )
        self.issuer._create_file(
            parent, pending, raw, mode, gid, allow_existing=recover, repair_prefix=recover
        )
        os.replace(pending, name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)

    def configure(self, *, recover: bool, quiescent: Callable[[], None]) -> None:
        self.inspect(recover=recover)
        quiescent()
        # A safely recoverable intent precedes any paired-profile mutation.
        with self.issuer._directory("/var/lib/agentbox-waw") as parent:
            self._replace(
                parent,
                _JOURNAL,
                self._journal_bytes("preparing"),
                mode=0o600,
                gid=self.issuer.root_gid,
                recover=recover,
            )
        dropin = self._dropin()
        with self.issuer._directory("/etc/systemd/system") as parent:
            name = "agentbox-runtime.service.d"
            try:
                os.mkdir(name, 0o755, dir_fd=parent)
            except FileExistsError:
                pass
            else:
                fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                try:
                    os.fchown(fd, self.issuer.owner_uid, self.issuer.root_gid)
                    os.fchmod(fd, 0o755)
                finally:
                    os.close(fd)
                os.fsync(parent)
        with self.issuer._directory("/etc/systemd/system/agentbox-runtime.service.d") as parent:
            self.issuer._create_file(
                parent,
                "waw.v1.conf",
                dropin,
                0o644,
                self.issuer.root_gid,
                allow_existing=True,
                repair_prefix=recover,
            )
        for index, (directory, name, _, enabled) in enumerate(_PROFILES):
            quiescent()
            with self.issuer._directory(directory) as parent:
                self._replace(
                    parent,
                    name,
                    enabled,
                    mode=0o440,
                    gid=self.issuer.runtime_gid if index == 0 else self.api_gid,
                    recover=recover,
                )
        with self.issuer._directory("/var/lib/agentbox-waw") as parent:
            self._replace(
                parent,
                _JOURNAL,
                self._journal_bytes("configured"),
                mode=0o600,
                gid=self.issuer.root_gid,
                recover=recover,
            )

    def mark_started(self, *, recover: bool) -> None:
        with self.issuer._directory("/var/lib/agentbox-waw") as parent:
            self._replace(
                parent,
                _JOURNAL,
                self._journal_bytes("started"),
                mode=0o600,
                gid=self.issuer.root_gid,
                recover=recover,
            )
