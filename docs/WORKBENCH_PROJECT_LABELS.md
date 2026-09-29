# Project and Workspace labels: shared AgentBox catalog

Status: rc24–rc26 catalog, Project and Workspace assignments reached main;
rc27 visible-client refresh candidate, 2026-09-29. PR #118 was later recognized as
indirectly merged when #119 merged; six post-main workflows succeeded on
the combined main SHA. [CURRENT_STATE](project/CURRENT_STATE.md) records
the live read-back. This extends
the [full capability plan](project/FULL_CAPABILITY_DELIVERY_PLAN.md) after
rc22 favorites and rc23 fixed command-center navigation. The first delivery
persists the shared label catalog and formal Project assignments in the
Control Plane; rc25 adds a Project-page manager for that API. Workspace
assignments use the same label identity in rc26; cross-host synchronization
remains later work. No label grants Project, Runtime, file,
Agent, Job, Provider or Secret authority.

The studied Apache-2.0 source is
`getpaseo/paseo@30178c4f58b67f8472901356e1484022bd835de0`:

| Upstream path | SHA-256 |
| --- | --- |
| `packages/protocol/src/workspace-labels.ts` | `ec8d8fee223a7cfb8da77846b8a4c1537989037863cc7913f1b5050cfd562875` |
| `packages/server/src/server/workspace-labels/internal/service.ts` | `f3e91fb421f40601222e68c51cd01a19e7c146d5391a7319506e79a2404a0255` |

The source defines ten named colors and whitespace-collapsed, case-insensitive
label names. Its host catalog supports assignment, atomic rename/recolor,
delete with assignment cleanup, and a count before destructive delete.
AgentBox will reuse those user-visible behaviors under its existing database
and administrator identity; it will not import the upstream daemon, JSON
catalog file, subscription stream or workspace identity as a second owner.

## Identity and bounds

One label definition belongs to the current AgentBox `AdminUser` and has an
immutable `lbl_` identifier, a display name, normalized comparison key,
one of the upstream ten colors, monotonic Web-safe revision and UTC update
time. The user ID is always derived from the authenticated Web Session.
Names collapse Unicode whitespace to one ASCII space and trim at both ends;
comparison uses Unicode lowercase. Empty names, control/format characters,
non-normalized Unicode, names above 64 characters/128 UTF-8 bytes and
duplicates by comparison key are rejected. The catalog is capped at 128
definitions per administrator. A delete followed by a same-name create gets
a new identifier, so stale assignment or edit requests cannot adopt it.

Project assignments reference the immutable label ID, not the display name.
They belong to `(admin_user_id, formal_project_id)` and preserve assignment
order. Each Project set has a revision that survives removing its last
label; up to 32 definitions may be assigned. Catalog rename/recolor changes
the projected name/color without rewriting assignment identities. Deleting a
definition atomically removes its assignments and increments each affected
Project set revision. Physical Project deletion cascades assignments;
archiving retains navigation metadata. No Project path or content is stored.

## Project API and transaction contract

- `GET /api/v1/project-labels`: authenticated, no-store, bounded current-user
  catalog. It never invokes Runtime. Exceeding the bound fails explicitly.
- `POST /api/v1/project-labels`: exact `{name,color}` body, Origin/CSRF,
  serialized create, duplicate-key conflict, immutable ID and revision 1.
- `PUT /api/v1/project-labels/{label_id}`: exact
  `{name,color,expected_revision}` body, Origin/CSRF, one-transaction
  rename/recolor. Same-value/current-revision is a no-op; stale revision and
  collision reject both fields atomically. Case-only rename is allowed.
- `POST /api/v1/project-labels/{label_id}/delete`: rc26 exact
  `{expected_revision,expected_affected_project_count,expected_affected_workspace_count}`
  body, Origin/CSRF. The response includes both actual counts. A changed
  count, stale revision or unknown ID cannot delete a newly assigned Project
  or Workspace or a new same-name label. Older clients without the Workspace
  count fail request validation; Web/API rollout must be coordinated.
