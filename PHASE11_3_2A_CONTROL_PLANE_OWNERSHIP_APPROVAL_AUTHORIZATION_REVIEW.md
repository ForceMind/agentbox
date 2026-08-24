# AgentBox Phase 11 Slice 3.2a — Control Plane Ownership & Approval Foundation

**Review type:** documentation-only architecture, security, and prospective
implementation-authorization review

**Authoritative baseline:** `7690a77431693716c12cace9d21304b1016dcbe7`

**Review date:** 2026-08-24

**Prospective implementation decision:** **AUTHORIZED**, subject to the merge
and human-review gates in §32. This document authorizes no implementation.

## 1. Final decision

Slice 3.2a has an implementation-ready Control Plane contract. A future,
separately instructed implementation may add one migration and non-secret
services for:

1. immutable `ProviderCredential` ownership by one `RuntimeInstallation`;
2. a durable, typed, Session-bound, five-minute `ConfirmationChallenge`;
3. a narrow `ProviderSecretProvisioningAttempt` recovery record created in the
   same transaction that consumes the challenge.

The contract deliberately rejects an upgrade containing any pre-`0005`
Credential row. It never guesses a Runtime owner. `ConfirmationChallenge` plus
`AuditEvent` is not sufficient because neither is an authoritative mutable
record for the crash window after approval consumption and before Runtime
authorization.

## 2. Authoritative baseline

The review began only after confirming all of the following:

- local `main`, `origin/main`, and `HEAD` were the authoritative SHA above;
- PR #38 was merged as that SHA and there were no open PRs;
- the working tree was clean and no Slice 3.2a branch existed;
- Alembic had exactly one head, `0004_phase11_provider_core`, and no `0005`;
- the canonical registry still contained 72 Accepted decisions, with
  `P11-ADR-010`, `020`, `050`, and `060` reserved.

Repository code and merged governance are authoritative where older planning
text describes an unimplemented `ConfirmationChallenge` as if it existed.

## 3. Current repository evidence

| Evidence | Current fact | Consequence |
|---|---|---|
| `provider_credentials` | columns are `id`, `provider_id`, `kind`, `runtime_secret_ref`, `secret_version`, `state`, `revision`, `created_at`, `updated_at` | no Runtime owner exists |
| `uq_provider_credentials_provider` | globally unique on `provider_id` | prevents one Provider from having independent Runtime credentials |
| Credential foreign keys | `provider_id -> provider_definitions.id`; profile uses `(credential_id, provider_id)` | database permits a profile for Runtime A to select a Credential intended for Runtime B |
| `RuntimeInstallation` | `rti_*`, `runtime_type`, `display_name`, integer `revision >= 1`, timestamps; `(id, runtime_type)` is unique | exact Runtime ID/type/revision can be bound |
| Credential creation | `CredentialMetadataCreate(provider_id, kind)` creates `MISSING`, null reference/version, revision 1 | future create must require Runtime and revisions |
| exposure | Provider repository methods are internal; no Provider/Credential API, Web, or CLI route exists | pre-`0005` Credential rows are development/internal metadata, not an externally provisioned Secret contract |
| profile validation | `_profile_credential` checks Provider, revision, Secret version, and `CONFIGURED`, but not Runtime | service bypass is presently possible |
| Session | `ses_*`; keyed token/CSRF digests, `created_at`, idle/absolute expiry, nullable `revoked_at` | current recent auth is only login time |
| re-authentication | no explicit re-auth endpoint/service; `authenticated_at = sessions.created_at`; login creates a new Session | `0005` must add a durable re-auth epoch and timestamp |
| Session invalidation | logout sets `revoked_at`; password change/recovery revokes active Sessions; cleanup deletes old rows | challenge eligibility must join the exact Session and protect referenced rows from pruning |
| Audit | flat metadata, at most 16 keys; scalar null/bool/int or string up to 256; sensitive-looking keys rejected; strings redacted | Slice-specific key allowlists must be stricter than the generic sanitizer |
| Job | generic `payload_json`, digest idempotency, resource lock, bounded attempts, lease and heartbeat | useful for ordinary work, but not approval or provisioning authority |
| SQLite writes | repository convention is a bounded transaction with explicit `BEGIN IMMEDIATE` for serialized mutations | issue/cancel/consume/prune use the same convention |
| identifiers | `new_identifier(prefix)` uses `secrets.token_hex(16)`; repository validation uses a three-letter prefix plus 32 lowercase hex | new IDs retain 128 bits of CSPRNG entropy |
| retention | terminal Jobs/Audit/login buckets/Sessions have bounded cleanup; active work is preserved | challenge and attempt cleanup must be bounded and dependency-aware |
| migration | SQLite foreign keys are enabled; `0004` uses named constraints, table invariants, and triggers | `0005` uses explicit rebuilds and schema verification |
| challenge | no model, migration, repository, API, CLI, UI, or test exists | an Audit row, request ID, Job lease, or digest cannot substitute |

## 4. Accepted ADR mapping

This review adds no ADR and changes no Accepted decision. It applies:

| Decisions | Application |
|---|---|
| P11-ADR-001–009 | Provider, Credential, Runtime/Profile/Binding/Session identities stay distinct; Claude stays outside Provider Manager |
| P11-ADR-011–019 | capability evidence cannot authorize mutation; Runtime UDS remains the later execution transport |
| P11-ADR-021–030 | Runtime is sole Secret authority; Control Plane stores only typed metadata and opaque references; local provisioning remains outside ordinary Web/API Secret ingress |
| P11-ADR-031–041 | planning, authorization, execution, transaction state, and reconciliation remain distinct and recoverable |
| P11-ADR-042–059 | validation/dry-run evidence does not provision or activate and carries no Secret |
| P11-ADR-061–070 | Runtime Binding and Remote/pairing stay independent from Provider credentials |
| P11-ADR-071–076 | public evidence, fixed managed scope, cryptography, custody, recovery, and implementation governance remain unchanged |

