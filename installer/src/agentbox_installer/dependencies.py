"""Fixed production and Runtime dependency detection."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from agentbox_installer.layout import InstallLayout


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    required_for_core: bool
    required_for_runtime: bool
    installed: bool
    selected_path: str | None
    installation_policy: str


DEPENDENCY_PATHS: dict[str, tuple[str, ...]] = {
    "python": ("/usr/bin/python3",),
    "python_venv": (),
    "git": ("/usr/bin/git",),
    "tmux": ("/usr/bin/tmux",),
    "curl": ("/usr/bin/curl",),
    "bubblewrap": ("/usr/bin/bwrap",),
    "gh": (
        "/usr/bin/gh",
        "/usr/local/bin/gh",
        "/home/agentbox-runtime/.local/bin/gh",
    ),
    "node": ("/usr/bin/node", "/usr/local/bin/node"),
    "npm": ("/usr/bin/npm", "/usr/local/bin/npm"),
    "pnpm": ("/usr/bin/pnpm", "/usr/local/bin/pnpm"),
    "sqlite": ("/usr/bin/sqlite3",),
    "systemd": ("/usr/bin/systemctl",),
    "codex": (
        "/usr/bin/codex",
        "/usr/local/bin/codex",
        "/home/agentbox-runtime/.local/bin/codex",
    ),
    "claude": (
        "/usr/bin/claude",
        "/usr/local/bin/claude",
        "/home/agentbox-runtime/.local/bin/claude",
    ),
}

REQUIRED_BASE = frozenset(
    {
        "python",
        "python_venv",
        "git",
        "curl",
        "sqlite",
        "systemd",
    }
)

OPTIONAL_RUNTIME = frozenset({"tmux", "bubblewrap", "gh", "node", "npm", "pnpm", "codex", "claude"})


def detect_dependencies(layout: InstallLayout) -> tuple[DependencyStatus, ...]:
    result: list[DependencyStatus] = []
    for name, candidates in DEPENDENCY_PATHS.items():
        selected = (
            "/usr/bin/python3 -m venv"
            if name == "python_venv" and _python_venv_available(layout)
            else next(
                (candidate for candidate in candidates if _safe_executable(layout, candidate)),
                None,
            )
        )
        if name in REQUIRED_BASE:
            policy = "fixed distro package mapping"
        elif name in {"codex", "claude", "gh"}:
            policy = "detect only; install explicitly from current official distribution guidance"
        else:
            policy = "optional; production Web uses prebuilt static assets"
        result.append(
            DependencyStatus(
                name=name,
                required_for_core=name in REQUIRED_BASE,
                required_for_runtime=name in OPTIONAL_RUNTIME or name == "git",
                installed=selected is not None,
                selected_path=selected,
                installation_policy=policy,
            )
        )
    return tuple(result)


def _python_venv_available(layout: InstallLayout) -> bool:
    executable = layout.map("/usr/bin/python3")
    if not layout.is_real_host:
        return layout.map("/usr/lib/agentbox-fixtures/python-venv").is_file()
    if not _safe_executable(layout, "/usr/bin/python3"):
        return False
    try:
        result = subprocess.run(  # noqa: S603 - fixed read-only module capability check
            (str(executable), "-c", "import ensurepip, venv"),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _safe_executable(layout: InstallLayout, candidate: str) -> bool:
    mapped = layout.map(candidate)
    if not mapped.is_file() or not os.access(mapped, os.X_OK):
        return False
    try:
        resolved = mapped.resolve(strict=True)
    except OSError:
        return False
    approved = (
        layout.map("/usr/bin").resolve(strict=False),
        layout.map("/usr/local/bin").resolve(strict=False),
        layout.map("/home/agentbox-runtime/.local/bin").resolve(strict=False),
    )
    return any(resolved.is_relative_to(root) for root in approved)
