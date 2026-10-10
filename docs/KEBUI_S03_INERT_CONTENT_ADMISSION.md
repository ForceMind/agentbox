# S03 immutable synthetic admission contract v1

Revision: `kebui-synthetic-content-admission-v1`, 2026-10-10.
Status: isolated software candidate; local implementation qualification complete, exact-head CI pending.

Base: PR172 head `659ff785af5e01f4dafc1d0c481680892fddb44b`, tree
`549aac1978f6bb7a94ddb40e845dfd9af102a07e`. Source and old PR heads stay frozen.
实施在独立stack分支；本片是S03前置子合同的软件闭环，不是S03 authenticated source/wire资格。
范围已获既定软件架构委托：current metadata journal→sealed synthetic body custody→fixed fake effect。
不改journal schema、DB、route、WAW/A3 authority/keys/wire、vendor或Runtime production接线。

## 1. 固定profile与实际消费者

1. 保留现有AdmissionRequest与完整16字段ConversationScope、exact execution、request_id、
   submit_turn operation和synthetic adapter profile。content_admission_ref仍为owner发行的ksyn_引用。
   请求/ref/hash/authenticated=true均不能选择更强来源、mint handle或重建旧资格。
2. ingress只接收exact bytes，长度1..16384，严格UTF-8。拒str、bytes-like、subclass、lazy loader、
   空正文、非法编码与超长输入，不执行隐式转换。保留原bytes，不NFC/NFD、trim、换行折叠或重编码。
3. body entry保存immutable bytes及完整descriptor/issuer/PID/opaque composition身份。公开handle
   无任意read/load/body/hash接口；只有固定测试consumer在下文共同临界区同步消费原bytes。
   Python seal/type/对象identity只防误接线，不是真实认证，也不防已控制Runtime的代码。
4. same-key/same-descriptor/same-bytes由原issuer持原bytes作exact equality，复用原entry/handle/ref。
   descriptor或任意byte不同则固定conflict、零新增effect。视觉相似Unicode/CRLF差异不视为相等。
   proof/正文/issuer丢失时不能宣称same-body；已有record只能metadata read，绝不重新mint witness。
5. _validate拆为metadata校验和额外bodyproof校验。read(request)、terminal和pre-dispatch rejection
   只需enabled/exact current scope+execution/record/CAS/既有receipt规则，不依赖body/clock存活；
   不赋予任意历史/跨epoch读取。submit与effect需要当前sealed handle及原issuer witness。
6. journal继续唯一持久operation-state authority；内容owner只持内存custody/equality/witness，
   不另建phase ledger，不落正文/hash/title。UNKNOWN始终按172合同保留execution占用，body费用
   的回收不是execution占用解除。真实S03正文源/跨restart equality/retention仍未资格化。
7. 同批实际fake-dispatch consumer必须最后await之后同步验证并消费entry原bytes，再生成固定
   synthetic receipt。仅计数metadata，不保留或返回正文历史。不得只测validator不接消费者。

## 2. Process-wide budgets

- 所有issuer共用唯一process级pool，最多1 live issuer；fork继承对象/PID漂移不能重置资格，
  旧handle/copy/pickle不能恢复。新的干净进程只能创建新source lease，不能恢复旧accepted witness。
- live+retained canonical entries/handles上限255；每份immutable body≤16384 bytes，retained body
  payload总上限4177920 bytes；只有1份16384-byte ingress staging（含duplicate比较）。
- retained+staging body ledger总上限4194304 bytes（4MiB）。独立validation workspace为最多
  16384 code points/65536-byte Unicode storage payload，加至多1份16384-byte失败decode副本，
  保守合计81920-byte workspace payload；不得偷偷产生额外副本。
- 至多255个与accepted records对应的owned worker slots；accept之前预留slot/可预留bookkeeping。
  await期间只有handle，0 in-flight body copies；fake sink不得扩大保留表或另存正文。
- 这是owned body/validation payload及固定容器项数的预算，不是Python RSS/allocator/header、
  调用者任意内存或secure erase保证。旧borrow尚未退役时不能先清费用再重建issuer超售。
- staging/工作区的并发争抢立即BUSY，不排无界队列；validation、确定未接受的BUSY/conflict等
  finally释放新prepared资源。accepted/uncertain与waiter取消遵下文释放表，不提前释放owned资源。

## 3. Synthetic source expiry

本profile采用source-issued原始deadline，不采用A3或approval TTL。

规范条款：

