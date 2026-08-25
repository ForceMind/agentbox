# AgentBox Phase 11 Slice 3.2a — Control Plane Ownership & Approval Foundation

**Review type:** documentation-only architecture, security, and prospective
implementation-authorization review

**Authoritative baseline:** `7690a77431693716c12cace9d21304b1016dcbe7`

**Review date:** 2026-08-25

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

- the retained `UNIQUE(id, provider_id)` named
  `uq_provider_credentials_id_provider`;
- `UNIQUE(id, provider_id, runtime_installation_id)` named
  `uq_provider_credentials_runtime_identity`;
- `UNIQUE(provider_id, runtime_installation_id, kind)` named
  `uq_provider_credentials_provider_runtime_kind`;
- index `ix_provider_credentials_runtime_installation_id` on the owner;
- the existing state/reference, reference grammar, and revision checks;
- trigger `trg_provider_credentials_identity_immutable`, a `BEFORE UPDATE`
  trigger that executes
  `RAISE(ABORT, 'credential identity is immutable')` when any of
  `NEW.id IS NOT OLD.id`, `NEW.provider_id IS NOT OLD.provider_id`,
  `NEW.runtime_installation_id IS NOT OLD.runtime_installation_id`,
  `NEW.kind IS NOT OLD.kind`, or `NEW.created_at IS NOT OLD.created_at`.

Only the old global `uq_provider_credentials_provider` is removed.
`uq_provider_credentials_id_provider` must remain because the untouched
`provider_compatibility_evidence_sets` table has the parent FK
`(credential_id, provider_id) -> provider_credentials(id, provider_id)`;
SQLite requires those exact parent columns to remain unique. No repository
update method accepts or changes any Credential identity field. Future typed
lifecycle services may change only `state`, `runtime_secret_ref`,
`secret_version`, `revision`, and `updated_at`. Moving/reinterpreting identity
requires a later separately authorized migration and never copies or rebinds a
`sec_*`.

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

`provider_compatibility_evidence_sets` is not rebuilt. Its existing
`fk_compatibility_evidence_credential_provider` remains valid through the retained
`uq_provider_credentials_id_provider`; valid Credential/Provider evidence rows
continue to insert, and a nonexistent or mismatched pair fails at the database.

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
| future implementation support | `migrations/env.py` must implement the exact SQLite runner below; this documentation PR does not change it |
| untouched data tables | all others, including `audit_events`, `jobs`, Provider/Binding/evidence tables |

The exact online SQLite mechanism is a future reviewed `migrations/env.py`
change plus the deployment/installer admission fence described here. This
documentation PR changes neither file. The runner owns three distinct phases.

**Phase A — locked outer preflight with FK ON.** The updater holds its global
deployment/update lock, stops or fences API/Worker database writers, proves no
application migration is active, and opens a verified pre-migration SQLite
backup under the existing backup protocol. On an SQLAlchemy connection created
with `isolation_level="AUTOCOMMIT"`, it requires
`PRAGMA foreign_keys` to return `1`, `PRAGMA foreign_key_check` to return zero
rows, and `PRAGMA quick_check;` to return exactly one row whose value is `ok`.
It verifies predecessor `0004_phase11_provider_core`, exact source schema,
zero legacy Credentials, and the complete non-mutating Session preflight. It
then calls `connection.commit()` solely to clear SQLAlchemy autobegin and
requires `not connection.in_transaction()`.

**Phase B — FK OFF plus one locked migration transaction.** Outside any SQLite
transaction it sets `PRAGMA foreign_keys=OFF`, requires the returned value `0`,
clears SQLAlchemy autobegin, and again proves no transaction is active. Alembic
is configured on that connection with `transactional_ddl=True` and without
`context.begin_transaction()`. Driver SQL opens exactly one `BEGIN IMMEDIATE`.
Inside that lock, the runner/revision rechecks predecessor version, exact source
schema, legacy Credential count, Session preflight, and every mutable data/schema
predicate from Phase A. The revision requires `foreign_keys=0`, performs all
rebuild/copy/index/trigger work, and returns. `context.run_migrations()` performs
the normal Alembic version update in this same transaction. Before driver
`COMMIT`, the runner requires copied counts, exact schema/constraint/index/
trigger inventory, empty `PRAGMA foreign_key_check`, exactly one `ok` row from
`PRAGMA quick_check;`, and exactly one version row equal to
`0005_phase11_control_plane_ownership_approval`. Any exception through this
point executes driver `ROLLBACK`; schema and version both remain `0004`.

**Phase C — post-commit verification and activation gate.** Outside the
transaction, re-enable FK and require `1`; repeat `foreign_key_check`,
`quick_check`, schema inventory, trigger inventory, and exact version check.
Only their success permits service activation. If commit succeeded but any
post-commit check fails, activation stays stopped; the installer restores the
verified backup with its WAL/SHM handling, verifies exact predecessor schema,
version and integrity, and does not blindly rerun `0005`.

The runner rejects offline SQL generation for `0005`; this contract is for the
online SQLite migration only. A failure after `COMMIT` but before all
post-commit checks is an uncertain/incomplete upgrade: the installer must stop
activation and restore its pre-migration verified SQLite backup, including
WAL/SHM handling, then verify `0004` before restarting the old release. It must
not run `0005` again blindly.

This final mechanism was rerun on 2026-08-25 with repository Alembic/SQLAlchemy
in a temporary `/tmp` tree. Success committed schema/version together. Injected
exceptions before the migration body, after DDL, and after version update but
before commit each restored exact `0004`. A simulated post-commit verification
failure stopped activation and restored the verified `0004` backup including
sidecar cleanup. FK re-enable/checks, exact `quick_check` row handling, retained
Compatibility Evidence valid/invalid child inserts, and trigger inventory all
passed. No prototype file entered Git.

Revision work inside Phase B is exact:

1. assert `PRAGMA foreign_keys=OFF`; validate the sole Alembic predecessor;
2. rerun the §13 Credential preflight and validate all existing Session IDs,
   timestamps, auth ownership, and no unexpected schema objects involved in the
   rebuild;
3. require that the runner's single SQLite `BEGIN IMMEDIATE` is active;
4. create `provider_credentials_new` with §9 constraints and trigger, copy the
   already-proven empty set, drop `provider_credentials`, then rename the new
   table to the canonical name without renaming the old parent (preserving
   untouched child FK target text);
5. rebuild `runtime_provider_profiles` with the §11 FK and recreate every
   existing constraint/index/validation trigger byte-for-contract;
6. rebuild `sessions`, adding `recent_authenticated_at DateTime(timezone=True)
   NOT NULL`, `auth_epoch Integer NOT NULL DEFAULT 1`, check
   `ck_sessions_auth_epoch` (`auth_epoch >= 1`), and check
   `ck_sessions_recent_auth_bounds` (`recent_authenticated_at >= created_at AND
   recent_authenticated_at <= last_seen_at`); existing rows receive
   `recent_authenticated_at=created_at`, `auth_epoch=1`; add
   `UNIQUE(id, user_id)` named `uq_sessions_id_user`;
7. create the two exact tables, indexes, and triggers in §§15 and 24;
8. validate row counts and copied Session values, exact retained/new unique
   keys, untouched Compatibility Evidence FK resolution, and required
   `sqlite_master` inventory; the runner then performs its in-transaction
   integrity/version checks and commit;
9. complete the runner's outside-transaction FK re-enable and post-commit
   verification.

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
| `intent_contract_version` | integer, non-null, exactly 1 |
| `purpose` | closed enum, non-null |
| `state` | closed enum: `issued`, `consumed`, `cancelled`, `expired` |
| `admin_user_id` | `String(40)`, bound with Session by composite FK |
| `control_plane_session_id` | `String(40)`, bound with Admin by composite FK |
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
| `provisioning_intent_id` | unique server-generated `psi_*`, `String(40)` |
| `issued_at` | UTC datetime, non-null |
| `created_at` | UTC datetime, non-null, exactly equal to `issued_at` |
| `expires_at` | UTC datetime, exactly issued + 300 seconds |
| `intent_issued_at` | UTC datetime, exactly equal to `issued_at` |
| `intent_expires_at` | UTC datetime, exactly equal to `expires_at` |
| `initial_cancellation_epoch` | integer exactly 0; immutable and digest-bound |
| `last_observed_at` | UTC datetime, non-null, initially issue time |
| `cancellation_epoch` | integer >=0, initially 0 |
| `terminal_at` | UTC datetime, null only while issued |
| `consumed_at` | UTC datetime, non-null only when consumed |
| `consumed_request_id` | `String(72)`, non-null only when consumed |
| `terminal_result_code` | exact nullable `ChallengeTerminalResultCode` enumerated below |
| `retention_eligible_at` | nullable immutable UTC6 database timestamp; null while active and exactly `terminal_at + 30 days` for every safe terminal Challenge |

Named constraints include
`uq_confirmation_challenges_id_intent` over
`(id, provisioning_intent_id)`, `uq_confirmation_challenges_intent` over the
single `provisioning_intent_id`,
`fk_confirmation_challenges_credential_runtime_identity` over
`(credential_id, provider_id, credential_runtime_installation_id)`,
`fk_confirmation_challenges_session_admin` over
`(control_plane_session_id, admin_user_id) -> sessions(id, user_id) ON DELETE
RESTRICT`,
`fk_confirmation_challenges_runtime_installation`, and
`fk_confirmation_challenges_provider`, all `ON DELETE RESTRICT`, plus
`ck_confirmation_challenges_id`, `ck_confirmation_challenges_schema`,
`ck_confirmation_challenges_timestamps`, `ck_confirmation_challenges_terminal`,
`ck_confirmation_challenges_expected_missing`, and
`ck_confirmation_challenges_runtime_owner`. ID checks require the exact
three-letter prefix plus 32 lowercase hex; verifier/digest checks require
exactly 64 lowercase hex. `ck_confirmation_challenges_terminal` encodes:
`ISSUED` has null terminal/consumption fields and null result;
`CONSUMED` has non-null `terminal_at`, `consumed_at`, consumed request, and
result `ATTEMPT_CREATED`; `CANCELLED`/`EXPIRED` have non-null `terminal_at`,
null consumption fields, and an allowed result for that state. Indexes are
`ix_confirmation_challenges_session_state`,
`ix_confirmation_challenges_credential_state`, and
`ix_confirmation_challenges_terminal_at`, plus partial unique index
`uq_confirmation_challenges_issued_credential` on `credential_id WHERE
state='issued'`.

