"""Dedicated local trustd server; no Web/API/Runtime authority is imported."""

from __future__ import annotations

import os
import socket
import stat
import struct
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path

from agentbox_browser_trust.codec import (
    TRUSTD_MESSAGE_MAX,
    canonical_json,
    read_frame,
    strict_json,
    write_frame,
)
from agentbox_browser_trust.protocol import TrustProtocolSession
from agentbox_browser_trust.store import BrowserTrustStore

DEFAULT_STORE = Path("/var/lib/agentbox-browser-trust")
DEFAULT_SOCKET = Path("/run/agentbox-browser-trust/trustd.sock")
DEFAULT_CLIENT_POLICY = Path("/etc/agentbox-browser-trust/clients.v1.json")
MAX_CONNECTIONS = 32
MAX_REQUESTS = 8192
SOCKET_DEADLINE_SECONDS = 8.0


def peer_credentials(connection: socket.socket) -> tuple[int, int, int]:
    option = getattr(socket, "SO_PEERCRED", None)
    if option is None:
        raise RuntimeError("SO_PEERCRED is unavailable")
    raw = connection.getsockopt(socket.SOL_SOCKET, option, struct.calcsize("3i"))
    return struct.unpack("3i", raw)


def serve_connection(
    connection: socket.socket,
    store: BrowserTrustStore,
    *,
    allowed_peer_uids: frozenset[int],
) -> None:
    pid, uid, _gid = peer_credentials(connection)
    if pid < 1 or uid not in allowed_peer_uids:
        raise RuntimeError("native host peer is not authorized")
    connection.settimeout(SOCKET_DEADLINE_SECONDS)
    stream = connection.makefile("rwb", buffering=0)
    try:
        opened = strict_json(read_frame(stream, limit=4096, little_endian=False), limit=4096)
        session = TrustProtocolSession(store, opened)
        write_frame(
            stream,
            canonical_json(session.broker_opened(), limit=4096),
            limit=4096,
            little_endian=False,
        )
        for _ in range(MAX_REQUESTS):
            value = strict_json(read_frame(stream, limit=4096, little_endian=False), limit=4096)
            response = session.handle(value)
            write_frame(
                stream,
                canonical_json(response, limit=TRUSTD_MESSAGE_MAX),
                limit=TRUSTD_MESSAGE_MAX,
                little_endian=False,
            )
            if response["type"] in ("CLOSE", "INVALIDATE"):
                return
        raise RuntimeError("browser trust request limit exceeded")
    finally:
        stream.close()


def load_allowed_peer_uids(path: Path = DEFAULT_CLIENT_POLICY) -> frozenset[int]:
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o644
        or info.st_uid != 0
        or info.st_gid != 0
        or info.st_size < 1
        or info.st_size > 4096
    ):
        raise RuntimeError("browser trust client policy is unavailable")
    value = strict_json(path.read_bytes(), limit=4096)
    if type(value) is not dict or frozenset(value) != {"schema_version", "uids"}:
        raise RuntimeError("browser trust client policy is invalid")
    uids = value["uids"]
    if (
        value["schema_version"] != "waw-browser-trust-clients-v1"
        or type(uids) is not list
        or not 1 <= len(uids) <= 32
        or any(type(uid) is not int or uid < 1 or uid > 0x7FFFFFFF for uid in uids)
        or len(set(uids)) != len(uids)
    ):
        raise RuntimeError("browser trust client policy is invalid")
    return frozenset(uids)


def run() -> None:
    store = BrowserTrustStore(DEFAULT_STORE)
    store.initialize()
    allowed_peer_uids = load_allowed_peer_uids()
    parent = DEFAULT_SOCKET.parent
    parent_info = parent.lstat()
    if (
        not stat.S_ISDIR(parent_info.st_mode)
        or stat.S_IMODE(parent_info.st_mode) != 0o750
        or parent_info.st_uid != os.geteuid()
        or DEFAULT_SOCKET.exists()
    ):
        raise RuntimeError("browser trust RuntimeDirectory is unavailable")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    capacity = threading.BoundedSemaphore(MAX_CONNECTIONS)
    workers = ThreadPoolExecutor(max_workers=MAX_CONNECTIONS, thread_name_prefix="trustd")

    def handle(connection: socket.socket) -> None:
        try:
            with suppress(Exception):
                serve_connection(connection, store, allowed_peer_uids=allowed_peer_uids)
        finally:
            connection.close()
            capacity.release()

    try:
        listener.bind(str(DEFAULT_SOCKET))
        os.chmod(DEFAULT_SOCKET, 0o660)
        listener.listen(MAX_CONNECTIONS)
        while True:
            connection, _ = listener.accept()
            if not capacity.acquire(blocking=False):
                connection.close()
                continue
            try:
                workers.submit(handle, connection)
            except RuntimeError:
                connection.close()
                capacity.release()
    finally:
        listener.close()
        workers.shutdown(wait=True, cancel_futures=True)
        with suppress(OSError):
            DEFAULT_SOCKET.unlink()


def main() -> None:
    run()
