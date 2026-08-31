# Codex Operating Protocol

## Standard Lifecycle

1. Rehydrate context
2. Live reconcile
3. Determine authorization
4. Plan bounded work
5. Use read-only subagents where required
6. Execute bounded work
7. Validate
8. Review diff
9. Publish Draft PR
10. Wait for exact-head CI terminal
11. Independent review
12. Owner gate
13. Merge/read-back only after exact Owner authorization
14. Update snapshot
15. Stop

## Recovery Rules

- **Stale context:** Git/GitHub live state and merged ADRs win; refresh snapshot, never roll back.
- **Dirty worktree:** do not modify, stash, reset, clean or overwrite; use an independent temporary worktree and report.
- **Unknown branch/repository:** stop until identity and permissions are verified.
- **CI failure:** fix only within authorized scope, push a normal commit, and re-run exact-head checks; never bypass.
- **External failure:** record command, exit code and recovery condition; do not claim success.
- **Architecture conflict:** do not silently reconcile; report evidence and BLOCKED until Owner decision.
- **User interruption:** preserve current branch/PR, stop writes, report partial state and next safe action.
- **“继续”:** rehydrate, reconcile, read `NEXT_ACTION`, execute only its still-authorized action, and stop at the next gate.
- **“批准合并”:** require literal human exact PR/head/base authorization; verify no drift, terminal CI and review evidence, then perform only the authorized merge method and read back parent/tree. Never self-approve.

## Safety Invariants

No automatic Ready, merge or next Slice; no production code/Secret/API key handling outside explicit authorization; no force push or `--admin`; no prompt relay to another AI.
