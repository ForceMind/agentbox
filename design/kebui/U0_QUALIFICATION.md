# U0 public-reference qualification

Recorded 2026-10-08 UTC. Scope: the five official public references in
[PUBLIC_VISUAL_EVIDENCE.md](PUBLIC_VISUAL_EVIDENCE.md), their adoption matrix,
[synthetic reference board](reference-board.html), and its offline verifier.
No third-party image bytes are redistributed. Existing historical evidence and
project-state documents are unchanged by this batch; the new public evidence
supersedes their earlier public-screenshot UNKNOWN statements only for these
five sources. This is not upstream product testing or final visual acceptance.

## Baseline and boundaries

[PR163](https://github.com/ForceMind/agentbox/pull/163) was merged as
`7b59d099fd3ed329cd55237f2101ed4c1b6dec26`; all six exact-main workflows were
completed/success, including [E2E37722890160](https://github.com/ForceMind/agentbox/actions/runs/37722890160).
U1 synthetic design and existing U2/brand work are prior completed software work.
This batch does not change application code, introduce U3 functionality, activate
real environments, or publish/deploy a release. Domain purchase is Owner-reported;
DNS, website availability and technical control remain unverified, as recorded in
[brand guidance](../../docs/project/KEBUI_BRAND.md).

## Local checks

- Documentation links, secret-pattern and source-boundary checks: exit 0.
- Prototype rebuild: byte-identical generated index.html; exit 0.
- Existing 11 regression checks and 504 DOM combinations: passed; DOM only.
- New verifier syntax and six-card/static-local-link checks: passed.
- SHA256SUMS: all listed files matched; git diff --check: exit 0.
- New reference browser check: not run locally. Installed Playwright lacks the
  required Chromium executable; no browser/pixel pass is inferred.

## Exact candidate and merge qualification

The isolated CI job runs verify-references.cjs after the existing prototype tests:
six public-source/design cards, widths 360/390/768/1024/1440, no external requests,
no page errors, a focusable evidence link, and desktop/mobile screenshots.
At commit preparation, the candidate CI and new reference-board pixels are pending.
The associated PR must record exact-head terminal checks, actual screenshot
inspection, ordinary merge, and exact-main read-back before claiming this batch
complete. Baseline checks do not qualify a later candidate.
