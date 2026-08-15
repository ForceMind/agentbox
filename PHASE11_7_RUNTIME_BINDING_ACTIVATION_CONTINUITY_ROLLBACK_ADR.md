# AgentBox Phase 11.7 — Runtime Binding, Activation, Continuity, and Rollback Architecture Decision Record

Status: **Proposed — design only, awaiting human approval**
Scope: Transition from a validated Provider intent to a verified active Runtime Binding
Governance acceptance: The decision content is canonically registered as
P11-ADR-061 through P11-ADR-070 and **Accepted** in `docs/adr/README.md`.
The document-local `ADR-061` through `ADR-070` labels and the status above are
historical drafting metadata. Acceptance becomes repository-effective only
after the Phase 11.10 governance change is reviewed and merged into `main`.
Contextual alternatives and open questions remain historical; supplemental
P11-ADR-071 through P11-ADR-076 provide their governing resolution.
Architecture sources: `PHASE11_PROVIDER_MANAGER_PROPOSAL.md`,
`PHASE11_IMPLEMENTATION_PLAN.md`,
`PHASE11_1_PROVIDER_DOMAIN_MODEL_ADR.md`,
`PHASE11_2_RUNTIME_CAPABILITY_CONTRACT_ADR.md`,
`PHASE11_3_SECRET_BOUNDARY_ADR.md`,
`PHASE11_4_CONFIG_TRANSACTION_FRAMEWORK_ADR.md`,
`PHASE11_5_PROVIDER_VALIDATION_PIPELINE_ADR.md`, and
`PHASE11_6_CODEX_PROVIDER_ADAPTER_DRY_RUN_ADR.md`
Repository baseline: `ForceMind/agentbox` at
`1c2005de59b1c5063b260591206a8411c7e5b1a5`

This document defines the final Phase 11 architecture link between validated
Provider intent and Runtime execution state. It does not authorize code,
database migrations, Runtime/Codex/Claude changes, Provider activation,
configuration writes, lifecycle actions, credential or Secret access, a branch,
or a commit.

## 1. Problem Statement

### 1.1 Why Runtime Binding is required

A Provider identifies an AI backend. A Runtime Profile describes how one
Runtime installation is intended to use a particular Provider revision. Neither
object says that the Runtime is currently using that configuration.

A `RuntimeBinding` is required to represent the control-plane selection boundary:

- one exact Runtime installation;
- one exact Runtime Profile and Provider revision;
- one Credential/Secret-version reference where required;
- one activation transaction and evidence history;
- one current lifecycle state;
- one prior binding reference available for approved recovery.

The binding separates durable AgentBox intent from transient Runtime-specific
names. A current Codex provider-block name, model-provider field, process, thread,
or config fingerprint is evidence used by an adapter; none is the AgentBox
RuntimeBindingID.

### 1.2 Why activation is not a configuration update

A configuration file may be syntactically valid while the Provider is
unreachable, the credential is rejected, the model or wire protocol is
incompatible, Codex fails to start, Remote Control fails to recover, or a session
loses continuity. Conversely, the Runtime might apply and verify a candidate
before the control plane records the new binding.

Activation therefore coordinates:

- Provider/Credential/Profile/Binding revisions;
- fresh validation and Runtime capability evidence;
- a read-only Codex Adapter dry-run and approved impact plan;
- active-work/session admission protection;
- a protected config/lifecycle snapshot;
- atomic Runtime-owned application;
- an approved lifecycle transition, if required;
- Provider, Runtime, Remote, and continuity verification;
- control-plane binding commit or independently verified rollback.

No single file write or SQLite transaction can make all of that true.

### 1.3 Why continuity is first class

Provider changes can affect more than future endpoint selection. Depending on
Codex's current public behavior, they may affect a long-running process, Remote
pairing/connection, thread resume, context, tool behavior, streaming, discovery,
or authentication.

AgentBox must not label an old session with the new Provider merely because the
global configuration changed. Existing effective state is historical evidence,
not a property to rewrite. When continuity cannot be established through public
contracts, AgentBox must report `UNKNOWN`/`EXPERIMENTAL` and recommend a new
session rather than invent continuity.

### 1.4 Why rollback is first class

Post-application behavior cannot be fully predicted by pre-validation. The
activation plan must therefore prove before mutation that a complete protected
snapshot and compatible prior state exist. Failure after mutation triggers a
compensating recovery path.

Rollback is successful only when configuration, ownership/mode, Secret
reference, binding metadata, lifecycle, Runtime health, Remote state, and every
required recovery dimension are verified. Otherwise the outcome is
`NEEDS_ATTENTION`, not success.

### 1.5 Architectural ownership

```text
Control Plane (`agentbox`)
    owns: request, authorization, approval, plan, transaction orchestration,
          Runtime Binding state, user visibility, audit

Runtime (`agentbox-runtime`)
    owns: local lock/fence, protected snapshot/journal, deterministic candidate,
          config application, lifecycle coordination, Secret use, verification

Codex Runtime
    owns: execution, interpretation of public config, actual process/Remote/
          session behavior

Root Helper
    owns: existing fixed AgentBox lifecycle actions only
    receives: no Provider, Secret, Runtime Binding, config, or Codex action
```

## 2. Runtime Binding Model

### 2.1 Definition

A `RuntimeBinding` is the durable, non-secret AgentBox record of administrator
intent for one Runtime installation to use one Runtime Profile revision.

Conceptually it owns:

- opaque RuntimeBindingID and monotonic revision;
- RuntimeInstallationID;
- RuntimeProfileID/revision;
- ProviderID/revision;
- CredentialID/revision and opaque Secret-version reference metadata where
  required;
- adapter/public-contract and validation-policy versions;
- lifecycle state;
- activation transaction and plan/evidence digests;
- previous/superseded binding reference for bounded recovery;
- activation, verification, commit, supersession, and recovery timestamps;
- safe compatibility/continuity summary and sanitized finding codes.

It never contains Secret Material, ciphertext, key material, Authorization,
raw Runtime configuration, rendered TOML, child environment, private Codex
state, prompts, completions, or conversation content.

### 2.2 Relationship model

