# Decision and Architecture Index

- `R12-VENDOR-ENROLLMENT-SOURCE-V1`: the sole production source for vendor
  versions and the Codex unauthenticated-output digest is a fixed,
  installer-owned, non-secret Runtime file. The authority-deferred provider
  requires a canonical, provenance-checked observation and re-reads it before
  opening lower resources. It pins host ID/revision, v2 manifest digest and
  enrollment epoch/state to the builder's one authority; missing/drifted
  input fails closed. See [fixed vendor enrollment](../WAW_R12_VENDOR_ENROLLMENT.md).

- `WORKBENCH-WS14-WORKSPACE-LABEL-COMMAND-CANDIDATE`: rc29 adds one
  query-only, metadata-only Workspace label choice per shared-catalog ID
  when the current route carries an exact formal `aws_` identity. Current
  session and route reads establish Project/AgentType; the choice uses the
  existing Workspace CAS API, exact ACK and GET readback without replay.
  No generic command, file or Runtime authority is added. See
  [Command center](../WORKBENCH_COMMAND_CENTER.md).

- `WORKBENCH-WS14-VISIBLE-LABEL-REFRESH-CANDIDATE`: rc27 keeps both label
  views current with a bounded visible-and-idle 30-second GET of the shared
  catalog and target assignment. During a background read, prior values
  remain visible but writes are fenced; failures become stale, not a replay.
  This is same-Control-Plane client convergence, not cross-host relay or
  Runtime authority. See [Project and Workspace labels](../WORKBENCH_PROJECT_LABELS.md).

- `WORKBENCH-WS14-WORKSPACE-LABELS-CANDIDATE`: rc26 assigns the rc24 shared
  catalog to the deterministic formal Project/AgentType Workspace identity,
  including before Runtime start. Per-admin ordered sets have their own CAS
  revision. Catalog deletion previews and transactionally rechecks both
  Project and Workspace counts; the Web picker waits for exact ACK/readback.
  Labels grant no Runtime or filesystem authority. Cross-host sync and broad
  command-center label actions remain open. See
  [Project and Workspace labels](../WORKBENCH_PROJECT_LABELS.md).

- `WORKBENCH-WS14-LABEL-MANAGER-CANDIDATE`: rc25 Project page reads the
  per-admin catalog/assignment, waits for exact ACK and fresh readback,
  supports create, assign, rename/recolor and impact-confirmed delete.
  Stale sessions and uncertain writes are fenced; no Runtime authority is
  added. Workspace labels and cross-host sync remain open. See
  [Project labels](../WORKBENCH_PROJECT_LABELS.md).

- `WORKBENCH-WS14-NAVIGATION-LABELS-CANDIDATE`: rc24 adds one per-admin
  immutable-ID label catalog with ten fixed colors, normalized names,
  revisioned atomic edit/delete and ordered formal Project assignments.
  Labels are Control Plane metadata, never Runtime or filesystem grants;
  Web picker and Workspace assignment remain separate. See
  [Project labels](../WORKBENCH_PROJECT_LABELS.md).

- `WORKBENCH-WS14-COMMAND-CENTER-CANDIDATE`: rc23 adds one authenticated
  AgentBox command center for fixed page/formal Project navigation only.
  Current-session Project reads, bounded results and session fencing do not
  authorize file, Agent, Runtime, script or plugin commands. See
  [Command center](../WORKBENCH_COMMAND_CENTER.md).

- `WORKBENCH-WS14-FAVORITE-UI-CANDIDATE`: rc22 Project cards read the rc21
  per-admin preference API, wait for exact revision ACK, and reconcile
  conflicts/uncertain responses by GET without retrying a PUT. A tab/session
  change fences old responses. This is no Runtime authority. See
  [Project favorites](../WORKBENCH_PROJECT_FAVORITES.md).

- `WORKBENCH-WS14-FAVORITES-CANDIDATE`: a per-AdminUser/formal-Project
  favorite is Control Plane metadata with a revision/CAS contract, not a
  Runtime or file capability. rc21 implements the backend/API candidate;
  Web UI and multi-browser acceptance are unfinished. See
  [Project favorites](../WORKBENCH_PROJECT_FAVORITES.md).

