# Test Strategy

## Objectives

Tests must prove that AgentBox remains a constrained control plane, not merely that happy-path commands run. The priority order is: privilege containment and secret non-persistence; path and command safety; recoverability; Runtime compatibility; API/UI correctness; performance within a small single-server envelope.

Sections explicitly labelled implemented record executed coverage; all other
sections remain release-gate designs and are not claims of passing tests.

## Phase 3 implemented coverage

The Phase 3 suite now uses temporary SQLite files, Alembic upgrade/downgrade,
cheap test-only Argon2id costs, an injectable clock, and in-process ASGI calls.
It covers configuration precedence/production refusal, WAL/FK/busy timeout,
schema upgrade → base downgrade → upgrade, single-admin/race constraints,
Argon2id, raw-token non-persistence scans, generic login errors, inactive users,
rate limiting without real sleeps, cookie flags, idle/absolute expiry,
revocation, fixation, cross-Session CSRF, Origin/Host rejection, malformed and
oversized inputs, request IDs/security headers, audit redaction, Worker
readiness/cleanup, CLI bootstrap, and the minimal React login/logout flow.
Dedicated concurrency tests prove that verify runs outside the request event-loop
thread, at most the configured two Argon2 operations run concurrently, locked
buckets skip verify, missing users use the dummy hash, and `/healthz` remains
schedulable while a password verification is deliberately held by a test gate.
Threading events and the existing fake clock make these tests deterministic;
timeouts are failure guards rather than timing assertions.

These are control-plane foundation tests, not a penetration test or proof of
production hardening. Runtime, Helper, Job execution, systemd, Project, and
installer test sections below remain future gates.

## Phase 4 implemented coverage

Phase 4 adds component tests for auth boot, protected-route redirect, Login
validation, successful and failed login, Retry-After presentation, Session
recovery, navigation, centralized `401` handling, CSRF logout, one-time CSRF
refresh/retry, safe request-ID parsing, cookie credentials, and zero auth data
in Web Storage. Backend tests cover unauthenticated and authenticated Doctor
responses and scan the serialized contract for secret/database/path fields.

The Playwright harness explicitly migrates a temporary SQLite database,
initializes a random test-only administrator, starts independent API and Vite
production-preview processes on random loopback ports, and cleans them up. The
Phase 4 baseline introduced ten logical scenarios in desktop Chromium at
1280×800 and mobile Chromium at 390×844 (20 executions): route protection,
accessible Login, generic invalid
credentials, login/refresh/Login redirect, CSRF logout, invalid-CSRF rejection,
all seven product sections, invalid/browser-expired cookies, Web Storage,
horizontal overflow/touch target checks, and the branded 404. It never uses
`.agentbox-dev`, a real administrator, GitHub Secrets, or a public listener.

The source-boundary check continues to reject process/shell primitives in
application Python, fixes the expected route count including safe Doctor GET,
and rejects browser
`dangerouslySetInnerHTML`, dynamic code execution, and Web Storage writes in
production frontend source.

## Phase 5 implemented coverage

Phase 5 adds hermetic Codex adapter fixtures and typed fake-runner results for
supported start/stop/Pair without status, no Remote Control, unknown future
commands, malformed/non-zero/timed-out help, missing/unsafe executable,
npm-only/conflict evidence, authentication states, native/inferred/unknown
Remote state, 仅基于实时证据的幂等 lifecycle、daemon 退出后的重新启动、
完整 status/mutation RPC timeout budget、command failure、timeout 和 Pair parser
failure。Controlled-runner tests assert absolute fingerprinted execution,
literal argv (including shell metacharacters), fixed cwd, environment
allowlisting, independent output caps, timeout cleanup, symlink/mode rejection,
no sensitive logging, and event-loop schedulability.

Unix-socket integration tests exercise all four allowlisted actions, exact
schema rejection, unknown action rejection, bounded framing, and `SO_PEERCRED`
UID rejection. API tests cover authentication, Origin, missing/wrong CSRF,
recent auth, Pair cooldown projection, no-store headers, normalized errors,
Audit metadata, and direct SQLite/WAL/SHM plus captured-log canary scans. CLI
tests cover typed status, fixed start/stop, Pair TTY-only output, and forbidden
Pair JSON.

