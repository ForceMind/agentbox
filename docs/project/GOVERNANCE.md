# AgentBox Governance

## Branch and PR Policy

- Work only on a feature branch; never write directly to `main`.
- Every change is published as a Draft PR first.
- Exact PR head/base and merge-base are checked before action and after every push.

## CI and Review

All required and additional checks for the exact head must reach terminal state. Pending checks are not PASS.
Security-critical changes require independent read-only Architecture, Security and Test reviewers; their PASS is evidence only.

## Delegated automation

Owner may delegate mechanical repository actions to `agentbox-governance-bot` through a protected GitHub Environment.

The delegation is policy-level, not PR-level. Every action still requires:

- exact repository (`ForceMind/agentbox`)
- exact PR number
- exact head SHA
- exact base SHA
- exact-head required checks are terminal `SUCCESS`
- required Architecture/Security/Test reviews present
- valid non-secret host / runtime evidence when needed

The bot identity must be separate from the Coding Agent identity and must not be able to alter

- its own workflow
- repository rulesets
- CODEOWNERS
- approval records.

## Owner Gates

Flow: `Owner-approved protected Environment -> governance-bot exact validation -> Ready -> Merge -> exact read-back`.

Owner authorization must be an explicit human statement bound to exact PR number, exact head SHA and exact base SHA.
A changed head/base invalidates prior authorization. Without it, remain Draft and do not start mechanical Ready/Merge or slice transition.

## Prohibitions

- No self-approval, `--admin`, force push, history rewrite, automatic Ready/merge/next Slice.
- production changes outside the authorized scope.
- real Provider Secret handling.

## BLOCKED Conditions

Block when repository identity, permissions, working-tree safety, exact-head CI evidence, or architecture contract cannot be verified; when reviewer conclusions conflict without evidence to close; or when a requested action exceeds `NEXT_ACTION` authorization.

## Evidence

Reports include commands, exit codes, exact SHAs, PR metadata, CI terminal summary, diff boundary and unverified scope.
`CURRENT_STATE` is a snapshot only; Git/GitHub live state wins.
