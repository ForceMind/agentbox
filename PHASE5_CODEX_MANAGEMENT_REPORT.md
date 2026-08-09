# Phase 5 Codex Management Report

Date: 2026-08-09
Status: implemented and locally verified in Draft PR #22; required GitHub CI pending

## Executive Summary

Phase 5 adds AgentBox's first real Runtime capability: capability-aware Codex
detection, public-CLI Remote start/stop, and an ephemeral Pair Code flow. The
Web/API process still cannot execute third-party commands. It sends one of four
parameter-free actions over a versioned Unix Domain Socket to a non-root Runtime
Executor, which owns a no-shell, bounded process runner and the Codex Adapter.

The Pair path is authenticated, Origin/Host and CSRF protected, recent-auth
gated, cooldown limited, no-store, metadata-only audited, memory-only in the
browser, and non-JSON/TTY-only in the CLI. Synthetic canary tests found no Pair
value in SQLite/WAL/SHM, Audit metadata, captured logs, E2E data/artifacts, or
Git diff. This is a control-plane integration foundation, not a claim that all
Codex versions or production deployment identities are validated.

Claude, tmux, Project Workspace, Git/GitHub business operations, the root
Privileged Helper, installer, systemd deployment, system-user creation, and
host network changes remain unimplemented.

## Branch / Commits / PR

- Repository: `ForceMind/agentbox`
- Branch: `phase/5-codex-management`
- Base: `f61f3f4c24f0ab48994b05e9c574385a5c9b795c`
- Commits: 6 Phase 5 commits, including this publication metadata update
- Draft PR: <https://github.com/ForceMind/agentbox/pull/22>
- Merge: not performed; human review is required

## Observed Codex Environment

The Phase 0 report remains the historical baseline. A Phase 5 read-only probe
on 2026-08-09 observed:

| Item | Safe observation |
|---|---|
| Installed | yes |
| Version | `0.147.0` |
| Selected entrypoint | `/root/.local/bin/codex` (diagnostic only) |
| Classification | standalone |
| npm/PATH conflict | not detected |
| Authentication | authenticated through detected public `login status` |
| Remote start/stop/Pair | supported by current public help |
| Native Remote status | unsupported |
| Remote state | unknown |
| Legacy exact unit | enabled, inactive; not modified |
| Resolved target ownership | unexpected current UID; warning retained |

No token, authentication content, private Codex path, or Pair Code was read or
recorded. These root-context observations do not transfer to the future
`agentbox-runtime` user.

## Adapter Architecture

`CodexAdapter` implements detection and typed operations. `CodexManager`
serializes mutations and owns Pair cooldown. `ControlledProcessRunner` is the
only production Python location permitted to reference subprocess execution.
`RuntimeExecutorServer` exposes exact Runtime Protocol V1 actions over UDS;
`UnixCodexRuntimeClient` is used by Web/API and mutating CLI commands.

The API routes do not import subprocess or accept executable, argv,
environment, cwd, PID, signal, or shell data. CLI status may use the same
Adapter directly only as a read-only fallback when the UDS is absent. CLI
start/stop/Pair never fall back.

## Process Runner

- `asyncio.create_subprocess_exec` with a literal argv tuple; no shell;
- resolved absolute regular executable, unsafe file/directory-mode rejection,
  and device/inode/mode/size/mtime revalidation before spawn;
- Runtime HOME as fixed cwd; missing/relative HOME fails closed;
- HOME/PATH/locale/TERM/necessary XDG allowlist; relative PATH entries and
  cloud/AgentBox/GitHub/OpenAI/Anthropic/loader variables excluded;
- stdin disabled, stdout/stderr separate, byte caps, exit status captured;
- 8-second help/version/status, 10-second npm, and 30-second action limits;
- process-group terminate/wait/kill cleanup targets only AgentBox-spawned work;
- sensitive output classification prevents Pair output logging.

The remaining executable replacement TOCTOU is between the final stat and the
kernel exec. No caller can select the executable, and Phase 8 must add the final
production PATH/allowed-root and ownership policy.

## Installation Detection

