# AgentBox 开发交接 — 2026-10-02


## 2026-10-05 工作概览浏览器/像素通过；native3.13 CI 关闭原因诊断

[PR #147](https://github.com/ForceMind/agentbox/pull/147) 保持 Draft，main仍为
`a1cab129f18ede5b982b6ab53d037c51771b4dea`。当前已推 head
`09e3142b145e30d60c9342f2100d6c80682824be` / tree
`806123f6fdd11d4ced2b5e4f542eed9a0573e194` 的 Frontend、Security、Deployment、
Release Candidate、E2E 五套成功。[实际 E2E](https://github.com/ForceMind/agentbox/actions/runs/37350114064)
232 passed/30 prescribed skipped/0 failed/0 flaky（含8项新概览正式App/API
桌面手机双语言、既有64项native；232中16项仍为pureNode）。6张概览原PNG
实际打开且独立功能像素PASS，artifact11363160449 ZIP摘要
`7398c39a542659861914df6f1fcae9c9f250c2544dee08ceed4cdba5aa9c058c`。
这不是对整体美观的认可；新的全量UI设计另线讨论，本卡不加布局/功能。

两轮 Backend 都仅Python3.13在未改动的 native READY测试遇到PATCH_REVOKED；
3.11/3.12与native job通过。历史原因未知；受控300ms CURRENT_REPLY延迟
能复现250ms fail-closed表象，但不是原CI因果证明。本地3.13.5原序前缀受
AF_UNIX平台阻碍，不能替代CI3.13.15。没有改产品预算/断言或重跑旧头。
本候选仅为该测试加入显式opt-in、最多4条固定phase/reason及封顶计数的
failure-only诊断，并保留原异常；不记录正文/凭据/路径，不称为修复。
新增诊断安全测试后3.12/3.13.5各69项通过，完整新head CI仍待采证。
详见[有界合同与失败记录](../WORKBENCH_WORK_OVERVIEW.md)。

尚未Ready/merge，主干与生产均未改动；无生产key/pin、host/账号或发布。
下方pending/失败均保留为当时快照，不能覆盖本节较新的实际结果。

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



## 2026-10-04 continuation verification

The Owner resumed AgentBox development in the current session. PR #136 head
`d6ee8c7c9635e2b5ecd58f18048fa8c1aaa59474` has six terminal successful workflows
(24 successful jobs and two prescribed historical rc8 skips). PR #136 was normally merged after the Owner confirmed continuation and repository
operations. Main read-back is `7d0521556727d64c80d02d69aea7b9d9b06432af`,
with parents `769197ed9dda2873b0b066a073efb7319d0665c1` and
`d6ee8c7c9635e2b5ecd58f18048fa8c1aaa59474`. Its tree exactly matches the
verified PR head. Post-merge CI is pending at this snapshot; no target-host
operation or product qualification is claimed.

This documentation-only continuation reconciles the stale #135 roadmap/index
and historical target inputs with the implemented `setup-fresh-waw` sequence.
See [target inputs](R12_TARGET_RECORD.md) for the actual remaining qualification
requirements. Do not redo composition, open #117, or substitute more fixture
checks for real fresh-host/client/login/reboot/upgrade/rollback evidence.
Repository link checking and `git diff --check` pass; the existing six workflow
results validate d6ee8c7 only, not a later documentation commit.


## 2026-10-04 PR #136 接手点

Owner 已决定由其他 AI 继续首版开发；本节是当前最高优先级交接快照，
实时 GitHub 状态始终高于本文。

已完成并 durable 的主线：

- PR #134 MERGED：统一真实 vendor observation 与生产 Runtime 的 framed
  stdout/stderr digest contract。
- PR #135 MERGED：固定 Claude 2.1.286 / Codex 0.159.3 的 release-qualified
  enrollment facts；真实 Codex 通过 native auth helper；只允许 AF_UNIX
  本地 IPC，AF_INET/AF_INET6 与网络操作继续拒绝。
- 当前 `main` =
  `769197ed9dda2873b0b066a073efb7319d0665c1`。

当前未合并工作：

- Draft PR #136：`codex/r12-fresh-install-composition`
- 最后一个代码-only exact head：
  `815adfcb60a72c7de48cdfcdc2007c338b7b03cd`
- 该 exact head 六套 workflow 全部 SUCCESS：Backend / Frontend /
  Security / Deployment / E2E / Release Candidate。
- 本次交接文档提交会把 PR head 继续向前推进；下一位 AI **必须重新读取
  PR #136 的实时 head 和 exact-head CI**，不能拿 815adfcb 的绿灯替代新的
  documentation-inclusive head。

#136 已实现：

1. 新 root-only CLI：`setup-fresh-waw`；
2. 固定顺序：
   deferred install -> browser dependencies -> fixed vendors -> manifests ->
   policies -> qualified enrollment -> existing `setup-waw-web` / HTTPS；
3. fresh 用 `apply --defer-activation`；
4. staged 中断只允许显式 `--recover`，并用
   `resume-install --defer-activation`；
5. same-version 继续必须再次验证 exact artifact，并要求 committed journal
   明确存在 `activation_deferred` + `receipt_written`；
6. 普通已经运行的旧安装不能被该 fresh-only 命令收养；
7. 如果 activation journal 已进入 `preparing/configured/started`，恢复时
   跳过所有要求离线的前置阶段，直接恢复 `setup-waw-web`，避免已启动 WAW
   被 policy quiescence guard 卡死；
8. 已新增顺序、staged recovery、same-version deferred evidence、started
   activation -> HTTPS-only recovery、CLI 参数合同测试。

#136 当前不应被描述为“真实首装已经验证”。仍未闭合：

- 同一 release artifact 在真实目标 Linux 上从零执行完整
  `setup-fresh-waw`；
- 真实 DNS/公网 80/443/Let's Encrypt 与最终 HTTPS；
- 实际初始化管理员；
- 真实 Claude Code 登录、输入/输出、resize、detach/reconnect、exact Stop；
- 真实 Codex CLI 登录、输入/输出、resize、detach/reconnect、exact Stop；
- 物理 PC / Android / iOS 的 IME、触摸、viewport、后台返回与重连；
- service reboot / host reboot；
- upgrade / rollback；
- immutable release artifact + checksum/SBOM/provenance + 正式安装命令。

下一位 AI 的第一步不要写新功能。先：
读取 `AGENTS.md`、本文件、`CURRENT_STATE.md`、`NEXT_ACTION.md`，
实时核对 main、PR #136 head、exact-head 六套 CI；若文档-inclusive head 全绿，
正常合并 #136 并 read-back main。之后直接进入真实首装资格化。

## 2026-10-03 #135 qualified enrollment continuation

Durable main before this Draft is
`7c29a470c35b61646e6f6c6a646d3fab9eefb497` (PR #134 merge). Draft #133 is
CLOSED/unmerged and must not be resumed; its installer `runuser` observation
is weaker than the production native auth boundary.

Continue Draft #135 `codex/r12-qualified-vendor-enrollment`. The fixed release
facts are now backed by actual official-download and native-helper evidence:
Claude 2.1.286 ELF
`fe503f65c6289d59c23e5b21ae44f03583f997dd33a2cbfc75ab4f96fb8fc73f`;
Codex 0.159.3 ELF
`8bf204b36a2f6dd0dab73aa2f639892e67ef9ac8befccb4a05b1496ebf25c479`;
Codex native unauthenticated framed digest
`76522c70a3df95fdd59bc4851200017bf42947a49d47e216c95bb0dea1579d9c`.

The real native probe originally exposed exit 101/panic/EPERM because all socket
creation was denied. The accepted repair allows only AF_UNIX local socket/socketpair
creation; Internet-family socket creation and network operations remain denied.
At exact code head `f6eb036490c508571fea8e145e2a4c5079c9fc6a`, the ordinary native
matrix passed 109/1 skip, the real pinned Codex probe passed with AWRP + exit 1
and the digest above, and sanitizer native passed 60/1 skip.

#135 now also provides `enroll-qualified-waw-vendors`: no caller version/digest
arguments, no installer vendor execution, exact v2 inventory/ELF revalidation,
atomic existing enrollment publication/recovery, no Secret read and no service
start. Runtime remains responsible for the actual auth-state observation.

Several documentation commits follow the native evidence, so first read live PR
head and require all six workflows on that exact head. After terminal SUCCESS,
merge #135 normally and read back main. Then continue complete fresh-install
composition; do not return to #133 or #117.

## 2026-10-02 #131 合并后继续开发

实时 GitHub 状态覆盖下方历史快照：当前 `main` =
`3da84df5fcc8b5543405f651d1a78c21ea9a8376`，PR #131 已 MERGED；
其 exact PR head 为 `2cc3443bb42c58fe066be60f42f6c62aafa1c00d`。
PR #132 的 merge `bac457b43efaa12c3a0a11f36af2cf5250b9a268` 是当前 merge 的第一父提交，
因此下方把 bac457 写成“current main”以及把 #131 写成 Draft 的段落仅保留为历史证据。

当前继续分支为 `codex/r12-vendor-observation-digest`。已确认并修复首个
post-#131 缺口：真实 pinned-vendor CI 曾使用 `sha256(stdout + stderr)`
生成 Codex unauthenticated digest，而生产 Runtime parser 使用带 stdout/stderr
长度 framing 的 `waw_vendor_probe_output_digest`。当前分支改为复用生产 helper，
并增加 framing 回归。此批只统一真实 observation 的 digest contract；
完整 Runtime-only observation/enrollment、fresh-install composition、真实双 CLI、
PC/Android/iOS、reboot/upgrade/rollback 与 release 仍按原主线继续。

## 2026-10-02 新环境继续开发更新

新环境不依赖旧机器路径、临时文件或未提交 WIP；GitHub 已推送内容是交付基线。
当前 main 已是 `bac457b43efaa12c3a0a11f36af2cf5250b9a268`（PR #132 merge）。

Draft #131 的已知 package-guard 恢复缺口已进入软件修复：`a6dd02b` 增加严格
matching guard 的独立 recovery，`e1653a4` 覆盖 packages 为空的 post-APT
crash window，`144817d` 增加回归测试并保证普通 no-op 不改 foreign policy。
分支随后正常 merge 当前 main，不进行 history rewrite。下方关于 797204e 和
“恢复缺口尚未修复”的内容保留为交接时历史证据，不覆盖本节。

#131 的 `e23119d` 软件基线六套 CI 已全绿。新增 native PID-1 APT probe
随后证明：实际安装缺失 certbot 时服务没有进入 active，但 `certbot.timer`
被 distro 自动 enable；这暴露了重启副作用而不是被 fixture 掩盖。当前候选已
增加 v2 guard dependency/phase recovery、只对本次新引入 unit 的 disable+readback，
并增加 maintenance service native sandbox 执行。预装 nginx 状态必须前后不变。
最终 exact-head CI 仍待全部终态成功；在此之前 #131 保持 Draft。

Owner 要求更新 GitHub/文档后转交新对话。本批只交接文档，停止新增开发。
实时 Git/GitHub 优先于本文快照；其他状态文档的旧条目是历史证据。
本机工作区路径与未提交 WIP 清单保存在本地交接附件，不发布到公开仓库。

## 当前目标与实际状态

**首个用户可部署版本尚未完成。** 源码仍为 Python `0.3.0rc30`、Web
`0.3.0-rc.30`。本批没有发布新版本、安装 URL，也没有激活用户服务器。

唯一首版目标：Owner 自己在 Linux 服务器运行一条固定版本安装命令，取得
HTTPS 入口；PC 和手机浏览器登录并选择正式 Project，分别使用服务器上的
Claude Code 和 Codex CLI，完成真实 input/output、resize、detach/reconnect、
exact Stop，并能处理中断、重启、升级与回退。不要再索要 SSH 地址；
Origin/email/ACME 同意由安装现场按步骤提供。

长期仍吸收上游全部 70 项能力，仅保留 AgentBox 品牌与运行服务，保留必要
版权/许可声明。原生桌面、iOS/Android、Files/Changes、relay/Hub 等按后续
版本展开；首版期间不恢复标签、导航、插件等旁支开发。

## Git 与未合并成果

2026-10-01T17:50:25Z 核对：fetch、Git/PR/CI 查询 exit 0。
文档分支 `codex/handoff-2026-10-02` 从 `origin/main` 创建，基线
`ba065e355cbf17ea4d68e8badcdde4ca81f46c41`（PR #130 merge）。
本文提交 SHA 以 PR/`git log` 为准，不在文件中填自引用 SHA。

- [Draft #131](https://github.com/ForceMind/agentbox/pull/131)：
  `codex/r12-browser-dependencies`，HEAD
  `797204e2dc0430eb56ffb6c3e56b93c1e465d04b`；已推送，当前 exact-head
  24 SUCCESS、2 SKIPPED，仍 OPEN/Draft。真实 APT/boot/完整流程未验收。
- [Draft #117](https://github.com/ForceMind/agentbox/pull/117)：Runtime-only staged
  Git patch reader，不是首版前置条件。本批不推进；历史文档 Draft #42 同样保留。
- 中断时托管执行工作树干净；本批改为纯文档分支。原工作区有旧 WIP，必须
  保全，不能 reset/stash/clean、广泛提交或未经比较复制到新分支。
- 针对本次开发路径与常用测试/同步工具的只读进程检查未发现匹配的遗留
  工作进程；不是全机器审计。交接时 Goal 查询为 null。

接手先执行 `git worktree list`、`git status --short --branch`、
`git fetch origin --prune`，按本地附件选择托管工作区。读取 #131 当前 HEAD/CI。
工作树干净后才切回 `codex/r12-browser-dependencies`；需要带入最新文档时
正常 merge `origin/main`，不 history rewrite。新环境可从远端候选建立独立分支。

## 已合并成果与证据边界

| 成果 | 合并位置/证据 | 未证明的范围 |
| --- | --- | --- |
| Runtime filesystem-v2 唯一 production graph、固定资源/manifest/enrollment、受限 cgroup 启动与恢复 | 先前 R12 软件批次；`waw_runtime_provider.py`、`server.py`、`waw_manifest_install.py`、`waw_activation.py` | 真实双 CLI、目标机重启恢复未验收 |
| Root Web/bootstrap 发布、独立 HTTPS ingress | PR #125，merge `f2af937dcf3c437409400ebcf1ba1d56c5a21f3a`；Deployment `36859319313` | Linux nginx/路由为 fixture；不是用户主机或手机验收 |
| Web Origin 配置与 HTTPS 激活 | PR #126，merge `ebf06758b93423b7110539854e9d30dd80b4266f`；Deployment `36862158050` | native PID 1、DynamicUser、LoadCredential、写入拒绝、fixture HTTPS 有证据；不是公网 CA/真实 CLI |
| ACME 事务、每日 Web maintenance | PR #127，merge `753e8be423e4a72276e28d93ac9e74a42961120f` | 参数解析/fixture 有证据；真实签发续期、maintenance service sandbox NOT RUN |
| 已安装/已 enrollment 主机的 `setup-waw-web` | PR #128，merge `4f849bea943e6062fac80d3c876f3e70a69d5a8d` | 不是首次安装入口 |
| 固定官方 native vendor 安装 | PR #129，merge `7761310647b62a8a0fd1489715f0cdc2af40787f`；Deployment `36875716477` | 实际 Claude `2.1.286`、Codex `0.159.3` 版本/签名/empty-HOME 未登录观察通过；不是 Login/agent turn |
| 首装 `apply` / `resume-install --defer-activation` | PR #130，merge `ba065e355cbf17ea4d68e8badcdde4ca81f46c41` | fresh-only、同模式恢复，`health_verified=false`；不启动服务，不等于完整首装 |
| 固定 APT 依赖候选 | Draft #131 / `797204e2dc0430eb56ffb6c3e56b93c1e465d04b` | 37 项依赖/platform/host fixture 回归、Ruff、374-file mypy 通过；实际 APT/boot NOT RUN |

历史 PR 的软件 CI 在 `CURRENT_STATE`；#131 当前 CI 本批重新确认，其余历史
run 未因文档更新重跑。真实 PC/Android/iOS、双 CLI、G1–G5、完整新装、重启、
升级回退均未闭合。绿 CI、版本数字、测试数量不能代替这些证据。

## 接手后的唯一开发路径

先关闭 #131 的 APT 副作用与恢复缺口，在隔离 Linux/PID 1 环境记录安装前后、
重启后的 unit/端口/策略，保护既有服务；不要在 Owner 服务器试验。

- `lifecycle.py:install_waw_dependencies` 仅在 `packages` 非空时调用 guard。
  安装完成但在清理 guard 前中断，下一次依赖齐全时跳过清理，`--recover`
  也走不到 guard。缺口直接来自当前控制流，尚未现场复现。
- `policy-rc.d` exit 101 不能单凭源码证明所有 maintainer script 都不启动服务；
  nginx.service/certbot.timer 的 boot enablement 未验收。返回字段
  `services_started=false` 不是实际进程观察。
- 完整匹配的临时 guard 才允许显式恢复；partial/foreign 文件不自动修补/收养。
  自动审批曾拒绝 prefix repair，原因是可能改写用户策略；被拒绝方案未应用。
  不要盲目删除 `/usr/sbin/policy-rc.d`。

再把现有步骤接成完整 fresh-install，而不是给底层批次另建“版本”：固定制品
下载 → deferred apply → 固定依赖/vendor → 完整资源/key/public observations →
enrollment → `setup-waw-web` → 打印实际 HTTPS 入口。
`enroll-waw-vendors` 仍要求外部提供 `--claude-version`、`--codex-version`、
`--codex-unauthenticated-output-sha256`；必须来自实际受限 Runtime-only 观察，
不能填默认/合成值开启服务。

随后在同一候选完成以下验收，失败先恢复故障，不扩大功能范围：

1. 新装、同版本重试、关键中断/失败恢复、数据保留、maintenance service 执行。
2. 真实 CLI 在 WAW namespace/profile/权限下启动与登录；核对 Claude interactive
   profile 与 remote-control metadata 是否一致。Ubuntu 24.04 scoped AppArmor
   userns 未资格化，不能以全局关闭防护替代目标支持。
3. PC 和代表性 Android/iOS 的输入法、触摸、resize、后台返回、重连、exact Stop，
   完整 G1–G5。响应式截图/模拟 viewport 不能代替手机证据。
4. 服务/主机重启、升级/回退；核对 `Host.stop_agentbox`、旧 unit 清单与新增
   Web/maintenance units 的停用、卸载和生命周期，不能遗漏 timer/凭据/overlay。
5. 验收后冻结候选版本、统一入口，发布不可变制品、checksum/SBOM/provenance
   与真实安装命令。仓库本批读取为 PUBLIC，但最终制品/URL 未发布或验证；
   仓库公开不等于安装命令已经可用。

每批只做受影响的必要验证，复用有效证据。默认单智能体，不启动子智能体，
不声称提示词能切换模型；给出具体下一步与可查看节点。若创建 Goal，先读取
现有状态，保留完整首版验收，不把单个基础 PR 标为主目标完成。

## 架构与授权

[ADR 0010](../adr/0010-cross-platform-web-bootstrap.md) 的 `https-web-v1` 和
[ADR 0011](../adr/0011-deployable-cgroup-compatibility.md) 的 systemd 255 受限
子树已批准软件实施；不要按“待授权”重问，不冒充 native/private 等价。
Control Plane 决定、Runtime 固定 typed actions、Root Helper 固定 privileged
lifecycle；禁止 Browser 任意 shell/filesystem gateway。Web/API/Worker non-root，
不读取 Runtime HOME/Provider Secret；Runtime 独占 Secret authority，Claude
runtime/session-only。TLS 维护不获得 Runtime/Provider Secret authority。
真实 host、Secret、付费调用、release publication 仍按明确范围授权；普通
软件按既有 CI→merge→read-back。本次文档更新不升级产品版本。

macOS 沙箱曾让 chmod(03770) 立即变 01770；相同临时目录探针在窄范围授权的
沙箱外保留 03770，原样 lifecycle/staged 测试 119 项通过，未放宽断言。
遇到同类问题先区分权限与代码缺陷，不改生产权限制造通过。

计划入口：[逐版本计划](RELEASE_ITERATION_PLAN.md)、[首版部署计划](DEPLOYABLE_RELEASE_PLAN.md)、
[完整能力计划](FULL_CAPABILITY_DELIVERY_PLAN.md)、[R12 验收计划](PRODUCTION_READINESS_PLAN.md)。
