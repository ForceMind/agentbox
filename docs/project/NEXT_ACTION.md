# Current Authorized Action

Action ID: `WAW2-CODEX-CONTROL-2026-09-03`

## Current stage

Stage C software implementation awaits exact-head CI/merge on `codex/waw2-codex-control-integration`, based on
`d2470601a06da0a4024fa1772b4f32ec2daa7293` (PR #58 exact merge read-back).

- Reuse the existing closed `AgentType`, Project-scoped WAW identity,
  `WAWCodexCommand`, lifecycle and transient attachment ticket contracts.
- Enable symmetric Codex Start/Stop/ticket metadata in API schemas/routes and
  Web response parsers/action hooks. Preserve exact Project/AgentType/generation
  response binding, CSRF/recent-auth, writer lease and no-store boundaries.
- Keep pre-registered Runtime/Project workspace provenance required. Do not
  synthesize a host binding, adopt legacy Remote Control, or route WAW through
  `codex.remote.*`.
- Validate with ASGI/Fake Runtime, closed-schema and cross-identity tests;
  independently review, update docs, run exact-head CI, merge and read back.

## Remaining scope

- Stage D wires the actual Workspace metadata page workflow and verifies its
  desktop/mobile rendering and interactions.
- The fixed Codex command exists, but real command execution still depends on
  the approved Runtime process/PTY substrate. Current Claude tmux adapter is not
  proof of Codex execution; no generic shell or caller argv fallback is allowed.
- Stage E prepares software release evidence. Stage F requires explicit
  architecture/host authorization and real evidence for Noise/WebSocket/PTY,
  CLI readiness, isolation, reboot and production acceptance.
- No Secret handling, Provider login, production release or host activation is
  authorized by routine software merges. See `EXECUTION_PLAN.md`.
