# AgentBox Phase 11 Slice 3.2 — Secret Provisioning and Runtime Attestation Authorization Review

**Review type:** architecture and implementation-authorization review only

**Authoritative baseline:** `6c8b185c6fa5b8ea2d2af4f9c03f849e1459f712`

**Decision:** **BLOCKED**

This review converts the accepted Secret-boundary decisions into a
repository-specific provisioning contract. It creates no production code,
Secret, Runtime Store record, Runtime RPC, Control Plane mutation, migration,
Provider request, configuration change, or activation behavior.

The Runtime-side protocol, TTY, transaction, attestation, recovery, and Store
evolution decisions below are closed. Implementation is nevertheless blocked
because the current Control Plane cannot unambiguously bind a Credential to one
Runtime installation and does not implement the durable, single-use
`ConfirmationChallenge` described by the architecture. Both defects require a
separately reviewed additive Control Plane schema change before Secret-bearing
implementation may begin.

## 1. Current Repository State

The review verified the following baseline facts:

- `origin/main` and local `main` were
  `6c8b185c6fa5b8ea2d2af4f9c03f849e1459f712` before this documentation branch;
- PR #37 is merged and Slice 3.1 is present;
- the Alembic head remains `0004_phase11_provider_core`; no `0005` exists;
- Slice 3.1 provides the fixed Runtime-owned Store, key custody, envelope
  primitives, health inspection, and the initialize-only local entry point;
- no provisioning command, provisioning UDS action, credential broker,
  Provider request, Codex/Claude configuration access, or activation exists;
- the production Store path was not created or mutated during this review;
- `provider_credentials` currently contains `id`, `provider_id`, `kind`,
  `runtime_secret_ref`, `secret_version`, `state`, `revision`, and timestamps,
  but no `runtime_installation_id`;
- the codebase has recent-auth checks and durable allowlisted Jobs, but no
  implemented `ConfirmationChallenge` model, repository, or single-use
  consumption service.

## 2. Accepted ADR Mapping

This contract preserves the following accepted decisions.

| Decision | Application to Slice 3.2 |
|---|---|
| P11-ADR-021 | Credential metadata remains distinct from Runtime-owned Secret Material |
| P11-ADR-022 | plaintext, ciphertext, keys, nonces, tags, and raw envelopes never enter Control Plane fields |
| P11-ADR-023 | Runtime Secret authority is typed, purpose-specific, and minimal; there is no generic reveal operation |
| P11-ADR-024 | authorization, consumption, attestation, and reconciliation produce only allowlisted non-secret Audit evidence |
| P11-ADR-025 | provisioning uses the dedicated Runtime-local Secret Store |
| P11-ADR-026 | every immutable Secret version uses authenticated envelope encryption |
| P11-ADR-027 | Secret ingress is local, interactive, Runtime-identity, and TTY-only |
| P11-ADR-028 | Root Helper receives no Secret authority or new action |
| P11-ADR-029 | ordinary backup excludes provisioning state and Secret Store material |
| P11-ADR-030 | later Secret delivery remains transient and action-specific; provisioning creates no generic read API |
| P11-ADR-073 | the frozen AES-256-GCM, HKDF-SHA-256, RFC 8785 AAD, identity, nonce, and key-use contract remains unchanged |
| P11-ADR-074 | Runtime owns key custody, initialization, loss behavior, and re-entry recovery |
| P11-ADR-076 | implementation must pass a separately reviewed, narrow, fail-closed governance gate |

No accepted ADR is changed or superseded by this review.

## 3. Scope and Non-scope

The future provisioning boundary may eventually authorize exactly one initial
Secret version for one pre-existing `MISSING` Credential, accept the value from
a local protected TTY, commit one immutable Runtime record, attest it, and
reconcile only opaque metadata.

It does not authorize rotation, revocation, deletion, reveal, export, import,
backup, Provider validation, Provider networking, a broker, Codex/Claude
configuration access, Runtime Binding mutation, activation, rollback, public
API/CLI/UI Secret input, or Root Helper expansion.