```text
Provider
    execution backend identity and non-secret metadata
        |
        v
Runtime Profile
    versioned typed mapping intent for one Runtime family/installation
        |
        v
Runtime Binding
    control-plane selection and activation/recovery history for one Runtime
        |
        v
Session Binding
    immutable effective-binding snapshot for a supported observed session
```

One Provider may have multiple Runtime Profiles. One Runtime Profile may be the
target of multiple historical Runtime Bindings. In v1, at most one Runtime
Binding may be committed `ACTIVE` for one Runtime installation.

“Active Provider” is a derived UI view of the one active Runtime Binding. A
Provider does not own a global active boolean.

### 2.3 Binding identity versus Runtime evidence

Control-plane binding identity is stable product identity. Runtime config
fingerprints, managed-scope IDs, Codex public identifiers, process state, and
minimal-request results are evidence that the selected intent became effective.
They do not replace RuntimeBindingID.

The control plane is authoritative for intended/committed binding state. Runtime
is authoritative for local config, process state, and execution evidence. A
conflict between them produces reconciliation or `NEEDS_ATTENTION`; neither side
silently overwrites the other's truth.

### 2.4 Binding lifecycle states

The proposed binding states are:

| State | Meaning |
|---|---|
| `UNMANAGED` | AgentBox has not assumed Provider-configuration ownership. This is the safe upgrade state for existing v0.3.0-rc.1 installations. |
| `PENDING` | A target binding exists but has not completed validation/planning/approval. |
| `ACTIVATING` | An approved activation transaction is in its critical section. No new binding is claimed active. |
| `COMMIT_PENDING` | Runtime application and required verification passed, but durable control-plane commit/final acknowledgement is incomplete. |
| `ACTIVE` | Required evidence passed and control-plane commit completed for this exact revision. |
| `ACTIVATION_FAILED` | Activation failed before commit; detailed transaction state determines whether no change or recovery occurred. |
| `ROLLBACK_PENDING` | A mutation occurred or may have occurred and compensation is required. |
| `ROLLING_BACK` | Runtime is restoring the prior protected state. |
| `ROLLBACK_VERIFIED` | The failed candidate was not committed and prior state was independently verified. This is transaction history, not a second active binding. |
| `SUPERSEDED` | A previously active binding was replaced by a later committed binding while retained as immutable history. |
| `NEEDS_ATTENTION` | Current effective state is inconsistent, unknown, or recovery could not be verified; mutation is blocked. |
| `UNKNOWN` | No sufficient current evidence establishes a safe binding state. |

The detailed Phase 11.4 transaction state remains authoritative for execution.
Binding state is a domain projection and must not collapse `FAILED_NO_CHANGE`,
`RECOVERED`, and `NEEDS_ATTENTION` into one generic failure.

### 2.5 Desired, transitioning, and effective state

During activation, AgentBox exposes separately:

- **previous committed binding** — the last control-plane state known to have
  completed its verification policy;
- **candidate binding** — the approved desired target;
- **transaction/effective observation** — what Runtime evidence currently shows;
- **committed active binding** — set only after the commit gate passes.

After local apply but before commit, AgentBox must show `ACTIVATING` or
`COMMIT_PENDING`, not pretend either old or new binding fully describes current
reality.

### 2.6 Historical state

Committed and superseded binding revisions are immutable historical records.
Rollback creates a new transaction and restoration event; it does not erase the
failed candidate or rewrite event history. Retention must keep enough metadata
to explain which binding, profile, Secret reference, plan, and evidence governed
each transition without retaining Secret Material.

### 2.7 Ownership rules

- Control Plane owns binding IDs, revisions, lifecycle projection, approval,
  transaction association, and audit.
- Runtime owns config/effective execution evidence and protected local recovery
  state.
- Session manager owns creation of SessionBinding only when public evidence can
  prove effective state.
- Provider metadata never owns a Runtime or Session Binding.
- Root Helper owns none of these records or actions.

## 3. Activation Lifecycle

### 3.1 Primary lifecycle

```text
REQUESTED
    -> VALIDATION_REQUIRED
    -> VALIDATED
    -> PLANNING
    -> PLANNED
    -> AWAITING_APPROVAL
    -> APPROVED
    -> ACTIVATING
    -> CANDIDATE_VERIFICATION_AUTHORIZED
    -> VERIFYING
    -> COMMIT_PENDING
    -> ACTIVE
```

- **REQUESTED** — authenticated intent identifies exact target revisions; no
  mutation.
- **VALIDATION_REQUIRED** — the required Phase 11.5 evidence policy is resolved.
- **VALIDATED** — a fresh evidence bundle makes the exact scope eligible for
  planning; it does not authorize activation.
- **PLANNING** — the Phase 11.6 Adapter performs a read-only dry-run.
- **PLANNED** — an immutable, expiring plan/digest exists with impact and
  rollback prerequisites.
- **AWAITING_APPROVAL** — the safe plan is visible to the administrator.
- **APPROVED** — recent authentication/confirmation is bound to that exact plan
  and expiry.
- **ACTIVATING** — Phase 11.4 has revalidated, fenced new work, created/verified
  a snapshot, and begun local application/lifecycle work.
- **CANDIDATE_VERIFICATION_AUTHORIZED** — transaction-local authority admits
  only the owning activation's internal Codex verifier. The Runtime Binding is
  still pending, ordinary sessions remain fenced, and no Session Binding is
  created.
- **VERIFYING** — candidate is applied but required evidence is incomplete.
- **COMMIT_PENDING** — Runtime evidence passed; control-plane binding commit and
  Runtime journal acknowledgement are being finalized.
- **ACTIVE** — the unique active-binding commit is durable and acknowledged.

### 3.2 No-change and cancellation outcomes

- A request cancelled before mutation becomes `CANCELLED` and no binding
  changes.
- A stale validation/plan/approval returns to validation/planning; it is not
  patched silently.
- A semantic `NO_CHANGE` dry-run may avoid a write, but activation still needs
  evidence that the desired binding is actually effective before it can be
  committed.
- Failure before mutation becomes `FAILED_NO_CHANGE` only after the original
  config/binding/lifecycle state is verified unchanged.

### 3.3 Failure and recovery lifecycle