`ChallengeTerminalResultCode` is exact:

| Python member / DB value | Eligible terminal state | Public mapping |
|---|---|---|
| `ATTEMPT_CREATED` | `CONSUMED` | success response only |
| `CANCELLED_BY_ISSUER` | `CANCELLED` | `APPROVAL_ALREADY_FINAL` after commit |
| `AUTH_EPOCH_ROTATED` | `CANCELLED` | `APPROVAL_STALE` |
| `SESSION_REVOKED` | `CANCELLED` | `APPROVAL_INVALID` |
| `ADMIN_DEACTIVATED` | `CANCELLED` | `APPROVAL_INVALID` |
| `CONFIRMATION_MISMATCH` | `CANCELLED` | `APPROVAL_INVALID` |
| `BOUND_ENTITY_STALE` | `CANCELLED` | `APPROVAL_STALE` |
| `CLOCK_ROLLBACK_DETECTED` | `CANCELLED` | `APPROVAL_UNAVAILABLE` |
| `DEADLINE_EXPIRED` | `EXPIRED` | `APPROVAL_EXPIRED` |

Database enforcement is exact:

- `trg_confirmation_challenges_binding_immutable` is `BEFORE UPDATE` and uses
  `IS NOT` comparisons to reject changes to ID, both schema versions, purpose,
  Admin/Session/auth tuple, issue request, Runtime tuple, Provider tuple,
  Credential tuple/owner, expected state/reference/version, postcondition,
  confirmation verifier, approval digest, `psi_*`, issue/intent timestamps,
  initial cancellation epoch, and creation timestamp; it also rejects any
  `retention_eligible_at` change after the row is terminal;
- `trg_confirmation_challenges_legal_transition` allows only
  `ISSUED -> CONSUMED|CANCELLED|EXPIRED` and rejects every terminal transition
  or return to `ISSUED`;
- `trg_confirmation_challenges_consumed_attempt` runs before
  `ISSUED -> CONSUMED` and requires exactly one attempt whose
  `(challenge_id, provisioning_intent_id)`, approval digest, and entire typed
  tuple equal the Challenge;
- `trg_confirmation_challenges_unresolved_attempt_guard` rejects every insert
  when that Credential has an Attempt in `authorized`, `runtime_staged`,
  `authorize_pending`, `cancel_pending`, `runtime_consuming`,
  `runtime_committed_unverified`, `runtime_verified`, or `needs_attention`;
- `trg_confirmation_challenges_delete_guard` rejects deletion when the state is
  `ISSUED`, an Attempt references the row, `retention_eligible_at` is null,
  `agentbox_now_utc6() < retention_eligible_at`, or terminal fields/result/
  retention boundary are inconsistent. A connection without the registered
  clock function cannot delete and therefore fails closed;
- table checks enforce terminal fields/result codes, timestamp equality,
  `expires_at = datetime(issued_at, '+300 seconds') || substr(issued_at,20,7)`
  and safe-terminal `retention_eligible_at = datetime(terminal_at,
  '+30 days') || substr(terminal_at,20,7)` under the exact §18A UTC6 storage,
  and cancellation epoch: 0 while
  `ISSUED`/`CONSUMED`/`EXPIRED`, exactly 1 for a directly cancelled Challenge.

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

`0005` adds the Session fields and `uq_sessions_id_user` in §14. Ordinary login
creates a new Session with `auth_epoch=1` and
`recent_authenticated_at=created_at`. Explicit re-auth keeps the durable
Session row ID so retained Challenge/Attempt FKs remain stable, but it must
rotate both browser credentials.

The future re-auth route is `POST /api/v1/auth/reauthenticate`. Its strict
request model contains only `password` with the same login password bounds and
rejects extras. Before expensive work it requires the exact authenticated
Session, exact Origin/Host, current Session-bound CSRF, the global 16 KiB
mutation-body limit, and the re-auth rate-limit decision. Re-auth uses the same
`BoundedLoginExecutor` semaphore limit and `asyncio.to_thread` Argon2 discipline
as login. Its purpose-separated persisted limiter keys are derived from
`reauth`, Admin ID, and effective source with the existing application-secret
keying; limits/window/lock and source trust rules are exactly the configured
login values. A locked bucket performs no Argon2 work. Pre-route authentication
failure uses the existing `INVALID_SESSION`; wrong password, inactive Admin, or
password-hash revalidation failure uses `INVALID_CREDENTIALS`; rate limit uses
`LOGIN_RATE_LIMITED` with the existing bounded retry; database/token-collision
failure uses `REAUTH_UNAVAILABLE`. These four identical uppercase member/wire
values are the complete `ReauthenticationPublicErrorCode` set for this route.

Password verification occurs outside a DB transaction. On success, one
`BEGIN IMMEDIATE` transaction reloads the exact `(session.id, user_id)`, active
Admin, non-revoked/non-expired Session, and unchanged password hash. It then:

1. generates a new raw 256-bit opaque Session token with at most three
   collision retries, stores only its new keyed `token_hash`, and fails
   `REAUTH_UNAVAILABLE` on a fourth collision;
2. derives the replacement CSRF value from the unchanged Session ID and new
   token hash and stores only the replacement keyed `csrf_hash`;
3. increments `auth_epoch`, sets `recent_authenticated_at=last_seen_at=now`,
   recomputes `idle_expires_at=min(original expires_at, now + configured idle
   TTL)`, and preserves the original absolute `expires_at`;
4. changes every `ISSUED` Challenge for that Session and prior auth epoch to
   `CANCELLED/AUTH_EPOCH_ROTATED` in the same transaction;
5. records `reauth_succeeded` and commits.

Only after commit does the no-store response replace the `HttpOnly`,
`SameSite=Strict`, `Path=/`, production-`Secure` Cookie and return the new CSRF
token. The old Cookie and old CSRF fail immediately because their stored
verifiers were replaced. A crash before commit leaves the old credentials and
epoch valid and exposes no new value; a crash after commit but before response
leaves the Session durably rotated, so both old browser credentials fail and
the operator must log in again. Raw token/CSRF/password never persist or log.

Exact Audit actions are `reauth_succeeded` (`succeeded`) and `reauth_failed`
(`failed`). Both target `auth_context` with no raw target ID and permit only
`auth_context_fingerprint` (24 lowercase hex), `source_fingerprint` (24
lowercase hex), and `reason`; success reason is `credentials_rotated`, failure
reason is one of `invalid_credentials`, `rate_limited`, `session_invalid`, or
`password_changed`. They contain no sensitive sanitizer substring.
`auth_context_fingerprint` is exactly
`keyed_digest(application_secret, "audit-auth-context",
control_plane_session_id)[:24]`; it is purpose-separated pseudonymous
correlation, not a token, token hash, Secret, or bearer value.

Consumption requires the same `session.id`, `user_id`, `auth_epoch`, and
`recent_authenticated_at`. A newer re-auth changes the epoch and makes the old
challenge stale. A different Session for the same Admin cannot consume it.
Login never inherits it. Logout, explicit revocation, active-Session eviction,
password change, and recovery cancel all that Session's `ISSUED` challenges in
the same serialized transaction before/while setting `revoked_at`. Inactive
Admin, expired/idle-expired/revoked/missing Session, or pruned Session makes
consumption fail.

Session cleanup is the priority-4 category inside the single §25
`BEGIN IMMEDIATE` maintenance union and its global 100-row total. Before a
Session can be selected, eligible issued Challenges are materialized/cancelled
by the earlier category. It deletes only retention-eligible Session rows
satisfying both
`NOT EXISTS (SELECT 1 FROM confirmation_challenges ...)` and `NOT EXISTS
(SELECT 1 FROM provider_secret_provisioning_attempts ...)`. It never bulk
deletes protected rows, bypasses `RESTRICT`, or lets one protected Session stop
unrelated eligible cleanup. Raw tokens, hashes, CSRF, and passwords never enter
either authority table.

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
`issue_request_id`, `provisioning_intent_id`, `intent_contract_version`,
`intent_issued_at`, `intent_expires_at`, `initial_cancellation_epoch`,
`runtime_installation_id`,
`runtime_installation_revision`, `runtime_type`, `provider_id`,
`provider_revision`, `provider_state`, `credential_id`, `credential_revision`,
`credential_kind`, `credential_state`, `expected_runtime_secret_ref`,
`expected_secret_version`, `credential_runtime_installation_id`,
`intended_state`, `intended_secret_version`, `issued_at`, `expires_at`,
`cancellation_epoch`, and `confirmation_verifier`. At issuance both
`initial_cancellation_epoch` and current `cancellation_epoch` are zero and both
are digest-bound; subsequent terminal cancellation changes only the current
epoch and cannot alter the already approved digest.

Nulls are JSON `null`; enums use exact lowercase database values; integers are
JSON integers; timestamps are UTC RFC 3339 with exactly six fractional digits
and terminal `Z` (for example `2026-08-24T00:00:00.000000Z`). Strings are UTF-8
JSON strings. Both challenge ID and issue/expiry times are included. Python
`repr`, insertion order, locale formatting, concatenated field strings, NaN,
Infinity, and non-canonical JSON are prohibited. The raw canonical document is
not persisted outside its typed columns and never enters Audit/logs.

### 18A. SQLite timestamp storage and clock authority

All `Session`, Challenge, and Attempt datetime columns use SQLAlchemy
`DateTime(timezone=True)` with the repository SQLite convention, but their
authoritative raw SQLite representation is frozen as 26 ASCII characters:
`YYYY-MM-DD HH:MM:SS.ffffff`. It is a naive textual representation of UTC,
never local time and never an offset-bearing string. The application accepts
only aware UTC input, normalizes with `astimezone(UTC)`, preserves exactly six
microsecond digits, removes `tzinfo` only at the SQLite bind boundary, and on
load immediately attaches UTC after validating the exact raw grammar. Existing
Session values are normalized to this form during the guarded rebuild. Mixed
offsets, missing/extra fractional digits, terminal `Z` in raw SQLite, leap
seconds, and non-UTC naive application input are rejected.

