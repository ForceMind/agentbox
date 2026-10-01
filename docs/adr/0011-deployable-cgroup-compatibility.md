# ADR 0011: deployable Runtime cgroup compatibility

Status: **Accepted alternative A for software implementation — Owner instructed
the recommended plan on 2026-09-30. Activation requires actual evidence**.
This preserves the full deployment goal; neither alternative is qualified yet.

## Verified conflict

The existing v1 cgroup manifest requires `protect_control_groups="private"`,
`Delegate=true`, fixed limits and a one-component delegate subgroup. The
Runtime verifier currently expects that subgroup directly below `/sys/fs/cgroup`.
The installed legacy Runtime unit uses `ProtectControlGroups=true` and has no
delegation. Existing Ubuntu 24.04/OpenCloudOS baseline evidence names systemd
255, which does not support the private value. These records cannot be
truthfully turned into an active WAW manifest by filling in hashes.

Official versioned sources: [v255 exec manual](https://raw.githubusercontent.com/systemd/systemd/v255/man/systemd.exec.xml)
and [v256](https://raw.githubusercontent.com/systemd/systemd/v256/man/systemd.exec.xml)
accept booleans only; [v257](https://raw.githubusercontent.com/systemd/systemd/v257/man/systemd.exec.xml)
adds private/strict cgroup namespace mounts. The Installer's compatibility
check now distinguishes values and rejects private/strict below 257. This
correction leaves the existing boolean legacy service compatible.

## A: compatible delegated-subtree architecture

- Keep legacy distro support and design a distinct, versioned WAW policy for
  systemd 255. The only writable cgroup area is the exact delegated service
  subtree; all other cgroup paths remain read-only and kernel permissions
  deny cross-user writes. Do not globally disable cgroup protection.
- Use an explicit service/supervisor/workload hierarchy. Freeze the exact
  service-relative path and validate real mount/namespace/ownership/limits;
  do not reinterpret the old single-component/private manifest as equivalent.
- Service-level cgroup namespace isolation differs from the private profile.
  Vendor sandbox/namespace, Root Helper exclusion, Runtime Secret authority,
  allowlisted actions, PID/FD identity and exact Stop remain mandatory.
- Prove the selected unit's read-only mount plus scoped writable delegation
  on actual systemd 255, deny sibling/outside writes, and test supervisor
  survival, admission, cleanup, restart and recovery. If that combination
  cannot be proved, fail closed and revise the proposal; no fallback to an
  unrestricted cgroup mount is authorized.

## B: private-namespace profile on newer systemd

- Keep the private policy and require systemd >=257 for WAW; older systems
  retain legacy core support but do not gain a WAW-ready claim.
- Observe the real private namespace root and delegate hierarchy. Correct
  the existing path assumptions through a versioned, bounded manifest;
  do not invent host mount IDs or issue an installer-namespace observation
  as a Runtime-namespace fact.
- Qualify an actual distro/image, native PID 1, delegation and limits before
  promising a deployable target. Current 255 CI is insufficient. Do not
  replace a server's systemd from an arbitrary download during installation.

## Decision and follow-up

### Positive absence during restart recovery — 2026-10-01

Under the existing software-decision delegation, Runtime-only recovery uses
`waw-cgroup-absence-attestation-v2` when the exact generated Workspace directory
is absent under the current verified scoped delegate. A pathname failure alone
is insufficient: two no-follow stat lookups must return ENOENT, the held
service/delegate FDs must have the Runtime owner and current verified mounts,
and the durable old logical identity/path must match. EACCES, missing workload
inside an existing Workspace, reappearance, bad owners and mount drift fail
closed. Runtime may provision only the already-approved fixed delegate root;
it does not create/adopt an absent old generation.

The new record explicitly sets workspace_presence=absent and uses the literal
absent marker for Workspace/workload device/inode. Service/delegate physical
identities are measured. Limits remain historical policy values, not measured
values for nonexistent groups; zero state flags mean absence under this schema.
The v1 encoder is unchanged for present records; downgrade and mixed physical
identity are rejected. Ordinary store writes cannot publish absence: only the
explicit latest-generation recovery CAS, followed by host/binding-preserving
floor migration, may commit it. No Browser/API path, command or recovery grant
is introduced. Linux producer evidence and full reboot acceptance are distinct.

After that acknowledgement, Runtime may remove only the exact durably empty
old Workspace/workload directories. It rechecks held FD device/inode/owner,
mount/limits, populated=0 and the closed child-directory layout; kernel busy
or unknown children retain quarantine. No kill or recursive removal exists.
An interrupted workload-only removal may resume from the stored empty record,
then requires fresh positive absence. Same-epoch present-to-absent CAS is limited
to a prior EMPTY_DURABLE record with the same invocation and exact unchanged
service/delegate identities. Ordinary live/same-epoch drift remains rejected.

### Restart-safe installation observations — 2026-10-01

The accepted scoped implementation cannot persist an installer's numeric mount
ID as a Runtime namespace ID. Mount IDs belong to the current namespace; the
kernel cgroup superblock device is also a boot observation. Pinning those
numbers at installation would make normal service/host recovery depend on
stale observations. This correction is resolved under GOVERNANCE's current-task
software-decision delegation, within alternative A; host qualification remains
separate.

The v2 bundle has a closed `runtime-namespace-v1` binding mode. ProjectRoot uses
that exact label in root_device/root_mount_id and pins the positive filesystem
ID plus root inode as `fsid:<uint64>;inode:<uint64>`. Runtime still verifies the
held directory against the fixed installed path, UID/GID/mode, filesystem/inode,
and its actual FD mount ID/device in current mountinfo. Changing the filesystem
or recreating the root requires explicit re-enrollment; no automatic fallback
to a new root is provided. A missing/zero filesystem ID fails closed.

Scoped cgroups use the same namespace label in cgroup_mount_device plus the
fixed `scoped-runtime-cgroup2-v1` identity. Runtime derives the device from the
held FD and verifies it against the exact scoped RW mount and same-device RO
global mount; outside RW mounts, wrong paths/owners and controller/limit drift
still fail. The v2 cross-pin rejects mixed namespace/numeric profiles; v1 cannot
use this mode. Legacy numeric/private vectors retain their existing semantics.

Installer enrollment must pin the three native helpers below one immutable
`/opt/agentbox/releases/<version>/libexec` directory. The closed helper names,
version grammar, digests and root-owned no-follow descriptor checks stay; mixed
releases or arbitrary roots are rejected. The existing `current` symlink remains
the service upgrade pointer but is not the new inventory's executable authority.

The CI-only PID-1 probe now runs two scoped services with ProtectSystem/PrivateTmp
and records actual namespace/mount IDs plus physical filesystem identity. Its
results and the real Linux ProjectRoot FD test are required evidence for this
software batch, not a claim of vendor, reboot or complete installation readiness.

Owner selected compatibility-first A; B remains an alternative if A cannot be
proved safely. Both require exact
implementation/host evidence and retain PC/mobile browser scope and all
later capabilities. Until selected, no enabled profile or fabricated cgroup
manifest is published. Non-secret resource work may continue when independent;
Secret key lifecycle and Web trust authorization remain separate.