## 5. Scope

The future Slice 3.2a implementation is limited to the planned `0005`, ORM and
repository/service support for the three models above, explicit same-Session
re-authentication, allowlisted Audit events, retention, and tests. It may create
an `AUTHORIZED` non-secret provisioning attempt while consuming an approval.

## 6. Explicit non-scope

Slice 3.2a contains no plaintext or ciphertext Secret, Runtime Store access,
Store v1-to-v2 migration, TTY input, Runtime provisioning UDS action, Provider
request, credential broker, config access/mutation, `MISSING -> CONFIGURED`,
validation, activation, Runtime restart, rollback, rotation, revocation,
deletion, export/import, Claude Provider management, or Root Helper change.

## 7. Trust-boundary statement

```text
Control Plane decides and durably records one exact authorization.
Runtime executes a later separately authorized typed operation.
Root Helper performs only its existing fixed lifecycle actions.
```

The Browser never supplies a Secret or arbitrary command. Web/API/Worker never
read Runtime HOME, plaintext/ciphertext, keys, nonces, tags, wrapped DEKs, or
AAD. A fully compromised Control Plane application identity/database can forge
Control Plane workflow state; this design provides replay/race integrity, not
resistance to that full compromise. A fully compromised `agentbox-runtime` UID
retains the Accepted ability to forge Runtime-local evidence and compromise
Runtime-usable Provider Secrets.

## 8. Current schema insufficiencies

The global Provider uniqueness constraint conflates Provider and Store scope.
Adding only `runtime_installation_id` would still allow the existing profile FK
to cross Runtime ownership. Service validation alone would not cover direct DB
mutation. The current Session row has no durable explicit re-auth event. Audit
is immutable history, while a consumed approval needs a recoverable current
workflow owner. Generic Job JSON is intentionally too broad for that authority.

## 9. Credential Runtime ownership decision

The exact V1 invariant is:

```text
one ProviderCredential = one RuntimeInstallation = one Runtime-local Secret Store
```

`provider_credentials.runtime_installation_id` is `String(40) NOT NULL`, with
`FOREIGN KEY ... REFERENCES runtime_installations(id) ON DELETE RESTRICT` named
`fk_provider_credentials_runtime_installation`. It is never inferred.

The rebuilt table has:

- `UNIQUE(id, provider_id, runtime_installation_id)` named
  `uq_provider_credentials_runtime_identity`;
- `UNIQUE(provider_id, runtime_installation_id, kind)` named
  `uq_provider_credentials_provider_runtime_kind`;
- index `ix_provider_credentials_runtime_installation_id` on the owner;
- the existing state/reference, reference grammar, and revision checks;
- trigger `trg_provider_credentials_runtime_immutable`, a `BEFORE UPDATE OF
  runtime_installation_id` trigger that executes
  `RAISE(ABORT, 'credential runtime ownership is immutable')` when
  `NEW.runtime_installation_id <> OLD.runtime_installation_id`.

The old `uq_provider_credentials_provider` and
`uq_provider_credentials_id_provider` are removed. No repository update method
accepts an owner. ORM relationships are view-only for navigation; the trigger
is the database enforcement against direct SQL. Moving ownership requires a
later separately authorized migration and never copies or rebinds a `sec_*`.

Cross-Runtime profile creation and direct insertion fail with a database
foreign-key error, normalized by the future service to
`PROVIDER_CREDENTIAL_RUNTIME_MISMATCH`. The public error does not reveal the
actual owner.

## 10. Cardinality decision

| Question | Frozen answer |
|---|---|
| Multiple Credentials for different Providers on one Runtime? | Yes, one per `(provider_id, runtime_installation_id, kind)` |
| Multiple Credentials for the same Provider on one Runtime? | No in V1; `API_KEY` is the only kind and the composite unique constraint rejects ambiguity |
| Same Provider on multiple Runtimes? | Yes, separate `crd_*` rows and separate Runtime Stores |
| Uniqueness scope? | exact `(provider_id, runtime_installation_id, kind)` |
| More than one API key for a Provider/Runtime pair? | No |
| Claude owner eligibility? | No; create requires `RuntimeType.CODEX` and `ProviderManagedAdapter.CODEX` |

## 11. Runtime/Profile/Credential relational integrity

`runtime_provider_profiles` is rebuilt. Its current
`fk_runtime_profiles_credential_provider` is replaced by:

```text
FOREIGN KEY (
  credential_id, provider_id, runtime_installation_id
) REFERENCES provider_credentials (
  id, provider_id, runtime_installation_id
) ON DELETE RESTRICT
```

The name is `fk_runtime_profiles_credential_runtime_identity`. The existing
`uq_runtime_provider_profiles_identity` and installation/adapter FK remain.
The nullable composite FK retains profiles without credentials; whenever
`credential_id` is non-null, existing all-or-none snapshot checks plus service
validation require an exact same-Runtime Credential. The profile insert/update
validation triggers are recreated against the rebuilt table.

## 12. Credential creation contract

Future `CredentialMetadataCreate` contains exactly:

| Field | Type/constraint |
|---|---|
| `provider_id` | valid `prv_*` |
| `provider_revision` | positive integer, exact current revision |
| `provider_state` | closed `ProviderLifecycleState`; current value must match and be `CONFIGURED` or `VALIDATED` |
| `runtime_installation_id` | valid `rti_*` |
| `runtime_installation_revision` | positive integer, exact current revision |
| `runtime_type` | exactly `RuntimeType.CODEX` |
| `kind` | exactly `CredentialKind.API_KEY` |

Creation runs one `BEGIN IMMEDIATE` transaction: validate IDs; reload Runtime
and Provider; compare type/state/revisions; reject disabled/ineligible/missing
entities; insert owner-bound Credential with `state=MISSING`, revision 1,
`runtime_secret_ref=NULL`, `secret_version=NULL`; record
`provider_credential.created`; flush and commit. It does not create/invent a
Secret or `sec_*`, contact Runtime/Provider, or create Profile/Binding/activation.

## 13. Existing-row migration decision

Upgrade is permitted only when this exact preflight returns zero:

```sql
SELECT COUNT(*) FROM provider_credentials;
```

Any nonzero result raises the normalized migration error
`PHASE11_0005_LEGACY_CREDENTIALS_PRESENT` before DDL. This single rule covers
valid `MISSING` rows, malformed duplicates, unexpected state/reference/version,
profile references, and databases with zero, one, or many Runtimes. Runtime
count and display/type never influence ownership. Nothing is assigned,
duplicated, converted, deleted, or synthesized.

Recovery is fail-closed: keep the pre-upgrade application/database backup,
inspect only non-secret metadata with the prior release, and obtain a separate
operator/governance authorization to remove unused `MISSING` metadata and any
dependent profiles or to define an explicit adoption migration. Slice 3.2a
does not expose that deletion/adoption. This is acceptable because Credential
creation is not exposed by current API/UI/CLI and no current Secret provisioning
can have made a valid non-`MISSING` row.

## 14. Exact planned Alembic `0005` contract

| Item | Frozen value |
|---|---|
| revision | `0005_phase11_control_plane_ownership_approval` |
| filename | `migrations/versions/0005_phase11_control_plane_ownership_approval.py` |
| `down_revision` | `0004_phase11_provider_core` |
| rebuilt tables | `provider_credentials`, `runtime_provider_profiles`, `sessions` |
| new tables | `confirmation_challenges`, `provider_secret_provisioning_attempts` |
| untouched tables | all others, including `audit_events`, `jobs`, Provider/Binding/evidence tables |

Upgrade ordering is exact:

1. assert `PRAGMA foreign_keys=ON`; run `PRAGMA foreign_key_check` and require no
   rows; validate the sole Alembic predecessor;
2. execute the §13 Credential preflight and validate all existing Session IDs,
   timestamps, auth ownership, and no unexpected schema objects involved in the
   rebuild;
3. disable FK enforcement only outside an active transaction, confirm it is
   `0`, and begin one SQLite `BEGIN IMMEDIATE` migration transaction;
4. rebuild `provider_credentials` empty with §9 constraints and trigger;
5. rebuild `runtime_provider_profiles` with the §11 FK and recreate every
   existing constraint/index/validation trigger byte-for-contract;
6. rebuild `sessions`, adding `recent_authenticated_at DateTime(timezone=True)
   NOT NULL`, `auth_epoch Integer NOT NULL DEFAULT 1`, check
   `ck_sessions_auth_epoch` (`auth_epoch >= 1`), and check
   `ck_sessions_recent_auth_bounds` (`recent_authenticated_at >= created_at AND
   recent_authenticated_at <= last_seen_at`); existing rows receive
   `recent_authenticated_at=created_at`, `auth_epoch=1`;
7. create the two exact tables, indexes, and triggers in §§15 and 24;
8. validate row counts and copied Session values, run `PRAGMA foreign_key_check`
   against the new schema, validate required `sqlite_master` inventory, then
   commit;
9. re-enable FK enforcement outside the transaction, require `PRAGMA
   foreign_keys=1`, run `foreign_key_check` and `quick_check`, and verify the
   Alembic revision.

Any preflight/DDL/copy/verification failure rolls back the whole migration and
preserves `0004`. Failure to re-enable or verify foreign keys fails the upgrade;
the installer restores its verified database backup under existing lifecycle
rules. A fresh database upgrades through the same empty path.

## 15. `ConfirmationChallenge` identity and schema

`ConfirmationChallenge` maps to `confirmation_challenges`. ID is server-only
`cch_<32 lowercase hexadecimal characters>`, `String(40)`, generated by
`new_identifier("cch")` from `secrets.token_hex(16)`. A primary-key collision
retries generation at most three times inside the issue operation; a fourth
collision returns `APPROVAL_UNAVAILABLE` with no partial row.

`ConfirmationPurpose` is a Python `StrEnum`; its only V1 member is
`PROVIDER_SECRET_PROVISION = "provider_secret_provision"`. Adding a member
requires code, schema, security, and migration review.

