# AgentBox Phase 11 — Implementation Readiness Review

Status: **Final design review — implementation not authorized**
Decision: **BLOCKED**
Scope: Provider / Secret / Runtime Continuity architecture readiness
Repository baseline: `ForceMind/agentbox` at
`1c2005de59b1c5063b260591206a8411c7e5b1a5`
Release baseline: `v0.3.0-rc.1`

Reviewed architecture baseline:

- `PHASE11_PROVIDER_MANAGER_PROPOSAL.md`;
- `PHASE11_IMPLEMENTATION_PLAN.md`;
- `PHASE11_1_PROVIDER_DOMAIN_MODEL_ADR.md`;
- `PHASE11_2_RUNTIME_CAPABILITY_CONTRACT_ADR.md`;
- `PHASE11_3_SECRET_BOUNDARY_ADR.md`;
- `PHASE11_4_CONFIG_TRANSACTION_FRAMEWORK_ADR.md`;
- `PHASE11_5_PROVIDER_VALIDATION_PIPELINE_ADR.md`;
- `PHASE11_6_CODEX_PROVIDER_ADAPTER_DRY_RUN_ADR.md`;
- `PHASE11_7_RUNTIME_BINDING_ACTIVATION_CONTINUITY_ROLLBACK_ADR.md`.

This review creates no production code, feature branch, migration, database
change, API, UI, Runtime operation, Provider/Secret object, commit, or approval.

## 1. Executive Summary

### 1.1 Phase 11 objective

Phase 11 adds a Provider Manager to AgentBox while preserving the separation
between:

```text
Codex Remote Control
    manages connection, pairing, observation, and approved lifecycle

Provider Manager
    manages which validated AI Provider a Runtime is intended to use
```

The target v1 architecture remains Linux, single-server, single-administrator,
and Codex-first. Provider metadata and orchestration belong to the control plane;
Runtime execution, local configuration, bounded Secret use, and actual Provider
requests remain under the non-root `agentbox-runtime` identity. Root Helper gains
no Provider or Secret authority.

### 1.2 Architecture maturity

Conceptual architecture maturity is **high**. The seven design layers form a
coherent chain:

```text
Provider Model
    -> Runtime Capability Contract
    -> Secret Boundary
    -> Config Transaction Framework
    -> Provider Validation Pipeline
    -> Codex Adapter and Dry-run
    -> Runtime Binding / Activation / Continuity / Rollback
```

The documents consistently preserve identity separation, non-root execution,
typed Runtime protocols, non-secret control-plane records, public Runtime
contracts, immutable evidence, explicit approval, fail-closed compatibility,
and verified recovery.

However, conceptual coverage is not the same as implementation readiness.
Every Phase 11 ADR remains **Proposed — awaiting human approval**, and several
security-critical choices were intentionally left open.

### 1.3 Implementation readiness decision

**BLOCKED**

Production engineering implementation must not begin yet. The blocking issues
are:

1. the Phase 11 ADR set has not been accepted/frozen;
2. the then-current public Codex Provider/config/credential/lifecycle/session
   contract has not been revalidated and captured as reviewed fixtures;
3. Secret encryption library/algorithm, master-key custody/recovery, local
   ingress, and backup policy have not been approved;
4. exact Codex managed-config scope, lossless preservation strategy, config
   validation method, and restart behavior remain undecided;
5. endpoint/private-network/DNS-rebinding/redirect/custom-CA policies are not
   frozen;
6. minimum activation evidence, active/unknown session policy, Runtime lock,
   commit-pending recovery, and rollback retention remain undecided;
7. Phase/ADR numbering has collisions that require a canonical registry before
   decisions become stable implementation references.

### 1.4 What may happen next

The next authorized step should be **Phase 11.0 contract validation and decision
freeze**, not feature coding. That work can produce reviewed public-contract
evidence, resolve product/security decisions, normalize decision identifiers,
and change the required ADRs from Proposed to Accepted.

After those gates pass, the first production engineering slice should be the
non-secret Provider core model with additive schema and all activation/Secret/
Runtime behavior disabled.

## 2. Architecture Completeness Review

### 2.1 Summary matrix

| Architecture area | Conceptual design | Decision closure | Implementation readiness | Principal risk |
|---|---|---|---|---|
| Provider Model | Complete | Incomplete | Blocked pending scope/identity policy approval | Identity or lifecycle coupling |
| Runtime Capability | Complete | Incomplete | Blocked pending current Codex contract fixtures | Capability guessed from version/private behavior |
| Secret Boundary | Complete | Critically incomplete | Blocked | Credential disclosure or unrecoverable key custody |
| Transaction Framework | Complete | Incomplete | Blocked for mutation | Partial state and false-positive recovery |
| Validation Pipeline | Complete | Incomplete | Blocked for live validation | SSRF, credential forwarding, misleading compatibility |
| Codex Adapter | Complete boundary | Critically incomplete contract | Blocked | Config corruption or undocumented coupling |
| Activation/Rollback | Complete state model | Critically incomplete policy | Blocked | Session disruption, split state, unverified rollback |

### 2.2 Provider Model

**Complete**

- Provider, Credential, Runtime Profile, Runtime Binding, Session Binding, and
  Compatibility Observation have separate identities and responsibilities.
- Provider active state is derived from Runtime Binding, not stored globally.
- Credential rotation does not replace Provider identity.
- Session Binding is immutable effective-state evidence.
- Provider-specific options use typed adapters rather than a universal bag.
- Claude remains Runtime-only and Local Provider remains inactive by default.

**Incomplete**

- Identity-field change versus revision/replacement policy needs final approval.
- Credential sharing across Provider definitions remains unresolved.
- Provider disable/delete rules against historical bindings, sessions, and
  rollback references need exact policy.
- V1 product scope has not been formally confirmed.
- Database constraints and read models remain proposals only.

**Risks**

