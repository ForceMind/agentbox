#!/usr/bin/env python3
"""Cross-check every published dependency and license inventory."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from agentbox_installer.artifact import extract_verified_tar
from agentbox_installer.build import verify_release_inventory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="agentbox-inventory-") as temporary:
        release = Path(temporary) / "release"
        extract_verified_tar(args.artifact, release)
        packages = verify_release_inventory(args.source.resolve(), release)
    print(f"Release dependency/license inventory verified ({packages} third-party packages).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
