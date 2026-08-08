# Test Strategy

## Objectives

Tests must prove that AgentBox remains a constrained control plane, not merely that happy-path commands run. The priority order is: privilege containment and secret non-persistence; path and command safety; recoverability; Runtime compatibility; API/UI correctness; performance within a small single-server envelope.

No statement in this document means these tests have already been implemented or passed.

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
4. interrupt after every durable stage, resume, and verify convergence;
5. simulate missing repositories, DNS failure, corrupt/truncated artifacts, full disk, locked package manager, service health failure, and schema migration failure;
6. confirm failure rollback preserves config, database, projects, authentication directories, and pre-existing unrelated services;
7. run explicit uninstall tests and confirm preserved data matches the stated policy.

Package installation is never tested directly on a shared CI runner or the assessed server.

## Upgrade, rollback, backup, and migration

Maintain representative database/config fixtures for every supported upgrade boundary. Test forward migration, pre-migration backup, health-gated release switch, code rollback with compatible schema, declared irreversible migrations, manual rollback, old/new API and IPC negotiation, and restart during each stage.

Restore tests begin on a fresh VM with a deliberately different numeric UID/GID. They verify ownership remapping, SQLite integrity, registered project status, missing external authentication reported as `unauthenticated`, and no assumption that Runtime credentials are portable.

## Playwright coverage

The MVP browser suite covers bootstrap/login, failed-login throttling, logout/session expiry, Dashboard, Codex capability/degraded states, Pair recent-auth and one-time display, Claude session list/start/stop confirmation, Projects create/clone/status, Job SSE reconnect, Doctor, bounded logs, Settings validation, keyboard navigation, and narrow mobile viewport behavior. The suite does not implement or test a browser terminal.

## Linux matrix

| Family | MVP target | Test expectation |
|---|---|---|
| OpenCloudOS 9 | Supported target | disposable VM: install, units, upgrade, Runtime smoke |
| Rocky Linux 9 | Supported target | disposable VM: full RPM-family path |
| Ubuntu LTS | Supported target | disposable VM: full APT-family path |
| Debian stable | Supported target | disposable VM: full APT-family path |

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