| Column | Exact contract |
|---|---|
| `id` | `String(40)` PK, `cch_*` check |
| `schema_version` | integer, non-null, exactly 1 |
| `purpose` | closed enum, non-null |
| `state` | closed enum: `issued`, `consumed`, `cancelled`, `expired` |
| `admin_user_id` | `String(40)` FK `admin_users.id`, `RESTRICT` |
| `control_plane_session_id` | `String(40)` FK `sessions.id`, `RESTRICT` |
| `auth_epoch` | integer >=1 |
| `recent_authenticated_at` | UTC datetime, non-null |
| `issue_request_id` | `String(72)`, non-null, request-ID grammar |
| `runtime_installation_id` | `String(40)` FK Runtime, `RESTRICT` |
| `runtime_installation_revision` | integer >=1 |
| `runtime_type` | closed enum, exactly `codex` |
| `provider_id` | `String(40)` FK Provider, `RESTRICT` |
| `provider_revision` | integer >=1 |
| `provider_state` | closed Provider lifecycle enum; `configured` or `validated` |
| `credential_id` | `String(40)` non-null |
| `credential_revision` | integer >=1 |
| `credential_kind` | closed enum, exactly `api_key` |
| `credential_state` | closed enum, exactly `missing` |
| `expected_runtime_secret_ref` | `String(40)`, constrained `IS NULL` |
| `expected_secret_version` | integer, constrained `IS NULL` |
| `credential_runtime_installation_id` | `String(40)`, must equal Runtime ID |
| `intended_state` | closed value exactly `configured` |
| `intended_secret_version` | integer exactly 1 |
| `confirmation_verifier` | lowercase hex SHA-256 HMAC, `String(64)` |
| `approval_digest` | lowercase SHA-256 hex, `String(64)` |
| `issued_at` | UTC datetime, non-null |
| `expires_at` | UTC datetime, exactly issued + 300 seconds |
| `last_observed_at` | UTC datetime, non-null, initially issue time |
| `cancellation_epoch` | integer >=0, initially 0 |
| `terminal_at` | UTC datetime, null only while issued |
| `consumed_at` | UTC datetime, non-null only when consumed |
| `consumed_request_id` | `String(72)`, non-null only when consumed |
| `terminal_result_code` | `String(80)`, closed service-written value, null while issued |

Named constraints include
`fk_confirmation_challenges_credential_runtime_identity` over
`(credential_id, provider_id, credential_runtime_installation_id)`,
`fk_confirmation_challenges_admin_user`,
`fk_confirmation_challenges_session`,
`fk_confirmation_challenges_runtime_installation`, and
`fk_confirmation_challenges_provider`, all `ON DELETE RESTRICT`, plus
`ck_confirmation_challenges_id`, `ck_confirmation_challenges_schema`,
`ck_confirmation_challenges_timestamps`, `ck_confirmation_challenges_terminal`,
`ck_confirmation_challenges_expected_missing`, and
`ck_confirmation_challenges_runtime_owner`. Indexes are
`ix_confirmation_challenges_session_state`,
`ix_confirmation_challenges_credential_state`, and
`ix_confirmation_challenges_terminal_at`.

No arbitrary JSON/metadata, command, path, environment, endpoint, Secret,
ciphertext, key, nonce, tag, wrapped DEK, or AAD column exists.

## 16. Challenge state machine

```text
ISSUED --consume--> CONSUMED (terminal)
ISSUED --cancel-->  CANCELLED (terminal)
ISSUED --now >= expires_at / cleanup--> EXPIRED (terminal)

CONSUMED  --any transition--> reject
CANCELLED --any transition--> reject
EXPIRED   --any transition--> reject
```

Expiry is both time-derived and durably materialized on the next access or
cleanup. There is no renewal, extension, reissue-in-place, deletion on cancel,
or return to `ISSUED`.

## 17. Actor, Session, and recent-auth binding

`0005` adds the Session fields in §14. Ordinary login creates a new Session
with `auth_epoch=1` and `recent_authenticated_at=created_at`. Explicit re-auth
verifies the current password outside the transaction, then uses `BEGIN
IMMEDIATE` to reload the exact active Session/Admin and unchanged password hash,
increments `auth_epoch`, and sets `recent_authenticated_at=now`; it does not
rotate the Session. Issue binds both values and requires re-auth freshness no
greater than five minutes.

Consumption requires the same `session.id`, `user_id`, `auth_epoch`, and
`recent_authenticated_at`. A newer re-auth changes the epoch and makes the old
challenge stale. A different Session for the same Admin cannot consume it.
Login never inherits it. Logout, explicit revocation, active-Session eviction,
password change, and recovery cancel all that Session's `ISSUED` challenges in
the same serialized transaction before/while setting `revoked_at`. Inactive
Admin, expired/idle-expired/revoked/missing Session, or pruned Session makes
consumption fail.

Session cleanup first materializes/cancels referenced challenges and cannot
delete a Session while any retained challenge/attempt FK remains. It reports
contention rather than bypassing `RESTRICT`. Raw tokens, hashes, CSRF, and
passwords never enter either new table.

## 18. Exact canonical approval digest

Purpose: integrity-bind the exact operator-reviewed provisioning plan. It is
not a Secret, bearer token, signature, durable authority replacement, or proof
against full Control Plane compromise.

Specification:

- domain bytes: UTF-8
  `AgentBox\u0000provider-secret-provision-approval\u0000v1\u0000`;
- document schema: `agentbox.provider-secret-provision-approval.v1`;
- canonicalization: RFC 8785 using the repository's pinned `rfc8785` primitive;
- digest: SHA-256 of `domain bytes || canonical JSON bytes`;
- output: exactly 64 lowercase hexadecimal ASCII characters, no prefix/padding;
- comparison: `hmac.compare_digest` on validated ASCII encodings.

The canonical object contains exactly these lexicographically canonicalized
keys: `schema`, `challenge_id`, `purpose`, `admin_user_id`,
`control_plane_session_id`, `auth_epoch`, `recent_authenticated_at`,
`issue_request_id`, `runtime_installation_id`,
`runtime_installation_revision`, `runtime_type`, `provider_id`,
`provider_revision`, `provider_state`, `credential_id`, `credential_revision`,
`credential_kind`, `credential_state`, `expected_runtime_secret_ref`,
`expected_secret_version`, `credential_runtime_installation_id`,
`intended_state`, `intended_secret_version`, `issued_at`, `expires_at`,
`cancellation_epoch`, and `confirmation_verifier`.

