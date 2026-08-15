# AgentBox Phase 11.6 — Codex Provider Adapter and Dry-run Plan Architecture Decision Record

Status: **Proposed — design only, awaiting human approval**
Scope: Codex-specific Provider translation and non-mutating activation planning
Governance acceptance: The decision content is canonically registered as
P11-ADR-051 through P11-ADR-059 and **Accepted** in `docs/adr/README.md`.
The document-local `ADR-051` through `ADR-059` labels and the status above are
historical drafting metadata. Acceptance becomes repository-effective only
after the Phase 11.10 governance change is reviewed and merged into `main`.
Contextual alternatives and open questions remain historical; supplemental
P11-ADR-071 through P11-ADR-076 provide their governing resolution.
Architecture sources: `PHASE11_PROVIDER_MANAGER_PROPOSAL.md`,
`PHASE11_IMPLEMENTATION_PLAN.md`,
`PHASE11_1_PROVIDER_DOMAIN_MODEL_ADR.md`,
`PHASE11_2_RUNTIME_CAPABILITY_CONTRACT_ADR.md`,
`PHASE11_3_SECRET_BOUNDARY_ADR.md`,
`PHASE11_4_CONFIG_TRANSACTION_FRAMEWORK_ADR.md`, and
`PHASE11_5_PROVIDER_VALIDATION_PIPELINE_ADR.md`
Repository baseline: `ForceMind/agentbox` at
`1c2005de59b1c5063b260591206a8411c7e5b1a5`

This document defines a future adapter and dry-run boundary. It does not
authorize code, database changes, Runtime or Codex/Claude changes, configuration
writes, snapshots, process lifecycle actions, external Provider requests, real
credential validation, Provider activation, a branch, or a commit.

No current Codex configuration shape, field, reload behavior, or session detail
is made a permanent contract by this design. Before implementation, the then-
current public Codex CLI help, public documentation, supported configuration
schema, authentication-reference capability, wire protocols, lifecycle behavior,
and Remote/session behavior must be reviewed and captured in versioned fixtures.

## 1. Problem Statement

### 1.1 Why a Codex Provider Adapter is required

The AgentBox Provider domain is intentionally Runtime-neutral. It describes
Provider identity, endpoint/protocol/model intent, Credential metadata, Runtime
Profiles, Runtime Bindings, validation evidence, and audit intent. Codex has its
own public configuration and lifecycle contract, which may change independently
of the AgentBox domain.

A dedicated `CodexProviderAdapter` is required to translate between those two
contracts without embedding Codex-specific assumptions in Web, API, Worker,
database, or the generic Provider domain.

The adapter provides one reviewed location to answer:

- which AgentBox Provider types are representable by the current public Codex
  contract;
- which typed Runtime Profile fields map to supported Codex concepts;
- which Runtime capabilities and Codex versions are required;
- which current settings are inside an AgentBox-managed semantic scope;
- which settings must remain untouched;
- whether the intended change affects new requests, a running process, Remote
  Control, authentication, or sessions;
- whether a safe dry-run and later transaction are possible.

### 1.2 Why Provider Manager cannot manipulate Codex directly

Direct control-plane manipulation would cross the existing identity boundary:

- `agentbox` would need access to Runtime HOME and potentially credentials;
- API input could become a path, raw TOML, config key, environment, or process
  control primitive;
- a stale or partial write could corrupt Codex configuration;
- unrelated user settings could be overwritten;
- undocumented files, thread state, or process behavior could become accidental
  product contracts;
- Provider activation could be conflated with pairing, login, Remote connection,
  or existing session state.

The control plane therefore sends typed intent and expected revisions only. A
Runtime-side adapter owns local interpretation. Even the adapter does not apply
configuration during dry-run; Phase 11.4 owns any future mutation transaction.

### 1.3 Why Runtime-specific adapters are necessary

Codex, Claude, future Runtimes, OpenAI-compatible protocols, and Local Providers
do not necessarily share configuration keys, credential references, lifecycle
semantics, or continuity guarantees. A universal config writer would either
expose arbitrary fields or encode the least-safe common denominator.

Runtime-specific adapters allow:

- typed, allowlisted mappings rather than arbitrary key/value input;
- public-contract and version-specific compatibility fixtures;
- precise lifecycle and session-impact classification;
- preservation of Runtime-owned and user-owned settings;
- fail-closed degradation when a public contract changes;
- separate future Claude handling without pretending Codex rules apply.

### 1.4 Codex remains externally owned

AgentBox orchestrates a supported integration boundary; it does not own Codex.
Codex continues to own execution, its documented local configuration behavior,
actual process state, Remote Control implementation, login/pairing state, and
public session behavior. AgentBox must not infer ownership from a file's
existence or from an observed private identifier.

## 2. Adapter Responsibility Model

### 2.1 Codex Provider Adapter responsibilities

The conceptual `CodexProviderAdapter`, executing inside the non-root
`agentbox-runtime` boundary, owns:

- mapping a typed, non-secret AgentBox Runtime Profile to supported public Codex
  configuration concepts;
- checking adapter/public-contract compatibility against fresh Runtime evidence;
- resolving the fixed Codex configuration target server-side;
- read-only parsing and semantic inspection of the current configuration;
- identifying the exact AgentBox-managed semantic scope and conflicts;
- generating an in-memory desired semantic model;
- validating that model against the approved public contract;
- creating a sanitized, immutable dry-run result and plan digest inputs;
- classifying expected lifecycle, Remote Control, authentication, and session
  effects conservatively;
