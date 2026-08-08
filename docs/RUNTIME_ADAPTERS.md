# AgentBox Runtime Adapter Design

Status: Phase 1 design baseline

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
├── create_session(project, requested_name)
├── stop_session(runtime_session_id)
├── list_sessions()
├── recent_output(runtime_session_id, limits)
├── attach_command(runtime_session_id)
└── workspace_state(project)
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

`generate_pair_code` is available only when pair capability and authentication are confirmed. The adapter marks output as secret at the first byte, validates only the expected bounded shape, returns it through the ephemeral secret channel, and ensures all diagnostic/log paths receive metadata only. It never persists a hash or suffix.

### Login Status

Use a documented public login-status command when detected. If absent, return Unknown with manual instruction. Never infer login by opening auth files or checking a token variable.

### Install and Update

The adapter produces a plan from supported publisher methods. The root Helper handles verified system/install steps. Internal standalone release directories may appear as diagnostic evidence but cannot be hardcoded. Post-install verification includes owner/mode checks due the UID/GID 1001 anomaly observed in Phase 0.

## Claude Adapter

### Public CLI Evidence

Phase 0 found Claude Code 2.1.223 as a global npm package and confirmed public help/auth status. Its current help exposed `--remote-control [name]`. The background example `claude remote-control` may describe another version. The adapter must parse the current help/fixtures and choose only a confirmed invocation; documentation examples are not executable contracts.

### Session Lifecycle

- all managed sessions run as `agentbox-runtime` in a registered project;
- tmux names derive from RuntimeSession IDs and fixed prefix;
- create validates project path, ownership, installation, auth, capability, collision, and workspace state;
- command/flag form comes from the selected version's capability fixture;
- stop addresses only a registered managed session and verifies its socket/owner before signaling;
- list merges managed database state with Runtime-user tmux observations, classifying unknown sessions as unmanaged;
- attach returns a fixed local command; the MVP Web does not create a PTY.

### Workspace Trust

Workspace Trust is `trusted`, `not_trusted`, `unknown`, or `manual_required`. Only a stable public CLI/status interface may produce trusted/not_trusted. Private configuration-file inspection is forbidden as a required mechanism. Unknown results produce project-scoped manual instructions and `needs_attention`; AgentBox never auto-trusts `/root` or a broad parent.

### Authentication

Use `claude auth status` or another detected public status interface with bounded parsing. Missing/changed output is Unknown/Broken. Root Phase 0 login does not transfer to the Runtime user.

### Recent Output

The adapter calls tmux capture for a registered pane only, caps lines/bytes, strips terminal control sequences, applies redaction, and returns an ephemeral response. It never stores pane history in RuntimeSession, Job, or Audit Event.

## Stable, Best-Effort, and Forbidden Evidence

| Evidence | Policy |
|---|---|
| documented/public `--version`, `--help`, status subcommand | preferred stable evidence, still versioned/tested |
| executable resolution and filesystem metadata | stable platform evidence; revalidate before execution |
| AgentBox-created unit/tmux/Job records | authoritative only for managed resources |
| process names/limited argument markers | best-effort supporting evidence, never sole ownership proof |
| package/npm database | best-effort installation-source evidence |
| private Runtime config/auth layout | forbidden as required contract; content not read for auth |
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

## Open Validation Tasks

- confirm the supported Claude Remote invocation for each release fixture;
- define safe Codex remote-health evidence when native status remains absent;
- verify official install/update artifact checks available from each publisher;
- validate Runtime-user auth and tmux behavior on each supported distribution;
- resolve current host Codex ownership and legacy service before adoption tests.
