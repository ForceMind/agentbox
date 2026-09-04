"""Local operator-only trust enrollment; never exposed through Web/API."""

from __future__ import annotations

import argparse
from pathlib import Path

from agentbox_browser_trust.store import BrowserTrustStore

DEFAULT_STORE = Path("/var/lib/agentbox-browser-trust")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="agentbox-browser-trustctl")
    commands = value.add_subparsers(dest="command", required=True)
    commands.add_parser("initialize")
    install = commands.add_parser("install")
    install.add_argument("candidate", type=Path)
    return value


def main() -> None:
    arguments = parser().parse_args()
    store = BrowserTrustStore(DEFAULT_STORE)
    if arguments.command == "initialize":
        print(store.initialize())
        return
    store.initialize()
    candidate: Path = arguments.candidate
    raw = candidate.read_bytes()
    state = store.install(raw)
    print(
        f"installed root={state.enrollment.root_revision} "
        f"pin={state.enrollment.pin_revision} origin={state.enrollment.origin}"
    )
