# Current Authorized Action

## 2026-09-30 R12 rc30 vendor enrollment candidate

当前只推进 [首个可用单机 RC](RELEASE_ITERATION_PLAN.md) 的 R12 依赖。
Draft #122 已对齐 `origin/main`，此前 head `8d11561` 的 26 项 CI 已终态
（24 success、2 prescribed skips）。当前 rc30 后继批次新增 installer
可复用的严格数据编码与真实文件/父目录替换、cleanup 失败测试；163 项
定向测试及 Ruff/Black 通过，待新 head 的 exact-head CI。
根据当前 AGENTS.md Review Protocol 完成主智能体自查并准确标注；
修复发现、相关回归与新 head 的必需 CI 通过后，可按已授权流程正常合并。
旧文档的额外独立审查机械门槛与当前 AGENTS.md 不符，不再作为恢复前提。
原 C3-b WIP 保全；#117 与 WS14 后续功能不进入本版。随后才处理
production `_main`、installer writer 与 D/E/F，真实 host/Secret/CLI/
recovery 验收仍需具体输入和授权。以下记录为历史行动项。

## 2026-09-29 首个可用 RC 收口

Owner 要求按版本迭代，不再以 70 项全量清单驱动并行旁支。当前唯一产品
目标与退出条件见 [逐版本计划](RELEASE_ITERATION_PLAN.md)。
`origin/main = 3a23f350582287de6b00499b8d4daa5d69c52011` 是 rc29
软件候选；六类 post-main workflow completed/success，但 R12 真实
host/client/CLI/recovery 未验收，不能称完整可用版本。

下一项是取得 Draft #122 的独立 Architecture/Security/Test 结论，处理
R12-C3-b 原工作区 WIP，再完成 `_main`、D/E/F 软件与制品。#117 保持
Draft，WS14 新功能暂停；现场输入缺失时报告本版阻断，不转去扩大功能
范围。Host、Secret、付费调用、重启、生产及发行仍按具体授权执行。
以下旧行动项保留为历史记录，不再驱动新的 WS14 批次。

## 2026-09-29 WS14 Workspace label command choices

`origin/main` remains rc27 merge
`458e7a5c9a87d50ebd9a4cd1040e7a51b148929a` with six successful
post-main workflows. Security-critical R12 rc28 Draft #122 has 26
terminal head checks (24 success, two prescribed skips) but awaits an
independent Architecture/Security/Test review; #117 remains Draft for the
same separate review gate. Continue independent WS14 software on
`codex/workbench-command-labels`: query-only label choices for an exact
formal Workspace route, current-session metadata validation, existing
CAS/Origin/CSRF API, exact ACK and GET readback, local panel invalidation,
pending/hidden/conflict fences, localization, desktop/mobile validation,
version and exact-head CI, then normal merge/read-back. The rc28 action
below is historical; real host/Secret/production gates remain untouched.

## 2026-09-29 WS14 visible-client label refresh

PR #120 delivered rc26 as merge
`88d2db79dd3cf58cfe0093ee90963f1ecfd45d35` with exact parents
`cab33679ec91bc2e46384f24e9a8cd3e4e985fa9` and
`816920a3c301569b8cd64ef99e7532537804d111`; six post-main workflows
completed successfully. On `codex/workbench-label-live-refresh`, finish
rc27's bounded visible-client Project/Workspace label refresh, prove
external-change convergence and hidden/pending/read fences, update the
version and acceptance record, then run exact-head CI, normal merge and
read-back. Cross-host synchronization remains S08. #117 stays Draft until
its independent security-critical review; R12 real-host/Secret/production
gates remain separate. The rc26 action below is historical.

## 2026-09-29 WS14 Workspace labels

Finish rc26 on `codex/workbench-workspace-labels`: shared-catalog formal
Workspace assignments, explicit Project+Workspace delete-impact count,
current-session Web readback and localized states. Run migration/foreign-key,
CAS/concurrency, API auth/Origin/CSRF, full Web/build, desktop/mobile browser
and release-version checks. Update exact local evidence, push feature branch,
obtain terminal exact-head CI, then normal merge and exact main/PR/workflow
read-back. Keep #117 Draft until its independent security-critical review;
continue R12 host and Secret gates separately. The prior rc25 action below
is historical and no longer directs this branch.

## 2026-09-29 WS14 Project label manager Web UI

