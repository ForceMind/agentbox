# AgentBox API Design

Status: Phase 1 contract design with the Phase 3 control-plane subset implemented.

Implemented in Phase 3: `GET /healthz`, `GET /readyz`, `GET /api/v1/meta`,
`POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, and
`GET /api/v1/auth/me`. All other contracts in this document remain designs,
not implemented routes.

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
| `GET /api/v1/codex/status` | synthesized installation/auth/remote health | read model with confidence |
| `POST /api/v1/codex/install-jobs` | apply approved install plan | Job |
| `POST /api/v1/codex/update-jobs` | apply approved update plan | Job |
| `POST /api/v1/codex/remote/start-jobs` | start managed Remote daemon | Job |
| `POST /api/v1/codex/remote/stop-jobs` | stop managed Remote daemon | Job |
| `POST /api/v1/codex/pair-codes` | generate/display one-time code | bounded one-time secret response |
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

The placeholder is contract documentation, not a real code. Response/log middleware must mark the body secret and set no-store headers. No Pair Code appears in SSE or a later resource.

## Claude API

| Method/path | Purpose |
|---|---|
| `GET /api/v1/claude/status` | installation/auth/capability summary |
| `GET /api/v1/claude/sessions` | managed sessions plus counts of unmanaged collisions |
| `POST /api/v1/claude/sessions` | create session for `project_id`; returns Job |
| `GET /api/v1/claude/sessions/{session_id}` | managed session state |
| `POST /api/v1/claude/sessions/{session_id}/stop-jobs` | stop exactly one managed session |
| `GET /api/v1/claude/sessions/{session_id}/recent-output` | ephemeral bounded/redacted pane output |
| `GET /api/v1/claude/sessions/{session_id}/attach-command` | fixed local attach instruction |
| `GET /api/v1/projects/{project_id}/workspace-state` | trusted/not-trusted/unknown/manual-required |

Session creation accepts a Project ID and optional display name only. It never accepts a working directory, tmux command/name, shell, Runtime flag, or environment.

## Project API

| Method/path | Purpose |
|---|---|
| `GET /api/v1/projects` | list registered projects |
| `POST /api/v1/projects` | create empty Project Workspace Job |
| `POST /api/v1/projects/clone-jobs` | clone credential-free allowed Git URL |
| `GET /api/v1/projects/{project_id}` | metadata and Runtime/session links |
| `GET /api/v1/projects/{project_id}/git-status` | branch/HEAD/dirty count/sanitized remote |
| `GET /api/v1/projects/{project_id}/path` | display/copy canonical managed path |

There is no MVP delete, arbitrary file-read, arbitrary Git-command, commit, push, reset, hook, or submodule-init endpoint.

Create request concept:

```json
{
  "name": "display-name"
}
```

Clone request concept:

```json
{
  "name": "display-name",
  "remote_url": "https://example.invalid/owner/repository.git"
}
```

The server generates the storage key. URLs with userinfo/credentials or unsupported schemes are rejected.

## Job API

| Method/path | Purpose |
|---|---|
| `GET /api/v1/jobs` | filtered paginated Jobs |
| `GET /api/v1/jobs/{job_id}` | current Job state and sanitized result |
| `POST /api/v1/jobs/{job_id}/cancel` | request cancellation if action allows |
| `GET /api/v1/jobs/events` | authenticated SSE stream for authorized Job summaries |
| `GET /api/v1/jobs/{job_id}/events` | one Job's SSE stream |

SSE event types: `job.queued`, `job.started`, `job.progress`, `job.needs_attention`, `job.succeeded`, `job.failed`, `job.cancelled`, and heartbeat. Events carry sequence, Job ID, status, progress, sanitized summary, and timestamp. They do not carry stdout/stderr, Pair Codes, credentials, or project contents.

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
| `POST /api/v1/doctor/runs` | start Diagnostic Run Job |
| `GET /api/v1/doctor/runs` | list runs |
| `GET /api/v1/doctor/runs/{run_id}` | findings, classifications, safe remediation plans |

Doctor plans but does not automatically repair. A remediation becomes a separately validated action/Job.

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

There is no `/shell`, `/exec`, `/terminal`, `/command`, arbitrary filesystem, arbitrary Git, arbitrary systemd, arbitrary package, credential read/write, Pair Code history, raw environment, or root impersonation endpoint.
