#!/usr/bin/env bash
set -euo pipefail

release_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
wheelhouse="${release_dir}/wheelhouse"

if [[ ! -f "${release_dir}/VERSION" || ! -d "${wheelhouse}" ]]; then
  printf 'AgentBox release payload is incomplete.\n' >&2
  exit 16
fi

bootstrap_dir="$(mktemp -d)"
cleanup() {
  rm -rf -- "${bootstrap_dir}"
}
trap cleanup EXIT HUP INT TERM

/usr/bin/python3 -m venv "${bootstrap_dir}/venv"
"${bootstrap_dir}/venv/bin/pip" install \
  --no-index \
  --disable-pip-version-check \
  --find-links "${wheelhouse}" \
  "agentbox==$(tr -d '\n' < "${release_dir}/VERSION")" >/dev/null

"${bootstrap_dir}/venv/bin/agentbox-install" "$@"