PR #118's exact head `b7a529dfe92fabd0b83486ee6082296c64713fc9`
passed 26 terminal checks. GitHub generated main merge
`36aa7294c4d9c8eaa3283281022e61cf8bbc4f69` with that head as second
parent, but PR #118 remains OPEN in the API and no post-main workflows are
listed. Preserve both facts; do not force push, fabricate a merged PR state
or close the PR merely to remove the inconsistency. On
`codex/workbench-project-labels-ui`, finish rc25 Project-page label
create/assign/edit/delete with current-session GET readback, exact server
ACK, confirmed delete count, localization, desktop/mobile browser evidence,
version and regression checks under
[Project labels](../WORKBENCH_PROJECT_LABELS.md). Run exact-head CI, normal
merge and read-back. Subsequent Workspace assignment and cross-host label
sync remain separate. Draft A3 PR #117 awaits independent security-critical
review; R12 `_main` and real-host/Secret/production gates remain open.

## Historical 2026-09-29 WS14 label catalog and formal Project assignments

PR #116 delivered rc23 command-center navigation as merge
`3e0069381a4d8f867e333191f298b4847256d751`; six post-main workflows
succeeded. Draft PR #117 passed exact-head CI but remains unmerged pending
independent security-critical review and separate A3 content gates. Continue
on `codex/workbench-project-labels`: finish rc24 additive migration,
per-admin immutable label catalog, ordered Project assignment CAS, atomic
rename/delete, strict authenticated Origin/CSRF/no-store API, Audit,
capacity/concurrency/upgrade/restart tests and source/version records under
[Project labels](../WORKBENCH_PROJECT_LABELS.md). Then run exact-head CI,
normal merge and read-back. The Web picker and Workspace assignment follow
on the same shared label identity; they are not implied by backend delivery.
R12 `_main` still needs target fixed inputs and positive legacy Codex Remote
state; real-host/Secret/production gates remain separate.

## Historical 2026-09-29 WS14 authenticated command center

PR #115 delivered the internal staged Git selection policy as merge
`885c623cf1114d23c5fdc13503f4a2a598985c5b`; all six post-main
workflows succeeded. On `codex/workbench-command-center`, finish the rc23
fixed page/formal Project navigation UI under
[Command center](../WORKBENCH_COMMAND_CENTER.md): current-session API read,
desktop/mobile dialog, keyboard/focus behavior, stale-session fences,
localized errors, version and browser evidence. Then run exact-head CI,
normal merge and read-back. Wider command actions remain bound to their own
future permissions and service contracts. Resume A3 object-store provenance
and descriptor-held staged extraction as the independent content track.
R12 `_main` still requires actual fixed inputs and a positive legacy Codex
Remote state source; real-host/Secret/production gates remain separate.

## Historical 2026-09-29 A3 staged selection policy

PR #114 delivered rc22 Project favorites UI and its six post-main workflows
completed successfully. On `codex/workbench-staged-read-policy`, finish the
Runtime-only staged path/index eligibility check and negative fixtures under
[A3 patch content contract](../WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md).
Run exact-head CI, normal merge and merge read-back. Next, prove object-store
provenance and a descriptor-held bounded staged extraction before any
selector or encrypted content route. R12 `_main` still requires actual fixed
inputs and a positive legacy Codex Remote state source; the production
profile must keep failing closed until that graph is complete.

## Historical 2026-09-29 WS14 Project favorites UI and native read-back

PR #113 merged as `8fb017f3e294c4a303547da729b007e9605ed9a0`
with exact parents; its post-main Backend native job first failed on an
incomplete tmux pane-death status, then a same-SHA failed-job rerun succeeded.
Validate the scoped transitional-state test repair on rc22's exact head.
On `codex/workbench-project-favorites-ui`, complete the rc22 favorite control
under [WS14 favorites](../WORKBENCH_PROJECT_FAVORITES.md): server revision
ACK, conflict/uncertain GET read-back without PUT replay, session/visibility
fencing, desktop/mobile screenshots, local tests and exact-head CI. Then
normal merge and read-back. Named labels and command center remain later
WS14 slices; A3 content and R12 real-host gates remain separate.

## Historical 2026-09-29 WS14 Project favorites

