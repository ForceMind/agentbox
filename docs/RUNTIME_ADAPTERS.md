# AgentBox Runtime Adapter Design

Status: Phase 1 design baseline with the Phase 5 Codex subset implemented

## Purpose

Runtime Adapters isolate AgentBox from changing third-party CLIs. Business services ask for capabilities and typed operations; they do not build commands, read private auth files, or reference managed internal installation layouts.

## Core Interface

Conceptual asynchronous interface:

```text
RuntimeAdapter
├── detect(context) -> RuntimeDetection
├── version(installation) -> VersionObservation
├── capabilities(installation) -> CapabilitySet
├── authentication_status(installation) -> AuthObservation
├── health(installation) -> HealthObservation
├── install_plan(platform, desired) -> RuntimePlan
├── update_plan(installation, desired) -> RuntimePlan
└── diagnostics(installation, level) -> DiagnosticFindings
```

Runtime-specific extensions:

```text
CodexAdapter
├── start_remote(installation)
├── stop_remote(installation)
├── generate_pair_code(installation)
└── remote_health(installation)

ClaudeAdapter
├── inspect_public_capabilities()
├── authentication_status()
└── selected_executable()

ClaudeSessionManager + TmuxAdapter
├── start_session(project_id)
├── stop_session(project_id)
├── list_sessions()
├── recent_output(project_id, fixed_limits)
├── attach_command(project_id)
└── workspace_state(project_id)
```

Future Provider management does not become another Remote lifecycle method on
these interfaces. It uses a runtime-neutral Provider domain plus typed
Runtime-specific adapters:

```text
ProviderManager
├── ProviderDefinition registry and Active Provider use cases
├── RuntimeBindingID intent (not a permanent Runtime provider ID)
├── SecretReference (never the secret value)
└── layered compatibility observations

RuntimeContinuityManager
├── preflight_public_writer_state()
├── assess_remote_recovery()
├── assess_thread_resume()
├── assess_context_continuity()
├── assess_thread_discovery()
└── recovery_guidance()

ProviderConfigAdapter
├── inspect_public_contract(runtime)
├── map_runtime_binding(binding_id, provider_definition)
├── generate_and_validate_candidate(expected_revision)
└── apply_via_config_transaction(plan)

ConfigTransactionManager
├── snapshot_content_existence_mode_lifecycle()
├── detect_concurrent_modification()
├── write_validate_fsync_replace()
├── rollback_full_scope()
└── verify_rollback()
```

Interfaces return typed observations with source, timestamp, confidence, raw-exit classification, and bounded sanitized evidence. They do not return raw stdout/stderr to callers.

## Capability Model

Each capability is independently classified:

| State | Meaning | Example response |
|---|---|---|
| `supported` | public CLI evidence confirms operation | Codex help lists `remote-control pair` |
| `unsupported` | installation is valid but feature is absent | Codex help has no `remote-control status` |
| `unavailable` | required executable/service/dependency is absent or inaccessible | `claude` not on allowed PATH |
| `unauthenticated` | public status says login is required | supported Runtime, no account login |
| `broken` | expected command exists but fails or is internally inconsistent | version works, help crashes |
| `unknown` | safe stable evidence is insufficient | Claude Workspace Trust without public API |

`unsupported` is not an error to repair blindly. `unknown` never becomes `supported` because a private file exists.

Capabilities include evidence version and detection age so API/Worker can require refresh before mutation.

## Detection Pipeline

1. accept an optional administrator-configured stable entrypoint subject to allowed-root policy;
2. inspect `command -v` under the Runtime user's fixed environment;
3. enumerate unique PATH candidates and resolve symlinks/realpaths;
4. verify regular executable, owner/mode, allowed filesystem root, package/source hints, and replacement fingerprint;
5. run bounded public `--version` and `--help` commands;
6. inspect active package manager/npm metadata for source/conflict hints;
7. derive capabilities from parsed help fixtures and safe command probes;
8. collect process/unit/session evidence without exposing full args/environments;
9. persist only typed observations and sanitized evidence.

An adapter reports multiple installations/conflicts rather than selecting the newest by guess. The administrator may choose a preferred installation; execution revalidates it.

