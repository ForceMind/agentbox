# R11 rc8 artifact and operations rehearsal

Status: P0 contract frozen. This document defines the software-only rc8
rehearsal. It does not install a release, activate a host, create a GitHub
Release, enroll a browser extension, use a real credential, or establish R12
product qualification.

## Provenance

The immutable predecessor is rc7 release-record merge
`87f5bce964eba231a6a7ade73eaedac7e54646ae`, version `0.3.0rc7`. rc8 uses
`0.3.0rc8`; the workflow supplies the candidate's exact HEAD SHA at runtime and
must not self-reference an anticipated merge SHA. The machine-readable contract
is [0.3.0rc8.rehearsal.json](releases/0.3.0rc8.rehearsal.json).

Every candidate artifact must contain its own manifest, checksums, SBOM,
wheelhouse and closed native helper source. Predecessor and candidate are built
from separate exact source trees. A checkout, editable install, user site or
ambient package may not satisfy an artifact test.

## Required evidence

### Unpacked native source and wheelhouse provenance

The rehearsal verifies the bundle, safely unpacks it, and invokes only the
unpacked `release/scripts/build-waw-native.py` and
`release/scripts/check-waw-native.py`. Compiler source and include paths must
remain under the unpacked release root.

A fresh virtual environment runs with `PIP_NO_INDEX=1`, an empty pip config and
`PYTHONNOUSERSITE=1`. It installs only the artifact wheelhouse. `python -I`
must prove that every `agentbox_*` module used by the smoke path resolves inside
that environment, and that distribution version and manifest provenance match.
The import matrix runs on CPython 3.11, 3.12 and 3.13; the full WAW rehearsal
runs on 3.11.

### Synthetic WAW path

The test harness uses separate API and Runtime processes, real AF_UNIX control
and stream sockets, a raw TCP RFC6455 browser peer, synthetic signed trust data
and a real kernel PTY with a fixed echo child. It may use existing `test_only`
closed ports, but may not introduce a production environment variable, query
parameter, global fault switch or configurable arbitrary socket path.

The path must demonstrate:

1. synthetic trust fingerprint matches the synthetic Runtime X25519 key;
2. HTTP Start returns one ticket and browser admission reaches `ADMITTED` before
   INPUT;
3. INPUT is decrypted only by Runtime and reaches the PTY once;
4. PTY output is encrypted by Runtime, opaque through API and decrypted by the
   browser peer;
5. RESIZE is read back with `TIOCGWINSZ`;
6. Detach returns positive `ATTACH_PTY_CLOSED`, then generation-bound Stop returns
   stopped evidence;
7. replayed tickets and shutdown cannot revive prior publication or ownership.

Synthetic trust, key and PTY data are fixtures only. They are not CRX,
Native Messaging, trustd installation, real vendor CLI or R12 evidence.

### Exact upgrade and rollback

The operations rehearsal builds an rc7 predecessor artifact and an rc8 candidate
artifact from their exact source SHAs. The predecessor artifact performs initial
fixture apply. The candidate artifact performs upgrade through artifact-local
installer and real Alembic migration; it must not merely write an
`alembic_version` row. The candidate installer performs the receipt-bound
rollback.

The final system must be the exact predecessor version and manifest source SHA.
It verifies the current symlink, API health/ready/meta endpoints, normalized
SQLite schema and logical-data fingerprints, `foreign_key_check`, `quick_check`,
Project files, Runtime HOME, WAW epoch, binding store, receipt/journal integrity,
backup digest and absence of stale WAL/SHM. Critical checks use explicit
fail-closed exceptions, never Python `assert`.

### Dynamic canary scans

Each rehearsal dynamically generates opaque payload, ticket and ephemeral private
key canaries. Scans cover raw, hex, base64 and base64url representations in
bundles, unpacked trees, wheelhouses, installed environments, native output,
fixture roots, backups, receipt/journal, SQLite/WAL/SHM and captured
API/Runtime/PTY stdout, stderr and reports. Failure output identifies only the
surface name. A public Runtime fingerprint is expected trust metadata and is not
treated as a private-key leak.

## Boundaries and acceptance

rc8 does not modify `UNIT_NAMES`, install or enable WAW sockets, write runner
`/etc`, `/opt` or `/run`, use a real Provider Secret, invoke real vendor login,
or claim host support. R12 exclusively owns systemd identities/sockets, Runtime
key custody, CRX/trustd deployment, real CLI/PTY compatibility, isolation,
reboot and production support evidence.

Acceptance requires: artifact-local native build, isolated provenance proof,
full synthetic WAW path, exact upgrade/rollback and canary scans all pass on the
candidate exact head; independent architecture/security/test review has P0=0 and
P1=0; then normal merge and exact read-back. A passing synthetic run cannot be
described as real-host qualification.

## Delivery slices

1. freeze provenance contract and rc8 version;
2. add unpacked-source and wheelhouse provenance rehearsal;
3. add synthetic API/Runtime/RFC6455/PTY rehearsal;
4. add exact upgrade/rollback and canary scan rehearsal;
5. integrate workflow gates, independent review, release record and read-back.

## Current core checkpoint

The P1 core supplies local fail-closed scripts for unpacked artifact provenance,
artifact-bound upgrade/rollback evidence and encoded canary scanning. It also
adds a source-composition synthetic TCP/AF_UNIX/PTY foundation and fixes a relay
lease-clock race found by that foundation. The synthetic test skips only where a
local sandbox forbids loopback bind; it is not counted as a successful local run.

This is an intermediate checkpoint, not rc8 acceptance. Required workflow work
still builds exact predecessor and candidate artifacts, creates fresh
wheelhouse-only environments, executes the synthetic path there, dynamically
injects/scans every canary surface and fails if the required loopback path skips.
Until that gate and the artifact evidence exist, rc8 remains incomplete.