1. 只有 trusted test-root composition 能创建 source lease，并向唯一 live issuer 提供一次性绝对 `monotonic_ns` deadline；该值不是请求/ref/caller 声明，也不是继承 A3 30 秒或 approval 60 秒 TTL。生产 TTL 仍未定义。
2. clock为exact int（拒bool），范围0..2**64-1；deadline为exact int，范围1..2**64-1，且必须严格晚于mint时的可信now。不得接受float/NaN或隐式数值转换；此整数上界不构成生产TTL或retention承诺。
3. entry 捕获原 deadline；duplicate、重新提交相同 bytes、reconnect、换 admission owner、换 ref 都不得修改 deadline。只有新的独立 synthetic source lease 才能 mint 新请求；不能因此重获旧 accepted record 的资格。
4. 所有 admission/equality/body 使用，以及最后一次 await 后的 effect 边界，都重新读取同一 trusted monotonic clock；`now >= original_deadline` 失效。相等时已过期。
5. clock 抛异常、非法类型/范围或相对于该 issuer 已观察 floor 回退时，issuer sticky-close；后续正常 tick 不能复活。fork 后 PID 不同也立即拒绝，不能清 ledger/rebase clock 恢复旧资格。
6. 过期撤销正文/effect 权限，不伪造 turn 失败或释放 UNKNOWN execution slot。原 exact-current metadata read、独立 receipt ACK/terminal 与正面 pre-dispatch rejection 仍按 journal/current-owner/CAS 处理，不依赖 source clock 或正文存活。
7. 原正文及 witness 丢失后，旧请求只允许 metadata 路径；重新提交同 bytes 不等于 same-body proof。边界应明确其支持的同 scope test recovery，不授予真实跨 auth/runtime epoch 的历史读。

## 4. Atomic check / borrow / effect

无await不足以排除另一线程close/revoke；采用以下共同临界区。

规范条款：

1. 锁序固定为 `current-owner guard → process-wide pool lock → journal transaction`，不反向取得锁。pool/journal 锁不得跨 await。
2. fake dispatcher 的最后一个 await 完成后，在同一个 current-owner guard 与 pool 临界区内完成：exact execution/current scope、issuer/PID/seal/registered entry、原 deadline、accepted witness 校验；借用 entry 原 immutable bytes；固定同步 fake effect；结束借用。
3. 最后 currentness/clock check 是该固定同步 effect 的权限线性化点；check 与 effect 之间不 await、不换线程、不调用任意外部 callback、不重新按 ref 查可变 body。effect 只执行有界同步测试动作，不可保存/返回正文、lazy reader 或能在临界区外再次使用的借用。
4. close/revoke/replacement 使用相同锁序，不能在已授予的同步借用尚未结束时释放费用。仅 pool 内部收尾可以在不取得 current-owner 锁的情况下执行，但不得反向调用 current-owner。
5. 如果实现选择跨 await 的借用，就违反本片的 zero in-flight body copies/只传 handle 合同，必须先改合同；不能以“Python immutable”代替 lifetime 和预算证明。

## 5. Single-composition volatile witness

两个不同journal可给出值完全相等的AdmissionRecord；record值相等不是同一次acceptance，因此必须绑定composition。

规范条款：

1. 唯一 issuer 从首次启用起只绑定一个固定 test-root/admission-owner/current-owner/journal composition；绑定是进程内 opaque identity，不写 journal schema。
2. entry 状态只允许 `prepared → accepted-once → unavailable/retired`；accepted witness 绑定 issuer identity、entry identity、完整 descriptor、exact execution 和原 composition 身份。不能改绑，不能由 record/ref 值相等重建。
3. 第二个 admission owner、fresh/reopened journal、fork/pickle/copy 产生的对象在调用 `journal.accept` 之前拒绝旧 handle/entry；不先在第二个 journal 接受后再拒绝。metadata-only reader 可独立存在，不借此获得正文 witness。
4. 同一 owner 的 duplicate 必须在 accept 调用前已经持有原 accepted witness，且在同一 guard/pool 临界区完成 same-key/descriptor/bytes 比较。创建返回 `False` 永不制造 witness、worker 或 effect。若实际发生并发，第一个 acceptance 的 witness 登记必须先于第二个请求进入该区。
5. 换 issuer 必须先撤销旧 issuer；全进程最多一个 live issuer。重建 pool/composition 不得让旧 entry/witness 在新命名空间重新获得一次 effect。

## 6. Acceptance / witness / worker failure ownership