## Executable and Environment Policy

- No business layer uses `/root/.codex/packages/...` or Claude private package internals as an invocation contract.
- The configured/PATH entrypoint is stored, with observed realpath for drift detection only.
- Allowed roots and ownership policy are installation-source specific.
- Execution uses argv arrays, no shell, fixed minimal environment, Runtime HOME, explicit working directory, timeout, output cap, and process-group cancellation.
- Locale is fixed for parsing where supported; machine-readable public output is preferred.
- Unknown exit/output fails closed and becomes Broken/Unknown, not a best-guess success.

## Codex Adapter

Phase 5 implements `CodexAdapter`, `CodexManager`, `ControlledProcessRunner`,
and the V1 Unix-socket client/server. The server accepts exactly
`codex.status`, `codex.remote.start`, `codex.remote.stop`, and `codex.pair` with
no caller parameters. It is the non-root Runtime Executor, not the root
Privileged Helper. Production identity, group ownership, and systemd activation
remain Phase 8 deployment work; development uses the current unprivileged
context and `.agentbox-dev/runtime.sock`.

### Public CLI Evidence

The Phase 0 host has standalone Codex 0.146.1 at `/root/.local/bin/codex`. Its public help confirmed:

- `codex remote-control start`;
- `codex remote-control stop`;
- `codex remote-control pair`;
- no `codex remote-control status`;
- `codex login status` succeeded for root.

These are observations, not permanent guarantees. Managed AgentBox operation will use the separate Runtime user and re-detect capabilities/authentication there.

### Installation Conflict Detection

Codex detection records:

- every unique PATH executable and realpath;
- version/help fingerprint;
- standalone-layout hint;
- active npm prefix and `@openai/codex` presence;
- package manager ownership where available;
- duplicate PATH aliases versus truly different binaries;
- owner/mode anomalies.

If npm and standalone candidates differ, status is Conflict until an administrator selects one. AgentBox never uninstalls a candidate automatically.

### Remote Lifecycle

- `start_remote` and `stop_remote` exist only when the exact help fixture confirms them.
- `remote_health` combines AgentBox-managed unit/session state, process identity, bounded liveness, last start/stop Job, and adapter evidence.
- Absence of a native status subcommand reduces confidence but is not Broken.
- Existing units/processes not created by AgentBox remain unmanaged and cannot be stopped/adopted without a future explicit workflow.

### Pairing

`generate_pair_code` is available only when Pair capability is supported and
authentication is not explicitly reported unauthenticated. If public auth
evidence is absent, authentication remains `unknown`; the UI does not claim a
login. The runner classifies Pair stdout/stderr as sensitive, caps each stream
at 4 KiB, validates exactly one labelled code with a conservative parser, and
maps unknown output to `CODEX_PAIR_OUTPUT_UNRECOGNIZED` without embedding raw
bytes. `CodexManager` serializes actions and applies a 10-second default,
5–300-second bounded in-process cooldown. No hash, suffix, raw output, or expiry
guess is persisted.

### Login Status

Use a documented public login-status command when detected. If absent, return Unknown with manual instruction. Never infer login by opening auth files or checking a token variable.

### Install and Update

The adapter produces a plan from supported publisher methods. The root Helper handles verified system/install steps. Internal standalone release directories may appear as diagnostic evidence but cannot be hardcoded. Post-install verification includes owner/mode checks due the UID/GID 1001 anomaly observed in Phase 0.

### Future Codex Provider Config and Continuity Adapters

Phase 11 may add `CodexProviderConfigAdapter`; it is not implemented in Phase
5. It must derive its accepted keys and validation behavior from the public
Codex CLI help, public config schema/documentation, and supported config keys
observed at implementation time. Current observed shapes are fixtures, not a
permanent protocol, and private Codex internal files are forbidden contracts.

