#!/usr/bin/env python3
"""Require audited immutable pins for every external workflow action."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

WORKFLOW_ROOT = Path(".github/workflows")
USES_PATTERN = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)(?:\s+#\s*(\S+))?\s*$")
COMMIT_PATTERN = re.compile(r"^[^/@\s]+/[^@\s]+(?:/[^@\s]+)?@[0-9a-f]{40}$")


@dataclass(frozen=True)
class AuditedAction:
    release_tag: str
    commit_sha: str
    source: str


# Each SHA was resolved against the exact tag in the action owner's official
# GitHub repository during the Phase 9 final review. This explicit registry is
# the update contract: a new action or SHA must arrive with a reviewed source
# and exact release tag rather than passing merely because it is 40 characters.
AUDITED_ACTIONS = {
    "actions/checkout": AuditedAction(
        "v4.4.0",
        "11d5960a326750d5838078e36cf38b85af677262",
        "https://github.com/actions/checkout",
    ),
    "actions/setup-python": AuditedAction(
        "v5.6.0",
        "a26af69be951a213d495a4c3e4e4022e16d87065",
        "https://github.com/actions/setup-python",
    ),
    "actions/setup-node": AuditedAction(
        "v4.4.0",
        "49933ea5288caeca8642d1e84afbd3f7d6820020",
        "https://github.com/actions/setup-node",
    ),
    "actions/dependency-review-action": AuditedAction(
        "v4.9.0",
        "2031cfc080254a8a887f58cffee85186f0e49e48",
        "https://github.com/actions/dependency-review-action",
    ),
    "pnpm/action-setup": AuditedAction(
        "v4.3.0",
        "b906affcce14559ad1aafd4ab0e942779e9f58b1",
        "https://github.com/pnpm/action-setup",
    ),
}


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
            release_comment = match.group(2)
            if action.startswith("./"):
                continue
            if action.startswith("docker://") and "@sha256:" in action:
                continue
            if not COMMIT_PATTERN.fullmatch(action):
                failures.append(f"{workflow}:{line_number}: mutable action ref {action!r}")
                continue
            locator, commit_sha = action.rsplit("@", 1)
            audited = AUDITED_ACTIONS.get(locator)
            if audited is None:
                failures.append(
                    f"{workflow}:{line_number}: action source {locator!r} is not audited"
                )
                continue
            if commit_sha != audited.commit_sha:
                failures.append(
                    f"{workflow}:{line_number}: {locator!r} SHA is not the audited "
                    f"{audited.release_tag} commit from {audited.source}"
                )
            if release_comment != audited.release_tag:
                failures.append(
                    f"{workflow}:{line_number}: {locator!r} must document exact tag "
                    f"{audited.release_tag!r}"
                )

    if checked == 0:
        failures.append("no workflow action references were found")
    if failures:
        print("Workflow action pin check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        f"Workflow action pin check passed ({checked} references, "
        f"{len(AUDITED_ACTIONS)} audited sources)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
