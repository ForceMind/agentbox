# Project and Workspace labels: shared AgentBox catalog

Status: WS14 design and implementation candidate, 2026-09-29. This extends
the [full capability plan](project/FULL_CAPABILITY_DELIVERY_PLAN.md) after
rc22 favorites and rc23 fixed command-center navigation. The first delivery
persists the shared label catalog and formal Project assignments in the
Control Plane; Workspace assignments and cross-host synchronization use the
same label identity in later slices. No label grants Project, Runtime, file,
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

## First API and transaction contract

- `GET /api/v1/project-labels`: authenticated, no-store, bounded current-user
  catalog. It never invokes Runtime. Exceeding the bound fails explicitly.
- `POST /api/v1/project-labels`: exact `{name,color}` body, Origin/CSRF,
  serialized create, duplicate-key conflict, immutable ID and revision 1.
- `PUT /api/v1/project-labels/{label_id}`: exact
  `{name,color,expected_revision}` body, Origin/CSRF, one-transaction
  rename/recolor. Same-value/current-revision is a no-op; stale revision and
  collision reject both fields atomically. Case-only rename is allowed.
- `POST /api/v1/project-labels/{label_id}/delete`: exact
  `{expected_revision}` body, Origin/CSRF. The response includes the count of
  affected Project assignments. A stale or unknown ID never deletes a new
  same-name label.
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

The service validates the administrator and formal Project inside each
transaction, uses additive foreign-keyed migrations, and writes bounded
Audit metadata with actor, label ID, Project ID, revision and operation only.
It records no prompt, source body, path, credential or arbitrary label query
text in Audit. Authentication/CSRF/Origin, validation, not found, stale CAS,
name collision, capacity and database unavailable have distinct fixed errors.

## Delivery evidence and remaining work

The first slice must cover old database upgrade, foreign keys, normalization,
duplicate/case-only rename, simultaneous create/edit/assignment, deletion
cleanup, archived/unknown Project, per-admin isolation, restart persistence,
Audit rollback and strict API auth/CSRF/Origin/no-store. The Web picker and
manager must later show pending, saved, conflict, failed, empty, archived and
session-change states on actual data, including desktop/mobile rendering.
Workspace label assignment, cross-device/host synchronization and command-
center label actions remain later behavior; completing only this backend is
not full WS14 parity. Real-host and production qualification remain separate.
