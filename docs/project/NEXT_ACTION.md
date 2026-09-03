# Current Authorized Action

Action ID: `REMAINING-PLAN-AUTH-CAPACITY-2026-09-03`

Owner clarified that development continues on the current Mac. Development
platform and deployment qualification are separate: a missing Linux test host
must not block platform-independent implementation, local tests or Linux CI.
The prior blanket host prerequisite for all remaining software work is superseded
by this clarification; actual host activation, Secret handling, new architecture
decisions and production promises retain their existing boundaries.

## Active reassessment and implementation

Owner requests continued parallel execution: complex work uses sol, ordinary
work uses terra. The current finite checklist is [REMAINING_PLAN.md](REMAINING_PLAN.md).

- R0: fix the reproduced login/reauthentication cancellation capacity defect;
  retain admission until actual thread completion and verify race/error behavior.
- R1: implement Python/Web opaque AWCE framing from the already fixed header;
  no application crypto, authentication, AAD choice or socket activation.
- R2: measure old local authentication timing failures before changing behavior;
  do not attribute them to the confirmed cancellation bug without evidence.
- R3: consolidate the newly identified full-wire/admission/trust ambiguities with
  the existing three-byte proposal into one reviewable decision. Its authority
  status remains PROPOSED; no new application bytes are silently approved.

Continue independent authorized software work on Mac. Architecture, real host,
real key/Provider Secret operations and production publication retain explicit
approval/evidence requirements. After required protocol decisions, proceed through
R4–R12 in the current plan; routine CI/merge/read-back needs no extra Owner gate.
