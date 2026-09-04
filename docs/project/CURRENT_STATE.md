---
schema_version: 1
verified_at_utc: "2026-09-04T20:43:46Z"
verified_by: "codex-live-reconciliation"
repository: "ForceMind/agentbox"
---

# Current Verified State

## Current authorized implementation

- Live preflight after `git fetch origin --prune`: local `main` and `origin/main`
  equal R10 merge `341a69bf855f48f90cbecfb5c6872c3bf8c28360`; active R11 branch
  `codex/waw-production-controller-rc6` starts exactly there with a clean tree
  before this documentation update. Historical Draft PR #42 is the only open PR.
- R9 PR #78 completed 19/19 exact-head checks, normal merge, exact read-back and
  all six standard post-main workflows. The separate historical Dependency Graph
  limitation is addressed on this R10 branch by the `.txt` release input.
- Owner delegated the remaining software goal/plan/architecture and explicitly
  approved managed Chromium extension + Native Messaging + independent `trustd`,
  followed by R8 rc3 → R9/provider rc4 → R10 rc5 → R11 rc6–rc9. R9 is delivered;
  real host/key/provider activation remains R12.
- R10 `0.3.0rc5` is delivered by PR #79: final exact head `0d9e7c7...` completed
  20/20 checks and merged normally at `2026-09-04T20:37:51Z`. Fetch/read-back
  observed merge `341a69bf...` with exact parents `15a4632f...` and `0d9e7c7...`.
  All six standard post-main workflows and the dynamic Dependency Graph update
  completed SUCCESS. R11/rc6 software composition is now active.

## Historical live baselines

- At current-task start: clean tree; `HEAD/main/origin/main/merge-base` equal
  `dfb5eb796f8745ee10cd2a9cefe0cdd15de057a9`.
- All six exact-main workflows completed SUCCESS. Historical Draft PR #42 is
  the only open PR and is outside current writes. Network preflight exited 0.
- Latest code delivery baseline: clean tree before this documentation snapshot;
  `HEAD/main/origin/main/merge-base` equal
  `3f2e3a2de4b0482629f5f9a296d5db757f989876`. PR #71 completed 19/19 exact-head
  checks before normal merge. Fetch, merge read-back and main fast-forward exited 0.
- Active snapshot branch: `codex/remaining-plan-delivery-record`. This increment
  updates documentation only; it cannot predict its own future merge SHA.
- R0/R1/R10.1/R2 six-workflow post-main runs were separately read as SUCCESS.
  R9.1's six post-main workflows were also read as terminal SUCCESS at
  `2026-09-03T10:35:54Z`, independently of its PR-head checks.
- This snapshot records observed facts and cannot predict its own merge SHA.

## Delivered software stages

| Stage | PR | Exact reviewed head | Observed merge | Exact-head CI |
| --- | --- | --- | --- | --- |
| A/B — plan + recovery | #58 | `f3bb9035e061fc0babfcace6af891f257eb7fa74` | `d2470601a06da0a4024fa1772b4f32ec2daa7293` | 19/19 SUCCESS |
| C — Codex control | #59 | `3e0e7a921e008d9c6b5198d37b8254fbee174068` | `7c1c755854077d2e0989ff1d3ab3d54f77e9e707` | 19/19 SUCCESS |
| D — metadata UX | #60 | `9be95b10e57a3daa3690205d6c2ffad8da74424d` | `6972f0dba907afd9741c2dc3584f431ee32765ed` | 19/19 SUCCESS |
| E — software readiness | #61 | `0c894ff52f49793f599eb33c4b92b8223e6109b3` | `35191eeaf858041cf5c0767dc1579b67690444ec` | 19/19 SUCCESS |
| F1.1 — shared supervisor | #63 | `c78cb92a5afe8056ab44a1cc4e8a6bea3074e184` | `90df8b9adfe3c03fc089634c18214a4fb6fcfe9e` | 19/19 SUCCESS |
| F1.2 — Runtime composition | #64 | `ef8641bd409bbb6d17db707370de66f552bf4640` | `624b34b656dbf239dbc56fa79d216db7d17a349b` | 19/19 SUCCESS |
| F1.3 — fixed Noise core | #65 | `6d0c0f8ff8b452fd0288d6ac98b1f3fe79352ed7` | `f95d1a4b0f0bdbdda45bd8da6cc10f3f8ac10269` | 19/19 SUCCESS |
| Native browser Noise | #66 | `27ff0161ef65f4a6fe1389a4dbcf4fa318f63db1` | `dfb5eb796f8745ee10cd2a9cefe0cdd15de057a9` | 19/19 SUCCESS |
| R0 — auth worker capacity | #67 | `31a0bc9f38a5c2891a4b9d2bb403a09175579a98` | `d9c26b9eb26664368c384805d1138a5349b92b60` | 19/19 SUCCESS |
| R1 — opaque AWCE framing | #68 | `0dccb2a71ea38259f1e76e2b268961c213bc98e1` | `3ebb3e938a03d067ea7df66b6746b9675637e65b` | 19/19 SUCCESS |
| R10.1 — executable provenance | #69 | `9147cace5b554205dfecc20cf8bfb643d4c46761` | `9529da6d5c110b7a09d5972dfa0db5e012727451` | 19/19 SUCCESS |
| R2 — auth timing diagnostic | #70 | `eca03e47849b12449bb2ab4aec8dfdc001ef13dd` | `f7ef3c936529b19838cd087dc9e232397f1e304d` | 19/19 SUCCESS |
| R9.1 — browser tokenizer | #71 | `a57764ae0e1f3fc962bc4d52e3610373ef4226ff` | `3f2e3a2de4b0482629f5f9a296d5db757f989876` | 19/19 SUCCESS |
| R3/R4 — accepted application crypto | #73 | `df943ecbf37b6c748dc1af73f4270017a3d9f6dc` | `e4a6ecd0bc28de8b3895453cf9160f9a8d4e0064` | 19/19 SUCCESS |
| R5 — full wire profiles | #74 | `62d04adbfa775f3a14ab678c485093f15b1039ed` | `3b11ebf0b3442c111586fc08df9f6a5a4abb3db6` | 19/19 SUCCESS |
| R6 — staged admission | #75 | `679b2f71ec5917ead7695c3b20cb1118cb46cc76` | `a27621faca0e0d04b529b51993f98138496a75b5` | 19/19 SUCCESS |
| R7 — Runtime encrypted stream | #76 | `01c716bd4713ef4a6676b71754a4e065ebce3b82` | `4180f0991af97cba108b6e5a707b7abf58a444d2` | 19/19 SUCCESS |
| R8 — API ciphertext relay | #77 | `a2c0b6afd002455267745d3da4d21bd87943da8a` | `64d37f9a4d39195930959c53c926a4184877355a` | 19/19 SUCCESS |
| R9 — browser trust + bounded terminal | #78 | `fdf2bd77ac3178ee973d10c5429b1b2d8b7a5051` | `15a4632f915dd1e1bde19425e313b52ada27166f` | 19/19 SUCCESS |
| R10 — fixed interactive process | #79 | `0d9e7c7f2abdd7a19dabc611fd1d2c8d01d3d013` | `341a69bf855f48f90cbecfb5c6872c3bf8c28360` | 20/20 SUCCESS |