- `GET /api/v1/project-labels/{label_id}/delete-impact`: authenticated,
  no-store count for a confirmation view; it does not mutate assignments.
- `GET /api/v1/project-labels/projects/{project_id}`: current-user ordered
  assigned label definitions plus Project-set revision, including revision
  zero for an existing Project with no set. No Project path is returned.
- `PUT /api/v1/project-labels/projects/{project_id}/{label_id}`: exact
  `{assigned,expected_revision}` body, Origin/CSRF. It compares the Project
  set revision and changes exactly one assignment in a SQLite immediate
  transaction. Same-state/current-revision is a no-op; uncertain client
  acknowledgment is resolved by GET, never automatic PUT replay.

## Formal Workspace assignment

The Workspace key is the current administrator plus a formal Project ID and
`claude` or `codex` AgentType. The existing deterministic `aws_` identity is
derived from the Project/AgentType pair. Labels can be assigned before any
Runtime session is started; no terminal lifecycle, Host, binding or Secret
authority is required or conferred. Physical Project deletion cascades these
metadata rows. The Workspace set preserves its revision after removing the
last assignment; up to 32 ordered labels may be assigned.

- `GET /api/v1/project-labels/workspaces/{project_id}/{agent_type}` reads
  current-user ordered assignments and the independent Workspace revision.
- `PUT /api/v1/project-labels/workspaces/{project_id}/{agent_type}/{label_id}`
  uses exact `{assigned,expected_revision}`, Origin/CSRF and a serialized
  transaction. Same-state/current-revision is a no-op; stale revision is a
  fixed conflict. It never invokes Runtime.
- Catalog deletion previews affected Project and Workspace counts and
  atomically bumps both affected set revisions if the confirmed counts
  still match. The Web confirmation displays both numbers.

The Workspace picker uses the same catalog IDs and color definitions as the
Project manager. It waits for exact ACK and fresh readback, invalidating
observations on session, selection and visibility changes. Catalog creation,
rename, recolor and deletion remain available on the Project page.

## Visible-client freshness

rc27 adds a 30-second bounded catalog+assignment GET to both Project and
Workspace pages while they are visible and no read or write is in flight.
The prior labels stay visible during a background read, but assignment
controls are disabled until both snapshots agree. A failed read becomes an
explicit stale/unavailable state; it never replays a write. Hidden pages do
not poll, and the existing return-to-page refresh revalidates immediately.
This closes same-Control-Plane visible-client convergence, not cross-host
replication, push subscriptions or offline synchronization.

The service validates the administrator and formal Project inside each
transaction, uses additive foreign-keyed migrations, and writes bounded
Audit metadata with actor, label ID, Project ID, revision and operation only.
It records no prompt, source body, path, credential or arbitrary label query
text in Audit. Authentication/CSRF/Origin, validation, not found, stale CAS,
name collision, capacity and database unavailable have distinct fixed errors.

## Delivery evidence and remaining work

The backend tests cover old database upgrade, foreign keys, normalization,
duplicate/case-only rename, simultaneous create/assignment, deletion cleanup
and impact-count drift, archived/unknown Project, per-admin isolation,
restart persistence, Audit rollback and strict API auth/CSRF/Origin/no-store.
The rc25 Project Web candidate adds pending, saved, conflict, uncertain,
empty and session-change states on actual data; its final local desktop/mobile
E2E run completed 112 passes and 28 prescribed skips, including a full
create/assign/reload/edit/delete flow and a fixed 422 error view after the
mobile layout guard. PR #119 merged as `cab33679ec91bc2e46384f24e9a8cd3e4e985fa9`;
six post-main workflows succeeded. rc26 Workspace assignments merged via
PR #120 as `88d2db79dd3cf58cfe0093ee90963f1ecfd45d35`, with six
successful post-main workflows. rc27 visible-client refresh is a candidate.
Cross-host relay synchronization, command-center label actions and a
broader archived-Project browser matrix remain later behavior; rc27 does
not close full WS14 parity. Real-host and production qualification remain
separate.
