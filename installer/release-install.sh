#!/usr/bin/env bash
set -euo pipefail
umask 077

release_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
wheelhouse="${release_dir}/wheelhouse"
bootstrap_pip="${release_dir}/bootstrap/pip-25.3-py3-none-any.whl"
bootstrap_pip_sha256="9655943313a94722b7774661c21049070f6bbb0a1516bf02f7c8d5d9201514cd"

if [[
  ! -f "${release_dir}/VERSION" || -L "${release_dir}/VERSION" ||
  ! -d "${wheelhouse}" || -L "${wheelhouse}" ||
  ! -f "${bootstrap_pip}" || -L "${bootstrap_pip}"
]]; then
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

observed_bootstrap_sha256="$("${bootstrap_python}" - "${bootstrap_pip}" <<'PY'
import hashlib
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
digest = hashlib.sha256()
with path.open("rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
)"
if [[ "${observed_bootstrap_sha256}" != "${bootstrap_pip_sha256}" ]]; then
  printf 'AgentBox bootstrap pip wheel checksum mismatch.\n' >&2
  exit 16
fi

bootstrap_parent="/tmp"
if [[ "${AGENTBOX_INSTALLER_TEST_MODE:-}" == "1" && -n "${TMPDIR:-}" ]]; then
  bootstrap_parent="${TMPDIR}"
fi
bootstrap_dir="$(mktemp -d "${bootstrap_parent}/agentbox-release-bootstrap.XXXXXX")"
cleanup() {
  rm -rf -- "${bootstrap_dir}"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
bootstrap_target="${bootstrap_dir}/site-packages"
mkdir -m 0700 "${bootstrap_target}"

PIP_CONFIG_FILE=/dev/null \
PIP_DISABLE_PIP_VERSION_CHECK=1 \
PIP_NO_INDEX=1 \
PIP_NO_INPUT=1 \
PYTHONNOUSERSITE=1 \
PYTHONPATH="${bootstrap_pip}" \
"${bootstrap_python}" -m pip install \
  --no-index \
  --no-input \
  --disable-pip-version-check \
  --find-links "${wheelhouse}" \
  --target "${bootstrap_target}" \
  "agentbox==${version}" >/dev/null

# The bootstrap target stays root-private; production release paths created by
# the inner Installer must use their explicitly managed modes, not this umask.
umask 022
PIP_CONFIG_FILE=/dev/null \
PYTHONNOUSERSITE=1 \
PYTHONPATH="${bootstrap_target}" \
"${bootstrap_python}" -m agentbox_installer.cli "$@"
