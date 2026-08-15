# AgentBox MVP Data Model

Status: Phase 1 logical design with the Phase 3 control-plane, Phase 7
Project/Job subset, and Phase 11 non-secret Provider core implemented.
Migration `0001_control_plane_foundation` creates `admin_users`, `sessions`,
and `audit_events`; migration `0002_project_jobs` adds `projects`, `jobs`, and
`job_events`; migration `0004_phase11_provider_core` adds only the typed,
non-secret Provider metadata schema described below. Runtime capability,
Setting, Diagnostic, and Confirmation tables remain future designs.
Development uses a configured path beneath `.agentbox-dev/` or a temporary
test directory; production retains the accepted
`/var/lib/agentbox/agentbox.db` policy and is not created by Phase 7.

## Database Decision

Use SQLite with SQLAlchemy and Alembic for the single-host MVP. Enable WAL mode, foreign keys, busy timeout, bounded transactions, and explicit write coordination. SQLite is not used as a distributed queue and no process shares the database over a network filesystem.

Database path: `/var/lib/agentbox/agentbox.db`, owned by `agentbox`, restrictive mode. Runtime Executor does not open it directly; Worker/API provide typed requests/results.

## General Conventions

- opaque application IDs; never reuse filesystem names or tmux names as primary keys;
- UTC timestamps and explicit revision numbers;
- enum values persisted as stable lower-case strings;
- soft state observations carry `observed_at` and freshness/confidence;
- user-supplied labels are separate from server-generated storage keys;
- summaries are bounded and sanitized before persistence;
- optimistic revision/state fingerprint for confirmation and stale-write protection;
- no generic JSON blob for privileged action arguments; Job payload is validated by versioned type schema.

## AdminUser

| Field | Purpose |
|---|---|
| `id` | opaque admin ID |
| `username_normalized` | unique single-admin login name |
| `display_name` | optional safe label |
| `password_hash` | Argon2id encoded hash only |
| `is_active` | account enabled state |
| `created_at` | creation time |
| `password_changed_at` | session-revocation boundary |
| `revision` | optimistic concurrency |

MVP enforces at most one active AdminUser. No plaintext/recoverable password is stored.

The Phase 3 physical model uses `id`, display `username`, unique normalized
username, Argon2id `password_hash`, `is_active`, `created_at`, `updated_at`, and
`last_login_at`. A SQLite partial unique index enforces at most one active row.
Display name, password-change boundary, and revision fields remain future work.

## Session

| Field | Purpose |
|---|---|
| `id` | opaque Session ID, not the cookie |
| `admin_user_id` | owner |
| `token_digest` | keyed digest of opaque browser session token |
| `created_at`, `last_seen_at` | lifecycle |
| `idle_expires_at`, `absolute_expires_at` | expiration |
| `recent_auth_until` | sensitive-action gate |
| `revoked_at`, `revoke_reason` | revocation |
| `csrf_digest` | verifier for CSRF token/secret |
| `client_class` | bounded Web/local label, no raw fingerprint |

This is an AgentBox application session verifier, not a third-party Token store. Raw session/cookie values are never persisted or audited. Migration restores revoke Sessions by default.

The Phase 3 physical model calls the keyed digest `token_hash`, stores a keyed
`csrf_hash`, has both idle and absolute expiry, revocation timestamp, and an
optional bounded client label. The raw cookie and raw CSRF value are not stored.
Restores revoking all Sessions remains a backup/restore policy for a later phase.

## Project

| Field | Purpose |
|---|---|
| `id` | opaque `prj_*` Project ID and API identity |
| `slug` | normalized bounded URL/filesystem-safe label, unique case-insensitively by normalization |
| `display_name` | bounded user-facing name, never an authorization boundary |
| `relative_path` | immutable server-derived immediate-child key, unique; never absolute |
| `source_type` | `empty`, `git_clone`, or reconciled `existing` |
| `repository_url` | validated credential-free clone identity or null |
| `default_branch` | bounded observed clone default branch or null |
| `state` | `creating`, `ready`, `error`, or `archived` |
| `archived_at` | future reversible archive timestamp; no filesystem deletion |
| `created_at`, `updated_at` | UTC lifecycle timestamps |

