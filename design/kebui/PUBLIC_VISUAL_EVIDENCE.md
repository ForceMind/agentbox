# Kebui U0 公开视觉取证补完

观察日期：2026-10-08 03:46–03:49 UTC。方法：只读官方网页、GitHub API/固定 SHA 原文件；下载公开图像到仓库外审查目录，逐图使用 `view_image` 实际查看。HAPI 官方 README 视频仅截取并查看 12s、26s 两帧，未声称观看全部视频。没有登录、安装或运行上游产品，没有复制上游实现。

本轮结论：五个公开参考均已取得并实际查看公开像素证据，不能再笼统标为“截图 UNKNOWN”。证据分为营销合成图、官方仓库 QA/PR 截图与组件预览、README 产品截图和公开视频帧；它们都不是本轮真实功能实测，也不证明截图来自当前发布版。当前仓库 SHA 固定的是文件所在版本，非拍摄时应用版本。

## 1. 官方身份、固定来源与版本边界

| 参考     | 官方入口和固定 README                                                                                                                                    | 本轮固定仓库 SHA                                                               | 可核对的版本/许可证边界                                                                                                       |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| cindy    | [官网](https://www.cindy.app/)；[固定 README](https://github.com/makecindy/cindy/blob/c940ab1903e16f24b249a06857afb27632693237/README.md)                | `c940ab1903e16f24b249a06857afb27632693237`（commit 时间 2026-10-08T01:59:57Z） | 根 package.json 无 version；Apache-2.0。品牌/人物图及截图内第三方内容不因根 LICENSE 自动获得无限再分发权。                    |
| paseo    | [官网](https://paseo.sh/)；[固定 README](https://github.com/getpaseo/paseo/blob/99fc204c55c8c1666477282eeba562ba87a3135f/README.md)                      | `99fc204c55c8c1666477282eeba562ba87a3135f`（commit 时间 2026-10-07T23:01:21Z） | 当前根 package.json 为 0.11.1；Apache-2.0。当前 mobile-mockup 内 About 显示 v0.1.34，记录为截图内版本文字，不等同当前包版本。 |
| hapi     | [官网](https://hapi.run/)；[固定 README](https://github.com/tiann/hapi/blob/99cd3d4172fb49f893b62dff39239fa85c5f6275/README.md)                          | `99cd3d4172fb49f893b62dff39239fa85c5f6275`（commit 时间 2026-10-05T09:14:11Z） | 根 package.json 无 version；根 LICENSE 为 AGPL v3，既有官方 FAQ 指明 AGPL-3.0-only。只取设计观察，不移植实现。                |
| cloudcli | [官网](https://cloudcli.ai/open-source)；[固定 README](https://github.com/siteboon/claudecodeui/blob/5fd3de63573ce5e50496da177bdfff5b9110d945/README.md) | `5fd3de63573ce5e50496da177bdfff5b9110d945`（commit 时间 2026-10-07T18:25:40Z） | 根 package.json 为 1.37.3，license 字段 AGPL-3.0-or-later；根 LICENSE 已取。                                                  |
| yep      | [官网](https://yepanywhere.com/)；[固定 README](https://github.com/kzahel/yepanywhere/blob/9858e08db82ca3a365e4520299b3ccb81fe7abce/README.md)           | `9858e08db82ca3a365e4520299b3ccb81fe7abce`（commit 时间 2026-10-08T03:30:41Z） | 根 package.json 为 0.7.0；根 LICENSE 为 MIT。版本是仓库文件声明，不保证图片拍摄版。                                           |

### Paseo 历史迁移源保持不变

原迁移固定 SHA 仍为 `30178c4f58b67f8472901356e1484022bd835de0`；本轮重新下载其 [package.json](https://raw.githubusercontent.com/getpaseo/paseo/30178c4f58b67f8472901356e1484022bd835de0/package.json)，version 确认为 `0.10.0-beta.1`。重新下载 [LICENSE](https://raw.githubusercontent.com/getpaseo/paseo/30178c4f58b67f8472901356e1484022bd835de0/LICENSE)，SHA-256 为 `79d5aedce6aa0adc547336dc1bd34c5cc9308ba110fac7079ed97515ee573ad3`，与既有 manifest 一致。

本轮下述 Paseo 图像固定在 **当前观察 SHA `99fc204…`**，不能倒填为旧 `30178…` 的功能或截图证据。没有变更第三方源码固定版本或迁移许可记录。

## 2. 五项视觉矩阵：看到了什么，采用什么，拒绝什么

图片 ID 的精确公开 URL、尺寸与哈希见第 4 节。表格只描述可见像素，不将截图内文字当成经过验证的事实。

| 参考 / 已查看图片   | 实际像素观察                                                                                                                                                                                                                                                                                                               | 采用并映射 Kebui 六核心组                                                                                                                                     | 明确不采用 / 证据局限                                                                                                                                                         |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cindy：C1–C4        | C1 是深底、红白标题与人物/猫的品牌海报，无产品工作区。C2 手机深色抽屉中明确写 Visual Mock User，Sessions/Teammates 分段，Search、Device Management、Settings 与 Sign Out 分区。C3 浅深色结果组件预览将任务标题、已完成/已停止、查看结果与正文分层。C4 手机宽度的浅深组件预览显示已完成与已超时、查看详情及 TIMEOUT 原因。  | 首页与 Agent/环境详情：工作导航与设备/系统入口分区；结果检查：标题+状态+查看结果的紧凑 ResultCard；手机恢复：失败详情可展开、无结果要明确说明。               | 不复制角色/品牌或 Mock User 信息；不拿品牌图证明 UI；不把官方组件预览当已发布整页；不把“没有文字结果”当执行成功，不引入新 Teammate/账户体系。                                 |
| Paseo：P1–P2        | P1 桌面深色三列：左侧仓库/分支、中央对话/工具行、右侧 Changes/Files diff；顶部任务与仓库上下文，底部模型与输入区；叠加手机只保留单主区。P2 四手机宣传拼图显示会话树、Hosts/主题设置、全屏 Changes 与终端。                                                                                                                 | 首页：Project 内工作分组；对话执行：上下文持续可见；结果检查：桌面并排 Inspector、手机单独检查页；Agent/环境详情：host 名称与连接状态可见。                   | 不复制终端与自由 shell、worktree、多 host 连接或 PR 写入口；不把彩色状态点单独作为状态文字；不由跨端拼图推断断线恢复或并行可靠性。营销图不是本轮设备测试。                    |
| HAPI：H1–H4         | H1 手机顶部会话标题、codex 字标与模型，底部在线文字/点、上下文和输入区，红圈是原 PR 注记。H2 手机 Terminal 卡显示输入/结果、exit 0、截断预览提示；内容明显过长且部分状态换行，文件名标 regression。H3/H4 是 README 视频 12s/26s 帧：左侧终端与右侧手机同类内容；26s 手机有 Switched to remote / Switched to local 系统行。 | 对话执行：执行者+模型不可只靠头像；结果检查：工具摘要/详情与截断提示；手机恢复：连接/控制权变化用独立系统事件，不混成助手正文。                               | H2 作为不采用的拥挤反例，不照搬长终端卡；不照搬 Yolo/权限模式；仅从帧观察“切换提示的呈现”，不声称测通无损接续、加密、通知或实际重连。                                         |
| CloudCLI：L1–L4     | L1 浅色桌面左列项目/会话，主区 Chat/Shell/Files，工具输入参数/结果卡和固定底部 composer。L2 手机隐藏会话列，顶部会话与仓库，消息内 inline diff，底部六项导航。L3 新会话用 provider 卡片、选中边框/对勾与模型选择。L4 Tools Settings 将危险跳过权限选项放警告区，允许工具列表与保存按钮分开。                               | 首页：会话属于项目；对话执行：工具与消息层次；Agent/环境详情：AgentPicker 显式选中与模型；结果检查：短摘要进入详细 diff。                                     | 不引入 Shell/Git 写入、插件/允许工具设置；不照搬跳过权限选项；不复制六项手机底栏（Kebui 保持工作任务主线）；不据截图假设可达键盘/读屏或真实审批已测。                         |
| Yep Anywhere：Y1–Y5 | Y1 手机暗色审批在下方明确写 Allow Write pages.yml?，分 Yes、Yes and don’t ask again、No 及替代输入。Y2 桌面左侧 Starred/近期会话、右侧 inline diff 与工具 IN/OUT，底部恢复输入。Y3 手机会话顶部项目/标题/模型，工具时间线与底部 composer。Y4 新会话分输入、附件、provider、model。Y5 手机 diff 是单列，长代码在右边裁切。  | 待审批：操作与对象紧贴决策；首页：近期/重点工作组织；对话执行：持续上下文；结果检查：手机单列、文件标题与变更可检查；Agent/环境详情：provider 与 model 分离。 | 不照搬“一直允许”语义，不扩大 scope/revision 审批；不把消息恢复输入等同网络恢复；长代码裁切作为反例，Kebui 须提供可操作的横滚/展开；不由手机浏览器截图宣称 native app 已发布。 |

## 3. 对六核心组的明确采用/不采用判定

| Kebui 核心组   | 视觉参考                      | 本轮可落到现有设计的判定                                                                                 | 依然需要 Kebui 自身验证                                                                                    |
| -------------- | ----------------------------- | -------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| 工作/会话首页  | P1/P2、L1、Y2、C2             | 采用 Project→工作/会话层级，工作导航与系统/设备入口分区；待处理状态必须文字化，不仅靠颜色。              | 桌面/手机真实路由与空/长列表、键盘焦点；参考图不证明待处理排序实现。                                       |
| 对话执行       | P1、H1/H3、L1/L2、Y3          | 标题/Project/执行者持续可见；工具事件用短摘要，正文与系统状态分开；底部输入区不盖内容。                  | Stop 必须 exact target；长流式结果、焦点与滚动行为。                                                       |
| 待审批         | Y1，L4 为风险反例             | 审批显示具体操作+对象，拒绝/替代路径可见；保留 Kebui scope/revision 与过期禁止批准，不提供静默扩大授权。 | 真实批准/拒绝/过期、重复提交、手机大字。                                                                   |
| 结果检查       | P1/P2、C3/C4、H2、L2、Y2/Y5   | 桌面按需 Inspector、手机单主区；标题+结果状态+详情；摘要截断必须明示且能查完整内容。                     | 文件/结果真实读取、长路径与横滚、无结果和失败分开。                                                        |
| Agent/环境详情 | P2、H1、L3、Y4、C2            | Agent 与 model 可辨、host/Project 可定位；选中态除颜色外有文字/对勾；不新增上游连接/权限能力。           | 已授权环境数据、能力差异、不可用原因，不假装互换。                                                         |
| 手机恢复       | H4、C4、Y3 仅提供视觉局部依据 | 连接/切换/超时作为独立系统事件；恢复前显示上下文、最后可信状态与下一步；不自动重放。                     | **本轮公开图中无经验证的断网→重连全流程。** 需要 Kebui 自身恢复状态/行为验证，不能将厂商演示当可靠性证明。 |

## 4. 固定图片/视频证据登记

所有图像仅临时下载审查，未添加到 Kebui 仓库。这里使用公开源链接，不内嵌或重新发布第三方像素；SHA-256 固定本轮实际观察字节。根开源许可证已读取，但未完成每张图中商标、人物、聊天/代码等独立权利审计，故不授权拷贝图片进产品或发布资产。

- **C1** [cindy-hero-en.webp](https://raw.githubusercontent.com/makecindy/cindy/c940ab1903e16f24b249a06857afb27632693237/.github/assets/hero-en.webp)；2400×904；SHA-256 `4ab5b2aa02356cf6c609f1b1124d47cf09116a5fd4ae22ca5cbf7558fa222637`。
- **C2** [cindy-android-drawer-dark.png](https://raw.githubusercontent.com/makecindy/cindy/c940ab1903e16f24b249a06857afb27632693237/docs/assets/mobile-companion-focus/android-drawer-dark.png)；1080×2400；SHA-256 `297c2f1ebcb2c2cc6777f87295d499cc3e9587d95faf0174296c025c992c468e`。
- **C3** [cindy-desktop-result-receipts.png](https://raw.githubusercontent.com/makecindy/cindy/c940ab1903e16f24b249a06857afb27632693237/docs/pr-assets/teammate-reply-results/desktop-result-receipts.png)；850×780；SHA-256 `9fe09a8950f4c1b7c110b40ab450b0d9f9585722f5f8285974132893d07ea15f`。
- **C4** [cindy-mobile-failure-details.png](https://raw.githubusercontent.com/makecindy/cindy/c940ab1903e16f24b249a06857afb27632693237/docs/pr-assets/teammate-reply-results/mobile-failure-details.png)；800×720；SHA-256 `f619d3a4aa7873448d00df8a975bf77c09228dec016636acb96f701aa3e48f6d`。
- **P1** [paseo-hero-mockup.png](https://raw.githubusercontent.com/getpaseo/paseo/99fc204c55c8c1666477282eeba562ba87a3135f/packages/website/public/hero-mockup.png)；2048×1233；SHA-256 `f5bbcf9766d3abb96bfe98dcdb1a5ce4979937a2fe9de47b0307e0861e8502c3`。
- **P2** [paseo-mobile-mockup.png](https://raw.githubusercontent.com/getpaseo/paseo/99fc204c55c8c1666477282eeba562ba87a3135f/packages/website/public/mobile-mockup.png)；2048×1239；SHA-256 `2b67e0152479eb3d7be1a25497f2aff2457322090f1f0e26c7a937de876df4d9`。
- **H1** [hapi-pr-agent-flavor-icons-codex.jpg](https://raw.githubusercontent.com/tiann/hapi/99cd3d4172fb49f893b62dff39239fa85c5f6275/.github/pr-assets/pr-agent-flavor-icons-codex.jpg)；1264×2800；SHA-256 `a26a2e4545afc5d52fffd989c706f54d0251ee9c0dca12b5e729dcc4cd8f5181`。
- **H2** [hapi-pr-601-mobile-terminal-card-regression.jpg](https://raw.githubusercontent.com/tiann/hapi/99cd3d4172fb49f893b62dff39239fa85c5f6275/.github/pr-assets/pr-601-mobile-terminal-card-regression.jpg)；1240×2772；SHA-256 `91ddbb9de06986e11c49de194764171676058091b59215638e8be204adf81d9b`。
- **H3** [官方 README 视频 @12s 抽帧](https://github.com/user-attachments/assets/38230353-94c6-4dbe-9c29-b2a2cc457546)；3840×2156；SHA-256 `db6393a8517e42671a25e54ba7215062dd498a41224213467013ca90c7b61dba`。
- **H4** [官方 README 视频 @26s 抽帧](https://github.com/user-attachments/assets/38230353-94c6-4dbe-9c29-b2a2cc457546)；3840×2156；SHA-256 `fe2bc3972d42948e1e7e81c89830030ffd42336a05cfc4b45523c914260d1751`。
- **L1** [cloudcli-desktop-main.png](https://raw.githubusercontent.com/siteboon/claudecodeui/5fd3de63573ce5e50496da177bdfff5b9110d945/public/screenshots/desktop-main.png)；2550×1644；SHA-256 `ba702a2674b09b4082887932175a828df6abe6ccdd94101ec8e99e4abcab044e`。
- **L2** [cloudcli-mobile-chat.png](https://raw.githubusercontent.com/siteboon/claudecodeui/5fd3de63573ce5e50496da177bdfff5b9110d945/public/screenshots/mobile-chat.png)；984×1576；SHA-256 `6829f3197d0eadba01fc21f90cd7eed1a8ae25ed354d43110fc5595657e4fd5d`。
- **L3** [cloudcli-cli-selection.png](https://raw.githubusercontent.com/siteboon/claudecodeui/5fd3de63573ce5e50496da177bdfff5b9110d945/public/screenshots/cli-selection.png)；984×1576；SHA-256 `4e7077caadc54559785e5a0b4b8eefb5e83eb0ce24b5a017fd1e74a79d5f172a`。
- **L4** [cloudcli-tools-modal.png](https://raw.githubusercontent.com/siteboon/claudecodeui/5fd3de63573ce5e50496da177bdfff5b9110d945/public/screenshots/tools-modal.png)；2465×1568；SHA-256 `d325a2d2af2a193c4a584ef5bc4b44039c5c42c0ba846fff58202c031f13f892`。
- **Y1** [yep-approval.png](https://raw.githubusercontent.com/kzahel/yepanywhere/9858e08db82ca3a365e4520299b3ccb81fe7abce/site/public/screenshots/approval.png)；1080×2424；SHA-256 `611953d784674575e1e68f4a67ed3b25cc747b3330a0aca9e985a458de012cda`。
- **Y2** [yep-desktop-diff.png](https://raw.githubusercontent.com/kzahel/yepanywhere/9858e08db82ca3a365e4520299b3ccb81fe7abce/site/public/screenshots/desktop-diff.png)；2834×2496；SHA-256 `f5e2331cb04a272583ce6bcc3f782bc84e2da2677c3008ec87a861aade5d4e59`。
- **Y3** [yep-session-view.png](https://raw.githubusercontent.com/kzahel/yepanywhere/9858e08db82ca3a365e4520299b3ccb81fe7abce/site/public/screenshots/session-view.png)；1080×2424；SHA-256 `d0572a1893abdfffe9d6d58388c74809786c534284804e3222fb3ac536ec76f8`。
- **Y4** [yep-new-session.png](https://raw.githubusercontent.com/kzahel/yepanywhere/9858e08db82ca3a365e4520299b3ccb81fe7abce/site/public/screenshots/new-session.png)；1080×2424；SHA-256 `6c20ebc0ec38b685ca024d4a5a2b594625f836392db9293753ae63a066ed88ea`。
- **Y5** [yep-mobile-diff.png](https://raw.githubusercontent.com/kzahel/yepanywhere/9858e08db82ca3a365e4520299b3ccb81fe7abce/site/public/screenshots/mobile-diff.png)；1080×2424；SHA-256 `e844700a7f74d4afd893a6ef8384832da0cb6638ea9db464bd4a8b83e2067222`。

HAPI 原视频：3840×2156，33.533333 秒，SHA-256 `c9487693d80b348ae7d3c8a8ef3e67a340291246b44b112cb4de31dbf36b75ca`。README 仅将其作为 Demo，无拍摄 commit 说明；视频 URL 不能替代产品版本固定。

## 5. 失败路径、替代路径与完成边界

- Paseo：官方 README 给出的 `https://paseo.sh/hero-mockup.png` 与 `https://paseo.sh/mobile-mockup.png` 本轮均 HTTP 403；随后读取官方仓库固定 tree，定位 `packages/website/public/` 中同名文件并成功取得。未绕过账号/访问控制，使用独立公开仓库资产。
- HAPI：`https://hapi.run/` 本轮 HTTP 403；官方仓库固定 README 成功，Demo 公开附件下载成功并查看两帧；固定仓库 `.github/pr-assets/` 截图也成功。官网 hero 插画虽已下载，但未作为产品 UI 证据。
- Cindy：官网公开 HTML 成功，所列图片主要为品牌人物；README hero 已看但判为不够证明产品 UI。继续检查官方固定 tree，使用明确标注 Mock User/组件预览的公开 QA/PR 资产，降低证据等级而不是伪称生产产品截图。
- CloudCLI、Yep：官方固定 README 路径图像直接成功。像素中的日期、模型、状态、对话内容只是截图内容，不用来宣称当前功能或依赖版本。
- 五项公开参考的来源、固定仓库文件、图片像素、采用/不采用和六组映射已可独立完成；此前“本轮没有看图/截图 UNKNOWN”的结论应保留为历史批次记录，并用本节作为新证据覆盖其当前缺口状态。
- 未完成且不能假填：真实上游产品流程实测、Owner 最终品牌/视觉接受、Kebui 真机/发布资格。这些不是继续寻找公开图像可解决的事项，不阻止现有设计和实现继续推进。
