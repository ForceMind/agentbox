# Security Policy

## Current maturity

AgentBox is pre-alpha. The current repository is an engineering skeleton and is not production-ready. It does not yet implement authentication, Runtime control, Pair Code generation, project operations, installation, systemd deployment, or privileged host actions.

The intended security architecture is documented in `docs/SECURITY.md`, `docs/PERMISSIONS.md`, and `docs/THREAT_MODEL.md`. Those are design commitments, not evidence that future features have passed a security review.

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

Maintainers will acknowledge a credible report, assess severity and supported versions, coordinate a fix/advisory, and credit the reporter with consent. Formal response timelines and supported-version guarantees will be published before the first release; none are promised for this pre-alpha skeleton.

## Scope boundaries

Third-party Codex, Claude, GitHub, Linux distributions, tunnels, and package repositories follow their own security processes. Reports about AgentBox's invocation, isolation, redaction, upgrade, or permission behavior remain in scope even when a third-party tool is involved.
