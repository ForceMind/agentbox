# AgentBox Phase 11 — Contract Freeze and ADR Acceptance Review

Status: **Final design governance review**
Architecture contract status: **Accepted with canonical registry**
Engineering implementation decision: **BLOCKED**
Repository baseline: `ForceMind/agentbox` at
`1c2005de59b1c5063b260591206a8411c7e5b1a5`
Release baseline: `v0.3.0-rc.1`

Reviewed documents:

- `PHASE11_IMPLEMENTATION_READINESS_REVIEW.md`;
- `PHASE11_1_PROVIDER_DOMAIN_MODEL_ADR.md`;
- `PHASE11_2_RUNTIME_CAPABILITY_CONTRACT_ADR.md`;
- `PHASE11_3_SECRET_BOUNDARY_ADR.md`;
- `PHASE11_4_CONFIG_TRANSACTION_FRAMEWORK_ADR.md`;
- `PHASE11_5_PROVIDER_VALIDATION_PIPELINE_ADR.md`;
- `PHASE11_6_CODEX_PROVIDER_ADAPTER_DRY_RUN_ADR.md`;
- `PHASE11_7_RUNTIME_BINDING_ACTIVATION_CONTINUITY_ROLLBACK_ADR.md`.

This review freezes architecture-level invariants and establishes a canonical
decision registry. “Accepted” means an implementation must obey the decision;
it does not mean missing implementation profiles, external public-contract
evidence, tests, or product approvals are complete.

This review creates no code, migration, database table, API, UI, Secret,
Provider, Runtime/Codex/Claude change, branch, commit, or implementation
authorization.

## 1. Architecture Freeze Summary

### 1.1 Phase 11 goal

Phase 11 introduces Provider / Secret / Runtime Continuity management while
keeping Codex Remote Control separate from AI Provider selection:

```text
Control Plane
    owns intent, authorization, workflow, evidence metadata, binding state,
    approval, transaction orchestration, and audit

Runtime
    owns local capabilities, Secret custody/use, configuration application,
    process state, Provider execution, and recovery evidence

Codex
    remains an externally owned Runtime governed only through public contracts
```

The feature must never turn AgentBox into a Web shell, arbitrary config editor,
generic HTTP proxy, root credential service, or session migration tool.

### 1.2 Completed architecture layers

The architecture now covers:

1. Provider/Credential/Profile/Binding/Session identity and lifecycle;
2. read-only Runtime capability evidence;
3. Runtime-owned Secret custody and minimal use;
4. recoverable configuration transactions;
5. layered Provider validation evidence;
6. a Codex-specific public-contract adapter and read-only semantic dry-run;
7. Runtime Binding activation, continuity, rollback, crash recovery, locking,
   and audit;
8. implementation readiness, migration, testing, security, and release review.

The layer boundaries are coherent. No reviewed ADR permits raw Secret storage,
direct control-plane Runtime access, arbitrary commands/paths, private Codex
state mutation, implicit session migration, automatic pairing, or Provider
fallback.

### 1.3 Frozen implementation boundary

The architecture contract is frozen at these boundaries:

- `agentbox` remains non-root and non-secret;
- `agentbox-runtime` remains the non-root execution/Secret/config boundary;
- root Helper remains unchanged and fixed-action only;
- Remote Control and Provider Manager remain separate domains;
- Provider metadata and Runtime selection use stable AgentBox identities;
- Runtime capabilities and Provider validation are evidence, not permission;
- Secrets remain outside normal database/API/Web/config/log/audit surfaces;
- all config mutation uses a typed Runtime adapter and recoverable transaction;
- activation requires explicit approval and layered post-verification;
- existing sessions remain unchanged and are never implicitly migrated;
- rollback must be verified; uncertainty becomes `NEEDS_ATTENTION`;
- no automatic fallback/failover exists.

### 1.4 Freeze does not authorize implementation

The architecture principles can be Accepted now because they are conservative,
mutually consistent, and sufficiently constrain unsafe designs. Engineering
remains blocked because several implementation contracts deliberately contain
unresolved choices that cannot safely be selected by developers during coding.

The freeze therefore produces two outputs:

```text
Architecture invariants: ACCEPTED
Engineering implementation gate: BLOCKED
```

## 2. ADR Acceptance Review

### 2.1 Review method

Every Phase 11 ADR was reviewed for:

- consistency with existing AgentBox process/privilege architecture;
- Secret and Runtime data minimization;
- absence of arbitrary execution/config/network primitives;
- public-contract discipline;
- identity and lifecycle correctness;
- session and Remote Control safety;
- crash recovery and truthful rollback semantics;
- compatibility with an additive, opt-in migration from v0.3.0-rc.1.

