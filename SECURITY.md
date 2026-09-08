# Security Policy

## Current maturity

AgentBox source is the `0.3.0rc10` development candidate, advancing from the
`0.3.0rc1` MVP artifact baseline. It implements authentication,
typed Runtime control, ephemeral Pair Code delivery, Project/Git/GitHub
operations, native installation, systemd deployment, staged update, and
verified rollback for a single-server/single-administrator Linux x86_64 model.
PR #87 head `80a6972466a514aa67577bb7812cf4c649a5983c` completed 26 terminal
checks (24 success and two prescribed historical skips), then merged normally
as `b3e9cd5dbfbdca0c5e0cd652dc0cce7e1e53214e`. R11 software rc6–rc9 and WEV-1
have software evidence; R12 remains independently unstarted and host-gated.
This pre-release does not claim production readiness, penetration testing or
broad platform support.

WEV-1 changes browser observation validity and action guards only, with independent
Architecture/Test/Security review. It adds no Runtime/Secret authority or
production activation. Its exact CI and host limits are recorded in
`docs/WORKSTATION_EVOLUTION.md`.

R10 packages inert WAW process-policy templates and native helper source/build
checks. It does not install or enable a unit/socket, create a native helper
binary, use a vendor account, or handle a Provider credential, Secret, key or
host enrollment record. R11 integration and R12 host qualification remain
separate security boundaries.

rc9 keeps user-facing copy in typed `zh-CN`/English catalogs and localizes API
errors from stable codes only. It never renders API/server prose as a fallback.
`navigator.languages[0]` is the sole per-document locale input; technical
values (identifiers, protocol fields, error codes and Audit actions) are not
translated. Test-only E2E uses a distinct-origin harness; it is absent from the
production bundle, and traces, video and screenshots remain disabled where a
sensitive artifact could be created.

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
