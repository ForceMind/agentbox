# R12-D API disabled profile and singleton lock

Status: software candidate on `codex/r12-api-profile-provision`, 2026-09-28.
The [R12 plan](project/PRODUCTION_READINESS_PLAN.md) and
[API bootstrap contract](WAW_R12_API_BOOTSTRAP.md) govern subsequent mode
changes and host qualification. This batch writes only fixture roots during
development.

Fresh installation creates exactly
`/etc/agentbox/waw-api-profile.v1.json` as root:`agentbox` mode 0440, with
canonical bytes:

```json
{"mode":"disabled","schema_version":"agentbox-waw-api-profile.v1"}
```

An existing profile is never rewritten by this path. The two canonical
`disabled`/`filesystem-v2` byte strings are accepted only when its regular
single-link leaf has the expected owner/group/mode and stable descriptor and
directory-entry identity. Symlink, hardlink, unknown content, oversized file
or concurrent drift fails closed. The installer does not select
`filesystem-v2`; a separate audited CAS mode updater and host read-back are
required before that mode can be enabled.

`/run/agentbox-waw-api` is root:root mode 0755, so the non-root API can
traverse but cannot replace the lock name. The installer and tmpfiles policy
create an empty `waw-api.v1.lock` as `agentbox:agentbox` mode 0444. The API
opens it read-only and obtains the process-lifetime advisory lock. Existing
objects are checked without truncation or replacement. The resource paths
appear in installer plan and transaction inventory; the profile remains
operator configuration across upgrade, rollback and default uninstall.

Local evidence: 143 installer/deployment/API profile loader fixture tests passed
with an x86_64 fixture on macOS; one `systemd-analyze` case skipped because
the tool is not installed. Tests cover exact disabled bytes, accepted enrolled bytes,
invalid content, wrong mode, hardlink, symlink and empty lock identity.
Full Linux-target mypy passed 313 source files; Ruff and Black passed.
Linux CI, real API/Runtime startup, public anchor/manifest, key/Secret,
vendor enrollment, client trust and host PID 1 remain separate gates.
