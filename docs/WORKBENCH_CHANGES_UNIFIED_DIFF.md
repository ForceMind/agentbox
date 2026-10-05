# S02 / WS08 bounded unified diff view

Contract frozen 2026-10-05 before implementation after parent review. Base:
`3e313b36b7cfc7c1de1c54cc20164ae223fcd122`, tree
`d2fa9213b40db3a5f2b9236646da7fdc50c39645`. This is a visible software increment
in [S02](project/FULL_CAPABILITY_DELIVERY_PLAN.md), not completion of S02/WS08.

## Single owner and source

The existing formal App Changes page supplies only its completed, END-verified
text to a synchronous React presentation component. No new reader, request,
prefetch, transport, authority, storage, log, clipboard, download, external link,
HTML/Markdown execution or syntax-highlighting dependency is introduced. Existing
[native A3](WORKBENCH_A3_NATIVE_TRANSPORT.md) currentness, expiry, cancellation,
route/hide/freeze/auth/trust/refresh/offline fences still own all content. The
component, model and view preferences unmount when completed ownership ends.
Clearing references is not a claim of secure memory zeroization.

The chosen filename remains the existing verified selection label. Header paths,
object IDs, modes and hunk coordinates are untrusted patch declarations. Parsing
cannot establish source identity, repository freshness or new authority. UI copy
labels coordinates accordingly; no inferred source URL or statistics are shown.

## Parsing and exact fallback

Original implementation of a deliberately narrow standard Git unified grammar;
no upstream code or algorithm is copied, translated or imported in this slice.
Existing attributed diff-tree/order modules remain unchanged. The integration
plan's DOM/accessibility adaptation goal does not require importing a native
renderer or its dependencies.

- Presentation bounds are independent of existing extraction/transport limits:
  at most 256 KiB UTF-8, 4,000 physical lines, 64 hunks, 8,192 UTF-16 code units
  per physical line. Bound failure chooses complete raw text, never failed read,
  truncated content, a partial model or an invented empty diff
- Recognize one `diff --git` section, optional standard index/new/deleted/old/new
  mode declarations, paired `---`/`+++` headers, then one or more `@@` hunks
- Canonical decimal ranges must fit 2,147,483,647; nonempty ranges start above
  zero. Exact context/delete/add consumption must match both ranges. Ranges are
  ordered, nonoverlapping, with consistent unchanged gaps; zero-count insertion
  and deletion positions use Git's preceding-line convention
- Only context, addition, deletion and exact `\ No newline at end of file`
  markers are accepted inside hunks. Markers require an immediately preceding
  content line and terminate the applicable side. An extra, repeated, malformed,
  contradictory or incomplete line rejects the entire model
- Binary headers or NUL, combined, rename/copy, unknown headers, metadata-only/empty patches,
  multiple files and malformed/unsupported syntax use complete raw text
- Split only at LF for presentation; preserve CR, tabs, Unicode, whitespace,
  dangerous literal strings and EOF markers. The raw view always renders the
  original verified JavaScript string, never a normalized/reconstructed string.
  This preserves the existing UTF-8 decoding contract, not arbitrary binary data

## View and accessibility

Supported text defaults to a unified semantic table with old/new coordinate
columns, hunk rows, original prefix characters and explicit Chinese row-kind
labels. Add/delete meaning does not depend on color. Native pressed-state view
buttons switch between unified and full raw text without any read or deadline
renewal. A native checkbox defaults to wrapping; disabling it permits horizontal
scrolling inside a bounded, keyboard-focusable region. On phone widths the page
must not overflow. Original headers remain inert, wrap-safe text. No interactive
element is constructed from source content. Focus indicators and column labels
remain readable; no per-source-line tab stops are added.

## Acceptance and release boundary