Decision content is classified only as `Accepted` or `Needs Revision`. All 66
architecture decisions are Accepted as constraints. Their source documents still
need an editorial governance update to reference the canonical IDs/statuses in
section 3; that editorial work does not reopen the decision content.

Implementation-specific choices not settled by an Accepted ADR are listed as
new required supplemental contracts in sections 4, 5, 7, and 8.

### 2.2 Provider Domain Model decisions

| Canonical ID | Decision | Status | Reasoning |
|---|---|---|---|
| P11-ADR-001 | Provider abstraction is separate from Runtime control | Accepted | Preserves Runtime neutrality and prevents Provider metadata from becoming execution authority. |
| P11-ADR-002 | Credentials are separate from Provider identity | Accepted | Enables rotation/revocation without identity confusion or Secret-derived identifiers. |
| P11-ADR-003 | Claude remains Runtime-only initially | Accepted | Avoids inventing unsupported Claude Provider/config semantics. |
| P11-ADR-004 | Phase 11 does not modify active sessions | Accepted | Protects established session behavior during foundational work. |
| P11-ADR-005 | Runtime Binding owns Provider selection | Accepted | Scopes active intent to a Runtime instead of a global Provider flag. |
| P11-ADR-006 | Session Binding is immutable effective-state evidence | Accepted | Prevents retroactive session relabeling when active Provider intent changes. |
| P11-ADR-007 | Provider capabilities are evidence, not promises | Accepted | Keeps observed behavior, compatibility, and authorization separate. |
| P11-ADR-008 | Foundational domain model is database-agnostic and non-secret | Accepted | Allows safe schema design without putting Secret/config execution into core entities. |
| P11-ADR-009 | Provider types use typed extensions, not a universal option bag | Accepted | Prevents arbitrary config/header/path/environment fields and false cross-Provider uniformity. |

### 2.3 Runtime Capability Contract decisions

| Canonical ID | Decision | Status | Reasoning |
|---|---|---|---|
| P11-ADR-011 | Runtime capability information is contract based | Accepted | Gives the control plane bounded typed evidence instead of raw Runtime access. |
| P11-ADR-012 | Control Plane does not directly modify Runtime internals | Accepted | Preserves the accepted process and filesystem boundary. |
| P11-ADR-013 | Read-only capability discovery precedes mutation | Accepted | Makes unsupported/unknown behavior visible before risk-bearing operations. |
| P11-ADR-014 | Capability outcome and evidence lifecycle are separate | Accepted | Prevents stale evidence from becoming a timeless feature flag. |
| P11-ADR-015 | Existing peer-authenticated Runtime UDS remains the transport | Accepted | Reuses the reviewed non-root, exact-schema, peer-credential boundary. |
| P11-ADR-016 | Runtime Adapters use public contracts and fixed probes | Accepted | Prevents caller-controlled commands and private-format dependencies. |
| P11-ADR-017 | Capability evidence never authorizes mutation | Accepted | Keeps observation distinct from approval/transaction permission. |
| P11-ADR-018 | Capability reports minimize sensitive Runtime information | Accepted | Prevents config, credential, process, session, or output leakage. |
| P11-ADR-019 | Claude capability remains Runtime/session scoped | Accepted | Maintains the deliberate Claude Provider non-support boundary. |

### 2.4 Secret Boundary decisions

| Canonical ID | Decision | Status | Reasoning |
|---|---|---|---|
| P11-ADR-021 | Secrets are separate from Provider identity | Accepted | Keeps Provider metadata safe and supports independent Secret lifecycle. |
| P11-ADR-022 | Plaintext Secrets never use normal database fields | Accepted | SQLite/Web/Worker must not become credential exposure paths. |
| P11-ADR-023 | Runtime Secret access is controlled and minimal | Accepted | Limits plaintext to one action-specific Runtime operation. |
| P11-ADR-024 | Secret operations require Audit records | Accepted | Provides accountability without recording values or sensitive payloads. |
| P11-ADR-025 | V1 uses a dedicated Runtime-owned local Secret store | Accepted | Aligns custody with the existing Runtime identity and keeps records outside SQLite. |
| P11-ADR-026 | Stored Secret versions use authenticated envelope encryption | Accepted | Establishes confidentiality/integrity and versioned rotation as mandatory architecture; exact cryptographic profile remains a supplemental contract. |
| P11-ADR-027 | Secret provisioning is local and outside ordinary Web/API | Accepted | Prevents browser/API/CLI-argv credential ingestion in v1. |
| P11-ADR-028 | Root Helper has no Secret authority | Accepted | Prevents a generic root decryption/extraction service. |
| P11-ADR-029 | Ordinary backup excludes Secret records and master keys | Accepted | Avoids spreading credentials through normal control-plane backup; recovery details remain supplemental. |
| P11-ADR-030 | Plaintext delivery is transient and action-specific | Accepted | Prohibits persistent config, long-lived environment, argv, and generic retrieval. |

