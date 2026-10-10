# K2-01 inert conversation observation model

Revision: `k2-observation-candidate-v1`, 2026-10-10. This is an isolated,
metadata-only software slice following [K2 preparation](KEBUI_K2_CONVERSATION_ARCHITECTURE.md).
No production import, route, migration, adapter, message send, approval execution,
Runtime construction, credential, transcript, browser storage or release change.
The only producer in this slice is a synthetic fixture. Validation is not source
authentication, capability evidence or permission to act; U3 remains unwired.

## Frozen input subset

This candidate validates already-decoded plain metadata objects. It is not a JSON
wire decoder: duplicate JSON keys, raw/ciphertext byte limits, framing, parser
work and crypto admission remain S03 work. Unknown/extra fields are rejected;
there is no raw content field, extension map or free-form error string.

A scope has exactly these 16 string fields:

- `owner_scope`: 64 lowercase hexadecimal characters, a noncredential scope
  commitment, never a raw login Session or a bearer token
- `auth_epoch`, `project_revision`, `binding_revision`, `host_revision`,
  `runtime_epoch`, `api_authority_epoch`, `conversation_revision`, `generation`:
  canonical positive decimal uint64 strings (no leading zeros/sign/whitespace)
- `project_id`: existing `prj_` plus 32 lowercase hexadecimal characters
- `binding_digest`: existing 64 lowercase hexadecimal characters
- `host_id`: existing `wri_` plus 32 lowercase hexadecimal characters
- `agent_type`: exactly `claude` or `codex`
- `execution_kind`: exactly `structured-candidate`; not an existing WAW kind
- `conversation_id`: `kcv_` plus 32 lowercase hexadecimal characters
- `turn_id`: `ktr_` plus 32 lowercase hexadecimal characters

The list above is normative and validators enforce that exact list. No
Workspace/attachment/vendor handle is invented or repurposed.
An observation has exactly `scope`, `revision` (positive decimal uint64) and
`status`: `running`, `awaiting_approval`, `awaiting_input`, `completed`, `failed`,
`canceled` or `unknown`. A status is a proposed typed observation, not a claim
that a real adapter exists or that a requested task succeeded.

Python reuses `AgentType` and Project/host/digest/uint64 validators from `waw.py`.
Web reuses the existing canonical uint64 helper and Project ID predicate. It
must not alter the existing WAW reducer or pretend its attachment fence is a
conversation fence. Both parsers copy accepted values; retained objects cannot
change when callers mutate their input.

## Read-only projection

Web state retains one scope, one latest observation and bounded scalar fences.
It never exposes a `canWrite` result or dispatches effects. A required 32-hex
`view_id` distinguishes view incarnations; the owning UI must issue a fresh ID
when replacing/reopening the view. This module creates no authority or random ID.
Read attempts are positive uint64 counters that strictly increase within a view.
Their floor survives interruption. The candidate does not import into a UI yet.

- Start a read: revoke the current pending read, mark prior observations stale,
  record the new attempt; no network effect is returned.
- A read result must match view ID, exact current scope and pending attempt.
  An older scope/attempt is ignored. A snapshot may jump revisions to reconcile
  a gap, but cannot move backward or change an already terminal turn outcome.
- An event is admitted only to a fresh projection with a matching view/scope.
  Equal revision and equal status is a no-op; a lower revision is ignored.
  Equal revision with different status is a protocol conflict. A revision gap
  marks the projection incomplete without accepting the new state. Its revision
  advances a separate observed-revision floor; a reconciling snapshot must reach
  that floor. Interruption and a new read attempt cannot erase the known gap.
- Completed/failed/canceled cannot transition to another status in that turn,
  even with a higher revision. A conflict is sticky until a new scope/view is
  explicitly constructed; reads do not silently clear it.
- Interruption clears the pending attempt and marks observations stale. Events
  cannot clear stale/incomplete state. A new explicit read and matching snapshot
  are required. Reconnecting does not replay a write or restore an attachment.
- A malformed object is rejected by the parser before reducer use; the caller
  must retain its prior fenced state. Validation never echoes input into errors.

This is a constant-space projection, not an event log, supervisor, write ledger
or capability registry. View IDs and tuple equality are not authentication.
Source authenticity, live owner verification, effect admission, aggregate process
limits and cross-process restart persistence remain independent blocking work.

## Verification scope

Shared public fixtures cover accepted/rejected metadata in Python and Web.
Tests cover each scope field, invalid types/keys/lengths/enum/u64, returned-copy
isolation, old view/attempt/scope, duplicate/stale/gapped/conflicting revisions,
terminal nonresurrection, hidden/offline interruption and explicit read recovery.
No real transport, CLI, browser page or host qualification is claimed.

## Source and local qualification

- [Python validator](../packages/agentbox-core/src/agentbox_core/kebui_observation.py)
  and [588 tests](../tests/unit/test_kebui_observation.py)
- [Web validator/projection](../apps/web/src/features/conversation/conversationObservation.ts)
  and [204 tests](../apps/web/src/features/conversation/conversationObservation.test.ts)
- [Shared synthetic metadata vectors](../tests/fixtures/kebui_observation/v1.json):
  eight accepted cases and 159 rejected mutations; no user/provider data

Base is PR170 head `b1d46c9b7e80590fc036de4edbf69452ee29adb1`, tree
`b713e4c783eb6c38e5d248bf72aef1bac8e4a3e6`; its six first-attempt workflows
passed (25 successful jobs, two existing skips). This candidate is stacked on
that branch while PR169/170 remain separately unmerged. Its own exact-head CI
is pending at commit preparation; later PR results must not borrow base green.

Actual local results on the final code:

- `pytest -q tests/unit/test_kebui_observation.py tests/unit/test_waw_domain.py
  tests/unit/test_waw_recovery.py`: 616 passed, exit 0, using this worktree's
  explicit package-source PYTHONPATH and the existing isolated test environment
- full Web Vitest: 88 files / 2176 passed; Web typecheck, full ESLint, full
  Prettier and Vite production build: exit 0; existing >500 kB bundle warning
- repository Ruff: passed; mypy: 398 source files passed; Black checks on the
  two new Python files: passed; no formatter or dependency policy changed
- Web and Python tests first failed on the absent new modules; these are
  implementation-presence RED checks, not a claim that a released product failed
- a required nonenumerable Web scope field was initially dropped by object
  copying: the new negative assertion actually failed, then passed after rejecting
  nonenumerable required properties
- independent review reproduced gap revision 3 followed by snapshot revision 1
  restoring `fresh`; the unchanged regression failed before `revisionFloor` and
  passed after it. The floor survives interruption and rejects revisions 1/2
  until a snapshot reaches revision 3; gap content/status are never accepted
- independent source review CLEAR after both fixes; additional independent
  decoded-object differential checks covered 1175 variants with zero Python/Web
  mismatches, plus bounded state/view/gap/descriptor matrices. These are local
  software observations, not browser, authenticated transport or vendor evidence

No existing application/Runtime/WAW/protocol/installer/workflow source changed.
The new modules have no production importer. Full native Python and browser E2E
were not run locally for this slice; required unchanged CI workflows provide the
candidate's aggregate checks. No new UI or screenshot matrix is introduced.
