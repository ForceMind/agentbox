"""Fixed FHS deployment resources and fixture-root mapping."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class DirectorySpec:
    path: str
    owner: str
    group: str
    mode: int
    persistent: bool = True


DIRECTORIES = (
    DirectorySpec("/etc/agentbox", "root", "agentbox", 0o750),
    # The application needs directory write access for SQLite WAL/SHM files, but
    # must not be able to replace root-owned backup, receipt, or journal names.
    DirectorySpec("/var/lib/agentbox", "root", "agentbox", 0o1770),
    DirectorySpec("/var/lib/agentbox/backups", "root", "root", 0o700),
    # WAW Runtime trust-root state is Runtime-owned and never readable by the
    # API/Worker identities.  The epoch file itself is created atomically by
    # the installer only during a fresh enrollment.
    DirectorySpec("/var/lib/agentbox-waw", "root", "agentbox-runtime", 0o750),
    DirectorySpec(
        "/var/lib/agentbox-waw/runtime-epoch-v1",
        "agentbox-runtime",
        "agentbox-runtime",
        0o700,
    ),
    # Durable Project binding records are Runtime-only state.  They share the
    # epoch counter's private ownership model but remain a separately
    # versioned store so a Runtime never needs write access to its parent.
    DirectorySpec(
        "/var/lib/agentbox-waw/bindings-v1",
        "agentbox-runtime",
        "agentbox-runtime",
        0o700,
    ),
    DirectorySpec("/var/log/agentbox", "agentbox", "agentbox", 0o750),
    # setgid keeps socket group ownership stable; sticky prevents either IPC
    # peer from unlinking a socket owned by the other identity.
    DirectorySpec("/run/agentbox", "root", "agentbox-runtime-ipc", 0o3770, persistent=False),
    DirectorySpec("/srv/agentbox/projects", "agentbox-runtime", "agentbox-runtime", 0o700),
    DirectorySpec("/opt/agentbox", "root", "root", 0o755),
    DirectorySpec("/opt/agentbox/releases", "root", "root", 0o755),
    DirectorySpec("/home/agentbox-runtime", "agentbox-runtime", "agentbox-runtime", 0o700),
)


@dataclass(frozen=True)
class InstallLayout:
    root: Path = Path("/")

    def map(self, absolute_path: str | Path) -> Path:
        value = PurePosixPath(str(absolute_path))
        if not value.is_absolute() or ".." in value.parts:
            raise ValueError("installer paths must be absolute and normalized")
        relative = Path(*value.parts[1:])
        return self.root / relative

    @property
    def is_real_host(self) -> bool:
        return self.root.resolve() == Path("/")

    @property
    def current_link(self) -> Path:
        return self.map("/opt/agentbox/current")

    def release(self, version: str) -> Path:
        return self.map(f"/opt/agentbox/releases/{version}")

    @property
    def database(self) -> Path:
        return self.map("/var/lib/agentbox/agentbox.db")

    @property
    def backups(self) -> Path:
        return self.map("/var/lib/agentbox/backups")

    @property
    def receipt(self) -> Path:
        return self.map("/var/lib/agentbox/install-receipt.json")

    @property
    def journal(self) -> Path:
        return self.map("/var/lib/agentbox/install-journal.json")
