# K2 inert admission journal contract

Revision: `k2-inert-admission-v1`, 2026-10-10. Status: **isolated software candidate;
not a production authority, content contract or real-vendor qualification**.

Checked base: PR171 head `1d6503df3510c54aa0dd8a897a0dcebfdea89b46`, tree
`9e1d41643643e482d462e552ebc2f60fcb030da5`. This candidate has its own branch
and must obtain its own local/review/CI evidence; prior green is not inherited.
不改既有 DB、route、Runtime production composition、安装器、凭据或真实 host。

## 1. 最小有实际用途的下一片

本片实现 **Runtime 请求准入组件 + 有界原子 metadata journal +
隔离 fake-dispatch composition**。证明一条接受记录与 execution 占用先 durable commit，
再进入可能有副作用的 dispatch；重试/并发/取消/重启不得重复调用 dispatch。

这会服务未来结构化消息提交的实际入口，覆盖 K2-T03/T04 的缺口。
只处理请求元数据和合成 content-admission 引用，fake dispatch 是测试内的计数器/receipt，
不启动 CLI，不接受命令、正文、shell、任意 argv、文件路径或新的生产接口。
它是现有 Runtime owner 将来消费的记账组件，不是第二个 process supervisor、Task 队列或调度器。

本轮已批准在本地临时目录实施、测试和独审这一准确范围。
合成 composition 的通过只证明软件状态机/文件提交纪律，不能证明真实 source、authority、
内容相等、host断电耐久、vendor幂等或 exactly-once execution。

## 2. 已读实现及复用判断

| 现有路径/符号 | 可复用内容 | 不可直接继承的保证 |
| --- | --- | --- |
| `agentbox_core/kebui_observation.py`：`ConversationScope`、`parse_scope`、`ObservationStatus` | 16字段精确scope、规范uint64与既有Agent/Project/host校验 | 不是认证/权限；观察状态不等于operation phase |
| `waw_lifecycle.py`：`WAWLifecycleRegistry.dispatch` | 入口序列化、peer/current authority先验、固定动作风格 | `_request_cache`只在操作完成后写入内存，最多1024项；没有durable acceptance，不能移植为此ledger |
| `waw_epoch.py`：`WAWRuntimeEpochStore` | held-dir、owner/mode、NOFOLLOW、flock、fsync+replace、显式bootstrap/普通consume分离 | 只能分配Runtime epoch；不能添加任意请求字段或私自调用生产bootstrap |
| `waw_workspace_attestation.py`：`advance`/`recover_epoch` | 副作用前保存单调floor；旧epoch不能直接变新；恢复需独立exact cleanup证明 | floor不是请求日志；不能把conversation/turn冒充workspace generation |
| `waw_runtime_executor.py`：inflight/reserved/map lock/quarantine | 取消调用方不释放仍运行worker的reservation；old completion不得覆盖new owner | 进程内dict不是持久事务，也不是结构化turn的当前owner |
| `waw_supervisor.py`：`reserve_runtime_attachment`/`runtime_attachment_guard`/cleanup | 同一owned execution的writer与scope前后校验；cleanup不确定时继续占用 | attachment/PTY lease不能改名用于conversation；K2不走terminal write_input |
| `waw_conflicts.py`：`WAWConflictCoordinator` | 共享当前Runtime冲突owner；unknown与active都fail closed | 只处理既有legacy/WAW start，锁是进程内；不自动包含structured/TUI互斥 |
| `a3_admission.py`：`A3TestReadOwner` | default-off且接现有lifecycle/executor的test-composition模式 | A3 content purpose、密钥、selector、nonce不授权S03或消息提交 |
| CP Job/WorkspaceStop record | 阅读其transaction与CAS做法 | Job不能改名Task/消息ledger；CP不能保存prompt fingerprint或取得Runtime执行authority |

下方固定源码链接给出原始实现与测试定位。
现有Runtime stores没有一个通用、已合格的请求事务ledger。
不扩老格式，也不在本片抽取/重构全部安全文件存储公共层。

## 3. 请求、scope 与身份

