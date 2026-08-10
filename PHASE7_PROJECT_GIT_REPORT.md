# Phase 7 Project Workspace + Git / GitHub Report

## Executive Summary

Phase 7 replaces Phase 6 directory enumeration with formal persistent
Projects, adds a minimal durable single-host Job system, and implements typed
Git/GitHub Runtime operations for create, clone, status, branches,
fast-forward-only Pull, ordinary no-force Push, and Draft PR creation. The
implementation exposes no arbitrary shell, Git argv/config/path, filesystem
Project deletion, dangerous Git mutation, Provider/Secret Manager, privileged
Helper, installer, systemd deployment, or production host mutation.

## Branch / Commits / PR

- Branch: `phase/7-project-git-management`
- Base synchronized from: `78a13b16937d17be2b388a649321f9b172e9e57e`
- Foundation commit: `4430578 feat(projects): add project and git management foundation`
- Main synchronization: `07c971a Merge remote-tracking branch 'origin/main' into phase/7-project-git-management`
- Runtime hardening: `163c373 fix(git): harden project runtime execution boundaries`
- Control Plane/CLI: `90986ea feat(projects): complete control-plane and CLI integration`
- Web UX: `b38a26e feat(web): complete project workspace management UX`
- Security coverage: `e946d10 test(projects): expand Git and workspace security coverage`
- Documentation: this report's semantic documentation commit
- Draft PR: recorded after publication

## Project Model

Migration `0002_project_jobs` adds `projects`, `jobs`, and `job_events`.
`Project` stores an opaque `prj_*` ID, normalized bounded slug, display name,
immutable relative path, source/state, credential-free repository URL, optional
default branch, archive timestamp, and UTC timestamps. The display name and
slug are labels; the opaque ID is the public identity and the immutable
relative key is the Runtime binding.

## Workspace Root

Development continues to use `.agentbox-dev/projects`; production architecture
remains `/srv/agentbox/projects`. Phase 7 did not create `/srv`, change host
ownership, create system users, or modify production configuration.

## Project Path Security

Web/API/CLI accept a Project ID or normalized slug, never a workspace path.
Application Services resolve the formal record and send only its immutable
relative key over UDS. Runtime joins exactly one child to the configured root
and rejects traversal, absolute/nested/hidden identifiers, root/project
symlinks, canonical escape, missing/non-directory paths, foreign ownership,
group/world-writable root/workspace/temp directories, and unsafe Git ownership.
The database never authorizes an absolute path.

## Phase 6 Migration

Safe immediate children previously enumerated by Phase 6 are reconciled into
formal Project records without moving or renaming them. Claude API and CLI
resolve formal ID/slug through `ProjectService`, then pass the unchanged
historical `relative_path` to Runtime. Existing deterministic tmux names and
markers therefore remain stable; managed sessions are not orphaned or adopted
by similarity.

## Project Create

Create validates and reserves a `creating` Project, queues a typed Job, creates
a marker-bound staging identity with safe permissions, atomically renames it to
the final server-derived destination, and removes the marker only after the DB
state is ready. Reservation, filesystem, DB, finalization, and audit failures
have explicit rollback or `needs_attention` semantics. No Project filesystem
Delete is exposed.

## Clone

Clone accepts only bounded GitHub HTTPS or `git@github.com` repository
identities. Userinfo, credentials, query/fragment data, malformed authority,
option injection, local paths, and `file`/`ext`/helper transports are rejected.
Git clones the parent repository only into a per-Job temporary sibling with
hardlinks, prompts, recursive submodules, and LFS smudge disabled. A valid Git
repository is required before atomic final rename. Cleanup is limited to the
exact marker-bearing operation/final identity; a collision never removes the
existing target.

## Git Security Model

Only `GitAdapter` invokes Git through `ControlledProcessRunner`; every operation
has fixed argv, exact cwd, bounded timeout/output, sanitized environment, and no
shell. Git system/global config, prompts, credential/SSH askpass, unapproved
protocols, hooks, pagers, editors, and external diff are disabled. Local config
is enumerated with includes disabled and fails closed on credentials, HTTP
headers, aliases/includes, filters, URL/protocol rewrites, `core.sshCommand`,
hooks/askpass/fsmonitor/worktree/gitProxy, remote programs, pager/editor, and
external diff. AgentBox never changes ownership or adds Git `safe.directory`.

## Git Status

