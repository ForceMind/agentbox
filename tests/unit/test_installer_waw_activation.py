from __future__ import annotations

import hashlib
import importlib.resources
import json
import os
from pathlib import Path
from typing import Any

import pytest
from agentbox_installer.host import HostOperations
from agentbox_installer.layout import InstallLayout
from agentbox_installer.lifecycle import AgentBoxInstaller, InstallError
from agentbox_installer.waw_activation import WAWActivationTransaction
from agentbox_runtime.waw_vendor_enrollment import encode_waw_vendor_enrollment
from test_installer_waw_manifests import _fixture, _load


def _installer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[AgentBoxInstaller, Path, list[str]]:
    issuer, root = _fixture(tmp_path)
    issuer.publish(issuer.observe(), "a" * 64)
    (root / "etc").mkdir(mode=0o755)
    issuer.prepare_fixed_policies()
    pin = _load(root)
    record = encode_waw_vendor_enrollment(
        {
            "schema_version": "agentbox-waw-vendor-enrollment.v1",
            "runtime_host_installation_id": pin.runtime.runtime_host_installation_id,
            "runtime_host_installation_revision": pin.runtime.runtime_host_installation_revision,
            "host_manifest_digest": pin.runtime_manifest_digest,
            "enrollment_epoch": pin.runtime.enrollment_epoch,
            "enrollment_state": pin.runtime.enrollment_state,
            "claude_vendor_version": "1.2.3",
            "codex_vendor_version": "4.5.6",
            "codex_unauthenticated_output_sha256": "b" * 64,
        }
    )
    path = root / "var/lib/agentbox-waw/vendor-enrollment.v1.json"
    path.write_bytes(record)
    path.chmod(0o440)
    for path, raw in (
        (
            root / "etc/agentbox/waw-api-profile.v1.json",
            b'{"mode":"disabled","schema_version":"agentbox-waw-api-profile.v1"}\n',
        ),
        (
            root / "var/lib/agentbox-waw/runtime-profile.v1.json",
            b'{"mode":"disabled","schema_version":"agentbox-waw-runtime-profile.v1"}\n',
        ),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o750)
        path.write_bytes(raw)
        path.chmod(0o440)
    units = root / "etc/systemd/system"
    units.mkdir(parents=True)
    resources = importlib.resources.files("agentbox_installer") / "assets/systemd"
    for name in (
        "agentbox-runtime.service",
        "agentbox-waw-control.socket",
        "agentbox-waw-stream.socket",
    ):
        path = units / name
        path.write_bytes((resources / name).read_bytes())
        path.chmod(0o644)
    host = HostOperations(real_host=False)
    installer = AgentBoxInstaller(InstallLayout(root), host)
    monkeypatch.setattr(installer, "installation_state", lambda: "installed")
    monkeypatch.setattr(installer, "current_version", lambda: "0.3.0rc30")
    calls: list[str] = []
    monkeypatch.setattr(host, "require_waw_policy_quiescence", lambda: calls.append("quiescent"))

    def observed_key(*_args: Any, **_kwargs: Any) -> str:
        calls.append("key-observed")
        return "a" * 64

    monkeypatch.setattr(host, "initialize_waw_runtime_key", observed_key)
    monkeypatch.setattr(host, "start_waw_services", lambda: calls.append("started"))
    monkeypatch.setattr(host, "stop_agentbox", lambda: calls.append("stopped"))
    return installer, root, calls


def _profiles(root: Path) -> tuple[str, str]:
    values = [
        json.loads((root / name).read_bytes())["mode"]
        for name in (
            "etc/agentbox/waw-api-profile.v1.json",
            "var/lib/agentbox-waw/runtime-profile.v1.json",
        )
    ]
    return values[0], values[1]


def test_activation_plan_does_not_write_or_observe_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer, root, calls = _installer(tmp_path, monkeypatch)
    before = {str(path.relative_to(root)) for path in root.rglob("*")}
    result = installer.activate_waw(plan=True)
    assert result["status"] == "resources_validated_key_not_observed"
    assert before == {str(path.relative_to(root)) for path in root.rglob("*")}
    assert calls == [] and _profiles(root) == ("disabled", "disabled")


def test_activation_pairs_profiles_and_records_unqualified_service_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer, root, calls = _installer(tmp_path, monkeypatch)
    result = installer.activate_waw()
    assert result == {"status": "services_started", "services_started": True, "qualified": False}
    assert _profiles(root) == ("filesystem-v2", "filesystem-v2")
    assert (
        json.loads((root / "var/lib/agentbox-waw/activation.v1.json").read_bytes())["phase"]
        == "started"
    )
    assert calls.index("key-observed") < calls.index("started")
    assert (root / "etc/systemd/system/agentbox-runtime.service.d/waw.v1.conf").is_file()


