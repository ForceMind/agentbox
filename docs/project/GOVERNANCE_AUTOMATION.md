# Governance Automation Policy

## Automation principal

All mechanical Ready, merge, release, and slice-transition actions are
performed only by `agentbox-governance-bot`.

The coding Agent is never the approval principal and cannot create or modify
its own authorization record.

## Required checks

The bot must revalidate, for every action:

- repository is `ForceMind/agentbox`;
- exact PR number;
- exact head SHA;
- exact base SHA;
- required CI checks are terminal SUCCESS;
- required Architecture/Security/Test reviews are present;
- host evidence is valid and non-secret;
- the authorization record is still current.

Any head/base change invalidates the authorization.

## Allowed actions

The bot may:

- update Draft/Ready state;
- squash-merge an exact approved PR;
- start a pre-authorized release workflow;
- transition to a specifically authorized next Slice.

## Forbidden actions

The bot and Coding Agent may never:

- handle Provider secrets, cookies, tokens, passwords, or private keys;
- create a self-approval;
- bypass required checks;
- use `--admin`, force push, or rewrite history;
- expose arbitrary shell, filesystem, or process execution;
- activate real host capabilities without host evidence;
- infer authorization for a different PR, head, base, or Slice.
