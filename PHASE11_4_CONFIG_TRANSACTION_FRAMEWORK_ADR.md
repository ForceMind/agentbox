# AgentBox Phase 11.4 — Configuration Transaction Framework Architecture Decision Record

Status: **Proposed — design only, awaiting human approval**
Scope: Future Provider activation and typed Runtime configuration mutation
Governance acceptance: The decision content is canonically registered as
P11-ADR-031 through P11-ADR-041 and **Accepted** in `docs/adr/README.md`.
The document-local `ADR-031` through `ADR-041` labels and the status above are
historical drafting metadata. Acceptance becomes repository-effective only
after the Phase 11.10 governance change is reviewed and merged into `main`.
Contextual alternatives and open questions remain historical; supplemental
P11-ADR-071 through P11-ADR-076 provide their governing resolution.
Architecture sources: `PHASE11_PROVIDER_MANAGER_PROPOSAL.md`,
`PHASE11_IMPLEMENTATION_PLAN.md`,
`PHASE11_1_PROVIDER_DOMAIN_MODEL_ADR.md`,
`PHASE11_2_RUNTIME_CAPABILITY_CONTRACT_ADR.md`, and
`PHASE11_3_SECRET_BOUNDARY_ADR.md`
Repository baseline: `ForceMind/agentbox` at
`1c2005de59b1c5063b260591206a8411c7e5b1a5`

This ADR defines a future transaction boundary. It does not authorize a
transaction engine, database migration, Runtime mutation, Codex or Claude
configuration change, Provider activation, Secret access, branch, or commit.

## 1. Problem Statement

### 1.1 Why Provider activation requires a transaction

Provider activation is not a single database update. It may coordinate:

- Provider, Credential, Runtime Profile, and Runtime Binding revisions;
- fresh Runtime capability and compatibility evidence;
- existing local Runtime configuration that AgentBox does not wholly own;
- a protected snapshot and recovery record;
- a schema-preserving local configuration change;
- an approved Runtime lifecycle action, when actually required;
- Provider, Runtime, Remote Control, and session-continuity verification;
- a final control-plane state and audit trail.

These steps span SQLite, a Runtime-owned filesystem, and local processes. No
single ACID transaction can cover all three. Treating activation as a simple
write would permit the control plane to claim one active Provider while the
Runtime uses another, or leave a valid file paired with a failed Runtime.

The framework is therefore a durable, recoverable state machine with staged
application, explicit verification, and compensating rollback. It must not be
described as distributed ACID.

### 1.2 Why direct file modification is unsafe

Directly rewriting a file such as `~/.codex/config.toml` is unsafe because it
can:

- discard settings that the user, Codex, or another tool owns;
- depend on an observed private format that changes without notice;
- follow a symlink or cross an ownership boundary;
- expose a credential in a file, diff, log, Job, or audit record;
- race with a manual edit or another AgentBox operation;
- leave truncated or partially synchronized bytes after failure or power loss;
- update configuration without updating Runtime Binding truth;
- disturb Remote Control, thread, conversation, streaming, or tool state;
- restart a Runtime unnecessarily and interrupt existing sessions.

The control plane must never become a generic Runtime filesystem editor. A
typed Runtime adapter must parse the current public configuration contract,
preserve unrelated settings, validate a generated candidate, and apply it at a
fixed adapter-owned target.

### 1.3 Why rollback is required

Pre-validation reduces risk but cannot prove that a new configuration will
work after application. Authentication can expire, a model can disappear, a
Runtime may reject otherwise valid configuration, Remote Control behavior may
change, and a process can fail during its lifecycle transition.

Rollback is therefore part of the transaction, not an optional cleanup step.
It must restore the prior configuration and relevant binding/lifecycle state,
then independently verify the restoration. If that verification fails, the
result is not `Recovered` or `Rollback verified`; it is `Needs Attention`, with
further mutations blocked until reconciliation.

### 1.4 Scope and non-goals

The framework may eventually support typed operations such as:

- Provider activation;
- a Runtime Profile or Runtime Binding change;
- an adapter-managed Codex configuration update;
- a narrowly defined Runtime lifecycle transition;
- verified rollback to a retained transaction snapshot.

It does not provide arbitrary file editing, arbitrary TOML keys, raw config
upload/download, arbitrary environment variables, shell/argv execution,
generic process control, generic systemd control, or Secret retrieval. It does
not modify Codex private databases, JSONL/rollout files, thread state, Claude
files, tmux internals, Project content, or Runtime credentials.

## 2. Transaction Model

### 2.1 Configuration Transaction

A `ConfigurationTransaction` is the durable coordination record for one
approved, typed mutation of one Runtime installation. It contains only safe
metadata:

- opaque transaction ID and correlation/request ID;
- actor, authorization decision, approval policy, and timestamps;
- immutable plan ID and plan digest;
- typed intent and adapter operation;
- target RuntimeInstallationID and expected Runtime identity;
- expected Provider, Credential, Runtime Profile, and Runtime Binding IDs and
  revisions, where applicable;
