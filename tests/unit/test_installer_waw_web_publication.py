from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from agentbox_installer.waw_manifest_install import WAWManifestInstallError, WAWManifestIssuer
from agentbox_installer.waw_web_publication import WAWWebPublisher
from test_installer_waw_manifests import _fixture, _load


def _publisher(tmp_path: Path) -> tuple[WAWWebPublisher, Path, dict[str, Any]]:
    issuer, root = _fixture(tmp_path)
    issuer.publish(issuer.observe(), "a" * 64)
    release = root / "opt/agentbox/releases/0.3.0rc30"
    source = release / "web/dist"
    (source / "assets").mkdir(parents=True)
    data = {
        "index.html": (
            b'<html><head></head><body><script type="module" '
            b'src="/assets/app.js"></script></body></html>'
        ),
        "assets/app.js": b"fixture javascript",
    }
    for name, raw in data.items():
        (source / name).write_bytes(raw)
        (source / name).chmod(0o644)
    files = {"web/dist/" + name: hashlib.sha256(raw).hexdigest() for name, raw in data.items()}
    # Exercise the real release manifest decoder with its legacy closed schema.
    (release / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "version": "0.3.0rc30",
                "database_revision": "0001",
                "database_backward_compatible": True,
                "files": files,
            }
        )
    )
    (release / "RELEASE_MANIFEST.json").write_bytes((release / "manifest.json").read_bytes())
    (release / "manifest.json").unlink()
    now = datetime(2026, 10, 1, tzinfo=UTC)
    return (
        WAWWebPublisher(issuer, _load(root)),
        root,
        dict(
            origin="https://example.agentbox.test",
            valid_from=now,
            valid_until=now + timedelta(days=1),
        ),
    )


def test_web_plan_is_readonly_and_overlay_preserves_original_artifact(tmp_path: Path) -> None:
    publisher, root, args = _publisher(tmp_path)
    source = root / "opt/agentbox/releases/0.3.0rc30/web/dist/index.html"
    original = source.read_bytes()
    before = {str(path.relative_to(root)) for path in root.rglob("*")}
    plan = publisher.publish(**args, plan=True)
    assert before == {str(path.relative_to(root)) for path in root.rglob("*")}
    published = publisher.publish(**args)
    assert plan["build_identity"] == published["build_identity"]
    current = root / "var/lib/agentbox-web/current"
    assert current.is_symlink() and source.read_bytes() == original
    html = (current / "index.html").read_text()
    assert 'content="https-web-v1"' in html and str(published["build_identity"]) in html
    assert (current / "index.html").stat().st_mode & 0o777 == 0o444
    inode = (current / "index.html").stat().st_ino
    publisher.publish(**args)
    assert (current / "index.html").stat().st_ino == inode


def test_web_partial_publication_requires_explicit_matching_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publisher, root, args = _publisher(tmp_path)
    original = WAWManifestIssuer._create_file

    def interrupted(self: WAWManifestIssuer, *values: Any, **kwargs: Any) -> None:
        if values[1] == "app.js":
            raise OSError("synthetic interrupted publication")
        original(self, *values, **kwargs)

    monkeypatch.setattr(WAWManifestIssuer, "_create_file", interrupted)
    with pytest.raises(OSError):
        publisher.publish(**args)
    assert not (root / "var/lib/agentbox-web/current").exists()
    monkeypatch.setattr(WAWManifestIssuer, "_create_file", original)
    with pytest.raises(WAWManifestInstallError, match="--recover"):
        publisher.publish(**args)
    publisher.publish(**args, recover=True)
    assert (root / "var/lib/agentbox-web/current/index.html").is_file()


def test_web_source_drift_rejects_before_publication(tmp_path: Path) -> None:
    publisher, root, args = _publisher(tmp_path)
    (root / "opt/agentbox/releases/0.3.0rc30/web/dist/assets/app.js").write_bytes(b"changed source")
    with pytest.raises(WAWManifestInstallError, match="changed"):
        publisher.publish(**args)
    assert not (root / "var/lib/agentbox-web").exists()