```text
ACTIVATING or VERIFYING
    -> FAILED
    -> ROLLBACK_REQUIRED
    -> ROLLING_BACK
    -> ROLLBACK_VERIFYING
    -> RECOVERED

uncertain outcome
    -> INTERRUPTED
    -> RECONCILING
    -> ACTIVE | FAILED_NO_CHANGE | RECOVERED | NEEDS_ATTENTION
```

`RECOVERED` means the candidate did not become active and the prior state is
fully verified. It does not mean the candidate activation succeeded. The binding
history records the failed attempt and verified restoration.

### 3.4 Approval challenge

The approval/confirmation should bind:

- actor/session and recent-auth state;
- candidate RuntimeBindingID/revision;
- Provider, Credential/Secret reference, Runtime Profile, Runtime installation,
  adapter, and public-contract revisions;
- validation-evidence and dry-run plan digests/expiry;
- destination/data-boundary, model, protocol, and cost class;
- semantic config-change summary;
- restart/reauthentication/Remote/session impact;
- active-work/quiescence finding;
- rollback snapshot/readiness policy.

Approval contains no Secret, raw config, arbitrary metadata, path, command, or
Provider response. Expired or changed input invalidates it.

### 3.5 Activation cannot self-escalate

An activation plan may execute only the lifecycle effect explicitly classified
and approved. If Runtime discovers that a restart, reauthentication, new session,
or broader change is required than the plan stated, it aborts or rolls back. It
does not widen its action dynamically.

## 4. Activation Transaction Flow

### 4.1 End-to-end flow

```text
Phase 11.1 Provider/Profile/Binding intent
    -> Phase 11.2 fresh Runtime capability evidence
    -> Phase 11.3 safe Credential/Secret-reference eligibility
    -> Phase 11.5 Provider Validation Evidence Bundle
    -> Phase 11.6 Codex Adapter Dry-run
    -> approval bound to plan digest
    -> Phase 11.4 Configuration Transaction
    -> Runtime Adapter Apply and lifecycle coordination
    -> layered post-activation Verification
    -> Runtime Binding Commit
       or verified Rollback / NEEDS_ATTENTION
```

### 4.2 Validate

The control plane verifies exact Provider, Credential, Secret-version reference,
Runtime Profile, candidate Binding, Runtime installation, capability, adapter,
and policy revisions. Phase 11.5 provides a fresh detailed matrix; lower-layer
success cannot fill untested Runtime/Remote/continuity dimensions.

No Secret is read by the control plane. No Runtime state is changed.

### 4.3 Plan

Phase 11.6 produces a read-only semantic dry-run bound to the current config
fingerprint, managed scope, active-work/session findings, public-contract
profile, expected lifecycle effect, required post-validation, rollback readiness,
and expiry.

The plan contains safe semantic changes and digests, not raw current/candidate
TOML or Secret values.

### 4.4 Approve

The administrator sees:

- current committed and candidate binding identities/revisions;
- destination and data-boundary class;
- model/protocol and compatibility matrix;
- credential configured/eligible state without value;
- config fields affected by name/change class only;
- whether existing sessions are unchanged, new-session-only, blocked, or
  unknown;
- required restart, Remote recovery, reauthentication, or quiescence;
- rollback prerequisites and unresolved risks.

Recent authentication and an exact confirmation are required for activation.
The exact approval policy remains open but cannot be bypassed by a durable Job
retry.

### 4.5 Revalidate and fence

Immediately before mutation, the transaction:

1. acquires the control-plane per-Runtime activation lock;
2. obtains the Runtime-local transaction lock;
3. establishes a Runtime activation/admission fence preventing new
   ordinary AgentBox-managed work from starting during the critical section;
4. refreshes active-writer/session/lifecycle evidence;
5. revalidates all object revisions, evidence, plan digest, config fingerprint,
   Credential lifecycle, and Secret-version reference;
6. reconstructs the candidate and checks its private digest;
7. verifies snapshot/rollback readiness.

If unmanaged or unobservable work can still race the change, activation blocks
unless a separately approved maintenance policy establishes safety. The fence
does not stop or manipulate existing sessions.

The transaction-owned session admission fence remains held through candidate
verification. It admits only the exact typed internal verifier launched by the
same transaction; that process is not a user session. A fence owned by another
transaction or representing external modification, lease loss, rollback,
reconciliation, revocation, key/store inconsistency, contradictory state, or
`NEEDS_ATTENTION` denies every credential resolution.

### 4.6 Snapshot

Runtime creates and verifies the complete protected Phase 11.4 snapshot before
mutation. It covers original content/nonexistence, owner/group/mode and required
metadata, prior binding/profile/Secret reference, lifecycle/Remote expectations,
adapter/schema version, and plan digest.

Separately managed Secret Material is excluded. If existing config contains
unmanaged sensitive bytes, the exact opaque snapshot is encrypted and remains
Runtime-owned as defined by Phase 11.4.

### 4.7 Apply

Runtime reconstructs the deterministic semantic candidate and uses the fixed
Codex Adapter action to stage, validate, atomically publish, synchronize, reread,
and verify it. The control plane does not supply config bytes.

If required by the approved public contract, Runtime coordinates the exact
existing non-root Codex lifecycle operation. It does not use root Helper, a
parallel daemon manager, arbitrary systemd, shell, PID, or signal. Pairing is
never invoked automatically.

### 4.8 Verify

Runtime gathers the exact post-activation evidence matrix in section 7. The
control plane evaluates required dimensions under the plan's versioned policy.
No single endpoint, process, or health result can substitute for the matrix.

Before Codex candidate verification, Runtime enters the exact transaction-local
state `CANDIDATE_VERIFICATION_AUTHORIZED`. It durably binds transaction,
Runtime/Binding/Profile/Provider/Credential/Secret revisions, approved plan and
profile postimage digests, public-contract evidence, lease epoch/expiry, and
lock/fence ownership. The candidate Binding remains pending and cannot be
reported active or verified.

The broker window expires within 60 seconds or immediately on any checkpoint,
verification, approval/evidence, lease, lock/fence, interruption, rollback,
recovery, or `NEEDS_ATTENTION` terminal condition. It allows at most two
durably counted broker invocations/resolutions: the initial authentication and
one retry. A third invocation fails verification. Direct live Provider
validation is separately typed and its Secret-use authority cannot be reused.

