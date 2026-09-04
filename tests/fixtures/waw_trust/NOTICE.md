# Public trust verification fixtures

These are the unchanged public Ed25519 records embedded in the historical WAW
architecture. They contain no private key and were not re-signed for these tests.
Their intervals begin in 2030; positive time tests require the explicit synthetic
clock from the fixture. They are never production enrollment or trust-store data.

The dot-form `waw-runtime-pin.v1` and exact signature bytes are preserved under
`docs/project/WAW_ENCRYPTED_STREAM_DECISION.md`. The primitive reference check
verifies hashes/signatures; lifecycle, origin, expiry, rollback resistance and a
real independent trust provider require separate tests and deployment evidence.
