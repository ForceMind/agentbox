# AgentBox 能力与吸收决策矩阵

审计日期：2026-09-08。基线 `b72f6ea67647d63ce26ae5610094e8aec34f7a78`。
本矩阵配合 [WORKSTATION_EVOLUTION](WORKSTATION_EVOLUTION.md) 使用，不作为另一份 Roadmap。
设计、代码、验证、产品可用性分别填写；已有历史主机资格仅覆盖明确的 rc1 管理范围。
CI 栏指基线提交的已完成 CI，R 指本次实际测试。R12 当前未验收。

## 能力矩阵

| 分组/能力 | 设计 | 实现 | 验证 | 产品状态与差距 | 本仓证据 | 吸收结论/优先级 |
| --- | --- | --- | --- | --- | --- | --- |
| 安装/环境检测 | Accepted | 已实现 | CI + rc1 部分主机 | 受限可用；OS/架构/ABI 不通用 | AB01 | 保留现状；R12 P1 |
| 升级/程序回滚 | Accepted | 已实现 | CI + rc1 指定主机 | 受限；receipt/备份/兼容目标必须匹配 | AB01 | 保留现状；不搬运 box snapshot |
| 卸载 | Accepted | 已实现 | CI | 仅自有程序；保留 DB/Project/凭据目录 | AB01 | 保留现状 |
| SQLite/config 备份 | Accepted | 已实现 | CI + R 4 cases | 受限；无 Project 全量备份/凭据迁移承诺 | AB02 | 改善说明；复用现有备份 |
| 跨机恢复/灾备 | Proposed 历史设计 | 部分实现 | 备份/rollback CI；跨机未测试 | 不可用的完整迁移产品；不能套用 downgrade | AB02 | 后续吸收；P2 |
| CLI/Installer Doctor/导出 | Accepted | 已实现 | CI | 受限、有界安全摘要；不是通用host日志 | AB03 | 保留现状 |
| Workstation | Accepted 单机 | 已实现部署 identity | CI | 无需新建多服务器实体 | AB01/AB09 | 保留现状；Coder 企业fleet不适合 |
| Project | Accepted | 已实现 | CI | 正式ID/relative_path/READY；不是任意目录 | AB04 | 保留现状 |
| Workspace | Accepted | 已实现 | CI/受控夹具 | 当前 Project+AgentType 一记录；不是任意多工作副本 | AB05 | 保留现状；多Workspace后续 |
| AI Session | Accepted WAW 子集 | 部分实现 | CI | 工作区generation存在；通用对话历史/Resume未闭合 | AB05 | 后续吸收；Codexia分层 |
| Web Session | Accepted | 已实现 | CI | 登录会话，不是AI上下文 | AB06 | 保留现状；禁止混用 |
| Task | Proposed 本轮概念 | 未实现 | 未测试 | 只有后台Job，不能冒充用户任务 | AB04/AB05 | 后续吸收；P3 |
| Runtime/AgentType | Accepted | 已实现适配基础 | CI/CLI fixtures | 按工具能力；不能假设所有CLI支持同一API | AB07 | 保留现状 |
| Provider/Model/CredentialRef | Accepted 受限基础 | 部分实现 | CI | 非Secret元数据/能力基础；未成为生产Provider管理 | AB08 | 保留边界；后续独立契约 |
| Git Worktree | Proposed 候选 | 未实现产品工作流 | 未测试 | 共享.git/磁盘/cleanup成本未定 | AB04/AB07 | 后续吸收；不默认每Task一个 |
| Agent交互/终端 | Accepted | 组合软件已实现；部署入口部分 | Linux CI/本地合成E2E | NOT ADMITTED：production bootstrap/信任安装未闭合 | AB09/AB10 | 优先R12闭环，不能开放fallback |
| Files文件树/读取 | 历史Proposed，未有Accepted新RPC | 未实现相应API | 未测试 | 不可用；必须新Project-scoped只读契约 | AB07/AB11 | 后续吸收；P1在明确授权后 |
| Changes/patch Diff | Proposed | 未实现相应API | 未测试 | Git dirty计数不能代替Diff | AB07/AB11 | 后续吸收；P1 |
| Git Status/Branch/Pull/Push | Accepted | 已实现 | CI/适配器测试 | 受限；ff-only/单refspec/不force/no hooks | AB07 | 保留现状 |
| Git Stage/Commit | 未有Accepted实现契约 | 未实现 | 未测试 | 无产品写入口 | AB07/AB11 | 后续吸收；明确用户动作/锁/回退先行 |
| GitHub PR摘要/Draft PR | Accepted | 已实现 | CI/受控gh fixtures | 实际仓库身份与认证决定可用性 | AB07 | 保留现状 |
| 测试结果归因 | Proposed 展示目标 | 未实现可信聚合 | 未测试 | 终端文本/文件改动不能推导测试通过或Agent归属 | AB04/AB11 | 后续吸收；P2 |
| Detach/Reconnect | Accepted | 已实现组合 | CI/模拟transport | 不等于Stop/Resume；真实CLI需R12 | AB05/AB10 | 保留协议；WEV-1改善返回状态 |
| 返回页面状态新鲜度 | Accepted恢复约束 | WEV-1已合并 | status18/controller24/page18单测；Chromium中英四场景；PR #87 CI/post-main | 软件验收完成；真实OS恢复未验收 | AB12 | 已改善；WEV-1完成 |
| Resume/History | 能力观察Accepted，产品执行未闭合 | 部分基础 | capability CI；产品未测试 | 不能承诺明天恢复原进程 | AB08/AB10 | 后续吸收；P1依vendor证据 |
| Existing Session Discovery/Adopt | observation基础Accepted，其余Proposed | 部分基础 | CI；实际发现接管未验证 | 不扫描整机/其他HOME，发现不授予Stop | AB08 | 后续吸收；Unknown不得当支持 |
| 移动端布局/短输入/Stop | Accepted | 已实现 | 本地+Linux Chromium矩阵 | 软件证据；真实连接仍需R12 | AB10/AB12 | 改善现有实现；P2 |
| Web内Attention | Proposed | 未实现产品投影 | 未测试 | Job needs_attention存在但无站内收件箱 | AB04/AB11 | 后续吸收；P2，复用事件 |
| Runtime结构化Approval | 未有当前Accepted adapter契约 | 未实现 | 未测试 | Provider事务Approval不等于Agent批准 | AB08 | 后续吸收；不能解析终端注入yes |
| 外部通知/PWA push | Proposed | 未实现产品交付 | 未测试 | 无权限/后台必达证据 | AB11 | 后续吸收；P2/P3 |
| Job持久化/租约/幂等 | Accepted | 已实现 | CI + R 6 cases | 同project锁；超时不确定副作用不重放 | AB04 | 保留现状；不再建队列 |
| 进程身份/代次/exact Stop | Accepted | 已实现软件 | Linux native CI | pidfd/epoch/固定helper不是real host证据 | AB05/AB09 | 保留现状；R12验收 |
| API/Runtime重启分类 | Accepted | 已实现软件 | CI故障注入 | 同epoch/更高epoch/回退分类；重启不等于Resume | AB05/AB10 | 保留现状；R12补验 |
| 背压/输出上限/丢失提示 | Accepted | 已实现软件 | 单测/互通/CI | bounded cursor/redraw，不承诺无限历史/exactly-once | AB10 | 保留现状 |
| Auth/CSRF/Origin/管理员 | Accepted | 已实现 | CI + 历史host管理 | 本地TTY首次admin，loopback默认 | AB06 | 保留现状 |
| Secret与审计 | Accepted | 基础已实现，生产Secret入口受限 | CI虚拟Secret/泄露canary | Web/API/Worker不读取Runtime材料 | AB08/AB13 | 保留现状；不复用竞品密钥系统 |
| OS隔离/网络文件边界 | Accepted固定策略 | 软件已实现、安装与证据部分 | Linux native CI | 固定入口/加密不证明安全沙箱 | AB09 | R12前置；不可“现在启用” |
| 供应链/包/校验和 | Accepted | 已实现 | packaging/reproducibility CI | unsigned；checksum不验证发布者身份 | AB01/AB13 | 改善说明；签名后续独立发布契约 |
| 兼容矩阵/诊断 | Accepted | 已实现受限矩阵 | fixture/CI/rc1指定host | aarch64/新CLI/新OS默认未资格化 | AB03/AB13 | 保留现状；声明逐版本 |
| 数据保留 | Accepted局部策略 | 部分实现 | retention/job/backup tests | 无统一Task/输出历史保留承诺 | AB02/AB04/AB08 | 改善已有说明；不新事件宇宙 |
| 指标/日汇总 | Proposed | 未实现业务指标 | 未测量 | 没有CLI成功率/每天SSH/空闲耗用测量 | AB11 | 先测量；P3不建监控集群 |
| 多租户/云市场/通用shell/商城 | 明确非目标 | 无授权 | 不适用 | 超出单人工作站定位 | AB13 | 不适合 |