PR #61 merged at `2026-09-03T05:47:57Z`. Every listed merge was followed by a
GitHub merge read-back and `git fetch origin --prune`; commands exited `0`.
All B/C/D/E merge commits completed all six post-merge workflows. E main
`35191eeaf858041cf5c0767dc1579b67690444ec` was re-read after completion; all six
were terminal SUCCESS, separately from its reviewed PR-head evidence.

## Implemented scope

- Pure recovery/cursor/lease identity fences and browser stale-event rejection.
- Typed Project-scoped Claude/Codex Start/Stop/ticket contracts with exact
  response identity, CSRF/recent-auth, transient tickets and no-store behavior.
- READY Project/AgentType metadata lookup, explicit Start and native exact Stop
  confirmation; stale lookup/action/auth/Runtime observations fail closed.
- README, limitations, acceptance, platform and release documents now agree;
  candidates include four fixed WAW workflow/recovery/readiness/host-gate docs.
- Phase 11 includes metadata/capability/Runtime Secret Store foundations, not a
  product Provider/Secret Manager or production activation capability.

## Verification evidence

- Recovery tests: `pytest -q tests/unit/test_waw_recovery.py tests/unit/test_waw_lease.py tests/unit/test_waw_supervisor.py tests/unit/test_waw_stream_contract.py tests/unit/test_waw_lifecycle.py`: exit `0`, 101 passed.
- API/command tests: `pytest -q tests/integration/test_waw_workspace_api.py tests/unit/test_waw_admission.py tests/unit/test_workspace_api_contract.py tests/unit/test_waw_codex_command.py`: exit `0`, 56 passed.
- Web `typecheck`, `lint`, `format:check`, `build`: exit `0`; `NODE_OPTIONS=--no-experimental-webstorage pnpm test`: exit `0`, 115 passed.
- `ruff check`, `black --check`, Linux-target mypy: exit `0`; 188 application/test Python files and 14 installer files checked in the respective runs.
- `pytest -q tests/unit/test_release_candidate.py`: exit `0`, 22 passed, with an expected duplicate-ZIP fixture warning.
- Full local E2E first passed the 54 existing tests and found four ambiguous new test locators. After correction, all four new desktop/mobile metadata E2E passed; the final complete E2E CI gate passed for PRs #60 and #61.
- Main-agent visual QA viewed actual Chromium at 1280x900 and 390x844 for normal/native Stop/empty/error states: no horizontal overflow, tested controls at least 44px, Cancel/Escape restored Stop focus. Synthetic metadata only; screenshots were not committed. Temporary preview was stopped.
- Independent read-only Architecture/Security/Test reviews found no remaining blocker in the delivered software scope. Visual work was main-agent structured QA, not an independent visual certification.
- Local Python 3.14.7 / Node 26.7.0 / pnpm 11.19.0 differ from CI's supported matrix. The expanded macOS WAW matrix did not pass (Linux socket/provenance requirements); it was not promoted to host evidence. Python tests above used `.venv/bin/python -m pytest`; Linux CI is the authoritative supported matrix.

## Independently verified candidate with packaged WAW docs

- E head: `0c894ff52f49793f599eb33c4b92b8223e6109b3`; source ref kind `pull_request_head`.
- Release Candidate run `33719963292`, artifact ID `9879903829`; terminal SUCCESS.
- Tarball SHA-256: `9b1dcd19452a79ee933a4781da368d70415deb374b2a6bd46353501b0c23eb03`.
- Manifest SHA-256: `20d460d8e1a4aee9c05149289d474fcbf2ed9d20904acd685eccb154d60ed354`.
- SBOM SHA-256: `4405cf4f6c8510da3cfacf346a0231893ac8133c94bc5cda3200da3068c676d4`.
- `scripts/check-release-artifact.py` with exact source/ref: exit `0`, 81 archive members, 2757 nested wheel members, 27510853 bytes, no source maps/canaries; all four required WAW docs present. Download and read-only validation only, no install/execution.
- Earlier merged implementation artifact and complete scope are recorded in `../WAW_SOFTWARE_READINESS.md`. Artifact integrity is not publisher authenticity; the candidate is unsigned.

## Current action after Owner clarification

Owner explicitly clarified that development continues on this Mac. The missing
Linux host is a gate for actual activation/qualification, not a blanket block
on software implementation. The prior blocked status has been superseded for
Mac development; A–E remain historical delivered increments.

PR #63 delivered shared Claude/Codex supervisor/stream integration.
PR #64 delivered the concrete lifecycle executor, read-only process probe,
two-phase attachment boundary and failed-start cleanup/restart fencing. PR #65 delivered
fixed Noise NX Python/WebCrypto cores and their interoperability checks; application
encoding remains a separate pending decision.
Real Runtime/PTY/Noise/WebSocket deployment and production readiness are not
claimed. Next scope is in `NEXT_ACTION.md`.