- defining the later adapter-specific apply, verify, and rollback contract used
  by Phase 11.4, without executing it in dry-run.

The adapter does not own Provider identity, Credential lifecycle, authorization,
approval, transaction state, audit policy, or the active Runtime Binding.

### 2.2 Control Plane responsibilities

The `agentbox` control plane owns:

- user intent and Provider/Profile/Binding identity/revisions;
- authorization, approval, policy, and confirmation;
- selection of fresh Phase 11.5 validation evidence;
- request orchestration and non-secret dry-run projection;
- immutable plan metadata and audit correlation;
- deciding whether a plan is eligible to proceed to a future transaction.

It never receives current or candidate raw Codex configuration, Runtime HOME
paths, Secret Material, child environments, arbitrary Runtime output, or
private Codex state.

### 2.3 Codex Runtime responsibilities

Codex owns:

- execution of AI requests;
- interpretation of its supported configuration;
- actual process and Remote Control behavior;
- public login, pairing, thread, resume, discovery, and context behavior;
- changes in its public contract across versions.

AgentBox does not patch Codex, modify its private databases/JSONL/rollout files,
invent a reload API, or claim compatibility that Codex does not publicly expose.

### 2.4 Runtime execution responsibilities

The broader `agentbox-runtime` layer—not the dry-run adapter alone—will later
own:

- protected snapshot and local transaction journal;
- atomic application through the approved adapter operation;
- minimal Secret resolution/delivery for the exact Runtime operation;
- approved lifecycle coordination using existing managers;
- post-application Provider, Runtime, Remote, and continuity verification;
- verified rollback.

Those responsibilities are inactive in this design phase.

### 2.5 Adapter types remain separate

A Provider protocol adapter tests endpoint, authentication, model, and wire
behavior. A Runtime Provider adapter maps Provider intent into one Runtime's
public configuration contract. A successful protocol test does not prove the
Codex mapping or Runtime behavior.

## 3. Provider Mapping Model

### 3.1 Conceptual flow

```text
Provider
    non-secret backend identity, type, endpoint policy, protocol, model options
        |
        v
Runtime Profile
    versioned typed Provider intent for one Runtime family
        |
        v
Codex Provider Adapter
    public-contract compatibility + semantic mapping + dry-run
        |
        v
Codex Runtime
    reads supported config and executes requests under its own behavior
```

A future `RuntimeBinding` selects one validated Runtime Profile for one Runtime
installation. It is not a Codex config block name, model-provider string,
process identity, thread identity, or credential.

### 3.2 Provider input

The generic Provider layer may supply only typed, non-secret intent:

- ProviderID/revision and Provider type;
- safe display identity;
- normalized endpoint identity/destination class where applicable;
- explicit wire/API protocol;
- selected model or model reference;
- versioned Provider-specific typed options;
- CredentialID and opaque Secret-version reference metadata;
- Phase 11.5 evidence-bundle ID/digest and compatibility matrix.

It does not supply raw config keys, raw TOML, headers, Secret values, an
environment map, a file path, executable, command, argv, PID, signal, or current
Codex Provider block name.

### 3.3 Runtime Profile

A `RuntimeProviderProfile` is the stable typed mapping input for the Codex
adapter. It binds:

- Provider and Credential metadata revisions;
- target Runtime family and installation identity;
- model/protocol intent;
- adapter-approved options only;
- non-secret credential-delivery capability/reference intent;
- lifecycle/continuity policy intent;
- validation-evidence digest and expiry.

The profile does not contain raw Codex configuration or Secret Material. Options
unsupported by the Codex adapter are rejected; they are not serialized under
an arbitrary extension map.

### 3.4 Adapter mapping output

The adapter creates two conceptual outputs:

1. a **Runtime-private candidate semantic model** used only to validate what the
   current config would mean after the managed change; and
2. a **sanitized dry-run plan** returned through the typed Runtime contract.

The private semantic model may represent the complete parsed document so
unrelated settings can be preserved, but its raw values never leave Runtime.
The control-plane plan contains only safe field names, change classes, digests,
impact/evidence states, and blockers.

### 3.5 Identity rules

- ProviderID identifies AgentBox Provider metadata.
- RuntimeProfileID identifies a versioned mapping intent.
- RuntimeBindingID identifies the control-plane selection for a Runtime.
- AdapterContractID identifies one reviewed Codex public-contract mapping.
- ManagedScopeID identifies AgentBox's local semantic ownership record.
- Codex public identifiers remain external evidence and are never AgentBox
  primary keys.
- SessionBinding records effective historical state; activation never rewrites
  it.

## 4. Codex Adapter Boundary

### 4.1 What the adapter may know

The adapter may know only what is necessary to perform its reviewed mapping:

- the then-current validated public Codex CLI/config/provider contract;
- supported Provider types and typed option schemas;
- required Codex/Runtime capability names and evidence versions;
- supported public credential-reference mechanisms;
- fixed Runtime-owned target-resolution rules;
- current file type, ownership, mode, fingerprint, and trusted parent evidence;
- the complete current config semantic structure inside Runtime;
- the exact AgentBox-managed semantic scope and ownership/conflict metadata;
- non-secret endpoint identity, protocol, model, and option intent;
- opaque Credential/Secret-version reference metadata and safe availability
  state, not the value;
