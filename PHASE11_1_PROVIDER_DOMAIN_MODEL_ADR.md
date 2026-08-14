# AgentBox Phase 11.1 — Provider Domain Model Architecture Decision Record

Status: **Proposed — design only, awaiting human approval**
Scope: Phase 11.1 domain model only
Governance acceptance: The decision content is canonically registered as
P11-ADR-001 through P11-ADR-009 and **Accepted** in `docs/adr/README.md`.
The document-local `ADR-001` through `ADR-009` labels and the status above are
historical drafting metadata. Acceptance becomes repository-effective only
after the Phase 11.10 governance change is reviewed and merged into `main`.
Contextual alternatives and open questions remain historical; supplemental
P11-ADR-071 through P11-ADR-076 provide their governing resolution.
Architecture sources: `PHASE11_PROVIDER_MANAGER_PROPOSAL.md` and
`PHASE11_IMPLEMENTATION_PLAN.md`
Repository baseline: `ForceMind/agentbox` at
`1c2005de59b1c5063b260591206a8411c7e5b1a5`

This document defines terminology and domain boundaries. It does not authorize
code, migrations, database tables, API/UI implementation, Secret storage,
Codex configuration changes, Provider activation, or session mutation. The
accepted Phase 0–10 architecture remains unchanged.

## 1. Problem Statement

### 1.1 The missing abstraction

AgentBox currently manages AI Runtime control without owning a formal AI
execution Provider domain. For Codex, Remote Control can answer questions such
as:

- Is Codex installed and does its public CLI expose Remote Control?
- Can AgentBox start, stop, observe, or pair the Remote process?
- Is Remote state running, stopped, broken, or unknown?

Those controls do not define where inference is executed. They do not describe
the backend endpoint, wire protocol, model, credential requirement, Provider
capabilities, or the compatibility of that backend with a particular Codex
Runtime.

Without a Provider abstraction, implementation would tend to encode Provider
selection directly inside Codex lifecycle operations or edit Runtime config as
unstructured text. That would conflate at least four different concerns:

1. connecting to and controlling a Runtime;
2. selecting an AI execution backend;
3. supplying a credential to that backend;
4. deciding whether an existing session remains valid after a change.

This conflation would make it difficult to explain whether a failure came from
Remote Control, Provider connectivity, authentication, model compatibility, or
session continuity. It would also make rollback and audit ambiguous.

### 1.2 Why Remote Control and Provider Management remain separate

Remote Control and Provider Management have different identities, lifecycles,
failure modes, and security boundaries:

| Concern | Remote Control | Provider Manager |
|---|---|---|
| Primary question | How is the Runtime connected and controlled? | Which backend should execute AI requests? |
| Examples | detect, start, stop, pair, observe | define, validate, bind, activate, disable |
| Credential domain | Runtime/Remote login and Pair flow | Provider credential metadata and opaque Secret reference |
| Main failure | disconnected, unsupported, broken, unknown | unreachable, unauthenticated, incompatible, degraded |
| Session impact | owns Runtime lifecycle observations | evaluates but does not assume continuity |
| Privilege | existing non-root Runtime boundary | no new privilege and no root Helper expansion |

A Provider API can be reachable while Codex Runtime requests fail. Codex can be
connected remotely while the selected Provider is unavailable. Pairing can
succeed without proving Provider authentication. A session can remain visible
while context continuity fails. These states must remain independently
observable.

### 1.3 Required boundary

The foundational relationship is:

```text
Provider Manager                   Remote Control Manager
    |                                  |
    | typed Provider intent            | detect/start/stop/pair
    v                                  v
Runtime-specific Provider Adapter  Runtime lifecycle adapter
    |                                  |
    +---------------+------------------+
                    v
               AI Runtime
                    |
                    v
              AI Provider
```

Provider Manager belongs to the `agentbox` control plane. It owns non-secret
descriptions, selection intent, lifecycle metadata, validation evidence, and
audit intent. It does not execute AI workloads, open Runtime configuration
files, decrypt Provider Secrets, spawn Codex, or control root services.

Provider-specific configuration rendering, Secret use, Provider requests, and
Runtime execution remain inside `agentbox-runtime`. The root Helper does not
participate.

## 2. Domain Concepts

### 2.1 Provider

#### Definition