def test_web_lifecycle_cli_plan_preserves_files_and_never_starts_services(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agentbox_installer.cli import create_parser
    from agentbox_installer.host import HostOperations
    from agentbox_installer.layout import InstallLayout
    from agentbox_installer.lifecycle import AgentBoxInstaller

    _pub, root, args = _publisher(tmp_path)
    host = HostOperations(real_host=False)
    installer = AgentBoxInstaller(InstallLayout(root), host)
    monkeypatch.setattr(installer, "installation_state", lambda: "installed")
    monkeypatch.setattr(installer, "current_version", lambda: "0.3.0rc30")

    def forbidden() -> None:
        raise AssertionError("public publication must not start services")

    monkeypatch.setattr(host, "enable_and_start", forbidden)
    before = {str(path.relative_to(root)) for path in root.rglob("*")}
    result = installer.publish_waw_web(**args, plan=True)
    assert result["services_started"] is False
    assert before == {str(path.relative_to(root)) for path in root.rglob("*")}
    installer.publish_waw_web(**args)
    assert (root / "var/lib/agentbox-web/current/index.html").is_file()
    parsed = create_parser().parse_args(
        [
            "publish-waw-web",
            "--origin",
            args["origin"],
            "--valid-from",
            "2026-10-01T00:00:00Z",
            "--valid-until",
            "2026-10-02T00:00:00Z",
            "--plan",
        ]
    )
    assert parsed.plan and not parsed.recover


def test_web_ingress_collision_rejects_before_pointer_change(tmp_path: Path) -> None:
    publisher, root, args = _publisher(tmp_path)
    config = root / "etc/agentbox-web/nginx.conf"
    config.parent.mkdir(parents=True)
    config.write_bytes(b"foreign ingress\n")
    config.chmod(0o444)
    for plan in (True, False):
        with pytest.raises(WAWManifestInstallError):
            publisher.publish(**args, plan=plan, recover=True)
    assert config.read_bytes() == b"foreign ingress\n"
    assert not (root / "var/lib/agentbox-web/current").exists()


def test_web_ingress_is_fixed_and_not_served_by_api(tmp_path: Path) -> None:
    publisher, root, args = _publisher(tmp_path)
    publisher.publish(**args)
    config = root / "etc/agentbox-web/nginx.conf"
    text = config.read_text()
    assert "root /var/lib/agentbox-web/current;" in text
    assert text.count("proxy_pass ") == 1
    assert "proxy_pass http://127.0.0.1:8787;" in text
    assert "proxy_ignore_headers X-Accel-Redirect" in text
    assert "proxy_hide_header Content-Type;" in text
    assert "default-src 'none'; sandbox;" in text
    assert "location ~ /\\." in text
    assert config.stat().st_mode & 0o777 == 0o444
    unit = root / "etc/systemd/system/agentbox-web.service"
    assert "nginx -t -c /etc/agentbox-web/nginx.conf" in unit.read_text()
    assert "User=agentbox-web\nDynamicUser=true" in unit.read_text()
    assert "LoadCredential=privkey.pem:" in unit.read_text()
    assert "CAP_CHOWN" not in unit.read_text()
    assert unit.stat().st_mode & 0o777 == 0o444


@pytest.mark.parametrize(
    "origin",
    [
        "http://example.test",
        "https://example.test/",
        "https://example.test:443",
        "https://example.test;include",
        "https://example.test\n",
        "https://user@example.test",
        "https://example.test:65536",
        "https://EXAMPLE.test",
        "https://-bad.test",
    ],
)
def test_web_ingress_rejects_config_injection_and_noncanonical_origin(origin: str) -> None:
    from agentbox_installer.waw_web_ingress import render_web_ingress

    with pytest.raises(ValueError):
        render_web_ingress(origin)