- expected new-request/reload/restart/reauthentication/session behavior when
  public evidence supports it;
- required Phase 11.5 and transaction verification dimensions.

### 4.2 What the adapter must not know or accept

The adapter must not receive, own, or expose:

- plaintext Provider Secrets, Codex login tokens, Pair Codes, Claude/GitHub
  credentials, AgentBox application secrets, or administrator passwords;
- root or another user's credential files;
- caller-selected config paths or arbitrary Runtime HOME paths;
- raw TOML, arbitrary config keys/values, arbitrary Provider block names, raw
  environment variables, or arbitrary headers;
- shell, script, executable, argv, cwd, PID, signal, package, systemd unit, UID,
  GID, mode, or owner from the caller;
- unrelated system configuration, Project files, Git worktrees, tmux pane
  output, or process environments;
- private Codex SQLite, JSONL, rollout, thread/conversation files, or inferred
  internal identifiers;
- Provider request/response bodies, prompts, completions, tool output, or
  conversation history.

### 4.3 Fixed target and managed scope

The target is resolved server-side for the exact Runtime installation using the
approved public contract. The caller cannot name `~/.codex/config.toml` or any
other path.

AgentBox manages only a narrowly defined, versioned semantic scope. The exact
scope representation must be supported by the then-current public format and a
lossless or otherwise approved preservation strategy. The adapter must detect:

- no managed scope;
- exactly one valid AgentBox-managed scope;
- a conflicting or duplicate scope;
- an unsupported legacy scope;
- ownership/fingerprint uncertainty;
- settings that cannot be safely preserved.

It must not claim ownership of the entire Codex configuration or infer ownership
from a coincidental field/block name. If safe ownership cannot be proven, the
dry-run is blocked.

### 4.4 Public contract profiles

Each supported integration is described by a versioned
`CodexPublicContractProfile` derived from reviewed public documentation/help and
fixtures. It declares:

- supported Codex evidence range/fingerprints;
- public config schema and validation method;
- supported Provider/profile fields;
- credential-reference mechanism;
- managed-scope rules;
- reload/restart/new-session/reauthentication classification;
- required validation and post-validation dimensions;
- known incompatible or uncertain behaviors.

Version alone is insufficient. Changed, malformed, localized, incomplete, or
unrecognized public output causes the affected capability to become `UNKNOWN`.

### 4.5 Fail-closed contract selection

No closest-version, prefix, lexicographic, or optimistic fallback is allowed.
The adapter selects an exact compatible public-contract profile using fresh
capability evidence. If no profile matches, it may return a safe blocked dry-run
showing `UNKNOWN`/`UNSUPPORTED`; it cannot generate an activatable plan.

## 5. Dry-run Model

### 5.1 Definition

A `CodexProviderDryRun` is a read-only evaluation of one immutable Runtime
Profile against one observed Codex installation and current configuration
fingerprint. It produces evidence and a proposed semantic change plan without
performing any mutation.

### 5.2 Dry-run inputs

Inputs are strictly typed and revision-bound:

- DryRunID/request correlation;
- Provider, Credential, Runtime Profile, candidate Runtime Binding, and Runtime
  installation IDs/revisions;
- selected Secret-version reference metadata, never Secret Material;
- Phase 11.5 evidence-bundle ID/digest and expiry;
- required Runtime capability evidence IDs/revisions;
- expected current Runtime/config ownership state when already known;
- selected public-contract profile and adapter version;
- lifecycle/session policy intent;
- current policy/approval class.

### 5.3 Read-only processing

The Runtime adapter:

1. authenticates the fixed typed request and target Runtime identity;
2. validates all IDs/revisions, capability evidence, validation evidence, and
   adapter/public-contract versions;
3. resolves and safely opens the fixed config target read-only with no-follow
   and trusted-parent checks;
4. records type, owner, mode, identity, and content fingerprint;
5. parses the complete current configuration in Runtime memory;
6. identifies the managed scope and preservation/conflict status;
7. maps the typed Runtime Profile into an in-memory desired semantic model;
8. validates the complete desired semantic model against the public contract;
9. derives a semantic diff and lifecycle/session impact;
10. builds a sanitized immutable dry-run result and deterministic plan digest;
11. discards raw configuration/candidate values after the bounded operation.

Dry-run does not create a snapshot or transaction journal because there is no
mutation to recover. It must not write a target or staging file merely to claim
read-only behavior. If public Codex validation can only be performed by a
mutating command or writing a candidate file, that capability is unsupported
until a separate safe design is approved.

### 5.4 Dry-run output

The safe output contains:

- DryRunID, adapter/public-contract/schema versions, and plan digest;
- exact target opaque IDs/revisions and evidence-bundle digest;
- current config fingerprint and safe ownership/conflict classification;
- managed-scope action: none, create, update, remove, conflict, or unknown;
- semantic change operations by allowlisted field name and change class;
- Provider type, safe destination identity/class, protocol, and model;
- credential requirement and safe presence/reference status, never value;
- expected affected Runtime components;
- lifecycle impact classification;
- existing-session and new-session impact classification;
- required pre/post-validation matrix;
- snapshot/rollback prerequisites for the future transaction;
- warnings, blockers, unknowns, expiry, and approval requirements;
- status such as `NO_CHANGE`, `READY_FOR_APPROVAL`, `BLOCKED`,
  `NEEDS_REVALIDATION`, or `UNKNOWN`.