A `Provider` is a concrete, non-secret definition of an AI execution backend
that AgentBox may validate and make available to a compatible Runtime Profile.

Phase 11 v1 Provider types are:

- Official OpenAI;
- OpenAI-compatible HTTP Provider.

A future Local Provider is represented only as an extension point. It is not a
Phase 11.1 implementation target or an activated v1 capability.

#### Provider-owned information

A Provider conceptually owns:

- opaque Provider identity and identity-schema version;
- administrator-facing display name;
- typed Provider kind;
- normalized endpoint identity where applicable;
- explicit wire/API protocol;
- model selection as defined by the approved Provider identity policy;
- versioned, typed, non-secret Provider options;
- declared or observed Provider capabilities;
- enabled/disabled lifecycle state;
- validation evidence references and freshness;
- optimistic revision and lifecycle timestamps.

The Provider is a definition, not a live process. “Provider health” is a
time-bound observation associated with it, not an intrinsic permanent property.

#### Provider does not own

A Provider does not own:

- raw credential or Secret material;
- Remote Control pairing/login state;
- Codex or Claude process lifecycle;
- Runtime executable, argv, shell, environment map, PID, or signal;
- filesystem paths or raw Runtime configuration;
- Project content;
- conversation history, thread/session files, or model output;
- systemd, SSH, firewall, proxy, tunnel, or package management;
- billing accounts, organization membership, or cloud infrastructure.

Changing a credential does not change Provider identity. Whether changing a
model creates a new Provider identity or a new Provider revision remains an
explicit versioning decision in Section 10.

### 2.2 Provider Capability

#### Definition

A `ProviderCapability` is a versioned, evidence-bearing statement about a
function that a Provider and selected model may expose. It is generic and does
not imply compatibility with every Runtime.

Examples include:

- conversational or completion-style generation;
- reasoning-oriented model behavior;
- tool/function invocation;
- streaming responses;
- structured output;
- model discovery;
- maximum or reported context size;
- supported request/wire protocols;
- authentication requirement;
- optional multimodal input classes.

Capabilities have at least:

- a stable AgentBox capability name;
- state such as `supported`, `unsupported`, `experimental`, or `unknown`;
- evidence class such as declared, Provider-reported, tested, or adapter
  inferred;
- evidence schema/adapter version;
- observation time and expiry;
- bounded sanitized evidence code.

A capability is not a generic free-form option bag. It cannot carry arbitrary
headers, request bodies, config keys, paths, commands, or Secrets.

#### Provider capability versus Runtime compatibility

Provider capability answers “what does this backend appear to offer?” Runtime
compatibility answers “can this Runtime use it safely through its public
contract?” These are different observations.

For example:

```text
Provider streaming capability: SUPPORTED
Codex streaming compatibility: UNKNOWN
Remote Control compatibility: NOT_TESTED
```

A Provider capability can contribute to a Runtime Profile validation, but it
cannot prove Codex Runtime, Remote, thread resume, context, or discovery
compatibility.

### 2.3 Credential

#### Definition

A `Credential` is the non-secret control-plane identity and lifecycle metadata
for authentication material used by one Provider.

It contains an opaque reference to Runtime-owned Secret material, but never the
value, ciphertext, prefix, suffix, reversible hint, Authorization header, or
low-entropy hash.

Credential conceptually owns:

- opaque Credential identity;
- Provider relationship;
- typed credential kind;
- opaque Runtime Secret reference;
- active Secret version;
- configured/missing/rotation/revoked state;
- safe validation state and freshness;
- revision and lifecycle timestamps.

Credential identity remains stable across a permitted Secret rotation. A
Provider may have no Credential when its approved type does not require one.

### 2.4 Runtime Profile

#### Definition

A `RuntimeProfile` is a versioned, non-secret execution configuration intent
that describes how one Runtime installation should use one Provider.

The relationship is:

```text
Provider
    +-- Provider capabilities and endpoint identity
    +-- optional Credential reference
              |
              v
Runtime Profile
    +-- Runtime type and installation
    +-- Provider and Credential revisions
    +-- adapter schema
    +-- typed Runtime-specific options
    +-- expected compatibility requirements
```

A Runtime Profile conceptually owns:

- opaque profile identity and revision;
- Runtime type/installation reference;
- Provider identity and revision;
- optional Credential identity and Secret version reference;
- Runtime-specific adapter and schema version;
- typed, non-secret Runtime options;
- public Runtime capability/schema evidence reference;
- validation state and profile digest.

A Runtime Profile does not own rendered TOML, a complete environment, a Secret,
or a Runtime process. Rendering and applying configuration are adapter/Runtime
operations outside this Phase 11.1 model.

One Provider may support multiple Runtime Profiles when different Runtimes or
approved Runtime options require different mappings. A Profile cannot claim
support for a Runtime merely because the Provider protocol is reachable.

### 2.5 Runtime Binding

#### Definition

A `RuntimeBinding` records AgentBox's explicit intent that one Runtime
installation use one Runtime Profile. It is the selection boundary between the
control plane and Runtime execution.

Conceptually it contains:

- stable AgentBox RuntimeBinding identity;
- Runtime installation identity;
- selected Runtime Profile and Provider revision;
- active/pending/failed/unmanaged state;
- previous binding reference for approved rollback;
- activation transaction and revision metadata.

The RuntimeBinding identity is not a current Codex `model_provider` identifier
and must not be derived from a Runtime's private state. A Runtime-specific
adapter maps the stable AgentBox intent to the public Runtime contract.

“Active” belongs to Runtime Binding, not to Provider identity. A Provider may be
the target of zero, one, or future multiple Runtime Bindings. In the current
single-Runtime product, the UI may derive “Active Provider” from the one active
binding, but the domain must not persist a globally active boolean on Provider.

### 2.6 Session Binding

#### Definition

A `SessionBinding` is an immutable, non-secret snapshot of the Runtime Binding
and Runtime Profile revision known to be effective when an AgentBox-observed
session started or was explicitly rebound through a supported public contract.

Conceptually it contains:

- AgentBox Session identity when one exists;
- Runtime installation and RuntimeBinding identity;
- Provider/Profile revision snapshot;
- public Runtime session/thread reference only when officially supported;
- effective time and evidence class;
- state such as `bound`, `legacy_unbound`, `rebind_required`,
  `continuity_unknown`, or `retired`.

A Session Binding does not own conversation content, model output, private
Codex IDs, JSONL, rollout data, discovery caches, or a Secret reference.

Changing the active Runtime Binding does not mutate an existing Session
Binding. Existing v0.3.0-rc.1 sessions remain `legacy_unbound` unless supported
public evidence proves a binding. When continuity cannot be proven, AgentBox
must recommend a new session rather than manufacture a relationship.

### 2.7 Compatibility Observation

A `CompatibilityObservation` records bounded evidence for one Provider/Profile/
Runtime combination. It keeps endpoint, network, authentication, model, wire
protocol, Provider API, Runtime, Remote, thread resume, context continuity, and
thread discovery as separate dimensions.

Each dimension is independently `PASS`, `FAIL`, `UNSUPPORTED`, `EXPERIMENTAL`,
`UNKNOWN`, or `NOT_TESTED`. An aggregate classification cannot hide a failing or
untested dimension.

### 2.8 Audit Record

An `AuditRecord` reuses AgentBox's existing audit domain. It records who
requested or observed a Provider-domain action, the opaque target, time,
revision, request/Job correlation, result, and sanitized code.

It never stores Secret material, Authorization, raw endpoint response, raw
Runtime config, prompt, completion, session content, or arbitrary metadata.

## 3. Identity Separation

### 3.1 Identity matrix

| Identity | Represents | Changes when | Must not be equated with |
|---|---|---|---|
| ProviderID | One concrete AI execution backend definition | Identity inputs change under approved versioning policy | Credential, Runtime, Codex Provider block, session |
| CredentialID | Authentication lifecycle metadata for a Provider | Credential object is replaced; Secret rotation normally keeps it stable | ProviderID, Secret value, admin user, Runtime login |
| RuntimeProfileID | One typed Runtime-to-Provider configuration intent | Profile identity/revision policy requires replacement | Rendered config, Runtime process, ProviderID |
| RuntimeBindingID | Stable AgentBox selection intent for one Runtime | Binding is explicitly replaced, not merely switched/revised | Current Codex Provider ID, ProviderID, SessionID |
| RuntimeInstallationID | One discovered/managed Runtime installation | The installation identity changes | Provider or credential |
| SessionID | One AgentBox-managed or observed Runtime session | A new session is created | RuntimeBindingID, ProviderID, thread content |
| SessionBindingID | One immutable effective-binding snapshot | A new supported binding event occurs | Session identity or active Provider state |
| Secret reference/version | One Runtime-owned secret record/version | Provision/rotation creates a version | CredentialID or ProviderID |

