# AgentBox CLI Design

Status: Phase 1 contract design with Phase 3 local administration and the
Phase 5 Codex command subset implemented.

Phase 3 implements `agentbox status`, `agentbox doctor`, `agentbox admin init`,
`agentbox admin status`, and `agentbox secret generate`. Phase 5 adds
`agentbox codex status/start/stop/pair` over the typed Runtime socket. Project,
Job, update, API-service UDS, and other third-party commands remain unimplemented.

## Role

`agentbox` is the bootstrap, diagnosis, recovery, scripting, and local-administration surface. It is not a hidden general shell. Web routes and CLI commands call the same Application Services and return the same stable error categories.

## Execution Modes

### Service Mode (Default)

CLI connects to `/run/agentbox/api.sock`, performs `/api/v1/meta` handshake, and uses the same API, Jobs, confirmations, Audit Events, and policy as Web. Local peer UID maps to an allowed local administrator principal.

### Local Read-Only Mode

When service is unavailable, only these may use the shared Application Services in a read-only execution context:

- `agentbox status --local`;
- `agentbox doctor --local` (bounded non-privileged subset);
- Runtime detect/version/capabilities/status where safe;
- project Git status for a registered/explicitly safe caller-accessible directory.

Local mode cannot mutate state, access Helper/Runtime sockets, generate Pair Codes, install/update, create/clone projects, or start/stop sessions. It labels output `execution_mode=local_read_only`.

## Global Options

| Option | Meaning |
|---|---|
| `--json` | stable machine-readable envelope; no ANSI/progress animation |
| `--dry-run` | produce plan/preconditions only; required support for privileged mutations |
| `--yes` | skip eligible low/medium-risk text prompt only; never bypass challenge/re-auth |
| `--wait` | wait for a Job to finish and map final state to exit code |
| `--timeout <duration>` | client wait timeout within server maximum; does not change action timeout |
| `--request-id <id>` | optional caller correlation ID with strict syntax |
| `--local` | explicitly use allowed read-only local mode |
| `--no-color` | disable ANSI in human output |
| `--version` | CLI version and API compatibility range |

Sensitive values are never accepted on argv because process lists/history can expose them. Passwords use TTY/stdin prompts with echo disabled. Pair Code is output-only.

## Command Tree

### General

```text
agentbox status
agentbox doctor
agentbox update
```

- `status`: compact component/Runtime/Job summary; read-only.
- `doctor`: creates Diagnostic Run Job in service mode; `--local` runs safe subset.
- `update`: shows plan by default; `--apply` (future flag within command contract) requires service, dry-run review, recent auth/confirmation where applicable.

### Phase 3 local administration

```text
agentbox admin init [--username <name>]
agentbox admin status
agentbox secret generate
```

- `admin init` requires a local TTY, prompts twice with echo disabled, refuses a
  second active administrator, and requires an explicit `alembic upgrade head`
  first. Password input is never accepted on argv.
- `admin status` is read-only and returns only initialized state and username.
- `secret generate` writes one CSPRNG value to stdout and never writes a file,
  environment variable, database row, or log. JSON mode is deliberately absent
  for this secret-returning command.
- Phase 3 `status` and `doctor` inspect only configuration validity, database
  reachability, migration currency, and administrator initialization.

### Codex

```text
agentbox codex status
agentbox codex install
agentbox codex start
agentbox codex stop
agentbox codex pair
agentbox codex update
```

- `status`: implemented synthesized adapter state; it uses `runtime.sock` when
  available and may fall back to the same adapter in local read-only mode. It
  never assumes native `remote-control status` exists.
- `install`/`update`: planned only; no Phase 5 code installs or changes Codex.
- `start`/`stop`: implemented as parameter-free bounded Runtime socket actions;
  they fail when the Runtime Executor is unavailable and never fall back to a
  local mutation.
- `pair`: implemented interactive secret action over the Runtime socket;
  capability is required and an explicitly unauthenticated Runtime is rejected.
  Unknown authentication is reported honestly and is not converted into a
  false authenticated claim.

`agentbox codex pair` writes the one-time code once to terminal stdout only
when stdout is a TTY and refuses redirected/non-TTY output. JSON mode is
explicitly forbidden for Pair; it does not emit metadata or `pair_code` JSON.
The code is never recoverable after display.

### Claude

```text
agentbox claude status
agentbox claude start <project>
agentbox claude stop <project>
agentbox claude attach <project>
agentbox claude list
```