Canonical path is derived on every Runtime operation from the configured root
plus `relative_path` and revalidated. Absolute paths, Git observations, full
command output, workspace contents, numeric ownership, and Claude/tmux names
are not Project columns.

## RuntimeInstallation

| Field | Purpose |
|---|---|
| `id` | opaque Runtime installation identity |
| `runtime_type` | typed `codex` or `claude` identity |
| `display_name` | bounded administrator-facing label |
| `revision` | optimistic-concurrency value, initially 1 |
| `created_at`, `updated_at` | UTC lifecycle timestamps |

The Slice 1 table does not contain entrypoints, paths, executable observations,
process state, Runtime credentials, or auth-file metadata. Those observations
require the later read-only Runtime capability contract.

## RuntimeCapability

| Field | Purpose |
|---|---|
| `id` | capability observation ID |
| `runtime_installation_id` | parent |
| `name` | stable AgentBox capability enum |
| `state` | `supported`, `unsupported`, `unavailable`, `unauthenticated`, `broken`, `unknown` |
| `evidence_class` | public_help/status/managed_state/best_effort |
| `evidence_summary` | bounded and sanitized |
| `adapter_schema_version` | parser/fixture version |
| `observed_at`, `expires_at` | freshness |

Unique by installation/name/current observation policy.

## Provider

Migration `0004_phase11_provider_core` persists a concrete, non-secret Provider
definition in `provider_definitions`. `ProviderID` remains separate from
Credential, Runtime Profile, Runtime Binding, Session Binding, Runtime
installation, Codex Remote state, and private Runtime state.

| Field | Purpose |
|---|---|
| `id` | opaque `ProviderID` |
| `identity_schema_version` | versioned normalization/identity algorithm |
| `display_name` | safe administrator label |
| `provider_type` | `official_openai` or `openai_compatible`; no Local/Claude type in v1 |
| `endpoint` | normalized non-credential HTTPS destination identity; Official OpenAI is fixed |
| `wire_protocol` | typed `responses` intent |
| `model` | bounded model identifier |
| `state` | typed configured/validated/needs-attention/disabled metadata state |
| `created_at`, `updated_at`, `revision` | lifecycle and stale-write protection |

There is no arbitrary options/headers/environment map. Provider active status
is derived from a verified Runtime Binding; it is not stored on Provider.

## ProviderCredential

`provider_credentials` is control-plane lifecycle metadata only.

| Field | Purpose |
|---|---|
| `id` | opaque independent `CredentialID` |
| `provider_id` | owning Provider; v1 allows at most one Credential identity per Provider |
| `kind` | typed credential kind |
| `runtime_secret_ref` | opaque `sec_*` Runtime-owned reference, never material |
| `secret_version` | positive opaque Secret version reference |
| `state` | missing/configured/rotating/revoked/needs-attention metadata state |
| `created_at`, `updated_at`, `revision` | lifecycle and stale-write protection |

The table has no plaintext, ciphertext, key, nonce, tag, token, header, or
cryptographic storage. Slice 1 does not create a Secret backend.

## RuntimeProviderProfile

`runtime_provider_profiles` stores typed Codex Provider configuration intent,
not rendered Runtime configuration.

| Field | Purpose |
|---|---|
| `id` | opaque independent `RuntimeProfileID` |
| `runtime_installation_id` | exact Runtime identity |
| `provider_id`, `provider_revision` | exact Provider metadata revision |
| `credential_id`, `credential_revision`, `credential_secret_version` | optional exact non-secret Credential references |
| `adapter_type`, `adapter_schema_version` | typed Runtime adapter/schema intent |
| `state` | draft/valid/superseded/incompatible/needs-attention |
| `created_at`, `updated_at`, `revision` | lifecycle and stale-write protection |

