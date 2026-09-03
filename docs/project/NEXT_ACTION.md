# Current Authorized Action

Action ID: `WORKSPACE-METADATA-UX-2026-09-03`

Stage D implementation awaits exact-head CI/merge on `codex/workspace-metadata-workflow`, based on
`7c1c755854077d2e0989ff1d3ab3d54f77e9e707` (PR #59 exact merge read-back).

- Add typed Project/AgentType filters before workspace list authorization/cap.
- Connect READY Project and Claude/Codex selectors to exact workspace metadata.
- Wire explicit Start and exact-generation Stop with a scoped second confirmation.
- Reject stale query/action responses, unknown selection, Runtime mismatch or
  recovery-required states; distinguish durable metadata from Runtime evidence.
- Provide clear loading/empty/unregistered/error states and desktop/mobile
  controls, plus an entry from Project Detail.
- Keep terminal Connect/Reconnect/Detach/input visibly unavailable until a
  qualified real stream adapter exists. No ticket is obtained merely to make a
  button appear functional, and HTTP success is never ADMITTED.
- Run unit/integration tests and actual browser metadata interaction/visual QA;
  independently review, update docs, run exact-head CI, merge and read back.

Stage E prepares software release evidence and remaining limitations. Stage F
still requires explicit architecture/host authorization and attributable real
host evidence for fixed CLI/PTY execution, legacy interlocks, Noise/WebSocket,
login readiness, isolation and reboot recovery. No Secret/host/production
activation is part of this metadata UI stage.
