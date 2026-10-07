# A3 currentness 最终接受时限：先取得真实RED

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
