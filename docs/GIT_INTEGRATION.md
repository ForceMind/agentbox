# Git Integration

## Execution boundary

Only `GitAdapter` in the Runtime Executor invokes Git through `ControlledProcessRunner`. Every operation has fixed argv, a bounded timeout/output cap, a controlled cwd resolved from a Project, and a sanitized environment. There is no shell, arbitrary argv, configuration passthrough, force push, reset, clean, branch deletion, staging, commit, or filesystem delete API.

The environment disables terminal prompts, system configuration, interactive credential managers, LFS smudge, and unapproved protocols. Fixed command-level configuration disables hooks, pagers, editors, and external diff. Repository-local executable configuration such as `core.sshCommand`, `credential.helper`, `core.hooksPath`, aliases, includes, pagers, editors, and external diff fails closed.

## Supported operations

- Status uses porcelain v2 and returns only structured branch, upstream, ahead/behind, staged, unstaged, untracked, conflict, clean, redacted remote, and submodule-presence fields.
- Branch names pass a strict lexical validator and `git check-ref-format --branch`. Switch never stashes, resets, or discards changes.
- Pull is always `--ff-only --no-rebase`; divergence returns `GIT_PULL_REQUIRES_RECONCILIATION` and never falls back to merge or rebase.
- Push requires an existing upstream and never uses force or guesses a remote.
- Pull and branch switch are rejected while the Project has a running or needs-interaction managed Claude session.

Remote credentials, query strings, fragments, control characters, and raw stdout/stderr are not returned, logged, audited, or persisted. Errors are normalized to stable codes. Repository and `.git` ownership must match the Runtime user; AgentBox never adds wildcard `safe.directory` or changes ownership.