- A schema implemented before identity policy freezes could require destructive
  migration later.
- A generic JSON option field could smuggle Secret, path, header, config, or
  executable data.
- A migration could accidentally create an active/default Provider for existing
  users.

**Assessment:** Conceptually complete; safe to implement only after the scope
and identity decisions are accepted.

### 2.3 Runtime Capability Contract

**Complete**

- Capabilities are typed evidence, not permission or execution guarantees.
- Read-only discovery precedes mutation.
- Control Plane cannot select executable, argv, environment, path, PID, signal,
  tmux target, package, or unit.
- Existing peer-authenticated UDS and Runtime Adapter boundaries are preserved.
- Evidence outcome, confidence, freshness, source, and expiry remain separate.
- Claude capability remains Runtime/session scoped.

**Incomplete**

- Exact wire schemas, capability names, TTLs, cache invalidation, and adapter
  versioning remain implementation artifacts.
- Current Codex public help/config/provider/session behavior has not been
  qualified for Phase 11.
- Public evidence for active writer, Runtime Profile validation, session resume,
  and discovery is unknown.

**Risks**

- Version-only enablement could promote unsupported mutation.
- Raw/public CLI output could leak credentials or become an injection surface.
- Same-UID Runtime compromise remains a residual trust-boundary risk.

**Assessment:** Boundary complete; current Codex contract validation is a hard
prerequisite.

### 2.4 Secret Boundary

**Complete**

- Provider identity, Credential metadata, Secret Material, Secret version, and
  Runtime identity are separate.
- Plaintext is prohibited from normal database fields, Web/API, argv, URLs,
  config, logs, Audit, Jobs, reports, Git, and ordinary backups.
- The recommended store is Runtime-owned, local, versioned, and outside SQLite.
- Runtime use is action-specific and minimal; no generic retrieval exists.
- Root Helper has no Secret authority.
- Local provisioning is preferred over Web Secret entry.

**Incomplete — critical**

- AEAD algorithm and reviewed library are not selected.
- Envelope format/version and associated-data schema are not frozen.
- Master-key generation, custody, storage, rotation, loss, and recovery are not
  approved.
- Exact local ingress command, TTY/stdin authorization, automation policy, and
  memory/dump handling are unresolved.
- Backup policy is undecided between re-entry-only and a separately encrypted
  mechanism.
- Codex's current public credential-reference capability is unvalidated.
- Rotation and prior-version retention periods are unspecified.

**Risks**

- Choosing storage before key custody could create encryption theater.
- Incorrect ingress/delivery could expose API keys through history, process
  inspection, environment dumps, config, or browser surfaces.
- Key loss could make all Provider credentials irrecoverable without an honest
  documented recovery policy.

**Assessment:** Architecture direction is strong, but any Secret implementation
is blocked.

### 2.5 Config Transaction Framework

**Complete**

- Runtime mutation is a durable recoverable state machine, not distributed
  ACID or a one-shot file write.
- Plan and execution are separate.
- Validation, protected snapshot, apply, post-verification, commit-pending,
  rollback, reconciliation, and needs-attention states are defined.
- Control Plane stores non-secret workflow metadata; Runtime stores protected
  local journal/snapshot.
- Runtime owns file application; control plane never receives raw config.
- External edits and stale plans fail closed.
- Rollback success requires independent verification.

**Incomplete**

- Exact transaction persistence schema and transition compare-and-swap rules
  are not frozen.
- Runtime journal/snapshot location, format, encryption domain, integrity, and
  retention are undecided.
- Lock/lease primitives and stale-lock recovery are unresolved.
- Commit-pending reconciliation policy needs exact rules.
- Filesystem primitives and preservation of ACL/xattr/SELinux metadata require
  platform qualification.
- Multi-target semantics and cancellation boundaries are open.

**Risks**

- Process death between Runtime apply and database commit can create split
  state.
- A symlink/replacement/manual-edit race can overwrite user configuration.
- Snapshot corruption or false-positive rollback can leave Codex unusable while
  AgentBox reports success.

**Assessment:** State model complete; config mutation remains blocked until
storage, locking, platform, and reconciliation decisions are accepted.

### 2.6 Provider Validation Pipeline

**Complete**

- Definition, capability, Credential boundary, endpoint/network, authentication,
  model/wire, Provider API, Runtime, Remote, and continuity stages remain
  independent.
- Offline validation and live validation are distinct.
- Evidence is immutable, scoped, versioned, expiring, non-secret, and never an
  execution guarantee.
- Provider success cannot fill Runtime/Remote/continuity dimensions.
- Retry/cooldown/cost and sanitized audit concepts are defined.
- Endpoint validation is Provider-type-specific and fail closed.

**Incomplete**

- Evidence TTL and activation-threshold policies are not approved.
- Exact private/LAN/loopback policy is unresolved.
- DNS rebinding, redirect, proxy, custom CA, and IPv4/IPv6 enforcement choices
  require implementation design and platform tests.
- Paid-test payload, budget, confirmation lifetime, retry, and retention are
  undecided.
- Evidence persistence schema and pruning remain proposals.

**Risks**

- SSRF, cloud metadata access, internal-network scanning, DNS rebinding, TLS
  downgrade, redirect credential forwarding, and malicious streaming.
- Authentication retries could become a credential oracle.
- A simple endpoint `PASS` could be presented as full compatibility.

**Assessment:** Pipeline semantics complete; live validation and activation use
are blocked pending endpoint/security/product policies.

### 2.7 Codex Provider Adapter and Dry-run

**Complete**

- A Runtime-side adapter maps typed Runtime Profiles to the public Codex contract.
- Raw TOML, arbitrary keys, caller paths, environment maps, and private Codex
  state are prohibited.
- Dry-run is read-only, semantic, revision-bound, non-secret, and performs no
  write/restart/Provider call.
