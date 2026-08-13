#!/usr/bin/env python3
"""Check repository Markdown relative links and local anchors."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)


def _anchor(value: str) -> str:
    value = re.sub(r"[`*_~]", "", value.strip().lower())
    value = re.sub(r"[^\w\- ]", "", value, flags=re.UNICODE)
    return re.sub(r"\s+", "-", value)


def main() -> int:
    failures: list[str] = []
    checked = 0
    markdown_files = [
        ROOT / "README.md",
        ROOT / "SECURITY.md",
        *sorted((ROOT / "docs").rglob("*.md")),
    ]
    for document in markdown_files:
        text = document.read_text(encoding="utf-8")
        for raw_target in LINK.findall(text):
            target = raw_target.strip().strip("<>")
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            checked += 1
            path_text, separator, fragment = target.partition("#")
            destination = (
                document if not path_text else (document.parent / unquote(path_text)).resolve()
            )
            try:
                destination.relative_to(ROOT)
            except ValueError:
                failures.append(f"{document.relative_to(ROOT)}: link escapes repository: {target}")
                continue
            if not destination.is_file():
                failures.append(f"{document.relative_to(ROOT)}: missing link target: {target}")
                continue
            if separator and destination.suffix.lower() == ".md":
                anchors = {
                    _anchor(heading)
                    for heading in HEADING.findall(destination.read_text(encoding="utf-8"))
                }
                if unquote(fragment).lower() not in anchors:
                    failures.append(f"{document.relative_to(ROOT)}: missing anchor: {target}")
    if failures:
        print("Documentation link check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"Documentation link check passed ({checked} relative links).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