### 2.5 Configuration Transaction decisions

| Canonical ID | Decision | Status | Reasoning |
|---|---|---|---|
| P11-ADR-031 | Runtime changes require transaction boundaries | Accepted | A Provider activation spans config, processes, evidence, and binding state. |
| P11-ADR-032 | Validation precedes mutation | Accepted | Rejects unsafe targets/plans before any Runtime change. |
| P11-ADR-033 | Failed Runtime changes require verified rollback | Accepted | Prevents a rollback attempt from being reported as recovery. |
| P11-ADR-034 | Snapshots exclude separately managed Secret Material | Accepted | Preserves recovery without turning snapshots into a plaintext Secret store. |
| P11-ADR-035 | Planning and execution are separate contracts | Accepted | Binds approval to an immutable read-only plan. |
| P11-ADR-036 | Transaction persistence is split across trust boundaries | Accepted | Control Plane keeps non-secret workflow; Runtime keeps protected local execution evidence. |
| P11-ADR-037 | Multi-resource atomicity uses a recoverable state machine | Accepted | Avoids false distributed-ACID claims and makes partial state explicit. |
| P11-ADR-038 | Transactions serialize per Runtime and detect external edits | Accepted | Prevents overlapping AgentBox writers and stale overwrite of user changes. |
| P11-ADR-039 | Active Runtime Binding commits only after required verification | Accepted | Separates file application from proven Runtime effectiveness. |
| P11-ADR-040 | Interrupted transactions reconcile and are never blindly replayed | Accepted | Prevents duplicate mutation, lifecycle, migration, or paid tests. |
| P11-ADR-041 | Runtime owns local configuration application | Accepted | Keeps raw config and filesystem mutation out of Control Plane. |

### 2.6 Provider Validation decisions

The Phase 11.5 source identifiers are deprecated aliases. Canonical IDs below
resolve their collision with P11-ADR-041.

| Canonical ID | Source alias | Decision | Status | Reasoning |
|---|---|---|---|---|
| P11-ADR-042 | ADR-11.5-041 | Provider activation requires validation evidence | Accepted | Activation must be bound to fresh exact-scope evidence. |
| P11-ADR-043 | ADR-11.5-042 | Validation does not equal an execution guarantee | Accepted | Minimal evidence cannot promise future availability, cost, Runtime, or continuity. |
| P11-ADR-044 | ADR-11.5-043 | Validation evidence contains no Secret Material | Accepted | Evidence must remain safe for control-plane persistence and display. |
| P11-ADR-045 | ADR-11.5-044 | Expired/invalidated evidence requires revalidation | Accepted | Prevents stale proof from authorizing a new plan. |
| P11-ADR-046 | ADR-11.5-045 | Validation stages remain independently observable | Accepted | Lower-layer success cannot hide higher-layer failure/unknown state. |
| P11-ADR-047 | ADR-11.5-046 | Offline and live validation are distinct operations | Accepted | Metadata checks cannot unexpectedly contact Providers, use Secrets, or incur cost. |
| P11-ADR-048 | ADR-11.5-047 | Endpoint validation is type-specific and fail closed | Accepted | Prevents generic HTTP, SSRF, credential forwarding, and network scanning. |
| P11-ADR-049 | ADR-11.5-048 | Validation eligibility never activates a Runtime | Accepted | Keeps evidence, approval, and mutation as separate contracts. |

### 2.7 Codex Provider Adapter decisions

| Canonical ID | Decision | Status | Reasoning |
|---|---|---|---|
| P11-ADR-051 | Codex integration uses an adapter boundary | Accepted | Isolates Codex-specific public-contract mapping from generic Provider/control-plane logic. |
| P11-ADR-052 | Dry-run precedes Provider activation | Accepted | Makes semantic impact visible without file, Secret, process, or endpoint changes. |
| P11-ADR-053 | Existing sessions are not implicitly migrated | Accepted | Preserves historical/effective state and avoids private-session manipulation. |
| P11-ADR-054 | Unknown Codex compatibility fails closed | Accepted | Prevents optimistic mutation against changed/undocumented behavior. |
| P11-ADR-055 | Configuration changes are semantic and scope-limited | Accepted | Protects unrelated user settings and prohibits raw whole-file ownership. |
| P11-ADR-056 | Dry-run never resolves Provider Secret Material | Accepted | Keeps planning safe and non-secret. |
| P11-ADR-057 | Runtime reconstructs the private candidate at apply time | Accepted | Prevents control-plane plan bytes from becoming arbitrary config input. |
| P11-ADR-058 | Codex pairing and Provider authentication remain separate | Accepted | Protects established Remote Control and login state. |
| P11-ADR-059 | Apply remains a Phase 11.4 Runtime transaction | Accepted | Prevents a second config/lifecycle mutation engine. |

