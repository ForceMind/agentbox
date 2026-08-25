# AgentBox Threat Model

Status: Phase 1 baseline updated through Phase 11 Slice 3.2a Control Plane
ownership and approval architecture authorization review
Method: pragmatic STRIDE-style analysis focused on AgentBox trust boundaries.

## Scope and Assets

In scope: Web/API, browser sessions, CLI/API socket, Worker, SQLite, Runtime Executor/socket, Privileged Helper/socket, Project Workspaces, Jobs, Audit Events, installer/update/backup paths, Codex/Claude/tmux/Git/gh invocation, future Provider definitions/Runtime bindings/Secret backends/config transactions/continuity assessment, and external access integrations.

Primary assets:

- root authority and host integrity;
- administrator account/session;
- Runtime authentication held by third-party CLIs;
- one-time Pair Codes;
- private source repositories and uncommitted work;
- SQLite state, Job integrity, settings, Audit Events, and backups;
- update artifacts and release provenance;
- availability of existing host services.
- future Provider metadata/config integrity, Runtime binding and continuity
  evidence, rollback recoverability, and API-key confidentiality.

Out of scope for the MVP: protection against a malicious root administrator, a fully compromised kernel/hypervisor, or security guarantees inside third-party SaaS. AgentBox must still avoid worsening those conditions.

## Actors

- legitimate single administrator;
- unauthenticated remote attacker;
- attacker with a stolen browser session;
- malicious or compromised Git repository/dependency;
- compromised Web/API, Worker, Runtime, or third-party CLI process;
- local unprivileged user;
- malicious/compromised package or update origin;
- accidental operator error.

## Trust Boundaries

TB1: remote client to loopback/private/proxied Web endpoint.
TB2: browser session to `/api/v1`.
TB3: API/CLI input to Application Services and Job records.
TB4: authorized API/Worker client to Runtime Executor.
TB5: Worker to root Privileged Helper.
TB6: Runtime Executor to Project Workspaces and third-party CLIs.
TB7: installer/updater to external repositories/artifacts.
TB8: live state to backup/export media.
TB9: the Phase 11 non-secret Provider Registry and Runtime Binding metadata is
present; the Runtime-owned Secret Store, Config Transaction Manager, Runtime
Continuity Manager, Runtime configuration/lifecycle mutation, and external
model/API Provider operations remain future, separately authorized boundaries.

Phase 11 Slice 2 narrows TB4 with `runtime.capabilities.query`: the Control
Plane supplies only a registered Runtime identity/revision and fixed capability
set; Runtime returns bounded typed observations over the existing UDS. There is
no database cache, public endpoint, new transport, Helper path, or mutation
authority.

## Threat Register

