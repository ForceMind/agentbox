# AgentBox Roadmap

## Completed

- Phase 0 through Phase 10 (as per existing repository governance).
- Governance automation policy is merged; routine mechanical actions proceed after CI.
- WAW-1 typed HTTP lifecycle, transient ticket/reconnect, Runtime attachment prepare/detach contracts merged in PRs #47/#48/#49.
- WAW-1 bounded synthetic stream bridge and WAW-2 Codex command identity contract merged in PR #52.
- WAW-1 fail-closed WebSocket route boundary merged in PR #54; WAW-2 synthetic lifecycle support merged in PR #55.

- WAW-3 software recovery/cursor/lease and browser stale-event fences merged in PR #58, with 19/19 exact-head checks successful. Full WAW-3 real transport/reboot remains unverified.

- WAW-2 Codex API/ticket/Web contracts merged in PR #59 with 19/19 exact-head checks successful. Real CLI execution and legacy process interlocks remain gated.

- Workspace metadata workflow merged in PR #60 with 19/19 exact-head checks successful; desktop/mobile metadata interactions are tested, terminal admission remains unavailable.

- Software readiness and packaged WAW scope/gate documents merged in PR #61; 19/19 exact-head checks and independent artifact/doc-presence validation passed.

## In Progress

- Final evidence snapshot and CI/merge read-back; software stages A–E are complete.
- Parallel multi-agent execution and per-stage GitHub/document updates are
  authorized by Owner on 2026-09-03. The active checklist is `EXECUTION_PLAN.md`.

## Next

- Stage F: real stream/Noise/PTY/browser, isolated CLI/host qualification and
  product acceptance. This stage has missing authorization/evidence gates;
  it is not implemented or validated by synthetic software stages.