The browser harness injects one explicit `E2ECodexRuntime`; production always
uses the UDS client. Sixteen logical scenarios run for desktop and mobile (32
executions), including real status rendering/refresh, CSRF start/stop, explicit
Pair confirmation/copy, storage and navigation clearing, unsupported and error
states, plus all Phase 4 authentication/navigation checks. Browser screenshots
and traces are disabled because a failed Pair test must not persist a secret
rendered in the DOM. The harness scans its temporary SQLite/WAL/SHM tree,
Playwright artifacts/report, and Git diff for the randomly generated Pair
canary on both success and failure paths; any canary-bearing browser artifact
is removed before a sanitized failure is returned.

The boundary check now permits subprocess references in exactly one Python
file, `agentbox_runtime/process.py`; `shell=True`, `os.system`, synchronous
subprocess helpers, API-route subprocess use, raw mutation expansion, dynamic
browser execution, and Web secret storage remain rejected.

## Phase 6 implemented coverage

Phase 6 adds synthetic/redacted Claude and tmux fixtures plus tests for public
capability evidence, Unknown authentication, timeouts, trust/login/ready/
unexpected classification, deterministic names, exact markers/collisions,
duplicate start, restart rediscovery, exact stop, output bounds/sanitation, and
no auto-trust.

Project tests cover immediate children, traversal, absolute/nested IDs, root,
file/missing targets, inside/outside/root symlinks, Unicode, long and malicious
names. UDS tests reject missing IDs and extra path/argv-style fields. API tests
cover auth, Origin/CSRF, no-store, metadata-only Audit, output canary absence
from logs/Audit/DB, and normalized Runtime failure. CLI/Web cover status/list,
start/stop, TTY attach, interaction guidance, copy, explicit reveal/hide, text
escaping, API errors, mobile layout, and browser-storage absence.

The branch has 150 backend tests and 22 frontend unit tests. Playwright defines
21 logical desktop/mobile cases (42 executions) with Fake Runtime only and
screenshots/traces disabled for Pair/output canary safety. CI never invokes real
Claude or tmux.

## Phase 11 Slice 2 implemented coverage

The read-only Runtime capability suite covers the exact V1 query/report models,
Codex and Claude fixed capability sets, independent outcome/evidence lifecycle,
one fixed 60-second UTC TTL, complete deterministic observations, sanitized
closed finding codes, and no persistent cache. UDS tests cover the new
`runtime.capabilities.query` action without introducing another socket and
reject wrong versions/actions/sets/type pairs, missing/extra/duplicate fields,
wrong scalar types, malformed Unicode/UTF-8, excessive or concatenated frames,
trailing data, timeouts, and response identity/revision/type/set/capability/time
drift.

Collector fixtures exercise installed/missing/malformed/conflicting Codex,
authentication and Remote tri-state behavior, Provider adapter/profile
validation remaining unavailable, and public-contract unknowns for config
ownership, writer, resume, and discovery. Claude fixtures cover Runtime-only
installation/auth/Remote/tmux and exact managed-session count evidence without
pane capture, private names, or attach commands. A per-type concurrency test
proves bounded single flight.

Security tests assert no mutation method, Provider call, Secret access, config
read/write, private session read, Helper action, `sudo`, `systemctl`, package
manager, public API/CLI/Web reachability, or migration. Canary data injected
into fake raw paths/diagnostics/errors must not enter the wire report, internal
read model, Audit, SQLite/WAL/SHM, logs, diagnostics, or serialized exceptions.
Control Plane tests require a registered Runtime, enforce exact pre/post IPC
revision and report membership, audit only allowlisted counts/states, preserve
synthetic `UNMANAGED`, and create no Provider compatibility evidence.

## Test layers

