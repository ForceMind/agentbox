# A3 native peer proof 重复成本：独立 WIP 候选

## 当前状态

2026-10-07 从已验证 main `9f2721ed6dc9c5e6ac41c162463f29674004ad12` 创建独立
`fix/native-peer-proof-dedup-20261007`。这是按 Owner 要求先保存的 WIP checkpoint，
生产代码仍未修改。下方有后继test-only快照；不宣称CI、合并或READY根因修复。

UI [PR153](https://github.com/ForceMind/agentbox/pull/153) 冻结在
`b07ba662a8d98a9ce5c97d4c19ab8ebb57d00709`，E2E299 passed /73 prescribed skipped，
70张新图完成下载校验；其 Backend3.13.15 仍有原 READY23/24 间歇失败：
[run37568112048](https://github.com/ForceMind/agentbox/actions/runs/37568112048)
job112620386589，runtime-receive PATCH_TIMEOUT，none/ge200ms/ge250ms，后继
PATCH_REVOKED，5306 passed /1 failed /88 skipped。UI 未合并，两个分支保持独立。

## 源码支持的有限改变

NativeChannel._check 在 guard=None 时连续执行两次完整 self.check()，中间只有
None 判断，没有 wait、syscall、decode 或业务回调。等价论证限于现有可信proof提供者，
不声称任意带副作用的_current callback等价；任意额外guard仍受前后proof约束。
候选只把第一次 self.check()
移入 guard is not None 分支，保留末尾无条件 proof 和原 absolute deadline 检查。

有 guard 时仍为 peer proof → inherited deadline → callback → finally 恢复
ContextVar → peer proof → deadline；全部等待前、readiness后syscall前、分片、
decode后与readiness-only最终 fence 保持。三个 leases、每个 authority/borrowed
pidfd 均不减少。Runtime.current 独立 final peer proof 与 PR152 最终 deadline
检查原样保留；不改250ms、caps、pins、GC/GIL、Secret或host设置。

完整写入、header/body各一次读取且无额外wait时，D内 proof 的pidfd poll下限可从
90降至48：channel七次_check原为84，最终proof另6；候选为42+6。D建立前另6次，
额外等待/分片可增加次数。这是成本分析，不是耗时或原CI因果证明。

## 必须完成的验证

- 先以真实 socket、pidfd、authority、peer proof 的有界回归取得重复成本 RED；
  计数只包装并调用原 proof，不替换 native。不能把自然 READY 未复现冒称已复现。
- guard callback 撤销真实 authority 后返回，post-guard proof 必须拒绝 I/O。
- guard=None 在真实 readiness 后撤销 authority，send/header/body及readiness-only
  必须拒绝；覆盖同步与异步路径，完整保留原 syscall/partial/decode/idle/cleanup检查。
- 测试与合同先独立审查，最小生产改变后同测试真实 GREEN；完整 exact-head六套CI
  必须终态通过。UI随后只能正常 merge-forward 合入已资格修正，再验实际UI头。

本地受限的AF_UNIX路径不再尝试绕过；真实native证据由既有CI提供。禁止mock native、
预算放宽、盲重跑、ABBA或新观察器。PR149/151诊断分支保持冻结。

## 已知限制

同进程fixture与正式两个exec进程存在调度差异，但没有GIL starvation因果证明。
fixture checker分别给receive/send新建250ms，正式API用同一end，虽是较宽的模型
差异，Runtime始终受原D约束；改严fixture不能解释当前超时。不得通过搬运pre-fork
socketpair冒充真实子进程SO_PEERCRED，不以换测试拓扑掩盖失败。

## 04:54 UTC test-only WIP checkpoint

新增 tests/unit/test_zzz_a3_peer_proof.py，16 cases：1个真实三lease proof重复成本、
_current自身关闭、已撤销authority不运行guard、guard异常ContextVar恢复、4个
guard撤销/关闭同步异步组合、8个无额外guard的readiness后撤销组合。
全部复用实际native_owner/Client三socket握手及pidfd；计数转调原proof，socket
wrapper转调原syscall，无人工延时或时钟替换。body仅允许已完成的1次header recv，
其他撤销路径不允许syscall。固定清理要求slot/selector/leases/channels全部释放。

AST解析、逐文件Ruff和Black通过；native尚未运行，唯一预期RED是已完成proof数2而
目标1，不是自然READY超时。生产文件与main9f仍逐字一致；测试与合同完整复审及
collection/type检查继续进行，按要求先将可审阅源码保存为WIP，不以备份声称通过。