本片固定一个候选操作：`submit_turn`，只是内部软件枚举，**不添加 Runtime wire action**。

- `request_id`：独立幂等身份，固定 `kreq_` +32 lowercase hex；不是turn ID、认证token或正文摘要。
- 复制完整 `ConversationScope`，逐字段与当前 Runtime-owned captured context 比较；
  owner/auth/Project/binding/host/runtime/API/conversation/generation/turn任一漂移都拒绝新dispatch。
- 固定 `adapter_profile = kebui-synthetic-adapter-v1`；没有 Codex/Claude adapter 或版本支持声明。
- `content_admission_ref`：固定 `ksyn_` +32 lowercase hex，仅合成不可变绑定。未来S03须另行定义非bearer引用。
  不能把任意相同字符串当成“same body”的证明。
- Runtime内部的execution关联来自current-owner port，不能来自Web请求。
  第一隔离profile保守限制同一 `(host_id, project_id, agent_type)` 只有一个占用，
  并把actual execution关联记录在占用内；这是候选限制，不复用WAW ID或制造多execution授权。
  不以auth epoch、conversation、generation作占用分区，避免换tab/会话/epoch绕过旧UNKNOWN。

这里journal保存的是 **active-turn reservation**，不是新授予的execution writer权限。
current-owner port必须另行证明已拥有该execution的唯一structured writer，且无并发TUI writer；
本片测试仅由fake owner模拟这个前提。turn终态释放的是active-turn slot，
不会交还/迁移底层writer lease或自动让TUI附着。production双writer排斥仍需由现有Runtime owner接线，
不能只凭journal里没有active条目就宣布“有写权限”。

幂等比较只在同一个受授权owner域内进行。已登记request_id对应的完整scope、操作、
adapter及不可变content-admission绑定不能改变；匹配返回原receipt，不再dispatch。
同key改变target/描述符是冲突。相同内容换一个新引用不是自动证明同operation。
缺失/过期的内容相等证据返回不可用，不猜测匹配，也不把prompt hash放入CP。

纯metadata候选只能测试“同/异synthetic admission绑定”的行为；
真实 same-key/same-body、same-key/different-body 资格仍被S03 immutable admission/equality合同阻挡。
原始scope永不因重启或重新登录被改写；历史记录的读授权以后在既有auth边界单独接线。

## 4. 原子记录与状态图

每个journal提交同时覆盖request记录及它隐含的execution占用；不能分开两个JSON文件再分别rename。
占用从记录phase推导，不建立相互矛盾的另一份“active表”。

候选phase（与 `ObservationStatus` 分开）：

```text
未登记 --校验/current owner/容量/无writer冲突--> ACCEPTED（durable）
ACCEPTED --fresh guard + durable fence--> DISPATCH_FENCED --一次fake call--> ACKNOWLEDGED
ACCEPTED --同一live owner证明尚未进入dispatch--> REJECTED_BEFORE_DISPATCH（durable）
DISPATCH_FENCED/ACKNOWLEDGED --exact positive终态证据--> TERMINAL（durable）
任何未完成接受记录 --重启/提交不确定/dispatch结果不确定--> UNKNOWN
UNKNOWN --本片无解除或重发路径--> UNKNOWN（持续占用）
```

- ACCEPTED持久化成功是**本地接受**的线性化点，不是vendor已收到。
- DISPATCH_FENCED必须在调用effect port前durable。即使之后实际未发出也可能UNKNOWN，不能安全重试猜测。
- ACKNOWLEDGED只代表固定port确认收到，不代表任务成功，不释放active-turn占用。
- TERMINAL仅在qualified source中可由真实turn事实产生；本片只能使用标明synthetic的receipt。
  记录terminal status复用现有completed/failed/canceled语义；不能从process exit/控制ACK推断。
  `receipt_ref` 是同一次dispatch的关联标识，不是独立terminal证据ID；ACK后的terminal必须
  保持相同receipt。FENCED直接得到synthetic positive terminal时可以首次绑定receipt。
