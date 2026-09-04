---
schema_version: 1
verified_at_utc: "2026-09-04T13:22:47Z"
verified_by: "codex-live-reconciliation"
repository: "ForceMind/agentbox"
---

# Current Verified State

## Current authorized implementation

- Live preflight after `git fetch origin --prune`: active R10 branch
  `codex/waw-fixed-interactive-process` has merge-base
  `15a4632f915dd1e1bde19425e313b52ada27166f`, equal to `origin/main` and the
  observed R9 merge. Branch HEAD `e3bc440bcce8b141cb4b7d9e20891282c5f246b0`
  contains the Dependency Graph input repair and R9 read-back documentation.
  Only historical Draft PR #42 is open; no R10 PR or exact-head CI exists yet.
- R9 PR #78 completed 19/19 exact-head checks, normal merge, exact read-back and
  all six standard post-main workflows. The separate historical Dependency Graph
  limitation is addressed on this R10 branch by the `.txt` release input.
- Owner delegated the remaining software goal/plan/architecture and explicitly
  approved managed Chromium extension + Native Messaging + independent `trustd`,
  followed by R8 rc3 → R9/provider rc4 → R10 rc5 → R11 rc6–rc9. R9 is delivered;
  real host/key/provider activation remains R12.
- R10 `0.3.0rc5` implementation and local review are complete in the working
  tree. Commit/push, PR exact-head Linux CI, normal merge and exact read-back are
  still pending, so R10 remains `待验证` rather than delivered.

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

## R10 reviewed local candidate

- Runtime host manifest v2 closes the exact-six executable inventory and exact-two
  Claude/Codex profiles. Descriptor-held launch authority carries seven fixed FD
  roles, and WBR resize/ack uses the fixed 64-byte network-order protocol.
- Three C17 Linux helpers implement pane bootstrap, PTY relay and attach supervision.
  Runtime composition adds one-shot pre-birth cgroup authority, exact tmux/process
  inspection, bounded output/input/resize/detach/reconnect cleanup and exact Stop.
- Vendor auth probes require qualified isolation evidence. Local login/trust uses
  a held foreground TTY, and the host-wide conflict coordinator serializes WAW and
  legacy Claude/Codex starts without making the default legacy-only server active.
- Inert tmux, sandbox, Claude and Codex policy assets are closed by package and
  release inventories. Codex ships the exact-two TOML inputs plus their canonical
  digest bundle; no policy is installed or activated.
- Local focused Runtime/release regression passed `676` tests with `12` explicit
  Linux-only skips; the encrypted Runtime server passed a separate `24` tests
  outside the macOS socket sandbox. Native portable-source gate built all three
  helpers. Ruff passed, Black left `287` files unchanged, Linux-target mypy passed
  `252` sources, and the documentation checker passed `238` relative links.
- With the repository Node option, Web passed `915` tests and the extension passed
  `6`; typecheck, lint, format and production builds passed. A deliberately broad
  macOS run remains invalid host evidence because Linux socket/peer-credential and
  temporary-path assumptions fail on this platform.
- Independent Sol review reports PASS with no P0/P1/P2 after closing constructor-
  time transport ownership and release inventory findings. Linux namespace,
  cgroup, tmux and sanitizer checks remain exact-head CI evidence; real vendor CLI,
  account, CRX installation and host qualification remain R12.
- Browser locale remains document-fixed: only `navigator.languages[0]` is read;
  primary `zh` selects `zh-CN`, while every other, missing or malformed value
  selects English. Technical identifiers stay English. Full cross-page bilingual
  migration remains an R11 deliverable.
- Chromium E2E passes `64` desktop/mobile cases and reads back the actual
  Dashboard `0.3.0rc5` / `API v1` text from the built candidate.
- PR #79 opened at initial exact head `35efb88f412386900a9e4188589f2debca4aa1f1`.
  Its first `repository-boundaries` run correctly rejected the new fixed vendor
  probe adapter because the controlled subprocess allowlist had not named that
  Runtime module. The allowlist now names only `waw_vendor_probe.py` in addition
  to the existing controlled adapters; the local boundary script and shell syntax
  checks pass. A replacement exact head and complete CI result are still pending.
