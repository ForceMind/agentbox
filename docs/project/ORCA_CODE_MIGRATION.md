# Orca Source Migration — First Functional Slice

Upstream pinned: [stablyai/orca](https://github.com/stablyai/orca),
commit `d378f49f17067c1949747d038a3b163fef5bbb41` (version 1.4.214), MIT,
Copyright (c) 2026 Lovecast Inc. AgentBox baseline:
`13b2877823d5338cd4044ead39d658a0c89e96de` (Apache-2.0). This is a selective source migration, not
a runtime fork or dependency on Orca binaries.

## O01 — Project Changes file-path filter (software candidate)

- Adapted Orca's `src/shared/file-name-filter-tokens.ts` tokenizer,
  all-token substring matching, and 2 KiB UTF-8 input limit in
  `apps/web/src/features/changes/fileNameFilter.ts`.
- Integrated into the real Project Changes page: filtering applies only to
  already-loaded, already-authorized current paths or prior rename paths.
  It provides Chinese/English search UI, local matching counts, no-match
  feedback, and expands stale collapsed directories for a fresh query.
- Added pure-unit and React tests. The existing A3 staged-content reader
  remains independent and requires explicit user action. No new network
  request, file-body read, secret, shell, Runtime action or DB schema was added.
- MIT license retained at `third_party/licenses/orca-MIT.txt`;
  original commit/blob and modifications documented in
  `third_party/orca-sources.json`, `NOTICE`, and
  `THIRD_PARTY_NOTICES.md`.

O01 is a candidate until the current feature-head CI, review and merge
are verified. The migrated filter cannot authorize paths, infer code
ownership, or establish a new content source.

## Remaining source assimilation — NOT DELIVERED

| Card | Orca implementation reference | AgentBox destination and gate |
| --- | --- | --- |
| O02 | `src/main/repo-worktrees.ts`, `src/main/git/` | Runtime-owned bounded Project worktree inventory/create/remove, dirty-state and busy-lease fencing; fixed allowlisted actions only |
| O03 | `src/main/acp/`, Agent status logic | Concurrent Claude/Codex owner/operation view and review selection, with exact lifecycle, single-writer, UNKNOWN and Stop handling |
| O04 | Renderer source-control review/annotations | A3-authorized bounded diff annotation, content epoch/source scope and inert UI; no raw patch authority |
| O05 | `src/main/ssh/`, `src/main/orcad/`, mobile | Remote client UX over WAW trust without a second auth, daemon or unbounded server ingress |
| O06 | `src/main/browser/` Design Mode | Separate consented and permission-scoped DOM/screenshot review; no generic Computer Use activation |

Orca Electron/native packages, broad IPC command surfaces, credential stores,
terminal process spawners, and SSH daemon must not be copied wholesale into the
AgentBox production runtime. Study their behavior and only integrate qualified
bounded adapters against the existing project identity, browser trust, A3 and
WAW contracts. Prior Paseo adaptations remain operational and attributed.

## Repeatable development and verification rule

For every source adaptation: pin upstream commit and Git blob; preserve license,
copyright and modified-source notice; identify the functional caller and test
real error/hostile input; run available tests and exact-head CI; merge normally
only after accepted results; then record the main SHA and any missing real-host
evidence. Copying files alone is not feature completion.
