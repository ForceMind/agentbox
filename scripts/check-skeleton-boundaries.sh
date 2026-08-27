#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

dangerous_python='(shell[[:space:]]*=[[:space:]]*True|asyncio\.create_subprocess_shell[[:space:]]*\(|os\.(system|popen|spawn[a-z_]*)[[:space:]]*\(|(^|[^[:alnum:]_])exec[[:space:]]*\(|run_as_root[[:space:]]*\()'

if grep --recursive --line-number --extended-regexp --include='*.py' \
  "$dangerous_python" apps packages helper installer; then
  printf 'Forbidden execution primitive found in AgentBox Python source.\n' >&2
  exit 1
fi

os_exec_calls="$({
  grep --recursive --line-number --extended-regexp --include='*.py' \
    'os\.exec[a-z_]*[[:space:]]*\(' apps packages helper installer || true
})"
unexpected_os_exec_calls="$(printf '%s\n' "$os_exec_calls" | grep --invert-match --extended-regexp \
  '^apps/cli/src/agentbox_cli/main\.py:[0-9]+:        os\.execv\(tmux, \[tmux, "attach-session", "-t", f"=\{runtime_session\.session_name\}"\]\)$' || true)"
if [[ -n "$unexpected_os_exec_calls" ]]; then
  printf 'OS exec use escaped the approved local tmux attach boundary:\n%s\n' \
    "$unexpected_os_exec_calls" >&2
  exit 1
fi

process_calls="$({
  grep --recursive --line-number --include='*.py' \
    'subprocess' apps packages helper installer || true
})"
unexpected_process_calls="$(printf '%s\n' "$process_calls" | grep --invert-match --extended-regexp \
  '^(packages/agentbox-runtime/src/agentbox_runtime/process\.py:|helper/src/agentbox_helper/actions\.py:|installer/src/agentbox_installer/(build|dependencies|diagnostics|host)\.py:)' || true)"
if [[ -n "$unexpected_process_calls" ]]; then
  printf 'Subprocess use escaped the approved controlled-runner boundary:\n%s\n' \
    "$unexpected_process_calls" >&2
  exit 1
fi

runner_references="$({
  grep --recursive --line-number --include='*.py' \
    'ControlledProcessRunner' apps packages || true
})"
unexpected_runner_references="$(printf '%s\n' "$runner_references" | grep --invert-match \
  --extended-regexp '^packages/agentbox-runtime/src/agentbox_runtime/(process|codex|claude|tmux|git|github)\.py:' || true)"
if [[ -n "$unexpected_runner_references" ]]; then
  printf 'Controlled runner use escaped approved Runtime adapters:\n%s\n' \
    "$unexpected_runner_references" >&2
  exit 1
fi

git_tool_selectors="$({
  grep --recursive --line-number --extended-regexp --include='*.py' \
    'shutil\.which\("(git|gh)"' apps packages || true
})"
unexpected_git_tool_selectors="$(printf '%s\n' "$git_tool_selectors" | grep --invert-match \
  --extended-regexp '^packages/agentbox-runtime/src/agentbox_runtime/(git|github)\.py:' || true)"
if [[ -n "$unexpected_git_tool_selectors" ]]; then
  printf 'Git/GitHub executable selection escaped approved adapters:\n%s\n' \
    "$unexpected_git_tool_selectors" >&2
  exit 1
fi

route_lines="$({
  grep --recursive --line-number --extended-regexp --include='*.py' \
    '@(application|router)\.(get|post|put|patch|delete)\(' apps/api/src || true
})"
route_count="$(printf '%s\n' "$route_lines" | sed '/^$/d' | wc -l)"
if [[ "$route_count" -ne 33 ]]; then
  printf 'Unexpected Phase 8 API route count: %s\n' "$route_count" >&2
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
  '^(apps/api/src/agentbox_api/auth\.py:.*@router\.post\("/(login|logout|reauthenticate)"|apps/api/src/agentbox_api/codex\.py:.*@router\.post\("/(remote/start|remote/stop|pair-codes)"|apps/api/src/agentbox_api/claude\.py:.*@router\.post\("/sessions/\{project_id\}/(start|stop)"|apps/api/src/agentbox_api/projects\.py:.*@router\.post\()' || true)"