## 4. Control Plane Authority

The Control Plane decides whether one exact provisioning attempt may be staged.
Before authorization it must reload and bind:

- authenticated administrator and Control Plane session;
- recent authentication;
- one unconsumed purpose-specific approval;
- `RuntimeInstallationID` and revision;
- `ProviderID` and revision;
- `CredentialID`, revision, and kind;
- Credential state `MISSING` with null reference/version;
- the Credential's exact Runtime ownership;
- purpose `PROVIDER_SECRET_PROVISION`;
- one server-generated provisioning intent ID;
- issue and expiry timestamps;
- an approval/plan digest over this exact typed postcondition.

The Control Plane sends only this bounded non-secret intent to Runtime. It
cannot generate a SecretRecordID, choose a Secret version, accept plaintext,
read ciphertext, inspect Store rows, or declare an attestation valid without
rechecking all current revisions.

## 5. Runtime Authority

Runtime alone may durably stage an approved intent, verify the fixed local
process and TTY, read transient plaintext, generate record/envelope identities,
encrypt, commit, reopen, authenticate, and emit a bounded attestation.

Knowing a Credential ID, intent ID, approval digest, or SecretRecordID is not a
bearer capability. Runtime resolves authorization from protected local state
and the peer-authenticated UDS record. The local CLI cannot self-authorize or
change identity, revision, purpose, path, algorithm, nonce, timeout, or
destination.

## 6. Provisioning Intent Model

Reserve the previously unused identity prefix:

`ProvisioningIntentID = psi_<32 lowercase hexadecimal characters>`

The Control Plane generates the ID. Runtime persists one exact immutable
authorization tuple:

- intent schema/version and `psi_*` ID;
- purpose `PROVIDER_SECRET_PROVISION`;
- RuntimeInstallationID/revision;
- ProviderID/revision;
- CredentialID/revision and credential kind;
- expected Credential state `MISSING`;
- expected null Secret reference/version;
- approval challenge ID and digest;
- authorizing administrator/session pseudonymous identifiers where required;
- issued time, fixed expiry, and cancellation epoch;
- state, transition time, and bounded terminal finding;
- committed SecretRecordID/version only after the atomic Store commit;
- verification mode and attestation-consumption status.

There is no generic metadata, arbitrary JSON, caller payload, command, path,
environment, Provider endpoint, or Secret-bearing field.

The exact authorization TTL is five minutes. It is server-selected and cannot
be extended or renewed. The earliest invalidator wins: expiry, approval
cancellation/consumption, revision change, lease loss where used, explicit
cancellation, recovery contradiction, or first failed/uncertain consumption.

## 7. Existing Approval Primitive Mapping

The intended authority source is a short-lived, one-time
`ConfirmationChallenge` issued after recent authentication and bound to the
exact provisioning tuple and purpose. Recent authentication proves freshness
of administrator authentication; it is not itself approval. A Job lease proves
worker ownership; it is not approval. An Audit row records history; it is not
approval.

Repository inspection found that `ConfirmationChallenge` is described in
`docs/SECURITY.md` and `PHASE11_IMPLEMENTATION_PLAN.md` but is not implemented
as a current model or service. Existing Jobs are restricted to unrelated job
types and their generic bounded payload cannot safely become a provisioning
authorization store.

Therefore the current repository has no authoritative primitive that can
provide all of: purpose binding, exact revisions, five-minute expiry,
cancellation, atomic single-use consumption, and durable replay prevention.
An `approval_digest` without that source would be security theater. This is a
blocking prerequisite requiring a separately reviewed additive Control Plane
schema and service.

Provisioning is not a long-running worker Job. The authorization stage is a
short synchronous internal orchestration operation; the local TTY operation is
out-of-band and Runtime-owned. Status/reconciliation is explicit and bounded.

## 8. Intent State Machine

