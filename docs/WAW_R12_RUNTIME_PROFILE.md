# R12 Runtime fixed deployment profile

Status: software candidate on `codex/r12-runtime-deployment-profile`,
2026-09-28. The [R12 plan](project/PRODUCTION_READINESS_PLAN.md) governs
production composition and host qualification. This batch does not change
any real host profile, socket or key.

Production Runtime reads only
`/var/lib/agentbox-waw/runtime-profile.v1.json`. The installer creates the
canonical `disabled` bytes as root:`agentbox-runtime` mode 0440 beneath its
existing root:`agentbox-runtime` mode 0750 parent:

```json
{"mode":"disabled","schema_version":"agentbox-waw-runtime-profile.v1"}
```

The only other recognized value is `filesystem-v2` with the same schema and
canonical serialization. Existing exact bytes are preserved during
upgrade; arbitrary environment, request or CLI input cannot select a mode.
The loader walks from `/` using no-follow held directory descriptors,
requires root ownership and no group/world write along ancestors, and
checks the fixed parent, regular single-link leaf, exact group/mode,
bounded bytes and descriptor/entry identity before and after reading.
A proven absent leaf on a safe parent retains disabled compatibility for
older installations; unsafe parent, missing group, links, malformed bytes
or read drift fails closed. The observation is revalidated before Runtime
starts listening.

The existing Runtime `_main` serves its legacy typed socket only for a
current `disabled` profile. An explicit `filesystem-v2` profile currently
raises before constructing that legacy listener. The next C3-b batch must
replace this deliberate rejection with one `WAWRuntimeApplication` graph;
the Runtime must never silently downgrade to legacy on a composition error.
The API and Runtime profiles are separate resources. A later installer CAS
mode update must coordinate them with drain/stop, prerequisites, restart,
read-back and recovery; this slice provides no mode-changing command.

Local evidence: 121 installer/profile cases passed with one macOS
`systemd-analyze` skip under an x86_64 fixture; 16 focused Runtime
profile/entrypoint cases passed; Linux-target mypy covered 315 files.
Eight older Runtime RPC socket cases failed on macOS because peer admission
requires Linux `SO_PEERCRED`, so their Linux CI result remains necessary.
No claim is made for real PID 1 sockets, key custody, vendor CLI login,
browser trust or production readiness.
