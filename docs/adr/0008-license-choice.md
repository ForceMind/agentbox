# ADR 0008: Adopt Apache License 2.0

## Status

Accepted

Decision date: 2026-08-09

## Context

AgentBox is intended as open AI developer infrastructure and should be easy for individuals, distributions, and companies to adopt. The project also benefits from an explicit patent grant. A copyleft network-service license could require hosted modifications to remain open, but would create a higher adoption and compatibility burden before the project's governance and business model are established.

## Decision

License AgentBox under the Apache License, Version 2.0 (`Apache-2.0`). The repository root contains the canonical license text. Apache-2.0 is selected because it combines permissive reuse with an explicit patent grant and patent-termination terms, and is familiar to enterprise and open-source adopters.

Contributions intentionally submitted for inclusion are accepted under Apache-2.0 unless a separate written agreement states otherwise. Distribution must preserve the license and applicable attribution notices. AgentBox does not currently need a project `NOTICE` file; one must be added if future bundled material or required attributions make it necessary. Blanket source-file headers are not required, but SPDX identifiers may be adopted consistently in a later policy.

Use Codex, Claude, GitHub, Linux, and distribution names only for factual compatibility statements. Do not imply endorsement; do not use third-party logos by default; include an independent-project/trademark disclaimer. Third-party CLI integrations remain subject to their own terms.

## Alternatives Considered

- **MIT:** shortest and highly permissive, but lacks Apache-2.0's express patent license and termination language. It also permits proprietary commercial derivatives.
- **Apache-2.0:** permissive, enterprise-friendly, includes an express patent grant and notice rules; it still allows closed-source commercial modification and resale.
- **AGPL-3.0:** requires providers of modified network services to offer corresponding source, limiting fully proprietary hosted forks; however, it raises enterprise adoption friction, reciprocal-license review, and possible commercial/dependency compatibility concerns.

## Consequences

Adopters may modify and commercialize AgentBox without publishing changes, subject to license/notice terms. The project relies on community, brand, governance, and quality rather than strong network copyleft to encourage contributions.

## Security Impact

No license alone guarantees secure forks or disclosure. Apache-2.0's patent terms reduce one legal risk, while security reporting, signed releases, and provenance remain separate policies.

## Operational Impact

Repository and package metadata identify `Apache-2.0`. Dependency-license review remains part of release preparation. No `NOTICE` file is created without an actual attribution requirement. Distribution must retain required notices, and compatibility claims must remain factual and non-endorsing.

## Revisit Conditions

Revisit only if maintainers prioritize hosted-source reciprocity, introduce dual licensing, receive legal advice that changes the assessment, discover incompatible dependencies, or establish a business model that materially changes the tradeoff. A later change cannot revoke Apache-2.0 rights already granted for published versions; it applies prospectively and requires a new ADR plus contributor-rights review.