### 5.5 Dry-run does not

A dry-run does not:

- write, create, replace, chmod, chown, rename, delete, or migrate a file;
- create a config snapshot, transaction journal, or active Runtime Binding;
- resolve/decrypt/use a Secret or construct a plaintext child environment;
- invoke Codex for a Provider request;
- start, stop, restart, pair, authenticate, signal, or attach to Codex;
- alter Remote Control, tmux, sessions, threads, context, or discovery state;
- call a real Provider endpoint;
- prove activation success or future availability.

### 5.6 Immutability, expiry, and digest

The dry-run plan is immutable and short-lived. Its digest binds:

- Provider/Credential/Secret-reference/Profile/Binding/Runtime IDs/revisions;
- validation-evidence and capability-evidence digests;
- adapter/public-contract/policy versions;
- source config fingerprint and managed-scope identity;
- semantic change set;
- lifecycle/session impact and verification matrix;
- expiry and approval class.

Any relevant change invalidates the plan. A future transaction re-runs all
security-critical checks and must not silently update the approved plan.

### 5.7 Plan status versus eligibility

`READY_FOR_APPROVAL` means the dry-run found no current blocking condition under
the exact policy. It is not authorization and not activation eligibility beyond
the plan expiry. `NO_CHANGE` means the desired managed semantics already match;
it does not prove Runtime requests use that Provider. `BLOCKED` and `UNKNOWN`
preserve detailed reasons without exposing raw configuration.

## 6. Configuration Diff Model

### 6.1 Semantic diff

AgentBox compares parsed semantics within the approved managed scope:

```text
Current semantic state
    + typed desired Runtime Profile
    -> allowlisted semantic operations
    -> complete desired semantic model
```

The safe diff uses operations such as:

- `MANAGED_SCOPE_CREATE`;
- `MANAGED_SCOPE_UPDATE`;
- `MANAGED_SCOPE_REMOVE` only for an explicit future rollback/deactivation plan;
- `FIELD_SET`, `FIELD_CHANGE`, or `FIELD_REMOVE` for allowlisted field names;
- `UNCHANGED`;
- `CONFLICT` or `UNKNOWN`.

The control-plane projection may say that `provider type`, `endpoint`, `model`,
`wire protocol`, `credential reference`, or a named typed option changes, but it
does not include Secret values, raw TOML snippets, or unrelated values.

### 6.2 Why semantic diff is preferred

Raw text replacement or line diff is unsafe because:

- TOML order and formatting are not the Runtime contract;
- comments and unrelated user settings may be lost;
- a raw diff may expose credentials or sensitive local configuration;
- text changes can appear large while semantics are unchanged;
- duplicate tables/keys and parser differences can hide conflicts;
- a caller could smuggle unsupported keys through a raw payload.

Semantic mapping enforces typed ownership and compatibility. It still requires
a preservation-capable implementation; semantic equivalence alone does not
authorize rewriting the entire user document.

### 6.3 Preservation requirements

The future implementation must prove one of:

- a round-trip parser/writer preserves all unrelated supported syntax and
  values to the approved standard; or
- a public Codex mechanism safely updates only the managed scope; or
- the plan is blocked because safe preservation cannot be guaranteed.

Comments, ordering, whitespace, duplicate semantics, extension tables, unknown
future keys, ACL/xattr/SELinux metadata, and file ownership requirements must be
classified before implementation. The dry-run reports preservation confidence
and blockers; it does not normalize the entire file for convenience.

### 6.4 Sensitive and unrelated differences

The adapter may inspect current values inside Runtime to preserve and validate
the complete document, but the safe plan reports only:

- `unrelated settings preserved`;
- `unrelated settings present but preservation unsupported`;
- `sensitive existing content detected by approved structural evidence`, if a
  public schema allows that determination without displaying it;
- `managed scope conflict`;
- safe field-level operations within AgentBox's scope.

It never returns a full before/after config, user-value diff, count that acts as
a Secret oracle, or raw hash intended for external correlation. The source
fingerprint is an opaque transaction precondition.

### 6.5 Idempotency

The same profile, evidence, adapter version, public-contract profile, and source
fingerprint must produce the same normalized semantic operations and plan digest.
A no-op dry-run remains a no-op and must not rotate credentials, rename a Codex
block, rewrite formatting, restart a Runtime, or update timestamps in the target
configuration.

## 7. Compatibility Model

### 7.1 Compatibility dimensions

The adapter evaluates independently:

- Codex installation identity and bounded public version evidence;
- executable/public-help fingerprint class;
- Runtime service and adapter availability;
- Codex Provider-adapter capability;
- public config target/schema/validation capability;
- supported Provider type;
- supported model/wire protocol and typed options;
- supported non-secret credential-reference mechanism;
- managed-scope and preservation capability;
- lifecycle behavior: new request, reload, restart, new session,
  reauthentication, or unknown;
- active-writer/session observation capability;
- required Provider, Runtime, Remote, resume, context, and discovery evidence.

### 7.2 Outcomes

Each dimension retains the Phase 11 vocabulary:

```text
PASS | FAIL | UNSUPPORTED | EXPERIMENTAL | UNKNOWN | NOT_TESTED
```

The aggregate remains:

```text
SUPPORTED | COMPATIBLE | EXPERIMENTAL | DEGRADED | INCOMPATIBLE | UNKNOWN
```

