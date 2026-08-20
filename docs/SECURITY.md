# AgentBox Security Design

Status: Phase 1 design baseline

## Security Goals

1. A compromised Browser session or Web/API process must not become an arbitrary root shell.
2. Third-party Runtime compromise must be contained to the non-root Runtime identity and registered workspaces.
3. Existing host services and unmanaged sessions must remain untouched by default.
4. Secrets and temporary pairing material must not enter AgentBox persistence, logs, traces, fixtures, URLs, or analytics.
5. Every privileged or dangerous action must be attributable, bounded, confirmable, and recoverable where possible.
6. Unknown versions, paths, owners, or capabilities must fail closed.
7. Future ProviderDefinition metadata, Runtime Binding intent, config
   transaction, Secret custody, Runtime lifecycle, and continuity evidence must
   remain separate trust decisions.

Availability and recoverability are also security goals: one malformed Job must not exhaust the verified 2-vCPU/3.5-GiB host or corrupt state.

## Phase 3 Security Foundation

The implemented Phase 3 boundary uses one locally initialized administrator,
Argon2id password hashes, opaque 256-bit Session tokens, keyed token digests in
SQLite, absolute and idle expiry, revocation, a ten-active-session limit, and a
session-derived CSRF token returned only by no-store authenticated responses.
The cookie is `HttpOnly`, `SameSite=Strict`, `Path=/`, and becomes `Secure` in
production. No anonymous registration endpoint exists.

All state-changing Phase 3 HTTP requests require an exact allowlisted Origin
and Host; logout additionally requires `X-CSRF-Token`. Forwarded client
addresses are ignored unless the direct peer belongs to an explicitly
configured trusted-proxy network. Production rejects non-loopback binds,
missing/short application secrets, unsafe SQLite paths, and non-HTTPS remote
origins. Loopback HTTP remains a development-mode-only workflow; production
authentication origins require HTTPS and use `Secure` cookies.

Production requires the pre-created SQLite parent to be either the legacy
private application directory or the installer-managed root-owned sticky
`root:agentbox 1770` state directory. The sticky bit prevents the application
identity from replacing root-owned receipt/journal/backup names while allowing
SQLite to create its own WAL/SHM files. Database/WAL/SHM files are mode `0600`.

The login limiter keeps pseudonymous account, source, and combined buckets in
SQLite: five failures in five minutes cause a five-minute bounded lock. A
successful login clears its account/combined buckets but does not erase the
source spray-defense bucket. State therefore survives API restart. Expired rows
are deleted and a hard row cap fails login closed instead of allowing the table
to grow without bound. Backward wall-clock movement clamps both observations
and active lock duration rather than creating a multi-year lock.

Login request validation and exact Origin/Host checks run before the login
service is scheduled. The service checks the rate-limit buckets before the user
lookup and before any real or dummy Argon2 verification; a locked bucket never
performs the expensive verify. Accepted login work runs through
`asyncio.to_thread` only after acquiring a process-local semaphore. The default
`AGENTBOX_ARGON2_MAX_CONCURRENCY=2` is constrained to 1–4, bounding simultaneous
Argon2 work and keeping password verify, dummy verify, hash, and rehash off the
FastAPI event loop. Limiter decisions and updates use serialized SQLite write
transactions because admitted login workers can execute concurrently; a busy
database fails authentication closed after the configured bounded timeout.

Request bodies are capped before JSON validation, authentication request models
reject unknown fields, and request IDs use a bounded syntax. API errors never
return Python exceptions or validation input. Audit metadata is a bounded flat
allowlist and rejects password/token/session/CSRF/cookie/authorization keys.

## Default Network Policy