The adapter accepts a ProviderDefinition, AgentBox RuntimeBinding intent, and a
Secret reference, never raw TOML, arbitrary keys, paths, environment maps,
current Codex IDs, or API keys. It parses the existing TOML, preserves unrelated
values, edits only AgentBox-controlled blocks, prevents duplicates, validates a
complete candidate, detects concurrent modification, protects against
symlinks/unsafe ownership, and delegates restrictive write/fsync/atomic replace
and full-scope verified rollback to `ConfigTransactionManager`. It prefers an
official Secret-reference mechanism over plaintext credentials where the
current public contract supports one.

Historical separation of Provider and session-provider identities is a
continuity strategy, not a Codex contract. Implementation must revalidate the
latest public config/session identity, reload/restart, active-writer, resume,
thread discovery, and Remote behavior. Direct mutation of Codex SQLite/session
DB, JSONL, rollout, or thread metadata is prohibited.

Provider types are adapter capabilities, not one shared parameter bag:
Official OpenAI, OpenAI-compatible HTTP, local, and Runtime-native/built-in are
initial design directions. Claude or another Runtime receives an adapter only
when its official public contract supports the operation.

### Future Provider Test and Compatibility

Provider testing is layered: typed config; DNS/TCP/TLS/endpoint; authentication;
model and Provider protocol; the then-current Runtime wire API; minimal Runtime
request; Remote recovery; and thread resume/context/discovery continuity.
Results independently expose Network, Authentication, Model Availability, Wire
Protocol, Provider API, Runtime, Remote, Thread Resume, Context Continuity, and
Thread Discovery as PASS/FAIL/UNSUPPORTED/EXPERIMENTAL/UNKNOWN/NOT_TESTED.

Planned aggregate classifications are `supported`, `compatible`,
`experimental`, `degraded`, `incompatible`, and `unknown`, backed by the full
matrix. Continuity levels 0–5 are monotonic evidence labels, not inferred
promises. Provider request success never promotes Remote, thread, context, or
discovery compatibility. Official Provider full inference is not run by default;
paid Runtime/continuity tests require explicit opt-in.

The dedicated harness uses two local fake compatible providers A/B, starts a
known-context test thread on A, waits for writer quiescence, switches through the
real transaction boundary, resumes through a public interface when supported,
and independently verifies context delivery, identity, discovery, and expected
artifacts. It never edits private session storage.

## Claude Adapter

Phase 6 implements `ClaudeAdapter`, `TmuxAdapter`, `ProjectRegistry`, and
`ClaudeSessionManager` behind the UDS Runtime Executor. No Claude/tmux
subprocess exists in API routes.

### Public CLI Evidence

Phase 0 found Claude Code 2.1.223 as a global npm package, but observed versions
are not capability contracts. Phase 6 parses public `--help`,
`remote-control --help`, and `--version`; a public auth status is called only if
advertised. Missing or changed evidence degrades to Unknown/Unsupported.

### Session Lifecycle

- production managed sessions are designed for `agentbox-runtime`; Phase 6 development does not migrate identities;
- a minimal registry resolves only configured-root immediate-child real directories;
- tmux names use a bounded ASCII slug/hash and atomically injected exact project-derived session-environment marker;
- create validates canonical path/symlink/access, installation, public capability, and exact collision;
- a fixed fingerprinted `sleep` placeholder lets tmux set `remain-on-exit` before a fixed multi-argument `respawn-pane` directly execs the fingerprinted Claude argv; current public tmux help documents no `sh -c` for this form;
- tmux owns the long-running interactive child; if detached `remote-control` exits on a Trust prompt, one fixed direct `claude --` respawn prepares a live manual-confirmation pane without sending input;
- stop/capture require exact name plus marker; similar, legacy, unmarked, or colliding sessions remain unmanaged;
- restart rediscovers through registry/name/marker/pane evidence rather than process memory;
- attach returns a fixed local command; the Web never creates a PTY.

### Workspace Trust

Workspace Trust is `unknown`, `requires_user_confirmation`, or the limited
`initialized_by_agentbox` launch hint. Private configuration inspection is
forbidden. Trust prompts produce `needs_interaction` plus attach guidance;
AgentBox never sends `yes`, key presses, or undocumented trust flags.

### Authentication

Use `claude auth status` only when public help advertises it, with bounded
parsing. Missing/changed output is Unknown. `--version` is not login evidence;
root Phase 0 login does not transfer to the Runtime user.

