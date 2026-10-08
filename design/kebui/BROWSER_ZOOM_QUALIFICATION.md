# U1 浏览器 200% 补验

2026-10-08 UTC。当前状态：六页中文浅色原生200%基准通过；两尺寸/双语/浅深候选待验。历史失败保留。

仅补已有 U1 设计验收。基线 main `62c5d5ddadcb74e0d8aa1898b1b490d1314b190b`
的原型 SHA256 为 `fd8d1c491a211a3df44bc2f4a8e80a4152254886896af9a841f4d01b2c1c19f8`。
本批不改 HTML/CSS/交互产品源码，不接真实 Agent/账户/host，不部署、不发布版本。

## 首轮只做六页基准

复用 `.github/workflows/e2e.yml` 的 `kebui-design` job、Chromium、中文字体和
既有七天合成 artifact。使用 headed Chromium / Xvfb，1440×1000 原生窗口、
中文、浅色；通过 X11 原生 Ctrl+0 / Ctrl+= 触发浏览器缩放。
`xvfb-run` 由既有 Playwright 系统依赖提供；仅缺少时安装 Ubuntu 官方 xdotool / ImageMagick。
不新增 npm 依赖、扩展、凭据、CI 权限、job、触发器或门禁。

先验证原生窗口不变、DPR 1→2、布局 CSS viewport 减半、visualViewport.scale=1、
CSS 正文字号/zoom 不变、无 transform 或 large 模式。中间 110/125/150/175/200
步骤也记录实际值。按键无效或校准不符直接失败，不把 viewport 缩小、DPR 模拟、
pinch zoom、CSS zoom/transform 或文本放大替换命名为浏览器200%。

校准成功后逐页：真实滚轮到达、按钮中心及周边命中检查、关键正文可见性和实际点击；
覆盖首页新建/取消、执行结果入口、审批范围/批准回读、显式读取结果正文/原文/返回、
Agent详情/选择取消、恢复核验及精确Stop取消/确认/回读。截图为滚动前后的原生X11整窗，
不靠fullPage截图掩盖遮挡。全部内容为原型合成数据。

脚本在失败时也写 `evidence/browser-zoom-verification.json`，记录源码hash、实际
浏览器、逐级校准、滚轮位置、目标命中与失败；PNG沿用既有artifact目录，不入Git。
先观察首轮原生缩放和六页基准，可靠后再追加必要两尺寸/双语/浅深覆盖；当前没有
把更大矩阵写成已通过。生产浏览器或物理设备资格仍独立。

## 本地检查与限制

开发位于助手云工作区。独立取回公开固定main，不使用或发布用户Mac的片段证据。
自启Chromium因Unix socket EPERM未能打开页面；平台云浏览器存在，但工作区HTTP
预览返回connection refused。没有连接变体、隧道或权限绕过。
本地仅运行语法及纯校准分类器检查；实际浏览器与像素结果待本候选的正式CI。

## 方法依据

