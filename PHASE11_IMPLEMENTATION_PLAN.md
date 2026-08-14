# AgentBox Phase 11 — Provider / Secret / Runtime Continuity Implementation Plan

Status: **Planning only — implementation has not started**
Architecture source of truth: `PHASE11_PROVIDER_MANAGER_PROPOSAL.md`
Repository baseline: `ForceMind/agentbox` at `1c2005de59b1c5063b260591206a8411c7e5b1a5`
Release baseline: `v0.3.0-rc.1`

Governance note: This plan preserves historical sequencing and open choices.
The accepted canonical decisions in `docs/adr/README.md` and the supplemental
closure in `PHASE11_10_PUBLIC_CONTRACT_EVIDENCE_CLOSURE.md` control wherever
this plan presents an unresolved or broader alternative.

## 1. Executive Summary

Phase 11 introduces a Provider Manager for AI execution Providers while keeping
Agent Remote Control independent. Remote Control continues to detect, pair,
start, stop, and observe Codex. Provider Manager owns non-secret Provider
metadata, credential lifecycle metadata, Runtime configuration intent,
Provider validation, explicit activation, and continuity evidence.

The first implementation is intentionally narrow:

- Linux only;
- one AgentBox server and one administrator;
- Codex as the only Provider-managed Runtime;
- Official OpenAI and typed OpenAI-compatible HTTP Providers;
- no Local Provider implementation, only an extension point;
- Claude remains Runtime/tmux management only.

Provider Manager is not a general Secret vault, Web shell, infrastructure
manager, cloud account manager, deployment Provider, or arbitrary Runtime
configuration editor. It does not manage SSH, firewall, reverse proxies,
cloudflared, system packages, arbitrary processes, or root credentials.

### 1.1 Process and trust-boundary decision

The accepted process model does not change:

```text
Browser / ordinary AgentBox CLI
        |
        | non-secret metadata, plans, confirmations, status
        v
agentbox API / Worker / SQLite
        |
        | typed versioned UDS messages, opaque IDs and revisions only
        v
agentbox-runtime
        +-- Provider config adapter
        +-- Runtime Secret backend
        +-- Provider test executor
        +-- continuity probes
        +-- Codex

root Helper
        +-- unchanged fixed lifecycle actions only
```

The `agentbox` identity owns control-plane records and Jobs but cannot read raw
Provider Secrets, Runtime HOME, rendered Runtime config snapshots, or child
Runtime environments. The `agentbox-runtime` identity owns Secret material,
Runtime configuration work, and Provider execution. The root Helper gains no
Provider action and never reads Runtime credentials.

### 1.2 Safe delivery principle

Phase 11 should be delivered as a sequence of independently reviewable trust-
boundary milestones. Early milestones are non-secret and read-only. Secret
storage, config mutation, activation, continuity, API, and Web controls remain
separately gated. Provider management defaults to `unmanaged` after upgrade and
does nothing until the administrator explicitly opts in.

No activation code should be reachable merely because the database schema,
Provider registry, or Secret backend exists. Activation is enabled only after
the config transaction, Runtime adapter, rollback verification, and continuity
gates all pass.

## 2. Implementation Phases

### 2.1 Dependency map

```text
11.0 Contract Validation and Decision ADRs
  |
  +--> 11.1 Provider Core Model and Additive Schema
  |       |
  |       +--> 11.2 Read-only Runtime Capability Boundary
  |       |       |
  |       |       +--> 11.3 Linux Secret Storage Boundary
  |       |       |
  |       |       +--> 11.4 Config Transaction Framework
  |       |                    |
  |       +--------------------+--> 11.5 Provider Validation Pipeline
  |                                      |
  +--------------------------------------> 11.6 Codex Provider Adapter
                                                 |
                                                 v
                                      11.7 Runtime Binding, Activation,
                                           Continuity and Rollback
                                                 |
                                  +--------------+--------------+
                                  v                             v
                         11.8 API and CLI                11.9 Frontend
                                  \                             /
                                   +-------------+-------------+
                                                 v
                                  11.10 Migration, Deployment,
                                        Compatibility and Release Gate
```

Milestones may be split into smaller pull requests, but their trust boundaries
must not be collapsed for convenience. Every implementation PR follows the
existing Draft PR, CI, review, and Squash Merge workflow.

### 2.2 Phase 11.0 — Public Contract Validation and Architecture Decisions

**Goal**

Resolve the decisions that would otherwise cause Secret, config, or session
work to be built on assumptions.

**Scope**

- Revalidate the then-current public Codex CLI help, configuration
  documentation/schema, supported Provider fields, wire protocols, credential
  reference mechanism, reload/restart behavior, Remote lifecycle, active-writer
  evidence, and public session/resume/discovery behavior.
- Record observed behavior as versioned fixtures and capability evidence, not
  permanent product contracts.
- Approve ADRs for Linux Secret storage/encryption and master-key custody,
  Secret ingress, Codex managed-config ownership, and active-session switching.
- Confirm that Phase 11 v1 supports only Linux, Codex, Official OpenAI, and
  OpenAI-compatible HTTP Providers.
- Confirm that Claude remains Runtime-only and Local Provider remains an
  inactive extension point.

**Dependencies**

- Approved Phase 11 architecture proposal.
- Current public Codex documentation and a controlled, non-production fixture
  environment.
- Product and security-owner availability for explicit decisions.

**Risks**

- Treating a current Codex field or Provider ID as a permanent contract.
- Mistaking private Runtime state for a supported interface.
- Allowing implementation to begin while key custody or session behavior is
  unresolved.

**Validation / exit gate**

- All required ADRs are accepted or implementation is stopped at the affected
  boundary.
- Public-contract fixtures contain no real credentials, account identifiers,
  sessions, prompts, or private paths.
- Each Codex capability is `supported`, `unsupported`, or `unknown` with an
  evidence class.
- No Provider mutation, Secret read, config write, Runtime restart, or paid
  request occurs in this milestone.

### 2.3 Phase 11.1 — Provider Core Model and Additive Schema

**Goal**

Introduce the non-secret Provider domain, repository interfaces, and additive
database structures without creating a Secret backend or changing Runtime
behavior.

**Scope**

- Define independent IDs and typed domain models for Provider, Credential
  metadata, Runtime Profile, Runtime Binding, Session Binding, compatibility
  observation, and config transaction metadata.
- Add repository and application-service interfaces for non-secret create,
  list, inspect, edit, disable, and revision checks.
- Add one reviewed, additive Alembic migration.
- Reuse existing Job, JobEvent, ConfirmationChallenge, and AuditEvent
  facilities instead of introducing parallel queues or audit systems.
- Add an explicit `unmanaged` read state for every existing Runtime with no
  active Provider binding.
- Keep Provider activation and Credential provisioning disabled.

**Dependencies**

- Phase 11.0 identity and schema decisions.
- Existing SQLite, SQLAlchemy, Alembic, Job, and Audit conventions.

**Risks**

- Accidentally storing raw Secret material or config in generic JSON fields.
- Conflating Provider, Credential, Runtime Binding, or Session identity.
- Creating an active Provider during migration.
- Breaking older application rollback by modifying existing tables or data.

**Validation / exit gate**

