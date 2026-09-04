# Current Authorized Action

Action ID: `DELEGATED-RUNTIME-RELAY-2026-09-03`

The Owner explicitly delegated software goal, plan and architecture decisions to
the Coding Agent and instructed continued development. The complete reviewed
[WAW stream supplement](WAW_ENCRYPTED_STREAM_DECISION.md) is accepted for software
implementation under [GOVERNANCE](GOVERNANCE.md). The previous R3 confirmation
blocker is resolved. Do not request the same software approval again.

## Active implementation

- Preserve merged R0/R1/R2/R9.1/R10.1 and the verified delivery record, PRs #67–#72.
- R3/R4 are merged as PR #73 after 19/19 checks and exact read-back.
- R5 is merged as PR #74 after 19/19 checks and exact read-back. Cold-start/GC
  parser failures are fixed without relaxing the 5 ms budget.
- R6 is merged as PR #75 after 19/19 checks and exact read-back; staged ticket
  authority, atomic publication, reader handoff and cleanup/Audit fences delivered.
- R7 is merged as PR #76 after final independent PASS, 19/19 exact-head checks
  and exact read-back; Runtime encrypted stream/server and publication fences delivered.
- R8 is merged as PR #77 after independent PASS, 19/19 exact-head checks,
  normal merge, exact read-back and six successful post-main workflows.
- R9 is merged as PR #78 after independent PASS, 19/19 exact-head checks,
  normal merge `15a4632f915dd1e1bde19425e313b52ada27166f`, exact read-back and
  six successful standard post-main workflows.
- R10/rc5 is delivered by PR #79: final head `0d9e7c7...` completed 20/20
  exact-head checks and merged as `341a69bf...`; exact parent read-back, all six
  post-main workflows and dynamic Dependency Graph completed SUCCESS.
- Active R11/rc6 first closes the public API host-anchor loader, same-live-Runtime
  control/stream pidfd binding, durable runtime-epoch reconciliation and Runtime
  redraw capture. It then composes the browser/API/Runtime controller. rc7–rc9
  add failure injection, operational/artifact rehearsal and full cross-page
  bilingual migration. Locale is fixed per document from only
  `navigator.languages[0]`: primary `zh` → `zh-CN`; all other/missing/malformed
  values → English; technical identifiers remain English.
- Keep R7/R8 active lifecycle obligations explicit: 30s stale/60s grace,
  15min idle/8h absolute, Runtime health, current auth and positive cleanup.
- Resolve remaining software contracts with documented rationale and independent
  review under the delegated authority, rather than another mechanical Owner gate.

Each stage follows feature branch → exact-head terminal CI → normal merge →
exact read-back, updating CURRENT_STATE, the remaining plan and relevant scope
documents. Complex work uses sol; routine implementation/verification uses terra.

## Remaining evidence boundaries

Mac remains the development platform. Real host activation, production keys or
Provider Secret operations, publication and support promises require a concrete
scope/target and real evidence. Software decisions do not certify those gates.
The independent trust-provider deployment and actual CLI/PTY/isolation/restart
qualification remain required before full product completion. No synthetic
handler or passing codec test may be presented as a working terminal.