The canonical Runtime-local state machine is:

```text
STAGED
  -> CONSUMING
  -> COMMITTED_UNVERIFIED
  -> VERIFIED
  -> RECONCILED
```

Terminal or fail-closed branches are:

```text
STAGED -> CANCELLED | EXPIRED
CONSUMING -> FAILED | NEEDS_ATTENTION
COMMITTED_UNVERIFIED -> VERIFIED | NEEDS_ATTENTION
VERIFIED -> RECONCILED | EXPIRED_UNRECONCILED | NEEDS_ATTENTION
```

`CONSUMING` is entered durably before any plaintext byte is read. It never
returns to `STAGED`. `COMMITTED_UNVERIFIED` is written in the same SQLite
transaction as the envelope and wrap counter. `VERIFIED` requires either the
live reopen-and-original-byte comparison or the exact recovery verification
defined below. `RECONCILED` is terminal and is recorded only after Runtime
accepts a Control Plane acknowledgement for the same attestation. No state can
be replayed into an earlier state.

## 9. UDS Contract

The existing peer-authenticated Runtime UDS is reused. Protocol version remains
`1`; a separate provisioning contract version starts at `1`. No second socket
or network listener is created.

The future exact actions are:

- `runtime.provider_secret.provision.authorize` — stage one typed intent;
- `runtime.provider_secret.provision.status` — retrieve one exact intent's
  non-secret state/attestation;
- `runtime.provider_secret.provision.cancel` — cancel one unconsumed `STAGED`
  intent or record that a later state cannot be cancelled;
- `runtime.provider_secret.provision.reconciled` — acknowledge one exact
  successfully committed Control Plane reconciliation.

Each action has exact keys, strict scalar types, no extras, frame bounds,
duplicate-key rejection, peer UID/GID checks, fixed timeouts, and exact ID
grammars. There is no list action, plaintext field, generic Store operation,
arbitrary payload, path, command, environment, algorithm, nonce, or TTL.

`authorize` is idempotent only for byte-identical identity/revision/digest
tuples while still `STAGED`; any contradiction fails closed. `status` is a
read of one server-generated ID and cannot consume or extend it. `cancel` and
`reconciled` are conditional state transitions, not generic patch operations.

## 10. Local CLI Contract

The sole future local command is:

```text
/opt/agentbox/current/venv/bin/agentbox-runtime-provider-secret provision \
  --credential <CredentialID> \
  --expected-revision <positive integer>
```

It accepts no Secret in argv, path, file, environment, Provider, Runtime,
intent ID, version, timeout, algorithm, key, nonce, or backend. Runtime resolves
the only eligible `STAGED` intent server-side. Zero or multiple eligible
intents fails closed.

Output is one bounded machine-readable English status code. It never prints a
path, SecretRecordID, key ID, ciphertext, raw exception, or plaintext. Ordinary
future user guidance and prompts default to Simplified Chinese (`zh-CN`).

## 11. TTY and Input Contract

The command requires a controlling TTY and `stdin` must be that TTY. It rejects
pipes, redirected files, sockets, environment values, clipboard automation,
and non-interactive input. It verifies real/effective/saved UID and GID are the
installed `agentbox-runtime` identity and the executable/release chain is not
writable by that identity.

Echo is disabled before input and restored in every success, failure, signal,
timeout, and cancellation path. Exactly one entry is used. Double entry would
increase Secret lifetime and copy count and cannot prove the Provider value is
correct; validation belongs to a later network-validation slice.

The value is 1–16384 visible ASCII bytes. Space is valid and is not trimmed.
The terminal Enter delimiter is consumed but is not part of the value; embedded
CR/LF, NUL, other controls, non-ASCII, empty, truncated, or oversized input is
rejected.

The exact input timeout is 90 seconds, but `expires_at` is a hard deadline. The
effective deadline is `min(CONSUMING-entered-at + 90 seconds, expires_at)`. If
the intent expires while the operator is typing, input stops, buffers are
best-effort cleared, the attempt becomes `EXPIRED`/`FAILED`, and a new approval,
intent, and complete re-entry are required. Starting before expiry does not
grant a grace period.

