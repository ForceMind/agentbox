# Current Authorized Action

Action ID: `MAC-WAW-NOISE-CORE-2026-09-03`

Owner clarified that development continues on the current Mac. Development
platform and deployment qualification are separate: a missing Linux test host
must not block platform-independent implementation, local tests or Linux CI.
The prior blanket host prerequisite for all remaining software work is superseded
by this clarification; actual host activation, Secret handling, new architecture
decisions and production promises retain their existing boundaries.

## Current slice — fixed Noise NX core

PR #64 completed concrete Runtime composition with 19/19 CI checks and merge
`624b34b656dbf239dbc56fa79d216db7d17a349b`.

- Implement the existing fixed Noise revision-34 NX profile in Python and
  WebCrypto using existing platform cryptographic primitives.
- Compare exact independent pinned Noise-C vectors and run real Python/Node
  interoperability for both roles, AD, tamper and cipher-state lifecycle.
- Require independent security review of handwritten state machines, including
  concurrent destroy, late async results, bounds, key-reference release and nonce
  exhaustion; no production key, socket, plaintext API or terminal activation.
- Update docs and GitHub, require exact-head CI, merge and read back.
- The concrete supplemental application encoding is in
  [WAW_ENCRYPTED_STREAM_DECISION.md](WAW_ENCRYPTED_STREAM_DECISION.md); its three
  previously undefined byte rules are awaiting Owner decision. Noise core work
  continues independently. Do not silently choose application bytes.

## Next implementation and validation

Continue the remaining Runtime command/transport factory, process and encrypted
stream/browser integration on Mac where feasible, using injected OS boundaries
and truthful local/CI evidence. Use the existing architecture contracts; resolve
new architecture decisions explicitly when encountered. Do not substitute Fake
Runtime evidence for actual CLI/PTY/Noise/host qualification or call partial
integration complete.

Linux systemd/cgroup/namespace/LSM/seccomp, real Runtime activation, official
Runtime-user login/Trust, deployment and reboot acceptance still require an
identified authorized target and attributable host evidence before those
operations or readiness claims. A Linux SSH alias is not required merely to
continue software development on this Mac.
