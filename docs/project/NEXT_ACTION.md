# Current Authorized Action

Action ID: `WAW3-RECOVERY-CONTRACT-2026-09-03`

- Implement pure WAW-3 recovery/cursor/lease reducers with exact generation, binding and runtime epoch fencing.
- Wire the Workspace reducer to reject stale events before any real stream is enabled.
- Keep real Noise/WebSocket/PTY/browser and host activation blocked until independent host evidence exists.
- After recovery contracts, continue WAW-2 Codex attachment/CLI integration.

## Current stage and delivery

- Stage B implementation is awaiting exact-head CI/merge on `codex/waw3-recovery-contracts` with independent
  backend/frontend ownership and read-only Architecture/Security/Test review.
- Preserve existing implementations; complete the specific missing recovery
  fences and meaningful negative tests. No public ABWS schema expansion,
  transport activation, database storage migration or Secret operation is part
  of this stage.
- Update project docs in the stage PR, wait for all exact-head CI to be
  terminal, merge normally and read back the actual merge SHA.
- Subsequent software work follows stages C/D/E in `EXECUTION_PLAN.md`.
  Stage F remains dependent on explicit authorization and host evidence.
