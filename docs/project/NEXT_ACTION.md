# Current Authorized Action

Action ID: `MAC-WAW-NOISE-CORE-2026-09-03`

Owner clarified that development continues on the current Mac. Development
platform and deployment qualification are separate: a missing Linux test host
must not block platform-independent implementation, local tests or Linux CI.
The prior blanket host prerequisite for all remaining software work is superseded
by this clarification; actual host activation, Secret handling, new architecture
decisions and production promises retain their existing boundaries.

## Completed slice — fixed Noise NX core

PR #65 completed fixed Python/WebCrypto Noise NX cores, pinned independent
vectors, concurrency/failure regressions and both-role interoperability:
head `6d0c0f8ff8b452fd0288d6ac98b1f3fe79352ed7`, 19/19 checks SUCCESS,
merge `f95d1a4b0f0bdbdda45bd8da6cc10f3f8ac10269`.

## Next slice — application profile decision

Status: **未开始 — concrete architecture byte rules await Owner confirmation**.

[WAW_ENCRYPTED_STREAM_DECISION.md](WAW_ENCRYPTED_STREAM_DECISION.md) proposes
exact `protocol_id`, final Noise hash usage and direction-label/AAD bytes that
were absent from the historical document. The proposal is reviewable and has
been presented to Owner. Do not silently treat it as approved or implement
alternative bytes while waiting.

After approval, implement the strict context/confirmation/AWCE codecs, Runtime
stream server and API ciphertext-only relay with staged admission, then browser
terminal integration. Require independent review, exact cross-language vectors,
normal/failure/cancellation tests and per-stage GitHub/document delivery. Keep
all existing real-key/host/production authorization and evidence boundaries.

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
