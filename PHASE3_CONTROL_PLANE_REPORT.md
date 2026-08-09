# AgentBox Phase 3 Control-Plane Foundation Report

> Date: 2026-08-09
> Phase: Control Plane Foundation
> Status: Local implementation and verification complete; Draft PR/remote CI pending
> Product scope: authentication and control-plane foundations only

## Executive Summary

Phase 3 establishes a minimal single-administrator control plane without
implementing any Runtime, Project, privileged, installer, or deployment action.
It has typed configuration, explicit SQLite/Alembic persistence, local admin
bootstrap, Argon2id authentication, opaque server-side Sessions, CSRF, login
throttling, bounded audit/log/error foundations, readiness, Session cleanup,
and a minimal login UI.

This is a **control-plane security foundation**, not a claim of production
readiness, complete hardening, or penetration testing. It does not start a
persistent service or change the host.

## Branch / Commits / PR

| Item | Value |
|---|---|
| Repository | `ForceMind/agentbox` |
| Base | `main` at `de758b2375b3e167ede6e75f8764e88aebf0156d` |
| Branch | `phase/3-control-plane-foundation` |
| Commits | Pending final Phase 3 commit sequence |
| Draft PR | Pending push and creation |
| Related Issues | #2, #3, #4; partial Phase 3 scope of #5 and #6 |

## Configuration

Configuration uses Pydantic Settings. Explicit `AGENTBOX_*` environment
variables override explicit construction/test values, which override the
optional local `.agentbox-dev/config.toml`, followed by defaults. `.env` loading
is deliberately not a configured source.

| Field | Development default / behavior |
|---|---|
| `AGENTBOX_ENV` | `development` |
| `AGENTBOX_BIND_HOST` | `127.0.0.1` |
| `AGENTBOX_BIND_PORT` | `8787` |
| `AGENTBOX_DATABASE_URL` | SQLite beneath `.agentbox-dev/` |
| `AGENTBOX_SECRET_KEY` | ephemeral per-process development key when absent; never displayed |
| `AGENTBOX_SESSION_TTL` | 28,800 seconds absolute lifetime |
| `AGENTBOX_SESSION_IDLE_TTL` | 1,800 seconds |
| `AGENTBOX_LOGIN_RATE_LIMIT` | 5 failed attempts |
| `AGENTBOX_LOGIN_RATE_WINDOW` | 300 seconds |
| `AGENTBOX_LOGIN_LOCK_DURATION` | 300 seconds |
| `AGENTBOX_DATA_DIR` | `.agentbox-dev` |
| body limit | 16 KiB for state-changing HTTP requests |

Production validation rejects a missing/short application secret, any
non-loopback bind, non-HTTPS authentication origin, non-SQLite or relative/out-
of-data-directory database, temporary data directory, symlinked production DB
path, or group/world-accessible state directory. The installer must create the
production directory; Phase 3 does not do so. Safe summaries omit the secret,
database URL, and data path.

## Database

- SQLAlchemy 2.x declarative mappings and explicit transaction context;
- SQLite WAL, `foreign_keys=ON`, 5,000 ms busy timeout, and `0600` database/WAL/
  SHM files;
- explicit Alembic migration `0001_control_plane_foundation`;
- verified empty → head, head → previous/base using `downgrade -1`, and upgrade
  to head again;
- application/Worker startup never calls `Base.metadata.create_all()` and never
  applies migrations implicitly.

The physical Phase 3 schema contains only:

- `admin_users`: username/normalized username, Argon2id hash, active flag, and
  lifecycle timestamps; a partial unique index permits one active admin;
- `sessions`: admin foreign key, keyed Session-token hash, keyed CSRF verifier,
  idle/absolute expiry, revocation, and bounded client label;
- `audit_events`: bounded actor/action/target/result/request correlation and
  allowlisted metadata JSON.

No Token, Setting, Job, Project, Runtime, Confirmation, or third-party
credential table exists.

## Administrator Initialization

`agentbox admin init [--username <name>]`:

1. requires a local TTY;
2. requires an explicit prior `alembic upgrade head`;
3. reads and confirms the password with echo disabled;
4. enforces a 12–1,024 character passphrase policy without composition rules;
5. serializes bootstrap with SQLite `BEGIN IMMEDIATE` and a database uniqueness
   constraint;
6. stores Argon2id only and records a metadata-only `admin_initialized` event;
7. rejects a second active administrator.

