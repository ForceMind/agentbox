# AgentBox API Design

Status: Phase 1 contract design with the Phase 3 control plane, Phase 4 Web,
Phase 5 Codex, Phase 6 Claude, and Phase 7 Project/Job/Git/GitHub subsets
implemented on their respective release branches.

Implemented in Phase 3: `GET /healthz`, `GET /readyz`, `GET /api/v1/meta`,
`POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, and
`GET /api/v1/auth/me`. Phase 4 implements authenticated
`GET /api/v1/doctor`. Phase 5 implements the four Codex routes identified
below. Later-phase contracts are explicitly marked as designs.

## Principles

- All application endpoints begin with `/api/v1` from the first release.
- Browser API is cookie-authenticated, CSRF-protected, same-origin, and loopback by default.
- Local CLI uses the same HTTP contracts over `/run/agentbox/api.sock` with OS peer authorization.
- Mutations use typed actions and durable Jobs unless explicitly documented as a bounded secret response.
- No endpoint accepts arbitrary shell, executable, argv, environment, systemd unit, package name, or absolute filesystem path.
- Pair Codes and other prohibited secrets are never resources that can be retrieved later.

## Media Types and Envelope

JSON requests use `application/json`. Normal resources return the resource body plus:

```json
{
  "api_version": "v1",
  "request_id": "req_...",
  "data": {},
  "meta": {}
}
```

Errors use:

```json
{
  "api_version": "v1",
  "request_id": "req_...",
  "error": {
    "code": "RUNTIME_UNSUPPORTED",
    "category": "unsupported",
    "message": "Safe human-readable summary",
    "retryable": false,
    "details": {}
  }
}
```

`details` is schema-specific, bounded, and never raw command output. Unknown JSON request fields are rejected on sensitive/mutating endpoints.

## Common Semantics

- UUID-like opaque IDs use prefixes such as `prj_`, `job_`, `ses_`, `run_`, `cnf_`; the format is not a filesystem name.
- Timestamps are UTC RFC 3339 in API responses.
- `Idempotency-Key` is required for Job-creating POSTs and scoped to administrator/action/target.
- Pagination is cursor-based with server maximums.
- Mutations return `202 Accepted` and a Job except Pair Code and authentication operations.
- Conditional mutation uses resource revision/state fingerprint to prevent stale confirmation.
- HTTP status and stable error category both matter.

## Authentication API

| Method/path | Purpose | Notes |
|---|---|---|
| `POST /api/v1/auth/login` | create Session | rate-limited; body never logged; cookie response no-store |
| `POST /api/v1/auth/logout` | revoke current Session | CSRF required |
| `GET /api/v1/auth/me` | current admin/session/expiry and session-bound CSRF token | no Session token value; response no-store |
| `POST /api/v1/auth/re-authenticate` | mark recent authentication | password body suppressed; short TTL |

The first three routes above are implemented in Phase 3. Re-authentication is a
future high-risk-action prerequisite and is not implemented yet. The CSRF token
is derived server-side from the Session and application secret, verified by a
stored keyed digest, and returned by login/`me`; there is no separate CSRF route.
Auth success uses the V1 envelope and contains only admin ID/name, Session ID and
absolute expiry, and the CSRF token. The raw Session token exists only in the
`agentbox_session` cookie and process memory.

First-admin creation is local CLI only and has no remote bootstrap endpoint.

## Confirmation API

| Method/path | Purpose |
|---|---|
| `POST /api/v1/confirmations` | create a typed challenge after preview/recent auth |
| `POST /api/v1/confirmations/{id}/verify` | submit typed confirmation and receive one-time authorization state |
| `GET /api/v1/confirmations/{id}` | status/expiry only |

Challenge requests use `action`, target opaque ID, resource revision, and preview ID. The server—not the caller—determines whether confirmation is required. There is no generic “confirm any action” flag.

## Dashboard API

| Method/path | Purpose |
|---|---|
| `GET /api/v1/dashboard` | summarized host/AgentBox/Runtime/Project/Job state |
| `GET /api/v1/system/status` | AgentBox components, versions, listener mode, capacity class |
| `GET /api/v1/meta` | API/service/protocol versions and top-level capabilities |

The Dashboard never exposes full process lists, public IPs, environments, tokens, or auth details.

## Generic Runtime API

| Method/path | Purpose |
|---|---|
| `GET /api/v1/runtimes` | list detected Runtime installations |
| `GET /api/v1/runtimes/{runtime_id}` | installation/version/source/health observation |
| `GET /api/v1/runtimes/{runtime_id}/capabilities` | Capability set with evidence/freshness |
| `POST /api/v1/runtimes/{runtime_id}/diagnostic-jobs` | bounded diagnostic Job |
| `POST /api/v1/runtimes/{runtime_id}/install-plan` | dry-run plan only |
| `POST /api/v1/runtimes/{runtime_id}/update-plan` | dry-run plan only |

Applying a plan uses a plan-specific Job endpoint and confirmation; clients cannot submit package names or commands.

## Codex API

| Method/path | Purpose | Result |
|---|---|---|
| `GET /api/v1/codex/status` | implemented installation/auth/capability/Remote status | no-store read model with confidence |
| `POST /api/v1/codex/remote/start` | implemented bounded typed start | direct action result |
| `POST /api/v1/codex/remote/stop` | implemented bounded typed stop | direct action result |
| `POST /api/v1/codex/pair-codes` | implemented ephemeral code generation | one-time no-store secret response |
| `POST /api/v1/codex/install-jobs` | apply approved install plan | Job |
| `POST /api/v1/codex/update-jobs` | apply approved update plan | Job |
| `GET /api/v1/codex/logs` | curated bounded managed-service logs | redacted page |

`POST /pair-codes` requires CSRF and recent authentication, is never idempotently replayed, has no GET counterpart, bypasses persistent Job result storage, and returns:

```json
{
  "api_version": "v1",
  "request_id": "req_...",
  "data": {
    "pair_code": "<one-time value>",
    "expires_at": "<if reported by Runtime, otherwise null>",
    "display_once": true
  }
}
```

The placeholder is contract documentation, not a real code. The implemented
response is `Cache-Control: no-store` plus `Pragma: no-cache`; it is not a Job,
SSE event, database resource, log field, or retrievable history. Start, stop,
and Pair accept no request body, executable, argv, environment, cwd, or process
identifier. All three require an authenticated Session, exact Origin/Host, and
Session-bound CSRF; Pair additionally requires recent authentication and is
subject to the Runtime Executor's cooldown.

Phase 5 direct actions are intentionally bounded while the durable Job worker
is not implemented. Install/update/log endpoints in this table remain designs,
not implemented routes.

## Future Provider, Secret, and Continuity API (Phase 11 planning only)

No endpoint in this section exists today. The future resource boundary is
Runtime-neutral and separate from `/codex/remote/*`. `ProviderDefinitionID`
selects concrete Provider metadata while `RuntimeBindingID` identifies stable
AgentBox binding intent; clients never supply a current Codex provider ID as a
permanent product identity. Activation may include a validated Runtime lifecycle
step inside its transaction, but cannot silently start/stop/pair/replace Remote
state or create a parallel daemon architecture.

Planned contract families, subject to Phase 11 public-contract revalidation:

| Method/path | Purpose | Security/result boundary |
|---|---|---|
| `GET /api/v1/providers` | list non-secret ProviderDefinition metadata | never Secret values |
| `POST /api/v1/providers` | create typed ProviderDefinition metadata | no raw API key in ordinary body; base URL participates in identity |
| `GET/PATCH/DELETE /api/v1/providers/{provider_id}` | inspect/edit/remove metadata | revision checks; active-reference policy |
| `GET /api/v1/providers/current` | Active Provider plus Runtime Binding metadata | selection, binding, Runtime/Remote/continuity evidence separated |
| `POST /api/v1/providers/{provider_id}/test-jobs` | connectivity, Runtime, or continuity test | explicit test kind; bounded/cost-aware; paid inference requires opt-in |
| `POST /api/v1/providers/{provider_id}/continuity-jobs` | dedicated thread/context/discovery assessment | public interfaces only; no session artifact mutation |
| `POST /api/v1/providers/{provider_id}/activation-plans` | preview writer/config/lifecycle/Remote/continuity impact | dry-run only; Provider/Binding/config revisions bound |
| `POST /api/v1/providers/{provider_id}/activation-jobs` | execute approved switching transaction | recent auth, confirmation, full snapshot, rollback verification |
| `POST /api/v1/providers/{provider_id}/secret-rotation-jobs` | rotate only this Provider's Secret material | dedicated transient Secret channel; retest auth/protocol |
| `POST /api/v1/provider-rollbacks` | restore an approved previous or pre-management state | never delete login, pairing, history, sessions, or Projects |

The Secret Manager write/replacement contract is deliberately not fixed here.
It requires approved Linux restrictive-file, macOS Keychain, and Windows
current-user DPAPI designs plus a dedicated transient input channel. An API must
never accept a raw API key in Provider metadata or return it from any GET.
Provider resources carry only an opaque Secret reference/configured-state.

Test results expose Network, Authentication, Model Availability, Wire Protocol,
Provider API, Codex Runtime, Remote Control, Thread Resume, Context Continuity,
and Thread Discovery independently using PASS/FAIL/UNSUPPORTED/EXPERIMENTAL/
UNKNOWN/NOT_TESTED. The aggregate Supported/Compatible/Experimental/Degraded/
Incompatible/Unknown classification never hides the matrix. Continuity levels
0–5 require their own evidence; lower-level success cannot set higher levels.

Config activation accepts neither raw TOML, arbitrary config keys, config path,
environment map, executable, Runtime ID mapping, nor restart flag. The server
creates a typed, revision-bound transaction plan using the then-current public
Runtime schema and public active-writer evidence. It owns Preflight, Snapshot,
Candidate, Atomic apply, required lifecycle action, layered verification,
Commit, and failure rollback. Results say `Rollback verified` only after
restored config, permissions, lifecycle, Active Provider, Runtime Binding,
generated profile, and Secret reference are verified.

## Claude API

| Method/path | Purpose |
|---|---|
| `GET /api/v1/claude` | installation/auth/public capability and safe tmux counts |
| `GET /api/v1/claude/sessions` | configured project session summaries |
| `GET /api/v1/claude/sessions/{project_id}` | exact project session state |
| `POST /api/v1/claude/sessions/{project_id}/start` | idempotent managed session start |
| `POST /api/v1/claude/sessions/{project_id}/stop` | stop exact marked managed session |
| `GET /api/v1/claude/sessions/{project_id}/output` | explicit ephemeral bounded pane output |

`project_id` is a formal opaque Project ID. The API resolves it to the immutable
relative Runtime key before UDS dispatch; it is never a submitted path.
Mutation bodies are rejected. Runtime UDS frames cannot contain path, argv,
shell, tmux flags, PID, signal, or environment. Responses distinguish
`running`, `stopped`, `starting`, `needs_interaction`, `broken`, and `unknown`;
tmux running is not automatically presented as Remote connected.

All Claude responses are `no-store`. Recent output is authenticated, capped at
200 lines/24 KiB after a stricter runner cap, terminal-control sanitized, and
marked sensitive. It is absent from Audit metadata, logs, DB, reports, and
automatic page loads. Authentication/Workspace Trust remains Unknown without a
public reliable signal.

## Project API

| Method/path | Purpose |
|---|---|
| `GET /api/v1/projects` | list formal Projects with bounded Git/Claude summaries |
| `POST /api/v1/projects` | queue empty Project Workspace creation |
| `POST /api/v1/projects/clone` | queue clone of an approved credential-free Git URL |
| `GET /api/v1/projects/{project_id}` | Project plus structured Git/GitHub observations |
| `GET /api/v1/projects/{project_id}/git` | structured Git status alias |
| `GET /api/v1/projects/{project_id}/git/branches` | bounded local branch list |
| `POST /api/v1/projects/{project_id}/git/branches` | queue ordinary branch creation |
| `POST /api/v1/projects/{project_id}/git/switch` | queue safe existing-branch switch |
| `POST /api/v1/projects/{project_id}/git/pull` | queue fast-forward-only Pull |
| `POST /api/v1/projects/{project_id}/git/push` | queue ordinary upstream Push, never force |
| `POST /api/v1/projects/{project_id}/github/pull-requests` | queue current-branch Draft PR creation |
| `GET /api/v1/github` | installed/version/public `gh auth status` summary |

There is no Project filesystem delete/archive endpoint, arbitrary file read,
arbitrary Git command/config/remote, staging, commit, force push, reset, clean,
branch delete, hook execution, submodule initialization, or workflow mutation.

Create request:

```json
{
  "name": "Display Name",
  "slug": "optional-normalized-slug"
}
```

Clone request concept:

```json
{
  "repository_url": "https://github.com/owner/repository.git",
  "name": "Optional Display Name",
  "slug": "optional-normalized-slug"
}
```

The server generates the opaque ID and relative path. URLs with userinfo,
credentials, query/fragment data, local/file/ext protocols, option-like forms,
or unsupported hosts/schemes are rejected.

## Job API

| Method/path | Purpose |
|---|---|
| `GET /api/v1/jobs` | filtered paginated Jobs |
| `GET /api/v1/jobs/{job_id}` | current Job state and sanitized result |
| `GET /api/v1/jobs/{job_id}/events` | authenticated bounded SSE replay for one Job |

SSE event types currently emitted are `job.queued`, `job.started`,
`job.progress`, `job.needs_attention`, `job.succeeded`, and `job.failed`, plus
transport heartbeats. Events carry sequence, Job ID, status, progress,
sanitized summary, and timestamp. They do not carry stdout/stderr, Pair Codes,
credentials, or project contents. Cancellation and global Job streams are not
implemented.

Reconnection uses `Last-Event-ID`/cursor backed by bounded non-secret Job event records.

## Logs API

| Method/path | Purpose |
|---|---|
| `GET /api/v1/logs` | curated AgentBox component log summaries |
| `GET /api/v1/logs/{component}` | bounded time/cursor filter for allowlisted component |

Callers cannot supply a journal unit name, file path, grep expression, or shell. Only AgentBox-owned component enums are accepted. Runtime recent output uses the dedicated Claude endpoint, not Logs API.

## Doctor API

| Method/path | Purpose |
|---|---|
| `GET /api/v1/doctor` | current control-plane readiness and safe policy summary |
| `POST /api/v1/doctor/runs` | start Diagnostic Run Job |
| `GET /api/v1/doctor/runs` | list runs |
| `GET /api/v1/doctor/runs/{run_id}` | findings, classifications, safe remediation plans |

The authenticated `GET` is implemented and returns
configuration validity, database reachability, migration currency,
administrator initialization, combined readiness, environment, loopback bind,
Session lifetime policy, login rate-limit policy, a safe Codex summary, and a
Phase 6 Claude/tmux summary (installation/version/auth Unknown-safe capability,
managed/unmanaged counts, Workspace interaction warnings, finding codes). It
is `Cache-Control: no-store` and excludes unmanaged names, project paths, pane
output, secrets, database URL, credentials, unrelated processes, general host
service state, and network state.

The three Diagnostic Run routes remain future designs. Doctor plans but does
not automatically repair. A remediation becomes a separately validated
action/Job.

Phase 8 production CLI Doctor extends local diagnostics with exact service,
identity, directory owner/mode, socket, loopback listener, Project Root, and
Runtime tool checks. This does not add a root-management HTTP endpoint. There
is no Web/API route for installer apply, package installation, update,
rollback, systemctl, arbitrary service restart, or Helper action.

Phase 9 diagnostics use schema version 1 and stable `code`, `category`,
`severity`, `summary`, safe `details`, and `remediation_id` fields. Severity is
one of `OK`, `WARN`, `FAIL`, or `UNKNOWN`. The local diagnostics export creates
a new `0600` file, refuses overwrite/symlink targets, caps output at 1 MiB, and
runs a final secret-pattern guard. It does not expose a new HTTP mutation.

All implemented Pydantic request models reject unknown fields and use strict
types. Security-relevant mutation input is not coerced from strings (for
example, `"1"` is not accepted as integer `1`).

## Settings API

| Method/path | Purpose |
|---|---|
| `GET /api/v1/settings` | non-secret typed settings and effective values |
| `PATCH /api/v1/settings` | update allowlisted non-secret settings |
| `POST /api/v1/settings/validate` | validate proposed settings without applying |

Settings do not include third-party tokens, passwords, cookies, SSH keys, auth files, arbitrary environment, executable paths outside policy, or raw systemd/package configuration. Non-loopback bind settings require explicit warnings and are not part of the default MVP UI.

## Audit API

| Method/path | Purpose |
|---|---|
| `GET /api/v1/audit-events` | paginated metadata-only Audit Events |
| `GET /api/v1/audit-events/{id}` | one sanitized event |

Audit is read-only through API. There is no endpoint to delete or rewrite events in MVP.

## Status Codes

- `200`: read/synchronous bounded action success;
- `201`: resource created when no Job is required;
- `202`: Job accepted;
- `204`: logout/cancellation acknowledgement without body;
- `400`: malformed request;
- `401`: unauthenticated/session expired;
- `403`: forbidden, CSRF/Origin/recent-auth/peer failure;
- `404`: resource not found without leaking unauthorized existence;
- `409`: state/idempotency/session/path conflict;
- `412`: stale revision/confirmation precondition;
- `422`: typed validation failure;
- `423`: resource/global lifecycle lock;
- `429`: login/action rate limit;
- `501`: Runtime capability unsupported;
- `503`: dependency unavailable/broken/degraded;
- `504`: bounded operation timeout.

Phase 3 also uses `413` for an over-limit request body. Validation error details
contain bounded field locations/types and never echo password or other input.

## Output and Execution Limits

Server maximums override caller requests. Recent output, logs, diagnostics, pagination, request bodies, SSE backlog, and command output all have separate byte/item/time limits. Limit violations return a normalized error and discard overflow; truncation is explicit.

## Version Evolution

Breaking resource/semantic changes require `/api/v2`. V1 may add optional fields and new enum values; clients ignore unknown fields and treat unknown capability/error values conservatively. `/api/v1/meta` exposes service/API/Helper/Runtime protocol versions for CLI handshake.

## Explicitly Absent API

There is no `/shell`, `/exec`, `/terminal`, `/command`, arbitrary filesystem,
arbitrary Git, arbitrary systemd, arbitrary package, install/update/rollback,
credential read/write, Pair Code history, raw environment, root impersonation,
Provider, or Secret Manager endpoint. The Provider routes above are future
planning only.
