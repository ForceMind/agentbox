# AgentBox Backup and Migration Design

Status: Phase 1 design baseline

## Objectives

Backups support recovery from host loss, failed upgrade, accidental project damage, and migration to a new server. A backup must be consistent, inspectable, versioned, least-privilege, and explicit about what it does **not** preserve.

`/var/lib/agentbox/backups` is optional local staging/rollback storage, not the only disaster-recovery destination. Operators must copy verified backups to separately protected storage.

## Backup Classes

| Class | Purpose | Contents | Retention |
|---|---|---|---|
| pre-upgrade snapshot | immediate rollback | SQLite, config, receipt, schema/version manifest | current + bounded previous releases |
| configuration/state backup | rebuild AgentBox | non-secret config, SQLite backup, manifests, audit policy metadata | operator policy |
| project backup | recover work | selected Project Workspace content and Git metadata | per project/importance |
| migration bundle | move host | config/state plus project manifests/content as selected | until destination verified |

## What to Back Up

- `/etc/agentbox` non-secret configuration and schema metadata;
- SQLite through the SQLite backup API, including an integrity-check result and schema/application version;
- AgentBox installation receipt, release manifests, and enabled feature/capability observations;
- Project registry and sanitized Git remote metadata;
- selected `/srv/agentbox/projects/<storage-key>` content, including `.git` only when repository history is part of the requested backup;
- non-secret operational settings, migration history, and sanitized Audit Events according to retention policy;
- a manifest of required Linux identities by logical name and ownership relationships, not a demand to reuse numeric IDs.

Immutable AgentBox release artifacts may be re-downloaded from verified origins; including them is optional for offline recovery.

## What Not to Back Up

AgentBox backups must exclude:

- Codex, Claude, GitHub or other tokens;
- raw browser sessions/cookies and recoverable session tokens;
- administrator plaintext password;
- OAuth codes, Pair Codes, SSH private keys, complete auth configuration;
- the complete Runtime Provider Secret Store subtree
  `/home/agentbox-runtime/.local/share/agentbox/provider-secrets/v1`, including
  root keys, `keyset.json`, `store.sqlite3`, rollback journals, ciphertext,
  nonces, tags, wrapped DEKs, lock/staging artifacts, Secret IDs, and key IDs;
- Runtime process memory, environment, tmux pane history by default;
- caches, temporary downloads, sockets, PID files, lock files;
- unrelated `/root`, `/home`, `/etc`, system logs, cloudflared, SSH, firewall, x-ui/xray data;
- userinfo-bearing Git URLs or credential helpers.

Password hashes may be included only in an administrator-approved full state backup protected as sensitive. Session records are revoked/omitted on migration so copied database state cannot replay browser sessions.

An ordinary backup may state only that Provider Secrets are excluded. It must
not enumerate Secret/key identities or record counts. Host-loss recovery
restores non-secret AgentBox metadata, explicitly initializes a new empty
Runtime Secret Store, and re-provisions credentials through a future reviewed
local ingress flow. Slice 3.1 provides no Secret export, import, recovery bundle,
or cross-host encrypted migration.

## SQLite Backup

1. request Worker quiescence for schema-changing work;
2. invoke SQLite online backup from the application data layer;
3. run integrity check on the copy;
4. record database/application/schema versions and digest;
5. fsync file and containing directory as appropriate;
6. move into a new immutable backup directory;
7. never copy only the main database file from an active WAL set.

Backup status and manifest are stored separately from the live database so corruption does not erase all recovery evidence.

## Project Repository Backup

- Backup runs as `agentbox-runtime`, not root, except for a root-owned outer staging/transport step.
- Before backup, record branch, HEAD, dirty/untracked counts, remotes sanitized of credentials, submodule presence, LFS indication, size, and active Runtime sessions.
- A clean repository with a verified remote may use a metadata-only policy if the administrator accepts remote dependency.
- Dirty/untracked work requires a content backup; AgentBox never silently assumes `git push` is a backup.
- Hooks are data only and never executed during backup/restore.
- Symlinks, hard links, special files, and archive paths receive the same containment checks as installation.
- Encrypted destination/transport is an operator responsibility until an approved secret-management design exists; AgentBox must not invent or store encryption passwords.