Live preflight from `dfc788a29623de5b5a9c3230855af1ee7aed2953`: clean tree,
HEAD/main/origin/main/merge-base equal, six exact-main workflows SUCCESS, only
historical Draft PR #42 open. Git fetch/GitHub reads exited 0.

## F1.1 merged evidence

- Shared concrete Claude/Codex command union, full supervisor binding checks,
  command revalidation and terminal stream cleanup/replay fences implemented.
- `.venv/bin/python -m pytest -q tests/unit/test_waw_command.py tests/unit/test_waw_codex_command.py tests/unit/test_waw_supervisor.py tests/unit/test_waw_stream_contract.py tests/unit/test_waw_transport.py tests/unit/test_waw_lifecycle.py tests/integration/test_waw_workspace_api.py`: exit 0, 135 passed.
- `ruff check apps packages tests migrations`, `black --check ...` and
  `mypy --platform linux apps/api apps/worker apps/cli packages tests`: exit 0;
  mypy checked 189 source files.
- Independent read-only review: PASS for this increment, including positive
  cleanup proof, rejection of post-close replay and explicit unsupported real
  Codex tmux handling. Targeted reviewer tests passed (55).
- No frontend behavior, CLI argv, real host, credential or production activation
  changed. Mac development evidence is not Linux-host qualification.

## F1.2 merged Runtime composition

- Concrete `WAWSupervisorExecutor` shares exact supervisors between lifecycle
  dispatch and admitted stream bridges; factories are trusted Runtime inputs.
- Status/reconcile use a separate exact read-only probe. They do not reconnect
  a PTY, grant a writer or clear uncertain input.
- Failed readiness keeps the exact cleanup target. Durable generation
  reservation precedes process effects; unknown restart state stays quarantined
  until the existing host evidence path acknowledges cleanup.
- PR #63 merged at `2026-09-03T06:43:01Z`; GitHub merge read-back and fetch
  both exited 0. F1.2 validation/review and subsequent PR #64 CI/merge are complete.

F1.2 final local validation before PR CI:

- `.venv/bin/python -m pytest -q tests/unit/test_waw_command.py tests/unit/test_waw_codex_command.py tests/unit/test_waw_supervisor.py tests/unit/test_waw_stream_contract.py tests/unit/test_waw_transport.py tests/unit/test_waw_lifecycle.py tests/unit/test_waw_bootstrap.py tests/unit/test_waw_runtime_executor.py tests/integration/test_waw_workspace_api.py`: exit 0, 187 passed.
- `ruff check apps packages tests migrations`, `black --check apps/api apps/worker apps/cli packages tests migrations`, `mypy --platform linux apps/api apps/worker apps/cli packages tests`: exit 0; 199 formatted files and 191 typed files.
- `scripts/check-doc-links.py`: exit 0, 156 relative links; `git diff --check`: exit 0.
- Independent read-only review PASS; reviewer ran 127 tests before the final
  two binding cancellation/path-drift regressions. Final executor test file:
  14 passed, including those regressions. All transports/processes are synthetic.
- Six exact-main workflows for `90df8b9adfe3c03fc089634c18214a4fb6fcfe9e`
  completed successfully; this is separate from PR #63's reviewed-head CI.


## F1.3 merged fixed Noise core

- PR #64 merge read-back: `624b34b656dbf239dbc56fa79d216db7d17a349b`,
  merged at `2026-09-03T07:09:03Z`; GitHub merge/fetch exited 0. Final independent
  composition review passed with 129 tests. A final pre-existing composition
  regression was subsequently added locally (15 executor tests); it is tracked
  with the next software increment rather than attributed to the earlier SHA.
- The new Python and WebCrypto modules implement only fixed Noise revision-34 NX
  and split CipherStates. Existing cryptography 50.0.0 and native WebCrypto are
  used; no dependency, real-key file loader, socket or product activation added.
- Shared Noise-C public vector has pinned commit, source/fixture SHA-256 and MIT
  notice. It contains public test key material only.
- Handwritten state-machine independent security review: PASS after fixing
  concurrent destroy/late-result, malformed-input and key-reference handling.
  Reviewer ran 14 Python core tests and the real Python/Node interop check.
  Golden vectors and cross-language positives were reviewed separately from
  concurrency/failure regressions.
- `WAW_ENCRYPTED_STREAM_DECISION.md` provides the concrete proposed application
  bytes absent from the historical architecture; Owner confirmation requested.
  Fixed core implementation continues, while those application bytes remain
  unimplemented/unapproved. See `../WAW_NOISE_CORE.md` for exact scope.


F1.3 final local validation before PR CI:

- `AGENTBOX_NOISE_TEST_PYTHON="$PWD/.venv/bin/python" node scripts/check-noise-interop.mjs`: exit 0; both roles, exact independent handshake/hash/four transport vectors, nonempty AD, bidirectional transport and tamper/closed-state fence.
- `.venv/bin/python -m pytest -q tests/unit/test_noise_nx.py tests/unit/test_waw_runtime_executor.py tests/unit/test_waw_noise_contract.py`: exit 0, 54 passed (14 new core, 15 executor, 25 existing metadata contract).
- Web Vitest: exit 0, 129 passed; new core tests include paused AES/DH destroy, constructor digest destroy, malformed inputs, maximum boundaries, prologue mismatch and low-order peer rejection. Node WebCrypto evidence, not native-browser certification.
- Web Prettier, ESLint, typecheck and production build: exit 0. No visible UI or admission route changed, so a new visual check is not applicable.
- Ruff, Black, Linux-target mypy: exit 0; 202 formatted files, 194 typed files. Documentation link check: exit 0, 164 relative links. `git diff --check`: exit 0.
- Core review, local tests and all 19 PR #65 exact-head CI checks completed successfully. Application bytes, pins, encrypted relay, real CLI/PTY/host and production readiness remain unclaimed.


## Delivery read-back and next decision

PR #65 merged at `2026-09-03T07:40:44Z`; GitHub merge, merge read-back,
`git fetch origin --prune`, local main fast-forward and delivery-branch creation
all exited 0. F1.1/F1.2/F1.3 have completed applicable software tests, independent
reviews and exact-head CI/merge. This is not completion of the interactive
terminal product or F2 host qualification.

