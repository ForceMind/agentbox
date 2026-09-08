# Current Authorized Action

## 2026-09-08 workstation evolution

The Owner requested a bounded incremental audit/research/implementation task.
Use [WORKSTATION_EVOLUTION](../WORKSTATION_EVOLUTION.md) as its task record and
[CAPABILITY_MATRIX](../CAPABILITY_MATRIX.md) as the evidence index. The current
software increment is WEV-1: invalidate browser Runtime observations after
interruption and re-read them on return before exposing lifecycle controls.
No automatic Start/Resume/Connect, new API/DB domain or production activation is
authorized by this increment. Branch: `codex/workstation-evolution`.

Complete the seven-project research, WEV-1 implementation, focused recovery
tests, bilingual browser coverage, independent review and normal CI/merge/read-back.
Later Files/Diff, Attention/Approval, Discovery/Resume and Task/Worktree proposals
need their own bounded contracts. R12 is still blocked on concrete target,
Runtime/trust/Secret scope and real-host evidence. The completed R11 record
below is historical context, not a command to repeat its work.

Action ID: `DELEGATED-RUNTIME-RELAY-2026-09-03`

The Owner explicitly delegated software goal, plan and architecture decisions to
the Coding Agent and instructed continued development. The complete reviewed
[WAW stream supplement](WAW_ENCRYPTED_STREAM_DECISION.md) is accepted for software
implementation under [GOVERNANCE](GOVERNANCE.md). The previous R3 confirmation
blocker is resolved. Do not request the same software approval again.

## Active implementation

- rc8 is delivered by PR #83: documentation head
  710ceef696757a8a1f2a9165f2312672db57bb1e completed 26 exact-head checks,
  merged normally as 95bf65d6114008b962985f7311941499c961a7b8 with exact
  parents 87f5bce and 710ceef, and all six post-main workflows succeeded. This
  remains software-only evidence; no tag, release, host activation or R12
  qualification occurred.
- RC9 is delivered through PR #85: exact-head CI, normal merge, merge read-back
  and all post-main workflows succeeded. Preserve the immutable locale rule (only
  `navigator.languages[0]`, `zh` primary → `zh-CN`, otherwise English) and
  preserve technical values without translating or humanizing external protocol
  strings. R11 software rc6–rc9 is complete as software evidence; do not extend
  that result to R12.
- The fixed rc8 predecessor/artifact operations jobs are now version-aware and
  fail-closed: rc8 executes them successfully, while rc9 skips exactly those
  historical jobs and still requires current-candidate artifact checks and
  `release-gate` success. Preserve the fixed rc8 contract; skipped, failing or
  unknown results must never count as pass.

- rc9 version text is Python `0.3.0rc9`, npm `0.3.0-rc.9`, MV3 `0.3.0.9`.
  Production output must retain no test bypass; the distinct-origin Workspace
  harness is E2E-only and sensitive artifacts remain disabled. R12 stays
  independent, unstarted and host-gated. No tag, GitHub Release, production
  deployment, Provider credential operation or real host activation occurred.

- Historical rc6 work-unit and checkpoint evidence remains in the execution
  plan and current-state record. The rc8 and rc9 actions above are the current
  authoritative sequence.

- Historical rc9 foundation commit `184781c...` completed 20/20 exact-head
  checks. Its shared catalog, error-code mapper and route-state manifest are
  now incorporated in the delivered rc9 implementation; the page migration and
  bilingual visual matrix are no longer a pending implementation item. Current
  evidence is recorded in `CURRENT_STATE.md`; its CI/merge record is delivered.

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
- PR #80 repair head `bbdd67c...` has terminal 20/20 CI after fixing the shared
  descriptor-release/inode-reuse issue. It verifies the current first-use/
  evidence checkpoint. Native/format follow-ups completed in `4222242...` 20/20
  CI. Do not merge before replay, controller composition and the remaining rc6
  acceptance set.
