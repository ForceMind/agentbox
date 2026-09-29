from __future__ import annotations

import grp
import hashlib
import json
import os
import pwd
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest import mock

import pytest
from agentbox_runtime import waw_vendor_enrollment as subject
from agentbox_runtime.waw_fixed_transport import WAWVerifiedExecutionAuthority
from agentbox_runtime.waw_manifest_codecs import CrossManifestPinV2
from agentbox_runtime.waw_vendor_enrollment import (
    WAWVendorEnrollmentError,
    WAWVendorEnrollmentRecord,
)

VALUES = {
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


def _canonical(values: Mapping[str, object]) -> bytes:
    return (
        json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode()


def _fixture(tmp_path: Path, raw: bytes | None = None) -> tuple[Path, Path]:
    root = tmp_path / "root"
    parent = root / "var" / "lib" / "agentbox-waw"
    parent.mkdir(parents=True)
    for path in (root, root / "var", root / "var" / "lib"):
        path.chmod(0o700)
    parent.chmod(0o750)
    leaf = parent / "vendor-enrollment.v1.json"
    leaf.write_bytes(_canonical(VALUES) if raw is None else raw)
    leaf.chmod(0o440)
    return root, leaf


def _load(root: Path, leaf: Path) -> WAWVendorEnrollmentRecord:
    return subject._load_at(leaf, root=root, owner_uid=os.geteuid(), runtime_gid=os.getegid())


def _authority(values: Mapping[str, object] = VALUES) -> WAWVerifiedExecutionAuthority:
    manifest = object.__new__(CrossManifestPinV2)
    object.__setattr__(
        manifest,
        "runtime",
        SimpleNamespace(
            runtime_host_installation_id=values["runtime_host_installation_id"],
            runtime_host_installation_revision=values["runtime_host_installation_revision"],
            enrollment_epoch=values["enrollment_epoch"],
            enrollment_state=values["enrollment_state"],
        ),
    )
    object.__setattr__(manifest, "runtime_manifest_digest", values["host_manifest_digest"])
    authority = object.__new__(WAWVerifiedExecutionAuthority)
    object.__setattr__(authority, "_manifest", manifest)
    return authority


def test_fixed_record_is_canonical_bounded_and_pinned(tmp_path: Path) -> None:
    root, leaf = _fixture(tmp_path)
    record = _load(root, leaf)
    assert record.values == {
        "claude_vendor_version": "2.1.226",
        "codex_vendor_version": "0.153.4",
        "codex_unauthenticated_output_sha256": "b" * 64,
    }
    assert record.raw_sha256 == hashlib.sha256(_canonical(VALUES)).hexdigest()
    assert "2.1.226" not in repr(record)
    record.require_authority(_authority())
    with pytest.raises(TypeError):
        cast(Any, record.values)["claude_vendor_version"] = "changed"


@pytest.mark.parametrize(
    "change",
    [
        {"runtime_host_installation_id": "wri_bad"},
        {"runtime_host_installation_revision": "0"},
        {"host_manifest_digest": "A" * 64},
        {"enrollment_epoch": "18446744073709551616"},
        {"enrollment_state": "untrusted"},
        {"claude_vendor_version": "bad version"},
        {"codex_vendor_version": "\n"},
        {"codex_unauthenticated_output_sha256": "0" * 63},
        {"extra": "not allowed"},
    ],
)
def test_invalid_or_extra_enrollment_fields_fail_closed(
    tmp_path: Path, change: dict[str, object]
) -> None:
    root, leaf = _fixture(tmp_path, _canonical({**VALUES, **change}))
    with pytest.raises(WAWVendorEnrollmentError):
        _load(root, leaf)


@pytest.mark.parametrize(
    "raw",
    [
        b"{}\n",
        json.dumps(VALUES).encode() + b"\n",
        _canonical(VALUES).replace(
            b'"enrollment_epoch":"3"', b'"enrollment_epoch":"3","enrollment_epoch":"3"'
        ),
        _canonical(VALUES) + b" ",
        b"x" * 1025,
    ],
)
def test_noncanonical_duplicate_or_oversized_record_is_rejected(tmp_path: Path, raw: bytes) -> None:
    root, leaf = _fixture(tmp_path, raw)
    with pytest.raises(WAWVendorEnrollmentError):
        _load(root, leaf)


def test_symlink_wrong_mode_and_missing_record_fail_closed(tmp_path: Path) -> None:
    root, leaf = _fixture(tmp_path)
    leaf.chmod(0o644)
    with pytest.raises(WAWVendorEnrollmentError):
        _load(root, leaf)
    leaf.chmod(0o440)
    leaf.unlink()
    leaf.symlink_to(root / "missing")
    with pytest.raises(WAWVendorEnrollmentError):
        _load(root, leaf)
    leaf.unlink()
    with pytest.raises(WAWVendorEnrollmentError):
        _load(root, leaf)


def test_unsafe_parent_is_rejected(tmp_path: Path) -> None:
    root, leaf = _fixture(tmp_path)
    leaf.parent.chmod(0o770)
    with pytest.raises(WAWVendorEnrollmentError):
        _load(root, leaf)


def test_hardlink_and_wrong_runtime_group_are_rejected(tmp_path: Path) -> None:
    root, leaf = _fixture(tmp_path)
    os.link(leaf, leaf.parent / "second-name")
    with pytest.raises(WAWVendorEnrollmentError):
        _load(root, leaf)
    (leaf.parent / "second-name").unlink()
    with pytest.raises(WAWVendorEnrollmentError):
        subject._load_at(leaf, root=root, owner_uid=os.geteuid(), runtime_gid=os.getegid() + 1)


def test_production_loader_rejects_wrong_process_before_file_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pwd,
        "getpwnam",
        lambda _name: SimpleNamespace(pw_uid=os.geteuid() + 1, pw_gid=os.getegid()),
    )
    monkeypatch.setattr(grp, "getgrnam", lambda _name: SimpleNamespace(gr_gid=os.getegid()))
    reader = mock.Mock()
    monkeypatch.setattr(subject, "_load_at", reader)
    with pytest.raises(WAWVendorEnrollmentError):
        subject.load_waw_vendor_enrollment()
    reader.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("runtime_host_installation_id", "wri_" + "f" * 32),
        ("runtime_host_installation_revision", "4"),
        ("host_manifest_digest", "c" * 64),
        ("enrollment_epoch", "4"),
        ("enrollment_state", "rotation"),
    ],
)
def test_every_authority_pin_is_required(tmp_path: Path, field: str, value: str) -> None:
    root, leaf = _fixture(tmp_path)
    record = _load(root, leaf)
    with pytest.raises(WAWVendorEnrollmentError):
        record.require_authority(_authority({**VALUES, field: value}))


def test_revalidation_rejects_changed_installed_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, leaf = _fixture(tmp_path)
    observed = _load(root, leaf)
    monkeypatch.setattr(subject, "load_waw_vendor_enrollment", lambda: observed)
    subject.revalidate_waw_vendor_enrollment(observed)
    monkeypatch.setattr(
        subject,
        "load_waw_vendor_enrollment",
        lambda: replace(observed, raw_sha256="0" * 64),
    )
    with pytest.raises(WAWVendorEnrollmentError):
        subject.revalidate_waw_vendor_enrollment(observed)
