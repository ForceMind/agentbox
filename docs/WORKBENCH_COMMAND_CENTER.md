# AgentBox command center: Project and page navigation

Status: rc23 software candidate, 2026-09-29. This is a partial WS14 delivery
under the [full capability plan](project/FULL_CAPABILITY_DELIVERY_PLAN.md).
The first command center opens from the authenticated AgentBox shell on
desktop or mobile, or with `Ctrl/Cmd+K`. It searches the fixed navigation
destinations and freshly loaded formal Project metadata. Selection changes
the browser route; it does not invoke a Runtime process, file read, Job,
Provider action, Agent control, script, plugin command, or arbitrary URL.
The result builder admits only the shell's fixed local routes and Project
IDs matching the formal `prj_` identity shape; a malformed API row cannot
become a navigation target.

The command center draws on the fixed Apache-2.0 source
`getpaseo/paseo@30178c4f58b67f8472901356e1484022bd835de0`:

| Studied source | SHA-256 |
| --- | --- |
| `packages/app/src/command-center/results.ts` | `cc6e266e53c7f83738a96212f5be9b0afa66fdc9d6d00b06fc839014fd98e2b4` |
| `packages/app/src/command-center/registry.ts` | `24baf867fa3ae0da5a4c264059a5ba30dd8f019f19003c3f4629909ecc7` |
| `packages/app/src/command-center/workspace-search.ts` | `44d237babc34d59a034126c8fa4c3b88c7f5ee2009ccc5f21f9ab06910a18c1b` |

AgentBox implements a fixed React DOM navigation surface in
`apps/web/src/app/CommandCenter.tsx`. It reuses AgentBox's previously
attributed Project matcher and current authenticated Project API; it does
not import the upstream daemon, registry, protocol, plugin execution, or
React Native UI. Upstream copyright and license attribution remain in the
repository notices and source records. Product labels show AgentBox only.

The modal mounts only while open, fetches Projects for the current Web
Session, limits the default list to five and matched results to 32, and
keeps page navigation available if the Project read fails. Closing aborts
the pending read; a session change unmounts the old result list and fences
late replies. The selected result
is keyboard reachable with arrows and Enter; Escape and the close button
leave the current route unchanged. The native dialog supplies modal focus
containment, and closing restores the prior focus target when it still
exists. Project names render as untrusted, direction-isolated text. A tab
or command result is navigation state, never a Runtime authority.

Named Project/Workspace labels, custom command registration, file search,
Agent controls, plugin contributions, multi-host results and persisted
history remain separate contracts. They may enter this UI only after their
own Project/session, permission and failure paths are implemented. CI and
browser evidence for this candidate are recorded in
[CURRENT_STATE](project/CURRENT_STATE.md); no real-host or production
qualification follows from the navigation UI.
