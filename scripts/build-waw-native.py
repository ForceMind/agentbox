#!/usr/bin/env python3
"""Build the fixed WAW C17 helpers with the platform-appropriate gate."""

from __future__ import annotations

import argparse
import os
import platform
import shlex
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "native" / "waw" / "src"
INCLUDE = ROOT / "native" / "waw" / "include"
PROGRAMS = {
    "agentbox-waw-pane-bootstrap": SOURCE / "pane_bootstrap.c",
    "agentbox-waw-bridge": SOURCE / "bridge.c",
    "agentbox-waw-attach-supervisor": SOURCE / "attach_supervisor.c",
}


def command_for(
    compiler: str, source: Path, output: Path, *, linux: bool, sanitizers: bool
) -> list[str]:
    command = [
        compiler,
        "-std=c17",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-Wpedantic",
        "-Wconversion",
        "-Wsign-conversion",
        "-Wformat=2",
        "-Wshadow",
        "-Wstrict-prototypes",
        "-Wmissing-prototypes",
        "-Wwrite-strings",
        "-Wundef",
        "-fPIE",
        "-fstack-protector-strong",
        f"-I{INCLUDE}",
        f"-I{SOURCE}",
    ]
    if linux:
        command.extend(["-D_FORTIFY_SOURCE=3"])
    else:
        command.extend(["-DAGENTBOX_WAW_PORTABLE_CHECK=1"])
    if sanitizers:
        command.extend(
            [
                "-fsanitize=address,undefined",
                "-fno-sanitize=leak",
                "-fno-omit-frame-pointer",
                "-DAGENTBOX_WAW_SANITIZED=1",
            ]
        )
    command.extend([str(source), str(SOURCE / "waw_native.c"), str(SOURCE / "waw_isolation.c")])
    if linux:
        command.extend(
            [
                "-Wl,-pie",
                "-Wl,-z,relro",
                "-Wl,-z,now",
                "-Wl,-z,noexecstack",
            ]
        )
    command.extend(["-o", str(output)])
    return command


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "native" / "waw")
    parser.add_argument("--cc", default=os.environ.get("CC", "cc"))
    parser.add_argument("--portable", action="store_true")
    parser.add_argument("--sanitizers", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    arguments = parser.parse_args()

    compiler = shutil.which(arguments.cc)
    if compiler is None:
        parser.error(f"C compiler not found: {arguments.cc}")
    linux = platform.system() == "Linux" and not arguments.portable
    if arguments.sanitizers and not linux:
        parser.error("sanitizers are only admitted by the Linux native gate")
    arguments.output.mkdir(parents=True, exist_ok=True)
    for name, source in PROGRAMS.items():
        output = arguments.output / name
        command = command_for(
            compiler, source, output, linux=linux, sanitizers=arguments.sanitizers
        )
        if arguments.verbose:
            print(shlex.join(command))
        subprocess.run(command, cwd=ROOT, check=True)
    mode = "linux-hardened" if linux else "portable-source"
    print(f"built {len(PROGRAMS)} WAW native helpers ({mode}) in {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