Canonical approval JSON is deliberately different: the same instant is
serialized as `YYYY-MM-DDTHH:MM:SS.ffffffZ` before RFC 8785. Conversion changes
only the separator and UTC suffix; it does not round or truncate. Equality and
ordering in SQLite use the fixed-width raw UTC6 text. Five-minute and retention
checks preserve microseconds exactly with
`datetime(value, '+300 seconds') || substr(value,20,7)` and
`datetime(value, '+30 days') || substr(value,20,7)` respectively; neither
`unixepoch()` nor floating-point `julianday()` is authority.

Every production SQLite connection registers zero-argument
`agentbox_now_utc6()`, returning one transaction-scoped application-clock value
in the same raw UTC6 grammar. Challenge/Attempt mutation and delete triggers
compare only against that function. `BEGIN IMMEDIATE` code captures `now` once
and pins the function result for the transaction; a connection lacking it, an
invalid result, or a backward value causes the statement to abort. At exact
equality, expiry/retention has elapsed. `last_observed_at`, Session bounds,
Challenge/Attempt deadlines, backward-clock checks, and deletion therefore use
one representation and one authority. The future tests inspect raw SQLite,
round-trip `000000`/`999999` microseconds, the exact five-minute boundary,
offset rejection, backward clock, and canonical JSON conversion.

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
5. reject any `ISSUED` challenge or unresolved provisioning attempt, including
   `NEEDS_ATTENTION`, for this Credential;
6. generate one `cch_*` and one `psi_*`, each with independent 128-bit CSPRNG
   entropy and at most three PK/unique-collision retries; a fourth collision
   returns `APPROVAL_UNAVAILABLE` and inserts neither;
7. set `intent_issued_at = issued_at = created_at = now`,
   `intent_expires_at = expires_at = now + 300 seconds`, both cancellation
   epochs to zero, then build the verifier and digest over the exact `psi_*` and
   complete tuple;
8. insert `ISSUED` challenge;
9. write `provider_secret.challenge_issued` Audit; commit.

Issuance creates no attempt, Runtime call, Secret, Profile, or Binding. It does
durably reserve the exact approved `psi_*`. A cancelled, expired, mismatched,
clock-rejected, stale, or otherwise terminal Challenge permanently burns that
intent ID; it is never reassigned, extended, or replaced.

## 21. Cancellation transaction

Only the issuing Admin in the exact issuing Session may explicitly cancel;
recent auth is not required to abort. In one `BEGIN IMMEDIATE`, reload and
validate the binding, apply clock policy, and conditionally update
`ISSUED -> CANCELLED`, increment `cancellation_epoch`, set terminal fields, and
set `terminal_result_code=CANCELLED_BY_ISSUER`; its `psi_*` is permanently
burned. Write `provider_secret.challenge_cancelled`. A repeat by the same issuer is
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
10. validate and copy the consumption request ID as immutable
    `authorization_request_id String(72) NOT NULL`; its exact accepted grammar
    is `[A-Za-z0-9][A-Za-z0-9._:-]{0,63}` (1–64 ASCII characters), matching the
    current API/Runtime request-ID contract;
11. generate only one `psa_*` attempt ID using independent 128-bit CSPRNG with
    at most three collision retries; a fourth collision rolls back and returns
    `APPROVAL_UNAVAILABLE`. Copy the already approved Challenge `psi_*`, intent
    contract version, issue/expiry times, and initial/current cancellation
    epochs without changing them;
12. insert the exact `AUTHORIZED` orchestration row. The `BEFORE INSERT`
    validator checks the complete Challenge tuple; the
    `AFTER INSERT trg_provider_secret_attempts_consume_challenge` performs the
    only Challenge update and sets `CONSUMED`, `terminal_at=consumed_at=
    NEW.authorized_at`, `consumed_request_id=NEW.authorization_request_id`, and
    `terminal_result_code=ATTEMPT_CREATED`;
13. require that trigger's conditional update matched exactly one row; the
    Challenge legal-transition and consumed-attempt triggers remain enabled;
14. write `provider_secret.challenge_consumed` and
    `provider_secret.attempt_created`; commit.

A second consumer cannot satisfy the validator/conditional trigger update.
The application performs no separate Challenge state update. Cancellation
and consumption serialize; exactly one terminal transition commits. Any busy
timeout returns `APPROVAL_UNAVAILABLE`; process crash, exception, or rollback
leaves both the `ISSUED` challenge and absence of an attempt, or commits both
consumption and attempt—never half of either.

For the authenticated exact issuer, entity/auth tuple staleness terminalizes
the issued row as `CANCELLED/BOUND_ENTITY_STALE` or
`CANCELLED/AUTH_EPOCH_ROTATED` in its own serialized rejection transaction;
confirmation mismatch and clock rollback use their exact §15 codes. Deadline
uses `EXPIRED/DEADLINE_EXPIRED`. Wrong/malformed/unknown actor or ID never
mutates a discovered row. Session revocation/Admin deactivation use their exact
codes in the transaction that performs that invalidation.

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
| `APPROVAL_CONFLICT` | one-unresolved-attempt/challenge or concurrent winner conflict |
| `APPROVAL_UNAVAILABLE` | busy timeout, clock rollback, or internal fail-closed result |

These are the complete `ApprovalPublicErrorCode` Python members and their
identical uppercase wire values. Internal terminal codes never pass through as
public messages; the service maps them only as this table states.

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
`psa_<32 lowercase hex>`, `String(40)`. Its `provisioning_intent_id` is copied
from the consumed Challenge's pre-generated `psi_*`; attempt creation never
generates or replaces an intent.

| Column | Exact contract |
|---|---|
| `id` | `psa_*` PK |
| `schema_version` | integer exactly 1 |
| `intent_contract_version` | integer exactly 1, copied from Challenge |
| `purpose` | exactly `provider_secret_provision` |
| `state` | enum below |
| `challenge_id`, `provisioning_intent_id` | unique pair and composite FK to exact Challenge pair, `RESTRICT` |
| `authorization_request_id` | immutable `String(72)`, non-null, exact `[A-Za-z0-9][A-Za-z0-9._:-]{0,63}` request ID selected by the consumption request |
| `admin_user_id`, `control_plane_session_id`, `auth_epoch` | copied exact authorization identity |
| Runtime ID/revision/type | exact challenge values |
| Provider ID/revision/state | exact challenge values |
| Credential ID/revision/kind/state/owner | exact challenge values |
| expected reference/version | constrained null |
| `approval_digest` | exact lowercase hex digest |
| `intent_issued_at`, `authorized_at`, `expires_at`, `created_at`, `updated_at` | UTC; intent issue/expiry equal Challenge; authorized/created equal consumption |
| `authorize_requested_at` | nullable UTC6; first durable pre-send admission time |
| `authorize_request_id` | nullable `String(72)`, exact request-ID grammar; current authorize/status recovery request |
| `authorize_attempt_count` | integer 0–3; total admitted Runtime authorize transmissions |
| `authorize_last_result_code` | non-null exact `AuthorizeResultCode` |
| `runtime_staged_at`, `runtime_consuming_at` | nullable UTC6 Control Plane observation times |
| `runtime_committed_at` | nullable UTC6 only when authenticated Runtime evidence supplies its commit timestamp |
| `runtime_commit_observed_at` | nullable UTC6 Control Plane observation time, required in `RUNTIME_COMMITTED_UNVERIFIED`; distinct from Runtime commit time |
| `runtime_verified_at`, `reconciled_at`, `terminal_at` | nullable UTC6 typed transition times |
| `cancellation_epoch` | integer >=0, initially copied as 0; server increments only |
| `cancel_requested_at` | nullable UTC; required in `CANCEL_PENDING` |
| `cancel_request_id` | nullable bounded request ID |
| `cancellation_result_code` | exact enum below |
| `runtime_attestation_code` | exact nullable enum reserved for Slice 3.2b |
| `terminal_result_code` | exact nullable enum below |
| `retention_eligible_at` | nullable immutable UTC6; null for active/unresolved and exactly `terminal_at + 30 days` for safely prunable terminal rows |

No arbitrary JSON, Job ID/payload, Secret-shaped field, endpoint, command,
path, environment, Store path, ciphertext, cryptographic material, raw
attestation, or exception exists.

```text
AUTHORIZED -> AUTHORIZE_PENDING | CANCELLED | EXPIRED | NEEDS_ATTENTION
AUTHORIZE_PENDING -> RUNTIME_STAGED | RUNTIME_CONSUMING |
  RUNTIME_COMMITTED_UNVERIFIED | RUNTIME_VERIFIED | CANCEL_PENDING |
  EXPIRED | NEEDS_ATTENTION
RUNTIME_STAGED -> CANCEL_PENDING | RUNTIME_CONSUMING |
  RUNTIME_COMMITTED_UNVERIFIED | RUNTIME_VERIFIED | EXPIRED | NEEDS_ATTENTION
CANCEL_PENDING -> CANCELLED | RUNTIME_CONSUMING |
  RUNTIME_COMMITTED_UNVERIFIED | RUNTIME_VERIFIED | EXPIRED | NEEDS_ATTENTION
RUNTIME_CONSUMING -> RUNTIME_COMMITTED_UNVERIFIED | RUNTIME_VERIFIED | NEEDS_ATTENTION
RUNTIME_COMMITTED_UNVERIFIED -> RUNTIME_VERIFIED | NEEDS_ATTENTION
RUNTIME_VERIFIED -> RECONCILED | NEEDS_ATTENTION
```

`RECONCILED`, `CANCELLED`, `EXPIRED`, and `NEEDS_ATTENTION` are terminal.
`AUTHORIZE_PENDING` and every subsequent nonterminal state are unresolved and
belong to Slice 3.2b. Slice 3.2a creates only `AUTHORIZED`, may locally
cancel/expire only that provably unsent state, and never contacts Runtime. No
state regresses, returns to `AUTHORIZED`, extends expiry, or creates a new
`psi_*`.

`AttemptTerminalResultCode` is exactly:

