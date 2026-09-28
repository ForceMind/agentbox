# Project work tabs: source and behavior

Status: rc18 software candidate, 2026-09-29. AgentBox adapts the pure
normalization, deduplication, ordering and active-fallback idea from the fixed
upstream workspace pane model. The source repository is `getpaseo/paseo` at
commit `30178c4f58b67f8472901356e1484022bd835de0`, licensed Apache-2.0
with Mohamed Boudra copyright. The studied files and SHA-256 digests are:

| Upstream path | SHA-256 |
| --- | --- |
| `packages/app/src/screens/workspace/workspace-pane-state.ts` | `9b99bab33aaedd3c794bcf93f6ebdec924cd9238fb869f05bb520b16f0083f7e` |
| `packages/app/src/screens/workspace/workspace-tab-model.ts` | `3c646d07f51d3103f5b6fec9c215fbf5baa7bfe0f719d060380339984c058118` |
| `packages/app/src/workspace-tabs/model.ts` | `cb43ea5a1be3b1915b41fd150ab8961795641cba324fc76b07f8c2e365dc9265` |

The adapted code is `apps/web/src/features/workbench/workTabs.ts`; the
navigation UI is AgentBox React DOM code in `apps/web/src/app/WorkbenchTabs.tsx`
and `AppShell.tsx`. No upstream daemon, protocol, store, plugin target,
arbitrary cwd or Native UI code is included. Legal source attribution is
retained; the user-facing product and controls are AgentBox only.

Only formal Project IDs and explicit Project/Changed Paths/Workspace routes
become tab identities. Workspace identity includes Project and AgentType;
WAW handles and route extras are discarded. The strip retains at most twelve
in-memory entries for the current administrator session. It does not persist
content, authentication state or a path. A revisit deduplicates the matching
tab, and an active close navigates to a neighbor or the Projects list. A tab
is navigation, not a Runtime owner: close, reorder, return and browser
history do not start, attach, interrupt or Stop a WAW process. Workspace
re-entry uses the existing controller's fresh Project/WAW lookup.

This is a partial WS02 delivery. Multiple Agent conversations, split panes,
cross-device persistence, rich file targets and independently managed
sessions remain future work. Desktop/mobile E2E must verify close/navigation,
authentication scope and horizontal layout; local browser evidence does not
qualify a real Runtime host.

rc18 local browser evidence: the isolated desktop/mobile Chromium suite
completed 102 passes and 28 prescribed skips. Project→Changes→Workspace
navigation and active close passed; the tab and all visible controls meet
the existing 44px target check. The original Workspace route matrix passed
after the tab control-height repair. Desktop/mobile screenshots were inspected
for visible active selection and no document overflow. Session replacement
clears prior tab history in a separate AppShell unit test.