Nulls are JSON `null`; enums use exact lowercase database values; integers are
JSON integers; timestamps are UTC RFC 3339 with exactly six fractional digits
and terminal `Z` (for example `2026-08-24T00:00:00.000000Z`). Strings are UTF-8
JSON strings. Both challenge ID and issue/expiry times are included. Python
`repr`, insertion order, locale formatting, concatenated field strings, NaN,
Infinity, and non-canonical JSON are prohibited. The raw canonical document is
not persisted outside its typed columns and never enters Audit/logs.

## 19. Typed confirmation decision

`PROVIDER_SECRET_PROVISION` requires exact ASCII:

```text
PROVISION <CredentialID>
```

For a valid `crd_*`, the value is exactly 46 ASCII characters. No trim,
case-fold, Unicode normalization, alternate whitespace, or localization is
accepted. The server stores only:

```text
HMAC-SHA-256(
  application_secret,
  UTF8("AgentBox\0provider-secret-confirmation\0v1\0" + challenge_id + "\0" + value)
)
```

encoded as 64 lowercase hex characters. Verification uses
`hmac.compare_digest`. One mismatch atomically changes `ISSUED -> CANCELLED`
with `terminal_result_code=CONFIRMATION_MISMATCH`; retry requires a new
challenge. Plain confirmation text never enters Audit/logs. The future Runtime
TTY Provider API key is unrelated and can never be this value.

## 20. Issue transaction

One `BEGIN IMMEDIATE` transaction performs, in order:

1. authenticate exact active Admin/Session and validate CSRF/Origin/Host at API
   boundary;
2. require Session `auth_epoch` and `recent_authenticated_at` freshness;
3. reload Runtime, Provider, Credential and exact revisions/type/state/kind;
4. require Credential owner equals Runtime and null reference/version;
5. expire stale outstanding challenges/attempts for this Credential;
6. reject any still-active challenge or provisioning attempt;
7. generate `cch_*`, timestamps, verifier, and exact digest;
8. insert `ISSUED` challenge;
9. write `provider_secret.challenge_issued` Audit; commit.

Issuance creates no attempt, `psi_*`, Runtime call, Secret, Profile, or Binding.

## 21. Cancellation transaction

Only the issuing Admin in the exact issuing Session may explicitly cancel;
recent auth is not required to abort. In one `BEGIN IMMEDIATE`, reload and
validate the binding, apply clock policy, and conditionally update
`ISSUED -> CANCELLED`, increment `cancellation_epoch`, set terminal fields, and
write `provider_secret.challenge_cancelled`. A repeat by the same issuer is
idempotent and returns the same generic cancelled result without another Audit.
Wrong actor/Session/unknown ID returns the generic error in §23. Consumption
already won returns `APPROVAL_ALREADY_FINAL`; expiry is materialized and returns
the same. Cancellation never deletes evidence.

## 22. Atomic consumption and idempotency

One `BEGIN IMMEDIATE` transaction performs exactly:

1. validate ID grammar and load the exact challenge;
2. validate schema and purpose;
3. require `ISSUED`, apply clock/expiry, and validate actor/Session binding;
4. require exact Session auth epoch/recent-auth marker and freshness;
5. reload Runtime and compare ID/revision/type;
6. reload Provider and compare ID/revision/state;
7. reload Credential and compare ID/revision/state/kind, owner, and null
   reference/version;
8. rebuild and constant-time compare the approval digest;
9. verify typed confirmation; mismatch cancels as §19;
10. generate one `psa_*` attempt ID and one `psi_*` future Runtime intent ID;
11. insert the exact `AUTHORIZED` orchestration row;
12. atomically set challenge `CONSUMED`, timestamps/request ID/result; the
    attempt's unique `challenge_id` is the reverse relationship;
13. write challenge-consumed and attempt-created Audit events; commit.

A second consumer cannot satisfy the conditional state update. Cancellation
and consumption serialize; exactly one terminal transition commits. Any busy
timeout returns `APPROVAL_UNAVAILABLE`; process crash, exception, or rollback
leaves both the `ISSUED` challenge and absence of an attempt, or commits both
consumption and attempt—never half of either.

Idempotency is authoritative by challenge ID: after a committed consumption,
the same Session/request may retrieve the existing non-secret attempt status,
but no call reports a second success or creates another attempt. A different
request/Session gets the generic final-state rejection. Caller chooses no ID,
timestamp, state, actor, revision, digest, or result.

## 23. Expiry, clock, replay, and enumeration policy

The server fixes `expires_at = issued_at + 300 seconds`. Effective eligibility
ends at the earliest of that time, Session idle/absolute expiry or revocation,
recent-auth time + 300 seconds, explicit cancellation, auth epoch change, Admin
deactivation, or any bound entity mismatch/revision change. At equality
`now >= expires_at`, consumption fails. UTC-aware datetimes are persisted; the
application clock supplies a single transaction `now`, normalized to six-digit
UTC. Restart does not change persisted deadlines.

Within every challenge mutation, if `now < issued_at` or
`now < last_observed_at`, the transaction cancels an issued challenge with
`CLOCK_ROLLBACK_DETECTED`; it never grants extra lifetime. Otherwise it updates
`last_observed_at=now`. Monotonic time may bound one process wait but is not
persisted authority. Database comparisons use normalized UTC values, not
SQLite locale strings.