- Migration upgrade and downgrade/compatibility tests run against a copy of the
  existing schema without changing existing auth, Project, Job, Session, or
  Runtime data.
- Schema inspection rejects Secret-shaped columns and unbounded privileged
  payloads.
- Unique and foreign-key constraints enforce one active binding per Runtime and
  valid revision relationships.
- Fresh and upgraded databases both report Provider management as `unmanaged`.
- No existing Codex config, credentials, sessions, Projects, or Runtime process
  are read or changed.

### 2.4 Phase 11.2 — Read-only Runtime Capability Boundary

**Goal**

Extend the existing typed Runtime boundary with read-only Provider capability
discovery before any Secret or config mutation is possible.

**Scope**

- Add versioned, exact-schema UDS messages for Provider capability discovery,
  adapter availability, config ownership state, and sanitized conflict status.
- Carry only opaque Provider/Runtime IDs, schema versions, revisions, and typed
  capability names.
- Resolve Runtime paths, executable identity, and public config locations
  server-side as `agentbox-runtime`.
- Report `supported`, `unsupported`, or `unknown`; never enable mutation from a
  version string alone.
- Keep root Helper and Remote Control protocols unchanged.

**Dependencies**

- Phase 11.0 public-contract fixtures.
- Phase 11.1 IDs and read models.
- Existing Runtime UDS peer-credential, framing, timeout, and action allowlist.

**Risks**

- Turning read-only discovery into a raw config reader.
- Leaking config values, internal endpoints, or Runtime HOME paths.
- Accepting arbitrary paths, executable names, environment maps, or config
  keys through the UDS.
- Cross-protocol confusion with Helper or existing Runtime actions.

**Validation / exit gate**

- Wrong UID/GID, protocol version, action, unknown field, oversized frame,
  concatenated frame, malformed Unicode, and timeout tests fail closed.
- Boundary scans show no shell, caller argv, caller environment, raw path, raw
  TOML, or systemctl input.
- Discovery returns only bounded sanitized facts.
- Existing Codex and Claude Runtime tests remain unchanged and pass.

### 2.5 Phase 11.3 — Linux Secret Storage Boundary

**Goal**

Create the Linux Runtime-owned Secret custody and rotation foundation without
allowing Provider activation.

**Scope**

- Implement the approved Runtime Secret backend under a fixed deployment-owned
  directory with `0700` directory and `0600` record/key modes.
- Implement the approved versioned authenticated-encryption envelope if AEAD is
  selected; otherwise document and enforce the approved permission-only model.
- Add local, interactive, Runtime-identity Secret provisioning that reads from
  TTY/protected stdin, never argv, environment, URL, browser, or ordinary API.
- Return only opaque Secret reference, version, and configured state.
- Implement create, staged rotation, revoke state, retirement, and explicit
  deletion policies.
- Keep the master key and Secret records outside SQLite and ordinary AgentBox
  backups.
- Keep activation disabled.

**Dependencies**

- Accepted Secret encryption/key custody and Secret ingress ADRs.
- Phase 11.1 Credential metadata.
- Phase 11.2 Runtime peer and protocol controls.
- Deployment owner/mode policy for the fixed Runtime-owned location.

**Risks**

- Secret leakage to process argv, shell history, environment dumps, logs,
  SQLite/WAL/SHM, Audit, diagnostics, reports, browser storage, or test
  artifacts.
- Symlink, hardlink, path replacement, or unsafe permissions.
- Losing the master key without an honest recovery policy.
- A compromised `agentbox` process invoking a generic Secret API.
- Deleting a Secret still required for active use or rollback.

**Validation / exit gate**

- Distinct-UID tests prove `agentbox` cannot traverse or read the Secret store
  and `agentbox-runtime` cannot read the AgentBox application secret or DB.
- Secret paths are server-selected; lstat/no-follow, owner/mode, link-count,
  atomic-write, fsync, concurrent-write, and crash tests pass.
- Canary scans cover SQLite/WAL/SHM, journal, Audit, Job/Event payloads,
  diagnostics, reports, process argv/environment observations, and browser
  artifacts.
- Rotation never changes Provider identity or activates a Provider.
- Reinstall, update, rollback, and default uninstall preserve the Secret store;
  there is no purge operation.
- Loss/corruption states are explicit and do not produce a guessed or empty key.

### 2.6 Phase 11.4 — Config Transaction Framework

**Goal**

Provide a runtime-neutral, fixture-tested transaction engine for safe Runtime
configuration changes and verified rollback, with no live Codex activation.

**Scope**

- Implement snapshot, candidate generation boundary, validation, expected
  fingerprint/revision, restrictive temporary write, fsync, atomic replace,
  verification, rollback, and rollback verification.
- Preserve original nonexistence, owner, group, mode, and all unrelated config
  settings.
- Store config snapshots only in bounded Runtime-owned protected transaction
  storage; SQLite holds opaque references and sanitized metadata.
- Implement crash states such as `staged`, `applied`, `verification_pending`,
  `rollback_pending`, `rollback_verified`, and `needs_attention`.
- Serialize transactions per Runtime and reject concurrent manual edits.
- Test against synthetic TOML fixtures only in this milestone.

**Dependencies**

- Accepted config ownership ADR.
- Phase 11.1 transaction metadata.
- Phase 11.2 Runtime protocol.
- Existing installer/update atomic file and recovery patterns where applicable,
  without coupling Provider transactions to root release activation.

**Risks**

- Overwriting unrelated user configuration.
- Following a symlink or writing through an attacker-controlled parent.
- Treating partial restore or binary-only restart as rollback success.
- Blindly replaying a mutation after Worker/Runtime/power failure.
- Persisting a snapshot that contains an unmanaged Secret in the control plane.

**Validation / exit gate**

- Golden-file tests prove unrelated TOML content and formatting-relevant
  semantics are preserved.
- Symlink, parent replacement, inode swap, duplicate block, permission drift,
  concurrent edit, disk-full, fsync, rename, and process-crash fixtures fail
  safely.
- Fault injection at every transaction step either leaves the original state
  unchanged or reports `needs_attention` with exact recovery evidence.
- `Rollback verified` is emitted only after content/nonexistence, ownership,
  mode, binding metadata, and lifecycle expectations are all verified.
- No live Codex file is changed and no Runtime is restarted.

### 2.7 Phase 11.5 — Provider Validation Pipeline

**Goal**

Implement layered Provider testing without conflating endpoint success with
Codex, Remote, or session continuity.

**Scope**

- Implement typed endpoint normalization and destination policy for Official
  OpenAI and OpenAI-compatible HTTP Providers.
- Implement independent endpoint, network, authentication, model, wire
  protocol, and minimal Provider API observations.
- Build local fake Provider A/B fixtures for deterministic auth, streaming,
  error, redirect, timeout, and compatibility behavior.
- Keep Runtime, Remote, and continuity layers `NOT_TESTED` until later
  milestones provide their evidence.
- Require explicit confirmation for any paid real-model test; use no real
  credentials in CI.
- Keep Local Provider inactive while retaining a typed capability extension
  point.

**Dependencies**

- Phase 11.1 Provider and observation models.
- Phase 11.3 protected Secret resolution.
- Approved endpoint/private-network and paid-test policies.

**Risks**

