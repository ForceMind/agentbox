#!/usr/bin/env python3
"""Compare pnpm's locked production license output with the reviewed inventory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agentbox_installer.build import (
    BuildError,
    _frontend_package_inventory,
    frontend_inventory_from_pnpm,
)

MAX_INPUT_BYTES = 2 * 1024 * 1024


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    payload = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(payload) > MAX_INPUT_BYTES:
        raise SystemExit("frontend license output exceeds the input limit")
    try:
        value: Any = json.loads(payload)
        observed = frontend_inventory_from_pnpm(value)
        reviewed = _frontend_package_inventory(args.source.resolve())
    except (UnicodeError, json.JSONDecodeError, BuildError) as exc:
        raise SystemExit(str(exc)) from exc
    if observed != reviewed:
        raise SystemExit(
            "frontend production license inventory drifted; review and update "
            "licenses-frontend.json"
        )
    print(f"Frontend production license inventory passed ({len(reviewed)} packages).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