- [Playwright：Linux headed CI 需要 Xvfb](https://playwright.dev/docs/ci)
- [Chromium：Browser Zoom 与 Pinch Zoom 的坐标区别](https://www.chromium.org/developers/design-documents/blink-coordinate-spaces/)
- [xdotool 原生键盘接口](https://github.com/jordansissel/xdotool/blob/main/xdotool.pod)

既有 large 模式与390px viewport结果保留其原资格，不作为本项200%证据。

## 首轮真实 CI：缩放成功，输入/截图证据仍需校准

head `3b0d327ae9fb1da2ca86fd7c9ca1f9ff10b66522` 的
[E2E37824042969 / job113472125262](https://github.com/ForceMind/agentbox/actions/runs/37824042969/job/113472125262)
首次运行保留为 failure，未重跑取绿。实际 Chromium151.0.7922.34：原生窗口1440×1000、
100% DPR1 / viewport1440×913；110/125/150/175各级符合，200% DPR2 / viewport720×456、
visualViewport.scale1，CSS正文字号15px、zoom1、无transform/large，缩放校准通过。
首页滚动/新建取消通过；执行页进入结果后，返回按钮的DOM矩形13点命中通过，
但Playwright locator.click报header/intro拦截而失败。其余四页未执行，不是六页PASS。

[artifact11569803816](https://github.com/ForceMind/agentbox/actions/runs/37824042969/artifacts/11569803816)
为3446843bytes，SHA256 `ecc265088b302c71f7f7838e3638d027e399c6abcc74f6f52b086963d411d191`。
包含六张新zoom截图和失败JSON；协调者实际查看zoom-failure.png：720×456图像显示
像桌面页面左上裁片，返回按钮不在图像中，与CSS720响应式矩形不符。故该轮API截图
不作为200%像素PASS，也不能据点击错误直接判产品遮挡或声称产品RED→GREEN。
checkout `e723e0374f4d02ccca14a3d5492850a1b9f3ff32` 的tree与head同为
`17c0e84f2f69d5b787f9640260bd10d12c8c098f`，parents为main62c5与head3b0。

后继仅修测试输入与取图：原生X11鼠标按DPR与实测浏览器chrome偏移转换，每次核对
可信mousemove的CSS坐标、button action，点击后再核可信click坐标与目标。
滚轮位置亦核对实际可信指针和wheel事件。保留所有遮挡、几何与状态断言，不force
click、不DOM.click/dispatchEvent、不改产品源码。用ImageMagick官方import -window root
保存未经缩放裁切的完整1600×1200隔离Xvfb画面；缺包才从Ubuntu官方源补ImageMagick。
另保留一次明确标注的API截图用于与原生画面对照，不当作像素资格。
后继CI仍待，不扩矩阵，先让相同六页基准给出可信输入/像素结果。

## 原生取图已核，CDP滚轮校准假设失败保留

head `a01e2f1efc7ce5d25dcaf02be03d0e5226ca3cff` 的
[E2E37825583803 / job113477467564](https://github.com/ForceMind/agentbox/actions/runs/37825583803/job/113477467564)
再次通过原生200%五级校准，并取得1600×1200原生X11整窗。
首屏滚动前，CDP mouse.move乘DPR的候选校准未等到匹配client坐标而失败；
没有开始native点击，没有六页PASS，也没有证明产品bug。旧头不重跑。

[artifact11570564368](https://github.com/ForceMind/agentbox/actions/runs/37825583803/artifacts/11570564368)
SHA256为 `9364be0143aa6394e158053309221985e39ccd97b0871ebc51946cc17816d235`。
协调者实看calibration-200与after-api-comparison-200两张原生图：均为真实200%响应式
首页、无桌面侧栏，API截图前后没有可见页面布局改变。API裁片仍不作为原生像素证据。

后继仅将滚轮也统一为X11原生mouse位置及wheel按钮4/5；真实mousemove和wheel的
可信标志、client坐标、方向以及scrollTop变化逐次校验。保留几何/遮挡/交互断言，
不再猜CDP坐标缩放。失败报告保存最后实际pointer/wheel/click。原型源码与六页基准
范围保持；后继正式CI与全部原生图资格仍待。

原生滚轮是单notch离散输入；报告中的centeringIntent只是方向计算的理想位移，
实际位移以wheel事件和scrollTop差值为准。旧纯wheelDelta数学unit不证明原生近满高
目标收敛；此helper边界仍保留。当前六页短样本必须真实滚动并完整可见才通过，
若32次无法到达仍失败，不放宽可见性或改用DOM滚动；不将helper限制误报成产品bug。

## 六页原生基准已实际通过（2026-10-08 18:46 UTC）

head `bcb67a975ad82b22bac1199c5ec05949b94e5f26` 的
[E2E37826543348 / job113480756955](https://github.com/ForceMind/agentbox/actions/runs/37826543348/job/113480756955)
首次成功。六页全部校准为原生200%，16次可信X11点击、59次可信真实滚轮、51个
目标可见性/遮挡检查通过，零外部request/pageerror。原back-work按钮的可信原生
client坐标633,159及action一致，实际返回成功；这是测试路径校准，不是产品修复。

checkout `1706d2fe41fd69e486e9c05944fee299c9d04f16` 与该head的tree都为
`380b31cee240a1ef6eb4f461c3b6b66295ea0737`，checkout parents为main62c5和headbcb67。
[artifact11571078786](https://github.com/ForceMind/agentbox/actions/runs/37826543348/artifacts/11571078786)
共5444627bytes，SHA256 `967fdf893d3e69b46973aac684f9a9972383112745c3f086b0b1c2606de87b63`。
独立逐一查看20张native整窗，无产品内部重叠；diff/原文、审批范围/回读、Stop身份与
按钮、composer、Agent资格文字可见。API对照单独排除，不冒称其缩放图合格。

该批若干旧名top图片实际为中下段；Stop取消后无独立图，最终readback图只露标题和
session顶部。动态行为由可信输入/状态断言支持，图片不单独证明取消和完整回读。
这些限制保留；后继改名entry并记录每图实际scroll/model状态，补取消后running/target
与最终exact-target字段可读原生图。既有小基准仅为1440×1000、中文浅色，不外推完整矩阵。

## 后继必要矩阵候选

保持同一六页流程与严格断言，原生窗口仅允许1440×1000、780×1000；200%后分别为
约720×456、390×456 CSS viewport。这是桌面浏览器的两种原生窗口宽度，不是物理
手机或viewport模拟。语言zh/en、主题light/dark，共8组合×6页=48。

既有job先执行1440/zh/light基准，成功后再逐一执行其余7组合；任一失败即保留报告，
未执行组合不算PASS。没有更改job超时、触发器、权限或门禁。每组合独立PNG/JSON
文件名防止覆盖，原始同一HTML hash继续记录；没有增加长文本/读屏/真实设备资格。
后继完整CI、48组实际结果与原生图复核仍待，不以小基准绿色替代。
