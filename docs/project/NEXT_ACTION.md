# Current Authorized Action

Action ID: `REMAINING-TOKENIZER-CONTRACT-2026-09-03`

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
- R1 is merged as PR #68 after 19/19 checks and actual merge read-back.
  No crypto/authentication or socket activation is implied.
- R2 is merged as PR #70 with 19/19 checks and read-back. CI executed all 21
  diagnostic regressions and 60 normal E2E cases. No historical root cause is claimed.
- R3: the complete reviewed full-wire/admission/trust supplement is ready for
  Owner acceptance. It remains PROPOSED; dependent R4/R5 implementation has not begun.
- R9.1: deliver the repaired, independently reviewed browser tokenizer core
  through exact-head CI. All 113 tests and 133 independent negatives passed;
  no renderer, trust/admission/controller or socket integration is implied.
- R10.1 is merged as PR #69 after 19/19 checks and actual merge read-back.
  Fixed interactive CLI execution profiles still need the missing launch/retention
  contracts; this foundation does not execute a CLI or claim host qualification.

Continue independent authorized software work on Mac. Architecture, real host,
real key/Provider Secret operations and production publication retain explicit
approval/evidence requirements. After required protocol decisions, proceed through
R4–R12 in the current plan; routine CI/merge/read-back needs no extra Owner gate.