- expected capability-evidence revision and expiry;
- expected current configuration fingerprint, never raw configuration;
- sanitized proposed-change summary;
- lifecycle, Remote Control, and session-impact classification;
- validation requirements and sanitized results;
- opaque Runtime snapshot reference and protected journal reference;
- current transaction state and monotonic state revision;
- apply, verification, rollback, and recovery outcomes;
- sanitized failure code and audit correlation.

It never contains plaintext Secret Material, ciphertext, a master key, raw
configuration, an arbitrary path, a config diff containing values, command,
argv, environment, Provider response body, prompt, completion, or Runtime
credential.

### 2.2 Configuration Plan

A `ConfigurationPlan` is an immutable, non-secret description of what would be
changed and under which evidence. It is produced before any mutation and has a
bounded lifetime.

At minimum, the plan records:

- typed operation and target identifiers/revisions;
- adapter contract/schema version;
- source configuration fingerprint and managed scope;
- safe field-name-level change summary, with sensitive values omitted;
- capability and compatibility evidence revisions;
- whether restart, new session, or reauthentication may be required;
- expected effect on new requests and existing sessions;
- required validation matrix;
- snapshot scope and rollback readiness;
- incompatibility, uncertainty, and warning classifications;
- expiry and deterministic plan digest.

The plan is evidence and intent, not permission and not a success guarantee.

### 2.3 Runtime execution record

The Runtime maintains a protected local journal for exact execution and crash
recovery. It contains the minimum local facts needed to determine whether the
candidate was staged, applied, verified, or restored. It may reference an
opaque protected snapshot.

The control plane stores only non-secret transaction workflow metadata. The
Runtime does not open the control-plane database, and the control plane does
not read the Runtime journal, snapshot bytes, or local configuration. The
typed Runtime contract exchanges bounded states, digests, evidence, and safe
error codes.

### 2.4 Final states

Final state is explicit and evidence-backed:

- `COMMITTED`: required post-application checks passed and control-plane intent
  was committed;
- `FAILED_NO_CHANGE`: the operation failed before mutation and the expected
  original state is still verified;
- `RECOVERED`: mutation failed, rollback was performed, and rollback was
  independently verified;
- `NEEDS_ATTENTION`: current state is unknown, inconsistent, or rollback could
  not be fully verified;
- `CANCELLED`: cancellation occurred before mutation and no change is verified.

`FAILED`, `rollback attempted`, or a successful atomic rename alone must never
be presented as recovery or success.

## 3. Transaction Lifecycle

### 3.1 Primary path

```text
CREATED
    -> PLANNING
    -> PREPARED
    -> VALIDATED
    -> SNAPSHOT_CREATING
    -> SNAPSHOT_CREATED
    -> APPLYING
    -> APPLIED
    -> VERIFYING
    -> COMMIT_PENDING
    -> COMMITTED
```

- **CREATED** — control plane accepted a typed intent but performed no Runtime
  work.
- **PLANNING** — the Runtime adapter is gathering current, bounded evidence and
  preparing a safe change plan.
- **PREPARED** — an immutable, expiring plan and digest exist; no mutation has
  occurred.
- **VALIDATED** — required authorization, revision, capability, compatibility,
  dependency, and configuration preconditions still pass.
- **SNAPSHOT_CREATING** — the Runtime is constructing a protected recovery
  snapshot and journal checkpoint.
- **SNAPSHOT_CREATED** — the snapshot is complete, durable, and verified before
  mutation.
- **APPLYING** — the Runtime is staging and atomically publishing the candidate
  within the adapter-owned scope.
- **APPLIED** — local publication and immediate reread/format checks completed;
  semantic/runtime verification remains outstanding.
- **VERIFYING** — required health, capability, Provider, Runtime, Remote Control,
  and continuity checks are being evaluated independently.
- **COMMIT_PENDING** — Runtime application and required verification passed,
  but durable control-plane binding/state commit has not yet been acknowledged.
- **COMMITTED** — the control plane committed the new intent and the Runtime
  journal recorded final acknowledgement.

`COMMIT_PENDING` is essential: a process may die after the Runtime has changed
but before SQLite reflects it. Such a state must be reconciled, not silently
treated as either success or rollback.

### 3.2 Failure and recovery path

```text
failure before mutation -> FAILED_NO_CHANGE

failure after snapshot or mutation
    -> ROLLBACK_REQUIRED
    -> ROLLING_BACK
    -> ROLLBACK_VERIFYING
    -> RECOVERED

uncertain or unverifiable state
    -> INTERRUPTED
    -> RECONCILING
    -> one of COMMITTED / FAILED_NO_CHANGE / RECOVERED / NEEDS_ATTENTION
```

- A pre-mutation failure requires verification that no mutation occurred.
- Any failure after mutation normally requests rollback automatically, unless
  rollback itself would be less safe and policy requires intervention.
- An interrupted state is never blindly replayed. Reconciliation reads the
  durable Runtime journal, target fingerprint, snapshot identity, lifecycle
  evidence, and control-plane state before deciding a next transition.
- `NEEDS_ATTENTION` is terminal for automatic mutation. It preserves evidence
  and blocks another configuration transaction for that Runtime.

