#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

dangerous_python='(shell[[:space:]]*=[[:space:]]*True|os\.system[[:space:]]*\(|subprocess\.(run|Popen|call|check_call|check_output)[[:space:]]*\(|(^|[^[:alnum:]_])exec[[:space:]]*\(|run_as_root[[:space:]]*\()'

if grep --recursive --line-number --extended-regexp --include='*.py' \
  "$dangerous_python" apps packages; then
  printf 'Forbidden execution primitive found in AgentBox Python source.\n' >&2
  exit 1
fi

route_lines="$({
  grep --recursive --line-number --extended-regexp --include='*.py' \
    '@(application|router)\.(get|post|put|patch|delete)\(' apps/api/src || true
})"
route_count="$(printf '%s\n' "$route_lines" | sed '/^$/d' | wc -l)"
if [[ "$route_count" -ne 7 ]]; then
  printf 'Unexpected Phase 4 API route count: %s\n' "$route_count" >&2
  exit 1
fi

dangerous_browser='(dangerouslySetInnerHTML|new[[:space:]]+Function[[:space:]]*\(|(^|[^[:alnum:]_])eval[[:space:]]*\(|localStorage\.setItem|sessionStorage\.setItem)'
if grep --recursive --line-number --extended-regexp --include='*.ts' --include='*.tsx' \
  --exclude='*.test.ts' --exclude='*.test.tsx' \
  "$dangerous_browser" apps/web/src; then
  printf 'Forbidden browser execution or credential-persistence primitive found.\n' >&2
  exit 1
fi

mutation_routes="$(printf '%s\n' "$route_lines" | grep --extended-regexp \
  '@(application|router)\.(post|put|patch|delete)\(' || true)"
unexpected_mutations="$(printf '%s\n' "$mutation_routes" | grep --invert-match --extended-regexp \
  '@router\.post\("/(login|logout)"' || true)"
if [[ -n "$unexpected_mutations" ]]; then
  printf 'Unexpected Phase 3 mutation route found:\n%s\n' "$unexpected_mutations" >&2
  exit 1
fi

if grep --recursive --line-number --extended-regexp --include='*.py' \
  "(Base\\.metadata\\.create_all|allow_origins[[:space:]]*=[[:space:]]*\\[[[:space:]]*\"\\*\"|/(shell|exec|command|register)[\"'])" \
  apps packages; then
  printf 'Forbidden schema, CORS, shell, or anonymous registration boundary found.\n' >&2
  exit 1
fi

printf 'Phase 4 source-boundary check passed.\n'