Terminal paste cannot be proven or prevented reliably by a portable TTY API.
The contract claims only: AgentBox provides no clipboard integration, never
requests paste, disables terminal echo, and treats pasted bytes exactly like
typed bytes subject to the same bounds. Host terminal software, root, and a
compromised Runtime UID remain outside this guarantee.

## 12. Input Timeout and Signal Policy

Input uses monotonic deadline accounting while persisted expiry remains UTC.
`SIGINT`, `SIGTERM`, hangup, timeout, EOF, short read, encoding failure, or
terminal-control failure restores termios, clears buffers best-effort, and
leaves a non-reusable terminal state. It never returns the intent to `STAGED`
and never attempts to infer whether the operator intended a partial value.

## 13. Secret Store Transaction

The Runtime-local Store requires an explicit schema v2 before provisioning.
One `BEGIN IMMEDIATE` transaction must atomically:

1. revalidate the `CONSUMING` intent and exact expiry/revisions;
2. allocate `secret_version = 1` and Runtime-generated `sec_*`/`dek_*` IDs;
3. generate one fresh DEK, payload nonce, and wrap nonce;
4. create the immutable DEK envelope and Secret record;
5. increment the current key's `successful_wraps` exactly once;
6. transition the intent to `COMMITTED_UNVERIFIED` and bind record/version;
7. commit durably under the fixed Store mutation lock.

There is no plaintext column or temporary plaintext file. All existing Store
size, record-count, schema-inventory, nonce-uniqueness, ownership, mode, link,
PRAGMA, fsync, and integrity rules remain mandatory.

## 14. Wrap-counter Atomicity

`successful_wraps` and the corresponding `dek_envelopes`, `secret_records`, and
intent transition are one SQLite transaction. The counter increments only if
the entire transaction commits. A uniqueness collision causes transaction
rollback and generation of an entirely fresh DEK and both nonces before a
bounded retry. Material from an uncertain commit is never reused. Reaching the
frozen wrap limit blocks the write; this slice does not rotate a key.

## 15. Post-commit Cryptographic Verification

After a successful commit Runtime closes/reopens the relevant Store state,
rereads the exact envelope and keyset, reconstructs and byte-compares canonical
AAD, unwraps the DEK, authenticates/decrypts the ciphertext, validates plaintext
bounds, and compares decrypted bytes with the still-live original input. Only
then does it best-effort clear both buffers and transition to `VERIFIED`.

Any mismatch or `InvalidTag` preserves evidence, denies attestation, and enters
`NEEDS_ATTENTION`; it never deletes or overwrites the committed record.

## 16. Runtime Attestation

A verified attestation contains exactly:

- attestation schema/version and provisioning contract version;
- intent ID and purpose;
- RuntimeInstallationID/revision;
- ProviderID/revision;
- CredentialID/revision and credential kind;
- expected prior state `MISSING`;
- Runtime-generated SecretRecordID and Secret version `1`;
- Store schema and envelope algorithm identifiers;
- approval challenge ID/digest;
- issued, committed, verified, and expiry timestamps;
- verification mode `live_plaintext_match` or `recovered_aead_reopen`;
- bounded result `VERIFIED` and one attestation-consumption state.

It contains no plaintext, ciphertext, root key, KEK, DEK, nonce, tag, wrapped
DEK, AAD bytes, key ID, Store path, raw row, Provider endpoint, command,
environment, or arbitrary metadata.

This is an authenticated UDS statement from the peer-validated Runtime and its
protected local journal, not a cryptographic signature or portable bearer
credential. A fully compromised `agentbox-runtime` UID can forge Runtime-local
behavior and compromise every Runtime-usable Provider Secret. Peer checks,
exact state, and replay protection remain defense in depth and workflow
integrity, not isolation from that compromise.