### Recent Output

The adapter calls capture only for an exact marked session, caps to 200 lines/
24 KiB under the runner cap, strips ANSI CSI/OSC and controls, and returns an
explicit no-store response. This is sanitation, not complete secret redaction.
Pane text never enters RuntimeSession, Job, Audit, log, DB, report, or browser
storage.

## Stable, Best-Effort, and Forbidden Evidence

| Evidence | Policy |
|---|---|
| documented/public `--version`, `--help`, status subcommand | preferred stable evidence, still versioned/tested |
| executable resolution and filesystem metadata | stable platform evidence; revalidate before execution |
| AgentBox-created unit/tmux/Job records | authoritative only for managed resources |
| process names/limited argument markers | best-effort supporting evidence, never sole ownership proof |
| package/npm database | best-effort installation-source evidence |
| private Runtime config/auth layout | forbidden as required contract; content not read for auth |
| public Runtime provider/config schema and documented supported keys | required future Provider config contract; revalidated per supported release |
| raw API key or Secret Manager value | forbidden adapter observation/output; only an opaque Secret reference crosses the application boundary |
| public Runtime provider/session identity and resume behavior | future RuntimeBinding mapping and continuity evidence; always version-revalidated |
| private SQLite/session DB, JSONL, rollout, thread metadata | permanently forbidden Provider migration/config interface |
| internal standalone managed path | diagnostic hint only; never invocation/business contract |
| parsing human output | best effort with exact fixtures; unknown output fails closed |

## Error Normalization

Adapters map results to stable codes:

- `RUNTIME_UNSUPPORTED`
- `RUNTIME_UNAVAILABLE`
- `RUNTIME_UNAUTHENTICATED`
- `RUNTIME_BROKEN`
- `CAPABILITY_UNKNOWN`
- `INSTALLATION_CONFLICT`
- `EXECUTABLE_CHANGED`
- `WORKSPACE_TRUST_REQUIRED`
- `SESSION_CONFLICT`
- `COMMAND_TIMEOUT`
- `OUTPUT_LIMIT_EXCEEDED`
- `UNEXPECTED_OUTPUT`
- `PERMISSION_MISMATCH`

Error summaries contain safe remediation and evidence timestamps, not raw sensitive output.

## Version Change and Degradation

At detection time, the adapter selects a parser/fixture family by semantic version range plus help fingerprint. Unknown versions may still expose read-only version/help data, but mutations remain Unsupported/NeedsAttention until compatible capabilities are proven. There is no “try old command and hope” fallback.

Runtime observation caching has a short TTL; start/stop/pair/session mutations force fresh executable/capability/auth checks. A binary fingerprint change invalidates pending plans and Confirmation Challenges.

## Test Doubles and Fixtures

- sanitized stdout/stderr/exit fixtures for every supported version/capability combination;
- fixtures for missing command, timeout, truncated/ANSI/localized output, invalid UTF-8, multiple installations, changed realpath, unauthenticated and unknown auth;
- fake Runtime process runner that asserts exact argv/env/cwd/time/output policy;
- fake tmux inventory with managed/unmanaged/collision states;
- Pair fixtures use a synthetic canary and tests prove it never persists/logs;
- no real token, account, Pair Code, home path, repository name, or public IP in fixtures.

Fixture updates are reviewed as compatibility changes and can change Capability support without changing Application Services.

The implemented sanitized Codex fixtures cover the help shape observed for
standalone 0.146.1, absence of `remote-control`, absence of native `status`, and
malformed help. Missing executable, timeout, non-zero exit, npm-only/conflict,
unsafe executable, output overflow, and future-command cases are expressed as
typed fake-runner results rather than fabricated CLI text. CI never calls a
real Codex binary.

## Phase 5 Controlled Runner and Status Semantics

- resolution uses `shutil.which` under the Runtime environment and enumerates
  only PATH candidates; it does not scan the filesystem or accept a Web path;
- symlinks resolve to a regular executable, group/world-writable targets are
  rejected, and device/inode/mode/size/mtime are rechecked immediately before
  spawn to narrow replacement races;
