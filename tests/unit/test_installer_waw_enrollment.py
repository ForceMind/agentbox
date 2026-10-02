from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from agentbox_installer import cli
from agentbox_installer.host import WAWVendorObservation
from agentbox_installer.waw_enrollment import (
    WAWEnrollmentPublicationError,
    WAWEnrollmentPublisher,
)
from agentbox_runtime.waw_host_manifest import WAW_PUBLIC_MANIFEST_FILENAMES_V2
from agentbox_runtime.waw_vendor_enrollment import encode_waw_vendor_enrollment

FIELDS: dict[str, object] = {
    "schema_version": "agentbox-waw-vendor-enrollment.v1",
    "runtime_host_installation_id": "wri_" + "1" * 32,
    "runtime_host_installation_revision": "2",
    "host_manifest_digest": "a" * 64,
    "enrollment_epoch": "3",
    "enrollment_state": "steady",
    "claude_vendor_version": "2.1.226",
    "codex_vendor_version": "0.153.4",
    "codex_unauthenticated_output_sha256": "b" * 64,
}


def _fixture(tmp_path: Path) -> tuple[WAWEnrollmentPublisher, Path]:
    root = tmp_path / "root"
    parent = root / "var/lib/agentbox-waw"
    parent.mkdir(parents=True)
    root.chmod(0o700)
    parent.chmod(0o750)
    publisher = WAWEnrollmentPublisher(
        root, owner_uid=os.geteuid(), root_gid=os.getegid(), runtime_gid=os.getegid()
    )
    return publisher, parent


def _publish(publisher: WAWEnrollmentPublisher, **kwargs: Any) -> Any:
    return publisher.publish(FIELDS, revalidate=lambda: None, **kwargs)


def test_plan_is_read_only_and_publish_is_idempotent(tmp_path: Path) -> None:
    publisher, parent = _fixture(tmp_path)
    assert _publish(publisher, plan=True).status == "planned"
    assert list(parent.iterdir()) == []
    first = _publish(publisher)
    assert first.status == "published"
    record = parent / "vendor-enrollment.v1.json"
    assert record.read_bytes() == encode_waw_vendor_enrollment(FIELDS)
    assert record.stat().st_mode & 0o777 == 0o440
    assert record.stat().st_nlink == 1
    assert _publish(publisher).status == "unchanged"
    assert "2.1.226" not in repr(first)


def test_conflicting_existing_record_is_never_replaced(tmp_path: Path) -> None:
    publisher, parent = _fixture(tmp_path)
    _publish(publisher)
    before = (parent / "vendor-enrollment.v1.json").read_bytes()
    with pytest.raises(WAWEnrollmentPublicationError, match="replacement is refused"):
        publisher.publish(
            {**FIELDS, "codex_vendor_version": "different"}, revalidate=lambda: None, recover=True
        )
    assert (parent / "vendor-enrollment.v1.json").read_bytes() == before


@pytest.mark.parametrize("point", ["link", "unlink"])
def test_interrupted_publication_recovers_only_when_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, point: str
) -> None:
    publisher, parent = _fixture(tmp_path)
    original = getattr(os, point)

    def fail(*args: Any, **kwargs: Any) -> None:
        raise OSError("injected publication interruption")

    with monkeypatch.context() as patch:
        patch.setattr(os, point, fail)
        with pytest.raises(WAWEnrollmentPublicationError):
            _publish(publisher)
    assert (parent / "vendor-enrollment.v1.pending").read_bytes() == encode_waw_vendor_enrollment(
        FIELDS
    )
    with pytest.raises(WAWEnrollmentPublicationError, match="explicit recovery"):
        _publish(publisher)
    assert _publish(publisher, recover=True).status == "recovered"
    record = parent / "vendor-enrollment.v1.json"
    assert record.read_bytes() == encode_waw_vendor_enrollment(FIELDS)
    assert record.stat().st_nlink == 1
    assert not (parent / "vendor-enrollment.v1.pending").exists()
    assert getattr(os, point) is original


def test_partial_private_stage_resumes_without_truncating_existing_record(tmp_path: Path) -> None:
    publisher, parent = _fixture(tmp_path)
    raw = encode_waw_vendor_enrollment(FIELDS)
    pending = parent / "vendor-enrollment.v1.pending"
    pending.write_bytes(raw[:65])
    pending.chmod(0o600)
    assert _publish(publisher, recover=True).status == "recovered"
    assert (parent / "vendor-enrollment.v1.json").read_bytes() == raw


@pytest.mark.parametrize("mode,content", [(0o600, b"unrelated"), (0o440, b"{")])
def test_unknown_or_incomplete_ready_stage_is_preserved(
    tmp_path: Path, mode: int, content: bytes
) -> None:
    publisher, parent = _fixture(tmp_path)
    pending = parent / "vendor-enrollment.v1.pending"
    pending.write_bytes(content)
    pending.chmod(mode)
    with pytest.raises(WAWEnrollmentPublicationError):
        _publish(publisher, recover=True)
    assert pending.read_bytes() == content
    assert not (parent / "vendor-enrollment.v1.json").exists()


@pytest.mark.parametrize("name", ["vendor-enrollment.v1.json", "vendor-enrollment.v1.pending"])
def test_symlinks_and_unknown_hardlinks_fail_before_publication(tmp_path: Path, name: str) -> None:
    publisher, parent = _fixture(tmp_path)
    unrelated = parent / "unrelated"
    unrelated.write_bytes(encode_waw_vendor_enrollment(FIELDS))
    unrelated.chmod(0o440 if name.endswith(".json") else 0o600)
    target = parent / name
    target.symlink_to(unrelated)
    with pytest.raises(WAWEnrollmentPublicationError):
        _publish(publisher, recover=True)
    target.unlink()
    os.link(unrelated, target)
    with pytest.raises(WAWEnrollmentPublicationError):
        _publish(publisher, recover=True)
    assert unrelated.read_bytes() == encode_waw_vendor_enrollment(FIELDS)


