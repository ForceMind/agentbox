# AgentBox Threat Model

Status: Phase 1 baseline updated for the implemented Phase 3 control plane,
Phase 4 Web surface, and Phase 5 Codex Runtime integration
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
TB9 (future): Provider Registry and Runtime Binding to Secret Manager, Config
Transaction Manager, Runtime Continuity Manager, Runtime configuration/lifecycle,
and external model/API Provider. No implementation exists yet.

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
prohibited. Phase 11 must revisit this model before implementation or real tests.

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

Every threat ID above must map to at least one test case or an explicit manual verification in `TEST_STRATEGY.md` before release. T-05, T-08, T-10, T-11, T-17, T-21, T-25, T-26, T-27, T-31, and T-34 are release blockers.

## Revisit Conditions

Revisit the threat model before adding Provider/Secret/config mutation,
staging/commit or dangerous Git, browser PTY/WebSocket, project deletion,
multi-user/multi-server, plugins, container control, third-party webhooks,
enterprise auth, or any non-loopback direct listener.
## Phase 7 threats and mitigations

New threats include malicious repository URLs/protocol helpers, credential helpers and `core.sshCommand`, hooks/pagers/editors/external diff, submodules/LFS, clone residue/races, branch injection, remote credential leakage, ownership mismatch, workspace mutation under an active Agent, Draft PR input injection, `gh` prompt blocking and long network DoS. Mitigations are protocol/input allowlists, fixed config/environment/argv, ownership/canonical-path checks, atomic marker-bound staging, mutation leases, bounded time/output, normalized errors, credential redaction and Claude activity guards.