### 3.3 Transition rules

Every transition must be:

- authorized for the actor and operation;
- conditional on the expected prior state and state revision;
- durably checkpointed before the next irreversible step;
- idempotent or safely detectable on retry;
- correlated across the control plane and Runtime without sharing secrets;
- rejected when the plan is expired or its evidence/revisions changed.

A timeout indicates unknown outcome until reconciliation. It does not prove
that the Runtime did nothing.

## 4. Plan vs Execution Separation

### 4.1 Planning is read-only

Planning uses the Phase 11.2 observation contract plus adapter-local read-only
inspection. The control plane submits typed intent and identifiers; the Runtime
reads its own fixed configuration target and returns a sanitized plan summary,
digest, impact classifications, and validation requirements.

Planning must not:

- write a target, create a snapshot, restart a process, resolve plaintext
  Secret Material, or change a binding;
- return raw Runtime config or Secret-derived values;
- authorize later execution merely because the plan was generated.

### 4.2 Execution is explicit

Execution references the immutable plan ID/digest, target revisions, and the
required approval/confirmation proof. The Runtime recomputes or verifies all
security-critical preconditions before mutation.

It does not accept a caller-supplied file, path, raw configuration, environment,
command, executable, argv, PID, signal, or arbitrary adapter option.

### 4.3 Plan staleness

A plan becomes stale when any relevant condition changes, including:

- Provider, Credential, Runtime Profile, or Runtime Binding revision;
- selected Secret version reference or lifecycle state;
- Runtime installation identity, adapter version, or public schema contract;
- required capability evidence, health, or compatibility classification;
- target configuration fingerprint, inode/type, owner, mode, or trusted parent;
- active transaction/lock, lifecycle state, or continuity policy;
- approval policy or plan expiry.

Stale plans are discarded and replanned. They are not automatically refreshed
inside an already-approved execution because that would change the approved
intent.

### 4.4 Human-visible plan

Before a high-impact operation, the user should see a safe summary of:

- target Runtime and Provider display identity;
- compatibility and confidence states;
- whether existing sessions are expected to be unchanged, require a new
  session, or are unknown;
- whether a Runtime restart or reauthentication may be required;
- what managed configuration fields will change, without values;
- validation steps, rollback availability, and unresolved warnings.

The user never receives the raw Secret, raw config, or snapshot.

## 5. Validation Framework

### 5.1 Pre-validation

Before snapshot or mutation, validate:

1. authenticated actor, authorization, recent-auth/confirmation policy, and
   approval status;
2. typed action and exact allowed fields;
3. Provider/Credential/Profile/Binding state and expected revisions;
4. Secret-reference lifecycle and presence evidence without resolving it in
   the control plane;
5. fresh Runtime identity, health, capability, and compatibility evidence;
6. adapter and public Runtime schema/config support;
7. target architecture, dependencies, disk space, and snapshot readiness;
8. expected target type, fingerprint, owner, mode, and trusted parent chain;
9. absence of a conflicting transaction or lifecycle operation;
10. expected session/Remote Control impact and approval policy.

An `UNKNOWN` or `EXPERIMENTAL` compatibility result must remain visible. Policy
may prohibit mutation or require stronger confirmation; it cannot be upgraded
to `SUPPORTED` by the transaction framework.

### 5.2 Candidate/apply validation

The Runtime adapter must:

- use a fixed adapter-owned target; callers cannot supply a path;
- use the latest approved public Runtime config contract at implementation
  time, not an observed private file format;
- parse the existing document and preserve unrelated settings;
- generate only typed, allowlisted Provider-specific options;
- keep plaintext Secret Material out of ordinary config when a public
  environment-reference mechanism such as `env_key` is supported;
- reject duplicate/conflicting managed scopes and unsafe values;
- stage with restrictive ownership/mode in the target directory;
- validate candidate syntax and schema before publication;
- revalidate target and parent identity/fingerprint immediately before commit;
- reject symlinks, hardlinks, special files, untrusted parents, or concurrent
  manual changes;
- verify the staged digest, permissions, and available durable storage.

### 5.3 Post-validation

After publication, validate separate dimensions rather than collapsing them
into one `PASS`:

- target bytes/digest, owner, mode, type, and parse/schema validity;
- expected Runtime process/lifecycle state;
- Runtime health and refreshed capability evidence;
- Provider endpoint resolution and network reachability;
- authentication validity;
- Provider protocol and model availability;
- required Runtime wire/API compatibility;
- a minimal Provider request where policy permits;
- a minimal Runtime request where safely possible;
- Remote Control connection and compatibility;
- thread, conversation history, tool, streaming, Responses behavior, and
  Remote state continuity where observable;
- expected Runtime Binding and Secret reference metadata.

`Provider request PASS` does not imply `Remote Control compatible`. Required
versus advisory checks, cost limits, and destructive/session-affecting checks
must be explicit in the plan.

### 5.4 Validation result model

Each result includes:

- dimension and safe status;
- evidence source, version, time, and expiry;
- adapter/schema version;
- sanitized error code;
- whether it is required for commit;
- confidence/compatibility classification.