### 2.8 Runtime Binding, Activation, Continuity, and Rollback decisions

| Canonical ID | Decision | Status | Reasoning |
|---|---|---|---|
| P11-ADR-061 | Runtime Binding is separate from Provider identity | Accepted | Scopes effective selection and history to one Runtime installation. |
| P11-ADR-062 | Activation requires the transaction lifecycle | Accepted | Activation cannot be reduced to a file or database update. |
| P11-ADR-063 | Existing sessions are not implicitly migrated | Accepted | New binding intent must not rewrite prior effective session state. |
| P11-ADR-064 | Rollback requires verification | Accepted | Recovery must include config, binding, lifecycle, Runtime, Remote, and required continuity evidence. |
| P11-ADR-065 | Unknown Runtime state requires explicit recovery | Accepted | Uncertainty blocks mutation instead of triggering blind replay/fallback. |
| P11-ADR-066 | Only one Runtime Binding may be active per Runtime | Accepted | Prevents competing active Provider claims and last-write-wins activation. |
| P11-ADR-067 | Active state commits only after layered verification | Accepted | Provider/API or health success alone cannot establish effective binding. |
| P11-ADR-068 | Activation never performs automatic Provider fallback | Accepted | Privacy, cost, destination, and model cannot change without a new approval. |
| P11-ADR-069 | Activation uses a per-Runtime lock and admission fence | Accepted | Prevents overlapping activation and new managed-session races. |
| P11-ADR-070 | Pairing and Provider activation remain independent | Accepted | Provider switching cannot silently reset or impersonate Remote Control. |

### 2.9 Acceptance result

```text
Accepted decision content: 66
Needs Revision decision content: 0
Editorial/canonical source updates required: YES
Supplemental implementation contracts required: YES
```

No accepted decision may be weakened by an implementation profile. A
supplemental contract may choose an algorithm, path, TTL, lock, policy, or
supported Codex version only within these constraints.

## 3. ADR Registry Cleanup

### 3.1 Canonical identifier format

All Phase 11 architecture decisions use:

```text
P11-ADR-NNN
```

The `P11` namespace prevents collision with repository-wide ADRs under
`docs/adr/`. The numeric suffix is immutable after allocation. Gaps are reserved
and IDs are never reused.

Future documents must:

1. consult this registry before allocating an ID;
2. use the canonical identifier in code comments, migrations, tests, PRs, and
   reports;
3. record old/document-local aliases only as deprecated mappings;
4. never renumber an Accepted decision silently;
5. add supersession metadata if a future ADR replaces a decision;
6. allocate the next unreserved identifier, starting at P11-ADR-071.

### 3.2 Reserved identifiers

`P11-ADR-010`, `P11-ADR-020`, `P11-ADR-050`, and `P11-ADR-060` are reserved as
series separators and must not be assigned. The next supplemental contract begins
at `P11-ADR-071`.

### 3.3 Canonical registry

| Canonical range | Titles/area | Status | Related document |
|---|---|---|---|
| P11-ADR-001–009 | Provider domain and identity decisions listed in section 2.2 | Accepted | `PHASE11_1_PROVIDER_DOMAIN_MODEL_ADR.md` |
| P11-ADR-011–019 | Runtime capability and adapter-observation decisions listed in section 2.3 | Accepted | `PHASE11_2_RUNTIME_CAPABILITY_CONTRACT_ADR.md` |
| P11-ADR-021–030 | Secret boundary/custody/lifecycle decisions listed in section 2.4 | Accepted | `PHASE11_3_SECRET_BOUNDARY_ADR.md` |
| P11-ADR-031–041 | Transaction/atomicity/rollback decisions listed in section 2.5 | Accepted | `PHASE11_4_CONFIG_TRANSACTION_FRAMEWORK_ADR.md` |
| P11-ADR-042–049 | Provider validation decisions listed in section 2.6 | Accepted | `PHASE11_5_PROVIDER_VALIDATION_PIPELINE_ADR.md` |
| P11-ADR-051–059 | Codex Adapter/dry-run decisions listed in section 2.7 | Accepted | `PHASE11_6_CODEX_PROVIDER_ADAPTER_DRY_RUN_ADR.md` |
| P11-ADR-061–070 | Runtime Binding/activation/continuity/rollback decisions listed in section 2.8 | Accepted | `PHASE11_7_RUNTIME_BINDING_ACTIVATION_CONTINUITY_ROLLBACK_ADR.md` |