| Python member / DB value | State |
|---|---|
| `LOCAL_CANCELLED` | `CANCELLED` from `AUTHORIZED` |
| `RUNTIME_CANCELLED_CONFIRMED` | `CANCELLED` from `CANCEL_PENDING` |
| `INTENT_EXPIRED_UNSENT` | `EXPIRED` from `AUTHORIZED` only |
| `INTENT_EXPIRED_NOT_FOUND_CONFIRMED` | `EXPIRED` from `AUTHORIZE_PENDING` after authenticated same-`psi_*` `NOT_FOUND` at/after deadline |
| `RUNTIME_INTENT_EXPIRED_CONFIRMED` | `EXPIRED` from `AUTHORIZE_PENDING`, `RUNTIME_STAGED`, or `CANCEL_PENDING` after same-`psi_*` Runtime `EXPIRED` |
| `RECONCILIATION_COMPLETE` | `RECONCILED` |
| `BOUND_ENTITY_STALE` | `NEEDS_ATTENTION` |
| `RUNTIME_STATUS_CONTRADICTION` | `NEEDS_ATTENTION` |
| `RUNTIME_OPERATION_UNCERTAIN` | `NEEDS_ATTENTION` |
| `ATTESTATION_REJECTED` | `NEEDS_ATTENTION` |
| `RUNTIME_REPORTED_UNEXPECTED_TERMINAL` | `NEEDS_ATTENTION` for `CANCELLED`, `FAILED`, `NEEDS_ATTENTION`, or `EXPIRED_UNRECONCILED` status outside its exact legal path |
| `AUTHORIZE_TRANSMISSION_LIMIT_EXCEEDED` | `NEEDS_ATTENTION` before a prohibited fourth transmission |

`CancellationResultCode` is exactly `NOT_REQUESTED` (initial),
`LOCAL_CANCELLED`, `RUNTIME_CANCEL_REQUESTED`,
`RUNTIME_CANCELLED_CONFIRMED`, `RUNTIME_CANCEL_LOST_TO_CONSUMING`,
`RUNTIME_CANCEL_LOST_TO_COMMITTED_UNVERIFIED`,
`RUNTIME_CANCEL_LOST_TO_VERIFIED`, `RUNTIME_CANCEL_LOST_TO_EXPIRY`, or
`RUNTIME_CANCEL_CONTRADICTION`. `RuntimeAttestationResultCode`, reserved for
Slice 3.2b and null throughout Slice 3.2a, is exactly
`VERIFIED_LIVE_PLAINTEXT_MATCH` or `VERIFIED_RECOVERED_AEAD_REOPEN`. No raw
Runtime output/exception is representable.
For `CancellationResultCode` and `RuntimeAttestationResultCode`, Python member
names and database values are the identical uppercase strings shown. Likewise,
`ProviderSecretProvisioningAttemptState` members and DB values are the exact
uppercase state labels in the diagram represented in the existing repository
enum convention as lowercase database values (`authorized`,
`authorize_pending`, `runtime_staged`, `cancel_pending`, `runtime_consuming`,
`runtime_committed_unverified`, `runtime_verified`, `reconciled`, `cancelled`,
`expired`, `needs_attention`).

`AuthorizeResultCode` Python members and DB values are exactly:
`NOT_REQUESTED`, `REQUEST_PERSISTED`, `STATUS_NOT_FOUND`, `RESEND_PERSISTED`,
`STATUS_STAGED`, `STATUS_CONSUMING`, `STATUS_COMMITTED_UNVERIFIED`,
`STATUS_VERIFIED`, `STATUS_EXPIRED`, `STATUS_CANCELLED_UNEXPECTED`,
`STATUS_FAILED_UNEXPECTED`, `STATUS_NEEDS_ATTENTION_UNEXPECTED`,
`STATUS_EXPIRED_UNRECONCILED_UNEXPECTED`, `STATUS_UNAVAILABLE`,
`STATUS_MALFORMED`, `STATUS_CONTRADICTORY`, and
`TRANSMISSION_LIMIT_EXCEEDED`. No raw Runtime message or exception is stored.
The bounded Slice 3.2b wire enum is `RuntimeProviderSecretProvisionStatus` with
identical Python member/wire values: `NOT_FOUND`, `STAGED`, `CONSUMING`,
`COMMITTED_UNVERIFIED`, `VERIFIED`, `CANCELLED`, `EXPIRED`, `FAILED`,
`NEEDS_ATTENTION`, and `EXPIRED_UNRECONCILED`. Transport unavailable is a local
transport outcome, not a fabricated wire member; malformed/contradictory is a
local validation outcome. These closed outcomes alone drive the matrix.

Attempt field consistency is exact:

| State | Required fields/codes | Forbidden fields |
|---|---|---|
| `AUTHORIZED` | authorization request fields null; count 0; `authorize_last_result_code=NOT_REQUESTED`; epoch 0; cancellation `NOT_REQUESTED` | every Runtime/cancel/terminal/retention timestamp, attestation, terminal result |
| `AUTHORIZE_PENDING` | authorize request time/ID non-null; count 1–3; authorize result one of `REQUEST_PERSISTED`, `RESEND_PERSISTED`, `STATUS_UNAVAILABLE`; epoch 0 | Runtime observation/commit/verified/reconciled/terminal/retention fields, attestation, terminal result |
| `RUNTIME_STAGED` | authorize request fields non-null; count 1–3; `STATUS_STAGED`; `runtime_staged_at` non-null | consuming/commit/verified/reconciled/terminal/retention fields, attestation, terminal result |
| `CANCEL_PENDING` | authorize request and cancel time/ID non-null; epoch 1; `RUNTIME_CANCEL_REQUESTED`; `runtime_staged_at` is non-null iff it was already observed before cancellation | consuming/commit/verified/reconciled/terminal/retention fields, attestation, terminal result |
| `RUNTIME_CONSUMING` | authorize request fields and `runtime_consuming_at` non-null; `STATUS_CONSUMING`; cancellation exactly `NOT_REQUESTED` or `RUNTIME_CANCEL_LOST_TO_CONSUMING` | commit/verified/reconciled/terminal/retention fields, attestation, terminal result |
| `RUNTIME_COMMITTED_UNVERIFIED` | authorize request fields and `runtime_commit_observed_at` non-null; `STATUS_COMMITTED_UNVERIFIED`; `runtime_committed_at` non-null only if Runtime supplied it; cancellation exactly `NOT_REQUESTED` or `RUNTIME_CANCEL_LOST_TO_COMMITTED_UNVERIFIED` | verified/reconciled/terminal/retention fields, attestation, terminal result |
| `RUNTIME_VERIFIED` | authorize request fields, verified time and exact attestation non-null; `STATUS_VERIFIED`; cancellation exactly `NOT_REQUESTED` or `RUNTIME_CANCEL_LOST_TO_VERIFIED` | reconciled/terminal/retention fields and terminal result |
| `RECONCILED` | verified/reconciled/terminal times, exact attestation, `STATUS_VERIFIED`, `RECONCILIATION_COMPLETE`, retention=`terminal+30d` | no required field is null |
| `CANCELLED` | terminal/cancel times, epoch 1, exact local or Runtime-confirmed cancellation and matching terminal code; retention=`terminal+30d` | verified attestation/reconciled fields unless Runtime evidence was observed before cancellation |
| `EXPIRED` | terminal time and exactly one of three expiry terminal codes; retention=`terminal+30d`; `RUNTIME_CANCEL_LOST_TO_EXPIRY` iff predecessor was `CANCEL_PENDING` | verified attestation/reconciled fields |
| `NEEDS_ATTENTION` | terminal time; one exact `NEEDS_ATTENTION` terminal code; `retention_eligible_at=NULL`; authorize/cancellation codes fixed by the triggering row below | reconciled and retention fields |

The following is the single authoritative transition matrix. `t` is the one
transaction UTC6 observation. `Runtime(t)` is populated only when the
authenticated bounded response provides that timestamp; otherwise
`runtime_committed_at` stays null and `runtime_commit_observed_at=t`. `Base`
means the immutable authorization tuple and timestamps are non-null.
`pre-send-null` means all Runtime, cancel, terminal and retention timestamps and
attestation/result fields are null. Every row preserves fields already required
by its old state unless the row explicitly sets them.