The next application-profile implementation is **未开始** pending the complete
supplemental decision in `WAW_ENCRYPTED_STREAM_DECISION.md`. The earlier three-rule
proposal has been expanded after identifying additional protocol conflicts;
Owner acceptance of the complete proposal has been requested and not received at
this snapshot. That is an architecture clarification under GOVERNANCE, not a Linux
host prerequisite for ordinary Mac development. After approval, continue the
application crypto, ciphertext-only relay, staged admission, browser controls
and remaining CLI/host acceptance in the existing plan.

## Native browser follow-up in the delivery PR

- Added `apps/web/e2e/noise-core.spec.ts`, reusing the actual core and pinned
  vector in native browser WebCrypto. No duplicated crypto implementation or
  product route/UI activation. Trace/video/screenshots disabled.
- Local engine: Chromium `151.0.7922.34`, desktop/mobile profiles. Both crypto
  tests passed, including the exact six messages/hash, nonextractable private
  keys, bidirectional AD and original-counter tamper/retry rejection.
- `node scripts/run-e2e.mjs`: exit 1, 56 passed and 4 existing 5-second
  authentication waits timed out (three Dashboard waits, one credentials alert).
  This is not recorded as a full local E2E pass. The new native crypto cases both
  passed in that run; root cause of local timing remains unproven. Linux CI must
  pass the complete updated suite before merge.
- Native test Prettier, ESLint and TypeScript checks passed. The worker's static
  preview on port 4173 was stopped; the isolated harness cleaned its own API,
  preview and temporary data after the run.
- The application byte proposal also passed independent read-only review as a
  coherent clarification. Its status remains PROPOSED pending Owner acceptance.


## Current reassessment

Owner requested a fresh remaining-plan evaluation, a persistent goal and
model-routed multi-agent work: complex sol, ordinary terra. See REMAINING_PLAN.
Sol confirmed AUTH-CAPACITY-CANCEL with an in-memory barrier reproduction:
configured limit 1, cancelled caller, peak actual workers 2. R0's fix and
deterministic unit/API verification are merged; this is not claimed as the cause
of old Mac E2E timeouts. Terra implemented independently specified opaque AWCE framing.
Sol also found additional full wire/admission/trust conflicts beyond the three
proposed bytes; those are consolidated in the new plan instead of silently
promoting the synthetic bridge or metadata state machine to production.


R0 local implementation evidence:

- `BoundedLoginExecutor` keeps shared login/reauthentication capacity until the
  underlying executor Future finishes, independent of caller cancellation. A
  non-throwing completion signal prevents Python 3.14 shield late-error logs;
  original exceptions still reach active callers and ContextVars propagate.
- `.venv/bin/python -m pytest -q tests/unit/test_auth_executor.py tests/integration/test_auth_api.py`: exit 0, 45 passed (14 new deterministic executor cases plus 31 existing auth API tests).
- Scoped Ruff, Black, Linux-target mypy and whitespace checks: exit 0.
- Independent sol review: PASS for this bounded fix; 14 executor cases rerun as
  part of its 48-case Python review with the separate opaque AWCE work.
- No password/Session/CSRF policy, limiter budget, database locking or E2E timeout
  was changed. The previous four Mac E2E authentication timeouts are not claimed
  resolved by this fix. PR #67 completed all 19 exact-head checks and merged at
  `2026-09-03T09:26:56Z`; GitHub read-back, fetch and main fast-forward exited 0.

## R1 framing and R3 proposal evidence

- R1 implements strict Python/Web opaque AWCE v1 framing and a shared header
  builder usable before encryption. Scope, field offsets and evidence are in
  [WAW_AWCE_FRAMING](../WAW_AWCE_FRAMING.md). No channel crypto or socket is activated.
- Python AWCE tests: exit 0, 44 passed. Web AWCE tests: exit 0, 38 passed.
  Bidirectional Python/TypeScript interop: exit 0. Scoped formatting/lint/type
  checks passed; independent sol read-only codec/header review: PASS.
- The complete R3 supplement freezes proposed key schemas/context derivation,
  Runtime/browser confirmation responsibility, ACK hop mapping, API ciphertext
  drop handling, effective limits and signed-pin compatibility. Independent sol
  review passed; three public Ed25519 fixtures and bootstrap digest were verified.
  It remains **PROPOSED**, not Owner acceptance or implemented application behavior.
- R1 merged at `2026-09-03T10:05:01Z` after 19/19 exact-head CI; read-back,
  fetch and main fast-forward exited 0. R2 diagnostics and R10 are separate increments.
- PR #66's Linux E2E run `33731800570`: exit 0, all 60 tests passed in 42.3s.
  Its six post-main workflows also completed SUCCESS. This does not erase the
  earlier four local timeouts or prove a local root cause.

## R10.1 executable provenance evidence

- New trusted Runtime inventory and descriptor-held executable verifier implement
  closed kind selection, root-owned no-follow ancestry, regular native ELF/file
  checks, bounded exact hash, path/descriptor revalidation and synchronized
  lifetime/cleanup. No execution or public filesystem action exists.
- `.venv/bin/python -m pytest -q tests/unit/test_waw_executable.py`: exit 0,
  80 passed / 1 native Linux skip. Scoped Ruff/Black/Linux-target mypy: exit 0.
- Independent sol read-only review: PASS, including additional syscall-failure
  and close/reuse injection. Mac positive stat/platform fixtures are synthetic;
  actual FD/read/rename/close work is exercised. No Linux-host readiness claimed.
- See [WAW_EXECUTABLE_PROVENANCE](../WAW_EXECUTABLE_PROVENANCE.md) for the API and
  [WAW_INTERACTIVE_PROFILE_ASSESSMENT](../WAW_INTERACTIVE_PROFILE_ASSESSMENT.md)
  for remaining launch/environment/state/retention gaps. R10.1 merged at
  `2026-09-03T10:15:12Z` with 19/19 exact-head CI and read-back; full R10 stays in progress. Browser parser foundation is independent R9 work.
