"""Phase 3 Worker lifecycle and expired-session maintenance."""

from __future__ import annotations

import argparse
import asyncio
import signal
from collections.abc import Sequence

from agentbox_core import __version__
from agentbox_core.configuration import Settings
from agentbox_core.services import ControlPlaneServices, build_services


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentbox-worker")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--check", action="store_true", help="check database readiness and exit")
    parser.add_argument("--once", action="store_true", help="run one session cleanup pass and exit")
    return parser


def check_worker(services: ControlPlaneServices) -> bool:
    return services.database.check_connection() and services.database.migrations_current()


async def run_worker(services: ControlPlaneServices, cleanup_interval: float = 60.0) -> None:
    """Run bounded session maintenance until a normal shutdown signal."""
    shutdown_requested = asyncio.Event()
    loop = asyncio.get_running_loop()

    for shutdown_signal in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(shutdown_signal, shutdown_requested.set)

    print(f"AgentBox Worker {__version__}: control-plane maintenance ready")
    while not shutdown_requested.is_set():
        services.sessions.cleanup()
        try:
            await asyncio.wait_for(shutdown_requested.wait(), timeout=cleanup_interval)
        except TimeoutError:
            continue
    print("AgentBox Worker: clean shutdown")


def main(argv: Sequence[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    settings = Settings()
    services = build_services(settings)
    try:
        if args.check:
            ready = check_worker(services)
            print(f"AgentBox Worker: {'ready' if ready else 'not ready'}")
            return 0 if ready else 10
        if args.once:
            if not check_worker(services):
                print("AgentBox Worker: not ready")
                return 10
            deleted = services.sessions.cleanup()
            print(f"AgentBox Worker: session cleanup complete ({deleted} removed)")
            return 0

        if not check_worker(services):
            print("AgentBox Worker: database or migrations not ready")
            return 10
        asyncio.run(run_worker(services))
        return 0
    finally:
        services.database.close()
