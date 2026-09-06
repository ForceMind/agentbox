# R11 rc8 artifact and operations rehearsal

Status: implementation checkpoint c998fb9981553e6fbd6e411f7fe79f57ddc8ebb2
completed the P1 candidate exact-head verification. This documentation
synchronization requires a fresh full exact-head CI before final review, normal
merge and exact read-back.
This document defines the software-only rc8 rehearsal. It does not install a
release, activate a host, create a GitHub Release, enroll a browser extension,
use a real credential, or establish R12 product qualification.

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

## Candidate exact-head checkpoint

The P1 core supplies local fail-closed scripts for unpacked artifact provenance,
artifact-bound upgrade/rollback evidence and encoded canary scanning. It also
adds a source-composition synthetic TCP/AF_UNIX/PTY foundation and fixes a relay
lease-clock race found by that foundation. The synthetic test skips only where a
local sandbox forbids loopback bind; it is not counted as a successful local run.

The first artifact checkpoint was intentionally incomplete: commit
3f97bf0848f8aa5e1cd2cfe0baf1227a062629f0 proved the candidate artifact
synthetic path on Linux CPython 3.11 and independent wheelhouse imports on
3.12/3.13. It did not yet prove the predecessor/candidate operations boundary.

Candidate c998fb9981553e6fbd6e411f7fe79f57ddc8ebb2 completed the full P1
software gate in the Release Candidate workflow. The workflow first validates
the frozen contract, builds the exact rc7 predecessor and exact candidate from
separate source trees, and binds each result to its own manifest and digest. It
creates fresh artifact-only environments, imports the candidate on CPython
3.11/3.12/3.13, and runs the full 3.11 synthetic TCP/AF_UNIX/RFC6455/PTY path
from the candidate artifact environment. The operations member applies the
predecessor, upgrades through the candidate artifact, performs the
receipt-bound rollback, and verifies the final predecessor version, manifest
source, health/ready/meta endpoints, migrations and non-secret durable state.

The same member dynamically generates payload, ticket and ephemeral-private-key
canaries, captures its private child evidence, scans every declared surface
before public reporting, and uploads only the safe result receipt. Its receipt
records synthetic_waw=passed, upgrade_rollback=passed, canary_scan=passed,
contains_secrets=false and host_qualification=false. The artifact operations job
is 101476798319 in GitHub Actions run 34029558191. All 26 PR checks for that
exact candidate reached terminal success.

This completes the rc8 P1 software implementation and CI-evidence gate. It is
not a delivery record until independent final review, normal merge and exact
read-back are complete, and it remains neither a publication nor R12
qualification.
