# AgentBox Charter

## Vision

AgentBox turns a Linux host into a securely operated AI development workstation with a typed control plane, separated secrets and runtime authority, and explicit Owner governance.

## Scope

- Read/write only via versioned APIs.
- No arbitrary command/filesystem/process gateway.
- Mechanical repository actions follow CI-gated feature branch, merge and exact
  read-back; a separate governance bot is optional.

## Governance boundary

- Host activation, secret-handling, architecture decisions, release publication, and support promises remain Owner-responsible unless explicitly delegated in protected policy.