- Replacement head `59a96da9b4e318d6ab28d7ec5385de75e24b963f`
  passes `repository-boundaries`. Its Linux native compiler found one missing
  standard `<signal.h>` declaration for `SIGKILL`; the header is now included.
  This source-level portability fix still awaits a new exact-head Linux run.
- The same replacement head's Python 3.13 matrix passed `3418` tests before one
  new server test tried to create its short Unix-socket directory under macOS-only
  `/private/tmp`. The fixture now uses portable `/tmp`, preserving the short-path
  requirement on both macOS and Linux; the next exact head must re-prove the matrix.
- Latest head `b689ff8b007b2a34478f8d1d06fee4930a70ca1a` compiled the
  helpers, then the native fixture could not bind its fixed control socket because
  CI created `/run/agentbox-waw` as root while only its children belonged to the
  runner. Ephemeral CI provisioning now assigns the exact parent and child runtime
  directories to the runner; no product installer or activation path changes.
- Head `9ddbd71c` progressed into the native integration suite. The first
  bootstrap correctly rejected CI's cgroup marker because the fixture used a
  32-character workspace prefix while the production contract requires the full
  64-character workspace hash; later tmux failures cascaded from that first
  rejected pane. All three CI cgroup fixture references now use the full hash.
- Head `bce0d29c` progressed past that identity check; its first isolated bridge
  then closed before READY. The failure pattern is consistent with Ubuntu 24.04's
  AppArmor restriction on unprivileged user namespaces. The ephemeral CI host explicitly
  disables that runner-only restriction before executing the helper as the
  non-root runner. The setting is not product installation or R12 host evidence.
- Kernel mount-namespace rules also explain the remaining pre-READY exit: mounts
  inherited into a less-privileged user-owned namespace are locked and cannot be
  individually unmounted. `setup_mounts` no longer attempts to detach inherited
  `/proc`; it stacks the new PID-namespace procfs directly over it with the fixed
  `nosuid,nodev,noexec,hidepid=2,subset=pid` restrictions. The regression gate
  forbids reintroducing the invalid detach.
- Because the same EOF persisted, static inspection no longer identifies a safe
  second fix. The next exact head uses bounded integer-only stage diagnostics and
  retains only the first failed pane long enough to read `pane_dead_status`; it
  does not change READY/WBR, write terminal payload, or relax isolation assertions.
  These diagnostic branches will be removed after the failing syscall stage is known.
- The first diagnostic head reached neither launch nor helper execution because
  tmux 3.4 requires a window-qualified target for the window option. The test now
  uses exact target `=session:0`; the failed diagnostic run is not native evidence.
- Window-qualified diagnostic head `8269d85c` reached its failure branch, but
  `_kill_tmux_server` raised before the intended stage report and masked the
  integer status. Production-candidate head `ae412c4c` reproduced the original
  pre-READY EOF. The bounded diagnostic is restored without that masking cleanup;
  no additional isolation behavior changes until the exact stage is observed.
- Head `110edb2c` showed the pane was still not retained because
  `remain-on-exit` requires pane scope. The diagnostic now uses exact pane target
  `=session:0.0` and `list-panes`; this remains diagnostics-only and carries no
  payload or protocol changes.
- Pane-scoped head `ef51061c` finally reported exact status
  `1:65:agentbox-waw-pane-bootstrap`, proving the failure precedes namespace
  creation. The bootstrap's previously combined predicate is split into fixed
  integer stages for parent/tmux/control/launch/identity/cgroup/FD-role checks;
  every predicate remains fail closed and unchanged.
- Bootstrap-stage head `577a178c` passed every pre-isolation check and reported
  exit `95`, the first project descriptor bind-remount. The remount now reads the
  source mount flags from the held descriptor and preserves locked `RDONLY` and
  `NOEXEC` while always adding `NOSUID|NODEV`; it no longer implicitly attempts
  to clear a more-privileged mount's locked restrictions.
- Sol review identified the remaining locked atime modes and recursive-bind risk.
  The remount also preserves source `NOATIME`, `NODIRATIME` and `RELATIME`, and
  the initial descriptor bind is non-recursive so unreviewed nested mounts are
  not imported. `NOSUID|NODEV` remain mandatory additions.
