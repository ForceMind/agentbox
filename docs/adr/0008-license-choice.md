# ADR 0008: Recommend Apache License 2.0

## Status

Proposed

## Context

AgentBox is intended as open AI developer infrastructure and should be easy for individuals, distributions, and companies to adopt. The project also benefits from an explicit patent grant. A copyleft network-service license could require hosted modifications to remain open, but would create a higher adoption and compatibility burden before the project's governance and business model are established.

## Decision

Recommend Apache License 2.0 for the initial release, subject to explicit human approval and dependency/license review. Do not add a `LICENSE` file during Phase 1. Preserve copyright and notice obligations and document third-party licenses.

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

Phase 2 must add the approved license text, copyright policy, `NOTICE` if needed, dependency inventory, source headers policy, and trademark disclaimer. Distribution must retain required notices.

## Revisit Conditions

Revisit before the first public release if maintainers prioritize hosted-source reciprocity, introduce dual licensing, receive legal advice, discover incompatible dependencies, or establish a business model that changes the tradeoff.
