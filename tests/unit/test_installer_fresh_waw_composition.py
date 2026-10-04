from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from agentbox_installer import cli
from agentbox_installer import lifecycle as lifecycle_module
from agentbox_installer.host import HostOperations
from agentbox_installer.layout import InstallLayout
from agentbox_installer.lifecycle import AgentBoxInstaller, InstallError, InstallPlan
from agentbox_installer.platform import PackageFamily, PlatformFacts, PlatformSupport

VERSION = "0.3.0rc30"
ARTIFACT_SHA = "a" * 64
ORIGIN = "https://agentbox.example.com"
EMAIL = "owner@example.com"
STEPS = [
    "deferred-install",
    "browser-dependencies",
    "fixed-vendors",
    "manifests",
    "policies",
    "qualified-enrollment",
    "https",
]


def _install_plan(state: str) -> InstallPlan:
    return InstallPlan(
        platform=PlatformFacts(
            "ubuntu",
            "24.04",
            "x86_64",
            PackageFamily.APT,
            PlatformSupport.SUPPORTED,
            "supported fixture",
        ),
        version=VERSION,
        state=state,
        users=(),
        groups=(),
        directories=(),
        files=(),
        units=(),
        bind="127.0.0.1:8787",
        port_state="available",
        systemd_state="available",
        package_changes=(),
        dependencies=(),
        existing_root_runtime="absent",
        network_changes=(),
    )


def _installer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str) -> AgentBoxInstaller:
    root = tmp_path / "root"
    root.mkdir()
    installer = AgentBoxInstaller(InstallLayout(root), HostOperations(real_host=False))
    monkeypatch.setattr(installer, "plan", lambda _artifact, _sha: _install_plan(state))
    monkeypatch.setattr(installer.host, "systemd_version", lambda: 255)
    monkeypatch.setattr(
        lifecycle_module,
        "web_acme_argv",
        lambda origin, email: ("certbot", origin, email),
    )
    return installer


def _install_downstream_stubs(
    installer: AgentBoxInstaller,
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
) -> None:
    def dependencies(**_kwargs: object) -> dict[str, object]:
        events.append("browser-dependencies")
        return {}

    def vendors(**_kwargs: object) -> dict[str, object]:
        events.append("fixed-vendors")
        return {}

    def manifests(**_kwargs: object) -> object:
        events.append("manifests")
        return object()

    def policies(**_kwargs: object) -> dict[str, object]:
        events.append("policies")
        return {}

    def enrollment(**_kwargs: object) -> object:
        events.append("qualified-enrollment")
        return object()

    def web(**_kwargs: object) -> dict[str, object]:
        events.append("https")
        return {
            "status": "started",
            "services_started": True,
            "runtime_restarted": True,
        }

    monkeypatch.setattr(installer, "install_waw_dependencies", dependencies)
    monkeypatch.setattr(installer, "install_waw_vendors", vendors)
    monkeypatch.setattr(installer, "prepare_waw_manifests", manifests)
    monkeypatch.setattr(installer, "prepare_waw_policies", policies)
    monkeypatch.setattr(installer, "enroll_qualified_waw_vendors", enrollment)
    monkeypatch.setattr(installer, "setup_waw_web", web)


def test_fresh_setup_plan_is_read_only_and_lists_closed_sequence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer = _installer(tmp_path, monkeypatch, "not_installed")

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("plan must not mutate installation state")

    for name in (
        "apply",
        "resume_install",
        "install_waw_dependencies",
        "install_waw_vendors",
        "prepare_waw_manifests",
        "prepare_waw_policies",
        "enroll_qualified_waw_vendors",
        "setup_waw_web",
    ):
        monkeypatch.setattr(installer, name, forbidden)

    result = installer.setup_fresh_waw(
        artifact=tmp_path / "artifact.tar.gz",
        expected_sha256=ARTIFACT_SHA,
        origin=ORIGIN,
        email=EMAIL,
        plan=True,
    )

    assert result == {
        "status": "planned",
        "version": VERSION,
        "installation_state": "not_installed",
        "origin": ORIGIN,
        "steps": STEPS,
        "requires_recover": False,
        "services_started": False,
        "qualified": False,
    }


def test_fresh_setup_executes_exact_sequence_from_not_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer = _installer(tmp_path, monkeypatch, "not_installed")
    events: list[str] = []

    def apply(_artifact: Path, _sha: str, *, defer_activation: bool) -> object:
        assert defer_activation is True
        events.append("deferred-install")
        return object()

    monkeypatch.setattr(installer, "apply", apply)
    monkeypatch.setattr(
        installer,
        "resume_install",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("fresh setup must not resume a new install")
        ),
    )
    _install_downstream_stubs(installer, monkeypatch, events)

    result = installer.setup_fresh_waw(
        artifact=tmp_path / "artifact.tar.gz",
        expected_sha256=ARTIFACT_SHA,
        origin=ORIGIN,
        email=EMAIL,
        agree_terms=True,
    )

    assert events == STEPS
    assert result["status"] == "started"
    assert result["https_url"] == ORIGIN
    assert result["services_started"] is True
    assert result["runtime_restarted"] is True


