from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from agentbox_installer.host import HostMutationError, HostOperations
from agentbox_installer.layout import InstallLayout
from agentbox_installer.lifecycle import AgentBoxInstaller
from agentbox_installer.waw_manifest_install import WAWManifestInstallError
from agentbox_installer.waw_web_certificates import WAWWebCertificates, web_acme_argv
from test_installer_waw_web_configuration import _tls
from test_installer_waw_web_publication import _publisher


def _certificates(tmp_path: Path) -> tuple[WAWWebCertificates, Path]:
    publisher, root, _args = _publisher(tmp_path)
    (root / "etc").mkdir(exist_ok=True)
    return WAWWebCertificates(publisher), root


def _issued(root: Path, revision: int, pair: tuple[bytes, bytes]) -> None:
    base = root / "etc/agentbox-web/acme"
    archive = base / "archive/agentbox-web"
    live = base / "live/agentbox-web"
    for directory in (archive, live):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
    for name, raw, mode in (("fullchain", pair[0], 0o644), ("privkey", pair[1], 0o600)):
        path = archive / f"{name}{revision}.pem"
        path.write_bytes(raw)
        path.chmod(mode)
        link = live / f"{name}.pem"
        link.unlink(missing_ok=True)
        link.symlink_to(f"../../archive/agentbox-web/{name}{revision}.pem")


def _args() -> dict[str, object]:
    return dict(
        origin="https://example.agentbox.test",
        email="owner@example.test",
        agree_terms=True,
        plan=False,
        recover=False,
    )


def test_certificate_plan_and_terms_gate_are_readonly(tmp_path: Path) -> None:
    certificates, root = _certificates(tmp_path)
    before = {str(path) for path in root.rglob("*")}

    def forbidden(_argv: tuple[str, ...]) -> None:
        raise AssertionError("read-only plan must not issue a certificate")

    args = _args() | {"agree_terms": False, "plan": True}
    result = certificates.provision(**args, issue=forbidden)  # type: ignore[arg-type]
    assert result["requires_terms_acceptance"] is True
    assert before == {str(path) for path in root.rglob("*")}
    with pytest.raises(ValueError, match="terms"):
        certificates.provision(**(args | {"plan": False}), issue=forbidden)  # type: ignore[arg-type]
    assert before == {str(path) for path in root.rglob("*")}


def test_certificate_pair_publish_idempotence_and_renewal(tmp_path: Path) -> None:
    certificates, root = _certificates(tmp_path)
    pair = _tls()
    calls: list[tuple[str, ...]] = []

    def issue(argv: tuple[str, ...]) -> None:
        calls.append(argv)
        _issued(root, 1, pair)

    certificates.provision(**_args(), issue=issue)  # type: ignore[arg-type]
    tls = root / "etc/agentbox-web/tls"
    assert (tls / "fullchain.pem").read_bytes() == pair[0]
    assert (tls / "privkey.pem").read_bytes() == pair[1]
    assert (tls / "privkey.pem").stat().st_mode & 0o777 == 0o600
    inode = (tls / "privkey.pem").stat().st_ino
    certificates.provision(**_args(), issue=issue)  # type: ignore[arg-type]
    assert (tls / "privkey.pem").stat().st_ino == inode
    assert all(
        argv == web_acme_argv("https://example.agentbox.test", "owner@example.test")
        for argv in calls
    )
    newer = _tls()
    certificates.provision(**_args(), issue=lambda _argv: _issued(root, 2, newer))  # type: ignore[arg-type]
    assert (tls / "privkey.pem").read_bytes() == newer[1]
    state = json.loads((tls.parent / "tls-publication.v1.json").read_bytes())
    assert state["phase"] == "published"
    assert state["previous"] != state["files"]


def test_certificate_partial_pair_has_sealed_explicit_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    certificates, root = _certificates(tmp_path)
    pair = _tls()
    calls: list[str] = []

    def issue(_argv: tuple[str, ...]) -> None:
        calls.append("issued")
        _issued(root, 1, pair)

    original = certificates._replace

    def interrupted(logical: str, name: str, raw: bytes, mode: int, recover: bool) -> None:
        if name == "privkey.pem":
            raise OSError("synthetic pair interruption")
        original(logical, name, raw, mode, recover)

    monkeypatch.setattr(certificates, "_replace", interrupted)
    with pytest.raises(OSError):
        certificates.provision(**_args(), issue=issue)  # type: ignore[arg-type]
    monkeypatch.setattr(certificates, "_replace", original)
    with pytest.raises(WAWManifestInstallError, match="--recover"):
        certificates.provision(**_args(), issue=issue)  # type: ignore[arg-type]
    certificates.provision(**(_args() | {"recover": True}), issue=issue)  # type: ignore[arg-type]
    assert calls == ["issued"]
    assert (root / "etc/agentbox-web/tls/privkey.pem").read_bytes() == pair[1]