| Old state | Exact event/evidence | New state | Must be null | Must be non-null / exact timestamps | `authorize_last_result_code` | `cancellation_result_code` | `runtime_attestation_code` | `terminal_result_code` | Terminal / retention / unresolved | Audit action/result |
|---|---|---|---|---|---|---|---|---|---|---|
| `AUTHORIZED` | Slice 3.2b admits first authorize transmission | `AUTHORIZE_PENDING` | pre-send Runtime/cancel/terminal/retention fields | Base; `authorize_requested_at=t`; request ID; count=1 | `REQUEST_PERSISTED` | `NOT_REQUESTED` | null | null | no / no / yes | `provider_secret.authorize_pending`/`succeeded` |
| `AUTHORIZED` | issuer local cancel before deadline | `CANCELLED` | all Runtime fields; attestation/reconciled | cancel time/request=`t`/ID; terminal=`t`; retention=`t+30d`; epoch=1 | `NOT_REQUESTED` | `LOCAL_CANCELLED` | null | `LOCAL_CANCELLED` | yes / yes / no | `provider_secret.attempt_transitioned`/`succeeded` |
| `AUTHORIZED` | local clock reaches deadline | `EXPIRED` | all Runtime/cancel fields; attestation/reconciled | terminal=`t`; retention=`t+30d`; epoch=0 | `NOT_REQUESTED` | `NOT_REQUESTED` | null | `INTENT_EXPIRED_UNSENT` | yes / yes / no | `provider_secret.attempt_transitioned`/`succeeded` |
| `AUTHORIZED` | bound entity stale before send | `NEEDS_ATTENTION` | all Runtime/cancel fields; attestation/reconciled/retention | terminal=`t` | `NOT_REQUESTED` | `NOT_REQUESTED` | null | `BOUND_ENTITY_STALE` | yes / no / yes | `provider_secret.attempt_transitioned`/`needs_attention` |
| `AUTHORIZE_PENDING` | authenticated same-`psi_*` `NOT_FOUND`, before deadline, count<3; persist before resend | `AUTHORIZE_PENDING` | Runtime/cancel/terminal/retention fields; attestation | request time=`t`; new request ID; count=`old+1` | `RESEND_PERSISTED` | `NOT_REQUESTED` | null | null | no / no / yes | `provider_secret.authorize_retry_admitted`/`succeeded` |
| `AUTHORIZE_PENDING` | status transport unavailable | `AUTHORIZE_PENDING` | Runtime/cancel/terminal/retention fields; attestation | existing request tuple; updated=`t` | `STATUS_UNAVAILABLE` | `NOT_REQUESTED` | null | null | no / no / yes | `provider_secret.authorize_status_checked`/`failed` |
| `AUTHORIZE_PENDING` | authenticated `STAGED` | `RUNTIME_STAGED` | consuming/commit/verified/reconciled/terminal/retention; attestation | staged=`t` | `STATUS_STAGED` | `NOT_REQUESTED` | null | null | no / no / yes | `provider_secret.attempt_transitioned`/`succeeded` |
| `AUTHORIZE_PENDING` | authenticated `CONSUMING` | `RUNTIME_CONSUMING` | commit/verified/reconciled/terminal/retention; attestation | consuming=`t` | `STATUS_CONSUMING` | `NOT_REQUESTED` | null | null | no / no / yes | `provider_secret.attempt_transitioned`/`succeeded` |
| `AUTHORIZE_PENDING` | authenticated `COMMITTED_UNVERIFIED` | `RUNTIME_COMMITTED_UNVERIFIED` | verified/reconciled/terminal/retention; attestation | commit-observed=`t`; Runtime commit time iff supplied | `STATUS_COMMITTED_UNVERIFIED` | `NOT_REQUESTED` | null | null | no / no / yes | `provider_secret.attempt_transitioned`/`succeeded` |
| `AUTHORIZE_PENDING` | authenticated `VERIFIED` plus accepted attestation | `RUNTIME_VERIFIED` | reconciled/terminal/retention | verified=`t`; exact attestation | `STATUS_VERIFIED` | `NOT_REQUESTED` | one exact verified code | null | no / no / yes | `provider_secret.attempt_transitioned`/`succeeded` |
| `AUTHORIZE_PENDING` | issuer requests cancellation | `CANCEL_PENDING` | Runtime observation/verified/reconciled/terminal/retention; attestation | cancel time=`t`, request ID, epoch=1 | unchanged member of `{REQUEST_PERSISTED, RESEND_PERSISTED, STATUS_UNAVAILABLE}` | `RUNTIME_CANCEL_REQUESTED` | null | null | no / no / yes | `provider_secret.cancel_pending`/`succeeded` |
| `AUTHORIZE_PENDING` | authenticated `NOT_FOUND` at/after deadline | `EXPIRED` | Runtime/cancel/verified/reconciled; attestation | terminal=`t`; retention=`t+30d` | `STATUS_NOT_FOUND` | `NOT_REQUESTED` | null | `INTENT_EXPIRED_NOT_FOUND_CONFIRMED` | yes / yes / no | `provider_secret.attempt_transitioned`/`succeeded` |
| `AUTHORIZE_PENDING` | authenticated `EXPIRED` same `psi_*` | `EXPIRED` | verified/reconciled; attestation | terminal=`t`; retention=`t+30d` | `STATUS_EXPIRED` | `NOT_REQUESTED` | null | `RUNTIME_INTENT_EXPIRED_CONFIRMED` | yes / yes / no | `provider_secret.attempt_transitioned`/`succeeded` |
| `RUNTIME_STAGED` | authenticated `CONSUMING` | `RUNTIME_CONSUMING` | commit/verified/reconciled/terminal/retention; attestation | staged retained; consuming=`t` | `STATUS_CONSUMING` | `NOT_REQUESTED` | null | null | no / no / yes | `provider_secret.attempt_transitioned`/`succeeded` |
| `RUNTIME_STAGED` | authenticated `COMMITTED_UNVERIFIED` | `RUNTIME_COMMITTED_UNVERIFIED` | verified/reconciled/terminal/retention; attestation | staged retained; commit-observed=`t`; Runtime commit iff supplied | `STATUS_COMMITTED_UNVERIFIED` | `NOT_REQUESTED` | null | null | no / no / yes | `provider_secret.attempt_transitioned`/`succeeded` |
| `RUNTIME_STAGED` | authenticated `VERIFIED` plus accepted attestation | `RUNTIME_VERIFIED` | reconciled/terminal/retention | staged retained; verified=`t`; exact attestation | `STATUS_VERIFIED` | `NOT_REQUESTED` | one exact verified code | null | no / no / yes | `provider_secret.attempt_transitioned`/`succeeded` |
| `RUNTIME_STAGED` | issuer requests cancellation | `CANCEL_PENDING` | consuming/commit/verified/reconciled/terminal/retention; attestation | staged retained; cancel time=`t`, request ID, epoch=1 | `STATUS_STAGED` | `RUNTIME_CANCEL_REQUESTED` | null | null | no / no / yes | `provider_secret.cancel_pending`/`succeeded` |
| `RUNTIME_STAGED` | authenticated `EXPIRED` same `psi_*` | `EXPIRED` | verified/reconciled; attestation | staged retained; terminal=`t`; retention=`t+30d` | `STATUS_EXPIRED` | `NOT_REQUESTED` | null | `RUNTIME_INTENT_EXPIRED_CONFIRMED` | yes / yes / no | `provider_secret.attempt_transitioned`/`succeeded` |
| `CANCEL_PENDING` | authenticated `CANCELLED` same epoch/`psi_*` | `CANCELLED` | verified/reconciled; attestation | cancel fields retained; terminal=`t`; retention=`t+30d` | unchanged member of `{REQUEST_PERSISTED, RESEND_PERSISTED, STATUS_UNAVAILABLE, STATUS_STAGED}` | `RUNTIME_CANCELLED_CONFIRMED` | null | `RUNTIME_CANCELLED_CONFIRMED` | yes / yes / no | `provider_secret.attempt_transitioned`/`succeeded` |
| `CANCEL_PENDING` | authenticated `CONSUMING` | `RUNTIME_CONSUMING` | commit/verified/reconciled/terminal/retention; attestation | cancel fields retained; consuming=`t` | `STATUS_CONSUMING` | `RUNTIME_CANCEL_LOST_TO_CONSUMING` | null | null | no / no / yes | `provider_secret.attempt_transitioned`/`failed` |
| `CANCEL_PENDING` | authenticated `COMMITTED_UNVERIFIED` | `RUNTIME_COMMITTED_UNVERIFIED` | verified/reconciled/terminal/retention; attestation | cancel retained; commit-observed=`t`; Runtime commit iff supplied | `STATUS_COMMITTED_UNVERIFIED` | `RUNTIME_CANCEL_LOST_TO_COMMITTED_UNVERIFIED` | null | null | no / no / yes | `provider_secret.attempt_transitioned`/`failed` |
| `CANCEL_PENDING` | authenticated `VERIFIED` plus accepted attestation | `RUNTIME_VERIFIED` | reconciled/terminal/retention | cancel retained; verified=`t`; exact attestation | `STATUS_VERIFIED` | `RUNTIME_CANCEL_LOST_TO_VERIFIED` | one exact verified code | null | no / no / yes | `provider_secret.attempt_transitioned`/`failed` |
| `CANCEL_PENDING` | authenticated `EXPIRED` same `psi_*` | `EXPIRED` | verified/reconciled; attestation | cancel retained; terminal=`t`; retention=`t+30d` | `STATUS_EXPIRED` | `RUNTIME_CANCEL_LOST_TO_EXPIRY` | null | `RUNTIME_INTENT_EXPIRED_CONFIRMED` | yes / yes / no | `provider_secret.attempt_transitioned`/`failed` |
| `RUNTIME_CONSUMING` | authenticated `COMMITTED_UNVERIFIED`, no cancellation history | `RUNTIME_COMMITTED_UNVERIFIED` | verified/reconciled/terminal/retention; attestation | consuming retained; commit-observed=`t`; Runtime commit iff supplied | `STATUS_COMMITTED_UNVERIFIED` | `NOT_REQUESTED` | null | null | no / no / yes | `provider_secret.attempt_transitioned`/`succeeded` |
| `RUNTIME_CONSUMING` | authenticated `COMMITTED_UNVERIFIED`, cancellation previously lost | `RUNTIME_COMMITTED_UNVERIFIED` | verified/reconciled/terminal/retention; attestation | cancel/consuming retained; commit-observed=`t`; Runtime commit iff supplied | `STATUS_COMMITTED_UNVERIFIED` | `RUNTIME_CANCEL_LOST_TO_COMMITTED_UNVERIFIED` | null | null | no / no / yes | `provider_secret.attempt_transitioned`/`failed` |
| `RUNTIME_CONSUMING` | authenticated `VERIFIED` plus accepted attestation, no cancellation history | `RUNTIME_VERIFIED` | reconciled/terminal/retention | consuming retained; verified=`t`; exact attestation | `STATUS_VERIFIED` | `NOT_REQUESTED` | one exact verified code | null | no / no / yes | `provider_secret.attempt_transitioned`/`succeeded` |
| `RUNTIME_CONSUMING` | authenticated `VERIFIED` plus accepted attestation, cancellation previously lost | `RUNTIME_VERIFIED` | reconciled/terminal/retention | cancel/consuming retained; verified=`t`; exact attestation | `STATUS_VERIFIED` | `RUNTIME_CANCEL_LOST_TO_VERIFIED` | one exact verified code | null | no / no / yes | `provider_secret.attempt_transitioned`/`failed` |
| `RUNTIME_COMMITTED_UNVERIFIED` | authenticated `VERIFIED` plus accepted attestation, no cancellation history | `RUNTIME_VERIFIED` | reconciled/terminal/retention | commit observation retained; verified=`t`; exact attestation | `STATUS_VERIFIED` | `NOT_REQUESTED` | one exact verified code | null | no / no / yes | `provider_secret.attempt_transitioned`/`succeeded` |
| `RUNTIME_COMMITTED_UNVERIFIED` | authenticated `VERIFIED` plus accepted attestation, cancellation previously lost | `RUNTIME_VERIFIED` | reconciled/terminal/retention | cancel/commit observation retained; verified=`t`; exact attestation | `STATUS_VERIFIED` | `RUNTIME_CANCEL_LOST_TO_VERIFIED` | one exact verified code | null | no / no / yes | `provider_secret.attempt_transitioned`/`failed` |
| `RUNTIME_VERIFIED` | exact Credential reference/version update and same-`psi_*` reconciliation committed; cancellation code `NOT_REQUESTED` | `RECONCILED` | none of its required evidence | verified retained; reconciled=terminal=`t`; retention=`t+30d` | `STATUS_VERIFIED` | `NOT_REQUESTED` | exact verified code | `RECONCILIATION_COMPLETE` | yes / yes / no | `provider_secret.attempt_transitioned`/`succeeded` |
| `RUNTIME_VERIFIED` | same exact reconciliation; cancellation code `RUNTIME_CANCEL_LOST_TO_VERIFIED` | `RECONCILED` | none of its required evidence | cancel/verified retained; reconciled=terminal=`t`; retention=`t+30d` | `STATUS_VERIFIED` | `RUNTIME_CANCEL_LOST_TO_VERIFIED` | exact verified code | `RECONCILIATION_COMPLETE` | yes / yes / no | `provider_secret.attempt_transitioned`/`succeeded` |