| ID | STRIDE | Threat | Boundary/assets | Required controls | Verification |
|---|---|---|---|---|---|
| T-01 | S/E | Unauthorized Web access | TB1/TB2, admin/session | loopback default, HTTPS integration, Argon2id, rate limits, session expiry | remote-bind and auth integration tests |
| T-02 | T/E | CSRF issues a privileged/runtime action | TB2 | SameSite, CSRF token, Origin/Host checks, no GET mutations | cross-origin negative tests |
| T-03 | S | Session hijacking/replay | session cookie | random token, hash at rest, HttpOnly, Secure on HTTPS, rotate/revoke, short idle lifetime | token-storage and replay tests |
| T-04 | D | Brute-force login/lockout abuse | auth | account+client throttles, exponential delay, bounded recovery | rate-limit/time tests |
| T-05 | E | Arbitrary command execution | TB3/TB4/TB5 | action enums, fixed argv, no shell, strict schemas | command-injection corpus |
| T-06 | T/E | Option/argument injection | Runtime/helper commands | `--` delimiters where supported, enums, length/control-char rejection | leading-dash/metacharacter tests |
| T-07 | E | Environment/PATH hijack | process execution | minimal env, fixed/configured+verified executable, realpath recheck | malicious PATH/env tests |
| T-08 | E/T | Helper socket abuse | TB5/root | `0660`, isolated group, `SO_PEERCRED`, schema/version, action allowlist | wrong-UID/socket-replacement tests |
| T-09 | E | Runtime socket used to reach root | TB4/TB5 | separate sockets/protocols/groups; Runtime has no Helper credentials | cross-protocol and group tests |
| T-10 | T | Path traversal | Projects/backups/releases | opaque IDs, canonical root, descriptor-relative traversal, reject `..`/absolute paths | traversal property tests |
| T-11 | T/E | Symlink/hard-link race escape | filesystem | no-follow operations, owner/mode checks, same-FS staging, revalidation | race/symlink/hard-link tests |
| T-12 | T/E | Malicious Git repository content | TB6/projects | non-root Runtime, no build, hooks disabled, bounded output, treat contents untrusted | malicious repo fixtures |
| T-13 | T/E | Git hook execution | Git operations | no AgentBox-controlled hook-triggering write/build flows in MVP; fixed hooks policy | hook fixture remains unexecuted |
| T-14 | T | Git submodule path/URL escape | Project Workspace | recursive submodules disabled; future per-entry validation | `.gitmodules` attack fixtures |
| T-15 | I | Credential embedded in Git URL | API/DB/log | reject userinfo; sanitize remote; no credential prompt | URL and log scans |
| T-16 | S/E | tmux session hijacking/collision | Runtime sessions | Runtime-owned socket, opaque names, managed registry, refuse unmanaged collision | fake socket/name tests |
| T-17 | I | Pair Code leakage | TB2/TB4, logs/DB | recent auth, ephemeral memory, no-store, never Job/SSE/audit body | end-to-end secret canary scan |
| T-18 | I | Log/recent-output leakage | journal/UI | structured allowlist, bounds, redaction, no raw bodies/env; ephemeral pane output | log canary and ANSI tests |
| T-19 | E | Web/API reads Runtime auth/project data | process/filesystem | separate UID/HOME; no project mount/read permission; typed Runtime read models | Linux permission tests |
| T-20 | E | Root Helper invokes Runtime as root | helper | explicit prohibition; Runtime Executor identity; unit tests on action registry | allowlist inspection/integration test |
| T-21 | T | Job payload/database tampering changes target | Jobs/SQLite | typed persisted payload, state fingerprint, revalidation at execution, DB permissions | DB mutation/fingerprint tests |
| T-22 | R | Audit repudiation | Audit Events | actor/request/action/target/time/result; append policy; clock/rotation monitoring | audit completeness tests |
| T-23 | I | Audit stores secret | Audit/DB | field allowlist, Pair/login body suppression, secret canaries | schema and persistence scans |
| T-24 | D | Unbounded command/output/job exhausts host | availability | timeout, bytes/lines, concurrency=1 default, quotas, cancellation, disk thresholds | stress/timeout/output-bomb tests |
| T-25 | T/D | Blind Job replay after crash | Job recovery | leases, attempts, idempotency class, uncertain mutation → `needs_attention` | crash-at-step fault injection |
| T-26 | T/E | Malicious update/package | TB7/root | pinned version, approved origins, digest/signature/provenance, staged extraction, rollback | tampered artifact tests |
| T-27 | T | Archive extraction escape/bomb | releases/backups | entry/path/link/type/count/size validation, staging | archive attack corpus |
| T-28 | I/T | Backup leaks secrets or restores wrong owner | TB8 | manifest allowlist, encryption left to operator-approved mechanism, no auth homes, UID mapping plan | backup inspection/restore tests |
| T-29 | E | Old root services are adopted silently | existing host | unmanaged classification, explicit adoption challenge, no automatic stop/change | Phase 0 fixture/adoption tests |
| T-30 | I/S | Proxy header spoofing | TB1 | trusted-proxy allowlist, ignore other forwarded headers, exact origins | spoofed header tests |
| T-31 | T | Database corruption/migration failure | SQLite | backups, integrity check, transaction/migration discipline, rollback gate | migration fault injection |
| T-32 | E | Dependency executes install/build code | build/runtime | lock/review dependencies, minimal production artifact, no project build in MVP | dependency review/SBOM |
| T-33 | T/I | Existing cloudflared route exposes AgentBox | external integration | never auto-edit/reuse; explicit proxy/access review; loopback bind | deployment checklist |
| T-34 | T/E | UID/GID 1001 reuse gives write access to Codex artifact | current host | collision check and ownership remediation before identity creation | pre-install owner/UID gate |
| T-35 | T/I | DOM XSS through API text or request ID | TB2/browser | React text rendering, bounded error text, request-ID syntax, no raw HTML | unit hostile-ID and browser rendering tests |
| T-36 | I | Session/CSRF leaks into browser storage | browser/session | HttpOnly Session, CSRF in memory, no auth Web Storage writes | unit and Playwright storage inspection |
| T-37 | S/I | Stale frontend auth state shows protected data | TB2/browser | boot gate, centralized 401 clearing, protected route guard | refresh/invalid-cookie/401 tests |
| T-38 | T/D | CSRF refresh creates an unbounded retry loop | TB2 | exactly one `me` refresh and one logout retry | deterministic component test |
| T-39 | S | Login redirect becomes an open redirect | browser routing | no `next` parameter; compile-time local routes only | route inspection and external-URL search |
| T-40 | S/I | Clickjacking overlays authenticated controls | browser | CSP `frame-ancestors 'none'` plus `X-Frame-Options: DENY` | response-header tests |
| T-41 | I/T | Malicious request ID injects or corrupts UI | API/browser | server syntax plus client syntax revalidation and text rendering | malformed-header and client-parser tests |
| T-42 | E | Client-side route guard is treated as authorization | TB2 | every protected API authenticates server-side; guard is UX only | unauthenticated Doctor/auth tests |
| T-43 | R/I | Fake UI status misleads the operator | browser | only real health/readiness/meta data; explicit Planned semantics | component and E2E assertions |
| T-44 | I | Browser/proxy cache retains authenticated data | TB1/TB2 | no-store auth/Doctor responses; static shell contains no user state | response-header tests and deployment gate |
| T-45 | S/E | Fake Codex executable wins PATH resolution | TB4/TB6 | fixed Runtime PATH, resolve/stat/mode validation, no caller path, revalidate fingerprint | fake PATH and unsafe-mode fixtures |
| T-46 | T/E | Codex executable replaced after validation | TB6 | absolute realpath plus device/inode/mode/size/mtime recheck immediately before spawn | replacement test; residual kernel-exec TOCTOU documented |
| T-47 | I/T | Malicious CLI output injects UI/log/error content | TB6/TB2 | bounded decoding, typed parsers, React text nodes, no raw output response | malformed/ANSI/oversize fixtures |
| T-48 | I | Pair Code leaks, replays, or remains stale in UI | TB6/TB2 | sensitive buffer, conservative parser, no-store, cooldown, memory-only display, explicit copy, timed/navigation clear | DB/log/audit/artifact/browser canary scans |
| T-49 | D/T | Concurrent Remote actions duplicate or reorder daemon state | TB4/TB6 | one Runtime action lock, idempotent known-state results, public command only | concurrency/state-transition tests |
| T-50 | E/D | Stop targets an unrelated process | TB6 | official stop command only; strict same-UID process evidence is read-only; no pid/pkill/kill action | unrelated-process fixture and boundary scan |
| T-51 | D | Codex hangs or emits unbounded output | TB6 | per-action timeout, separate byte caps, spawned-process-group cleanup | timeout/output-bomb tests |
| T-52 | I/E | API environment secrets reach Codex | TB4/TB6 | separate process plus HOME/PATH/locale/XDG allowlist; no caller env | environment canary test |
| T-53 | E | Caller controls Codex cwd | TB4/TB6 | no cwd field; Runtime HOME is fixed server-side and must exist | protocol exact-schema and runner cwd tests |
| T-54 | T | npm metadata poisons installation classification | TB6 | fixed npm argv, bounded JSON, known names as hints only, conflict/unknown without mutation | malformed/npm conflict fixtures |
| T-55 | S/T | Legacy `codex.service` confused with managed daemon | existing host/TB6 | presence is warning only; never adopted, started, stopped, or called authoritative | host read-only check and UI diagnostic review |
| T-56 | T/D | Third-party CLI changes command/help/output semantics | TB6 | capability detection from current public help, tri-state degradation, exact fixtures, fail-closed mutations | old/malformed/future-help fixtures |
| T-86 | I | Capability report leaks Runtime paths, raw output, auth or session data | TB4/TB6 | exact report schema, closed codes, bounded reduction, no paths/output/config/private session fields | canary serialization, DB/WAL/SHM, Audit, log and exception scans |
| T-87 | T/R | Runtime capability evidence is mistaken for permission, adoption, or Provider compatibility | TB3/TB4 | separate evidence domain, no cache/adoption, explicit outcome/lifecycle, internal-only service | repository and reachability tests |
| T-88 | D/E | Caller turns capability discovery into arbitrary or unbounded execution | TB4/TB6 | one action, two fixed sets, fixed probes/TTL/timeouts/output caps, per-type single flight, no caller command/path/env/parser | protocol fuzz, concurrency and mutation-absence tests |
| T-89 | S/T | Forged, stale, or mismatched Runtime report crosses a revision boundary | TB3/TB4 | UDS peer credentials, exact contract, ID/type/set/revision echo, post-IPC revision reread, expiry rejection | wrong-peer and mismatch/race fixtures |
| T-90 | D/E | Outer capability timeout cancels a probe but leaves its child process running | TB6 | external cancellation terminates only the invocation-owned process group, completes I/O/wait tasks, re-raises cancellation, then releases single flight | real child PID cancellation and collector recovery tests |
| T-91 | I/T | Runtime exfiltrates bounded text through a capability RPC error code or message | TB4 | exact envelope, closed expected-code mapping, fixed unknown-code collapse, discard remote message/category/retry semantics | error-code/message canary, Audit/log/serialized exception tests |
| T-92 | I/E | Provider Secret crosses into Web/API/Worker or Control Plane SQLite | TB3/TB9, Provider credentials | Runtime-only authority; opaque `sec_*` reference/version only; no Secret-bearing API, model, event, log, or database field | schema/reachability inspection and Secret canaries across API/DB/WAL/SHM/Audit/logs |
| T-93 | T/E | Symlink, hard link, ownership drift, or path race redirects the Runtime Secret Store or root key | TB9/Runtime filesystem | fixed Runtime-owned root; no caller path; ancestor/final no-follow checks; regular single-link files; exact UID/GID/modes; same-parent atomic commit and revalidation | parent/final link, owner/mode, swap-race, and inode tests |
| T-94 | T/D | Missing or corrupt root key is silently replaced while encrypted records exist | TB9/key custody | startup never creates keys; replacement prohibited when any store/keyset/record evidence exists; subsystem unavailable and explicit recovery/re-provisioning required | missing/partial/corrupt state matrix and no-generation spy |
| T-95 | T/I | Ciphertext, wrapped DEK, or record is substituted across Credential, Runtime, version, or key identity | TB9/envelope | exact RFC 8785 AAD binds Runtime/Credential/Secret/version/DEK/key identities; AES-256-GCM tag verification; immutable records | wrong-AAD/identity/version/key/tag/ciphertext adversarial tests |
| T-96 | T/I | AES-GCM nonce reuse or uncertain crash state compromises payload/DEK confidentiality | TB9/cryptography/store | independent CSPRNG nonces; unique wrap-nonce index; one payload per DEK; immediate transaction; uncertain result blocks further use; KEK retired before `2^32` wraps | collision injection, crash-boundary, uniqueness, and wrap-count tests |
| T-97 | I | Secret leaks through TTY ingress, argv, environment, temporary file, exception, diagnostic, or test output | TB3/TB9/process | local real-TTY input only in later slice; echo restoration; fixed non-secret argv; no env/file/clipboard ingress; bounded codes; best-effort memory cleanup | TTY failure matrix and cross-surface canary scan |
| T-98 | S/T | Forged or replayed provisioning result attaches an arbitrary Runtime Secret reference to Credential metadata | TB3/TB4/TB9 | future expiring single-use authorization binds exact Runtime/Provider/Credential revisions and purpose; Runtime generates reference; Control Plane accepts typed attestation only after revision recheck | replay, stale-revision, wrong-peer, crash-uncertainty, and fabricated-reference tests |
| T-99 | I | Ordinary backup, migration, release, or uninstall captures Secret Store/key material | TB7/TB8/TB9 | ordinary backup and release allowlists exclude fixed store; update/rollback/default uninstall preserve in place without copying; cross-host recovery re-provisions | archive/manifest canaries, uninstall/update preservation, and fixture-root inspection |
| T-100 | I/E | Compromised Runtime UID uses a generic vault/decrypt interface to harvest every Provider Secret | TB6/TB9 | no generic get/list/reveal/export; typed purpose/revision-bound operations; admission and transaction policies in later slices; same-UID compromise remains explicit residual risk | operation allowlist, cross-purpose denial, and no-raw-response tests |
| T-101 | T/D | Store corruption or interrupted key/Secret rotation is auto-repaired, deleted, or falsely reported healthy | TB9/store/recovery | bounded schema/integrity checks; preserve evidence; fail closed to `NEEDS_ATTENTION`; distinct Provider-Secret and root-key rotations; verified references before pruning | corrupt-page/schema/keyset, interrupted rotation, health-code, and no-delete fault tests |
| T-102 | S/T | A Runtime-local `sec_*` reference is attached to a Credential owned by another Runtime installation | TB3/TB4/TB9 | one V1 Credential has one explicit database-enforced Runtime owner; authorization, Store record, attestation, and reconciliation bind the same Runtime/revisions | cross-Runtime Credential, profile-derivation ambiguity, forged attestation, and direct-database tests |
| T-103 | S/R/E | Recent authentication, a Job lease, or a fabricated digest is treated as provisioning approval | TB3/TB4 | durable purpose-specific `ConfirmationChallenge`; exact actor/session/Runtime/Provider/Credential revisions; five-minute expiry, cancellation, and atomic single use | missing/expired/cancelled/wrong-purpose/stale-revision/replayed challenge tests |
| T-104 | I | Secret leaks through echo, signal handling, timeout, terminal middleware, or an overstated paste-prevention guarantee | TB9/TTY/process | real controlling TTY only; echo restored on every path; one bounded entry; no clipboard integration; hard expiry/input deadline; no claim that portable TTY APIs prevent paste | PTY echo/signal/timeout/EOF/paste canaries across argv/env/log/diagnostic/output surfaces |
| T-105 | T/R | Intent expiry or revision change races plaintext entry and permits an unauthorized late commit | TB3/TB4/TB9 | durable `CONSUMING` before input; effective deadline is the earlier of 90 seconds and intent expiry; exact tuple revalidated inside the write transaction; no grace or replay | expiry-during-input, revision race, cancellation, lease loss, and clock-boundary tests |
| T-106 | T/D | Envelope rows commit without the KEK wrap counter, or the counter advances without the envelope | TB9/store | one `BEGIN IMMEDIATE` transaction binds intent, envelope, immutable record, and one counter increment; uncertain material is never reused | fault injection at every statement/commit/fsync boundary and wrap-nonce collision tests |
| T-107 | T/D | Crash after record commit but before plaintext comparison causes blind replay, silent deletion, or false live verification | TB9/store/recovery | atomic `COMMITTED_UNVERIFIED`; exact linked record is reopened and AEAD-verified under a distinct recovered mode; contradiction becomes `NEEDS_ATTENTION`; no overwrite/delete | crash-after-commit matrix, linkage/AAD/tag corruption, recovery-mode and no-replay tests |
| T-108 | T/R/D | Runtime commit succeeds but Control Plane reconciliation fails, leaving a record that is rebound, activated, or silently discarded | TB3/TB4/TB9 | retained unreconciled orphan tied to one intent; ineligible for use; bounded status retry; exact revision recheck; no rebinding/deletion in initial provisioning | Control Plane rollback/restart/stale-state/retry/expiry and cross-Credential orphan tests |
| T-109 | S/T/R | A forged or replayed Runtime attestation configures a Credential more than once or after expiry | TB3/TB4 | peer-authenticated UDS, exact typed attestation, durable challenge and attestation consumption, conditional `MISSING` revision update, bounded retention | wrong peer/ID/revision/digest/schema, duplicate, expired, reordered, and post-consumption replay tests |
| T-110 | T/D | Runtime Store v1 is silently altered, partially migrated, or unsafely opened by older code | TB9/store/upgrade | explicit v2 schema and user version; locked atomic fixed migration; exact inventory and read-back; failure preserves v1 or enters `NEEDS_ATTENTION`; older code fails closed and preserves bytes | empty/non-empty v1, crash-at-DDL/commit/fsync, unexpected-object, downgrade, and old-reader tests |
| T-111 | I/E | Provisioning intent enumeration or a compromised Runtime UID turns bounded provisioning state into a generic Secret capability | TB4/TB9 | no list action; exact `psi_*` lookup; fixed retention/pruning; no reveal/export; same-UID compromise remains an explicit residual risk | action-allowlist, enumeration, retained-attestation, generic-get, and compromised-UID threat review |

