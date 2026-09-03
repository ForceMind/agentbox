# Current Authorized Action

Action ID: `REMAINING-AWCE-DIAGNOSTICS-2026-09-03`

Owner clarified that development continues on the current Mac. Development
platform and deployment qualification are separate: a missing Linux test host
must not block platform-independent implementation, local tests or Linux CI.
The prior blanket host prerequisite for all remaining software work is superseded
by this clarification; actual host activation, Secret handling, new architecture
decisions and production promises retain their existing boundaries.

## Active reassessment and implementation

Owner requests continued parallel execution: complex work uses sol, ordinary
work uses terra. The current finite checklist is [REMAINING_PLAN.md](REMAINING_PLAN.md).

- R0 is merged as PR #67 after 19/19 exact-head checks and merge read-back.
- R1: deliver reviewed Python/Web opaque AWCE framing and pre-encryption header
  builders, including cross-language CI. No crypto/authentication or socket activation.
- R2: review and deliver the bounded opt-in authentication timing diagnostic.
  Two small local runs passed the original 5-second assertions; old timeouts were
  not reproduced, so no latency root cause or behavioral fix is claimed.
- R3: the complete reviewed full-wire/admission/trust supplement is ready for
  Owner acceptance. It remains PROPOSED; dependent R4/R5 implementation has not begun.
- R10: implement the independently specified descriptor-held executable verifier.
  Fixed interactive CLI execution profiles still need the missing launch/retention
  contracts; this foundation does not execute a CLI or claim host qualification.

Continue independent authorized software work on Mac. Architecture, real host,
real key/Provider Secret operations and production publication retain explicit
approval/evidence requirements. After required protocol decisions, proceed through
R4–R12 in the current plan; routine CI/merge/read-back needs no extra Owner gate.