- Existing config must be fully parsed and unrelated settings preserved.
- Unknown compatibility fails closed.
- Existing sessions are not implicitly migrated.
- Runtime reconstructs and revalidates private candidates at apply time.

**Incomplete — critical**

- The current public Codex Provider/config schema and supported fields are not
  recorded as approved fixtures.
- Managed-scope marker/ownership and fixed target resolution are undecided.
- No approved lossless TOML preservation/validation strategy exists.
- Supported Codex versions and contract-profile matching rules are not frozen.
- Credential-reference support and child-delivery semantics are unvalidated.
- Reload/restart/new-session/reauthentication behavior is unknown.
- Public active-writer/session/effective-binding evidence is unproven.

**Risks**

- Building against observed private formats would create a fragile unsafe
  permanent contract.
- Whole-file serialization could discard user settings or inline credentials.
- Incorrect lifecycle assumptions could break Remote Control or active sessions.

**Assessment:** Adapter boundary complete; implementation is blocked until
current public-contract validation and ownership/preservation decisions finish.

### 2.8 Runtime Binding, Activation, Continuity, and Rollback

**Complete**

- Runtime Binding is separate from Provider/Profile/Session identity.
- Only one committed active binding exists per Runtime.
- Requested, validated, planned, approved, activating, verifying, commit-pending,
  active, rollback, recovered, and needs-attention states are distinguished.
- Existing sessions remain unchanged; v1 is new-session-first.
- Per-Runtime locking and AgentBox-managed admission fencing are required.
- Provider, Runtime, Remote, resume, context, tools, streaming, Responses, and
  discovery verification remain independent.
- No automatic Provider fallback or automatic Pairing exists.
- Crash recovery reconciles control-plane and Runtime journals.

**Incomplete — critical**

- Minimum evidence required for activation is not approved.
- Unknown/active session behavior is undecided between absolute block and an
  experimental maintenance workflow.
- Exact admission-fence integration and unmanaged-work treatment are unresolved.
- Transaction timeouts, lock leases, crash-recovery authority, and commit-
  pending policy are not frozen.
- Snapshot/prior Secret/binding retention and revoked-prior-Credential behavior
  are unresolved.
- Restart/Remote recovery and public session-continuity evidence are unqualified.

**Risks**

- An active turn or new session can race a global configuration change.
- Runtime apply can succeed while control-plane binding commit fails.
- Rollback may restore config but not Provider credential, Runtime, Remote, or
  session usability.
- Automatic recovery can repeat a paid request or destructive lifecycle action.

**Assessment:** Lifecycle model complete; activation implementation is blocked.

### 2.9 Architecture governance gaps

Two governance issues must be corrected before implementation references ADR
numbers in code, migrations, protocol schemas, or tests:

1. every Phase 11 ADR is still Proposed, not Accepted;
2. Phase 11.4 already uses `ADR-041`, while Phase 11.5 had to introduce
   qualified `ADR-11.5-041` identifiers; a canonical registry is absent.

The current task is also named “Phase 11.8 Implementation Readiness Review,”
while `PHASE11_IMPLEMENTATION_PLAN.md` uses implementation milestone 11.8 for
API/CLI. Architecture-review numbering and engineering-milestone numbering must
be disambiguated before scheduling or release reporting.

## 3. Frozen Architecture Decisions

The following decisions should become explicit Accepted implementation
constraints. Until approved, they are freeze candidates rather than authorization.

### 3.1 Process and trust boundaries

1. `agentbox` owns Web/API/Worker/SQLite, intent, authorization, orchestration,
   evidence metadata, binding state, and Audit.
2. `agentbox-runtime` owns local Runtime inspection, config application, Secret
   use, Provider requests, process state, and recovery evidence.
3. API/Worker remain non-root and cannot read Runtime HOME, Secret store, config
   snapshots, Projects directly, or child environments.
4. Root Helper gains no Provider, Secret, config, validation, package, Runtime,
   or session action.
5. Provider management adds no Web shell, generic HTTP proxy, arbitrary command,
   config editor, path, argv, env, PID, signal, package, or systemd primitive.

### 3.2 Domain and identity

6. Provider, Credential, Secret version, Runtime Profile, Runtime Binding,
   Runtime installation, Session, and Session Binding identities remain distinct.
7. Active state belongs to Runtime Binding; Provider has no global active flag.
8. One committed active Runtime Binding is allowed per Runtime installation.
9. Session Binding is immutable effective-state evidence and never contains a
   Secret reference or conversation content.
10. Existing/pre-Phase-11 sessions remain unchanged and normally
    `legacy_unbound`.
11. Existing v0.3.0-rc.1 installations upgrade to `UNMANAGED`; no Provider,
    Credential, Profile, or active Binding is auto-created.

### 3.3 Secret boundary

12. Plaintext Provider Secrets never enter ordinary SQLite fields, Web/API,
    ordinary CLI argv, config, URL, logs, Audit, Jobs, reports, Git, or default
    backups.
13. Provider Secret records and key custody are Runtime-owned and outside the
    control-plane database.
14. Secret provisioning is local and outside ordinary Web/API in v1.
15. Runtime resolves only one exact Secret version for one typed approved
    operation; no retrieval/export/list-all interface exists.
16. Existing root/Codex/Claude/GitHub credentials are never copied, imported,
    chowned, or exposed.

### 3.4 Runtime and configuration

17. Runtime capabilities are typed evidence, not authorization or success
    guarantees.
18. Runtime adapters use only current public contracts and fixed probes/actions.
19. Control Plane never reads/supplies raw Runtime config; Runtime owns parsing,
    candidate reconstruction, application, verification, and restoration.
20. Codex changes are semantic, typed, scope-limited, preservation-aware, and
    never raw whole-file replacement.
21. Dry-run is mandatory, read-only, immutable, revision-bound, and Secret-free.
22. Unknown mandatory Codex compatibility fails closed.