### Phase 11 Slice 3.2a Control Plane ownership and approval threats

| ID | STRIDE | Threat | Preconditions | Impact | Required controls | Validation approach | Residual risk |
|---|---|---|---|---|---|---|---|
| T-112 | T/E | Legacy Credential ownership is assigned automatically or ambiguously | pre-`0005` Credential metadata exists during upgrade | a `sec_*` may later resolve against the wrong Runtime Store | reject `0005` unless `SELECT COUNT(*) FROM provider_credentials` is zero; no inference, adoption, duplication, deletion, or synthetic owner | upgrade fixtures for every Credential state, reference/version shape, profile reference, and zero/one/many Runtimes | separately authorized operator recovery may be required for development metadata |
| T-113 | S/T | A Runtime Profile references a Credential owned by another Runtime | service validation is bypassed or a stale/crafted profile is inserted | cross-Runtime Secret use and false configuration intent | non-null Credential owner plus composite `(credential_id, provider_id, runtime_installation_id)` FK and service revalidation | repository and direct-SQL cross-Runtime tests with foreign keys enabled | a fully compromised Control Plane DB/application identity can rewrite coordinated authority state |
| T-114 | T/E | Credential identity is moved or reinterpreted after creation | attacker updates ID, Provider, Runtime owner, kind, or creation time through ordinary/direct SQL | an opaque Secret reference changes Provider, Store, or credential-kind meaning | no identity-update method; one null-safe `IS NOT` trigger freezes all five identity fields; only typed lifecycle fields remain mutable | ORM/update absence scan and direct-SQL test for every frozen/allowed field | database owner with power to replace schema/triggers is outside workflow-integrity protection |
| T-115 | T/D | Global Provider uniqueness blocks or confuses multi-Runtime credentials | one Provider is used on multiple Runtime installations | second Runtime is unavailable or incorrectly shares the first Store identity | unique `(provider_id, runtime_installation_id, kind)`; one `API_KEY` per pair; separate Credential IDs across Runtimes; Claude rejected | cardinality and constraint inspection tests | V1 cannot hold two simultaneously usable API keys for one Provider/Runtime pair by design |
| T-116 | S/T/R | A forged, replayed, or cross-purpose challenge authorizes provisioning | attacker knows an opaque ID or replays a prior request | unauthorized or repeated provisioning intent | server-generated 128-bit ID, closed purpose, exact typed tuple, durable terminal state, five-minute TTL, atomic single use | malformed/unknown/wrong-purpose/replayed/concurrent challenge tests | full Control Plane compromise can forge rows and application decisions |
| T-117 | T | Canonical digest ambiguity, cross-purpose substitution, or unapproved intent replacement changes the reviewed plan | serialization is ambiguous or `psi_*` is generated after approval | approval binds a different Runtime/Provider/Credential/postcondition or Runtime intent | challenge and `psi_*` issued together; domain-separated SHA-256 over RFC 8785 exact tuple including intent ID/version/times/epoch; no replacement | golden vectors plus post-issue/consume intent substitution and collision tests | digest is not a signature or protection from a compromised Control Plane |
| T-118 | S/E | Challenge is rebound to another Admin/Session or newer authentication epoch; re-auth leaves old browser credentials valid | same Admin logs in/re-authenticates elsewhere, direct SQL mixes identities, or token/CSRF are not rotated | one context consumes another context's approval or stolen old credentials survive re-auth | composite `(session_id, admin_id)` FK; durable auth epoch/time; re-auth rotates token hash and CSRF verifier while preserving Session row ID and absolute expiry; prior-epoch challenges cancel atomically | direct-SQL Admin/Session mismatch, second login, re-auth old Cookie/CSRF, timestamp, newer-epoch and crash tests | theft of the exact replacement browser Session remains within normal Session risk |
| T-119 | T/R | Session revocation races challenge consumption | logout, password reset, eviction, or revoke occurs concurrently with consume | revoked authority might win after invalidation | both paths use `BEGIN IMMEDIATE`; invalidation cancels issued challenges in the revocation transaction; exactly one serialized winner | revoke/consume barriers and crash injection | a transaction committed before revocation is valid and remains durable by ordering |
| T-120 | T/R | Cancellation races consumption or two consumers both succeed | concurrent requests target one issued challenge/attempt | duplicate attempts, false cancellation, or contradictory terminal evidence | conditional Challenge transition; exact Attempt cancellation state machine including `CANCEL_PENDING`; one unresolved-attempt partial index including `NEEDS_ATTENTION`; serialized winner | consume/consume, consume/cancel, Runtime-consuming/cancel, lost-ack and commit-failure tests | SQLite/Runtime unavailability can deny service but cannot create two committed winners |
| T-121 | T/E | Runtime, Provider, or Credential changes between issue and consume | entity revision/state/ownership is mutable during five-minute window | approval applies to an unreviewed target | bind exact revisions/state/null postcondition; reload every entity inside serialized consumption; stale becomes terminal rejection | mutation-at-each-step and direct-database mismatch tests | coordinated full database compromise is outside the guarantee |
| T-122 | T/E | Five-minute expiry is extended by restart or backward clock movement | wall clock moves backward or process restarts | stale approval becomes eligible longer than reviewed | persisted UTC issue/expiry/last-observed times; `now >= expires_at` fails; backward observation cancels; no renewal | equality, restart, forward/backward-clock, timezone and serialization tests | sufficiently compromised host time before issue can affect timestamp truth; root is trusted |
| T-123 | I/S | Error differences enumerate challenge existence, actor, owner, or terminal state | attacker can submit guessed `cch_*` IDs | workflow and target metadata disclosure | 128-bit IDs; normalized closed public codes/status/size; wrong actor reveals no tuple/state; no list endpoint | malformed/unknown/wrong-actor timing, body, status, and size comparisons | traffic timing remains best-effort and an authenticated issuer sees bounded status for its own challenge |
| T-124 | D/I | Authority rows grow without bound, are pruned too early, or inconsistent batch limits exceed the bound | repeated issue/terminal transitions, direct SQL deletion, or maintenance category fan-out | disk exhaustion, reopened admission, or loss of replay/reconciliation evidence | immutable stored `terminal_at+30d` eligibility; DB delete guards using transaction UTC6 clock; unresolved `NEEDS_ATTENTION` never pruned/deleted and blocks one Credential; one deterministic union limits all categories to 100 total | volume, exact boundary, direct delete at arbitrary ages, global total/category/order, protected-row and contention tests | unresolved evidence persists until a separately authorized lifecycle action; one row per Credential bounds retries |
| T-125 | T/R | Challenge is deleted while issued or while provisioning orchestration still needs it | direct SQL or independent retention jobs race/run out of order | approval/admission fence or recovery correlation is erased | Challenge delete trigger rejects issued/null-boundary/referenced/inconsistent rows; delete terminal Attempt before Challenge; composite FK `RESTRICT` | issued/direct-delete, FK race, pre/post-boundary and Attempt-first deletion tests | safely terminal metadata disappears after its reviewed retention period |
| T-126 | T/R | Append-only Audit is treated as authoritative orchestration state | recovery code queries Audit after a crash | history is replayed as current authorization or mutable state | dedicated `ProviderSecretProvisioningAttempt`; Audit is evidence only and never a transition source | boundary scan and crash tests with missing/reordered Audit fixtures | Audit loss reduces forensic evidence but must not change workflow authority |
| T-127 | T/E | Generic Job JSON or lease is treated as approval authority | implementer reuses current Job payload/idempotency/lease | caller-controlled generic data authorizes Secret provisioning | no provisioning Job type/payload; typed challenge and narrow attempt columns only | model/API/worker reachability scans and hostile Job fixtures | generic Job compromise can affect other supported work, not this approval path |
| T-128 | T/D | Attempt insert commits without Challenge consumption, or Challenge consumes without its exact Attempt | direct SQL/application fault separates two statements | replay fence and durable recovery disagree | `BEFORE INSERT` exact validator plus `AFTER INSERT` conditional Challenge update with `changes()=1`/`RAISE(ABORT)`; reverse consume trigger remains active; Audit shares transaction | successful handshake, failure-after-insert rollback, direct consume, tuple/`psi_*`/digest/request mismatch and concurrency tests | full Control Plane DB compromise can replace triggers |
| T-129 | T/I/D | Unsafe `0005` runner phase/order, preflight race, partial commit, or forbidden Audit metadata loses authority/leaks values | FK mode contract contradicts revision, writers mutate after outer preflight, schema/version split, or sanitizer rejects Audit | invalid schema/FKs, partial version, activation of incompatible code, DoS, or leaked derivatives | deployment lock/writer fence/backup; FK-ON outer checks; FK-OFF `BEGIN IMMEDIATE` rechecks; schema/version atomic commit; post-check restore gate; exact sanitizer-compatible keys | exceptions before body/after DDL/after version, post-commit failure restore, FK/schema/trigger inventory, sanitizer and WAL/SHM canaries | verified backup restoration is required after a committed-but-unverified migration; full Control Plane compromise remains residual |
| T-130 | T/D | Credential rebuild removes the exact parent key required by untouched Compatibility Evidence | `uq_provider_credentials_id_provider` is dropped while its child FK remains | SQLite reports foreign-key mismatch or evidence writes bypass/fail | retain `(id, provider_id)` unique key; add Runtime-scoped keys separately; do not rebuild evidence table | schema inspection plus valid and invalid child inserts after rebuild and downgrade | redundant unique keys add schema complexity but preserve narrow compatibility |
| T-131 | T/E | Direct SQL mutates Challenge/Attempt authority, inserts mismatched tuples, or erases unresolved authority | attacker bypasses repository methods | approval is moved/replayed/regressed, bound to another `psi_*`, reconciled early, or admission reopens | composite FKs; immutable tuple; exact insert/consume handshake; legal-transition/state-code consistency; active/unresolved delete guards; exact enums | direct mutation/transition/mismatch/delete corpus and transaction fault injection | full Control Plane DB/application compromise can replace enforcement and forge authority |
| T-132 | D/S | Re-auth password brute force or Argon2 exhaustion bypasses login controls | attacker holds/guesses a Session and submits repeated re-auth | CPU denial or password discovery | exact Origin/Host/CSRF/body/auth checks; purpose-separated durable rate limit before Argon2; same bounded semaphore/thread discipline and normalized failures | locked-bucket no-Argon2 spy, concurrency cap, source/account buckets and timing tests | authenticated browser theft can spend the bounded re-auth allowance |
| T-133 | T/D | Stale auth-epoch Challenge survives re-auth or a forbidden Audit key rolls back credential rotation | re-auth does not cancel old epoch atomically or writes `session_id` metadata rejected by sanitizer | old approval remains usable or re-auth transaction denies service | token/CSRF rotation, epoch increment, prior challenge cancellation and sanitizer-compatible Audit share one `BEGIN IMMEDIATE`; use only `auth_context_fingerprint` | old-Cookie/CSRF/challenge tests and current `sanitize_metadata` tests for every exact key | crash after commit/before response forces login again by design |
| T-134 | T/R | Lost cancellation acknowledgement is reported as cancelled while Runtime is consuming, committed, verified, or expired | Control Plane requested cancellation after possible delivery | encrypted orphan is retried, falsely absent, or expiry victory is unrecorded | `CANCEL_PENDING`; only exact confirmation reaches `CANCELLED`; consuming/committed/verified/expired observations win with distinct cancellation codes; contradiction becomes `NEEDS_ATTENTION`; same `psi_*` status only | lost response across every Runtime state, expiry race, contradiction, no-new-intent tests | Runtime compromise can forge status within the accepted same-UID residual risk |
| T-135 | D | One referenced Session prevents cleanup of unrelated expired Sessions | cleanup issues one bulk delete under `ON DELETE RESTRICT` | retention stalls and Session table grows | materialize/cancel first; deterministic batch; delete only rows with `NOT EXISTS` Challenge/Attempt references | mixed protected/unprotected Session cleanup and contention tests | protected Sessions remain as long as authority evidence requires them |
| T-136 | T/D | `NEEDS_ATTENTION` pruning or direct deletion enables blind reprovision | cleanup or SQL treats unresolved state as disposable after time | a second attempt targets an unresolved Runtime orphan | unresolved partial index and Challenge guard; null retention forever; Attempt delete trigger always rejects; separate lifecycle authorization required | maintenance/direct-delete/admission tests after 1 day, 90 days, and arbitrary time | metadata remains indefinitely until explicit review, bounded to one per Credential |
| T-137 | T/R | `AUTHORIZED` is incorrectly treated as proof that no Runtime contact occurred | send happens before a durable marker or state update is lost after send | local cancel/expiry permits reuse while Runtime may hold material | commit `AUTHORIZE_PENDING` with request/count/result before every send; Runtime call forbidden from `AUTHORIZED` | crash before send, after send, after response and direct state bypass tests | fully compromised Control Plane can violate call ordering |
| T-138 | T/R/D | Recovery blindly retransmits or creates a new intent after an uncertain authorize | `AUTHORIZE_PENDING` response is lost or status unavailable | duplicate provisioning or orphaned encrypted material | same-`psi_*` authenticated status first; byte-identical resend only on pre-expiry `NOT_FOUND`; persisted count before send; maximum three; never new `psi_*` | all status mappings, counts 1–4, byte comparison, unavailable and restart tests | compromised Runtime can falsely report `NOT_FOUND` |
| T-139 | T/R | Runtime `COMMITTED_UNVERIFIED` is collapsed into staged/retryable state | Control Plane lacks a distinct state or timestamp semantics | existing encrypted record is overwritten/retried or misreported absent | `RUNTIME_COMMITTED_UNVERIFIED`, separate Runtime commit timestamp and Control Plane observation timestamp, forward-only transitions | status mapping with/without Runtime timestamp, restart and no-resend tests | encrypted orphan remains until verified or separately reviewed |
| T-140 | T/D | Possibly delivered intent is cancelled or expired from wall clock alone | deadline passes in `AUTHORIZE_PENDING`, `RUNTIME_STAGED`, or `CANCEL_PENDING` while status is unavailable | Runtime material exists but admission fence is removed | only `AUTHORIZED` expires locally; post-send states require exact same-`psi_*` status; unavailable remains unresolved; three distinct expiry codes | deadline equality for every predecessor/status, unavailable/contradictory and cancel-loses-expiry tests | prolonged Runtime outage retains unresolved rows |
| T-141 | T/D | Active or unresolved Attempt is deleted before/after retention boundary | direct SQL bypasses maintenance | admission fence and recovery evidence disappear | immutable eligibility; delete guard permits only reconciled/safely cancelled/safely expired after UTC6 boundary and always rejects all unresolved states | state-by-state direct deletes, microsecond boundary, missing-clock and arbitrary-age tests | full DB compromise can remove triggers |
| T-142 | T/R | Outer migration preflight races a writer before `BEGIN IMMEDIATE` | API/Worker remains active or data changes after observation | rebuild assumptions become stale | deployment lock and writer fence; repeat every mutable data/schema preflight inside FK-OFF `BEGIN IMMEDIATE` | concurrent writer attempt between phases and locked recheck failure | host/root compromise can bypass deployment fencing |
| T-143 | T/D | Raw SQLite timestamp differs from canonical approval JSON or loses boundary precision | implementer assumes timezone-aware SQLite storage or uses `unixepoch()` | digest mismatch, extended validity, early deletion, or backward-clock bypass | fixed raw UTC6 text, explicit aware-UTC bind/load, distinct RFC3339 canonical conversion, fixed-text arithmetic, transaction clock function | raw storage/round-trip, offsets, `000000`/`999999`, exact deadline/retention and canonical vectors | host clock compromise still causes fail-closed availability loss |
| T-144 | T/R | State/result-code cross-product is incomplete | unusual Runtime status, cancellation race, or malformed evidence has no exact row | unsafe fallback, raw error persistence, or regression | one exhaustive transition matrix; closed state/status/authorize/cancel/attestation/terminal enums; no raw messages | generated state-event coverage and database constraint/trigger corpus | future Runtime protocol additions require a new review |
| T-57 | I | Raw Provider API key enters metadata/output/persistence | TB3/TB9 | opaque Secret reference only; dedicated input/injection channel; field allowlists; no value/suffix/hash in output/audit | schema inspection and cross-store Secret canary scan |
| T-58 | T/E | Provider config update overwrites unrelated or concurrent Codex settings | TB6/TB9 | parse/preserve, typed managed keys, expected revision/digest, complete validation, stale-plan refusal | golden config and concurrent-edit tests |
| T-59 | T/E | Symlink/replacement race redirects Provider config or backup write | TB6/TB9 | no-follow/lstat, owner/mode checks, same-directory temp, fingerprint recheck, restrictive atomic replace | symlink/swap/permission race tests |
| T-60 | S/I | Provider endpoint or diagnostic output exfiltrates Secret | TB9/external Provider | validated scheme/endpoint policy, no URL userinfo, bounded requests, no auth header/body logging, Secret isolation | malicious endpoint, redirect, error, and log canaries |
| T-61 | R/T | Provider API PASS is misrepresented as Remote compatibility | operator/Remote state | independent evidence dimensions and Supported/Compatible/Experimental/Degraded/Incompatible/Unknown states | partial-success compatibility fixtures and UI/CLI assertions |
| T-62 | T/D | Provider activation breaks active Remote session/thread state | TB6/TB9 | preflight impact plan; explicit restart/re-auth/session action; rollback; Unknown/Experimental on uncertain public behavior | session/history/tools/streaming/Responses/Remote regression matrix |
| T-63 | T/R | ProviderDefinition identity is conflated with Runtime binding identity | TB3/TB9, thread discovery | distinct IDs; Runtime-specific mapping; current Codex behavior is revalidated, not permanent | identity migration and changed-base-URL fixtures |
| T-64 | T/D | Provider switch races an active turn/tool call/writer or duplicate Runtime | TB6/TB9 | public-signal preflight; per-Runtime serialization; uncertain state requires turn-complete confirmation | active/unknown/duplicate writer fault matrix |
| T-65 | R/T | Partial restoration is falsely reported as successful rollback | TB9/config/lifecycle | snapshot complete scope; restore content/nonexistence/mode/binding/Secret reference/lifecycle; explicit rollback verification | fail at every transaction step and restart verification |
| T-66 | T/I | Private SQLite/JSONL/rollout/thread metadata is rewritten to fake continuity | Runtime history | permanent direct-mutation prohibition; public migration/resume API only after review | source boundary scan and artifact canary tests |
| T-67 | I/T | Automatic Provider failover changes model, cost, privacy, or data boundary | Provider selection | no automatic fallback; persisted explicit Active Provider; failure remains visible | restart/failure state-machine tests |
| T-68 | I/E | Platform Secret backend exposes material across user or OS boundary | TB9/Secret backend | Linux restrictive structured file; macOS Keychain; current-user Windows DPAPI; WSL/native isolation | owner/mode, Keychain identity, DPAPI user, and shared-directory negative tests |
| T-69 | I/T | Provider test leaks Authorization in argv or incurs undisclosed model cost | TB9/process/provider | in-memory header or restrictive mechanism; never argv; connectivity/runtime/continuity split; paid inference requires explicit opt-in | process-list canary and paid-test confirmation tests |
| T-70 | R/I | Thread absent from discovery is reported as deleted or fully compatible | UI/CLI/operator | separate Resume/Context/Discovery results; `Thread not listed` wording; only validated public recovery guidance | A/B continuity harness partial-success fixtures |
| T-71 | E | Compromised Web escalates through Helper | TB2/TB5/root | separate UID, no API Helper import, peer UID/GID, six argument-free actions | boundary scan and Helper injection tests |
| T-72 | S/E | Runtime or Helper UDS is spoofed or peer credentials bypassed | TB4/TB5 | setgid/sticky protected parent, socket activation, `SO_PEERCRED`, expected UID/GID, protocol version | wrong-peer and socket ownership tests |
| T-73 | T/E | Install symlink or TOCTOU redirects a privileged write | TB7/filesystem | every ancestor lstat/root-owner check, no-follow open/copy, same-parent atomic replace, exact owned paths | parent-symlink/collision/race fixtures |
| T-74 | E | World-writable install directory enables replacement | FHS/release | exact owner/mode specs, refuse unsafe existing objects, Doctor diagnostics | mode/owner and privilege tests |
| T-75 | T/E | Package supply chain installs malicious dependency | TB7/root | fixed packages/repos, explicit plan, manager result plus binary verification | adapter fixtures and dependency review |
| T-76 | T/E | Release archive traversal/link escape or bomb | TB7/releases | checksum, manifest digests, path/type/link/count/size validation, staging | hostile tar corpus |
| T-77 | T/E | Malicious or substituted upgrade artifact activates | TB7/releases | expected SHA-256, semantic version, wheel/manifest match, immutable staged release | tamper/version tests; signatures remain residual |
| T-78 | R/T | Rollback mismatch is reported successful | backup/release/DB | receipt-pinned backup manifest, sidecar cleanup, DB revision/integrity, service/socket/endpoint/meta version checks | rollback-verification failure injection |
| T-79 | T/D | DB migration failure leaves incompatible active code | SQLite/release | quiesce, online backup, explicit migration before activation, rollback | migration fault injection |
| T-80 | T/D | Stale or external `current` symlink selects unknown code | release layout | relative one-level link, verified manifest/digests, atomic replace | stale/symlink/collision tests |
| T-81 | E | systemd unit or environment-file injection | root units/config | exact packaged units, no arbitrary values, strict key parser, root ownership, fixed PATH | unit verification and hostile config tests |
| T-82 | I/E | Secret permissions expose application or Runtime credential | config/HOME | separate UIDs/files, restrictive modes, no logs, no credential migration | real-UID isolation and canary scans |
| T-83 | D | Service restart crash loop exhausts host | systemd | on-failure policy, RestartSec, StartLimit, health gate | unit parser/systemd analysis and real-host check |
| T-84 | I/E | Runtime credentials cross into Web/root migration | process/HOME | independent Runtime HOME/login; no copy/chown; typed output only | privilege and real-host unchanged-state checks |
| T-85 | T/E | Project ownership crosses into Web or root | Project Root | Runtime-only `0700`, typed Runtime operations, no automatic `/root/projects` migration | real-UID write denial and path tests |
| T-86 | T/D | Partial install deletes or adopts unrelated objects | host state | root-only transaction journal with existed-before and inode identity; service-account reuse requires receipt-bound UID/GID plus fixed home/shell/group shape; uninstall preflights all targets before mutation | partial/account collision/re-entry/uninstall no-mutation tests |
| T-87 | T/E | Release activation races another lifecycle writer | release/current | global nonblocking lock, stage/verify then atomic symlink, post-activation verification | concurrent transaction test |
| T-88 | E | systemd process resolves attacker-controlled PATH | services/helper | minimal fixed PATH; Helper absolute `/usr/bin/systemctl`; no shell profile | unit and boundary inspection |
| T-89 | T/D | Power loss leaves migrated DB and release activation out of sync | lifecycle journal | durable stage classification (`staged`, `partially_migrated`, `activated`, `rollback_pending`, `unknown`) and fail-closed re-entry | crash-state fixtures; automatic resume deferred |

