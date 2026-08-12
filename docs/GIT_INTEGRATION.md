# Git Integration

## Execution boundary

Only `GitAdapter` in the Runtime Executor invokes Git through `ControlledProcessRunner`. Every operation has fixed argv, a bounded timeout/output cap, a controlled cwd resolved from a Project, and a sanitized environment. There is no shell, arbitrary argv, configuration passthrough, force push, reset, clean, branch deletion, staging, commit, or filesystem delete API.

The environment disables terminal prompts, system configuration, interactive
credential managers, LFS smudge, and unapproved protocols. Only controlled
values for `GIT_CONFIG_GLOBAL`, `GIT_ASKPASS`, and `SSH_ASKPASS` may reach the
final Git process. Fixed command-level configuration disables hooks, pagers,
editors, external diff, and optional locks for read-only inspection.

Repository and worktree-scope executable or transport-changing configuration is
enumerated with includes disabled and fails closed. System/global configuration
is disabled, while command-scope safety overrides remain fixed by AgentBox.
The deny set covers credentials and all repository HTTP settings; `core.sshCommand`,
`core.hooksPath`, `core.askPass`, `core.fsmonitor`, `core.worktree`,
`core.gitProxy`, pagers and editors; aliases and includes; diff drivers and
external diff; clean/smudge/process filters; `url.*.insteadOf` rewrites;
remote upload/receive programs; and related helper injection. This is a typed
adapter policy, not a user-extensible Git config allowlist.

## Supported operations

- Status uses porcelain v2 and returns only structured branch, upstream, ahead/behind, staged, unstaged, untracked, conflict, clean, redacted remote, and submodule-presence fields.
- Branch names pass a strict lexical validator and `git check-ref-format --branch`. Switch never stashes, resets, or discards changes.
- Pull fixes the target to the validated `origin` upstream ref and always uses `--ff-only --no-rebase --no-tags --no-recurse-submodules --no-verify`; divergence returns `GIT_PULL_REQUIRES_RECONCILIATION` and never falls back to merge or rebase.
- Push requires a uniquely configured, approved GitHub `origin` upstream and sends one explicit non-`+` local-to-remote branch refspec with hooks disabled. It never uses force, guesses a remote, mirrors, or deletes a branch.
- Pull and branch switch are rejected while the Project has a running or needs-interaction managed Claude session.

Remote credentials, query strings, fragments, control characters, and raw stdout/stderr are not returned, logged, audited, or persisted. Errors are normalized to stable codes. Repository and `.git` ownership must match the Runtime user; AgentBox never adds wildcard `safe.directory` or changes ownership.