There is no Web registration route and no password argv option.

## Authentication

- `POST /api/v1/auth/login` uses a strict request schema, exact Origin/Host,
  generic invalid-credential responses, a process-precomputed dummy Argon2
  verifier for missing users, and future rehash support;
- inactive/missing/wrong-password responses share the same public code/message;
- success creates a new Session and never reuses a supplied cookie identity;
- `POST /api/v1/auth/logout` revokes server state, validates CSRF, clears the
  Cookie, and audits logout;
- `GET /api/v1/auth/me` returns bounded admin/Session metadata and the current
  session-bound CSRF token, never the raw Session token.

Default Argon2id settings are 64 MiB memory, three iterations, parallelism two,
32-byte hash, and a unique 16-byte salt supplied by the maintained library.

## Session Security

- raw Session token: URL-safe CSPRNG output with 256 bits of entropy;
- persistence: HMAC-SHA-256 keyed digest only;
- CSRF: deterministic HMAC-derived per-Session token with a separately keyed
  persisted verifier; raw CSRF is not persisted;
- cookie: `agentbox_session`, `HttpOnly`, `SameSite=Strict`, `Path=/`, bounded
  Max-Age; `Secure` is mandatory in production;
- expiry: 30-minute sliding idle window within an immutable eight-hour absolute
  lifetime;
- revocation: logout plus oldest-session revocation above ten active Sessions;
- cleanup: expired/idle-expired/revoked rows are deleted only after retention.

Raw Session and CSRF canaries were checked against the SQLite/WAL/SHM files and
Audit metadata in tests.

## CSRF

All Phase 3 mutations require an exact allowlisted Origin and Host. Logout also
requires `X-CSRF-Token`, which is compared in constant time against the current
Session verifier. Missing, malformed, incorrect, and different-Session values
fail closed. Tokens are never accepted in URLs or logged.

## Login Rate Limiting

The Phase 3 limiter maintains HMAC-pseudonymous account, source, and combined
buckets in the API process. Five failures in a rolling five-minute window cause
a bounded five-minute lock. A success clears the account/combined bucket but
retains the source spray-defense history. The clock and storage interface are
deterministic in tests.

API restart currently clears limiter state. This is an explicit limitation and
the main deviation from the longer-term restart-persistent design; it is not
hidden with a success claim.

Forwarded client addresses are ignored unless the immediate peer is inside an
explicit `AGENTBOX_TRUSTED_PROXIES` network. Audit stores only a keyed source
fingerprint, not a raw public address or raw forwarded header.

## Audit and Logging

Implemented events:

- `admin_initialized`
- `login_succeeded`
- `login_failed`
- `logout`
- `session_revoked`

Audit metadata is a flat, maximum-16-field scalar allowlist. Sensitive key
names, long/nested values, and newline injection are rejected. Structured JSON
logging includes timestamp, level, logger, event/message, and request ID. It
uses allowlisted fields plus assignment redaction and never logs request bodies.

Passwords, raw Sessions, CSRF, application secrets, Cookies, Authorization
headers, and full headers are not audit/log inputs.

## API

Implemented endpoints:

- `GET /healthz` — process liveness only;
- `GET /readyz` — database reachability and Alembic head state;
- `GET /api/v1/meta` — name, version, API version, environment only;
- `POST /api/v1/auth/login`;
- `POST /api/v1/auth/logout`;
- `GET /api/v1/auth/me`.

Errors use a V1 envelope with stable code/category/message/request ID and never
return exception text or validation input. `X-Request-ID` is accepted only with
a bounded 64-character syntax; otherwise the server generates one. Responses
include CSP, frame denial, `nosniff`, and no-referrer headers. HSTS is not set on
the default local development HTTP flow. No CORS middleware is enabled.

## CLI

- `agentbox --version`
- `agentbox status [--json]`
- `agentbox doctor [--json]`
- `agentbox admin init [--username]`
- `agentbox admin status [--json]`
- `agentbox secret generate`

Status/Doctor inspect only configuration, database, migration, and admin state.
Secret generation prints CSPRNG output once and writes no file/database/log;
JSON secret output is deliberately unsupported.

## Worker

The Worker supports version/check/one-pass cleanup and a signal-aware cleanup
loop. It may connect to SQLite and call Session cleanup only. It does not read or
execute Jobs, spawn a process, connect to Helper/Runtime, or perform system work.

## Frontend

