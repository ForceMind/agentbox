# 首个用户可部署版本

Owner 在 2026-09-30 要求交付自己能在服务器运行的安装版本，并再次明确 PC 和手机支持。本记录承接 RELEASE_ITERATION_PLAN，不建立新路线，不缩减完整功能目标。

## 交付与入口

- 最终入口是一条固定发布版本的安装命令；脚本获取不可变制品、校验 checksum/manifest/SBOM，预检平台、现有安装和端口，再执行安装。命令在制品与脚本实际发布后给出，不提前提供不存在的 URL。
- Owner 自己执行服务器安装，不需要向 Coding Agent 提供 SSH 地址。安装器现场收集必要的非敏感参数；真实账号登录、证书、付费调用和生产操作仍由执行者按明确步骤决定。
- Linux 服务器与客户端平台分别验收。Owner 已确定首版 PC 和手机浏览器优先；最终原生桌面、iOS/Android 与完整上游功能清单保留。响应式布局不等于手机终端已经可用。
- 本版的用户流程是登录、选择正式 Project、使用 Claude/Codex、输入输出、重连、exact Stop；安装、错误恢复、数据保留和回退也必须能实际执行。

## 当前迭代

| 顺序 | 本轮必要成果 | 查看/运行入口 | 验收 |
| --- | --- | --- | --- |
| 1 | 非敏感 vendor enrollment 计划、发布及中断恢复 | agentbox-install enroll-waw-vendors --help；--plan/--recover | 实际 CLI 与完整 cross-pinned fixture；关闭态、幂等、不覆盖、路径/链接/漂移、中断恢复 |
| 2 | 安装器现场生成完整可信资源、单一 Runtime production graph | installer + Runtime doctor/start | 固定 manifest/key/epoch/socket/profile 所有权及 Linux/native 集成；缺输入不进入就绪 |
| 3 | PC/手机可用连接与核心交互 | 两端实际登录、项目和 Agent 页面 | 明确客户端信任来源、键盘/触摸、后台返回、重连及 Stop；不能仅用 desktop CI 外推手机 |
| 4 | 固定制品与一键安装入口 | 发布的 bootstrap 与验证制品 | 新安装、重试、中断恢复、升级回退；记录用户现场资格化尚未运行的项 |

这些步骤属于同一个部署版本。调试中间提交不升级版本；安装入口和核心流程的可交付批次验收后，统一固定发布编号与制品。

## 必须闭合的依赖

当前 production _main 仍拒绝 filesystem-v2；安装器也没有现场生成完整 v2 资源的步骤。新注册命令只发布非敏感观察记录，不启用服务、不运行 CLI Login、不读取 Provider Secret。

安装器现已接入目标机 native helper 构建：从已验证的源码编译三个固定程序，验证版本、拒绝任意命令和 ELF 加固，整体发布 libexec 与源码/输出摘要记录。制品 manifest 保持原样；安装状态、回滚和保留流程通过显式闭合的生成目录校验。Linux CI 的真实编译尚待运行，不能从本地合成 ELF 记录测试外推。gcc/binutils 纳入固定依赖映射。完整 v2 manifest、Runtime key、公钥观测和启用事务仍未完成。

新建安装在 staged journal 中断后的整事务恢复仍是已有缺口；helper 的独立重试不能代替它。本版必须提供显式、同一制品 pin 的恢复，证明未迁移/未激活及账户/资源身份后继续，未知状态继续拒绝，不允许靠删除 journal 重新安装。

Codex Remote 的 host-global 冲突来源也必须提供可信的 STOPPED/ABSENT 观察。目前 CLI 不支持 status 时，进程未被发现只得到 UNKNOWN；不能改成 ABSENT 或删除原有 Remote 功能来制造可用结果。此依赖随 Runtime 正式启动接线一并闭合。

现有浏览器信任合同依赖 managed Chromium/MV3/Native Messaging/trustd，并明确禁止以 API/DOM/localStorage 等作为生产 fallback。普通手机浏览器不具备这条桌面链。跨平台连接方案必须明确对应可信客户端来源，复核原合同及授权，再实现；不得通过删除该 gate 声称手机可用。原生 App 的安装/签名/分发与浏览器网页支持也分别记录。

具体网页方案见 [ADR 0010](../adr/0010-cross-platform-web-bootstrap.md)，待 Owner 授权新的网页信任前提。依赖已满足的服务器软件继续实现；客户端方案未确认时，不把手机支持写成 PASS。最后要分别说明源码/CI、安装制品、真实客户端/CLI和用户服务器资格化。

## 当前事实

基线 main 为 19f8c5125d5a831e3db2d9724a1cc7985b091294，rc30 源码/制品批次已交付。当前分支 codex/r12-deployable-runtime 保留原 checkout 与 rc30 post-merge 文档 WIP；新增服务器注册发布实现和 fixture 验证，尚未提交或构成部署版本。

下载入口代码为 installer/bootstrap.sh，当前接口为 `bash bootstrap.sh VERSION SHA256 [--apply]`。版本和摘要必须来自独立可信的固定发布说明；下载到的 SHA256SUMS 不作为自身真实性证明。默认只输出 plan；最终一条命令将在完整发布后绑定版本、摘要和 --apply。39 项下载/解释器/注册测试通过，传输与平台采用本地 fixture，尚未证明服务器安装。此源码入口不能当成目前可用的一键部署命令。

参考上游固定源码 30178c4f58b67f8472901356e1484022bd835de0 的 public-docs/connectivity.md、SECURITY.md、server/pairing-qr.ts：保留跨设备连接和扫码体验目标，重接 AgentBox 认证、权限与 Runtime 边界；不接入 Paseo 服务，不自动开放其 relay/password 兼容宽权限。