## 首轮取舍的成本与验收

| 候选 | 用户价值/差距 | 依赖与复杂度 | 攻击面/恢复成本 | 测试与维护负担 | 权限和结论 |
| --- | --- | --- | --- | --- | --- |
| 返回重读 | 重新操作前得到新观察 | 现有GET/生命周期ref；中等状态耦合 | 不加RPC/数据表；取消GET，无副作用重放 | 事件合并、late response、旧确认负例；复用catalog | 本轮授权，WEV-1 |
| Active Work首页 | 用户更快找到需关注的工作 | 需有界Job/Session索引和新鲜度；中等 | 读查询与最小元数据；不保留终端 | 不能把活动数当完成数；必须来源/Unknown | Proposed，后续最小投影 |
| Files/Diff | 能检查实际变化 | 新typed Runtime读契约；高 | traversal/symlink/Secret内容/大文件；正文不默认缓存或导出 | 路径、编码、binary、内容配额和脱敏限制 | 后续方案需批准，先只读 |
| Discovery/Resume | 找回已有工作 | 明确用户/路径/项目 + 每vendor能力；高 | 错误接管/身份复用/凭据私有格式；失败只能只读 | 跨版本、已退出/外部/托管/权限矩阵 | Proposed；Adopt独立批准 |
| Attention/Approval | 手机处理待办 | 已有事件归属；审批另需受信adapter协议 | 通知是提示，审批是一次性权限；不能混用 | 去重/到期/撤销/运行代次/并发消费 | 站内优先，外部通知后续 |
| Worktree/Task | 长期目标和隔离工作副本 | 当前Session不足的真实案例先行；中/高 | .git共享锁/磁盘/残留/force cleanup；需可恢复删除策略 | 版本迁移/冲突/生命周期成本持续 | Later；不复制强制清理 |