if [[ -n "$unexpected_mutations" ]]; then
  printf 'Unexpected Phase 7 mutation route found:\n%s\n' "$unexpected_mutations" >&2
  exit 1
fi

if grep --recursive --line-number --extended-regexp --include='*.py' \
  '(push[^\n]*(--force|-f)([^[:alnum:]]|$)|reset[[:space:]]+--hard|git[[:space:]]+clean|branch[[:space:]]+-D|push[[:space:]]+--delete)' \
  apps packages; then
  printf 'Forbidden destructive Git operation found.\n' >&2
  exit 1
fi

if grep --recursive --line-number --extended-regexp --include='*.py' \
  "(Base\\.metadata\\.create_all|allow_origins[[:space:]]*=[[:space:]]*\\[[[:space:]]*\"\\*\"|/(shell|exec|command|register)[\"'])" \
  apps packages; then
  printf 'Forbidden schema, CORS, shell, or anonymous registration boundary found.\n' >&2
  exit 1
fi

if grep --recursive --line-number --extended-regexp --include='*.py' \
  '(kill-server|pkill[[:space:]]+claude|/root/\.claude|~/\.claude)' \
  apps packages; then
  printf 'Forbidden Claude/tmux ownership or private-config primitive found.\n' >&2
  exit 1
fi

host_primitives="$({
  grep --recursive --line-number --extended-regexp --include='*.py' \
    '(useradd|groupadd|usermod|/etc/systemd/system|/usr/bin/systemctl|/usr/sbin/runuser)' \
    apps packages || true
})"
unexpected_host_primitives="$(printf '%s\n' "$host_primitives" | grep --invert-match \
  '^packages/agentbox-runtime/src/agentbox_runtime/codex\.py:[0-9]*:        if Path("/etc/systemd/system/codex\.service")\.exists():$' || true)"
if [[ -n "$unexpected_host_primitives" ]]; then
  printf '%s\n' "$unexpected_host_primitives"
  printf 'Privileged host primitive escaped Installer/Helper boundaries.\n' >&2
  exit 1
fi

if grep --recursive --line-number --extended-regexp --include='*.py' \
  'agentbox_(helper|installer)' apps/api apps/worker packages; then
  printf 'API, Worker, or shared packages imported a privileged implementation boundary.\n' >&2
  exit 1
fi

if grep --recursive --line-number --extended-regexp --include='*.py' \
  '((^|[^[:alnum:]_])(sudo|runuser|setuid|seteuid|setgid|setegid)[^[:alnum:]_]|/usr/(bin|sbin)/(sudo|su|runuser))' \
  apps packages helper; then
  printf 'Runtime, Web, Worker, or Helper contains a sudo/set-ID escalation primitive.\n' >&2
  exit 1
fi

helper_forbidden='("(shell|command|argv|executable|script|path|service|package|signal|pid)"[[:space:]]*:|request\.(get|\[)[^\n]*(shell|command|argv|executable|script|path|service|package|signal|pid))'
if grep --recursive --line-number --extended-regexp --include='*.py' \
  "$helper_forbidden" helper/src; then
  printf 'Privileged Helper protocol can represent a forbidden caller-controlled field.\n' >&2
  exit 1
fi

if grep --recursive --line-number --extended-regexp --include='*.py' \
  '(provider[._ -]*(add|edit|remove|use|test)|SecretManager|CodexProviderConfigAdapter)' \
  apps packages helper installer; then
  printf 'Phase 11 Provider or Secret Manager implementation was introduced early.\n' >&2
  exit 1
fi

printf 'Phase 8 source-boundary check passed.\n'