- SSRF, metadata-service access, DNS rebinding, malicious redirects, TLS
  downgrade, credential forwarding, or internal-network scanning.
- Unbounded streaming/output or decompression/resource exhaustion.
- Raw Provider response, prompt, or Authorization leakage.
- Reporting Provider request `PASS` as Runtime or Remote compatibility.

**Validation / exit gate**

- Scheme, userinfo, fragment, control-character, Unicode normalization,
  redirect-authority, DNS-rebind, link-local, metadata-service, timeout,
  response-size, and streaming-limit tests pass.
- Official and compatible Provider validators are separate typed policies.
- Authorization exists only in trusted in-memory request state and never in
  argv, URL, logs, DB, Audit, reports, or returned error details.
- Compatibility aggregation preserves every detailed dimension and cannot
  promote untested higher layers.
- No paid test runs without a per-run confirmation.

### 2.8 Phase 11.6 — Codex Provider Adapter and Dry-run Plans

**Goal**

Map typed Provider intent to the currently validated public Codex contract and
produce trustworthy activation plans, while keeping real activation disabled.

**Scope**

- Implement `CodexProviderConfigAdapter` for Official OpenAI and approved
  OpenAI-compatible fields only.
- Parse existing TOML and manage only a versioned AgentBox-owned scope.
- Preserve all unrelated settings and reject duplicate or conflicting managed
  scope.
- Reference Provider Secrets through the approved public credential reference,
  preferably an environment-variable name, never a raw value in TOML.
- Produce a revision-bound plan describing current/target Provider, model,
  destination, config changes by safe field name, restart impact, active
  writer/session findings, and expected verification.
- Generate and validate candidates through Phase 11.4 without committing them.
- Continue to prohibit private Codex session/thread/JSONL/rollout access.

**Dependencies**

- Phase 11.0 Codex public-contract approval.
- Phase 11.3 Secret-reference boundary.
- Phase 11.4 config transaction framework.
- Phase 11.5 Provider test evidence.

**Risks**

- Public Codex schema drift.
- Treating a current Codex Provider block ID as the AgentBox RuntimeBindingID.
- Leaking a raw key into TOML or an ordinary service environment.
- A plan becoming stale before application.
- Hiding restart or session effects from the administrator.

**Validation / exit gate**

- Versioned public-help/schema fixtures cover supported, unsupported, changed,
  localized/malformed, and unknown capabilities.
- Candidate golden tests preserve unrelated config and reject arbitrary keys,
  raw TOML, raw environment, duplicate blocks, paths, or Provider IDs from a
  caller.
- Plan digest binds Provider, Credential, Runtime Profile, Runtime Binding,
  config fingerprint, Runtime capability evidence, and lifecycle intent.
- Secret canaries do not appear in candidate TOML or plan output.
- Live activation remains unavailable.

### 2.9 Phase 11.7 — Runtime Binding, Activation, Continuity, and Rollback

**Goal**

Enable the first complete, explicitly confirmed Provider switch transaction
with active-work protection and verified recovery.

**Scope**

- Implement per-Runtime serialized activation using a durable Job and an exact
  ConfirmationChallenge bound to the reviewed plan digest.
- Preflight Provider/Credential revisions, config fingerprint, Runtime
  capability, active writer/turn, current Remote state, and Session Bindings.
- Apply the candidate through the config transaction framework.
- Inject the Secret only into the allowlisted Codex child process or trusted
  direct Provider test.
- Request any necessary stop/start through the existing non-root Codex Remote
  lifecycle manager; never through root Helper or a parallel daemon manager.
- Verify Provider, Codex Runtime, Remote recovery, thread resume, context
  continuity, and thread discovery independently.
- Commit the active binding only after required dimensions pass; otherwise
  restore config, Secret reference, binding, lifecycle, and verify rollback.
- Create immutable Session Bindings only from supported public evidence.

**Dependencies**

- Phases 11.1 through 11.6.
- Approved active-session switching and minimum activation compatibility policy.
- Existing Codex lifecycle behavior and Job recovery model.

**Risks**

- Switching during an active turn or duplicate writer.
- Breaking Pairing, Remote state, existing sessions, context, or discovery.
- Applying config successfully but recording the wrong active binding.
- Restarting with the wrong Secret version.
- False-positive rollback after config, lifecycle, or DB restoration fails.
- Automatic fallback changing privacy, model, cost, or data destination.

**Validation / exit gate**

- Two-fake-Provider A/B tests independently verify Provider request, Codex
  Runtime request, Remote recovery, resume, context, and discovery outcomes.
- Active/unknown writer, duplicate Runtime, stale plan, changed Secret,
  concurrent config edit, failed apply, failed restart, failed health,
  failed Remote recovery, missing prior release/config snapshot, and corrupt
  rollback evidence all fail closed.
- Existing sessions are never rewritten; pre-Phase-11 sessions remain
  `legacy_unbound` unless public evidence proves otherwise.
- Pairing is never invoked, reset, or deleted by activation.
- No automatic Provider fallback exists.
- Only fully restored config, binding, Secret reference, lifecycle, Runtime,
  and Remote state can produce `Rollback verified`.

### 2.10 Phase 11.8 — API and CLI Surface

**Goal**

Expose the approved Provider workflows through typed control-plane contracts
without placing plaintext Secrets in the HTTP API or ordinary CLI arguments.

**Scope**

- Add Provider create/list/inspect/edit/validate/activate/disable contracts.
- Add Credential metadata/provisioning-state, rotation-plan, and revoke
  contracts. Raw Secret input remains a local Runtime-identity operation.
- Add Runtime Profile, Runtime Binding, Session Binding, compatibility matrix,
  activation plan, transaction, rollback, and recovery read models.
- Use durable Jobs for Provider tests, activation, rollback, and revocation that
  involve Runtime work.
- Require recent authentication, exact Origin/Host, CSRF, revision-bound plans,
  and confirmation for activation/rollback/credential retirement.
- Extend CLI with safe provider/status/plan/use/test/rollback operations and a
  separately approved local Secret-provisioning mode.

**Dependencies**

- Phase 11.7 complete transaction semantics.
- Approved Secret ingress and paid-test UX policies.
- Existing API envelope, authentication, Job, SSE, Audit, and local UDS
  conventions.

**Risks**

- Accidentally adding a raw key field to Provider or Credential JSON.
- Mass assignment of adapter options, URL headers, paths, or config keys.
- CSRF/recent-auth bypass for activation or revocation.
- Job replay of an uncertain mutation.
- CLI argv/history leakage.

**Validation / exit gate**

- Strict request models reject unknown fields, raw Secret/key/token fields,
  arbitrary headers, environment, config, paths, argv, and commands.
- Every high-impact mutation is revision-bound, recent-authenticated,
  confirmed, audited, and non-replayable after uncertainty.
- GET, Job, SSE, Audit, error, and diagnostics responses contain no Secret or
  raw Runtime config.
- CLI refuses Secret input from argv; non-interactive behavior is explicit and
  secure.
- Existing Remote, Project, Git/GitHub, Claude, auth, and Doctor API tests pass.

### 2.11 Phase 11.9 — Frontend

**Goal**

Provide an honest, non-terminal Provider management UI that makes Provider,
Credential, Runtime, Remote, and continuity state visibly distinct.

