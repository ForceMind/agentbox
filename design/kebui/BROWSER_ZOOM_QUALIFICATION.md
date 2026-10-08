# U1 浏览器 200% 补验

2026-10-08 UTC。当前状态：48组原生200%通过；42/184原生图独立有界复核通过。完整PR CI终态另验，保持Draft。

仅补已有 U1 设计验收。基线 main `62c5d5ddadcb74e0d8aa1898b1b490d1314b190b`
的原型 SHA256 为 `fd8d1c491a211a3df44bc2f4a8e80a4152254886896af9a841f4d01b2c1c19f8`。
本批不改 HTML/CSS/交互产品源码，不接真实 Agent/账户/host，不部署、不发布版本。

以下从“首轮只做六页基准”至“后继必要矩阵候选”为分阶段历史记录，其“待验”时态
和首轮旧JSON文件名不能覆盖末尾19:06节的现行结论。当前每组合独立写入
`evidence/browser-zoom-<width>-<lang>-<theme>.json`；旧
`browser-zoom-verification.json`仅指早期单组合采证。

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

## 2026-10-08 19:06 UTC：48组原生200%与有界像素资格

源head `88a4f2e70aca1bce204947b3434b5ca6c210f27e` 的
[E2E37828139269 / design job113486200256](https://github.com/ForceMind/agentbox/actions/runs/37828139269/job/113486200256)
首轮完成success。Chromium151.0.7922.34，原生窗口1440×1000 / 780×1000；
每组从100%经五级原生快捷键到200%，实际CSS宽720/390、DPR2、scale1、字号15px不变。
两语言×两主题×两尺寸×六核心页=48组全部通过。128次trusted原生点击、585次真实
滚轮、432个可见/无遮挡目标检查，page外部requests与pageerrors均为0。
窄英文浅/深两组各实际发生2次dialog内滚，其余dialog不需要内滚。

[artifact11571489036](https://github.com/ForceMind/agentbox/actions/runs/37828139269/artifacts/11571489036)
为21500181bytes，ZIP SHA256 `140dc384d41865c2c3b1ed78e10eeaf7e9bffb0ff31630548ea54ab4682c90eb`。
含8份新JSON、184张native整窗（含100%校准图）、8张明确API对照；另含既有标准26图。
本轮独立检查全部8JSON，实际逐一查看**42/184张native原图**，覆盖全部8配置；
其中特别检查390CSS英文浅/深的24张正文、审批、Agent、composer与Stop关键图。
所查关键正文与按钮无产品内部遮挡，Stop取消后running/epoch7、最终exact-target/
epoch7/not replayed可见。没有声称其余142张已看，也没有用API对照图替代原生图。
部分home-entry图的浏览器zoom/翻译泡泡覆盖顶部演示横幅；未挡所查关键操作/正文，
但不能宣称“每处文字零遮挡”。entry记录实际scroll，不再冒称都是页首。

8报告的source统一为PR merge checkout `09814eb2fc7f98b37346f02f69b24883424ae456`，
headSource统一88a4；官方Git API已核checkout parents为main62c5和head88a4，
tree与head同为 `11c6814c49c14593cab9998228890e22228355f2`。
原型HTML始终保持 `fd8d1c491a211a3df44bc2f4a8e80a4152254886896af9a841f4d01b2c1c19f8`。
没有产品修复提交：前两轮失败属于本次测试输入/取图资格问题，原失败及原artifact保留。

本节只关闭上述六核心合成页的原生200%有界验收缺口，不是21页全面200%、长文本
压力、键盘/读屏、物理Android/iOS或真实Agent/账号/host资格。原生单notch的近满高
helper边界仍在，未通过放宽断言隐藏。生产源码、版本和功能范围不变，无U3/release/deploy。

本次后继提交只更新说明/状态，HTML/测试/CI脚本保持该合格源head字节；文档组合head
仍需自己的完整六套CI、逐项报告及证据一致性回读。19:06时88a4五套success、完整E2E
仍运行，不能提前称整PR已绿。保持[PR165](https://github.com/ForceMind/agentbox/pull/165)
Draft，不合并；最终exact-head状态以该PR回读为准，不借旧头绿色。

## 2026-10-08 19:22 UTC：后继原生窗口发现失败保留

源88a4的完整六套CI现已全部success；但不能据此替代后继文档头。
head `a481fbc63c7f204e7645ca55d72e76ecb357c7dc` 的
[E2E37829956579 / job113492416077](https://github.com/ForceMind/agentbox/actions/runs/37829956579/job/113492416077)
在两个1440中文组合通过后，第三个1440英文浅色于缩放前的一次性原生窗口标题匹配
得到0个对应窗口，立即失败。其余组合未执行，不算通过。该head没有改HTML/测试源码，
这仍不是产品布局或缩放RED。原实现未记录当时native title值，不能断言具体标题值
或已确定平台根因；该失败不重跑取绿。

[artifact11573071591](https://github.com/ForceMind/agentbox/actions/runs/37829956579/artifacts/11573071591)
8430514bytes，SHA256 `7ec700e0771b511c38192bae594984b2fe220f8e025d3c26c248c39a1dcddeba`。
后继仅为窗口发现增加同条件就绪等待及实际title/ids日志：仍只接受visible Chromium
与原页面标题对应的唯一窗口；歧义直接失败，不取first或扩大selector。
采用10秒单调时钟就绪预算，每次原生probe只使用剩余预算，返回后在接受匹配前检查
截止时间。迟到、持续旧标题、歧义均有纯unit拒绝案例。不增加整体job时限、retries、
权限或产品改动，真实输入/截图与48组断言保持。后继头须独立六套CI及证据回读，
当前不称ready，继续保持PR165 Draft；最终状态以该PR回读为准。

## 2026-10-08 主线滚动同步失败与最小测试候选

PR165已于19:47:21 UTC正常合并为main `0386db252e8800b9a2dc1b0a28984b79b39641d3`，
tree `bdc7fe85a8527b716274a3636ec0d95d219a7092` 与合格head3bcd57相同。
该head六套CI各attempt1成功，48组/128点击/585滚轮/432目标再次通过；独立42图
为7张字节/像素相同继承、35变化原图重看，未声称184图全审。

main自身六套已经终态：五套success，
[E2E37834575583](https://github.com/ForceMind/agentbox/actions/runs/37834575583) failure。
原主e2e仍650 passed / 270 skipped、21 preflight通过；只有新design job113508213018
失败。首个1440/zh/light的前五页通过，recovery的recover按钮命中检查失败；其余组合
未执行。旧main不重跑取绿，不把head成功代替main资格。

[失败artifact11575286294](https://github.com/ForceMind/agentbox/actions/runs/37834575583/artifacts/11575286294)
5185954bytes，SHA256 `640f0a9232536809eee3ac210454f97d13b2b1c212e17c95145dd28bd5c4c123`。
JSON记录entry取图后的scrollY65.5、失败时0；最后输入是Ctrl+Home，recover尚未点击。
独立实看两图：entry按钮完整，failure移回页首后按钮下缘出视口，未见遮罩/弹层叠在按钮。
两图位移又大于随后JSON位置之差，说明抓图与view采样不能直接视为同一稳定时刻。
证据支持滚动/几何采样未对齐，不凭静帧宣称准确根因或产品布局RED。

后继只修测试同步：观察浏览器真实scroll/scrollend，Ctrl+Home等待实际Y0和滚动结束；
每个wheel等待对应document/dialog的新scrollend，原可信坐标和实际位移检查保留；
目标几何须非pending且连续两次完全相同，之后仍执行原13点无遮挡检查。截图前亦等待
原生滚动非pending。没有JS滚动、force click、合成scroll事件、产品或工作流修改。
[Chrome官方语义](https://developer.chrome.com/blog/scrollend-a-new-javascript-event?hl=en)
说明scrollend在实际滚动结束后发出，无位移时不发出；不以固定延时假装滚动结束。

6项纯unit与Node语法检查通过，独立源码复核无阻断；它们不是浏览器通过。
几何检查设10秒准入截止并拒绝迟到结果；不声称已定位后的浏览器求值可硬取消于10秒。
原job总时限/门禁不变。此候选须新head自身完整CI与原图核证，再正常合并/主线回读。
原型HTML/CSS/app.js、版本、权限及所有旧失败历史保持；不启U3、发布或真实host操作。