### 3.2 Why Provider and Credential identity are separate

A Provider endpoint and model can remain the same while its key rotates. If the
key were part of Provider identity, every rotation would appear to be a new
Provider, break binding history, enlarge Audit exposure, and encourage key
fingerprints in metadata. Conversely, one key must not silently authenticate an
unrelated Provider merely because a label matches.

### 3.3 Why Provider and Runtime identity are separate

One Provider can be used by different Runtime types or installations with
different public configuration contracts. A successful Provider request does
not mean a particular Runtime supports its protocol, tools, streaming, or
model. Runtime identity and compatibility remain explicit.

### 3.4 Why Runtime Binding and Session identity are separate

A Runtime Binding expresses current administrator intent; a Session records a
historical/effective execution context. Switching a binding must not rewrite
the Provider attribution or continuity expectations of existing sessions.

### 3.5 Why AgentBox identity and Runtime-private identity are separate

AgentBox opaque IDs are stable product identities. A current Codex config block,
thread ID, file path, or private database key is external evidence, not an
AgentBox primary key. Runtime-specific adapters may hold a bounded public
mapping, but private identifiers are never adopted as permanent domain identity.

## 4. Lifecycle Model

### 4.1 Provider lifecycle states

The Provider lifecycle should expose these conceptual states:

| State | Meaning |
|---|---|
| `discovered` | A read-only candidate or capability observation exists, but AgentBox has not adopted a managed Provider definition. |
| `configured` | Required non-secret metadata is complete and any required Credential reference is configured. No compatibility claim follows. |
| `validated` | Required Provider-level checks passed with fresh evidence. Runtime/Remote/session compatibility may still be unknown. |
| `active` | Derived presentation state: at least one active Runtime Binding selects a validated Provider/Profile. It is not a Provider-owned global boolean. |
| `needs_attention` | Metadata, credential state, evidence freshness, or referenced compatibility prevents safe use. |
| `disabled` | The Provider remains retained for history but cannot be selected for new bindings. |

`discovered` may remain an ephemeral read model rather than a persisted
Provider. Discovery must not auto-create a Provider or import configuration.

### 4.2 Provider transitions

```text
read-only candidate
       |
       | explicit adoption
       v
discovered --> configured --> validated
                    ^             |
                    |             | selected by verified Runtime Binding
                    |             v
                    +-------- active (derived)
                                   |
                    evidence/config/credential drift
                                   v
                           needs_attention

configured / validated / needs_attention --> disabled
disabled -- explicit re-enable + revalidation --> configured or validated
```

Transition rules:

- Discovery never creates an active Provider.
- Configuration completeness never implies validation.
- Provider validation never implies Runtime or Remote compatibility.
- Activation belongs to a Runtime Binding transaction and requires fresh
  validation plus all approved compatibility gates.
- Disabling an active or rollback-referenced Provider is blocked until the
  binding is safely changed and recovery references are released.
- Evidence expiry moves the effective state to `needs_attention` or requires
  revalidation; it does not automatically choose another Provider.
- Deletion is not a normal lifecycle transition in Phase 11.1. Future deletion
  requires reference checks and separate Secret-retirement policy.

### 4.3 Runtime Profile lifecycle

Recommended conceptual states:

```text
draft -> valid -> superseded
          |
          +-> incompatible
          +-> needs_attention
```

A Profile becomes valid only against a specific adapter schema and current
Runtime capability evidence. Editing identity-bearing inputs creates a new
revision or Profile under the approved versioning policy. A Profile is never
active by itself.

### 4.4 Runtime Binding lifecycle

Recommended conceptual states:

```text
unmanaged -> pending -> active
                |         |
                v         v
       activation_failed  needs_attention
                |         |
                +-> rollback_pending -> rollback_verified
```