Every transition to `NEEDS_ATTENTION` is exact:

| Evidence | `authorize_last_result_code` | `cancellation_result_code` | `terminal_result_code` |
|---|---|---|---|
| authenticated `CANCELLED` outside the exact cancel-confirm path | `STATUS_CANCELLED_UNEXPECTED` | `RUNTIME_CANCEL_CONTRADICTION` if cancel was pending, otherwise `NOT_REQUESTED` | `RUNTIME_REPORTED_UNEXPECTED_TERMINAL` |
| authenticated `FAILED` | `STATUS_FAILED_UNEXPECTED` | retained exact cancellation code | `RUNTIME_REPORTED_UNEXPECTED_TERMINAL` |
| authenticated Runtime `NEEDS_ATTENTION` | `STATUS_NEEDS_ATTENTION_UNEXPECTED` | retained exact cancellation code | `RUNTIME_REPORTED_UNEXPECTED_TERMINAL` |
| authenticated `EXPIRED_UNRECONCILED` | `STATUS_EXPIRED_UNRECONCILED_UNEXPECTED` | retained exact cancellation code | `RUNTIME_REPORTED_UNEXPECTED_TERMINAL` |
| malformed response | `STATUS_MALFORMED` | `RUNTIME_CANCEL_CONTRADICTION` if cancel was pending, otherwise retained | `RUNTIME_STATUS_CONTRADICTION` |
| contradictory tuple/state/epoch/timestamp | `STATUS_CONTRADICTORY` | `RUNTIME_CANCEL_CONTRADICTION` if cancel was pending, otherwise retained | `RUNTIME_STATUS_CONTRADICTION` |
| authenticated `NOT_FOUND` before expiry when count=3 | `TRANSMISSION_LIMIT_EXCEEDED` | retained | `AUTHORIZE_TRANSMISSION_LIMIT_EXCEEDED` |
| bound entity stale at any unresolved state | retained | retained | `BOUND_ENTITY_STALE` |
| rejected attestation | `STATUS_VERIFIED` | retained | `ATTESTATION_REJECTED` |
| status remains unavailable after deadline and separately configured recovery deadline elapses | `STATUS_UNAVAILABLE` | retained | `RUNTIME_OPERATION_UNCERTAIN` |

Each such row sets `terminal_at=t`, leaves `retention_eligible_at=NULL`, is
terminal and unresolved, and writes `provider_secret.attempt_transitioned` with
result `needs_attention`. Before that separate recovery deadline, unavailable
status remains in the same unresolved state and never becomes locally expired.

Named constraints/indexes are:

- `uq_provider_secret_attempts_challenge`;
- `uq_provider_secret_attempts_intent`;
- `fk_provider_secret_attempts_challenge_intent` over
  `(challenge_id, provisioning_intent_id) ->
  confirmation_challenges(id, provisioning_intent_id)`,
  `fk_provider_secret_attempts_session_admin` over
  `(control_plane_session_id, admin_user_id) -> sessions(id, user_id)`,
  `fk_provider_secret_attempts_runtime_installation`,
  `fk_provider_secret_attempts_provider`, and
  `fk_provider_secret_attempts_credential_runtime_identity`, all `ON DELETE
  RESTRICT`;
- `ck_provider_secret_attempts_id`, `_intent_id`, `_schema`, `_expected_missing`,
  `_timestamps`, and `_state_timestamps`;
- partial unique index `uq_provider_secret_attempts_unresolved_credential` on
  `credential_id WHERE state IN ('authorized','authorize_pending',
  'runtime_staged','cancel_pending','runtime_consuming',
  'runtime_committed_unverified','runtime_verified','needs_attention')`;
- indexes `ix_provider_secret_attempts_state_updated` and
  `ix_provider_secret_attempts_terminal_at`.

Database authority is enforced by six triggers:

1. `trg_provider_secret_attempts_insert_matches_challenge` permits insert only
   in `AUTHORIZED` while the exact Challenge is `ISSUED`, and requires `IS`
   equality for every copied schema/purpose/Admin/Session/auth,
   Runtime/Provider/Credential/owner, expected/postcondition, digest, `psi_*`,
   intent timestamp, expiry, and initial cancellation value;
2. `trg_provider_secret_attempts_consume_challenge` is `AFTER INSERT`. It issues
   exactly one conditional update matching Challenge ID, `psi_*`, digest,
   schema/purpose, actor/Session/auth tuple, Runtime/Provider/Credential tuple,
   expected postcondition, and state `ISSUED`; it sets
   `CONSUMED`, `terminal_at=consumed_at=NEW.authorized_at`,
   `consumed_request_id=NEW.authorization_request_id`, and
   `terminal_result_code=ATTEMPT_CREATED`. It then requires `changes()=1` or
   executes `RAISE(ABORT,'provider secret challenge consume mismatch')`;
3. `trg_provider_secret_attempts_authority_immutable` uses `IS NOT` to reject
   changes to ID, schema/purpose, Challenge/intent identity, Admin/Session/auth,
   every Runtime/Provider/Credential identity/revision/state/owner,
   expected/postcondition, digest, `authorization_request_id`, intent
   issue/expiry, authorized/created time, and retention boundary after terminal;
4. `trg_provider_secret_attempts_legal_transition` permits only the arrows in
   the state diagram and rejects regression/terminal transitions;
5. `trg_provider_secret_attempts_transition_consistency` requires exact
   per-state timestamps, cancellation/attestation/terminal result codes, and
   forbids `RECONCILED` unless prior state is `RUNTIME_VERIFIED` with a valid
   attestation code and non-null verified time;
6. `trg_provider_secret_attempts_delete_guard` permits deletion only for
   `RECONCILED`, safely confirmed `CANCELLED`, or safely confirmed `EXPIRED`,
   with exact consistent terminal/result fields, non-null
   `retention_eligible_at = terminal_at + 30 days`, and
   `agentbox_now_utc6() >= retention_eligible_at`. It always rejects every
   active/unresolved state and every `NEEDS_ATTENTION`; missing clock function
   fails closed.

The insert/consume pair is one database-enforced trigger handshake inside the
same statement and transaction. The `BEFORE INSERT` validator admits only the
exact eligible `ISSUED` Challenge; after the row exists, the `AFTER INSERT`
trigger consumes it, while the Challenge legal-transition and consumed-attempt
validation triggers remain active. Any Audit/constraint error or later crash/
rollback removes both the Attempt and transition. Direct SQL cannot commit an
Attempt with an `ISSUED` Challenge, consume without the exact Attempt, copy
another Challenge, or create more than one Attempt per Challenge.

The final trigger shape was exercised on 2026-08-25 in temporary SQLite:
valid insert produced Attempt plus consumed Challenge; an injected failure
after insert rolled both back; direct consume and mismatched `psi_*`, digest,
tuple, or request field failed; active/unresolved deletion failed; safely
terminal Attempt then Challenge deletion succeeded only after their exact UTC6
retention boundaries; `NEEDS_ATTENTION` deletion failed after 1, 90, and 9,999
days. Raw UTC6 `2026-08-25 01:02:03.456789` round-tripped and
the five-minute value remained `2026-08-25 01:07:03.456789`. No prototype file
entered Git.

Table checks require exact ID/digest grammar, timestamp ordering, state-field
consistency, and the enumerated codes. Together with the partial index and
composite FKs, direct SQL cannot substitute a Challenge tuple, move an Attempt,
regress it, reconcile it early, or create a second unresolved Attempt.

Slice 3.2a Attempt cancellation is one `BEGIN IMMEDIATE`: require the issuing
Admin/exact Session, load `AUTHORIZED`, prove no Runtime-send marker exists,
conditionally transition to `CANCELLED`, increment `cancellation_epoch` from 0
to 1, set `cancel_requested_at`, bounded `cancel_request_id`, `terminal_at`,
`cancellation_result_code=LOCAL_CANCELLED`,
`terminal_result_code=LOCAL_CANCELLED`, write Audit, and commit. It invokes no
Runtime. A repeat is idempotent for the issuer and writes no second Audit.

The phrase “no Runtime-send marker” is exactly the database invariant
`state='authorized'`, null `authorize_requested_at`/`authorize_request_id`,
`authorize_attempt_count=0`, and `authorize_last_result_code=NOT_REQUESTED`.
Before any future Runtime authorize UDS call, Slice 3.2b must use
`BEGIN IMMEDIATE`, reload the exact Attempt and bound entities, require
`AUTHORIZED` and `agentbox_now_utc6() < expires_at`, transition to
`AUTHORIZE_PENDING`, persist request time/ID, count 1 and `REQUEST_PERSISTED`,
write `provider_secret.authorize_pending`, and commit. Only then may it send the
already approved tuple and same `psi_*`. A Runtime call while `AUTHORIZED` is a
contract violation. A crash before send or after send/response loss remains
durably `AUTHORIZE_PENDING`.

