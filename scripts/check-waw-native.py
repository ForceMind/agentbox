#!/usr/bin/env python3
"""Source, C17, wire-header, and Linux hardening checks for WAW helpers."""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "native" / "waw" / "src"
INCLUDE = ROOT / "native" / "waw" / "include"
BUILD = ROOT / "scripts" / "build-waw-native.py"
PROGRAMS = (
    "agentbox-waw-pane-bootstrap",
    "agentbox-waw-bridge",
    "agentbox-waw-attach-supervisor",
)
FORBIDDEN_SOURCE = (
    r"\bsystem\s*\(",
    r"\bpopen\s*\(",
    r"\bexeclp\s*\(",
    r"\bexecvp\s*\(",
    r"\bexecvpe\s*\(",
    r"\bposix_spawnp\s*\(",
    r"/bin/(?:ba|z|c|fi)?sh\b",
    r"\bsh\s+-c\b",
)


def check_sources() -> None:
    sources = sorted(SOURCE.glob("*.c")) + sorted(SOURCE.glob("*.h"))
    if {path.name for path in sources} != {
        "attach_supervisor.c",
        "bridge.c",
        "pane_bootstrap.c",
        "waw_isolation.c",
        "waw_isolation.h",
        "waw_native.c",
        "waw_native.h",
    }:
        raise RuntimeError("native WAW source inventory is not exact")
    combined = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    for pattern in FORBIDDEN_SOURCE:
        if re.search(pattern, combined, flags=re.IGNORECASE):
            raise RuntimeError(f"forbidden command primitive in native WAW source: {pattern}")
    if combined.count("agentbox_waw_exec_held(") < 4:
        raise RuntimeError("held-descriptor execution is missing")
    if "AT_EMPTY_PATH" not in combined or "execveat" not in combined:
        raise RuntimeError("execveat held-descriptor gate is missing")
    if "PR_SET_NO_NEW_PRIVS" not in combined or "TIOCSCTTY" not in combined:
        raise RuntimeError("native process hardening or controlling PTY gate is missing")
    if "AGENTBOX_WBR_FRAME_BYTES" not in combined or "TIOCSWINSZ" not in combined:
        raise RuntimeError("WBR resize gate is missing")
    for required in (
        "CLONE_NEWUSER",
        "CLONE_NEWNS",
        "CLONE_NEWPID",
        "CLONE_NEWIPC",
        "LANDLOCK_RULE_PATH_BENEATH",
        "SECCOMP_MODE_FILTER",
        "SYS_close_range",
    ):
        if required not in combined:
            raise RuntimeError(f"native isolation gate is missing: {required}")


def check_header(compiler: str, directory: Path) -> None:
    probe = directory / "header-probe.c"
    binary = directory / "header-probe"
    probe.write_text(
        """
#include "agentbox_waw_protocol.h"
_Static_assert(AGENTBOX_WAW_FD_COUNT == 7, "fd count");
_Static_assert(AGENTBOX_WAW_FD_ROLE_BITMAP == 0x7f, "fd bitmap");
_Static_assert(AGENTBOX_WBR_FRAME_BYTES == 64, "wbr bytes");
_Static_assert(AGENTBOX_WBR_OFFSET_RESERVED + AGENTBOX_WBR_RESERVED_BYTES == 64,
               "wbr layout");
_Static_assert(AGENTBOX_WAW_RELAY_BUFFER_BYTES == 65536, "relay bound");
_Static_assert(AGENTBOX_WAW_READY_FRAME_BYTES == 8, "ready bytes");
_Static_assert(AGENTBOX_WAW_READY_OFFSET_RESERVED + AGENTBOX_WAW_READY_RESERVED_BYTES == 8,
               "ready layout");
_Static_assert(AGENTBOX_WAW_ATTACH_READY_FD == 6, "attach ready fd");
_Static_assert(AGENTBOX_WAW_LAUNCHER_CGROUP_FD == 3 &&
               AGENTBOX_WAW_LAUNCHER_READY_FD == 6, "launcher fd map");
_Static_assert(AGENTBOX_WAW_INNER_UID == 1000 && AGENTBOX_WAW_INNER_GID == 1000,
               "inner identity");
int main(void) { return 0; }
""".lstrip(),
        encoding="utf-8",
    )
    subprocess.run(
        [
            compiler,
            "-std=c17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wpedantic",
            f"-I{INCLUDE}",
            str(probe),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True)


def readelf(binary: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["readelf", *arguments, str(binary)],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def check_linux_binary(binary: Path) -> None:
    header = readelf(binary, "-h")
    program = readelf(binary, "-W", "-l")
    dynamic = readelf(binary, "-W", "-d")
    symbols = readelf(binary, "-W", "-s")
    if "Type:                              DYN" not in header:
        raise RuntimeError(f"{binary.name} is not PIE")
    if "GNU_RELRO" not in program or "BIND_NOW" not in dynamic:
        raise RuntimeError(f"{binary.name} is missing RELRO/NOW")
    stack_lines = [line for line in program.splitlines() if "GNU_STACK" in line]
    if len(stack_lines) != 1 or re.search(r"\bRWE\b", stack_lines[0]):
        raise RuntimeError(f"{binary.name} has an executable or ambiguous stack")
    if "__stack_chk_fail" not in symbols:
        raise RuntimeError(f"{binary.name} is missing stack-protector evidence")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary-dir", type=Path)
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--portable-only", action="store_true")
    parser.add_argument("--cc", default=os.environ.get("CC", "cc"))
    arguments = parser.parse_args()
    compiler = shutil.which(arguments.cc)
    if compiler is None:
        parser.error(f"C compiler not found: {arguments.cc}")

    check_sources()
    with tempfile.TemporaryDirectory(prefix="agentbox-waw-native-") as temporary:
        temp = Path(temporary)
        check_header(compiler, temp)
        binary_dir = arguments.binary_dir or temp / "bin"
        if not arguments.no_build:
            command = [sys.executable, str(BUILD), "--output", str(binary_dir), "--cc", compiler]
            if arguments.portable_only:
                command.append("--portable")
            subprocess.run(command, cwd=ROOT, check=True)
        for name in PROGRAMS:
            binary = binary_dir / name
            if not binary.is_file():
                raise RuntimeError(f"missing native helper: {binary}")
            version = subprocess.run(
                [str(binary), "--version"], check=True, capture_output=True, text=True
            ).stdout
            if version != f"{name} 1\n":
                raise RuntimeError(f"unexpected version output from {name}")
            rejected = subprocess.run(
                [str(binary), "--command", "id"], capture_output=True, check=False
            )
            if rejected.returncode == 0 or rejected.stdout or rejected.stderr:
                raise RuntimeError(f"{name} exposed an unexpected command surface")
            if platform.system() == "Linux" and not arguments.portable_only:
                check_linux_binary(binary)
    gate = "portable" if platform.system() != "Linux" or arguments.portable_only else "linux"
    print(f"WAW native {gate} gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