Slice 1 admits Provider Profiles only for Codex. Claude remains Runtime-only.
No TOML, rendered config, path, command, environment, or snapshot bytes are
representable.

## RuntimeProviderBinding

| Field | Purpose |
|---|---|
| `id` | opaque independent `RuntimeBindingID` |
| `runtime_installation_id` | Runtime whose Provider selection is managed |
| `runtime_profile_id`, `runtime_profile_revision` | exact selected Profile intent |
| `provider_id`, `provider_revision` | exact effective Provider metadata revision |
| `state` | typed pending/activation/recovery/history state |
| `previous_binding_id` | optional bounded prior Binding identity |
| `created_at`, `updated_at`, `revision` | lifecycle and stale-plan protection |

The database partial unique index permits at most one `active` Binding per
Runtime. Slice 1 creates only `pending` Bindings and exposes no activation
operation. Persisted Binding rows cannot use `unmanaged`: absence of a managed
Binding yields the explicit logical `UNMANAGED` read state. Migration creates
no rows and does not adopt an existing Runtime.

## RuntimeSessionProviderBinding

`runtime_session_provider_bindings` is immutable historical effective-state
evidence with independent `SessionBindingID`, Runtime session ID, installation,
Binding/Profile/Provider IDs and exact revisions, typed evidence class/state,
and timestamps. SQLite triggers reject update and delete. The migration does
not inspect or backfill existing sessions and stores no conversation, private
Runtime, Credential, or Secret data.

## ProviderCompatibilityObservation

One row records one typed dimension in a bounded observation set. Provider
endpoint, Network, Authentication, Model, Wire Protocol, Provider API, Codex
Runtime, Remote, Resume, Context, and Discovery remain independent. Each is
`pass`, `fail`, `unsupported`, `experimental`, `unknown`, or `not_tested`, with
schema, bounded non-secret evidence code, and freshness timestamps. Slice 1
does not perform tests or network requests.

## ProviderConfigTransaction

The additive table reserves only typed non-secret orchestration relationships:
transaction identity/state, Runtime and Binding identity, optional Job,
expected Binding/Profile/Provider/Credential revisions, plan digest, opaque
Runtime-owned snapshot reference, bounded outcome code, revision, and
timestamps. Slice 1 implements no transaction executor or mutation operation.
It never stores raw config, snapshot bytes, Secret material, Authorization,
Provider response bodies, prompts, model output, or private Runtime/session
artifacts.

Raw API keys, API-key hashes/suffixes, complete Runtime config, arbitrary TOML,
Codex SQLite/session DB, JSONL, rollout, and thread metadata are prohibited
Provider-domain fields and migration targets.

## RuntimeSession

| Field | Purpose |
|---|---|
| `id` | opaque session ID |
| `runtime_type` | Claude first; Codex managed daemon may use a distinct subtype |
| `project_id` | required for Claude |
| `installation_id` | selected Runtime |
| `session_key` | server-generated tmux/managed identifier |
| `display_name` | safe UI label |
| `linux_identity` | logical `agentbox-runtime` |
| `state` | `starting`, `running`, `stopping`, `stopped`, `failed`, `unknown`, `unmanaged_conflict` |
| `managed` | AgentBox ownership flag |
| `started_at`, `stopped_at`, `observed_at` | lifecycle |
| `last_error_code`, `last_error_summary` | sanitized failure |
| `revision` | stale action protection |

No pane output, Pair Code, auth state content, full command, or environment is stored.

## Job

Required core fields:

| Field | Purpose |
|---|---|
| `id` | opaque Job ID |
| `type` | versioned allowlisted Job type |
| `status` | state enum |
| `created_at` | accepted time |
| `started_at` | first execution time |
| `finished_at` | terminal time |
| `requested_by` | AdminUser/local principal ID |
| `target_type` | project/runtime/session/system/release/diagnostic |
| `target_id` | opaque resource ID |
| `progress` | 0–100 or null with phase label |
| `result_summary` | bounded sanitized human summary |
| `error_code` | stable normalized code |
| `error_summary` | bounded sanitized summary |

