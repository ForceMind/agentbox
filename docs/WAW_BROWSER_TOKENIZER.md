# Browser terminal tokenizer foundation

`features/workspace/terminalTokenizer.ts` is a pure incremental byte-to-token
component. It implements the fixed character/control allowlist from
[Browser Terminal Security](../WEB_AGENT_WORKSPACE_ARCHITECTURE_AUTHORIZATION_REVIEW.md).
It has no DOM, renderer, xterm dependency, timer, network, crypto, admission,
terminal response, clipboard, browser storage or logging operation.

This is only R9.1 of [REMAINING_PLAN](project/REMAINING_PLAN.md). No terminal
button or WebSocket is enabled by this component. The application wire supplement
remains separately [PROPOSED](project/WAW_ENCRYPTED_STREAM_DECISION.md).

## Token and character rules

- A coupled UTF-8 DFA consumes valid multibyte scalars before raw C1 detection.
  Ordinary non-ASCII continuation bytes are preserved; raw and UTF-8-encoded C1
  controls are denied. CSI/string families introduced by C1 remain entirely inert.
- Printable text is returned as text-model data. Invalid UTF-8 produces bounded
  U+FFFD replacement and resynchronization. Fixed bidi ranges render as visible
  escaped markers; the specified zero-width ranges are discarded and counted.
- BS, HT, LF, VT, FF and CR become closed typed operations. Denied C0, DEL,
  notifications and C1 controls never become terminal responses or browser calls.
- Only the exact CSI parameter/final table and ESC 7/8 produce typed cursor,
  erase/scroll/color or save/restore data. Alternate-screen mode is limited to
  exact `?1049h/l`. Other mode changes and bracketed-paste wrappers are inert.
- OSC/DCS/APC/PM/SOS bodies are consumed under the sequence budget and discarded,
  including title, clipboard, hyperlink, image and device-query payloads.

Consumers must not concatenate tokens back into an unchecked VT stream. A future
renderer must implement each typed operation within the validated viewport, use
its text model rather than HTML, and retain the side-effect denylist. This module
does not by itself prove renderer safety or terminal UI behavior.

## Calling and resource contract

1. `beginFrame(bytes)` accepts and copies one bounded `Uint8Array`; another frame
   cannot begin while one remains pending. A frame is at most 32768 bytes.
2. Call `runTask(clock)` with a pure monotonic millisecond clock. It returns typed
   tokens, consumed byte count, frame completion, state, bounded discard count,
   local status and the next carry deadline. Callers arrange subsequent tasks
   and must service a deadline even when no new frame arrives.
3. Each task cooperatively checks the 10000-byte/5-ms budget before consuming
   another byte. Each frame permits at most 256 controls. Carried sequences are
   bounded to 4096 bytes and 100 ms, including across frame boundaries.
4. Logical lines count raw bytes across frames and cap at 32768. Excess bytes are
   omitted through LF with local `TERMINAL_PARSE_LIMIT`; this is not a Runtime
   output cursor or ABWS GAP. Independent sequence/frame budgets still apply.
5. Sequence/frame limit failure clears carry and enters `needs-reset`, refusing
   further input. `reset()` is an explicit caller decision. `destroy()` clears
   held state and permanently rejects reuse. These methods never grant admission.

At most one copied pending frame and bounded parser state are retained. Consumed
frame bytes are zeroed; no raw logical line or denied string body is accumulated.
Invalid input/clock errors use fixed identifiers, never terminal payload values.

## Remaining integration and contract gaps

The historical architecture does not provide a duration for its logical-line
deadline or complete recovery rules after a sequence/frame limit. This core does
not invent them. It provides the explicit failure boundary above; controller
recovery policy still requires a resolved contract. The specified sequence/carry
100-ms deadline is implemented separately.

The 50-ms/s attachment scheduler, three consecutive over-budget windows, exact
detach cleanup, pending-output/scrollback budgets, viewport renderer, trust/pin
verification, crypto and admission gate remain unimplemented integrations. No
visual QA or real-browser terminal certification is claimed for a pure tokenizer.

Run the scoped corpus from `apps/web`:

```sh
NODE_OPTIONS=--no-experimental-webstorage pnpm exec vitest run src/features/workspace/terminalTokenizer.test.ts
```

Current test counts, independent review findings and final CI/merge evidence are
recorded in [CURRENT_STATE](project/CURRENT_STATE.md), rather than inferred from
the existence of a parser or a successful isolated test.