**Scope**

- Provider list and details.
- Provider type, model, destination authority, enabled state, and last tested
  freshness.
- Credential state as `configured`, `missing`, `rotation_pending`, `revoked`, or
  `unknown`; never reveal or partially display the value.
- Independent health matrix for endpoint, network, authentication, model, wire,
  Provider API, Codex Runtime, Remote, resume, context, and discovery.
- Runtime Profile and active Runtime Binding summary.
- Activation preview showing current/target binding, data destination, cost
  class, restart/session impact, stale evidence, and required confirmation.
- Transaction and rollback progress with `Rollback verified` versus
  `Rollback attempted but verification failed`.
- Local Secret-provisioning guidance without a Web Secret entry field in v1.

**Dependencies**

- Stable Phase 11.8 read/mutation contracts.
- Approved terminology and minimum activation policy.

**Risks**

- Displaying a Provider API `PASS` as full compatibility.
- Encouraging users to paste keys into an unsupported browser field.
- Hiding destination/privacy/restart impact behind a generic confirmation.
- Persisting sensitive state in browser storage, URLs, screenshots, traces, or
  analytics.
- Calling a missing thread deleted.

**Validation / exit gate**

- Component and Playwright tests cover configured/missing/unknown credentials,
  partial compatibility, stale plans, restart required, active-session block,
  activation failure, verified rollback, and failed rollback verification.
- No raw HTML, Provider response, Secret, config, prompt, or model output is
  rendered or persisted.
- Authenticated responses remain no-store; Session and CSRF behavior is
  unchanged.
- Desktop and mobile layouts make the active Provider and each compatibility
  dimension unambiguous.
- No Web terminal, arbitrary config editor, Provider key field, SSH control, or
  infrastructure management appears.

### 2.12 Phase 11.10 — Migration, Deployment, Compatibility, and Release Gate

**Goal**

Prove that a v0.3.0-rc.1 installation can adopt or decline Provider Management
without disrupting current Runtime behavior, then prepare Phase 11 for review.

**Scope**

- Exercise fresh fixture installation and upgrade from v0.3.0-rc.1.
- Verify default `unmanaged` behavior and explicit adoption.
- Verify install/update/rollback/uninstall preservation for Runtime HOME,
  Secret store, config snapshots, DB, Projects, application secret, and current
  Runtime credentials.
- Add production directory and permission checks only for approved Phase 11
  Runtime-owned paths; do not expand root Helper.
- Run compatibility fixtures for supported Codex versions and both v1 Provider
  types.
- Perform a gated OpenCloudOS AgentBox-only adoption/switch/rollback rehearsal
  only after all automated gates pass and with explicit real-credential/cost
  approval when required.
- Add a stable Phase 11 gate only after its constituent jobs are real and stable;
  Ruleset changes remain a separate post-merge operation.

**Dependencies**

- Phases 11.1 through 11.9.
- Approved real-host plan, backup, credential, paid-test, and Runtime restart
  authorization.

**Risks**

- Upgrade silently adopting or rewriting existing Codex config.
- Credential migration from root or the existing Runtime.
- Losing current Remote/session state during rehearsal.
- Application rollback leaving Phase 11-managed config active without a
  compatible controller.
- Overstating platform or Provider compatibility.

**Validation / exit gate**

- Upgrade does not create a Provider, Credential, active binding, Secret store,
  or config change without opt-in.
- Existing root Codex/Claude/tmux state and credentials remain unchanged.
- Existing `agentbox-runtime` auth, Projects, sessions, and config remain
  unchanged until an explicit adoption transaction.
- Fixture fresh install, repeated install, update, failed activation, verified
  rollback, application rollback, and default uninstall preservation pass.
- Backend, Frontend, Security, E2E, Deployment, deployment-gate, Phase 11 tests,
  dependency audits, boundary scans, and the new stable gate pass.
- Real-host evidence is labeled accurately; `UNKNOWN`/`EXPERIMENTAL` is retained
  for unproven compatibility.
- Phase 11 remains not complete until human review approves the final Draft PR.

## 3. Database Design Proposal

The database stores control-plane intent and non-secret evidence. It never
stores raw Provider Secrets, encrypted Secret ciphertext, master keys, raw
Runtime config, Authorization headers, prompts, completions, or private Runtime
session data. SQLite remains owned by `agentbox`; `agentbox-runtime` never opens
it directly.

### 3.1 Entity mapping

| Domain entity | Proposed table/authority | Purpose |
|---|---|---|
| Provider | `provider_definitions` | Typed non-secret endpoint/model/protocol identity and lifecycle. |
| Credential | `provider_credentials` | Non-secret credential kind, opaque Runtime Secret reference, version/state. |
| Runtime Profile | `runtime_provider_profiles` | Versioned typed profile connecting Provider, Credential, adapter schema, and validation intent. |
| Runtime Binding | `runtime_provider_bindings` | Administrator-selected Provider/Profile intent for a Runtime installation. |
| Session Binding | `runtime_session_provider_bindings` | Immutable effective-binding snapshot where supported public evidence exists. |
| Compatibility | `provider_compatibility_observations` | Independent Provider/Runtime/Remote/continuity observations. |
| Config transaction | `provider_config_transactions` | Revision-bound plan, safe phase, opaque backup reference, sanitized result, rollback evidence. |
| Audit record | existing `audit_events` | Actor/action/target/result correlation with allowlisted non-secret metadata. |

### 3.2 Provider

Recommended fields:

- opaque ID and identity schema version;
- display name;
- `official_openai` or `openai_compatible` type for v1;
- normalized endpoint authority where applicable;
- wire protocol and model;
- versioned typed non-secret options;
- enabled/lifecycle state;
- derived compatibility classification and observation freshness;
- created/updated timestamps and optimistic revision.

Official OpenAI uses a fixed endpoint policy. OpenAI-compatible endpoint changes
normally create a new Provider identity or explicit migration. No generic JSON
may represent headers, environment, paths, executables, or arbitrary config.

### 3.3 Credential

Recommended fields:

- opaque Credential ID;
- Provider ID;
- credential kind;
- opaque Runtime Secret reference;
- active Secret version;
- configured/rotation/revoked/missing state;
- safe last-validation state and timestamp;
- optimistic revision and lifecycle timestamps.

There is no `api_key`, `token`, `secret_value`, ciphertext, prefix, suffix, or
key hash column. V1 should allow zero or one active Credential per Provider and
should not share one Credential across Providers by default.

### 3.4 Runtime Profile

Recommended fields:

- opaque Runtime Profile ID;
- Runtime installation ID;
- Provider ID and Provider revision;
- optional Credential ID and Credential/Secret version;
- adapter type and adapter schema version;
- public Runtime capability/schema evidence ID;
- non-secret typed profile JSON and profile digest;
- lifecycle state and optimistic revision.

The profile is a control-plane description, not rendered TOML or environment.
Rendered candidate data and config snapshots remain in the Runtime-owned
transaction boundary.

### 3.5 Runtime Binding

Recommended fields:

- record ID and stable AgentBox RuntimeBindingID;
- Runtime installation ID;
- Runtime Profile and Provider IDs;
- active flag;
- state: unmanaged/pending/active/activation_failed/rollback_pending/
  rollback_verified/needs_attention/unknown;
