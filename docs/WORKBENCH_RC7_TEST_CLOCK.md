# Bounded rc7 lifecycle test-clock correction

Base: main `c93ed22a57b2667d8f6b13fdb3fd3720001e72f2`, tree
`44630157273d4eea963d5738ed930eb257b7847e`. PR #145's final head had six
successful first-attempt workflows and independent six-image pixel PASS. The
merge tree equals that head. This is a separate test-only CI-closure follow-on,
not another Changes feature, WAW product change or new authority.

## Observed main failure

[Frontend run 37334720162](https://github.com/ForceMind/agentbox/actions/runs/37334720162),
job 111846470320, failed in the unchanged
`wawBrowserLifecycle.rc7.test.ts` socket error/backpressure case: 5000ms timeout
plus one unhandled `PROTOCOL_INVALID` rejection. Web totals were 1553 passed and
1 failed. The other five exact-main workflows succeeded. No blind rerun was
used to erase this result, and no successful PR-head run substitutes for main.

The fixture already controls the controller scheduler with `WAWRc7FakeClock`,
but wire decoding still read real `performance.now()`. `decodeWireFrame` keeps
its strict 5ms nonopaque validation budget. Adjacent `wawWire.test.ts` and
`wawBrowserController.test.ts` already freeze that clock for deterministic
unit tests. The lifecycle test exercises fencing/cleanup/backpressure, not
wall-clock performance qualification.

## Controlled evidence and limits of inference

An isolated archive of exact main reproduced the same failure fingerprint by
changing only the first controller-inbound decoder readings from 0 to 6 ms:
5000 ms timeout plus unhandled `PROTOCOL_INVALID`. With a frozen clock the original
three lifecycle cases passed in 52 ms.

A second same-condition experiment injected a real pause into the first
controller-inbound `TextDecoder.decode`. The old test observed 8.022 ms and
reproduced the timeout/rejection. With the same 8.026 ms pause and only the unit
clock frozen, the affected case passed in 51 ms. No product decoder, deadline,
test timeout or behavioral assertion changed. These are controlled local
observations, not a claim that the historical CI pause duration was recorded.
CI did not log internal timer readings: its cause remains a strongly supported
inference. Diagnostic code/logs are retained with the task evidence and are not
installed into the product or regular tests.

The three-microtask `settle()` helper was also inspected. A fixture may inject
the next frame before outbound publication appears in a synchronous metadata
probe, but controller continuations precede queued inbound handling. The normal
baseline passed. That observation did not prove a separate historical race and
was not used to justify unrelated changes or rejection suppression.

## Exact minimal change and retained negative coverage

Only the lifecycle test imports `beforeEach` and stubs `performance.now()` to 0
per case, with the existing `afterEach(restoreAllMocks)` restoring it. Product
files, strict 5 ms decoder budget, 5000 ms test timeout, fixture action ordering and
all assertions are unchanged. The controller fake clock and scheduler remain
independent, including its 60000 ms backpressure cleanup advance. The global
performance spy also freezes TerminalScheduler elapsed readings inside these
fixtures; these three cases do not claim renderer timing qualification. The
separate wire and renderer deadline suites remain unchanged.

`wawWire.test.ts` retains the separate `checks a bounded validation deadline and
fails without hop allocation` case: it supplies 0 then 6 to the real decoder and
directly requires `WireError`. The same unchanged test separately checks closed
state and no hop allocation for invalid sequences after restoring the timer.
Freezing ordinary lifecycle fixtures therefore does not remove deadline-rejection coverage.
The diagnosis candidate's adjacent five-file suite passed 317 tests, including
that negative case. Independent review and full new exact-head/main gates are
still required for this new branch; old green tests cannot close it.

No production key/pin, credentials, listener/host activation, release or deploy
is included. The original unified view and raw fallback remain unchanged.
