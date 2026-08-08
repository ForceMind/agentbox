"""Idle Worker process used only to validate packaging and clean shutdown."""

import argparse
import asyncio
import signal
from collections.abc import Sequence

from agentbox_core import __version__


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentbox-worker")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="run the Phase 2 in-process health check and exit",
    )
    return parser


async def run_worker() -> None:
    """Wait safely until a normal service-stop signal arrives."""
    shutdown_requested = asyncio.Event()
    loop = asyncio.get_running_loop()

    for shutdown_signal in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(shutdown_signal, shutdown_requested.set)

    print(f"AgentBox Worker {__version__}: engineering skeleton ready")
    await shutdown_requested.wait()
    print("AgentBox Worker: clean shutdown")


def main(argv: Sequence[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    if args.check:
        print("AgentBox Worker: ok (Phase 2 skeleton; no Jobs configured)")
        return 0

    asyncio.run(run_worker())
    return 0