- Default bind: `127.0.0.1:8787`.
- Privileged Helper and Runtime Executor: UDS only, never TCP.
- Supported remote access patterns: Tailscale, Cloudflare Tunnel, VPN, or an HTTPS reverse proxy.
- Nginx/Caddy are optional operator-managed integrations, not MVP requirements or automatic installs.
- Direct `0.0.0.0`/non-loopback binding is disabled by default. A future explicit override must require a startup warning, a configured trusted-origin set, and documented TLS/auth controls.
- Forwarded headers are ignored unless the immediate proxy address is allowlisted. Host and Origin are validated.
- AgentBox never changes SSH, iptables, cloud security groups, Tailscale, or cloudflared without a later separately approved feature.

The Phase 0 host already runs cloudflared and wildcard services, and port 8000 is occupied. Installation must preflight its exact bind and treat existing network services as production dependencies.

## Administrator Authentication

### Bootstrap

- First administrator initialization is a local TTY CLI action, not a remotely open Web endpoint.
- The instance allows exactly one active AdminUser in the MVP.
- Password policy checks length and breached/common-pattern defenses without logging the candidate password.
- Passwords are hashed with Argon2id using a maintained library, per-password salt, and release-calibrated parameters. Only the encoded hash is stored.
- Web login password work is admitted through the bounded Argon2 semaphore and
  executed in a thread; excess login requests wait as coroutines before work is
  submitted to the thread pool.

### Login and Sessions

- Login returns a cryptographically random opaque session token with at least 256 bits of entropy.
- SQLite stores only a keyed hash/digest of the token; the raw token exists only in the cookie and process memory.
- Cookie attributes: `HttpOnly`, `SameSite=Strict`, narrow `Path`, bounded lifetime; `Secure` is mandatory for HTTPS remote access.
- Loopback HTTP is permitted only for a local connection/forwarding workflow. The UI warns when transport is not HTTPS; non-loopback HTTP is refused.
- Absolute and idle expiry, rotation after login/re-auth, logout revocation, password-change revocation, and a small maximum active-session count are required.
- Authentication responses are `Cache-Control: no-store` and must not expose whether an arbitrary username exists.
- Missing users execute the same dummy Argon2 verification as an ordinary
  invalid login unless the applicable rate-limit bucket is already locked.

### Login Rate Limiting

- Rate limits combine account, effective-client, and combined buckets with a
  bounded lock.
- Proxy client addresses are accepted only from configured trusted proxies.
- Bucket identities are keyed pseudonymous digests and persist in SQLite across
  API restarts; no raw password, username, token, or public address is stored in
  a rate-limit record.
- Lockout is bounded to avoid permanent administrator denial of service; local recovery is documented and audited.
- Phase 9 does not expose application-secret rotation. A future controlled
  rotation must treat existing Session digests as invalid and explicitly clear
  obsolete limiter buckets: their keyed identities cannot match after rotation,
  although retention would eventually remove them. Reinstall/update/rollback
  preserve the existing application secret and do not silently rotate it.

### Recent Authentication

Pair Code generation, update/rollback, authentication reset, permission changes, project deletion, and other high-risk actions require a recent password re-authentication marker bound to the current Session.

## CSRF and Browser Controls

