# WS14 Project favorites contract

Status: rc21 backend/API and rc22 Web UI merged, 2026-09-29. This extends the approved
[full capability plan](project/FULL_CAPABILITY_DELIVERY_PLAN.md) after the
[rc20 Project search](WORKBENCH_PROJECT_SEARCH.md). It specifies metadata-only
favorites for formal Projects; it does not grant Project, Runtime, file or
terminal authority. rc21 implements persistence/CAS and typed API; rc22
connects the Web control. Full multi-client/browser proof and later label
features remain unfinished. The rc23 command center is separate navigation.

rc22 local browser evidence covers server-confirmed save, reload read-back,
synthetic conflict, no PUT replay, and desktop/mobile visible state in 106
passing and 28 prescribed skipped isolated Chromium cases. The first full
run exposed old test harness gaps (a fuzzy `Clone` locator and rc9 mocked
authentication without a favorite GET); the corrected full rerun passed.
This is local browser evidence, not real-host or production acceptance.

## Identity and persistence

A favorite belongs to the authenticated AgentBox `AdminUser` and a formal
Project ID. The administrator identity is derived from the current server
session, never supplied by the browser. The data is Control Plane metadata:
one row keyed by `(admin_user_id, project_id)`, a boolean `favorite`, a
monotonic Web-safe `revision` in `1..2^53-1` and a canonical UTC update time. Foreign keys
reference the existing user and Project rows. There is no Project path,
credential, search query, prompt, terminal output or content body in this
table, Audit event, API URL or response. An absent row means
`favorite=false, revision=0`; migration preserves every existing Project and
WAW record. A physical Project deletion can cascade the preference; archive
alone retains it.

The first read API is `GET /api/v1/project-favorites`. It requires the current
administrator session, returns `Cache-Control: no-store`, and exposes only
bounded `{project_id, favorite, revision, updated_at}` records belonging to
that user. It fails explicitly above a fixed 10,000-record bound instead of
returning an incomplete favorite projection. It never invokes Runtime.

The mutation API is a fixed `PUT /api/v1/project-favorites/{project_id}` with
an exact JSON body `{favorite: boolean, expected_revision: integer}`. It
requires the existing session, Origin and CSRF checks. The Project must
exist as a formal row; its state does not affect the preference. The server
holds one database transaction and compares the expected revision. At
revision 0, `favorite=true` inserts revision 1; an absent `false` is a
read-only no-op at revision 0. At an existing revision, changing the value
increments exactly once, while a same-value request at the current revision
returns the existing revision. Any stale expected revision fails with a fixed
`PROJECT_FAVORITE_CONFLICT` response; a second concurrent create or update
cannot silently win. Unknown Project, invalid version/body, inactive session
and database unavailability have separate bounded errors.

The response includes the server-owned current favorite/version and request
ID, never a Project name or source body. New Audit payload fields are limited
to the authenticated user ID, Project ID, operation, accepted revision and
boolean outcome; no query text. An uncertain client acknowledgment is
resolved by a fresh GET,
not an automatic PUT replay. The Web page keeps pending/error state per
Project, disables only that toggle during mutation, and refreshes on page
return, focus and conflict. It must discard late responses from an older
session or Project observation. Search and favorite sorting use the same
freshly loaded Project IDs but neither changes Git/Workspace ownership.

## Delivery and evidence

Implement additively: migration/model and transactional service, exact
request/response schemas and authenticated routes, then the accessible Web
toggle. Tests must cover old database upgrade, foreign keys, absent/default
behavior, repeated same-value requests, two-client revision races, stale
conflicts, unknown/archived Projects, CSRF/Origin/auth failures, server
restart and no Runtime calls. Desktop/mobile browser evidence must show
pending, saved, conflict and failure feedback without pretending an
unacknowledged write succeeded. CI, browser and real-host evidence are
separate.

This is a partial WS14 delivery. Named labels, favorite ordering across
devices, command-center actions and multi-principal Hub policy remain later
contracts. There is no upstream service import; the label/favorite behavior
is reimplemented on AgentBox's existing Control Plane identity and schema.
