# Governance Automation Policy

## Automation principal

Mechanical Ready, merge, release, and slice-transition actions may be performed
by the Coding Agent after required CI succeeds. A separate governance bot is
optional and is not required for routine repository work.

## Required checks

The Coding Agent or optional bot revalidates routine repository actions:

- repository is `ForceMind/agentbox`;
- exact PR number;
- exact head SHA;
- exact base SHA;
- required CI checks are terminal SUCCESS;
- all additional exact-head checks are terminal and successful as well.

Host activation additionally requires valid, attributable non-secret host
evidence. Release publication additionally requires a current exact release
authorization record and target tuple. These additional gates apply to those
operations, not to an ordinary software/documentation merge.

## Allowed actions

The Coding Agent may:

- update Draft/Ready state;
- squash-merge a PR whose exact head has completed CI and applicable review;
- start a release workflow only when an exact release authorization record matches all of:
  - PR number;
  - exact target workflow ref;
  - exact target workflow file;
  - exact release tag or branch ref;
  - immutable artifact fingerprint bound to the record;
- and only for the explicit authorized release scope.
- transition to the next software stage in the current Owner-authorized plan.

## Forbidden actions

The bot and Coding Agent may never:

- handle Provider secrets, cookies, tokens, passwords, or private keys;
- bypass required checks;
- use `--admin`, force push, or rewrite history;
- expose arbitrary shell, filesystem, or process execution;
- activate real host capabilities without host evidence;
- infer host, Secret, architecture or release authorization from a routine PR
  merge, or exceed the currently authorized software plan.
