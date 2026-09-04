# Managed browser trust provider

R9 implements the software boundary selected for independent browser trust:

```text
AgentBox page
  -> Chromium-owned external runtime.Port
  -> force-installed MV3 trust bridge
  -> Chrome Native Messaging
  -> fixed native bridge
  -> trustd Unix socket
  -> agentbox-browser-trustd
```

The Web/API/Runtime server cannot install trust records, reset a floor, choose
trusted time or synthesize provider invalidation. The page has no fallback to
HTML, API metadata, DOM events, `postMessage`, localStorage, IndexedDB, a service
worker or a localhost HTTP broker.

## Source-build and deployment boundary

`clients/browser-trust/extension` is a separate pnpm workspace. Its ordinary
build is intentionally inert: `manifest.json` has no `externally_connectable`
entry, no signing key and no update URL. Source tests can validate the fixed
protocol, but the build cannot enable production Connect.

`agentbox-browser-trust-package` requires all public deployment inputs at once:

- the CRX public key and matching 32-character Chrome extension ID;
- one canonical HTTPS AgentBox Origin and HTTPS update URL;
- the enrolled `trustd` installation-key SHA-256 fingerprint;
- one to 32 exact browser-client UIDs.

It derives the extension ID from the CRX public key and rejects a mismatch. The
output cross-pins the production MV3 `externally_connectable` match, Native
Messaging `allowed_origins`, Chrome force-install/update policy, extension
managed-storage fingerprint/origin and root-owned trustd client policy. It writes
no private key, browser profile, API cookie, Runtime secret or terminal data.

The Linux systemd asset runs `trustd` under its own identity with a private state
directory and a fixed Unix-only read path. The actual package install, user/group
creation, Chrome policy placement and extension signing remain inert until R12.

## Trust authority and store

The Python `agentbox_browser_trust` package independently verifies the frozen
canonical bootstrap/root/pin schemas and Ed25519 domain-separated signatures.
It enforces the fixed bootstrap digest, 4 KiB record and 64-root limits, safe
revisions, final trusted-time validity, supersession/revocation, canonical Origin,
pin/host identity and non-decreasing root/pin floors.

The service-owned store uses a generated raw Ed25519 installation key held in a
service-owned mode-0600 file. It is never exported to Web/API or included in the
public deployment bundle. The store also uses mode-0600 state, a bounded chained
append-only rotation/floor journal, a separately signed trusted-time high-water,
atomic state replace,
file and directory fsync, exact owner/mode/type checks and a closed directory
inventory. A state/journal mismatch, backward time, unsafe mode, unexpected file,
network-policy failure or missing installation key makes the provider unavailable;
it never initializes a replacement floor automatically.

A successful successor-root installation creates a durable checkpoint while
the exact predecessor is still valid. It binds `accepted_at`, the accepted
root/signer and the complete canonical root-history digest, and is committed
with the history, tombstones, floors and provider epoch. Each later active-root
rotation verifies the old exact prefix and checkpoint before advancing the
cumulative proof; pin-only updates and terminal revocation preserve it. Restart
validation checks the checkpoint's direct signer/root pair at `accepted_at` and
the current root/pin at final trusted time, without requiring every older ancestor
to remain valid at later rotations. Missing, late, truncated, forked, modified
or independently rolled-back checkpoint state fails closed. A privileged
consistent rollback of the entire key/state/journal/time store has no external
generation anchor and can remain self-consistent while an older pin is still
inside its validity/skew window.

Before returning a snapshot the provider verifies DNS/network policy and persists
a time high-water. `production` rejects private, loopback, link-local, multicast,
unspecified and reserved resolutions; `loopback-development` accepts only
loopback. Provider rotation changes `provider_epoch`; an old document receives
`changed` on its next fixed interaction and cannot continue authorization.

The signed time file detects a backward wall clock while its latest service-owned
state remains intact. This software mechanism does not survive a privileged
consistent filesystem rollback during an older pin's validity/skew window, with
or without a matching host/VM clock rollback, and it does not claim TPM-backed
monotonic time. R12 must qualify the target's clock, backup/restore and snapshot
policy; a deployment requiring resistance to privileged rollback must add an
external monotonic or hardware-backed anchor.

## Fixed session protocol

The extension accepts only a top-level, non-incognito `/workspace` document whose
browser-supplied Origin, URL, frame and document ID agree with managed policy. It
opens only `com.forcemind.agentbox.waw_trust`. The Native Host verifies a
domain-separated `trustd` installation signature before forwarding page traffic.

Messages bind protocol version, 32-byte page nonce, document, Origin, provider
installation/epoch, decimal uint64 sequence and correlation ID. Page/native
requests are at most 4 KiB; provider responses are at most 512 KiB; each public
record remains at most 4 KiB. Unknown fields, sequence gaps, wrong nonce,
deadline, port loss or malformed base64 close the port and invalidate the lease.

The production Web adapter is compiled with a nullable generated extension
identity. It returns no provider while that identity is absent. A successful
snapshot still passes the existing browser record/policy verifier and grants only
a generation-bound public pin lease; it does not grant Noise, ADMITTED, terminal
input or process authority.

## Locale and client support

Trust errors are presented through the browser UI locale: only a first browser
language whose primary tag is `zh` selects `zh-CN`; every other/malformed value
selects English. Protocol types, error codes, IDs and signed records remain
English ASCII and are not localized.

The first production qualification target is managed Google Chrome desktop on
Linux x86_64. macOS, Windows, Edge, Android and iOS remain unsupported for
production Connect until their native service, policy and store durability are
implemented and qualified. Mobile Web may continue metadata and exact Stop, but
responsive viewport tests are not mobile trust-provider evidence.

## Current software evidence

- Browser record/policy/provider/adapter repair: 121 targeted tests.
- Terminal tokenizer/model/scheduler repair: 185 targeted tests plus two Unicode
  generator checks.
- Browser locale/controller/Workspace shell: 41 targeted tests.
- Managed Chromium adapter: 5 targeted tests.
- MV3 bridge protocol: 4 targeted tests plus type/lint/format/build.
- Python trust provider/store/native/package core: 13 targeted tests plus
  Ruff, Black and strict mypy.
- Root Web matrix: 915 tests; desktop/mobile browser E2E: 64 tests.
- The real production `dist` six-file inventory passes the public-only deployment
  bundle gate with an ephemeral test RSA key and derived extension ID.
- Original PyCA fixture check: bootstrap digest, three signatures and nine
  mutations.

These are local software results. Independent review passed with no remaining
P0/P1/P2; full exact-head CI and merge are still pending. R12 must prove the
signed CRX, managed Chrome policy,
Native Host manifest/path, trustd identity/socket/store, restart/rollback/time/DNS
behavior and active attachment teardown on an authorized disposable target.
File permissions do not provide hardware-backed non-exportability. If deployment
policy requires that stronger property, R12 must add and qualify TPM/HSM-backed
key custody before production activation.
