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
- PR #80 remote baseline `b2f0e0b...` completed 20/20 exact-head checks with
  `SUCCESS`. The current rc6 integration is uncommitted: a single
  `WAWPeerAuthority` now supplies typed control peer context, stream authority,
  lifecycle transfer/revocation and Runtime shutdown ownership. It is not yet a
  committed or CI-verified delivery.
- Current evidence: the final local core matrix completed 216 plus 5 focused
  cases; independent Sol/xhigh review completed 244 cases with 1 Linux-only skip
  and 9 deselected, plus 8 encrypted-server non-UDS cases. Review is PASS with no
  remaining P0/P1/P2. Twenty-eight real-UDS cases are locally unverified because
  this environment returned `PermissionError` during socket setup. Ruff, Black,
  Linux-target mypy (256 sources), doc links (240) and `git diff --check` pass.
- Complete this rc6 integration slice by commit/push and exact-head Linux CI,
  then continue bounded redraw and the remaining production controller composition.
  Normal merge and exact read-back follow the complete rc6 acceptance set. After
  rc6, proceed serially to rc7 failure injection, rc8 artifact/operations rehearsal
  and rc9 full UI localization/visual E2E.
- First integration head `e210d749...` completed 17/20 checks. Three Backend
  matrix jobs exposed one shared legacy regression: a clean non-fixed server could
  no longer restart without consuming a second epoch. The local reviewed fix
  restores only that compatible restart; fixed/control/poisoned/incomplete shutdown
  stays terminal. Follow-up `c534fe437...` completed the fresh exact-head 20/20
  matrix. Continue with the bounded redraw slice; do not merge rc6 until the full
  controller composition and rc6 acceptance set are complete.
- Locale remains fixed per document from only `navigator.languages[0]`: primary
  `zh` → `zh-CN`; all other, missing or malformed values → English. Technical
  identifiers remain English.
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
