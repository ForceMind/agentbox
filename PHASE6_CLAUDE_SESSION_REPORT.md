# Phase 6 Claude Code + tmux Session Management Report

## Executive Summary

Phase 6 implements AgentBox's second Runtime capability: project-scoped Claude
Code Remote Control sessions persisted by the Runtime user's tmux server. Web,
API, and CLI callers send only a validated project identifier. The Runtime
Executor resolves the project, detects Claude through public CLI behavior,
creates an exact marked tmux session without a shell, and conservatively reports
Remote and Workspace Trust state.

The implementation includes safe start/stop, duplicate prevention, deterministic
session names, managed/unmanaged separation, restart rediscovery, local TTY
attach, explicit bounded recent output, Doctor diagnostics, authenticated Web UX,
fixtures, backend/frontend tests, desktop/mobile E2E, and a real-host isolated
validation. The real test project required Workspace Trust. AgentBox correctly
returned `NEEDS_INTERACTION`, prepared a live interactive Claude pane without
accepting the prompt, preserved it across detach, rediscovered it after a manager
restart, and cleaned up only the exact test session.

Phase 6 does not implement Project CRUD, Git/GitHub business operations,
Provider Manager, Secret Manager, Privileged Helper, installer, system-user
migration, systemd, or production deployment. No Codex configuration, API key,
Claude authentication state, existing user session, or host system configuration
was modified.

## Branch / Commits / PR

- Repository: `ForceMind/agentbox`
- Base: `main` at `3c33ad6df1c36c0f04949cdc947a665affd36543`
- Branch: `phase/6-claude-session-management`
- Related existing Issues: #11 (Claude adapter) and #12 (tmux lifecycle)
- Commits:
  - `96efbb4` — `feat(runtime): add safe Claude tmux session management`
  - `abc291f` — `feat(runtime): extend typed Claude UDS actions`
  - `9d23b9d` — `feat(claude): add project-scoped session API and CLI`
  - `f90123b` — `feat(web): add Claude session management interface`
  - `d844589` — `test(claude): add Remote session E2E coverage`
  - `0261632` — `docs: document Claude Remote integration`
  - `24515bd` — `docs: record Phase 6 draft PR`
  - finalization documentation recording human review and required CI PASS
- PR: <https://github.com/ForceMind/agentbox/pull/25>

## Observed Claude Environment

Only public CLI behavior and current-user tmux metadata were inspected. No
credential, authentication directory, private Claude configuration, existing
pane content, or unmanaged session name was read.

| Observation | Result |
|---|---|
| Claude installed | Yes |
| Selected executable | controlled absolute executable identity; path omitted from report |
| Claude version | `2.1.226` |
| `claude --help` | PASS |
| `claude remote-control --help` | PASS |
| Remote Control capability | Supported by current public help |
| Authentication | `UNKNOWN` |
| tmux installed | Yes |
| tmux version | `3.4` |
| Existing current-user tmux sessions | 5; names and panes not disclosed |

These are development-host observations, not permanent product protocol or
production Runtime identity evidence.

## Runtime Architecture

The implemented call chain is:

```text
Web / CLI
    -> authenticated AgentBox API / typed CLI
    -> versioned Unix Domain Socket
    -> non-root Runtime Executor boundary
    -> ClaudeSessionManager
    -> ClaudeAdapter + TmuxAdapter + ProjectRegistry
    -> Runtime-user tmux
    -> Claude Code
```

API routes contain no subprocess execution. The UDS protocol retains its 64 KiB
frame and same-UID peer checks. Claude actions are allowlisted and accept only a
validated `project_id`; they cannot carry a path, argv, shell, executable, tmux
flag, PID, signal, or environment.

## Claude Adapter

`ClaudeAdapter` uses only public `--version`, `--help`, advertised
`remote-control --help`, and advertised public auth-status behavior. It does not
guess capabilities from a version and does not inspect private files. The
version parser covers both public forms observed in fixtures and the real host:
`claude 1.2.3` and `2.1.226 (Claude Code)`.

Authentication is `AUTHENTICATED` or `UNAUTHENTICATED` only when public CLI
output gives a recognized signal. The real host remained `UNKNOWN`; successful
`--version` and tmux creation were not treated as login evidence.

## tmux Adapter

`TmuxAdapter` is a fixed-operation wrapper for detect, version, list, exact
presence, create, marker inspection, pane-state inspection, bounded capture,
manual-interaction preparation, and exact kill. It exposes no raw command or
caller-provided argv.