The transaction outcome and capability evidence remain distinct.

## 6. Snapshot Design

### 6.1 Snapshot contents

The protected Runtime snapshot should contain only recovery-critical state:

- exact prior content of the adapter-owned configuration target, or a marker
  proving that it did not exist;
- original file type, owner, group, mode, fingerprint, and relevant parent
  identity;
- adapter-managed scope metadata and public schema/adapter version;
- prior Provider, Credential version reference, Runtime Profile, and Runtime
  Binding IDs/revisions, without Secret Material;
- prior lifecycle, Runtime, Remote Control, and continuity evidence necessary
  to restore and verify expected state;
- transaction ID, plan digest, snapshot schema, creation time, and integrity
  metadata.

Exact original bytes are necessary to preserve settings outside AgentBox's
managed scope and to restore an originally absent file.

### 6.2 Snapshot exclusions

Snapshots must not intentionally collect:

- Provider Secret Material, Secret-store records, ciphertext, or master keys;
- Codex, Claude, or GitHub login credentials;
- arbitrary Runtime HOME files;
- Projects or Git worktrees;
- prompts, completions, conversation history, private session stores,
  JSONL/rollout data, or tmux internals;
- application secrets, Web sessions, database contents, or broad filesystem
  trees.

### 6.3 Pre-existing sensitive configuration

An existing user-owned configuration can itself contain a credential or other
sensitive value even though AgentBox never writes such a value. Exact rollback
may require preserving those bytes.

Therefore ADR-034 does not permit plaintext snapshot export. A full-file
snapshot containing pre-existing sensitive bytes is an opaque sensitive blob:

- encrypted/authenticated at rest under a Runtime-owned snapshot key domain;
- inaccessible to `agentbox`, Web/API, Worker, audit, reports, and users;
- never diffed or returned by the Runtime contract;
- retained for the minimum rollback window and securely retired according to
  approved policy.

The snapshot must not reuse the Provider Secret store as a generic file vault,
and its key-domain relationship to the Secret store remains an open design
decision.

### 6.4 Snapshot identity and integrity

Snapshot references are opaque IDs, not paths. Before use, the Runtime verifies
transaction binding, plan digest, target identity, snapshot schema, AEAD or
equivalent integrity, and expected owner/mode. Missing, corrupt, swapped, or
ambiguous snapshots fail closed.

Snapshot completion and verification must be durably journaled before mutation.
The control plane may record only the opaque reference and safe status.

## 7. Atomicity Model

### 7.1 Filesystem atomicity

For a single regular configuration file, the future adapter should conceptually:

1. validate trusted parent directories with no-follow semantics;
2. open/read the current target safely and record identity/fingerprint;
3. create a same-directory temporary regular file using exclusive creation,
   restrictive permissions, and no-follow behavior;
4. write the complete candidate and synchronize file data/metadata;
5. parse and validate the staged file;
6. revalidate the source target and parent against the plan;
7. publish with an atomic same-filesystem replacement primitive;
8. synchronize the parent directory where appropriate;
9. reopen without following links, reread, parse, and verify the published
   fingerprint and metadata;
10. record the durable journal checkpoint.

Exact primitives are implementation/platform decisions and require filesystem
and crash testing. A Runtime's public contract may prohibit replacing the file
or require its own supported command; the adapter must follow that public
contract.

### 7.2 Multi-resource atomicity

Filesystem publication, Runtime lifecycle, Provider verification, and SQLite
binding commit cannot be one atomic operation. The framework provides logical
atomicity through:

- immutable plan and expected revisions;
- durable checkpoints before irreversible actions;
- one active transaction per Runtime;
- idempotent state reconciliation;
- protected prior-state snapshot;
- delayed control-plane commit;
- compensating rollback with independent verification.

The user-visible outcome is all required state committed, verified recovery, or
an explicit `NEEDS_ATTENTION` condition. Partial success is never hidden.

### 7.3 Versioned configuration and commit markers

Versioned files or a `current` symlink may be used only if the Runtime's public
configuration contract supports that layout and ownership/security checks can
prevent symlink escape. AgentBox must not impose such a structure on Codex or
Claude merely because it is convenient.

The transaction journal/commit marker belongs in a fixed Runtime-owned state
directory separate from the user's target config. It must never be injected
into a third-party config as a private key or comment unless that Runtime's
public contract explicitly supports it.

### 7.4 Concurrency and out-of-band edits

The design uses two serialization layers:

- a control-plane resource lock preventing two approved AgentBox transactions
  from targeting the same Runtime simultaneously;
- a Runtime-local lock protecting application, lifecycle, verification, and
  rollback.

Locks coordinate AgentBox writers, not users or external tools. Fingerprint,
file identity, parent identity, and revision checks detect out-of-band edits.
AgentBox never overwrites a concurrent manual change to force its plan through.

## 8. Rollback Design

### 8.1 Automatic rollback conditions

After mutation, automatic rollback is normally requested when:

- publication or immediate reread validation fails;
- a required lifecycle transition fails;
- a required post-validation dimension fails or times out;
- the Runtime/binding state cannot be committed consistently;
- the process is recovered in an applied but unverified state and policy says
  restoration is safer than completion.