- `unmanaged` is the default for existing installations.
- `pending` means a revision-bound plan exists; it does not mean config changed.
- `active` requires successful transaction and required validation.
- `activation_failed` does not imply recovery succeeded.
- `rollback_verified` requires independent restoration proof.
- Unknown state is explicit and is never converted to active by assumption.

### 4.5 Session Binding lifecycle

Session Bindings are append-only/immutable observations:

```text
legacy_unbound
bound
rebind_required
continuity_unknown
retired
```

A Provider switch creates no implicit Session Binding transition. A new binding
record may be created only when a supported public Runtime operation proves the
effective relationship. Historical records are not overwritten to match the
current active Provider.

## 5. Codex Relationship

### 5.1 Boundary

```text
Provider Manager             Codex Adapter                 Codex Runtime
----------------             -------------                 -------------
Provider metadata       -->  public contract mapping  -->  reads approved config
Runtime Profile              capability validation         executes AI requests
Runtime Binding intent       typed candidate plan           owns live process state
compatibility evidence       config ownership rules         owns public session state
non-secret revisions         lifecycle impact report        uses Runtime credentials
```

### 5.2 What Provider Manager knows

Provider Manager knows:

- Provider, Credential metadata, Runtime Profile, Binding, and Session Binding
  identities/revisions;
- typed Provider kind, endpoint identity, protocol, model, and options;
- credential configured state and opaque reference, never the Secret;
- compatibility observations and freshness;
- administrator intent, activation plan digest, and audit state.

It does not know raw Codex config, a Secret value, child environment, private
thread data, or executable command construction.

### 5.3 What Codex Adapter knows

The Codex Adapter knows:

- the currently validated public Codex config schema and help/capabilities;
- how to map a typed Runtime Profile to the approved managed config scope;
- which typed fields are supported;
- how to preserve unrelated settings;
- whether current public evidence says new request, reload, restart, new
  session, reauthentication, or unknown;
- how to report a bounded plan and compatibility evidence.

It does not establish product identity, own a Secret store, edit private Codex
state, accept raw TOML, or invent compatibility when public evidence is absent.

### 5.4 What Runtime owns

The `agentbox-runtime` boundary owns:

- fixed Runtime HOME and config path resolution;
- config parsing/rendering/application when later authorized;
- Runtime-owned protected snapshots;
- Secret resolution and minimal child injection;
- exact approved Codex process execution;
- Provider/Runtime/Remote/continuity probes;
- live Runtime state.

It does not open the AgentBox SQLite database or accept arbitrary control-plane
paths, shell, executable, argv, environment, PID, signal, or config.

### 5.5 Remote Control remains independent

Codex Remote Control retains detect/start/stop/pair authority. Provider Manager
may later request an explicitly planned lifecycle transition through that
existing manager, but cannot call Pair automatically or introduce a second
daemon/lifecycle implementation.

Provider activation must not equate:

- Pairing with Provider authentication;
- Remote connected with Provider compatibility;
- Provider request success with Runtime or session continuity;
- a current Codex Provider block name with RuntimeBindingID.

### 5.6 Public contract only

No Phase 11.1 decision assumes a specific undocumented Codex field, config
layout, thread database, JSONL/rollout format, reload mechanism, or Provider ID.
All Runtime-specific details require then-current public documentation/help and
versioned fixtures before implementation.

## 6. Claude Relationship

Claude remains Runtime-only in Phase 11 v1.

Existing responsibilities remain unchanged:

- `ClaudeAdapter` detects public installation/auth/capabilities;
- `ClaudeSessionManager` manages project-scoped tmux sessions;
- Claude credentials remain under the official CLI model in Runtime HOME;
- Provider Manager does not import, rotate, inspect, or replace Claude auth;
- Codex Provider changes do not change Claude config or sessions.

The domain may define a future `ClaudeProviderConfigAdapter` extension point,
but it remains disabled. Future integration requires a separately approved,
current public Claude Code contract covering:

- external Provider selection;
- credential references;
- configuration schema and validation;
- reload/restart behavior;
- active-session and continuity effects.

Claude must receive its own typed options and compatibility tests. Codex,
OpenAI, or OpenAI-compatible parameters cannot be assumed to apply.

## 7. Database-Agnostic Model

Phase 11.1 defines logical entities and invariants only. It does not select
physical columns, create migrations, or add database tables.

### 7.1 Logical entities