def test_staged_fresh_setup_requires_explicit_recovery_and_resumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer = _installer(tmp_path, monkeypatch, "staged")
    artifact = tmp_path / "artifact.tar.gz"

    with pytest.raises(InstallError, match="requires --recover"):
        installer.setup_fresh_waw(
            artifact=artifact,
            expected_sha256=ARTIFACT_SHA,
            origin=ORIGIN,
            email=EMAIL,
            agree_terms=True,
        )

    events: list[str] = []

    def resume(_artifact: Path, _sha: str, *, defer_activation: bool) -> object:
        assert defer_activation is True
        events.append("deferred-install")
        return object()

    monkeypatch.setattr(installer, "resume_install", resume)
    monkeypatch.setattr(
        installer,
        "apply",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("staged recovery must use resume-install")
        ),
    )
    _install_downstream_stubs(installer, monkeypatch, events)

    installer.setup_fresh_waw(
        artifact=artifact,
        expected_sha256=ARTIFACT_SHA,
        origin=ORIGIN,
        email=EMAIL,
        agree_terms=True,
        recover=True,
    )
    assert events == STEPS


def test_existing_same_version_requires_committed_deferred_install_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer = _installer(tmp_path, monkeypatch, "installed_same_version")
    artifact = tmp_path / "artifact.tar.gz"
    candidate = SimpleNamespace(version=VERSION)
    monkeypatch.setattr(lifecycle_module, "verify_artifact_digest", lambda *_args: None)
    monkeypatch.setattr(installer, "_peek_artifact_manifest", lambda _artifact: candidate)
    monkeypatch.setattr(lifecycle_module, "verify_release", lambda *_args, **_kwargs: candidate)
    monkeypatch.setattr(installer, "_read_journal", lambda: None)

    with pytest.raises(InstallError, match="committed deferred"):
        installer.setup_fresh_waw(
            artifact=artifact,
            expected_sha256=ARTIFACT_SHA,
            origin=ORIGIN,
            email=EMAIL,
            agree_terms=True,
        )

    monkeypatch.setattr(
        installer,
        "_read_journal",
        lambda: {
            "schema_version": 3,
            "status": "committed",
            "version": VERSION,
            "completed_steps": ["activation_deferred", "receipt_written"],
        },
    )
    events: list[str] = []
    _install_downstream_stubs(installer, monkeypatch, events)
    monkeypatch.setattr(
        installer,
        "apply",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("committed deferred install must not re-apply")
        ),
    )
    monkeypatch.setattr(
        installer,
        "resume_install",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("committed deferred install must not resume")
        ),
    )

    installer.setup_fresh_waw(
        artifact=artifact,
        expected_sha256=ARTIFACT_SHA,
        origin=ORIGIN,
        email=EMAIL,
        agree_terms=True,
        recover=True,
    )
    assert events == STEPS[1:]


def test_started_activation_resumes_https_without_replaying_offline_phases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer = _installer(tmp_path, monkeypatch, "installed_same_version")
    artifact = tmp_path / "artifact.tar.gz"
    candidate = SimpleNamespace(version=VERSION)
    monkeypatch.setattr(lifecycle_module, "verify_artifact_digest", lambda *_args: None)
    monkeypatch.setattr(installer, "_peek_artifact_manifest", lambda _artifact: candidate)
    monkeypatch.setattr(lifecycle_module, "verify_release", lambda *_args, **_kwargs: candidate)
    monkeypatch.setattr(
        installer,
        "_read_journal",
        lambda: {
            "schema_version": 3,
            "status": "committed",
            "version": VERSION,
            "completed_steps": ["activation_deferred", "receipt_written"],
        },
    )
    monkeypatch.setattr(installer, "_fresh_waw_activation_phase", lambda **_kwargs: "started")

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("offline fresh-setup phases must not replay after activation")

    for name in (
        "install_waw_dependencies",
        "install_waw_vendors",
        "prepare_waw_manifests",
        "prepare_waw_policies",
        "enroll_qualified_waw_vendors",
    ):
        monkeypatch.setattr(installer, name, forbidden)

    calls: list[str] = []

    def web(**_kwargs: object) -> dict[str, object]:
        calls.append("https")
        return {
            "status": "started",
            "services_started": True,
            "runtime_restarted": False,
        }

    monkeypatch.setattr(installer, "setup_waw_web", web)
    result = installer.setup_fresh_waw(
        artifact=artifact,
        expected_sha256=ARTIFACT_SHA,
        origin=ORIGIN,
        email=EMAIL,
        agree_terms=True,
        recover=True,
    )

    assert calls == ["https"]
    assert result["resumed_activation_phase"] == "started"
    assert result["services_started"] is True


def test_fresh_setup_cli_contract() -> None:
    args = cli.create_parser().parse_args(
        [
            "setup-fresh-waw",
            "--artifact",
            "/tmp/agentbox.tar.gz",
            "--sha256",
            ARTIFACT_SHA,
            "--origin",
            ORIGIN,
            "--email",
            EMAIL,
            "--agree-acme-terms",
            "--recover",
            "--json",
        ]
    )

    assert args.command == "setup-fresh-waw"
    assert args.artifact == Path("/tmp/agentbox.tar.gz")
    assert args.sha256 == ARTIFACT_SHA
    assert args.origin == ORIGIN
    assert args.email == EMAIL
    assert args.agree_acme_terms is True
    assert args.recover is True
    assert args.json is True
