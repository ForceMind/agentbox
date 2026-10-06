# A3 currentness 失败时序诊断

最新结果见末节“固定四轮完成与结果判读”：A1/B1/B2通过，A2基线重现原超时；
采样已停止，native产品根因仍未闭合。下方候选、待采证与准备失败记录保留为
当时快照，不覆盖末节实际终态。

## 范围与已有证据

本节描述最初observer补丁；末节ABBA候选另增独立诊断workflow，原有六套不改。

本候选从 main `a586eaec27984e0632187048cc1b82e7e29552d1` 独立分支接续，
与 UI Draft PR148 分开。仅增加测试可观测性，不修复或重新定义产品时限。
原失败用例继续使用真实 socketpair、admission、Git、crypto 和 publication
检查；生产源码、CI workflow、预算、断言、重试与 GC 策略均不变。

Python3.13.15 的 job112289152799、112295026324、112299168102 均在 READY
前出现 runtime-receive PATCH_TIMEOUT，随后 bundle EOF。每次 receive 入口
剩余至少200ms、耗时至少250ms，checker 计数比 currentness 计数少一次，
checker 自身也报 PATCH_TIMEOUT。前两次没有 inherited native I/O deadline，
第三次有 active inherited deadline。因此不能归因为 receive 入口已经耗尽
继承预算；已有证据仍无法定位 checker 停顿，也不能证明 GC、GIL、OS 调度
或 codec 是原因。原始日志：