worker创建/strong retention/callback登记以及journal commit后的_live.add都可能失败；旧候选的无await路径不自动具备本新profile的故障安全保证。

规范条款：

1. metadata/worker slot、staging、entry 和所有可预留的 bookkeeping 在 acceptance 前预留。`created=True` durable 返回后，仍在同一 guard/pool 临界区同步登记 witness，然后建立 worker 的可靠 ownership，最后才使 worker 可以进入 fence/effect。
2. witness、worker 创建、strong-retain 或必要 done-callback 登记任一步失败，都不能 effect。不能依赖“本函数没有 await”来保证 create_task 不执行：eager/custom task factory 可能在创建中启动 coroutine。实现必须有明确未 armed 的 effect gate，或等价能被故障注入验证的顺序。
3. 失败先不可逆撤销本次 entry 的 effect claim，并确保已创建任务未 armed；再取消/退役未运行任务、清理未调度 coroutine。优先对确已取得 live claim 的记录 CAS 到 UNKNOWN；CAS/commit 失败或 acceptance 返回前已不确定时返回固定 unavailable/store fence，保留 execution 占用。不伪造 None、REJECTED_BEFORE_DISPATCH 或未曾接受，不自动重新 accept。
4. `journal.accept` 抛错（包括 commit 后 `_live.add` 等内存错误）绝不 mint witness。即使随后看见 ACCEPTED，也不推断 created=True，不 schedule；恢复后按已有合同 UNKNOWN。
5. release 表必须区分：
   - validation/duplicate conflict/BUSY/确定未接受：finally 释放 staging、decode workspace 和新 prepared entry；不能占满 255 槽形成泄漏。
   - 已接受、ACK/terminal 或明确 pre-dispatch rejection：若保留 same-body equality，原 bytes 与 metadata 继续计费至原 lease 失效；不因重复 submit 增加 entry/handle。也可以失效后删除正文，但此后只能 content_unavailable/metadata read，不能继续宣称 dedup equality。
   - waiter cancellation：只取消等待，仍由原 worker/entry 持有的资源不得提前释放。
   - issuer expiry/close/replacement：立即撤销资格；只有实际借用/worker 对 payload 的所有权已退役后才减 payload/entry 账本。旧句柄保留在 caller 手中也不能经字段/copy/pickle 再次访问已释放正文。
   - UNKNOWN：正文费用可以在安全退役后释放，journal execution slot 仍不释放。这两种 slot 不能混为一谈。
6. pool 跨 issuer 世代仍只有 255 live+retained charged entries、一份 16KiB staging；所有同步清理路径本身也必须有界。单独新建 pool 不能重置仍存活的旧费用。撤销后的 lightweight 外部 handle 不构成新有效 entry；不能保留一份隐藏正文。

## 7. Safe errors and decode workspace

本profile要求固定错误且公开异常链无正文，不能只使用raise safe_error from None。

本地实测（CPython 3.12.14）：对 16,384 字节、最后字节非法的 UTF-8 输入 decode，在 except 内 `raise RuntimeError('content_unavailable') from None` 后：`__cause__ is None`，但 `__context__` 仍是 `UnicodeDecodeError`；其 `.object == body` 且 `.object is not body`，保存另一份完整 16,384 字节 payload。

规范条款：

1. 所有公开失败只输出固定 allowlisted codes；不输出 body/hash、输入 repr、下游 exception text。private decode/helper 以固定结果结束捕获区，释放原异常/临时对象，再于异常处理区外构造/抛出公开错误；检查实际返回异常的 args、cause/context 链和支持的 traceback/log 渲染。
   此规则也适用于 owner guard enter/exit、content proof 和 dispatch port，不能只修 UTF-8 decoder。尤其 `_run` 在 `except` 中调用 journal.read/transition 时，二次 journal 异常会隐式关联原 dispatch 异常；应先退出原异常处理区，再做固定错误/保守 journal 记账，使公开链不携带原 port 正文。不是只设置 `__suppress_context__`。
2. 16KiB 上限在 decode 前校验；staging reservation 覆盖整个 decode/比较/失败清理过程，任何失败释放后才允许下一 staging。未知 bytes-like/callback/subclass 在转换前拒绝。
3. 4MiB 继续明确为 `255 × 16KiB retained + 1 × 16KiB staging` 的 body ledger，不能暗含 decoder 的失败输入副本。独立有界 validation workspace 必须包含最多 65,536 字节 Unicode code-point storage 与至多一份 16,384 字节失败输入副本，保守合计 81,920 字节 payload；实现若产生额外副本必须另计或避免。不是 Python RSS/allocator/header 或 secure erasure 保证。
4. safe errors 不能长期保留 decoder exception/body；fake sink 不收集正文历史。测试只记录有界 metadata/count，并在同步 effect 内验证收到的就是 entry 原 bytes。
5. 不宣称防止已控制 Runtime 的代码、反射或任意 capture-locals 工具读取内存。本片要求的是规定的接口/异常/日志和磁盘边界，仍必须实际验证。