Additional execution fields:

| Field | Purpose |
|---|---|
| `payload_schema_version` | validates typed payload |
| `payload_json` | bounded type-specific non-secret JSON |
| `idempotency_key_digest` | deduplicate accepted request |
| `resource_lock_key` | serialize conflicting work |
| `attempt` / `max_attempts` | retry policy |
| `lease_owner`, `lease_expires_at` | crash recovery |
| `heartbeat_at` | worker liveness |
| `request_id` | correlation |

Statuses:

- `queued`
- `running`
- `succeeded`
- `failed`
- `cancelled` (reserved state; no Phase 7 cancellation endpoint)
- `needs_attention`

Allowed transitions are explicit. Terminal states do not return to running. A new retry becomes a new Job linked by correlation, unless the same lease attempt is safely requeued by recovery rules.

Prohibited payload/result data: tokens, passwords, cookies, OAuth codes, Pair Codes, SSH keys, auth files, full environment, arbitrary command/argv/path, or raw stdout/stderr.

## JobEvent

Small bounded events support SSE replay:

| Field | Purpose |
|---|---|
| `sequence` | monotonic cursor |
| `job_id` | Job |
| `event_type` | queued/started/progress/final/heartbeat category |
| `status`, `progress`, `phase` | safe state |
| `summary` | bounded sanitized text |
| `created_at` | ordering |

Events have short retention and never contain secret results or command output.

## AuditEvent

| Field | Purpose |
|---|---|
| `id` | event ID |
| `occurred_at` | UTC time |
| `actor_type`, `actor_id` | admin/local/system |
| `action` | stable action enum |
| `target_type`, `target_id` | opaque target |
| `request_id`, `job_id` | correlation |
| `outcome`, `error_code` | result |
| `confirmation_required`, `confirmed` | confirmation metadata |
| `metadata` | strictly allowlisted non-secret small fields |

There is no raw request/response body, command output, token, Pair Code, password, cookie, public IP, or auth configuration.

Phase 3 implements the core actor/action/target/result/request-ID/timestamp
fields and `metadata_json`. Metadata is a maximum-16-field flat scalar map with
length limits, newline neutralization, and secret-key rejection. Job and
confirmation correlation fields are deferred with those models.

## Setting

| Field | Purpose |
|---|---|
| `key` | allowlisted typed key |
| `value` | non-secret typed JSON only |
| `schema_version` | validation |
| `source` | default/admin/config |
| `updated_at`, `updated_by` | auditability |
| `revision` | concurrency |

There is no generic secret setting and no Token table. Runtime credentials remain managed by third-party CLIs in Runtime HOME and are never surfaced to this model.

## DiagnosticRun

| Field | Purpose |
|---|---|
| `id` | run ID |
| `job_id` | execution Job |
| `scope` | safe enum |
| `started_at`, `finished_at` | lifecycle |
| `overall_state` | healthy/warnings/broken/unknown |
| `finding_counts` | severity counts |
| `environment_snapshot_id` | non-secret fact set reference |

Findings use a child logical structure with stable code, severity, component, sanitized evidence, remediation plan, and `requires_human_approval`. No raw log bundle is stored.

## ConfirmationChallenge

| Field | Purpose |
|---|---|
| `id` | challenge ID |
| `admin_user_id`, `session_id` | bound actor/session |
| `action` | exact action enum |
| `target_type`, `target_id` | exact target |
| `target_revision` | state fingerprint |
| `preview_digest` | binds reviewed plan |
| `verifier_digest` | hash of one-time challenge proof |
| `required_phrase_kind` | exact-name/action phrase policy |
| `created_at`, `expires_at`, `used_at` | one-time lifecycle |
| `request_id` | correlation |

The proof is treated as transient authorization material; only a digest is stored. A changed target/plan/session invalidates it.

## Relationships