The React client has only a login view and a minimal authenticated shell showing
the current username, “Control Plane Ready”, and logout. Fetch uses
`credentials: "include"`; logout sends the in-memory CSRF token. Session values
are never placed in local/session storage, and password state is cleared after
the request. Vite continues to proxy to loopback for development.

## Tests

Actual local results before publication:

| Check | Result |
|---|---|
| Ruff | PASS |
| Black (one file/process bwrap workaround) | PASS |
| mypy strict | PASS — 34 checked source files |
| pytest | PASS — 50 tests |
| migration upgrade/downgrade/upgrade | PASS |
| ESLint | PASS |
| Prettier | PASS |
| TypeScript strict | PASS |
| Vitest | PASS — 4 tests |
| Vite build | PASS |
| repository secret-pattern check | PASS |
| Phase 3 source/mutation boundary check | PASS |
| `git diff --check` | PASS |
| pip-audit | PASS — no known vulnerabilities; editable project skipped |
| pnpm production/high audit | PASS — no known vulnerabilities |

The Black directory-batch behavior remains unreliable in the current bwrap
environment, so the Phase 2 one-file-per-process workaround was used locally.
GitHub Actions continues to run the normal batch command.

## Security Review

| Area | Result |
|---|---|
| Secrets | no tracked `.env`, database, generated secret, key, auth state, or raw Session/CSRF persistence found |
| Shell execution | no `shell=True`, `os.system`, `eval`, `exec`, or subprocess primitive in application packages |
| SQL injection surface | ORM bound comparisons only; hostile login strings tested; no raw user SQL |
| CSRF | exact Origin/Host plus Session-bound token on logout; negative/cross-Session tests pass |
| Session | new random token per login, keyed hash storage, idle/absolute expiry, revocation, cleanup, active cap |
| Cookie | HttpOnly/Strict/Path/Max-Age tested; production policy forces Secure/HTTPS origin |
| Rate limit | deterministic account/source/combined throttling; restart reset documented |
| Logging/audit | no request bodies; bounded fields, key rejection, newline and assignment redaction |
| CORS/proxy | no wildcard CORS; forwarded source ignored absent explicit trusted peer network |
| Error handling | stable envelope; no client traceback or echoed validation values |
| Registration | no anonymous or Web admin registration endpoint |
| Production secret | no fixed production secret; production refuses missing/short secret |

These repository checks are safeguards, not a penetration test.

## Dependencies

Direct Phase 3 additions:

- `pydantic-settings`: typed environment/TOML settings and production validation;
- `argon2-cffi`: maintained Argon2id password hashing.

No Redis, Celery, PostgreSQL, OAuth provider/framework, telemetry, subprocess,
container, cloud, or Runtime dependency was added.

## Deviations

1. The Phase 1 security target described restart-persistent login counters. The
   Phase 3-approved scope allowed a process-local MVP limiter; restart reset is
   documented and must be revisited before a hardened release.
2. The earlier development-plan shorthand mentioned Job records in Phase 3.
   The explicitly approved Phase 3 scope excludes Job execution/business models,
   so no Job table or consumer was created. ADR 0005 remains accepted for the
   later Job phase.
3. API route functions are asynchronous but call short synchronous SQLAlchemy/
   Argon2 service boundaries. This avoids an observed AnyIO threadpool stall in
   the current bwrap environment; under bursts of allowed password checks it can
   temporarily reduce API responsiveness and should be profiled/revisited.
4. `SameSite=Strict` follows the approved Phase 1 security design and is stronger
   than the Phase 3 minimum of Lax.

No Accepted ADR was changed or contradicted.

## Known Limitations

- no persisted login-rate state across API restart;
- no password change/reset or recent re-authentication flow;
- no Session listing/revoke-all UI;
- no Job table, Job Worker, or SSE;
- no API UDS/service-mode CLI handshake;
- no Playwright browser end-to-end suite yet;
- no installed production permissions, system user, systemd unit, HTTPS proxy,
  public exposure, or deployment verification;
- no Codex, Claude, tmux, Project, Git/GitHub, Helper, or installer behavior.

## Phase 4 Recommendation

After human review and merge of the Phase 3 Draft PR, Phase 4 may build the
authenticated frontend page shells and browser end-to-end coverage against
these V1 contracts. It must not expand the backend into Runtime, Project,
Helper, installer, or public-exposure work without the corresponding later
phase approval.