Section 2 is the row-level canonical registry: every canonical identifier,
decision title, acceptance state, rationale, and source document is recorded
there. This range table is the allocation index, not a replacement for those
entries.

### 3.4 Deprecated alias mapping

| Deprecated source ID | Canonical ID |
|---|---|
| ADR-001…ADR-009 | P11-ADR-001…P11-ADR-009 |
| ADR-011…ADR-019 | P11-ADR-011…P11-ADR-019 |
| ADR-021…ADR-041 | P11-ADR-021…P11-ADR-041 |
| ADR-11.5-041 | P11-ADR-042 |
| ADR-11.5-042 | P11-ADR-043 |
| ADR-11.5-043 | P11-ADR-044 |
| ADR-11.5-044 | P11-ADR-045 |
| ADR-11.5-045 | P11-ADR-046 |
| ADR-11.5-046 | P11-ADR-047 |
| ADR-11.5-047 | P11-ADR-048 |
| ADR-11.5-048 | P11-ADR-049 |
| ADR-051…ADR-059 | P11-ADR-051…P11-ADR-059 |
| ADR-061…ADR-070 | P11-ADR-061…P11-ADR-070 |

The original Phase 11.5 `ADR-11.5-041` alias must never be shortened to
`ADR-041`; that identifier belongs canonically to Runtime-owned config
application as P11-ADR-041.

### 3.5 Governance editorial action

Before an engineering PR, a documentation-only governance PR must:

- place these decisions under the repository's canonical ADR convention;
- update each source decision status from Proposed to Accepted or add an
  authoritative acceptance header pointing here;
- replace implementation references with `P11-ADR-NNN` identifiers;
- distinguish “Architecture Phase 11.8 readiness review” from implementation
  milestone “11.8 API/CLI” through namespaced numbering;
- preserve original aliases for history without creating duplicate canonical
  IDs.

## 4. Security Decision Freeze

### 4.1 Secret boundary

**Accepted and frozen**

- Secrets are independent from Provider/Credential identity.
- Control Plane, SQLite, Web/API, ordinary CLI argv, config, logs, Audit, Jobs,
  reports, Git, and normal backups never contain plaintext Provider Secrets.
- V1 Secret custody is a dedicated Runtime-owned local store.
- Stored versions require authenticated envelope encryption.
- Provisioning is local and outside ordinary Web/API.
- Plaintext use is transient, action-specific, and limited to one exact Runtime
  operation.
- Root Helper cannot create, read, decrypt, export, rotate, or delete Secrets.

**Remaining implementation contracts**

- `P11-ADR-071 — Secret Cryptographic and Master-Key Profile`: reviewed library,
  AEAD, envelope/associated-data schema, CSPRNG, key file/OS custody, generation,
  permissions, rotation, memory/dump behavior, corruption, and key-loss response.
- `P11-ADR-072 — Secret Ingress, Backup, Recovery, and Retention Profile`: exact
  local command/identity/TTY/stdin rules, automation policy, re-entry versus
  encrypted backup, rotation overlap, prior-version retention, revocation, and
  physical deletion expectations.

No Secret milestone begins until both are Accepted.

### 4.2 Runtime boundary

**Accepted and frozen**

- Runtime owns execution, local config, Secret use, Provider requests, and
  execution evidence.
- Control Plane sends only typed IDs/revisions/evidence/plan digests.
- Existing peer-authenticated UDS, exact schemas, bounded frames/timeouts, and
  fixed server-side resolution remain mandatory.
- No command/executable/argv/environment/path/PID/signal/package/systemd/raw-
  config/header-map fields are allowed.
- Runtime capability discovery is read-only; evidence does not authorize
  mutation.

**Remaining implementation contracts**

- exact capability/protocol schemas, evidence TTLs, cache invalidation, adapter
  versioning, lock/fence messages, and current public Codex fixtures;
- same-UID threat treatment and deployment/path/permission evidence.

These details may be finalized in P11-ADR-073 and P11-ADR-076 below.

### 4.3 Root Helper boundary

**Accepted and frozen**

- Phase 11 adds no root Helper action.
- Helper never reads Runtime HOME, Secret/config snapshots, Provider metadata,
  credentials, Codex/Claude state, endpoint requests, or binding transactions.
- No Provider operation accepts arbitrary path, mode, user, group, command,
  executable, argv, environment, PID, signal, package, or unit.

**Remaining decisions**

None at architecture level. Implementation must preserve existing Helper tests
and repository boundary scans. Any future root requirement needs a new, separate
ADR and is outside Phase 11's frozen scope.

### 4.4 Transaction safety

**Accepted and frozen**