- R2's review found raw exception logging, missing metrics accepted as PASS and
  an ambiguous 5-second flag. Fixes passed 21 dedicated regression cases and a
  fresh 4/4 isolated Chromium diagnostic; independent sol re-review passed with
  all 21 regression cases executed. R2 subsequently merged after 19/19
  exact-head CI and read-back.
  The historic four local auth timeouts remain unproven, not marked fixed.

## R2 diagnostic delivery evidence

- Added closed `--auth-timing` mode to the existing isolated harness, separate
  diagnostic Playwright configuration/spec and test-only numeric API wrapper.
  Normal default E2E selection and production auth/database policy are unchanged.
- Repaired three independent review findings: raw exception logs, missing metrics
  accepted as PASS and a misleading total-visibility flag. Required sample
  completeness, fixed numeric failure metadata and separate per-assertion/total
  elapsed flags are verified. See [AUTH_TIMING_DIAGNOSTIC](../AUTH_TIMING_DIAGNOSTIC.md).
- Worker and independent sol reviewer each ran 21 dedicated regressions, exit 0,
  zero skipped, including real Uvicorn/child-process and transpiled-spec negatives.
  E2E CI runs them after web dependency installation so these negatives cannot
  silently skip due to a Python-only job lacking TypeScript.
- Repaired isolated Chromium diagnostic: exit 0, 4/4 in 6.5s, observed visibility
  approximately 78–456 ms. Root default `node scripts/run-e2e.mjs`: exit 0,
  60 passed in 37.2s with API/preview cleanup. Historical timeout cause remains
  unknown; current passing samples do not establish a latency fix.
- Scoped lint/format/type/syntax checks and independent sol re-review passed.
  R2 merged at `2026-09-03T10:23:56Z` with 19/19 exact-head CI and read-back.
  CI E2E job `100611172739` executed all 21 regressions (3.67s) and the complete
  60-test browser suite (40.0s); no diagnostic case was skipped. R9.1 remains
  a separate increment; no browser terminal/controller has been enabled.
- PR #69 Python 3.13 CI job `100608598342`: 1864 passed / 1 skipped / 5 warnings
  in 171.77s. This is full software CI, not real CLI/host qualification.

## R9.1 tokenizer foundation evidence

- Added pure incremental UTF-8/VT tokenizer with typed output tokens, the closed
  character/control allowlist, frame/task/sequence/raw-line limits and explicit
  reset/destroy. No renderer, browser response, DOM, logging or persistence exists.
- Independent sol review found line overflow masking a simultaneous frame-control
  limit and incomplete ESC/CSI state exposing a denied C1 sequence body. Both
  were fixed; the same-root ESC re-entry case was fixed with the same budget rules.
  Output suppression no longer bypasses parsing/counters, and introducer changes
  preserve the earliest deadline and cumulative byte count.
- Worker and independent reviewer each ran 113 scoped Vitest tests, exit 0.
  The reviewer additionally ran 133 independent negatives against actual
  transpiled source, all passed. Independent sol re-review: PASS.
- Scoped ESLint, Prettier, TypeScript and whitespace checks passed. No visible
  UI change, so visual QA is not applicable. See
  [WAW_BROWSER_TOKENIZER](../WAW_BROWSER_TOKENIZER.md) for API and integration limits.
- R9.1 merged at `2026-09-03T10:32:17Z` after 19/19 exact-head CI and read-back.
  Frontend CI job `100613672473` ran 280 tests in 13 files, all passed, and both
  Noise NX / AWCE interoperability checks passed. Full R9 remains incomplete: renderer/controller,
  trust/crypto/admission, attachment scheduler and exact detach are not connected.
  Logical-line deadline duration and post-limit controller recovery still need
  explicit contract resolution; this core does not invent them.

## Historical checkpoint before software decision delegation

The current reassessment delivered five reviewed software increments: R0, R1,
R2, R10.1 and R9.1. Each has an observed merged PR and 19/19 successful exact-head
checks. Each stage updated GitHub and its scope/verification/plan documents.
The complete terminal product and the persistent overall goal are not complete.

The next implementation is R4/R5 after explicit acceptance of the reviewed
[complete protocol supplement](WAW_ENCRYPTED_STREAM_DECISION.md). Acceptance has
been requested but not received; its status remains PROPOSED. This is the
architecture Owner gate in GOVERNANCE, not an extra routine PR approval or a
requirement to move development off this Mac. No real key, Provider Secret,
Runtime HOME, CLI login, host activation or production release was performed.

Additional remaining decisions/evidence are tracked explicitly: interactive
AgentType launch/state/retention/official login/Project Trust profile; the
independent browser trust provider; logical-line deadline and post-limit
controller recovery; complete stream/relay/terminal integration; then authorized
real-host/CLI/isolation/restart qualification. Historical local authentication
timeouts were not reproduced, so their root cause remains unknown.

Independent terra documentation review found one stale R2 merge sentence and
missing R9/R10 decision dependencies in the plan's acceptance cells. Those are
corrected in this documentation checkpoint. Existing historical evidence and
PROPOSED architecture status are preserved.

## R3/R4 delegated implementation evidence

- Complete R3 supplement accepted by the Coding Agent under the Owner's explicit
  software decision delegation. GOVERNANCE/NEXT_ACTION/plan record that the old
  software approval blocker is resolved; real target/key/production scope and
  evidence remain separate.
- R4 implements exact context/prologue, four key frames, independent pin checks,
  confirmation n=0, AWCE n>=1/AAD/size/cursor binding and permanent failure/close
  fences. See [WAW_APPLICATION_CRYPTO](../WAW_APPLICATION_CRYPTO.md).
- Root Python context/profile + Noise/AWCE: exit 0, 560 passed. New Web suites:
  exit 0, 148 passed. Independent primitive reference and Python/WebCrypto
  bidirectional full-profile interop: exit 0, exact complete vector/bounds/fences.
- Independent sol review: PASS after fixing Python close publication and final
  readiness publication races. Both original P1 reproductions were rerun and
  rejected correctly; previously verified Web/metadata/vector evidence retained.
- Root isolated full E2E: exit 0, 62 passed in 45.3s, including new native
  Chromium desktop/mobile application crypto tests. Earlier attempt stopped at
  a temporary in-progress R5 test compile error, not a browser test failure.