- Head `b2523cc` then reported bootstrap stage `87`, the exact cgroup marker,
  even though the preceding runner had passed it. Before changing production
  matching, the diagnostic reads pytest, tmux-server and pane cgroup records from
  `/proc` before launch to distinguish inheritance from runner relocation or path
  format differences.
- Head `0c4c593` supplied the exact records: pytest and tmux server remained in
  the full-hash workload, while systemd-enabled Ubuntu tmux moved the pane to an
  `app-tmux.slice/tmux-spawn-*.scope`. Production already starts tmux with a
  five-key fixed environment that contains no DBus/XDG systemd channel. Native
  tests now use that same environment for every new server and keep the positive
  pane cgroup assertion; the production cgroup predicate is not weakened.
- With the pane held in the workload, head `67ca4b2` again reached project
  bind-remount stage `95`. The classic remount is replaced by Linux 5.12+
  `mount_setattr`: it only sets `NOSUID|NODEV` and policy `RDONLY`, never clears
  inherited mount attributes, and fails closed when the syscall is unavailable.
- Head `8bf1ef2` remained within the project bind stage. The bounded diagnostic
  now distinguishes descriptor/path construction, initial `MS_BIND`,
  `mount_setattr`, and unsupported UAPI with non-overlapping integer statuses.
- Split head `75d8136` reported `112`, the initial project `MS_BIND`, confirming
  the builder lacked effective `CAP_SYS_ADMIN`. After UID/GID maps are written,
  existing credentials already appear as inner `1000`; redundant `setresuid` and
  `setresgid` cleared the new namespace capabilities. They are replaced by exact
  UID/GID assertions. Mount setup runs with the creation-time capabilities, and
  the subsequent nonzero-UID exec clears them before the bridge/vendor workload.
- Independent Sol review passed this lifecycle. The fake vendor now reads its
  own `/proc/self/status` and requires both `CapPrm` and `CapEff` to be zero,
  explicitly proving no namespace setup capability crosses the exec boundary.
- Head `0889a40` still reported initial bind code `112`; the rejected operation
  is the classic `/proc/self/fd/N` source path on the runner overlay, not the
  attribute step. Directory mounting now uses descriptor-native `open_tree`,
  detached `mount_setattr`, and `move_mount` without source path re-resolution,
  nested mounts, or a temporarily less-restricted attached mount.
- Descriptor-native clone head `3c783a9` reported `111`, confirming the builder
  still lacked effective setup capability. The final lifecycle uses
  `PR_SET_KEEPCAPS`, switches to inner UID/GID 1000, narrows capset v3 to the
  new user namespace's sole `CAP_SYS_ADMIN`, and exact-reads it back. Before
  Landlock/seccomp/bridge exec it sets NNP, disables KEEPCAPS, clears all three
  capability sets and ambient capabilities, and exact-reads zero back.
- Head `40f2816` no longer returned a staged exit status; tmux reported a dead
  pane with an empty numeric status, indicating signal termination. The bounded
  formatter now includes `pane_dead_signal` to distinguish seccomp, parent-death
  and memory faults before any further implementation change.
- The apparent blank signal field was later read as status `111`, so no signal
  fault occurred: U1 still could not clone the host mount while mapped as
  nonzero UID 1000. The implementation now uses two rootless user namespaces:
  U1 maps `0` to the outer Runtime UID/GID for fixed namespace/mount setup; U2
  maps final `1000` to U1's `0`, clears all capabilities with exact read-back,
  and runs Landlock/seccomp/bridge. U1 retains a pre-overmount `/proc` FD only
  for the fixed second mapping, then clears capabilities, applies seccomp and
  only waits/reaps. Root Helper remains outside the terminal path.
- Independent Sol review found and closed a publication-order issue: U1 now
  completes NNP, exact capability clearing and seccomp before sending the byte
  that releases U2, so U2 cannot reach READY if the trusted waiter lockdown
  fails. U1 also resets PDEATHSIG after its map and closes every inherited FD
  before entering the wait/reap-only loop.