No automatic rollback occurs before confirming a valid, durable snapshot.
Where rollback could destroy an out-of-band user edit, the transaction moves to
`NEEDS_ATTENTION` rather than overwriting it.

### 8.2 Manual rollback

Manual rollback is itself a new approved transaction targeting an eligible
retained snapshot. It requires:

- exact Runtime and snapshot identity;
- current-state plan and conflict validation;
- authorization and impact confirmation;
- explicit treatment of Runtime Profile/Binding/Secret-version state;
- a fresh snapshot of the state being left when safe;
- the same application and verification rigor as forward activation.

Users cannot supply a snapshot path or upload arbitrary snapshot bytes.

### 8.3 Restoration scope

Rollback restores or reconciles:

- original configuration bytes or original nonexistence;
- original owner/group/mode and trusted target identity;
- prior managed Provider configuration;
- prior Runtime Profile, Runtime Binding, and non-secret Secret-version
  reference;
- prior lifecycle state when a transition occurred;
- expected Runtime and Remote Control continuity state where support exists.

It does not roll back Provider-side external state, billing, API key revocation,
model availability, prompts, conversation data, Projects, or unrelated Runtime
files. A revoked credential cannot be made valid by restoring its reference.

### 8.4 Rollback verification

Rollback verification independently checks:

1. snapshot integrity and target identity;
2. restored content/nonexistence, ownership, mode, and schema;
3. database/config migration compatibility if any future operation includes it;
4. Runtime process and socket state;
5. health and readiness;
6. reported Runtime/config/binding version;
7. capability refresh and expected Provider state;
8. Remote Control and session-continuity expectations;
9. control-plane/Runtime journal agreement.

Only then may the transaction enter `RECOVERED` and report `Rollback verified`.

### 8.5 Rollback failure

If a snapshot is missing/corrupt, a concurrent edit exists, restore publication
fails, lifecycle recovery fails, or any required check is inconclusive:

- record `NEEDS_ATTENTION` with sanitized evidence;
- retain the snapshot and journal;
- block further mutation of the affected Runtime;
- keep read-only diagnosis available;
- do not loop automatic rollback or silently choose another Provider;
- require an approved recovery procedure.

## 9. Failure Scenarios

| Scenario | Required behavior | Safe outcome |
|---|---|---|
| Provider/auth/model pre-validation fails | Do not snapshot or mutate; report the failed dimension | `FAILED_NO_CHANGE` |
| Runtime unavailable | Retry only bounded observation; do not infer state | `FAILED_NO_CHANGE` or `INTERRUPTED` if execution had begun |
| Capability evidence expired or version changed | Invalidate plan and require replan | `FAILED_NO_CHANGE` |
| Config fingerprint or revision conflict | Preserve manual change; reject execution | `FAILED_NO_CHANGE` |
| Target/parent becomes symlink, special file, or untrusted | Fail closed without following it | `FAILED_NO_CHANGE` or `NEEDS_ATTENTION` |
| Snapshot creation/integrity fails | Do not mutate | `FAILED_NO_CHANGE` |
| Staged write, fsync, or validation fails | Remove only verified transaction-owned temp state | `FAILED_NO_CHANGE` |
| Crash before publication | Reconcile journal and verify original fingerprint | `FAILED_NO_CHANGE` or `NEEDS_ATTENTION` |
| Crash after atomic replace, before checkpoint | Compare target/candidate/snapshot digests; never blindly replay | `RECONCILING` |
| Migration or adapter conversion partially fails | Do not claim database/config recovery; apply declared compatibility policy | `ROLLBACK_REQUIRED` or `NEEDS_ATTENTION` |
| Runtime restart/lifecycle action fails | Attempt verified restoration when safe | `RECOVERED` or `NEEDS_ATTENTION` |
| Health/Provider/Remote/continuity verification fails | Record dimensions separately; roll back if required by plan | `RECOVERED` or `NEEDS_ATTENTION` |
| Runtime verified, DB commit missing | Use `COMMIT_PENDING`; reconcile exact plan and revisions | `COMMITTED`, `RECOVERED`, or `NEEDS_ATTENTION` |
| DB committed, final Runtime acknowledgement missing | Reconcile Runtime journal and actual target before action | `COMMITTED`, `RECOVERED`, or `NEEDS_ATTENTION` |
| Snapshot corrupt or old release/adapter unavailable | Do not report rollback success | `NEEDS_ATTENTION` |
| Adapter/public schema changes mid-transaction | Pin plan to adapter/schema version; do not reinterpret | `FAILED_NO_CHANGE` or `NEEDS_ATTENTION` |
| Secret version revoked during activation | Do not reactivate it; invalidate plan or recover to an actually valid state | `FAILED_NO_CHANGE`, `RECOVERED`, or `NEEDS_ATTENTION` |
| Cancellation or timeout during apply | Treat outcome as unknown until reconciliation | `INTERRUPTED` |

### 9.1 Crash and power-loss recovery

On startup, both control-plane orchestration and the Runtime transaction service
must discover non-terminal transactions. Recovery compares:

- control-plane state and revision;
- Runtime journal state and transaction/plan digest;
- target and staged fingerprints;
- snapshot identity/integrity;
- lifecycle/process/socket observations;
- binding and capability evidence.

Recognized states include `staged`, `snapshot durable`, `applied`, `verified but
uncommitted`, `rollback pending`, `rollback applied but unverified`, and
`unknown`. Recovery does not automatically rerun migrations, reapply a file,
repeat a paid Provider request, restart a Runtime, or delete a snapshot unless
the transition is explicitly proven idempotent.

## 10. Audit Model

### 10.1 Events

The existing audit system should record safe, append-only events such as:

- `config_plan_created`, `config_plan_prepared`, `config_plan_expired`, and
  `config_plan_stale`;
- `config_transaction_approved`, `started`, and `cancelled`;
- `config_snapshot_created` and `config_snapshot_retired`;
- `config_apply_started`, `succeeded`, and `failed`;
- `config_verify_started` and per-dimension sanitized result;
- `config_commit_pending` and `config_committed`;
- `config_rollback_requested`, `started`, `verified`, and `failed`;
- `config_reconciliation_started`, `completed`, and `needs_attention`.

Each event may include actor, transaction/plan/request IDs, target opaque IDs,
expected revisions, adapter/schema version, safe status/error code, timestamps,
and approval/audit correlation.

### 10.2 Prohibited audit content

Audit, Jobs, logs, reports, diagnostics, and ordinary CLI/Web responses never
record:

- Secret Material, ciphertext, nonces, tags, key material, token hints, or
  Authorization headers;
- raw Runtime configuration or snapshots;
- config values, value-bearing diffs, environment contents, or arbitrary user
  payload;
- Provider response bodies, prompts, completions, conversation history, Pair
  Codes, or Runtime credentials;
- caller-supplied paths, commands, argv, executable, PID, signal, or unit name.

Request IDs and user-supplied labels are length/character bounded and escaped
for their output context. The Runtime records only typed action, caller
identity, correlation ID, state transition, and sanitized result.

## 11. Runtime Interaction

### 11.1 Conceptual flow

```text
Control Plane
    user intent + authorization + policy + expected revisions
        |
        v
Typed Plan Request over authenticated Runtime contract
        |
        v
Runtime Adapter
    local read-only inspection -> sanitized immutable plan + digest
        |
        v
Control Plane approval and transaction state
        |
        v
Typed Execute Request
    transaction ID + plan digest + approval proof + expected revisions
        |
        v
Runtime
    validate -> snapshot -> apply -> verify -> safe evidence
        |
        v
Control Plane
    commit intent or request verified rollback
```

### 11.2 Contract requirements

The future mutation protocol is distinct from the Phase 11.2 read-only
capability contract. It requires its own versioned, exact request/response
schemas, size/time bounds, replay/idempotency semantics, transaction-state
preconditions, and peer authentication.

The existing Runtime UDS security model remains the baseline:

- fixed Unix socket ownership/mode and `SO_PEERCRED` validation;
- one bounded typed operation, not a generic RPC tunnel;
- reject unknown fields and unknown actions;
- no raw path, shell, command, executable, argv, environment, PID, signal,
  chmod/chown, package, or systemd unit supplied by the caller;
- fixed adapter mapping and target selection inside Runtime;
- protocol/version mismatch fails closed.

### 11.3 Runtime remains execution owner

Only `agentbox-runtime` may inspect or modify its local Runtime configuration,
use a Provider Secret, coordinate its Runtime lifecycle, and gather local
verification evidence. The `agentbox` user cannot read Runtime HOME or write
the Project/config filesystem.

The root Helper remains unchanged. It is not used to read, decrypt, snapshot,
edit, activate, test, or roll back Provider configuration. If a future
operation genuinely needs a new root action, it requires a separate security
review and fixed-action protocol decision; this ADR grants none.

### 11.4 Session and Remote Control continuity

Activation policy must identify whether a change:

- affects only new requests;
- requires a Runtime restart;
- affects existing Remote sessions or conversation/thread state;
- requires a new session or reauthentication;
- has `UNKNOWN` or `EXPERIMENTAL` continuity.

The transaction cannot mutate private session state to make continuity appear
successful. When public behavior cannot establish compatibility, it reports
uncertainty rather than promising continuity.

## 12. Security Model

### 12.1 Unauthorized configuration change

Mitigations include authenticated sessions, CSRF/origin policy, operation-level
authorization, recent authentication or explicit confirmation for high-impact
changes, immutable plan digests, expected revisions, expiry, one active
transaction per Runtime, exact Runtime peer identity, and complete audit.

A compromised browser request cannot send raw Runtime bytes or turn an approved
action into an arbitrary file write.

### 12.2 Secret exposure

The control plane carries only CredentialID, SecretRecordID/version reference,
and safe lifecycle evidence. Runtime resolves plaintext only within the bounded
Secret-use operation defined by Phase 11.3. Candidate config prefers a public
environment-variable reference capability; plaintext is never persisted in an
ordinary config, plan, snapshot metadata, journal, audit, log, argv, API, or
database field.