- previous binding reference retained for the approved rollback window;
- activation transaction ID;
- optimistic revision and timestamps.

A partial unique constraint allows one active binding per Runtime installation.
No row, or an explicit `unmanaged` representation, means AgentBox has not taken
ownership. Failure never selects a different Provider automatically.

### 3.6 Session Binding

Recommended fields:

- record ID;
- AgentBox Runtime Session ID when available;
- Runtime installation and RuntimeBindingID;
- Provider/Profile revisions effective at creation;
- public Runtime session/thread reference only when officially supported;
- evidence class and effective timestamp;
- bound/legacy_unbound/rebind_required/continuity_unknown/retired state.

It contains no Secret reference, conversation content, private Codex ID, JSONL,
rollout, or discovery cache. Existing sessions are not backfilled from private
files.

### 3.7 Compatibility and transaction records

Compatibility observations keep endpoint, network, authentication, model, wire,
Provider API, Codex Runtime, Remote, resume, context, and discovery as separate
states with evidence schema, time, expiry, cost class, and sanitized codes.

Config transaction records keep expected revisions, plan digest, safe phase,
config fingerprint/digest, opaque Runtime backup reference, original
existence/mode metadata, lifecycle intent, and rollback attempted/verified
timestamps. Raw config and backups never enter SQLite.

### 3.8 Relationships and ownership

```text
Provider 1 -------- 0..1 active Credential
Provider 1 -------- * Runtime Profile
Provider 1 -------- * Compatibility Observation
Runtime Installation 1 -- * Runtime Profile
Runtime Installation 1 -- * Runtime Binding
Runtime Profile 1 -- * Runtime Binding history
Runtime Binding 1 -- * Session Binding
Runtime Binding 1 -- * Config Transaction
Runtime Session 1 -- 0..1 effective Session Binding
Job 1 -- 0..1 Config Transaction
Job 1 -- * AuditEvent
```

Control-plane rows are owned through the existing repository/application
service boundary. Runtime Secret records and config snapshots are not database
entities and are owned by `agentbox-runtime`.

### 3.9 Migration and compatibility strategy

- Use an additive migration; do not rewrite existing tables or rows.
- Create no Provider, Credential, Profile, Binding, or Secret automatically.
- Preserve all current Runtime and Project records.
- Present upgraded Runtimes as `unmanaged` through a read-model default.
- Migration is transactional and explicit; application startup does not hide
  migration work.
- Older binaries should tolerate the additional tables by ignoring them.
- Database downgrade is not used to undo an activated Runtime config. Config
  ownership must first be relinquished through verified Phase 11 rollback.
- Backup continues to use the SQLite online backup mechanism and excludes the
  Runtime Secret backend/master key unless a separate approved encrypted Secret
  backup design exists.

## 4. Secret Management Design

### 4.1 How plaintext stays outside Web/API

V1 uses a split flow:

```text
Local administrator
    -> protected local command executed in the agentbox-runtime identity
    -> TTY/protected stdin, never argv
    -> RuntimeSecretBackend
    -> opaque Secret reference + configured state

Browser / ordinary CLI
    -> creates Provider/Credential metadata using opaque reference only
    -> agentbox API / SQLite never receives the Secret value
```

The browser has no Secret entry or reveal field. The ordinary HTTP API has no
raw Secret request or response schema. A compromised Web/API process can at
most request typed operations using an existing opaque Credential reference; it
cannot read or choose filesystem paths for Secret material.

### 4.2 Storage location and filesystem policy

- Fixed Linux path selected by deployment policy under a Runtime-owned root;
  no caller path.
- Directory `0700`; records and master-key files `0600` or stricter.
- `agentbox-runtime` owner; `agentbox` and unrelated users cannot traverse.
- Every ancestor, owner, mode, file type, link count, symlink, and replacement
  condition checked with lstat/no-follow semantics.
- Opaque server-generated filenames.
- Restrictive temporary file, same-directory atomic replace, fsync where
  appropriate, and concurrent revision checking.
- Structured versioned envelope; never shell-sourceable environment files.

The final path is chosen during deployment design and must not be embedded in
the domain or accepted from API/CLI input.

### 4.3 Encryption boundary

The architecture recommends reviewed AEAD protection with a separately stored
Runtime-owned master key, subject to ADR approval. The envelope binds Secret ID,
credential kind, Secret version, Runtime identity, and schema version as
associated data. No custom cryptography is permitted.

The same-host software key cannot protect against root, full host compromise,
or a compromised `agentbox-runtime`. It protects a separated Secret-record copy
and detects tampering. TPM/kernel-keyring support remains future qualification,
not a v1 promise.

If the approved v1 chooses permission-only storage, documentation and UI must
state the weaker boundary. Implementation cannot begin until this decision is
accepted.

### 4.4 Access flow

- Provision: local interactive Runtime-identity command creates a new opaque
  Secret version.
- Resolve: only the Runtime Provider coordinator resolves an approved reference
  for a typed test or activation transaction.
- Inject: use the current public Codex credential-reference mechanism; Secret is
  placed only in a minimal child environment or trusted in-memory HTTP header.
- Observe: control plane receives configured/missing/valid/invalid/unknown and
  sanitized codes only.
- Retrieve: no operation returns the value.

The normal Runtime UDS does not expose generic Secret read/write, raw file,
environment, or config actions.

### 4.5 Rotation

Rotation creates a new Secret version without changing Provider identity,
RuntimeBindingID, endpoint, protocol, or model. The new version is tested, then
activated through a reviewed transaction. The old version is retained only for
the approved rollback window and is retired after verified success. There is no
automatic fallback to an old key.

### 4.6 Revoke and deletion

- Revoke prevents new resolution immediately after revision validation.
- An active or rollback-referenced version cannot be deleted.
- Metadata revocation and physical Secret deletion are separate, confirmed
  steps.
- Deletion verifies exact opaque identity, owner, type, link count, and expected
  revision before removing only the one AgentBox-owned record.
- Default uninstall preserves the Secret backend; no Phase 11 purge is planned.
- Missing master key or Secret record becomes `needs_attention`, never an empty
  or silently replaced credential.

### 4.7 Audit

Audit records Provider/Credential IDs, action, actor, time, request/Job ID,
Secret version numbers, sanitized outcome/error, and rollback verification. It
never records values, prefixes, suffixes, ciphertext, nonces, Authorization,
raw config, complete sensitive endpoints, prompts, completions, or Provider
responses.

## 5. Runtime Integration

### 5.1 Communication contract

The Worker sends typed, versioned Runtime requests containing:

- action enum;
- request and Job IDs;
- Runtime, Provider, Credential, Profile, Binding, and transaction IDs;
- expected revisions and plan digest;
- approved test kind or lifecycle intent.

It never sends shell, executable, argv, environment, raw path, raw TOML,
systemd unit, PID, signal, package name, header map, or Secret value. Runtime
resolves its fixed paths, adapters, Secret references, and executable policy
server-side.

Responses contain bounded states, compatibility dimensions, evidence class,
sanitized codes, transaction phase, and rollback status. They contain no raw
Runtime/Provider output or config.

### 5.2 Configuration flow

