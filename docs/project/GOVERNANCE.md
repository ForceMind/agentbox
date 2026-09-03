# AgentBox Governance

## Branch and PR Policy

- Work on a feature branch for ordinary changes.
- Merge after required CI succeeds; Draft PRs and exact approval records are optional.

## CI and Review

All required and additional checks for the exact head must reach terminal state. Pending checks are not PASS.
Security-critical changes require independent read-only Architecture, Security and Test reviewers; their PASS is evidence only.

## Automation

Mechanical repository actions may be performed directly by the Coding Agent after
required CI succeeds. A separate governance bot and protected Environment are not
required for routine work.

## Owner Gates

There is no additional Owner gate for routine code, documentation, or test changes.
Architecture changes, real-host activation, Secret handling, and production
support promises remain explicitly authorized operations.

## Current-task software decision delegation

On 2026-09-03 the Owner explicitly instructed the Coding Agent to continue and
stated that it may start/change goals and make the decisions itself. This is
explicit delegation of software plan and architecture decisions for the current
remaining-development objective, not merely an automatic “continue” event.
The Coding Agent may resolve reviewed software contract choices, record its
rationale, implement, test and obtain independent review without another
per-decision Owner confirmation.

Under that delegation the Coding Agent accepts the complete
[WAW stream supplement](WAW_ENCRYPTED_STREAM_DECISION.md) as the R4/R5 software
implementation contract. Existing authority separation, exact fixed actions,
no arbitrary shell/filesystem gateway, cryptographic verification and truthful
acceptance evidence remain mandatory. Real-host activation, production Runtime
key/Provider Secret operations, publication and production support commitments
still require a concrete authorized target/scope and actual evidence.

## Prohibitions

- No `--admin`, force push, or history rewrite.
- production changes outside the authorized scope.
- real Provider Secret handling.

## BLOCKED Conditions

Block when repository identity, permissions, working-tree safety, exact-head CI evidence, or architecture contract cannot be verified; when reviewer conclusions conflict without evidence to close; or when a requested action exceeds `NEXT_ACTION` authorization.

## Evidence

Reports include commands, exit codes, exact SHAs, PR metadata, CI terminal summary, diff boundary and unverified scope.
`CURRENT_STATE` is a snapshot only; Git/GitHub live state wins.
