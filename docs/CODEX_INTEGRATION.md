# Codex Integration

Status: Phase 5 implementation, pending human review

## Boundary and supported intent

AgentBox manages an already installed Codex CLI only through behavior advertised
by that installation's public command help. It does not install, update,
uninstall, log in, migrate authentication, or use the standalone manager's
private directory layout in Phase 5.

The implemented intent set is deliberately closed:

| Intent | Runtime RPC | Public CLI selected by adapter |
|---|---|---|
| status/detect | `codex.status` | `--version`, `--help`, capability-specific help/status probes |
| start Remote | `codex.remote.start` | `remote-control start` only when advertised |
| stop Remote | `codex.remote.stop` | `remote-control stop` only when advertised |
| Pair device | `codex.pair` | `remote-control pair` only when advertised |

No RPC or HTTP request contains an executable, argv, environment, cwd, PID, or
shell fragment. The API process cannot spawn Codex. It talks to the non-root
Runtime Executor over a Unix Domain Socket; the root Privileged Helper remains
unimplemented and uninvolved.

## Executable resolution and installation evidence

Resolution uses `shutil.which("codex")` against the Runtime process's fixed
PATH, enumerates only matching PATH entries, resolves symlinks, and requires a
regular executable without group/world write permission. The selected target's
device, inode, mode, size, and mtime are revalidated immediately before every
spawn. The absolute selected path may be shown to the single administrator for
diagnosis, but cannot be supplied by Web or CLI.

Installation classification is best-effort:

- `$HOME/.local/bin/codex` is a conventional standalone hint, not a private
  managed-binary contract;
- bounded `npm list -g --depth=0 --json` may identify known public Codex package
  names;
- different resolved Codex PATH candidates or simultaneous standalone/npm
  evidence produce `conflict`;
- incomplete evidence produces `unknown` and never triggers removal or repair.

AgentBox does not scan the filesystem, open a Codex auth/config file, or invoke
the Phase 0 internal managed path.

## Capability and authentication model

Capabilities are independent tri-state values: `supported`, `unsupported`, or
`unknown`. Main help must expose `remote-control`; Remote help must independently
list `start`, `stop`, `pair`, and optionally `status`. Version comparisons never
enable a mutation. Timeout, malformed output, and non-zero help degrade safely.

Authentication is `authenticated`, `unauthenticated`, or `unknown`. A detected
public `login status` command is the only positive/negative signal. The
existence of Runtime HOME files or a successful version/help command proves
nothing. Pair is blocked when the public result is explicitly unauthenticated;
unknown remains visible as unknown rather than being relabelled.

## Controlled process policy

`ControlledProcessRunner` uses `asyncio.create_subprocess_exec` and a literal
argv. It never uses a shell, stdin, caller arguments, or inherited environment.
The allowlist is HOME, PATH, locale, TERM when present, and necessary XDG paths.
AgentBox, GitHub, OpenAI, Anthropic, AWS, loader, proxy, and other token-bearing
variables are not copied.

工作目录固定为 Runtime HOME。version/help/status 单次探测上限为 8 秒，npm
检测为 10 秒，lifecycle/Pair 命令为 30 秒。完整 status 探测的 RPC 预算为
70 秒，完整 mutation 的 RPC 预算为 100 秒；浏览器对应使用 85 秒和 130 秒，
确保内层先返回明确结果，避免浏览器或 API 已报告超时、Runtime 仍可能执行
副作用。普通 stdout 上限为 64 KiB、stderr 为 16 KiB，Pair 每个流为 4 KiB。
溢出和超时均 fail closed；超时清理只作用于 AgentBox 本次创建的进程组。

## Remote lifecycle and state

All mutations share one `asyncio.Lock`, so start, stop, and Pair cannot overlap.
当公开的 `remote-control status` 存在时，受控解析结果可返回 `running`、
`stopped` 或 `broken`，confidence 为 `reported`。没有公开 status 时，仅当
same-UID `/proc` 检查同时匹配 resolved executable 与已知
`remote-control start` argv 标记，才以 `inferred` 返回 `running`。成功的
start/stop 响应不会缓存成后续实时状态；缺少实时证据时必须返回 `unknown`，
避免 daemon 已退出却持续阻止重新启动。

Known `running`/`stopped` states return `already_running`/`already_stopped`.
Unknown stop state may invoke only the advertised official stop command. There
is no PID API, `pkill`, arbitrary signal, private lock file, or adoption of an
unmanaged systemd unit. The exact legacy `/etc/systemd/system/codex.service`
presence is a warning only.

## Pair secret lifecycle

Pair is a direct bounded secret response rather than a persistent Job:

1. authenticated Web mutation validates exact Origin/Host and Session-bound
   CSRF, then requires authentication no older than ten minutes;
2. Runtime action serialization and a ten-second default cooldown run before
   spawning;
3. stdout/stderr are classified sensitive, bounded, and never logged;
4. a conservative parser accepts exactly one labelled alphanumeric/hyphen code;
5. unknown output returns `CODEX_PAIR_OUTPUT_UNRECOGNIZED` without raw bytes;
6. API returns only `pair_code`, optional reported expiry, and `display_once`,
   with `Cache-Control: no-store` and `Pragma: no-cache`;
7. Audit stores only metadata and normalized outcome/error code;
8. Web holds one in-memory value, copies only on explicit click, and clears on
   Hide, navigation, or after 90 seconds;
9. CLI refuses JSON and non-TTY Pair output, then prints the value once.

The 90-second Web display timeout is not the Codex validity period. When Codex
does not publicly report expiry, AgentBox returns `null` and makes no estimate.

## API, CLI, and diagnostics

Implemented API:

- `GET /api/v1/codex/status`
- `POST /api/v1/codex/remote/start`
- `POST /api/v1/codex/remote/stop`
- `POST /api/v1/codex/pair-codes`

Implemented CLI:

- `agentbox codex status [--json]`
- `agentbox codex start`
- `agentbox codex stop`
- `agentbox codex pair`

Status can fall back to direct local read-only adapter execution if the Runtime
socket is unavailable. Mutations never fall back. Doctor adds only installed,
version, installation type, Remote capability/state, and finding codes. No raw
CLI output, unrelated process detail, authentication path, token, or general
systemd state is exposed.

## Compatibility and failure semantics

Stable AgentBox error codes include `CODEX_NOT_INSTALLED`,
`CODEX_EXECUTABLE_INVALID`, `CODEX_EXECUTABLE_CHANGED`,
`CODEX_REMOTE_UNSUPPORTED`, `CODEX_REMOTE_START_FAILED`,
`CODEX_REMOTE_STOP_FAILED`, `CODEX_PAIR_UNSUPPORTED`,
`CODEX_PAIR_RATE_LIMITED`, `CODEX_PAIR_TIMEOUT`,
`CODEX_PAIR_OUTPUT_UNRECOGNIZED`, `CODEX_UNAUTHENTICATED`,
`CODEX_COMMAND_TIMEOUT`, and `CODEX_OUTPUT_LIMIT_EXCEEDED`. Messages never echo
stderr. `unknown` is a correct observation, not an invitation to try a private
fallback.

Fixture compatibility changes require review. A future version may remain
detectable while all mutations are disabled until its public help/output shape
is understood. Installation/update remains planned for Phase 8.

## Test strategy

CI uses sanitized help fixtures and fake runners/adapters; it never needs a real
Codex account or daemon. Tests cover runner argv/environment/cwd/timeout/output
and cleanup, installation evidence, capability degradation, authentication,
state/idempotency, Pair parsing/cooldown/non-persistence, UDS schema/peer checks,
API auth/CSRF/audit/no-store, CLI privacy, and desktop/mobile Web flows.

Pair tests use synthetic canaries. They scan SQLite including WAL/SHM, captured
logs, Audit metadata, E2E temporary data, Playwright artifacts/report, and Git
diff. Fixture files contain no real account, token, Pair Code, hostname, auth
path, or private managed path.

## Real-host validation policy

Read-only `--version`, main help, Remote help, strict current-user process
inspection, and exact legacy-unit state may be checked on the assessed host.
Start/stop/Pair are attempted only after hermetic tests pass. An existing active
Remote session is never stopped. Pair output is consumed in memory and reduced
to PASS/FAIL; it is not copied to a file, report, PR, issue, log, or final
response.

The assessed root-owned Codex authentication and the Phase 0 UID/GID anomaly
are not migrated. Production `agentbox-runtime` must authenticate independently
during a later approved installation workflow.

### Phase 5 observed host result (2026-08-09)

- selected entrypoint: `/root/.local/bin/codex` (diagnostic display only);
- public version: `0.147.0`;
- installation evidence: standalone, no npm/PATH conflict detected;
- public capabilities: Remote/start/stop/Pair supported; native status
  unsupported;
- public authentication status: authenticated for the current root-owned
  development context;
- Remote state: unknown (no native status and no strict matching process);
- legacy exact unit: enabled but inactive; never modified;
- executable owner mismatch warning remains from the resolved managed target;
- real Pair parser/secret-channel validation: PASS; no code recorded;
- real start/stop: SKIPPED because state was unknown and preserving the active
  user environment takes priority.

These observations do not transfer to future `agentbox-runtime` authentication
or constitute a compatibility guarantee for later Codex releases.
