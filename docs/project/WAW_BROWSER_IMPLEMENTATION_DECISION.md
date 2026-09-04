# Browser trust and terminal implementation decisions

Status: **ACCEPTED for software implementation — 2026-09-04**. The Owner
explicitly approved this R9 scope, the logical-line clarification, the bounded
terminal model and the staged model/ownership plan. This is the R9 software
contract, not an enabled terminal or a provisioned trust provider.

The accepted [stream supplement](WAW_ENCRYPTED_STREAM_DECISION.md) remains
authoritative for signed records, crypto and admission. This document resolves
only the missing browser integration choices. Existing strict tuple/epoch
checks, plaintext exclusion from API, no persistence and exact cleanup remain.

## Independent trust consumer

The browser verifier consumes public records from one explicitly supplied
trusted provider port. There is no fallback to API metadata, a global window
property, HTML configuration, localStorage or IndexedDB. Absence, ambiguity,
failed capability checks or expired authorization keeps Connect unavailable.
Production installation of that provider is a separate deployment qualification;
a test provider must be named and reported as synthetic.

The port owns independently provisioned bootstrap/root/pin records, atomic
revision floors, trustworthy absolute time and origin/network-policy evidence.
The served application gets a read-only bounded snapshot and invalidation
subscription. It cannot install/replace/revoke records or reset a floor. Any
import/rotation transaction belongs to the independent provider, not a page
button or API endpoint. A TypeScript interface is not evidence that the provider
actually enforces these properties.

The verifier checks the closed schemas and original public signatures, bounded
canonical UTF-8 bytes, exact safe signed revisions, root chain/supersession,
revocation, validity, origin and host revision before constructing the Noise
initiator. New trust snapshots require complete verification; a malformed API
response cannot mutate the accepted trust state. Revocation/provider loss,
backward time or a changed binding destroys active crypto and starts exact
attachment cleanup. UI labels, WebSocket origin and API host metadata never
serve as an independent pin.

Root/pin import records are proposed to use full canonical JSON objects,
including `signature`, at most 4 KiB each. Restricted schema values are ASCII;
unknown/duplicate keys, alternate escaping, whitespace, exponent revisions,
unsafe integers and noncanonical encodings are rejected before verification.
Signing still omits `signature` and uses the existing domain/NUL prefix. The
original dot-form pin, signature bytes and public 2030 fixture intervals remain
unchanged. This is a deliberately closed import format, not a general JCS API.

### Durable root-rotation checkpoint

Root rotation must remain usable after an earlier signing root expires. The
provider therefore creates an authenticated checkpoint only while installing a
successor whose exact predecessor is still valid at the final trusted install
time. The checkpoint binds the accepted root identity and signer, the exact
canonical root-history SHA-256 digest through that root, and `accepted_at`. It
is provider state proving that the predecessor-validity check already completed;
it is not another signed root, an API assertion or permission to truncate the
history.

The provider persists the checkpoint, complete root history, key tombstones,
revision floors, provider epoch and journal through a crash-fail-closed
multi-file transition. The state file itself uses atomic replacement, while an
interruption between journal, time and state writes makes the store unavailable
rather than presenting a partially accepted update. A later successor first
verifies the old checkpoint and exact history prefix, verifies
the new direct signer/successor pair at the new `accepted_at`, and then advances
the checkpoint over the cumulative history. Pin-only updates and terminal root
revocation preserve the last active-root checkpoint exactly.

On later loads the provider rebuilds signer, retired and revoked-key state from
the complete signed history. The checkpoint root and its direct signer are
checked at `accepted_at`; the current root and pin remain valid at the final
trusted time. Earlier ancestors rely on the provider's already-accepted exact
prefix and are not incorrectly required to be valid at every later rotation.
A missing checkpoint, a checkpoint created only after its direct signer expired,
a history/digest/signer mismatch, a single-file rollback or a fork fails closed.
Without an external generation anchor, a privileged consistent rollback of the
entire key/state/journal/time store can remain internally self-consistent while
the older pin is still inside its validity/skew window. R12 must qualify or
externally anchor that deployment boundary. The browser independently checks the
same cumulative full-history checkpoint before accepting a fresh document after
restart.

## Logical line and parser recovery

The tokenizer holds a raw-byte **count**, not an unrendered raw logical-line
buffer. A prompt without LF may legitimately remain visible while awaiting input.
The accepted clarification removes a wall-clock timeout for that already-rendered
line count: the 32 KiB count persists across frames until LF; exceeding it drops
through LF and raises local `TERMINAL_PARSE_LIMIT`. Waiting does not reset the
count or permit a slow sender to evade the byte ceiling.

Incomplete UTF-8/control-sequence carry still has its independent 100 ms and
4 KiB limits, serviced even while idle. Task budgets remain 10,000 bytes/5 ms,
frame controls remain 256 and attachment parser work remains 50 ms per fixed
one-second monotonic window. Three consecutive windows with parser/line budget
incidents clear local terminal state and start exact detach of that attachment.
A quiet window resets the consecutive counter; a suspended tab does not synthesize
successful heartbeats or replay missed timers.

A sequence/frame failure that makes tokenizer state ambiguous immediately clears
the local terminal and fences that attachment. It is not automatically reset
midstream. The three-window rule remains for recoverable logical-line truncation
and scheduler saturation. This stricter failure boundary prevents denied control
string tails from being reinterpreted after losing parser carry. Recovery uses
an explicit fresh ticket/Noise attachment and never resends unresolved input.

