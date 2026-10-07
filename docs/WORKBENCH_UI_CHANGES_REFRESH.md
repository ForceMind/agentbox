# A2 UI 接续：既有 Changes 页面与 staged reader 呈现

## 基线与同一版本范围

2026-10-07 09:34 UTC，Workspace [PR156](https://github.com/ForceMind/agentbox/pull/156)
正常合并后的 main `5ca2f1d348e03796c317d9c7c66f2582f240490f` 六套首轮全部成功，
tree `58679a774e6dfc8786a796091dcac33f330ae711` 与合格头01af67相同。
Backend实际3.11.16/3.12.14/3.13.16各5375 passed/88 skipped；Frontend1771+6；
E2E344 passed/94规定skip、无failed/flaky，26checks为23success/3规定skip。
合格头实际3.13.15通过另记，历史READY间歇问题仍开放，不称为根因修复。

本批继续同一已批准完整UI重设计，仅迁移现有
`/projects/:projectId/changes`。依据[原整合计划](project/WORKBENCH_INTEGRATION_PLAN.md)、
[A3 reader合同](WORKBENCH_A3_CHANGES_READER.md)、
[native合同](WORKBENCH_A3_NATIVE_TRANSPORT.md)与
[统一diff呈现合同](WORKBENCH_CHANGES_UNIFIED_DIFF.md)。沿用暖白/墨色/琥珀tokens；
这是可回退实施选择，不冒称Owner指定色板。分支 `feat/ui-changes-reader-20261007`。

页面范围为原metadata路径树与显式staged reader：目录折叠、路径/原路径/类型、
真实已显示/总数、Refresh/Load more、Read/Cancel/Clear、unified/raw/wrap。
调整信息层级、桌面双区与手机纵向布局；把page和VerifiedPatchView硬编码文案
迁入typed en/zh-CN catalog。完成时间继续明确为浏览器读取完成时间，不能变成
仓库观察时间。技术identifiers、原始路径/代码/hunk/坐标不翻译。

不新增Files、搜索、编辑、stage/commit、复制/下载、统计、读取入口、Provider配置
或Runtime能力。当前版本号保持0.3.0-rc.31；内部PR不是新的产品发行。
完整UI范围与剩余页面集中在[逐版本计划](project/RELEASE_ITERATION_PLAN.md)，
本卡不另立功能路线图，不改变真实host、账号、Secret、发布和部署边界。

## 必须保留的行为

- metadata不授予内容身份或权限。仅staged added/modified/deleted的明确按钮
  激活原reader；hover/focus/折叠/渲染不触发读取。保留fresh observation、nonce、
  selector和Project/session绑定，不向transport增加path/command。
- 缺少独立A3 trust时仍unavailable；不由WAW或metadata成功推导可读，不注入
  生产替身。原App/useNativeA3Changes/hook/controller/crypto/parser/API全部保留。
- 完整END验证后才挂载原VerifiedPatchView，保持唯一正文owner。Cancel、新选择、
  Refresh/Load more、metadata变化、route/session/auth、hide/freeze/pagehide/offline、
  trust/disconnect/expiry继续取消清除，晚到结果不复活。raw/wrap/locale/布局变化
  不续期、不重读；无新polling/prefetch/retry/replay。原≤50ms安全currentness/expiry
  守卫及native trust监视不属于可删除的轮询。
- 原metadata、staged observation、content/crypto和unified模型全部资源上限不动。
  解析失败保持完整原文fallback，不截断、不显示部分结果、不伪称空diff。
- path保留visibleGitPath与OpaqueUserValue，正文为inert React text。保留header/
  坐标不证明源身份的说明、敏感信息警告、文字化增删语义与可聚焦有界滚动。
  `.diff-region`定位容器及page width/height边界不退回已知巨型空白缺陷。

## 验证与交付

保留全部既有page/controller/parser/native断言。原测试中英文page混用中文reader
的假设改为显式locale，不能用宽泛test-id代替accessible-name证明。补齐双语九种
reader状态、fallback/警告/时间语义、纯呈现操作无读取或TTL续期、分页先清正文、
长inert路径、键盘focus与44px控件。安全行为若出现真实RED，先保存最小证据与
独立有界修复卡，不把新业务/安全合同混入布局。

新`ui-changes-*.png`仅为合成metadata/unavailable，包含双语×五宽度×light/dark
ready矩阵、异常/分页状态及两张正常名称展示图；固定route/API/capture门禁排除
补丁正文、输入、密码和server-prose。原A3两个spec已有明确获准的synthetic patch
截图，保留其既有边界；不扩大真实内容留存，不开启自动失败截图/trace/video。
正文双语与布局继续用原合成reader/native fixtures的DOM/geometry断言证明。

小稳定源码提交、Draft PR、适用本地检查、独立source/像素审查、新exact-head六套、
正常merge/read-back及exact-main六套分别记录。当前只完成合同和只读评估，尚未
取得本卡实现、实际浏览器或CI资格；不能借用PR156结果。

## 09:51 UTC 源码、回归与本地质量检查点

产品五文件已实现：metadata/reader双区、typed双语、原生44px控件、dark/forced-colors。
独立AST/source审查确认page pre-render owner/hooks/effects字节不变，page5个与view3个
callback表达式逐一保持。完整正文仍只在原completed owner内挂载，无安全/能力变化。
产品remote56efb6e与65项focused回归remotefb5321已分提交保存；原所有断言保持。

新增metadata-only spec静态70注册（49执行/21规定重复skip）、42PNG；22份实际fixture
response通过production closed decoder。既有native fixture仅可选browser locale，
默认中文不变；新增一个英文DOM/geometry用例（双端共2），无capture。原12个native
测试定义经AST逐一保留。双栏高度上界改为workbench正常流bottom+原128px，仍检测
脱离定位容器的辅助标签造成页面巨大空白；内部滚动、width、timeouts/预算均保持。

首轮全Web1798 passed/2 failed，失败仅旧App.a3Native测试在英文App中仍断言中文。
修正四处精确文案并增加lang=en，原bootstrap/read/socket等安全断言不变；focused2
转绿。独立审查另发现新spec中文folder全角冒号不匹配原产品ASCII冒号，已只修期望，
保留exact locator。二者都是测试语言假设修正，不称产品RED→GREEN。

最终本地1800 Web+6 extension、全lint/typecheck/format/build、768 doc links与diff-check
均exit0；既有Vite大chunk提示保留。新spec/native差异独立source复审CLEAR。实际
浏览器、42新图及新的exact-head六套仍待；没有本地native/browser执行或通过声明。
[Draft PR157](https://github.com/ForceMind/agentbox/pull/157)按正常追加历史资格化，
不重跑旧头、不把本地pure测试或旧PR156绿灯当作本批浏览器/权限证明。

## 10:07 UTC 旧browser布局断言适配

早期source checkpoint fb5321的官方E2E37602974890/job112731569203终态为
335 passed/94规定skip/9 failed。七项native desktop失败是旧reader-bottom高度
假设，不含合法较长metadata列；该断言已在140a34按前述正常流workbench边界修正。
另两项authenticated-web desktop/phone失败是旧card.y>note.bottom；本次设计已将
metadata说明放入card，因此旧断言与合法DOM结构矛盾。

仅把后者改为note/tree均包含在card内、tree位于note之后，无裁切/遮挡；保持原
page width、sidebar、无正文/动作、fold/pagination等断言和所有timeout/预算。
不改产品或放宽权限。targeted lint/format/TypeScript/diff-check通过，原spec静态
仍72项；首次collection缺既有测试环境变量未成功，随后以纯static占位值收集通过，
未运行browser。修正方案独立source审查CLEAR；实际浏览器结果仍待。

140a34头当时五套首轮成功，Backend实际3.11.17/3.12.14/3.13.15各5375/88，
Frontend1800+6；E2E仍在运行，不能称六套或整批合格。原失败保留，后继正常
追加test/docs提交；不手动重跑旧头，不借布局调整掩盖任何内容/安全断言。
