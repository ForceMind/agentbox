# 首个用户可部署版本

## 2026-10-04 接续核对与真实首装准备

已重新核对 PR #136 的 documentation-inclusive head
`d6ee8c7c9635e2b5ecd58f18048fa8c1aaa59474`：Backend、Frontend、Security、
Deployment、E2E、Release Candidate 六套 workflow 均为 terminal SUCCESS。
其中 24 jobs 成功、2 个历史 rc8 jobs 按版本跳过；不能把 skipped 写成通过。
[Backend 证据](https://github.com/ForceMind/agentbox/actions/runs/37166599345)。
当前已验证 main 仍是 `769197ed9dda2873b0b066a073efb7319d0665c1`。
PR #136 尚未合并；本次会话的 Ready/merge 操作正在等待明确确认。
实时 GitHub 状态优先于本记录，合并后须重新读取 main 和 post-merge CI。

`setup-fresh-waw` 已完成软件组合与恢复逻辑，不再重做 #131/#134/#135，
也不再把 composition 当成待开发功能。下一实质阶段是同一固定 candidate 的
真实首装资格化，详见 [当前行动](NEXT_ACTION.md) 和
[目标输入记录](R12_TARGET_RECORD.md)。当前没有指定或激活真实目标服务器；
公网 HTTPS、管理员初始化、真实双 CLI 登录/turn、物理客户端、重启及升级回退
仍为 NOT RUN。下方旧阶段叙述仅为历史记录。


## 2026-10-03 当前事实与执行顺序

状态入口为 [DEVELOPMENT_HANDOFF](DEVELOPMENT_HANDOFF.md)。当前 durable main 为
`7c29a470c35b61646e6f6c6a646d3fab9eefb497`（PR #134 merge），当前开发为
Draft #135。package guard、native Ubuntu 24.04 APT/maintenance、固定 vendor 下载、
deferred 首装、Runtime production graph、HTTPS Web/bootstrap/certificate/setup 均已有
前序软件/CI证据；源码仍 rc30，首版尚未可部署。

#135 已资格化固定 Claude 2.1.286 / Codex 0.159.3 最终 ELF，并证明真实 Codex
通过 production native auth helper 在离线 sandbox 中得到 exit 1 未登录状态；
qualified enrollment 只在 verified v2 inventory 与当前 ELF 均匹配时发布固定非秘密
事实，不由 Root installer 执行 vendor CLI。真实双 CLI/PC手机/完整安装、reboot/
upgrade/rollback 仍未验收。

同一版本顺序：#135 final exact-head CI/merge/read-back → 完整
download/deferred apply/依赖/vendor/manifests/policies/qualified enrollment/
activation/setup composition → PC/手机双 CLI → 中断/重启/升级回退 →
不可变制品与有效安装命令。不能把 `setup-waw-web` 单独当作新机安装器，
不提供不存在的发布 URL。Owner 自行安装，不需要 SSH。PUBLIC 仓库不等于
制品已发布；真实 host/Secret/付费调用/发行另按具体授权。

## 历史部署记录（当前状态以交接入口为准）

Owner 在 2026-09-30 要求交付自己能在服务器运行的安装版本，并再次明确 PC 和手机支持。本记录承接 RELEASE_ITERATION_PLAN，不建立新路线，不缩减完整功能目标。

## 交付与入口

- 最终入口是一条固定发布版本的安装命令；脚本获取不可变制品、校验 checksum/manifest/SBOM，预检平台、现有安装和端口，再执行安装。命令在制品与脚本实际发布后给出，不提前提供不存在的 URL。
- Owner 自己执行服务器安装，不需要向 Coding Agent 提供 SSH 地址。安装器现场收集必要的非敏感参数；真实账号登录、证书、付费调用和生产操作仍由执行者按明确步骤决定。
- Linux 服务器与客户端平台分别验收。Owner 已确定首版 PC 和手机浏览器优先；最终原生桌面、iOS/Android 与完整上游功能清单保留。响应式布局不等于手机终端已经可用。
- 本版的用户流程是登录、选择正式 Project、使用 Claude/Codex、输入输出、重连、exact Stop；安装、错误恢复、数据保留和回退也必须能实际执行。

## 当前迭代

| 顺序 | 本轮必要成果 | 查看/运行入口 | 验收 |
| --- | --- | --- | --- |
| 1 | 固定 vendor 资格化与非执行式 enrollment | agentbox-install enroll-qualified-waw-vendors --help；--plan/--recover | 官方 ELF/native auth 证据；v2 inventory + 当前 ELF 双重 pin；关闭态、幂等、不覆盖、漂移/中断恢复 |
| 2 | 安装器现场生成完整可信资源、单一 Runtime production graph | installer + Runtime doctor/start | 固定 manifest/key/epoch/socket/profile 所有权及 Linux/native 集成；缺输入不进入就绪 |
| 3 | PC/手机可用连接与核心交互 | 两端实际登录、项目和 Agent 页面 | 明确客户端信任来源、键盘/触摸、后台返回、重连及 Stop；不能仅用 desktop CI 外推手机 |
| 4 | 固定制品与一键安装入口 | 发布的 bootstrap 与验证制品 | 新安装、重试、中断恢复、升级回退；记录用户现场资格化尚未运行的项 |

这些步骤属于同一个部署版本。调试中间提交不升级版本；安装入口和核心流程的可交付批次验收后，统一固定发布编号与制品。

## 必须闭合的依赖

Owner 已选择 [ADR 0011](../adr/0011-deployable-cgroup-compatibility.md) 的 A 方案：兼容 255 的版本化受限子树。v1 private 合同不被冒充为等价；现有关闭态 unit 仍须完整接线。Legacy core 平台支持保留，实际 WAW 支持须完整实施和资格化。下一步将已通过的探针结果接入启动链，而非继续新增基础批次。

production filesystem-v2 graph、manifest/policy/key/activation building blocks 已在前序批次接线。
当前剩余安装器工作是把这些步骤与 fixed vendor、qualified enrollment、Web setup
组合成一个可恢复 fresh-install transaction；qualified enrollment 本身不启用服务、
不运行 CLI Login、不读取 Provider Secret。

安装器已接入并在 Linux native CI 执行固定 helper 构建；当前 #135 进一步用真实
官方 Codex ELF 穿过 `agentbox-waw-pane-bootstrap --auth-probe`，验证 AWRP、
离线未登录结果与 cleanup。AF_UNIX local IPC 是唯一新增 socket-family 例外；
AF_INET 与 network connect/bind/listen/send/recv 仍拒绝。完整 v2 manifest、
Runtime key、policy/activation building blocks 已存在，下一步是安装事务组合与整体验收。

新建安装现有显式 `resume-install --artifact ... --sha256 ...`，下载入口对应同一 VERSION/SHA256 的 `--resume`。它只接受新 schema-3 的 staging 证据，核对账户/Runtime group、固定配置和目录身份、同一制品及资源清单，确认没有 DB/receipt/current/activation unit，再从 staging 继续同一 transaction。不会重建账户、重写配置或重放迁移；旧 journal、preflight/account-creation 中断、已经迁移/激活以及升级 staging 暂不进入此恢复路径，仍须安全的独立恢复方案。本版恢复验收未全部完成，禁止删除 journal 伪装新安装。

Codex Remote 的 host-global 冲突来源也必须提供可信的 STOPPED/ABSENT 观察。目前 CLI 不支持 status 时，进程未被发现只得到 UNKNOWN；不能改成 ABSENT 或删除原有 Remote 功能来制造可用结果。此依赖随 Runtime 正式启动接线一并闭合。

现有浏览器信任合同依赖 managed Chromium/MV3/Native Messaging/trustd，并明确禁止以 API/DOM/localStorage 等作为生产 fallback。普通手机浏览器不具备这条桌面链。跨平台连接方案必须明确对应可信客户端来源，复核原合同及授权，再实现；不得通过删除该 gate 声称手机可用。原生 App 的安装/签名/分发与浏览器网页支持也分别记录。

Owner 已批准 [ADR 0010](../adr/0010-cross-platform-web-bootstrap.md) 的 HTTPS Web 信任前提；直接实施 PC/手机浏览器核心流程。授权不等于手机支持已通过验收；最后仍分别说明源码/CI、安装制品、真实客户端/CLI和用户服务器资格化。

## 当前事实

基线 main 为 19f8c5125d5a831e3db2d9724a1cc7985b091294，rc30 源码/制品批次已交付。当前分支 codex/r12-deployable-runtime 保留原 checkout 与 rc30 post-merge 文档 WIP；新增服务器注册发布实现和 fixture 验证，尚未提交或构成部署版本。

下载入口代码为 installer/bootstrap.sh，当前接口为 `bash bootstrap.sh VERSION SHA256 [--apply|--resume]`。版本和摘要必须来自独立可信的固定发布说明；下载到的 SHA256SUMS 不作为自身真实性证明。默认只输出 plan；最终一条命令将在完整发布后绑定版本、摘要和 --apply。下载、恢复及账户 focused run 47 项通过，传输与平台采用本地 fixture，尚未证明服务器安装。此源码入口不能当成目前可用的一键部署命令。

参考上游固定源码 30178c4f58b67f8472901356e1484022bd835de0 的 public-docs/connectivity.md、SECURITY.md、server/pairing-qr.ts：保留跨设备连接和扫码体验目标，重接 AgentBox 认证、权限与 Runtime 边界；不接入 Paseo 服务，不自动开放其 relay/password 兼容宽权限。