## Accepted bounded renderer decision

`@xterm/xterm`, without addons, was evaluated as the sole external candidate. A read-only official
npm query on 2026-09-03 returned version `6.0.0`, MIT and integrity
`sha512-TQwDdQGtwwDt+2cgKDLn0IRaSxYu1tSUjgKarSDkUM0ZNiSRXFpjxEsvc/Zgc5kq5omJ+V0a8/kIM2WD3sMOYg==`.
The fixed tarball was downloaded with `npm pack --ignore-scripts` to a temporary
assessment directory and its SHA-512 was recomputed to match that integrity.
No dependency has been installed into the project.

The versioned public implementation exposes parser hooks without enabling
`allowProposedApi`. Its public write API is asynchronous and requires callback
completion for accurate buffer observation. The implementation must prove
typed-token rendering, bounded pending writes/model retention, disabled device
responses/links/clipboard/title effects and destruction of late work before
dependency admission is finalized. Raw PTY bytes cannot bypass the tokenizer.
See the versioned [public API](https://github.com/xtermjs/xterm.js/blob/6.0.0/typings/xterm.d.ts),
[implementation](https://github.com/xtermjs/xterm.js/blob/6.0.0/src/browser/public/Terminal.ts)
and [MIT license](https://github.com/xtermjs/xterm.js/blob/6.0.0/LICENSE).

The 256 KiB/2,000-line terminal retention bound must include alternate screen,
combining characters and async write backlog. A default scrollback row count is
insufficient evidence. The accepted implementation therefore uses a
project-owned bounded terminal model and text-DOM projection over the existing
typed token allowlist. It does not install xterm or depend on its private state.
Normal/alternate screens, history, combining content and pending projection
share the fixed payload/line budgets; overwrite, erase, trim, screen exit and
destroy release old ownership. Closed SGR/CSI semantics cannot create arbitrary
CSS, HTML, links or browser actions. Unicode width data is fixed and reviewed,
not browser-dependent.

The xterm admission is rejected for R9 because versioned source inspection found
that `BufferLine` keeps a separate combined-
character map, and replacing a cell with a plain codepoint does not itself remove
the old map entry. Public visible-cell byte counts therefore cannot by themselves
prove the required retained-data ceiling. The adapter assessment must account
for those retained entries, trimming/reset and pending writes, or choose a
reviewed bounded text model. This is a concrete integration concern, not a claim
that the upstream terminal violates its own advertised contract. A future
supplement may reassess another version, but R9 cannot silently switch to it.

## Acceptance evidence

## Browser locale contract

The product UI has exactly two user-facing locales: `zh-CN` and English. On each
fresh page load only `navigator.languages[0]` is normalized. If that first
preference has the exact primary language `zh`, the UI selects `zh-CN`;
otherwise it selects English even when a later preference is Chinese. Missing,
malformed and unsupported first preferences fall back to English. The selected
locale sets the document `lang`
attribute and all user-facing workspace, trust, terminal, recovery and error
copy. Protocol fields, identifiers, enum values, error codes, Audit actions,
filenames and source names remain English and are never translated.

The locale decision comes only from the browser language preferences in v1; API
metadata, HTML configuration and provider records cannot override it. A browser
language change takes effect on an explicit reload/new document and cannot alter
an active protocol or attachment identity. R9/R11 tests must cover Chinese and
non-Chinese desktop/mobile contexts, English fallback, document `lang`, complete
error/action translations, layout/overflow and the absence of mixed placeholder
copy.

Trust tests must verify the unchanged three public vectors, mutations, every
revision/time/origin edge, crash failure/rollback and invalidation races with
pending crypto. They must also prove a successor accepted before predecessor
expiry survives restart after that expiry, while missing, late, modified or
rolled-back checkpoints fail closed. Synthetic policy tests do not qualify
persistent trust storage.

Terminal tests must cover real native-browser desktop/mobile key, bounded
single-line paste, resize/ACK, detach/reconnect, stale/unmounted events, bounded
pending output, unsafe controls and parser limits. Terminal payload capture in
screenshots, traces, video, logs and retained test artifacts stays disabled;
visual QA uses explicitly non-sensitive test content and reports that boundary.
The final product path still needs R10/R11 software composition and R12 evidence.

## Current terminal-model review status

The first bounded model/scheduler implementation failed independent review. The
reported bidi/default-ignorable, Hangul/variation/emoji, 48,000-cell deadline,
fixed-window CPU and UCD provenance findings are now repaired locally.

The tokenizer now uses fixed UCD 13 Bidi_Control/Default_Ignorable tables,
Hangul GB6-8 roles and Emoji_Modifier/Base rules. Model apply, projection and the
renderer port are cooperative under one absolute five-millisecond callback
deadline; CPU is apportioned across one-second boundaries. The offline generator
pins six Unicode inputs, hashes and canonical serialization. Normal, alternate,
history, pending projection, combining overwrite and 48,000-cell continuation
are tested. The scoped tokenizer/model/scheduler matrix passes 185 cases and two
Unicode-data checks; independent review found no remaining P0/P1/P2. The full
Web matrix passes 915 tests and desktop/mobile browser E2E passes 64 tests. No
live UI/terminal connection is claimed.