The detailed matrix is never hidden by the aggregate.

### 7.3 Known public behavior versus future capability

The adapter contract registry must distinguish:

- **Known public behavior** — documented and covered by reviewed fixtures for
  the exact supported Codex contract/profile;
- **Observed but uncontracted behavior** — diagnostic evidence only, never a
  mutation premise;
- **Future adapter capability** — declared as unavailable/unknown until public
  support and fixtures exist;
- **Private behavior** — prohibited, even if reverse engineering appears to
  make it work.

Current file shapes and observed `model_provider` names are fixtures, not stable
AgentBox identities. A version string alone cannot promote behavior into the
known category.

### 7.4 Unknown compatibility fails closed

If any mandatory dimension is `UNKNOWN`, stale, conflicting, or unsupported,
the adapter may return a blocked diagnostic dry-run but cannot return an
activatable transaction plan. It does not:

- select the nearest contract profile;
- assume hot reload;
- assume Pairing or login survives;
- assume existing sessions remain compatible;
- write first and test afterward;
- inspect private state to fill evidence gaps.

### 7.5 Compatibility invalidation

A dry-run becomes `NEEDS_REVALIDATION` when Codex executable/fingerprint,
version/help, adapter/public-contract profile, Runtime capability evidence,
Provider/Profile revision, Credential version reference, config fingerprint,
validation bundle, or lifecycle/session state changes.

## 8. Existing Session Handling

### 8.1 Initial safety policy

The initial recommendation is:

**Provider activation applies only to future work proven to use the new binding;
existing sessions are never implicitly migrated, rebound, relabeled, resumed,
restarted, or stopped.**

Where Codex's public behavior cannot isolate new work from existing work, the
dry-run is blocking or requires a later explicit maintenance/quiescence plan.
It must not promise a hot switch.

### 8.2 Session classifications

The dry-run may report:

- `NO_MANAGED_ACTIVE_SESSION`;
- `EXISTING_SESSIONS_UNCHANGED` when public evidence supports it;
- `NEW_SESSIONS_ONLY`;
- `QUIESCENCE_REQUIRED`;
- `RUNTIME_RESTART_REQUIRED`;
- `NEW_SESSION_REQUIRED`;
- `REAUTHENTICATION_REQUIRED`;
- `MIGRATION_UNSUPPORTED`;
- `CONTINUITY_EXPERIMENTAL`;
- `CONTINUITY_UNKNOWN_BLOCKING`.

These are plan impact classifications, not lifecycle actions.

### 8.3 Legacy and existing sessions

- Sessions predating Phase 11 remain `legacy_unbound` unless supported public
  evidence proves an effective binding.
- Existing SessionBinding records remain immutable historical/effective state.
- A new active Runtime Binding never rewrites an old SessionBinding.
- No private session file, thread database, JSONL, rollout, conversation content,
  or tmux pane is inspected to infer a Provider.
- `thread not discovered` is not reported as `thread deleted`.
- Pairing state, Codex login state, Provider authentication, and session binding
  remain separate observations.

### 8.4 Explicit future migration

Session migration/rebind is not supported by this ADR. A future feature would
require a separate typed public Codex contract, explicit user action, immutable
before/after SessionBinding evidence, context/resume/discovery tests, failure
recovery, and its own ADR. It cannot be smuggled into Provider activation.

### 8.5 Active work

If an active writer/turn/session cannot be safely observed, the state is
`UNKNOWN`, not idle. A future activation must block or require an explicitly
approved quiescence/maintenance workflow. Dry-run only reports the impact; it
does not send keys, stop tmux, kill a process, or wait on private state.

## 9. Secret Interaction Boundary

### 9.1 Dry-run uses no Secret Material

Dry-run checks only:

- whether a Credential is required;
- CredentialID/revision and Secret-version reference identity;
- safe lifecycle/presence/integrity evidence from Phase 11.3/11.5;
- whether the public Codex contract supports the selected non-secret reference
  mechanism.

It never decrypts, validates, hashes, prefixes, suffixes, stores, logs, or
injects the Secret value. Secret canaries must never appear in current/candidate
plan output, semantic diff, digest input visible to the control plane, logs,
Audit, Jobs, or reports.

### 9.2 Approved future Codex interaction

The Phase 11.10 contract selects one fixed command-backed AgentBox credential
broker. The managed profile contains only that root-owned executable path and
the typed non-secret arguments `codex`, RuntimeBindingID, and Binding revision.
It contains no Secret, bearer capability, transaction token, caller-supplied
command, argument, path, environment, or destination.

During a later separately authorized execution, `agentbox-runtime` may resolve
the exact opaque Secret version only under `COMMITTED_ACTIVE_USE` or the
transaction-local `CANDIDATE_ACTIVATION_VERIFICATION` eligibility mode. The
candidate mode requires the exact post-publication
`CANDIDATE_VERIFICATION_AUTHORIZED` checkpoint, retains the ordinary-session
admission fence, expires within 60 seconds, and permits at most two durably
counted broker invocations/resolutions. The config adapter and control plane do
not receive the plaintext value.

### 9.3 Fail-closed delivery capability

If public Codex behavior does not support a safe credential-reference/delivery
method for the selected Provider, the adapter reports `UNSUPPORTED` or
`UNKNOWN`. It must not fall back to:

