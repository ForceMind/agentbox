from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from agentbox_installer.lifecycle import InstallError
from test_installer_waw_activation import _installer
from test_installer_waw_web_certificates import _issued
from test_installer_waw_web_configuration import _tls
from test_installer_waw_web_publication import _publisher


def test_web_setup_composes_enrolled_installation_and_resumes_without_runtime_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "core").mkdir()
    (tmp_path / "web").mkdir()
    installer, root, calls = _installer(tmp_path / "core", monkeypatch)
    _source, source_root, _args = _publisher(tmp_path / "web")
    release = root / "opt/agentbox/releases/0.3.0rc30"
    source = source_root / "opt/agentbox/releases/0.3.0rc30"
    shutil.copytree(source / "web", release / "web")
    shutil.copyfile(source / "RELEASE_MANIFEST.json", release / "RELEASE_MANIFEST.json")
    config = root / "etc/agentbox/agentbox.toml"
    config.write_text('env = "production"\nallowed_origins = []\ntrusted_proxies = []\n')
    config.chmod(0o640)
    pair = _tls()

    def issue(_argv: tuple[str, ...]) -> None:
        calls.append("acme")
        _issued(root, 1, pair)

    monkeypatch.setattr(installer.host, "issue_web_certificate", issue)
    monkeypatch.setattr(installer.host, "start_web_service", lambda: calls.append("https"))
    origin, email = "https://example.agentbox.test", "owner@example.test"
    before = {str(path) for path in root.rglob("*")}
    installer.setup_waw_web(origin=origin, email=email, plan=True)
    assert before == {str(path) for path in root.rglob("*")} and calls == []
    with pytest.raises(InstallError, match="terms"):
        installer.setup_waw_web(origin=origin, email=email)
    assert calls == []
    result = installer.setup_waw_web(origin=origin, email=email, agree_terms=True)
    assert result["services_started"] is True and result["qualified"] is False
    assert (
        calls.index("acme")
        < calls.index("key-observed")
        < calls.index("started")
        < calls.index("https")
    )
    calls.clear()
    result = installer.setup_waw_web(origin=origin, email=email, agree_terms=True, recover=True)
    assert result["runtime_restarted"] is False
    assert "started" not in calls and "key-observed" not in calls
    assert calls == ["acme", "https"]


def test_setup_cli_has_explicit_plan_consent_and_recovery() -> None:
    from agentbox_installer.cli import create_parser

    args = create_parser().parse_args(
        [
            "setup-waw-web",
            "--origin",
            "https://example.test",
            "--email",
            "owner@example.test",
            "--plan",
            "--recover",
        ]
    )
    assert args.plan and args.recover and not args.agree_acme_terms
