# ADR 0006: React, TypeScript, and Vite frontend

## Status

Accepted

## Context

The MVP needs a responsive authenticated control panel with seven focused operational views and live Job/status updates. It does not need server-side rendering, a browser IDE, or a full design-system program. The frontend must remain a replaceable client of `/api/v1`, not a second policy engine.

## Decision

Use React, TypeScript, and Vite. Use Tailwind CSS for a small tokenized layout system and selectively adopt shadcn/ui source components when they improve accessibility or consistency. Avoid large component suites and unnecessary state frameworks. Build static assets into the immutable release under `/opt/agentbox/current/web` and serve them from Web/API or an optional reverse proxy.

Use HTTP request/response plus SSE for Job and status progress. Do not add WebSocket in the MVP; reconsider it only for a genuinely bidirectional feature such as a future PTY, which is itself deferred.

## Alternatives Considered

- **Server-rendered templates/HTMX:** smaller dependency surface and viable, but less aligned with the planned multi-view stateful dashboard and typed client contract.
- **Next.js or another SSR framework:** rejected as unnecessary server/runtime complexity for a local static panel.
- **Vue/Svelte:** capable alternatives, but React has the strongest fit with the stated team/product direction and shadcn/ui ecosystem.
- **Full component framework:** rejected to control dependency and visual complexity.

## Consequences

The repository needs a Node toolchain, a lockfile, dependency review, frontend build artifacts, and generated API types or carefully shared schemas. Client behavior remains tolerant of unavailable capabilities.

## Security Impact

Static assets do not receive filesystem access. CSP, safe rendering, CSRF, secure cookies, cache policy, dependency pinning, and avoidance of secret-bearing client persistence are mandatory. Pair Code is never stored in browser storage or analytics.

## Operational Impact

Production needs no standalone Node server. Atomic release switching replaces the whole asset set and avoids mixed frontend/backend versions. Nginx/Caddy remains optional.

## Revisit Conditions

Revisit if accessibility/performance goals are not met, offline-first behavior becomes necessary, server-side rendering has a proven benefit, or frontend dependencies become disproportionate.
