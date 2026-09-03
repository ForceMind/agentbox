# Current Authorized Action

Action ID: `WAW-HOST-GATE-PENDING-2026-09-03`

Software stages A–E are merged and verified. The final documentation snapshot
records PR #61 merge `35191eeaf858041cf5c0767dc1579b67690444ec` and its exact-head
CI/artifact evidence; the snapshot itself follows normal CI/merge/read-back.

## Stage F — 未开始，等待必要输入

The overall interactive-terminal goal is not complete. Before real WAW
implementation/activation proceeds, the current project gates require:

1. Explicit Architecture/Owner scope for the existing proposed real
   Noise/WebSocket/PTY/process profile.
2. A named authorized isolated Linux test host (for example an SSH alias), with
   bounded install/start/stop/restart/recovery permission and preservation of
   existing production data/state.
3. Attributable non-secret evidence in the order of
   `../WAW1_HOST_GATE_CHECKLIST.md`, including operator-managed official CLI
   readiness, exact Runtime identities and recovery conditions.

The Owner was asked for the host during this task; no target/SSH alias was
provided. Do not reuse an existing production/MVP host by inference. Safe
read-only planning may continue, but ordinary merge permission does not
satisfy real architecture, host, Secret or publication gates.

Remaining implementation includes fixed CLI/PTY execution, legacy process
probes/interlocks, real Noise and authenticated WebSocket/browser terminal,
Linux isolation and end-to-end Runtime/API restart/reboot recovery. These are
not merely unchecked test boxes and must not be marked complete from Fake
Runtime or metadata UI. The detailed scope is `../WAW_SOFTWARE_READINESS.md`.

On receipt of the missing authorization/target, revalidate live Git/GitHub and
host context, then proceed in bounded feature branches. No prompt relay to
another AI, generic shell/filesystem gateway, credential copying, automatic
Trust acceptance, production release or support promise is permitted.
