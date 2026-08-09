#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

dangerous_python='(shell[[:space:]]*=[[:space:]]*True|os\.system[[:space:]]*\(|subprocess\.(run|Popen|call|check_call|check_output)[[:space:]]*\(|(^|[^[:alnum:]_])exec[[:space:]]*\(|run_as_root[[:space:]]*\()'

if grep --recursive --line-number --extended-regexp --include='*.py' \
  "$dangerous_python" apps packages; then
  printf 'Forbidden execution primitive found in AgentBox Python source.\n' >&2
  exit 1
fi

process_calls="$({
  grep --recursive --line-number --include='*.py' \
    'subprocess' apps packages || true
})"
unexpected_process_calls="$(printf '%s\n' "$process_calls" | grep --invert-match \
  '^packages/agentbox-runtime/src/agentbox_runtime/process\.py:' || true)"
if [[ -n "$unexpected_process_calls" ]]; then
  printf 'Subprocess use escaped the approved controlled-runner boundary:\n%s\n' \
    "$unexpected_process_calls" >&2
  exit 1
fi

route_lines="$({
  grep --recursive --line-number --extended-regexp --include='*.py' \
    '@(application|router)\.(get|post|put|patch|delete)\(' apps/api/src || true
})"
route_count="$(printf '%s\n' "$route_lines" | sed '/^$/d' | wc -l)"
if [[ "$route_count" -ne 11 ]]; then
  printf 'Unexpected Phase 5 API route count: %s\n' "$route_count" >&2
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
  '^(apps/api/src/agentbox_api/auth\.py:.*@router\.post\("/(login|logout)"|apps/api/src/agentbox_api/codex\.py:.*@router\.post\("/(remote/start|remote/stop|pair-codes)")' || true)"
if [[ -n "$unexpected_mutations" ]]; then
  printf 'Unexpected Phase 5 mutation route found:\n%s\n' "$unexpected_mutations" >&2
  exit 1
fi

if grep --recursive --line-number --extended-regexp --include='*.py' \
  "(Base\\.metadata\\.create_all|allow_origins[[:space:]]*=[[:space:]]*\\[[[:space:]]*\"\\*\"|/(shell|exec|command|register)[\"'])" \
  apps packages; then
  printf 'Forbidden schema, CORS, shell, or anonymous registration boundary found.\n' >&2
  exit 1
fi

printf 'Phase 5 source-boundary check passed.\n'