Current public tmux documentation states that multi-argument `new-session` and
`respawn-pane` commands are executed directly without `sh -c`. Creation uses a
fingerprinted absolute `sleep` as a 30-second setup placeholder, atomically
injects the project-derived marker, enables `remain-on-exit`, then directly
respawns the fingerprinted Claude executable with the fixed `remote-control`
argument. The placeholder is immediately replaced and is never owned by the API
request or Runtime Executor as a foreground child.

If detached Remote startup exits on a Workspace Trust prompt, one fixed direct
`claude --` respawn prepares a live interactive pane. This sends no input and
does not accept Trust. It exists only so an SSH/local-terminal user can attach
and make the decision personally.

## Project Binding

Phase 6 implements a minimal configured-root registry, not Project management.
It enumerates only immediate, real directories beneath `AGENTBOX_PROJECT_ROOT`.
Development defaults to `.agentbox-dev/projects`; production design remains
`/srv/agentbox/projects`. `/root/projects` is not a production default.

There is no create, clone, rename, delete, remote URL, Git status, pull, push,
Issue, or PR operation. The Web cannot submit a filesystem path.

## Path Security

Project IDs are bounded normalized single components. Runtime rejects absolute
paths, `.`/`..`, separators, control characters, shell punctuation, hidden root
references, overly long IDs, files, missing targets, root itself, root symlinks,
project symlinks (including links that remain inside the root), inaccessible
directories, nested escape, and canonical escape.

The canonical directory is rechecked before tmux creation and direct Claude
respawn. Bind mounts and same-UID post-check mount changes remain documented
limitations for the later deployment/namespace phase.

## Workspace Trust

AgentBox does not read or write Claude private Workspace Trust data, pass
undocumented trust flags, send `yes`, simulate keys, or automatically confirm a
project. Public output is parsed conservatively:

- recognized Trust or login interaction -> `NEEDS_INTERACTION`;
- recognized fatal startup hint -> `BROKEN`;
- recognized Remote ready hint -> `RUNNING` with bounded evidence;
- changed or unrecognized output -> `UNKNOWN` (or initial `STARTING`).

`INITIALIZED_BY_AGENTBOX` means only that this Runtime process created a managed
session. It is never a claim that Claude's private trust state is true. On the
real host, Workspace Trust interaction was required and left for the user.

## Session Naming

Names are deterministic and bounded:

```text
agentbox-claude-<ASCII-slug>-<sha256-prefix>
```

The slug is only for readability. The hash binds the complete project ID,
including Unicode and display-name collisions. The final grammar is stricter
than `[A-Za-z0-9_-]`, and caller text never becomes tmux syntax.

## Managed / Unmanaged Sessions

Managed ownership requires both the exact deterministic name and the exact
versioned project-derived `AGENTBOX_MANAGED_SESSION` session-environment marker.
An exact-name collision without the marker fails closed. Similar names, legacy
`claude-*` sessions, and other tmux sessions are unmanaged: AgentBox does not
adopt, rename, attach, capture, or stop them. Web/Doctor expose at most a count,
not unmanaged names.

The marker is not a cryptographic boundary against another process running as
the same UID. Production still requires a dedicated Runtime identity and a
minimal same-UID process set.

## Session Lifecycle

MVP ownership is one managed Claude session per project. Per-project
`asyncio.Lock` objects serialize start/stop, and a bounded tmux semaphore limits
operations. A duplicate start returns `already_running`; an absent stop returns
`already_stopped`.

Start resolves the project, checks capabilities and exact collision, creates the
marked session, observes bounded output, and returns conservative state. It does
not block for the long-running Claude child. Stop revalidates exact name and
marker before `tmux kill-session -t =<name>`; there is no `pkill`, PID signal,
similar-name match, or `kill-server`.

tmux owns the long-running interactive process. Runtime Executor restart
rediscovers sessions from configured project IDs, deterministic names, markers,
pane state, and bounded output instead of an in-memory ownership map.

## Attach

Web only displays/copies the exact generated command and never embeds a terminal
or SSH topology:

```text
tmux attach-session -t =<managed-name>
```

`agentbox claude attach <project>` requires local stdin/stdout TTYs, obtains the
exact generated name through the typed Runtime client, validates it again, and
executes only local `tmux attach-session`. It has no JSON mode. In production,
the command must run under the identity that owns the tmux server; cross-user
attach is not implemented.

For first-time Trust on the observed Claude version, the user attaches to the
prepared interactive pane, confirms the project manually, exits that interactive
Claude process, then explicitly stops and starts the Remote session again.

## Recent Output Security

