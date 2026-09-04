# AgentBox Roadmap

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

## Current reassessment

See [REMAINING_PLAN.md](REMAINING_PLAN.md). R0 and R1 are merged. R10.1 executable provenance is merged; R9.1 browser tokenizer foundation is merged. The complete wire/admission/trust supplement has passed independent review and is accepted under the Owner's explicit software decision delegation. R2 diagnostics and R9.1 tokenizer are merged. R4 is merged; R5 is merged; R6 staged admission is merged as PR #75; R7 Runtime integration is merged as PR #76; R8 API relay is merged as PR #77; full R9/R10 implementation and host evidence remain separately tracked.

## In Progress

- Mac remains the development platform. R9 is delivered; R10 fixed interactive
  process/profile implementation is active under delegated software decision authority.
- Parallel multi-agent execution and per-stage GitHub/document updates are
  authorized by Owner on 2026-09-03. The active checklist is `EXECUTION_PLAN.md`.

## Next

- F1: continue remaining software implementation on Mac and validate through local tests plus Linux CI.
- F2: real Linux host activation, isolation/CLI/PTY/reboot qualification and product acceptance remain independently gated.
