# Browser public trust records

R9's `wawTrustRecords.ts` implements closed record decoding and Ed25519 signature
checks. Status: the lifecycle/provider review findings are repaired locally and
the managed Chromium/trustd provider core is implemented and independent review
passed; exact-head CI and merge remain pending.
It does not install policy, maintain revision floors, choose a trustworthy clock,
authorize an attachment or enable the terminal.

## Contract and APIs

`parseBootstrapRecord`, `parseRootRecord` and `parsePinRecord` consume at most
4 KiB of canonical UTF-8 JSON. They return owned frozen records. Unknown,
duplicate, missing or extra fields, nested values, non-ASCII schema values,
alternate escaping/whitespace, invalid UTF-8/BOM and noncanonical number tokens
are rejected. Only the fixed safe signed-integer range is admitted; wire uint64
strings remain a different domain.

This full-record canonical import boundary is accepted in the
[browser implementation decision](project/WAW_BROWSER_IMPLEMENTATION_DECISION.md).
The underlying fields, signed bytes and fixtures are already fixed by the
[accepted stream supplement](project/WAW_ENCRYPTED_STREAM_DECISION.md). The pin
literal stays `waw-runtime-pin.v1`; no aliases or fixture re-signing are used.

`trustSignedBytes` accepts only this parser's frozen records and constructs the
existing domain/NUL-prefixed canonical bytes without `signature`.
`verifyTrustRecordSignature` verifies those bytes against an explicitly supplied
public signer using native WebCrypto Ed25519. Its return value proves only the
signature; it neither selects nor trusts that signer. A private validation
WeakSet prevents forged typed objects/getters from entering the signing-byte
path, but is not a trust-store or authorization mechanism.

`validateTrustOrigin` checks exact effective HTTPS-origin syntax. It does not
perform DNS resolution, decide production versus loopback policy or authenticate
the origin. `trustTimestamp` checks the exact calendar and millisecond UTC form;
it never treats the local wall clock as trusted time. Revocation records can be
decoded as data and cannot thereby become attachment authority.

Root rotation uses a provider-authenticated checkpoint that binds the accepted
root/signer, `accepted_at` and the SHA-256 digest of the complete canonical root
history through that root. The checkpoint is created only during a successful
crash-fail-closed successor installation while the direct predecessor and successor are
valid. Consumers retain and verify the full history to rebuild retired/revoked
key tombstones. A later rotation verifies the prior exact prefix before advancing
the cumulative checkpoint; only its new direct signer/successor pair is checked
at the new acceptance time. It cannot be supplied by API data, created
retroactively or used to hide a truncated/forked history.

## Verified scope

- Local record Vitest: 77 passed; the full trust consumer/provider/adapter matrix
  passed 121 tests. TypeScript, ESLint and Prettier passed.
- The three original public records retain their exact signed bytes and SHA-256
  digests, and verify with native WebCrypto. Wrong keys and field mutations fail.
- The independent PyCA script verifies the bootstrap digest, all three original
  signatures and nine domain/prefix mutations. It is a fixed-fixture primitive
  reference, not a general JCS or lifecycle implementation.
- Parser negatives cover unsafe/alternate revision tokens, duplicate/extra fields,
  newline/C1 smuggling, noncanonical base64, invalid dates, origins and forged
  objects. These are software tests using public future-dated fixtures.

The fixture validity begins in 2030. A signature test does not claim current
validity or production enrollment. No private key was used to create new
signatures, and no policy store, credential or Runtime HOME was read.

## Remaining R9 work

The root/pin consumer now covers predecessor, revocation, supersession,
floor/rollback, trusted-time and exact invalidation races. The independent
provider core supplies an inert MV3 bridge, fixed Native Messaging/trustd
protocol, service-owned floors/time store and deployment bundle cross-pins; a
real signed extension/client installation remains an R12 gate. The R11 browser
controller must still require both local canary verification and ADMITTED, apply
actual input/output/resize/detach/reconnect rules and reject stale asynchronous
results. None is replaced by record/signature helpers alone.

## Repaired independent review findings

- Policy commit synchronously rechecks the exact provider registration and epoch
  after all awaits and immediately before accepted-state replacement.
- Every actual signing predecessor is valid at final trusted time under the
  single 300-second skew rule.
- Every snapshot record passes its 1..4096-byte gate before any copy, with a
  second defensive check at the copy boundary.
- Initial and final trusted time cannot move behind accepted time.
- A durable full-history checkpoint preserves a valid successor across restart
  after its predecessor expires; missing, late, altered or rolled-back evidence
  fails closed.
- Failed authorization retires its exact subscription once without clearing a
  newer concurrent registration; active invalidation synchronously aborts its
  generation-bound authorization lease.
- Origin accepts only WHATWG-canonical lowercase bracketed hexadecimal IPv6 and
  rejects dotted IPv4-in-IPv6 spelling.

The repaired trust matrix passes 121 cases and preserves the original public
fixture signatures. Independent Architecture/Security/Test review passed with no
remaining P0/P1/P2. Real provider deployment claims remain unqualified regardless
of these software results.