### 3.5 Validation, activation, continuity, and recovery

23. Validation produces expiring evidence; it is not execution or a permanent
    Provider-health guarantee.
24. Endpoint, network, authentication, model, wire, Provider API, Runtime,
    Remote, resume, context, tools, streaming, Responses, and discovery outcomes
    remain independent.
25. Activation requires validate, dry-run plan, recent approval, transaction
    preflight, protected snapshot, Runtime-owned apply, layered verification,
    then commit or verified rollback.
26. Runtime application does not make a Binding active; commit occurs only after
    required post-validation.
27. Existing sessions are never implicitly migrated, rebound, relabeled,
    restarted, or stopped.
28. Activation uses one per-Runtime transaction lock and an AgentBox-managed
    admission fence; external changes are conflicts.
29. Pairing, Codex login, Provider authentication, Remote connection, and
    session continuity remain separate.
30. No automatic Provider fallback/failover exists.
31. Rollback success requires independent config, permissions, Secret reference,
    binding, lifecycle, Runtime, Remote, and required continuity verification.
32. Unknown or contradictory state becomes reconciliation/`NEEDS_ATTENTION` and
    blocks further mutation; no blind replay.

### 3.6 Product scope freeze candidates

33. V1 is Linux, one server, one administrator, and Codex Provider management
    only.
34. Official OpenAI and approved typed OpenAI-compatible HTTP Providers are the
    only initial external Provider classes.
35. Claude remains Runtime/tmux management only.
36. Local Provider remains an inactive interface/fixture until a separate policy
    is approved.
37. No Web Secret input, multi-tenancy, enterprise RBAC, billing, external
    Secret-manager integration, or automatic network/firewall/proxy management
    is introduced.

## 4. Remaining Design Risks

### 4.1 Risk register

| Severity | Type | Risk/decision | Required closure |
|---|---|---|---|
| Critical | Governance | All ADRs remain Proposed and no canonical decision registry exists | Human architecture/security approval; canonical IDs; accepted baseline commit before code |
| Critical | Technical/security | Current public Codex Provider/config/credential/lifecycle/session contract is unqualified | Revalidate official public contract; versioned sanitized fixtures; capability matrix |
| Critical | Security | Secret AEAD/library, envelope, master-key custody/recovery, ingress, and backup are undecided | Accepted Secret implementation ADR and failure/recovery policy |
| Critical | Data integrity | Codex managed scope, lossless preservation, validation method, and restart semantics are undecided | Accepted config ownership/adapter contract with fixture proof |
| Critical | Runtime safety | Minimum activation evidence and unknown active-session policy are undecided | Product/security decision; public evidence requirements; default fail-closed policy |
| Critical | Recovery | Commit-pending/crash recovery and rollback eligibility with revoked prior Secret are not frozen | Exact reconciliation table, recovery owner, retention and recovery gates |
| High | Network security | Private/LAN/local endpoint policy, DNS rebinding, redirects, proxy, custom CA are unresolved | Provider-type-specific network ADR and adversarial fixture plan |
| High | Concurrency | Control-plane lease, Runtime lock, admission fence, stale-lock behavior are unspecified | Fixed lock ordering, lease/recovery protocol, session-race tests |
| High | Persistence | Transaction/evidence/journal/snapshot schemas and retention remain proposals | Schema/version/integrity/retention decisions before related migrations |
| High | Product/security | Paid test payload, budget, consent, retries, and storage are unresolved | Per-run cost/data policy; no real tests before approval |
| High | Continuity | Public Remote/resume/context/discovery evidence may be unavailable | Define minimum activation class and show unsupported/unknown honestly |
| High | Credential lifecycle | Sharing, rotation overlap, revocation, delete, and rollback references lack exact policy | Credential reference and retention invariants |
| Medium | Product | V1 scope, no Web Secret input, Local deferred, Claude Runtime-only need formal sign-off | Product decision record |
| Medium | API security | Exact API/CLI request schemas, idempotency, confirmation, and error codes are not frozen | Later API/CLI ADR after lifecycle decisions |
| Medium | Evidence | TTL, pruning, invalidation, trust/provenance, and clock anomalies are unspecified | Versioned evidence policy |
| Medium | Platform | ACL/xattr/SELinux/fsync/filesystem durability qualification incomplete | Linux platform matrix and fault-injection acceptance criteria |
| Medium | Governance | “Phase 11.8” denotes both readiness review and API/CLI milestone | Rename/namespace architecture versus engineering milestones |
| Medium | Governance | ADR-041 collision required qualified Phase 11.5 IDs | Central ADR registry and renumbering/mapping before Accepted state |
| Low | UX | Exact labels for partial compatibility and manual recovery are not finalized | UX review after API read models freeze |
| Low | Operations | Snapshot/evidence diagnostics presentation is not finalized | Sanitized doctor/support design without retrieval primitives |

### 4.2 Critical blockers

Implementation remains blocked until all Critical rows are resolved. It is not
safe to begin “just the Secret store,” “just the Codex writer,” or “just the
activation endpoint” independently because those are precisely the trust
boundaries with unresolved decisions.

### 4.3 High-risk work that may be deferred from the first slice

The first non-secret foundation may defer High-risk live behavior when:

- activation remains unreachable;
- no Secret store or real Credential value exists;
- no Runtime mutation or Provider network request is possible;
- all new Runtime Bindings remain `UNMANAGED`/non-active;
- schema/API fields cannot later become generic escape hatches.

This does not change the overall `BLOCKED` decision. It defines the safe shape
of the first engineering PR after contract/ADR approval.

## 5. Implementation Scope Proposal

### 5.1 Smallest safe vertical slice

After Phase 11.0 decisions are accepted, the first implementation slice should
be **non-secret Provider domain foundation with unmanaged/read-only state**:

- typed Provider, Credential-metadata, Runtime Profile, Runtime Binding, Session
  Binding, and Compatibility Observation identities/value objects;
- explicit Provider type enums with Official OpenAI and OpenAI-compatible
  metadata schemas; Local and Claude Provider activation disabled;
- repository interfaces and application services for non-secret create/list/
  inspect/revision operations only;
- an additive SQLite migration for non-secret metadata, with no Secret/config/
  path/command/header/environment columns or generic privileged JSON bag;
- explicit `UNMANAGED` derived/read state for existing installations;
- revision and relationship constraints;
- feature/capability gates that make validation, Secret provisioning, dry-run,
  activation, rollback, API mutation, and UI entry unreachable;
- Audit allowlists for any non-secret metadata operations introduced;
- fresh-database and v0.3.0-rc.1 upgrade/rollback compatibility tests.

This slice creates no Provider automatically and performs no Runtime RPC. Its
observable success criterion is that existing AgentBox behavior is unchanged and
the new domain can represent an empty/unmanaged state safely.

### 5.2 Why this is the first safe slice

It exercises the highest-value identity and persistence invariants without
crossing the Secret, network, Runtime configuration, lifecycle, or session
boundaries. It also exposes schema mistakes early, before real credentials or
mutable Runtime state exist.

### 5.3 Explicit exclusions from the first slice

Do not build first:

- Secret encryption/store/key generation/provisioning;
- Web/API/CLI Secret input;
- Provider endpoint/network/authentication tests;
- Codex config parser/writer or managed block;
- Provider activation, restart, rollback, or recovery executor;
- Runtime Binding active transition;
- session migration/rebind;
- Local Provider activation;
- Claude Provider support;
- frontend Provider pages;
- automatic fallback, health monitoring, paid requests, custom CA, proxy, or
  private-LAN support;
- root Helper actions or systemd/package/network automation.

### 5.4 Subsequent safe sequence

After the first slice passes review:

1. read-only Runtime capability protocol and Codex public-contract fixtures;
2. Secret backend only after Secret ADR acceptance, with activation absent;
3. fixture-only config transaction engine and fault-injected rollback;
4. fake-Provider validation pipeline with no real credentials;
5. Codex Adapter dry-run with no writes;
6. activation/continuity/rollback behind a disabled feature gate using fake A/B
   Providers first;
7. typed API/CLI surfaces;
8. frontend read models and confirmation workflows;
9. migration/deployment/compatibility/release gate and explicitly authorized
   real-host/provider validation.

Each step remains independently reviewable and cannot reach later mutation
capabilities merely because earlier schema/code exists.

## 6. Proposed Feature Branch Strategy

No branch is created by this review. Suggested future branches are:

### 6.1 Prerequisite architecture/evidence branch

`phase/11-contract-validation`

Purpose:

- canonicalize/accept Phase 11 ADRs and numbering;
- record product/security decisions;
- capture sanitized current public Codex contract fixtures;
- define exact Secret/config/network/activation gates;
- update implementation sequencing so architecture-review and engineering
  milestone numbers are unambiguous.

This is a prerequisite review PR, not a production feature branch.

### 6.2 First feature branch

`phase/11-provider-core-model`

Purpose: implement the non-secret domain foundation and additive unmanaged-state
schema only.

### 6.3 Second feature branch

`phase/11-runtime-capabilities`

Purpose: implement read-only, exact-schema Runtime capability observations from
the approved public fixtures, with no Secret/config mutation.

### 6.4 Future branches

Suggested sequence:

```text
phase/11-secret-boundary
phase/11-config-transactions
phase/11-provider-validation
phase/11-codex-adapter-dry-run
phase/11-activation-continuity-rollback
phase/11-api-cli
phase/11-frontend
phase/11-release-gate
```

Every branch starts from the latest reviewed `main`, opens a Draft PR, preserves
the existing ten required checks, adds bounded phase-specific checks, receives
human review, and uses Squash Merge. No branch combines Secret storage with
activation or combines dry-run with live apply.

## 7. First PR Proposal

### 7.1 Recommended first PR

Before production code, open:

**Title:** `Phase 11: validate public contracts and freeze Provider architecture`

**Branch:** `phase/11-contract-validation`

**Goal:** Convert the current Proposed design set into a canonical, evidence-
backed Accepted baseline and resolve every Critical implementation blocker.

This PR should remain documentation/fixture focused and should not implement
Provider behavior.

### 7.2 Expected files/components

The PR should be expected to include only reviewed planning/evidence assets such
as:

- canonical Phase 11 ADRs under the repository's accepted ADR convention;
- a Phase 11 decision registry and ID mapping;
- current public Codex contract evidence/fixtures with no account, credential,
  session, prompt, private path, or host-specific data;
- product/security decision records for scope, Secret custody/ingress/backup,
  config ownership, endpoint policy, active-session policy, activation threshold,
  recovery, and retention;
- updated `PHASE11_IMPLEMENTATION_PLAN.md` sequencing;
- threat-model/test-strategy additions describing the accepted gates.

It should not include migrations, application models, API endpoints, frontend,
Secret backend, config writer, Runtime mutation, Provider request, or activation.

### 7.3 Required review evidence

- Every architecture decision has a unique canonical ID and Accepted/Rejected/
  Deferred state.
- Current Codex public-contract evidence has source/date/version/provenance and
  sanitized deterministic fixtures.
- No private Codex files or real credentials were used.
- Product and security owners explicitly approve all Critical rows in section 4.
- Unsupported/unknown capabilities are recorded rather than inferred.
- Phase 11 v1 scope and non-goals are explicit.

### 7.4 Required tests/checks

Even a docs/fixture PR should run:

- existing Backend, Frontend, Security, E2E, Deployment, and deployment-gate;
- release-gate if it is part of current repository CI behavior;
- documentation link/format checks;
- Secret/canary scan over all fixtures and documents;
- private path/account/session identifier scan;
- GitHub Actions immutable-pin policy;
- repository-boundary and forbidden-primitive scans;
- `git diff --check`;
- review for license/copyright impact of copied public fixture material.

### 7.5 First production-code PR after acceptance

After the contract-validation PR merges, open:

**Title:** `Phase 11: add non-secret Provider core model`

**Branch:** `phase/11-provider-core-model`

Expected components may include:

- new focused modules under `packages/agentbox-core/src/agentbox_core/` for
  Provider-domain models, repositories, and application services rather than
  overloading generic `models.py`/`services.py`;
- an additive Alembic migration under `migrations/versions/`;
- optional strictly non-secret protocol/read models under
  `packages/agentbox-protocol/src/agentbox_protocol/` only if required by the
  accepted scope;
- unit and migration tests under `tests/unit/` and `tests/integration/`;
- boundary/Secret-field schema tests;
- documentation stating activation/Secret/Runtime behavior remains disabled.

Security checks must fail if schemas contain fields matching Secret/config/path/
command/argv/env/header payloads or if migration creates an active Provider/
Binding for existing users.

## 8. Database Migration Strategy

### 8.1 When schema changes may begin

No Phase 11 migration should be created until:

- identity/revision/lifecycle decisions are Accepted;
- V1 scope is approved;
- table/relationship/uniqueness design is reviewed against downgrade and old-
  application compatibility;
- forbidden Secret/config/privileged payload fields are mechanically specified.

Secret records, master keys, raw config, protected snapshots, Runtime journal,
Provider responses, prompts, or credentials never belong in these tables.

### 8.2 Migration stages

Use additive migrations aligned with trust boundaries:

1. **Non-secret domain migration** — Provider, Credential metadata, Runtime
   Profile, Runtime Binding, Session Binding, compatibility/evidence references,
   revisions, and safe lifecycle metadata.
2. **Transaction/evidence metadata migration** — only after state machines,
   retention, and safe finding schemas are frozen.
3. **API/UI projections or indexes** — only when query behavior is known; avoid
   denormalized Secret-bearing or raw JSON projections.

Runtime Secret store, config snapshots, and Runtime journal use separate
Runtime-owned storage and are not Alembic migrations.

### 8.3 Additive safety

- Do not rewrite existing authentication, Project, Job, Audit, Codex, Claude, or
  Session data.
- Do not create Provider/Credential/Profile/Binding rows automatically.
- Existing installations derive/report `UNMANAGED` until explicit opt-in.
- Existing admin, config, Projects, Runtime HOME, credentials, and sessions
  remain unchanged.
- Use explicit foreign keys, revisions, enums/check constraints, and uniqueness;
  do not depend solely on application validation.
- Enforce at most one committed active binding per Runtime with an approved
  SQLite-compatible constraint/index strategy.
- Do not use generic arbitrary JSON for Provider options, config diffs, audit
  metadata, or Runtime requests.

### 8.4 Upgrade and rollback compatibility

Before migration, use the existing safe SQLite online backup process. Run
Alembic explicitly; application startup does not migrate silently.

Preferred application rollback strategy:

- old `v0.3.0-rc.1`-line application code ignores new additive tables;
- no existing table semantics are changed;
- application rollback may leave unused Phase 11 tables in place;
- automatic destructive database downgrade is not assumed;
- downgrade that would discard Phase 11 data requires explicit backup and human
  approval;
- migration failure stops upgrade and invokes the existing verified recovery
  process.

### 8.5 Migration tests

Required fixtures:

- fresh empty database;
- populated v0.3.0-rc.1 database;
- database with existing users/sessions/jobs/projects/audit;
- upgrade, old-application compatibility, downgrade policy, and upgrade again;
- migration failure at each step;
- uniqueness/foreign-key/revision violation;
- zero automatically active Providers/Bindings;
- canary scans across DB/WAL/SHM and migration logs;
- database integrity and migration-head verification.

## 9. Testing Strategy

### 9.1 Test principles

- Each trust-boundary milestone has its own tests and feature gate.
- Fake Providers and sanitized public-contract fixtures precede real credentials
  or paid requests.
- Every failure point after possible mutation has fault injection and verified
  recovery assertions.
- `UNKNOWN`, `NOT_TESTED`, `EXPERIMENTAL`, and `NEEDS_ATTENTION` are tested as
  first-class outcomes.
- No test makes a private/undocumented Runtime format a supported contract.
- Existing v0.3.0-rc.1 behavior remains a required regression suite.

### 9.2 Backend tests

- domain identity/revision/lifecycle invariants;
- repository authorization and optimistic concurrency;
- one-active-binding constraint;
- SessionBinding immutability;
- safe evidence/transaction aggregation;
- exact audit allowlists and sanitized errors;
- Job idempotency/lease/crash recovery;
- migration fresh/upgrade/compatibility/failure tests;
- strict request fields when API work begins;
- no Secret/config/path/command/argv/env/header fields in ordinary schemas;
- Ruff, Black, mypy, pytest, migrations, and pip-audit.

### 9.3 Frontend tests

Frontend remains unchanged in early milestones. When introduced, test:

- empty/unmanaged, partial, stale, blocked, active, rollback, and
  needs-attention states;
- separate Provider/Runtime/Remote/continuity dimensions;
- no Secret entry/reveal/copy/storage or raw Provider/Runtime content;
- exact confirmation binding and disabled action for stale/unknown evidence;
- authenticated no-store behavior, CSP, Origin/Host/CSRF regression;
- mobile/desktop layout without leaking state into screenshot/trace;
- lint, formatting, typecheck, unit tests, build, and audit.

### 9.4 Runtime protocol and adapter tests

- wrong peer UID/GID, socket ownership/mode, protocol version, unknown action/
  field, malformed/oversized/concatenated frame, timeout, cancellation, and
  concurrency cap;