- `WORKBENCH-WS14-PROJECT-SEARCH-CANDIDATE`: rc20 ranks only visible fields
  from the authenticated Project list in volatile page state. No query is
  persisted or sent to an action endpoint; no-match is distinct from no
  Projects. Favorites, labels and command center remain separate. See
  [Project search](../WORKBENCH_PROJECT_SEARCH.md).

- `WORKBENCH-A3-GIT-FD-CWD-CANDIDATE`: rc19 adds an internal Linux-only
  child-cwd descriptor seam with pre/post named identity checks and no
  content authority. It cannot be called by Web/API and is not composed into
  a Git patch action. See [A3 cwd proof](../WORKBENCH_A3_GIT_CWD.md).

- `WORKBENCH-S02-PROJECT-TABS-CANDIDATE`: rc18 keeps up to twelve current-session
  navigation targets for formal Project, Changed Paths and Project/AgentType
  Workspace routes. Tabs are not Runtime, file or conversation authority;
  closing one only navigates. This is partial WS02, without persistent tabs,
  split panes or multiple conversations. See
  [Project work tabs](../WORKBENCH_PROJECT_TABS.md).

- `WORKBENCH-A3-GIT-CONTENT-ROOT-CANDIDATE`: an internal rc17 class holds and
  rechecks only fixed Project/Git directories and metadata-file descriptors.
  Its purpose is to reject replacement and alternate stores before any
  content action exists. It exports no fd or bytes and does not yet prove
  complete object-store or child-cwd provenance. See
  [A3 patch content contract](../WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md).

- `WORKBENCH-A3-PATCH-CONTENT-CANDIDATE`: draft the next bounded Runtime-only
  extraction and a separate encrypted Project content channel before exposing
  patch text. Its selector is not path authority; staged/unstaged and unsupported
  cases have explicit outcomes. Descriptor-held Project/Git provenance is a
  prerequisite because current Git metadata uses path-based cwd. This is a
  proposed software contract, not a
  shipped action or an Accepted deployment configuration. See
  [A3 patch content contract](../WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md).

- `WORKBENCH-S02-CHANGED-PATHS-V1`: the rc16 AgentBox Project page links to a
  separate authenticated Changed Paths view backed only by the rc15 metadata
  API. It reuses the upstream-derived directory order but flattens a
  path-only tree, so absent line stats are not represented as zero. Browser
  observations are invalidated on Project/session change and hidden-document
  return; pagination never merges changed snapshots. Path rendering escapes
  control/format characters and grants no path-based Runtime action. Patch,
  preview and editing remain separate A3/S04 contracts. See
  [A3 Git Changes](../WORKBENCH_A3_GIT_CHANGES.md).

- `WORKBENCH-A3-GIT-CHANGES-METADATA-V1`: a READY formal Project can request
  bounded Git path/status metadata through one fixed Runtime action. No
  request-supplied path, argv, cwd or environment reaches Git. The API keeps
  session authentication and no-store; the Runtime owns repository checks,
  porcelain-v2 parsing, limits and snapshot-digest pagination. Path metadata
  is display data, not a content/read/edit grant. Patch bodies, file preview
  and user-visible Changes rendering remain distinct A3 work. See
  [A3 Git Changes metadata](../WORKBENCH_A3_GIT_CHANGES.md) and
  [ADR 0009](../adr/0009-workbench-identity-and-content-boundary.md).

- `R12-RUNTIME-FIXED-PROFILE-V1`: Runtime's expected WAW mode comes only from
  fixed `/var/lib/agentbox-waw/runtime-profile.v1.json`, separate from API
  mode and inaccessible to API/Worker. The installer creates exact disabled
  bytes; the Runtime verifies a root-owned, Runtime-group-readable 0440 leaf
  under its root-owned 0750 directory. A proven absent leaf preserves old
  disabled installations; malformed or drifting state fails. Until C3-b
  composition exists, an explicit `filesystem-v2` value makes `_main` fail
  before constructing the legacy listener. Future mode updates require a
  coordinated API/Runtime CAS transaction and host qualification. See
  [Runtime profile](../WAW_R12_RUNTIME_PROFILE.md).

- `R12-C3B-DYNAMIC-CONFLICT-SNAPSHOT-V1`: the existing supervisor executor
  remains the sole source of current WAW state. It maps formal Project IDs to
  unique current relative keys and exposes a synchronous, read-only state
  snapshot for legacy-start arbitration. A binding update, inflight operation,
  restart quarantine, ambiguous mapping or map change during observation
  yields a blocking state instead of `ABSENT`. The snapshot does not create
  a second WAW registry, grant browser access or supply legacy Claude/Codex
  observations; production `_main` needs one later sealed probe composition.
  See [C3-b composition closure](../WAW_R12_C3B_PRODUCTION_COMPOSITION.md).

