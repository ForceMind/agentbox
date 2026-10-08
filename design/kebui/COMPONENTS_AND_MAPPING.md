# Design system and product mapping

## Tokens / components

| 类别                     | 本批设计                                                                                                     |
| ------------------------ | ------------------------------------------------------------------------------------------------------------ |
| 排版                     | 系统中文/英文字体回退；正文 15px、标题 30px；代码使用系统等宽。无外部字体                                    |
| 间距                     | 4/8/12/16/24/32/48px；布局用区域和留白而不是全部嵌套卡片                                                     |
| 色彩                     | 暖白/墨色基础，探索性墨绿强调；success/warning/danger 独立角色且配文字。暗色独立 token                       |
| 圆角                     | 控件 8px、卡片 14px、对话 18px；一致家族                                                                     |
| 身份                     | 抽象 k 标记、Cx/Cl 缩写。不是最终 Logo，也不复制第三方头像                                                   |
| 动效                     | 没有自动进度动画或思考百分比；reduced-motion 规则                                                            |
| 密度                     | 桌面约254px导航、可读主区、310px上下文面板；1100px以下先隐藏辅助面板；767px以下单主区                        |
| 可访问性设计             | 44px 最小按钮高度、focus-visible、skip link、原生 dialog、状态文本、aria-live、lang；真实浏览器/读屏资格待验 |
| ConversationRow          | 身份、标题、Project、进展、明确待确认/执行中/未读；固定顺序，搜索仅三条合成数据                              |
| ContextBar / AgentPicker | 显式 Project 与 Codex/Claude Code；换范围开始新演示并清空旧授权                                              |
| Composer                 | Enter换行、Ctrl/Cmd+Enter发送、IME抑制、空输入提醒、已接受/失败/未知区别、重复发送抑制                       |
| WorkStageCard            | 来源为明示 fixture，不由 CLI/Job 判断成功；手动推进，不伪造进度百分比                                        |
| ApprovalCard             | owner/Project/request/revision/有效性/目标/后果/申请者；拒绝、过期、未知与显式回读                           |
| ResultCard / Inspector   | 点击后才渲染合成正文；失效清除；inert text；返回原对话位置                                                   |
| RecoveryBanner           | UNKNOWN、失败、重新核验、无回放、精确目标停止与取消；detach/interrupt/cancel/Stop分开                        |

## 六组核心画面

| 组         | 可打开入口              | 桌面 / 手机 / 主题       | 状态                                                       |
| ---------- | ----------------------- | ------------------------ | ---------------------------------------------------------- |
| 工作入口   | `index.html#home`       | 共用响应式浅深主题       | 三会话、待确认、执行中、未读、搜索空态                     |
| 对话执行   | `#work`                 | 同上                     | idle/accepted/running/succeeded/failed/unknown/interrupted |
| 待审批     | `#approval`             | 同上                     | pending/approved/rejected/expired/unknown                  |
| 结果检查   | `#results` / `#changes` | 桌面辅助详情，手机单主区 | 未读取/已读取/失效/读取失败/未知                           |
| Agent/环境 | `#agents`               | 响应式卡片               | 合成连接、真实认证UNKNOWN、真实host未验                    |
| 手机恢复   | `#recovery`             | 桌面与手机同一明确状态面 | UNKNOWN/核验失败/运行回读/exact Stop回读                   |

上述是已实现的原型呈现，不是六组已通过浏览器/像素验收。五宽几何脚本待 CI 真正运行。

## 全页面与生产映射

| 页面族             | 原型状态                                  | 当前 source 对应 / 后续合同                        | 未实现边界                                  |
| ------------------ | ----------------------------------------- | -------------------------------------------------- | ------------------------------------------- |
| 登录/初始化        | 合成登录入口、初始化说明、通用失败场景    | `pages/LoginPage.tsx`                              | 不输入凭据、不认证、不初始化host            |
| 工作概览/对话入口  | 合成会话列表与搜索                        | `pages/DashboardPage.tsx` 是既有 Job 概览；未来 K2 | 不把 Job 当 Task；不替换 dashboard          |
| 项目列表/详情      | 两个fixture、选项目、创建/clone预演与取消 | `ProjectsPage.tsx` / `ProjectDetailPage.tsx`       | 不访问目录、不clone仓库                     |
| 现有Workspace      | CLI说明、Detach/Reconnect/exact Stop演示  | `WorkspacePage.tsx` / `useWorkspaceController`     | 无终端或命令执行；真实 exact Stop资格不外推 |
| Changes            | 合成diff、原文、准入与失效                | `ProjectChangesPage.tsx` / `useNativeA3Changes`    | 不接 A3 或读取真实路径                      |
| Codex/Claude 管理  | 一页内分别展示两者身份与资格              | `CodexPage.tsx` / `ClaudePage.tsx`                 | 无安装/登录/Provider/Remote接线             |
| Doctor             | 分层UNKNOWN与演示检查                     | `DoctorPage.tsx`                                   | Control Plane示例READY不代表Runtime资格     |
| Logs               | 规划说明                                  | `LogsPage.tsx`                                     | 无日志流、下载或读取                        |
| Settings           | 本页主题/语言/字号；身份失效              | `SettingsPage.tsx`                                 | 不新增生产设置写入                          |
| 404/无权限/离线    | 独立入口、回退路径、正文清除              | `NotFoundPage.tsx` / guards；全局生命周期合同      | 不创建真实账户或权限                        |
| 对话/任务与审批    | 三旅程fixture状态机                       | K2–K3 / S03/WEV                                    | 无真实turn、Task、审批与TTL；不解析TUI      |
| Files/Artifacts    | 不可用原因与导航设计                      | S02/S04 / K3/K6                                    | 没有正文读取/预览能力                       |
| 历史与记忆         | 规划边界说明                              | K6                                                 | 无持久化、删除或跨设备恢复                  |
| Agent交接/策略路由 | 规划边界说明                              | K4–K5                                              | 无Agent切换执行、无路由策略                 |
| 人与Agent协作      | 规划边界说明                              | K7                                                 | 无邀请、共享、指派或权限写入                |

最后五行的未来能力只出现于“设计画面目录”，不是生产可用导航的建议。所有生产接线必须另取得对应合同/来源/身份/恢复/权限证据。
