# Phase 4 Authenticated Web Foundation Report

## Executive Summary

Phase 4 establishes AgentBox's authenticated browser product frame without
adding Runtime, Project, host-control, or privileged behavior. The Web client
now restores the existing Phase 3 server-side Session, presents a responsive
application shell, renders only truthful control-plane data, handles Session
expiry and CSRF logout coherently, and labels all future capabilities as
planned. A temporary-database Playwright suite executes the real API and
production Web build in desktop and mobile Chromium.

This is a browser and control-plane foundation, not a claim that AgentBox can
manage Codex, Claude, tmux, Git, projects, systemd, packages, or a public
deployment.

## Branch / Commits / PR

- Repository: `ForceMind/agentbox`
- Base: `main` at Phase 3 squash merge `87bcf1ee60c4efb4194e9320e11613f8296f95e8`
- Branch: `phase/4-authenticated-web-foundation`
- Commits: 6 focused commits, including the final report-state update
- Draft PR: [#21](https://github.com/ForceMind/agentbox/pull/21)
- Related existing Issue: #5, `feat: deliver minimal authenticated Web control plane`

## Route Map

Nine named routes plus a branded wildcard are present:

| Route | Protection | Actual Phase 4 behavior |
|---|---|---|
| `/` | auth-resolved | Dashboard/Login redirect |
| `/login` | public-only | real Phase 3 Login API |
| `/dashboard` | authenticated | real health/readiness/meta/auth data |
| `/codex` | authenticated | planned shell only |
| `/claude` | authenticated | planned shell only |
| `/projects` | authenticated | planned shell only |
| `/doctor` | authenticated | real safe Doctor read model |
| `/logs` | authenticated | not-implemented shell only |
| `/settings` | authenticated | safe read-only Doctor policy fields |
| `*` | branded fallback | local 404; no external redirect |

## Authentication UX

`AuthProvider` boots in `checking`, requests `/api/v1/auth/me`, and renders no
protected route or Login flash until the result is known. Login uses the
existing username/password contract, disables duplicate submission, clears the
password state after every attempt, surfaces the generic invalid-credential
message, and displays only a syntactically validated request ID in expandable
details. A `429` uses the bounded `Retry-After` value as approximate guidance.

Successful authentication stores safe administrator/Session metadata and the
Session-bound CSRF token only in React memory. The opaque Session remains an
`HttpOnly` Cookie. Refresh recovers from `auth/me`; direct `/login` access by an
authenticated user returns to Dashboard. A protected-request `401` clears
memory and routes to Login without an auth retry loop.

Logout sends the active CSRF token. On `403`, the provider performs at most one
`auth/me` refresh and one retry. Server revocation and Cookie deletion remain
the Phase 3 authority.

## API Client

The native-fetch client supplies app-relative URLs, Cookie credentials, JSON
headers/bodies, ten-second bounded timeout, CSRF headers, V1 error-envelope
mapping, bounded error text, validated request IDs, Retry-After parsing,
centralized `401` recovery, and runtime validation of all consumed Phase 4
success contracts. It introduces no Axios or frontend state-management
framework.

## Dashboard

Real data:

- process liveness from `/healthz`;
- database/migration readiness from `/readyz`;
- AgentBox version, API version, and environment from `/api/v1/meta`;
- signed-in administrator and absolute Session expiry from `/auth/me`.

Planned only:

- Codex Remote and pairing;
- Claude Remote/tmux sessions;
- Project Workspaces and Git state.

No fabricated status, count, connection, or Runtime observation exists in
production frontend code. Missing responses display `Unavailable`; failed
readiness displays `Not Ready`.

## Responsive UI

The dark-first interface uses neutral surfaces, restrained borders, clear
headings, and text status semantics. Desktop uses a sticky sidebar. Below 900
pixels a sticky compact header opens a full-height navigation drawer. Cards and
policy rows collapse without horizontal scrolling, identifiers wrap, and
primary controls meet the tested 44-pixel mobile target.

The real browser suite passed at 1280×800 and 390×844. CSS breakpoints and
content behavior also cover the requested 360, 768, and 1024+ classes; the
automated regression gate currently uses the representative mobile/desktop
viewports rather than four duplicate projects.

## Security

- **Browser storage:** no Session, CSRF, password, or auth metadata writes to
  localStorage/sessionStorage/IndexedDB; browser inspection passes.
- **CSRF:** normal logout sends the token; wrong token returns `403` without
  revoking the Session; stale-token retry is bounded to one.
- **XSS:** React text rendering only; no raw HTML, dynamic evaluation, remote
  script, analytics, or unvalidated request-ID rendering.
- **Open redirects:** no `next` or caller-selected navigation target exists.
- **Errors:** internal exception objects and malformed error bodies are never
  presented; API success payloads are validated before use.
- **Cache:** Login/Logout/Me and Doctor API responses are `no-store`; the Vite
  shell contains no user state. Phase 8 owns final static/proxy cache headers.
- **CSP:** production output contains external hashed JS/CSS and needs neither
  `unsafe-inline` nor `unsafe-eval`; existing AgentBox API CSP was not weakened.
- **CORS/proxy:** no CORS middleware or wildcard was added. Vite proxies only
  `/api`, `/healthz`, and `/readyz` to an explicitly configured loopback target.

## Backend Changes

Phase 4 adds only `GET /api/v1/doctor`. It requires the existing opaque Cookie
Session, is read-only and `Cache-Control: no-store`, and returns:

- configuration-valid, database-reachable, migration-current,
  admin-initialized, and combined-ready booleans;
- environment, bind host/port, absolute/idle Session lifetimes, and login
  throttling policy.

It does not expose application secret material, secret source, database URL,
data path, auth files, credentials, host networking, system services, GitHub,
tmux, Codex, or Claude. Synchronous SQLite calls remain short bounded
transactions consistent with the accepted Phase 3 MVP boundary; no migration,
cleanup, Runtime probe, or long collection occurs in the request.

## Frontend Tests

Result: **PASS — 15 tests in 2 Vitest files.**

Coverage includes auth boot, protected routes, Login labels/validation,
successful Login and password clearing, generic error and safe request ID,
rate-limit UX, refresh recovery, shell navigation, no fake Runtime data,
CSRF logout, one-time CSRF refresh, centralized `401`, browser storage, fetch
credentials/error parsing, unauthorized callback, and success-contract
validation.

## Backend Tests

Result: **PASS — 60 pytest tests.**

The two new Doctor tests prove unauthenticated `401`, authenticated safe data,
readiness/migration/admin fields, no-store behavior, and absence of secret,
database URL, SQLite URL, and data-directory fields. Existing migration,
authentication, Session, CSRF, rate-limit, audit, configuration, CLI, Worker,
and security tests remain green.

## Playwright

Result: **PASS — 20 browser executions (10 logical scenarios × desktop/mobile).**

Scenarios cover unauthenticated protection, Login semantics, invalid password,
Login/refresh/authenticated Login redirect, CSRF logout and revocation, invalid
CSRF rejection, all Phase 4 navigation, invalid and browser-expired cookies,
zero auth Web Storage, horizontal overflow/mobile control size, and branded
404/semantic landmarks.

The harness uses a temporary SQLite database, explicit Alembic migration,
random test secret/password, independent processes, random loopback ports, and
automatic cleanup. The assessed OpenCloudOS host lacked three Chromium shared
libraries; local verification temporarily extracted official RPM contents into
`/tmp` and removed them after testing. No RPM was installed and no system path
was modified. GitHub Actions independently completed the same 20 browser
executions on Ubuntu in 1m6s with a passing `e2e` result.

## Accessibility

Basic semantic/interaction smoke is **PASS**: labelled form controls, semantic
landmarks/navigation/headings, icon-button labels, visible focus styles,
disabled pending state, reduced-motion handling, textual status, mobile target
size, and keyboard-compatible native controls are present. No axe or formal
screen-reader/WCAG audit was performed; that remains a pre-release hardening
item.

## Dependencies

- `react-router-dom`: versioned client routing and nested route guards;
- `lucide-react`: one consistent lightweight icon set;
- `@playwright/test`: desktop/mobile Chromium E2E.

No Axios, Redux/Zustand, Radix bundle, analytics, telemetry, terminal, editor,
chart, Redis, Celery, or host-control dependency was added. `pip-audit --local
--skip-editable` and `pnpm audit --audit-level high` both report no known
vulnerabilities.

## CI

Existing Backend, Frontend, Security, dependency-audit, and dependency-review
workflows remain intact. New `.github/workflows/e2e.yml` runs Python 3.12,
explicit migration, isolated API/Web processes, Playwright Chromium, and the
same 20 tests without GitHub Secrets. It does not call `playwright
install-deps`.

The first remote E2E run exposed a CI-only harness assumption: Python tools were
looked up only beneath the repository `.venv`, while `setup-python` installs
them on runner `PATH`. The harness now prefers local `.venv/bin/python` and
otherwise uses the configured `python`, invoking Alembic and Uvicorn as Python
modules. The next remote run passed. At handoff all existing required contexts
(`quality`, Python 3.11/3.12/3.13 quality, repository boundaries, both
dependency audits, and dependency review) plus the new `e2e` context are
passing on the final Phase 4 head.

The new `e2e` context has now appeared successfully and is eligible for a
future human-approved addition to the `Protect main` required checks. This
Phase does not modify the Repository Ruleset.

## Deviations

- The Phase 1 development plan mentioned an SSE client foundation. Phase 4 does
  not add speculative SSE behavior because no durable Job event endpoint is
  implemented; it remains aligned with SSE-first architecture and is deferred
  until the Job workstream.
- No shadcn/ui components were required. Small native semantic components keep
  the dependency surface lower while preserving the approved selective-use
  decision.
- The local OpenCloudOS browser needed temporary extracted shared libraries;
  the host was not changed and CI is the repeatable supported browser gate.

No Accepted ADR was changed or contradicted.

## Known Limitations

- Runtime, Project, Git/GitHub, Logs, Settings mutation, Helper, installer, and
  host control remain unimplemented.
- Multi-tab logout is observed on the next API request or refresh, not through a
  cross-tab broadcast channel.
- Doctor uses the accepted short synchronous SQLite MVP boundary.
- There is no formal axe/screen-reader audit or screenshot golden suite.
- Final static-file serving, proxy cache policy, HTTPS headers, and deployment
  smoke belong to Phase 8.

## Phase 5 Recommendation

After human review and merge of Phase 4, Phase 5 should implement only the
capability-aware Codex adapter and its reviewed Remote/Pair security flows from
the accepted plan. It must preserve the Runtime-user boundary, depend only on
public CLI capability detection, and keep Pair Code material out of persistence
and logs. Phase 5 was not started here.