PR #112 merged as `01a0ecd5eb21f74fe8605913bffd0c98bf322165`
with exact parent read-back and six successful post-main workflows. On
`codex/workbench-project-favorites`, finish the rc21 additive per-admin
preference schema, transactional revision/CAS service and typed authenticated
GET/PUT API under the [favorites contract](../WORKBENCH_PROJECT_FAVORITES.md).
The API must never call Runtime. Verify migration, concurrent writes, stale
conflicts, auth/CSRF/Origin and restart before exact-head CI and normal merge.
The Web toggle/pending/conflict flow, labels, ordering and command center
remain separate WS14 slices.

## Historical 2026-09-29 S02/WS14 Project search

PR #111 merged as `2d64ccde14877118f13f9c843d0c0aae0808dce0` with
exact parent read-back and six successful post-main workflows. Continue on
`codex/workbench-project-search`: verify the pure ranked matcher and the
authenticated Projects page against loaded formal Project data, nonmatching
and failed/loading states, desktop/mobile layout and visible rc20 version.
Retain the pinned source and attribution in
[Project search](../WORKBENCH_PROJECT_SEARCH.md), then run exact-head CI,
normal merge and read-back. Search remains read-only page state; favorites,
sync and the command center need separate contracts. A3 Git object provenance
and R12 `_main` are still unfinished, with real-host/Secret/production gates
separate.

## Historical 2026-09-29 S02/A3 descriptor-bound Git cwd

PR #110 merged as `6cd045dd8831283e2c0d0333a39461671b04bf76` with
exact parent read-back and six successful post-main workflows. Continue on
`codex/workbench-git-fd-cwd-v2`: verify the Linux-only fixed process runner
cwd descriptor inheritance and name-swap fail-closed behavior, then run
exact-head CI, normal merge and read-back. No Runtime action, API route or
patch bytes are added. The [cwd proof](../WORKBENCH_A3_GIT_CWD.md) and
[A3 patch contract](../WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md) retain object
store and index provenance, sensitivity and encrypted content as future
gates. The Owner's broad shell/file/plugin/Hub choice remains unanswered.

## Historical 2026-09-29 S02 Project work tabs

PR #109 merged as `1e3f463c5aafcc9ffdd266a94cfe35bfdca46c0a`
with exact parent read-back and six successful post-main workflows. Continue
on `codex/workbench-project-tabs`: finish bounded Project/Changed Paths/
Workspace navigation tabs with actual desktop/mobile rendering, route and
session fencing, and no implicit Runtime lifecycle operation. Record fixed
upstream source and legal attribution in
[Project work tabs](../WORKBENCH_PROJECT_TABS.md). Then run local regression,
exact-head Linux CI, normal merge and read-back. WS02 multiple conversations
and split panes remain separate. A3 patch content still needs complete Git
object provenance and child-cwd proof before extraction; broad permissions
await the Owner's semantic choice.

## Historical 2026-09-29 S02/A3 descriptor-held Git foundation

PR #108 merged as `692f58a5823c4a8fbb438e61f6575fc88150753f`
with exact parent read-back and six successful post-main workflows. On
`codex/workbench-git-content-root`, finish the internal rc17 Project/Git
descriptor custody and negative tests, then exact-head Linux CI, normal
merge and read-back. This source increment must expose no file bytes, Git
patch action, API route, browser selector or general filesystem gateway.
Afterward, prove complete object-store and child-cwd provenance before the
staged-only patch reader. The [A3 patch contract](../WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md)
keeps encrypted delivery, unstaged content and real-host qualification as
separate steps. Broad shell/file/plugin/Hub authority still awaits the
Owner's semantic choice.

## Historical 2026-09-29 S02/A3 patch content boundary

PR #107 merged as `87c0913f86324588608b191a8318115b36a59fbc` with
exact parent read-back and all six post-main workflows successful. Continue
on `codex/workbench-patch-contract` from that merge. Freeze the bounded,
sensitivity-aware Runtime Git patch reader and separate encrypted content
admission in [A3 patch content contract](../WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md),
then establish descriptor-held Project/repository and Git store/index
provenance before the staged-only Runtime extraction slice. No browser
content route precedes those proofs. Require fixed Git argv, current
Project/snapshot validation, bounded bytes/lines, helper-execution negatives
and explicit unsupported states. Unstaged content additionally needs
descriptor-bound working-file acquisition.
Document-only changes keep rc16; source behavior changes receive the next
aligned release candidate. Ordinary shell, arbitrary file browsing and
plugin/Hub authority still await the Owner's semantic choice. R12 `_main`
and real host/Secret/production gates remain separate.

## Historical 2026-09-29 S02 Changed Paths page