Actual Git fixtures exercise add/modify/delete, multiple hunks, zero-count ranges,
no final newline, CRLF/Unicode, long lines and every presentation bound. Negative
tests reject incorrect counts/positions/markers/headers without partial display.
Page tests retain legacy plain fallback and exercise unified-active invalidation,
raw switching and unmount. Formal native App CI exercises separate API/Runtime,
real staged Git, complete END, desktop/phone keyboard and overflow, plus actual
PNG review. Existing lifecycle/security regressions stay mandatory.

Normal local quality gates, independent review, six exact-head workflows, normal
expected-head merge/read-back and six exact-main workflows are required. Old
PR #144 evidence is only the baseline. Unconfigured installations stay
unavailable. Production key/pin enrollment, host listener/installer activation,
real accounts, physical-client/CLI qualification, release and deploy are outside
this software increment. No next feature starts as part of this card.


## Initial implementation evidence, 2026-10-05

- Full Web Vitest: 71 files / 1,554 passed; extension 6 passed
- Independent source review: P2 nonexistent-side coordinate gap fixed, actual
  Git mutation regressions added; initial focused 88 passed. The later NUL
  raw-fallback guard and exact-text DOM regression bring independent focused
  coverage to 90 passed, with no remaining blocker
- Native fixture local unit set: 33 passed (8 new), Ruff/Black/mypy passed
- Web/extension lint, formatting, typecheck and production build passed;
  browser-trust bundle, secret-pattern, repository-boundary, workflow pin and
  documentation-link checks passed. Existing >500 kB chunk warning is retained
- Native browser list: 64 desktop/phone cases, including all prior 52. New
  controls exercise real Enter/Space/ArrowRight; synthetic main and multi-hunk
  PNGs are specified. Local native/browser run is NOT RUN; CI/pixels are pending
- Local command corrections remain factual: pnpm wrapper attempted an unavailable
  home-directory store, so installed locked binaries were used directly. Initial
  extension typecheck command emitted test artifacts; these generated outputs
  were set aside and the actual production build/bundle gate reran successfully.
  Wrong Python interpreter/import-path and license-script invocation attempts
  were not counted as passes. No dependencies or security controls were changed

Publication, six exact-head workflows, actual PNG review, merge/read-back and
six exact-main workflows remain pending at commit time. Their results belong in
PR evidence and the next ordinary snapshot; no perpetual docs-only CI loop.


## First CI: successful tests, failed long-content pixels

Head `a49230f574c8b71394b20c1a102015ad3b61b9ec` / tree
`64ede3e2adae935fc5b6e7305e6f054c100b6125` has six first-attempt successful
workflows; Backend each Python version reports 5284 passed / 88 skipped, with
14 native process tests. E2E reports 224 passed / 30 prescribed skipped, no
failures or flakes, including 64 formal native desktop/phone cases. Six PNGs
were opened independently, and the pixel verdict is FAIL: the native main
screenshots are 1280×7427 and 1073×65772, with huge blank tails beyond the card.
The bounded internal scroll area cannot justify that page overflow.

The absolute assistive labels have no positioned scroll ancestor, consistent
with their wrapped-line static positions escaping to the root. This correction
establishes the region as their containing block and adds a small note margin
for focus-outline clearance. Browser assertions now bound document scrollHeight
against the reader-card bottom plus normal page padding, across raw/unified,
wrap, keyboard and screenshot paths. Read limits, source text, lifecycle and
all previous assertions remain unchanged. New CI and actual pixels must verify
the correction; old successful tests alone are insufficient. No merge occurred.

First artifact 11353574147 ZIP SHA256:
`b8b7523f33d6d49933f571ae7c5d399f9f65cc100470117932416da0a4a18980`.
Failed desktop PNG SHA256:
`07893476e09ffe497857ea0ef682255c2b2ef75dee7d2901beb831f01f84b5ff`;
failed phone PNG SHA256:
`fd485783aacb757a3624e8ab461271eda96c4c89ff5befa0d8781920b6b6ed7b`.