### 4.9 Commit

Only after all mandatory evidence passes does the control plane:

- close `CANDIDATE_VERIFICATION_AUTHORIZED` and deny further candidate Secret
  resolution;
- reverify all durable evidence, revisions, postimage digest, and journal
  agreement;
- atomically commit the candidate Runtime Binding as the one `ACTIVE` binding;
- mark the previous binding `SUPERSEDED` while preserving history/rollback
  references;
- record verification evidence and audit correlation;
- acknowledge commit to the Runtime journal;
- release the admission fence and locks;
- permit new AgentBox-managed sessions to receive the new SessionBinding when
  public evidence proves effective state.

If SQLite commit succeeds but Runtime acknowledgement is lost, or Runtime
verification passes before SQLite commit, the transaction remains
`COMMIT_PENDING` and must reconcile before new activation.

### 4.10 Rollback

Any post-mutation failure or uncertainty follows section 8. There is no automatic
selection of another Provider. The only automatic compensation target is the
exact verified pre-transaction state.

## 5. Session Continuity Model

### 5.1 Separate continuity dimensions

Continuity is not one boolean. Record independently:

- existing process/Remote connection state;
- thread/session reference resume;
- actual prior-context use;
- tool behavior;
- streaming behavior;
- Responses/wire behavior;
- thread discovery;
- new-session binding behavior;
- pairing and authentication observations.

Each dimension remains `PASS`, `FAIL`, `UNSUPPORTED`, `EXPERIMENTAL`, `UNKNOWN`,
or `NOT_TESTED`. `Remote connected` does not prove context continuity.

### 5.2 New sessions

After an `ACTIVE` binding commit, a new AgentBox-managed session may receive a
new immutable SessionBinding only when public Runtime evidence proves that the
new binding was effective for that session. The SessionBinding captures the
exact Runtime Binding/Profile/Provider revisions and evidence class at start.

If effective state cannot be proven, session creation is blocked or marked
`continuity_unknown` according to approved policy; it is not falsely attributed.

### 5.3 Existing active sessions

Existing sessions keep their previous immutable SessionBinding or
`legacy_unbound` state. Activation does not change their historical meaning.

The initial safety preference is to avoid activation while any existing active
session or writer may be affected unless the public contract proves the change
is new-session-only. If state is unobservable, it is treated as active/unsafe
for mutation rather than idle.

### 5.4 Historical sessions

Historical/retired sessions remain associated with the binding evidence known
when they ran. Superseding a Runtime Binding does not relabel them. Provider or
Credential deletion/retirement must respect historical and audit references
without retaining Secret Material.

### 5.5 Remote Control

Remote Control remains an independent subsystem:

- pairing is not repeated, reset, or deleted by activation;
- Codex login and Provider authentication remain separate;
- Remote start/stop uses only existing reviewed lifecycle actions when explicitly
  present in the approved plan;
- a Provider test does not imply Remote recovery;
- inability to observe Remote state remains `UNKNOWN`.

### 5.6 Continuity policy outcome

The plan should report one of:

- `UNCHANGED_PROVEN`;
- `NEW_SESSIONS_ONLY`;
- `QUIESCENCE_REQUIRED`;
- `RESTART_AND_REMOTE_RECOVERY_REQUIRED`;
- `NEW_SESSION_REQUIRED`;
- `CONTINUITY_EXPERIMENTAL`;
- `CONTINUITY_UNKNOWN_BLOCKING`;
- `UNSUPPORTED`.

These results govern whether approval is possible; they never perform the
lifecycle action themselves.

## 6. Existing Session Policy

### 6.1 Initial v1 recommendation

V1 should use this conservative policy:

1. Never implicitly migrate, rebind, relabel, resume, restart, stop, or delete
   an existing session.
2. Prefer Provider activation for future new sessions only when the public Codex
   contract proves that scope.
3. If activation requires a Runtime/Remote restart, require no active or unknown
   affected session/writer plus an explicit maintenance-impact confirmation.
4. If existing-session impact cannot be proven, block activation and recommend
   ending/quiescing work followed by a new session.
5. Leave pre-Phase-11 sessions `legacy_unbound` unless supported public evidence
   proves otherwise.
6. Never inspect private Codex/thread files or tmux pane output to make the
   policy appear satisfied.

### 6.2 Rebinding

Runtime Binding activation changes the current Runtime selection, not an
existing SessionBinding. An existing session is never automatically rebound.

An explicit future rebind would be a separate user operation and transaction
with its own public contract, context/resume/discovery evidence, cost/data
impact, confirmation, and rollback semantics. It is out of scope for v1.

### 6.3 Migration

Session migration is `UNSUPPORTED` in the initial design. AgentBox does not copy
conversation data, rewrite private thread metadata, change a Provider label, or
resume an old thread under a new Provider merely to simulate migration.

### 6.4 Session creation race

The activation session-admission fence prevents new ordinary AgentBox-managed
sessions/turns from starting between the final active-work check and binding
commit/rollback. The sole exception is the owning transaction's internal Codex
candidate verifier; it is not a user session and creates no SessionBinding. At
release, queued work rechecks the committed Binding revision and creates its
SessionBinding from fresh public evidence.

Unmanaged or independently started Codex work is outside AgentBox's admission
control. If it cannot be safely observed, the Runtime is not eligible for
activation under v1 policy.

## 7. Runtime Verification

### 7.1 Verification matrix

Post-application verification preserves independent evidence:

1. **Configuration consistency** — target type, owner/group/mode, fingerprint,
   parse/schema validity, managed-scope semantic digest, and preservation
   invariants match the candidate.
2. **Secret-reference consistency** — expected Credential/Secret-version
   reference is selected and eligible without exposing the value.
3. **Lifecycle consistency** — only the approved lifecycle transition occurred;
   expected process/socket/service state is observed.
4. **Runtime capability refresh** — Codex executable/adapter/public-contract and
   required capabilities remain valid after the change.
5. **Health/readiness** — Runtime service and bounded AgentBox readiness evidence
   are healthy.
6. **Endpoint/network/TLS** — destination and transport observations meet the
   approved policy.