PR #106 merged as `c285872546f81c173c3e40e1711e8506c164cebc` with
exact parent read-back and six successful post-main workflows. Continue on
`codex/workbench-changes-tree`: connect its authenticated rc15 Project API
to a read-only AgentBox Changed Paths page. The candidate uses the migrated
folder ordering without fabricated line stats, presents staged/unstaged
metadata, and clears stale observations on Project/session change or browser
hide. Local Node 22 Web 1149/1149, MV3 6/6 and desktop/mobile browser E2E
100 pass/28 prescribed skips. Run exact-head Linux CI, normally merge and
read back. Then scope the next A3 sensitivity-aware patch/content contract;
ordinary shell, arbitrary file browsing and plugin authority still depend
on the pending Owner choice. See [A3 Git Changes](../WORKBENCH_A3_GIT_CHANGES.md).

## Historical 2026-09-28 S02 A3 bounded Git Changes metadata

PR #105 merged as `7ffc1734b0ce5a4f6fdc5575eaeac6804f2aca5c`
with exact parent read-back and six successful post-main workflows. R12's
Runtime profile gate is now software-delivered but enabled-mode composition,
positive legacy conflict observation, fixed manifest/native inputs and real
host/client/CLI evidence remain separate unfinished work.

Continue on `codex/workbench-git-changes` under
[A3 Git Changes metadata](../WORKBENCH_A3_GIT_CHANGES.md): complete fixed
Runtime `git.changes.list`, strict RPC, READY Project API, pagination and
negative tests. Local Git/Project API/release matrix (164 pass), Web/MV3
version/build checks and browser E2E (98 pass, 28 prescribed skips) now
pass. Run exact-head Linux CI, normally merge and read back. Then
connect the authenticated page to this real list and the migrated tree/order
logic; patch bodies and Files access need their own bounded sensitivity
contract. The pending broad-permission decision does not block this read-only
Project metadata slice.

## Historical 2026-09-28 R12 Runtime fixed deployment profile

PR #104 merged as `e6a5bf36636c5baf1225368c0acea1d89a73762e`
with exact parent read-back and six successful post-main workflows. Continue
on `codex/r12-runtime-deployment-profile`: the installer creates only the
canonical `disabled` Runtime profile at the fixed private path; an exact
loader checks parent and leaf provenance, and `_main` may run legacy mode
only when the profile remains disabled at startup. Explicit
`filesystem-v2` fails until the full application graph is wired. Local
installer/profile and focused entrypoint tests pass; Linux exact-head CI
and merge are pending. See [Runtime profile](../WAW_R12_RUNTIME_PROFILE.md).

After this software guard, replace the deliberate enabled-mode rejection
with one production composition from activated sockets, Runtime-only key,
epoch, verified manifest, deferred provider, current Project bindings and
one bounded bidirectional conflict authority. Installer CAS transactions
must coordinate API and Runtime profiles; no real host mode switch, Secret
or credential operation follows from a software merge.

## Historical 2026-09-28 R12-C3-b dynamic Runtime conflict state

PR #103 merged as `72b87c8333896eb6403e3a7e02516e4dcdf910c3`
with exact parent read-back and six successful post-main workflows. Continue
on `codex/r12-runtime-conflict-probe` with an internal, read-only snapshot
that maps current formal Project IDs back to their unique Runtime relative
keys and reports WAW supervisor/inflight/quarantine state to the existing
legacy conflict coordinator. Missing binding, ambiguity, concurrent change
and unknown state must block, never imply absence. Local executor tests pass;
Linux exact-head CI and merge are pending. See
[C3-b composition closure](../WAW_R12_C3B_PRODUCTION_COMPOSITION.md).