- Every cookie-authenticated state-changing request requires an unpredictable CSRF token plus exact Origin/Host validation.
- The token is delivered outside URLs and is never logged. API clients using the local UDS use OS peer authorization instead of browser cookies.
- GET/HEAD/OPTIONS are side-effect free. Pairing is POST-only.
- SSE endpoints are read-only, require an authenticated session, validate Origin, and never carry Pair Codes or raw secret-bearing command output.
- A strict Content Security Policy, `frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, restrictive Referrer Policy, and no inline third-party scripts are required.
- Login and Pair pages must not load third-party analytics, fonts, or widgets.

### Phase 4 browser implementation

- The raw Session token remains only in the `HttpOnly` Cookie. `AuthProvider`
  stores safe user/Session metadata and CSRF only in process memory; neither
  `localStorage`, `sessionStorage`, nor IndexedDB is used for authentication.
- Initial routing waits for `auth/me`, preventing a transient Login render from
  becoming authenticated-content flicker. A centralized `401` handler clears
  in-memory state and returns the browser to Login without a retry loop.
- Logout sends the in-memory Session-bound CSRF header. A `403` permits one
  `auth/me` refresh and one retry; any further error is surfaced without
  recursion. Origin and Host remain server-enforced.
- Error messages are plain React text. Server request IDs are displayed only
  after matching the bounded request-ID syntax; no API object is rendered as
  HTML. `dangerouslySetInnerHTML`, `eval`, and remote scripts are absent.
- The router has no `next` or external redirect support. Navigation targets are
  compile-time same-application paths.
- Authenticated API responses use `Cache-Control: no-store`. The static shell
  carries no user state; Phase 8 must configure its reverse proxy so HTML is
  revalidated while immutable hashed assets may be cached.
- Runtime cards never infer state: unavailable data is `Unavailable`, and
  unimplemented capabilities are `Planned` or `Not Implemented`.
- The production build uses external hashed assets compatible with
  `script-src 'self'` and `style-src 'self'`; Phase 4 does not add
  `unsafe-inline`, `unsafe-eval`, wildcard CORS, analytics, or telemetry.

## Action Whitelists

No interface accepts a shell command. Requests carry an action enum and strong parameters, for example:

```json
{
  "action": "codex_pair",
  "runtime_installation_id": "rt_..."
}
```

They never carry this shape:

```json
{
  "command": "user supplied shell"
}
```

Each action definition fixes:

- executable discovery policy and allowed realpath roots;
- argv template and enumerated options;
- working-directory source;
- environment allowlist and fixed safe defaults;
- caller identity and required Linux execution identity;
- timeout, output-byte limit, line limit, and concurrency key;
- accepted exit codes and normalized error mapping;
- path/root/owner preconditions;
- whether a Job, recent-auth, Confirmation Challenge, or dry-run is required;
- redaction and persistence policy.

No action uses `shell=True`, `/bin/sh -c`, `eval`, string concatenation, untrusted unit/package names, or caller-selected executable paths.

Future Provider actions also reject raw config text, arbitrary config keys,
caller environment maps, filesystem paths, process arguments, and API keys.
They accept a `ProviderDefinitionID`, typed options, expected revision, approved
`RuntimeBindingID` intent, and opaque Secret reference only. Provider activation,
Runtime lifecycle, Secret rotation/removal, and rollback are revision-bound
transactions with separate impact plans and confirmations.

## Input and Parameter Validation

- Pydantic request models reject unknown fields for security-sensitive actions.
- IDs are opaque server-generated identifiers; user labels never become systemd unit, tmux, socket, file, or database identifiers directly.
- Project names use a conservative length/character policy and a separate generated storage key.
- Git URLs reject embedded username/password/token userinfo, control characters, local filesystem schemes, and unsupported transports.
- Timeouts, output limits, clone depth, recent-output lines, and pagination use server-set maximums.
- Environment starts from a minimal fixed map (`HOME`, `PATH`, locale, noninteractive flags) and accepts no arbitrary caller values.
- Every adapter validates the resolved executable again at execution time to detect replacement after planning.

## Path and Filesystem Safety

- Project requests use Project IDs, not arbitrary absolute paths.
- The database stores a relative storage key plus configured root; canonical absolute paths are derived server-side.
- Components open the configured project root first, then traverse with descriptor-relative/no-follow operations where supported.
- Every path component is checked for symlinks, mount changes, owner, mode, and containment both before and immediately before mutation.
- Cross-filesystem atomicity assumptions are forbidden; staging and final paths share a filesystem.
- Hard links, device nodes, FIFOs, sockets, setuid/setgid bits, and unexpected ownership in managed write targets are rejected.
- Archive extraction validates every entry, link target, size, count, and expanded total before writing.
- Web static serving has no route into `/srv/agentbox/projects`, Runtime HOME, `/etc/agentbox`, backups, or `.git` internals.

## Git and Repository Safety

- Git executes as `agentbox-runtime`, never root.
- Credential prompting is disabled in noninteractive Jobs; AgentBox never parses or stores GitHub tokens.
- Remote URLs are sanitized before persistence/display.
- MVP does not run arbitrary repo scripts or provide `git config --global safe.directory=*`.
- Git hooks from cloned repositories are not executed by AgentBox-controlled MVP operations. Later write/build workflows require a separate threat-model update.
- Recursive submodule initialization is off by default; enabling it later requires URL and path policy for every submodule.
- Repository contents are untrusted even when the clone source is trusted.

## Dangerous Operations and Confirmation Challenges

High-risk operations use two stages:

1. a preview/dry-run describes the exact action, target, state fingerprint, reversibility, and backups;
2. the server creates a short-lived, one-time Confirmation Challenge bound to administrator Session, action, target, request ID, and state fingerprint.

Execution requires recent authentication and the expected typed confirmation (for example the exact project name). A changed target fingerprint invalidates the challenge. Challenges store only a verifier hash and metadata, never credentials.

`--yes` may suppress a text prompt only for idempotent or reversible actions explicitly marked safe. It cannot bypass recent authentication or a server-issued challenge and is rejected for force push, hard reset, project deletion, backup deletion, auth reset, Runtime uninstall, system permission changes, or service replacement.

Permanent project deletion is not in the MVP. Its future design must first stop sessions, detect dirty/unpushed data, create/verify an optional backup, rename into a root-confined quarantine, wait a retention period, and require a second confirmation before erasure.

## Pair Code Handling

Pair Code generation is a secret-returning action with these mandatory controls:

- authenticated administrator, CSRF, Origin check, recent authentication, and Runtime Capability check;
- generated only by the non-root Runtime Executor through the public Codex CLI capability;
- hard timeout and small output cap;
- transient memory only, never SQLite/Job/Audit/journal/trace/fixture/cache/clipboard automation;
- one-time no-store response, short in-memory TTL, explicit UI countdown and clearing;
- generic Audit Event such as `codex_pair:succeeded`, never a code hash or masked suffix;
- exceptions and debug mode cannot render captured output;
- retry generates a new code rather than retrieving the old one.

### Phase 5 implemented controls

The Web/API route is `POST /api/v1/codex/pair-codes`. It has no request body,
requires the existing Session/Origin/Host/CSRF controls plus authentication no
older than ten minutes, and returns `Cache-Control: no-store` and `Pragma:
no-cache`. The Runtime process serializes Pair with start/stop and applies a
ten-second default cooldown. The CLI refuses Pair JSON and redirected output.

The controlled runner never logs. Pair stdout/stderr are limited to 4 KiB each,
are passed only to a conservative parser, and cannot enter normalized
exceptions. Audit records contain only actor, action, Runtime target, request
ID, result, and optional normalized error code. The React page keeps the value
in component memory, requires a separate explicit clipboard click, clears it on
Hide/navigation, and removes it after 90 seconds. That UI visibility timeout is
not represented as the third-party code's validity period.

Capability `unknown` is not authentication success. If a public Codex login
status is unavailable, AgentBox displays `Unknown`; it never opens Codex auth
files. An explicit public unauthenticated result blocks Pair.

## Provider, Secret, Config, and Continuity Security Boundary

Phase 11 Slice 1 implements non-secret Provider metadata and Slice 2 adds a
read-only Runtime capability boundary. Slice 3.1 adds only the Runtime-owned
Secret Store foundation; Secret provisioning, credential reconciliation or
delivery, configuration mutation, Provider validation/activation, and
continuity execution remain unimplemented.
`ProviderDefinitionID` identifies concrete normalized Provider configuration;
`RuntimeBindingID` expresses stable AgentBox binding intent and is never
permanently equated with a current Codex provider ID. Ordinary metadata may
contain name/type, credential-free base URL, model, wire protocol, typed options,
compatibility evidence, and an opaque Secret reference, but never a raw API key.

On Linux v1, Secret authority belongs only to `agentbox-runtime`; Control Plane,
Web/API/Worker, Control Plane SQLite, and Root Helper receive neither plaintext
nor ciphertext. The fixed foundation root is
`/home/agentbox-runtime/.local/share/agentbox/provider-secrets/v1`, with `0700`
directories and `0600` protected files. Explicit initialization creates a raw
32-byte CSPRNG root key, strict bounded non-secret `keyset.json`, and an empty
dedicated `store.sqlite3`; startup and read-only health never create or replace
key material. Missing/corrupt custody after initialization fails closed and
requires operator recovery or future re-provisioning.

The frozen envelope uses per-version 32-byte DEKs, HKDF-SHA-256 purpose-separated
KEKs, AES-256-GCM payload/wrap encryption with independent 12-byte nonces, and
RFC 8785 canonical associated data. The foundation exposes only private
in-memory seal/open verification and a fixed empty-store initialize command;
it has no provisioning, generic reveal, Runtime UDS action, or Provider call.
Python memory clearing is best effort and is not claimed as guaranteed
zeroization. Secret-record and DEK-envelope rows are database-immutable in the
v1 schema, and initialization creates schema plus metadata in one bounded
`BEGIN IMMEDIATE` transaction before the staged tree can be committed. Directory
and SQLite schema inventories are enumerated with fixed upper bounds; excess or
unexpected objects fail closed.
A fully compromised `agentbox-runtime` UID remains capable of
compromising Runtime-usable Provider Secrets.

WSL remains a separate Linux Runtime and must not share a writable Runtime
config directory with Windows native. No backend sources a shell environment
file. Secret material must not
enter argv, URL, process listings, avoidable ordinary TOML, CLI/Web output,
automatic clipboard, Web Storage, logs, Audit, Git, reports, Jobs, backups,
diagnostics, exceptions, or fixtures. Provider tests inject Authorization via a
trusted in-memory HTTP path or equally restrictive mechanism, never argv.

`ConfigTransactionManager` and the Runtime-specific adapter must snapshot the
complete transaction scope, parse and validate a candidate, preserve unmanaged
settings and original file nonexistence/permissions, detect concurrent edits,
reject symlinks/unsafe ownership, use restrictive temporary files and atomic
replacement, and restore Provider/Binding/Secret references plus Runtime
lifecycle on failure. Recovery is `Rollback verified` only after explicit
verification; otherwise it is `Rollback attempted`.

The future `CodexProviderConfigAdapter` edits only AgentBox-controlled typed
keys/blocks, prevents duplicate Provider blocks, and validates against the
then-current public Codex schema. Current TOML layouts, reasoning enums, wire
events, thread filtering, and storage formats are fixtures rather than stable
interfaces. Provider Manager is permanently forbidden from rewriting Codex
SQLite/session DB, JSONL, rollout, or thread metadata to manufacture migration
or continuity.

Provider tests are typed, bounded, cost-aware, and non-persistent. Network,
Authentication, Model Availability, Wire Protocol, Provider API, Runtime,
Remote, Thread Resume, Context Continuity, and Thread Discovery are independent
results. Official Provider tests do not run paid full inference by default.
Active-writer protection uses only public reliable signals; uncertainty requires
turn-complete confirmation rather than private-state mutation. Automatic
Provider failover is not planned.

### Phase 11 Slice 2 Runtime capability controls

The existing `runtime.sock` accepts one additional exact action,
`runtime.capabilities.query`, after filesystem and `SO_PEERCRED` UID/GID checks.
The protocol carries a registered `RuntimeInstallationID` and revision plus one
fixed capability-set enum; it has no command, path, environment, parser, TTL,
or arbitrary capability-list field. Runtime performs a fresh fixed read-only
collection and returns a strict bounded report with a fixed 60-second expiry.

Raw command output, selected/alternative paths, Runtime HOME, config/auth/tmux
paths, process/session details, private Codex/Claude state, Pair Codes, and
credentials are reduced away before the UDS response. The Control Plane
rechecks identity, revision, complete capability membership, timestamps, and
the RuntimeInstallation revision after IPC. Only allowlisted count/state
metadata is audited. Reports are not cached in SQLite and never manufacture
Provider compatibility evidence or adoption. The collector has no mutation,
Provider network, Secret, Helper, `sudo`, `systemctl`, or package-manager path.
Independent observations cannot erase or promote each other: tmux availability
is reported even when Claude is absent, while managed-session inspection
requires validated Claude, tmux, and exact AgentBox marker evidence together.

Fixed overall collection timeouts cancel in-flight read-only probes. The shared
runner handles external cancellation by synchronously terminating only the
process group it created, completing/cancelling its stdout, stderr, and wait
tasks, and re-raising `CancelledError`; pre-existing Runtime services, processes,
and tmux sessions are outside that authority. The capability client maps the
small expected Runtime error set to fixed local codes and collapses every other
valid remote code to `RUNTIME_CAPABILITY_REMOTE_ERROR`, discarding remote
messages and category/retry claims.

The same-UID Runtime compromise boundary remains: a compromised Runtime identity
can falsify Runtime-usable observations and compromise Runtime-accessible data.
Peer authentication, strict schemas, bounded probing, and Control Plane
revision checks provide defense in depth and workflow integrity, not isolation
from a fully compromised Runtime UID.

## Logs, Recent Output, and Audit

### Audit Events

Allowed fields:

- actor and authentication mode;
- action type;
- target type and opaque ID;
- request ID and Job ID;
- timestamp, result, duration class, and normalized error code;
- confirmation-required/confirmed booleans.

Forbidden fields include request/response bodies for secret actions, Pair Codes (even masked or hashed), tokens, cookies, passwords, OAuth codes, SSH keys, auth-file contents, complete process environment, and raw command output.

Future Provider audit metadata may record ProviderDefinitionID,
RuntimeBindingID, action, compatibility classification, continuity level,
config revision, rollback-verification state, and sanitized outcome. It must not
record a Secret value, API-key suffix/hash, Authorization header, provider
response body, raw Runtime config, or complete base URL when it can contain
userinfo/query credentials.

### Operational Logs

- structured fields and explicit allowlists, not arbitrary object serialization;
- journald is primary; optional files use rotation and restrictive permissions;
- Runtime stdout/stderr is normalized and bounded before logging;
- known-secret-pattern redaction is defense in depth, not permission to log sensitive streams;
- log level changes cannot enable auth/Pair output;
- request bodies for login, re-auth, Pair, settings, and confirmations are never logged.

### Claude Recent Output

Recent output is fetched on demand only from an exact marked managed tmux pane,
strips ANSI/control sequences, caps at 200 lines/24 KiB, is authenticated and
no-store, and is not persisted. Audit records only access metadata, never pane
text. Sanitation is not complete secret redaction. Raw continuous terminal
streaming is not an MVP feature.

## Phase 6 Claude/tmux Controls

- API/Web submit only `project_id`; Runtime resolves a configured-root immediate child and rejects traversal, absolute IDs, root/file/missing targets, root/project symlinks, inaccessible directories, and canonical escapes.
- bounded generated names and exact versioned markers separate managed from legacy/similar/colliding sessions; only exact marked targets may be captured or killed.
- tmux receives fixed operation argv and fixed absolute Claude argv; there is no shell string, raw tmux flag, PID/signal, `pkill`, or `kill-server` action.
- Workspace Trust/authentication use public evidence only, never private Claude files or automatic acceptance.
- per-project locks and a bounded tmux semaphore serialize lifecycle operations; tmux owns the long-running child.
- same-UID processes can tamper with a per-user tmux server; Phase 8 dedicated identity and systemd sandboxing remain required.

## UDS Security

- `helper.sock`: root-owned, group-readable/writable only by the AgentBox control identity, mode `0660`, created by systemd.
- `runtime.sock`: owned by `agentbox-runtime` and a narrow control group
  containing only authorized API/Worker identities, mode `0660`.
- servers verify `SO_PEERCRED` against the expected peer identity and reject
  unexpected peers even if filesystem permissions were misconfigured. Runtime
  checks an explicit UID set; production Helper checks explicit UID and
  primary-GID sets from a root-only environment file.
- messages are framed, versioned, size-limited, typed, request-ID-bound, and time-limited.
- sockets are below setgid/sticky `/run/agentbox`; symlink/socket replacement
  and stale inode checks fail closed.
- no UDS proxying over HTTP and no Helper TCP listener.

The Runtime protocol is JSON-line V1 with a 64 KiB frame limit and exact keys.
Codex actions remain parameter-free; Claude and Phase 7 Project/Git/GitHub
actions accept only their typed bounded fields and a validated relative Project
identifier. It has a bounded request ID and no path/executable/arbitrary argv/
environment/cwd/shell/tmux/PID/signal fields. Development may create only the local
`.agentbox-dev` socket parent. Production refuses a socket outside
`/run/agentbox` and never creates that system directory itself.

## Dependency and Supply-Chain Security

- lock Python and Node dependency graphs; review direct dependencies and generated lockfile changes;
- generate an SBOM and retain source/version/digest metadata for AgentBox releases;
- run dependency, secret, license, and static-analysis checks in CI;
- install only from mapped distribution packages or approved publisher origins;
- never execute `curl | sh` directly from a Web request. Download to root-owned staging, enforce TLS/host/size, capture digest, inspect publisher-provided verification, show plan, then execute only after approval;
- if a third party provides no signature/checksum, report that limitation and require explicit confirmation; do not invent verification;
- versioned releases are immutable and rollback remains available.

## Update Verification Direction

AgentBox releases should publish checksums and a cryptographic signature or build provenance attestation. The installer pins a requested version, verifies metadata before extraction, rejects downgrades unless explicitly confirmed, and records non-secret provenance. Signature format and release key governance require a later accepted ADR before the first public release.

## Vulnerability Reporting

- publish a private security-reporting channel in the future `SECURITY.md` at repository root;
- do not require reporters to open a public Issue for a vulnerability;
- acknowledge, triage severity, coordinate a fix/advisory, and credit reporters with consent;
- document supported versions and disclosure timelines before the first release;
- never include live tokens, Pair Codes, private repositories, or public IPs in reports.

## Security Release Gates

- threat-model test cases implemented and passing;
- no default public listener;
- no root Web/API/Worker/Runtime process;
- no arbitrary shell/argv/environment/path API;
- Pair Code non-persistence test passes across DB, journal, traces, errors, and restart;
- traversal, symlink, Git URL, hook, UDS peer, CSRF, rate-limit, and confirmation tests pass;
- install/update rollback tested;
- no unresolved Critical/High finding.
## Phase 7 Git security boundary

Project operations accept opaque IDs and Runtime resolves one canonical
non-symlink, Runtime-owned child beneath a non-symlink, non-group/world-writable
root. Clone allowlists GitHub HTTPS/SSH and disables local/file/ext protocols,
prompts, LFS smudge and recursive submodules. Fixed Git config disables hooks,
pagers, editors and external diff; repository/worktree-scope credentials, HTTP settings,
URL/protocol rewrites, SSH commands, filters, fsmonitor/worktree/proxy settings,
remote helper programs, includes and aliases fail closed. Pull is fast-forward
only against an explicit validated origin ref, Push uses an explicit non-forcing
origin refspec, and Pull/switch are blocked during an active managed Claude
session. Clone activation is atomic no-replace; rollback validates both Project
and staging markers before any recursive removal. Credentials and raw tool
output never enter API, logs, Audit or Jobs.

## Phase 8 Installation and Privilege Boundary

Phase 8 preserves `browser-facing process != root`. API and Worker run as
`agentbox`; Runtime runs as `agentbox-runtime`; only the socket-activated Helper
is root. The Helper protocol has no arbitrary command, service, path, argv,
environment, PID, signal, package, user, or mode field. Peer UID, frame size,
protocol version, exact schema, concurrency, and timeout fail closed.
Production Helper additionally validates the peer's primary GID, rejects a
second concatenated frame before dispatch, has an empty capability bounding
set, and can communicate only over AF_UNIX.

Installer mutation requires effective UID 0 and an exact checksum-reviewed
plan. Archive extraction rejects absolute/traversal paths, duplicate entries,
links, special files, and count/size overflow. Files use no-follow writes,
fsync, restrictive modes, root-owned ancestor validation, and atomic replacement. Existing unit/config/release
collisions are verified before mutation; unknown objects stop the transaction.

The application secret is CSPRNG-generated in a separate root-created
`root:root 0600` environment file, injected by systemd, never printed or logged,
and not directly readable by either service identity.
Runtime authentication remains exclusively in the Runtime user's HOME; root
authentication is neither read nor copied. Phase 11 Provider/Secret management
remains unimplemented.

SQLite backup uses the online backup API plus integrity verification, including
WAL-active databases. Upgrade is staged and health/version gated. Rollback
restores only the receipt-pinned AgentBox snapshot, removes stale WAL/SHM after
quiesce, and must verify service/sockets, health/readiness, reported version,
SQLite integrity, and exact migration revision before success is
reported. Unsigned checksum-only Phase 8 artifacts leave a documented
supply-chain residual risk.

The network default is loopback and trusted proxies default empty. Installer
never modifies SSH, firewall, cloudflared, reverse proxies, or TLS. Secure
cookies and exact HTTPS origins remain mandatory for authenticated production
browser use behind an operator-managed proxy.

## Phase 9 release-candidate hardening

- Login failure buckets are SQLite-persisted, automatically expired, row bounded, and keyed with the application secret; neither account text nor raw source address is stored.
- Password changes and session revocation are local TTY-only operations. The current password is required and a successful password change revokes every existing session.
- API, Worker, and Helper apply `@system-service` syscall filters. Runtime keeps a broader syscall/namespace/executable-memory surface for Codex, Claude, Node/V8, tmux, Git, and bubblewrap compatibility.
- Runtime and Helper reject duplicate/deep malformed JSON, invalid UTF-8, concatenated/oversized frames, unknown fields/actions/versions, and unbounded correlation IDs. UID and primary GID are checked with `SO_PEERCRED`.
- GitHub Actions use immutable commit pins. Checksums establish artifact integrity only, not publisher authenticity; signed distribution remains a Phase 10 gate.
- Job/Audit/login buckets and verified lifecycle artifacts have bounded retention. Cleanup protects active rollback identities and leaves unknown objects for operator review.

## Phase 10 release-candidate artifacts

The RC builder accepts only a clean tracked commit and an explicit source epoch.
It normalizes archive ordering, timestamps, ownership and modes, then verifies a
second independent build has the same SHA-256 in the same CI environment. The
artifact verifier rejects absolute or non-canonical names, traversal,
duplicates, case-fold collisions, links, sockets, devices, FIFOs, unexpected
executables, setuid/setgid/world-writable modes, undeclared files, digest drift,
version drift, migration drift, and platform mismatch.

The public bundle includes an external manifest, SPDX 2.3 SBOM and
`SHA256SUMS`. Checksums are an integrity control only. No signing key is created
or used in Phase 10, so publisher authenticity remains unverified and must not
be inferred from a successful checksum. The PR workflow is read-only, uses
immutable Action pins, receives no release/signing secret, publishes only a
short-lived CI artifact, and cannot create tags or GitHub Releases.