| Layer | Primary coverage | Default environment |
|---|---|---|
| Unit | validators, policies, state transitions, redaction, adapter parsers | unprivileged CI process |
| Contract | API schemas, error codes, IPC messages, CLI JSON | unprivileged CI process |
| Adapter fixture | captured redacted Codex/Claude/tmux/Git outputs | hermetic fake process runner |
| Integration | FastAPI, SQLite, Worker, SSE, Runtime Executor fakes | temporary directories and UDS |
| Security | path/command/env/PATH attacks, auth, CSRF, sockets | unprivileged CI plus dedicated VM jobs |
| Browser | login, protected pages, jobs, session expiry, accessibility | Playwright against test API |
| System | installer, units, permissions, upgrade/rollback, real tools | disposable virtual machines only |

## Unit and property tests

Unit tests cover strong parameter types, action registry completeness, canonical error mapping, Job transitions and recovery, Confirmation Challenge binding/expiry/single use, audit redaction, output truncation, timeouts, concurrency leases, supported distro parsing, configuration precedence, and version negotiation.

Property/fuzz-style cases should generate unusual Unicode, separators, null-like values, long names, URL encodings, and hostile subprocess output. A policy test fails if a privileged or Runtime action is reachable without a named allowlisted action definition.

## Adapter fixtures

Runtime Adapters are tested primarily against small, redacted fixtures that include:

- known supported output for selected versions;
- missing and renamed subcommands;
- success text on stderr, localized or reordered help, and non-zero exits;
- partial, malformed, slow, and excessively large output;
- authentication that is `authenticated`, `unauthenticated`, `unknown`, or `broken` without reading private configuration;
- Codex versions with `start`, `stop`, and `pair` but no `status`;
- Claude help with and without Remote Control and tmux session collision/staleness.

Fixtures record provenance, tool version, command, exit code, redaction review, and expected capability result. They contain no Pair Code, token, username, private path, repository secret, or complete authentication output. Fake runners assert the exact executable, argument array, working directory, environment allowlist, timeout, output cap, UID, and cancellation behavior.

## Integration tests

Integration tests use temporary roots, disposable SQLite databases, fake Helper/Runtime UDS peers, and deterministic clocks. They exercise login through service execution, Job persistence, Worker claiming, SSE resume via event IDs, cancellation, daemon restart recovery, incompatible client versions, audit correlation, and bounded log views.

The database suite verifies Alembic upgrade paths, transaction behavior under serialized writes, WAL configuration, orphan handling, backup via SQLite's consistent backup mechanism, and restoration. It also scans all tables and test log sinks for secret canaries.

## Security tests

### Authentication and Web

- missing/invalid/expired sessions, fixation and rotation;
- CSRF across all state-changing requests, including Pair generation;
- login throttling without account-discovery leaks;
- bounded off-loop Argon2 execution, dummy verification, and no verify after a
  rate-limit precheck rejects the request;
- cookie flags, origin checks, cache headers, and no-store secret responses;
- authorization on every object and Job/event stream;
- SSE connection limits and reconnect behavior.

### Command and environment injection

- metacharacters, leading dashes, newlines, Unicode controls, and huge values remain data in an argument array;
- no shell invocation or user-selected executable;
- fixed absolute executable resolution and expected ownership/mode checks;
- `PATH`, loader, proxy, Git, Python, Node, and authentication environment variables are absent unless explicitly allowlisted;
- time, output, process count, and concurrency limits are enforced.

### Path escape

Test `..`, absolute paths, URL encodings, case/normalization edge cases, hard links where relevant, symlink components and final symlinks, mount/bind surprises, rename/symlink swaps between validation and use, and repository worktrees pointing outside the project root. Destructive operations require descriptor-relative or equivalent race-resistant resolution, not a single string-prefix assertion.

### Git and repository content

Use hostile local repositories to test hooks, aliases, pager/editor/config injection, `.gitmodules`, recursive submodules, credential prompts, large object/output cases, and filenames that resemble options. Networked URL policy tests use controlled fixtures. Default project operations do not execute repository hooks or submodule code.

### Pair Code and secrets

A generated canary must appear only in the direct authorized response/TTY path. After the test, scan SQLite, WAL/SHM files, journald capture, application logs, audit records, Job rows/events, traces, metrics, exceptions, HTTP access logs, SSE events, crash artifacts, and backup output. Test disconnect and timeout cases to prove cleanup. Screenshots and snapshot tests may never capture the code.

### Privilege and IPC