After this snapshot, bind a single closed production conflict probe to the
same executor and legacy managers. The legacy Claude/Codex observations need
bounded, fresh, read-only source evidence within the R12 start envelope;
do not use an always-ABSENT callback or a stale manager status cache to make
the software path appear complete. The [official Codex CLI command reference](https://learn.chatgpt.com/docs/developer-commands)
does not document `remote-control status`; local `codex-cli 0.153.4` help
also lacks it. Confirm a positive target-specific daemon state source rather
than interpreting an absent process match as stopped. Then close `_main` and remaining installer
manifest/native inputs, keeping real host/key/client/CLI gates separate.

PR #104's Linux native job reported 106 passed and one `tmux wait-for`
timeout in a pane-death test. The follow-up polls the exact retained pane
state and exact exit code within the same five-second budget, eliminating a
one-shot hook/waiter ordering race without relaxing the behavior assertion.
Require a new exact-head native/Backend pass before merge.

## Historical 2026-09-28 R12-D API disabled profile and singleton lock

PR #102 merged as `f70a3fdfda2439ad91a58aa9c38deb0e9c0f7417`
with exact parent read-back and six successful post-main workflows. Continue
R12-D on `codex/r12-api-profile-provision`: install the exact disabled
`/etc/agentbox/waw-api-profile.v1.json` and fixed
`/run/agentbox-waw-api/waw-api.v1.lock` with their loader-required owners
and modes. Existing valid `filesystem-v2` profile bytes must be preserved;
unknown or unsafe existing objects fail closed. No activation or mode update
is authorized by this software batch. Local fixture tests pass; Linux
installer/Backend CI and merge remain pending. See
[R12-D API resources](../WAW_R12_D_API_RESOURCES.md).

After exact-head CI and merge, continue the fixed public anchor/manifest and
Runtime `_main` composition. The separate mode CAS updater, static key
creation, external vendor enrollment and real host/client/CLI gates remain
later work. Keep the original checkout's WIP intact.

## Historical 2026-09-28 R12-D dormant installer socket substrate

PR #101 merged as `3d0ba375b5a616f1432789eb430ef1a7de4f3347`
after 24 exact-head successes, two prescribed skips, and six successful
post-main workflows. Continue R12-D on `codex/r12-installer-waw-sockets`:
install two fixed named socket units without enabling them; provision only
fixed non-secret directory structure; keep PID1 G3/HG-04 `NOT RUN`.

The current software candidate checks new directory collisions instead of
adopting them, stops any installed exact package WAW units before Runtime,
and removes newly introduced units when rolling back to an older backed-up
release. Simulated x86_64 fixture tests pass locally, but Linux
`systemd-analyze`, native installer CI and real host evidence are pending.
Next, run exact-head CI and normal merge/read-back, then continue fixed
manifest/policy/key provisioning and `_main` composition under separate
software and host gates. [R12-D socket substrate](../WAW_R12_D_INSTALLER_SOCKETS.md)
records the exact paths and incomplete inputs.

## Historical 2026-09-28 R12-D named socket admission refinement

PR #100 delivered the C3-b authority-deferred resource foundation as merge
`e3eb23930f6a34720ccf3ef604619acbc2d6cf4c` after exact-head CI and
six successful post-main workflows. Continue the production `_main` and
installer/client software work; do not claim host qualification.

Before writing two systemd socket units, close the loader's old FD ordering
assumption. [systemd.socket](https://github.com/systemd/systemd/blob/main/man/systemd.socket.xml)
does not guarantee relative order across socket units targeting one service.
Current `codex/r12-waw-socket-names` software candidate requires exact-two
unique control/stream `LISTEN_FDNAMES`, validates each FD's fixed path and
provenance, then normalizes the result. Linux CI and later PID 1 host evidence
must separately prove delivery; G3/HG-04 remain `NOT RUN`.

## 2026-09-28 C3-b deferred resource foundation — software candidate

Owner-approved [full capability plan](FULL_CAPABILITY_DELIVERY_PLAN.md) keeps
R12 production Runtime integration first. The latest main is rc14 merge
`986e8fa87c6d14030677c026342813c6921cc6f9`. An isolated branch
`codex/r12-c3b-resource-factory` carries the authority-deferred provider,
fixed executable/descriptor resource builder, distinct application owner,
native auth-probe path and cleanup repairs. Local related tests and Linux-target
type checking pass; exact-head CI and merge are pending. This is no production
entrypoint or host qualification.

The next software action is `_main` composition using installed activated
sockets, Runtime-only static key, epoch store and external vendor enrollment
without introducing a second authority. Keep the original checkout's C3-b
provider/tests, `.reasonix/`, `build/` and planning WIP intact. The exact
remaining issues and acceptance tests are in
[C3-b composition closure](../WAW_R12_C3B_PRODUCTION_COMPOSITION.md).

## R12-C2 C3-a composition closure delivered for review; C3-b next — 2026-09-15

M4 executor integration is delivered by PR #95: final head
`dfcefe87a2d53bac6eff73c7a63ea42d9ef52caf` completed all 26 terminal checks
(24 success, two prescribed rc8 skips), merged normally as
`4f374aef102c820a001517e14c49803da3e0ff73` with exact parent read-back, and
all six post-main workflows succeeded. Preserve this result.

The current branch `codex/r12-runtime-main` carries C3-a: the one-shot
`bind_native_probe_path` closing the owner↔factory↔process-port construction
loop, vendor digest per-entry `max_bytes`, the fixed-composition pin moved to
`WAWProductionAuthOwner`, and the API client per-action envelope
(`workspace.workspace.start` at 9.0s), closing decision
`R12-AUTH-PROBE-BUDGET-V1`. Independent review PASS with no P0/P1. Owner
review is held before merge per the 2026-09-15 milestone-review instruction.

C3-b after review/merge: production executor provider and the `_main`
production branch (activated sockets, static key, epoch store, provider,
application builder). Production profiles additionally require external
enrollment inputs (`vendor_version`, `codex_unauthenticated_output_sha256`,
D/G/H) and fail closed without them. No actual host/client/key/CLI activation
follows from the software merge.

## R12-B delivered; C1 candidate and C2 native work

R12-B/rc11 is delivered by PR #90: final head `64d45e7...` completed the exact
26-check contract, normal merge `e126e47172491f382efb2f5daaeac1e22a550ad6`
has verified parents and six successful post-main workflows. Preserve this result.
Continue the independently reviewed C1 static-key candidate on
`codex/r12-runtime-key`, followed by C2 fixed auth-isolation/executor and C3 main.
Native C2 work has separate file ownership; Python shared-file writes wait for C1
delivery. No actual host/client/key/CLI activation follows from the software merge.

## 2026-09-08 approved R12 execution

The Owner explicitly approved [PRP-2026-09-08-v1](PRODUCTION_READINESS_PLAN.md)
and instructed execution. Begin R12-A contract/input closure, then continue
dependency-ready R12-B/C/D/E/F software work on feature branches with CI,
normal merge and exact read-back. One persistent Goal is active; the main agent
owns the checklist and shared files. Mac Chrome/Edge terminal and mobile
management/exact Stop follow the plan's suggested scope, without claiming new
platform qualification.

Concrete host, Origin, client distribution and real key/login/paid-call/reboot
scope remain external inputs. Missing host evidence does not block independent
software work. Host/client activation and production/publication retain the
separate boundaries in the approved plan. The WEV-1 section below is historical
delivery context, not the current execution instruction.

## 2026-09-08 workstation evolution

The Owner requested a bounded incremental audit/research/implementation task.
Use [WORKSTATION_EVOLUTION](../WORKSTATION_EVOLUTION.md) as its task record and
[CAPABILITY_MATRIX](../CAPABILITY_MATRIX.md) as the evidence index. The current
software increment is WEV-1: invalidate browser Runtime observations after
interruption and re-read them on return before exposing lifecycle controls.
No automatic Start/Resume/Connect, new API/DB domain or production activation is
authorized by this increment. Branch: `codex/workstation-evolution`.

The seven-project research and WEV-1 implementation are merged through PR #87.
Head `80a6972466a514aa67577bb7812cf4c649a5983c` passed the complete 26-check
contract (24 success, two prescribed skips); merge
`b3e9cd5dbfbdca0c5e0cd652dc0cce7e1e53214e` has verified parents and six successful
post-main workflows. Preserve the completed tests, reviews and delivery record.

The next product-flow action is to establish the concrete R12 target and
authorized Runtime/Project/trust/key handling, then implement and verify the
five gates below. No other proposed feature is implicitly activated by WEV-1.
Later Files/Diff, Attention/Approval, Discovery/Resume and Task/Worktree proposals
need their own bounded contracts. R12 is still blocked on concrete target,
Runtime/trust/Secret scope and real-host evidence. The completed R11 record
below is historical context, not a command to repeat its work.

R12 must close all five [production bootstrap and host gates](../WORKSTATION_EVOLUTION.md#r12-production-bootstrap-and-host-gates):
production API mode/composition; Runtime filesystem-v2 builder and concrete
executor/key provider; activated sockets and peer/cgroup/isolation; managed CRX,
Native Messaging and trustd enrollment; real CLI login, input, return/reconnect,
exact Stop and reboot recovery. This is implementation plus host acceptance,
not a feature-flag change or a request to rerun synthetic tests.

Action ID: `DELEGATED-RUNTIME-RELAY-2026-09-03`

The Owner explicitly delegated software goal, plan and architecture decisions to
the Coding Agent and instructed continued development. The complete reviewed
[WAW stream supplement](WAW_ENCRYPTED_STREAM_DECISION.md) is accepted for software
implementation under [GOVERNANCE](GOVERNANCE.md). The previous R3 confirmation
blocker is resolved. Do not request the same software approval again.

## Active implementation

- rc8 is delivered by PR #83: documentation head
  710ceef696757a8a1f2a9165f2312672db57bb1e completed 26 exact-head checks,
  merged normally as 95bf65d6114008b962985f7311941499c961a7b8 with exact
  parents 87f5bce and 710ceef, and all six post-main workflows succeeded. This
  remains software-only evidence; no tag, release, host activation or R12
  qualification occurred.
- RC9 is delivered through PR #85: exact-head CI, normal merge, merge read-back
  and all post-main workflows succeeded. Preserve the immutable locale rule (only
  `navigator.languages[0]`, `zh` primary → `zh-CN`, otherwise English) and
  preserve technical values without translating or humanizing external protocol
  strings. R11 software rc6–rc9 is complete as software evidence; do not extend
  that result to R12.
- The fixed rc8 predecessor/artifact operations jobs are now version-aware and
  fail-closed: rc8 executes them successfully, while rc9 skips exactly those
  historical jobs and still requires current-candidate artifact checks and
  `release-gate` success. Preserve the fixed rc8 contract; skipped, failing or
  unknown results must never count as pass.

- rc9 version text is Python `0.3.0rc9`, npm `0.3.0-rc.9`, MV3 `0.3.0.9`.
  Production output must retain no test bypass; the distinct-origin Workspace
  harness is E2E-only and sensitive artifacts remain disabled. R12 stays
  independent, unstarted and host-gated. No tag, GitHub Release, production
  deployment, Provider credential operation or real host activation occurred.

- Historical rc6 work-unit and checkpoint evidence remains in the execution
  plan and current-state record. The rc8 and rc9 actions above are the current
  authoritative sequence.

- Historical rc9 foundation commit `184781c...` completed 20/20 exact-head
  checks. Its shared catalog, error-code mapper and route-state manifest are
  now incorporated in the delivered rc9 implementation; the page migration and
  bilingual visual matrix are no longer a pending implementation item. Current
  evidence is recorded in `CURRENT_STATE.md`; its CI/merge record is delivered.

- Preserve merged R0/R1/R2/R9.1/R10.1 and the verified delivery record, PRs #67–#72.
- R3/R4 are merged as PR #73 after 19/19 checks and exact read-back.
- R5 is merged as PR #74 after 19/19 checks and exact read-back. Cold-start/GC
  parser failures are fixed without relaxing the 5 ms budget.
- R6 is merged as PR #75 after 19/19 checks and exact read-back; staged ticket
  authority, atomic publication, reader handoff and cleanup/Audit fences delivered.
- R7 is merged as PR #76 after final independent PASS, 19/19 exact-head checks
  and exact read-back; Runtime encrypted stream/server and publication fences delivered.
- R8 is merged as PR #77 after independent PASS, 19/19 exact-head checks,
  normal merge, exact read-back and six successful post-main workflows.
- R9 is merged as PR #78 after independent PASS, 19/19 exact-head checks,
  normal merge `15a4632f915dd1e1bde19425e313b52ada27166f`, exact read-back and
  six successful standard post-main workflows.
- R10/rc5 is delivered by PR #79: final head `0d9e7c7...` completed 20/20
  exact-head checks and merged as `341a69bf...`; exact parent read-back, all six
  post-main workflows and dynamic Dependency Graph completed SUCCESS.
- PR #80 repair head `bbdd67c...` has terminal 20/20 CI after fixing the shared
  descriptor-release/inode-reuse issue. It verifies the current first-use/
  evidence checkpoint. Native/format follow-ups completed in `4222242...` 20/20
  CI. Do not merge before replay, controller composition and the remaining rc6
  acceptance set.
- Current evidence: the final local core matrix completed 216 plus 5 focused
  cases; independent Sol/xhigh review completed 244 cases with 1 Linux-only skip
  and 9 deselected, plus 8 encrypted-server non-UDS cases. Review is PASS with no
  remaining P0/P1/P2. Twenty-eight real-UDS cases are locally unverified because
  this environment returned `PermissionError` during socket setup. Ruff, Black,
  Linux-target mypy (256 sources), doc links (240) and `git diff --check` pass.
- The current uncommitted bounded-redraw slice has a neutral 24-row/60 KiB
  contract with row 25 and byte 61,441 as discarded sentinels. Held-FD tmux
  capture proves socket/pane/retained-pidfd identity before and after one shared
  one-second deadline; supervisor capture/cursor/baseline publication is atomic,
  and production capture callbacks are removed from registry/service/bootstrap.
  The unified focused matrix completed 341 tests with 9 Linux-only skips and 2
  local UDS cases deselected; independent Sol/xhigh review reports PASS with no
  P0/P1/P2. The new Linux native case requires exact-head CI; local UDS setup
  remains unverified after `PermissionError`.
- Head `adf44fc0...` ran the new real Linux capture successfully, then failed the
  native job at teardown because the test killed tmux before calling a helper
  that expects the tmux socket. The test-only follow-up removes that invalid
  cleanup assertion. Commit/push it and require a fresh exact-head native/full
  Backend pass before recording bounded redraw complete.
- Follow-up `f37f92d9...` completed the required 20/20 exact-head matrix. Linux
  native completed 73 cases; Backend Python 3.11 completed 3629 passed/44 skipped,
  with 3.12/3.13 also successful. Treat bounded redraw as verified and continue
  with `WAWRuntimeApplication` production composition and singleton ownership.
- The current `WAWRuntimeApplication` composition is uncommitted: typed Runtime
  key/executor providers and activated sockets have distinct one-shot ownership;
  stream, control and legacy share application start/close tasks and one dispatch
  gate. Partial production builders are private and weak-map provenance is gone.
  Incomplete construction retains a typed retryable owner. Provider closure waits
  for stream/control/lifecycle/legacy clean evidence. Independent Sol/xhigh review
  reports PASS with no P0/P1/P2; Linux-target mypy covers 260 sources. Production
  main, real key/provider and host activation remain disabled.
- `WAWRuntimeApplication` head `628e9c00...` completed 20/20 exact-head checks.
  Continue rc6 with the API singleton, one attachment/bind/control/relay owner and
  lifespan shutdown ordering; keep real key/provider and production activation in
  their existing host-gated scope.
- `AttachmentAuthority` shutdown fencing is implemented and independently reviewed:
  pending tickets burn, cleanup obligations survive invalidation, and only exact
  cleanup/Audit ACK reaches clean. Commit and exact-head verify this foundation,
  then implement the process lock and single bind/control/relay lifespan owner.
- Bind/control shutdown evidence is also complete locally: pending exchange,
  detached task, retained peer or uncertain FD close prevents clean. Commit and
  exact-head verify it, then continue process lock and stream-owner composition.
- Begin rc7 with named test-only checkpoints, manual promises, fake monotonic clocks
  and controlled partial-write sockets. Prove admission/stream/restart/shutdown/Stop/
  browser-lifecycle failure invariants before advancing to rc8 artifact rehearsal
  and rc9 full browser-selected bilingual UI.
- First integration head `e210d749...` completed 17/20 checks. Three Backend
  matrix jobs exposed one shared legacy regression: a clean non-fixed server could
  no longer restart without consuming a second epoch. The local reviewed fix
  restores only that compatible restart; fixed/control/poisoned/incomplete shutdown
  stays terminal. Follow-up `c534fe437...` completed the fresh exact-head 20/20
  matrix. Continue the remaining rc6 controller composition; do not merge rc6 until the full
  controller composition and rc6 acceptance set are complete.
- Locale remains fixed per document from only `navigator.languages[0]`: primary
  `zh` → `zh-CN`; all other, missing or malformed values → English. Technical
  identifiers remain English.
- Keep R7/R8 active lifecycle obligations explicit: 30s stale/60s grace,
  15min idle/8h absolute, Runtime health, current auth and positive cleanup.
- Resolve remaining software contracts with documented rationale and independent
  review under the delegated authority, rather than another mechanical Owner gate.

Each stage follows feature branch → exact-head terminal CI → normal merge →
exact read-back, updating CURRENT_STATE, the remaining plan and relevant scope
documents. Complex work uses sol; routine implementation/verification uses terra.

## Remaining evidence boundaries

Mac remains the development platform. Real host activation, production keys or
Provider Secret operations, publication and support promises require a concrete
scope/target and real evidence. Software decisions do not certify those gates.
The independent trust-provider deployment and actual CLI/PTY/isolation/restart
qualification remain required before full product completion. No synthetic
handler or passing codec test may be presented as a working terminal.
