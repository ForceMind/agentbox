# Current Authorized Action

Action ID: `MAC-WAW-CODEX-SUPERVISOR-2026-09-03`

Owner clarified that development continues on the current Mac. Development
platform and deployment qualification are separate: a missing Linux test host
must not block platform-independent implementation, local tests or Linux CI.
The prior blanket host prerequisite for all remaining software work is superseded
by this clarification; actual host activation, Secret handling, new architecture
decisions and production promises retain their existing boundaries.

## Current slice — shared Codex supervisor and stream lifecycle

- Reuse the concrete fixed Claude/Codex command types as a closed union.
- Bind supervisor lifecycle/attachment/input/output/resize/detach/reconnect/exact
  Stop to the selected command's AgentType and complete workspace identity.
- Revalidate concrete commands before transport start; reject duck types,
  subclasses, stale executable identity and cross-AgentType operations.
- Fence closed/detached stream replay and make active CLOSE use positive
  attachment cleanup proof without stopping the workspace.
- Keep the existing real Claude tmux adapter explicit about unsupported Codex;
  no caller argv/path/env or fake real-host success is introduced.
- Run Mac-compatible tests, independent review, exact-head Linux CI, then
  merge/read-back and update the project documents.

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