## Phase 3 Control-Plane Attack Surface

| Threat | Current mitigation | Residual/verification |
|---|---|---|
| Admin bootstrap race | `BEGIN IMMEDIATE`, database uniqueness for one active admin, no Web registration | concurrent bootstrap test; local OS/TTY authority is assumed |
| Brute-force login | account, source, and combined pseudonymous buckets; five failures/five minutes; bounded five-minute lock | deterministic fake-clock tests; buckets reset on API restart |
| Username enumeration | identical invalid-credential code/message for missing, wrong-password, and inactive users | missing users run one precomputed Argon2 dummy verification; timing remains a review target |
| Session fixation | every login generates a new 256-bit opaque Session and ignores caller-selected cookie identity | fixation test compares attacker cookie with issued cookie |
| Session theft/replay | keyed token hash at rest, `HttpOnly`, `SameSite=Strict`, idle/absolute expiry, revocation, active-session cap | production requires `Secure`; host/browser compromise remains residual risk |
| CSRF | Session-bound derived token, stored keyed verifier, `X-CSRF-Token`, exact Origin and Host on mutations | missing/wrong/cross-Session/hostile-Origin tests |
| Cookie leakage | no Session value in API body/DB/audit/log; no-store auth responses; CSP/referrer/frame headers | loopback development HTTP is explicitly less transport-secure than HTTPS |
| Database theft | only Argon2id passwords and keyed Session/CSRF digests; no raw tokens; restricted production path policy | DB theft still exposes metadata/password hashes; installer permissions and encrypted backups are later gates |
| Authentication timing leak | maintained Argon2id verifier and a process-precomputed dummy hash | exact timing equivalence is best effort and must be profiled before release |
| Header/proxy spoofing | bounded request IDs, exact Origin/Host, socket peer source by default, forwarded address only from configured trusted proxy networks | trusted-proxy chain semantics need deployment-specific tests |
| Audit/log injection | flat bounded metadata allowlist, secret-key rejection, newline neutralization, structured logging and assignment redaction | arbitrary secret text cannot always be pattern-detected, so sensitive values are prohibited at the call site |
| Oversized request DoS | global 16 KiB mutation-body cap plus username/password/request-ID length limits | CPU/memory concurrency limits and reverse-proxy limits remain deployment hardening |

