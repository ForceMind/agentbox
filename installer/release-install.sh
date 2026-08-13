#!/usr/bin/env bash
set -euo pipefail
umask 077

release_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
wheelhouse="${release_dir}/wheelhouse"

if [[ ! -f "${release_dir}/VERSION" || ! -d "${wheelhouse}" ]]; then
  printf 'AgentBox release payload is incomplete.\n' >&2
  exit 16
fi

bootstrap_python="/usr/bin/python3"
if [[ -n "${AGENTBOX_RELEASE_BOOTSTRAP_PYTHON:-}" ]]; then
  if [[ "${AGENTBOX_INSTALLER_TEST_MODE:-}" != "1" ]]; then
    printf 'AgentBox bootstrap Python override is available only in explicit test mode.\n' >&2
    exit 18
  fi
  bootstrap_python="${AGENTBOX_RELEASE_BOOTSTRAP_PYTHON}"
fi
if [[ "${bootstrap_python}" != /* || ! -x "${bootstrap_python}" ]]; then
  printf 'AgentBox requires an executable absolute Python path.\n' >&2
  exit 18
fi

"${bootstrap_python}" -c '
import os
import platform
import re
import sys

override = os.environ.get("AGENTBOX_RELEASE_PLATFORM_TEST_OVERRIDE")
if override is not None:
    if os.environ.get("AGENTBOX_INSTALLER_TEST_MODE") != "1" or not re.fullmatch(
        r"[A-Za-z]+:[A-Za-z0-9_]+:3\.[0-9]+", override
    ):
        print("AgentBox release platform override is invalid.", file=sys.stderr)
        raise SystemExit(18)
    system, machine, version = override.split(":")
    major, minor = (int(item) for item in version.split("."))
else:
    system = platform.system()
    machine = platform.machine()
    major, minor = sys.version_info[:2]

if system != "Linux":
    print("This AgentBox artifact supports Linux only.", file=sys.stderr)
    raise SystemExit(18)
if machine != "x86_64":
    print("This AgentBox artifact supports x86_64 only.", file=sys.stderr)
    raise SystemExit(18)
if major != 3 or minor not in (11, 12, 13):
    print(
        f"This AgentBox artifact requires Python 3.11, 3.12, or 3.13; found {major}.{minor}.",
        file=sys.stderr,
    )
    raise SystemExit(18)
'

if [[ -n "${AGENTBOX_RELEASE_PLATFORM_CHECK_ONLY:-}" ]]; then
  if [[ "${AGENTBOX_INSTALLER_TEST_MODE:-}" != "1" ]]; then
    printf 'AgentBox platform-only mode is available only in explicit test mode.\n' >&2
    exit 18
  fi
  exit 0
fi

version="$(tr -d '\n' < "${release_dir}/VERSION")"
if [[ ! "${version}" =~ ^[0-9]+\.[0-9]+\.[0-9]+(rc[1-9][0-9]*)?$ ]]; then
  printf 'AgentBox release VERSION is invalid.\n' >&2
  exit 16
fi

bootstrap_dir="$(mktemp -d "${TMPDIR:-/tmp}/agentbox-release-bootstrap.XXXXXX")"
cleanup() {
  rm -rf -- "${bootstrap_dir}"
}
trap cleanup EXIT HUP INT TERM

"${bootstrap_python}" -m venv "${bootstrap_dir}/venv"
PIP_NO_INDEX=1 "${bootstrap_dir}/venv/bin/pip" install \
  --no-index \
  --disable-pip-version-check \
  --find-links "${wheelhouse}" \
  "agentbox==${version}" >/dev/null

"${bootstrap_dir}/venv/bin/agentbox-install" "$@"