VM tests verify socket ownership/mode, `SO_PEERCRED` enforcement, protocol/action allowlists, replay/duplicate requests, UID separation, systemd sandbox directives, helper timeout/kill semantics, file ownership, and inability of Web/API to invoke a shell or connect as an unauthorized user. Root Helper tests use an ephemeral VM snapshot, never the normal developer host.

## Installer idempotency and failure injection

For each supported distribution family:

1. dry-run a clean image and verify no mutation;
2. install, capture declared resources, and validate units/users/permissions;
3. install again and require no unexpected changes;
4. interrupt around migration/activation, require an exact recovery-state
   classification, and prove a later invocation does not replay mutation;
5. simulate missing repositories, DNS failure, corrupt/truncated artifacts, full disk, locked package manager, service health failure, and schema migration failure;
6. confirm failure rollback preserves config, database, projects, authentication directories, and pre-existing unrelated services;
7. run explicit uninstall tests and confirm preserved data matches the stated policy.

Package installation is never tested directly on a shared CI runner. The
designated OpenCloudOS host may receive only the exact printed Phase 8 package
plan after every fixture/security/backup gate passes.

## Upgrade, rollback, backup, and migration

Maintain representative database/config fixtures for every supported upgrade boundary. Test forward migration, pre-migration backup, health-gated release switch, code rollback with compatible schema, declared irreversible migrations, manual rollback, old/new API and IPC negotiation, and restart during each stage.

Restore tests begin on a fresh VM with a deliberately different numeric UID/GID. They verify ownership remapping, SQLite integrity, registered project status, missing external authentication reported as `unauthenticated`, and no assumption that Runtime credentials are portable.

## Playwright coverage

The suite uses a dedicated test application with fake typed Runtime services;
production UI still consumes only backend data. Phase 7 defines 27 scenarios
at desktop and mobile sizes (54 cases): Project empty/list/create/clone success
and failure; clean/dirty detail; branch create/switch; active-Claude blocking;
Pull success/reconciliation; Push success/upstream missing; GitHub auth,
Draft PR and checks; dangerous-action absence; responsive layout; and
authentication expiry/recovery. It also retains the earlier auth, Codex,
Claude, Doctor and Settings flows. Tests never use a real account, token,
repository mutation, Pair Code, or browser terminal.

## Linux matrix

| Family | MVP target | Test expectation |
|---|---|---|
| OpenCloudOS 9 | validation target | fixture plus one gated real-host install/update/rollback |
| Rocky Linux 9 | preview | DNF/os-release fixtures; VM remains required |
| Ubuntu 22.04 | unsupported fixture | rejection plus GitHub Actions; stock Python 3.10 is below the product minimum |
| Ubuntu 24.04 | CI preview | APT fixtures and GitHub Actions; native VM systemd remains required |
| Debian 12 | preview | APT/os-release fixtures; VM remains required |

## Phase 8 Implemented Coverage

The installer/deployment suite uses temporary filesystem roots and fake host
operations for fresh/repeated/partial installs, config/secret/admin/project
preservation, migration failure, activation/service failure, online WAL backup,
update, rollback, rollback-verification failure, collisions, lifecycle locking,
and data-preserving uninstall. Platform fixtures cover every matrix row and
unsupported distribution/architecture behavior.

Helper tests exercise wrong peers, invalid/unknown/extra frames, malformed and
oversized messages, path/argv/service injection, timeout, request-ID sanitation,
and concurrency caps. Real temporary POSIX identities verify cross-user file
denials. Unit tests combine semantic assertions with actual
`systemd-analyze verify` and offline security analysis where available.

GitHub deployment CI runs the safe fixture subset on Ubuntu 22.04/24.04 with
Python 3.11/3.13. This does not make stock Ubuntu 22.04 installable. It never
creates `/etc/agentbox`, users, units, or services.
Rocky/OpenCloudOS/Debian fixture evidence is not represented as a native VM
claim. The Phase 8 report records real-host evidence separately.

Exact minor releases and architecture coverage are pinned in Phase 2/8 based on available runners. `x86_64` is the first verified architecture; `aarch64` is not claimed until its matrix passes. Container jobs can test pure Python/Node behavior but cannot substitute for PID 1 systemd, SELinux/AppArmor, package-manager, UDS ownership, tmux, cgroup, or privileged Helper VM tests.

