# AgentBox Phase 9 Security Hardening Report

## Executive Summary

Phase 9 reduces release-candidate risk without adding a product surface. It
adds restart-persistent login throttling, local TTY-only administrator recovery,
strict IPC and API parsing, compatible systemd syscall filtering, version-aware
unit validation, fail-closed transaction recovery, verified retention,
sanitized diagnostics, immutable GitHub Actions pins, and expanded failure and
secret-regression tests.

The designated OpenCloudOS 9.4 x86_64 host completed an update, rollback, and
forward-update regression to `0.2.10+dev.9`. API, Worker, and Runtime remain
non-root; the root Helper remains fixed-action only. The API still listens only
on `127.0.0.1:8787`. No reboot, SSH, firewall, cloudflared, Provider, Secret,
or root Runtime change was made.

This is a pre-release/MVP-candidate review, not a penetration test,
certification, stable-release declaration, or broad distribution support claim.

## Branch / Commits / PR

- Baseline: `main` at `90c51cb4d5071ed3393d132e2cc959d2b102ab61`
- Branch: `phase/9-security-hardening-compatibility`
- Commits before this report-finalization commit:
  - `6b3726a` — `security(auth): persist throttling and add admin recovery`
  - `df6170c` — `security(ipc): reject ambiguous runtime and helper frames`
  - `d0b266a` — `security(systemd): apply compatible sandbox limits`
  - `8aaed4f` — `test(recovery): harden lifecycle crash and retention handling`
  - `00b379b` — `feat(diagnostics): add sanitized production export`
  - `3786061` — `ci(security): pin third-party workflow actions`
  - `8217541` — `docs: record Phase 9 hardening and compatibility evidence`
