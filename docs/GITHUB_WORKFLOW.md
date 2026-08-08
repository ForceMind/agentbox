# GitHub Workflow

## Status and prerequisites

This document is a plan only. Phase 1 does not initialize Git, create a GitHub repository, create milestones or issues, commit, push, or open a pull request. Phase 0 found that Git is installed and GitHub CLI authentication is usable, but Git identity is not configured and repository ownership/visibility have not been approved.

## Repository policy

- `main` is the only long-lived branch and must be protected once the remote exists.
- Direct development on `main` is prohibited. Work uses short-lived branches such as `feat/codex-capabilities`, `fix/pair-redaction`, and `docs/runtime-model`.
- Require pull requests, at least one approving review, resolved conversations, passing required checks, and a current branch before merge.
- Disallow force pushes and branch deletion on `main`; never rewrite published release tags.
- Prefer squash merge for focused changes. Preserve a merge commit only when it materially improves history.
- CODEOWNERS review should be required for Helper, authentication, update verification, migrations, IPC protocol, and security policy paths.
- Never commit tokens, Pair Codes, passwords, cookies, private keys, real authentication files, database snapshots, or unredacted command fixtures.

## Pull requests

One pull request should express one coherent outcome. It may include code, tests, and the documentation needed for that outcome; unrelated cleanup is split out. A Draft PR is encouraged for design validation, risky IPC/security work, or an early vertical slice.

The planned PR template asks for:

- problem, scope, and explicit non-goals;
- linked issue and ADR where relevant;
- trust-boundary or privilege impact;
- migrations and rollback behavior;
- tests performed and tests not performed;
- screenshots only when they add review value and contain no secrets;
- checklist for redaction, documentation, compatibility, and changelog impact.

Small reviewable PRs are preferred, but artificial file-by-file PRs are not. Privilege changes must not be hidden inside broad refactors.

## Commits

Use Conventional Commit-style subjects (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `build:`, `ci:`, `chore:`), imperative mood, and a meaningful scope when helpful. A commit must build on its own when practical and must never contain secrets. Signed commits or signatures may be required later by the repository policy; that choice is not a Phase 1 blocker.

## Initial planning scale

Use five initial milestones and approximately 18 issues—well below a 100-issue backlog. Each issue uses checklists for bounded sub-tasks rather than generating an issue per file or endpoint.

| Milestone | Purpose | Planned initial issues |
|---|---|---:|
| M1 Foundation and authentication | Phase 2–3 skeleton, persistence, auth, IPC protocol | 4 |
| M2 Operator interface | Phase 4 frontend and CLI contract | 3 |
| M3 Runtime management | Phase 5–6 Codex and Claude adapters | 4 |
| M4 Projects and deployment | Phase 7–8 project/Git and native installation | 4 |
| M5 Release hardening | Phase 9–10 security, compatibility, release | 3 |

The proposed 18 initial issue themes are: monorepo/CI skeleton; typed contracts; database foundation; authentication/session security; frontend shell; CLI foundation; SSE/job views; Codex detection/lifecycle; Pair Code channel; Claude adapter; tmux session lifecycle; project path guard; project/Git read model; installer and package abstraction; systemd/IPC hardening; upgrade/rollback; threat-model validation; release/compatibility matrix. These are planning suggestions and have not been created.

## Issue templates

Phase 2 may add:

- **Feature:** outcome, user value, scope/non-goals, acceptance checklist, tests, docs, security/privilege impact, dependencies.
- **Bug:** observed/expected behavior, redacted reproduction, version/environment, severity, regression status, logs with secrets removed.
- **Security:** directs reporters to the private vulnerability channel and warns against public secret/exploit disclosure.
- **ADR proposal:** decision, context, alternatives, impacts, and revisit trigger.

Issue titles describe outcomes. Security-sensitive defects are handled privately until coordinated disclosure is safe.

## ADR workflow

Material architectural decisions begin as `Proposed`. A PR changes an ADR to `Accepted` only after human review. Reversals add a new ADR and mark the old record `Superseded`; rejected options remain recorded as `Rejected`. Code that changes a trust boundary cannot merge before the matching ADR is approved.

## CI and branch checks

Required checks should eventually include backend format/lint/type/unit tests, frontend lint/type/unit/build, contract/schema validation, secret scanning, dependency review, migration checks, and targeted security tests. VM-only privileged tests report separately and must not receive production credentials. CI logs and fixtures are treated as public artifacts.

## Releases

1. Create a release issue/checklist from an approved milestone.
2. Freeze schema and protocol versions; update changelog and compatibility matrix.
3. Run the required CI and ephemeral-VM deployment matrix.
4. Build from protected `main`; generate provenance, checksums, and signatures according to the approved release policy.
5. Verify clean install, update, health gate, backup, and rollback.
6. Create an immutable semantic-version tag and publish release notes with known limitations.
7. Do not replace a published tag or force-push history; publish a new patch release for corrections.

Release credentials are held by GitHub/environment protection, never the repository. No workflow automatically modifies a user's server.

## Third-party naming and content

Codex, Claude, and GitHub are compatibility targets, not endorsements. Documentation uses factual nominative references and the appropriate owners' names, avoids logos by default, and includes an independent-project disclaimer. Third-party CLI output fixtures must be minimal, redacted, and reviewed for license and privacy concerns.