## 17. Control Plane Reconciliation

After receiving `VERIFIED`, the future Control Plane service must use
`BEGIN IMMEDIATE`, atomically consume its durable approval/orchestration record,
and reload RuntimeInstallation, Provider, Credential, and all revisions. It
requires:

- exact Runtime ownership and unchanged Runtime revision/type;
- exact Provider relationship and unchanged, non-disabled Provider revision;
- exact Credential revision/kind/state `MISSING`;
- null current `runtime_secret_ref` and `secret_version`;
- exact attestation tuple, purpose, approval digest, Store/envelope schemas;
- `sec_*` grammar and attested version `1`;
- unconsumed/unexpired attestation and matching expected postcondition.

It then performs only:

```text
runtime_secret_ref = attested SecretRecordID
secret_version     = 1
state              = CONFIGURED
revision           = previous revision + 1
updated_at         = now
```

and writes one allowlisted non-secret Audit event in the same transaction.
After commit it sends the conditional `reconciled` acknowledgement. Failure to
acknowledge does not roll back Control Plane state; a later exact status check
may repeat the acknowledgement idempotently.

Existing `MISSING`/`CONFIGURED` reference constraints are useful but insufficient
to enforce Runtime ownership and durable attestation consumption. A Control
Plane migration is required before this operation may exist.

## 18. Credential State Transition

The only transition in initial provisioning is `MISSING -> CONFIGURED`. It is
not a generic Credential patch. Rotation, revoke, `NEEDS_ATTENTION`, and
replacement transitions remain deferred. Direct caller-supplied `sec_*` values
are always rejected. A stale or duplicate attestation never increments the
Credential revision.

## 19. RuntimeInstallation Ownership Decision

V1 chooses one Credential metadata row per one concrete Runtime installation.
Its opaque `sec_*` reference is meaningful only inside that Runtime's local
Store. Multi-Runtime reuse therefore requires separate Credential identities;
it cannot reuse one `ProviderCredential` row across stores.

The current `ProviderCredential` schema is **not sufficient** because it has no
RuntimeInstallationID. Deriving ownership from a Runtime Profile is unsafe:
profiles are optional, can be multiple or historical, and provisioning must
precede a Credential-backed Profile. An attestation alone cannot make the
missing durable relationship queryable or database-enforced.

A separately reviewed additive migration must add an explicit, foreign-keyed
Runtime ownership relation (preferably a non-null
`provider_credentials.runtime_installation_id` for newly created V1
credentials, with a defined treatment for pre-existing `MISSING` rows), plus
database enforcement that non-null reference/version state has exactly one
Runtime owner. It must also update Credential creation to require a registered
Runtime. No automatic assignment or adoption is permitted.

## 20. Runtime-local Store Schema Evolution

Slice 3.1 Store schema v1 contains only `secret_store_meta`, `key_metadata`,
`secret_records`, and `dek_envelopes`; it did not reserve provisioning intent
persistence. Adding a table without a version change would violate exact schema
inventory and downgrade safety. The provisioning-capable Store must therefore
be `agentbox.provider-secret-store.v2` with `PRAGMA user_version = 2`.

The fixed Runtime-only v1-to-v2 migration runs under the same Store mutation
lock, after full v1 health verification. It creates only the exact bounded
provisioning-intent table/indexes/triggers, changes the singleton Store schema
identifier and user version in one `BEGIN IMMEDIATE` transaction, runs
`quick_check`, foreign-key and exact-inventory validation, commits, fsyncs, and
reopens for full v2 read-back. It migrates no plaintext or envelope bytes and
creates no intent or Secret row.

On failure the transaction rolls back to verified v1 or the Store becomes
`NEEDS_ATTENTION`; there is no partial best-effort repair. Older Slice 3.1 code
must treat v2 as unsupported, preserve all bytes, and fail Provider Secret
operations closed. No automatic downgrade exists. A valid empty v1 Store is
eligible for this exact migration; a non-empty valid v1 Store is also migrated
without rewriting immutable records. Unknown schema objects or inconsistent
state blocks migration.

