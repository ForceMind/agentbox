# Governance Automation Policy

## Automation principal

Mechanical Ready, merge, release, and slice-transition actions may be performed
by the Coding Agent after required CI succeeds. A separate governance bot is
optional and is not required for routine repository work.

## Required checks

The bot must revalidate, for every action:

- repository is `ForceMind/agentbox`;
- exact PR number;
- exact head SHA;
- exact base SHA;
- required CI checks are terminal SUCCESS;
- host evidence is valid and non-secret;
- release actions include an exact release authorization record and exact target tuple;
- the authorization record is still current.

Head/base validation remains recommended for auditability but does not create a
separate approval gate.

## Allowed actions

The Coding Agent may:

- update Draft/Ready state;
- squash-merge an exact approved PR;
- start a release workflow only when an exact release authorization record matches all of:
  - PR number;
  - exact target workflow ref;
  - exact target workflow file;
  - exact release tag or branch ref;
  - immutable artifact fingerprint bound to the record;
- and only for the explicit authorized release scope.
- transition to a specifically authorized next Slice.

## Forbidden actions

The bot and Coding Agent may never:

- handle Provider secrets, cookies, tokens, passwords, or private keys;
- bypass required checks;
- use `--admin`, force push, or rewrite history;
- expose arbitrary shell, filesystem, or process execution;
- activate real host capabilities without host evidence;
- infer authorization for a different PR, head, base, or Slice.