An opaque full-file snapshot that incidentally contains pre-existing sensitive
bytes is encrypted and never exposed, as defined in section 6.3.

### 12.3 Privilege escalation and Runtime takeover

The mutation protocol has no generic command or path primitives. It runs under
the existing non-root `agentbox-runtime` identity and cannot use sudo, the root
Helper, or arbitrary systemd actions. Fixed targets, trusted parent validation,
no-follow I/O, restrictive files, exact schemas, bounded messages, and adapter
allowlists limit filesystem and protocol abuse.

The contract changes configuration; it never grants the control plane an
interactive shell, tmux internals, Runtime credential export, Project write,
or arbitrary process control.

### 12.4 Malicious Provider activation

Endpoint, protocol, model, and typed adapter options remain Provider-domain
data subject to validation. Mitigations include:

- URL scheme, hostname/IP, redirect, DNS rebinding, and local-network policy;
- no arbitrary headers, environment variables, config keys, or paths;
- credential-to-Provider revision binding;
- Runtime compatibility classification and required verification matrix;
- bounded request size/time/cost and sanitized responses;
- no automatic fallback or silent Provider substitution;
- explicit `EXPERIMENTAL`, `DEGRADED`, `INCOMPATIBLE`, or `UNKNOWN` reporting.

A reachable Provider is not automatically trusted, Runtime-compatible, or
Remote-Control-compatible.

### 12.5 Concurrency, replay, and TOCTOU

Plan expiry, transaction IDs, monotonic revisions, plan digests, Runtime-local
journals, resource locks, source fingerprints, immediate pre-publication
revalidation, and state-conditional transitions prevent stale replay and reduce
TOCTOU exposure. These controls cannot prevent a privileged out-of-band writer;
such interference produces a conflict or `NEEDS_ATTENTION`, never a forced
overwrite.

### 12.6 Residual risks

- Root or a compromised `agentbox-runtime` remains a host-level trust failure.
- Third-party public schemas and Runtime behavior may change.
- Filesystem atomicity and durability differ by platform/filesystem.
- External Provider state and credential revocation cannot be rolled back
  locally.
- Remote/session continuity may remain unobservable or experimental.
- Snapshot protection cannot guarantee erasure on all storage media.
- A multi-resource state machine can reach `NEEDS_ATTENTION`; honest uncertainty
  is preferable to false atomicity.

## 13. Architecture Decisions

### ADR-031 — Runtime changes require transaction boundaries

**Status:** Proposed
**Decision:** Every AgentBox-managed Runtime configuration mutation uses a
durable Configuration Transaction with typed intent, immutable plan, validation,
protected snapshot, application, verification, final state, and audit. No
direct one-shot config write is allowed.
**Consequence:** Provider activation has more workflow/state complexity, but
partial and unknown outcomes become detectable and recoverable.

### ADR-032 — Validation precedes mutation

**Status:** Proposed
**Decision:** Authorization, revisions, fresh capability/compatibility evidence,
target safety, candidate syntax/schema, dependencies, and rollback readiness
must pass before publication. Post-application validation remains independently
required.
**Consequence:** A successful plan is not permission or a guarantee; execution
revalidates all security-critical assumptions.

### ADR-033 — Failed Runtime changes require verified rollback

**Status:** Proposed
**Decision:** A failure after mutation triggers a compensating rollback when it
is safe. Recovery is reported only after exact restoration and independent
Runtime/health/continuity verification. Otherwise the Runtime enters
`NEEDS_ATTENTION` and further mutations are blocked.
**Consequence:** AgentBox never equates rollback attempt, file replacement, or
old-binary activation with verified recovery.

### ADR-034 — Snapshots exclude separately managed Secret Material

**Status:** Proposed
**Decision:** Snapshot metadata never contains Provider Secret Material,
Secret-store records, ciphertext, or keys. If exact rollback requires preserving
a pre-existing config that contains sensitive bytes, it is stored only as an
opaque encrypted Runtime-owned snapshot and never exposed to the control plane,
Audit, logs, reports, or API.
**Consequence:** Exact user-setting preservation remains possible without
turning snapshot storage into a plaintext Secret or general backup system.

### ADR-035 — Planning and execution are separate contracts

**Status:** Proposed
**Decision:** Planning is read-only and produces an immutable, expiring,
revision-bound plan digest. Execution requires an explicit approved request for
that exact plan and revalidates it before mutation.
**Consequence:** Approval cannot silently authorize a different config after
evidence or Runtime state changes.

### ADR-036 — Transaction persistence is split across trust boundaries

**Status:** Proposed
**Decision:** The control plane persists non-secret orchestration state and
audit correlation. Runtime persists a protected local execution journal and
opaque snapshots. Neither side reads the other's private store.
**Consequence:** Crash recovery requires a reconciliation protocol, but raw
Runtime config and snapshots do not enter SQLite.

### ADR-037 — Multi-resource atomicity uses a recoverable state machine

