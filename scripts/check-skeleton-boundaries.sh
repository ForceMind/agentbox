#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

dangerous_python='(shell[[:space:]]*=[[:space:]]*True|os\.system[[:space:]]*\(|subprocess\.(run|Popen|call|check_call|check_output)[[:space:]]*\(|\bexec[[:space:]]*\(|run_as_root[[:space:]]*\()'

if rg --line-number --pcre2 --glob '*.py' "$dangerous_python" apps packages; then
  printf 'Forbidden execution primitive found in Phase 2 Python source.\n' >&2
  exit 1
fi

route_count="$(rg --count '@application\.(get|post|put|patch|delete)\(' apps/api/src || true)"
if [[ "$route_count" != *":2" ]]; then
  printf 'Unexpected Phase 2 API route count: %s\n' "$route_count" >&2
  exit 1
fi

if rg --line-number --pcre2 '@application\.(post|put|patch|delete)\(' apps/api/src; then
  printf 'Mutating API route found in Phase 2 skeleton.\n' >&2
  exit 1
fi

printf 'Phase 2 source-boundary check passed.\n'