## GitHub Actions design

Pull requests run deterministic unprivileged lint/type/unit/contract/fixture/integration/frontend/Playwright and secret/dependency checks. Scheduled or manually approved jobs run selected disposable VM matrices. Release workflows require protected environments and never receive Runtime-user credentials from a real server. Logs are assumed public and are passed through redaction.

Required checks should be fast enough for normal review; slower VM and compatibility suites may be required for release branches/tags rather than every documentation change. Cache keys must not contain secrets, and third-party actions are pinned to immutable references according to the supply-chain policy.

## Tests that normal CI cannot safely provide

- real Codex/Claude/GitHub authentication or Pair generation using production accounts;
- modification of the assessed host's old Codex unit, root-owned sessions, cloudflared, firewall, or network listeners;
- authoritative compatibility with future undocumented CLI behavior;
- full systemd/package/SELinux/AppArmor behavior on a generic container runner;
- external tunnel or public-internet exposure tests without a dedicated isolated environment.

These require disposable VMs, dedicated test identities, redacted evidence, and explicit approval. Manual checks are recorded as such; they are never described as automated proof.

## Release quality gates

A release is blocked by an open Critical/High security defect; a Pair Code or credential canary in persistent output; a path/command escape; a root-owned Runtime path; broken upgrade/rollback/restore; unclassified destructive failure; or missing supported-family deployment evidence. Accepted residual Medium risks require explicit human sign-off and a documented mitigation/revisit date.
## Phase 10 release-candidate coverage

The independent Release Candidate workflow derives `0.3.0rc1` from the core
version source, builds the production Web once, and creates two release bundles
from separate staging directories at the same commit and
`SOURCE_DATE_EPOCH`. Exact tarball, manifest, SBOM, and checksum equality is the
same-runner reproducibility gate; cross-runner byte equality remains unverified.

The release verifier checks the external/internal manifest and SPDX SBOM,
SHA-256 files, complete file allowlist and per-file hashes, artifact naming,
wheel/version/platform/migration consistency, canonical paths, duplicate and
Unicode-normalization collisions, archive links/special types/unsafe modes and
bounds. A separate canary scan covers archive names, extracted content, docs,
static JavaScript, metadata, and public files; source maps are forbidden.

The artifact-only smoke creates an isolated venv from the embedded wheelhouse
without Node or a source checkout, runs CLI help/version, migrates a temporary
SQLite database, starts loopback API/static Web, verifies health/readiness/meta,
then exercises fixture fresh install, two idempotent reinstalls, and
data-preserving uninstall. Existing fault matrices remain the update/rollback
rehearsal. No CI job writes runner `/etc`/`/opt`, uses production credentials,
creates a tag/Release, or connects to a real server.

## Phase 9 hardening and recovery coverage

The release-candidate suite adds systemd minimum-version/capability fixtures,
offline unit verification, restart-persistent login throttling, local
password/session management, strict mutation types, proxy trust/source tests,
UID+GID UDS peers, malformed/deep/duplicate/concatenated frames, lifecycle
crash points, corrupt rollback evidence, concurrent WAL backup, retention
identity, permission-drift diagnostics, clock rollback, and a cross-path secret
scan.

The Deployment matrix runs installer/security/recovery fixtures on Ubuntu
22.04 and 24.04 with Python 3.11 and 3.13, then a fail-closed aggregate gate.
This does not emulate PID 1 or qualify Rocky/Debian native installs. Full host
reboot remains unperformed without separate human approval.

## Phase 7 coverage

Tests cover Project normalization/idempotency/rollback, traversal and symlink escape, clone protocol and option injection, marker-bound cleanup and no-replace activation, porcelain v2 variants, branch/refspec injection, ff-only Pull, explicit no-force Push, active-Claude guards, dangerous repository and worktree Git config (including a real executable canary), credential redaction, public `gh` auth states, bounded Draft PR stdin, Jobs/non-replay recovery, authenticated API/CSRF/no-store, responsive Web and Fake Runtime E2E. Core tests never require GitHub network access.
