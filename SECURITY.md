# Security Policy

## Current maturity

AgentBox source is the `0.3.0rc2` development candidate, advancing from the
`0.3.0rc1` MVP artifact baseline. It implements authentication,
typed Runtime control, ephemeral Pair Code delivery, Project/Git/GitHub
operations, native installation, systemd deployment, staged update, and
verified rollback for a single-server/single-administrator Linux x86_64 model.
It is a pre-release—not a production-readiness, penetration-test, or broad
platform-support claim.

The security architecture and completed internal review are documented in
`docs/SECURITY.md`, `docs/PERMISSIONS.md`, `docs/THREAT_MODEL.md`, and
`docs/SECURITY_REVIEW_MVP.md`. Release artifacts are reproducible in the same
CI environment and have SHA-256 integrity metadata, but remain unsigned and do
not provide cryptographically verified publisher authenticity.

## Reporting a vulnerability

Please do not publish an exploit, sensitive log, credential, Pair Code, private repository content, host address, or authentication file in a public Issue or Discussion.

Use GitHub's private vulnerability reporting for this repository:

`https://github.com/ForceMind/agentbox/security/advisories/new`

If private reporting is unavailable, contact the repository maintainer privately through their GitHub profile and disclose only enough non-sensitive information to establish a secure reporting channel.

Include, when safe:

- affected commit/version and component;
- impact and prerequisites;
- minimal redacted reproduction;
- whether root, Runtime credentials, Project Workspaces, sessions, updates, or secret handling are affected;
- suggested mitigation, if known.

Never use production tokens or real Pair Codes as proof.

## Response expectations

Maintainers will acknowledge a credible report, assess severity and affected
candidate versions, coordinate a fix/advisory, and credit the reporter with
consent. This Release Candidate has no formal response-time SLA or stable
supported-version guarantee.

## Scope boundaries

Third-party Codex, Claude, GitHub, Linux distributions, tunnels, and package repositories follow their own security processes. Reports about AgentBox's invocation, isolation, redaction, upgrade, or permission behavior remain in scope even when a third-party tool is involved.
