"""Root-only immutable Web overlay publication, separate from original artifacts."""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import os
import re
import stat
from datetime import UTC, datetime
from pathlib import PurePosixPath

from agentbox_runtime.waw_manifest_codecs import CrossManifestPinV2

from agentbox_installer.artifact import RELEASE_MANIFEST_NAME, load_manifest
from agentbox_installer.waw_https_bootstrap import encode_https_bootstrap
from agentbox_installer.waw_manifest_install import WAWManifestInstallError, WAWManifestIssuer
from agentbox_installer.waw_web_ingress import render_web_ingress

_ROOT = "/var/lib/agentbox-web"


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode()


class WAWWebPublisher:
    def __init__(self, issuer: WAWManifestIssuer, pin: CrossManifestPinV2) -> None:
        self.issuer = issuer
        self.pin = pin

    def _current_logical(self) -> str:
        with self.issuer._directory(_ROOT) as parent:
            facts = os.stat("current", dir_fd=parent, follow_symlinks=False)
            target = os.readlink("current", dir_fd=parent)
            if (
                not stat.S_ISLNK(facts.st_mode)
                or facts.st_uid != self.issuer.owner_uid
                or re.fullmatch(r"releases/[0-9a-f]{64}", target) is None
            ):
                raise WAWManifestInstallError("Web current pointer is unsafe")
        return _ROOT + "/" + target

    def current_origin(self) -> str:
        raw = self.issuer._read(
            self._current_logical() + "/.well-known/agentbox/waw-bootstrap.v1.json", 8192
        )
        value = json.loads(raw)
        if type(value) is not dict or type(value.get("origin")) is not str:
            raise WAWManifestInstallError("public bootstrap Origin is invalid")
        origin = str(value["origin"])
        self.inspect_current(origin, allow_expired=True)
        return origin

    def inspect_current(self, origin: str, *, allow_expired: bool = False) -> str:
        """Verify the complete current overlay against the active cross-pinned source."""
        logical = self._current_logical()
        target = logical[len(_ROOT) + 1 :]
        raw = self.issuer._read(logical + "/.well-known/agentbox/waw-bootstrap.v1.json", 8192)
        try:
            bootstrap = json.loads(raw)
            if type(bootstrap) is not dict:
                raise ValueError("public bootstrap must be an object")
            valid_from = datetime.fromisoformat(bootstrap["valid_from"])
            valid_until = datetime.fromisoformat(bootstrap["valid_until"])
        except (ValueError, TypeError, KeyError) as exc:
            raise WAWManifestInstallError("public bootstrap is malformed") from exc
        identity, files = self._observe(
            origin=origin, valid_from=valid_from, valid_until=valid_until
        )
        now = datetime.now(UTC)
        if (
            target != "releases/" + identity
            or now < valid_from
            or not allow_expired
            and now >= valid_until
        ):
            raise WAWManifestInstallError("Web publication is stale or inconsistent")
        self._verify(logical, files)
        self._prepare_ingress(origin, plan=True, recover=False)
        return identity

    def _prepare_ingress(self, origin: str, *, plan: bool, recover: bool) -> None:
        unit = (
            importlib.resources.files("agentbox_installer")
            .joinpath("assets/systemd/agentbox-web.service")
            .read_bytes()
        )
        targets = {
            "/etc/agentbox-web/nginx.conf": render_web_ingress(origin),
            "/etc/systemd/system/agentbox-web.service": unit,
        }
        for name in ("agentbox-web-maintenance.service", "agentbox-web-maintenance.timer"):
            targets["/etc/systemd/system/" + name] = (
                importlib.resources.files("agentbox_installer")
                .joinpath("assets/systemd/" + name)
                .read_bytes()
            )
        # Check all existing entries before creating any configuration. No
        # replacement of another ingress or implicit Origin change is allowed.
        for logical, raw in targets.items():
            path = self.issuer.root / logical.lstrip("/")
            if path.exists() or path.is_symlink():
                with self.issuer._directory(str(PurePosixPath(logical).parent)) as parent:
                    try:
                        self.issuer._require_bytes(
                            parent, path.name, raw, 0o444, self.issuer.root_gid
                        )
                    except WAWManifestInstallError:
                        if not recover or plan:
                            raise
                        # _create_file only repairs an exact, safely owned prefix.
                        # This is checked below without replacing foreign bytes.
                        observed = self.issuer._read(logical, len(raw))
                        facts = path.lstat()
                        if (
                            not raw.startswith(observed)
                            or len(observed) >= len(raw)
                            or not stat.S_ISREG(facts.st_mode)
                            or facts.st_nlink != 1
                            or facts.st_gid != self.issuer.root_gid
                            or stat.S_IMODE(facts.st_mode) != 0o444
                        ):
                            raise WAWManifestInstallError(
                                "Web ingress recovery is unsafe"
                            ) from None
        if plan:
            return
        for logical, raw in targets.items():
            parent_path = PurePosixPath(logical).parent
            accumulated = ""
            for component in parent_path.parts[1:]:
                accumulated += "/" + component
                self._directory(accumulated)
            with self.issuer._directory(str(parent_path)) as parent:
                self.issuer._create_file(
                    parent,
                    PurePosixPath(logical).name,
                    raw,
                    0o444,
                    self.issuer.root_gid,
                    allow_existing=True,
                    repair_prefix=recover,
                )

    def _directory(self, logical: str, *, mode: int = 0o755) -> None:
        parent, name = str(PurePosixPath(logical).parent), PurePosixPath(logical).name
        with self.issuer._directory(parent) as descriptor:
            try:
                os.mkdir(name, mode, dir_fd=descriptor)
            except FileExistsError:
                pass
            else:
                fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                try:
                    os.fchown(fd, self.issuer.owner_uid, self.issuer.root_gid)
                    os.fchmod(fd, mode)
                    os.fsync(fd)
                finally:
                    os.close(fd)
                os.fsync(descriptor)
        with self.issuer._directory(logical) as descriptor:
            facts = os.fstat(descriptor)
            if facts.st_gid != self.issuer.root_gid or stat.S_IMODE(facts.st_mode) != mode:
                raise WAWManifestInstallError("Web publication directory is unsafe")

    def _observe(
        self, *, origin: str, valid_from: datetime, valid_until: datetime
    ) -> tuple[str, dict[str, bytes]]:
        release = f"/opt/agentbox/releases/{self.issuer.version}"
        manifest_raw = self.issuer._read(release + "/" + RELEASE_MANIFEST_NAME, 4 * 1024 * 1024)
        manifest = load_manifest(self.issuer.root / release.lstrip("/"))
        if manifest.version != self.issuer.version:
            raise WAWManifestInstallError("Web source release changed")
        files: dict[str, bytes] = {}
        for name, digest in manifest.files.items():
            if not name.startswith("web/dist/"):
                continue
            relative = name[len("web/dist/") :]
            parts = PurePosixPath(relative).parts
            if not parts or relative.startswith("/") or any(part in {".", ".."} for part in parts):
                raise WAWManifestInstallError("Web source path is invalid")
            raw = self.issuer._read(release + "/" + name, 16 * 1024 * 1024)
            if hashlib.sha256(raw).hexdigest() != digest:
                raise WAWManifestInstallError("Web source asset changed")
            files[relative] = raw
        if (
            "index.html" not in files
            or len(files) > 4096
            or sum(map(len, files.values())) > 64 * 1024 * 1024
        ):
            raise WAWManifestInstallError("Web source assets are incomplete or oversized")
        identity = hashlib.sha256(
            _canonical(
                {
                    "origin": origin,
                    "version": self.issuer.version,
                    "host_manifest_digest": self.pin.runtime_manifest_digest,
                    "source_manifest_digest": hashlib.sha256(manifest_raw).hexdigest(),
                    "valid_from": valid_from.isoformat(),
                    "valid_until": valid_until.isoformat(),
                }
            )
        ).hexdigest()
        bootstrap = encode_https_bootstrap(
            self.pin,
            origin=origin,
            build_identity=identity,
            version=self.issuer.version,
            valid_from=valid_from,
            valid_until=valid_until,
        )
        html = files["index.html"].decode("utf-8")
        if (
            html.count("</head>") != 1
            or "agentbox-waw-trust-profile" in html
            or "agentbox-waw-build-identity" in html
        ):
            raise WAWManifestInstallError("Web index cannot accept fixed profile markers")
        markers = (
            f'<meta name="agentbox-waw-trust-profile" content="https-web-v1">'
            f'<meta name="agentbox-waw-build-identity" content="{identity}">'
        )
        files["index.html"] = html.replace("</head>", markers + "</head>").encode()
        files[".well-known/agentbox/waw-bootstrap.v1.json"] = bootstrap
        files[".publication.v1.json"] = _canonical(
            {
                "schema_version": "agentbox-waw-web-publication.v1",
                "build_identity": identity,
                "origin": origin,
                "version": self.issuer.version,
                "host_manifest_digest": self.pin.runtime_manifest_digest,
                "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
            }
        )
        self.issuer.revalidate()
        return identity, files

    def publish(
        self,
        *,
        origin: str,
        valid_from: datetime,
        valid_until: datetime,
        plan: bool = False,
        recover: bool = False,
    ) -> dict[str, object]:
        identity, files = self._observe(
            origin=origin, valid_from=valid_from, valid_until=valid_until
        )
        result: dict[str, object] = {
            "status": "validated" if plan else "published",
            "build_identity": identity,
            "origin": origin,
            "runtime_fingerprint": self.pin.runtime.runtime_attestation_x25519_fingerprint,
            "services_started": False,
            "ingress_config": "/etc/agentbox-web/nginx.conf",
            "ingress_unit": "agentbox-web.service",
            "ingress_activation_required": True,
        }
        self._prepare_ingress(origin, plan=plan, recover=recover)
        if plan:
            return result
        self._directory(_ROOT)
        self._directory(_ROOT + "/releases")
        final = _ROOT + "/releases/" + identity
        pending = _ROOT + "/releases/.pending-" + identity
        with self.issuer._directory(_ROOT) as parent:
            try:
                current = os.stat("current", dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                if (
                    not stat.S_ISLNK(current.st_mode)
                    or current.st_uid != self.issuer.owner_uid
                    or re.fullmatch(r"releases/[0-9a-f]{64}", os.readlink("current", dir_fd=parent))
                    is None
                ):
                    raise WAWManifestInstallError("Web current pointer is unsafe")
        target = self.issuer.root / final.lstrip("/")
        if target.exists() or target.is_symlink():
            self._verify(final, files)
        else:
            stage = self.issuer.root / pending.lstrip("/")
            if (stage.exists() or stage.is_symlink()) and not recover:
                raise WAWManifestInstallError("interrupted Web publication requires --recover")
            self._directory(pending, mode=0o700)
            directories = sorted(
                {str(PurePosixPath(name).parent) for name in files} - {"."},
                key=lambda name: (name.count("/"), name),
            )
            for directory in directories:
                accumulated = pending
                for part in PurePosixPath(directory).parts:
                    accumulated += "/" + part
                    self._directory(accumulated)
            for name, raw in files.items():
                self.issuer.revalidate()
                with self.issuer._directory(
                    pending + "/" + str(PurePosixPath(name).parent)
                ) as parent:
                    self.issuer._create_file(
                        parent,
                        PurePosixPath(name).name,
                        raw,
                        0o444,
                        self.issuer.root_gid,
                        allow_existing=recover,
                        repair_prefix=recover,
                    )
            self._verify(pending, files)
            with self.issuer._directory(_ROOT + "/releases") as parent:
                os.rename(".pending-" + identity, identity, src_dir_fd=parent, dst_dir_fd=parent)
                os.fsync(parent)
        self._verify(final, files)
        with self.issuer._directory(_ROOT + "/releases") as parent:
            descriptor = os.open(
                identity, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
            )
            try:
                facts = os.fstat(descriptor)
                if (
                    facts.st_uid != self.issuer.owner_uid
                    or facts.st_gid != self.issuer.root_gid
                    or stat.S_IMODE(facts.st_mode) not in {0o700, 0o755}
                ):
                    raise WAWManifestInstallError("Web publication root mode is unsafe")
                os.fchmod(descriptor, 0o755)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.fsync(parent)
        with self.issuer._directory(_ROOT) as parent:
            temporary = ".current-" + identity
            try:
                os.symlink("releases/" + identity, temporary, dir_fd=parent)
            except FileExistsError:
                facts = os.stat(temporary, dir_fd=parent, follow_symlinks=False)
                if (
                    not recover
                    or not stat.S_ISLNK(facts.st_mode)
                    or facts.st_uid != self.issuer.owner_uid
                    or os.readlink(temporary, dir_fd=parent) != "releases/" + identity
                ):
                    raise WAWManifestInstallError("Web pending pointer is unsafe") from None
            os.replace(temporary, "current", src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        return result

    def _verify(self, logical: str, files: dict[str, bytes]) -> None:
        expected_dirs = {"."}
        for name in files:
            relative_parent = PurePosixPath(name).parent
            while str(relative_parent) != ".":
                expected_dirs.add(str(relative_parent))
                relative_parent = relative_parent.parent
        for directory in expected_dirs:
            with self.issuer._directory(logical + "/" + directory) as parent:
                expected = {
                    PurePosixPath(name).name
                    for name in files
                    if str(PurePosixPath(name).parent) == directory
                }
                expected |= {
                    PurePosixPath(name).name
                    for name in expected_dirs - {"."}
                    if str(PurePosixPath(name).parent) == directory
                }
                if set(os.listdir(parent)) != expected:
                    raise WAWManifestInstallError("Web publication tree is not closed")
                for name in files:
                    if str(PurePosixPath(name).parent) == directory:
                        self.issuer._require_bytes(
                            parent,
                            PurePosixPath(name).name,
                            files[name],
                            0o444,
                            self.issuer.root_gid,
                        )
