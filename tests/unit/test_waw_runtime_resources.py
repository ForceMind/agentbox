"""R12-C3-b: issue fixed resources only from one verified v2 authority."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
from agentbox_runtime import waw_runtime_resources as subject
from agentbox_runtime.waw_executable import WAWExecutableInventory, WAWExecutableKind
from agentbox_runtime.waw_fixed_transport import WAWVerifiedExecutionAuthority
from agentbox_runtime.waw_manifest_codecs import CrossManifestPinV2


@dataclass
class _IssuedHandle:
    kind: WAWExecutableKind
    closed: bool = False

    @property
    def identity(self) -> SimpleNamespace:
        return SimpleNamespace(kind=self.kind)

    def close(self) -> None:
        self.closed = True


class _Verified:
    def __init__(self, kind: WAWExecutableKind, issued: list[_IssuedHandle]) -> None:
        self.kind = kind
        self.issued = issued
        self.closed = False

    def __enter__(self) -> _Verified:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.closed = True

    def create_launch_handle(
        self, *, expected_kind: WAWExecutableKind, profile_digest: str
    ) -> _IssuedHandle:
        assert expected_kind is self.kind
        assert profile_digest == "a" * 64
        handle = _IssuedHandle(self.kind)
        self.issued.append(handle)
        return handle


class _Inventory:
    def __init__(self) -> None:
        self.issued: list[_IssuedHandle] = []
        self.sources: list[_Verified] = []

    def open(self, kind: WAWExecutableKind) -> _Verified:
        source = _Verified(kind, self.issued)
        self.sources.append(source)
        return source


@dataclass
class _ObservedFactory:
    authority: WAWVerifiedExecutionAuthority
    roles: dict[str, object]
    closed: bool = False

    def close(self) -> None:
        self.closed = True


@dataclass
class _Harness:
    authority: WAWVerifiedExecutionAuthority
    inventory: _Inventory
    opened: list[tuple[str, bool, int]] = field(default_factory=list)
    factories: list[_ObservedFactory] = field(default_factory=list)


def _harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Harness:
    manifest = object.__new__(CrossManifestPinV2)
    object.__setattr__(manifest, "executable_inventory", object())
    object.__setattr__(manifest, "interactive_profile_bundle_digest", "a" * 64)
    object.__setattr__(
        manifest, "project_root", SimpleNamespace(configured_root="/srv/agentbox/projects")
    )
    object.__setattr__(manifest, "cgroup", SimpleNamespace(delegate_subgroup="agentbox-waw"))
    authority = object.__new__(WAWVerifiedExecutionAuthority)
    object.__setattr__(authority, "_manifest", manifest)
    inventory = _Inventory()
    harness = _Harness(authority, inventory)
    policy_file = tmp_path / "policy"
    policy_file.write_text("fixed")

    def open_role(path: str, *, directory: bool) -> int:
        fd = os.open(tmp_path if directory else policy_file, os.O_RDONLY)
        harness.opened.append((path, directory, fd))
        return fd

    class Factory(_ObservedFactory):
        def __init__(self, **roles: object) -> None:
            assert roles["authority"] is authority
            super().__init__(authority, roles)
            harness.factories.append(self)

    monkeypatch.setattr(subject, "_open_role", open_role)
    monkeypatch.setattr(subject, "WAWVerifiedLaunchHandleFactory", Factory)
    monkeypatch.setattr(
        WAWExecutableInventory,
        "from_manifest",
        classmethod(lambda _cls, _manifest: inventory),
    )
    monkeypatch.setattr(
        subject,
        "_verify_delegate_root",
        lambda _descriptor, observed: observed is authority or pytest.fail("wrong authority"),
    )
    return harness


def test_fixed_resources_use_one_authority_and_close_temporary_roles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _harness(tmp_path, monkeypatch)

    resources = subject.build_waw_production_resources(harness.authority)

    assert resources.authority is harness.authority
    assert [handle.kind for handle in harness.inventory.issued] == list(WAWExecutableKind)
    assert len(harness.inventory.sources) == 6
    assert all(source.closed for source in harness.inventory.sources)
    assert [path for path, _directory, _fd in harness.opened] == [
        "/srv/agentbox/projects",
        "/var/lib/agentbox-waw/vendor-homes/claude",
        "/var/lib/agentbox-waw/vendor-homes/codex",
        "/run/agentbox-waw/tmp",
        "/etc/claude-code",
        "/etc/codex",
        "/etc/claude-code/managed-settings.json",
        "/etc/codex/requirements.toml",
        "/etc/codex/managed_config.toml",
        "/sys/fs/cgroup/agentbox-waw",
    ]
    for _path, _directory, descriptor in harness.opened[:-1]:
        if descriptor == resources.cgroup_delegate_root:
            continue  # the later cgroup open may reuse a released FD number
        with pytest.raises(OSError):
            os.fstat(descriptor)
    os.fstat(resources.cgroup_delegate_root)
    assert resources.close() is True
    assert resources.close() is True
    assert all(handle.closed for handle in harness.inventory.issued)
    assert harness.factories[0].closed
    with pytest.raises(OSError):
        os.fstat(harness.opened[-1][2])


def test_partial_role_open_reclaims_executables_and_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _harness(tmp_path, monkeypatch)
    original = subject._open_role

    def fail_on_policy(path: str, *, directory: bool) -> int:
        if path == "/etc/codex/requirements.toml":
            raise RuntimeError("policy unavailable")
        return original(path, directory=directory)

    monkeypatch.setattr(subject, "_open_role", fail_on_policy)
    with pytest.raises(RuntimeError, match="policy unavailable"):
        subject.build_waw_production_resources(harness.authority)
    assert len(harness.inventory.issued) == 6
    assert all(handle.closed for handle in harness.inventory.issued)
    assert all(source.closed for source in harness.inventory.sources)
    assert harness.factories == []
    for _path, _directory, descriptor in harness.opened:
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_transferred_bundle_cannot_close_provider_owned_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _harness(tmp_path, monkeypatch)
    resources = subject.build_waw_production_resources(harness.authority)
    delegate = resources.cgroup_delegate_root

    resources.transfer_to_provider()
    assert resources.close() is False
    os.fstat(delegate)

    for handle in resources.handles:
        handle.close()
    resources.launch_factory.close()
    os.close(delegate)


def test_rejects_unverified_authority_before_opening_any_resource(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _harness(tmp_path, monkeypatch)
    with pytest.raises(TypeError, match="verified execution authority"):
        subject.build_waw_production_resources(object())  # type: ignore[arg-type]
    assert harness.opened == []
    assert harness.inventory.issued == []