- R3/R4 merged at `2026-09-03T11:54:23Z` after 19/19 exact-head checks;
  merge read-back/fetch/main fast-forward exited 0. R5 repaired hostile numeric exponent,
  failure-state/order, paired-source and Python sequence synchronization findings;
  independent R5 review passed with 276 Python / 274 Web cases. Its software
  delivery remains separate; no product admission is claimed.

## R5 full wire evidence

- All 27 types / 50 direction profiles, strict exact scalar/JSON/binary codecs,
  four-leg observed ordering, byte-preserving key/opaque relay and bounded FIFO
  source witnesses are implemented. Python state changes use RLock; no grant,
  decryption, ACK lifecycle or actual network ownership is implied.
- Independent sol review closed extreme-number exception escape, early/regressing
  STATE, premature browser failure, unsourced/altered relay and concurrent hop
  acceptance findings. See [WAW_WIRE_CONTRACT](../WAW_WIRE_CONTRACT.md).
- Python 279 / Web 274 cases passed; independent schema/negative/boundary review
  passed. Python/Web interop covers 50 controlled-clock structural profiles and
  four actual-clock probes, preserving raw key JSON and immutable AWCE bytes.
- Actual-clock combined R6/API/ticket/wire tests initially failed under parser GC
  or cold timestamp work. Moving the number-token type to module scope and using
  direct strict calendar validation resolved both causes without changing GC or
  the 5 ms budget. Final combined gate: exit 0, 496 passed.
- Independent fresh-process measurements: 6/6 first ADMITTED decodes passed,
  0.594–1.141 ms CPU; 5,000 mixed decodes had zero failures, P95 0.185 ms,
  maximum 1.430 ms. Injected >6 ms CPU work remains rejected. These are local
  measurements, not universal latency guarantees.
- R5 merged at `2026-09-03T13:03:37Z` after 19/19 exact-head CI; exact
  merge/fetch/main read-back completed. R6 passed independent review after four fixes;
  30s stale/60s grace and complete active lifecycle remain R7/R8 dependencies.

## R6 staged admission evidence

- Real staged ticket authority and coordinator implemented over closed ports,
  including exact burn/reserve/advance, required Audit, bounded quarantine,
  commit retry, reader retirement, atomic publication and positive cleanup.
  See [WAW_STAGED_ADMISSION](../WAW_STAGED_ADMISSION.md).
- Independent sol review PASS after four fixes: known mismatched bearer burn,
  single-reader handoff, known-cleanup issuance fence and detached failure Audit
  after Runtime cleanup errors. New suites: 135 passed; scoped type/lint/format
  and relevant existing API/ticket regressions passed. The actual-clock combined
  R6/wire suite passed 496 cases after R5 performance repair.
- The 30s stale/60s grace, idle/absolute lifetime, Runtime health, native controls,
  failed-attempt rate limits and real Audit/network adapters remain R7/R8 scope.
  Configured authority expiry is not a standalone live-input authorization proof.
- R6 merged at `2026-09-03T13:33:51Z` after 19/19 exact-head checks; normal
  merge, read-back, fetch and local main fast-forward exited 0. Root final staged/
  coordinator/ticket regression: exit 0, 164 passed; scoped lint/format/type passed.
- R7 Runtime server/lifecycle and R8 native WebSocket/API relay are being
  implemented in parallel; no complete terminal or real-host qualification is
  claimed yet. See [Runtime stream scope](../WAW_RUNTIME_ENCRYPTED_STREAM.md).

## R7/R8 current review checkpoint

- R7 worker completed bounded failure profiles, health/ping checks at each live
  permit, truthful non-exit STATE handling and preserved workspace fault fences.
  Actual UDS regressions also repaired late OUTPUT after detach/exact Stop, with
  socket publication tied to cleanup and the exact Runtime lease invalidator.
- Latest R7 stream/server/supervisor/executor command: exit 0, 160 passed; all
  ten owned files passed scoped lint/format/Linux-target type checks. Final
  independent R7 review found P1 map/supervisor lock inversion during a new Start
  and late old registry.open, plus P2 retaining 2001 logical lines by omitting a
  trailing non-LF line. Both were repaired before merge.
- Independent R7 review ran 11 targeted tests and four actual UDS writability
  delay/cleanup/revoke/health/Stop cases, all exit 0. Its deadlock and line-count
  reproductions also exited 0 and confirmed the defects. These results do not
  establish real-host qualification.
- Repaired R7 matrix: 170 passed; focused lock/state/cancellation set 16 passed;
  PTY set 17 passed. All ten R7 files passed lint/format/Linux-target mypy.
  Independent re-review PASS: 10 deadlock/state tests plus all 17 PTY tests,
  with exact repair hashes matched. R7 final head
  `01c716bd4713ef4a6676b71754a4e065ebce3b82` passed 19/19 exact-head checks
  and merged as `4180f0991af97cba108b6e5a707b7abf58a444d2` at
  `2026-09-03T17:46:25Z`. Fetch/main fast-forward/read-back exited 0; all six
  exact-main workflows subsequently completed SUCCESS.
- R8 repairs cover terminal queue authorization, actual send guards, pending PING
  deadlines and fresh browser-leg correlation IDs. Shared 128 partial slots /
  8 MiB parser accounting and synchronous first-ciphertext-drop fencing are now
  implemented. A shared INPUT ownership ledger now spans native-ready,
  browser-delivery, relay-pending and Runtime-send-inflight without releasing
  capacity at layer transitions. Its expanded matrix passed 604 cases; full
  lint/format and Linux-target mypy over 224 files passed. Independent direct
  replays closed the
  terminal, pending-PING, first-drop and former 65872-byte INPUT findings.
  Final R8 review found and closed a relay P2 and an admission-coordinator P1:
  `authority.fence` and CLOSE-frame encoding failures no longer skip Runtime
  cleanup, detached Audit or local transport/budget/wire closure. Cleanup is
  single-task and cancellation-resistant; first fence errors propagate only
  after cleanup, and authority release still requires exact positive proof.
  Independent re-review PASS: 12 directed cases, 126 admission unit cases and
  69 sandbox-compatible relay cases. Main-agent validation passed 539 R8 Python
  cases, 832 Web cases, 50-profile wire interop, Ruff, Black over 232 files,
  Linux-target mypy over 224 files, Web build and all 62 isolated Chromium E2E
  cases. R8 final head `a2c0b6afd002455267745d3da4d21bd87943da8a`
  passed 19/19 exact-head checks and merged normally as
  `64d37f9a4d39195930959c53c926a4184877355a` at `2026-09-04T04:11:58Z`.
  Fetch/read-back exited 0 and all six post-main workflows completed SUCCESS.
