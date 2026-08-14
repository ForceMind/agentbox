#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 \
  && "${1:-}" != "build-artifact" \
  && "${1:-}" != "build-release-candidate" \
  && "${1:-}" != "verify-artifact" \
  && "${1:-}" != "verify-version" \
  && "${1:-}" != "plan" ]]; then
  printf 'AgentBox apply/update/rollback requires root.\n' >&2
  exit 13
fi

installer_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "${installer_dir}/.." && pwd)"
export PYTHONPATH="${repo_dir}/installer/src${PYTHONPATH:+:${PYTHONPATH}}"
exec /usr/bin/python3 -m agentbox_installer.cli "$@"