- Draft PR: [ForceMind/agentbox#30](https://github.com/ForceMind/agentbox/pull/30).
  Merge is explicitly not authorized by Phase 9.

## Security Scope

Reviewed boundaries are Browser/CLI to API, API/Worker to Runtime UDS,
`agentbox` to the root Helper UDS, root installer to AgentBox-owned host paths,
SQLite/WAL, releases/backups, and CI artifact inputs. Provider Manager, Secret
Manager, public ingress automation, multi-server, SaaS, SSH/firewall/tunnel
management, and arbitrary shell remain absent.

## systemd Hardening

All services retain empty ambient and capability bounding sets. API, Worker,
and Helper now use the tested `@system-service` syscall allowlist with `EPERM`
failures. The Runtime intentionally does not use that allowlist because current
Codex/Claude/Node/V8/tmux/Git/bubblewrap behavior cannot be covered safely by a
stable narrow filter. Unit directives are mapped to a minimum systemd version
and rejected before installation when the target is incompatible.

| Unit | Before | After | Remaining findings and rationale |
|---|---:|---:|---|
| `agentbox-api.service` | 2.7 OK | 1.4 OK | Host root rather than chroot; IPC supplementary group; AF_UNIX and loopback INET are required; host networking remains for loopback serving but IP allowlist is localhost-only; `PrivateUsers` is deferred. The broad tested syscall group still includes resource/chown-class calls. |
| `agentbox-worker.service` | 2.0 OK | 0.6 SAFE | Host root rather than chroot; Runtime IPC supplementary group and AF_UNIX are required; `PrivateUsers` is deferred. Worker has `PrivateNetwork=true`; the syscall group retains resource/chown-class calls. |
| `agentbox-runtime.service` | 3.7 OK | 3.7 OK | Runtime needs HOME, AF_UNIX/INET, host networking, namespaces/bubblewrap, executable memory for V8/JIT, and broad third-party CLI syscalls. Chroot, `PrivateUsers`, syscall whitelist, `MemoryDenyWriteExecute`, and namespace restrictions remain accepted compatibility findings. Capabilities, kernel/device/control-group mutation, SUID/SGID, personality changes, and unapproved filesystem writes remain blocked. |
| `agentbox-helper.service` | 2.3 MEDIUM | 0.9 SAFE | The socket-activated process must be UID 0 to perform six fixed AgentBox lifecycle mappings. It needs AF_UNIX and host root visibility for fixed systemd operations; no ambient/file capability exists. `PrivateUsers` and chroot are deferred. The tested syscall group retains resource/chown-class calls, but the typed protocol cannot supply such arguments. |

Scores are host-specific `systemd-analyze security` heuristics, not a proof of
security. Remaining items are accepted because they are required by explicit
service behavior or need broader compatibility evidence before tightening.

## Runtime Compatibility

The Runtime keeps `ProtectSystem=strict`, kernel/control-group/device
protections, empty capabilities, `RestrictSUIDSGID`, `LockPersonality`, native
syscall ABI, and explicit write paths. It retains its private Runtime HOME,
Project root, network, namespaces, and executable memory. On the real host it
detected Codex, Claude `2.1.229`, tmux `3.4`, and Git `2.43.7` through the
Runtime socket under the `agentbox` caller. Authentication was not copied;
Claude authentication and Remote compatibility correctly remain `UNKNOWN`.

## Platform Matrix

| Platform | Qualification | Evidence / limit |
|---|---|---|
| OpenCloudOS 9 x86_64 | Real-host validated | 9.4 host, systemd 255, install/update/rollback/service/Doctor evidence |
| Ubuntu 22.04 x86_64 | CI rejection validated | Repository matrix runs with Python 3.11/3.13; native stock Python 3.10 is unsupported |
| Ubuntu 24.04 x86_64 | CI validated | Deployment matrix, offline unit analysis, fixture lifecycle; not real PID 1 validation |
| Rocky Linux 9 x86_64 | Fixture validated | DNF/package/filesystem/systemd 252/install/update/rollback fixtures |
| Debian 12 x86_64 | Fixture validated | APT/package/filesystem/systemd 252/install/update/rollback fixtures |
| aarch64 | Unsupported / unqualified | Detected and rejected fail closed; no qualified release/Runtime inventory |

The prebuilt Web does not require Node. Codex, Claude, tmux, bubblewrap, gh,
Node/npm/pnpm are optional Runtime capabilities rather than core API install
blockers.

## Failure Injection

`tests/support/failure_injection.py` is test-only and is not packaged. It
injects bounded failures at filesystem, backup, migration, activation, service,
socket, health, checksum, timeout, and ENOSPC boundaries. Production lifecycle
code contains no environment-controlled failure hook.

## Installer Recovery

Tests cover crashes after identity creation, directories, configuration,
release staging, backup, migration, activation, daemon reload, service start,
and before health verification. A durable journal entry is written before each
mutation class. A later invocation classifies staged, activated, partially
migrated, rollback-pending, committed, or unknown state rather than blindly
replaying it.

## Upgrade Recovery

The upgrade matrix covers stage, verify, backup, migration, activation,
restart, health, and commit. `receipt_write_started` is recorded before the
receipt is written, preventing a process death between receipt and final journal
commit from being misclassified as a migration replay. A migration failure does
not claim database restoration unless the verified backup is restored and
checked.

Real-host validation deliberately encountered and recovered from one candidate
artifact whose manifest declared the old Alembic head. The installer rejected
the post-migration mismatch, restored release `0.2.8+dev.8` and database
revision `0002_project_jobs`, restarted services, and verified readiness. The
builder was corrected to derive the unique Alembic head statically and reject
dynamic/branched/incomplete migration graphs. The corrected artifact then
completed the full lifecycle.

## Rollback Corruption

Missing/corrupt backup, checksum mismatch, missing/corrupt old release, unit
restore failure, health/readiness failure, wrong version, DB integrity failure,
socket failure, and Helper failure all prevent `rollback verified`. Output
distinguishes a rollback attempt from verified recovery.

## SQLite / WAL

SQLite remains appropriate for the bounded single-host MVP. Tests run online
backup while WAL writes continue, verify the self-contained backup with
`PRAGMA integrity_check`, exercise login/Job/Doctor/cleanup concurrency and busy
timeouts, and reject corrupt backup evidence. Production DB and sidecars remain
owned by `agentbox`; backups are root-owned `0700` storage and verified files
are restrictive. The final database was 155,648 bytes, passed integrity check,
and was at revision `0003_security_hardening`.

## Worker Recovery

Tests cover killed workers, expired leases, duplicate claim attempts, delayed
heartbeat, temporary database lock, and unavailable Runtime. Uncertain
mutations transition to attention-required state and are not blindly replayed.
Worker remains single-concurrency by default and has no Internet namespace.

## Runtime Recovery

Service lifecycle tests verify Runtime socket recovery, queued request failure
classification, Codex status rediscovery, Claude managed-tmux rediscovery, and
Git workspace state without adopting or stopping unmanaged/root sessions. No
host reboot was performed.

## Authentication Hardening

Login throttling is SQLite-persistent, automatically expires, clamps backward
clock movement, has a fixed maximum row count, and stores only keyed
pseudonymous account/source bucket IDs. Raw usernames and IP addresses are not
stored. Argon2 concurrency caps, idle/absolute Session TTL, exact Host/Origin,
CSRF, Secure Cookies, and explicit trusted-proxy handling remain enforced.

## Sessions

`agentbox admin password` is TTY-only, verifies the current password, accepts no
password argument, writes a fresh Argon2 hash, and revokes all Sessions.
`agentbox admin sessions` lists metadata only, and
`agentbox admin revoke-sessions` verifies the current password. Raw Session
tokens and password material are neither displayed nor audited.

## Logging / Secret Regression

A full-system canary covers password, Session token, CSRF, application secret,
credential URL, fake gh token, Codex Pair Code, and Claude output. It scans
captured logs plus SQLite, WAL, and SHM bytes. This review found and fixed a
real redaction defect where a `Bearer` label was removed but its token remained.
The corrected patterns consume the complete bearer credential and known token
shapes. Installer/helper logs do not dump request payloads or environment.

## Pair Code Regression

Pair Code remains a transient delivery channel only. API/CLI/Web, logs, Audit,
Jobs, database files, reports, and browser artifacts do not persist it; tests
exercise the integrated canary path.

## Claude Output Regression

Recent Claude pane output remains a bounded sensitive response and is absent
from logs, Audit, Jobs, SQLite/WAL/SHM, diagnostics, reports, and test artifacts.

## Git Credential Regression

Credential-bearing URL and fake gh token canaries are redacted before logs and
are absent from persistence and diagnostics. Runtime credentials remain in the
private Runtime HOME and are never copied from root.

## UDS Robustness

Runtime and Helper reject oversized, truncated, concatenated, duplicate-key,
deeply nested, malformed UTF-8, null/wrong-type, unknown-field, unknown-version,
unknown-action, and invalid request-ID frames. Correlation IDs use a bounded
grammar and cannot supply path, argv, environment, PID, signal, unit, or log
structure. SO_PEERCRED validates allowed UID and primary GID; socket mode is not
the sole identity control.

## Supply Chain

Release archives retain checksum, manifest, extraction bounds, traversal/link/
device/FIFO defenses, and semantic version identity. SHA-256 is described only
as integrity evidence; authenticity is not verified until a future signed
release design is approved. Generated release trees exclude bytecode/cache
artifacts, and manifest database revision is derived from the migration graph.

## Dependency / CI Security

All 19 external GitHub Actions references are pinned to immutable commit SHAs.
`scripts/check-workflow-action-pins.py` checks every reference against an
explicit five-source registry containing the official repository, exact
release tag, and audited SHA; a previously unseen source or a SHA/tag-comment
mismatch fails. Existing
`pip-audit`, `pnpm audit`, dependency review, secret scan, repository-boundary,
forbidden-primitive, Backend, Frontend, E2E, and Deployment gates remain.
Shell syntax is checked; actionlint/shellcheck were not added as new required
contexts because the existing targeted checks provide stable low-noise coverage.
The first PR run exposed a test-fixture portability defect: a proxy/Cookie test
used the production `/opt/agentbox` static path, which existed on the designated
host but not clean runners. The fixture now disables unrelated static serving;
the production static artifact retains separate integration coverage.

## Diagnostics

Doctor findings use stable schema version 1 with `OK`, `WARN`, `FAIL`, and
`UNKNOWN`, codes/categories, safe details, and remediation IDs. It checks
platform, units, identities, directory/permission drift, sockets, loopback,
database/migration, optional Runtime tools, and disk usage without recursive
Project reads. Diagnostics export is new-file-only, no-follow, `0600`, and
guarded against known secret shapes before the first write. It rejects
symlinked parent chains and unsafe shared parents, creates relative to a
validated parent descriptor, removes an incomplete new file on failure, and
caps total, section, finding, collection, nesting, message, and filename sizes.
Operators are told to review it before sharing.

## Retention

Worker cleanup defaults to 14 days for completed Jobs/JobEvents and 90 days for
Audit Events, and removes expired login limiter buckets. Lifecycle retention
keeps five verified backups and four verified releases. It independently
resolves and verifies the managed `current` link instead of relying only on a
caller-supplied keep set, and also protects the direct rollback and
current-transaction identities. Deletion requires verified manifests/digests
and refuses symlinks or unknown objects. A diagnostic report is an
operator-selected new file and has no AgentBox-owned temporary retention area.

The real host contains exactly five Phase 8/9 backups that pass the new
verification contract; all five are retained. Nine older Phase 8 directories
do not satisfy that contract and are conservatively retained as unknown for
manual review. No user or unknown path was deleted.

## Performance Baseline

On the 2-vCPU/approximately 3.5-GB OpenCloudOS host after final update:

| Process | Current RSS | Observed peak RSS |
|---|---:|---:|
| API | 62.1 MB | 128.1 MB |
| Worker | 48.9 MB | 115.2 MB |
| Runtime | 66.0 MB | 112.3 MB |
| Combined current | approximately 177 MB | not summed as simultaneous peaks |

SQLite was 155,648 bytes. No obvious idle growth or default high-concurrency
path was observed. These point measurements are a baseline, not a capacity or
load-test claim.

## Real-host Validation

The final active release is `0.2.10+dev.9`; health is `ok`, readiness reports
database/migrations ready, DB revision is `0003_security_hardening`, and Doctor
reports ready. API/Worker run as `agentbox`; Runtime runs as
`agentbox-runtime`; Helper is socket-activated root. Runtime and Helper sockets
are `0660` with their designed owner/group. Runtime HOME and Project root are
`0700` and unreadable/unwritable by `agentbox`; application environment/DB are
unreadable by `agentbox-runtime`. A fixed Helper daemon-reload action succeeded
under the new seccomp profile.

The update path was exercised as: verified failure/recovery from the rejected
candidate, successful `0.2.10+dev.9` update, verified rollback to
`0.2.8+dev.8`, then successful forward update. The final transaction journal is
committed through health, retention, and receipt checkpoints. API listens only
on `127.0.0.1:8787`. Existing root Codex PIDs, the primary root Claude process,
root tmux session identity, legacy Codex service, root Codex config metadata,
and root gh config metadata remained unchanged. An active root Claude process
changed its own directory timestamp during the review; AgentBox contains no
path or operation targeting that directory.

No host reboot occurred. SSH, firewall, cloudflared, existing root Runtime
services/credentials/sessions, Provider configuration, and Project source were
not modified.

## Security Review

No Phase 9 blocker remains in the reviewed implementation. Privilege identities,
fixed Helper actions, credential separation, rollback verification, WAL backup,
secret non-persistence, proxy semantics, loopback bind, and required dependency
audits pass. Residual systemd and platform limits are explicit accepted findings
requiring human review; they are not represented as full hardening or broad
support.

## Residual Risks

- Runtime remains the widest non-root boundary because third-party developer
  tools need HOME, network, namespaces, and JIT-compatible executable memory.
- Services use the host root filesystem read-only rather than a chroot/VM, and
  `PrivateUsers` is deferred.
- Artifact checksums prove integrity only when the expected digest is trusted;
  signed authenticity is not implemented.
- TLS/reverse proxy, external backups, monitoring, and Project-source backup are
  operator responsibilities.
- SQLite and local leases are single-host only.
- Pattern-based diagnostics/secret guards reduce known leakage but cannot prove
  arbitrary text safe; reports still require operator review.
- Nine legacy backup directories are intentionally retained because they lack
  the new verified retention identity.

## Known Limitations

- OpenCloudOS 9 x86_64 is the only real-host-qualified platform.
- Ubuntu 24.04 has CI/fixture rather than native PID 1 evidence; Rocky 9 and
  Debian 12 remain fixture-only; Ubuntu 22.04 native installation and aarch64
  are unsupported.
- Local Playwright could not launch because the host lacks `libgbm.so.1`;
  browser acceptance relies on the required GitHub E2E run. No host package was
  installed to mask this environment limitation.
- Runtime authentication is deliberately independent and remains manual.
- Signed releases, formal SBOM publication, stable packaging/release notes, and
  broader VM qualification remain future release gates.

## Final Security Review

The merge-preparation review on 2026-08-13 was limited to Phase 9 security
surfaces. It did not add a product feature or touch Phase 10/11 scope.

### Persistent limiter and account boundary

- SQLite contains only keyed account/source/combined digests, a bounded failure
  timestamp list, update time, and optional lock expiry. Raw passwords,
  usernames, and source addresses are absent.
- `BEGIN IMMEDIATE` serializes checks and failure writes. The row limit is
  rechecked in the same failure transaction, and SQLite busy/lock failure maps
  to a fail-closed database-not-ready result after the configured timeout.
- Restart persistence, five-failure lock/expiry, source spray, distributed
  account attack, successful-login cleanup, concurrent failures, row-cap
  admission, cleanup boundary, forward/backward clock behavior, and malformed
  username identity collision all pass. An active lock observed after a large
  backward clock step is clamped to the configured lock duration.
- Missing, inactive, wrong-password, and equivalently locked account paths use
  matching public status/error shapes. Rate-limit admission occurs before the
  bounded off-event-loop Argon2id verification.
- Phase 9 exposes no application-secret rotation command. Update/reinstall/
  rollback preserve it. A future controlled rotation must invalidate Sessions
  and explicitly clear now-unmatchable limiter digests; this implication is
  recorded in `docs/SECURITY.md`.

### Password and Session review

`agentbox admin password`, `sessions`, and `revoke-sessions` remain local
TTY-only. Password values have no argv/environment/JSON path, terminal echo is
disabled, current-password and policy checks run through Argon2id, and the hash
change, all-Session revocation, and safe audit event commit atomically. An
injected audit failure rolls back both hash and revocation. Two browser Sessions,
their old CSRF values, and the old password are rejected after a successful
change; the new password succeeds.

The chosen local recovery policy revokes all browser Sessions, including any
Session from which the operator may previously have authenticated. Phase 9 has
no by-row or by-ID revoke surface, so one/other/current/expired/unknown-ID
manipulation is structurally unavailable. Listing returns only the opaque
display ID, bounded client label, and timestamps—not cookie/token hashes or
CSRF material. Repeated all-Session revocation is safely idempotent.

The final review identified and reproduced one password-rotation/Login race:
an old-password Login could finish Argon2 verification before a password
change committed, then issue a Session afterward. The final Login write now
uses `BEGIN IMMEDIATE`, reloads the administrator, and compares the stored hash
in constant time with the exact encoded hash that was verified. The hash
revalidation, optional rehash, `last_login_at` update, Session issue, and
`login_succeeded` audit are protected by that same serialized transaction.
Limiter success cleanup runs only after it commits. A stale Login instead keeps
the generic invalid-credentials response, records a failure, preserves failure
buckets, emits no success audit, issues no Session, and cannot write a stale
rehash over the new password.

Deterministic Event-coordinated tests (all with five-second failure timeouts)
cover both commit orders. If password change commits first, the paused Login is
rejected. If the Login transaction owns the writer reservation first, password
change subsequently revokes the Session it created. These tests establish the
fix for the identified SQLite transaction interleaving; they are not a claim
of a general proof over every external database engine.

### Diagnostics allowlist and canaries

The collector constructs a fixed observation schema; it does not collect logs,
Project files, database rows, process environments, Runtime auth/config, Pair
Code, Claude pane output, or credential-bearing Git data and then attempt to
redact them. Pattern checks are a second fail-closed layer.

Tests place `PASSWORD-CANARY`, `SESSION-TOKEN-CANARY`, `CSRF-CANARY`,
`APP-SECRET-CANARY`, `CODEX-PAIR-CANARY`, `CLAUDE-OUTPUT-CANARY`,
`GITHUB-TOKEN-CANARY`, `GIT-CREDENTIAL-CANARY`, `SSH-KEY-CANARY`, and
`PROVIDER-KEY-CANARY` in simulated sensitive sources. Each forbidden source is
rejected before output creation, and a generated allowlist report contains none
of the values. Symlink destination/parent, overwrite, filename, structural,
size, and injected fsync failure cases leave no secret-bearing partial file.
The CLI says `Review this diagnostic report before sharing` and makes no
guarantee that arbitrary text is secret-free.

### Retention, recovery, and SQLite evidence

- Terminal Jobs and their JobEvents use 14-day parent retention; Audit uses 90
  days; active Jobs and Sessions survive cleanup; revoked/expired Sessions and
  expired limiter rows have separate boundaries. Concurrent active Session
  authentication and cleanup retains the Session.
- Backup/release cleanup accepts only verified AgentBox manifests and digests,
  refuses roots/candidates with symlinks or mismatched/unknown identity, and
  preserves receipt/transaction targets plus the independently verified active
  release target. Escaping `current` links stop cleanup without deletion.
- `FailureInjector` exists only below `tests/support`; no packaged source,
  environment variable, Web/API/config, or installer CLI switch can enable it.
- Crash tests inject after real persistent mutations: journal/receipt writes,
  backup, migration, activation, restart, health, and committed journal. A
  corrupt journal or unknown schema now fails closed rather than being treated
  as absent, and real-host reads require root ownership and mode `0600`.
- Online SQLite backup ran with simultaneous committed WAL writes and live
  reads, produced no dependent WAL/SHM sidecar, and passed digest plus
  `PRAGMA integrity_check`. Concurrent limiter, Session, and Job transactions
  exercise real SQLite rather than a mocked backup API.

### GitHub Action provenance

Official repository commit and tag endpoints were read during this review; each
pinned commit was present at the exact release tag below. The script stores this
mapping locally and checks all 19 uses. This is action-source provenance
evidence, not a claim that the complete CI supply chain is cryptographically
attested.

| Action source | Exact tag | Pinned commit |
|---|---|---|
| `actions/checkout` | `v4.4.0` | `11d5960a326750d5838078e36cf38b85af677262` |
| `actions/setup-python` | `v5.6.0` | `a26af69be951a213d495a4c3e4e4022e16d87065` |
| `actions/setup-node` | `v4.4.0` | `49933ea5288caeca8642d1e84afbd3f7d6820020` |
| `actions/dependency-review-action` | `v4.9.0` | `2031cfc080254a8a887f58cffee85186f0e49e48` |
| `pnpm/action-setup` | `v4.3.0` | `b906affcce14559ad1aafd4ab0e942779e9f58b1` |

### Platform and systemd claim audit

Repository claims are consistent: OpenCloudOS 9 x86_64 is real-host validated;
Ubuntu 24.04 is CI validated without PID 1/native-host evidence; Rocky 9 and
Debian 12 are fixture validated; Ubuntu 22.04 native installation and aarch64
are unsupported. No preview was promoted to supported.

The live unit scores remain API `1.4 OK`, Worker `0.6 SAFE`, Runtime `3.7 OK`,
and Helper `0.9 SAFE`. API/Worker/Helper retain the tested syscall filter;
Runtime retains HOME/project writes, AF_UNIX/INET and host networking,
namespace capability for bubblewrap-compatible workflows, executable-memory
compatibility for Node/V8 tools, and broad third-party CLI syscalls. Individual
namespace/JIT/syscall restrictions were not enabled experimentally on the
stable host merely to improve a heuristic score; they remain explicit accepted
compatibility findings until isolated VM evidence can cover Codex, Claude,
bubblewrap, Node, Git/gh, tmux, and future supported versions.

### Final regression and host evidence

- Python: Ruff, Black, strict mypy, 510 pytest cases, and Alembic
  upgrade/downgrade/re-upgrade pass. `pip-audit` reports no known vulnerability.
- Web: lint, formatting, typecheck, 25 Vitest cases, build, and high-level pnpm
  audit pass with no known vulnerability.
- Deployment/security: 150 workflow-local tests pass; secret, privilege-boundary,
  forbidden-primitive, exact action-pin, and diff checks pass.
- Local Playwright reaches the 54-case runner but Chromium cannot load
  `libgbm.so.1`; no host package was installed. GitHub E2E remains the required
  browser result for the final pushed head.
- The existing OpenCloudOS install remains release `0.2.10+dev.9`, journal
  `committed`, DB revision `0003_security_hardening`, integrity `ok`, and bound
  only to `127.0.0.1:8787`. API/Worker are `agentbox`, Runtime is
  `agentbox-runtime`, Helper is socket-activated root, and socket/home/project/
  environment/DB modes and owners match the design.
- Production Doctor returned `OK`. A synthetic production diagnostics export
  was 3,629 bytes, mode `0600`, contained only the seven allowlisted top-level
  sections and sharing warning, and did not contain the application secret. The
  temporary report was removed after verification.
- No service restart, release update/rollback, reboot, SSH/firewall/cloudflared,
  Project, Provider/Secret, or root Codex/Claude/tmux credential mutation was
  performed. Root Runtime evidence was inspected as process/file metadata only.

Post-push GitHub checks are deliberately not pre-claimed by this file. PR #30
may leave Draft only after the final head's Backend, Frontend, Security, E2E,
Deployment matrix, and `deployment-gate` results complete successfully.

## Phase 10 Recommendation

After human review and merge of this Draft PR, Phase 10 may prepare an MVP
release candidate: reproducible packaging, changelog/release notes, signed
artifact decision, optional SBOM, documentation polish, and release rehearsal.
It must not begin automatically. Phase 11 Provider/Secret/Runtime Continuity
remains planned only and not started.
