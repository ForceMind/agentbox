# ADR 0007: SQLite for the single-server MVP

## Status

Proposed

## Context

The MVP is one server with one administrator, modest metadata, a low-concurrency Worker, and no requirement for distributed database operations. AgentBox needs migrations, consistent backups, durable Jobs, and a path to a client/server database if the scope expands.

## Decision

Use SQLite through SQLAlchemy and Alembic. Enable WAL, foreign keys, a bounded busy timeout, short transactions, and serialized or intentionally coordinated writes. Store the database beneath `/var/lib/agentbox`; use SQLite's online backup mechanism/checkpoint policy rather than copying an active database blindly. ORM/domain boundaries must avoid SQLite-specific business logic so PostgreSQL remains a feasible future migration.

No model stores GitHub, Codex, Claude, OAuth, Pair Code, cookie, password plaintext, SSH key, or complete authentication configuration. The administrator password is an approved memory-hard hash, not an external-service secret.

## Alternatives Considered

- **PostgreSQL:** robust concurrency and operations, but unnecessary service/install/backup complexity for the single-host MVP.
- **JSON/YAML state files:** rejected for concurrency, migrations, integrity, and Job recovery.
- **Redis plus database:** rejected because it adds an external volatile component without an MVP requirement.

## Consequences

Write concurrency is bounded and large raw logs do not belong in the database. Migrations, backup, integrity checks, WAL/SHM handling, disk-full behavior, and recovery must be tested. Data access stays behind repositories/services.

## Security Impact

Database file and backups are mode-restricted to the service identity, and sensitive operational output is minimized/redacted. Local file compromise still exposes metadata and password hashes, so host permissions and backup protection matter.

## Operational Impact

Installation has no separate database daemon. Backups are simple but must be transactionally consistent. Maintenance should expose integrity and size diagnostics without dumping rows.

## Revisit Conditions

Revisit for multi-server or multi-tenant operation, high concurrent write volume, HA/replication, database size/latency limits, or operational demand for PostgreSQL.
