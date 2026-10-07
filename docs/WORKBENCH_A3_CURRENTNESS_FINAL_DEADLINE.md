# A3 currentness 最终接受时限：先取得真实RED

## 已取得真实RED；最小修正待GREEN

[PR152](https://github.com/ForceMind/agentbox/pull/152) 的test-only head
`98420f82e0e36107e5c49dae510f665590fbb5a6` / tree
`3ce2e2a336cc2b92e1f96d3b60f93dd3646630eb` 已由现有
[Backend run37559042416](https://github.com/ForceMind/agentbox/actions/runs/37559042416)
证明原实现的迟到成功。实际Python3.11.16/job112591895487、3.12.14/job112591895284、
3.13.15/job112591895497各5395 collected，5306 passed / 1 failed / 88 skipped。
唯一失败都是本新增真实UDS用例；reply_before_deadline、final_peer_after_deadline、
returned_late_facts、metadata_received四个见证均为True。不是原READY超时或
未完成注入产生的失败。独立审查已读官方日志确认该RED。

当前后继只在Runtime.current原最终_check_peer之后、facts返回之前新增两行：
若time.monotonic_ns() >= 原deadline则抛PATCH_TIMEOUT。原D创建、较小inherited/
expiry cap、全部I/O/peer proof及except close/finally释放锁保持；没有续期或正向
授权缓存。原peer失败/取消仍先于新时间检查传播；D-1/D/D+1比较和cap复用由源码
检查确认，不另宣称这三个边界已各做真实native执行。119行真实回归逐字不变，
SHA256为`7c4b13992c6aa39deef31a7040189968d878102bd715aa82f1f895132be2fde3`。

该最小修正本地Ruff、mypy394、两改动Python逐文件Black、原3项无socket安全测试
通过；一次多文件Black因沙箱IPC权限受限失败，随后逐文件执行通过，无权限绕过。
新UDS回归仍不在本地运行，必须由后继exact-head完整六套CI给出GREEN。
独立源码、同一真实回归及两份记录复审均CLEAR，无P0/P1/P2；三份官方RED日志
已由独立审查者核对。该复审不替代后继真实GREEN。
无workflow、matrix、pins、预算、GC/GIL、pidfd去重或UI变动。

这是独立的最终接受时限修正。旧main3.13.15的23/24 READY超时根因仍未闭合，
不能把本RED/GREEN当作其因果证明。下方是test-only提交时的合同与验证快照，
其中“未修正/未取得RED”不覆盖本节实际进展；最终GREEN仍待验证。

## 独立问题与当前阶段

基线为main `2b5449ee2832e7173aadf8d54ffa312b13025723` / tree
`ad659b0f2b429f5d529783e24e32db44fcdc1755`。本候选只增加一个真实UDS回归与
记录，生产实现尚未修正，也没有取得该回归的真实RED或GREEN。PR149/151保持
冻结；原23/24 READY超时的可用性根因仍未闭合，不把本问题与pidfd检查去重合并。

[native合同](WORKBENCH_A3_NATIVE_TRANSPORT.md)规定currentness RPC共用不续期的
250ms绝对deadline。[Runtime.current](../packages/agentbox-runtime/src/agentbox_runtime/a3_native_transport.py)
在receive按原D检查并返回后，仍执行payload比较和最终_check_peer，然后直接
返回facts，缺少最终D检查。最后peer proof可能跨过D；5s OBSERVE或30s selector
预算不能恢复这个RPC的原时限。相邻[API._rpc](../apps/api/src/agentbox_api/a3_native_transport.py)
在最终check_current之后明确复查end，提供了现有合同的一致实现参考。

这是“收到及时reply后仍可能过晚接受”的独立缺口；历史READY失败则已经在
runtime-receive报告PATCH_TIMEOUT，两者不能混称同一个已证明根因。

## 一个真实I/O回归

新增test_zz_a3_currentness_deadline.py复用原native_owner和Client，执行真实
socketpair、CURRENT/CURRENT_REPLY、peer pidfd proof及OBSERVE，不替换frame、
wire、clock、NativeChannel、authority或产品deadline，也不修改原fixture。

- 真实receive先完整执行；仅CURRENT_REPLY返回时记录它收到的原D，HELLO不触发
- 下一次bundle实例显式最终_check_peer只注入一次实际sleep，请求时长至多260ms，
  随后执行原peer proof。channel先前绑定的原peer callback保持，I/O内的检查不变
- delay只使最终proof返回晚于原D，不改变D。OS可使实际sleep更长；本测试不保证
  固定总时长，也不把外层5s超时当作所需RED
- 透明current wrapper调用真实实现，保留返回值和原异常，只记录晚返回facts或
  PATCH_TIMEOUT的事实。_resolve会吞掉内部异常，故外部EOF/PATCH_REVOKED允许，
  不要求wire直接携带内部PATCH_TIMEOUT
- 修正后必须内部PATCH_TIMEOUT、没有METADATA，且测试主动close前bundle自动
  关闭、slot清零、server channels shutdown_complete、_current_lock释放；finally
  沿用原Client/owner/authority清理，之后复核两端channel和slot实际已释放

所需旧实现RED必须有明确late-currentness-acceptance断言：reply_before_deadline、
final_peer_after_deadline、returned_late_facts为True，并报告metadata_received。
预期旧OBSERVE在5s外层预算内取得METADATA。早期receive超时、未进入注入点、
peer proof失败或清理错误不能冒充这个迟接受缺口的RED。注入使正确实现拒绝的
目的在于验证最终deadline fence，不证明历史CI为何曾停顿超过250ms。

## 验证与后续顺序

本地AF_UNIX权限限制已知，本批不尝试或绕过，也不以mock native替代真实RED。
本地只执行静态检查、既有无socket安全回归和collect-only；新用例本地NOT RUN。
实际独立archive基线与候选收集5394→5395，原5394项ID/绝对顺序及旧目标763
保持，唯一新项位于5395。原13个动态PID参数经struct bytes与真实pytest编码
前向精确核验，其余5381项原ID逐字相同；项目模块各自来自准确source roots。
collection期间生产/原tests/workflow及所有Python源码字节不变，文档有并行更新。
全量Ruff、394文件mypy、新测试Black、727文档链接与secret/source-boundary/diff
检查通过；既有无socket安全回归3 passed / 66 deselected，不计作新回归通过。
独立回归审查尚待完成，真实RED与GREEN都不能由这些本地检查替代。

独立审查通过后，先发布本test-only head，沿用现有Backend完整workflow取得
真实RED；不更改matrix、pins、权限、依赖、预算或测试命令。记录实际Python版本，
不把3.13 matrix标签当作精确patch版本。相关真实UDS用例属于quality全量pytest，
不是另建native job。未取得所需晚返回见证时，不直接声称RED成立或开始产品修复。

取得真实RED后，才以同一测试加入最小最终D条件并重新完整资格、独立审查。
拟议条件应沿用原deadline，置于最终peer proof之后、facts返回之前，超时沿用
PATCH_TIMEOUT及原close/finally；当前尚未实施。临界D-1/D/D+1、较小继承/expiry
cap和peer失效错误优先级须在后继修正时核验。结果保留真实失败，不重跑取绿，
不顺带去重peer检查、不调整GC/GIL或时限，不推进新UI或生产部署。
