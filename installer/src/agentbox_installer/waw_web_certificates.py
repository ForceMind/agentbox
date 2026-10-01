"""Root-only fixed ACME policy and recoverable TLS pair publication."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlsplit

from agentbox_installer.waw_activation import WAWActivationTransaction
from agentbox_installer.waw_manifest_install import WAWManifestInstallError
from agentbox_installer.waw_web_configuration import validate_web_tls
from agentbox_installer.waw_web_ingress import render_web_ingress
from agentbox_installer.waw_web_publication import WAWWebPublisher

_ROOT = "/etc/agentbox-web"
_ACME = _ROOT + "/acme"
_TLS = _ROOT + "/tls"
_CA = "https://acme-v02.api.letsencrypt.org/directory"
_FILES = {"fullchain.pem": 0o644, "privkey.pem": 0o600}


def web_acme_argv(origin: str, email: str) -> tuple[str, ...]:
    render_web_ingress(origin)
    if (
        len(email) > 254
        or not email.isascii()
        or email.startswith("-")
        or re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9.-]+\.[a-z]{2,}", email) is None
    ):
        raise ValueError("a valid ASCII ACME contact email is required")
    return (
        "/usr/bin/certbot",
        "certonly",
        "--standalone",
        "--non-interactive",
        "--agree-tos",
        "--keep-until-expiring",
        "--no-directory-hooks",
        "--cert-name",
        "agentbox-web",
        "--domains=" + str(urlsplit(origin).hostname),
        "--email=" + email,
        "--server",
        _CA,
        "--config",
        _ACME + "/cli.ini",
        "--config-dir",
        _ACME,
        "--work-dir",
        "/var/lib/agentbox-web/acme-work",
        "--logs-dir",
        "/var/lib/agentbox-web/acme-log",
    )


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


class WAWWebCertificates:
    def __init__(self, publisher: WAWWebPublisher) -> None:
        self.publisher = publisher
        self.issuer = publisher.issuer
        self.reader = WAWActivationTransaction(
            self.issuer, publisher.pin, api_gid=self.issuer.root_gid
        )

    def _read(self, logical: str, name: str, mode: int) -> bytes:
        with self.issuer._directory(logical) as parent:
            return self.reader._read(
                parent, name, mode=mode, gid=self.issuer.root_gid, maximum=262144
            )

    def _replace(self, logical: str, name: str, raw: bytes, mode: int, recover: bool) -> None:
        pending = "." + name + "." + hashlib.sha256(raw).hexdigest()[:16]
        with self.issuer._directory(logical) as parent:
            self.issuer._create_file(
                parent,
                pending,
                raw,
                mode,
                self.issuer.root_gid,
                allow_existing=recover,
                repair_prefix=recover,
            )
            os.replace(pending, name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)

    def _acme_pair(self) -> dict[str, bytes]:
        files: dict[str, bytes] = {}
        revisions: set[str] = set()
        with self.issuer._directory(_ACME + "/live/agentbox-web") as parent:
            for name in _FILES:
                facts = os.stat(name, dir_fd=parent, follow_symlinks=False)
                target = os.readlink(name, dir_fd=parent)
                match = re.fullmatch(
                    r"\.\./\.\./archive/agentbox-web/" + name[:-4] + r"([1-9][0-9]*)\.pem", target
                )
                if (
                    not stat.S_ISLNK(facts.st_mode)
                    or facts.st_uid != self.issuer.owner_uid
                    or facts.st_gid != self.issuer.root_gid
                    or facts.st_nlink != 1
                    or match is None
                ):
                    raise WAWManifestInstallError("ACME certificate link is unsafe")
                revisions.add(match[1])
                files[name] = self._read(
                    _ACME + "/archive/agentbox-web", name[:-4] + match[1] + ".pem", _FILES[name]
                )
        if len(revisions) != 1:
            raise WAWManifestInstallError("ACME certificate/key revisions disagree")
        return files

    def _state(self, origin: str) -> dict[str, object] | None:
        try:
            raw = self._read(_ROOT, "tls-publication.v1.json", 0o600)
        except FileNotFoundError:
            return None
        state = json.loads(raw)
        if (
            type(state) is not dict
            or set(state) != {"schema_version", "origin", "phase", "files", "previous"}
            or state["schema_version"] != "agentbox-web-tls-publication.v1"
            or state["origin"] != origin
            or state["phase"] not in {"preparing", "published"}
            or raw != _canonical(state)
        ):
            raise WAWManifestInstallError("TLS publication record is invalid")
        for key in ("files", "previous"):
            values = state[key]
            if (
                not isinstance(values, dict)
                or set(values) not in ({*_FILES}, set())
                or key == "files"
                and not values
                or any(
                    not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
                    for value in values.values()
                )
            ):
                raise WAWManifestInstallError("TLS publication hashes are invalid")
        return state

    def _verify_current(self, state: dict[str, object] | None, *, recover: bool) -> None:
        if state is not None and state["phase"] == "preparing" and not recover:
            raise WAWManifestInstallError("matching TLS recovery requires --recover")
        tls_path = self.issuer.root / _TLS.lstrip("/")
        if not (tls_path.exists() or tls_path.is_symlink()):
            if state is not None:
                raise WAWManifestInstallError("managed TLS directory is missing")
            return
        previous = (
            {}
            if state is None
            else (state["files"] if state["phase"] == "published" else state["previous"])
        )
        new = state["files"] if state is not None and state["phase"] == "preparing" else {}
        assert isinstance(previous, dict) and isinstance(new, dict)
        pending = {"." + name + "." + str(digest)[:16] for name, digest in new.items()}
        with self.issuer._directory(_TLS) as parent:
            facts = os.fstat(parent)
            if facts.st_gid != self.issuer.root_gid or stat.S_IMODE(facts.st_mode) != 0o700:
                raise WAWManifestInstallError("TLS directory provenance is invalid")
            if set(os.listdir(parent)) - set(_FILES) - (pending if recover else set()):
                raise WAWManifestInstallError("TLS directory contains foreign entries")
            for name, mode in _FILES.items():
                try:
                    raw = self._read(_TLS, name, mode)
                except FileNotFoundError:
                    if name in previous:
                        raise
                    continue
                if hashlib.sha256(raw).hexdigest() not in {previous.get(name), new.get(name)}:
                    raise WAWManifestInstallError("TLS file is foreign or changed")

    def provision(
        self,
        *,
        origin: str,
        email: str,
        agree_terms: bool,
        plan: bool,
        recover: bool,
        issue: Callable[[tuple[str, ...]], None],
    ) -> dict[str, object]:
        argv = web_acme_argv(origin, email)
        policy = _canonical(
            {
                "schema_version": "agentbox-web-acme.v1",
                "origin": origin,
                "email": email,
                "server": _CA,
                "terms_accepted": True,
            }
        )
        root_path = self.issuer.root / _ROOT.lstrip("/")
        policy_path = root_path / "acme-policy.v1.json"
        if (policy_path.exists() or policy_path.is_symlink()) and self._read(
            _ROOT, policy_path.name, 0o600
        ) != policy:
            raise WAWManifestInstallError("ACME policy differs; explicit migration required")
        acme_path = self.issuer.root / _ACME.lstrip("/")
        if not policy_path.exists() and (acme_path.exists() or acme_path.is_symlink()):
            with self.issuer._directory(_ACME) as parent:
                if os.listdir(parent):
                    raise WAWManifestInstallError("unmanaged ACME directory cannot be adopted")
        state = self._state(origin) if root_path.exists() else None
        self._verify_current(state, recover=recover)
        result: dict[str, object] = {
            "status": "validated" if plan else "published",
            "origin": origin,
            "requires_port": 80,
            "requires_terms_acceptance": not agree_terms,
            "services_started": False,
            "changed": False,
            "qualified": False,
        }
        if plan:
            return result
        if not agree_terms:
            raise ValueError("explicit ACME terms acceptance is required")
        for logical, mode in (
            (_ROOT, 0o755),
            (_ACME, 0o700),
            ("/var/lib/agentbox-web", 0o755),
            ("/var/lib/agentbox-web/acme-work", 0o700),
            ("/var/lib/agentbox-web/acme-log", 0o700),
        ):
            self.publisher._directory(logical, mode=mode)
        if not policy_path.exists():
            self._replace(_ROOT, policy_path.name, policy, 0o600, recover)
        with self.issuer._directory(_ACME) as parent:
            self.issuer._create_file(
                parent,
                "cli.ini",
                b"# AgentBox fixed ACME policy\n",
                0o600,
                self.issuer.root_gid,
                allow_existing=True,
                repair_prefix=recover,
            )
        if state is None or state["phase"] != "preparing":
            issue(argv)
        files = self._acme_pair()
        expiration = validate_web_tls(
            files["fullchain.pem"], files["privkey.pem"], origin, datetime.now(UTC)
        )
        digests = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
        previous: dict[str, str] = {}
        if state is not None:
            values = state["files"] if state["phase"] == "published" else state["previous"]
            if not isinstance(values, dict):
                raise WAWManifestInstallError("TLS publication hashes are invalid")
            previous = values
            if state["phase"] == "preparing" and (not recover or state["files"] != digests):
                raise WAWManifestInstallError("matching TLS recovery requires --recover")
        self._verify_current(state, recover=recover)
        if state is not None and state["phase"] == "published" and state["files"] == digests:
            result["tls_valid_until"] = expiration
            return result
        self.publisher._directory(_TLS, mode=0o700)
        record = {
            "schema_version": "agentbox-web-tls-publication.v1",
            "origin": origin,
            "phase": "preparing",
            "files": digests,
            "previous": previous,
        }
        self._replace(_ROOT, "tls-publication.v1.json", _canonical(record), 0o600, recover)
        for name, mode in _FILES.items():
            self._replace(_TLS, name, files[name], mode, recover)
        record["phase"] = "published"
        self._replace(_ROOT, "tls-publication.v1.json", _canonical(record), 0o600, recover)
        result["tls_valid_until"] = expiration
        result["changed"] = True
        return result

    def policy(self) -> tuple[str, str]:
        raw = self._read(_ROOT, "acme-policy.v1.json", 0o600)
        value = json.loads(raw)
        if (
            type(value) is not dict
            or set(value) != {"schema_version", "origin", "email", "server", "terms_accepted"}
            or value["schema_version"] != "agentbox-web-acme.v1"
            or value["server"] != _CA
            or value["terms_accepted"] is not True
            or type(value["origin"]) is not str
            or type(value["email"]) is not str
            or raw != _canonical(value)
        ):
            raise WAWManifestInstallError("fixed ACME policy is invalid")
        web_acme_argv(value["origin"], value["email"])
        return value["origin"], value["email"]