`git status --porcelain=v2 --branch -z` is parsed into repository, normal/
detached/unborn branch, upstream, ahead/behind, staged/unstaged/untracked/
conflicted counts, clean state, bounded redacted origin, and submodule-presence
fields. Raw porcelain, filenames, stdout, and stderr are not Web contracts.

## Branch Management

Branch list is capped at 500 local branches. Create/switch use strict lexical
validation plus fixed `git check-ref-format --branch`; option-like, control,
reflog and reserved forms fail closed. Switch uses `git switch -- <branch>` and
never stashes, resets, cleans, or discards. A blocked dirty switch returns a
normalized conflict.

## Pull

Pull is strictly `git pull --ff-only --no-rebase`. It requires a non-detached
branch with an existing upstream. Divergence returns
`GIT_PULL_REQUIRES_RECONCILIATION`; there is no merge or rebase fallback.

## Push

Push is ordinary `git push` against the existing configured upstream. AgentBox
does not guess/publish a remote, accept a remote selector, delete branches, or
offer force/force-with-lease.

## GitHub Integration

`GitHubAdapter` uses only the public `gh` CLI with prompts/pagers and nested Git
config/askpass/protocol behavior pinned to non-interactive safe values. It
determines `AUTHENTICATED`, `UNAUTHENTICATED`, or `UNKNOWN` from
`gh auth status`; it never reads `hosts.yml` or a token. GitHub features are
available only for a conservatively parsed `github.com/owner/repo` remote.
Current-branch PR metadata, base/head, public mergeability evidence, and check
status are bounded.

## Draft PR

Draft PR input is bounded to a validated title, 16 KiB plain-text body, and
optional valid base branch. Runtime uses fixed `gh pr create --draft` argv,
sends the body on stdin, disables prompts/editors/pagers, and keeps the current
branch as head. No arbitrary flags, repo selector, template path, Web launch,
workflow action, or raw `gh` output is exposed.

## Job Model

SQLite Jobs provide queued/running/succeeded/failed/needs-attention states,
idempotency digests, per-Project resource serialization, bounded typed payloads
and summaries, leases, heartbeats, and authenticated bounded JobEvent/SSE
replay. Worker heartbeats renew long bounded Runtime RPC leases without noisy
progress rows. Expired running work becomes `needs_attention` and is never
blindly replayed. Success and failure audits occur before terminal Job
transition; uncertain rollback or audit persistence remains operator-visible.
Raw command output, credentials, repository content, and pane output are not
persisted.

## API

Implemented routes cover Project list/create/clone/detail, structured Git
status, branch list/create/switch, Pull, Push, global GitHub status, Project
Draft PR creation, Job list/detail, and per-Job SSE. All are authenticated and
`no-store`; mutations require exact Host/Origin, session-bound CSRF, and an
Idempotency-Key and return `202`. Bodies cannot carry paths, argv, environment,
Git config, remote selectors, or dangerous-operation flags.

## CLI

The CLI implements `project list|create|clone|status|pull|push`,
`project branch list|create|switch`, and
`github status|pr status|pr create`. Safe read-only commands support `--json`;
mutations enqueue the same typed Jobs. References resolve only formal IDs or
slugs. There is no `git run`, Project delete, force/reset/clean/discard, or
secret input.

## Web

`/projects` provides real Project summaries plus New Project and Clone forms
without a path field. `/projects/:projectId` has bounded loading, structured Git
counts/branch/upstream/remote/submodule state, capped branches, safe mutation
actions, durable Job polling and terminal errors, current PR/check state, Draft
PR title/body/base fields, and Project-bound Claude start/stop. Buttons are
disabled while a mutation is active. Production UI contains no fake Project
data, raw HTML/output, dangerous Git, delete, diff, file browser, or token
storage.

## Claude Integration

Claude list/status/start/stop now use formal Project identity externally while
retaining the Phase 6 relative Runtime key internally. Runtime rejects Pull and
branch switch with `PROJECT_RUNTIME_ACTIVE` whenever the managed tmux session
is running (including needs-interaction work). AgentBox never changes the
workspace under an active managed Claude session or auto-accepts Workspace
Trust. Codex remains not Project-aware and is documented as a limitation.

## Doctor

Doctor reports configured Project Root, formal Project count, Git installation/
version, GitHub CLI installation/authentication, and bounded ownership/root
findings. Codex, Claude, Git, and GitHub probes run concurrently and degrade
independently. Doctor never scans arbitrary paths or exposes tokens,
credential-bearing remotes, or raw CLI output.

## Tests