独立保留的合成语义实验与原始日志中，对照确认离开 except 后抛固定错误的 `__context__` 为 None；nested bookkeeping 的固定 store error 在旧写法下仍携带 ValueError 的原正文 args。实验只打印元数据/布尔值，没有输出合成正文。


## 8. Implementation scope and qualification boundary

- 新runtime `kebui_content_admission.py`：synthetic issuer/sealed handle/immutable equality/budget/lease。
- 修改 `kebui_admission.py`：metadata与bodyproof分开；typed handle handoff、accepted-once witness、
  armed worker gate与安全失败记账。保持journal文件及其schema逐字不变；异常窗口通过故障注入验证。
- 新body unit，更新owner unit与现有inert integration消费者；精确扩source-boundary allowlist，
  不允许其他生产消费者。同批文档/current-state记录本profile和实际证据，不堆中间远端头。
- 必测：UTF8/16KiB/exact-byte差异、255-entry/staging/workspace所有边界，same-key并发，
  expiry/非法clock/回退/重复不延期，issuer/handle/第二journal/fork/copy/pickle拒绝，
  owner/source撤权与同步线程race，waiter取消/旧worker，accept/witness/create/retain/callback每窗口
  故障含eager factory，正文proof丢失后metadata仍可读且UNKNOWN不重放，异常args/cause/context/
  支持的traceback日志与journal bytes无正文或hash。实际执行与证据边界见§10。
- 先局部回归+独审，再单一准确head的完整六套CI；发布Draft不merge旧PR或retarget。
- 本片停止于synthetic bytes被真实fake消费者正确消费；下一真实integration仍须独立S03
  domain/version/context/key custody/pins/directions/counters/nonce/relay/lifetime及Python-Web interop，
  fixed vendor operation/source证据、生产current authority与structured/TUI single-writer及真实host。
  本片不授权新credentials/持久访问、真实CLI/host/production接线、发布部署或K3 Task。

## 9. Fixed source references