Recovery from `AUTHORIZE_PENDING` always calls the authenticated bounded
`runtime.provider_secret.provision.status` for the same `psi_*` before any
transmission decision. The exact mapping is: `STAGED`, `CONSUMING`,
`COMMITTED_UNVERIFIED`, `VERIFIED`, and `EXPIRED` follow the corresponding
matrix rows; unexpected `CANCELLED`, `FAILED`, `NEEDS_ATTENTION`, or
`EXPIRED_UNRECONCILED`, and malformed/contradictory evidence enter
`NEEDS_ATTENTION`; transport unavailability remains `AUTHORIZE_PENDING`.
Authenticated exact `NOT_FOUND` before expiry permits only a byte-identical
same-intent resend: same `psi_*`, digest, tuple, issue/expiry, and cancellation
epoch. Its incremented count, new request ID/time and `RESEND_PERSISTED` commit
before transmission. Counts 1–3 are the only transmissions; an attempted
fourth is prohibited and terminalizes to `NEEDS_ATTENTION` with the exact codes
in the matrix. `NOT_FOUND` at/after expiry becomes
`INTENT_EXPIRED_NOT_FOUND_CONFIRMED`. No recovery returns to `AUTHORIZED`,
generates a new `psi_*`, or derives authority from Job, lease, Audit, timeout,
or response absence.

Slice 3.2b cancellation after `AUTHORIZE_PENDING` or `RUNTIME_STAGED` must
transition locally to
`CANCEL_PENDING`, increment the server-controlled epoch, and request Runtime
cancellation for the same `psi_*`. Control Plane cannot set `CANCELLED` until
an authenticated exact Runtime response confirms `CANCELLED` for that same
`psi_*` and cancellation epoch. Lost response leaves
`CANCEL_PENDING` and status is queried by the same `psi_*`; Runtime already
`CONSUMING` moves to observed `RUNTIME_CONSUMING` with
`RUNTIME_CANCEL_LOST_TO_CONSUMING`; verified status moves to
`RUNTIME_VERIFIED`; committed-unverified status moves to
`RUNTIME_COMMITTED_UNVERIFIED`; exact expiry moves to `EXPIRED` with
`RUNTIME_CANCEL_LOST_TO_EXPIRY`; contradiction becomes `NEEDS_ATTENTION` with
`RUNTIME_CANCEL_CONTRADICTION`/`RUNTIME_STATUS_CONTRADICTION`. There is no blind
resend, new intent, caller-selected epoch, or state rollback.

Crash-window recovery is exact:

| Window | Authority/recovery |
|---|---|
| issued, not consumed | Challenge already owns the approved `psi_*`; terminalization burns it |
| consume rolls back | no attempt; challenge remains issued unless mismatch/expiry terminalization committed |
| consumed before Runtime admission | `AUTHORIZED` atomically copies the approved `psi_*` and proves no Runtime request was admitted |
| pre-send marker commits, process crashes before send | durable `AUTHORIZE_PENDING`; exact same-`psi_*` status first; never local cancel/expire |
| Runtime receives authorize, response/state update lost | durable `AUTHORIZE_PENDING`; exact status first; bounded byte-identical resend only after authenticated pre-expiry `NOT_FOUND` |
| three authorize transmissions remain `NOT_FOUND` | prohibit a fourth and enter `NEEDS_ATTENTION` |
| Runtime staged, response lost | exact status by `psi_*`; never generate a replacement |
| Runtime consuming across restart | status/reconciliation only; no blind resend or second attempt |
| Runtime committed but unverified | `RUNTIME_COMMITTED_UNVERIFIED`; encrypted material may exist and state is never retryable/pre-write |
| Runtime reports exact expiry | terminal code distinguishes unsent, confirmed not-found, and Runtime-confirmed expiry; cancellation loss records its exact code |
| Runtime verified while Control Plane unavailable | retained `RUNTIME_VERIFIED`/Runtime attestation is reconciled against exact tuple |
| attestation received, CP crashes | state remains pre-transition or `RUNTIME_VERIFIED`; same attestation is conditionally idempotent |
| Credential update commits, acknowledgement lost | future exact status observes Credential revision/reference and repeats only acknowledgement |
| Session expires after consumption | status/reconciliation is system recovery against durable attempt, not a new authorization |
| challenge retention reached | FK protects it until attempt is terminal and independently retention-eligible |
| entity revision stale | attempt becomes `NEEDS_ATTENTION`; no rebinding |
| simultaneous attempts | partial unique index permits one unresolved attempt per Credential |
| local cancel response lost | committed `AUTHORIZED -> CANCELLED` is read idempotently; Runtime was never contacted |
| Runtime cancel response lost | remain `CANCEL_PENDING` and query exact `psi_*` status |

## 25. Retention and pruning

An `ISSUED` challenge is never pruned. Cleanup first materializes expiry.
Legal terminalization sets immutable `retention_eligible_at` to exactly
`terminal_at + 30 days` for safely prunable rows and permanently null for
`NEEDS_ATTENTION`. Terminal challenges become eligible only at that stored
boundary, and deletion additionally requires no retained Attempt FK;
therefore a consumed Challenge for `NEEDS_ATTENTION` remains retained.
Only safely terminal `RECONCILED`, locally/Runtime-confirmed `CANCELLED`, and
safely confirmed `EXPIRED` attempts are eligible for ordinary pruning, exactly
30 days after `terminal_at`.

`NEEDS_ATTENTION` is unresolved and fail-closed, not time-prunable. It remains
inside `uq_provider_secret_attempts_unresolved_credential`; a Credential with
such a row can receive neither a new Challenge nor Attempt. Ordinary
maintenance and direct SQL cannot delete, abandon, resolve, or make it
retryable because both the partial index and delete trigger remain active. A future
separately authorized lifecycle review/operation is required. At most one
unresolved row per Credential bounds repeated-attempt growth. Its consumed
Challenge remains protected by FK, and Runtime orphan material never becomes
eligible because time passed. Audit retention remains independent.

One maintenance invocation uses one `BEGIN IMMEDIATE` and selects at most 100
**total** candidate rows across all categories through one deterministic union:

1. priority 1: materialize elapsed `ISSUED -> EXPIRED` Challenges and unsent
   `AUTHORIZED -> EXPIRED/INTENT_EXPIRED_UNSENT` Attempts, ordered by
   `(expires_at, id)`. `AUTHORIZE_PENDING`, `RUNTIME_STAGED`, and
   `CANCEL_PENDING` require exact Runtime status and are never expired from the
   wall clock alone;
2. priority 2: delete eligible safe terminal Attempts, ordered by
   `(terminal_at, id)`;
3. priority 3: delete eligible terminal Challenges having no retained Attempt,
   ordered by `(terminal_at, id)`;
4. priority 4: selectively delete retention-eligible Session rows having no
   retained Challenge/Attempt, ordered by `(retention_eligible_at, id)`.

The union orders by `(priority, eligible_at, id)` and applies one `LIMIT 100`;
therefore all four category counts sum to 0–100. The existing internal
maintenance owner is the only caller; cutoff, order, priority, and batch are
server constants. One Audit event `provider_secret.maintenance_completed`
records exactly the integer keys `approval_expired_count`,
`attempt_pruned_count`, `challenge_pruned_count`, and
`auth_context_pruned_count`, each 0–100 and with a sum no greater than 100.
Busy/rollback performs no partial change and retries next run. FK `RESTRICT`
remains authoritative. Maintenance deletes through both database delete guards
with one transaction-pinned `agentbox_now_utc6()`; it cannot bypass the stored
boundary. Only confirmed-safe `EXPIRED` rows are ordinarily prunable, expiry
never generates a replacement intent, and Runtime encrypted material never
becomes reusable.

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
all `0004` indexes/triggers/constraints—including
`uq_provider_credentials_id_provider` required by the untouched Compatibility
Evidence FK and the old global `uq_provider_credentials_provider` only because
the Credential table is proven empty—verify counts/schema/FKs, and use the
same §14 `AUTOCOMMIT`/`BEGIN IMMEDIATE` runner so schema and predecessor version
row commit atomically before FK re-enable/post-checks. The complete Credential
identity trigger and `uq_sessions_id_user` are removed only when the empty/
unused downgrade predicates have passed. A verified backup is required by
deployment lifecycle before attempting downgrade. Feature use
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
| `reauth_succeeded` | `auth_context`/null | `succeeded` | `auth_context_fingerprint`, `source_fingerprint`, `reason=credentials_rotated` |
| `reauth_failed` | `auth_context`/null | `failed` | `auth_context_fingerprint` when an authenticated context existed, `source_fingerprint`, `reason` from §17 |
| `provider_secret.challenge_issued` | `confirmation_challenge`/`cch_*` | `succeeded` | `runtime_installation_id`, `runtime_revision`, `provider_id`, `provider_revision`, `credential_id`, `credential_revision`, `auth_context_fingerprint`, `auth_epoch`, `purpose`, `expires_at`, `approval_digest`, `provisioning_intent_id` |
| `provider_secret.challenge_cancelled` | challenge | `succeeded` | `purpose`, `terminal_result_code`, `runtime_installation_id`, `provider_id`, `credential_id`, `provisioning_intent_id`, `auth_context_fingerprint` |
| `provider_secret.challenge_consumed` | challenge | `succeeded` | `provisioning_attempt_id`, `provisioning_intent_id`, `runtime_installation_id`, `runtime_revision`, `provider_id`, `provider_revision`, `credential_id`, `credential_revision`, `approval_digest`, `auth_context_fingerprint` |
| `provider_secret.challenge_rejected` | challenge or null | `rejected` | `reason_code` from public closed codes; `id_well_formed` bool; no target tuple for unknown/wrong actor |
| `provider_secret.attempt_created` | `provider_secret_provisioning_attempt`/`psa_*` | `succeeded` | `challenge_id`, `provisioning_intent_id`, `runtime_installation_id`, `runtime_revision`, `provider_id`, `provider_revision`, `credential_id`, `credential_revision`, `state=authorized`, `approval_digest`, `auth_context_fingerprint` |
| `provider_secret.authorize_pending` | attempt | `succeeded` | `from_state=authorized`, `to_state=authorize_pending`, `attempt_count=1`, `authorize_result_code=REQUEST_PERSISTED`, `runtime_installation_id`, `provider_id`, `credential_id`, `provisioning_intent_id`; request ID uses the dedicated Audit request column |
| `provider_secret.authorize_status_checked` | attempt | `succeeded`, `failed`, `needs_attention` | `from_state`, `to_state`, `attempt_count`, `authorize_result_code`, `runtime_status`, `runtime_installation_id`, `provider_id`, `credential_id`, `provisioning_intent_id`; `runtime_status` is one closed status label, never raw output |
| `provider_secret.authorize_retry_admitted` | attempt | `succeeded` | `state=authorize_pending`, `attempt_count`=2 or 3, `authorize_result_code=RESEND_PERSISTED`, `runtime_installation_id`, `provider_id`, `credential_id`, `provisioning_intent_id`; request ID uses the dedicated Audit request column |
| `provider_secret.cancel_pending` | attempt | `succeeded` | `from_state`, `to_state=cancel_pending`, `cancellation_result_code=RUNTIME_CANCEL_REQUESTED`, `runtime_installation_id`, `provider_id`, `credential_id`, `provisioning_intent_id` |
| `provider_secret.attempt_transitioned` | attempt | `succeeded`, `failed`, `needs_attention` | `from_state`, `to_state`, `authorize_result_code`, `terminal_result_code`, `cancellation_result_code`, `runtime_attestation_code`, `runtime_installation_id`, `provider_id`, `credential_id`, `provisioning_intent_id`; nullable codes are recorded only in the exact matrix rows |
| `provider_secret.maintenance_completed` | `provider_secret_maintenance`/null | `succeeded` | `approval_expired_count`, `attempt_pruned_count`, `challenge_pruned_count`, `auth_context_pruned_count`, each int 0–100 and total ≤100 |
| `phase11_0005.migration_blocked` | `database`/null | `blocked` | `reason_code`, `credential_row_count` nonnegative int; emitted only when application-owned migration Audit is transactionally available, otherwise normalized installer log code only |