7. **Authentication** — exact credential version is accepted or otherwise meets
   the Provider type's policy.
8. **Model/wire protocol** — model availability and required request/streaming/
   event/error semantics pass.
9. **Provider API** — bounded minimal direct Provider request passes when
   separately approved.
10. **Codex Runtime request** — bounded minimal request through Codex proves the
    selected Runtime path can use the intended Provider.
11. **Remote recovery** — required Remote connection/state recovers or remains
    compatible through public evidence.
12. **Session continuity** — resume, context, tools, streaming, Responses, and
    discovery are tested only where the plan requires and public evidence allows.
13. **Binding confirmation** — candidate config/effective evidence and exact
    Runtime/Profile/Provider revisions agree with the transaction plan.

### 7.2 Required versus advisory evidence

The plan contains a versioned policy declaring each dimension required,
advisory, unsupported, or intentionally not tested. A required `FAIL`,
`UNKNOWN`, `EXPIRED`, `UNSUPPORTED`, or `NOT_TESTED` blocks commit unless a
separately approved policy explicitly defines a narrower activation class.

`Provider API PASS` cannot promote Codex Runtime, Remote, or continuity. Health
alone cannot prove Provider binding.

### 7.3 Evidence freshness and provenance

Every observation records source, adapter/validator version, time/expiry,
Runtime executable/config fingerprint, transaction ID, and safe outcome. Fixture
or simulated evidence cannot satisfy a real activation policy. Pre-validation
may be reused only when the plan permits and the dimension is unaffected by
apply; configuration, Runtime, Remote, and effective-binding evidence must be
recollected after application.

### 7.4 Binding commit gate

The binding commit gate requires:

- all required post-validation dimensions accepted;
- no stale revision/evidence, unexpected lifecycle effect, or active-work race;
- candidate semantic/fingerprint consistency;
- Runtime and control-plane transaction/journal agreement;
- unique-active-binding constraint ready to commit;
- rollback snapshot remains valid until commit acknowledgement.

Only then is `ACTIVE` durable. The snapshot is not immediately destroyed; it is
retained according to the approved rollback policy.

### 7.5 No-op activation

A semantic no-op still requires effective-binding verification. AgentBox cannot
create an `ACTIVE` Runtime Binding solely because desired config equals observed
config. If public Runtime evidence cannot prove that requests use the intended
Provider/Profile revision, the outcome remains `UNKNOWN` or unmanaged.

## 8. Rollback Model

### 8.1 Automatic rollback triggers

After a verified snapshot and any possible mutation, automatic rollback is
requested when:

- candidate application, fsync, reread, or schema verification fails;
- the approved lifecycle transition fails or exceeds its bounded state;
- a required Provider, Runtime, Remote, or continuity check fails/expires;
- unexpected restart/reauthentication/session impact appears;
- binding commit cannot be completed consistently;
- Secret-reference/Credential state changes before commit;
- crash reconciliation proves the candidate is applied but not safely
  committable.

Before mutation, failures end as `FAILED_NO_CHANGE`; no rollback theater is
performed.

### 8.2 Rollback target

The only automatic target is the exact pre-activation state captured by the
protected snapshot and previous binding metadata. AgentBox does not choose a
different Provider, newest successful Provider, Official OpenAI, or an arbitrary
historical version.

Rollback attempts to restore:

- original config content or original nonexistence;
- owner/group/mode and required trusted metadata;
- prior managed scope and source fingerprint relationship;
- prior Runtime Profile/Binding and opaque Secret-version reference;
- prior approved lifecycle/Remote state;
- control-plane binding projection and transaction agreement.

External Provider state, revoked API keys, quotas, billing, model availability,
prompts, conversations, Projects, and unrelated files cannot be restored by this
transaction.

### 8.3 Rollback process

```text
ROLLBACK_REQUIRED
    -> validate snapshot integrity and target identity
    -> recheck external-edit conflict and prior Secret-reference eligibility
    -> restore exact config/nonexistence atomically
    -> restore approved lifecycle state
    -> verify config/permissions/fingerprint
    -> refresh Runtime capabilities and health
    -> verify prior Provider/Runtime/Remote expectations
    -> reconcile binding/journal state
    -> RECOVERED / ROLLBACK_VERIFIED
       or NEEDS_ATTENTION
```

If a concurrent external edit would be overwritten, rollback fails closed into
`NEEDS_ATTENTION`; it does not destroy the user change.

### 8.4 Rollback verification

`Rollback verified` requires all policy-required checks:

- snapshot integrity and exact transaction/plan/target binding;
- restored content/nonexistence and semantic state;
- restored file type, owner/group/mode, trusted parent, and required metadata;
- prior Secret reference identity/lifecycle remains eligible;
- expected process/socket/lifecycle state;
- Runtime health/readiness and config/public-contract compatibility;
- prior Provider/Runtime request behavior where safely required;
- Remote recovery and applicable session expectations;
- previous active-binding or unmanaged state matches control-plane projection;
- Runtime journal and control-plane transaction agree.

Restoring bytes, switching an application symlink, or restarting successfully is
not sufficient.

### 8.5 Rollback failure

Missing/corrupt snapshot, revoked prior Credential, unavailable prior adapter/
Runtime contract, concurrent edit, failed publication, failed lifecycle recovery,
failed health/Remote check, or DB/journal disagreement produces
`NEEDS_ATTENTION`.

In that state:

- further Provider activation and automatic rollback are blocked;
- existing work is not killed or relabeled;
- evidence/snapshots/journals are retained;
- read-only sanitized diagnosis remains available;
- no blind retry, auto-fallback, or root escalation occurs;
- a separately approved recovery procedure is required.

### 8.6 Manual rollback

Manual rollback is a new approved transaction targeting one eligible retained
snapshot, not a direct pointer switch. It re-plans current state, detects
conflicts, displays impact, creates a new recovery point when safe, and verifies
the restored result. Users cannot supply snapshot paths or bytes.

## 9. Crash Recovery

### 9.1 Durable recovery sources

Recovery uses two coordinated but separated stores:

- Control Plane: non-secret transaction/Job/binding state, plan/evidence digests,
  revisions, approval/audit correlation;
- Runtime: protected local transaction journal, candidate/snapshot fingerprints,
  lifecycle checkpoints, and opaque snapshot.