- Exact head `0d5d1f5` still returned project status `111`: U1's namespace root
  could not use `open_tree(OPEN_TREE_CLONE)` on the inherited runner mount. The
  setup now uses the standard non-recursive rootless `MS_BIND` operation inside
  U1, followed by the same one-way `mount_setattr` additions. U2 stays blocked
  until all mounts and the U1 waiter lockdown succeed, so this trusted setup
  change does not expose a less-restricted mount to the vendor workload.
- Independent Sol review also moved U1 FD lockdown into that publication gate:
  after NNP/capability/seccomp lockdown, U1 closes the saved `/proc` and every
  inherited descriptor except the release pipe before sending the release byte.
  Any close-range failure keeps U2 blocked and forces its termination.
- Exact head `023febf` passed the portable native gate but returned project bind
  status `112` on the real Ubuntu runner; the other native failures were expected
  diagnostic exit-code differences or cascades from the intentionally retained
  first pane. A bounded errno map now distinguishes `EPERM`, `EACCES`, path-shape
  failures, and other initial bind failures without emitting host data.
- Exact head `2fd59f8` returned `116`, confirming `EINVAL`: the SCM_RIGHTS held
  FD still referenced the pre-`CLONE_NEWNS` mount, which Linux refuses to copy
  into the new namespace. The held FD remains authoritative, while its
  kernel-generated absolute target is now used only as an `openat2` lookup hint
  inside the new namespace. The reanchored FD must exact-match device, inode,
  type/mode, visible owner and filesystem mount flags before bind; replacement,
  changed visible metadata, deleted/truncated hint, or missing UAPI fails closed.
  R12 must reject idmapped sources and audit mount topology plus per-mount LSM
  and `nosymfollow` metadata that `fstatvfs` cannot attest. U2 remains behind the
  existing mount/lockdown/FD publication gate.
- Exact head `8705712` compiled with strict Linux warnings, passed the portable
  native gate, and for the first time completed workspace READY through
  reanchor, all four binds/attributes, U1/U2 lockdown, Landlock/seccomp and
  vendor exec. The remaining primary failure is isolated to attach before attach
  READY. A bounded attach-stage status replaces the generic `71` only for this
  diagnosis; retained-pane cascades remain non-primary.
- Exact head `5d1b1a2` reports attach status `65`, before fork/exec/query. The
  bounded entry diagnostics now separate parent-death binding, role-FD
  validation, three-stream TTY validation, FD lockdown, resource limits and
  NNP; workspace READY remains proven at this head.
- Exact head `b62f1bd` reports descriptor-validation status `66`. The next
  bounded code identifies the exact tmux executable, socket directory, config,
  or READY descriptor without exposing descriptor values or host paths.
- Exact head `5f994f9` identifies the tmux executable role (`83`). The Linux
  test pre-exec mapper could overwrite a later source FD while assigning the
  low fixed destinations. It now duplicates every source above FD 64 first,
  then maps the collision-free copies to the exact roles and closes them.
- Head `a757799` still returned `83`, proving CPython's `pass_fds` keep-set also
  closed fixed destinations created in `preexec_fn`. A dedicated test exec shim
  is now the sole mapper: `Popen(pass_fds=exact sources)` starts the shim without
  changing parent CLOEXEC state or inheriting unrelated FDs; the shim performs
  collision-free high-FD copies, fixed-role `dup2`, optional `setsid`, and direct
  `execv`. Each native helper still closes the original source FDs immediately
  with its existing allowlist.
- Exact head `6165f9a` passed workspace READY, attach READY, PTY I/O, resize and
  session exit. The first failure moved to the empty tmux server retaining its
  socket. The inert config now pins server option `exit-empty=on` instead of
  relying on a distro/default value; the native gate reads it back exactly.
- The session and server cleanup checks previously shared one ten-second
  deadline, so a valid late session exit left no observation budget for the
  server/socket transition. Each independently bounded transition now receives
  its own ten-second deadline; the server still must disappear without an
  explicit test-side kill.