**Status:** Proposed
**Decision:** AgentBox does not claim distributed ACID across SQLite, files, and
processes. It uses durable checkpoints, delayed commit, idempotent reconciliation,
and compensating rollback.
**Consequence:** `COMMIT_PENDING`, `INTERRUPTED`, and `NEEDS_ATTENTION` are
first-class states rather than hidden partial failures.

### ADR-038 — Transactions serialize per Runtime and detect external edits

**Status:** Proposed
**Decision:** At most one mutating AgentBox transaction targets a Runtime at a
time, enforced in both orchestration and Runtime layers. Fingerprint and file-
identity checks detect writers outside AgentBox.
**Consequence:** Manual edits are preserved as conflicts; AgentBox does not
overwrite them to satisfy a stale plan.

### ADR-039 — Active Runtime Binding commits only after required verification

**Status:** Proposed
**Decision:** Runtime application does not make a binding active in control-
plane truth. Activation is committed only after the plan's required validation
matrix passes; each compatibility dimension remains visible.
**Consequence:** Provider reachability cannot be mistaken for Codex Runtime or
Remote Control compatibility.

### ADR-040 — Interrupted transactions reconcile; they are never blindly replayed

**Status:** Proposed
**Decision:** Restart recovery compares the transaction, plan digest, local
journal, snapshot, target fingerprint, lifecycle, and binding state before any
next action. Unknown state blocks mutation.
**Consequence:** Retry cannot duplicate a paid test, rerun a migration, overwrite
a concurrent edit, or restart a Runtime without evidence.

### ADR-041 — Runtime owns local configuration application

**Status:** Proposed
**Decision:** The control plane sends typed intent and expected revisions; the
Runtime adapter generates, applies, verifies, and restores its own fixed target.
The control plane never receives or supplies raw Runtime configuration.
**Consequence:** Existing process/filesystem separation remains intact and
AgentBox does not become a Web shell or Runtime file editor.

## 14. Open Questions

The following require product, security, or implementation approval before any
mutation work begins:

1. **Control-plane persistence:** What exact future database schema and retention
   represent transaction state, transitions, plan digest, and safe evidence?
2. **Runtime journal location:** Which fixed Runtime-owned state path, mode,
   format, and durability rules are qualified on supported Linux platforms?
3. **Snapshot encryption:** Does the snapshot store use a distinct key domain
   from the Phase 11.3 Provider Secret store, and how is its key rotated?
4. **Snapshot retention:** What count, age, and disk quota apply, and when may a
   committed/recovered transaction's snapshot be retired?
5. **Manual rollback retention:** How long may a prior state be selected, and
   what happens after its Provider credential is revoked or adapter removed?
6. **Concurrency mechanism:** What control-plane lease and Runtime-local lock
   primitives are used, how is stale-lock ownership proven, and how are split
   locks reconciled after a crash?
7. **Commit-pending policy:** When Runtime verification passed but the database
   commit did not, when should recovery finish commit versus roll back?
8. **Approval policy:** Which actions require recent authentication, explicit
   confirmation, two-step approval, or an impact-specific warning?
9. **Verification policy:** Which Provider, Runtime, Remote Control, and session
   checks are mandatory for each adapter/compatibility class, and which may incur
   cost or alter session state?
10. **Lifecycle policy:** Which public Runtime operations may be restarted, how
    are active sessions handled, and can activation be limited to new sessions?
11. **Atomic primitives:** Which no-follow/open/rename/fsync behavior is required
    for each qualified filesystem and Linux distribution?
12. **Metadata preservation:** Must rollback preserve ACLs, extended attributes,
    SELinux labels, or only owner/group/mode, and how are unsupported cases
    surfaced?
13. **Multiple targets:** Does v1 permit only one adapter-owned config file per
    transaction, or how are multiple files/directories safely compensated?
14. **Adapter upgrade:** How is an interrupted transaction recovered if the
    adapter or public Runtime schema version changes during AgentBox upgrade?
15. **Pre-existing inline Secrets:** Should activation be blocked until users
    migrate them to a reference, or can opaque snapshot-and-preserve coexist
    without AgentBox inspecting the value?
16. **Cancellation semantics:** At which states is user cancellation accepted,
    and when does it become a rollback request rather than cancellation?
17. **Recovery operations:** What narrowly typed, local-only operator workflow
    may inspect safe recovery evidence or unblock `NEEDS_ATTENTION` without
    exposing config/snapshots or creating a generic repair shell?
18. **Remote continuity:** What public Codex evidence can safely distinguish
    unchanged existing sessions, new-session-only behavior, degraded behavior,
    and unknown compatibility at implementation time?
19. **Timeouts and leases:** What bounded operation and verification timeouts
    avoid indefinite locks without incorrectly assuming a timed-out mutation
    failed?
20. **Audit/event ordering:** How are Runtime journal sequence numbers correlated
    with control-plane Audit so retries cannot duplicate or reorder a final
    result?

## Recommended Next Design Phase

Proceed only after human approval to **Phase 11.5 — Provider Validation Pipeline
Design**. That design should define the validation dimensions, evidence schema,
cost/side-effect policy, compatibility classification, and commit-gating matrix
used by this transaction framework. It must remain design-only until the full
Phase 11 architecture is approved.
