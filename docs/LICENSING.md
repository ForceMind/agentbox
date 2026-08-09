# AgentBox Licensing

Status: **Accepted**

AgentBox is licensed under the [Apache License, Version 2.0](../LICENSE), with
SPDX identifier `Apache-2.0`. The authorized maintainer accepted this decision
on 2026-08-09 in [ADR 0008](adr/0008-license-choice.md).

## Why Apache-2.0

Apache-2.0 is permissive and widely understood by individual, enterprise, and
distribution adopters. Unlike MIT, it includes an express patent grant and
patent-termination terms. Unlike AGPL-3.0, it does not require operators of a
modified network service to publish corresponding source, avoiding that
adoption and compatibility burden for the initial project.

The tradeoff is deliberate: Apache-2.0 permits proprietary modification,
commercial distribution, and hosted offerings when its conditions are met.
AgentBox will encourage contribution through transparent governance, security,
quality, and project identity rather than network copyleft.

## Contributions and notices

- Contributions intentionally submitted for inclusion are under Apache-2.0
  unless a separate written agreement explicitly says otherwise.
- Distributed copies must include the license and retain applicable copyright,
  patent, trademark, and attribution notices.
- AgentBox does not currently include a project `NOTICE` file because no
  project or bundled attribution has been identified that requires one. Add it
  when a concrete attribution obligation arises; do not use it to alter the
  license.
- Blanket source-file headers are not currently required. A consistent SPDX
  header policy may be adopted later without changing the project license.
- Direct and transitive dependency license compatibility remains a release
  check; the root license does not relicense third-party components.

## Third-party names

Codex, Claude, GitHub, Linux distribution names, and other third-party marks are
used only for factual compatibility descriptions. AgentBox is an independent
project, claims no affiliation or endorsement, and does not use third-party
logos by default. Third-party tools and redistributed materials remain subject
to their own licenses and terms.

## Revisit policy

Reconsider the licensing strategy only through a new ADR if legal advice,
dependency compatibility, hosted-source reciprocity, dual licensing, or the
project's business model materially changes the tradeoff. A future decision
cannot revoke Apache-2.0 rights already granted for published versions and must
include a contributor-rights review.