- REJECTED_BEFORE_DISPATCH只用于live owner知道未进入effect的正面证据。
  它必须在同一owner临界区以expected record_revision从ACCEPTED做CAS，
  不可逆退役该operation的dispatch claim，然后才可随durable提交释放active-turn slot。
  排队/取消中的worker在真正进入effect前仍必须成功完成同一个ACCEPTED→DISPATCH_FENCED CAS，
  不得拿早先捕获的claim绕过状态重验。已到DISPATCH_FENCED的记录即使还未实际调用port，
  本片也不允许降为REJECTED_BEFORE_DISPATCH或释放slot。
  首个profile重启时保守把所有未完成接受记录置UNKNOWN，连ACCEPTED也不自动roll-forward。
- 调用方取消/timeout只停止等待，不释放reservation、不取消仍可能执行的worker、不触发重发。
- terminal或明确pre-dispatch rejection的持久化提交才释放该turn占用；UNKNOWN不能由TTL、
  换request_id、换conversation、或观察到CLI“idle”解除。
- 若已观察正面终态但持久化失败，不对外确认完成/释放slot；维持UNKNOWN/store fence。

新消息占用与将来approval/interrupt的控制通道必须分离；本片不实现这些control，
也不修改或阻塞既有WAW exact Stop路径。

## 5. 有界journal

本片使用独立的本地snapshot文件格式；不新增依赖、不修改CP SQLite schema/Alembic。
所有实例只在test `tmp_path` 中创建，production没有构造入口、默认路径或自动初始化。

- 候选预算：最多255条记录，每条完整framed编码及后继更新**预留4 KiB**，header/全局fence
  另保留4 KiB，总上限1 MiB。字段集合与null槽固定，revision最大20位和receipt/terminal的
  最坏增长都计入预留；不能按当前短ACCEPTED记录实际长度超卖容量。
  acceptance前先验证schema最坏编码落在该预留内；容量满也仍能更新每条已接受记录。
  1 MiB限定单份snapshot和逻辑预留；atomic replace写入阶段可同时有旧、新两份，
  **不是整个目录瞬时磁盘峰值1 MiB**，也不承诺磁盘空间预分配；两份逻辑payload
  至多2 MiB，不包括filesystem metadata/blocks或Python对象内存。
  上限耗尽在接受前拒绝，不先dispatch再丢记录。255来自整体预算而非继承现有256项cache资格。
- 第一profile **不自动GC、不设按天过期**；所有receipt/tombstone保留至容量满。
  这是有界安全软件候选，不是最终生产保留策略或无限容量承诺。
  专用journal目录初始化必须为空，后继仅允许admission.json；额外文件或crash遗留tmp
  使store不可用，既不忽略后继续累积，也不自动删除未知文件。
- journal header带独立单调 `journal_revision`；记录带 `record_revision`。
  二者不能充当Runtime epoch、API epoch或Web turn observation revision。
- 持有可信目录FD，验证owner/mode/link/type；同一目录的非阻塞exclusive flock内完成
  read-current/校验/CAS/写临时文件/fsync/原子replace/目录fsync。
  锁冲突立即返回BUSY，不继承现有store无deadline的阻塞锁行为。
- 拒绝重复JSON key、未知字段、超长/溢出/非法类型、损坏/截断/不一致slot记录，错误不回显内容。
- 显式test初始化与open-existing分开。正常open缺journal或corrupt时fail closed，
  不能自动创建空store；未知request的read返回None（NOT_OBSERVED），不等于“从未发送”；UNKNOWN是已接受记录的phase。
- rename之后目录fsync失败是**commit outcome uncertain**；不能按普通未写入处理。
  本实例进入sticky store fence，效果不调用/不重试；重开也不自动重发未完成记录。
- 该fence不能靠换一个store实例绕过。每次open/recovery、以及跨实例看到新snapshot后，
  在返回可当作committed的receipt或允许新admission前，必须在同一exclusive目录锁内
  验证完整snapshot、held file与目录身份，并完成该可见版本的file fsync + directory fsync
  持久屏障及identity复核。单纯JSON重读相等不够；屏障失败则仍全store不可用。
  屏障成功仅使当前已验证版本durable；未完成记录仍按恢复规则转UNKNOWN且不dispatch。
  可见TERMINAL只有经过此屏障后才可作为durable terminal返回/释放slot。
