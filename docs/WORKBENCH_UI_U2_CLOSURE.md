# rc31 U2 既有 UI 跨页验收收口

## 范围和退出条件

本记录接续 [既有页面清单](project/RELEASE_ITERATION_PLAN.md)、
[Kebui UI 计划 U2](project/KEBUI_UI_DELIVERY_PLAN.md) 与
[Login/404 卡](WORKBENCH_UI_ENTRY_REFRESH.md)，不建立另一套功能路线。
PR148/153/156/157/158/160 已完成各自页面软件资格；PR161 的 Login/404 及下列
少量 test-only 收口仍待最终组合 head、真实 browser/原图、正常 merge 与 exact-main。

只在所有既有正式路由和本表没有未标注缺项后，声明“rc31 既有 UI 的 U2 呈现与
跨页软件验收闭环”。不称全部 A2/S02、未来 U1 原型或首个可用 RC 已交付。
默认未配置能力、Logs 尚未实现预览、Settings 六项只读、Doctor control-plane READY
与 Agent/Remote 状态区分继续保持。历史 native READY 间歇问题开放，不称根因修复。

## 已有回归映射

本表是源码与当前回归的映射，不把静态读取写成新一次执行；最终 exact-head E2E /
Frontend 日志才是本候选执行证据。每个套件原有 fixture/预算/断言和截图边界保持。

| 需要闭合的行为 | 复用来源 | 具体边界 |
| --- | --- | --- |
| 页面导航与 Back/Forward | [shell](../apps/web/e2e/ui-shell.spec.ts)、[detail/attention](../apps/web/e2e/ui-detail-attention.spec.ts)、[Workspace](../apps/web/e2e/ui-workspace.spec.ts)、[Changes](../apps/web/e2e/ui-changes.spec.ts)、[admin](../apps/web/e2e/ui-admin-pages.spec.ts)、[entry](../apps/web/e2e/ui-entry-pages.spec.ts) | 实际 App 路由、页面 commit 与 held response owner；沿用零额外 mutation 断言 |
| 标题 | [rc9 helper](../apps/web/e2e/rc9-assertions.ts)、上述页面 suite | 其余直达页已有 title；只补 Attention/Changes 与既有 history 当前标题 |
| 语言和主题 | 各 ui-* 双语言、light/dark、五宽度；[i18n](../apps/web/e2e/i18n.spec.ts) | locale 每个 document 初始化一次，不虚构热切换功能；Entry 加 900/960 边界 |
| mobile、modal、keyboard | shell/admin drawer、Workspace Stop、Agent Pair 与 [dialog focus](../apps/web/src/app/dialogFocus.test.tsx) | 原生 modal、Escape/焦点恢复、Tab/Enter、44px 和几何，不新增 modal authority |
| Session / 401 / logout | [App](../apps/web/src/App.test.tsx)、[admin scope](../apps/web/src/App.adminReadOnlyScope.test.tsx)、[Agent scope](../apps/web/src/App.agentManagementScope.test.tsx)、[auth browser](../apps/web/e2e/agent-management-auth-scope.spec.ts) | A→B 身份重验、旧 Pair/output 不复活，真实 CSRF/401 恢复 |
| offline / hidden / resume | [overview](../apps/web/src/features/overview/WorkOverview.test.tsx)、[Projects](../apps/web/src/features/projects/useProjects.test.tsx)、[Workspace return](../apps/web/e2e/workspace-return.spec.ts)、ui-detail/ui-workspace/ui-changes | 各分域状态失效与显式恢复，不为只读 Doctor 添加通用框架，不重放写入 |
| empty / error / unknown | ui-detail、ui-workspace、ui-changes、ui-agent-management、ui-admin 与 overview | unknown 不冒充 empty；不可用与计划能力明确 |
| sensitive currentness | [management owner](../apps/web/src/features/managementOwnership.test.tsx)、[Workspace controller](../apps/web/src/features/workspace/useWorkspaceController.test.tsx)、[A3 page](../apps/web/src/pages/ProjectChangesPage.a3.test.tsx)、[native A3](../apps/web/e2e/a3-native-changes.spec.ts) | Pair TTL/迟到 clipboard，旧 Session Stop，offline 输入围栏，A3 END/TTL/session/logout/hide 清除 |

## 最小 test-only 追加

源码审计确认 Attention 与 Changes 调用 usePageTitle，已有全局 title 断言没有覆盖这两页。
既有 history 用例主要验证 URL/DOM/owner，还需断言 document.title 跟随当前 route commit，
尤其 Project A→B→Back→Forward 与 404 返回目的地。直接复用 assertRc9Title，
在原 helper 与 history 步骤补精确中英文期望；不导入产品 catalog 当测试期望。

保留原全部 DOM、URL、currentness、mutation、deadline 和 captures，不添加大范围遍历
框架、新测试矩阵或额外截图。该改动与 PR161 同一个候选资格化，避免另拆纯断言版本。
若新断言出现真实 RED，先记录实际错误，再决定最小修复，不能改期望掩盖产品问题。

## 图像与资格记录

PR161 计划 60 新图：48 清洁入口/404、6 清空输入后的公开错误、4 health、2 authenticated
404；已有产品截图保留原批次 identity/source head/digest/实际检查范围。不同 tree 不能借
旧截图，只有明确 source/screenshot 字节证明才继承；不冒称查看 artifact 内所有图片。
此记录时实际 browser、60 图、最终组合 head 六套和 post-main 仍待，不提前标记 PASS。

## 真实可用性与后续工作

U1 参考板、tokens、新 Kebui 高保真/可点击原型仍是独立未交付项；U3 结构化 Chat 与
后续 Task/Files/Memory 需要已有计划规定的合同。U2 没有自动获得这些能力。
真实 Linux host、双 CLI、代表性 PC/手机、trust/Secret、重启/升级/回退尚需相应目标和
实际证据；软件 CI 不能代替。当前不执行 release、deploy、账户登录或敏感权限操作。