## Phase 4 Browser Attack Surface

| Threat | Current mitigation | Residual/verification |
|---|---|---|
| DOM XSS | no raw HTML insertion, remote script, analytics, dynamic evaluation, or unvalidated request-ID display | dependency compromise remains governed by lockfile review and CSP |
| Frontend token leakage | Session is HttpOnly; CSRF and safe metadata are memory-only; no auth data is stored in browser storage or logged | browser extensions and a compromised same-origin script remain residual browser risks |
| Stale authentication | auth boot blocks routing until `me`; any protected `401` clears state; guards redirect to Login | multiple tabs do not proactively synchronize logout until the next request/refresh |
| CSRF retry bug | logout retries only after one authenticated `me` refresh and never more than once | future mutation endpoints must use the same bounded policy deliberately |
| Open redirect | no post-login `next` support and all navigation targets are local constants | any future deep-link feature requires strict relative-path validation |
| Clickjacking | CSP frame ancestor denial and legacy frame header | deployment proxy must preserve rather than overwrite headers |
| Malicious request ID | server and browser each enforce a small safe character/length grammar; React renders text | diagnostic copy/paste remains operator-controlled |
| Route authorization bypass | browser guards provide UX only; Doctor and auth state are server authenticated | every future route requires an API authorization test independent of UI |
| UI confusion/fake status | actual APIs drive control-plane cards; missing data is Unavailable; future functions are Planned | product copy needs review as capabilities become real |
| Browser cache | auth and Doctor API responses are no-store; static Vite shell has no user-specific content | Phase 8 reverse-proxy/static cache headers remain a deployment gate |
| Oversized/browser DoS | bounded server body, client timeout, modest bundle, no charts/editor/terminal or unbounded retries | API response-size policy remains the authoritative control |

