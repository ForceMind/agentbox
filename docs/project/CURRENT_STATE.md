---
schema_version: 1
verified_at_utc: "2026-09-03T06:50:25Z"
verified_by: "codex-live-reconciliation"
repository: "ForceMind/agentbox"
---

# Current Verified State

## Live baseline

- Observed `origin/main`: `90df8b9adfe3c03fc089634c18214a4fb6fcfe9e`.
- Active implementation branch: `codex/waw-runtime-composition`, created from
  PR #63 head and normally merged with the read-back main; no history rewrite.
- Local `main` still points to `dfc788a29623de5b5a9c3230855af1ee7aed2953`
  while work continues on the feature branch.
- Historical Draft PR #42 remains open and outside this task's write scope.
- This file records observed commits; it cannot predict its own future merge
  SHA. Live Git/GitHub always overrides the snapshot.

## Delivered software stages

| Stage | PR | Exact reviewed head | Observed merge | Exact-head CI |
| --- | --- | --- | --- | --- |
| A/B — plan + recovery | #58 | `f3bb9035e061fc0babfcace6af891f257eb7fa74` | `d2470601a06da0a4024fa1772b4f32ec2daa7293` | 19/19 SUCCESS |
| C — Codex control | #59 | `3e0e7a921e008d9c6b5198d37b8254fbee174068` | `7c1c755854077d2e0989ff1d3ab3d54f77e9e707` | 19/19 SUCCESS |
| D — metadata UX | #60 | `9be95b10e57a3daa3690205d6c2ffad8da74424d` | `6972f0dba907afd9741c2dc3584f431ee32765ed` | 19/19 SUCCESS |
| E — software readiness | #61 | `0c894ff52f49793f599eb33c4b92b8223e6109b3` | `35191eeaf858041cf5c0767dc1579b67690444ec` | 19/19 SUCCESS |
| F1.1 — shared supervisor | #63 | `c78cb92a5afe8056ab44a1cc4e8a6bea3074e184` | `90df8b9adfe3c03fc089634c18214a4fb6fcfe9e` | 19/19 SUCCESS |

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
Current branch implements the concrete lifecycle executor, read-only process
probe, two-phase attachment boundary and failed-start cleanup/restart fencing.
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

## F1.2 Runtime composition in progress

- Concrete `WAWSupervisorExecutor` shares exact supervisors between lifecycle
  dispatch and admitted stream bridges; factories are trusted Runtime inputs.
- Status/reconcile use a separate exact read-only probe. They do not reconnect
  a PTY, grant a writer or clear uncertain input.
- Failed readiness keeps the exact cleanup target. Durable generation
  reservation precedes process effects; unknown restart state stays quarantined
  until the existing host evidence path acknowledges cleanup.
- PR #63 merged at `2026-09-03T06:43:01Z`; GitHub merge read-back and fetch
  both exited 0. F1.2 validation and review are being completed on this branch.

F1.2 final local validation before PR CI:

- `.venv/bin/python -m pytest -q tests/unit/test_waw_command.py tests/unit/test_waw_codex_command.py tests/unit/test_waw_supervisor.py tests/unit/test_waw_stream_contract.py tests/unit/test_waw_transport.py tests/unit/test_waw_lifecycle.py tests/unit/test_waw_bootstrap.py tests/unit/test_waw_runtime_executor.py tests/integration/test_waw_workspace_api.py`: exit 0, 187 passed.
- `ruff check apps packages tests migrations`, `black --check apps/api apps/worker apps/cli packages tests migrations`, `mypy --platform linux apps/api apps/worker apps/cli packages tests`: exit 0; 199 formatted files and 191 typed files.
- `scripts/check-doc-links.py`: exit 0, 156 relative links; `git diff --check`: exit 0.
- Independent read-only review PASS; reviewer ran 127 tests before the final
  two binding cancellation/path-drift regressions. Final executor test file:
  14 passed, including those regressions. All transports/processes are synthetic.
- Six exact-main workflows for `90df8b9adfe3c03fc089634c18214a4fb6fcfe9e`
  completed successfully; this is separate from this branch's pending PR CI.
