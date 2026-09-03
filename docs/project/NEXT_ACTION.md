# Current Authorized Action

Action ID: `WAW-SOFTWARE-READINESS-2026-09-03`

Stage E documentation/packaging awaits exact-head CI/merge on `codex/waw-software-readiness`, based on
`6972f0dba907afd9741c2dc3584f431ee32765ed` (PR #60 exact merge read-back).

- Verify the merged implementation baseline's CI artifact by exact source
  commit/ref kind, manifest/checksums/SBOM, archive and nested-wheel scans.
- Reconcile current README, limitations, acceptance, release notes and checklist
  with the actual software foundations and explicitly unavailable real terminal.
- Include WAW workflow/recovery/host-gate/readiness documents in the candidate
  artifact so standalone readers receive the same capability boundaries.
- Independently review, run the exact-head CI matrix, merge and read back; no
  version/tag publication, production activation or support promise is included.

After E, Stage F is pending explicit Architecture/Owner scope, an identified
isolated Linux test host and attributable host evidence. The outstanding work
is listed in `../WAW_SOFTWARE_READINESS.md`: real fixed CLI/PTY execution,
legacy interlocks, Noise/WebSocket/browser terminal, Linux isolation, official
Runtime-user readiness and end-to-end restart/reboot recovery. Some are not yet
implemented; none may be marked PASS from synthetic contracts.

The Owner was asked for the isolated host/SSH alias during this task; no target
has been provided. Continue safe software preparation while available. Do not
infer host, Secret or publication authorization from the routine merge plan.