Audit/logs prohibit Secret value/prefix/suffix/hash/fingerprint/length,
ciphertext, root key, KEK/DEK, wrapped DEK, nonce, tag, AAD, terminal input,
Session token/hash, CSRF, password, confirmation plaintext, canonical document,
arbitrary JSON, raw exception, Runtime Store path, endpoint Authorization, or
Secret-shaped metadata keys. Opaque `sec_*` is not created in Slice 3.2a and is
not part of these events.

Every key above is an exact literal and must pass the existing
`sanitize_metadata()` implementation without changing its forbidden substring
list or 16-key/scalar bounds. In particular, no metadata key contains
`password`, `token`, `secret`, `cookie`, `authorization`, `csrf`, `session`, or
`private_key`. `auth_context_fingerprint` is computed exactly as §17 and is the
only durable auth-context correlation; raw Session ID is absent from Audit.
Audit result values are exactly `succeeded`, `failed`, `rejected`,
`needs_attention`, or `blocked` as enumerated per action in this table.

## 28. Threat-model mapping

Threats T-112 through T-144 in `docs/THREAT_MODEL.md` cover ambiguous legacy
adoption, cross-Runtime references, owner mutation, cardinality, challenge
forgery/replay/digest substitution, Session binding/revocation races,
cancellation/double consumption, revision TOCTOU, expiry/clock rollback,
enumeration, retention/pruning, false Audit/Job authority, crash atomicity,
migration/downgrade, Secret-shaped generic metadata, atomic insert/consume,
durable pre-send admission, bounded recovery, committed-unverified Runtime
state, confirmed expiry, deletion guards, migration races, UTC6 storage, and
the complete state/result cross-product. The residual
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
- verify retained `uq_provider_credentials_id_provider`; after the Credential
  rebuild, insert a valid existing Compatibility Evidence child and reject
  missing/mismatched `(credential_id, provider_id)` children;
- cross-Runtime profile direct SQL and repository rejection; direct updates of
  Credential `id`, Provider, Runtime, kind, or creation time fail with `IS NOT`
  trigger while typed lifecycle fields remain eligible;
- cardinality, Claude rejection, revision races, and all-or-none create/Audit;
- Session migration and `uq_sessions_id_user`; direct-SQL Admin A/Session B
  Challenge/Attempt rejection; selective cleanup proves one protected Session
  does not block unrelated eligible rows;
- explicit re-auth rotates token hash and CSRF verifier while preserving row ID
  and absolute expiry; old Cookie/CSRF rejection, timestamp constraint,
  auth-epoch cancellation, rate-limit-before-Argon2, bounded semaphore,
  password-hash race, token collision, and pre/post-commit crash tests;
- challenge ID entropy/grammar/collision, purpose closure, strict field inventory,
  immutable tuple/state transition direct SQL, one-issued partial index, exact
  terminal codes, and digest golden vectors including approved `psi_*`, intent
  times/epoch, Unicode/null/timestamp/integer cases;
- typed confirmation exactness, no plaintext logs/Audit, one-attempt mismatch;
- exact five-minute equality, restart, forward/backward clock, stale revisions,
  wrong owner/actor/Session/purpose, malformed/unknown ID normalization;
- concurrent consume/consume and consume/cancel with exactly one winner;
- fault injection before/after every consume/attempt/Audit statement and commit;
- direct-SQL mismatched Challenge/Attempt tuple/digest/intent rejection,
  immutable `authorization_request_id`, trigger-driven insert/consume atomicity,
  forced rollback after insert, consume-without-Attempt rejection, Attempt
  immutability, forward-only transitions, early reconcile rejection,
  and one-unresolved-attempt guard including `NEEDS_ATTENTION`;
- `AUTHORIZED` null/zero pre-send invariant; Runtime call spy proves every call
  follows committed `AUTHORIZE_PENDING`; crash before send and after send;
- every exact status mapping from `AUTHORIZE_PENDING`, byte-identical same-`psi_*`
  resend, persisted counts 1–3, prohibited fourth transmission, unavailable and
  malformed status, no new intent, and no return to `AUTHORIZED`;
- `RUNTIME_COMMITTED_UNVERIFIED` with and without supplied Runtime commit time;
  local Attempt cancellation, `CANCEL_PENDING`, lost acknowledgement,
  consume/commit/verify/expiry wins and contradictory status recovery tests;
- all §24 crash windows and proof that neither Job nor Audit is authority;
- retention cutoff equality, global 100-row total, deterministic category/order,
  both database delete guards, issued/active deletion rejection, safe terminal
  deletion after boundary, Challenge only after Attempt deletion,
  `NEEDS_ATTENTION` rejection after 1/90/arbitrary days, FK protection,
  selective Session pruning,
  contention, and safe/unsafe downgrade;
- temporary/fixture migration tests prove no active transaction before FK off,
  FK-ON outer checks, writer fence, FK-OFF locked rechecks, one explicit
  `BEGIN IMMEDIATE`, schema plus Alembic version rollback under injected failure
  before body/after DDL/after version, post-commit failure simulation, exact
  trigger inventory, and verified backup/WAL/SHM restoration gate;
- raw SQLite UTC6 storage/round-trip, aware-UTC bind and load, offset/grammar
  rejection, microseconds `000000`/`999999`, exact five-minute and 30-day
  equality, backward clock, clock-function absence, and RFC3339Z digest vectors;
- generated coverage proves every state/event row has its exact null/non-null
  fields, timestamps, four result-code dimensions, terminal/retention/unresolved
  flags, and Audit action/result; raw Runtime text/exception rejection;
- every Audit metadata literal passes current `sanitize_metadata`; forbidden
  keys including raw Session correlation fail before reaching an authority
  transaction; re-auth and approval Audit contains only the exact allowlists;
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

- Slice 3.2a Architecture Review: `REQUEST CHANGES` from the second human review;
  this corrected contract awaits the third human Architecture/Security Review;
- Slice 3.2a prospective implementation decision: `AUTHORIZED`;
- Slice 3.2a implementation: not started and not authorized to begin;
- Slice 3.2b implementation: not authorized;
- Secret provisioning: blocked.

## 33. Decision matrix

| PR #39 correction blocker | Decision location | Closed |
|---|---|---|
| Compatibility Evidence parent key | §§9, 11, 14, 26, 30 | Yes |
| complete Credential identity immutability | §§9, 26, 30 | Yes |
| approval-bound pre-generated `psi_*` | §§15, 18, 20, 22, 24 | Yes |
| re-auth credential rotation | §§14, 17, 27, 30 | Yes |
| Admin/Session composite identity and selective cleanup | §§14, 15, 17, 24, 25 | Yes |
| sanitizer-compatible Audit | §§17, 27, 30 | Yes |
| Challenge database authority | §§15–16, 20–23 | Yes |
| Attempt database authority | §§22, 24 | Yes |
| durable local/Runtime cancellation | §§21, 24–25 | Yes |
| fail-closed `NEEDS_ATTENTION` | §§24–25 | Yes |
| exact Alembic/FK/version transaction | §§14, 26, 30 | Yes |
| one global 100-row cleanup bound | §§17, 25, 30 | Yes |
| terminal/result enum closure | §§15, 23–24, 27 | Yes |
| corrected threats | §28 and T-112–T-144 | Yes |
| atomic Attempt/Challenge trigger handshake | §§15, 22, 24, 30 | Yes |
| durable `AUTHORIZE_PENDING` pre-send marker | §24 | Yes |
| exact status-first bounded retransmission | §24 | Yes |
| `RUNTIME_COMMITTED_UNVERIFIED` | §24 | Yes |
| Runtime-confirmed expiry and cancellation loss | §§24–25 | Yes |
| Challenge/Attempt delete guards | §§15, 24–25 | Yes |
| `NEEDS_ATTENTION` non-deletability | §§24–25 | Yes |
| complete state/field/code/Audit matrix | §§24, 27, 30 | Yes |
| corrected Alembic three-phase runner | §§14, 26, 30 | Yes |
| raw UTC6 versus canonical RFC3339Z | §§18, 18A, 23, 30 | Yes |
| second-review threat corrections | §28 and T-112–T-144 | Yes |

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

The only next action is **Third Human Architecture/Security Review of the
corrected Draft PR #39**. Implementation must not start in this execution.