## Configuration Backup

- Include validated config, schema version, and file ownership/mode manifest.
- Exclude environment snapshots and third-party auth files.
- If future config references an external credential identifier, back up only the reference and document that the credential must be re-provisioned.

## Backup Job Safety

Backup is a durable Job with project/global locks, disk-space preflight, output/size/time limits, progress, cancellation boundaries, and a final digest. Job summaries contain only backup ID, selected resources, size class, destination class, digest, and outcome—never file content.

Backup deletion is a destructive, recent-auth, two-step confirmed operation and is not an MVP must-have.

## Migration to a New Server

### Source

1. run Doctor and resolve corruption/uncertain Jobs;
2. inventory OS, architecture, AgentBox/database/config versions, logical users, projects, Runtime installs/capabilities, sessions, and external access integrations;
3. stop or quiesce AgentBox-managed sessions as required; do not touch unmanaged root sessions;
4. create and verify a migration bundle;
5. transfer through an operator-approved encrypted channel;
6. keep source unchanged until destination validation and rollback window finish.

### Destination

1. run installation dry-run on a supported clean server;
2. install the compatible AgentBox release without importing secrets;
3. create logical users/groups using collision-free destination IDs;
4. verify bundle digest/manifest/version and available space;
5. restore config to staging and validate schema;
6. restore SQLite using the migration compatibility path;
7. restore projects as destination `agentbox-runtime`, checking every path/type/owner;
8. update stored observed UID/GID/path facts to destination policy;
9. revoke imported Sessions and require administrator login;
10. re-detect Runtime installations/capabilities instead of copying executable paths;
11. re-authenticate third-party tools as the destination Runtime user;
12. complete Claude Workspace Trust separately for each concrete project;
13. configure remote access separately and validate loopback bind;
14. run full Doctor and project/session smoke checks.

## UID/GID Handling

Logical identity and ownership policy matter; numeric UID/GID values are host-local. Restore chooses free destination IDs, changes ownership only inside approved AgentBox roots, and verifies no symlink/mount escape. It does not reuse an ID merely because the source used it.

On the current Phase 0 host, UID/GID 1001 is an explicit collision gate due to standalone Codex ownership. No AgentBox user may be assigned that numeric ID until ownership is understood/remediated under separate approval.

## Runtime and GitHub Re-authentication

- Do not copy `/root` or Runtime auth directories into a bundle.
- Codex and Claude log in again using their supported public flows under `agentbox-runtime`.
- GitHub runs `gh auth login` and `gh auth setup-git` manually as the Runtime user when required; AgentBox records only status.
- New devices generate new Codex Pair Codes; old codes are not recoverable.
- Authentication APIs that are absent/unstable are reported Unknown/NeedsAttention with manual instructions.

## Existing `/root/projects` Migration

Legacy root projects use the adoption flow in `PERMISSIONS.md`: read-only inventory, backup, copy-to-staging, safe ownership conversion, Git verification, atomic activation, and retention of the original. AgentBox never treats `/root/projects` as its default or moves it during installation.

## Restore Verification Checklist

- [ ] bundle manifest/digest and source version verified;
- [ ] destination OS/systemd/architecture supported;
- [ ] AgentBox binds only loopback and UDS permissions pass;
- [ ] database integrity/schema and migration history valid;
- [ ] no active browser Session survived migration;
- [ ] non-secret configuration validates;
- [ ] each project remains beneath root, contains no escape, and is Runtime-owned;
- [ ] Git branch/HEAD/dirty counts match expected source snapshot;
- [ ] Runtime commands are newly detected through stable entrypoints;
- [ ] Codex/Claude/GitHub auth is re-established manually where desired;
- [ ] Workspace Trust is project-specific;
- [ ] no root/unmanaged session was adopted;
- [ ] Doctor and core flows pass;
- [ ] external tunnel/proxy policy was independently reviewed;
- [ ] source remains available until operator signs off.

## Failure and Rollback

Restore writes to staging and switches into place only after verification. If destination validation fails, stop AgentBox destination services, restore the destination pre-restore snapshot, preserve the failed staging evidence, and keep the source active. Never “repair” by deleting the only backup or original project.