Malformed/unknown ID, wrong purpose/actor/Session, expired/cancelled/consumed,
digest/confirmation mismatch, stale entity revision, wrong owner, and duplicate
race expose only:

| Public code | Use |
|---|---|
| `APPROVAL_INVALID` | malformed, unknown, wrong purpose/actor/Session/digest/confirmation |
| `APPROVAL_EXPIRED` | authenticated issuer reaches an expired effective boundary |
| `APPROVAL_STALE` | authenticated issuer's bound entity/auth revision is stale |
| `APPROVAL_ALREADY_FINAL` | authenticated issuer reaches a terminal row |
| `APPROVAL_CONFLICT` | one-active-attempt or concurrent winner conflict |
| `APPROVAL_UNAVAILABLE` | busy timeout, clock rollback, or internal fail-closed result |

HTTP status and response size are normalized per code. No response reveals an
owner, target, terminal result, or whether an arbitrary ID exists. Future UI
maps these English codes to Simplified Chinese.

## 24. Control Plane orchestration durability

`ConfirmationChallenge + AuditEvent` is insufficient. The challenge proves
one approval was consumed; Audit cannot be queried/updated as workflow
authority. A crash immediately after consumption otherwise loses whether a
Runtime intent was generated/sent. Generic Job retry/payload semantics cannot
represent Runtime attestation and must not authorize provisioning.

The exact model is `ProviderSecretProvisioningAttempt`, table
`provider_secret_provisioning_attempts`. ID is server-generated
`psa_<32 lowercase hex>`, `String(40)`. `provisioning_intent_id` is
server-generated `psi_<32 lowercase hex>`, `String(40)`, unique, and reserved
for the later Runtime contract.

| Column | Exact contract |
|---|---|
| `id` | `psa_*` PK |
| `schema_version` | integer exactly 1 |
| `purpose` | exactly `provider_secret_provision` |
| `state` | enum below |
| `challenge_id` | unique FK challenge, `RESTRICT` |
| `provisioning_intent_id` | unique `psi_*` |
| `admin_user_id`, `control_plane_session_id`, `auth_epoch` | copied exact authorization identity |
| Runtime ID/revision/type | exact challenge values |
| Provider ID/revision/state | exact challenge values |
| Credential ID/revision/kind/state/owner | exact challenge values |
| expected reference/version | constrained null |
| `approval_digest` | exact lowercase hex digest |
| `authorized_at`, `expires_at`, `updated_at` | UTC; expiry equals challenge expiry |
| `runtime_staged_at`, `runtime_verified_at`, `reconciled_at`, `terminal_at` | nullable typed transition times |
| `runtime_attestation_code` | nullable closed `String(80)`, never raw output |
| `terminal_result_code` | nullable closed `String(80)` |

No arbitrary JSON, Job ID/payload, Secret-shaped field, endpoint, command,
path, environment, Store path, ciphertext, cryptographic material, raw
attestation, or exception exists.

```text
AUTHORIZED -> RUNTIME_STAGED -> RUNTIME_CONSUMING -> RUNTIME_VERIFIED -> RECONCILED
AUTHORIZED -> CANCELLED | EXPIRED
RUNTIME_STAGED -> CANCELLED | EXPIRED | NEEDS_ATTENTION
RUNTIME_CONSUMING -> NEEDS_ATTENTION
RUNTIME_VERIFIED -> RECONCILED | NEEDS_ATTENTION
```

`RECONCILED`, `CANCELLED`, `EXPIRED`, and `NEEDS_ATTENTION` are terminal in the
Control Plane. `RUNTIME_*` transitions belong to Slice 3.2b. Slice 3.2a may
create only `AUTHORIZED`, expire/cancel an unsent `AUTHORIZED`, and never
contact Runtime. No state regresses or extends expiry.

Named constraints/indexes are:

- `uq_provider_secret_attempts_challenge`;
- `uq_provider_secret_attempts_intent`;
- `fk_provider_secret_attempts_challenge`,
  `fk_provider_secret_attempts_admin_user`,
  `fk_provider_secret_attempts_session`,
  `fk_provider_secret_attempts_runtime_installation`,
  `fk_provider_secret_attempts_provider`, and
  `fk_provider_secret_attempts_credential_runtime_identity`, all `ON DELETE
  RESTRICT`;
- `ck_provider_secret_attempts_id`, `_intent_id`, `_schema`, `_expected_missing`,
  `_timestamps`, and `_state_timestamps`;
- partial unique index `uq_provider_secret_attempts_active_credential` on
  `credential_id WHERE state IN ('authorized','runtime_staged',
  'runtime_consuming','runtime_verified')`;
- indexes `ix_provider_secret_attempts_state_updated` and
  `ix_provider_secret_attempts_terminal_at`.

Crash-window recovery is exact:

| Window | Authority/recovery |
|---|---|
| issued, not consumed | challenge remains eligible until invalidated |
| consume rolls back | no attempt; challenge remains issued unless mismatch/expiry terminalization committed |
| consumed before Runtime authorization | impossible to lose intent: `AUTHORIZED` attempt and `psi_*` commit atomically |
| authorization never sent | later Slice 3.2b reads `AUTHORIZED`; after expiry marks `EXPIRED` without Runtime call |
| Runtime staged, response lost | later exact status by `psi_*`; never generate a replacement |
| Runtime consuming across restart | status/reconciliation only; no blind resend or second attempt |
| Runtime verified while Control Plane unavailable | retained `RUNTIME_VERIFIED`/Runtime attestation is reconciled against exact tuple |
| attestation received, CP crashes | state remains pre-transition or `RUNTIME_VERIFIED`; same attestation is conditionally idempotent |
| Credential update commits, acknowledgement lost | future exact status observes Credential revision/reference and repeats only acknowledgement |
| Session expires after consumption | status/reconciliation is system recovery against durable attempt, not a new authorization |
| challenge retention reached | FK protects it until attempt is terminal and independently retention-eligible |
| entity revision stale | attempt becomes `NEEDS_ATTENTION`; no rebinding |
| simultaneous attempts | partial unique index permits one active attempt per Credential |

