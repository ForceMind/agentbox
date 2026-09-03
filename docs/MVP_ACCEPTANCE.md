# AgentBox MVP Acceptance

Candidate: `0.3.0rc1` (`v0.3.0-rc.1` planned; no tag created in Phase 10).

`PASS` means automated or recorded real-host evidence exists. `MANUAL` means a
release operator must perform the step with dedicated credentials or an HTTPS
deployment. `NOT SUPPORTED` means the RC intentionally provides no such action.

| User-visible capability | Status | Acceptance evidence / boundary |
|---|---|---|
| Authenticate to the control panel | PASS | Argon2id, Session/CSRF, desktop/mobile E2E; production use requires external HTTPS |
| View Codex install/auth/Remote status | PASS | Public CLI evidence and typed Runtime fixtures; Unknown remains explicit |
| Start/stop Codex Remote | PASS | Fixed typed Runtime actions; no PID/signal/shell surface |
| Generate/display Codex Pair Code | PASS | Recent-auth, no-store, one-time memory channel and persistence canary scans |
| Authenticate/pair a real Runtime user | MANUAL | Operator performs official flow as `agentbox-runtime`; no root credential copy |
| Start/list/stop Claude project Session | PASS | Managed tmux marker, typed Project ID, fixture and E2E coverage |
| Complete Claude Workspace Trust | MANUAL | Attach locally as Runtime identity; AgentBox never auto-accepts trust |
| Create an empty Project | PASS | Runtime-owned staging, marker and atomic no-replace activation |
| Clone an approved GitHub Project | PASS | HTTPS/SSH GitHub URL allowlist, hooks/prompts/submodules disabled |
| Inspect Git status | PASS | Structured porcelain v2 response with credential redaction |
| Create/switch ordinary branch | PASS | Strict ref validation; active Claude guard; no discard/stash/reset |
| Pull | PASS | Explicit origin upstream and fast-forward only; no merge/rebase fallback |
| Push | PASS | Explicit non-force refspec; no delete/mirror/force |
| Create a Draft PR | PASS | Fixed `gh pr create --draft`; bounded title/body; stdin body |
| Stage/commit/reset/clean/force push | NOT SUPPORTED | Dangerous Git operations are absent from API, CLI, Web, and Runtime protocol |
| Run Doctor and status | PASS | Sanitized control-plane, deployment, permission, Runtime and Project diagnostics |
| Fresh install from RC artifact | PASS | Isolated fixture/artifact smoke; not claimed as clean real-host validation |
| Reinstall idempotently | PASS | Secret/admin/DB/Projects/Runtime HOME preservation fixtures |
| Upgrade with online DB backup | PASS | Staged release, WAL-consistent backup, explicit migration and health gate |
| Roll back and verify | PASS | Release/DB/service/socket/health/readiness/version verification fixtures and OpenCloudOS rehearsal |
| Run API and Worker non-root | PASS | systemd identities and real-host evidence |
| Run Runtime non-root | PASS | `agentbox-runtime` identity, separate HOME and Project Root |
| Invoke arbitrary root action | NOT SUPPORTED | Helper exposes only six fixed argument-free AgentBox lifecycle actions |
| Listen publicly by default | NOT SUPPORTED | Default and validated listener is `127.0.0.1:8787` |
| Provider or Secret management | NOT SUPPORTED | Phase 11 software foundations exist; product API/UI/CLI and activation workflows remain incomplete |

This table is an MVP acceptance record, not a performance certification or
promise that third-party services remain compatible indefinitely.

## WAW software acceptance

| User-visible capability | Status | Evidence / boundary |
| --- | --- | --- |
| READY Project/Claude/Codex metadata selection | PASS | Typed exact query filters and browser metadata E2E |
| Explicit WAW Start and exact Stop confirmation | PASS | ASGI/Fake Runtime and desktop/mobile metadata tests; trusted pre-registered binding remains mandatory |
| Real browser terminal input/output/resize/detach/reconnect | NOT SUPPORTED | NOT ADMITTED; real transport/process implementation and host qualification remain Stage F gates |
| Runtime/API restart and host reboot continuity | NOT SUPPORTED | Pure recovery contracts exist; complete real end-to-end behavior still requires implementation and attributable host evidence |

These PASS rows describe software/control evidence, not a real terminal or
production-host approval. See [WAW software readiness](WAW_SOFTWARE_READINESS.md).
