#!/usr/bin/env python3
"""Validate the fixed rc8 workflow inputs before any artifact checkout or build."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_PREDECESSOR_VERSION = "0.3.0rc7"
_PREDECESSOR_SHA = "87f5bce964eba231a6a7ade73eaedac7e54646ae"
_CANDIDATE_VERSION = "0.3.0rc8"
_REQUIRED_REHEARSALS = (
    "unpacked_native_source",
    "wheelhouse_import_provenance",
    "synthetic_waw_end_to_end",
    "exact_upgrade_rollback",
    "canary_surface_scan",
)
_FORBIDDEN_CAPABILITIES = (
    "systemd_activation",
    "real_provider_secret",
    "real_vendor_login",
    "real_host_qualification",
    "production_fault_switch",
)


class ContractError(RuntimeError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ContractError("duplicate JSON key")
        value[key] = item
    return value


def _read_contract(path: Path) -> dict[str, Any]:
    try:
        details = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(details.st_mode) or details.st_size > 16_384:
            raise ContractError("contract file is unsafe")
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    except ContractError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("contract file is invalid") from exc
    if not isinstance(value, dict):
        raise ContractError("contract root is invalid")
    return value


def validate_contract(path: Path, candidate_sha: str) -> dict[str, str]:
    """Return only the fixed values trusted by later workflow steps."""

    if _SHA.fullmatch(candidate_sha) is None:
        raise ContractError("candidate SHA is invalid")
    value = _read_contract(path)
    if set(value) != {
        "schema_version",
        "stage",
        "predecessor",
        "candidate",
        "required_rehearsals",
        "forbidden_capabilities",
    }:
        raise ContractError("contract schema is invalid")
    predecessor = value.get("predecessor")
    candidate = value.get("candidate")
    rehearsals = value.get("required_rehearsals")
    forbidden = value.get("forbidden_capabilities")
    if (
        value.get("schema_version") != 1
        or value.get("stage") != "r11-rc8-artifact-operations"
        or not isinstance(predecessor, dict)
        or set(predecessor) != {"version", "merge_sha"}
        or predecessor.get("version") != _PREDECESSOR_VERSION
        or predecessor.get("merge_sha") != _PREDECESSOR_SHA
        or not isinstance(candidate, dict)
        or set(candidate) != {"version", "source_sha"}
        or candidate.get("version") != _CANDIDATE_VERSION
        or candidate.get("source_sha") != "WORKFLOW_EXACT_HEAD"
        or not isinstance(rehearsals, list)
        or tuple(rehearsals) != _REQUIRED_REHEARSALS
        or not isinstance(forbidden, list)
        or tuple(forbidden) != _FORBIDDEN_CAPABILITIES
    ):
        raise ContractError("contract values are invalid")
    return {
        "candidate_sha": candidate_sha,
        "candidate_version": _CANDIDATE_VERSION,
        "predecessor_sha": _PREDECESSOR_SHA,
        "predecessor_version": _PREDECESSOR_VERSION,
    }


def write_github_output(path: Path, values: dict[str, str]) -> None:
    """Append only validated public workflow values to GitHub's designated file."""

    try:
        details = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(details.st_mode):
            raise ContractError("GitHub output is unsafe")
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "w", encoding="ascii") as stream:
            for name in (
                "candidate_sha",
                "candidate_version",
                "predecessor_sha",
                "predecessor_version",
            ):
                stream.write(f"{name}={values[name]}\n")
            stream.flush()
            os.fsync(stream.fileno())
    except ContractError:
        raise
    except OSError as exc:
        raise ContractError("GitHub output is unavailable") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    try:
        values = validate_contract(args.contract, args.candidate_sha)
        if args.github_output is not None:
            write_github_output(args.github_output, values)
    except ContractError:
        parser.exit(1, "rc8 rehearsal contract failed\n")
    print(
        "rc8 rehearsal contract passed "
        f"(predecessor {values['predecessor_version']} {values['predecessor_sha']})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