- [首次](https://github.com/ForceMind/agentbox/actions/runs/37469554499/job/112289152799)
- [受控重试](https://github.com/ForceMind/agentbox/actions/runs/37469554499/job/112295026324)
- [后继 head](https://github.com/ForceMind/agentbox/actions/runs/37472453007/job/112299168102)

## 调用链与等待预算

测试 Client 是同进程 socketpair driver：Runtime owner event loop 同步调用
A3NativeReservation.current，先 send CURRENT，再 receive CURRENT_REPLY。
独立 Python checker thread 依次 wait_readable、receive、比较 facts digest、
计数加一、send reply，不调 API DB 或 owner event loop。send 正常返回才会
进入 runtime receive，因此失败计数差不能再被误读为“尚未调用 send”。

Runtime currentness 共用一个250ms绝对截止时刻，另取原始 selector expiry
与 NATIVE_IO_DEADLINE 的最小值。OPEN 的 serve task 显式清除 command deadline，
而 opaque I/O guard 可以设置新的嵌套 cap。NativeChannel select 每段至多50ms，
每次 I/O 前和完整解码后仍校验原截止时刻，部分读写不续期。fixture checker
空闲等待30s，receive/send各250ms；原 READY等待5s、opaque I/O1s不变。
同进程 checker 与 Runtime 共享解释器，因此 GC/GIL 停顿有可能同时影响两端；
这只是架构事实与待检验假设，不是本次 CI 的根因结论。

## 有界观察合同

仅原有显式 diagnostic opt-in 安装包装。保留 operation 的实参、返回值、原
异常和次序。runtime send/receive、checker wait_readable/receive/send 入口
采样 wall、thread CPU、process CPU。仅 operation 原本抛异常时记录固定 phase
与时长 bucket，最多4条；采样/probe失败不能替换或吞掉原异常。没有任意异常
正文、stack、wire bytes、路径、凭据、admission facts 或标识符输出。
原固定 reason/count/budget 诊断保留。
诊断自身的BaseException也被隔离，包括CancelledError、KeyboardInterrupt、
SystemExit；注册已插入callback后失败时仍精确清理。真实operation的这些
BaseException继续以原对象传播，不把native取消或退出转换为成功。

临时 GC callback 只观察 start/stop wall span，最多保留最近8条完成记录和1条
active span。不检查回收对象，不调用 collect、disable、freeze、set_threshold
或更改 debug flags。失败输出只有 overlap bucket、generation mask0..7 和
truncated 标志；计数封顶65535。缺失/畸形/采样失败明确为 unknown，启用失败
明确 unavailable；截断记录不能用于推断无 GC。Client start失败与close的finally
均按 callback 对象 identity 精确移除，不 clear 其他 callbacks，支持重复启用
与重复close。GC callback不持锁，避免 GC 重入同一诊断锁。
采样携带observer epoch；operation期间close或close后restart均强制GC结果
unknown/truncated。无锁revision校验拒绝并发callback的半更新快照，不把观察
已停止、重启或不一致的时段解释为没有GC。

checker-receive失败且低CPU/没有可见GC重叠，支持继续调查调度或I/O等待；
高checker CPU与GC重叠可进一步缩小范围。checker-wait或checker-send失败则
定位到不同阶段。GC wall overlap本身不证明CPU因果：GC也可能被OS暂停。
时序采样会产生扰动，诊断头全绿也不能被称为修复。

## 验证与停止条件

验证 bucket边界、span裁剪、有界保留、generation校验、callback生命周期、
参数/返回值/异常透明性和诊断自身故障隔离，不替换真实native测试。
在独立候选执行可用lint/type/test门禁。此环境AF_UNIX限制已验证，不重复被拒
syscall或声称本地native等价；Black按单文件调用，避免diff模式进程池的socket。

选择修复前须由新exact-head CI采集真实证据。产品修复必须单独审查，并具备
同条件真实red/green。保留所有历史失败，不盲目rerun取绿，不在此merge main
或UI分支。本文是诊断合同，不是根因修复或native资格通过声明。

GC观察采用 [CPython官方callback接口](https://docs.python.org/3.13/library/gc.html#gc.callbacks)，
只记录开始/结束与generation，不改变收集策略。

## 独立审查修正

首次独立审查发现P2：仅隔离Exception时，诊断采样/记录的CancelledError会
阻止operation或替换其异常，注册插入后同类失败还会遗留callback。先新增
7项纯内存回归，旧实现7 failed；只扩大诊断自身隔离与清理后，同条件7 passed。
另覆盖KeyboardInterrupt/SystemExit、成功operation只调用一次、native自身
取消原对象传播及Client清理失败。此red/green仅证明诊断隔离缺陷已修正，
不证明native currentness超时的根因或产品修复。

## 2026-10-06 独立复审与发布候选

独立审查发现的诊断BaseException隔离P2已经同条件7 failed→7 passed闭合，
复审独立重跑68项无socket测试全部通过，确认CancelledError/KeyboardInterrupt/
SystemExit的诊断失败隔离与真实operation原对象传播、identity callback清理、
epoch/revision边界、固定输出与有界空间。没有新增P0/P1/P2。源文件摘要与
冻结manifest一致；这只证明诊断自身安全边界，不证明currentness根因或产品修复。

本候选发布为独立Draft PR，等待精确head的真实Python3.13.15 CI采证。
前端dependency修复位于UI PR148；此分支仍采用main基线锁定依赖，各套CI结果
分别报告，不借旧通过记录或诊断绿色结果宣称完整合并/发布资格。

## 2026-10-06 首轮真实Backend通过与测试尾置对照

独立Draft PR149首轮head `86b1281803c4563572e6e9337198d8c5fd3980ef`，
tree `f6a1bc128e064f9aadd47956efd2c6a0a72a88f0` 的
[Backend run37480210068](https://github.com/ForceMind/agentbox/actions/runs/37480210068)
全部通过。[Python3.13.15 job112326041707](https://github.com/ForceMind/agentbox/actions/runs/37480210068/job/112326041707)
为5370 passed/88 skipped，收集5458项，未产生新的失败phase/CPU/GC note。
这是未复现，不能认定诊断修复了真实currentness超时；UI旧头三次失败保留。

该通过job与旧失败job112299168102的Python3.13.15、pytest9.1.1、pip install
日志列出的版本清单、ubuntu-24.04 image20260927.320.1及setup-python cache
key一致。没有pip freeze --all证据，不能推断原global site-packages完整相同；
临时PEP517构建环境版本亦未单独输出。这些相同也不证明宿主负载或GC/堆状态
相同。新增实际是65项：新observer模块
62项，加既有fixture新增3个BaseException参数；68是新旧诊断安全测试合计。

本轮只把新增65项执行位置移到旧suite之后。observer文件更名为
`tests/unit/test_zz_a3_currentness_diagnostics.py`；既有fixture恢复单个
RuntimeError默认检查与原test ID，其余3个参数在尾部复用完全相同的检查。
observer实现、Client、真实native目标、预算、依赖及CI workflow不变；不skip、
删除用例或修改GC策略，默认资格CI仍执行全部5458项。

实际collect-only对照main `a586eaec27984e0632187048cc1b82e7e29552d1`：

- 原5393项仍按原顺序位于1–5393；新增65项全部位于5394–5458
- 真实native目标由第828项恢复到main的第763项
- 5380个原node ID逐字一致；另外13个只含已有动态PID差异，已检查其余参数
  完全一致，且两份相关测试源码与main字节一致
- native的第293–301项是test_auth_probe_rejects_malformed_or_wrong_parent_record
  的9个动态runtime_pid参数，差异仅payload bytes8..11
- unit的第2381–2384项是test_activation_metadata_must_be_exact的4个
  listen_pid参数，差异仅PID值；不以简单删除所有参数ID的方式掩盖差异

本地收集使用Python3.12.14/pytest9.1.1，main以独立归档和显式source roots
读取，不是Python3.13.15运行证据。新head真实CI仍须确认5458项完整执行。
原目标及Client的AST均不变，observer SHA256保持
`47056c3a70a1cabc4708e454736e807a6f1dd4de7013e75c4cbca6675f93ce6c`。
本轮本地相关68项无socket回归通过；全量Ruff、395文件mypy、两个改动测试文件
逐一Black check、716项doc links、source-boundary及Python3.13.5语法检查通过。
完整native与Python3.13.15执行未在本地复验，独立审查和新head CI仍待完成。

后续独立复审已重跑68项无socket回归，重新收集main与候选，逐项核验上述
13个PID字段和原62项observer测试AST，并重建相同候选tree；无新增P0/P1/P2。
代码内容未因复审改变，仅补充此证据与状态。新head的Python3.13.15真实CI
仍须采证；本地Python3.12.14验证不替代它。

这是一轮有意改变新增测试安排的诊断对照，不能称严格只改变堆状态的实验：
尾置同时改变collection模块导入次序，observer自身仍有时序扰动，既有fixture
仍使用已审观察实现。仅运行新exact-head首次CI；失败则采固定phase/CPU/GC，
通过仍记未复现，不预设根因、不自动盲目rerun取绿。此轮不增加CI job，亦不
修改UI PR148或main；后续若仍缺证据，再单独设计同时期baseline对照。

## 2026-10-06 固定ABBA同时期对照候选

尾置后的head `404daae0be4225b30a6e3e71ee239376bd5e6ca6` / tree
`238a35a0629e3307560d3a57371e9f2410e3f047` 的
[Python3.13.15 job112342237328](https://github.com/ForceMind/agentbox/actions/runs/37484879498/job/112342237328)
再次5370 passed/88 skipped，5458项完整收集且新模块在末尾，未产生新的失败
note。此次pytest耗时309.50s，首轮约365s；不能认为同镜像即代表同负载。
以下是新受控采证条件，不是产品修复，也不是再次重跑同头取绿。

### 固定条件与一次触发

- A：冻结main基线a586eaec27984e0632187048cc1b82e7e29552d1，tree
  e5d9309dca123f17f9ff9ee48df0765c332ea451，完整原5393项
- B：冻结404daae0be4225b30a6e3e71ee239376bd5e6ca6，tree
  238a35a0629e3307560d3a57371e9f2410e3f047；仅此诊断条件用--ignore排除
  tests/unit/test_zz_a3_currentness_diagnostics.py，仍运行完整原5393项
- 顺序固定A1、B1、B2、A2，单个ubuntu-24.04 runner，无参数扩展、循环重试或
  动态增轮。B是诊断旧suite，绝不称完整资格；默认CI仍保留65项安全测试及
  新增orchestration单测，现有六套workflow不改
- 新workflow仅接受PR149、同仓库精确branch diag/native-currentness-20261006、
  main base、bug labeled事件及run_attempt1。普通push、schedule、workflow_dispatch
  均不触发本实验，不使用pull_request_target，不添加写权限或host操作
- 只读已核验bug标签存在、PR149当前labels为空；不做加删探针。复审并
  发布后为真实采证添加一次标签；实际触发失败须如实报告，不假设能
  新建label。actions沿用仓库已审SHA，contents:read，checkout不持久保存凭据

### 隔离与预检

四次各自新checkout、新venv、新pytest进程。固定Python3.13.15并实查版本、
Linux/x86_64与ImageVersion20260927.320.1；不把matrix的3.13标签当作patch固定。
四套源码SHA/tree、tracked洁净状态、venv前缀、模块实际来源及5393收集序列
全部预检成功后才开始测量；每次前后再次核验源码和wheelhouse。只允许原有
13个PID字段归一化，目标必须为第763项，其他node/参数/顺序变化均使实验无效。

requirements文件冻结job112342237328安装日志可见的74个外部包，包括pip26.2.1、
setuptools84.0.0；每个venv另加对应源码的editable agentbox0.3.0rc31，并严格
核验实际集合恰为75包。pytest11 entry points固定为anyio和platformdirs，不允许
额外PYTEST_PLUGINS/ADDOPTS、禁用autoload或host-gate配置。源码/import与collection
预检运行在独立的python -B进程，不向真正pytest进程添加事件插件或预载模块。

外部wheel只下载一次，核验包名/版本、记录每个实际wheel的SHA256后只读封存。
四个venv用require-hashes/no-index/no-deps从该wheelhouse离线安装所需依赖；
已满足版本的包可保留，末节记录实际预置pip的字节验证边界。editable
构建明确no-build-isolation，使用固定setuptools84；不添加没有原日志版本依据
的wheel包。此模式固定了本轮构建环境，却不等价于原CI未公开的临时PEP517
环境。原global site-packages可能还有未显示的预装包；75包集合是新受控条件。
wheel摘要证明四次安装所引用的wheelhouse内容一致，不是原CI wheel字节相同
或全部已安装包均由这些wheel重新安装的证明。

### 有界成本、证据与判读

真实执行命令保持python -m pytest -o faulthandler_timeout=120，只有B加上述
ignore。原250ms/1s/5s/30s、断言、GC策略、hash seed及真实I/O均不改变。
最初21–25分钟pytest估计已被后续492.02s实测更新。当前诊断step外层37分钟、
整个job40分钟，依据与余量见下节；为always artifact上传预留时间。这只是采证
外层上限，不是native
或单测预算。每阶段summary立即落盘，保留四份原始pytest/预检日志、版本、
module来源和wheel摘要；不dump环境变量、凭据或进程命令行。

- 四次全通过：只报告本轮未复现，不能声称修复
- 两个A目标失败、两个B全部通过：只支持observer相关性，不能证明GC因果
- B目标失败：读取固定phase/CPU/GC证据再分析，不根据wall overlap直接归因
- 其他交错/非目标失败：保留全部结果，结论不足
- 版本/源码/collection/skip数量不符、准备失败、取消或外层超时：实验无效或
  未完成，不计绿色。有效测试失败不会提前跳过后续固定条件，也不会追加重试
- 四次终态后停止；失败返回非零，不用continue-on-error把实验包装成通过。
  外层超时会保留已落盘的未完成状态并尝试上传；平台终止/上传故障仍可能缺
  artifact，不能把缺证据当成功

此次只比较原基线与最小observer的旧suite。helper导入、原fixture使用observer
及观察本身都是B处理的一部分；这是新受控比较，不是严格证明历史GC根因。
Release Candidate的setup-python缓存问题保持独立，不混入本候选。

### ABBA编排审查修正与本地验证

独立审查发现P2：pytest9.1.1的bytes ID保留字面反斜杠，不能以unicode_escape
逆解。使用真实_pytest.compat.ascii_escaped与原160字节auth payload的PID92、
4700、23604、23662、23672五项先全部失败；中间prefix-only方案仍有2项把静态
PID1误计为动态。最终修正先从4个固定activation字符串参数校验唯一PID，再对
冻结原11个完整auth payload前向编码并逐字匹配，仅归一化9个动态PID，所有
非PID字段均精确核验。没有逆解bytes、改Popen或增加预检进程。

同条件五项最终全部通过，且全部256字节的前向编码与真实pytest oracle一致；
PID不一致、auth/activation不匹配、非PID字段漂移均拒绝。实际原main与404头
收集日志用新normalizer再次证明5393项完全同序、目标第763项。这是编排P2的
red/green，不是native currentness根因或修复证据。

本地46项编排/合同测试与原68项合计114 passed，仅模拟orchestration，不mock
真实native。全量Ruff、mypy397、顺序单文件Black410项（修正的两文件再次验）、
56个action pins、doc links、source-boundary、secret-pattern与Python3.13.5
语法检查通过。真实ABBA、wheel下载/75包安装与3.13.15执行尚未运行；当前
只提交可独立复审的源码、固定约束、workflow和文档，不提前宣称真实采证成功。

独立复审已重跑114项及原5个真实PID探针，并核验256字节oracle、非PID拒绝、
静态PID1歧义、真实collection顺序及四文件摘要。P2闭合，无新增P0/P1/P2；
最终文档亦经回读。源码保持复审摘要不变，进入普通提交与一次真实标签触发。


## 2026-10-06 首次真实ABBA准备失败与root METADATA修正

首次标签触发head `e1b631fd32099d3baf2835ef9922c5f387d4cf78`，tree
`14a48cbb02e2046418d82f292cfc6a65eca33bb0` 的
[run37494932672/job112376929532](https://github.com/ForceMind/agentbox/actions/runs/37494932672/job/112376929532)
在prepare阶段因invalid_wheel_metadata返回exit2。74个wheel下载成功，但尚未
建立任何case venv，未执行任何native或ABBA测量，summary.results为空。这不是
A/B任一条件通过或失败。原artifact11426309681 ZIP SHA256为
`0a835821eac74c57b3efd43ec95125de8abcd733485ee11c6767619958cc8548`，
原失败与日志保留，不rerun旧头取绿。

### 真实官方wheel证据与最小修正

实际取得并校验了官方PyPI相同文件名的74个wheel，所有SHA256与size均与各自
官方PyPI JSON一致。旧collector把任意层级的.dist-info/METADATA当作发行包
元数据；实际[setuptools84.0.0](https://pypi.org/pypi/setuptools/84.0.0/json)包含
1个root METADATA（6581 bytes）以及setuptools/_vendor下12个nested METADATA，
所以会被旧逻辑误拒。[pip26.2.1](https://pypi.org/pypi/pip/26.2.1/json)只有1个root
METADATA（4617 bytes）。两份实际wheel的SHA256分别为：

- setuptools：51a52592b3b99e102b609654876bd65f19f999935166d1352678931132b0c670
- pip：71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e

用原版本seal_wheels读取上述同一批官方bytes，实际RED为invalid_wheel_metadata
exit1；仅修正root-level选择后，同两wheel及全部74wheel的seal/verify均GREEN
exit0。读取不再把vendored METADATA当成第二个发行包，但仍拒绝多root、重复
root METADATA、缺失root、非规范分隔和超限root。131072 size cap、pins、hash
核验、只读封存、四条件、Runtime与单测预算均不变。54项编排测试包含新增8项
结构/边界回归，并保留131072接受、131073拒绝的明确断言。

74份实际wheel都恰有一个root；最大root为pydantic2.13.5的110178 bytes，
只有setuptools有nested METADATA，没有发现需要扩大cap的同类问题。文件名
与失败CI下载清单全部相同，但原CI在失败前没有产出wheel hashes，因此不声称
历史CI下载bytes与本地逐字一致。这是已复现并修正的collector缺陷；native
currentness根因仍未证明。

### 本地package-only验证与限度

A/B两份隔离Python3.13.5 fresh venv已实际完成74包require-hashes/no-index/
no-deps离线安装、固定setuptools84无build isolation的editable安装、pip check、
完整75包map、两个pytest11 entry points和9个module实际来源核验，均exit0。
74个wheel摘要和A/B原始源码文件安装前后未变。A使用冻结commit a586eae；
B使用本地mirror6999014，其tree严格等于冻结238a35a，不冒称本地已读到外部
404daae commit对象。

本机3.13.5没有ensurepip，因此本地package-only先用--without-pip建venv、再由
已验pip26.2.1通过--python目标venv bootstrap，之后使用各venv自身pip。这不是
正式CI的python -m venv路径，也没有改正式probe的3.13.15要求。没有运行pytest
collection、AF_UNIX/native用例或四轮ABBA；本地package-only不替代CI3.13.15资格。

### 更新后的外层采证限额

后继真实默认Backend job112376311244在Python3.13.15报告5504 collected、
5416 passed/88 skipped，pytest实际492.02s。四次按此估算为1968.08s，即
32m48.08s，尚未包含准备，已超过原step32。故本轮仅把step改37min、job改40min：
按该实测估算，脚本准备/编排余量约251.92s（4.20min），step之外checkout/setup/
artifact约3min。原四次固定流程、pytest命令和全部产品/测试预算不变。

首次CI时间戳显示wheel下载到失败约8.08s、artifact上传约1.20s。本地每套package
准备按新log birth至最后mtime估计：安装11.89–12.69s、editable2.16–2.35s、
pip check0.29–0.32s、imports1.66–1.79s；没有独立stopwatch，且不包括venv和
collection，不能外推CI严格上界。官方74份JSON额外审计不在CI harness内。
新外层余量是有依据的估计，仍可能超时，不保证完成；超时/缺证据仍记未完成。
修正须独立复审、新head再单次触发，不在旧e1头rerun，也不追加实验轮次。

## 2026-10-06 固定四轮完成与结果判读

### 精确来源、原始证据与实际成本

已审root METADATA修正发布为head
`7cc9d971db92a3b809e9c02b467351483f30c8b0` / tree
`fc95b8bdaa0b26e3615885f6d74c3065cd259361`。新头一次标签事件触发的
[run37498497962/job112389102587](https://github.com/ForceMind/agentbox/actions/runs/37498497962/job/112389102587)
为attempt1，已完整执行A1、B1、B2、A2。summary.stage为complete，interpretation为
inconclusive_failures_retained；harness exit1来自A2真实测试失败，没有外层超时，
也不是准备失败或被取消。此前e1的prepare失败仍保留，不计入这四轮。

[artifact11429444729](https://github.com/ForceMind/agentbox/actions/runs/37498497962/artifacts/11429444729)
ZIP SHA256实际复核为
`b5d8e8b3684aefde995a8741524565b4ceb8670a413699c144a260cb94e0e4fb`。
39份解包文件逐字节等于ZIP内容，包含四份pytest、collection、imports、package/
editable/pip-check/source/tracked-status日志，以及summary和wheel摘要。summary
SHA256为`021cd33d3786d75c8e839c2aa3a5e3dfe9802da53d331862681b9020d433b6a0`。

本轮实际条件如下，A/B不是发布新功能后的可变分支：

- A1/A2均为main冻结源码a586eaec27984e0632187048cc1b82e7e29552d1，tree
  e5d9309dca123f17f9ff9ee48df0765c332ea451，原5393项完整执行
- B1/B2均为404daae0be4225b30a6e3e71ee239376bd5e6ca6，tree
  238a35a0629e3307560d3a57371e9f2410e3f047；仅本诊断条件ignore尾部65项模块，
  执行原5393项，不称完整资格
- 同一ubuntu-24.04 runner，image20260927.320.1，四套全新checkout、venv和
  pytest进程；四份imports与pytest均明确Python3.13.15、pytest9.1.1
- requirements SHA256为
  1112958277d13d476a6a04449c055c7ef81d82ed3caac57aee3d94ee08071e23。
  四份imports实测75包集合一致，等于冻结74包加editable agentbox0.3.0rc31；
  pip26.2.1、setuptools84.0.0及两个pytest11入口anyio/platformdirs均吻合。
  四份pip check均为No broken requirements found，9个module来源/摘要符合冻结源码
- 四份原始collection均为5393项，目标均为第763项；只归一化原9个runtime_pid
  payload字段和4个listen_pid字符串字段，其余node ID及顺序相同。这是独立
  collect-only预检的逐项证据；实际测量日志确认5393 collected并保留文件级
  进度，没有第二次逐node执行顺序的完整追踪
- 四份source日志均为对应SHA/tree，最后一次tracked-status均为空。CI日志保留
  全部预检、各轮前后source核验步骤，complete表明相应wheel摘要核验也已通过。
  source/status同名日志会覆盖，因此artifact只保留最后一次结果。74项wheel
  摘要与此前官方PyPI核验的实物逐项一致；artifact不含CI wheel实物、venv或
  完整checkout，不能据此声称独立重验了CI现场的全部字节，也不把本轮摘要
  反推为历史旧job的wheel字节

四份dependencies日志均写pip26.2.1为Requirement already satisfied：实际从
sealed wheelhouse安装73个包，pip由fresh venv预置。最终75包map及pip版本已
严格核验，但manifest中的pip wheel摘要不证明预置pip的安装字节；不得称74包
全部由sealed wheels重新安装。这个限制保留在结果中，不修改harness重采。

四轮pytest报告耗时合计1862.50s（31m02.50s）；Actions记录诊断step从16:47:53Z
至17:21:18Z，约33m25s，含准备、进程启动和编排。job从16:47:43Z至17:21:24Z，
约33m41s，artifact上传成功。37min/40min外层限制本轮足够，不能外推为后续
完成保证；原产品与pytest内部预算均保持。

### 四份实际结果

| 条件 | 实际结果 | pytest耗时 | currentness失败note |
| --- | --- | --- | --- |
| A1 | 5305 passed / 88 skipped，exit0 | 487.96s | 无 |
| B1 | 5305 passed / 88 skipped，exit0 | 473.11s | 无 |
| B2 | 5305 passed / 88 skipped，exit0 | 448.83s | 无 |
| A2 | 5304 passed / 1 failed / 88 skipped，exit1 | 452.60s | 原目标失败，见下文 |

四份日志均有5393 collected及相同88项规定skip。A2唯一失败是
test_native_records_hold_admission_through_publication_complete_and_revoke，
在等待READY时收到PATCH_REVOKED EOF。原note记录fixture-checker PATCH_TIMEOUT，
checker/currentness为23/24；runtime-receive PATCH_TIMEOUT的bucket为
none/ge200ms/ge250ms，runtime-currentness亦为PATCH_TIMEOUT。summary中两行
note来自同一异常在traceback和short summary的重复呈现，不计为两个失败。

### 可得结论、限制与停止

事实：在固定75包fresh venv、完整原5393顺序和真实Python3.13.15下，冻结main
仍能出现与旧失败相同的currentness超时/READY EOF表象；同一A条件首轮通过、
末轮失败。此次出现不需要UI PR148改动、新增65项observer安全测试的导入/执行，
或B的新CPU/GC观察器。本轮表象在fresh venv/固定setuptools构建条件中出现，
原global/PEP517环境差异仍限制历史归因，不能据此证明几次失败具有同一根因。

结论不足：预定“两个A目标失败、两个B通过”的模式未出现。两个B通过只能记本轮
两次未复现，不能把1/2对0/2解释为observer因果或修复效果。顺序固定且每条件
仅两次，宿主负载、调度、缓存和时间变化仍未受控；全suite耗时不提供目标250ms
窗口的CPU或GC归因。B仍包含helper导入、fixture接线与采样扰动，本轮没有第三个
完整tail条件，不能单独估计新增65项collection或执行的影响。

A2只有main原有reason/count/budget note，无法进一步区分checker wait/receive/
send；B未失败，所以没有新的失败phase/CPU/GC note。缺少note不是“没有GC”
或“没有调度停顿”的证据。native根因、observer影响和同条件产品red/green均
未闭合，不调整250ms或其他产品/测试预算，不据此实施产品修复。

固定四轮采样已停止；不追加轮次、不重跑旧head，也不通过新文档head再次触发
ABBA。默认六套资格CI继续保留完整测试，包括65项安全回归和编排单测；本次
诊断结果不能替代它们。UI PR148、Release Candidate缓存PR150继续独立处理。
本轮收尾只更新本文和CURRENT_STATE。独立对照审查已核验ZIP、官方job日志、
四份原始结果、源码与环境证据及上述保证缺口，最终记录进入发布并查看新head
普通六套CI；不把诊断完成等同于产品根因修复或发布资格。