- An optional whole-repository macOS pytest run was stopped at 37% after 1,013
  passed, 184 failed and 2 skipped. The first failures were macOS AF_UNIX path
  length plus Linux/root-owned installer, diagnostics and Secret Store semantics;
  it is neither a pass nor R8 regression evidence. The exact-head Ubuntu matrix
  remains the authoritative full-suite gate.
- The R6 admission-negative integration seam is a separate uncommitted R8 change:
  17 new tests pass; independent review closed both correlation and per-frame
  revocation findings, with 26 focused coordinator/wire tests and direct replay.
- The existing two Sol/high execution/review roles resumed after a model-service
  interruption; unfinished checks were retained as unverified. A separate
  Sol/ultra role is doing only the new R9 read-only plan under the updated working
  agreement, with no execution delegation or file writes from that role.
- The visible version plan is approved. R7 delivered `0.3.0rc2`; the R8 worktree
  is now `0.3.0rc3`, with root/Web metadata and release documents aligned. Version
  consistency, TypeScript, lint and format passed. The R8 isolated browser suite
  passed 62 tests; actual desktop and 390x844 mobile Dashboard views showed
  `0.3.0rc3` / API v1 with no horizontal overflow or overlap. This is local
  preview evidence, not deployment.
- The approved Sol/ultra plans for Start lock order and shared INPUT ownership
  are implemented. R9 trust lifecycle and bounded terminal model implementation
  is active under the accepted browser decision; real provider qualification
  remains separate.

## R9 reviewed candidate and R10 plan

- Public trust lifecycle/provider/Chromium repairs pass 121 Web tests and the
  unchanged PyCA bootstrap/three-signature/nine-mutation vectors. Cumulative
  latest-ACTIVE checkpoints, strict history prefix/floors/tombstones, revocation,
  crash-fail-closed store transitions, exact registration/invalidation and the
  six-second provider request deadline are implemented.
- The bounded terminal passes 185 tokenizer/model/scheduler tests plus two
  offline Unicode generator checks. Fixed UCD 13 rules, cooperative five-
  millisecond work, exact 50 ms fixed-window throttling, 256 KiB/2,000-line
  cross-layer reservations, UTF-8 carry expansion and resumable maintenance are
  covered.
- The managed provider core includes an inert MV3 extension, fixed external/
  Native Messaging/trustd protocols, service-owned Ed25519 state/floor/time
  store, DNS policy, deployment cross-pin builder and Web adapter. Python
  provider/store/native/package tests pass 13 cases; MV3 passes 4. The production
  build emits the exact six-file inventory and passes a real `dist` to public-only
  bundle gate. No CRX, real extension ID/Origin, policy or service is installed.
- Browser locale/controller/Workspace shell passes 41 focused tests. Only
  `navigator.languages[0]` selects the document locale: primary `zh` maps to
  `zh-CN`; every other/missing/malformed value maps to English. Technical values
  remain printable English ASCII with `lang=en`, `dir=ltr`, `translate=no`.
- Root Web tests pass 915 plus 4 extension tests. Desktop/mobile Chromium E2E
  passes 64 cases, including Chinese, English, non-Chinese fallback, exact Stop,
  overflow and 44 px control checks. Build/type/lint/format, Ruff/Black on 264
  files, Linux-target mypy on 253 sources, 37 focused Python tests, 236 doc links
  and the real bundle gate pass locally.
- Main-agent visual inspection used the built rc4 assets with bounded synthetic
  metadata. The 1280x900 English Dashboard visibly shows `0.3.0rc4` / API v1;
  the 390x844 `zh-CN` Workspace shows Chinese lifecycle copy and technical values
  in English. Both measured no horizontal overflow, and no terminal payload was
  captured. This is local preview evidence, not a deployed/host-qualified UI.
- Independent read-only Architecture/Security/Test review reports PASS with no
  remaining P0/P1/P2. PR #78 exact head `fdf2bd77...` completed 19/19 checks,
  then merged normally at `2026-09-04T09:22:07Z`; fetch/read-back observed exact
  merge `15a4632f...` with parents `64d37f9a...` and `fdf2bd77...`.
- All six standard post-main workflows for `15a4632f...` are SUCCESS after the
  Security `frontend-audit` retry recovered from npm advisory API 503/timeouts.
  GitHub's separate dynamic Dependency Graph job remains a historical
  `pip-compile` `.lock` include limitation already present before R9; R10 tracks
  the `.txt` include repair and will require its post-main graph to succeed.
- Sol/ultra produced the complete R10 read-only plan: distinct fixed interactive
  Claude/Codex profile, host manifest v2, version/auth/env records, descriptor/WBR
  codecs, three native helper binaries, Runtime composition and inert installer
  assets. No CLI/HOME/key/host action occurred; implementation is approved after
  R9 delivery.

## R10 delivered fixed interactive process

- Runtime host manifest v2 closes the exact-six executable inventory and exact-two
  Claude/Codex profiles. Seven fixed descriptor roles, the 64-byte WBR protocol,
  three native helpers, pre-birth cgroup placement, tmux/PTY attachment, qualified
  auth probes, local-TTY login and host-wide WAW/legacy conflict coordination are
  implemented without activating a host or handling a real credential.
- Rootless isolation uses held-directory authority, in-namespace `openat2`
  reanchoring, exact metadata/mount-flag comparison, non-recursive binds and a
  two-level user-namespace lifecycle. Exact Stop proves cgroup empty, pane pidfd
  exit, process-group disappearance and identity-bound stale-socket cleanup.
