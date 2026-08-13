#!/usr/bin/env python3
"""Require immutable commit pins for every third-party workflow action."""

from __future__ import annotations

import re
import sys
from pathlib import Path

WORKFLOW_ROOT = Path(".github/workflows")
USES_PATTERN = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
COMMIT_PATTERN = re.compile(r"^[^/@\s]+/[^@\s]+(?:/[^@\s]+)?@[0-9a-f]{40}$")


def main() -> int:
    failures: list[str] = []
    checked = 0
    for workflow in sorted(WORKFLOW_ROOT.glob("*.y*ml")):
        for line_number, line in enumerate(workflow.read_text().splitlines(), start=1):
            match = USES_PATTERN.match(line)
            if match is None:
                continue
            checked += 1
            action = match.group(1)
            if action.startswith("./"):
                continue
            if action.startswith("docker://") and "@sha256:" in action:
                continue
            if not COMMIT_PATTERN.fullmatch(action):
                failures.append(f"{workflow}:{line_number}: mutable action ref {action!r}")

    if checked == 0:
        failures.append("no workflow action references were found")
    if failures:
        print("Workflow action pin check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"Workflow action pin check passed ({checked} references).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
