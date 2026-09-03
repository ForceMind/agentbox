---
schema_version: 1
verified_at_utc: "2026-09-03T10:35:54Z"
verified_by: "codex-live-reconciliation"
repository: "ForceMind/agentbox"
---

# Current Verified State

## Live baseline

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

## Delivery checkpoint and next required decision

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