## Phase 5 Codex Attack Surface

| Threat | Current mitigation | Residual/verification |
|---|---|---|
| PATH hijack/fake executable | Runtime-owned fixed PATH, no API path input, realpath/mode validation and fingerprint recheck | small validation-to-exec TOCTOU remains; production allowed-root policy is a Phase 8 gate |
| CLI behavior/output change | public help detection, tri-state capabilities, bounded conservative parsing, no version-only enablement | localized or newly formatted output may degrade to Unknown/Unsupported until a fixture is reviewed |
| Secret environment inheritance | new environment built from HOME/PATH/locale/necessary XDG keys only | Runtime HOME intentionally lets the official CLI use its own auth; AgentBox cannot harden third-party file parsing |
| Duplicate/reordered actions | one `asyncio.Lock` serializes start/stop/Pair; known states are idempotent | process-local state is lost on restart and native status may be absent |
| Wrong-process stop | only public `remote-control stop`; process inspection never supplies a kill target | the third-party command's own scope is outside AgentBox control |
| Pair disclosure | recent auth, CSRF/Origin/Host, 4 KiB sensitive streams, safe parser/error, metadata-only audit, no-store, memory-only UI, explicit copy and canary scans | authenticated browser compromise or extensions can read displayed code |
| Pair replay/stale display | ten-second generation cooldown, Hide/navigation/90-second UI clear, no retrieval endpoint | UI clear is not official expiry; unknown expiry is shown as unknown |
| Runtime socket abuse | `0660`, UID allowlist via `SO_PEERCRED`, exact V1 keys/action enum, 64 KiB frame | Phase 8 must install exact owner/group/unit sandboxing |
| Resource exhaustion | action lock, per-command timeout/output caps, spawned-process-group cleanup | status requests are uncached in Phase 5; reverse-proxy/request concurrency hardening remains later work |
| Legacy service confusion | exact legacy-unit presence is warning-only and never managed/adopted | operator must manually assess the existing unit before deployment |

