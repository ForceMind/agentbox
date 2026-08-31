# WAW-1 Host-Gate Readiness Checklist

This checklist is an execution contract for a future disposable Linux host
validation. It is not evidence that the host exists or that any item passes.
The agent must not access Provider credentials, login state, cookies, tokens, or
private keys while collecting evidence.

## Gate ordering

Run the gates in order. A missing, malformed, contradictory, or unverifiable
result is `BLOCKED`; there is no plaintext or compatibility fallback.

1. **Repository and artifact identity** — the installer-owned
   `RuntimeHostInstallation`, `project-root.v1`, `cgroup-delegation.v1`, and
   `api-host-anchor.v1` manifests are root-owned, immutable by Runtime/API,
   canonical, cross-pinned, and verified through no-follow descriptors and
   second `fstat` checks.
2. **Runtime epoch and provenance** — the Runtime-only epoch counter advances
   monotonically; the service PID, control socket inode, peer credentials,
   executable/template digests, and host revision are read back and bound as a
   single attestation.
3. **systemd and cgroup** — the dedicated WAW sockets are systemd-precreated;
   the exact approved `Delegate`/`DelegateSubgroup`, process-lifecycle policy,
   controller set, limits, `cgroup.events`, and same-UID write-denial behavior
   match the immutable policy. The selected values remain an Owner/host gate.
4. **Process isolation** — PTY/devpts, `openpty`/`setsid`/`TIOCSCTTY`,
   process-group and `pidfd` stop semantics, namespace topology, seccomp, LSM,
   and `PrivateDevices` behavior are demonstrated on the target kernel.
5. **Transport** — authenticated WebSocket upgrade, the approved Noise
   protocol revision and transcript/payload binding, replay/epoch fences,
   bounded ABWS framing, and no-plaintext API/proxy behavior are verified with
   synthetic canaries. Exact cryptographic parameters require a separate
   Architecture/Owner decision before host validation.
6. **Claude readiness** — the Runtime user locally completes Claude login and
   Workspace Trust on the isolated disposable host. Only redacted readiness
   states are returned; credentials and auth directories never enter AgentBox
   API/Worker or this agent's context.
7. **Failure and recovery** — start/attach/reconnect/detach/stop races,
   Runtime/API restart, host reboot, cgroup cleanup, stale tickets, and
   generation fencing produce the documented bounded states.

## Evidence status

Every item below must carry exactly one status in the eventual evidence
package: `PASS`, `BLOCKED`, `UNKNOWN`, or `NOT RUN`. This checklist currently
has no host observations, so all items are `NOT RUN` until an authorized
operator supplies redacted evidence.

## Required evidence package

- Target distro, kernel, architecture, systemd version, and Runtime UID/GID.
- Redacted manifest/anchor digests and schema versions (never raw key material).
- Socket owner/mode/inode and `SO_PEERCRED` observations.
- Cgroup path, controller and limit read-back, `cgroup.events`, and cleanup
  proof for each synthetic generation.
- Process-tree/pidfd/PTY/tmux provenance with command arguments represented only
  by fixed contract identifiers.
- Noise/WebSocket/ABWS vector results and browser E2E artifact scans showing no
  terminal payload, ciphertext, credential, or ticket persistence.
- Claude readiness classification and operator attestation without login output.
- Exact test commands, exit codes, timestamps, host revision, and Runtime epoch.

## Governance stop

The checklist may be prepared and reviewed in a Draft PR. It does not enable
production routes, real PTY/WS/Noise, service activation, Provider login,
deployment, or the next Slice. Host evidence must be supplied by an authorized
operator, and implementation/merge decisions remain bound to the exact PR
head/base and Owner gate.