Neither side opens the other's store. Reconciliation uses the typed Runtime
contract and safe digests/states.

### 9.2 Recovery on service start or machine reboot

Before accepting a new activation, startup recovery enumerates non-terminal
transactions and establishes a mutation gate for each affected Runtime. It then
compares:

- transaction ID/state revision and plan digest;
- target/candidate/snapshot fingerprints and integrity;
- Runtime Binding previous/candidate/committed revisions;
- lifecycle/process/socket observations;
- active-work/admission-fence state;
- capability/adapter/public-contract evidence;
- control-plane and Runtime journal checkpoints.

The system classifies the state before action. A reboot does not imply rollback,
commit, or failure.

### 9.3 Crash scenarios

| Crash point | Recovery behavior |
|---|---|
| Before snapshot | Verify original state and finish `FAILED_NO_CHANGE` or continue only with fresh approval/plan according to policy. |
| Snapshot durable, before apply | Verify no target mutation; normally cancel/fail without rollback, retaining safe evidence. |
| During staged write, before atomic publish | Remove only exact transaction-owned temporary state after identity proof; verify original target. |
| After publish, before journal checkpoint | Compare target candidate/snapshot digests; enter `RECONCILING`, never reapply blindly. |
| After apply, before lifecycle transition | Decide verified rollback or resume only if the exact next step is idempotent and policy-approved. |
| During restart/Remote recovery | Observe actual process/socket/Remote state before any lifecycle action; do not issue duplicate stop/start blindly. |
| During `CANDIDATE_VERIFICATION_AUTHORIZED` or Codex candidate verification | Candidate authorization becomes unusable and is never reconstructed/reopened. If broker count or the last Secret-use outcome is uncertain, issue no further candidate Secret; perform verified rollback or enter `NEEDS_ATTENTION`. |
| During other post-validation | Preserve completed dimension evidence; repeat only explicitly safe tests, never an uncertain paid request. |
| Runtime verified, before DB commit | Remain `COMMIT_PENDING`; finish commit only if every revision/evidence still matches, otherwise roll back or require attention. |
| DB committed, before Runtime acknowledgement | Verify target/journal/evidence before acknowledging; do not create a second active binding. |
| During rollback | Determine which prior bytes/lifecycle steps are effective, then continue verification or enter `NEEDS_ATTENTION`. |

### 9.4 Recovery ownership

Control Plane orchestrates recovery policy and binding decisions. Runtime owns
local evidence, restoration, and lifecycle action. Neither may unilaterally
declare success when the other side is unavailable or contradictory.

Automatic recovery is limited to transitions proven idempotent under the exact
journal state. Otherwise human-approved recovery is required.

### 9.5 Unknown state

Unknown state is a safety result, not an error to hide. `NEEDS_ATTENTION` blocks
new mutations for that Runtime while allowing read-only status/diagnosis. The UI
must distinguish:

- activation failed with no change;
- rollback verified;
- rollback attempted but verification failed;
- activation possibly applied but commit unknown;
- external modification conflict;
- Runtime unavailable.

## 10. Concurrency Model

### 10.1 One activation per Runtime

At most one mutating Provider/Runtime transaction may target a Runtime
installation at a time. A second request is rejected or queued as a new intent;
it cannot share, replace, or amend the active transaction.

### 10.2 Lock layers

Activation uses:

1. a control-plane per-Runtime resource lock/lease protecting transaction and
   unique-active-binding intent;
2. a Runtime-local transaction lock protecting config, lifecycle, Secret use,
   and verification;
3. a session admission fence preventing new ordinary AgentBox-managed
   sessions/turns/jobs from entering the affected Runtime during the critical
   section, while admitting only the owning transaction's typed internal
   candidate verifier;
4. config identity/fingerprint checks detecting external writers.

Exact lock primitives and leases remain open. Lock ownership is bound to
transaction identity and cannot be released by arbitrary callers.

### 10.3 Lock ordering

To avoid deadlock, resource acquisition follows a fixed order, conceptually:

```text
Runtime activation resource
    -> candidate Binding revision
    -> Credential/Secret-version use lease
    -> Runtime-local transaction lock
    -> session admission fence
```

Locks do not grant authorization. Failure to acquire all resources before
expiry causes no mutation.

### 10.4 Concurrent domain changes

Provider/Profile edits, Credential rotation/revocation, Runtime/adapter upgrade,
validation refresh, config edits, lifecycle changes, or active-session changes
invalidate the plan or block commit according to expected revisions.

Credential rotation cannot swap the Secret version inside an approved plan.
Provider edit cannot alter destination/model after approval. A second binding
cannot become active through last-write-wins behavior.

### 10.5 External Runtime/config changes

AgentBox locks coordinate AgentBox operations only. Manual or unmanaged Runtime
changes are detected by target identity/fingerprint, process/lifecycle, and
capability evidence.

- Before mutation: abort as `FAILED_NO_CHANGE`/stale plan.
- After mutation but before rollback: do not overwrite the external change;
  enter reconciliation/`NEEDS_ATTENTION`.
- After commit: invalidate effective evidence and require revalidation; do not
  silently rewrite configuration to enforce database intent.

### 10.6 Multiple sessions and work admission

The fence affects only AgentBox-managed admission and does not manipulate
existing sessions. Queued work resumes only after reading the final committed
binding revision. If unmanaged work cannot be detected or fenced and the change
could affect it, v1 activation is blocked.

## 11. Audit Model

### 11.1 Activation events

The existing append-only audit system should record safe events such as:

- `runtime_binding_created`;
- `provider_activation_requested`;
- `provider_activation_validated`;
- `provider_activation_planned`;
- `provider_activation_approval_requested`;
- `provider_activation_approved` or `approval_expired`;
- `provider_activation_started`;
- `provider_activation_fence_acquired`;
- `provider_activation_snapshot_created`;
- `provider_activation_applied`;
- `provider_activation_verification_started`;
- per-dimension sanitized verification result;
- `provider_activation_commit_pending`;
- `provider_activation_committed`;
- `provider_activation_failed_no_change`;
- `provider_rollback_requested`, `started`, `verified`, or `failed`;
- `provider_activation_reconciliation_started`/`completed`;
- `runtime_binding_needs_attention`;
- `runtime_binding_superseded`.

