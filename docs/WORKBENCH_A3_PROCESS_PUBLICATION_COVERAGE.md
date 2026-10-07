# A3 分进程 publication / COMPLETE 保留：新增测试合同

## 当前范围与状态

2026-10-07 从main `1ce060f57afde6f7369e815a969aeb03eab2b012` 建立独立
`test/a3-native-process-publication-20261007`。本批只新增现有exec fixture的默认关闭
断言见证与一项分进程完整场景，不改生产代码，不替换、跳过或削弱原测试。
原 `tests/unit/test_a3_native_transport.py` 与 `test_a3_native_guard_budget.py`
必须逐字保留，包括COMPLETE后的current=False与8ms checker/独立loop/大patch/
LIVE heartbeat回归。UI PR153冻结在621402c，不增加UI范围。

PR154的两行重复proof消除有真实成本RED→GREEN和合格head，但main1ce的3.13.15
仍原READY23/24超时（Backend37576490608/job112646443732）。这证明该优化没有
消除历史间歇问题，不能继续以串行微调冒称根因修复。现有UI整合头六套成功，
实际3.13.16不覆盖main3.13.15失败。本新增覆盖不预先声明修复或合并资格。

## 复用的身份与作用域

只复用 tests/a3_native_fixture.py 的两个真实exec child与既有control pipe。
Runtime监听器在自身进程建立，API child新建并connect三个AF_UNIX stream；实际
SO_PEERCRED/pidfd身份保持，不搬运pre-fork socketpair。API不得导入Runtime代码，
不新增listener、权限、生产hook、任意object/path/command访问或诊断框架。

见证仅在显式测试场景启用，默认模式的行为、状态字段与现有用例不变。它们读取
真实方法的参数/返回值完成本地断言，完整转调原方法并保留原异常；不替换native、
插入等待、缓存授权或改变任何原deadline。输出只允许固定bool/有界计数，计数
饱和必须使验证失败，不能让多个饱和值伪装相等。禁止正文、ciphertext、key、
路径、身份值或任意异常文本进入新增控制结果。

## 新场景必须证明的原有不变量

1. 原modified.txt/staged secret-canary内容与固定nonce；OBSERVE结束后正式OPEN。
2. 真实READY不超过5s，立即确认admission active=1；LIVE sequence/challenge精确相等。
3. 每个record发布前admission仍1；对应CHECKED和PUBLISHED→ACK逐次精确匹配
   record sequence/SHA256，并验证计数涵盖所有真实records。
4. 真实Noise/Git内容解密包含原canary；不能用另一个默认文件替代此检查。
5. API实际收到NativeKind.COMPLETE不超过1s，先见证COMPLETE，再确认active=1、
   active_bundles=1、burned_nonces=1。仅PATCH_END或browser ACK不是COMPLETE。
6. 完成后100ms真实后台CURRENT/REPLY次数增长，admission仍1；查询见证本身不得
   发起currentness/LIVE或刷新授权，不能用主动browser.current替代后台增长。
7. 实际session撤销后不超过1s清理admission/bundle，nonce仍烧毁；不采用旧helper
   默认3s或control RPC默认10s无声放宽，接受结果时也必须检查同一绝对deadline。
8. 原有child/descriptor/authority清理完整、正常退出有证据；强制终止兜底不计为
   成功清理。真实API撤销关闭checker，负布尔reply仍由未变旧测试独立保留。

NativeBrowser.complete当前仅等PATCH_END；本场景须增加明确COMPLETE接收见证。
新增测试不能使guard-budget companion原monkeypatch失效；两个旧源文件不改。

## 验证与交付

先检查默认关闭、固定输出、计数边界与脱敏的纯测试，再独立审阅每条不变量映射。
本地受限AF_UNIX不绕过；真实分进程执行由既有CI完成。所有当前有效源码按阶段
及时提交WIP，不等待完整CI才备份，但WIP或静态检查不冒称native通过。

受控supervisor load不是本新增覆盖的前置条件；本批不做负载调参、强制GC、GIL/
亲和性或时钟变更、ABBA、重试到绿色。若以后单次负载观察没有真实在途RPC与
原250ms重叠见证，必须标为证据不足，不能宣称历史root cause RED→GREEN。

当前仅合同checkpoint，源码实现/真实新测试/资格处置待完成；不发布或部署。
