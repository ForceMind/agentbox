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

## User experience and design quality

Kebui should be as approachable as a conversation and as inspectable as a
workbench. A rebrand or palette change alone is not a completed UI redesign.

The Owner requested reference-led design using the supplied projects. Preserve
Cromma and Cindy as product-interaction references and the existing Paseo, HAPI,
CloudCLI and Yep Anywhere workbench reference set. Keep actual screenshot
observations, upstream descriptions, design proposals and production capabilities
separate; do not copy private messages or third-party brand assets into releases.

[KEBUI_UI_DESIGN.md](KEBUI_UI_DESIGN.md) defines desktop/mobile interaction,
visual principles, components, full-page coverage and acceptance requirements.
[KEBUI_UI_DELIVERY_PLAN.md](KEBUI_UI_DELIVERY_PLAN.md) maps visible designs,
interactive synthetic prototypes and bounded implementation onto the existing
product stages without replacing current rc31 work or creating another roadmap.

Conversation-first does not remove Project ownership, content permissions,
explicit consequential-operation approval or exact Stop. Future task, routing,
memory and collaboration controls require their own qualified capabilities.

## Vision

AgentBox turns a Linux host into a securely operated AI development workstation with a typed control plane, separated secrets and runtime authority, and explicit Owner governance.

## Scope

- Read/write only via versioned APIs.
- No arbitrary command/filesystem/process gateway.
- Mechanical repository actions follow CI-gated feature branch, merge and exact
  read-back; a separate governance bot is optional.

## Governance boundary

- Host activation, secret-handling, architecture decisions, release publication, and support promises remain Owner-responsible unless explicitly delegated in protected policy.