Recent output is opt-in, authenticated, ephemeral, and limited to the exact
marked pane. Capture is limited to 200 lines and 48 KiB at the process boundary,
then ANSI CSI/OSC and control characters are removed and the returned text is
capped to 24 KiB. Runtime JSON uses UTF-8 so bounded Unicode output remains below
the unchanged 64 KiB UDS frame. This is terminal sanitation, not complete secret
redaction.

Responses are `Cache-Control: no-store` and `Pragma: no-cache`. Web keeps the
section collapsed until Reveal, renders text only, and clears it on Hide/unmount.
Pane output is not written to Audit metadata, AgentBox logs, the DB, reports,
Web Storage, URLs, screenshots, or Playwright traces. Audit records only that an
authenticated administrator viewed output for a project.

## API

Implemented authenticated no-store routes:

```text
GET  /api/v1/claude
GET  /api/v1/claude/sessions
GET  /api/v1/claude/sessions/{project_id}
POST /api/v1/claude/sessions/{project_id}/start
POST /api/v1/claude/sessions/{project_id}/stop
GET  /api/v1/claude/sessions/{project_id}/output
```

Mutations require trusted Host/Origin, authenticated admin Session, and
Session-bound CSRF. Bodies are rejected. Audit events cover requested/succeeded/
failed start/stop and metadata-only output access.

## CLI

Implemented commands:

```text
agentbox claude status [--json]
agentbox claude list [--json]
agentbox claude start <project>
agentbox claude stop <project>
agentbox claude attach <project>
agentbox claude output <project>
```

List output omits paths, credentials, unmanaged names, and pane text. Attach and
output do not offer JSON. Sensitive output prints an explicit warning.

## Web

The Phase 4 placeholder is replaced with a responsive Claude page. It presents
installation/version/auth/capability and tmux summary cards plus mobile-first
project session cards. Cards separate tmux running from Remote readiness, never
invent `Connected`, provide explicit start/stop, generated attach copy, Trust
guidance, and collapsed sensitive output.

Stop copy states that the project is not deleted. No Web terminal, arbitrary
input, raw HTML, secret persistence, or automatic session creation exists.

## Doctor

Doctor now includes bounded Claude installation/version/auth/capability, tmux
version, managed count, unmanaged count, Workspace interaction warning count,
and diagnostic codes. It excludes paths, unmanaged names, panes, credentials,
private state, and general host/process details.

## Tests

Final local automated results:

| Check | Result |
|---|---|
| Ruff | PASS |
| Black check | PASS; 57 files unchanged |
| mypy strict scope | PASS; 55 source files |
| pytest | PASS; 150 tests |
| migration upgrade/downgrade/upgrade | PASS |
| frontend ESLint | PASS |
| frontend Prettier check | PASS |
| frontend typecheck | PASS |
| frontend unit | PASS; 22 tests |
| frontend production build | PASS |

Fixtures cover supported/unsupported Remote help, unauthenticated, Trust, ready,
unexpected, timeout, empty/managed/unmanaged/malformed tmux lists, capture, and
missing sessions. Tests cover naming, traversal, root/file/missing paths,
inside/outside symlinks, Unicode, exact marker collision, duplicate start,
restart discovery, wrong-session stop prevention, Trust preparation, output
bounds/sanitation/non-persistence, UDS exact keys, auth/CSRF, API/CLI, and Web.

## E2E

Playwright passed 42 executions: 21 logical cases across desktop Chromium and
mobile Chromium. It uses Fake Runtime only. Coverage includes protected Claude
routes, installed state, start, duplicate start, Needs Interaction, attach copy,
explicit output reveal, no-store/no-storage, stop, stopped/Unknown state,
unmanaged count-only handling, CSRF, 401/session recovery, and mobile layout.

The host Playwright binary lacked three shared libraries. No packages were
installed. RPMs for `mesa-libgbm`, `alsa-lib`, and `libwayland-server` were
downloaded and extracted only into a fresh `/tmp` directory, passed through a
one-run `LD_LIBRARY_PATH`, and deleted. The final run passed 42/42. The initial
browser-launch-only failures did not exercise or fail application assertions.

## Real Host Validation

Automated tests completed before real-host actions. Read-only detection used
public Claude help/version, tmux version/list, and current-user metadata only.
Existing names/panes were not printed or captured, and no existing session was
stopped or modified.

The isolated project was:

```text
.agentbox-dev/projects/agentbox-test-claude-validation-phase6-20260810
```

Only its deterministic AgentBox test session was used. Raw pane output was not
reported.

