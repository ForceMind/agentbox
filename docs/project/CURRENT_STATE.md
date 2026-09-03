---
schema_version: 1
verified_at_utc: "2026-09-03T05:22:07Z"
verified_by: "codex-live-reconciliation"
repository: "ForceMind/agentbox"
---

# Current Verified State

- Repository: `ForceMind/agentbox`
- Current stage starting `HEAD` / `main` / `origin/main` / merge-base: `7c1c755854077d2e0989ff1d3ab3d54f77e9e707`.
- Starting working tree: clean. Active implementation branch: `codex/workspace-metadata-workflow`.
- Historical starting-main `24d08414b20e7158e8c84694aac59d0326799bfd` CI: Backend, Frontend, E2E, Deployment, Security and Release Candidate were all terminal `success`. Current merge CI is tracked separately below.
- Historical Draft PR `#42` remains open and is outside this implementation branch.
- WAW-1 HTTP lifecycle/attachment routes: PR `#47` merged (`cd599a6e4b24ba860f4c9f294b16625a397a30f7`).
- WAW-1 Runtime attachment prepare/detach contracts: PR `#49` merged (`03f862a6cab41cd499a9d9a1024d581348818eda`).
- WAW-1 synthetic stream bridge, bounded stream controls, and WAW-2 Codex command identity contract: PR `#52` merged (`2bd58b07a7e0941e45b62eecc6bd5d66efc8350e`).
- WAW-1 fail-closed WebSocket route boundary: PR `#54` merged (`73a423576fe23a2671fd68b0d54dfcd0c9d9469d`).
- WAW-2 Codex lifecycle synthetic support: PR `#55` merged (`d25615b6edb3dce5d0ceecd79589a66558d49b21`).
- Repository Ruleset and `owner-approval` Environment were removed on 2026-09-01 at Owner request.
- Routine mechanical actions may proceed after CI; host/Secret safety boundaries remain.
- Owner authorized parallel multi-agent development and per-stage GitHub/document updates on 2026-09-03. See `EXECUTION_PLAN.md`.
- WAW-3 already has lease cleanup, output ring and durable cleanup contracts; software recovery classification and browser event fencing were merged in PR #58. Full transport recovery remains incomplete.
- Real WAW Linux host, PTY/devpts, Noise cryptography, WebSocket transport, browser terminal wiring, Codex attachment/CLI integration and WAW-3 end-to-end continuity/recovery remain unverified/incomplete. Earlier MVP host qualification is not WAW qualification.
- Durable generation allocation currently fails closed at SQLite signed-64 maximum (`2**63 - 1`); full protocol uint64 storage is not claimed. A storage representation change would require a separate architecture decision.

## Evidence boundaries

- Preflight: `git fetch origin --prune`, local identity/diff checks, `gh pr list`, and `gh run list --commit 24d08414b20e7158e8c84694aac59d0326799bfd` all exited `0`.
- Initial targeted baseline: `.venv/bin/python -m pytest tests/unit/test_waw_lease.py tests/unit/test_waw_stream_contract.py tests/unit/test_waw_lifecycle.py -q` exited `0`, `51 passed`.
- Local toolchain is Python `3.14.7`, Node `26.7.0`, pnpm `11.19.0`; project CI uses Python `3.11–3.13`, Node `22`, pnpm `11.20.0`. Local checks supplement exact-head CI and do not replace its supported matrix.
- This snapshot records an observed base. The merge SHA of the containing PR can only be recorded after actual merge read-back, in a later snapshot.

## Stage B local verification (before PR CI)

- `.venv/bin/ruff check apps packages tests migrations`: exit `0`.
- `.venv/bin/black --check apps/api apps/worker apps/cli packages tests migrations`: exit `0`, 196 files unchanged; final touched Python files were also formatted/checked.
- `.venv/bin/mypy --platform linux apps/api apps/worker apps/cli packages tests`: exit `0`, 188 files. This is static Linux-target checking, not execution on Linux.
- `.venv/bin/python -m pytest -q tests/unit/test_waw_recovery.py tests/unit/test_waw_lease.py tests/unit/test_waw_supervisor.py tests/unit/test_waw_stream_contract.py tests/unit/test_waw_lifecycle.py`: exit `0`, `101 passed`.
- `pnpm typecheck`, `pnpm lint`, `pnpm format:check`: exit `0`.
- `NODE_OPTIONS=--no-experimental-webstorage pnpm test`: exit `0`, `102 passed`, including 47 recovery reducer tests. Without this local Node 26 flag, 20 existing storage assertions failed because Node's experimental storage shadowed jsdom; no production code or assertions were relaxed.
- `pnpm build`: exit `0`.
- Expanded local WAW unit/integration run outside the sandbox: exit `1`, `545 passed / 73 failed`; macOS lacks the required Linux socket behavior and the short temporary directory did not satisfy provenance checks. This matrix is **not PASS**; supported Linux exact-head CI remains required.
- Independent read-only Architecture/Security review found no remaining frontend P1/P2 after repairs. Backend review found identity/epoch/cleanup issues which were fixed and regression tested; final independent Test/Security review reran all 101 targeted tests and reported no remaining software-contract blocker.
- No real terminal, host activation, browser transport, Provider login or production release was executed. Contract mapping: `../WAW3_RECOVERY_CONTRACTS.md`.