- The bridge exits only after descendants are reaped, the inner PTY reaches EOF,
  output is empty and tmux returns the exact 192-bit random cursor challenge. R11
  must quiesce browser INPUT/WBR resize during this final barrier and retain an
  outer minimum size of eight columns by one row.
- PR #79 implementation head
  `6083e6e1aa118b19b548a9070b7e49558988f7e5` completed all `20/20` exact-head
  checks. Python 3.13 quality ran `3428 passed / 43 skipped`; Linux native ran
  `66 passed` normally and `24 passed` with sanitizers. Web ran `915`, the
  extension ran `6`, Chromium E2E ran `64`, release validation ran `143`, and
  the documentation checker verified `238` relative links.
- Independent Sol review reports PASS with no remaining P0/P1/P2 in the R10
  software scope. CI fake-vendor/native evidence is not a real vendor build,
  installed CRX, account, credential, production binary provenance or host
  qualification; those remain R12 gates.
- Documentation-only head `d5d1838...` exposed one sanitizer scheduling flake in
  the native tail fixture: intentional legacy DSR noise at frame 1900 could be
  echoed by the canonical inner PTY and alter tmux row 1 while the test treated
  the rendered grid as a raw log. The fixture now emits all 2,048 strictly
  ordered/hash-checked frames and its marker/padding before the same complete
  DSR5/eight-position DSR6 overlap noise. Production bridge code and every strict
  tail assertion remain unchanged; a new exact-head CI run is required.
- Final exact head `0d9e7c7f2abdd7a19dabc611fd1d2c8d01d3d013` completed
  all 20 checks, including native normal/sanitizer. PR #79 merged normally as
  `341a69bf855f48f90cbecfb5c6872c3bf8c28360`; exact parent read-back, all six
  post-main workflows and the dynamic Dependency Graph update are SUCCESS.
- Browser locale remains fixed: read only `navigator.languages[0]`; primary
  language `zh` selects `zh-CN`; every other, missing or malformed value selects
  English. Technical identifiers remain English. Full cross-page bilingual
  migration is part of R11/rc9.

## R11/rc6 foundation in progress

- The accepted rc6–rc9 composition contract is recorded in
  `WAW_R11_CONTROLLER_COMPOSITION.md`; PR #80 tracks the active rc6 branch.
- An API-only v2 anchor loader reads the fixed public leaf through a held,
  root-owned non-writable directory chain and revalidates all identities. It does
  not open Runtime-private manifest/HOME/Secret state; 21 boundary tests pass.
- Migration `0008_waw_runtime_epoch_fence` adds nullable canonical decimal TEXT
  `last_runtime_epoch`. One `BEGIN IMMEDIATE` transaction classifies first/same/
  greater epochs, preserves terminal rows and atomically fences every nonterminal
  workspace plus pending Stop operation to reconciliation on Runtime advance.
- Bind attestation is durably classified before coordinator publication. Focused
  binding/session/anchor tests pass 49 cases; the complete migration suite passes
  41. Scoped Ruff, Black and Linux-target mypy pass. Commit `4f27409...` completed
  all 20 exact-head checks in PR #80.
- Both systemd-inherited Runtime listeners now re-`listen` with fixed backlog 64
  before readiness/accept so client `SO_PEERCRED` can bind Runtime rather than the
  socket activator. Re-listen failure closes and poisons the inherited listener;
  four deterministic lifecycle tests pass. Real systemd credentials remain R12.
- Listener lifecycle now uses shared start/close operations, sticky close failure
  and explicit control-socket ownership `RAW → IN_FLIGHT → TRANSFERRED`. Close
  never raw-closes an ownership-unknown socket; accept/start failures, direct
  cancellation and delayed cleanup remain poisoned. Thirteen focused tests pass
  with one Linux-only real-loop skip; independent Sol review reports no P0/P1/P2.
- PR #80 head `6467a09...` passed the 66-case normal native run; sanitizer reached
  23 pass / 1 failure because tmux exposed PTY-dead before its child wait status,
  yielding transient `pane_dead_status` empty. The strict DCS gate now waits on a
  unique test-only `pane-died → wait-for -S` child-status event and then requires
  exact `1:74:` (normal exit 74, no signal). Independent Sol review PASS; a new
  exact-head Linux CI run remained required.
- Head `5b4237e...` proved that DCS gate, then the same PTY-dead/status-publication
  race appeared in the closed-descendant status check. All three `remain-on-exit`
  gates now share one test-only unique `pane-died → wait-for -S` barrier and
  strictly require `1:7:`, `1:74:`, and `1:7:` respectively. Tail order/hash and
  descendant termination-canary assertions remain unchanged; another exact-head
  native normal/sanitizer run was required.
- Head `6916406...` passed native normal/sanitizer. Python 3.11 alone then exposed
  a unit-test observation race: the intentionally failing close worker could
  finish and its done callback could clear `_close_operation` before the test
  captured it. The test now captures the synchronously created operation before
  its first await; sticky failure/direct-cancel assertions remain unchanged.
  Python 3.12/3.13 and the other 19 checks passed. Head `4059474...` then completed
  all 20 exact-head checks, including Python 3.11 and native normal/sanitizer.
- API control bind now publishes one retained `BoundRuntimePeer` only after full
  response/EOF, anchor attestation and durable epoch classification. Every later
  control request and stream connection borrows only a duplicate of that retained
  pidfd with exact peer credentials, owner identity and generation checks.
- Coordinator/client close synchronously fence new bind/request/borrow work;
  candidate publication rechecks the fence. Poison and close are irreversible;
  a retired client can issue only one replacement after a successful terminal
  close. `poll(0)` supports high pidfds, and uncertain writer cleanup poisons.
  Focused regression passes 115 with one Linux-only peer integration skip; full
  Linux-target mypy checks 254 sources. Independent Sol review reports PASS with
  no P0/P1/P2. Linux exact-head CI remains required for this uncommitted slice.
- Runtime-side API authority transfer, redraw and application ownership remain
  active rc6 work. No production WAW path is enabled by this foundation.