- plaintext in TOML;
- argv or URL;
- a caller-supplied environment map;
- long-lived systemd or AgentBox service environment;
- Project `.env` or source files;
- root Helper decryption;
- copying `/root/.codex` or another user's auth/config;
- an undocumented file descriptor, stdin, wrapper, or credential file.

### 9.4 Separation from Codex login and Pairing

Codex official login/Remote pairing credentials and Provider API credentials
are distinct. Provider Manager does not import, rotate, expose, delete, or
replace existing Codex login files; activation never automatically calls Pair
or logs Codex out.

## 10. Transaction Integration

### 10.1 End-to-end design flow

```text
Provider request / Runtime Binding intent
    -> Phase 11.5 Validation Evidence Bundle
    -> Codex Adapter read-only Dry-run
    -> immutable Configuration Transaction Plan
    -> user approval / impact confirmation
    -> Phase 11.4 precondition revalidation
    -> protected Runtime snapshot
    -> atomic semantic Apply by Runtime adapter
    -> Provider / Codex / Remote / continuity Verify
    -> Runtime Binding Commit
       or verified Rollback / NEEDS_ATTENTION
```

This Phase 11.6 design ends at dry-run/plan generation. Apply, restart,
post-validation, binding commit, and rollback remain disabled until Phase 11.7
and the full architecture receive approval.

### 10.2 Plan handoff

The Codex dry-run supplies adapter-specific plan evidence to the Phase 11.4
generic transaction framework:

- source config fingerprint and managed-scope identity;
- semantic change summary and private candidate digest;
- adapter/public-contract versions;
- required snapshot scope and preservation metadata;
- lifecycle/session impact and active-work classification;
- required pre/post-validation matrix;
- exact evidence/revision dependencies;
- rollback support/readiness classification;
- safe blockers, warnings, expiry, and approval requirements.

The control plane stores only the sanitized plan. Any private candidate semantic
model is reconstructed and revalidated inside Runtime at execution time; it is
not serialized into SQLite or accepted back from the caller.

### 10.3 Apply boundary

Future apply is a fixed adapter action that references an approved transaction
and plan digest. It does not accept raw config. Runtime must:

- reacquire the current target safely;
- verify all revisions, fingerprints, evidence, and locks;
- reconstruct the deterministic desired semantic model;
- create/verify a protected complete snapshot;
- stage, validate, atomically publish, fsync, reread, and verify according to
  Phase 11.4;
- coordinate only the lifecycle action explicitly present in the plan;
- enter `CANDIDATE_VERIFICATION_AUTHORIZED` only after profile postimage,
  revisions, lease, Runtime lock, and transaction-owned session fence agree;
- launch only the exact typed internal Codex candidate verifier;
- close candidate authorization before commit or rollback; and
- run required post-validation and report safe evidence.

The candidate verifier is not a user session and creates no Session Binding.
It cannot reuse direct Provider live-validation authority. A crash or uncertain
broker attempt count/outcome prohibits another candidate Secret issue and moves
to verified rollback or `NEEDS_ATTENTION`.

### 10.4 Stale plans and reconstruction

If reconstruction produces a different private candidate digest or semantic
change set, the plan is stale and no mutation occurs. Runtime cannot repair the
plan silently, select another Provider/Secret version, or ignore a newly active
session.

### 10.5 Commit and rollback

Runtime application does not itself make a Runtime Binding active. Only the
control plane commits it after required Provider, Codex Runtime, Remote, and
continuity checks pass. Any failure after mutation follows the protected
snapshot and independently verified rollback path. `Rollback attempted` is not
`Rollback verified`.

## 11. Failure Handling

### 11.1 Unsupported or changed Codex version

If no exact validated public-contract profile matches:

- return `UNSUPPORTED` or `UNKNOWN` with a safe code;
- retain read-only diagnostics/capability evidence;
- do not generate an activatable plan;
- do not try a nearby version or observed private format;
- require public-contract review, new fixtures, and adapter approval.

### 11.2 Provider/Profile mismatch

Unknown Provider types, unsupported protocols/models/options, incompatible
Credential requirements, or a Provider/Profile revision mismatch block dry-run.
The adapter does not drop unsupported fields, change the model, substitute the
Official Provider, or auto-fallback.

### 11.3 Invalid or conflicting configuration

Parse errors, duplicate/conflicting managed scopes, unsafe type/owner/mode,
symlinks/special files, untrusted parents, unknown preservation behavior, or a
config fingerprint conflict produce `BLOCKED`/`NEEDS_ATTENTION`. Dry-run does
not modify, normalize, repair, rename, or back up the file.

### 11.4 Runtime unavailable or evidence stale

If Runtime peer authentication fails, Runtime is unavailable, capability
evidence is expired, or the executable/config changes during planning:

- preserve existing historical evidence as stale;
- return `UNKNOWN` or `NEEDS_REVALIDATION`;
- do not use direct control-plane filesystem/process fallback;
- do not activate from cached evidence alone.

### 11.5 Secret-reference incompatibility

A missing/revoked/rotating Credential, changed Secret version, absent safe
reference capability, or uncertain delivery semantics blocks the plan. Dry-run
does not test or reveal the Secret to diagnose the mismatch.

### 11.6 Failed future activation

After a later approved apply, failure in publication, lifecycle, Provider,
Runtime, Remote, or continuity verification triggers the Phase 11.4 rollback
policy. If restoration cannot be verified, the Runtime enters
`NEEDS_ATTENTION`; no Provider is selected automatically.