## Phase 6 Claude/tmux Attack Surface

| Threat | Current mitigation | Residual/verification |
|---|---|---|
| Malicious project ID/path traversal | API/UDS carry only bounded ID; Runtime immediate-child canonical resolution rejects separators, traversal, root/file/missing targets and project/root symlinks | bind mounts and post-check mount changes remain a Phase 8 namespace/ownership concern |
| Session-name/argv injection | bounded ASCII slug/hash name; fixed tmux argv and absolute fingerprinted Claude command; no shell string or caller flags | reviewed against current public tmux multi-argument command behavior |
| tmux collision/unmanaged takeover | exact deterministic name plus versioned project marker; collision fails closed; unmanaged names are count-only | same-UID processes can inspect/forge tmux state, requiring a dedicated Runtime identity |
| Wrong-session kill | stop revalidates project, exact name and exact marker; only `kill-session -t =name` exists | an external same-UID race between marker check and kill is residual |
| Pane secret/control leakage | explicit authenticated fetch, runner/output caps, ANSI CSI/OSC/control sanitation, no-store, text-only DOM, no Audit/log/DB/storage | output can still contain secrets/source; sanitation is not redaction |
| Workspace Trust auto-accept | no key input, `yes`, private file parsing, or undocumented trust flag; prompt becomes Needs Interaction | localized/changed prompts may degrade to Unknown and need fixture review |
| Claude auth file disclosure | only public CLI evidence; private config/credential directories are never read/copied | official CLI itself reads its Runtime HOME under its security model |
| Cross-user tmux confusion | tmux operations run only as Runtime Executor current user; no root-server socket selection | current root-host validation is development evidence only |
| Runtime restart/stale state | registry/name/marker/pane rediscovery; Unknown when readiness is not evidenced | no official machine-readable Remote health; tmux running is not connected proof |
| Long-running child ownership | tmux directly owns interactive Claude; request/Executor does not hold foreground child | tmux server loss ends sessions; recovery is operator-visible, not auto-restart |
| Terminal attach misuse | Web only copies fixed command; CLI requires local TTY and exact validated returned name | attach exposes live terminal content to the local Runtime identity by design |

