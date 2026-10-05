# AgentBox Roadmap


## 2026-10-05 A2 / WEV-2 工作概览候选

当前独立 branch `codex/a2-work-overview-20261005` 从已闭环 main
`a1cab129f18ede5b982b6ab53d037c51771b4dea` / tree
`26f245acde25737aa9c8ef47e408ad9c56a8006a` 接续原计划。
[有界工作概览合同](../WORKBENCH_WORK_OVERVIEW.md) 已冻结：Dashboard
优先显示当前 user 最近100条 Job 的待处理/排队/运行中窗口与最近6个 Project
元数据；计数明确有界，项目时间仅表示真实 updated_at。复用已有认证与目录
权限，不调用 Runtime/reconcile、Git status 或文件正文。失效快照清除，
loading/empty/error/permission/stale 分开；原健康与就绪入口保留。

七文件 #145/#146 闭环快照修正在 exact base 校验后随本批应用，原失败保留。
本候选 source/tests/translations/docs 同批；版本同步 rc31，不发布 tag/Release。
完整新 head 六套 CI、正式 App 桌面手机截图与独立像素、正常 merge 和 main
六套仍待完成，不借旧 CI 宣称本卡通过。完成此卡后停止，只给 Files 下一卡；
WS08 split 属最终范围但不是本卡，不称 A2/S02 整体完成。
无生产 key/pin、真实 host/账号、安装激活、release/deploy。


## 2026-10-05 #145 / #146 已闭环：统一视图与主干质量复核通过

#145 已交付正式 Changes 页有界统一diff（hunk、旧/新补丁坐标、增删文本、
完整原文fallback、键盘与手机wrap）。最终feature head
`63da1b1539ed68186b249e905e8b14c568ce1673` 六套首次CI与独立六图pixel
PASS；首轮巨大留白的失败证据保留，最终滚动区域定位修正已验。

#145 merge `c93ed22a57b2667d8f6b13fdb3fd3720001e72f2` 的旧rc7 lifecycle
单测导致Frontend失败，其余五套通过。后继test-only #146 不改产品5ms预算、
测试timeout、断言或UI；历史成因仍为强支持推断，原失败未抹除。最终head
`1c4d5c30d62531eebb219e1afea82a11059175bb` 六套首次workflow全SUCCESS。