- no shell, executable, argv, environment, cwd, raw path/config, PID, signal,
  mode, owner, package, unit, header map, or arbitrary URL request;
- fixed server-side target/executable/Secret resolution;
- public Codex fixtures for supported, unsupported, changed, malformed,
  localized, and unknown behavior;
- capability freshness/fingerprint invalidation;
- semantic dry-run preserves unrelated config and leaks no values;
- duplicate managed scope, unsafe file, symlink, hardlink, external edit, and
  ownership/mode conflict;
- distinct-UID denial of Runtime HOME/Secret/snapshot access.

### 9.5 Secret security tests

Only after the Secret ADR is Accepted:

- AEAD known-answer/tamper/wrong-key/wrong-associated-data tests;
- master-key create/rotate/loss/recovery behavior;
- directory/file permissions and reinstall/update/uninstall preservation;
- symlink/hardlink/path replacement/unsafe parent/race/corrupt envelope;
- local TTY/protected-stdin ingress; reject argv/env/Web/API/history;
- versioned rotation/revocation/deletion/retention and crash recovery;
- canary scan across DB/WAL/SHM, Audit, Job/Event, journal, config, snapshots,
  logs, reports, diagnostics, backups, frontend artifacts, process inspection,
  Git, and CI artifacts.

### 9.6 Provider validation tests

- Official fixed endpoint policy;
- compatible URL normalization, Unicode/IDNA, schemes, ports, userinfo,
  fragments, queries, redirects, TLS, proxies, custom CA policy;
- IPv4/IPv6, DNS rebinding, metadata/link-local/private/multicast/unspecified
  destinations;
- time/byte/header/event/stream/decompression/concurrency bounds;
- fake authentication/model/wire/stream/error/timeout behavior;
- rate limit/cooldown/paid-test confirmation;
- no credential forwarding across authority;
- Provider `PASS` never fills Runtime/Remote/continuity evidence.

### 9.7 Transaction, activation, and rollback tests

Inject failure at:

- validation, dry-run, approval expiry, final revision check;
- snapshot creation/integrity;
- candidate rendering/validation;
- short write, fsync, atomic publication, parent fsync, reread;
- Secret resolution and child injection;
- Runtime lifecycle/restart/socket/health;
- Provider/Codex/Remote/resume/context/tool/stream/discovery verification;
- DB commit and Runtime acknowledgement;
- rollback publication/lifecycle/verification;
- process crash and machine-reboot simulation at every checkpoint.

Assert exact original config/nonexistence, owner/mode/metadata, prior Secret
reference, binding, lifecycle, Runtime/Remote/session state, journal agreement,
and final wording. Corrupt/missing snapshot or unknown state must never yield
`Rollback verified`.

### 9.8 E2E tests

When API/UI exist:

- create non-secret Provider metadata;
- local Secret setup guidance without browser value entry;
- validation evidence and compatibility matrix;
- dry-run and confirmation;
- active-session block/new-session policy;
- activation Job success/failure and exact rollback states;
- login/session/CSRF/no-store/security-header regression;
- Codex Remote, Claude/tmux, Projects, Git/GitHub, Doctor, and mobile regression;
- no real credentials, paid Provider calls, or private Runtime state in CI.

### 9.9 Deployment tests

- fixed Runtime Secret/journal/snapshot directories and owner/mode only after
  their ADRs are accepted;
- API/Worker remain `agentbox`; Runtime remains `agentbox-runtime`; Helper stays
  unchanged;
- fresh fixture install and repeated install;
- upgrade from v0.3.0-rc.1 with existing config/auth/sessions/Projects untouched;
- application rollback and default uninstall preservation;
- systemd sandbox and Runtime HOME access requirements;
- OpenCloudOS real-host validation only after automated gates and explicit
  plan/approval;
- existing Deployment/deployment-gate remain passing.

### 9.10 CI and security gates

- existing required Backend, Frontend, Security, E2E, Deployment, and
  deployment-gate checks;
- dependency review, pip/pnpm audit, Secret scan, repository-boundary scan,
  forbidden-primitive scan, and action-pin policy;
- a stable Phase 11 aggregate gate only after it exists and proves stable;
- no Ruleset change inside a Phase feature PR;
- no open P0/P1 security issue or unresolved blocking review thread.

## 10. Security Readiness Checklist

### 10.1 Checklist

| Security area | Design status | Implementation gate |
|---|---|---|
| Control Plane/Runtime separation | Defined consistently | Must be enforced by exact protocol, UID, filesystem, and import-boundary tests |
| API/Worker non-root | Frozen candidate | Must remain unchanged in deployment/systemd evidence |
| Root Helper restrictions | Defined: no new Phase 11 authority | Boundary scan and adversarial protocol regression required |
| Provider/Remote separation | Defined consistently | UI/API/read-model and activation tests must preserve independent states |
| Secret isolation | Boundary defined | **Blocked:** algorithm, key custody, ingress, backup not approved |
| No plaintext DB/API/Web/log | Frozen candidate | Schema scan and end-to-end canary tests required |
| Runtime minimal Secret use | Defined conceptually | Public Codex reference and child-delivery tests required |
| Read-only capability boundary | Defined | Peer/framing/exact-schema and data-minimization tests required |
| Endpoint/SSRF protections | Threats/controls defined | **Blocked:** exact private/DNS/redirect/proxy/CA policy not approved |
| Semantic config ownership | Defined conceptually | **Blocked:** managed scope and preservation mechanism not approved |
| Transaction atomicity | State model defined | Journal/lock/fsync/fault-injection implementation evidence required |
| Audit requirements | Event/content allowlists defined | Schema allowlist, sanitization, ordering, and canary tests required |
| Existing session stability | Conservative policy defined | **Blocked:** active-writer/public-session evidence and product policy not approved |
| Rollback safety | Exact verification model defined | **Blocked:** retention, prior Secret, recovery ownership and crash policy not approved |
| Automatic fallback | Explicitly prohibited | Adversarial activation/recovery tests required |
| Tenant isolation | Explicitly not claimed | V1 remains single-administrator; no placeholder tenant claims |

