# Phase 7 Project Workspace + Git / GitHub Report

## Executive Summary

Phase 7 replaces Phase 6 directory enumeration with formal persistent
Projects, adds a minimal durable single-host Job system, and implements typed
Git/GitHub Runtime operations for create, clone, status, branches,
fast-forward-only Pull, explicit no-force Push, and Draft PR creation. The
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
- Final security hardening: `dd3ea7a fix(security): harden Phase 7 Git workspace boundaries`
- Draft PR: https://github.com/ForceMind/agentbox/pull/27

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
a marker-bound staging identity with safe permissions, and uses descriptor-
relative Linux `renameat2(RENAME_NOREPLACE)` plus directory fsync to activate
the final server-derived destination without an overwrite fallback. The marker
is removed only after the DB state is ready. Reservation, filesystem, DB,
finalization, and audit failures have explicit rollback or `needs_attention`
semantics. Empty-Project rollback refuses any unexpected content. No Project
filesystem Delete is exposed.

## Clone

Clone accepts only bounded GitHub HTTPS or `git@github.com` repository
identities. Userinfo, credentials, query/fragment data, malformed authority,
option injection, local paths, and `file`/`ext`/helper transports are rejected.
Git clones the parent repository only into a per-Job temporary sibling with
hardlinks, prompts, recursive submodules, and LFS smudge disabled. A valid Git
repository is required before atomic no-replace activation. Recursive cleanup
is limited to a clone identity whose final marker and staging operation marker
both match the Job; a collision never removes the existing target. Stale or
mismatched staging fails closed for operator review.

## Git Security Model

Only `GitAdapter` invokes Git through `ControlledProcessRunner`; every operation
has fixed argv, exact cwd, bounded timeout/output, sanitized environment, and no
shell. Git system/global config, prompts, credential/SSH askpass, unapproved
protocols, hooks, pagers, editors, and external diff are disabled. Repository
and worktree config scopes are enumerated with includes disabled and fail closed
on credentials, HTTP settings, aliases/includes, filters, URL/protocol rewrites,
`core.sshCommand`, hooks/askpass/fsmonitor/worktree/gitProxy, remote programs,
push/pull strategy, pager/editor, and external diff. A real Git canary test
proves malicious `config.worktree` cannot execute its `core.fsmonitor` program.
AgentBox never changes ownership or adds Git `safe.directory`.

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

Pull fixes the network target to the uniquely configured, validated GitHub
`origin` upstream branch and uses `git pull --ff-only --no-rebase --no-tags
--no-recurse-submodules --no-verify origin refs/heads/<upstream>`. Command-scope
configuration also pins ff-only/no-rebase and disables autostash. Divergence
returns `GIT_PULL_REQUIRES_RECONCILIATION`; there is no merge or rebase fallback.

## Push

Push requires the same uniquely configured, validated GitHub `origin` upstream
and invokes one explicit `git push --no-verify --porcelain origin
refs/heads/<local>:refs/heads/<upstream>` refspec. Both branch components are
validated and the refspec can never begin with `+`. AgentBox does not guess or
publish a remote, accept a remote selector, mirror/delete branches, or offer
force/force-with-lease.

## GitHub Integration

`GitHubAdapter` uses only the public `gh` CLI with prompts/pagers and nested Git
config/askpass/protocol behavior pinned to non-interactive safe values. It
determines `AUTHENTICATED`, `UNAUTHENTICATED`, or `UNKNOWN` from
`gh auth status`; it never reads `hosts.yml` or a token. GitHub features are
available only for a conservatively parsed `github.com/owner/repo` remote.
Current-branch PR metadata, base/head, public mergeability evidence, and check
status are bounded.

## Draft PR

Draft PR input is bounded to a validated title, 7 KiB plain-text body, and
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

- Backend: Ruff PASS; Black PASS; mypy PASS; `305 passed` after final security,
  worktree-config canary, no-replace, rollback-identity, and audit additions.
- Frontend: ESLint PASS; Prettier PASS; TypeScript PASS; Vitest `25 passed`;
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

## Final Security Review

- Shell/argv: no `shell=True`, `os.system`, route subprocess, general exec, or
  application-layer arbitrary Git argv.
- Protocol/URL: GitHub HTTPS/SSH only; malformed authority and local/file/ext/
  helper/option injection rejected; `GIT_ALLOW_PROTOCOL=https:ssh`.
- Path/symlink: formal ID lookup, canonical immediate child, ownership/mode
  checks, non-symlink root/workspace/temp, descriptor-relative no-replace
  activation, case-normalized collision rejection, and dual-marker cleanup.
- Clone atomicity/rollback: final-path overwrite is impossible; empty and clone
  markers have distinct cleanup semantics; a ready workspace survives uncertain
  finalization; stale/mismatched staging and unknown content require attention.