- Every Runtime mutation is a durable state machine with plan, validation,
  snapshot, apply, post-verification, commit, or recovery.
- Runtime owns file application and protected local journal/snapshot.
- Control Plane stores only non-secret orchestration metadata.
- Target/path selection is fixed server-side; semantic mapping preserves
  unrelated settings.
- One mutating transaction is allowed per Runtime; external edits fail closed.
- `COMMIT_PENDING`, `INTERRUPTED`, `RECONCILING`, and `NEEDS_ATTENTION` are
  first-class states.

**Remaining implementation contract**

- `P11-ADR-076 — Transaction Persistence, Locking, Crash-Recovery, and Retention
  Profile`: DB/JOB state schema, Runtime journal/snapshot location/integrity,
  lock/lease/admission fence, lock order, fsync/platform semantics, timeouts,
  commit-pending decision table, cancellation, retention, and recovery ownership.

No config mutation begins until P11-ADR-076 and the Codex config profile are
Accepted.

### 4.5 Rollback model

**Accepted and frozen**

- Rollback targets only the exact pre-transaction state; no automatic Provider
  fallback exists.
- Rollback restores config/nonexistence, permissions/metadata, prior binding/
  profile/Secret reference, lifecycle, Runtime, Remote, and required continuity
  expectations.
- Rollback is successful only after independent verification.
- Missing/corrupt snapshot, concurrent edit, revoked prior credential, or
  uncertain Runtime state becomes `NEEDS_ATTENTION` and blocks mutation.
- Manual rollback is a new approved transaction, never an arbitrary snapshot
  path or pointer switch.

**Remaining decisions**

- rollback snapshot and old Secret-version retention;
- policy when the prior credential is revoked/unusable;
- which recovery transitions may run automatically after reboot;
- exact required recovery evidence and timeouts.

These must be frozen in P11-ADR-072, P11-ADR-075, and P11-ADR-076.

## 5. Codex Contract Freeze

### 5.1 Confirmed public behavior at the existing release boundary

The existing v0.3.0-rc.1 AgentBox integration has reviewed, fixture-backed
support for a limited public observation/lifecycle surface:

- detecting a Codex executable under the fixed Runtime policy;
- obtaining bounded public version/help evidence;
- classifying advertised `remote-control` capabilities conservatively;
- existing typed Remote start, stop, and Pair operations when the public command
  is advertised;
- treating Pair Code as ephemeral and keeping it out of persistent surfaces;
- keeping Codex login/auth state separate from Remote status;
- degrading changed/malformed/unsupported output to unknown rather than using
  arbitrary fallback.

This evidence supports the existing Phase 5/10 feature only. It does not prove
any Phase 11 Provider/config capability, and it is not a promise about the
latest Codex version at implementation time.

### 5.2 Unverified assumptions

The following are explicitly **unverified** and cannot be implementation inputs:

- current public Provider-definition/config schema and supported keys;
- whether concepts such as provider block IDs, base URL, model, wire API, or an
  environment-key reference exist in the required stable form;
- fixed config target, safe managed-scope marker, and public validation method;
- whether a lossless semantic update can preserve all unrelated settings;
- whether Provider changes apply to new requests, hot reload, process restart,
  Remote restart, reauthentication, or new sessions;
- whether Remote Pairing/login survives a Provider/config change;
- public evidence for active writer/turn, duplicate Runtime, effective Provider,
  session/thread identity, resume, context use, tools, streaming, Responses, and
  discovery;
- supported Codex version range and adapter-profile matching;
- safe Secret reference/delivery behavior;
- whether a minimal direct or Codex Runtime request can prove binding without
  private-state access.

Observed TOML, private SQLite/JSONL/rollout/thread files, process command lines,
or host credentials cannot fill these gaps.

### 5.3 Required Codex contract validation

Before any Provider-related Runtime schema, config parser/writer, dry-run, or
activation code:

1. review the then-current official Codex CLI help, public config documentation/
   schema, credential reference, Provider options, wire protocols, lifecycle,
   Remote, and session behavior;
2. record exact version/date/source/provenance in sanitized fixtures;
3. classify every required capability as supported, unsupported, experimental,
   or unknown;
4. cover supported, changed, malformed, localized, incomplete, and unsupported
   output without real credentials or private user data;
5. determine the fixed config target and AgentBox-managed semantic scope;
6. prove unrelated-setting preservation and safe in-memory validation;
7. establish restart/new-session/active-work/Remote implications through public
   evidence;
8. define the safe credential-reference method without plaintext config;
9. perform security review for config ownership, symlink/TOCTOU, Secret delivery,
   session continuity, and error sanitization;
10. keep live config mutation, real credentials, paid requests, and existing
    root Runtime state unchanged during contract validation.

