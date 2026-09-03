# Public WAW application profile vector

`profile-v1.json` contains synthetic public metadata, challenge and payloads.
Its X25519 private inputs are the already public values in the existing
[Noise-C fixture](../noise_nx/noise-c-nx-aesgcm-sha256.json); provenance and the
upstream MIT notice remain in [its notice](../noise_nx/NOTICE.md). No production
Runtime key, vendor credential or captured terminal byte is present.

The independent reference generator is
[check-waw-crypto-vector.py](../../../scripts/check-waw-crypto-vector.py). It uses
PyCA X25519, AESGCM and standard SHA-256/HMAC directly, without importing the
product Noise, context, AWCE or profile implementation. Before deriving this
application vector it verifies all six messages and final handshake hash of the
upstream Noise-C vector. It then uses hand-authored canonical context bytes,
the fixed challenge `00..1f`, confirmation formulas and a separately packed AWCE
header. Values above JavaScript's safe Number range remain decimal strings.

Run `.venv/bin/python scripts/check-waw-crypto-vector.py` to verify. The explicit
`--write` option regenerates this one fixed fixture for review. Check mode never
rewrites it. This is an independently implemented project-specific application
vector, not an externally standardized WAW vector or production certification.

The Python/WebCrypto interop check verifies both actual profile roles against
every fixed handshake/confirmation/first-envelope byte, then exercises active
payload size boundaries and both-direction invalid-tag/closed-counter rejection.
Only its disposable test process substitutes the public challenge entropy;
product defaults use the system CSPRNG. Public test bytes remain in bounded
captured pipes, and console output contains bounded result labels only.
