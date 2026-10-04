# AgentBox 开发交接 — 2026-10-02

## 2026-10-04 continuation verification

The Owner resumed AgentBox development in the current session. PR #136 head
`d6ee8c7c9635e2b5ecd58f18048fa8c1aaa59474` has six terminal successful workflows
(24 successful jobs and two prescribed historical rc8 skips). Main remains
`769197ed9dda2873b0b066a073efb7319d0665c1`; Ready/merge awaits explicit
confirmation in this session. No merge or target-host operation is claimed.

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