Selection uses `shutil.which` under the sanitized Runtime PATH, then enumerates
only PATH candidates and collapses aliases resolving to the same target.
`$HOME/.local/bin/codex` is a standalone hint. A bounded fixed npm JSON query
checks known public package names. Distinct PATH targets or simultaneous
standalone/npm evidence produce `conflict`; incomplete evidence stays
`unknown`. AgentBox never scans the host or removes a package.

## Capability Detection

Main and `remote-control` public help are parsed into independent
`supported`/`unsupported`/`unknown` values for Remote Control, start, stop,
Pair, and status. No version threshold enables a command. Missing, malformed,
timed-out, non-zero, and future help shapes degrade without trying a private or
legacy fallback.

## Authentication Status

Only a detected public `login status` command can produce authenticated or
unauthenticated. Otherwise the result is unknown. AgentBox never opens Codex
authentication/config files or infers login from successful version/help.
Explicit unauthenticated state blocks Pair; unknown remains visible as unknown.

## Remote Lifecycle

Start and stop require fresh supported capabilities and share a Runtime action
lock with Pair. Known state returns `already_running`/`already_stopped`.
Native public status is preferred. Without it, strict current-UID resolved-exe
and known-argv evidence may infer running; successful actions are retained only
as process-local observed state. Otherwise status is unknown.

Stop invokes only the public stop command. There is no `pkill`, discovered-PID
signal, `kill -9`, service adoption, or private lock/state-file dependency.

## Pair Security

- Web route: `POST /api/v1/codex/pair-codes`;
- authenticated Session, exact Origin/Host, CSRF, and 10-minute recent auth;
- 10-second default cooldown, constrained to 5–300 seconds;
- 4 KiB per-stream cap and 30-second timeout;
- exactly one conservative labelled-code parse; unexpected output fails closed;
- response contains only code, optional publicly reported expiry, and
  `display_once`; headers are no-store/no-cache;
- raw stdout/stderr never enters API error, log, Audit, database, Job, file, or
  persistent cache;
- Web state clears on Hide, navigation, or after 90 seconds; copy is explicit;
- CLI refuses JSON and redirected/non-TTY Pair output.

The Web visibility timer is not an expiry claim. The current CLI did not expose
a machine-readable expiry, so AgentBox reports no expiry.

## API

Implemented, authenticated, no-store endpoints:

- `GET /api/v1/codex/status`
- `POST /api/v1/codex/remote/start`
- `POST /api/v1/codex/remote/stop`
- `POST /api/v1/codex/pair-codes`

Mutations require the existing CSRF and Origin/Host controls. Pair additionally
requires recent authentication. Stable normalized errors replace stderr.

## CLI

- `agentbox codex status [--json]`
- `agentbox codex start`
- `agentbox codex stop`
- `agentbox codex pair`

Install/update commands remain designs and were not added. Pair prints one
warning and one code only to a TTY; JSON Pair output is refused.

## Web

The Codex page now renders real installed/version/type/authentication,
independent capability values, Remote state/confidence, diagnostics, and
state-aware Start/Stop/Refresh controls. Pair uses explicit confirmation,
one-time display, explicit clipboard copy, Hide, and automatic memory clearing.
No production fake status exists. Claude/Projects/Logs remain placeholders.

## Doctor

Authenticated Doctor adds only a safe Codex summary: installed state, version,
classification, Remote capability/state, and bounded finding codes. A Runtime
socket failure reports unknown rather than falsely reporting not installed.
Legacy `codex.service` is only an exact presence warning and is never changed.

## Tests

Actual local results after the final code changes:

- Ruff: PASS
- Black: PASS — the bwrap batch invocation again stopped without a result;
  the established one-file-per-process check covered every Python source file
  successfully.
- mypy strict: PASS
- pytest: PASS — 99 tests
- migration upgrade → downgrade → upgrade: PASS
- frontend ESLint: PASS
- frontend Prettier: PASS
- TypeScript strict: PASS
- Vitest: PASS — 19 tests
- Vite production build: PASS
- Playwright: PASS — 32 executions (16 logical scenarios × desktop/mobile)
- repository secret scan: PASS
- Phase 5 source/runtime boundary scan: PASS
- `git diff --check`: PASS

