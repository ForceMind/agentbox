# A3 codec fixture provenance

All inputs are public synthetic values, including the opaque selector and session
scope. No key or secret is included in `v1.json`, which was assembled independently with
Python stdlib `json.dumps(sort_keys=True, separators=(',', ':'))`, `base64` and
`hashlib`, without importing either production codec. All schema strings are
ASCII; that restricted canonical JSON is equivalent to RFC8785. The patch is
UTF-8 Chinese plus a four-byte emoji, deliberately crossing neither trust nor
production boundaries. The uint64 fields include values above binary64 exact
integer range and the uint64 maximum.

Both unit suites and the interop command check the literal canonical context,
message and AAD bytes, not just each other's round trips. Negative raw JSON is
shared across both languages. These are deterministic **codec** vectors, not
independent Noise/AEAD vectors, cryptographic authentication or encrypted
transport qualification. The next crypto-profile slice must separately prove
its handshake, independent pin, fresh CipherStates and cross-language crypto
vectors before any Runtime/API content path may open.


## Independent crypto continuation

`crypto-v1.json` retains historical rejected-profile evidence. `crypto-v2.json`
is the current public deterministic A3 crypto fixture, adding authenticated
uint32be remaining_ms=30000 and the separate v2 domains/prologue. All private-key
inputs are the already public values from the upstream Noise-C fixture; challenge
is bytes 0..31. They are test data, never production credentials.
`scripts/check-a3-crypto-vector.py` uses the existing standalone TEST oracle's
PyCA X25519/HMAC/AESGCM algorithm, first rechecking upstream Noise-C handshake,
final hash and transport messages, then deriving dedicated A3 prologue,
challenge-confirm/ACK domains, application AAD and envelope bytes. It imports no
product Noise, A3 or WAW application module. The ASCII canonicalization uses
stdlib sorted JSON; it does not call the production codec. Python and Web each
compare every literal key/application record, not merely each other's roundtrip.

The separate native Git→Python→Web harness uses bytes 0..31 as its synthetic
static key and fresh random ephemerals. Fixture trust/bootstrap/time is explicitly
synthetic, not production pin/authentication evidence. No production key material
is read, generated, stored or transmitted.
