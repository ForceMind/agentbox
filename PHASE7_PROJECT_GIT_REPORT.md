# Phase 7 Project Workspace + Git / GitHub Report

## Executive Summary

Phase 7 replaces Phase 6 directory enumeration with formal persistent Projects, adds durable single-host Jobs, and implements typed Git/GitHub Runtime operations for create, clone, status, branches, fast-forward-only pull, no-force push, and Draft PR creation. No arbitrary shell, Git argv, raw path, credential store, dangerous Git mutation, Project filesystem delete, Provider/Secret Manager, Helper, Installer, or deployment capability was added.

## Branch / Commits / PR

- Branch: `phase/7-project-git-management`
- Base: `5d8297c29dfd89da80056b1abffad07e07c5f8fb`
- Draft PR: populated after publication

## Project Model and Workspace Root

`projects` stores opaque ID, normalized slug, display name, immutable relative path, source/state metadata, timestamps, repository URL, default branch, and archive timestamp. Development root is `.agentbox-dev/projects`; production design remains `/srv/agentbox/projects`. No production directory or host ownership was changed.

## Project Path Security and Phase 6 Migration

API accepts Project IDs, never paths. Runtime resolves one controlled child beneath a canonical, non-symlink root and rejects traversal, absolute/nested identifiers, symlinks, inaccessible paths, root aliases, and ownership ambiguity. Existing Phase 6 children are reconciled without moving them; Claude public APIs translate formal ID to the unchanged relative Runtime key, preserving deterministic managed tmux identity.

## Project Create and Clone

Create/Clone reserve a `creating` Project and enqueue a durable typed Job. Marker-bound staging under `.agentbox-tmp` plus atomic rename prevents partial final workspaces. Rollback deletes only the exact operation identity. Clone accepts approved GitHub HTTPS/SSH identities, blocks local/ext/file protocols, disables prompts, submodule recursion and LFS smudge, and never accepts destination or Git flags.

## Git Security Model and Status

`GitAdapter` alone invokes fixed Git argv through `ControlledProcessRunner`, without a shell. Environment and config overrides disable prompts, hooks, pagers, editors, external diff, system config, LFS smudge, and unapproved protocols. Repository-local executable configuration fails closed. Porcelain v2 is parsed into bounded structured status; remote userinfo/query/fragment is redacted.

## Branch Management, Pull, and Push

Branches are lexically validated and checked with `git check-ref-format --branch`. Switch never discards/stashes changes. Runtime rejects switch and Pull when a managed Claude session is active. Pull is strictly fast-forward only with no merge/rebase fallback. Push requires an upstream and has no force path.

## GitHub Integration and Draft PR

`GitHubAdapter` uses public `gh auth status` and never parses/stores tokens. Current-branch PR/check summaries are bounded. Draft PR title/body/base are validated; fixed `gh pr create --draft` receives body on stdin with prompts/pagers disabled.

## Job Model

SQLite-backed Jobs and JobEvents provide queued/running/succeeded/failed/needs-attention states, idempotency digests, per-Project serialization, bounded summaries, leases, and authenticated bounded SSE replay. Interrupted running mutations become `needs_attention` and are not blindly replayed. Raw command output and credentials are not persisted.

## API, CLI, Web, Claude Integration, and Doctor

Authenticated no-store Project, Git, GitHub and Job APIs enforce Origin/CSRF/idempotency for mutations. CLI supports Project list/create/clone/status/pull/push/branch and GitHub status/PR commands. Web provides responsive Project list/create/clone/detail, structured Git state, safe actions and Draft PR UI. Claude uses formal IDs externally and historical relative keys internally. Doctor reports Project Root/count and Runtime-observed Git/GitHub CLI/auth state without tokens or private paths beyond the configured root.

## Tests and E2E

- Backend: 178 tests passed at the implementation checkpoint; final count recorded after final verification.
- Frontend: 22 tests passed at the implementation checkpoint.
- Playwright: 48 desktop/mobile cases are defined after adding Phase 7 coverage. Local execution is blocked only by the unchanged host missing `libgbm.so.1`; GitHub CI is authoritative and no host package was installed.
- Migration upgrade/base-downgrade/upgrade is covered.

## Real Host Validation

Read-only validation observed Git 2.43.7, GitHub CLI 2.97.0, and a successful public `gh auth status` signal without exposing account/token data. A marker-bound Project under `.agentbox-dev/projects` passed init, structured status, branch create/list/switch and recoverable cleanup. Pull/Push network mutation and real Draft PR were safely skipped. No user Project or Claude/tmux session was touched and no host configuration was changed.

## Security Review

- Shell/arbitrary argv: absent.
- Protocol/URL: GitHub HTTPS/SSH allowlist; local/file/ext rejected.
- Path/symlink: canonical immediate-child resolution; symlink/root escape rejected.
- Git config/credentials: executable settings fail closed; prompts disabled; URL credentials redacted; raw output not logged/audited.
- Branch/remote: strict validation; no arbitrary remote, force, reset, clean, delete, merge or rebase fallback.
- Claude active session: Pull/switch blocked in Runtime.
- Partial clone: marker-bound atomic staging and exact rollback.
- Output/logging: normalized codes and bounded safe summaries only.

## Dependencies and CI

No Python or JavaScript runtime dependency was added. Dependency audits and GitHub required CI are recorded after publication.

## Deviations and Known Limitations

Issue browsing, commit/staging, diff/file browser, submodule/LFS management, Project deletion, upstream publishing, workflow actions, real GitHub PR mutation validation, and Project-aware Codex sessions remain out of scope. Local Playwright requires the host browser library noted above; CI runners contain the supported browser dependencies.

## Phase 8 Recommendation

After human review and merge, Phase 8 may address installer/runtime identity and production migration. Phase 8 was not started.
