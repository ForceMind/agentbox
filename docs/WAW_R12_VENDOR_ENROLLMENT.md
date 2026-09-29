# R12 fixed vendor enrollment input

Status: Runtime software candidate, 2026-09-29. This is a non-secret input
contract for C3-b and R12-D/G/H; it is not a target enrollment receipt or
permission to read a real CLI login. The approved
[R12 plan](project/PRODUCTION_READINESS_PLAN.md) remains authoritative.

The Runtime reads only
`/var/lib/agentbox-waw/vendor-enrollment.v1.json`. The installer or a later
explicit enrollment operation must create the record after observing the
exact target binaries and the bounded unauthenticated Codex probe output.
It is not generated from a fake vendor, current developer Mac, environment
variable, API request, Browser, Worker or Provider Secret. A missing file
fails closed. No code in this batch creates the file on a host.

The canonical JSON object has these exact keys, ASCII JSON with sorted keys,
compact separators and one trailing newline, at most 1024 bytes:

| Field | Meaning |
| --- | --- |
| `schema_version` | Fixed `agentbox-waw-vendor-enrollment.v1` |
| `runtime_host_installation_id`, `runtime_host_installation_revision` | Exact enrolled host tuple |
| `host_manifest_digest` | SHA-256 of the verified v2 Runtime manifest |
| `enrollment_epoch`, `enrollment_state` | Exact v2 manifest epoch and `bootstrap`/`steady`/`rotation` state |
| `claude_vendor_version`, `codex_vendor_version` | Exact observed printable version strings, 1–96 bytes |
| `codex_unauthenticated_output_sha256` | Lowercase SHA-256 of the target's enrolled fixed unauthenticated output |

Only `agentbox-runtime` may read the installed record. The Runtime process
checks its real/effective/saved UID/GID against that non-root account. The
reader walks from `/` with held no-follow descriptors, requires root-owned
non-writable ancestors, the root:`agentbox-runtime` 0750 final directory,
and a single-link root:`agentbox-runtime` 0440 regular file. It bounds the
read, compares descriptor and directory-entry identity before and after,
and rejects uncertain descriptor cleanup. Its digest and held identity are
retained as a non-secret observation for an exact re-read before resource
construction. Diagnostics never include version strings or raw file bytes.

The authority-deferred production provider requires that record, compares
host ID/revision, manifest digest and enrollment epoch/state against the
builder's one `WAWVerifiedExecutionAuthority`, then re-reads the fixed file
before opening any executable, policy or cgroup descriptor. Only then does
it pass the three validated values to the existing native auth-probe
profiles. A stale file, different authority, absent target value or failed
re-read cannot publish an executor or consume an epoch.

This closes the **software source and pinning** dependency, not `_main`.
The installer still needs a versioned enrollment/rollback transaction and
fixed target artifacts, and C3-b still needs the positive bounded legacy
Codex Remote state source and single application graph. Linux PID 1 sockets,
real CLI login, host isolation and reboot recovery remain `NOT RUN` until a
specific host/client tuple and authorization are supplied. Tests use only
synthetic fixture records and never write the fixed production path.