```text
Control plane validates metadata and revisions
    -> Worker creates durable plan Job
    -> Runtime discovers public capability and config ownership
    -> Runtime renders typed candidate
    -> full candidate validates against current public schema
    -> Runtime returns safe plan/digest, without applying
    -> administrator confirms exact plan
    -> activation Job revalidates every revision/fingerprint
```

The plan becomes stale if Provider, Credential, Profile, Binding, Runtime
capability, config fingerprint, active writer state, or lifecycle intent changes.

### 5.3 Activation

Activation runs under one per-Runtime lock:

1. revalidate plan and current state;
2. verify Provider/Credential and preflight compatibility;
3. detect active writer/turn/session state using public evidence;
4. create the complete protected config/lifecycle snapshot;
5. render and validate candidate;
6. atomically apply;
7. perform only the approved existing Codex lifecycle action if required;
8. test Provider, Codex Runtime, Remote, and applicable continuity dimensions;
9. commit DB binding state or enter rollback.

The root Helper is not used. The existing Codex Remote manager remains the sole
owner of start/stop/pair behavior.

### 5.4 Validation

Validation is layered. Endpoint/network/auth/model/wire/Provider API are direct
Provider evidence. Codex Runtime, Remote recovery, resume, context, and discovery
require their own tests. Untested layers remain `NOT_TESTED`; uncertain public
behavior remains `UNKNOWN` or `EXPERIMENTAL`.

### 5.5 Rollback and failure handling

Rollback restores:

- original config content or original nonexistence;
- owner/group/mode and managed-scope state;
- active Credential/Secret reference;
- Runtime Profile and Binding state;
- original Runtime/Remote lifecycle when safe;
- Session Binding state;
- protected snapshot retention metadata.

It then verifies config, permissions, binding, Provider behavior, Runtime
identity, Remote state, and applicable continuity evidence. Only complete proof
produces `Rollback verified`. A failed or uncertain step produces
`needs_attention`; mutation is not blindly replayed after a crash.

## 6. Codex Integration

### 6.1 What Provider Manager changes

Provider Manager may change only the explicitly approved AgentBox-managed
portion of Codex Provider configuration through `CodexProviderConfigAdapter`.
It preserves unrelated settings and uses only the then-current public Codex
contract. It does not edit private Runtime/session files, inspect conversation
history, change Pairing, or replace the existing Remote lifecycle manager.

### 6.2 New sessions and requests

After a binding is activated and verified, new Codex processes/requests use the
new Runtime Profile according to current public behavior. The Secret is resolved
inside `agentbox-runtime` and exposed only through the approved minimal child
environment. A new Session Binding captures the effective Provider/Profile
revision only when supported public evidence exists.

### 6.3 Existing sessions

- Existing sessions are not modified or automatically migrated.
- Pre-Phase-11 sessions are `legacy_unbound` unless a public contract proves
  their binding.
- A new active Provider does not rewrite an old Session Binding.
- The default guidance is to finish the active session and start a new one.
- Resume under a new Provider requires explicit approval and separate resume,
  context, and discovery evidence.
- Private Codex DB/JSONL/rollout/thread data is never inspected or rewritten.

### 6.4 Active sessions and user approval

The activation plan must show:

- current and target Provider/Profile;
- target destination and model;
- credential configured state;
- whether the current public contract says new requests only, reload, restart,
  new session, reauthentication, or unknown;
- active writer/session evidence and confidence;
- expected Remote and continuity checks;
- rollback scope.

Unknown active-writer or session impact defaults to `needs_attention`. The user
must quiesce work and approve the exact revision-bound plan; AgentBox does not
kill unknown processes or force a migration.

### 6.5 Pairing and Remote Control

Pairing remains an independent ephemeral Remote Control flow. Provider
activation never invokes Pair, logs out Codex, deletes Pair state, or treats a
Provider API key as a Remote credential. If a restart is required, it is routed
through the existing typed, non-root Remote lifecycle manager and explicitly
shown in the plan.

### 6.6 Rollback

Failure restores the pre-activation config, Credential reference, Binding, and
lifecycle, then verifies them. If the old session cannot be proved usable, the
result is not “fully restored”; AgentBox reports the exact failed continuity
dimension and supplies safe recovery guidance.

## 7. Claude Compatibility

Claude remains Runtime-only in Phase 11 v1:

- existing Claude installation/auth observations remain with `ClaudeAdapter`;
- Claude/tmux sessions remain with `ClaudeSessionManager`;
- existing Claude credentials remain in Runtime HOME under the official CLI's
  model;
- Provider Manager does not import, rotate, inspect, or replace Claude auth;
- no Claude config or session is changed by Codex Provider activation.

The domain may retain a future `ClaudeProviderConfigAdapter` interface, but it
must remain disabled. Future enablement requires an official public Claude Code
contract for external Provider selection, credential references, config
validation, lifecycle effects, and continuity. It also requires separate typed
options and tests; Codex/OpenAI-compatible assumptions cannot be reused.

## 8. API Design Proposal

All paths and schemas below are planning candidates. No endpoint is authorized
by this document.

### 8.1 Provider resources

| Method/path | Purpose | Boundary |
|---|---|---|
| `GET /api/v1/providers` | List non-secret Provider summaries | No credential value or raw endpoint evidence. |
| `POST /api/v1/providers` | Create typed Provider metadata | No API-key field; strict Provider-type schema. |
| `GET /api/v1/providers/{provider_id}` | Inspect Provider and compatibility matrix | Bounded, no raw Provider responses. |
| `PATCH /api/v1/providers/{provider_id}` | Edit non-identity metadata or create a revisioned identity change plan | Optimistic revision; no arbitrary options. |
| `POST /api/v1/providers/{provider_id}/validation-jobs` | Run selected validation layers | Explicit test kind/cost flag. |
| `POST /api/v1/providers/{provider_id}/activation-plans` | Create a dry-run plan | No mutation; binds all revisions and evidence. |
| `POST /api/v1/providers/{provider_id}/activation-jobs` | Execute a confirmed plan | Recent auth, CSRF, confirmation, durable Job. |
| `POST /api/v1/providers/{provider_id}/disable-jobs` | Disable only when no active/rollback reference remains | Does not delete Secret automatically. |

### 8.2 Credential resources

The HTTP API manages metadata and workflow state, not plaintext Secret input:

| Method/path | Purpose | Boundary |
|---|---|---|
| `POST /api/v1/provider-credentials` | Create Credential metadata/provisioning intent | No Secret value; returns opaque ID and local setup guidance. |
| `GET /api/v1/provider-credentials/{credential_id}` | Inspect configured/missing/rotation/revoked state | Never returns value, hint, ciphertext, or path. |
| `POST /api/v1/provider-credentials/{credential_id}/rotation-plans` | Plan use of an already locally provisioned Secret version | Revision-bound; no raw key. |
| `POST /api/v1/provider-credentials/{credential_id}/rotation-jobs` | Activate confirmed new Secret version | Retests auth/protocol and can roll back reference. |
| `POST /api/v1/provider-credentials/{credential_id}/revoke-jobs` | Revoke future use | Blocks if active/rollback requirements are unresolved. |

Physical Secret creation/deletion remains a local Runtime-identity operation,
not an ordinary Web API endpoint.