- 单个snapshot的原子性不解决恶意rollback/backup恢复、目标FS断电保证或两个独立Runtime
  进程同时存活问题；这些仍需现有Runtime epoch/启动独占与host恢复契约。

锁序固定为current-owner guard → journal transaction；不能反向取得owner锁。
不持journal文件锁等待异步结果；实际effect边界仍须current owner的精确guard。
`SyntheticCurrentOwnerPort.guard` 的跨await排他是被注入port必须满足的前提。Python
contextmanager本身不会创造生产锁；effect consumer必须在effect边界使用同一个current guard。

## 6. 精确候选代码范围

本候选由PR171另建独立叠加分支；既有169/170/171 head和merge边界保持。

1. `packages/agentbox-runtime/src/agentbox_runtime/kebui_admission.py`：
   请求/phase/receipt、准入记账组件、固定typed端口；复用现有scope validators。
   没有command、route、DB model、真实vendor import或第二个进程owner。
2. `packages/agentbox-runtime/src/agentbox_runtime/kebui_admission_journal.py`：
   有界snapshot codec、held-directory原子CAS与failure fence；格式独立，不改旧store。
3. `tests/unit/test_kebui_admission.py`：状态/幂等/owner/占用负例。
4. `tests/unit/test_kebui_admission_journal.py`：文件原子性/损坏/锁/容量/故障注入。
5. `tests/integration/test_kebui_admission_inert.py`：test-only synthetic owner、admission equality
   和dispatch port，临时目录restart/进程中断；明确无real Runtime/CLI/provider。
6. 本合同随实际实现记录source、选择、运行结果与未验事项；不为只读research单开docs PR。

不修改 `waw_lifecycle.py`、`waw_runtime_executor.py`、`waw_production.py`、WAW writer leases、
API/Worker、现有数据库/迁移、installer profile、S03 wire、CLI启动参数或UI。
未来真正接线必须由现有 Runtime lifecycle/executor owner提供生产current-context/reservation端口，
不能用test port的“current=true”取得权限。

## 7. 有限测试合同

| 组 | 断言 |
| --- | --- |
| Exact scope | 16字段分别替换、profile漂移、旧generation/epoch、await前后revocation均不产生fake effect |
| Atomic acceptance | 记录、slot与fence不能部分提交；接受commit前effect次数恒0 |
| Duplicate | 同key同synthetic绑定并发返回同receipt且effect≤1；不同target/绑定拒绝，不泄漏他域receipt |
| Single writer | 不同key/不同conversation同execution slot拒BUSY；fake TUI占用也拒；同key读结果不算新writer |
| Crash windows | 接受前、ACCEPTED后、fence前后、effect前后、ACK前后、terminal commit前后逐点中断并重开 |
| UNKNOWN | 全部恢复未完成记录不自动调用port；新key/新view/新epoch也不能解除旧占用 |
| Cancellation | waiter取消后在途fake worker仍受跟踪；pre-dispatch拒绝退役claim后旧排队worker不能effect；late ACK仅匹配原记录 |
| Store uncertainty | write/file-fsync/replace/dir-fsync异常、损坏/缺失文件、并发CAS/锁BUSY、超容量全部fail closed；满额时仍可完成最坏大小的既有record更新；terminal rename后dir-fsync失败再换instance不能跳过durability barrier |
| Terminal | ACK非完成；late dispatch ACK不覆盖已证明终态；冲突终态拒绝；终态持久化失败不释放slot |
| Boundaries | journal无prompt/body/hash/error文本/credential；production无import；不新增真实authority或Job/Task队列 |

实际子进程SIGKILL/reopen测试验证的是本地进程中断恢复；注入fsync错误及源码检查
仍不能冒称真实断电/文件系统/host qualification。局部RED/GREEN与独审之后，
候选仍须一次有意义的exact-head CI；不借旧PR171绿色、不重复U1浏览器资格。

## 8. 已批准阶段内是否可做