| Entity | Logical responsibility | Secret-bearing? |
|---|---|---|
| Provider | Concrete backend definition and non-secret lifecycle | No |
| ProviderCapability | Evidence-bearing Provider/model capability | No |
| Credential | Authentication metadata and opaque Secret reference | No |
| RuntimeProfile | Typed Runtime-to-Provider configuration intent | No |
| RuntimeBinding | Current/historical selection intent for a Runtime | No |
| SessionBinding | Immutable effective-binding observation | No |
| CompatibilityObservation | Layered Provider/Runtime/Remote/continuity evidence | No |
| ConfigTransactionRecord | Revisions, plan digest, safe phase, opaque snapshot reference, rollback evidence | No |
| AuditRecord | Actor/action/target/result correlation | No |

Secret records and complete config snapshots are deliberately outside this
logical database model. They belong to the future Runtime-owned Secret/config
transaction boundaries.

### 7.2 Relationships

```text
Provider 1 -------- * ProviderCapability
Provider 1 -------- 0..1 active Credential in v1
Provider 1 -------- * RuntimeProfile
Provider 1 -------- * CompatibilityObservation

RuntimeInstallation 1 -- * RuntimeProfile
RuntimeInstallation 1 -- * RuntimeBinding history
RuntimeProfile 1 -------- * RuntimeBinding history
RuntimeBinding 1 -------- * SessionBinding
RuntimeBinding 1 -------- * ConfigTransactionRecord

RuntimeSession 1 -------- 0..1 effective SessionBinding
Job 1 ------------------- 0..1 ConfigTransactionRecord
Job 1 ------------------- * AuditRecord
```

The “one active Credential” and “one effective Session Binding” statements are
v1 constraints, not a claim of future multi-tenant architecture.

### 7.3 Ownership

- Provider, Credential metadata, Profiles, Bindings, observations,
  transactions, and Audit belong to control-plane application services.
- The control plane may persist them in its existing database after a later
  approved migration.
- The Runtime receives typed IDs/revisions and returns bounded observations; it
  does not open the control-plane database.
- Raw Secret material, rendered config, protected snapshot content, and live
  Runtime state belong to `agentbox-runtime` and never become logical database
  fields.

### 7.4 Compatibility and migration invariant

An upgraded v0.3.0-rc.1 installation has no managed Provider entity or active
Runtime Binding by default. The logical read model reports the Runtime as
`unmanaged`. No existing config, credential, or session is imported or inferred.

Any future physical schema must be additive, preserve current records, and keep
older application rollback possible without silently leaving an activated
Provider configuration under an incompatible controller.

## 8. Security Boundary

### 8.1 Secret leakage prevention

Separating Provider and Credential means Provider metadata can be listed,
validated, audited, and bound without carrying a raw Secret. Credential holds
only an opaque Runtime reference. Runtime Profile and Bindings also contain no
Secret value.

The model prevents ordinary Web/API/DB/Job/Audit types from needing plaintext
credential fields. Actual Secret custody and injection remain a later,
separately approved `agentbox-runtime` boundary.

### 8.2 Runtime privilege-escalation prevention

Provider Manager describes intent; it does not execute. The domain has no
concept for shell, executable, argv, environment, cwd, filesystem path, PID,
signal, systemd unit, package name, UID/GID, owner, or mode. Adding any of these
as generic Provider/Profile fields would violate this ADR.

The root Helper receives no Provider operation. A compromised control plane
must still be constrained to typed opaque IDs and revisions over the existing
peer-authenticated Runtime boundary.

### 8.3 Provider-confusion prevention

Independent identities prevent:

- a rotated key from becoming a new Provider accidentally;
- two endpoints with similar names from becoming the same Provider;
- a Codex Provider block ID from becoming an AgentBox binding identity;
- Provider reachability from being reported as Runtime/Remote compatibility;
- a new active binding from rewriting an existing session's attribution.

Typed Provider kinds and adapter schemas prevent an OpenAI-compatible endpoint,
future Local Provider, and future Claude adapter from sharing an unsafe generic
parameter bag.

### 8.4 Uncontrolled-switching prevention

Provider definition does not itself activate anything. Selection belongs to a
Runtime Binding, while historical execution context belongs to immutable
Session Bindings. A later activation must be explicit, revision-bound,
validated, confirmed, serialized, and rollback-capable.