## Stage A/B completed and Stage C live preflight

- PR #58: `MERGED` at `2026-09-03T04:22:05Z`.
- Exact reviewed head: `f3bb9035e061fc0babfcace6af891f257eb7fa74`; base: `24d08414b20e7158e8c84694aac59d0326799bfd`.
- Exact-head CI: `19/19 SUCCESS`, all terminal, including Python 3.11/3.12/3.13, Node 22 frontend, E2E, deployment, security and release gates.
- Observed merge commit: `d2470601a06da0a4024fa1772b4f32ec2daa7293`; `origin/main` matches. Merge/read-back/fetch/fast-forward commands exited `0`.
- Post-merge exact-main CI was re-read: all six workflows (Backend, Frontend, E2E, Deployment, Security, Release Candidate) are terminal `success` for `d2470601a06da0a4024fa1772b4f32ec2daa7293`. This is separate from the PR-head 19/19 evidence.
- Stage C began from a clean tree; only historical Draft PR #42 remains open. WAW Codex API/Web contract work is in progress; real CLI execution remains host/architecture-gated.

## Stage C software validation (before PR CI)

- API Start/Stop/ticket now support both closed AgentTypes and reject mismatched Runtime workspace/Project/AgentType/generation responses.
- Web Start/Stop/ticket/Detach parsers reject unknown fields and bind response identity to the requested context; the action hook rejects concurrent work and discards results after auth scope changes or unmount.
- `.venv/bin/python -m pytest -q tests/integration/test_waw_workspace_api.py tests/unit/test_waw_admission.py tests/unit/test_workspace_api_contract.py tests/unit/test_waw_codex_command.py`: exit `0`, `50 passed`.
- `ruff check`, `black --check`: exit `0`; `mypy --platform linux apps/api apps/worker apps/cli packages tests`: exit `0`, 188 files.
- `pnpm typecheck`, `pnpm lint`, `pnpm format:check`: exit `0`; `NODE_OPTIONS=--no-experimental-webstorage pnpm test`: exit `0`, `110 passed`; `pnpm build`: exit `0`.
- `python scripts/check-doc-links.py`: exit `0`, 148 relative links.
- Independent read-only API and frontend Architecture/Security reviews: PASS for this synthetic/control software scope, no remaining blocker. Review does not qualify a real CLI/host.
- Actual legacy Remote Control interlocks and fixed Codex process/PTY execution remain unimplemented/unverified. The API rejects Runtime-reported conflict states; no real process probe, terminal or login was run.

## Stage C completed / Stage D in progress

- PR #59 MERGED at `2026-09-03T04:45:48Z`; reviewed head `3e0e7a921e008d9c6b5198d37b8254fbee174068`, base `d2470601a06da0a4024fa1772b4f32ec2daa7293`.
- Exact-head checks: `19/19 SUCCESS`, all terminal. Actual merge read-back and `origin/main`: `7c1c755854077d2e0989ff1d3ab3d54f77e9e707`.
- Stage D began from a clean tree; only historical Draft PR #42 remains open.
- Workspace metadata queries, UI/controller integration and desktop/mobile validation are in progress. Terminal transport remains unavailable and is not replaced with a fake admission.

## Stage D software and browser evidence (before PR CI)

- PR #59 post-merge CI for `7c1c755854077d2e0989ff1d3ab3d54f77e9e707`: all six workflows terminal `success`.
- Typed Project/AgentType query filters precede authorization/32-row cap; Workspace page now uses exact selection, registered metadata, explicit Start and scoped exact Stop confirmation.
- `.venv/bin/python -m pytest -q tests/integration/test_waw_workspace_api.py tests/unit/test_waw_admission.py tests/unit/test_workspace_api_contract.py tests/unit/test_waw_codex_command.py`: exit `0`, `56 passed`.
- `ruff check`, `black --check`, `mypy --platform linux ...`: exit `0` (188 Python source files for mypy).
- Web `typecheck`, `lint`, `format:check`, `build`: exit `0`; `NODE_OPTIONS=--no-experimental-webstorage pnpm test`: exit `0`, `115 passed`.
- Initial `pnpm e2e`: exit `1`, 54 existing tests passed and four new metadata tests failed due to ambiguous Playwright locators. Locators were made exact; subsequent `PLAYWRIGHT_BASE_URL=http://127.0.0.1:4178 pnpm --filter @agentbox/web exec playwright test e2e/workspace-metadata.spec.ts`: exit `0`, all four new desktop/mobile tests passed. The combined final exact-head CI remains the merge gate.
- Main-agent visual QA used actual Chromium at `1280x900` and `390x844`; synthetic normal, Stop confirmation, mobile empty and mobile error renderings were viewed. No horizontal overflow; all tested visible controls at least 44px; native Cancel/Escape restored Stop focus. Screenshots contain synthetic metadata only and are not committed or release artifacts.
- Independent read-only Architecture/Security review: PASS for metadata/control scope after checking server-side binding/epoch validation, client stale-response and Stop-target fencing. Visual checking was main-agent structured QA, not an independent visual certification.
- Terminal remains `NOT ADMITTED`; no ticket/terminal bytes were obtained or persisted, no real host or Provider operation occurred. Workflow mapping: `../WORKSPACE_METADATA_WORKFLOW.md`.