- Current evidence: the final local core matrix completed 216 plus 5 focused
  cases; independent Sol/xhigh review completed 244 cases with 1 Linux-only skip
  and 9 deselected, plus 8 encrypted-server non-UDS cases. Review is PASS with no
  remaining P0/P1/P2. Twenty-eight real-UDS cases are locally unverified because
  this environment returned `PermissionError` during socket setup. Ruff, Black,
  Linux-target mypy (256 sources), doc links (240) and `git diff --check` pass.
- The current uncommitted bounded-redraw slice has a neutral 24-row/60 KiB
  contract with row 25 and byte 61,441 as discarded sentinels. Held-FD tmux
  capture proves socket/pane/retained-pidfd identity before and after one shared
  one-second deadline; supervisor capture/cursor/baseline publication is atomic,
  and production capture callbacks are removed from registry/service/bootstrap.
  The unified focused matrix completed 341 tests with 9 Linux-only skips and 2
  local UDS cases deselected; independent Sol/xhigh review reports PASS with no
  P0/P1/P2. The new Linux native case requires exact-head CI; local UDS setup
  remains unverified after `PermissionError`.
- Head `adf44fc0...` ran the new real Linux capture successfully, then failed the
  native job at teardown because the test killed tmux before calling a helper
  that expects the tmux socket. The test-only follow-up removes that invalid
  cleanup assertion. Commit/push it and require a fresh exact-head native/full
  Backend pass before recording bounded redraw complete.
- Follow-up `f37f92d9...` completed the required 20/20 exact-head matrix. Linux
  native completed 73 cases; Backend Python 3.11 completed 3629 passed/44 skipped,
  with 3.12/3.13 also successful. Treat bounded redraw as verified and continue
  with `WAWRuntimeApplication` production composition and singleton ownership.
- The current `WAWRuntimeApplication` composition is uncommitted: typed Runtime
  key/executor providers and activated sockets have distinct one-shot ownership;
  stream, control and legacy share application start/close tasks and one dispatch
  gate. Partial production builders are private and weak-map provenance is gone.
  Incomplete construction retains a typed retryable owner. Provider closure waits
  for stream/control/lifecycle/legacy clean evidence. Independent Sol/xhigh review
  reports PASS with no P0/P1/P2; Linux-target mypy covers 260 sources. Production
  main, real key/provider and host activation remain disabled.
- `WAWRuntimeApplication` head `628e9c00...` completed 20/20 exact-head checks.
  Continue rc6 with the API singleton, one attachment/bind/control/relay owner and
  lifespan shutdown ordering; keep real key/provider and production activation in
  their existing host-gated scope.
- `AttachmentAuthority` shutdown fencing is implemented and independently reviewed:
  pending tickets burn, cleanup obligations survive invalidation, and only exact
  cleanup/Audit ACK reaches clean. Commit and exact-head verify this foundation,
  then implement the process lock and single bind/control/relay lifespan owner.
- Bind/control shutdown evidence is also complete locally: pending exchange,
  detached task, retained peer or uncertain FD close prevents clean. Commit and
  exact-head verify it, then continue process lock and stream-owner composition.
- Begin rc7 with named test-only checkpoints, manual promises, fake monotonic clocks
  and controlled partial-write sockets. Prove admission/stream/restart/shutdown/Stop/
  browser-lifecycle failure invariants before advancing to rc8 artifact rehearsal
  and rc9 full browser-selected bilingual UI.
- First integration head `e210d749...` completed 17/20 checks. Three Backend
  matrix jobs exposed one shared legacy regression: a clean non-fixed server could
  no longer restart without consuming a second epoch. The local reviewed fix
  restores only that compatible restart; fixed/control/poisoned/incomplete shutdown
  stays terminal. Follow-up `c534fe437...` completed the fresh exact-head 20/20
  matrix. Continue the remaining rc6 controller composition; do not merge rc6 until the full
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
