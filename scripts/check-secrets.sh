#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

suspicious_paths="$({
  find . \
    -path './.git' -prune -o \
    -path './.venv' -prune -o \
    -path './node_modules' -prune -o \
    -path './apps/web/node_modules' -prune -o \
    -type f \( \
      -name '.env' -o \
      -name '.env.*' -o \
      -name 'id_rsa' -o \
      -name 'id_ed25519' -o \
      -name '*.pem' -o \
      -name '*.p12' -o \
      -name '*.pfx' \
    \) -print
} || true)"

if [[ -n "$suspicious_paths" ]]; then
  printf 'Suspicious secret-bearing filenames found:\n%s\n' "$suspicious_paths" >&2
  exit 1
fi

secret_pattern='(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{24,}|-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----|Bearer[[:space:]]+[A-Za-z0-9._~+/-]{24,})'

if rg --hidden --line-number --pcre2 \
  --glob '!.git/**' \
  --glob '!.venv/**' \
  --glob '!node_modules/**' \
  --glob '!apps/web/node_modules/**' \
  --glob '!scripts/check-secrets.sh' \
  "$secret_pattern" .; then
  printf 'Potential credential literal found. Review without printing any real secret.\n' >&2
  exit 1
fi

printf 'Repository secret-pattern check passed.\n'
