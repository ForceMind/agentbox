# ADR 0005: SQLite-backed Jobs with a separate systemd Worker

## Status

Proposed

## Context

Install, update, Git network operations, Runtime lifecycle, Doctor, logs, backup, and migration can outlive an HTTP request and must survive Web/API restarts. The single-server MVP does not need distributed scheduling, Redis, or Celery, but an in-process background task alone has weak recovery and couples work lifetime to HTTP workers.

## Decision

Persist Job state in SQLite and execute Jobs in one separate non-root systemd Worker process with default global concurrency one plus per-resource locks. Web/API validates and enqueues; Worker leases, checkpoints, and delegates typed actions to Runtime Executor or Privileged Helper. Progress is persisted as bounded structured summaries and streamed through SSE. Full or sensitive subprocess output is never stored in Job rows.

States are `queued`, `running`, `succeeded`, `failed`, `cancelled`, and `needs_attention`. On restart, expired `running` leases become `needs_attention` unless the Job type declares a safe idempotent resume/checkpoint strategy. Destructive work is never blindly replayed.

## Alternatives Considered

- **FastAPI `asyncio` background tasks:** acceptable only for short non-durable notifications, rejected for control Jobs.
- **Worker embedded in Web/API:** rejected because process restarts and multi-worker deployment complicate ownership and recovery.
- **Redis/Celery:** deferred as unnecessary operational weight for one server.
- **Synchronous HTTP:** rejected for timeout, disconnect, and recovery behavior.

## Consequences

Job handlers need idempotency keys, leases, checkpoints, cancellation policy, per-target locks, and standardized summaries. Throughput is intentionally modest. A future queue can replace storage/claiming behind the service interface.

## Security Impact

Persistent Jobs contain action identifiers and redacted summaries, never raw shell, credentials, Pair Codes, or complete command output. The Worker has no root rights and cannot bypass either narrow IPC boundary.

## Operational Impact

systemd supervises the Worker independently. SQLite transaction discipline and WAL backup are required. SSE reconnects use bounded event IDs; database state remains authoritative.

## Revisit Conditions

Revisit for multi-server scheduling, sustained concurrency beyond SQLite's single-writer envelope, high-volume logs/events, or a need for externally managed workers.