- `<project>` is a registered name/ID resolved server-side, not a path.
- `start` and `stop` are Jobs against managed sessions only.
- `attach` prints a fixed local `tmux` attach instruction for `agentbox-runtime`; it does not expose a Web terminal or accept a command.
- `list` distinguishes managed, unmanaged/collision, stale, and unknown state.
- Workspace Trust unknown returns NeedsAttention and a concrete project-scoped manual instruction.

### Projects

```text
agentbox project create <name>
agentbox project clone <url>
agentbox project list
agentbox project status <name>
```

- `create` and `clone` are Jobs; storage path is server-generated.
- `clone` rejects credential-bearing/unsupported URLs; no interactive credential prompt.
- `status` shows project metadata and bounded Git branch/HEAD/dirty/remote summary.
- no MVP delete, move, commit, push, reset, hook, submodule, or arbitrary Git command.

### GitHub

```text
agentbox github status
```

Reports gh availability, version, protocol, and authenticated/unauthenticated/unknown status without account/token/config content. Login/setup are manual Runtime-user instructions in MVP; AgentBox does not accept a token.

## Human-Readable Output

Human output begins with outcome and affected resource, followed by evidence freshness, safe warnings, Job ID, and next action. Tables remain narrow for mobile/SSH terminals. Secrets never appear in progress spinners, debug logs, error context, or shell completion.

Example status shape:

```text
Codex: available (0.x; standalone hint)
Remote Control: supported; managed daemon stopped
Authentication: authenticated (method/details suppressed)
Warnings: existing unmanaged service conflict
```

Version numbers above are illustrative, not claimed current facts.

## JSON Output

Every command except interactive Pair secret display supports `--json`:

```json
{
  "schema_version": 1,
  "command": "codex.status",
  "request_id": "req_...",
  "execution_mode": "service",
  "ok": true,
  "data": {},
  "error": null
}
```

JSON uses stdout; warnings/progress use stderr only when they cannot corrupt JSON. With `--wait`, the final envelope is emitted once. Without `--wait`, Job commands emit the accepted Job resource.

## Exit Codes

| Code | Meaning |
|---:|---|
| 0 | success or Job accepted as requested |
| 2 | CLI usage/flag error |
| 10 | dependency/Runtime unavailable |
| 11 | capability unsupported |
| 12 | unauthenticated/session expired |
| 13 | forbidden/recent-auth/confirmation required |
| 14 | conflict or resource locked |
| 15 | validation/path/precondition failure |
| 16 | client or action timeout |
| 17 | Job/action failed |
| 18 | needs human attention/uncertain state |
| 19 | CLI/API/protocol version mismatch |
| 20 | partial/degraded read-only result |

If a Job is accepted without `--wait`, exit 0 means acceptance, not eventual success. JSON includes Job ID/status.

## Error Format

Human:

```text
ERROR [RUNTIME_UNSUPPORTED]: Codex pairing is not advertised by the selected installation.
Next: run agentbox codex status --json
Request: req_...
```

JSON uses the API error `code`, `category`, `message`, `retryable`, and bounded `details`. Raw stderr, secret values, environment, public IP, and authentication content are excluded.

## Non-Interactive Behavior

- If confirmation, password, Workspace Trust, third-party login, or Pair TTY is required and no TTY exists, fail with an actionable exit code; never hang.
- `--yes` is allowed only for operations explicitly marked eligible by the service and cannot approve project deletion, force push, reset, backup deletion, auth reset, uninstall, permission/unit replacement, or an unverified download.
- `--dry-run` makes no mutation and returns a plan digest/expiry.
- Environment variables cannot carry third-party tokens through AgentBox. A small allowlist may select socket/format/timeouts, never executable/working directory/action.
- stdin data is used only by an explicitly documented secure prompt and is never echoed/logged.

## Capability and Version Mismatch

CLI calls `/api/v1/meta` before service operations. API major or Helper/Runtime protocol mismatch returns exit 19. Compatible minor additions are negotiated through Capability fields; CLI must not expose a command as usable solely because its own version knows the name.

For a newer CLI talking to an older service, unsupported service operations remain unavailable. For an older CLI, the service preserves V1 fields and rejects unknown mutation shapes. There is no fallback to direct local mutation.

## Dangerous Operations

Most destructive Git/project operations are outside MVP. When introduced, CLI first displays a dry-run and obtains a server Confirmation Challenge bound to target/state. A user must type the required target phrase; `--yes` cannot bypass it. Force push remains disabled unless a future security ADR explicitly adds it.

## Shell Completion and Privacy

Completion lists static commands/options and non-sensitive project display names only when locally authorized. It never queries Pair Codes, tokens, remote URLs with userinfo, logs, or project files, and does not execute Runtime commands.
