# R12 fixed vendor enrollment input

Status: Runtime software candidate, 2026-09-29. This is a non-secret input
contract for C3-b and R12-D/G/H; it is not a target enrollment receipt or
permission to read a real CLI login. The approved
[R12 plan](project/PRODUCTION_READINESS_PLAN.md) remains authoritative.

The Runtime reads only
`/var/lib/agentbox-waw/vendor-enrollment.v1.json`. For the fixed AgentBox-owned
vendor release, qualification is produced in isolated Linux CI from the pinned
official artifacts: exact decoded ELF SHA-256, exact version output and the
Codex unauthenticated digest observed through the production native auth helper.
The target installer does not execute a vendor CLI to recreate those facts.
It may publish them only after the verified v2 executable inventory and a fresh
held-file re-read prove that the installed `/usr/local/bin/claude` and
`/usr/local/bin/codex` bytes match the qualified release exactly.

The record is not generated from a fake vendor, current developer Mac,
environment variable, API request, Browser, Worker or Provider Secret. A
missing or mismatched qualification fails closed.

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

Web/API/Worker cannot read the installed record. The local root installer
may inspect its non-secret contents only for fixed publication/recovery;
Root Helper gains no action or Secret authority. The Runtime process
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

## Shared encoding and failure-path evidence

`encode_waw_vendor_enrollment` is a data-only entry point for the later
installer transaction. It rejects unknown/missing fields, non-string or
oversized values and invalid authority/version fields before returning the
same bounded canonical bytes accepted by the Runtime reader. It performs no
filesystem I/O and does not attest to how the values were observed. The
installer must still bind actual target observations to its verified manifest
and publish/recover the fixed record; this helper does not complete that work.

Fixture tests replace the leaf file or its parent during a held-descriptor
read, using identical content. Both replacements are rejected. An injected
descriptor-close error rejects the record and still attempts the remaining
descriptor cleanup. These are portable software failure-path checks, not
real Linux enrollment or independent security-review evidence.

## Local installer publication

For the fixed AgentBox-owned vendor set, the preferred path is
`agentbox-install enroll-qualified-waw-vendors`. It accepts no version or
digest arguments and executes no vendor process. It requires a completed
installation, safe disabled API/Runtime profiles and the fixed, fully
cross-pinned v2 manifest resources. The executable inventory must name exactly
the qualified `/usr/local/bin` vendor paths and pin the qualified final ELF
digests; the installer re-reads those executable bytes through the existing
no-follow/provenance-checked manifest issuer immediately before publication.
Manifest and executable observations are revalidated during the atomic
publication transaction.

The older `agentbox-install enroll-waw-vendors` remains available for
explicit independently qualified values with `--plan`, `--recover` and
optional JSON metadata output. Neither path performs Provider login, reads
Runtime credentials or starts a service. Host/epoch/digest pins come from the
verified manifest, not user flags. Both share the installer lifecycle lock.

The current fixed qualification is Claude 2.1.286 with ELF SHA-256
`fe503f65c6289d59c23e5b21ae44f03583f997dd33a2cbfc75ab4f96fb8fc73f`,
and Codex 0.159.3 with decoded ELF SHA-256
`8bf204b36a2f6dd0dab73aa2f639892e67ef9ac8befccb4a05b1496ebf25c479`.
The production native auth helper observes the empty qualified Codex HOME as
exit 1 with framed stdout/stderr SHA-256
`76522c70a3df95fdd59bc4851200017bf42947a49d47e216c95bb0dea1579d9c`.
A simpler empty-HOME subprocess produced a different digest and is therefore
diagnostic only, not enrollment authority.

Publication uses a fixed root-private 0600 pending file, finishes and fsyncs
its content, changes it to root:Runtime 0440, then links it into the fixed
record name without replacing an existing file. The final single-link
record is re-read after unlinking the pending name and fsyncing the directory.
An interrupted operation requires explicit recovery with the same observation.
An owned private partial stage can only resume an exact canonical prefix;
unknown data, a truncated ready stage, foreign links, path replacement or
manifest/profile drift fail closed. A differing existing record is never
replaced; vendor rotation needs its own future closed-mode transaction.

This closes fixed-release non-executing automatic enrollment for the currently
qualified AgentBox-owned vendor binaries. It does not qualify an authenticated
user session, runtime-mode activation, the complete fresh-install composition or
a usable product release. Runtime still performs the actual bounded native auth
probe before interactive Start/Resume. Real user input is not logged or placed
in this non-secret record.