### 10.2 Security conclusion

Security principles are coherent and conservative, but security readiness is
not PASS until the highlighted decisions are Accepted and their tests exist.
Documentation alone cannot prove key custody, no Secret leakage, filesystem
atomicity, peer authentication, SSRF resistance, or verified rollback.

## 11. Release Impact

### 11.1 Impact on v0.3.0-rc.1 users

The intended safe upgrade behavior is:

- existing AgentBox users, admin state, sessions, Jobs, Projects, config, and
  application secret remain unchanged;
- existing root and `agentbox-runtime` Codex/Claude/GitHub credentials remain
  unchanged and are never imported;
- existing Codex configuration remains untouched;
- existing Codex/Claude/tmux processes and sessions remain untouched;
- no Provider/Credential/Profile/Binding is created automatically;
- Provider management reports `UNMANAGED` until explicit opt-in;
- pre-existing sessions remain `legacy_unbound` unless public evidence proves a
  supported binding;
- loopback network default, Secure Cookie/proxy policy, SSH, firewall,
  cloudflared, systemd privilege boundaries, and root Helper remain unchanged.

### 11.2 Upgrade path

Recommended rollout:

1. safe SQLite backup and migration preflight;
2. additive non-secret schema with feature disabled;
3. service restart/health/readiness and existing-function regression;
4. no Runtime/Secret directory creation until the corresponding milestone;
5. no config ownership/adoption until explicit user plan/approval;
6. local credential re-entry for managed Providers; never copy existing root or
   Runtime login credentials;
7. validation and dry-run before any activation;
8. explicit activation only after all gates and rollback prerequisites pass.

Offline upgrade should not require Provider credentials. Missing Provider
credentials must not make the existing AgentBox control plane unavailable.

### 11.3 Application rollback compatibility

Early additive schema should permit an older application to ignore new tables.
Application rollback must preserve:

- database/admin/session state;
- Projects and Runtime HOME;
- existing Codex/Claude/GitHub auth;
- AgentBox config/application secret;
- Runtime config and sessions;
- Phase 11 Runtime-owned Secret/journal/snapshots if they were later created.

Automatic database downgrade is not guaranteed. Once Phase 11 stores non-secret
metadata or encrypted Runtime Secrets, application rollback, database downgrade,
Secret custody, and config rollback are separate operations. Documentation must
state when re-entry or manual recovery is required.

### 11.4 Release compatibility gates

Before any Phase 11 release candidate:

- fresh install and upgrade from v0.3.0-rc.1 fixtures pass;
- older-application compatibility and migration failure recovery pass;
- existing Runtime state metadata comparisons prove no implicit adoption;
- Secret/config/session canaries are absent from prohibited surfaces;
- fake-provider activation/rollback fault matrix passes;
- OpenCloudOS real-host rehearsal restores the pre-rehearsal state;
- platform claims remain accurate;
- all required CI and a stable Phase 11 release gate pass;
- no tag or Release is created before human authorization.

### 11.5 Release/version decision

This review does not select a Phase 11 product version, release tag, migration
revision, or compatibility promise. Those decisions occur only after the
implementation and release gates pass.

## 12. Implementation Gate Decision

### 12.1 Final recommendation

```text
BLOCKED
```

Phase 11 architecture is conceptually coherent but not ready for engineering
implementation. The unresolved Critical decisions affect credential custody,
filesystem ownership, Runtime compatibility, session safety, and recovery—the
areas where implementing first and deciding later would create the greatest
security and migration risk.

### 12.2 Conditions to change the decision to READY FOR IMPLEMENTATION

All of the following are required:

1. Human architecture/security review accepts the Phase 11 ADR baseline and a
   canonical decision registry resolves numbering collisions.
2. Product scope is approved: Linux/Codex first; Official OpenAI and approved
   compatible Providers; Claude Runtime-only; Local inactive; no Web Secret
   input; no fallback; single administrator.
3. Current public Codex contract is revalidated and captured in sanitized,
   versioned fixtures covering Provider config, credential reference, validation,
   lifecycle, Remote, active-writer, and session behavior.
4. Secret algorithm/library/envelope, master-key custody/recovery, ingress,
   backup, rotation, and retention decisions are Accepted.
5. Codex config target, managed scope, ownership marker, lossless preservation,
   validation method, and metadata/durability requirements are Accepted.
6. Endpoint/private-network/DNS/redirect/proxy/custom-CA and paid-test policies
   are Accepted.
7. Activation compatibility threshold, existing/unknown-session policy,
   admission fence, lock/lease, timeout, commit-pending, rollback retention,
   revoked-prior-Credential, and crash-recovery rules are Accepted.
8. First-slice migration, forbidden-field schema rules, threat model, and test
   gates receive review approval.

### 12.3 First recommended implementation step after unblocking

Implement the **non-secret Provider core model and additive unmanaged-state
schema only**, on `phase/11-provider-core-model`, with every Secret, network,
Runtime mutation, activation, rollback, API mutation, and UI feature disabled.

Before that production PR, complete and merge the contract-validation/
architecture-freeze PR described in section 7.

### 12.4 Remaining blockers summary

- ADRs Proposed, not Accepted;
- no canonical ADR/milestone numbering;
- current public Codex contract not qualified;
- Secret cryptography/key custody/ingress/backup undecided;
- Codex managed scope/preservation/lifecycle undecided;
- endpoint/private-network/paid-test policy undecided;
- activation threshold and session switching policy undecided;
- lock/commit-pending/crash-recovery/rollback-retention rules undecided.

Phase 11 implementation remains **NOT STARTED**.