### 5.4 Required supplemental decision

Create and Accept:

`P11-ADR-073 — Codex Public Contract, Managed Configuration, and Lifecycle Profile`

It must bind approved Codex versions/evidence, public schema, supported Provider
types/options, fixed target, managed scope, preservation method, validation,
credential reference, lifecycle/restart behavior, active-work evidence, and
unknown-version response.

Until P11-ADR-073 is Accepted, Codex Provider Adapter and config implementation
remain blocked.

## 6. Implementation Scope Freeze

### 6.1 In scope after the engineering gate opens

- Linux single-server, single-administrator Provider management;
- Codex as the only Provider-managed Runtime;
- Official OpenAI and explicitly approved typed OpenAI-compatible HTTP Provider
  definitions;
- non-secret Provider/Credential metadata, Runtime Profiles, Runtime Bindings,
  immutable Session Bindings, evidence, plans, transaction state, and audit;
- read-only typed Runtime capability discovery;
- Runtime-owned local encrypted Provider Secret storage and local provisioning
  under the accepted profiles;
- fake-Provider layered validation before real Provider testing;
- typed Codex Adapter semantic dry-run;
- transactionally applied Provider activation only after every specific gate;
- new-session-first continuity policy and verified rollback;
- later typed API/CLI and frontend read/approval workflows without Web Secret
  input;
- additive opt-in migration from v0.3.0-rc.1 with default `UNMANAGED` state.

Each capability remains separately gated. Inclusion in scope does not permit a
later milestone to be implemented before its supplemental contracts/tests.

### 6.2 Out of scope

- automatic Provider switching, fallback, or failover;
- implicit or private-state-based session migration/rebinding;
- Claude Provider selection;
- active Local Provider support before a separate Local Provider ADR;
- multi-server, multi-user SaaS, tenant isolation, enterprise RBAC, or billing;
- general-purpose Secret Manager or external vault integrations;
- Web Secret paste/reveal/copy/download/storage;
- arbitrary Runtime config, raw TOML, arbitrary keys/options/headers/paths/
  environments/commands;
- Browser Terminal, Web shell, SSH/firewall/nginx/cloudflared/TLS automation;
- arbitrary Provider proxy/network scanner/custom package installation;
- root Helper Provider/Secret/Runtime actions;
- copying root or existing Codex/Claude/GitHub credentials;
- private Codex SQLite/JSONL/rollout/thread manipulation;
- automatic pairing/login/logout;
- Kubernetes, Docker management, multi-host orchestration, or public SaaS.

### 6.3 Product scope confirmation still required

The product owner must explicitly confirm:

- Linux/Codex-first V1;
- Official OpenAI plus approved compatible Providers only;
- Claude Runtime-only and Local inactive;
- no Web Secret input;
- no fallback/failover;
- single administrator/no tenancy claim;
- default block for unknown active-session impact;
- acceptable activation evidence level and paid-test policy.

This confirmation is a gate, not an invitation to expand scope.

## 7. First Implementation Gate

### 7.1 Governance gate before any engineering PR

The first engineering PR may be opened only after:

1. this canonical registry and all 66 Accepted constraints receive human
   architecture/security approval;
2. source ADRs are editorially updated or canonically imported under
   `P11-ADR-NNN` identifiers;
3. product scope decisions in section 6.3 are approved;
4. all Critical supplemental contracts below are Accepted;
5. the current Codex public-contract fixture set is reviewed and Secret/private-
   data clean;
6. threat model, migration strategy, and milestone-specific test gates are
   approved;
7. no P0/P1 security issue or blocking design-review thread remains.

### 7.2 Required supplemental contracts

| Canonical ID | Required decision | Blocks |
|---|---|---|
| P11-ADR-071 | Secret Cryptographic and Master-Key Profile | Any Secret store/key implementation |
| P11-ADR-072 | Secret Ingress, Backup, Recovery, and Retention Profile | Provisioning, rotation, revoke/delete, rollback Secret references |
| P11-ADR-073 | Codex Public Contract, Managed Configuration, and Lifecycle Profile | Runtime Provider capability, config, dry-run, activation |
| P11-ADR-074 | Provider Network, Private-Destination, TLS, Redirect, Proxy, and Paid-Test Policy | Live Provider validation and compatible endpoints |
| P11-ADR-075 | Activation Compatibility and Existing-Session Policy | Runtime Binding activation, Remote/session continuity |
| P11-ADR-076 | Transaction Persistence, Locking, Crash-Recovery, and Retention Profile | Config mutation, activation, rollback, automatic recovery |

### 7.3 Test-strategy gate

Before the first production slice, approve mechanical rules for:

