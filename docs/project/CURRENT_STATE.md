---
schema_version: 1
verified_at_utc: "2026-09-03T05:52:08Z"
verified_by: "codex-live-reconciliation"
repository: "ForceMind/agentbox"
---

# Current Verified State

## Live baseline

- Verified `HEAD` / `main` / `origin/main` / merge-base at snapshot-branch start:
  `35191eeaf858041cf5c0767dc1579b67690444ec`.
- Active documentation branch: `codex/waw-final-state-snapshot`; starting tree clean.
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

## Remaining blocker / next action

**The complete interactive product is not finished.** Stage F remains not
started: explicit real-transport Architecture/Owner scope, an authorized isolated
Linux target, and attributable non-secret host evidence are missing. The Owner
was asked for the target/SSH alias; no target was supplied during this snapshot.

Real fixed CLI/PTY execution, Noise/WebSocket/browser terminal, legacy process
interlocks, Runtime/API restart and reboot recovery still require implementation
and qualification. Current UI remains NOT ADMITTED. Earlier MVP OpenCloudOS
qualification does not qualify WAW. No real Provider credentials, Runtime HOME,
Secret handling, host activation, release tag/publication or production support
promise was used or authorized by this task. See `NEXT_ACTION.md`.
