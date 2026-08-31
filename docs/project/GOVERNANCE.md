# AgentBox Governance

## Branch and PR Policy

- Work only on a feature branch; never write directly to `main`.
- Every change is published as a Draft PR first. Context migration is documentation/configuration only.
- Exact PR head/base and merge-base are checked before action and after every push.

## CI and Review

All required and additional checks for the exact head must reach terminal state. Pending checks are not PASS. Security-critical changes require independent read-only Architecture, Security and Test reviewers; their PASS is evidence only.

## Owner Gates

Flow: `feature branch → Draft PR → CI → Architecture/Security Review → Owner explicit approval → Ready → Squash Merge → exact read-back`.

Owner authorization must be an explicit human statement bound to exact PR number, exact head SHA and exact base SHA. A changed head/base invalidates prior authorization. Without it, remain Draft and do not Ready or merge.

## Prohibitions

No self-approval, `--admin`, force push, history rewrite, automatic Ready/merge/next Slice, production changes outside the authorized scope, or real Provider Secret handling. Context migration must not modify PR #41.

## BLOCKED Conditions

Block when repository identity, permissions, working-tree safety, exact-head CI evidence, or architecture contract cannot be verified; when reviewer conclusions conflict without evidence to close; or when a requested action exceeds `NEXT_ACTION` authorization. Report facts and recovery condition.

## Evidence

Reports include commands, exit codes, exact SHAs, PR metadata, CI terminal summary, diff boundary and unverified scope. `CURRENT_STATE` is a snapshot only; Git/GitHub live state wins.
