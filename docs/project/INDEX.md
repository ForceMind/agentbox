# AgentBox Project Context Index

## 2026-10-05 PR #143 已闭环；native A3 六套 CI 全绿、像素收尾

PR [#143](https://github.com/ForceMind/agentbox/pull/143) 已正常合并。
最终 head `ad9d199c3ca08661cfb8171e1a782060cc694534` 的六套 workflow
均 SUCCESS（24 jobs SUCCESS、2 项历史 rc8 SKIPPED）；main 显式 fetch/read-back
为 `61a5efce6ab43754a2acdb313d5e21ee83f64c52`，tree
`ec1ca86988ea4e84e7aa1d818e5d85a4b967cf08` 与 head 完全一致。
parents 为 `b7dd51d3288022f12604656515aafe7e11a00d3e` 和上述 head。

exact-main 六套首次 workflow 均 terminal SUCCESS（23 jobs SUCCESS、3 SKIPPED：
push 的 dependency-review 与两项历史 rc8）。[Backend](https://github.com/ForceMind/agentbox/actions/runs/37267834425)
三个 Python 版本各 5119 passed/88 skipped；[E2E](https://github.com/ForceMind/agentbox/actions/runs/37267834421)
144 passed/30 prescribed skipped，包括新增28个desktop/phone场景。
最终 head 已补齐 CJK 字体并完成实际截图复核；同 tree 的 main 截图 artifact 已核验
摘要，但没有重复进行像素复核。下方旧 CI 失败、teardown race 与缺字事实作为历史
保留，不能再将旧 head 的待补状态当作当前未完成门槛。

当前独立 branch `codex/a3-native-changes` 从该 main 接续
[A3 native transport 合同](../WORKBENCH_A3_NATIVE_TRANSPORT.md)：正式 App factory、
独立 A3 HTTPS bootstrap consumer、分离 API/Runtime 的 bounded metadata/opaque UDS。
合同已独立审查冻结，源代码已实现并完成独立 source review；跨进程 currentness、
最终 publication/END 与显示生命周期保持分层。第七轮 head
`f67b93dfa0678ee0f04ea187a91d9a8cddb35c07` 六套 CI 首次全绿；Backend 三版本各
5276 passed/88 skipped，14项真实 native 全通过；E2E212 passed/30 prescribed
skipped/0 failed/0 flaky，新增52项正式 App desktop/phone 全通过（212还包括
16项纯 Node checks）。[Current state](CURRENT_STATE.md) 保留六轮失败、真实
原因与双 loop 同条件 red/green，不用已排除的裸 adapter 竞态假设解释 CI。

原始 artifact 摘要已核验并打开四张 PNG，发现 full-page 截图滚动位置及 phone
刷新按钮换行问题；仅进行小幅视觉/截图收尾，最终候选的 exact-head CI 与像素
复核尚待完成。PR #144 仍 Draft，main 仍为上述 #143 merge。通过后按正常
Ready/merge、parents/tree read-back 与 exact-main 六套 CI 闭环。
无生产 key loader/pin enrollment、installer 开关、真实 host listener/账号或发布。
未配置安装仍 unavailable；真实 host/physical client/CLI 验收仍 NOT RUN。

本地最终 A3 matrix428 passed，Web1480 tests 与 extension6 tests、正常质量门禁、
独立 crypto/interop 与 source review PASS。此 executor 的 AF_UNIX 创建限制与
旧全量 pytest 因共享 /tmp ENOSPC 终止仍是失败历史，不能改记本地全量 PASS；
真实 numeric-UID、UDS、HTTPS 与浏览器资格来自上述 CI，不来自本地跳过项。



## 2026-10-04 A3 Changes-page staged reader 软件候选

已显式 fetch/read-back 核对 #142 merge `b7dd51d3288022f12604656515aafe7e11a00d3e`，
tree `2cdfa72e7ca99b57312dadf156af1b74d82db15e`；#142 exact-head 六套
workflow 均 SUCCESS。旧 staged/readback worktrees 全保留，新独立
`feature/s02-changes-a3-reader` 接续 [Changes-page 软件合同](../WORKBENCH_A3_CHANGES_READER.md)。

本批加入独立 staged-observation metadata route、purpose-specific A3 trust port、
显式点击/完整 END 后 inert text 展示和 page-owned lifecycle。API 新边界仅用 typed
metadata port，不导入/执行 Runtime；生产 source 默认缺失且拒绝注入，正式页面无
A3 adapter/pin 时明确不可用。实际 Git→API route→existing admission→opaque relay→
Web DOM 将由 isolated fixture 与新 exact-head CI Chromium 验证；此刻浏览器尚未运行，
不称生产可用或真实 host PASS。
无新 listener、WAW trust fallback、真实 key/pin enrollment、安装激活或发布。

本地检查与独立 source review 已完成；新 exact-head CI、merge/read-back 尚未运行，
不能使用 #142 的 CI 替代本候选证据。后续为候选审阅、Draft PR 与新 CI。
下方旧批次边界保留为历史，不覆盖本合同已批准的 source-only 页面接线。


## 2026-10-04 A3 admission/lifetime software continuation

#141 已正常合并为 `1c2befb9be47c8f7181accd67965e4187fcf06cf`，tree
`9c79cb24a121ff7641e191547a10823df3e1caef`；exact-head/post-main 六套首次
CI 全 SUCCESS。当前独立批次为 [default-off admission 与 crypto v2 lifetime](../WORKBENCH_A3_ADMISSION_LIFETIME.md)：
复用现有 API session/READY 与 Runtime binding/lifecycle owner，专用 synthetic
key/opaque TEST wiring，以及原始 selector lifetime 的 authenticated remaining-ms
桥接。plaintext/context/AAD v1 不变，无生产 route/key/pin/host/UI 激活。
候选需完成源代码独立审查、全量适用检查和新 exact-head CI；下方为历史批次。


- **当前优先级（2026-10-04）**：#140 已正常合并，exact-head/post-main 六套
  CI 全终态 SUCCESS。当前推进 [独立 encrypted single-read](../WORKBENCH_A3_ENCRYPTED_SINGLE_READ.md)
  的 synthetic Git→fresh A3 Noise→opaque relay→Web 软件链；真实 host/device
  验收继续 NOT RUN，生产 resolver/key/relay/UI 与 release 仍分开。

- [Development handoff](DEVELOPMENT_HANDOFF.md)：2026-10-04 接续入口；
  PR #136 完整 fresh-install 已实现，documentation-inclusive CI 全绿；
  已正常合并为 7d052155；当前进入真实首装资格化准备。
- [Deployable release plan](DEPLOYABLE_RELEASE_PLAN.md)：Owner 自行运行一键安装的
  首版目标、实际命令入口、PC/手机范围及部署链剩余依赖。
- [Cross-platform Web bootstrap proposal](../adr/0010-cross-platform-web-bootstrap.md)：
  已批准 PC/手机浏览器的 HTTPS 信任前提、与原生保护的差别及实际验收条件。
- [Deployable cgroup compatibility proposal](../adr/0011-deployable-cgroup-compatibility.md)：
  已批准 systemd 255 受限子树方案；不等同旧 private 合同，激活仍须真实证据。

- [Release iteration plan](RELEASE_ITERATION_PLAN.md)：当前唯一目标是首个可用单机 RC；
  明确软件候选、真实目标验收和后续逐版本吸收的退出条件与范围冻结。
- [Full capability delivery plan](FULL_CAPABILITY_DELIVERY_PLAN.md)：Owner 将范围扩展为
  吸收全部现有上游功能；按三仓固定提交与 70 项 ID 组织一条分阶段实施路线。
- [Full capability inventory](FULL_CAPABILITY_INVENTORY.md)：主仓、生产 relay、Hub
  的功能、现有 AgentBox 状态与逐项验收目标；权限冲突另有待确认选择。
- [Workbench integration plan](WORKBENCH_INTEGRATION_PLAN.md)：Owner 已批准软件实施；
  v1 保留 A0/A1 技术基线与来源规则；全量范围以 v2 为准。
- [Workbench identity and content ADR](../adr/0009-workbench-identity-and-content-boundary.md)：
  Project、WAW、会话与 UI tab 分域，内容仍须 A3 专项协议和审查。
- [A3 Git Changes metadata](../WORKBENCH_A3_GIT_CHANGES.md)：
  READY Project 范围内的只读路径/状态分页合同，不授予正文或 patch 读取。
- [A3 Git patch content contract](../WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md)：
  reader/selector 已随 #138/#139 合并；纯 content codec 候选不开放加密通道。
- [A3 Git child cwd](../WORKBENCH_A3_GIT_CWD.md)：
  Linux-only 子进程目录 descriptor 前后身份验证基础；尚无内容读取动作。
- [A3 staged reader candidate](../WORKBENCH_A3_STAGED_READER.md)：
  Runtime 内部有界暂存 patch 观察、对象库快照与仍未开放的内容门禁。
- [Project work tabs](../WORKBENCH_PROJECT_TABS.md)：
  固定上游来源、AgentBox 路由身份和纯导航生命周期；多会话仍待后续阶段。
- [Project search](../WORKBENCH_PROJECT_SEARCH.md)：
  固定上游匹配算法来源、只读 Project 列表搜索和未完成的 WS14 同步能力。
- [Project favorites](../WORKBENCH_PROJECT_FAVORITES.md)：
  WS14 每位管理员的收藏状态、CAS 并发与 Control Plane 元数据候选合同。
- [Project and Workspace labels](../WORKBENCH_PROJECT_LABELS.md)：
  WS14 共享标签目录、正式 Project/Workspace 分配及可见客户端刷新边界。
- [Command center](../WORKBENCH_COMMAND_CENTER.md)：
  WS14 固定页面/正式 Project 导航及精确 Workspace 标签选择，当前 Session 隔离。
- [Production readiness plan](PRODUCTION_READINESS_PLAN.md)：2026-09-08 已批准执行计划；
  R12 软件接线、客户端、真实主机/CLI、恢复与有限生产的依赖、验收和授权范围。
  R12-A已开始；软件执行、host资格化与生产准入分开记录。
- [R12 target record](R12_TARGET_RECORD.md)：目标输入、已确认软件边界、外部阻断与当前派工。
- [R12 API bootstrap](../WAW_R12_API_BOOTSTRAP.md)：固定installer-owned mode、默认兼容、
  root-owned读取、启动currentness与API生产入口契约。
- [R12 Runtime key port](../WAW_R12_RUNTIME_KEY_PORT.md)：C1固定Runtime-only key custody、
  同一manifest authority绑定、epoch时点与关闭契约；C2/C3尚未完成。
- [R12 fixed vendor enrollment](../WAW_R12_VENDOR_ENROLLMENT.md)：
  非Secret CLI版本/输出摘要的固定来源、文件身份及同一Runtime authority配对候选；
  不含真实目标采集或主机激活。
- [R12 fixed auth probe](../WAW_R12_RUNTIME_AUTH_PROBE.md)：C2的closed native ABI、
  同generation借用、offline status、shared cache与cleanup契约；实现与host资格分开。
- [R12-C3-b production composition](../WAW_R12_C3B_PRODUCTION_COMPOSITION.md)：
  唯一authority的资源签发、native owner、Project绑定与后续 `_main` 接线缺口。
- [R12-D installer socket substrate](../WAW_R12_D_INSTALLER_SOCKETS.md)：
  固定具名 socket unit、Runtime 资源目录、安装/回滚与尚未激活的现场边界。
- [R12-D API disabled resources](../WAW_R12_D_API_RESOURCES.md)：
  固定关闭态 API profile、单例锁目录与文件，及后继 CAS 更新门禁。
- [R12 Runtime fixed profile](../WAW_R12_RUNTIME_PROFILE.md)：
  Runtime私有关闭态profile、固定加载及 `_main` 拒绝静默回退的入口边界。

本目录是治理执行入口。每个任务执行前按顺序读取：

1. `CHARTER.md`
2. `CURRENT_STATE.md`
3. `NEXT_ACTION.md`
4. `ROADMAP.md`
5. `DECISION_INDEX.md`
6. `GOVERNANCE.md`
7. `GOVERNANCE_AUTOMATION.md`
8. `EXECUTION_PLAN.md` — 当前目标、阶段状态、职责、验收与交付流程。

- [Workstation evolution](../WORKSTATION_EVOLUTION.md)：2026-09-08 增量任务的
  事实基线、七仓研究、取舍、WEV-1 契约与阶段验收记录。
- [Capability matrix](../CAPABILITY_MATRIX.md)：设计、实现、验证、产品状态分别记录；
  R12 不因新增产品研究而开放。

- [WAW encrypted stream supplemental decision](WAW_ENCRYPTED_STREAM_DECISION.md): accepted full wire/admission/trust contract under explicit Owner-delegated software decision authority; R4/R5 are merged and Runtime/API integration is in progress.

- [Fixed Noise NX core](../WAW_NOISE_CORE.md): implementation limits, independent vector provenance and Python/WebCrypto interoperability.

- [Remaining development plan](REMAINING_PLAN.md): latest assessed goals, finite slices, model routing, confirmed defects and contract decisions.

- [Opaque AWCE framing](../WAW_AWCE_FRAMING.md): exact envelope layout, bounded Python/Web codecs, header builders, cross-language checks and unimplemented crypto/session boundaries.

- [Executable provenance](../WAW_EXECUTABLE_PROVENANCE.md): descriptor-held Runtime inventory verification and its launch/host limits.
- [Interactive CLI assessment](../WAW_INTERACTIVE_PROFILE_ASSESSMENT.md): current code/vendor documentation gaps requiring a complete execution-profile contract.
- [Fixed interactive process](../WAW_FIXED_INTERACTIVE_PROCESS.md): R10 inert
  packaging inputs, digest-pinned policy boundary, and R11/R12 separation.
- [R11 production integration](../WAW_R11_CONTROLLER_COMPOSITION.md): accepted
  rc6–rc9 composition, failure, artifact/operations and bilingual UI contract.
- [R11 execution plan](../WAW_R11_EXECUTION_PLAN.md): delivered rc6–rc9 work-unit
  ownership, state-machine, Project binding, controller and acceptance plan.
- [R11 rc8 artifact and operations rehearsal](../WAW_R11_RC8_ARTIFACT_OPERATIONS.md):
  frozen provenance, artifact-only synthetic and dual-artifact operations
  evidence, current candidate status, and the R12 boundary.

- [R11 rc6 first use](../WAW_R11_RC6_FIRST_USE.md): typed Project binding,
  generation-one creation and Runtime executable-evidence checkpoint, with its
  verification and remaining boundaries.
- [R11 rc6 binding replay](../WAW_R11_RC6_BINDING_REPLAY.md): exact API/Runtime
  replay, inventory-finalization gate, drift fences, installer boundary and
  explicit Linux/host evidence limits.
- [R11 rc6 browser controller](../WAW_R11_RC6_BROWSER_CONTROLLER.md): controller
  cursor/input/control fences, fresh-redraw contract and page-composition limits.

- [Authentication timing diagnostic](../AUTH_TIMING_DIAGNOSTIC.md): isolated numeric observations, failure/privacy rules, regression evidence and unknown historical latency cause.

- [Browser tokenizer foundation](../WAW_BROWSER_TOKENIZER.md): incremental UTF-8/VT typed tokens, independent limits, explicit failure boundary and remaining controller/renderer contracts.

- [WAW application cryptography](../WAW_APPLICATION_CRYPTO.md): exact implemented handshake/channel, deadline/publication rules, independent vectors/interop and native-browser evidence.

- [Full WAW wire profiles](../WAW_WIRE_CONTRACT.md): complete direction schemas, exact-byte relay/trace, failure/retry decisions, parser budgets and measured verification.

- [Staged admission](../WAW_STAGED_ADMISSION.md): ticket burn/reservation, required Audit, atomic publication, reader handoff, cleanup and the distinct active-lifecycle obligations.

- [Runtime encrypted stream](../WAW_RUNTIME_ENCRYPTED_STREAM.md): actual Runtime crypto/session/server, exact cleanup and trusted deployment-port boundaries; current review status is explicit.

- [API ciphertext relay](../WAW_API_CIPHERTEXT_RELAY.md): native WebSocket, Runtime ciphertext relay, active permission/publication fences and current shared-budget status.
- [Browser trust records](../WAW_BROWSER_TRUST_RECORDS.md): canonical public record/signature foundation and the remaining provider/lifecycle boundary.
- [Managed browser trust provider](../WAW_BROWSER_TRUST_PROVIDER.md): inert MV3 source build, deployment cross-pins, Native Messaging/trustd authority and qualification boundary.
- [Browser implementation decision](WAW_BROWSER_IMPLEMENTATION_DECISION.md): accepted R9 trust/controller/bounded-renderer contract and qualification split.
