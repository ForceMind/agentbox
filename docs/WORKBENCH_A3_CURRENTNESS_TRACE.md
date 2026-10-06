# A3 currentness 失败点分类合同

## 来源与有限目标

PR148已合入main `2b5449ee2832e7173aadf8d54ffa312b13025723`，tree
`ad659b0f2b429f5d529783e24e32db44fcdc1755`。该main五套workflow通过，
[Backend run37511667916/job112434107183](https://github.com/ForceMind/agentbox/actions/runs/37511667916/job/112434107183)
实际Python3.13.15仍为5305 passed / 1 failed / 88 skipped，5394 collected。
唯一失败仍为原native READY用例：checker/currentness23/24、fixture-checker
PATCH_TIMEOUT、runtime-receive none/ge200ms/ge250ms，随后PATCH_REVOKED EOF。
这是当前main的新失败；原UI head通过、PR149的ABBA结果都不证明根因已修复。

本候选从该main独立接续，只补既有fixture的失败点分类。生产源码、真实native
流程/断言、收发顺序、全部预算和GC策略不变；不引入PR149的CPU/GC observer、
ABBA或wheel harness，不追加采样循环。新UI工作等待本次有界采证结果。

## 四类标签与证据边界

分类仅在既有checker异常处理中的原record之后、原close之前调用，且要求原
diagnostic opt-in。只沿该异常的__traceback__/tb_next最多8节点，严格校验
ContentError的固定PATCH_TIMEOUT码、原code object identity、完整相邻调用链、
每个唯一调用点的相对tb_lineno，以及最内层_check自己的timeout raise位置。
不根据函数名、错误正文或路径猜测；不遍历f_back、cause或context。

白名单来自本候选审定的[NativeChannel源码](../packages/agentbox-core/src/agentbox_core/a3_native_io.py)
和[Client.checker](../tests/unit/test_a3_native_transport.py)，五条路径对应四类：

| 固定标签 | 可确认的失败位置 |
| --- | --- |
| idle-readiness | checker→wait_readable→_wait→_check，或wait_readable就绪后直接_check |
| receive-wait-deadline-check | checker→receive→_wait→_check |
| pre-recv-deadline-check | receive中_wait返回后、recv调用前的_check |
| post-decode-deadline-check | decode_frame已正常返回之后的最终_check |

只有post-decode-deadline-check证明完整frame已解码；它仍不证明checker已比较
facts、增加计数或发送reply。其余标签不能区分header/body、已收字节、某次循环
进度、耗时或停顿原因。send、额外guard/current/codec/cleanup异常、错误来源或
调用点不符、缺失/多余/过长链、检查故障均为unknown。分类只适用于已审定源码；
后续相关函数改动须重新核对调用点，不承诺抵抗任意进程内人为伪造traceback。

实现不读取locals、wire/body、协议IDs、filename/path或格式化raw traceback，
不新增成功路径时钟、hook、callback或operation包装。遍历中的frame/traceback
引用不写入持久状态；Client只保存一个固定标签，失败note只追加固定前缀和标签。
原reason/count/budget note保持。新增classifier及site note自身的CancelledError、
KeyboardInterrupt、SystemExit均独立隔离；真实operation的这些异常保持原对象
传播，原record与close的相对次序保持。

既有diagnostic recorder、timed wrapper采样/记录和旧note的suppress(Exception)
原样保留；其自身BaseException仍有原有异常/清理限制，本批未将其作为额外修复。
Runtime也可能先关闭opaque，而checker分类尚未写入；此时site note明确unknown，
不等待checker、不承诺每次失败都能取得分类。helper和新单测的import/collection
仍可能影响调度或堆状态，因此不承诺零观察扰动。

## 原序与本地验证

从精确main独立git archive、显式九个source roots重新执行collect-only：
基线5394项，目标第763项；候选5435项，原5394项按原序保留，新41项全部位于
5395–5435，文件为test_zz_a3_currentness_trace.py。只有原13项动态PID字段需
归一化：native auth第293–301项与activation第2382–2385项；其余5381项ID
逐字相同。13字段按实际PID和pytest bytes前向编码精确验证，没有逆解或宽泛
删除参数。基线/候选项目、测试及helper模块分别来自各自source，未混入旧worktree。

分类器五条阳性由真正白名单函数和调用点产生traceback；仅单测中的socket、
select和clock使用内存替身。最终同一份测试与fixture源码下，缺分类占位实现
5 failed，真实分类实现5 passed，各36 deselected；这是分类能力的red/green，
不是native时序故障或产品修复的red/green。新41项另覆盖code/name/site/chain
伪装、截断/过长/受控cycle、敏感字段、三种BaseException及原异常语义。
新41项与原3项安全回归在Python3.12.14和3.13.5均44 passed / 66 deselected。
本地未执行真实socket/native；3.13.5也不冒充3.13.15。

所有原test函数、checker成功循环、旧record/close、旧note块及其余Client方法
的AST对照不变。全量Ruff、395文件mypy、408文件逐一Black、50个action pins、
726个文档链接、secret-pattern、source-boundary和diff检查均exit0。独立复审
在3.12.14/3.13.5各重跑44项，并重新核验fresh collection、13个PID字段、原AST、
源码摘要/tree及workflow唯一matrix变化；两份文档亦已回读，无新增P0/P1/P2。
这些本地证据不替代真实3.13.15候选CI。

## 一次真实资格与停止

本地检查和独立复审后，候选仅进行一次新exact-head的真实资格CI。backend.yml
只把quality matrix的3.13写为3.13.15，保留3.11/3.12及原native job、action pins、
权限、依赖安装命令和所有测试预算；不是新增workflow或ABBA条件。普通六套CI
继续完整执行全部测试，不借旧head通过替代。

若原目标失败，读取固定site及原reason/count/budget证据；unknown如实保留，
不从标签推导GC/GIL/OS调度因果。若目标通过，只记本次未复现。未观测到预期
失败点、准备失败或证据不完整均不自动重测。一次终态后停止采样，保留当前main
和全部历史失败；产品根因仍须源码支持的机制、真实同条件red/green及独立审查
才能闭合。唯一hosted结果记录在PR说明中，不再为结果另提交文档或改变已测head，
以维持一次资格边界。本候选未发布、未合并，不改变host、Secret或生产资格。
