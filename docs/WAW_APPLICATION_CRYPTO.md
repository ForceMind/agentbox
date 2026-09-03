# WAW application cryptography

R4 implements the accepted
[application contract](project/WAW_ENCRYPTED_STREAM_DECISION.md) using the existing
fixed Noise NX and opaque AWCE cores. The Owner delegated software decisions;
acceptance is recorded in [GOVERNANCE](project/GOVERNANCE.md). This document
describes implemented cryptographic components, not an admitted terminal.

## Context and endpoint ownership

The pure Python `waw_crypto_context` and Web `wawCryptoContext` modules validate
the exact 13-field AdmissionTuple, derive its exact 15-field HandshakeContext,
and serialize the canonical prologue without rounding uint64 values. They copy
validated input and reject unknown fields, modes, types and invalid encodings.

| Endpoint | Python API | Web API |
| --- | --- | --- |
| Browser initiator | `BrowserCryptoProfile`: `start`, `receive_attest`, `receive_ack`, `encrypt_input`, `decrypt_output` | `WAWInitiator`: `writeKeyInit`, `readKeyAttest`, `readKeyConfirmAck`, `encryptInput`, `decryptOutput` |
| Runtime responder | `RuntimeCryptoProfile`: `receive_init`, `receive_confirm`, `decrypt_input`, `encrypt_output` | `WAWResponder`: `readKeyInit`, `readKeyConfirm`, `decryptInput`, `encryptOutput` |

The Runtime caller supplies its in-memory static key. The browser caller supplies
an independently trusted static-public-key fingerprint and bound context. No
file loader, trust-provider enrollment, Provider Secret, CLI, socket or browser
storage access is added. The Web responder supports cross-language/native test
composition; it does not supply the real Runtime's private key to a browser.

## Implemented handshake and channel rules

- Four exact flat key-frame profiles enforce the accepted metadata fields,
  canonical base64url, fixed Noise message lengths and duplicate ephemeral-key
  equality. The browser verifies the recovered static key against both the
  independently supplied pin and declared fingerprint.
- The Runtime generates exactly 32 challenge bytes using its CSPRNG. Every
  32-byte result is valid, including an all-zero result; a nonzero test is not an
  entropy-health proof. Wrong type/length and RNG failure close the profile.
- Both confirmation operations consume their direction's Noise `n=0` with empty
  AD. The browser confirmation binds the challenge and final transcript hash;
  the Runtime ACK uses the fixed canary and exact transcript hash.
- First INPUT/OUTPUT uses `n=1`. The immutable AWCE header, raw final `h` and exact
  direction label form AAD; context ID is `h[:16]`. Input is 1..16384 bytes and
  output 1..32768. Sequence, direction, tag, context and cursor mismatches fail
  closed; there is no counter skip, decryption retry or plaintext fallback.
- The output caller supplies the independently selected/expected cursor. Send
  and receive require strictly increasing valid output cursors and exact incoming
  equality. Ring selection, GAP policy and cursor authority are external.
- Destroy/failed authentication closes both directions. Reconnect creates a new
  profile and fresh keys. Public metadata is not permission to reuse a closed
  CipherState or create a new nonce counter.

## Publication, concurrency and deadlines

One original five-second admission deadline covers the handshake. Python uses
monotonic seconds and exposes `check_deadline()`; its future owner must call it
from the bounded idle admission timer. Web uses monotonic milliseconds and an
idle timer. Calls and final handshake completion also check the same deadline.

Python serializes cryptographic state with an `RLock`. `destroy()` publishes a
permanent closing Event before waiting for cleanup; in-flight calls check that
fence before publishing a result. Readiness has a separate publication Event,
set only after the final deadline/closing guard succeeds. `crypto_ready` therefore
cannot expose a provisional `CRYPTO_READY` phase, and closing always overrides it.

Web handshakes are exclusive; ready profiles have separate send/receive lanes,
so one operation in each direction may overlap. Same-direction overlap fails
closed. A shared operation epoch and destroy fence prevent late AES/DH/hash
completion from publishing success after invalidation. Neither implementation
exports channel keys or accepts a caller-selected nonce.

Cryptographic readiness is distinct from `ADMITTED`, a writer lease, process
readiness and trusted deployment. R6–R9 must enforce those independent conditions
before releasing input/output. This increment does not enable Workspace controls.

## Evidence

- Root Python context/profile plus existing Noise/AWCE regression: **560 passed**,
  exit 0. The two new Python suites alone contain 502 passing cases.
- Web context/profile: **148 passed**, exit 0; includes duplex overlap and
  asynchronous destroy/failure barriers, pin/context/canary/size/cursor rejection.
- Independent sol review found and verified fixes for two Python P1 issues:
  destroy waiting before invalidation, then provisional readiness publishing
  before its final guard. Final targeted re-review passed, including original
  reproductions. Additional independent Web schema/AEAD negatives passed.
- [Public vector provenance](../tests/fixtures/waw_crypto/NOTICE.md) explains the
  separate primitive reference and its upstream Noise-C check. Both actual
  Python/WebCrypto roles match the complete fixed application vector, then pass
  minimum/maximum active payloads and tampered/original-counter retry rejection.
- `node scripts/run-e2e.mjs`: exit 0, **62 passed in 45.3s** on the local Mac.
  The new native Chromium desktop/mobile cases verify exact vector bytes,
  nonextractable keys, same-profile duplex operations and both-direction fences.
  API/preview cleanup completed; no real CLI, user credential or host was used.
- An earlier local E2E attempt exited 1 during build because the parallel R5 test
  file was still being written. It did not reach browser execution; after that
  file became valid, the complete rerun above passed. No check was disabled.
- Scoped type/lint/format and documentation-link checks passed. Exact-head CI and
  merge/read-back are recorded separately in CURRENT_STATE.

Native tests execute real component code with public fixture material in a test
realm. They do not certify the eventual WAW CSP, trusted provisioning, actual
terminal rendering or Linux process isolation. Those remain in
[REMAINING_PLAN](project/REMAINING_PLAN.md).