### 8.3 Runtime and binding resources

| Method/path | Purpose |
|---|---|
| `GET /api/v1/runtime-provider-profiles` | List typed non-secret profiles. |
| `POST /api/v1/runtime-provider-profiles` | Create a validated profile from Provider/Credential IDs. |
| `GET /api/v1/runtime-provider-bindings` | Inspect active/unmanaged/failed bindings. |
| `GET /api/v1/runtime-provider-bindings/{binding_id}` | Inspect revisions, current transaction, and compatibility. |
| `POST /api/v1/runtime-provider-bindings/{binding_id}/plans` | Plan bind/rebind without mutation. |
| `POST /api/v1/runtime-provider-bindings/{binding_id}/jobs` | Execute confirmed bind/rebind. |
| `GET /api/v1/runtime-session-provider-bindings` | Inspect bound/legacy/unknown sessions. |
| `POST /api/v1/provider-rollbacks` | Execute an approved previous/pre-management restoration. |

### 8.4 Common API controls

- Strict Pydantic schemas and unknown-field rejection.
- Opaque IDs; no paths, commands, env, argv, headers, raw config, or unit names.
- Optimistic revision and plan digest on every mutation.
- Recent authentication and exact Origin/Host + Session-bound CSRF for high-risk
  actions.
- Durable Jobs for network, Runtime, activation, rollback, and revoke actions.
- No-store for sensitive status/plan responses.
- Stable sanitized error codes and bounded metadata.
- Compatibility dimensions remain separate in every response.
- No raw Secret in request, response, Job, SSE, Audit, diagnostics, or OpenAPI
  examples.

## 9. Frontend Design Proposal

### 9.1 Navigation and information architecture

Add a `Providers` area without changing existing Codex Remote or Claude Session
pages into Provider editors. The active Provider may be summarized on the Codex
page, but Remote connection and Provider health remain distinct cards.

Suggested screens:

1. Provider list;
2. Provider details and compatibility matrix;
3. create/edit typed Provider metadata;
4. Runtime Profile and Binding details;
5. validation plan/progress;
6. activation confirmation;
7. transaction and rollback status;
8. credential setup/rotation guidance.

### 9.2 Provider list

Each card shows:

- display name and Provider type;
- model and safe destination authority;
- enabled/current state;
- credential state without value;
- Provider, Codex Runtime, and Remote summary separately;
- aggregate classification and evidence age.

Example state, not a promise:

```text
Provider: MyAPI
Type: OpenAI-compatible
Provider API: Reachable
Codex Request: PASS
Remote Control: Connected
Remote Compatibility: Experimental
```

### 9.3 Credential UX

V1 shows only configured/missing/rotation_pending/revoked/unknown and a safe
local provisioning command or guided steps. It has no paste, reveal, copy,
download, browser storage, or “show last four” behavior.

### 9.4 Activation confirmation

The confirmation must display:

- current and target Provider/Profile revisions;
- target destination, TLS policy, model, and cost class;
- credential configured state;
- config ownership/conflict state;
- Runtime restart, Remote interruption, session/new-request impact;
- stale or unknown evidence;
- exact rollback scope;
- an expiring confirmation bound to the plan digest.

The primary action is disabled when required evidence is missing, the plan is
stale, an active writer is unsafe, or rollback prerequisites are unavailable.

### 9.5 Health and rollback status

The UI presents the full matrix, not one green Provider badge. Rollback states
use exact language:

- `Rollback in progress`;
- `Rollback verified`;
- `Rollback attempted but verification failed`;
- `Manual recovery required`.

Missing thread discovery is `Thread not listed`, never `Thread deleted`.

### 9.6 Browser security

- No Secret input or output in v1.
- No Web Storage for Provider plans, credentials, or compatibility payloads.
- No raw HTML, Provider response, prompt, model output, or Runtime config.
- No source URL containing credentials.
- Authenticated responses remain no-store.
- Existing CSP, Secure Cookie, trusted-proxy, CSRF, and Origin/Host policies
  remain unchanged.

## 10. Security Review

### 10.1 Secret leakage

Primary leak surfaces are Web/API bodies, SQLite/WAL/SHM, Job payloads/events,
Audit, journal, argv, environment dumps, config snapshots, Provider errors,
browser storage, screenshots/traces, diagnostics, reports, backups, and Git.

Controls:

- Runtime-only Secret custody;
- local TTY/protected-stdin provisioning;
- no retrieval operation;
- no raw Secret field in ordinary API/DB schemas;
- minimal child environment or in-memory Authorization header;
- bounded sanitized output and allowlisted Audit metadata;
- comprehensive deterministic canary scans;
- Secret store/master key excluded from ordinary backup and reports.

### 10.2 Privilege escalation

Provider UDS messages cannot express command, executable, argv, env, path, PID,
signal, systemd unit, package, mode, owner, or raw config. Runtime resolves fixed
policy internally. Root Helper gains no Provider action and never runs Codex or
Provider tests. Distinct-UID tests must prove the control plane cannot read
Runtime Secrets or config snapshots.

### 10.3 Malicious Provider endpoint

Risks include SSRF, metadata access, internal network scanning, DNS rebinding,
redirect credential forwarding, TLS downgrade, hostile streaming, oversized
responses, misleading model lists, and data exfiltration.

Controls include Provider-type-specific endpoint policy, fixed official
destination, normalized compatible endpoints, HTTPS by default, no userinfo or
arbitrary headers, redirect restrictions, DNS/destination revalidation, TLS
verification, bounded time/bytes/events, and explicit data-boundary confirmation.

### 10.4 Insecure Runtime configuration

Risks include raw-key TOML, duplicate blocks, unrelated-setting loss, stale plan,
symlink/replacement race, manual-edit conflict, unsafe mode, partial write,
restart failure, and incomplete rollback.

Controls include typed adapter schemas, Secret references only, full parse and
validation, managed scope, fingerprint/revision checks, no-follow operations,
atomic replace/fsync, protected snapshot, per-Runtime serialization, and
verified rollback.

### 10.5 Session and continuity safety

Activation must not rewrite or falsely attribute existing sessions. Active or
unknown writer state blocks or requires the separately approved maintenance
flow. Resume, context, and discovery are independent. No automatic Provider
failover or private session mutation is allowed.

### 10.6 Audit requirements

Audit must cover Provider create/edit/disable/test, Credential metadata/create-
intent/rotate/revoke, activation plan/request/success/failure, binding changes,
rollback request/attempt/verification, and manual recovery state. It records
opaque targets, revisions, actor, time, request/Job correlation, result, and
sanitized codes only.

### 10.7 Single-node isolation statement

Phase 11 v1 remains single-administrator and one shared Runtime identity. It
does not provide tenant isolation or enterprise RBAC. Future multi-user support
requires separate authorization and execution identities, not a placeholder
`tenant_id` column.

## 11. Testing Strategy

### 11.1 Backend and database tests

- Domain identity separation and Provider-type schemas.
- Revision/stale-plan and uniqueness constraints.
- Additive migration on fresh and v0.3.0-rc.1 databases.
- No automatic Provider/Credential/Binding creation.
- Repository/service authorization and lifecycle state machines.
- Job lease/crash recovery with uncertain mutation becoming
  `needs_attention`.
