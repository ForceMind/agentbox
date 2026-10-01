"""Bounded Linux current-UID Remote evidence; incomplete visibility is UNKNOWN."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import sys
import time
from pathlib import Path

from agentbox_runtime.models import RemoteState


class LinuxCodexRemoteObserver:
    def __init__(self, proc_root: Path = Path("/proc")) -> None:
        self.proc = proc_root

    @staticmethod
    def _path_read(path: str, maximum: int) -> bytes:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            raw = os.read(fd, maximum + 1)
            if len(raw) > maximum:
                raise ValueError("bounded namespace metadata exceeded")
            return raw
        finally:
            os.close(fd)

    def _namespace_complete(self, descriptor: int) -> bool:
        if self.proc != Path("/proc") or sys.platform != "linux":
            return False
        # PID 1 namespace symlinks can require ptrace privileges. Use public
        # kernel metadata instead, under the exact unit's no-private-PID and
        # empty-capability policy; vendor PID namespaces fail this guard.
        status = self._path_read("/proc/self/status", 65536)
        nspids = [line.split()[1:] for line in status.splitlines() if line.startswith(b"NSpid:\t")]
        capabilities = [
            line.split()[1:] for line in status.splitlines() if line.startswith(b"CapEff:\t")
        ]
        if (
            nspids != [[str(os.getpid()).encode()]]
            or len(capabilities) != 1
            or len(capabilities[0]) != 1
            or int(capabilities[0][0], 16) != 0
        ):
            return False
        if self._path_read("/proc/1/comm", 64).strip() != b"systemd":
            return False
        if self._path_read("/proc/self/uid_map", 4096).split() != [b"0", b"0", b"4294967295"]:
            return False
        fdinfo = self._path_read(f"/proc/self/fdinfo/{descriptor}", 16384)
        mount_ids = [
            line.split()[1] for line in fdinfo.splitlines() if line.startswith(b"mnt_id:\t")
        ]
        if len(mount_ids) != 1:
            return False
        rows = self._path_read("/proc/self/mountinfo", 2 * 1024 * 1024)
        if len(rows) > 2 * 1024 * 1024:
            return False
        matching = [line.split() for line in rows.splitlines() if line.split()[0] == mount_ids[0]]
        if len(matching) != 1:
            return False
        row = matching[0]
        separator = row.index(b"-")
        if row[3:5] != [b"/", b"/proc"] or row[separator + 1] != b"proc":
            return False
        options = row[5].split(b",") + row[separator + 3].split(b",")
        return all(
            not option.startswith(b"hidepid=") or option in {b"hidepid=0", b"hidepid=off"}
            for option in options
        )

    @staticmethod
    def _read(parent: int, name: str, maximum: int) -> bytes:
        fd = os.open(
            name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
        )
        try:
            raw = os.read(fd, maximum + 1)
            if len(raw) > maximum:
                raise ValueError("bounded process metadata exceeded")
            return raw
        finally:
            os.close(fd)

    @staticmethod
    def _identity(raw: bytes, pid: str) -> tuple[bytes, bytes]:
        boundary = raw.rfind(b") ")
        if not raw.startswith(pid.encode() + b" (") or boundary < 0:
            raise ValueError("invalid process stat")
        fields = raw[boundary + 2 :].split()
        if (
            len(fields) < 20
            or fields[0] not in {b"R", b"S", b"D", b"Z", b"T", b"t", b"X", b"I"}
            or not fields[19].isdigit()
        ):
            raise ValueError("invalid process identity")
        return fields[0], fields[19]

    def _snapshot(
        self, proc: int, uid: int, executable: tuple[int, int], deadline: float
    ) -> tuple[dict[str, tuple[bytes, bytes, tuple[int, int], bytes]], bool]:
        result: dict[str, tuple[bytes, bytes, tuple[int, int], bytes]] = {}
        running = False
        names = [name for name in os.listdir(proc) if re.fullmatch(r"[1-9][0-9]{0,9}", name)]
        if len(names) > 65536:
            raise ValueError("process visibility exceeded budget")
        for name in names:
            if time.monotonic() >= deadline:
                raise TimeoutError("process visibility timed out")
            try:
                parent = os.open(
                    name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=proc
                )
            except FileNotFoundError:
                raise ValueError("process set changed") from None
            try:
                status = self._read(parent, "status", 65536)
                uid_rows = [
                    line.split()[1:] for line in status.splitlines() if line.startswith(b"Uid:\t")
                ]
                if (
                    len(uid_rows) != 1
                    or len(uid_rows[0]) != 4
                    or any(not value.isdigit() for value in uid_rows[0])
                ):
                    raise ValueError("UID visibility is incomplete")
                if uid not in {int(value) for value in uid_rows[0]}:
                    continue
                before = self._identity(self._read(parent, "stat", 16384), name)
                if before[0] in {b"Z", b"X"}:
                    result[name] = (before[0], before[1], (0, 0), b"")
                    continue
                facts = os.stat("exe", dir_fd=parent)
                identity = (facts.st_dev, facts.st_ino)
                argv = self._read(parent, "cmdline", 65536)
                after = self._identity(self._read(parent, "stat", 16384), name)
                if (
                    before[1] != after[1]
                    or after[0] in {b"Z", b"X"}
                    or not argv.endswith(b"\0")
                    or not argv
                ):
                    raise ValueError("process identity changed or argv incomplete")
                result[name] = (b"L", before[1], identity, hashlib.sha256(argv).digest())
                # Any Remote token on the selected executable is conservative
                # RUNNING, including global options/aliases around the command.
                arguments = argv.split(b"\0")
                if b"remote-control" in arguments[1:]:
                    if identity == executable:
                        running = True
                    elif any(
                        Path(os.fsdecode(argument)).name.startswith("codex")
                        for argument in arguments[:2]
                    ):
                        raise ValueError("another Codex installation may own Remote")
            finally:
                os.close(parent)
        return result, running

    def observe(self, executable: Path) -> RemoteState:
        proc = -1
        try:
            uid = os.geteuid()
            if uid == 0 or sys.platform != "linux" or os.getresuid() != (uid, uid, uid):
                return RemoteState.UNKNOWN
            facts = executable.stat()
            if not stat.S_ISREG(facts.st_mode):
                return RemoteState.UNKNOWN
            expected = (facts.st_dev, facts.st_ino)
            proc = os.open(self.proc, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            if not self._namespace_complete(proc):
                return RemoteState.UNKNOWN
            deadline = time.monotonic() + 2
            first, first_running = self._snapshot(proc, uid, expected, deadline)
            second, second_running = self._snapshot(proc, uid, expected, deadline)
            if first_running or second_running:
                return RemoteState.RUNNING
            current = executable.stat()
            if (
                first != second
                or (current.st_dev, current.st_ino) != expected
                or not self._namespace_complete(proc)
            ):
                return RemoteState.UNKNOWN
            return RemoteState.STOPPED
        except (OSError, ValueError, IndexError):
            return RemoteState.UNKNOWN
        finally:
            if proc >= 0:
                os.close(proc)
