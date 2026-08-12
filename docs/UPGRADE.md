# AgentBox Upgrade

Status: Phase 8 implementation, pending human review

Run `agentbox system update --artifact PATH --sha256 DIGEST` as root after
reviewing `agentbox-install plan`. The operation is serialized by the same
lifecycle lock as install, rollback, and uninstall.

An update verifies the archive checksum, safe extraction policy, manifest,
per-file digests, semantic version ordering, release-local wheel version, and
offline dependency set. It stages a new release rather than overwriting
`current`. Existing AgentBox services are stopped before the SQLite online
backup and migration boundary. After explicit migration, the `current` symlink
is atomically replaced, exact units restart, and health/readiness plus reported
version are verified.

The backup contains the SQLite database, safe AgentBox configuration, any
pre-existing AgentBox units, release/version metadata, and migration revision.
It excludes projects, Runtime HOME, Codex/Claude/gh credentials, root state,
Provider secrets, and arbitrary filesystem content. SQLite uses its online
backup API and an integrity check; a live WAL file is never blindly copied.

The release artifact currently uses SHA-256 checksums and complete file
digests. Signed distribution is a later release gate, so Phase 8 does not claim
complete supply-chain protection. Third-party tools are detected and verified
separately; an update never automatically upgrades an existing Codex or Claude
installation.

If migration or activation fails, the installer stops further forward work,
records completed AgentBox-owned mutations, attempts restoration, restarts the
prior release, and verifies service, endpoints, version, and database backup
compatibility. The result never collapses an attempted rollback into a success.

Database migrations are not assumed reversible. A release manifest declares
backward compatibility; otherwise application rollback requires the verified
pre-change database backup and restore.