## 25. Retention and pruning

An `ISSUED` challenge is never pruned. Cleanup first materializes expiry.
Terminal challenges are retained for exactly 30 days from `terminal_at`.
`RECONCILED`, `CANCELLED`, and `EXPIRED` attempts are retained for exactly 30
days from `terminal_at`; `NEEDS_ATTENTION` attempts are retained for exactly 90
days from `terminal_at`. `NEEDS_ATTENTION` is terminal, cannot be resumed, and
blocks a new attempt for that Credential during retention. Ninety days provides
a fixed operator investigation window without unbounded growth. Any future
Runtime evidence has its separately frozen Runtime retention and cannot become
usable merely because the non-secret Control Plane attempt aged out.

One maintenance run uses `BEGIN IMMEDIATE`, processes at most 100 rows ordered
by `(terminal_at, id)`, and:

1. marks at most 100 elapsed `ISSUED` challenges/`AUTHORIZED` attempts expired;
2. deletes at most 100 retention-eligible terminal attempts not required by
   Runtime reconciliation;
3. deletes at most 100 terminal challenges with no remaining attempt FK.

Only the existing internal maintenance owner may invoke it; no API parameter
sets cutoff/batch/order. One summary Audit event per category records only
`deleted_count`/`expired_count` (integers 0–100). Busy contention performs no
partial deletion and retries on the next scheduled run. FK `RESTRICT` prevents
unsafe order. Audit correlation remains under its existing independent
retention policy.

## 26. Downgrade contract

Downgrade to `0004` is permitted only if all predicates hold in one
`BEGIN IMMEDIATE` preflight:

```sql
SELECT COUNT(*) FROM provider_credentials;                    -- must be 0
SELECT COUNT(*) FROM confirmation_challenges;                 -- must be 0
SELECT COUNT(*) FROM provider_secret_provisioning_attempts;   -- must be 0
SELECT COUNT(*) FROM sessions WHERE auth_epoch <> 1
   OR recent_authenticated_at <> created_at;                  -- must be 0
PRAGMA foreign_key_check;                                     -- must return 0 rows
```

Otherwise downgrade raises `PHASE11_0005_DOWNGRADE_UNSAFE` before DDL. There is
no deletion, challenge collapse, Runtime-owner discard, or recreation of global
Provider uniqueness over violating data. With all predicates satisfied, drop
new tables, rebuild profiles/credentials/sessions exactly to `0004`, recreate
all `0004` indexes/triggers/constraints, verify counts/schema/FKs, commit,
re-enable FKs, and run `foreign_key_check`/`quick_check`. A verified backup is
required by deployment lifecycle before attempting downgrade. Feature use
therefore intentionally makes downgrade fail closed until separately authorized
data retirement has removed all new authority/evidence safely.

## 27. Audit allowlist

All events use existing bounded `AuditService`, plus a per-action key allowlist.
Actor is `admin_user` with Admin ID for issue/create/cancel/consume/reject;
maintenance/recovery uses `system`, null actor. Request ID is recorded in the
dedicated column, never duplicated as metadata.

| Action | Target | Results | Exact metadata keys |
|---|---|---|---|
| `provider_credential.created` | `provider_credential`/`crd_*` | `succeeded` | `runtime_installation_id` str≤40, `runtime_revision` int, `provider_id` str≤40, `provider_revision` int, `kind`=`api_key`, `state`=`missing`, `revision`=1 |
| `provider_secret.challenge_issued` | `confirmation_challenge`/`cch_*` | `succeeded` | Runtime/Provider/Credential IDs and revisions, `session_id` str≤40, `auth_epoch` int, `purpose`, `expires_at` str≤32, `approval_digest` 64-hex |
| `provider_secret.challenge_cancelled` | challenge | `succeeded` | `purpose`, `terminal_result_code`, Runtime/Provider/Credential IDs |
| `provider_secret.challenge_consumed` | challenge | `succeeded` | `provisioning_attempt_id`, `provisioning_intent_id`, Runtime/Provider/Credential IDs and revisions, `approval_digest` |
| `provider_secret.challenge_rejected` | challenge or null | `rejected` | `reason_code` from public closed codes; `id_well_formed` bool; no target tuple for unknown/wrong actor |
| `provider_secret.attempt_created` | `provider_secret_provisioning_attempt`/`psa_*` | `succeeded` | `challenge_id`, `provisioning_intent_id`, Runtime/Provider/Credential IDs and revisions, `state`=`authorized`, `approval_digest` |
| `provider_secret.attempt_transitioned` | attempt | `succeeded`, `failed`, `needs_attention` | `from_state`, `to_state`, `terminal_result_code` nullable, Runtime/Provider/Credential IDs, `provisioning_intent_id` |
| `provider_secret.challenge_pruned` | `confirmation_challenge`/null | `succeeded` | `deleted_count` int 0–100 |
| `provider_secret.attempt_pruned` | attempt/null | `succeeded` | `deleted_count` int 0–100 |
| `provider_secret.approval_expired` | challenge/attempt or null summary | `succeeded` | `expired_count` int 0–100 |
| `phase11_0005.migration_blocked` | `database`/null | `blocked` | `reason_code`, `credential_row_count` nonnegative int; emitted only when application-owned migration Audit is transactionally available, otherwise normalized installer log code only |