### 11.2 Safe audit fields

Events may include:

- actor and authenticated session reference;
- request/Job/transaction/plan/validation IDs;
- Provider/Credential/Profile/Binding/Runtime opaque IDs and revisions;
- adapter/public-contract/policy versions;
- semantic change field names/classes;
- lifecycle/session impact class;
- evidence dimension/outcome and sanitized finding code;
- previous/candidate/final binding state;
- timestamps, expiry, attempt, and recovery classification.

### 11.3 Prohibited audit/log content

Audit, Jobs, logs, reports, metrics, diagnostics, and ordinary API/UI output
never contain:

- Secret Material, ciphertext, keys, tokens, hints, Authorization, cookies, or
  credential paths;
- raw current/candidate/restored config or snapshots;
- environment values, command lines, Provider headers/bodies, prompts,
  completions, tools, or streamed content;
- private Codex session/thread/JSONL/rollout data or tmux pane output;
- DNS/certificate/internal-network dumps;
- arbitrary user/provider error text or unbounded metadata.

Audit records a rollback snapshot ID only as an opaque reference and never makes
it retrievable through ordinary API/UI.

### 11.4 Audit truthfulness

Audit event names must distinguish `apply completed`, `verification completed`,
`binding committed`, `rollback attempted`, and `rollback verified`. A process
exit code, file rename, or service start cannot produce a misleading
`activation succeeded` event.

## 12. Security Model

### 12.1 Unauthorized activation

Controls include authenticated administrator intent, operation authorization,
recent authentication, CSRF/Origin/Host policy, exact revision-bound plans,
one-time confirmation challenge, expiry, per-Runtime lock, immutable evidence
digests, and append-only audit.

Durable Job retry does not bypass approval or substitute a new plan. Runtime
does not self-authorize based on local validation.

### 12.2 Runtime takeover prevention

The mutation protocol has fixed adapter actions and exact schemas. It cannot
express shell, executable, argv, environment, cwd, raw config, path, PID,
signal, tmux input, package, chmod/chown, UID/GID, or arbitrary systemd unit.
Unknown fields/actions fail closed under Runtime UDS peer credentials, size/
time bounds, and versioning.

Control Plane cannot read Runtime HOME or directly operate processes. Runtime
cannot open AgentBox SQLite or change binding/approval state.

### 12.3 Secret exposure prevention

Control Plane carries only Credential identity, opaque Secret-version reference,
and safe lifecycle/evidence. Runtime resolves one Secret version for one
approved operation and supplies only the minimal supported child delivery.

The approved Codex operations are exact committed active use and the bounded
transaction-local candidate-verification mode. Candidate authority is not
Binding activation, does not bypass ordinary-session fencing, and is never
reopened after crash or uncertain Secret use.

Secrets never enter config values, argv, URLs, long-lived service environments,
SQLite, plans, evidence, snapshots metadata, Audit, logs, reports, or root
Helper. Existing Codex/Claude/GitHub credentials are not copied or altered.

### 12.4 Privilege escalation prevention

Activation runs as non-root `agentbox-runtime` and uses existing non-root Codex
lifecycle management. It does not use sudo, setuid, root Helper, arbitrary
systemctl, package installation, or filesystem ownership primitives from a
caller.

Any future genuinely required root action needs a separate accepted ADR and a
fixed-action Helper review; this ADR authorizes none.

### 12.5 Malicious Provider and data-boundary risk

Only Phase 11.5 validated typed Provider metadata enters the plan. Endpoint,
protocol, model, destination, redirect/TLS policy, cost, and data boundary are
shown at approval and bound by digest. Runtime cannot substitute a destination
or forward credentials across authority.

There is no automatic failover because it could silently change privacy, model,
cost, geography, or capability.

### 12.6 Configuration and TOCTOU safety

Fixed target resolution, trusted-parent/no-follow checks, typed semantic mapping,
lossless preservation, expected fingerprint, deterministic candidate digest,
same-directory atomic publication, fsync, reread, per-Runtime locks, active-work
fence, protected snapshot, and independent rollback verification mitigate
replacement races and partial state.

External edits are conflicts, not permission to overwrite.

### 12.7 Session safety

Immutable SessionBindings, legacy-unbound status, admission fencing, no private
state inspection, new-session-first policy, and independent Remote/resume/context/
discovery evidence prevent retroactive attribution and silent migration.

### 12.8 Residual risks

- Root or compromised `agentbox-runtime` can alter local execution evidence and
  inspect live Secret use within the existing host trust model.
- Public Codex behavior can change after validation.
- Machine power loss and filesystem durability can leave an uncertain state.
- External Provider availability, credential revocation, billing, and model
  changes cannot be rolled back locally.
- Unmanaged Codex processes/sessions may be unobservable.
- A same-host multi-resource workflow cannot provide distributed ACID.
- A prior Secret may become unusable during the rollback window.
- Some continuity dimensions may remain impossible to prove.

The safe response is explicit incompatibility/unknown/recovery state, not wider
privileges or invented guarantees.

## 13. ADR Decisions

### ADR-061 — Runtime Binding is separate from Provider identity

**Status:** Proposed

**Decision:** RuntimeBindingID records the explicit versioned selection for one
Runtime installation. It is not ProviderID, RuntimeProfileID, a Codex config
block, process, session, or global active flag.

**Consequence:** Provider metadata and binding history can evolve independently,
and active state is scoped to one Runtime.

### ADR-062 — Activation requires the transaction lifecycle

**Status:** Proposed

**Decision:** Provider activation must follow validate, dry-run plan, approval,
transaction preflight, protected snapshot, Runtime-owned apply, layered verify,
and commit or verified rollback. No direct config or binding update activates a
Provider.

**Consequence:** Partial and uncertain state remains visible and recoverable
instead of being hidden behind a database flag.

### ADR-063 — Existing sessions are not implicitly migrated

**Status:** Proposed

**Decision:** Activation never rewrites, rebinds, relabels, resumes, restarts, or
stops an existing session. Initial v1 behavior is new-session-first and blocks
when active/unknown affected work cannot be made safe.

