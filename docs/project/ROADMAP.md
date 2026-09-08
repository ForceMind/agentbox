# AgentBox Roadmap

## Current increment: workstation evolution

The 2026-09-08 task adds an audit and evidence-backed product evolution to this
existing roadmap. [WORKSTATION_EVOLUTION](../WORKSTATION_EVOLUTION.md) defines
the sequence; [CAPABILITY_MATRIX](../CAPABILITY_MATRIX.md) separates design,
implementation, validation and availability.

1. WEV-1 — merged in PR #87 as `b3e9cd5`: revalidate Workspace observations when
   returning to the browser; no automatic Agent lifecycle operation or new data
   domain. Exact-head CI and independent reviews passed; delivery read-back is
   recorded in the evolution document.
2. R12 — not started: concrete authorized host/trust/provider/bootstrap and
   real CLI/recovery acceptance; remains the first real product-flow blocker.
   Use the five-part [bootstrap/host checklist](../WORKSTATION_EVOLUTION.md#r12-production-bootstrap-and-host-gates):
   production API composition, Runtime filesystem-v2/provider composition,
   activated sockets/isolation, managed CRX/Native Messaging/trustd, and real
   CLI login/input/return/reconnect/exact Stop/reboot acceptance.
3. Proposed follow-ups — bounded Active Work/Attention projection, read-only
   Changes/Files, then capability-bound Discovery/Resume and structured Approval.
   Task/Worktree and external notification remain later, contract-dependent work.

The completed R11 software evidence below remains valid; it does not claim
end-to-end production availability or authorize new host/Secret operations.

## Completed

- Phase 0 through Phase 10 (as per existing repository governance).
- Governance automation policy is merged; routine mechanical actions proceed after CI.
- WAW-1 typed HTTP lifecycle, transient ticket/reconnect, Runtime attachment prepare/detach contracts merged in PRs #47/#48/#49.
- WAW-1 bounded synthetic stream bridge and WAW-2 Codex command identity contract merged in PR #52.
- WAW-1 fail-closed WebSocket route boundary merged in PR #54; WAW-2 synthetic lifecycle support merged in PR #55.

- WAW-3 software recovery/cursor/lease and browser stale-event fences merged in PR #58, with 19/19 exact-head checks successful. Full WAW-3 real transport/reboot remains unverified.

- WAW-2 Codex API/ticket/Web contracts merged in PR #59 with 19/19 exact-head checks successful. Real CLI execution and legacy process interlocks remain gated.

- Workspace metadata workflow merged in PR #60 with 19/19 exact-head checks successful; desktop/mobile metadata interactions are tested, terminal admission remains unavailable.

- Software readiness and packaged WAW scope/gate documents merged in PR #61; 19/19 exact-head checks and independent artifact/doc-presence validation passed.

- Shared Claude/Codex supervisor and stream lifecycle fences merged in PR #63 with 19/19 exact-head checks successful.

- Concrete Runtime executor, formal Project mapping, read-only probes and failed-start recovery merged in PR #64 with 19/19 exact-head checks successful.

- Fixed Noise NX Python/WebCrypto cores, pinned independent vectors and two-role interoperability merged in PR #65 with 19/19 exact-head checks successful.

- Native Chromium Noise verification merged in PR #66; all 60 Linux E2E tests and 19/19 exact-head checks passed.

- Login/reauthentication capacity now follows actual worker completion after caller cancellation; PR #67 merged with 19/19 exact-head checks successful.

- Opaque AWCE Python/Web framing, header builders and interoperability merged in PR #68 with 19/19 exact-head checks successful.

- Descriptor-held executable provenance foundation merged in PR #69 with 19/19 exact-head checks successful; complete interactive process/host qualification remains unfinished.

- Isolated numeric authentication timing diagnostic and failure/privacy regressions merged in PR #70 with 19/19 exact-head checks successful; historical latency cause remains unknown.

- Incremental UTF-8/VT tokenizer foundation merged in PR #71 with 19/19 exact-head checks successful; complete browser terminal/controller remains unfinished.

- Accepted application cryptography merged in PR #73 with 19/19 exact-head checks; full-vector interop and 62 native/normal browser cases passed.

- Full WAW wire profiles and bounded transcript validation merged in PR #74 with 19/19 exact-head checks; real parser-budget integration failures were corrected and measured.

- Staged ticket authority and admission coordinator merged in PR #75 with 19/19 exact-head checks; four independent review findings were fixed before delivery.

- Runtime encrypted attachment stream and exact socket/Stop publication fences merged in PR #76 with 19/19 exact-head checks; final review deadlock and logical-line findings were repaired before delivery.

- Native WebSocket/API ciphertext relay, shared parser/INPUT budgets and cancellation-resistant cleanup merged in PR #77 with 19/19 exact-head checks; all six post-main workflows succeeded.

- Managed Chromium/Native Messaging/trustd browser trust, cumulative root checkpoints,
  bounded browser terminal model and `zh-CN`/English Workspace boundary merged in
  PR #78 with 19/19 exact-head checks and exact read-back.

- Fixed Claude/Codex interactive profiles, native PTY/bootstrap/attach chain,
  Runtime process composition and inert rc5 policies merged in PR #79 at
  `341a69bf...` after 20/20 exact-head checks; six post-main workflows and the
  dynamic Dependency Graph update succeeded.

## Current reassessment

See [REMAINING_PLAN.md](REMAINING_PLAN.md). R0–R10 are delivered through PR #79.
R10 final head `0d9e7c7...` passed 20/20 checks and merged as `341a69bf...` with
exact read-back and successful post-main workflows. Host evidence remains
separately tracked in R12.

## In Progress

- Mac remains the development platform. R11 rc6 and rc7 are delivered by
  PRs #80 and #81, and rc8 is delivered by PR #83. Documentation head
  710ceef completed 26 exact-head checks, merged normally as
  95bf65d6114008b962985f7311941499c961a7b8 with exact parents 87f5bce and
  710ceef, and all six post-main workflows succeeded. rc8 is software evidence
  only: no tag, GitHub Release, host activation or R12 qualification occurred.
  PR #85 final head `751d4d010f92e18780bd6d96fdb3c9ea23107464` completed all 26
  exact-head checks and merged normally as `b07f944ef2c7b590e5a3f1fa50354d6f492d6c31`.
  All six post-main workflows succeeded, so R11 software rc6–rc9 is delivered
  as software evidence. R12 remains independently unstarted and host-gated.

- Parallel multi-agent execution and per-stage GitHub/document updates are
  authorized by Owner on 2026-09-03. The active checklist is `EXECUTION_PLAN.md`.

## Next

- F1: preserve the delivered R11 software contracts and evidence; no tag, GitHub
  Release, production deployment or Provider credential operation follows from
  the merge.
- F2: real Linux host activation, isolation/CLI/PTY/reboot qualification and
  product acceptance remain independently gated.