## 本仓证据索引

以下均是在上述基线的路径/符号观察；当前内容可能随 WEV-1 演进，历史复验可
从 [基线 tree](https://github.com/ForceMind/agentbox/tree/b72f6ea67647d63ce26ae5610094e8aec34f7a78) 读取。

- AB01：[Installer lifecycle](../installer/src/agentbox_installer/lifecycle.py) `plan/apply/rollback/uninstall`；[测试](../tests/unit/test_installer_lifecycle.py)；[平台支持](PLATFORM_SUPPORT.md)。
- AB02：[备份](../installer/src/agentbox_installer/backup.py) `create_sqlite_backup/verify_sqlite_backup`；[在线WAL/篡改测试](../tests/unit/test_installer_backup.py)；[retention](../installer/src/agentbox_installer/retention.py)；[迁移设计](BACKUP_AND_MIGRATION.md)。
- AB03：[Doctor API](../apps/api/src/agentbox_api/doctor.py)；[CLI](../apps/cli/src/agentbox_cli/main.py) `status/doctor`；[Installer diagnostics](../installer/src/agentbox_installer/diagnostics.py)；[API tests](../tests/unit/test_api.py)、[diagnostics tests](../tests/unit/test_diagnostics.py)。主机范围见 [平台支持](PLATFORM_SUPPORT.md)，不包含 R12。
- AB04：[Project/Job表](../packages/agentbox-core/src/agentbox_core/models.py)；[JobService](../packages/agentbox-core/src/agentbox_core/jobs.py) `recover_expired/claim_next`；[Worker](../apps/worker/src/agentbox_worker/main.py)；[测试](../tests/unit/test_jobs.py)。
- AB05：[WAW表](../packages/agentbox-core/src/agentbox_core/waw_models.py)；[WorkspaceSessionService](../packages/agentbox-core/src/agentbox_core/waw_sessions.py)；[Workspace API](../apps/api/src/agentbox_api/workspaces.py)；[session tests](../tests/unit/test_waw_sessions.py)。
- AB06：[Auth](../apps/api/src/agentbox_api/auth.py)；[CLI local TTY](../apps/cli/src/agentbox_cli/main.py) `_admin_init`；[Auth tests](../tests/integration/test_auth_api.py)。
- AB07：[Git](../packages/agentbox-runtime/src/agentbox_runtime/git.py) `GitAdapter`；[GitHub](../packages/agentbox-runtime/src/agentbox_runtime/github.py)；[Project routes](../apps/api/src/agentbox_api/projects.py)；[adapter tests](../tests/unit/test_git_adapters.py)。
- AB08：[Provider表](../packages/agentbox-core/src/agentbox_core/provider_models.py)；[能力协议](../packages/agentbox-protocol/src/agentbox_protocol/runtime_capabilities.py)；[Secret store](../packages/agentbox-runtime/src/agentbox_runtime/secret_store.py)；[Provider approval](../packages/agentbox-core/src/agentbox_core/approvals.py)。对应测试：[Provider core](../tests/unit/test_provider_core.py)、[Provider security](../tests/unit/test_provider_core_security.py)、[capability service](../tests/unit/test_runtime_capability_service.py)、[capability security](../tests/unit/test_runtime_capability_security.py)、[Secret store security](../tests/unit/test_secret_store_security.py)、[Provider approval](../tests/unit/test_phase11_approval.py)。这些测试不证明生产凭据、通用 Discovery/Adopt 或 Agent Approval 可用。
- AB09：[API bootstrap](../apps/api/src/agentbox_api/main.py) `create_app` 默认 WAW disabled；[Runtime main](../packages/agentbox-runtime/src/agentbox_runtime/server.py)；[Runtime composition](../packages/agentbox-runtime/src/agentbox_runtime/waw_runtime_application.py)。对应测试：[API composition](../tests/unit/test_waw_api_application.py)、[Runtime composition](../tests/unit/test_waw_runtime_application.py)、[bootstrap](../tests/unit/test_waw_bootstrap.py)、[Linux native](../tests/native/test_waw_native_linux.py)。真实主机尚缺 [R12 bootstrap 清单](WORKSTATION_EVOLUTION.md#r12-production-bootstrap-and-host-gates) 和 [host gate](WAW1_HOST_GATE_CHECKLIST.md) 证据；Linux CI 不替代目标主机资格。
- AB10：[现有controller](../apps/web/src/features/workspace/wawBrowserController.ts)；[attachment hook](../apps/web/src/features/workspace/useWAWBrowserAttachment.ts)；[R11 contract](WAW_R11_CONTROLLER_COMPOSITION.md)；[native tests](../tests/native/test_waw_native_linux.py)。
- AB11：[页面路由](../apps/web/src/App.tsx)；[Dashboard](../apps/web/src/pages/DashboardPage.tsx)；[Logs](../apps/web/src/pages/LogsPage.tsx)；[公开产品范围](MVP_SCOPE.md)；[Phase7 Git契约](GIT_INTEGRATION.md)。这里证明现有入口与范围；未实现的 Files/Diff、Task、Attention 和业务指标没有对应产品验收测试，不能由现有页面 CI 推导为已覆盖。
- AB12：[status hook](../apps/web/src/features/workspace/useWorkspaceStatus.ts)；[controller hook](../apps/web/src/features/workspace/useWorkspaceController.ts)；[status tests](../apps/web/src/features/workspace/useWorkspaceStatus.test.tsx)、[controller tests](../apps/web/src/features/workspace/useWorkspaceController.test.tsx)、[page tests](../apps/web/src/pages/WorkspacePage.test.tsx)；[return E2E](../apps/web/e2e/workspace-return.spec.ts)、[RC9 E2E](../apps/web/e2e/rc9-workspace.spec.ts)。
- AB13：[Security](SECURITY.md)；[Helper协议](../helper/src/agentbox_helper/protocol.py)；[Release verifier](../installer/src/agentbox_installer/artifact.py)；[CI gate](../.github/workflows/release-candidate.yml)；[candidate/gate tests](../tests/unit/test_release_candidate.py)、[install-script tests](../tests/unit/test_release_install_script.py)。包测试不证明发布者签名、生产安装或真实 Secret/主机准入。

## 成熟度与测量

目前不授予整站 Level 2/3。Level 0 管理能力有证据，Level 1 的新交互会话尚缺
R12；Level 2 的真实开发与代码变化检查也未闭合。以下只定义测量方法，不预填结果：

1. 首次工作流：在授权目标记录从安装到第一条收到 ACK 的任务输入所需动作与阻断。
2. 返回工作区：本轮确定性测试计数 GET/POST 和失效后可操作状态；不推算线上成功率。
3. 故障恢复：每种注入记录 generation/ownership 分类、是否重复副作用、用户下一动作。
4. R12 再测启动/回连时延、空闲/活跃RSS/CPU、每日SSH次数和升级恢复，写明样本与版本。
5. 竞品只做 D/C/T 研究；无同环境运行，因此无跨项目性能或“更成熟”排名。