K2 architecture §6明确接受线性化、crash windows、UNKNOWN与dedup/tombstone是后继软件工作；
§10先要求冻结schemas/aggregate budgets/durable dedup再独立实现，且明确安全schema/design可独立推进。
因此上面**隔离本地合成候选**不需先获得真实host/Secret权限，也不构成K3持久Task。

但§10明确fixed source/wire profile须先冻结才能integration。本候选不关闭该前置条件：
S03 immutable content/equality、真正single-writer/current authority端口、durable生产路径/retention与恢复、
fixed vendor source提取器及真实host/CLI都没有由本研究获准。生产提交路由/DB/真实dispatch继续阻挡。

本轮只按上述独立软件范围推进，生产接线与真实host等前置仍未关闭。

## 固定源码链接

- [当前K2架构](https://github.com/ForceMind/agentbox/blob/1d6503df3510c54aa0dd8a897a0dcebfdea89b46/docs/KEBUI_K2_CONVERSATION_ARCHITECTURE.md#6-message-acceptance-and-unknown-outcomes)
- [WAW内存request cache](https://github.com/ForceMind/agentbox/blob/1d6503df3510c54aa0dd8a897a0dcebfdea89b46/packages/agentbox-runtime/src/agentbox_runtime/waw_lifecycle.py#L666-L737)
- [副作用前generation fence](https://github.com/ForceMind/agentbox/blob/1d6503df3510c54aa0dd8a897a0dcebfdea89b46/packages/agentbox-runtime/src/agentbox_runtime/waw_lifecycle.py#L1320-L1358)
- [epoch显式bootstrap与consume](https://github.com/ForceMind/agentbox/blob/1d6503df3510c54aa0dd8a897a0dcebfdea89b46/packages/agentbox-runtime/src/agentbox_runtime/waw_epoch.py#L51-L135)
- [attestation exact恢复及advance](https://github.com/ForceMind/agentbox/blob/1d6503df3510c54aa0dd8a897a0dcebfdea89b46/packages/agentbox-runtime/src/agentbox_runtime/waw_workspace_attestation.py#L64-L150)
- [既有副作用后失败与restart测试源码](https://github.com/ForceMind/agentbox/blob/1d6503df3510c54aa0dd8a897a0dcebfdea89b46/tests/unit/test_waw_lifecycle.py#L2540-L2577)

链接给出设计复用的source evidence；其测试是否本轮执行，以后文命令及结果为准。

## 9. Fixed vendor evidence informing this candidate

[Codex 0.159.3](https://github.com/openai/codex/releases/tag/rust-v0.159.3) maps to
commit `01fc69f4026735edfdf6789820549727a4867b11`. Its actual `turn/start`
[can steer an existing turn](https://github.com/openai/codex/blob/01fc69f4026735edfdf6789820549727a4867b11/codex-rs/app-server/src/request_processors/turn_processor.rs#L651-L715),
so a new-message busy fence cannot be delegated to the RPC name. Actual
[completion notifications may carry assistant text](https://github.com/openai/codex/blob/01fc69f4026735edfdf6789820549727a4867b11/codex-rs/app-server/src/bespoke_event_handling.rs#L1319-L1346);
this metadata journal does not ingest them. History can
[project stale inProgress to interrupted](https://github.com/openai/codex/blob/01fc69f4026735edfdf6789820549727a4867b11/codex-rs/app-server/src/request_processors/thread_lifecycle.rs#L919-L932),
which cannot resolve uncertain delivery as a proven live cancellation.

The [fixed Claude Python SDK v0.2.163](https://github.com/anthropics/claude-agent-sdk-python/releases/tag/v0.2.163)
explicitly bundles CLI 2.1.286. Its actual tag commit is
`1ef6d8c71bb0e44a6b33fe61497864f21e17fdb7`;
[result types](https://github.com/anthropics/claude-agent-sdk-python/blob/1ef6d8c71bb0e44a6b33fe61497864f21e17fdb7/src/claude_agent_sdk/types.py#L1340-L1377)
allow success with an error or cancellation reason. This is fixed SDK source
evidence, not native CLI execution or an exact-turn authority. Neither vendor
source study qualifies K2 approval revision/deadline, content retention, real
host behavior or the synthetic equality port used by this candidate.

## 10. Candidate qualification (2026-10-10, local)

实际命令均在本候选worktree执行，Python显式设置其 `packages/*/src`、
`apps/{api,cli,worker}/src`、`helper/src`、`installer/src` 到 `PYTHONPATH`；
import provenance已核，不借用另一worktree的editable安装。

- `python -m pytest -q tests/unit/test_kebui_observation.py tests/unit/test_kebui_admission.py tests/unit/test_kebui_admission_journal.py tests/integration/test_kebui_admission_inert.py`：
  **723 passed**，exit 0；588既有scope/观察测试、116新unit、19新集成。
- 19集成包含9个真实SIGKILL/reopen位置、并发duplicate/waiter取消、current-owner切换、
  receipt关联，以及3个await后fake consumer effect-boundary复验。没有CLI或用户正文。
- 独立审查：**91 passed**，其中87项独立实验、4个已有SIGKILL用例另行独立执行；
  另14个source-boundary mutation全部通过。255条ACCEPTED全部完成FENCED→ACK→TERMINAL
  的765次后继提交，256th拒绝且旧bytes不变；跨instance durability barrier与旧claim均复验。
- 最坏counter/最长scope实际编码：terminal framed 1173 bytes，保守最坏后继1189 bytes，
  255条terminal snapshot 299219 bytes，最大revision空header105 bytes。
  UTF-8按bytes计费，非法非ASCII metadata拒绝；固定预留仍为1048576 bytes，不按短编码超卖。
- `ruff check apps packages tests migrations`：PASS；
  `mypy apps/api apps/worker apps/cli packages tests`：403 source files PASS。
  Black多文件调用因本地sandbox禁止其multiprocessing Unix socket而未运行完成；
  对同一Python范围逐文件执行 `black --check --diff <file>`，416文件全部PASS。
- doc-link、secret-pattern、source-boundary、54个workflow action pins和 `git diff --check` 通过。
  既有observation边界测试只增加两个精确inert consumer，并对其余生产源码同时禁止
  observation/admission/journal三种import；原pure-validator依赖断言保留。

实际RED与修复：最初缺module仅证明实现未存在；首次held-FD rename检查因合法ctime变化
误拒绝，保留失败后改为核rename后的held inode。另保全原断言及修前源码：current read
遗漏execution identity；owner port异常自由文本外泄；未知目录库存被忽略。修后均GREEN。
ACK后terminal receipt不可更换是本候选的保守合同收紧，不能冒称原先已冻结的vendor协议bug。
容量测试的首个inode-replace错误码期望、typing/format错误也记录为测试/开发修正，不充作产品发现。

本地全量 `pytest -q -o faulthandler_timeout=120` 的6186项collection已完成，但执行中断，
**没有全量PASS**。两项准确诊断均因本地Unix socket `PermissionError: EPERM`：
`test_prebound_runtime_control_round_trip_uses_consumed_epoch`、
`test_rc8_separate_process_socket_crypto_pty_path`（后者子进程socket失败导致ready timeout）。
没有修改旧测试、解除sandbox限制或使用旧PR绿色代替。本候选发布前后的准确CI终态记录在
其Draft PR；公开仓现有standard runner/workflow不变，六套pull_request无base branch过滤。
新candidate未获自身CI前不称完整软件资格；不为追加CI结果制造docs-only提交反复Actions。

冻结模块SHA256：

- `kebui_admission.py`: `ee4d2254749d01cae1d45daf9756808d41907e629f3a51851c5eb2be623f6b21`
- `kebui_admission_journal.py`: `f613074d1db4147e800e2cc16417da0ed302c495999464e9879cfac84c4f8a7f`

本片仍未验证真实CLI、S03内容源/equality、真实Runtime current-owner/structured与TUI排他、
host power-loss/rollback/双Runtime启动恢复、生产路径与retention、approval或interrupt。
它不能用于宣称U3接入、K3 Task上线或真实消息exactly-once。
