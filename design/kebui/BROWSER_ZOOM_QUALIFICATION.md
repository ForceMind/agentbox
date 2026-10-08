# U1 浏览器 200% 补验

2026-10-08 UTC。当前状态：六核心页基准候选，浏览器尚未运行；不宣称 PASS。

仅补已有 U1 设计验收。基线 main `62c5d5ddadcb74e0d8aa1898b1b490d1314b190b`
的原型 SHA256 为 `fd8d1c491a211a3df44bc2f4a8e80a4152254886896af9a841f4d01b2c1c19f8`。
本批不改 HTML/CSS/交互产品源码，不接真实 Agent/账户/host，不部署、不发布版本。

## 首轮只做六页基准

复用 `.github/workflows/e2e.yml` 的 `kebui-design` job、Chromium、中文字体和
既有七天合成 artifact。使用 headed Chromium / Xvfb，1440×1000 原生窗口、
中文、浅色；通过 X11 原生 Ctrl+0 / Ctrl+= 触发浏览器缩放。
`xvfb-run` 由既有 Playwright 系统依赖提供；仅缺少时安装 Ubuntu 官方 xdotool。
不新增 npm 依赖、扩展、凭据、CI 权限、job、触发器或门禁。

先验证原生窗口不变、DPR 1→2、布局 CSS viewport 减半、visualViewport.scale=1、
CSS 正文字号/zoom 不变、无 transform 或 large 模式。中间 110/125/150/175/200
步骤也记录实际值。按键无效或校准不符直接失败，不把 viewport 缩小、DPR 模拟、
pinch zoom、CSS zoom/transform 或文本放大替换命名为浏览器200%。

校准成功后逐页：真实滚轮到达、按钮中心及周边命中检查、关键正文可见性和实际点击；
覆盖首页新建/取消、执行结果入口、审批范围/批准回读、显式读取结果正文/原文/返回、
Agent详情/选择取消、恢复核验及精确Stop取消/确认/回读。截图为滚动前后viewport，
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