- execution uses `asyncio.create_subprocess_exec`, an argv tuple, no stdin,
  `start_new_session`, fixed absolute cwd, and an explicit HOME/PATH/locale/XDG
  allowlist. AgentBox, cloud, GitHub, OpenAI, and Anthropic token variables are
  not inherited;
- version/help/status 单次探测使用 8 秒上限，npm metadata 使用 10 秒，
  start/stop/Pair 使用 30 秒；完整 status/mutation RPC 分别使用 70/100 秒
  预算，浏览器使用 85/130 秒预算，使外层 deadline 晚于受控内层 deadline；
  stdout/stderr 仍分别受限；
- timeout/output failure terminates only the process group spawned by AgentBox,
  waits, then kills that group only if required;
- 当公开 Remote `status` 不存在时，只有 strict same-UID、resolved-executable
  和 known-argv 证据可以用 `inferred` confidence 报告 `running`。action 返回值
  不作为后续实时状态缓存；缺少实时证据时保持 `unknown`，因此 daemon 退出后
  不会被陈旧的 `running` 结果阻止重启。AgentBox 不使用 `pkill`、针对发现
  进程的 `kill -9` 或 Codex 私有 lock/state 文件。

MVP residual TOCTOU remains between final `stat` and kernel exec, and
installation classification is best-effort: `$HOME/.local/bin/codex` is a
standalone hint and bounded global npm metadata recognizes known public package
names. Unknown evidence stays `unknown`; no package is removed automatically.

## Open Validation Tasks

- confirm the supported Claude Remote invocation for each release fixture;
- define safe Codex remote-health evidence when native status remains absent;
- verify official install/update artifact checks available from each publisher;
- validate Runtime-user auth and tmux behavior on each supported distribution;
- resolve current host Codex ownership and legacy service before adoption tests.
- before Phase 11, revalidate current public Codex version, Provider/config
  schema, wire APIs, auth, reload/restart, Remote lifecycle, Provider/thread
  relationship, discovery filtering, session storage, active-writer, resume,
  macOS, and Windows behavior;
- define Linux restrictive-file, macOS Keychain, Windows current-user DPAPI,
  and WSL/native isolation boundaries without exposing real API keys;
- validate a single Runtime/Remote lifecycle with switchable Provider binding;
  any proposal for parallel official/third-party daemons requires an ADR and
  human approval;
- execute the two-fake-provider continuity harness and preserve partial failures
  rather than treating an HTTP/Runtime request as full support.

## Phase 7 Adapters

`GitAdapter`, `GitHubAdapter`, and `ProjectWorkspaceManager` expose typed
operations only. UDS arguments are a controlled relative Project key plus
bounded operation-specific values; path, argv, shell, environment, PID, and Git
config are forbidden. Clone staging uses exact Job markers and atomic rename.
Git/GitHub output is bounded and normalized before crossing the socket.

## Phase 9 compatibility exceptions

Runtime syscall filtering, `RestrictNamespaces`, and
`MemoryDenyWriteExecute` remain disabled as explicit compatibility limitations.
Bubblewrap may require user namespaces and Node/V8 may require JIT memory. The
executor instead relies on non-root identity, empty capabilities, typed actions,
bounded processes, Project/HOME write scopes, UID/GID IPC, and redaction.
API/Worker/Helper do not inherit these Runtime exceptions.

## Phase 8 Production Runtime Identity

The installed Runtime Executor runs only as `agentbox-runtime` with HOME
`/home/agentbox-runtime`, Project Root `/srv/agentbox/projects`, and a fixed
server-owned PATH/XDG policy. `/run/agentbox/runtime.sock` is mode `0660` under
the narrow IPC group, and the executor verifies the expected supplementary
group before serving.

Installation does not read, copy, chown, stop, adopt, or rename root Codex,
Claude, gh, tmux, or Project state. `detect`, `version`, and verification are
separate from installation and authentication; production may honestly report
Unavailable, Unauthenticated, or Unknown until the Runtime user completes each
official login. No Phase 8 component changes Provider selection or Codex
configuration.
