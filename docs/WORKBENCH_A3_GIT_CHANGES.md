# A3 bounded Git Changes metadata

Status: rc15 metadata API merged as PR #106; rc16 Changed Paths UI candidate,
2026-09-29.
This is the first read-only data contract under
[ADR 0009](adr/0009-workbench-identity-and-content-boundary.md). It supplies
paths and change classes to the AgentBox Changes tree; it does not yet supply
patch bodies, file previews, comments or staging.

`GET /api/v1/projects/{project_id}/git/changes` requires the existing
authenticated administrator session and a READY formal Project. The only
query input is an optional opaque `cursor`; `path`, cwd, argv, Git flags,
environment and file body selectors are not accepted. The API resolves the
Project's registered relative key and calls one typed Runtime action,
`git.changes.list`, with only `project_key` and `cursor`. Responses use
`Cache-Control: no-store`; no path or file text is written to Audit or the
Control Plane database.

The Runtime revalidates the Project under its fixed root and the repository's
ownership and configuration. It runs a single fixed `git status
--porcelain=v2 -z --untracked-files=all --renames` with no optional locks,
sanitized environment and the existing disallowed executable Git config
checks. The complete stdout is limited to 1 MiB. The parser follows
[Git's porcelain-v2 `-z` record contract](https://git-scm.com/docs/git-status):
ordinary, rename/copy, unmerged and untracked records have distinct shapes;
the rename source consumes its second NUL field. Unknown, incomplete,
duplicate, non-UTF-8, absolute or traversal paths fail the whole observation.
Only relative path metadata, previous path for rename/copy, change class and
staged/unstaged flags are returned; file contents and diff hunks are never
read by this action.

Results sort by full path and page at most 32 entries. A page has a 48 KiB
data budget inside the existing 64 KiB Runtime frame, so long paths can
reduce the actual page size. `total_count` describes all parsed entries;
`next_cursor` carries the canonical snapshot digest and next offset. Each
request re-runs Git status and rejects a cursor after any change in the
sorted metadata with `GIT_CHANGES_STALE`. No cursor means a fresh first
page. The protocol and API response validate exact types, status values,
path bounds and the absence of extra fields. Repositories exceeding the
1 MiB source or 10,000-entry limit report an explicit error rather than a
partial success.

This metadata admission does not grant a file-read capability. The rc16
candidate adds a Project-linked Changed Paths page using the migrated tree
sort and folder compression without inserting artificial line totals. It
fetches pages only for the selected Project, hides previous-scope rows on
Project/session change, invalidates on browser hiding, rejects changed
cursors, and offers explicit refresh and load-more. Path text escapes control
and invisible formatting
characters before display; the page distinguishes loading, empty, non-Git,
stale and failed states. It explicitly says that only path/status metadata
is available. The next A3 content batch must define bounded,
sensitivity-aware patch extraction. Git content extraction
must explicitly disable external diff/textconv effects as required by
[ADR 0009](adr/0009-workbench-identity-and-content-boundary.md); a path in
this response is display data and cannot be passed back as authority.

rc15 local evidence: 164 Git/Project API/release-candidate Python tests passed;
parser, cursor, real Git rename/untracked, fixed argv, strict RPC and
authenticated API cases are included. Web/MV3 version tests and builds passed.
The source-boundary script retains an exact 41-route count and checks that
the added route is this fixed read-only Project endpoint.
The rc15 isolated browser suite ran 98 passing and 28 prescribed skipped
cases. rc16 local evidence: 1149 Web tests passed serially on Node 22.23.2,
six MV3 tests passed, and the browser suite completed 100 passes and 28
prescribed skips across desktop/mobile Chromium, including Changed Paths
navigation, collapse, pagination and no horizontal overflow. Desktop and
mobile screenshots were inspected after spacing corrections. The rc16 Web
main JS bundle is 598.88 kB/171.22 kB gzip versus rc15 587.01/167.85 kB;
the >500 kB warning predates rc16. Linux CI and real-host operation remain
separate evidence; no production service was changed.