Phase 11.1 exposes no switching behavior. Existing sessions and active Runtime
state remain unchanged.

### 8.5 Tenant and infrastructure boundary

The model is single-node and single-administrator. It does not provide tenant
isolation, RBAC organizations, billing, cloud Secret services, or general
infrastructure control. Future multi-user support requires new authorization
and Runtime isolation decisions rather than adding a cosmetic tenant field.

## 9. ADR Decisions

The decisions below are **Proposed** until human approval. Their numbering is
scoped to this Phase 11.1 document and does not renumber the repository's
existing accepted ADR series.

### ADR-001 — Provider abstraction is separate from Runtime control

**Status:** Proposed

**Decision**

Provider Manager owns Provider definitions, capability evidence, Runtime
Profiles, Binding intent, and non-secret lifecycle state. Remote Control keeps
detect/start/stop/pair authority. Runtime execution and config/Secret operations
remain inside `agentbox-runtime`.

**Rationale**

Provider, Runtime, Remote, and session continuity have independent identities
and failure modes. Separation prevents Provider success from being mistaken for
Remote success and avoids expanding lifecycle methods into a config editor.

**Consequences**

- Provider activation later coordinates with, but does not replace, the
  existing Remote manager.
- Root Helper remains unchanged.
- Compatibility must be reported in independent dimensions.

### ADR-002 — Credentials are separate from Provider identity

**Status:** Proposed

**Decision**

Provider and Credential use independent opaque identities. Provider metadata
stores at most a Credential relationship; Credential metadata stores only an
opaque Runtime Secret reference and safe state. Secret rotation does not change
Provider identity.

**Rationale**

This permits safe rotation, avoids key-derived identity and metadata leakage,
and prevents credentials from contaminating Provider/API/audit records.

**Consequences**

- No raw Secret, prefix/suffix, ciphertext, or low-entropy key hash belongs in
  the Provider domain.
- Secret custody requires a later separate ADR and security review.
- Credential sharing across Providers remains disabled or unresolved for v1.

### ADR-003 — Claude remains Runtime-only in the initial implementation

**Status:** Proposed

**Decision**

Claude stays under the existing Claude Runtime/tmux management boundary. Phase
11 v1 does not add Claude Provider selection or credential management.

**Rationale**

Runtime neutrality does not justify assuming Claude supports Codex or
OpenAI-compatible Provider contracts. Enabling it without an official public
contract would create config, credential, and continuity risk.

**Consequences**

- A future adapter interface may exist but remains disabled.
- Claude auth/config/session state is unchanged by Phase 11 v1.
- Future support requires a separate public-contract review and approval.

### ADR-004 — Phase 11.1 does not modify active sessions

**Status:** Proposed

**Decision**

Phase 11.1 is domain design only. It neither activates a Provider nor modifies,
rebinds, stops, migrates, inspects private state of, or relabels any existing
session.

**Rationale**

Session continuity cannot be inferred from Provider metadata. Existing sessions
must remain operational and unattributed unless a supported public contract
provides proof.

**Consequences**

- Existing sessions are conceptually `legacy_unbound` or
  `continuity_unknown`.
- Session Binding is immutable evidence, not a mutable pointer to the active
  Provider.
- Later session rebind requires explicit approval and independent continuity
  validation.

### ADR-005 — Runtime Binding owns Provider selection

**Status:** Proposed

**Decision**

Active Provider selection is represented by Runtime Binding. Provider does not
carry a global active boolean; “Active Provider” is a derived view of the active
binding for a Runtime.

**Rationale**

Selection is meaningful only in relation to a Runtime/Profile. This prevents a
Provider record from conflating availability with use and preserves a clean
future extension to more than one Runtime installation.

**Consequences**

- One active binding per Runtime is the v1 invariant.
- Provider validation alone never activates it.
- Binding history can support explicit rollback without mutating Provider
  identity.

### ADR-006 — Session Binding is an immutable effective-state snapshot

**Status:** Proposed

**Decision**

Session Binding records the Provider/Profile revision known to be effective for
one session at one time and is never rewritten by a later Runtime Binding
change.

**Rationale**

Historical execution context must not follow current configuration
retroactively. Immutable evidence enables honest continuity and audit results.

**Consequences**

