# Isolated authentication timing diagnostic

This is an opt-in diagnostic for the existing synthetic E2E application. It
measures where a bounded login sample spends time without changing production
authentication, password policy, SQLite behavior or normal E2E assertions.

Run from the repository root with the existing Python/web test dependencies and
Playwright Chromium installed:

```sh
node scripts/run-e2e.mjs --auth-timing
```

The harness creates a temporary database, random loopback ports and generated
test credentials. It runs valid and invalid logins once each on desktop and
mobile, with one worker and no retry. `node scripts/run-e2e.mjs` still selects the
normal 60-test suite. Unknown command-line arguments fail rather than forwarding
arbitrary runner options. Do not invoke the fixture against production state.

## What the observations mean

| Observation | Boundary |
| --- | --- |
| Browser request/response/finished/visible | Elapsed monotonic time since the explicit sign-in click begins |
| `assertion_within_5s` | Original per-operation five-second UI assertions completed successfully |
| `ui_within_5s` | Total click-to-visible elapsed time is at most five seconds; separate from per-operation assertions |
| `request_total_ms` | Entire instrumented ASGI request |
| `admission_ms` | Shared login executor entry through submission after admission |
| `pool_queue_ms` | Default executor submission through actual worker start |
| `worker_ms` | Actual worker execution |
| `argon2_ms` | Password verification call |
| `begin_immediate_ms` | Execution of a `BEGIN IMMEDIATE` statement, including any lock wait and statement overhead; not a pure lock-wait measurement |
| `loop_lag_ms` | Maximum observed excess delay of the 50 ms loop sampler since the last drain |

Backend output uses fixed phase labels and numeric sample IDs. In the shared
`ms` field, `status`, `request_kind`, `dropped` and `unhandled_error` are codes or
counts, not milliseconds. The other timing phases are elapsed milliseconds.
Metrics are drained before a fresh login so old samples cannot substitute for
current evidence. Success requires exactly one current login with all necessary
phases, the expected 200/401 status, and complete loop/dropped summaries. Empty,
missing, inconsistent, dropped or errored measurements fail the diagnostic.

The original assertions remain five seconds per operation. A click taking four
seconds followed by a four-second successful assertion correctly reports
`visible_ms=8000`, `assertion_within_5s=1`, `ui_within_5s=0`; it is not described as
an end-to-end five-second success.

## Privacy, failure and cleanup

The fixture rejects missing test/loopback/opt-in configuration before importing
the synthetic application. Observation buffers are bounded and contain no
passwords, headers, bodies, SQL parameters, request URLs or exception details.
The browser emits only fixed numeric reports; trace, video, screenshots and
preserved diagnostic output are disabled.

HTTP exceptions record a fixed numeric error and invalidate the sample. The
diagnostic API's raw stdout/stderr are discarded so startup/background/Uvicorn
tracebacks cannot expose SQL or parameters. Process failure and readiness failure
still fail the run. The normal E2E API logging behavior is unchanged. A failing
diagnostic reports bounded metadata and retains a nonzero harness exit status.

The existing harness always attempts to stop its child services, checks temporary
data/reports for its synthetic Pair Code canary, and removes its temporary root.
Only synthetic test state is involved; this tool never reads real CLI credentials
or performs a host activation. It is not a production telemetry endpoint.

## Verified results and limits

- Independent sol review initially found raw exception logging, empty metrics
  accepted as PASS and the ambiguous timing flag. All three were repaired.
- `tests/unit/test_e2e_auth_timing.py`: 21 passed, zero skipped on the local Mac.
  It executes the actual Uvicorn request cycle and child-process log boundary,
  plus transpiled real TypeScript with missing-metric and fake-clock negatives.
  Independent sol re-review reran all 21 and passed.
- The repaired isolated Chromium diagnostic passed 4/4 in 6.5 seconds, with
  observed click-to-visible times approximately 78–456 ms. Earlier small runs
  also passed; none reproduced the four historical local full-suite timeouts.
- Root reran the default `node scripts/run-e2e.mjs` after these changes: exit 0,
  all 60 tests passed in 37.2 seconds; temporary API/preview cleanup completed.
  This is a current full-suite pass, not proof of the earlier timeout's cause.
- Scoped formatting, lint, type and syntax checks passed. The E2E CI job runs
  the 21-case regression file after installing web dependencies, then runs the
  unchanged normal browser suite. Backend-only environments may skip the
  TypeScript-dependent cases when web dependencies are unavailable.

These are small synthetic samples using the E2E password-cost configuration.
They neither establish production latency nor prove the cause of historical
timeouts. No held-lock experiment or full-load reproduction is claimed. Further
behavior changes require a concrete reproduction and evidence from this or an
equally bounded diagnostic. See [REMAINING_PLAN](project/REMAINING_PLAN.md).