The host lacked Chromium `libgbm`, `libasound`, and `libwayland-server`; their
RPMs were downloaded without installation, extracted beneath `/tmp`, and used
only through a temporary `LD_LIBRARY_PATH`. No system package was installed.

## E2E

The harness uses a temporary migrated SQLite database, random credentials,
random loopback ports, and an explicitly injected fake Codex Runtime. It covers
status/refresh, start/stop CSRF, Pair confirmation/display/copy/navigation
clear, no-store, no Web Storage, unsupported/error behavior, and all Phase 4
auth/navigation scenarios in desktop and mobile Chromium. It scans temporary
database/WAL/SHM, Playwright artifacts/report, and Git diff for the random Pair
canary before cleanup.

## Real Host Validation

| Validation | Result |
|---|---|
| Adapter read-only detection | PASS |
| Public version/help/capabilities/auth | PASS |
| Real Pair parser/ephemeral channel | PASS; code not recorded |
| Real start | SKIPPED — Remote state unknown; preserve existing environment |
| Real stop | SKIPPED — AgentBox did not start a daemon and will not risk another session |

## Security Review

- Arbitrary shell: none; global boundary rejects `shell=True`, `os.system`,
  sync subprocess helpers, dynamic exec, and subprocess outside the Runner.
- PATH/executable: no Web/CLI path input; relative PATH removed; target and
  fingerprint validated; residual TOCTOU documented.
- Output: independent caps, timeout, strict parsers, raw stderr never returned.
- Pair leakage: canary absent from persistence, Audit, logs, artifacts, and Git
  diff; real code was reduced to PASS in memory only.
- Audit: requested/succeeded/failed events contain Runtime and normalized error
  code only; no body/output/secret.
- Browser: no Pair Web Storage, URL, title, automatic clipboard, analytics, or
  console logging.
- Wrong-process stop: only official stop; no discovered process signalling.
- Root: no root assertion, sudo, Helper, systemd mutation, auth copy, chown, or
  host directory creation.

## Dependencies

No new Python or frontend dependency was added. Phase 5 uses Python standard
library asyncio/subprocess/socket/stat/proc capabilities and the existing
React/API stack. A new `agentbox-runtime` console entry point exposes the
Runtime Executor lifecycle.

- `pip-audit --local`: PASS, no known vulnerability (local AgentBox package is
  not published and is skipped as expected).
- `pnpm audit --audit-level high`: PASS, no known vulnerability.

## CI

Local equivalents of the nine protected checks pass. Remote GitHub required CI:
PENDING until the branch and Draft PR are published.

## Deviations

- The accepted architecture remains intact: API/Worker are non-root, Runtime
  work belongs to a separate non-root Runtime Executor, and root Helper remains
  separate/unimplemented.
- Because the durable Job consumer is not implemented, Phase 5 start/stop/Pair
  are bounded direct UDS actions instead of Jobs. This is documented and must be
  revisited when Job execution is delivered.
- Development/real-host validation uses the current root-owned historical Codex
  context only. Product code contains no root assumption. No authentication or
  file ownership was migrated.

## Known Limitations

- Remote state is unknown on the assessed CLI because it has no native status
  and no strict matching process was found.
- Process-local observed state and Pair cooldown reset when Runtime restarts.
- Status probes are on demand and not persisted/cached in Phase 5.
- UDS production group ownership/systemd sandboxing and Runtime-user login are
  Phase 8 responsibilities.
- Installation classification is intentionally best-effort; unknown package
  names/layouts remain unknown.
- The executable stat-to-exec TOCTOU is reduced but not eliminated.
- CLI mutation auditing through the future local API service path is not yet
  available; Runtime socket access is currently protected by OS peer identity.
- General Codex log viewing, installation, update, repair, and legacy-unit
  cleanup are not implemented.

## Phase 6 Recommendation

After human review and merge of this Draft PR, Phase 6 should implement
project-scoped Claude Remote sessions through the same non-root Runtime
boundary and tmux, with public-capability detection and manual Workspace Trust
guidance. Phase 6 is not started by this report.