| Real test | Result |
|---|---|
| Session creation | PASS |
| Workspace interaction | REQUIRED (`NEEDS_INTERACTION`) |
| Live manual-confirmation pane | PASS |
| Managed marker | PASS |
| Remote process presence | UNKNOWN until Trust is manually confirmed |
| Session detach persistence | PASS |
| Runtime restart rediscovery | PASS |
| Exact session cleanup | PASS |
| Test directory cleanup | PASS |

No Trust answer was sent. This result is a safe `NEEDS_INTERACTION`, not a Remote
connected, authenticated, or Workspace trusted claim.

## Security Review

| Risk | Result |
|---|---|
| Arbitrary shell / API subprocess | PASS; no shell and subprocess only in ControlledProcessRunner |
| Caller argv/tmux flags | PASS; fixed typed operations only |
| Path traversal/root escape | PASS |
| Project/root symlink escape | PASS for resolved filesystem paths; bind mount limitation documented |
| Session-name collision | PASS; slug/hash plus exact marker |
| Wrong/similar session kill | PASS; exact marked target only |
| Unmanaged takeover/adoption | PASS; fails closed |
| Output leakage | PASS; no-store, bounded, no raw Audit/log/DB/storage/report |
| ANSI/control injection | PASS; sanitation and text-only rendering |
| Workspace Trust auto-accept | PASS; absent |
| Private auth/config parsing | PASS; absent |
| tmux cross-user confusion | PASS in code boundary; dedicated production identity remains Phase 8 |
| Runtime restart | PASS; real rediscovery validated |
| Long-running child ownership | PASS; tmux-owned |
| Terminal attach misuse | PASS; exact TTY-only local attach |

Repository secret-pattern scanning, Phase 6 source-boundary scanning, forbidden
primitive scanning, project-path tests, E2E canary artifact scanning, temporary
library cleanup checks, and `git diff --check` passed.

## Dependencies

- `pip-audit --local --skip-editable`: PASS; no known vulnerabilities.
- `pnpm audit --audit-level high`: PASS; no known vulnerabilities.
- No dependency version or lockfile changes were required by Phase 6.
- No Claude, tmux, browser library, or system package was installed or updated.

## CI

Local equivalents of Backend, Frontend, Security, dependency audit, and E2E
workflows pass. PR #25 required checks pass: Frontend quality, Backend
quality on Python 3.11/3.12/3.13, E2E, repository boundaries, dependency review,
Python audit, and frontend audit. No required failure is waived by this report.

## Deviations

1. Phase 6 uses bounded direct UDS start/stop responses instead of future durable
   Job/SSE orchestration. The development plan documents this without pulling
   Phase 7 project state forward.
2. Initial real validation found a race when the marker was written after tmux
   creation. Creation now injects the marker atomically with `new-session -e`.
3. Current Claude exits detached `remote-control` with status 1 on an untrusted
   workspace. The final fixed command sequence sets `remain-on-exit` first, then
   prepares one live direct `claude --` pane after Trust evidence. This is not a
   trust bypass or retry loop.
4. The first final-host E2E attempt lacked a transitive Wayland library. The
   environment-only rerun used temporary extracted RPM files and passed; no host
   installation occurred.

No Accepted ADR was overturned. No part is marked Requires Human Approval for a
changed architecture contract.

## Known Limitations

- Claude public help/output and tmux behavior must be revalidated as versions
  change; fixtures are evidence, not a permanent private protocol.
- A ready output hint is not an official machine-readable Remote health API.
- tmux running is not equivalent to Remote connected.
- Authentication and Workspace Trust remain Unknown without recognized public
  evidence.
- After manual first-time Trust, the user must exit interactive Claude and
  explicitly stop/start Remote again.
- Same-UID processes can inspect or forge per-user tmux state.
- Bind mounts and post-check mount changes are not fully solved by canonical path
  checks.
- CLI attach must run as the tmux-owning identity; cross-user attach is absent.
- No automatic restart exists after tmux server loss or a broken Claude process.
- Production identity, authentication migration, systemd hardening, installer,
  and deployment validation remain later phases.

## Phase 7 Recommendation

After merge of the human-reviewed Phase 6 PR, Phase 7 may define formal
Project Workspaces and minimal Git operations. It should reuse the strict
Project ID/canonical-root boundary, replace the temporary immediate-child
registry deliberately, preserve no-raw-path UDS actions, and add an ADR only if
the accepted project ownership or Runtime identity boundary changes.

Do not start Phase 7 until Phase 6 is reviewed and merged. Do not add Project
CRUD, GitHub business operations, Provider/Secret management, Helper, installer,
or host configuration under this branch.