## 21. Crash Recovery

- Crash before durable `CONSUMING`: a still-valid `STAGED` intent may be used.
- Crash after `CONSUMING` but before Store commit: no record exists; the intent
  is terminal and a new approval and re-entry are required.
- Crash after atomic commit but before live plaintext comparison: recovery may
  reopen the exact record, prove the transaction linkage, reconstruct AAD,
  authenticate/decrypt internally, validate bounds, and transition to
  `VERIFIED` with mode `recovered_aead_reopen`. It cannot compare against the
  lost input, and the attestation states that fact. This is safe because the
  atomic transaction proves which bytes the one consuming process encrypted;
  it does not claim the operator typed the intended Provider value.
- Any uncertainty about whether the record/intention/counter committed, or any
  contradictory linkage, becomes `NEEDS_ATTENTION`; no blind retry occurs.

Startup reconciliation runs before another provisioning mutation. It never
reopens an expired `STAGED` or `CONSUMING` authorization.

## 22. Orphan Handling

If Runtime commits and verifies a record but Control Plane reconciliation
fails, the immutable record remains an **unreconciled orphan** bound to its
intent. It is not eligible for broker use, validation, activation, generic
lookup, or a second Credential. The exact same Control Plane orchestration may
retry status and reconciliation while the verified attestation is retained.

If the Control Plane tuple is now stale or contradictory, reconciliation is
denied and the intent becomes `EXPIRED_UNRECONCILED`/`NEEDS_ATTENTION`. This
slice does not delete the Secret. Orphan deletion/reprovision policy requires a
later explicit lifecycle review; preserving encrypted evidence is safer than
silently deleting or rebinding it.

## 23. Replay Prevention and Retention

Replay is prevented by the combination of the server-generated `psi_*` ID,
exact approval/identity/revision digest, atomic challenge consumption,
Runtime state monotonicity, unique Credential/version and record IDs, exact
attestation consumption state, and conditional Credential revision update.

Verified attestation metadata is retained in Runtime Store v2 for exactly 24
hours from `verified_at`, or until a `reconciled` acknowledgement is durably
recorded plus a minimum one-hour audit/retry window, whichever is later. It is
never renewable. After retention it may be pruned only by a fixed bounded
maintenance rule; encrypted records are not pruned. An expired attestation
cannot configure a Credential. The Control Plane's consumed challenge and
Audit evidence follow their own repository retention policy and contain no
Secret material.

## 24. Audit and Log Policy

Control Plane Audit may record only action/result, administrator ID,
RuntimeInstallationID/revision, ProviderID/revision, CredentialID/revision,
intent ID, purpose, challenge ID, transition/result code, Secret version,
opaque SecretRecordID when operationally required, contract versions, and
timestamps. Runtime logs use closed operation/result codes only.

No Audit, Job, log, diagnostic, exception, CLI output, UDS frame, test report,
or Control Plane database may contain plaintext, partial/hash/suffix of the
Secret, ciphertext, key material, nonces, tags, wrapped DEK, AAD bytes, raw
Store rows, terminal bytes, or arbitrary error text.

## 25. Threat Model

This review adds T-102 through T-111 to `docs/THREAT_MODEL.md` for:

- cross-Runtime Credential/Secret confusion;
- fabricated or replayed approval;
- TTY leakage and unrealistic paste assumptions;
- expiry/signal races during input;
- partial counter/envelope commit;
- crash between commit and verification;
- reconciliation failure and orphan rebinding;
- forged/replayed attestation;
- unsafe Store v1-to-v2 migration/downgrade;
- provisioning state enumeration and same-UID abuse.

The residual risk remains explicit: a fully compromised Runtime UID can
compromise Runtime-usable Provider Secrets and forge Runtime-local evidence.

## 26. Exact Implementation Slice Boundary