### 11.7 Interruption and timeout

A dry-run is safe to retry only after confirming it was read-only and binding a
new run to fresh evidence/fingerprint. A timeout does not yield a ready plan.
During future mutation, timeout is an unknown transaction outcome requiring
journal reconciliation, never blind reapplication.

## 12. Security Review

### 12.1 Arbitrary Codex manipulation

The adapter request contains fixed operation enums, opaque IDs, expected
revisions, and evidence digests. It cannot express raw config, a path, command,
executable, argv, environment, PID, signal, tmux input, package, or systemd unit.
Unknown actions/fields fail closed under the existing versioned Runtime UDS,
frame/time bounds, socket permissions, and `SO_PEERCRED` validation.

The adapter never attaches to a Codex session, edits private state, or invokes
Pair as part of Provider planning.

### 12.2 Secret exposure

Dry-run resolves no Secret. Plans contain only safe credential requirement and
opaque reference status. Raw current/candidate config and sensitive unrelated
settings stay inside bounded Runtime memory and are discarded. Logs/Audit use
typed safe codes and never serialize Provider responses, auth output, config
values, environment, or Secret-derived hints.

### 12.3 Unsafe configuration replacement

Controls include fixed target resolution, trusted-parent/no-follow checks,
complete parsing, narrow managed scope, typed mapping, duplicate/conflict
detection, preservation validation, expected fingerprint/revisions, immutable
plan digest, and Phase 11.4 snapshot/atomic replace/verified rollback.

Dry-run itself performs no write. A future apply cannot accept the control-
plane plan as raw bytes; Runtime reconstructs and revalidates the candidate.

### 12.4 Privilege escalation

The adapter runs as non-root `agentbox-runtime`. It does not call sudo, setuid,
package managers, arbitrary systemctl, or the root Helper. `agentbox` remains
unable to read Runtime HOME or credentials. Root Helper receives no Provider,
Secret, Codex config, validation, or adapter action.

### 12.5 Malicious Provider metadata

The adapter consumes only Phase 11.5 validated, normalized, typed Provider
metadata. Endpoint, model, protocol, and options remain bounded and allowlisted.
They cannot become config keys, paths, commands, environment names, headers, or
HTML. Safe plans display the data destination and compatibility class without
exposing credential material.

### 12.6 Stale evidence and TOCTOU

Plan expiry, exact IDs/revisions, config fingerprint, adapter/public-contract
version, Runtime capability evidence, validation-bundle digest, active-work
state, and deterministic candidate digest bind dry-run to future execution.
Phase 11.4 revalidates immediately before mutation and detects external edits.

### 12.7 Runtime compromise and residual risks

- A compromised `agentbox-runtime` can forge local evidence or inspect Runtime
  memory within the existing trust boundary.
- Root can ultimately inspect host state.
- A public Codex contract can change after validation.
- Lossless preservation can be difficult when parsers normalize formatting or
  unknown future syntax.
- A dry-run cannot prove future Provider availability, cost, or actual Runtime
  behavior.
- Session and hot-reload behavior may remain unknown.
- File-level atomicity cannot make configuration, process lifecycle, Provider,
  and database state distributed ACID; recovery remains compensating.

These risks require explicit compatibility states and verified recovery, not
broader adapter powers.

## 13. ADR Decisions

### ADR-051 — Codex integration uses an adapter boundary

**Status:** Proposed

**Decision:** Provider Manager sends typed, non-secret intent to a reviewed
Runtime-side Codex Provider Adapter. The adapter maps only the then-current
validated public Codex contract and never exposes generic config or execution
primitives.

**Consequence:** Codex-specific schema and lifecycle behavior remain isolated
from the generic Provider domain and control plane.

### ADR-052 — Dry-run precedes Provider activation

**Status:** Proposed

**Decision:** Every proposed Codex Provider activation requires a read-only,
revision-bound semantic dry-run before approval or transaction application.
Dry-run performs no file, process, Secret, endpoint, or binding mutation.

**Consequence:** The administrator can review safe semantic changes, lifecycle
impact, evidence, and blockers before any Runtime state changes.

### ADR-053 — Existing sessions are not implicitly migrated

**Status:** Proposed

**Decision:** Provider activation does not rewrite, rebind, relabel, resume,
restart, or stop existing Codex sessions. Existing SessionBindings remain
immutable; legacy sessions stay unbound unless public evidence proves otherwise.

**Consequence:** Initial activation favors new sessions and explicit quiescence
over unproven continuity or hidden session mutation.

### ADR-054 — Unknown Codex compatibility fails closed

**Status:** Proposed

**Decision:** Missing, stale, changed, undocumented, conflicting, or unrecognized
mandatory Codex evidence blocks an activatable plan. The adapter may return safe
diagnostics but cannot infer behavior from version proximity or private files.

**Consequence:** Newly changed Codex versions require public-contract review and
fixture qualification before Provider mutation is enabled.

### ADR-055 — Configuration changes are semantic and scope-limited

**Status:** Proposed

**Decision:** The adapter maps typed Runtime Profiles into a narrow versioned
AgentBox-managed semantic scope while preserving unrelated settings. Raw file
replacement, raw TOML, arbitrary keys, and whole-config ownership are prohibited.