- Audit allowlists and forbidden Secret/config fields.
- API strict-field, recent-auth, CSRF, Origin/Host, idempotency, and no-store
  behavior.

### 11.2 Runtime protocol tests

- Wrong UID/GID, socket mode/ownership, protocol version, unknown action/field,
  malformed/oversized/concatenated frame, timeout, and concurrency cap.
- No executable, argv, shell, env, cwd, raw path/config, PID, signal, unit, mode,
  user, group, package, or header-map fields.
- Runtime resolves fixed config/Secret/executable policy itself.
- Cross-protocol requests cannot reach Helper or existing Runtime actions.

### 11.3 Secret security tests

- Distinct-UID access denials.
- Directory/file owner and mode.
- Symlink, hardlink, path replacement, unsafe parent, duplicate ID, race,
  truncated/corrupt envelope, wrong key, wrong associated data, and concurrent
  rotation.
- TTY/stdin-only provisioning; argv, environment, Web/API, log, and history
  negative tests.
- Canary scans across DB/WAL/SHM, journal, Audit, Job/Event, reports,
  diagnostics, config/backup, process inspection, frontend artifacts, and Git.
- Reinstall/update/rollback/default uninstall preservation.

### 11.4 Provider and endpoint tests

- Official endpoint fixed-policy tests.
- Compatible URL normalization, userinfo, scheme, fragment, control character,
  Unicode, port, redirect, TLS, DNS rebinding, metadata/link-local/private
  destination, timeout, byte/event/decompression bounds.
- Authentication accepted/rejected/unknown.
- Model availability and protocol/streaming completion fixtures.
- Paid-test confirmation and cost-class reporting.
- Provider success never fills Runtime/Remote/continuity states.

### 11.5 Config transaction tests

- Existing file absent/present, comments/unrelated settings, duplicate managed
  scope, malformed TOML, schema mismatch, ownership/mode drift.
- Symlink/replacement race, concurrent manual edit, stale fingerprint,
  temporary-file failure, short write, fsync failure, rename failure, disk full,
  and crash at every phase.
- Complete original-state restoration and false-positive rollback rejection.
- Snapshot never enters SQLite, Job, Audit, logs, reports, or diagnostics.

### 11.6 Codex Runtime and continuity tests

- Current public help/config fixtures for supported, unsupported, and unknown
  versions.
- Secret-reference rendering without raw values.
- New request with active binding.
- Active/unknown writer and duplicate Runtime protection.
- Existing legacy session remains untouched.
- Fake A/B Provider Runtime request, Remote recovery, resume, context use, and
  discovery tested independently.
- Pair/login state remains independent and Pair is never invoked by switching.
- No private Codex state access or mutation.

### 11.7 Rollback and recovery tests

Inject failure during Provider preflight, candidate validation, atomic apply,
Secret resolution, Runtime stop/start, Provider request, Codex request, Remote
recovery, resume, context, discovery, DB commit, and post-commit verification.

Each case verifies config/nonexistence, owner/mode, Secret reference, Provider/
Profile/Binding state, Runtime/Remote state, session state, backup identity, and
final status. Corrupt/missing backup or uncertain lifecycle must never produce
`Rollback verified`.

### 11.8 Frontend tests

- Provider list/details and empty/unmanaged state.
- Credential configured/missing/rotation/revoked/unknown without value.
- Full partial-success compatibility matrix.
- Stale activation plan, active-session block, restart impact, cost/privacy
  confirmation, Job progress, activation failure, verified/failed rollback.
- No Web credential form, storage, raw HTML, external navigation, or sensitive
  screenshot/trace.
- Desktop/mobile layout and existing auth/Remote/Claude/Project regression.

### 11.9 Deployment and upgrade tests

- Phase 11 directories/owners/modes in fixture root.
- API/Worker remain `agentbox`; Runtime remains `agentbox-runtime`; Helper
  unchanged.
- Fresh install, install-repeat, upgrade from v0.3.0-rc.1, partial install,
  application rollback, and default uninstall preservation.
- Existing Runtime config/auth/sessions/Projects remain unchanged before opt-in.
- OpenCloudOS real-host test only after automated gates and explicit approval;
  Ubuntu/Rocky/Debian claims remain at their actually validated level.

### 11.10 Required regression and quality gates

- Existing Backend, Frontend, Security, E2E, Deployment, and deployment-gate.
- Ruff, Black, mypy, pytest, migrations, pip-audit.
- Frontend lint, formatting, typecheck, unit tests, build, and audit.
- Secret scan, dependency review, repository-boundary scan, action pin policy,
  and forbidden-primitive scan.
- Phase 11 stable aggregate gate after it exists and proves stable; Protect main
  changes only in a separate reviewed Ruleset finalization.
- No open P0/P1 security issues or unresolved blocking review threads.

## 12. Open Decisions

The following decisions require approval before the related implementation
milestone starts.

### 12.1 Required before any Secret implementation

1. **Encryption method:** AEAD algorithm/library and envelope version, or an
   explicit approval of permission-only storage.
2. **Master-key custody:** Runtime-owned software key, qualified OS/hardware
   mechanism, generation/recovery, and failure behavior.
3. **Secret backup:** excluded with credential re-entry, separately encrypted
   export, or another approved mechanism.
4. **Secret ingress:** exact local Runtime-identity command, authorization, TTY/
   stdin rules, and whether automation is ever allowed.

### 12.2 Required before config mutation

5. **Codex ownership scope:** managed block/keys, marker/version, config target,
   validation method, and behavior when manual config conflicts.
6. **Snapshot retention:** duration, count, disk limit, and retirement rules for
   config snapshots and old Secret versions.
7. **Custom CA policy:** whether supported and how trust objects are selected
   without arbitrary paths.

### 12.3 Required before activation

8. **Switching behavior:** absolute block versus confirmed maintenance flow when
   active writer/session state is unknown.
9. **Minimum compatibility:** whether Codex activation requires Provider +
   Runtime only or also Remote recovery. Recommendation: require Remote recovery
   for Remote-managed use.
10. **Session policy:** finish-and-create-new default, optional public resume,
    and when a Session Binding may be recorded.
11. **Private network policy:** compatible Provider access to RFC1918/ULA
    destinations versus requiring the future Local Provider type.
12. **Paid tests:** allowed surfaces, per-run consent, budget, prompt, output,
    and retention.
13. **Credential sharing:** prohibited in v1 or explicitly supported across
    Provider definitions.

### 12.4 Product scope confirmation

14. Confirm Phase 11 v1 is Linux + Codex + Official OpenAI/OpenAI-compatible
    only.
15. Confirm Claude remains Runtime-only.
16. Confirm Local Provider is an interface/fixture only, not a supported v1
    activation target.
17. Confirm there is no Web Secret input in v1.
18. Confirm no automatic Provider fallback/failover.
19. Confirm no multi-user tenancy, enterprise RBAC, billing, or cloud Secret
    service.

## Planning Completion State

This document defines implementation order and gates only. It creates no
Provider, Secret backend, migration, API, CLI, UI, test, config change, Runtime
restart, branch, commit, or release. Phase 11 implementation remains
**NOT STARTED** until the architecture and product decisions above are approved.