- Backend: Ruff PASS; Black PASS; mypy PASS; `248 passed` after final security
  and rollback-audit additions.
- Frontend: ESLint PASS; Prettier PASS; TypeScript PASS; Vitest `22 passed`;
  production build PASS.
- Migration: isolated `upgrade → downgrade base → upgrade` PASS; final head is
  `0002_project_jobs`.
- Coverage includes Project normalization/idempotency/DB-filesystem rollback,
  traversal/symlink/mode/ownership, atomic clone/collision cleanup, malformed
  and malicious URLs, protocol/config/branch/PR injection, porcelain variants,
  exact Pull/Push/branch argv, no-force proof, active-Claude guards, credential
  redaction, fake `gh` auth/PR/check/error/timeout behavior, UDS fail-closed
  decoding, Job serialization/recovery/heartbeat/audit, API/CLI, and Web tests.

## E2E

Playwright defines 27 scenarios at desktop and mobile sizes (54 cases),
including Projects empty/create/clone success/failure, clean/dirty Git, branches,
active-Claude blocking, Pull reconciliation, Push upstream missing, GitHub auth,
Draft PR/checks, dangerous-action absence, layout, and auth expiry. The local
harness completed migration/build/API/Web startup, but Chromium could not start
because this host lacks `libgbm.so.1`; therefore zero application assertions ran
locally. No system package was installed. GitHub CI is the authoritative E2E
environment.

## Real Host Validation

Only `/root/AgentBox/.agentbox-dev/projects/phase7-host-validation` was used,
with an exact product marker. Actual Git 2.43.7 passed Project create, Git init,
clean structured status, branch create/list/switch, and marker-verified product
rollback. Pull and Push safely returned `GIT_UPSTREAM_MISSING`; network mutation
was skipped. The validation workspace is absent after cleanup. Read-only probes
observed GitHub CLI 2.97.0 and an authenticated public `gh auth status` signal;
no token was read. Real Draft PR mutation was skipped. No user Project,
Claude/tmux session, or host configuration was touched.

## Security Review

- Shell/argv: no `shell=True`, `os.system`, route subprocess, general exec, or
  application-layer arbitrary Git argv.
- Protocol/URL: GitHub HTTPS/SSH only; malformed authority and local/file/ext/
  helper/option injection rejected; `GIT_ALLOW_PROTOCOL=https:ssh`.
- Path/symlink: formal ID lookup, canonical immediate child, ownership/mode
  checks, non-symlink root/workspace/temp, marker-bound destructive cleanup.
- Git config: include expansion disabled; executable/credential/transport
  settings rejected; no global `safe.directory` or chown.
- Credentials: remote userinfo/query/fragment redacted; prompts disabled; raw
  Git/gh output absent from API, DB, Audit and logs.
- Branch/remote: strict ref validation; no arbitrary remote, force, reset,
  clean, delete, merge, or rebase fallback.
- Claude: Pull/switch blocked while managed session is active.
- Partial clone: per-Job temp, exact marker identity, atomic rename, bounded
  cleanup; unknown directories remain untouched.
- Output/logging: stable normalized codes, bounded sanitized summaries, no
  source/filename/raw-tool persistence.

## Dependencies

No Python or JavaScript runtime dependency was added. `pip-audit --local
--skip-editable` and `pnpm audit --audit-level high` report no known
vulnerabilities.

## CI

Local lint/type/unit/build/migration/audit/security gates pass. GitHub required
checks and CI E2E will be recorded after Draft PR publication.

## Deviations

- GitHub-only HTTPS/SSH clone is intentionally narrower than a general approved
  host registry.
- Job progress uses coarse phases and Web polling; per-Job SSE exists, but the
  current Project page does not require an SSE client.
- Archive state exists in the model, but no archive/delete endpoint is exposed.
- Local Playwright is environment-blocked rather than hidden or converted to a
  false pass.

## Known Limitations

Issue browsing, staging/commit, diff/file browser, submodule/LFS management,
Project filesystem deletion/archive UX, branch publishing, workflow actions,
real GitHub PR mutation validation, and Project-aware Codex sessions remain out
of scope. Authentication remains owned by official Git/gh tooling under the
Runtime identity. Phase 11 Provider, Secret & Runtime Continuity Management is
planning-only and remains `NOT STARTED`.

## Phase 8 Recommendation

After human review and merge, Phase 8 may address installer/runtime identity,
production Project Root ownership, systemd units, and migration/adoption. Phase
8 was not started by this work.