**Consequence:** A preservation failure or ownership conflict blocks planning
rather than sacrificing user settings.

### ADR-056 — Dry-run never resolves Provider Secret Material

**Status:** Proposed

**Decision:** Dry-run uses only Credential/Secret-reference identity and safe
lifecycle/presence evidence. The config adapter never stores, logs, returns, or
injects plaintext Secret Material.

**Consequence:** Planning can be exposed through authenticated control-plane
workflows without moving Provider credentials into Web/API or SQLite.

### ADR-057 — Runtime reconstructs the private candidate at apply time

**Status:** Proposed

**Decision:** The control plane stores a sanitized semantic plan and digest, not
candidate config bytes. During a future approved transaction, Runtime
deterministically reconstructs and revalidates the candidate against current
state before mutation.

**Consequence:** A compromised/stale control-plane payload cannot become an
arbitrary Codex config write, and changed state invalidates the plan.

### ADR-058 — Codex pairing and Provider authentication remain separate

**Status:** Proposed

**Decision:** Provider planning/activation never automatically pairs, logs in,
logs out, imports, deletes, or rotates Codex Remote credentials. Pairing,
Provider authentication, Runtime compatibility, and Remote connection remain
independent observations.

**Consequence:** A Provider change cannot silently disrupt or impersonate the
existing Remote Control lifecycle.

### ADR-059 — Apply remains a Phase 11.4 Runtime transaction

**Status:** Proposed

**Decision:** The adapter does not create a second mutation engine. Any future
application, lifecycle action, verification, binding commit, and rollback use
the Phase 11.4 transaction state machine under Runtime execution ownership.

**Consequence:** Dry-run and apply share one revision/evidence model without
bypassing snapshot, atomicity, audit, or verified recovery controls.

## 14. Open Questions

The following require product, security, or implementation approval before a
Codex adapter can be implemented:

1. **Public configuration contract:** What does the then-current official Codex
   documentation/schema support for Provider definitions, models, wire APIs,
   validation, and credential references?
2. **Supported Codex versions:** Which exact public-contract profiles and
   executable/help fixtures are qualified, and what is the support window?
3. **Managed scope:** How is AgentBox ownership represented without relying on
   a private field/comment or claiming the whole config?
4. **Lossless preservation:** Which parser/writer or public update mechanism
   preserves unrelated values, extensions, comments, ordering, and future keys
   to the accepted standard?
5. **Configuration target:** What fixed target-resolution rule is public,
   portable, symlink-safe, and compatible with Runtime HOME?
6. **Public validation method:** Can a complete candidate be schema-validated
   entirely in memory without writing or invoking a mutating Codex command?
7. **Provider types:** Are Official OpenAI and which OpenAI-compatible profiles
   supported initially? Local and Runtime-native remain disabled until separate
   capability gates pass.
8. **Credential broker lifecycle:** Which qualified Codex versions preserve
   the fixed command-backed authentication behavior, and what restart/profile
   reload semantics apply? `env_key` and child-only injection are excluded from
   the managed Codex v1 contract.
9. **Existing inline credentials:** Must activation block until the user removes
   them, or can AgentBox preserve them opaquely without treating them as managed
   Secrets?
10. **Lifecycle impact:** Do supported changes affect new requests only, hot
    reload, require Runtime/Remote restart, new session, or reauthentication?
11. **Restart authority:** Which existing Remote lifecycle action may a future
    transaction request, and how is active work safely quiesced?
12. **Activation scope:** Is a Runtime Binding process-wide, new-session-only,
    request-scoped, or another public Codex concept?
13. **Active writer evidence:** Which current public evidence can prove idle,
    active, or unknown state without private process/session inspection?
14. **Session policy:** Is v1 strictly new-session-only, and under what public
    contract could explicit resume or migration ever be designed?
15. **Remote continuity:** What public tests prove Pairing/connection recovery
    separately from Provider and Runtime requests?
16. **Semantic diff disclosure:** Which endpoint/model/option changes are safe
    to display, particularly for private/local destinations?
17. **Sensitive existing config:** How is an opaque Runtime-only snapshot
    encrypted when the existing file contains unmanaged inline credentials?
18. **Metadata preservation:** Must snapshots/application preserve ACLs, xattrs,
    SELinux labels, owner/group/mode, and filesystem-specific durability?
19. **Plan lifetime:** What TTL applies to config fingerprints, active-work
    evidence, compatibility evidence, and approval?
20. **Candidate digest:** What canonical semantic encoding avoids parser/order
    ambiguity without revealing sensitive config?
21. **No-op verification:** What Runtime evidence proves the existing config is
    actually effective when semantic diff is `NO_CHANGE`?
22. **Adapter upgrade:** How are old dry-runs invalidated and interrupted
    transactions reconciled when the adapter/public-contract profile changes?
23. **Unknown fields:** Can unknown public-extension fields be losslessly
    preserved, or must their presence block v1 management?
24. **Claude boundary:** What future official Claude Code Provider contract
    would justify a separate adapter ADR without reusing Codex mappings?

## Recommended Next Design Phase

Proceed only after human approval to **Phase 11.7 — Runtime Binding, Activation,
Continuity, and Rollback Design**. That phase should define the first complete
binding transition, active-work policy, lifecycle coordination, post-activation
evidence matrix, SessionBinding behavior, commit conditions, and verified
rollback while preserving the dry-run and adapter boundaries established here.