def test_interrupted_profile_pair_requires_explicit_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer, root, calls = _installer(tmp_path, monkeypatch)
    original = WAWActivationTransaction._replace

    def interrupted(
        self: WAWActivationTransaction, parent: int, name: str, raw: bytes, **kwargs: Any
    ) -> None:
        if name == "waw-api-profile.v1.json":
            raise OSError("synthetic interruption")
        original(self, parent, name, raw, **kwargs)

    monkeypatch.setattr(WAWActivationTransaction, "_replace", interrupted)
    with pytest.raises(InstallError):
        installer.activate_waw()
    assert _profiles(root) == ("disabled", "filesystem-v2") and "started" not in calls
    monkeypatch.setattr(WAWActivationTransaction, "_replace", original)
    with pytest.raises(RuntimeError, match="--recover"):
        installer.activate_waw()
    installer.activate_waw(recover=True)
    assert _profiles(root) == ("filesystem-v2", "filesystem-v2")


def test_failed_start_stops_only_fixed_services_and_can_recover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer, root, calls = _installer(tmp_path, monkeypatch)

    def failed() -> None:
        raise RuntimeError("synthetic service failure")

    monkeypatch.setattr(installer.host, "start_waw_services", failed)
    with pytest.raises(InstallError, match="--recover"):
        installer.activate_waw()
    assert calls[-1] == "stopped"
    assert (
        json.loads((root / "var/lib/agentbox-waw/activation.v1.json").read_bytes())["phase"]
        == "configured"
    )
    monkeypatch.setattr(installer.host, "start_waw_services", lambda: calls.append("started"))
    installer.activate_waw(recover=True)
    assert calls[-1] == "started"


@pytest.mark.parametrize("stage", ["profile", "journal"])
def test_activation_recovers_matching_partial_atomic_pending_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    installer, root, _calls = _installer(tmp_path, monkeypatch)
    original = WAWActivationTransaction._replace
    pending_paths: list[Path] = []

    def interrupted(
        self: WAWActivationTransaction, parent: int, name: str, raw: bytes, **kwargs: Any
    ) -> None:
        trigger = (
            name == "runtime-profile.v1.json"
            if stage == "profile"
            else (name == "activation.v1.json" and b'"phase":"configured"' in raw)
        )
        if trigger:
            pending = (
                "." + name + "." + hashlib.sha256(raw).hexdigest()[:16] + ".waw-activation.pending"
            )
            fd = os.open(
                pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, kwargs["mode"], dir_fd=parent
            )
            try:
                os.fchmod(fd, kwargs["mode"])
                os.write(fd, raw[:8])
            finally:
                os.close(fd)
            pending_paths.append(root / "var/lib/agentbox-waw" / pending)
            raise OSError("synthetic interrupted atomic publication")
        original(self, parent, name, raw, **kwargs)

    monkeypatch.setattr(WAWActivationTransaction, "_replace", interrupted)
    with pytest.raises(InstallError):
        installer.activate_waw()
    assert pending_paths and pending_paths[0].is_file()
    monkeypatch.setattr(WAWActivationTransaction, "_replace", original)
    installer.activate_waw(recover=True)
    assert not pending_paths[0].exists() and _profiles(root) == ("filesystem-v2", "filesystem-v2")


def test_host_start_uses_only_fixed_named_sockets_then_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = HostOperations(real_host=True)
    monkeypatch.setattr(
        host,
        "_installed_waw_socket_units",
        lambda: ("agentbox-waw-control.socket", "agentbox-waw-stream.socket"),
    )
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(host, "_run", lambda argv, **_kwargs: calls.append(argv))
    host.start_waw_services()
    assert calls[:4] == [
        ("/usr/bin/systemctl", "daemon-reload"),
        (
            "/usr/bin/systemctl",
            "enable",
            "--now",
            "agentbox-waw-control.socket",
            "agentbox-waw-stream.socket",
        ),
        ("/usr/bin/systemctl", "enable", "--now", "agentbox-runtime.service"),
        (
            "/usr/bin/systemctl",
            "enable",
            "--now",
            "agentbox-worker.service",
            "agentbox-api.service",
        ),
    ]
    assert len(calls[4:]) == 5 and all(
        argv[:3] == ("/usr/bin/systemctl", "is-active", "--quiet") for argv in calls[4:]
    )


@pytest.mark.parametrize("kind", ["key", "unit", "dropin", "enrollment"])
def test_activation_rejects_resource_drift_before_profile_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    installer, root, calls = _installer(tmp_path, monkeypatch)
    if kind == "key":
        monkeypatch.setattr(
            installer.host, "initialize_waw_runtime_key", lambda *_args, **_kwargs: "c" * 64
        )
    elif kind == "unit":
        (root / "etc/systemd/system/agentbox-runtime.service").write_bytes(b"unrelated unit")
    elif kind == "dropin":
        directory = root / "etc/systemd/system/agentbox-runtime.service.d"
        directory.mkdir()
        (directory / "unrelated.conf").write_bytes(b"other setting")
    else:
        path = root / "var/lib/agentbox-waw/vendor-enrollment.v1.json"
        raw = path.read_bytes().replace(_load(root).runtime_manifest_digest.encode(), b"c" * 64)
        path.chmod(0o600)
        path.write_bytes(raw)
        path.chmod(0o440)
    with pytest.raises(RuntimeError):
        installer.activate_waw()
    assert _profiles(root) == ("disabled", "disabled") and "started" not in calls