- forbidden Secret/config/path/command/argv/env/header fields;
- migration fresh/upgrade/old-app compatibility/no-auto-adoption;
- Runtime UDS peer/framing/schema/data-minimization;
- Secret canary scanning across persistent/output/process/artifact surfaces;
- malicious endpoint/DNS/redirect/TLS/streaming fixtures;
- semantic config preservation and symlink/concurrent-edit/fault injection;
- active-writer/session admission races;
- crash at every transaction checkpoint and false-positive rollback rejection;
- existing Backend/Frontend/Security/E2E/Deployment/deployment-gate regression.

### 7.4 First safe production PR after the gate

The first production PR is limited to:

```text
Non-secret Provider core model
    + additive metadata schema
    + explicit UNMANAGED state
    + repositories/application services
    + audit/revision constraints
    + migration/security tests
```

It contains no Secret backend, Provider request, Runtime RPC, config access,
activation, rollback executor, API mutation, frontend, or active binding. No
Provider/Credential/Profile/Binding is auto-created during upgrade.

## 8. Remaining Blockers

### 8.1 Critical

1. **Human acceptance is not yet durable:** this review records Accepted
   decisions, but no governance PR/commit has made the canonical registry and
   status authoritative in repository history.
2. **P11-ADR-071 missing:** cryptographic algorithm/library/envelope and master-
   key custody/recovery are not frozen.
3. **P11-ADR-072 missing:** Secret ingress/backup/recovery/retention is not
   frozen.
4. **P11-ADR-073 missing:** current Codex public/config/credential/lifecycle/
   session contract and managed scope are unqualified.
5. **P11-ADR-075 missing:** minimum activation compatibility and existing/unknown
   session behavior are not approved.
6. **P11-ADR-076 missing:** transaction storage, locks, commit-pending, crash
   recovery, timeouts, and rollback retention are not frozen.

### 8.2 High

1. **P11-ADR-074 missing:** private/LAN endpoint, DNS rebinding, redirects, proxy,
   custom CA, TLS, paid-test payload/budget/retry policy remain open.
2. Product scope confirmation has not been recorded by the product owner.
3. Current Codex fixtures/evidence do not cover Phase 11 Provider/config/
   effective-binding/session capabilities.
4. Rollback behavior when a prior Secret is revoked or unavailable remains open.
5. Exact Runtime admission-fence integration and unmanaged-work treatment remain
   open.

### 8.3 Medium

1. Phase architecture numbering conflicts with implementation-plan milestone
   numbering at “11.8.”
2. Source ADR documents still contain Proposed statuses and deprecated aliases.
3. Evidence TTL/pruning, safe error taxonomy, diagnostics, and clock-anomaly
   policy need implementation profiles.
4. ACL/xattr/SELinux/filesystem durability qualification is not complete.
5. API/CLI confirmation/idempotency and frontend recovery UX remain later design
   work.

### 8.4 Low

1. Final UI wording for partial compatibility and recovery states is not frozen.
2. Phase 11 release/version naming is intentionally undecided.
3. Long-term external Secret-manager, Local Provider, and Claude Provider
   extension mechanisms remain deferred and do not block V1 when kept disabled.

## 9. Final Decision

### 9.1 Decision

```text
BLOCKED
```

The Phase 11 architecture invariants are now reviewable as an Accepted contract,
and the ADR collision has a canonical resolution. Phase 11 still cannot enter
engineering implementation because implementation-critical security, public
Codex, activation/session, network, and crash-recovery profiles are absent and
the acceptance record is not yet durable in repository governance.

### 9.2 Exact actions required to unblock

1. Obtain human architecture/security approval for this freeze review and the
   66 canonical Accepted decisions.
2. Create a documentation-only governance PR that installs the canonical
   `P11-ADR-NNN` registry, updates source statuses/aliases, and resolves milestone
   numbering.
3. Validate the then-current public Codex contract using official public
   documentation/help and sanitized deterministic fixtures without real
   credentials or private state.
4. Write, review, and Accept P11-ADR-071 through P11-ADR-076.
5. Record product-owner scope and activation/session/paid-test decisions.
6. Approve the first-slice migration schema rules, threat model, and test gates.
7. Re-run an implementation readiness gate; only a new review may change the
   result to `READY FOR IMPLEMENTATION`.

### 9.3 Recommended next action

Perform **Phase 11.10 — Public Contract Evidence and Supplemental Decision
Closure**, documentation/fixture work only. Its output should be the six
supplemental Accepted contracts, current sanitized Codex public-contract
evidence, product/security approvals, and a final gate review.

Do not open a production feature branch until that review returns
`READY FOR IMPLEMENTATION`.

Phase 11 implementation remains **NOT STARTED**.
