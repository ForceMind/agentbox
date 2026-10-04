# A3 codec fixture provenance

All inputs are public synthetic values, including the opaque selector and session
scope. No key or secret is included. `v1.json` was assembled independently with
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
