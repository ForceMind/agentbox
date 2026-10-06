# A3 currentness 失败时序诊断

## 范围与已有证据

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

该通过job与旧失败job112299168102的Python3.13.15、pytest9.1.1、完整已安装
依赖版本清单、ubuntu-24.04 image20260927.320.1及setup-python cache key一致。
这些相同并不证明宿主负载或GC/堆状态相同。新增实际是65项：新observer模块
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
