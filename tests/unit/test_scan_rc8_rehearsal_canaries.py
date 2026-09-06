from __future__ import annotations

import base64
import importlib.util
import io
import json
import os
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/scan-rc8-rehearsal-canaries.py"


def _module() -> Any:
    spec = importlib.util.spec_from_file_location("scan_rc8_rehearsal_canaries", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load canary scanner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canary_file(root: Path, values: tuple[bytes, ...]) -> Path:
    path = root / "canaries.json"
    path.write_text(json.dumps([base64.b64encode(value).decode("ascii") for value in values]))
    path.chmod(0o600)
    return path


def _typed_canary_file(root: Path, values: tuple[bytes, bytes, bytes]) -> Path:
    path = root / "typed-canaries.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "canaries": [
                    {"kind": kind, "value_base64": base64.b64encode(value).decode("ascii")}
                    for kind, value in zip(
                        ("payload", "private_key", "ticket"), values, strict=True
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


@pytest.mark.parametrize(
    "form",
    ("raw", "hex", "upper_hex", "base64", "base64url", "base64_no_pad", "base64url_no_pad"),
)
def test_scan_rejects_each_canary_encoding_without_disclosure(tmp_path: Path, form: str) -> None:
    module = _module()
    canary = bytes(range(16)) + b"\xfb\xff-rc8-dynamic-canary"
    target = tmp_path / "surface"
    target.mkdir()
    value = {
        "raw": canary,
        "hex": canary.hex().encode("ascii"),
        "upper_hex": canary.hex().upper().encode("ascii"),
        "base64": base64.b64encode(canary),
        "base64url": base64.urlsafe_b64encode(canary),
        "base64_no_pad": base64.b64encode(canary).rstrip(b"="),
        "base64url_no_pad": base64.urlsafe_b64encode(canary).rstrip(b"="),
    }[form]
    (target / "evidence.bin").write_bytes(b"prefix:" + value + b":suffix")

    with pytest.raises(module.RehearsalCanaryError) as raised:
        module.scan_surfaces({"fixture": target}, (canary,))
    assert str(raised.value) == "fixture"
    assert canary.hex() not in str(raised.value)


@pytest.mark.parametrize(("suffix", "writer"), ((".tar.gz", "tar"), (".whl", "zip")))
def test_scan_rejects_canary_inside_compressed_bundle_member(
    tmp_path: Path, suffix: str, writer: str
) -> None:
    module = _module()
    canary = bytes(range(24)) + b"-compressed-rc8-canary"
    archive = tmp_path / f"candidate{suffix}"
    member = b"nested:" + base64.urlsafe_b64encode(canary).rstrip(b"=")
    if writer == "tar":
        with tarfile.open(archive, "w:gz") as bundle:
            info = tarfile.TarInfo("wheelhouse/agentbox.whl")
            info.size = len(member)
            bundle.addfile(info, io.BytesIO(member))
    else:
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("agentbox/data.bin", member)

    with pytest.raises(module.RehearsalCanaryError, match="bundle"):
        module.scan_surfaces({"bundle": archive}, (canary,))


def test_scan_allows_clean_evidence_and_reads_safe_canary_file(tmp_path: Path) -> None:
    module = _module()
    canary = b"rc8-dynamic-canary-abcdefghijkl"
    canary_file = _canary_file(tmp_path, (canary,))
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "clean.txt").write_text("bounded non-secret evidence", encoding="utf-8")

    values = module.read_canary_file(canary_file)
    assert values == (canary,)
    module.scan_surfaces({"evidence": evidence}, values)


def test_scan_requires_the_three_typed_dynamic_canaries(tmp_path: Path) -> None:
    module = _module()
    values = (
        b"rc8-payload-canary-0123456789",
        bytes(range(32)),
        b"wat_0123456789abcdef0123456789abcdef",
    )
    canary_file = _typed_canary_file(tmp_path, values)

    assert module.read_canary_file(canary_file) == values
    value = json.loads(canary_file.read_text(encoding="utf-8"))
    value["canaries"].pop()
    canary_file.write_text(json.dumps(value), encoding="utf-8")
    canary_file.chmod(0o600)
    with pytest.raises(module.RehearsalCanaryError, match="canary input"):
        module.read_canary_file(canary_file)


def test_scan_rejects_canary_in_archive_names_and_zip_metadata(tmp_path: Path) -> None:
    module = _module()
    canary = b"rc8-archive-name-canary"
    archive = tmp_path / "candidate.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.comment = base64.b64encode(canary)
        bundle.writestr("clean.txt", b"clean")

    with pytest.raises(module.RehearsalCanaryError, match="bundle"):
        module.scan_surfaces({"bundle": archive}, (canary,))


def test_scan_rejects_canary_in_regular_file_and_directory_names(tmp_path: Path) -> None:
    module = _module()
    canary = b"rc8-file-name-canary"
    directory = tmp_path / base64.urlsafe_b64encode(canary).rstrip(b"=").decode("ascii")
    directory.mkdir()
    (directory / "clean.txt").write_text("clean", encoding="utf-8")

    with pytest.raises(module.RehearsalCanaryError, match="surface"):
        module.scan_surfaces({"surface": tmp_path}, (canary,))


def test_scan_rejects_unsafe_canary_input_and_surface_symlink(tmp_path: Path) -> None:
    module = _module()
    canary = b"rc8-dynamic-canary-abcdefghijkl"
    canary_file = _canary_file(tmp_path, (canary,))
    canary_file.chmod(0o644)
    with pytest.raises(module.RehearsalCanaryError, match="canary input"):
        module.read_canary_file(canary_file)

    target = tmp_path / "target"
    target.write_bytes(b"clean")
    link = tmp_path / "link"
    try:
        os.symlink(target, link)
    except OSError as exc:
        pytest.skip(f"test host cannot create symlink: {exc}")
    with pytest.raises(module.RehearsalCanaryError, match="unsafe"):
        module.scan_surfaces({"unsafe": link}, (canary,))