- [K2 architecture](https://github.com/ForceMind/agentbox/blob/659ff785af5e01f4dafc1d0c481680892fddb44b/docs/KEBUI_K2_CONVERSATION_ARCHITECTURE.md)
- [Metadata admission/journal contract](https://github.com/ForceMind/agentbox/blob/659ff785af5e01f4dafc1d0c481680892fddb44b/docs/KEBUI_K2_INERT_ADMISSION.md)
- [Existing admission owner](https://github.com/ForceMind/agentbox/blob/659ff785af5e01f4dafc1d0c481680892fddb44b/packages/agentbox-runtime/src/agentbox_runtime/kebui_admission.py)
- [Existing metadata journal](https://github.com/ForceMind/agentbox/blob/659ff785af5e01f4dafc1d0c481680892fddb44b/packages/agentbox-runtime/src/agentbox_runtime/kebui_admission_journal.py)
- [A3 sealed source-custody pattern](https://github.com/ForceMind/agentbox/blob/659ff785af5e01f4dafc1d0c481680892fddb44b/packages/agentbox-runtime/src/agentbox_runtime/git_staged_selectors.py#L90-L152)
- [A3 after-backpressure publication contract](https://github.com/ForceMind/agentbox/blob/659ff785af5e01f4dafc1d0c481680892fddb44b/packages/agentbox-runtime/src/agentbox_runtime/a3_content_session.py#L23-L35)

本片只复用custody/检查纪律，不复用A3 purpose/key/pin/selector/records或authority。

## 10. Candidate qualification

2026-10-10 local qualification (CPython 3.12.14), before the new Draft publication:

- Exact final focused set: **815 passed**, exit 0. This is 588 observation tests,
  50 unchanged journal tests, 153 owner/body tests and 24 inert integration tests.
  The integration set includes 9 actual SIGKILL windows. All six source/test input
  hashes matched before and after execution.
- Independent final source probes: **51 passed**, exit 0, plus 12 production-import
  mutation probes rejected. Actual public staging contention, 255 retained
  terminal records, original-byte effect, real eager task factories, fork, thread
  revoke/close, final-await changes, exception chains and post-acceptance failure
  windows were exercised. This is independent source qualification, not merely
  the earlier contract design clearance.
- One independently observed implementation RED was fixed: an already-written
  ACK result survived a final current-owner guard exit error. It now becomes
  UNKNOWN after leaving the exception handler. The regression verifies effect=1,
  occupied execution, metadata readability, and rejection of both old-handle and
  same-byte re-issuance replay. Original RED and exact-source GREEN are retained.
- Earlier baseline probes demonstrated owner/dispatch-secondary-journal exception
  context leaks; safe errors now leave the original handler before public error
  construction or conservative bookkeeping. The separate metadata-read-after-
  body-loss RED is a newly required contract difference, not an assertion that
  the old boolean-content profile had promised authenticated body independence.
  The old-API RED fixture remains historical; current-API equivalent assertions
  pass. A transient missing test import and mid-construction collection failure
  are recorded separately and are not relabeled product failures.
- All-repository Ruff, mypy (405 source files), sequential per-file Black (418
  files), and diff checks passed. Full collection found **6,278 tests**. The prior
  PR172 full local attempt hit existing sandbox AF_UNIX EPERM; this slice did not
  repeat that known blocked full execution. Its own complete remote Python matrix
  and the other required workflows remain pending, not borrowed from PR172.

Commands ran with this worktree's package `src` directories and API/CLI/Worker/
helper/installer `src` directories explicitly in `PYTHONPATH`, not older editable
installs. The focused command was `python -m pytest -q` with
`tests/unit/test_kebui_observation.py`, `tests/unit/test_kebui_admission.py`,
`tests/unit/test_kebui_admission_journal.py`,
`tests/unit/test_kebui_content_admission.py` and
`tests/integration/test_kebui_admission_inert.py`.
Quality commands were `python -m ruff check apps packages tests migrations`,
`python -m mypy apps/api apps/worker apps/cli packages tests`, and
`python -m black --check --diff <each Python file>` under API/Worker/CLI/packages/
tests/migrations. All listed commands exited 0. Actual final remote results belong
in the candidate PR, avoiding an extra documentation-only source head.

Exact SHA256:

- `kebui_admission.py`: `ca713c36104e304a6e6723ab131f962db3251298930d832b99d7f33e9c0c79a0`
- `kebui_content_admission.py`: `6b988fc06e884e35174a62bc1b02704b36acde455cdaa2b04468de3aaa1e0775`
- Unchanged `kebui_admission_journal.py`: `f613074d1db4147e800e2cc16417da0ed302c495999464e9879cfac84c4f8a7f`

The 4MiB plus 81,920-byte observations are bounded payload ledger observations,
not a measurement or guarantee of allocator peak/RSS or secure erasure. No real
S03 authentication, vendor/CLI call, authenticated content relay, production
current-owner/single-writer authority, target host, power-loss persistence,
cross-restart body equality or production retention was qualified.

### Concrete isolated composition

`SyntheticContentIssuer(deadline_ns=..., clock=...)` is explicitly bound once by
`KebuiTestAdmissionOwner(journal, current_owner, issuer, dispatch, enabled=True)`.
Only then can `issuer.prepare(request_id, scope, exact_bytes)` mint a sealed
handle and capture the guarded execution. `handle.request` exposes metadata;
`await owner.submit(handle.request, handle)` performs durable admission and the
accepted-once handoff. A caller-supplied `ksyn_` value cannot mint that handle.

`dispatch.dispatch(request, execution_id, handle)` is an asynchronous synthetic
readiness/fault boundary. It receives no body and performs no effect. After its
last await, the admission owner reacquires the current-owner and pool locks,
rechecks custody and journal CAS, and calls the exact fixed
`SyntheticBodyConsumer` synchronously with the original immutable bytes.
Readiness arrivals are not counted as effects. The consumer retains only bounded
metadata counters and the most recent object's numeric identity, never body or
hash history. The consumer is an actual test consumer, not a vendor adapter.

An owner with `content_admission=None` can perform the existing exact-current
metadata read/receipt paths; it cannot submit. Explicit issuer close revokes
content authority, while `wait_for_idle()` drains retained workers without
authorizing cancellation or replay. A short pool-only critical section reserves
the single process-wide staging slot and releases the pool lock before entering
the owner guard. The staging charge survives validation and cleanup, so competing
ingress returns BUSY rather than queuing behind the validator; nested lock order
remains owner → pool → journal.
