---
schema_version: 1
verified_at_utc: "2026-09-03T04:17:40Z"
verified_by: "codex-live-reconciliation"
repository: "ForceMind/agentbox"
---

# Current Verified State

- Repository: `ForceMind/agentbox`
- Verified starting `HEAD` / `main` / `origin/main` / merge-base: `24d08414b20e7158e8c84694aac59d0326799bfd`.
- Starting working tree: clean. Active implementation branch: `codex/waw3-recovery-contracts`.
- Exact-main CI: Backend, Frontend, E2E, Deployment, Security and Release Candidate are all terminal `success` (live GitHub read on 2026-09-03).
- Historical Draft PR `#42` remains open and is outside this implementation branch.
- WAW-1 HTTP lifecycle/attachment routes: PR `#47` merged (`cd599a6e4b24ba860f4c9f294b16625a397a30f7`).
- WAW-1 Runtime attachment prepare/detach contracts: PR `#49` merged (`03f862a6cab41cd499a9d9a1024d581348818eda`).
- WAW-1 synthetic stream bridge, bounded stream controls, and WAW-2 Codex command identity contract: PR `#52` merged (`2bd58b07a7e0941e45b62eecc6bd5d66efc8350e`).
- WAW-1 fail-closed WebSocket route boundary: PR `#54` merged (`73a423576fe23a2671fd68b0d54dfcd0c9d9469d`).
- WAW-2 Codex lifecycle synthetic support: PR `#55` merged (`d25615b6edb3dce5d0ceecd79589a66558d49b21`).
- Repository Ruleset and `owner-approval` Environment were removed on 2026-09-01 at Owner request.
- Routine mechanical actions may proceed after CI; host/Secret safety boundaries remain.
- Owner authorized parallel multi-agent development and per-stage GitHub/document updates on 2026-09-03. See `EXECUTION_PLAN.md`.
- WAW-3 already has lease cleanup, output ring and durable cleanup contracts; software recovery classification and browser event fencing are implemented in this branch and await exact-head CI/merge. Full transport recovery remains incomplete.
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
