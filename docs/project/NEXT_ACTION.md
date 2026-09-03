# Current Authorized Action

Action ID: `MAC-WAW-RUNTIME-COMPOSITION-2026-09-03`

Owner clarified that development continues on the current Mac. Development
platform and deployment qualification are separate: a missing Linux test host
must not block platform-independent implementation, local tests or Linux CI.
The prior blanket host prerequisite for all remaining software work is superseded
by this clarification; actual host activation, Secret handling, new architecture
decisions and production promises retain their existing boundaries.

## Current slice — concrete Runtime composition

PR #63 completed shared Claude/Codex supervisor integration with 19/19 CI
checks and merge `90df8b9adfe3c03fc089634c18214a4fb6fcfe9e`.

- Implement `WAWSupervisorExecutor` over the real shared supervisor and trusted
  Project/command/transport factories, using the consumed Runtime epoch.
- Use exact read-only process probes for status/reconcile; preserve detached
  writer and uncertain input states. Explicit reconnect restores the binding.
- Retain failed-start targets for exact cleanup; consume durable generation
  before side effects and quarantine unknown restart/cleanup outcomes.
- Construct stream bridges over the same supervisor only for an already-admitted
  `ActiveAttachment`; prepare remains a reservation with no terminal writer.
- Test both AgentTypes, failure, cancellation, identity drift and restart; run
  independent review and exact-head Linux CI before merge/read-back.

## Next implementation and validation

Continue the remaining Runtime command/transport factory, process and encrypted
stream/browser integration on Mac where feasible, using injected OS boundaries
and truthful local/CI evidence. Use the existing architecture contracts; resolve
new architecture decisions explicitly when encountered. Do not substitute Fake
Runtime evidence for actual CLI/PTY/Noise/host qualification or call partial
integration complete.

Linux systemd/cgroup/namespace/LSM/seccomp, real Runtime activation, official
Runtime-user login/Trust, deployment and reboot acceptance still require an
identified authorized target and attributable host evidence before those
operations or readiness claims. A Linux SSH alias is not required merely to
continue software development on this Mac.
