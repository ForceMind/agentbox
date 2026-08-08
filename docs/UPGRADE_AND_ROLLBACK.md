# AgentBox Upgrade and Rollback Design

Status: Phase 1 design baseline

## Objectives

Upgrades must be version-pinned, observable, minimally disruptive, and reversible across program files, frontend assets, configuration, and SQLite state. An “update” is never an unbounded `git pull` or execution of latest remote content.

## Version Model

- AgentBox releases use Semantic Versioning once public API stability begins.
- Program, API major, configuration schema, database schema, Runtime Adapter fixture schema, and Helper protocol versions are recorded separately.
- Release channels are `stable` by default and optional `preview`; channel changes require explicit confirmation.
- Downgrade is not the same as rollback and is refused unless the target declares backward compatibility and the administrator confirms.

## Update Check

Update check is read-only and returns:

- current and candidate version;
- channel and publisher origin;
- compatibility requirements;
- database/config migration range;
- artifact size and available verification metadata;
- breaking changes and manual gates;
- whether automatic rollback is supported.

No candidate is installed merely because it is newer.

## Download and Verification

Artifacts download into root-owned staging with strict origin, TLS, timeout, redirect, content-length, expanded-size, and filesystem limits. The updater verifies the published checksum and signature/provenance mechanism selected before release, then checks an internal manifest. A missing verification method becomes a visible approval gate, never an invented success.

## Upgrade Plan

1. acquire the global lifecycle lock;
2. re-check Phase 0-style disk, memory, systemd, port, owner, and conflicting-unit facts;
3. verify no incompatible Job/session/update is active;
4. download and verify immutable release to staging;
5. run compatibility and migration preflight without changing state;
6. quiesce new mutating requests while keeping status available;
7. drain safe Jobs; mark uncertain Jobs `needs_attention`;
8. create verified SQLite/config/installation-receipt backups;
9. install release directory and frontend assets;
10. apply configuration and database migrations;
11. atomically switch `/opt/agentbox/current`;
12. daemon-reload only if AgentBox units changed;
13. restart Helper, Runtime Executor, Worker, then API in dependency order;
14. run UDS, API, DB, permission, listener, adapter, and Doctor health checks;
15. commit upgrade receipt and release the lock, or enter rollback.

## Database Migration

- Alembic migrations are ordered, reviewed, and tied to release compatibility metadata.
- A SQLite online backup plus integrity check precedes the first schema change.
- Migrations are short and transactional where SQLite supports the operation.
- Destructive schema changes use expand/migrate/contract across releases rather than immediate column/data deletion.
- Application code tolerates the defined rolling boundary only as long as needed for ordered restart; this is not a multi-node rolling-upgrade design.
- A migration that cannot safely reverse marks automatic rollback unsupported and requires explicit confirmation before apply.

## Configuration Upgrade

- Configuration has an explicit schema version.
- Defaults are merged only for absent keys; administrator values are not overwritten.
- Unknown/deprecated keys are reported with migration guidance.
- Generated replacement is written to staging, validated, permissions checked, then atomically renamed.
- Secrets are not migrated because AgentBox config does not store third-party credentials.

## Frontend Static Files

Frontend assets are immutable inside the release directory. They switch with the backend release symlink so API and static assets remain version-compatible. Filenames use content hashes and the HTML shell is served with cache policy that prevents it from pinning a stale asset manifest.

## systemd Restart and Health

- Existing unmanaged units—including the Phase 0 `codex.service`—are never touched.
- Only exact AgentBox unit names are reloaded/restarted.
- Helper protocol compatibility is checked before Worker/API reconnect.
- Runtime sessions continue when compatible; a release that requires Runtime restart declares it and obtains confirmation.
- Health includes correct loopback bind, UDS peer tests, database schema/integrity, Job lease recovery, static/API version match, and no unexpected wildcard listener.

## Automatic Rollback

Automatic rollback is allowed when all are true:

- failure occurs inside the documented health window;
- previous immutable release still exists and verifies;
- previous config snapshot is available;
- database restore is safe and no post-upgrade user mutation must be discarded;
- Runtime/session transition is known reversible.

Rollback stops new mutations, restores SQLite/config if required, repoints `current`, reloads/restarts AgentBox units, runs the previous health check, and records only sanitized outcome metadata.

If any condition is false, the system enters maintenance/`needs_attention`; it does not claim success or repeatedly oscillate versions.

## Manual Rollback

`agentbox update rollback --to <version>` is a local-admin, recent-auth, confirmation-required operation. Dry-run shows:

- program/config/database target versions;
- Jobs or sessions affected;
- data created after the target backup that could be lost;
- whether re-authentication is expected;
- exact recovery and cancellation boundary.

`--yes` cannot bypass the server challenge. Manual rollback never alters projects, third-party auth, firewall, SSH, or tunnels.

## Retention

Keep at least the current and one previously healthy release, associated manifests, and a bounded set of pre-upgrade SQLite/config backups. Retention deletion is a separate confirmed Job. A local backup under `/var/lib/agentbox/backups` is not a disaster-recovery copy.

## Compatibility Policy

- CLI and API major versions must match; minor capabilities are negotiated.
- Helper and Runtime protocols reject unsupported major versions.
- Database downgrade compatibility is declared per release.
- Runtime Adapter changes are tested against saved fixtures; a changed third-party CLI returns Unsupported/Broken rather than unsafe fallback.
- Release notes identify supported OS families and migrations.

## Failure Injection Requirements

Before release, tests interrupt download, extraction, symlink switch, config write, each migration boundary, each unit restart, and health check. They verify either the old version remains healthy, rollback succeeds, or the state is honestly `needs_attention` with no unrelated host modification.

## Phase 0-Specific Gate

The old enabled/inactive `/etc/systemd/system/codex.service`, unmapped UID/GID 1001 Codex files, root Runtime state, port 8000 conflict, and existing cloudflared must be resolved or explicitly excluded before the first real AgentBox install/upgrade test on this host.
