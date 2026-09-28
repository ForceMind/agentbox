# Project search: source and boundary

Status: rc20 software candidate, 2026-09-29. AgentBox adapts ranked,
per-token text matching from `getpaseo/paseo` at pinned commit
`30178c4f58b67f8472901356e1484022bd835de0` (Apache-2.0; Mohamed
Boudra copyright). The studied source files and SHA-256 digests are:

| Upstream path | SHA-256 |
| --- | --- |
| `packages/protocol/src/search/text-match.ts` | `6c503b03948f51a27dd0a9055ddf1681f4914dc50a644fd307978848e65050b0` |
| `packages/app/src/command-center/workspace-search.ts` | `44d237babc34d59a034126c8fa4c3b88c7f5ee2009ccc5f21f9ab06910a18c1b` |

The adapted pure matcher is `apps/web/src/features/projects/searchProjects.ts`.
It uses AgentBox `ProjectData` and only fields already shown on the card:
display name, slug and a Git branch that passes the existing printable-ASCII
display check. Repository URL, hidden errors, session/Secret data and raw
Runtime output are not search fields. No upstream daemon, protocol, command
registry or executable action is imported. Legal attribution remains in source
and this document; user-facing product language remains AgentBox.

Search text is bounded by the page's 96-character input and stays in volatile
React state. It filters the Project list the authenticated API already
returned; an empty query preserves server order. Every token must match a
visible field, and equal-ranked entries retain API order. The page shows an
explicit no-match state and never treats filtering as deletion or an empty
account. It cannot reveal unloaded Projects if the server list itself is
incomplete or stale, and it does not grant filesystem or process authority.

This is partial WS14. Favorites, synced labels, universal command search and
multi-client reconciliation need separate persistence and authority contracts.

rc20 local browser evidence: 104 passing and 28 prescribed skipped isolated
desktop/mobile Chromium cases. The search scenario covers matching, no-match,
clear and no horizontal document overflow. Desktop/mobile page-top screenshots
were inspected after returning the page to scroll position zero.