- Git config execution: include expansion is disabled and all active repository
  scopes, including `config.worktree`, fail closed on executable, credential,
  transport, HTTP, pull/push, pager/editor, filter/driver, and helper settings.
  A real Git fsmonitor canary remains unexecuted. There is no global
  `safe.directory` or chown.
- Credentials: remote userinfo/query/fragment redacted; prompts disabled; raw
  Git/gh output absent from API, DB, Audit and logs.
- Branch/remote: strict ref validation; explicit validated origin targets and a
  non-`+` Push refspec; no arbitrary remote, force, reset, clean, delete, merge,
  or rebase fallback.
- Claude: the Runtime UDS enforces Pull/switch blocking while the managed tmux
  session is active, so API, CLI, and direct Runtime dispatch share the guard.
- Jobs: scoped Idempotency-Key digests deduplicate mutations; expired running
  leases become `needs_attention` and are never replayed after an uncertain
  worker crash.
- GitHub/PR: fixed `gh` operations, prompts/editors/pagers disabled, published
  current branch required, bounded title/body/base, body via stdin, no shell or
  caller-controlled flags/repository selector.
- Phase 6 compatibility: formal opaque IDs resolve to the unchanged immutable
  relative Runtime key, preserving deterministic tmux identity and discovery.
- Output/logging: stable normalized codes, bounded sanitized summaries, no
  source/filename/raw-tool persistence; URL userinfo and sensitive assignments
  are redacted before length truncation, including token-only userinfo.

The final code and security review found and corrected unsafe Push config
influence, worktree-scope Git-config inspection gaps, activation overwrite
races, rollback identity ordering, ready/finalize rollback ambiguity, and
credential/control-character sanitation. Local review gates pass with no
remaining Phase 7 blocker. Merge readiness still requires the required checks
on the pushed final-review head; their live result is reported in the handoff.

## Post-Review Remediation

The Ready-for-Review pass on implementation head
`dd3ea7ae8237cc1a4125432cfc128a14ec76cb77` produced four actionable P2 review
threads. Implementation head `af3f71c85276dfab20927a1516f25971b9c02340`
addresses all four:

- Web Project mutations retain the same Idempotency-Key after an uncertain
  timeout/transport/response-validation failure and release it only after a
  successful or definitive HTTP response. The fingerprint includes Project,
  typed operation, and body. Create/clone use the same retry rule.
- A failed initial Project detail request now renders the bounded API error
  instead of remaining indefinitely in the loading state.
- Project and GitHub CLI read operations map Runtime categories through the
  documented exit-code contract instead of collapsing them to validation exit
  15.
- Draft PR bodies are capped at 7 KiB, reserving sufficient space beneath the
  existing global 16 KiB mutation-body limit even for maximally JSON-escaped
  accepted input. An integration test proves the accepted maximum reaches the
  route and queues exactly one typed Job.

Regression coverage proves uncertain retries reuse their key, definitive HTTP
failures receive a new key, all four CLI Runtime category paths preserve exit
codes, Project load failures are visible, and the maximum accepted Draft PR body
does not fail at HTTP middleware. Full local results are Backend `305 passed`,
Frontend `25 passed`, migration upgrade/downgrade/upgrade PASS, both dependency
audits PASS, secret/boundary/forbidden-primitive scans PASS, and diff check PASS.
Local Playwright again reached migration/build/API/Web startup but executed zero
application assertions because Chromium lacks host `libgbm.so.1`; no system
package was installed.

## Dependencies

No Python or JavaScript runtime dependency was added. `pip-audit --local
--skip-editable` and `pnpm audit --audit-level high` report no known
vulnerabilities.

## CI

Local lint/type/unit/build/migration/audit/security gates pass. All nine GitHub
checks passed on the original final-review implementation head
`dd3ea7ae8237cc1a4125432cfc128a14ec76cb77`: Backend on Python 3.11/3.12/3.13,
Frontend, repository boundaries, dependency review, Python audit, Frontend
audit, and the 54-case E2E suite. PR #27 was then marked Ready for Review. The
post-review remediation requires all applicable workflows to rerun on the
pushed report head; their authoritative live result is reported in the final
handoff.

## Final Conclusion

Project path, clone atomicity, Git config/transport/command, ff-only Pull,
no-force Push, branch/PR injection, credential redaction, active-Claude, Job
non-replay/idempotency, GitHub CLI, Web retry/error behavior, CLI exit mapping,
request-size compatibility, and Phase 6 session-compatibility review gates
pass. There is no remaining local Phase 7 code blocker. Final merge
recommendation depends only on required checks passing on the pushed
post-review head and is reported in the handoff. PR #27 remains unmerged for
human review. Phase 8 and Phase 11 implementation remain `NOT STARTED`.

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