- `R12-D-DISABLED-API-RESOURCES-V1`: the installer creates only the canonical
  `disabled` API profile under `/etc/agentbox` and a fixed read-only singleton
  lock under a root-owned `/run/agentbox-waw-api` parent. It validates exact
  bytes, owner, group, mode, link count and stable no-follow file identity;
  existing canonical `filesystem-v2` bytes are preserved, not promoted by an
  installer default. Invalid or drifting content fails closed. The profile
  is operator state and survives upgrades/rollback/uninstall; the separate
  atomic CAS mode updater remains R12-D work. See
  [R12-D API resources](../WAW_R12_D_API_RESOURCES.md).

- `R12-D-DORMANT-WAW-SOCKETS-V1`: the installer owns exactly two WAW socket
  units with distinct fixed `FileDescriptorName`, `SocketUser=agentbox-runtime`,
  `SocketGroup=agentbox-runtime-ipc` and mode 0660. Installation and upgrades
  do not enable them. `/run/agentbox-waw` remains root-owned and unwritable by
  Runtime; private scratch, tmux and persistent vendor/key directories have
  fixed owners/modes. Existing new paths with mismatched provenance are not
  adopted. Stop/uninstall and rollback to a backed-up pre-WAW release close
  the exact unit set; changed files fail closed before database restoration.
  A unit asset change needs an explicit migration path because HostOperations
  only stops package-identical installed WAW units. This is software/fixture
  evidence, not G3 host activation. See
  [R12-D socket substrate](../WAW_R12_D_INSTALLER_SOCKETS.md).