Audit/logs prohibit Secret value/prefix/suffix/hash/fingerprint/length,
ciphertext, root key, KEK/DEK, wrapped DEK, nonce, tag, AAD, terminal input,
Session token/hash, CSRF, password, confirmation plaintext, canonical document,
arbitrary JSON, raw exception, Runtime Store path, endpoint Authorization, or
Secret-shaped metadata keys. Opaque `sec_*` is not created in Slice 3.2a and is
not part of these events.

## 28. Threat-model mapping

Threats T-112 through T-129 in `docs/THREAT_MODEL.md` cover ambiguous legacy
adoption, cross-Runtime references, owner mutation, cardinality, challenge
forgery/replay/digest substitution, Session binding/revocation races,
cancellation/double consumption, revision TOCTOU, expiry/clock rollback,
enumeration, retention/pruning, false Audit/Job authority, crash atomicity,
migration/downgrade, and Secret-shaped generic metadata. The residual
Control Plane and Runtime compromises in §7 remain explicit.

## 29. Future Slice 3.2a implementation boundary

The future branch may change only the Control Plane migration/models/services,
auth re-auth/session invalidation integration, internal retention wiring,
protocol models needed for non-secret API responses, narrow API/CLI/UI approval
surfaces if separately enumerated by the implementation instruction, and tests.
It may not add or invoke a Runtime UDS action. It may end with one durable
`AUTHORIZED` attempt and no Runtime side effect.

## 30. Future implementation test matrix

The implementation gate requires, at minimum:

- fresh `0005`, `0004 -> 0005`, and rejected legacy-row upgrades for every §13
  state/runtime/profile combination;
- exact schema/constraint/index/trigger inspection and FK-on/off bypass tests;
- cross-Runtime profile direct SQL and repository rejection;
- owner update trigger, no update API, cardinality, Claude rejection, revision
  races, and all-or-none create/Audit tests;
- Session migration, login, explicit re-auth, newer epoch, logout, revocation,
  password reset, idle/absolute expiry, inactive Admin, pruning/FK tests;
- challenge ID entropy/grammar/collision, purpose closure, strict field inventory,
  digest golden vectors including Unicode/null/timestamp/integer cases;
- typed confirmation exactness, no plaintext logs/Audit, one-attempt mismatch;
- exact five-minute equality, restart, forward/backward clock, stale revisions,
  wrong owner/actor/Session/purpose, malformed/unknown ID normalization;
- concurrent consume/consume and consume/cancel with exactly one winner;
- fault injection before/after every consume/attempt/Audit statement and commit;
- one-active-attempt partial index, all §24 crash windows, no Job/Audit authority;
- retention limits/order/FK protection/contention and safe/unsafe downgrade;
- canary scans across SQLite/WAL/SHM, Audit, Job/Event, logs, API/OpenAPI,
  diagnostics, reports, Web storage, and exceptions;
- unchanged Runtime Store, Runtime protocol, Helper actions, dependencies, and
  canonical ADR registry.

## 31. Explicit Slice 3.2b dependency

Slice 3.2b remains blocked until the Slice 3.2a documentation is human-reviewed
and merged, a separate implementation instruction is issued, its exact
implementation passes review/CI and is merged, and the merge is read back.
Only then may a separate architecture/implementation authorization cover Store
v2, `psi_*` Runtime persistence, TTY input, UDS authorize/status/cancel/
reconciled, attestation, and `MISSING -> CONFIGURED` reconciliation.

## 32. Remaining blockers and implementation authorization

All architecture questions in this review are closed; no technical contract
blocker remains for the exact future Slice 3.2a implementation.

**Prospective decision: AUTHORIZED.** This becomes actionable only after this
documentation PR passes CI, Architecture Review, Security Review, recorded
human review, protected Squash Merge, merge read-back, and a new explicit owner
instruction. Until then:

- Slice 3.2a architecture review: in review;
- Slice 3.2a implementation: not started and not authorized to begin;
- Slice 3.2b implementation: not authorized;
- Secret provisioning: blocked.

## 33. Decision matrix

| Prompt issue | Decision location | Closed |
|---|---|---|
| 7.1 ownership | §§9, 11 | Yes |
| 7.2 cardinality | §10 | Yes |
| 7.3 relational integrity | §11 | Yes |
| 7.4 immutability | §9 | Yes |
| 7.5 creation | §12 | Yes |
| 7.6 existing rows | §13 | Yes |
| 7.7 planned `0005` | §§14, 26 | Yes |
| 8.1 identity | §15 | Yes |
| 8.2 purpose | §15 | Yes |
| 8.3 state machine | §16 | Yes |
| 8.4 typed binding | §15 | Yes |
| 8.5 actor/Session/recent auth | §17 | Yes |
| 8.6 expiry | §23 | Yes |
| 8.7 digest | §18 | Yes |
| 8.8 typed confirmation | §19 | Yes |
| 8.9 atomic consumption | §22 | Yes |
| 8.10 replay/enumeration | §23 | Yes |
| 8.11 cancellation | §21 | Yes |
| 8.12 retention/pruning | §25 | Yes |
| 9 orchestration durability | §24 | Yes |
| 10 Audit | §27 | Yes |
| 11 threat model | §28 and threat-model update | Yes |

## 34. Next authorized action

The only next action is **Human Architecture/Security Review of the Draft
documentation PR**. Implementation must not start in this execution.
