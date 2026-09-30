"""Create-only complete WAW manifest issuance from fixed installed resources."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentbox_runtime.waw_executable import _validate_elf_header
from agentbox_runtime.waw_fixed_transport import _project_filesystem_identity
from agentbox_runtime.waw_host_manifest import WAW_PUBLIC_MANIFEST_FILENAMES_V2
from agentbox_runtime.waw_manifest_codecs import (
    RUNTIME_HOST_MANIFEST_SCHEMA_V2,
    RUNTIME_HOST_MANIFEST_V2_PATHS,
    RUNTIME_NAMESPACE_BINDING_V1,
    SCOPED_CGROUP_FILESYSTEM_V1,
    SCOPED_CGROUP_PROTECTION_V1,
    SCOPED_CGROUP_TEMPLATE_SHA256_V1,
    SCOPED_CGROUP_WORKSPACES_V1,
    decode_runtime_host_manifest_v2,
    encode_api_host_anchor_v2,
    encode_cgroup_delegation_manifest,
    encode_project_root_manifest,
    encode_runtime_host_manifest_v2,
    manifest_sha256,
    verify_api_host_anchor_v2_cross_manifest,
)
from agentbox_runtime.waw_process_profile import (
    EXECUTABLE_POLICIES_V1,
    INTERACTIVE_PROFILE_CONSTANTS_V1,
    encode_codex_managed_policy_bundle_v1,
    encode_executable_inventory_v1,
    encode_interactive_profile_bundle_v1,
)

_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
_PRIVATE = "runtime-host-installation.v2.json"
_PENDING = "runtime-host-installation.initial-v2.pending"


class WAWManifestInstallError(RuntimeError):
    pass


def _identity(facts: os.stat_result) -> tuple[int, ...]:
    return (
        facts.st_dev,
        facts.st_ino,
        facts.st_uid,
        facts.st_gid,
        facts.st_mode,
        facts.st_nlink,
        facts.st_size,
        facts.st_mtime_ns,
        facts.st_ctime_ns,
    )


@dataclass(frozen=True)
class WAWManifestPublication:
    status: str
    runtime_host_installation_id: str
    host_manifest_digest: str


class WAWManifestIssuer:
    """Private installer boundary; paths are derived, never request selectors."""

    def __init__(
        self,
        root: Path,
        release_version: str,
        *,
        owner_uid: int,
        root_gid: int,
        runtime_uid: int,
        runtime_gid: int,
    ) -> None:
        if (
            not root.is_absolute()
            or ".." in root.parts
            or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:(?:a|b|rc)[0-9]+)?", release_version) is None
            or any(
                type(value) is not int or value < 0
                for value in (owner_uid, root_gid, runtime_uid, runtime_gid)
            )
        ):
            raise WAWManifestInstallError("manifest issuer identity is invalid")
        self.root = root
        self.version = release_version
        self.owner_uid = owner_uid
        self.root_gid = root_gid
        self.runtime_uid = runtime_uid
        self.runtime_gid = runtime_gid
        self.observations: list[tuple[Path, tuple[int, ...], bool]] = []

    @contextmanager
    def _directory(self, logical: str, *, runtime_leaf: bool = False) -> Iterator[int]:
        descriptors: list[int] = []
        nodes: list[tuple[str, int, tuple[int, ...]]] = []
        try:
            descriptor = os.open(self.root, _DIR)
            descriptors.append(descriptor)
            facts = os.fstat(descriptor)
            if facts.st_uid != self.owner_uid or facts.st_mode & 0o022:
                raise WAWManifestInstallError("manifest root provenance is invalid")
            for component in Path(logical).parts[1:]:
                parent = descriptor
                descriptor = os.open(component, _DIR, dir_fd=descriptor)
                descriptors.append(descriptor)
                facts = os.fstat(descriptor)
                expected = (
                    self.runtime_uid
                    if runtime_leaf and component == Path(logical).name
                    else self.owner_uid
                )
                if (
                    facts.st_uid != expected
                    or facts.st_mode & 0o022
                    or runtime_leaf
                    and component == Path(logical).name
                    and facts.st_gid != self.runtime_gid
                ):
                    raise WAWManifestInstallError("manifest directory provenance is invalid")
                nodes.append((component, parent, _identity(facts)[:5]))

            def revalidate_parents() -> None:
                for (component, parent, expected), child in zip(
                    nodes, descriptors[1:], strict=True
                ):
                    if (
                        _identity(os.fstat(child))[:5] != expected
                        or _identity(os.stat(component, dir_fd=parent, follow_symlinks=False))[:5]
                        != expected
                    ):
                        raise WAWManifestInstallError("manifest parent entry changed")

            revalidate_parents()
            yield descriptor
            revalidate_parents()
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def _read(self, logical: str, maximum: int, *, executable: bool = False) -> bytes:
        path = self.root / logical.lstrip("/")
        with self._directory(str(Path(logical).parent)) as parent:
            fd = os.open(Path(logical).name, _FILE, dir_fd=parent)
            try:
                facts = os.fstat(fd)
                if (
                    not stat.S_ISREG(facts.st_mode)
                    or facts.st_uid != self.owner_uid
                    or facts.st_nlink != 1
                    or facts.st_mode & 0o7022
                    or not 0 < facts.st_size <= maximum
                    or executable
                    and facts.st_mode & 0o005 != 0o005
                ):
                    raise WAWManifestInstallError("manifest source provenance is invalid")
                raw = os.read(fd, maximum + 1)
                if len(raw) != facts.st_size or _identity(os.fstat(fd)) != _identity(facts):
                    raise WAWManifestInstallError("manifest source changed during read")
                if executable and (
                    len(raw) < 64 or raw[:7] != b"\x7fELF\x02\x01\x01" or raw[18:20] != b"\x3e\x00"
                ):
                    raise WAWManifestInstallError("native Linux x86_64 executable is required")
                self.observations.append((path, _identity(facts), False))
                if executable:
                    _validate_elf_header(raw[:64])
                return raw
            finally:
                os.close(fd)

    def observe(self) -> dict[str, Any]:
        self.observations.clear()
        with self._directory("/srv/agentbox/projects", runtime_leaf=True) as fd:
            facts = os.fstat(fd)
            project = {
                "manifest_revision": "1",
                "configured_root": "/srv/agentbox/projects",
                "root_device": RUNTIME_NAMESPACE_BINDING_V1,
                "root_mount_id": RUNTIME_NAMESPACE_BINDING_V1,
                "root_filesystem_id": _project_filesystem_identity(fd),
                "root_uid": str(facts.st_uid),
                "root_gid": str(facts.st_gid),
                "root_mode": format(stat.S_IMODE(facts.st_mode), "o"),
                "relative_key_grammar_version": "one-component-v1",
                "binding_digest_algorithm": "sha256-rfc8785",
                "no_shell_executable_path": "/bin/false",
                "no_shell_executable_digest": hashlib.sha256(
                    self._read("/usr/bin/false", 16 * 1024 * 1024, executable=True)
                ).hexdigest(),
            }
            self.observations.append((self.root / "srv/agentbox/projects", _identity(facts), True))
        entries = []
        for policy in EXECUTABLE_POLICIES_V1:
            if policy.kind in {"pane_bootstrap", "bridge", "attach_supervisor"}:
                assert policy.fixed_path is not None
                path = policy.fixed_path.replace("/current/", f"/releases/{self.version}/")
            elif policy.kind in {"claude", "codex"}:
                candidates = (f"/usr/local/bin/{policy.kind}", f"/usr/bin/{policy.kind}")
                path = next(
                    (path for path in candidates if (self.root / path.lstrip("/")).exists()), ""
                )
                if not path:
                    raise WAWManifestInstallError("both native vendor CLIs must be installed")
            else:
                assert policy.fixed_path is not None
                path = policy.fixed_path
            raw = self._read(path, policy.max_bytes, executable=True)
            entries.append(
                {
                    "kind": policy.kind,
                    "path": path,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "max_bytes": policy.max_bytes,
                    "version_identity": policy.version_identity,
                    "version_probe_id": policy.version_probe_id,
                }
            )
        base = f"/opt/agentbox/releases/{self.version}/waw/templates"
        policy_names = {
            "tmux.conf": "tmux.conf",
            "sandbox-policies.v1.json": "sandbox-policies.v1.json",
            "claude-managed-policy.v1.json": "claude/managed-settings.json",
            "codex-requirements.toml": "codex/requirements.toml",
            "codex-managed-config.toml": "codex/managed_config.toml",
        }
        policies = {
            name: self._read(f"{base}/{source}", 64 * 1024) for name, source in policy_names.items()
        }
        self.revalidate()
        return {
            "project": project,
            "inventory": encode_executable_inventory_v1({"executables": entries}),
            "policies": policies,
        }

    def revalidate(self) -> None:
        for path, observed, directory in self.observations:
            logical = "/" + str(path.relative_to(self.root))
            with self._directory(str(Path(logical).parent)) as parent:
                facts = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                current = _identity(facts)
                if directory:
                    current, expected = current[:5], observed[:5]
                else:
                    expected = observed
                if current != expected:
                    raise WAWManifestInstallError("manifest installation source changed")

    def assemble(
        self, observed: dict[str, Any], fingerprint: str, host_id: str
    ) -> tuple[bytes, dict[str, bytes]]:
        project = encode_project_root_manifest(observed["project"])
        cgroup = encode_cgroup_delegation_manifest(
            {
                "service_unit": "agentbox-runtime.service",
                "cgroup_mount_type": "cgroup2",
                "cgroup_mount_device": RUNTIME_NAMESPACE_BINDING_V1,
                "cgroup_mount_filesystem_id": SCOPED_CGROUP_FILESYSTEM_V1,
                "cgroup_schema_identity": "cgroup-v2",
                "delegate": True,
                "delegate_subgroup": SCOPED_CGROUP_WORKSPACES_V1,
                "protect_control_groups": SCOPED_CGROUP_PROTECTION_V1,
                "kill_mode": "process",
                "controllers": ["cpu", "memory", "pids"],
                "tasks_max": 256,
                "memory_max": 536870912,
                "memory_swap_max": 0,
                "cpu_quota_percent": 400,
                "cpu_quota_period_usec": 100000,
                "policy_template_digest": SCOPED_CGROUP_TEMPLATE_SHA256_V1,
            }
        )
        policies = observed["policies"]
        codex_policy = encode_codex_managed_policy_bundle_v1(
            requirements=policies["codex-requirements.toml"],
            managed_config=policies["codex-managed-config.toml"],
        )
        profiles = []
        for agent in ("claude", "codex"):
            profile = dict(INTERACTIVE_PROFILE_CONSTANTS_V1[agent])
            profile["managed_policy_digest"] = manifest_sha256(
                policies["claude-managed-policy.v1.json"] if agent == "claude" else codex_policy
            )
            profiles.append(profile)
        profile_bytes = encode_interactive_profile_bundle_v1({"profiles": profiles})
        socket_policy = (
            b'{"control":"workspace-control.sock","mode":"0660","peer":"agentbox",'
            b'"schema_version":"waw-socket-policy-v1","stream":"workspace-stream.sock"}'
        )
        common = {
            "runtime_host_installation_id": host_id,
            "runtime_host_installation_revision": "1",
            "runtime_attestation_x25519_fingerprint": fingerprint,
            "enrollment_epoch": "1",
            "enrollment_state": "bootstrap",
        }
        runtime = encode_runtime_host_manifest_v2(
            {
                **common,
                **RUNTIME_HOST_MANIFEST_V2_PATHS,
                "project_root_manifest_digest": manifest_sha256(project),
                "cgroup_delegation_manifest_digest": manifest_sha256(cgroup),
                "executable_inventory_digest": manifest_sha256(observed["inventory"]),
                "interactive_profile_bundle_digest": manifest_sha256(profile_bytes),
                "tmux_config_digest": manifest_sha256(policies["tmux.conf"]),
                "sandbox_policy_bundle_digest": manifest_sha256(
                    policies["sandbox-policies.v1.json"]
                ),
                "socket_policy_digest": manifest_sha256(socket_policy),
            }
        )
        anchor = encode_api_host_anchor_v2(
            {
                **common,
                "runtime_manifest_schema": RUNTIME_HOST_MANIFEST_SCHEMA_V2,
                "host_manifest_digest": manifest_sha256(runtime),
                "project_root_manifest_digest": manifest_sha256(project),
            }
        )
        public = {
            "api-host-anchor.v2.json": anchor,
            "project-root.v1.json": project,
            "cgroup-delegation.v1.json": cgroup,
            "executable-inventory.v1.json": observed["inventory"],
            "interactive-profiles.v1.json": profile_bytes,
            "socket-policy.v1.json": socket_policy,
            "codex-managed-policy.v1.json": codex_policy,
            **policies,
        }
        verify_api_host_anchor_v2_cross_manifest(
            anchor,
            runtime,
            project,
            cgroup,
            observed["inventory"],
            profile_bytes,
            policies["tmux.conf"],
            policies["sandbox-policies.v1.json"],
            socket_policy,
            policies["claude-managed-policy.v1.json"],
            codex_policy,
            policies["codex-requirements.toml"],
            policies["codex-managed-config.toml"],
        )
        return runtime, public

    def publish(
        self, observed: dict[str, Any], fingerprint: str, *, recover: bool = False
    ) -> WAWManifestPublication:
        with self._directory("/var/lib/agentbox-waw") as private_parent:
            host_id = (
                "wri_"
                + hashlib.sha256(
                    ("agentbox-installation-v1:" + fingerprint).encode("ascii")
                ).hexdigest()[:32]
            )
            try:
                os.stat(_PENDING, dir_fd=private_parent, follow_symlinks=False)
                pending_exists = True
            except FileNotFoundError:
                pending_exists = False
            existing_private = None
            for name in (_PRIVATE, _PENDING):
                try:
                    fd = os.open(name, _FILE, dir_fd=private_parent)
                    try:
                        facts = os.fstat(fd)
                        if (
                            not stat.S_ISREG(facts.st_mode)
                            or facts.st_uid != self.owner_uid
                            or facts.st_gid != self.runtime_gid
                            or stat.S_IMODE(facts.st_mode) != 0o440
                            or facts.st_nlink not in {1, 2}
                            or not (0 if name == _PENDING and recover else 1)
                            <= facts.st_size
                            <= 64 * 1024
                        ):
                            raise WAWManifestInstallError("existing private manifest is unsafe")
                        raw = os.read(fd, 64 * 1024 + 1)
                        if _identity(os.fstat(fd)) != _identity(facts):
                            raise WAWManifestInstallError("private manifest changed during read")
                    finally:
                        os.close(fd)
                except FileNotFoundError:
                    continue
                try:
                    host_id = decode_runtime_host_manifest_v2(raw).runtime_host_installation_id
                except ValueError:
                    if name != _PENDING or not recover:
                        raise
                    expected, _public = self.assemble(observed, fingerprint, host_id)
                    if not expected.startswith(raw) or len(raw) >= len(expected):
                        raise WAWManifestInstallError(
                            "pending manifest prefix does not match"
                        ) from None
                if name == _PRIVATE:
                    existing_private = raw
                break
            runtime, public = self.assemble(observed, fingerprint, host_id)
            if existing_private is not None and existing_private != runtime:
                raise WAWManifestInstallError("existing manifest requires explicit rotation")
            if pending_exists and not recover:
                raise WAWManifestInstallError("interrupted manifest publication requires --recover")
            self.revalidate()
            self._create_file(
                private_parent,
                _PENDING,
                runtime,
                0o440,
                self.runtime_gid,
                allow_existing=recover or not pending_exists,
                repair_prefix=recover,
            )
            share = self.root / "usr/share/agentbox"
            if not share.exists():
                with self._directory("/usr/share") as parent:
                    os.mkdir("agentbox", 0o755, dir_fd=parent)
                    os.chown(
                        "agentbox",
                        self.owner_uid,
                        self.root_gid,
                        dir_fd=parent,
                        follow_symlinks=False,
                    )
            with self._directory("/usr/share/agentbox") as parent:
                try:
                    os.mkdir("waw", 0o755, dir_fd=parent)
                    os.chown(
                        "waw", self.owner_uid, self.root_gid, dir_fd=parent, follow_symlinks=False
                    )
                except FileExistsError:
                    pass
                with self._directory("/usr/share/agentbox/waw") as directory:
                    for name in WAW_PUBLIC_MANIFEST_FILENAMES_V2:
                        self.revalidate()
                        self._create_file(
                            directory,
                            name,
                            public[name],
                            0o444,
                            self.root_gid,
                            allow_existing=recover or not pending_exists,
                            repair_prefix=recover,
                        )
                    if set(os.listdir(directory)) != set(WAW_PUBLIC_MANIFEST_FILENAMES_V2):
                        raise WAWManifestInstallError(
                            "public manifest directory has unexpected files"
                        )
                    os.fsync(directory)
            self.revalidate()
            try:
                os.link(
                    _PENDING,
                    _PRIVATE,
                    src_dir_fd=private_parent,
                    dst_dir_fd=private_parent,
                    follow_symlinks=False,
                )
            except FileExistsError:
                self._require_bytes(private_parent, _PRIVATE, runtime, 0o440, self.runtime_gid)
            os.fsync(private_parent)
            os.unlink(_PENDING, dir_fd=private_parent)
            os.fsync(private_parent)
            return WAWManifestPublication("prepared", host_id, manifest_sha256(runtime))

    def _create_file(
        self,
        parent: int,
        name: str,
        raw: bytes,
        mode: int,
        gid: int,
        *,
        allow_existing: bool,
        repair_prefix: bool = False,
    ) -> None:
        try:
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                mode,
                dir_fd=parent,
            )
        except FileExistsError:
            if not allow_existing:
                raise WAWManifestInstallError("manifest publication collision") from None
            try:
                self._require_bytes(parent, name, raw, mode, gid)
            except WAWManifestInstallError:
                if not repair_prefix:
                    raise
                self._complete_prefix(parent, name, raw, mode, gid)
            return
        try:
            os.fchown(fd, self.owner_uid, gid)
            os.fchmod(fd, mode)
            view = memoryview(raw)
            while view:
                count = os.write(fd, view)
                if count <= 0:
                    raise WAWManifestInstallError("manifest write is incomplete")
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(parent)

    def _complete_prefix(self, parent: int, name: str, raw: bytes, mode: int, gid: int) -> None:
        fd = os.open(name, _FILE, dir_fd=parent)
        mode_changed = False
        try:
            facts = os.fstat(fd)
            if (
                not stat.S_ISREG(facts.st_mode)
                or facts.st_uid != self.owner_uid
                or facts.st_gid != gid
                or stat.S_IMODE(facts.st_mode) != mode
                or facts.st_nlink != 1
                or not 0 <= facts.st_size < len(raw)
                or os.read(fd, facts.st_size + 1) != raw[: facts.st_size]
            ):
                raise WAWManifestInstallError("manifest recovery prefix is unsafe or different")
            # Root normally bypasses the read-only publication mode. The
            # temporary owner-write bit also supports the non-root fixture;
            # restored mode is required before admission by the strict loader.
            os.fchmod(fd, 0o600)
            mode_changed = True
            writer = os.open(name, os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            try:
                opened = os.fstat(writer)
                if (opened.st_dev, opened.st_ino) != (facts.st_dev, facts.st_ino):
                    raise WAWManifestInstallError("manifest recovery entry changed")
                os.lseek(writer, facts.st_size, os.SEEK_SET)
                view = memoryview(raw)[facts.st_size :]
                while view:
                    count = os.write(writer, view)
                    if count <= 0:
                        raise WAWManifestInstallError("manifest recovery write is incomplete")
                    view = view[count:]
                os.fsync(writer)
            finally:
                os.close(writer)
        finally:
            if mode_changed:
                os.fchmod(fd, mode)
            os.close(fd)
        os.fsync(parent)

    def _require_bytes(self, parent: int, name: str, raw: bytes, mode: int, gid: int) -> None:
        fd = os.open(name, _FILE, dir_fd=parent)
        try:
            facts = os.fstat(fd)
            if (
                not stat.S_ISREG(facts.st_mode)
                or facts.st_uid != self.owner_uid
                or facts.st_gid != gid
                or stat.S_IMODE(facts.st_mode) != mode
                or facts.st_nlink not in ({1, 2} if name in {_PRIVATE, _PENDING} else {1})
                or facts.st_size != len(raw)
                or os.read(fd, len(raw) + 1) != raw
            ):
                raise WAWManifestInstallError("existing manifest does not match this publication")
            if facts.st_nlink == 2:
                other = _PRIVATE if name == _PENDING else _PENDING
                paired = os.stat(other, dir_fd=parent, follow_symlinks=False)
                if (paired.st_dev, paired.st_ino) != (facts.st_dev, facts.st_ino):
                    raise WAWManifestInstallError("private manifest link pair does not match")
        finally:
            os.close(fd)