```mermaid
erDiagram
    AdminUser ||--o{ Session : owns
    AdminUser ||--o{ Job : requests
    AdminUser ||--o{ ConfirmationChallenge : receives
    Project ||--o{ RuntimeSession : hosts
    RuntimeInstallation ||--o{ RuntimeCapability : advertises
    RuntimeInstallation ||--o{ RuntimeSession : runs
    RuntimeInstallation ||--o{ RuntimeProviderProfile : configures
    RuntimeInstallation ||--o{ RuntimeProviderBinding : selects
    Provider ||--o| ProviderCredential : authenticates_with
    Provider ||--o{ RuntimeProviderProfile : targets
    RuntimeProviderProfile ||--o{ RuntimeProviderBinding : selected_by
    RuntimeProviderBinding ||--o{ RuntimeSessionProviderBinding : evidenced_by
    Provider ||--o{ ProviderCompatibilityObservation : observed_by
    RuntimeProviderBinding ||--o{ ProviderConfigTransaction : changes_through
    Job ||--o{ JobEvent : emits
    Job ||--o| DiagnosticRun : executes
    Job ||--o{ AuditEvent : correlates
    Project ||--o{ Job : targeted_by
```

## Worker and SQLite Execution Model

### Evaluation

- In-process API asyncio worker: rejected as primary; API restart/deployment would interrupt work and couple request availability to subprocess lifecycle.
- Redis/Celery/distributed queue: deferred; excessive for one host and adds operational/security dependencies.
- Separate systemd Worker with SQLite Job table: selected.

The Worker may use asyncio internally for subprocess timeouts and event handling, but it is a distinct process/service. Default concurrency is one; carefully classified independent read-only work may later increase it.

### Claiming

Worker atomically changes one eligible queued Job to running with lease owner/expiry, respecting global/resource locks and attempts. A short transaction protects the claim; the long action happens outside the transaction. Heartbeats renew leases.

### Recovery After Restart

- queued: remains eligible;
- running with an expired lease: `needs_attention`, never blind replay in Phase 7;
- Pair operation: no persistent secret result; interrupted delivery is discarded and regenerated by a new request.

### Progress and SSE

Worker writes coarse non-secret phases and percentages. While a bounded Runtime
RPC is active it renews the Job lease without emitting noisy progress rows. SSE
reads JobEvent rows and does not hold a Worker connection.

## Retention

- Completed Jobs/JobEvents, Audit Events, Sessions, and login-limiter buckets
  have independent bounded retention policies with safe defaults.
- Pair Codes never participate in retention.
- JobEvents are deleted only with their verified terminal parent Job through the
  database relationship; active Jobs and their events are never selected.
- Diagnostics export creates only the operator-selected new file. AgentBox has
  no diagnostics temp directory or automatic deletion policy; the operator owns
  retention of that report.
- Phase 9 exposes no generic purge or arbitrary backup/audit deletion operation.
- Database maintenance checks free disk and never blocks the API indefinitely.

Phase 9 adds a bounded `login_rate_limit_buckets` table. Its key is a
pseudonymous keyed digest of the normalized account/source tuple; raw account
names and IP addresses are not stored. Each row contains only the bucket key, a
bounded failure-timestamp list, update time, and optional bounded lock expiry.
Expired rows are removed. At the fixed maximum, admission fails closed rather
than evicting active spray evidence, so restart persistence cannot become
unbounded state or a permanent lockout.

Default operational retention is 14 days for completed Jobs/JobEvents and 90
days for Audit Events. Lifecycle storage separately keeps five verified SQLite
backups and four verified releases while protecting the active and direct
rollback identities. Unknown, corrupt, or symlinked objects are retained for
operator review rather than inferred to be AgentBox-owned.

## Future PostgreSQL Boundary

Repositories depend on SQLAlchemy models/repositories and transaction abstractions, not SQLite-specific SQL in routes/services. Job claim and migration behavior is isolated. Moving to PostgreSQL is a future multi-server decision; MVP does not pretend SQLite provides multi-host leases.