#146 于2026-10-05T16:21:56Z正常合并。最新main
`a1cab129f18ede5b982b6ab53d037c51771b4dea`，parents为上述c93ed22与
1c4d5c3；tree `26f245acde25737aa9c8ef47e408ad9c56a8006a` 与head完全一致。
新exact-main六套首次workflow均SUCCESS（23成功/3预期skip）：
[Frontend](https://github.com/ForceMind/agentbox/actions/runs/37340266309)
1554 Web+6 extension、原rc7三项110ms通过；
[Backend](https://github.com/ForceMind/agentbox/actions/runs/37340266512)
三版本各5284 passed/88 skipped与14项native process；
[E2E](https://github.com/ForceMind/agentbox/actions/runs/37340266503)
224 passed/30 prescribed skipped/0failed/0flaky，包括64项formal native
桌面/手机，224还含16项pureNode检查。

main artifact11359310257 ZIP摘要已实际校验为
`818a8d6b7441f77a8aa6580f2dd65658975b411c28a29a3c56b93733ba746ba4`。
未声称重复main图像素审查：production UI/native fixture/E2E与已独立pixel-PASS
的63da1b1未改。最终feature图artifact11355935840摘要为
`73d1faf08c60a7b1e973a32c562801eab98b16e2a64d2fe888aa62f029347186`。

本有界卡到此停止，下一功能仅建议、未启动；不称整个S02/WS08完成。
默认未配置仍unavailable；无生产key/pin、host/installer激活、真实账号或发布。
下方所有pending与失败描述是当时快照，不覆盖本节最新闭环事实。


## 2026-10-05 #145 已合并；main Frontend 单测时钟修正候选

#145 最终 head `63da1b1539ed68186b249e905e8b14c568ce1673` 六套首次CI
和独立六图像素均PASS。main `c93ed22a57b2667d8f6b13fdb3fd3720001e72f2`
于15:40:24Z正常合并，parents/tree已显式核对，tree仍为
`44630157273d4eea963d5738ed930eb257b7847e`。长补丁巨大留白已修正。

exact-main五套workflow SUCCESS，但[Frontend](https://github.com/ForceMind/agentbox/actions/runs/37334720162)
失败：既有 rc7 lifecycle socket/backpressure 用例 timeout5000ms，加一个
PROTOCOL_INVALID unhandled rejection；1553 passed/1 failed。不能称main全绿。
当前独立 `codex/rc7-lifecycle-test-clock` 只固定该测试的performance elapsed clock，
沿用相邻协议单测的既定方式；产品5ms预算、测试timeout和全部断言不变。
[诊断与限定修正](../WORKBENCH_RC7_TEST_CLOCK.md) 保留同条件8ms暂停红绿；
真实CI无内部时钟数据，历史成因仍为有强支持的推断。待独立review、新head与
新main六套终态，禁止重跑旧失败取绿或借旧head过关。未新增功能/部署权限。


## 2026-10-05 PR #145 首轮 CI 全绿，长补丁纵向布局收尾

head `a49230f574c8b71394b20c1a102015ad3b61b9ec`、tree
`64ede3e2adae935fc5b6e7305e6f054c100b6125` 的六套首次 workflow 均
SUCCESS；[Backend](https://github.com/ForceMind/agentbox/actions/runs/37328655732)
三版本各5284 passed/88 skipped，14项真实 native process 通过；
[E2E](https://github.com/ForceMind/agentbox/actions/runs/37328655879) 为
224 passed/30 prescribed skipped/0 failed/0 flaky，包含64项正式 native
桌面/手机场景。224中16项仍是纯Node checks，不全称浏览器用例。

实际打开并独立复核全部6张 PNG 后，长内容主截图出现巨大页尾留白：desktop
1280×7427，phone1073×65772；两张 multiple-hunks 图正常。首轮 pixel verdict
为 FAIL，PR仍Draft且未合并。CSS 的 absolute 辅助标签缺少定位祖先与现象
一致；本候选仅为滚动区域添加 position:relative、给说明文字增加焦点框间距，
并补页面 scrollHeight 相对 reader 卡片底部的有界断言。现有横滚/键盘/生命周期
断言不放宽。原因推断与新图通过仍须由新 exact-head CI/像素结果验证。

首轮 artifact11353574147 ZIP SHA256 为
`b8b7523f33d6d49933f571ae7c5d399f9f65cc100470117932416da0a4a18980`；
旧图与失败事实保留。不得用首轮全绿替代修正候选、新图或 exact-main 资格。
下节初始候选的 pending 描述是当时快照；本批权限/生产/host/发布边界不变。


## 2026-10-05 S02 / WS08 统一 diff 视图软件候选

从已闭环 #144 的 main `3e313b36b7cfc7c1de1c54cc20164ae223fcd122`
（tree `d2fa9213b40db3a5f2b9236646da7fdc50c39645`）新建
`codex/s02-changes-unified-diff`。实际 fetch、open PR 与 exact-main 六套
SUCCESS 已复核；旧 worktree/历史不改写。本批先冻结
[有界统一 diff 合同](../WORKBENCH_CHANGES_UNIFIED_DIFF.md)，再实现正式
Changes 页的 hunk、旧/新行号、增删文本、统一/完整原文切换及默认换行。

只消费既有 completed owner 的完整 END 已验证文本；不新增 reader、网络、
预取、缓存、存储、复制/导出或权限。取消、刷新、route/hide/auth/trust/offline、
原始 expiry 等旧 fence 一并卸载模型。头部和坐标只是补丁声明，不生成源身份。
256 KiB / 4,000行 / 64 hunks / 单行8,192 UTF-16 units 是独立显示上限，
越界或未知/畸形/binary/metadata-only 输入整体显示完整原文，不截断；CRLF、
Unicode、EOF marker 均保留。原文不由 parsed model 重建。

独立 source review 发现的 `/dev/null` 一侧虚构 unchanged gap 已修正并加
真实 Git mutation 回归。focused Web 88项与 Git fixture 8项复核 PASS；
新增 native fixture 与原 fixture unit 合计33 passed。旧52项 native browser
保留，新增12项，当前列表共64项。实际 browser/桌面手机 PNG、新 exact-head
六套 CI、normal expected-head merge 和 exact-main 六套均尚待运行/核验；
不借用 #144 的证据宣称本候选通过。下节记录旧批次真实闭环，历史失败仍保留。

默认未配置仍 unavailable；未进行生产 key/pin、host listener/installer 激活、
真实账号、physical client/CLI、release/deploy。此卡只关闭可见统一视图增量，
不称 S02/WS08 整体完成，也不自动启动下一功能。


## 2026-10-05 PR #144 已闭环：正式 App native A3 与真实 CI 像素通过

最终 head `ec89d73c64ed6b5b87371d9a72209e79ccc36760` 六套首次 workflow 均
SUCCESS（24 jobs SUCCESS、2项历史 rc8 SKIPPED）；独立 source/doc 与实际
四张中文 desktop/phone PNG 像素复核 PASS。下方较早的 pending/失败叙述保留
为历史，不能继续作为当前状态。

PR [#144](https://github.com/ForceMind/agentbox/pull/144) 已于
2026-10-05T13:59:54Z 正常合并。main read-back 为
`3e313b36b7cfc7c1de1c54cc20164ae223fcd122`，parents 为
`61a5efce6ab43754a2acdb313d5e21ee83f64c52` 与上述 head；tree
`d2fa9213b40db3a5f2b9236646da7fdc50c39645` 与已验 head 完全一致。

exact-main 六套首次 workflow 均 SUCCESS（23 jobs SUCCESS、3 SKIPPED：push
的 dependency-review 与两项历史 rc8）。[Backend](https://github.com/ForceMind/agentbox/actions/runs/37321159493)
三版本各5276 passed/88 skipped，全部14项 native 通过；
[E2E](https://github.com/ForceMind/agentbox/actions/runs/37321159428) 为212 passed/
30 prescribed skipped/0 failed/0 flaky，包括新增52项正式 App native 场景。
212中有16项纯 Node cleanup/counter checks，不能全称浏览器测试。

最终 head artifact11349880911 ZIP SHA256 已核验为
`f41b7b4346bf32acf763153e1269cbfc2b33adb861560deb157370af99c8e723`；
四张原始 PNG 均已打开，固定导航置顶、phone 刷新单行、中文无缺字，完整验证
状态与 inert text/focus 清晰。完整24KiB与未执行性由 E2E 断言证明，截图仅呈现
可滚动区域。同 tree 的 main artifact11350222710 摘要亦已核验为
`0cd6b83f513096b1dd3826a6c068f09d2ebed401acdb246051203bdc88f263db`，
但未重复做 main 图像素审查。

这是 CI 跨进程软件闭环。默认未配置仍 unavailable；生产 key/pin enrollment、
installer/listener 激活、真实 host/physical client/CLI、账号或发布仍未执行。
后续只可按实际已批准计划进入独立下一批，不把更多 fixture/helper 数量当产品进展。
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


## 2026-10-04 A3 独立加密单次读取

#140 exact-head/post-main 六套 CI 全 SUCCESS，main `57cb8cd`。本批将已有
reader/selector/codecs 组合为 [inert encrypted single-read](../WORKBENCH_A3_ENCRYPTED_SINGLE_READ.md)：
原始 expiry、owner nonce ledger、fresh NX、opaque-only 软件 relay 与 Web 完整
验证。actual synthetic fixture 不等同 production authentication/relay/UI；后续
生产接线和真实 host/client 资格仍需各自证据。下方阶段陈述保留历史。

## 2026-10-04 A3 独立协议软件候选

#139 已合并到 `587fe8eabf7e5d5e4d3a561091ec00c3e9f40881`，exact-head 与
post-main 六套 CI 均 SUCCESS。当前独立批次为 [content schema/codecs](../WORKBENCH_A3_CONTENT_CODECS.md)：
专用 context/AAD bytes、四类严格消息、单次 transcript 和跨语言向量；不实施
或开放 encrypted Runtime/API/UI path。完整 PAGE 16 KiB 限制不变，超容量先
TOO_LARGE；真实 host/client 验收继续 NOT RUN。后续 crypto/admission/relay/UI
按合同与证据分别交付，旧批次范围仅作历史。

## 2026-10-04 下一项软件边界

PR #138 已合并到 `35d25bdccbb9311a57fc06a0683f4f60bf50dd9c`，#117 因保留
历史而间接合并。当前仅推进 Runtime-only short-lived staged selectors：versioned
internal observation、完整 snapshot digest、可信 formal Project/session/epoch 绑定
及同一 held view 的校验/读取；生产 resolver、RPC、encrypted channel 与 UI 均未组合。
详见 [当前状态](CURRENT_STATE.md) 与 [reader/selector 合同](../WORKBENCH_A3_STAGED_READER.md)。
此段接续并覆盖下方 reader-only 的历史批次范围，不扩大真实 host/device/Secret 或发布权限。

## 2026-10-04 软件续建优先级（覆盖下方历史冻结）

Owner 已明确暂缓真实目标测试、继续开发并要求列出后续计划。真实
host/device/login/reboot/upgrade/rollback 仍为 **NOT RUN**；软件/CI 不能替代
现场验收或授权发布。当前基线为 PR #136/#137 合并后的
`7fa54c3f5e3ce7e96c3d2cb33828c759665d81d2`。
本批仅复用 Draft #117 接续 S02 Runtime-only staged reader、安全修复和必要
验证，不新增 selector/content channel/UI/Files 编辑。具体边界与事实见
[当前行动](NEXT_ACTION.md)；该最新 Owner 顺序覆盖下方禁止 #117/S02 的
历史冻结，其他 S00–S14 依赖和安全边界保持有效。


## 2026-10-04 接续核对与真实首装准备

已重新核对 PR #136 的 documentation-inclusive head
`d6ee8c7c9635e2b5ecd58f18048fa8c1aaa59474`：Backend、Frontend、Security、
Deployment、E2E、Release Candidate 六套 workflow 均为 terminal SUCCESS。
其中 24 jobs 成功、2 个历史 rc8 jobs 按版本跳过；不能把 skipped 写成通过。
[Backend 证据](https://github.com/ForceMind/agentbox/actions/runs/37166599345)。
Owner 已明确授权继续操作，PR #136 已正常合并，main read-back 为
`7d0521556727d64c80d02d69aea7b9d9b06432af`；父提交与已验证 PR head
一致，tree 与该 head 完全相同。此快照时 post-merge CI 尚待终态；
实时 GitHub 状态优先于本记录。

`setup-fresh-waw` 已完成软件组合与恢复逻辑，不再重做 #131/#134/#135，
也不再把 composition 当成待开发功能。下一实质阶段是同一固定 candidate 的
真实首装资格化，详见 [当前行动](NEXT_ACTION.md) 和
[目标输入记录](R12_TARGET_RECORD.md)。当前没有指定或激活真实目标服务器；
公网 HTTPS、管理员初始化、真实双 CLI 登录/turn、物理客户端、重启及升级回退
仍为 NOT RUN。下方旧阶段叙述仅为历史记录。


## 2026-10-03 接手顺序

[开发交接](DEVELOPMENT_HANDOFF.md) 为当前状态入口；
[逐版本计划](RELEASE_ITERATION_PLAN.md) 和 [首版部署计划](DEPLOYABLE_RELEASE_PLAN.md)
定义当前验收。只推进完整单机首版：一条安装命令、PC/手机、真实双 CLI 与恢复。

PR #134 已合并并统一真实 vendor/Runtime digest framing。当前 Draft #135 已完成
固定 Claude/Codex ELF 资格化、真实 Codex native auth probe 和不执行 vendor CLI 的
qualified enrollment；其最终 documentation-inclusive exact-head CI 与 merge/read-back
仍是当前动作。#135 合并后直接组合完整 fresh-install，再进入真实客户端/双 CLI/
reboot/upgrade/rollback。下方“not started”等均为历史阶段快照，不覆盖本节。
长期 70 项范围保留，在首版验收后逐版本展开。

## Current release focus — 2026-09-29

当前唯一产品目标是 [首个可用单机 RC](RELEASE_ITERATION_PLAN.md)：
先完成 R12 软件/制品，随后在指定目标完成真实 host/client/CLI/
recovery 验收。70 项完整吸收清单仍在 [全量计划](FULL_CAPABILITY_DELIVERY_PLAN.md)，
但 S02–S14 暂不扩大；下列历史阶段陈述不覆盖本次版本顺序。

## Current execution: approved R12 plan

Owner approved [PRP-2026-09-08-v1](PRODUCTION_READINESS_PLAN.md) on 2026-09-08.
R12-A contract/input closure is in progress; dependency-ready B/C/D/E/F software
follows. G/H/I real host/client/CLI qualification and J/K production/publication
remain separately authorized and evidence-bound. R11 and WEV-1 stay delivered;
later workstation features remain Proposed. The earlier snapshot below records
the starting state and does not override this execution update.

## Current increment: workstation evolution

The 2026-09-08 task adds an audit and evidence-backed product evolution to this
existing roadmap. [WORKSTATION_EVOLUTION](../WORKSTATION_EVOLUTION.md) defines
the sequence; [CAPABILITY_MATRIX](../CAPABILITY_MATRIX.md) separates design,
implementation, validation and availability.

1. WEV-1 — merged in PR #87 as `b3e9cd5`: revalidate Workspace observations when
   returning to the browser; no automatic Agent lifecycle operation or new data
   domain. Exact-head CI and independent reviews passed; delivery read-back is
   recorded in the evolution document.
2. R12 — not started: concrete authorized host/trust/provider/bootstrap and
   real CLI/recovery acceptance; remains the first real product-flow blocker.
   Use the five-part [bootstrap/host checklist](../WORKSTATION_EVOLUTION.md#r12-production-bootstrap-and-host-gates):
   production API composition, Runtime filesystem-v2/provider composition,
   activated sockets/isolation, managed CRX/Native Messaging/trustd, and real
   CLI login/input/return/reconnect/exact Stop/reboot acceptance.
3. Proposed follow-ups — bounded Active Work/Attention projection, read-only
   Changes/Files, then capability-bound Discovery/Resume and structured Approval.
   Task/Worktree and external notification remain later, contract-dependent work.

The completed R11 software evidence below remains valid; it does not claim
end-to-end production availability or authorize new host/Secret operations.

## Completed

- Phase 0 through Phase 10 (as per existing repository governance).
- Governance automation policy is merged; routine mechanical actions proceed after CI.
- WAW-1 typed HTTP lifecycle, transient ticket/reconnect, Runtime attachment prepare/detach contracts merged in PRs #47/#48/#49.
- WAW-1 bounded synthetic stream bridge and WAW-2 Codex command identity contract merged in PR #52.
- WAW-1 fail-closed WebSocket route boundary merged in PR #54; WAW-2 synthetic lifecycle support merged in PR #55.

- WAW-3 software recovery/cursor/lease and browser stale-event fences merged in PR #58, with 19/19 exact-head checks successful. Full WAW-3 real transport/reboot remains unverified.

- WAW-2 Codex API/ticket/Web contracts merged in PR #59 with 19/19 exact-head checks successful. Real CLI execution and legacy process interlocks remain gated.

- Workspace metadata workflow merged in PR #60 with 19/19 exact-head checks successful; desktop/mobile metadata interactions are tested, terminal admission remains unavailable.

- Software readiness and packaged WAW scope/gate documents merged in PR #61; 19/19 exact-head checks and independent artifact/doc-presence validation passed.

- Shared Claude/Codex supervisor and stream lifecycle fences merged in PR #63 with 19/19 exact-head checks successful.

- Concrete Runtime executor, formal Project mapping, read-only probes and failed-start recovery merged in PR #64 with 19/19 exact-head checks successful.

- Fixed Noise NX Python/WebCrypto cores, pinned independent vectors and two-role interoperability merged in PR #65 with 19/19 exact-head checks successful.

- Native Chromium Noise verification merged in PR #66; all 60 Linux E2E tests and 19/19 exact-head checks passed.

- Login/reauthentication capacity now follows actual worker completion after caller cancellation; PR #67 merged with 19/19 exact-head checks successful.

- Opaque AWCE Python/Web framing, header builders and interoperability merged in PR #68 with 19/19 exact-head checks successful.

- Descriptor-held executable provenance foundation merged in PR #69 with 19/19 exact-head checks successful; complete interactive process/host qualification remains unfinished.

- Isolated numeric authentication timing diagnostic and failure/privacy regressions merged in PR #70 with 19/19 exact-head checks successful; historical latency cause remains unknown.

- Incremental UTF-8/VT tokenizer foundation merged in PR #71 with 19/19 exact-head checks successful; complete browser terminal/controller remains unfinished.

- Accepted application cryptography merged in PR #73 with 19/19 exact-head checks; full-vector interop and 62 native/normal browser cases passed.

- Full WAW wire profiles and bounded transcript validation merged in PR #74 with 19/19 exact-head checks; real parser-budget integration failures were corrected and measured.

- Staged ticket authority and admission coordinator merged in PR #75 with 19/19 exact-head checks; four independent review findings were fixed before delivery.

- Runtime encrypted attachment stream and exact socket/Stop publication fences merged in PR #76 with 19/19 exact-head checks; final review deadlock and logical-line findings were repaired before delivery.

- Native WebSocket/API ciphertext relay, shared parser/INPUT budgets and cancellation-resistant cleanup merged in PR #77 with 19/19 exact-head checks; all six post-main workflows succeeded.

- Managed Chromium/Native Messaging/trustd browser trust, cumulative root checkpoints,
  bounded browser terminal model and `zh-CN`/English Workspace boundary merged in
  PR #78 with 19/19 exact-head checks and exact read-back.

- Fixed Claude/Codex interactive profiles, native PTY/bootstrap/attach chain,
  Runtime process composition and inert rc5 policies merged in PR #79 at
  `341a69bf...` after 20/20 exact-head checks; six post-main workflows and the
  dynamic Dependency Graph update succeeded.

## Current reassessment

See [REMAINING_PLAN.md](REMAINING_PLAN.md). R0–R10 are delivered through PR #79.
R10 final head `0d9e7c7...` passed 20/20 checks and merged as `341a69bf...` with
exact read-back and successful post-main workflows. Host evidence remains
separately tracked in R12.

## In Progress

- Mac remains the development platform. R11 rc6 and rc7 are delivered by
  PRs #80 and #81, and rc8 is delivered by PR #83. Documentation head
  710ceef completed 26 exact-head checks, merged normally as
  95bf65d6114008b962985f7311941499c961a7b8 with exact parents 87f5bce and
  710ceef, and all six post-main workflows succeeded. rc8 is software evidence
  only: no tag, GitHub Release, host activation or R12 qualification occurred.
  PR #85 final head `751d4d010f92e18780bd6d96fdb3c9ea23107464` completed all 26
  exact-head checks and merged normally as `b07f944ef2c7b590e5a3f1fa50354d6f492d6c31`.
  All six post-main workflows succeeded, so R11 software rc6–rc9 is delivered
  as software evidence. R12 remains independently unstarted and host-gated.

- Parallel multi-agent execution and per-stage GitHub/document updates are
  authorized by Owner on 2026-09-03. The active checklist is `EXECUTION_PLAN.md`.

## Next

- F1: preserve the delivered R11 software contracts and evidence; no tag, GitHub
  Release, production deployment or Provider credential operation follows from
  the merge.
- F2: real Linux host activation, isolation/CLI/PTY/reboot qualification and
  product acceptance remain independently gated.