The originally proposed combined Slice 3.2 is too large and is not currently
implementable. The recommended ordering is:

### Slice 3.2a — Control Plane Ownership and Approval Foundation

Documentation and implementation authorization must separately review one
additive Alembic migration and non-secret services for:

- explicit Credential-to-Runtime ownership;
- durable typed `ConfirmationChallenge` with purpose, revisions, expiry,
  cancellation, and atomic single use;
- bounded non-secret orchestration/reconciliation state if needed;
- exact database constraints, migration of existing `MISSING` metadata,
  Audit allowlists, and tests.

It includes no Secret input, Store mutation, Runtime provisioning UDS, or
Credential transition to `CONFIGURED`.

### Slice 3.2b — Runtime Provisioning, Attestation, and Reconciliation

Only after 3.2a is merged may a second authorization cover:

- Store v1-to-v2 migration and intent persistence;
- strict authorize/status/cancel/reconciled UDS actions;
- fixed local TTY provisioning command;
- atomic envelope/counter/intent commit;
- reopen/recovery verification and bounded attestation;
- exact `MISSING -> CONFIGURED` reconciliation using the 3.2a authority;
- crash, replay, TTY, leak, migration, and adversarial tests.

This ordering is preferred to the prompt's Runtime-first/reconciliation-second
split. A Runtime-first PR would deliberately create unreconciled encrypted
orphans without an implemented authorization source or ownership model. The
non-secret authority foundation must exist first; then Runtime commit and
reconciliation should be reviewed together because their shared attestation
and orphan-recovery contract is the security boundary.

## 27. Remaining Blockers and Open Questions

### Blocking before any Slice 3.2 implementation

1. **Credential Runtime ownership:** choose and review the exact additive
   Control Plane migration, existing-row policy, foreign keys, and constraints.
2. **Approval authority:** implement/review a real durable
   `ConfirmationChallenge`; recent auth, Job lease, and Audit are insufficient.
3. **Control Plane durability:** decide whether challenge plus Audit is enough
   or a narrow provisioning-orchestration row is also necessary; no generic
   Job payload may substitute.

### Closed for the later Runtime implementation

- `psi_*` intent identity, five-minute TTL, 90-second bounded one-entry TTY
  input, hard expiry during typing, monotonic state machine;
- four exact UDS actions over the existing socket;
- Store schema v2 and crash-safe local migration;
- one atomic counter/envelope/intent commit;
- live and recovered verification modes;
- exact attestation, 24-hour retention, replay rejection, and orphan behavior.

### Deferred beyond initial provisioning

Rotation, revocation, orphan deletion, key rotation, Provider validation,
broker use, activation, export/import, and multi-Runtime credential semantics
remain separate reviews.

## 28. Final Authorization Decision

**BLOCKED**

The 16 critical questions A–P have concrete answers in this document, but
answers B, C, and G expose missing repository prerequisites rather than a safe
no-migration implementation path:

- one Credential is bound to one Runtime Store through an explicit durable
  RuntimeInstallation relation;
- the current ProviderCredential schema is insufficient;
- an additive Control Plane migration is required;
- Runtime Store v1 evolves explicitly to v2;
- the intent state machine and UDS actions are frozen;
- no implemented approval primitive currently meets the contract;
- reconciliation failure produces a retained unusable orphan;
- crash-after-commit recovery uses exact AEAD reopen with a distinct mode;
- expiry is a hard input deadline; timeout is 90 seconds; input is single-entry;
- AgentBox makes no claim that a terminal can prevent paste;
- the wrap counter and envelope commit atomically;
- attestation is single-use and retained for 24 hours subject to the stated
  reconciled retry floor.

Neither Slice 3.2a nor Slice 3.2b is implementation-authorized by this review.
The next governance action is a focused architecture/security review of the
additive Control Plane ownership and confirmation foundation. No provisioning
implementation may begin until that prerequisite is accepted and separately
authorized.
