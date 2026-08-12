# GitHub Integration

Phase 7 uses the public `gh` CLI through a typed `GitHubAdapter` with prompts,
pagers, Git config inheritance, credential/SSH askpass, and unapproved Git
protocols pinned to safe non-interactive values. Authentication is determined
only by `gh auth status`; AgentBox never reads `hosts.yml`, stores a token,
exports credentials to the browser, or copies authentication between users.

GitHub features are available only when a redacted Project remote
conservatively identifies `github.com/owner/repo`. The Project view exposes a
bounded current-branch PR summary, base/head, public merge-state evidence, and
check state (`pass`, `fail`, `pending`, or `unknown`). Workflow dispatch,
rerun, cancellation, issue management, and arbitrary repository selection are
out of scope.

Draft PR creation uses fixed `gh pr create --draft` argv. Title, body, and optional base are bounded and validated; body travels on stdin, not through shell quoting or an editor. Prompts and pagers are disabled. The current branch is the head, and AgentBox does not guess an unknown base branch. Raw `gh` output and authentication material are never persisted or audited.