## Highest-Risk Abuse Cases

### Future Provider Secret or Config Compromise

Attack chain: an administrator submits a Provider → raw API key reaches argv or
storage → ProviderDefinition and RuntimeBinding identities are conflated → a
config editor races an active writer or overwrites unrelated settings → partial
rollback is called successful → thread discovery loss is misreported as
deletion. The planned prevention boundary requires platform Secret backends,
typed identities/options, public-contract validation, active-writer preflight,
full-scope config/lifecycle transactions, rollback verification, and independent
Provider/Runtime/Remote/thread/context/discovery evidence. Direct mutation of
private session DB/JSONL/rollout state and automatic Provider failover are
prohibited. Phase 11 Slice 3 has now frozen the Runtime-only Secret custody,
envelope, filesystem, backup, recovery, and first-foundation implementation
boundary. Slice 3.1 implements only that fixed-path empty-Store, key-custody,
envelope, integrity, and packaging foundation. It still implements no Secret
provisioning, credential broker, Provider request, config mutation, or Provider
activation.

### Web-to-Root Command Injection

Attack chain: authenticated or compromised Web submits crafted command/path → Worker passes it to Helper → root shell executes. Prevention is architectural: no raw command model exists, action handlers build fixed argv, paths derive from server records, Helper independently validates, and the root process has no generic execution action.

### Malicious Repository-to-Host Escalation

Attack chain: clone a hostile repository → Git hooks/submodules/symlinks/build
steps escape project → overwrite executable or collect credentials. MVP clones
as non-root into staging, disables recursive submodules and credential
prompting, runs no project builds or repository hooks, exposes no file-browser
operation, and keeps root/AgentBox credentials inaccessible. Repository file
content remains untrusted data.

### Pair Code Disclosure

Attack chain: pair command output enters Job result/logger/exception/SSE/browser cache → another actor pairs. Pairing bypasses persistent Job results, uses a one-time no-store response, suppresses bodies/output, and is covered by canary scanning across DB/journal/API traces.

### Update Supply-Chain Compromise

Attack chain: attacker replaces release/installer → root Helper installs it. Controls require approved origin, version pin, digest/signature/provenance where available, staged validation, immutable release, health check, and rollback. Lack of publisher verification is explicitly surfaced, not silently accepted.

## Residual Risks and Assumptions

- Codex and Claude public CLI behavior can change; capability detection limits but cannot remove this risk.
- Third-party authentication remains in Runtime HOME under that tool's security model; AgentBox observes status but does not manage tokens.
- An administrator can intentionally weaken bind/proxy/security settings; AgentBox must warn and audit but cannot defeat root.
- Recent Claude pane output can contain private source/model text even after pattern redaction; access remains highly restricted and ephemeral.
- SQLite and a single Worker fit one host but are not a multi-host consistency design.
- SELinux is disabled and AppArmor absent on the Phase 0 host; process separation and systemd hardening carry more weight.
- External cloud firewall and Cloudflare Access policy were not inspected in Phase 0.

## Security Test Traceability

Every threat ID above must map to at least one test case or an explicit manual verification in `TEST_STRATEGY.md` before release. T-05, T-08, T-10, T-11, T-17, T-21, T-25, T-26, T-27, T-31, T-34, and T-71 through T-88 are release blockers for their applicable boundaries.

## Revisit Conditions

Revisit the threat model before adding Provider/Secret/config mutation,
staging/commit or dangerous Git, browser PTY/WebSocket, project deletion,
multi-user/multi-server, plugins, container control, third-party webhooks,
enterprise auth, or any non-loopback direct listener.
## Phase 9 hardening review

Phase 9 retests persistent lockout bypass, backward-clock expiry,
proxy-source spoofing, Bearer-token redaction, duplicate/deep/concatenated UDS
messages, peer UID/GID mismatch, unit directive incompatibility, partial
installer/update state, corrupt rollback evidence, concurrent WAL backup,
permission drift, and retention deletion identity. A full-system canary gate
scans logs plus SQLite/WAL/SHM for password, Session, CSRF, application secret,
Git credential, gh token, Codex Pair Code, and Claude output values.

Residual risks remain explicit: Runtime needs network, HOME, user namespaces,
and JIT-compatible memory; service sandboxing is not a chroot; checksums do not
authenticate their publisher; only OpenCloudOS has real-host evidence; TLS and
trusted-proxy configuration remain operator responsibilities; secret-pattern
detection remains defense in depth.

## Phase 7 threats and mitigations

New threats include malicious repository URLs/protocol helpers, credential helpers and `core.sshCommand`, repository/worktree config scope bypass, hooks/pagers/editors/external diff, submodules/LFS, clone residue/no-replace/rollback races, branch/refspec injection, remote credential leakage, ownership mismatch, workspace mutation under an active Agent, Draft PR input injection, `gh` prompt blocking and long network DoS. Mitigations are protocol/input allowlists, fixed config/environment/argv, all active repository-scope config inspection with includes disabled, ownership/canonical-path checks, descriptor-relative no-replace activation, dual-marker rollback identity, mutation leases, bounded time/output, normalized errors, credential redaction and Claude activity guards.

## Phase 10 release artifact review

The release boundary adds threats from dirty-checkout inclusion, nondeterministic
output, archive path ambiguity, manifest substitution, dependency/license drift,
source-map disclosure, artifact growth, and a compromised PR workflow. Controls
are a clean-commit gate, locked Python and pnpm dependencies, normalized
bit-for-bit same-runner builds, a 100 MiB artifact ceiling, a strict archive
allowlist, external and per-file SHA-256 verification, SPDX SBOM, license
inventory, canary scan, no source maps, immutable Action pins, read-only workflow
permissions, and artifact-only install/upgrade/rollback fixtures.

Residual risk remains that SHA-256 does not authenticate the publisher and that
cross-runner reproducibility is unqualified. An operator who obtains both an
artifact and checksum from the same compromised origin has no independent
signature. Signing and provenance key governance require separate human review;
Phase 10 creates neither keys nor a public release.