def test_manifest_drift_leaves_stage_without_publishing(tmp_path: Path) -> None:
    publisher, parent = _fixture(tmp_path)
    calls = 0

    def drift() -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("manifest changed")

    with pytest.raises(RuntimeError, match="manifest changed"):
        publisher.publish(FIELDS, revalidate=drift)
    assert not (parent / "vendor-enrollment.v1.json").exists()
    assert (parent / "vendor-enrollment.v1.pending").exists()


def test_parent_replacement_cannot_publish_to_stale_directory(tmp_path: Path) -> None:
    publisher, parent = _fixture(tmp_path)
    old = parent.with_name("old")
    calls = 0

    def replace_parent() -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            parent.rename(old)
            parent.mkdir(mode=0o750)

    with pytest.raises(WAWEnrollmentPublicationError, match="parent entry changed"):
        publisher.publish(FIELDS, revalidate=replace_parent)
    assert not (parent / "vendor-enrollment.v1.json").exists()
    assert not (old / "vendor-enrollment.v1.json").exists()


def _installed_fixture(tmp_path: Path) -> Path:
    from test_installer_lifecycle import _artifact, _installer
    from test_waw_manifest_codecs import _v2_cross_pin_inputs

    installer, layout = _installer(tmp_path)
    artifact, digest = _artifact(tmp_path, "0.3.0rc30", "0012_workspace_labels")
    installer.apply(artifact, digest)
    values = _v2_cross_pin_inputs()
    public = layout.map("/usr/share/agentbox/waw")
    public.mkdir(parents=True, mode=0o755)
    for name, raw in zip(WAW_PUBLIC_MANIFEST_FILENAMES_V2, (values[0], *values[2:]), strict=True):
        path = public / name
        path.write_bytes(raw)
        path.chmod(0o444)
    private = layout.map("/var/lib/agentbox-waw/runtime-host-installation.v2.json")
    private.write_bytes(values[1])
    private.chmod(0o440)
    return layout.root


def test_cli_plan_and_apply_use_actual_cross_pinned_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("agentbox_installer.platform.platform_module.machine", lambda: "x86_64")
    root = _installed_fixture(tmp_path)
    monkeypatch.setenv("AGENTBOX_INSTALLER_TEST_MODE", "1")
    args = [
        "--fixture-root",
        str(root),
        "enroll-waw-vendors",
        "--claude-version",
        "2.1.226",
        "--codex-version",
        "0.153.4",
        "--codex-unauthenticated-output-sha256",
        "b" * 64,
        "--json",
    ]
    assert cli.main([*args, "--plan"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "planned"
    record = root / "var/lib/agentbox-waw/vendor-enrollment.v1.json"
    assert not record.exists()
    assert cli.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "published"
    assert "2.1.226" not in json.dumps(result)
    assert cli.main(args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "unchanged"
    assert record.stat().st_nlink == 1


@pytest.mark.parametrize(
    "profile",
    ["/etc/agentbox/waw-api-profile.v1.json", "/var/lib/agentbox-waw/runtime-profile.v1.json"],
)
def test_cli_refuses_enabled_profiles_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    profile: str,
) -> None:
    monkeypatch.setattr("agentbox_installer.platform.platform_module.machine", lambda: "x86_64")
    root = _installed_fixture(tmp_path)
    path = root / profile.lstrip("/")
    path.chmod(0o600)
    path.write_bytes(path.read_bytes().replace(b'"disabled"', b'"filesystem-v2"'))
    path.chmod(0o440)
    monkeypatch.setenv("AGENTBOX_INSTALLER_TEST_MODE", "1")
    args = [
        "--fixture-root",
        str(root),
        "enroll-waw-vendors",
        "--claude-version",
        "2.1.226",
        "--codex-version",
        "0.153.4",
        "--codex-unauthenticated-output-sha256",
        "b" * 64,
        "--json",
    ]
    assert cli.main(args) == 17
    assert "disabled WAW profiles" in capsys.readouterr().err
    assert not (root / "var/lib/agentbox-waw/vendor-enrollment.v1.json").exists()
    assert not (root / "var/lib/agentbox-waw/vendor-enrollment.v1.pending").exists()


def test_cli_observe_enroll_uses_one_runtime_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("agentbox_installer.platform.platform_module.machine", lambda: "x86_64")
    root = _installed_fixture(tmp_path)
    monkeypatch.setenv("AGENTBOX_INSTALLER_TEST_MODE", "1")
    observed = WAWVendorObservation(
        claude_vendor_version="2.1.286 (Claude Code)",
        codex_vendor_version="codex-cli 0.159.3",
        codex_unauthenticated_output_sha256="c" * 64,
    )
    calls = 0

    def observe(_self: object) -> WAWVendorObservation:
        nonlocal calls
        calls += 1
        return observed

    monkeypatch.setattr("agentbox_installer.host.HostOperations.observe_waw_vendors", observe)
    args = [
        "--fixture-root",
        str(root),
        "observe-enroll-waw-vendors",
        "--json",
    ]
    assert cli.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "published"
    assert calls == 1
    record = json.loads(
        (root / "var/lib/agentbox-waw/vendor-enrollment.v1.json").read_text(encoding="ascii")
    )
    assert record["claude_vendor_version"] == observed.claude_vendor_version
    assert record["codex_vendor_version"] == observed.codex_vendor_version
    assert (
        record["codex_unauthenticated_output_sha256"]
        == observed.codex_unauthenticated_output_sha256
    )
