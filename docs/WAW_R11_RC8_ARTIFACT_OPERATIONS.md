# R11 rc8 artifact and operations rehearsal

Status: delivered software evidence. Implementation checkpoint
c998fb9981553e6fbd6e411f7fe79f57ddc8ebb2 and documentation head
710ceef696757a8a1f2a9165f2312672db57bb1e each completed 26 exact-head checks.
PR #83 merged normally as 95bf65d6114008b962985f7311941499c961a7b8; all six
post-main workflows succeeded. This document does not establish a release, host
activation, credential use, or R12 product qualification.

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

The 3.11 artifact runner is a manifest-hashed closed source file at
`rehearsal/waw_rc8_synthetic.py`. It is copied only from the reviewed test
fixture during the artifact build, then runs with the artifact venv's
`python -I`; it does not import AgentBox code from the checkout. Its parent,
API child and Runtime child each reject an `agentbox_*` origin outside that
venv before opening sockets, generating keys or starting a PTY. The venv starts
without pip, uses the manifest-hashed bootstrap pip wheel only to install into
the venv's site-packages, and rejects `.pth`, `sitecustomize.py`,
`usercustomize.py`, user site and non-wheelhouse pip-report inputs.

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

## Delivered software record

The local P1 foundation supplied fail-closed provenance, operations and canary
scanning scripts plus the source-composition TCP/AF_UNIX/PTY harness. Candidate
c998fb9981553e6fbd6e411f7fe79f57ddc8ebb2 then completed all 26 exact-head
checks. Its full Linux gate built separate exact rc7 predecessor and rc8
candidate artifacts, created fresh artifact-only environments, imported the
candidate on CPython 3.11/3.12/3.13, executed the complete 3.11 artifact
synthetic path, upgraded and receipt-bound rolled back, and scanned dynamically
generated payload, ticket and ephemeral-private-key canaries before emitting a
safe receipt.

The documentation head 710ceef696757a8a1f2a9165f2312672db57bb1e completed a
fresh 26-check exact-head matrix. PR #83 merged as
95bf65d6114008b962985f7311941499c961a7b8 with predecessor
87f5bce964eba231a6a7ade73eaedac7e54646ae and reviewed head 710ceef. Security,
Deployment, Frontend, E2E, Release Candidate and Backend all completed success
on that merge.

This closes rc8 software delivery. It creates no tag, GitHub Release, real
credential, systemd activation, provider login or R12 qualification.