def test_certificate_rejects_foreign_tls_before_acme(tmp_path: Path) -> None:
    certificates, root = _certificates(tmp_path)
    tls = root / "etc/agentbox-web/tls"
    tls.mkdir(parents=True, mode=0o700)
    (tls / "privkey.pem").write_bytes(b"foreign key")
    (tls / "privkey.pem").chmod(0o600)

    def forbidden(_argv: tuple[str, ...]) -> None:
        raise AssertionError("foreign TLS must reject before network side effects")

    with pytest.raises(WAWManifestInstallError, match="foreign"):
        certificates.provision(**_args(), issue=forbidden)  # type: ignore[arg-type]
    assert (tls / "privkey.pem").read_bytes() == b"foreign key"


def test_fixed_acme_argv_rejects_hook_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    host = HostOperations(real_host=True)
    monkeypatch.setattr(host, "require_root", lambda: None)
    argv = web_acme_argv("https://example.agentbox.test", "owner@example.test")
    with pytest.raises(HostMutationError, match="fixed ACME"):
        host.issue_web_certificate(argv + ("--deploy-hook=arbitrary",))


def test_maintenance_refreshes_expiring_bootstrap_without_runtime_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    certificates, root = _certificates(tmp_path)
    pair = _tls()
    calls: list[str] = []

    def issue(_argv: tuple[str, ...]) -> None:
        calls.append("acme")
        _issued(root, 1, pair)

    certificates.provision(**_args(), issue=issue)  # type: ignore[arg-type]
    now = datetime.now(UTC).replace(microsecond=0)
    origin = "https://example.agentbox.test"
    certificates.publisher.publish(
        origin=origin, valid_from=now - timedelta(minutes=1), valid_until=now + timedelta(days=1)
    )
    host = HostOperations(real_host=False)
    installer = AgentBoxInstaller(InstallLayout(root), host)
    monkeypatch.setattr(installer, "installation_state", lambda: "installed")
    monkeypatch.setattr(installer, "current_version", lambda: "0.3.0rc30")
    monkeypatch.setattr(host, "issue_web_certificate", issue)

    def forbidden() -> None:
        raise AssertionError("unchanged TLS must not restart a service")

    monkeypatch.setattr(host, "start_web_service", forbidden)
    monkeypatch.setattr(host, "start_waw_services", forbidden)
    old = (root / "var/lib/agentbox-web/current").readlink()
    result = installer.maintain_waw_web(recover=True)
    assert result["bootstrap_refreshed"] is True and result["certificate_changed"] is False
    current = root / "var/lib/agentbox-web/current"
    assert current.readlink() != old
    bootstrap = json.loads((current / ".well-known/agentbox/waw-bootstrap.v1.json").read_bytes())
    assert datetime.fromisoformat(bootstrap["valid_until"]) > now + timedelta(days=20)
    assert (root / "var/lib/agentbox-web" / old / "index.html").is_file()
    assert installer.maintain_waw_web(recover=True)["bootstrap_refreshed"] is False


def test_unmanaged_acme_directory_rejects_before_adoption(tmp_path: Path) -> None:
    certificates, root = _certificates(tmp_path)
    acme = root / "etc/agentbox-web/acme"
    acme.mkdir(parents=True, mode=0o700)
    (acme / "foreign.ini").write_text("foreign policy")
    with pytest.raises(WAWManifestInstallError, match="unmanaged"):
        certificates.provision(**_args(), issue=lambda _argv: None)  # type: ignore[arg-type]


def test_acme_foreign_symlink_never_reads_unrelated_private_key(tmp_path: Path) -> None:
    certificates, root = _certificates(tmp_path)

    def issue(_argv: tuple[str, ...]) -> None:
        _issued(root, 1, _tls())
        link = root / "etc/agentbox-web/acme/live/agentbox-web/privkey.pem"
        link.unlink()
        link.symlink_to("/root/private-key")

    with pytest.raises(WAWManifestInstallError, match="link"):
        certificates.provision(**_args(), issue=issue)  # type: ignore[arg-type]
    assert not (root / "etc/agentbox-web/tls").exists()