- Source inspection and Linux evidence established that tmux 3.2a exits its
  server loop without unlinking a custom `-S` pathname. `exit-empty=on` remains
  the server-process policy, while Runtime Stop now waits for exact cgroup
  `populated=0`, revalidates the recorded socket device/inode/type/Runtime UID
  through its held directory FD, performs fixed-basename `unlinkat`, and reads
  back `ENOENT`. Identity drift or any unlink/read-back error remains
  `WAW_STOP_UNCONFIRMED`; Root Helper is not involved.
- Independent Sol review found that failed Start had the same stale-path risk
  but no binding through which a caller could invoke Stop. Runtime now records
  the socket identity before pane acceptance. After any later Start failure it
  exhausts process/cgroup cleanup, removes only that recorded identity once
  exact cgroup empty is proven, and still closes cgroup/control/WBR resources if
  cleanup itself fails. An unrecorded remaining pathname yields
  `RECONCILIATION_REQUIRED` and is never blindly deleted.
- A second Sol review found the pane/bootstrap PID comes from `SO_PEERCRED` and
  is a tmux-server child, so Runtime cannot legally obtain its status with
  `waitid(P_PIDFD)`. Pane probe/failed-Start/Stop now use poll-only pidfd exit
  observation and close the pidfd without reaping; `EXITED` permits an explicit
  unknown `exit_code`. Direct launcher and attach-supervisor children retain
  poll plus `waitid` reaping. Exact pane exit status would require a future
  authenticated exit frame and is not synthesized.
- R12 must prove the tmux socket directory has one Runtime authority writer and
  that the per-workspace conflict coordinator serializes basename lifecycle.
  These conditions close the userspace `stat`/`unlinkat` interval; any observed
  identity drift remains reconciliation-required.
- Final Sol cleanup review separated every failed-Start stage. A pane cleanup
  failure cannot skip direct tmux-child signaling; cgroup cleanup always runs;
  the direct child is reaped after cgroup cleanup with its pidfd closed in a
  `finally`; socket cleanup and all local control/WBR handles are still attempted.
  The first cleanup error is retained and chained from the original Start error.
- Exact head `1662f00` reached `53 passed` in the Linux native job. Its nine
  failures were the intentionally staged `65/71` diagnostics, one legacy
  auto-unlink assertion, the resulting launch-listener cascade, and a unit
  fixture whose replacement socket could reuse the same inode. The production
  candidate now restores public `65/71` errors, removes retained-pane/status
  diagnostics, routes detach/reconnect cleanup through identity-bound stale
  socket removal, and uses a deterministic mismatched-identity negative test.
- Production-shaped head `8221d52` reached `60 passed` with two failures. The
  remaining integration failure came from the test cleanup helper invoking
  tmux `kill-server` when no socket/server existed: tmux 3.2a started and exited
  a server for that command, leaving an unrecorded stale pathname that production
  Start correctly rejected. Cleanup now returns immediately when no recorded
  socket exists, and the session fixture uses that same identity-bound helper.
- Exact head `1300696` reached `59 passed`; its first failure received the final
  `TAIL-END` but counted only 94,775 of 100,000 repeated bytes on a live tmux
  attach client. That client is a coalesced screen-update view, not a raw pane
  journal. The replacement regression uses a test-only pre-creation tmux config
  with history 4096 and `remain-on-exit=on`, emits 2,048 numbered deterministic
  short-line frames (>64 KiB), waits for exact pane exit `7`, captures complete
  server history, and verifies sequence, payload, byte bound and SHA-256. The
  packaged config remains independently pinned to history 25/remain-off.
- The same head reached the standalone launcher fake but returned its diagnostic
  `90`: that fixture only accepted attach-session argv while the launcher test
  correctly emits fixed new-session argv. The fake now validates both exact
  shapes while retaining the attach-only TTY/NNP checks and the exact post-exec
  FD inventory.
- The launcher test keeps its bootstrap executable only in the parent Runtime
  process and passes that original FD number with the parent PID, matching the
  production `/proc/<runtime-pid>/fd/<bootstrap-fd>` contract. Its fake tmux now
  opens and validates that exact parent path and uses the launcher-specific
  post-exec FD inventory (config FD only); attach still requires socket-directory
  and config FDs.