**Consequence:** Existing SessionBindings and legacy state remain historically
truthful; future migration requires a separate public-contract ADR.

### ADR-064 — Rollback requires verification

**Status:** Proposed

**Decision:** Rollback success requires independent verification of exact config/
nonexistence, permissions/metadata, prior Secret reference, binding, lifecycle,
Runtime health, Remote state, and required continuity evidence.

**Consequence:** `Rollback attempted` or restored bytes cannot be reported as
`Rollback verified` when effective state remains uncertain.

### ADR-065 — Unknown Runtime state requires explicit recovery

**Status:** Proposed

**Decision:** Interrupted, contradictory, or unverifiable activation/rollback
state enters reconciliation and then `NEEDS_ATTENTION` when it cannot be proven.
Further mutation is blocked; no blind replay, commit, rollback loop, or fallback
is allowed.

**Consequence:** Recovery may require human action, but AgentBox does not corrupt
or disguise unknown Runtime state.

### ADR-066 — Only one Runtime Binding may be active per Runtime

**Status:** Proposed

**Decision:** The control plane enforces one committed active RuntimeBinding
revision per Runtime installation. Candidate and previous bindings remain
explicit during transition.

**Consequence:** Concurrent activation cannot use last-write-wins or produce two
claimed active Providers.

### ADR-067 — Active state commits only after layered verification

**Status:** Proposed

**Decision:** Runtime application is not activation. The candidate becomes
`ACTIVE` only after every mandatory configuration, lifecycle, Provider, Codex,
Remote, continuity, and binding-consistency dimension passes.

**Consequence:** Endpoint or health success cannot falsely establish an active
Runtime Binding.

### ADR-068 — Activation never performs automatic Provider fallback

**Status:** Proposed

**Decision:** Failure restores only the exact approved prior state when possible.
AgentBox never selects another Provider automatically.

**Consequence:** Privacy, destination, model, cost, and capability cannot change
without a new validated plan and approval.

### ADR-069 — Activation uses a per-Runtime lock and admission fence

**Status:** Proposed

**Decision:** One control-plane lock, one Runtime-local lock, and a bounded
AgentBox-managed work-admission fence protect the critical activation window.
External changes remain detectable conflicts.

**Consequence:** New managed sessions cannot race between active-work assessment
and binding commit, while existing sessions are not manipulated.

### ADR-070 — Pairing and Provider activation remain independent

**Status:** Proposed

**Decision:** Activation may use only an explicitly approved existing Remote
lifecycle transition. It never automatically pairs, logs in/out, resets Remote
credentials, or treats Remote connection as Provider authentication.

**Consequence:** The stable Codex Remote Control boundary remains decoupled from
Provider selection.

## 14. Open Questions

The following require product, security, or implementation approval before any
activation implementation:

1. **Approval model:** Which activation classes require recent authentication,
   exact typed confirmation, maintenance-window acknowledgement, or another
   approval step?
2. **Minimum compatibility gate:** Which Provider, Codex Runtime, Remote, resume,
   context, tool, streaming, Responses, and discovery dimensions are mandatory
   for each supported activation class?
3. **V1 activation scope:** Is v1 strictly new-session-only, or may an idle
   Runtime-wide restart be permitted after explicit confirmation?
4. **Existing-session policy:** What public evidence is sufficient to prove a
   config change cannot affect an existing session?
5. **Future migration:** Is explicit session rebind/resume ever a product goal,
   and what public Codex contract would justify it?
6. **Active writer detection:** How does the then-current public Codex contract
   prove active, idle, duplicate writer, or unknown state without private files?
7. **Admission fence:** Which existing Runtime/session/Job entry points must
   participate, and how are queued requests surfaced without becoming a kill
   switch for unmanaged work?
8. **Lock strategy:** Which durable control-plane lease and Runtime-local lock
   primitives, ownership proofs, and stale-lock rules are qualified?
9. **Transaction timeout:** What are the maximum apply, lifecycle, validation,
   commit-pending, and rollback/reconciliation times?
10. **Crash recovery ownership:** Which reconciliations may run automatically at
    service start, and which always require administrator approval?
11. **Commit-pending policy:** When Runtime verification passed but DB commit did
    not, when should recovery commit versus restore?
12. **Rollback retention:** How long and how many snapshots/prior bindings/Secret
    versions remain eligible, under what disk quota and secure retirement rules?
13. **Revoked prior Credential:** Is activation blocked unless the prior
    Credential remains rollback-eligible, or may a nonfunctional config-only
    recovery ever be accepted?
14. **Manual rollback:** Which historical binding/snapshot may be targeted, and
    when must current state first be snapshotted?
15. **No-op activation:** What public Runtime request proves the desired binding
    is effective when no config bytes change?
16. **Lifecycle semantics:** Which exact public Codex changes require reload,
    Runtime restart, Remote stop/start, new session, or reauthentication?
17. **Remote recovery:** Which public evidence distinguishes connected, paired,
    authenticated, recoverable, and unknown states?
18. **Unmanaged processes:** Must any unobservable Codex process/session block
    all activation in v1?
19. **Paid post-validation:** Which minimal Runtime/Provider checks incur cost,
    how is the bound approved budget represented, and may an uncertain request
    be retried?
20. **Unique binding persistence:** What future database constraint/state model
    enforces one active binding without losing `COMMIT_PENDING` recovery facts?
21. **Runtime journal:** What fixed path, format, integrity, retention, and key
    domain are approved for activation and rollback evidence?
22. **Provider/Secret deletion:** Which binding/session/history/rollback
    references block deletion or revocation?
23. **External config change after commit:** Does AgentBox mark binding
    `UNKNOWN`, `NEEDS_ATTENTION`, or `UNMANAGED`, and what repair workflow is
    allowed?
24. **Claude boundary:** Claude remains Runtime-only; what future official
    contract would require a separate activation/continuity design?

## Recommended Next Design Phase

Proceed only after human approval to **Phase 11.8 — Provider API and CLI Surface
Design**. That phase should expose typed Provider, Credential-metadata, Runtime
Profile/Binding, validation, dry-run, activation, rollback, and recovery
workflows without placing Secret input in ordinary HTTP/CLI arguments or
expanding Runtime/root execution primitives.
