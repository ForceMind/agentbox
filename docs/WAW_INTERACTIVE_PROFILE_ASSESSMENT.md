# Interactive CLI profile assessment

Assessment date: 2026-09-03. This records implementation gaps and public vendor
documentation, not an approved replacement for the fixed execution contract.
No installed CLI, credential store, Runtime HOME, real key or target host was
opened or executed. Product qualification remains separate from Mac development.

Read [REMAINING_PLAN](project/REMAINING_PLAN.md) for R10 dependencies and the
[historical architecture](../WEB_AGENT_WORKSPACE_ARCHITECTURE_AUTHORIZATION_REVIEW.md)
for the isolation, immutable executable, argv and exact environment requirements.

## Current code versus required execution

The existing supervisor/executor composition and typed lifecycle API do not yet
start the required interactive CLI process tree. Current legacy Claude commands
use Remote Control, the existing Codex command prototype has no interactive argv,
and the real tmux adapter is Claude-only. Renaming those paths would not provide
the required pane bootstrap, isolated bridge, fixed CLI or exact attach process.

`waw_manifest_codecs.py`'s `RuntimeHostManifest` contains fingerprints for tmux,
bridge, Claude, Codex and attach supervisor. It does not define the pane-bootstrap
fingerprint or a complete immutable execution inventory with paths, supported
versions, version-bound probes and profile identity. Its current codec must not
silently accept extra fields or treat a supplied path as authority.

The fixed launch and WBR boundaries also need exact record fields, descriptor
numbers, packet encoding and lifecycle rules before production composition can
consume them. These are not browser/API inputs; Runtime alone derives execution
from trusted installation records and formal Project identity.

## Public CLI evidence and limits

| Topic | Observed public contract | Consequence for R10 |
| --- | --- | --- |
| Codex entry | No subcommand starts the interactive interface. `login status` documents successful authentication with exit 0. | The version-bound probe must distinguish unauthenticated from unsupported/failed/unknown; arbitrary nonzero exit is not a sufficient classification. |
| Codex retention | `--ephemeral` is documented for `codex exec`. `history.persistence = "none"` controls history.jsonl; an explicit `log_dir` enables file logging. | These facts do not establish an interactive all-retention-disable profile. |
| Codex state root | `$CODEX_HOME` selects configuration/state; default `~/.codex`. | The exact ten-key WAW environment has no `CODEX_HOME`. Do not assume XDG variables relocate vendor state. |
| Claude retention | `CLAUDE_CODE_SKIP_PROMPT_HISTORY` is documented for transcript/prompt-history control. `--no-session-persistence` remains a print-mode option. | Other tool-result, paste-cache, file-history, plan/task and crash/telemetry sinks still require version-bound evidence. |
| Claude state root | `$CLAUDE_CONFIG_DIR` can change the default `~/.claude` location. | The current exact environment has no such variable; silently adding it would change the contract. |

Sources inspected: [Codex CLI commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli),
[Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference),
[Codex advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced),
[Claude CLI usage](https://code.claude.com/docs/en/cli-usage),
[Claude directory](https://code.claude.com/docs/en/claude-directory), and
[Claude settings](https://code.claude.com/docs/en/settings).
These are documentation observations, not tests of a particular installed build.

## Contract work still required

The present vendor HOME is root-owned `0750`; only `.config`, `.cache`,
`.local/share` and `.local/state` are writable, plus the separate fixed TMPDIR.
The documented vendor defaults cannot be assumed to fit that layout. A reviewed
execution-profile supplement must resolve these items together:

1. Exact supported native build identities and version/probe output rules for
   both AgentTypes, including unknown/error handling and immutable inventory.
2. Vendor state roots and fixed environment/configuration needed for official
   local login and Project Trust without changing the closed authority model.
3. Explicit retention, telemetry, update, crash-report and implicit credential
   discovery settings, plus the remaining host evidence for each supported build.
4. Exact bootstrap/bridge/attach launch records, descriptor ownership and WBR
   schema, including fail-closed cleanup and loss/restart behavior.

The descriptor-held executable verifier is independent software groundwork: it
checks trusted inventory paths, file/ancestor identity and content pins without
launching anything. It cannot certify version compatibility, install a manifest,
prove vendor retention policy, or provide namespace/PTY/real-host evidence.

Until the missing profile decisions and host observations are satisfied, actual
CLI execution and product readiness remain unclaimed. Existing Project metadata,
typed lifecycle contracts and reviewed software foundations remain usable within
their documented scope.