- New public evidence creates a new binding observation rather than rewriting
  history.
- Unsupported or unavailable evidence remains legacy/unknown.
- No private Runtime artifacts are read to populate this model.

### ADR-007 — Provider capabilities are evidence, not compatibility promises

**Status:** Proposed

**Decision**

Provider capabilities are versioned, time-bound observations. Provider,
Runtime, Remote, resume, context, and discovery compatibility remain distinct.

**Rationale**

A backend can advertise a feature that a Runtime cannot use, and a successful
request cannot prove session continuity.

**Consequences**

- Capability records carry evidence class and freshness.
- Higher compatibility layers remain `NOT_TESTED` or `UNKNOWN` until proven.
- Aggregate status cannot hide individual results.

### ADR-008 — The foundational domain model is database-agnostic and non-secret

**Status:** Proposed

**Decision**

Phase 11.1 defines logical entities and invariants without selecting physical
tables or migrations. All logical entities are non-secret; Secret records and
config snapshots remain outside the control-plane model.

**Rationale**

Domain stability should precede persistence implementation, and the existing
Runtime/control-plane identity separation forbids Secret custody in SQLite.

**Consequences**

- Physical schema work is a later reviewed milestone.
- Runtime never opens the application database.
- Existing v0.3.0-rc.1 installations remain unmanaged and unchanged.

### ADR-009 — Provider types use typed extension points, not a universal option bag

**Status:** Proposed

**Decision**

Official OpenAI, OpenAI-compatible HTTP, future Local, and future Runtime-native
Providers use explicit type-specific schemas and adapters. Local Provider is an
extension point only in v1.

**Rationale**

Provider types have different endpoints, credentials, protocols, trust models,
and capabilities. A universal bag would allow arbitrary headers/config and
couple the domain to Codex TOML.

**Consequences**

- Unsupported Provider-specific options fail closed.
- Local-process/model lifecycle is not introduced by this domain.
- Future adapters can extend the domain without changing root or Remote
  boundaries.

## 10. Open Questions

The following require product, security, or Runtime-contract decisions before
the affected implementation milestone:

1. **Provider identity/versioning:** Which fields are identity-bearing, and does
   a model change create a new Provider, a Provider revision, or only a new
   Runtime Profile?
2. **Discovery persistence:** Should `discovered` remain an ephemeral candidate,
   or may an administrator explicitly persist it as a disabled Provider?
3. **Capability discovery:** Which capabilities are Provider-declared versus
   actively tested, how are conflicting claims represented, and when does
   evidence expire?
4. **Context-size semantics:** Is context size Provider/model metadata,
   adapter-observed capability, or both with separate evidence?
5. **Runtime compatibility:** Which dimensions and freshness thresholds are
   required before a Profile can become bindable?
6. **Activation threshold:** For Codex Remote-managed use, must Remote recovery
   pass in addition to Provider and Runtime validation?
7. **Runtime Profile versioning:** Which option changes create a revision and
   which require a new profile identity?
8. **Session migration:** Is the default always finish-and-create-new, and under
   what public evidence may explicit resume/rebind be offered?
9. **Active-session policy:** Does unknown active-writer/session state block all
   switching, or permit a separately confirmed maintenance flow?
10. **Credential cardinality:** Is Credential sharing always prohibited in v1,
    and can a Provider have staged old/new versions during rotation?
11. **Provider disable/delete:** What historical references and rollback window
    prevent disablement or deletion?
12. **Private-network endpoints:** Are OpenAI-compatible RFC1918/ULA targets
    allowed, or must they wait for the future Local Provider policy?
13. **Local Provider boundary:** What capabilities can be described without
    introducing executable, model-path, container, or process lifecycle input?
14. **Public Codex identity:** Does the current public contract expose a stable
    session/thread identity sufficient for Session Binding?
15. **Claude extension:** What future official contract would be sufficient to
    reconsider Runtime-only status?
16. **Secret architecture:** Encryption, key custody, backup, local ingress,
    rotation retention, and physical deletion remain separate Phase 11 design
    decisions.

## Decision Outcome if Approved

Approval of this document authorizes only the terminology and boundaries above.
It does not authorize implementation. The recommended next design milestone is
Phase 11.2 planning for the read-only Runtime capability contract, after the
required public Codex contract validation and before any Secret or config work.
