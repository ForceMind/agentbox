# AgentBox Execution Plan

This is the live execution plan for the remaining AgentBox product slices.
Each stage is delivered as a feature branch and PR, requires terminal CI for
the exact head, and is followed by an exact merge read-back and a snapshot
update. Synthetic/Fake Runtime evidence is never promoted to real-host or
production evidence.

## Stage 1 — WAW-1 Claude transport contract

Deliver a bounded Runtime-owned stream session that composes the existing
ABWS framing, Noise metadata state machine, output ring, attachment lease and
supervisor. Cover input, resize, output replay/GAP, detach, close, backpressure
and typed failure states with synthetic data. No plaintext terminal payload may
cross API/Worker; no real cryptography, listener, PTY or provider login is
claimed.

## Stage 2 — WAW-1 web workspace experience

Wire the browser Workspace page to the typed metadata APIs and expose explicit
Start/Connect, Detach and exact Stop state transitions with loading, conflict,
reconnect and mobile-control states. Keep tickets and terminal bytes in memory
only. Real WebSocket/Noise/PTY rendering remains host-gated.

## Stage 3 — WAW-2 Codex

Add a separate Project-scoped Codex workspace model and fixed Runtime command
contract. Claude runtime/session-only boundaries remain unchanged. Cover
identity, generation, marker, lifecycle and attachment behavior using Fake
Runtime; provider authentication and real Codex login are excluded.

## Stage 4 — WAW-3 continuity and recovery

Implement bounded restart/reconnect, lease and cursor fencing, mobile/background
suspension handling, Runtime/API restart classification, recovery states and
reboot-safe reconciliation. Add race, stale-generation and failure-injection
tests without durable terminal transcript storage.

## Stage 5 — release readiness

Run the complete Python/frontend/e2e/security test matrix, obtain independent
read-only Architecture/Security/Test conclusions, update all project snapshots
and release documents, and prepare artifacts. Any unverified host capability
remains explicitly blocked.

## Stage 6 — host validation and production

Only with authorized disposable Linux host evidence, validate installer,
systemd sockets, cgroups, PTY/devpts, pidfd/process isolation, Noise/WebSocket
transport, Claude readiness, recovery and deployment. Record exact evidence and
release fingerprints before production publication; otherwise report the
specific blocker and continue non-host work.

## Exit criteria

The product is complete only when each stage has merged code/docs, terminal
CI, exact read-back, and evidence appropriate to its claim. Real-host and
production criteria cannot be satisfied by local macOS tests, Fake Runtime,
synthetic canaries, or architecture prose.
