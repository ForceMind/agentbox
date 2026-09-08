#!/usr/bin/env python3
"""Require the exact Release Candidate job-result contract for this version."""

from __future__ import annotations

import argparse
from collections.abc import Mapping


class ReleaseGateError(RuntimeError):
    pass


_CURRENT_JOBS = (
    "packaging-toolchain",
    "release-candidate",
    "rc8-artifact-import",
    "rc8-synthetic-source",
)
_RC8_HISTORY_JOBS = (
    "rc8-predecessor-artifact",
    "rc8-artifact-operations",
)
_EXPECTED_RESULTS = {
    "0.3.0rc8": {
        **dict.fromkeys(_CURRENT_JOBS, "success"),
        **dict.fromkeys(_RC8_HISTORY_JOBS, "success"),
    },
    "0.3.0rc9": {
        **dict.fromkeys(_CURRENT_JOBS, "success"),
        **dict.fromkeys(_RC8_HISTORY_JOBS, "skipped"),
    },
    "0.3.0rc10": {
        **dict.fromkeys(_CURRENT_JOBS, "success"),
        **dict.fromkeys(_RC8_HISTORY_JOBS, "skipped"),
    },
    "0.3.0rc11": {
        **dict.fromkeys(_CURRENT_JOBS, "success"),
        **dict.fromkeys(_RC8_HISTORY_JOBS, "skipped"),
    },
    "0.3.0rc12": {
        **dict.fromkeys(_CURRENT_JOBS, "success"),
        **dict.fromkeys(_RC8_HISTORY_JOBS, "skipped"),
    },
}


def validate_release_gate(candidate_version: str, results: Mapping[str, str]) -> None:
    """Reject unknown versions and any incomplete or unexpected job result."""

    expected = _EXPECTED_RESULTS.get(candidate_version)
    if expected is None:
        raise ReleaseGateError("release gate candidate version is not approved")
    if dict(results) != expected:
        raise ReleaseGateError("release gate job results do not match the version contract")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-version", required=True)
    for job in (*_CURRENT_JOBS, *_RC8_HISTORY_JOBS):
        parser.add_argument(f"--{job}-result", required=True)
    args = parser.parse_args()
    results = {
        job: getattr(args, job.replace("-", "_") + "_result")
        for job in (*_CURRENT_JOBS, *_RC8_HISTORY_JOBS)
    }
    try:
        validate_release_gate(args.candidate_version, results)
    except ReleaseGateError:
        parser.exit(1, "release candidate gate failed\n")
    print(f"Release candidate gate passed for {args.candidate_version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
