# AgentBox Charter

## Strategic product identity

The strategic user-facing product brand is **Kebui（科布）**: an open-source,
conversation-first AI workspace where users express intent once and let the
right agents do the work.

During migration, **AgentBox Runtime** remains the execution/runtime identity
and keeps all existing typed-control, privilege, Secret and lifecycle
boundaries. Brand evolution does not authorize an arbitrary shell/filesystem
gateway and does not rename current internals by itself.

See [KEBUI_BRAND.md](KEBUI_BRAND.md) and
[KEBUI_PRODUCT_PLAN.md](KEBUI_PRODUCT_PLAN.md).

## Vision

AgentBox turns a Linux host into a securely operated AI development workstation with a typed control plane, separated secrets and runtime authority, and explicit Owner governance.

## Scope

- Read/write only via versioned APIs.
- No arbitrary command/filesystem/process gateway.
- Mechanical repository actions follow CI-gated feature branch, merge and exact
  read-back; a separate governance bot is optional.

## Governance boundary

- Host activation, secret-handling, architecture decisions, release publication, and support promises remain Owner-responsible unless explicitly delegated in protected policy.