- `R12-SYSTEMD-NAMED-SOCKETS-V1`: systemd 可以把两个 socket unit 指向同一
  Runtime 服务，但不保证跨 unit FD 的顺序。Runtime 只接受 FD3/4 恰好两个、
  各有唯一固定 `LISTEN_FDNAMES`，分别验证名称到 control/stream 固定路径
  及 owner/gid/mode/inode，再归一化返回。路径必须由 Runtime 拥有；FD
  可保持 PID 1 的 root:root 所有权（systemd 对 socket 路径执行 chown），
  或为 Runtime 本身所有；其他 FD owner 拒绝。重复/未知名称、错配路径或多余 FD
  fail closed；真实 PID1 与重启资格另验。来源为
  [systemd.socket](https://github.com/systemd/systemd/blob/main/man/systemd.socket.xml)；
  [R12-D](PRODUCTION_READINESS_PLAN.md#r12-dinstallersystemd-与制品)
  与 [G3/HG-04](../WAW1_HOST_GATE_CHECKLIST.md#g1g5-证据矩阵) 采用同一合同。

- `R12-C3B-AUTHORITY-DEFERRED-RESOURCES-V1`: the filesystem-v2 builder issues
  exactly one verified Runtime authority. A distinct provider owner opens the
  six executable handles, nine fixed installed roles and cgroup delegation
  only after receiving that same authority. Any mismatched Project root,
  descriptor or incomplete cleanup fails closed before admission. This is a
  software construction decision under the approved R12 plan; `_main`,
  installer and real host evidence remain separate. See
  [C3-b composition closure](../WAW_R12_C3B_PRODUCTION_COMPOSITION.md).

- `R12-AUTH-PROBE-BUDGET-V1`: the fixed 5.0s spawn-to-exit probe budget (plus
  0.25s TERM grace and 1.0s drain margin) is owned inside the probe port; the
  control listener's per-connection deadline is only an envelope, so
  `build_waw_control_server` widens exactly the `workspace.workspace.start`
  dispatch-plus-response deadline to `WAW_START_OPERATION_TIMEOUT_SECONDS`
  (8.0s) while every other action keeps 2.0s. The API-side
  `WAWControlClient` is reconciled through a per-action
  `action_timeout_seconds` map: the production composition assigns exactly
  `workspace.workspace.start` 9.0s (8.0s server envelope plus 1.0s transport
  margin, so the server's bounded response arrives before the client would
  poison its transport), and every other action keeps the 2.0s default.

- `R12-AUTH-PROBE-NATIVE-V1`: the approved software objective is refined by
  [the fixed auth-probe contract](../WAW_R12_RUNTIME_AUTH_PROBE.md): separate
  160-byte AWP1/8-byte AWRP ABI, no Project/PTY/bridge/tmux authority, offline
  fixed status commands and one generation-bound cgroup borrow. It preserves
  old interactive ABI; Python integration and actual host/vendor qualification
  remain required before claiming C2 or Runtime main availability.

- `R12-API-PROFILE-V1`: under approvedPRP software scope,
  [fixed API bootstrap](../WAW_R12_API_BOOTSTRAP.md) uses one installer-owned,
  bounded root-owned profile and retains disabled compatibility only for a
  verified absent leaf; ordinary environment/request input cannot enable WAW.
  Implementation and target qualification remain separate from this contract.

- `R12-EXECUTION-2026-09-08`: Owner explicitly approved
  [PRP-2026-09-08-v1](PRODUCTION_READINESS_PLAN.md) and instructed execution.
  R12-A–K is the finite checklist, one Goal is active, and stable software
  contracts may be closed before concrete host inputs arrive. Mac Chrome/Edge
  terminal and mobile management/Stop are the approved suggested scope;
  new client qualification, real host/key/credential operations and production/
  publication are not implied by software-plan approval.

- `WORKSTATION-EVOLUTION-2026-09-08`: the Owner requested a seven-project
  evidence-based audit and the first independently verifiable improvement within
  current authority. [WORKSTATION_EVOLUTION](../WORKSTATION_EVOLUTION.md) and
  [CAPABILITY_MATRIX](../CAPABILITY_MATRIX.md) record scope and Proposed follow-ups.
- `WEV-1-BROWSER-RETURN`: an implementation refinement of the existing WAW3
  browser-lifecycle contract: interruption invalidates the current Runtime
  observation and confirmation; return re-reads status without automatic
  lifecycle actions. No new wire/API/DB/host/Secret authority is created.
  Local reception time is descriptive only; no new TTL or trust-time guarantee.

## Current execution policy

- `GOV-AUTOMATION-1` is superseded for routine repository work: the Coding Agent
  may perform CI-gated Ready/merge/read-back without a governance bot or an
  additional Owner Merge Authorization. See `GOVERNANCE.md` and `AGENTS.md`.
- `GOV-AUTOMATION-2`: revalidate live repository identity, exact PR/head/base and
  terminal CI; snapshots do not override Git/GitHub.
- `GOV-AUTOMATION-3`: real-host activation, architecture decisions, Secret
  handling and production support remain subject to explicit authorization
  and evidence. Routine merge permission does not satisfy these gates.
- `EXECUTION-2026-09-03`: Owner authorized parallel multi-agent development and
  requires GitHub/document updates at every completed stage. See
  `EXECUTION_PLAN.md` for scope, ownership, dependencies and exit criteria.

- `MAC-DEVELOPMENT-2026-09-03`: Owner clarified continued development on the
  current Mac. Separate software implementation/local+CI checks from actual
  Linux activation and qualification; a missing Linux target does not block
  independent software work. See `NEXT_ACTION.md`.

## Architecture and evidence

- `WEB_AGENT_WORKSPACE_ARCHITECTURE_AUTHORIZATION_REVIEW.md`: historical WAW
  proposal and detailed safety contracts; its historical status is retained.
- `docs/WAW1_CONTRACT_MATRIX.md`: implementation/evidence mapping, not host
  readiness or new authorization.
- `docs/WAW1_HOST_GATE_CHECKLIST.md`: required host observations and recovery
  conditions; unobserved items remain `NOT RUN`.
- `docs/WAW3_RECOVERY_CONTRACTS.md`: software recovery classification, browser
  event fences, validation mapping and explicit unimplemented integration scope.
- `docs/WORKSPACE_METADATA_WORKFLOW.md`: current metadata UI/control workflow, exact lookup and Stop boundaries, tests and visual evidence limits.
- `docs/WAW_SOFTWARE_READINESS.md`: immutable software/artifact evidence, current capability limits and explicit Stage F input/gates.
- `CURRENT_STATE.md`: last verified snapshot. `NEXT_ACTION.md`: current software
  stage and remaining gates.

- `MAC-RUNTIME-COMPOSITION-2026-09-03`: continue concrete lifecycle-to-supervisor
  software composition on Mac. Read-only status probes and durable generation
  reservation are required before claiming Runtime observations; attachment
  prepare remains separate from actual admission. No host activation or
  architecture proposal approval is inferred.


- `REMAINING-EXECUTION-2026-09-03`: Owner requested reassessment and persistent
  parallel development, routing complex work to `gpt-5.6-sol` and ordinary work
  to `gpt-5.6-terra`. Current finite goals/dependencies are in
  [REMAINING_PLAN.md](REMAINING_PLAN.md). Routine implementation/CI/merge continue;
  unapproved architecture and real-host/key/production actions retain their gates.

- `WAW-STREAM-SUPPLEMENT-ACCEPTED`: the complete protocol supplement is accepted by the Coding Agent under the Owner's explicit 2026-09-03 software decision delegation. It resolves key/context, verification, ACK, drop, limit and signed-pin contradictions. Prior independent review passed; implementation is R4/R5, and host/production evidence remains separate.

- `SOFTWARE-DECISION-DELEGATION-2026-09-03`: Owner explicitly permits the Coding Agent to decide goals, plans and software architecture for the ongoing objective. See GOVERNANCE for scope; resolve software choices with evidence/review without repeatedly requesting the same authorization.

- `WAW-WIRE-IMPLEMENTATION-2026-09-03`: under delegated software authority, the [wire contract](../WAW_WIRE_CONTRACT.md) records precise early-failure precedence, exact numeric/version handling, retry limits, bounded opaque-source pairing and synchronized sequence acceptance. Independent review and actual parser-budget evidence are recorded separately from authority effects.

- `WAW-BROWSER-BOUNDED-MODEL-2026-09-04`: Owner accepted the
  [browser implementation decision](WAW_BROWSER_IMPLEMENTATION_DECISION.md).
  R9 uses a project-owned bounded terminal model over typed tokenizer output,
  keeps the 32 KiB logical-line count across waits without a wall-clock expiry,
  retains the 100 ms incomplete carry deadline, and immediately fences ambiguous
  parser state. xterm is not admitted for this implementation.
- `WAW-BROWSER-TRUST-PROVIDER-GATE-2026-09-04`: signature/lifecycle consumer
  software may proceed, but a real independent provider must separately prove
  bootstrap authority, atomic floors, trusted time, network/origin policy and
  loss/revocation delivery. Missing provider keeps production Connect closed.
- `WAW-BROWSER-TRUST-PROVIDER-V1-2026-09-04`: Owner approved a managed MV3
  Chromium extension, fixed Native Messaging bridge and independent local
  `trustd`. The ordinary build is externally inert; production Connect requires
  a CRX-key-derived ID, exact Origin/update policy and R12 installation evidence.
- `WAW-BROWSER-ROOT-CHECKPOINT-V1-2026-09-04`: a successor accepted while its
  exact predecessor is valid creates an atomic provider checkpoint binding
  `accepted_at`, root/signer identity and the complete root-history digest.
  Later rotations verify the previous exact prefix before advancing this
  cumulative proof. Restart keeps full history/tombstones, checks the direct
  signer/root pair at that recorded time and checks current root/pin at final
  trusted time; missing, late, truncated, forked or rolled-back evidence fails
  closed.
- `BROWSER-LOCALE-V1-2026-09-04`: only `navigator.languages[0]` selects UI
  locale; primary language `zh` maps to `zh-CN`, every other or malformed value
  maps to English. Technical identifiers and protocol values remain English.
- `WAW-INPUT-OWNERSHIP-2026-09-04`: one 65536-byte encoded INPUT ledger follows
  ownership from native ready through ASGI/relay pending to Runtime send. Layer
  transitions do not release/reacquire capacity, and first overflow synchronously
  fences I/O. The 128-slot/8 MiB parser pool remains a separate budget.
- `WAW-R11-COMPOSITION-2026-09-05`: R11 executes serially as rc6 controller
  composition, rc7 deterministic composed failure injection, rc8 artifact/ops
  rehearsal and rc9 full bilingual UI. rc6 first binds control/stream to the same
  pidfd-backed API/Runtime peers, persists Runtime epoch classification, adds
  bounded Runtime redraw and single application ownership. See
  [WAW_R11_CONTROLLER_COMPOSITION](../WAW_R11_CONTROLLER_COMPOSITION.md).
