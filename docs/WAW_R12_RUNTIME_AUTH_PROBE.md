# R12-C2 fixed auth-probe contract

状态：2026-09-08软件设计细化；在C1之后实施，尚无host/CLI资格。
本文件沿用[已批准计划](project/PRODUCTION_READINESS_PLAN.md)，只关闭固定认证观察
进程与interactive launcher之间的依赖，不新增通用process/argv/environment接口。

## Authority与执行顺序

同一verified filesystem-v2 authority内部创建一个production auth owner，持有一个
shared `WAWPublicAuthProbeCache`、固定vendor profile、native probe port和cached probe。
production接线不接受外部runner/bindings/cache、synthetic isolation或authenticated callback。
port的`production_qualified`布尔值本身不能证明来源，必须是exact native类型与同一issuer。

Start/Resume先prepare固定transport，不产生interactive vendor/tmux效果；随后借用该
transport已准备的同workspace/generation cgroup与固定FD，执行auth观察。观察命令不要求
已有AUTHENTICATED，因此不经过interactive launcher。只有完整退出/cleanup证据才解析
metadata并更新同一cache。interactive launch前再次核验AgentType、host/revision、
vendor fingerprint和monotonic freshness；Unknown/unsupported/expired不得Start。
resume_after_login重新观察。前后预算还需在Python接线时核对既有Control/API外层deadline。

## 独立native ABI v1

保持现有interactive ABI、7-role enum、WBR offsets、bridge和tmux流程不变。
新增closed `--auth-probe`模式（argc=2），不得把该flag转到现有`run_bootstrap()`。
新ABI版本独立；binary digest由实际后续候选更新，不冒充C1/rc12已含此功能。

FD3接收一个exact 160-byte SOCK_SEQPACKET record，network byte order：

| offset | 字段 | 约束 |
| --- | --- | --- |
| 0 | magic[4] | `AWP1` |
| 4 | version uint8 | 1 |
| 5 | agent_type uint8 | 复用已定义Claude/Codex enum值 |
| 6 | flags uint16 | 0 |
| 8 | runtime_pid uint32 | exact parent PID，正值 |
| 12 | runtime_uid uint32 | exact非root Runtime UID |
| 16 | runtime_gid uint32 | exact Runtime GID |
| 20 | generation uint64 | current positive generation |
| 28 | workspace_hash[64] | lowercase ASCII hex |
| 92 | profile_digest[64] | lowercase ASCII hex |
| 156 | reserved[4] | 全零 |

Runtime parent在FD3的`SO_PEERCRED`必须与record中的PID/UID/GID及当前Runtime身份一致；仅payload字段不能证明peer。发送端在唯一record后执行`shutdown(SHUT_WR)`，helper在placement前等待EOF；任何第二个record、ancillary、truncated/oversize/undersize或未封口连接都拒绝。不从argv/env取字段。
fixed FD角色为0 devnull只读stdin、1 stdout pipe、2 stderr pipe、3 config/placed-ready
SOCK_SEQPACKET、4 generation cgroup directory、5 held vendor executable、6 selected
vendor HOME、7 auth scratch/TMP、8 selected policy directory；无Project/bridge/PTY/tmux/WBR。
逐一核验type/ownership及角色身份，不允许混用或额外泄露Runtime/key descriptors。`profile_digest`
是Runtime sealed lease对已验证profile的声明；native auth helper只验证格式和held executable
类型，不能单独把任意FD5提升为可信profile。Python production owner必须在发出record前将
FD5、AgentType、executable digest与同一manifest/authority绑定，并拒绝不匹配的lease。

helper验证record、parent身份与FD后，先写FD4/cgroup.procs并回读，再验证既有
`ws-<hash>-g<generation>/workload` marker；发送独立placed-ready后才能建立隔离并exec vendor。
helper本身是固定可信bootstrap，vendor第一条指令前必须已处于目标cgroup。
placed-ready为独立8-byte record：magic `AWRP`、version uint8=1、status uint8=1
(`PLACED`)、reserved uint16=0；不能复用interactive的`AWR1/RUNNING`身份。

## 固定隔离

复用held exec、FD校验、basic limits、no_new_privs、pidfd/reap、user-map、mount/reanchor、
双层user/PID namespace、私有proc及Landlock/seccomp基础原语。
另建closed auth mounts/landlock/seccomp/launch函数：不绑定Project、不运行bridge，
不创建PTY，不向caller暴露mode callback/argv/env/path。

vendor argv仅Claude `auth status`或Codex `login status`。HOME/XDG/state/PATH/LANG/
LC_CTYPE依固定auth profile；TMPDIR/cwd映射到隔离内`/run/agentbox-waw/auth-probe`，
TERM=dumb，不继承Runtime完整环境。selected HOME/policy只提供所需受限视图，禁止
通过scratch、proc或继承FD访问Project、其他vendor HOME、Runtime key或Provider Secret。
auth namespace增加CLONE_NEWNET、无接口配置，auth-only seccomp禁止network socket/
connect/bind/listen/accept/send等。需要联网才能status的vendor版本保持unsupported，
不得在实现中临时开放网络或更换认证方式。
auth scratch anchor`/run/agentbox-waw/auth-probe`必须由host provisioning创建为
root:root 0755；helper在进入第一层user namespace前（初始namespace，uid 0有意义的
上下文）fail-closed校验其type/ownership/mode，namespace内仅复验type/mode。生产
provisioning必须保证`/run/agentbox-waw`不被非root（含Runtime uid）写入，否则该
anchor约定的安全意义减弱；此前提属于D/G/H host资格化范围，不由CI synthetic证据替代。
目标Project root若存在必须被auth mount遮蔽；测试应放置固定Project canary并确认不可见。

## Borrow lease与cleanup

复用prepare_start已准备且尚未用于interactive的generation cgroup，不新增另一套cgroup
schema。exact transport一次只借出一个sealed auth lease，dup上述必要FD，借用前后
都要求cgroup empty。native probe返回完整cleanup proof后才归还interactive launch能力。
probe不能删除后续interactive还需使用的cgroup；native不删除host source scratch目录或vendor residue；Python sealed lease owner在收到
cleanup proof后独占清理source/残留，并在归还interactive launch前证明目录为空。
不确定cleanup则poison该transport/owner，不能交还或复用launcher FD。

从spawn到正常退出共享5.0s；stdout+stderr总4096bytes，第4097字节触发overflow。
两根pipe并发drain；固定TERM grace 0.25s，之后pidfd终止helper与cgroup.kill处理后代。
caller取消先shield cleanup再传播；需要direct child reaped、pidfd terminal、pipes EOF/
closed、cgroup populated=0以及scratch/FD的确定清理。close不确定不重复使用FD号。
raw输出仅在Runtime port→parser内存路径，错误/log/Audit/Job/DB/diagnostics均无正文。

## 组合与并行边界

Native owner：protocol header、waw_native.c/.h、waw_isolation.c/.h、pane_bootstrap.c
与独立native auth tests。Python owner：vendor probe native port、auth owner/cache、
fixed transport的sealed lease与production callback移除、executor/bootstrap/最终main接线
及unit tests。C1共享Python文件交付后才开始该部分写入；root集成parity/workflow/版本。
具体lease如何传入现有observe接口必须先保证：cache hit也释放unused lease、异常/取消
仍有owner、同一workspace最多一个probe、Stop/Start并发不复用busy cgroup；不得用全局
可替换callback或未受约束map注册代替sealed ownership。Native-only代码不单独宣称C2完成。

实施状态（2026-09-15，`codex/r12-auth-lease`）：sealed auth lease（`waw_auth_lease.py`）
与sealed production auth owner（`waw_auth_owner.py`）已按本节语义实现：一次一个lease、
借用/归还前后cgroup empty、release同步ceremony、cache hit走完整release、不确定即
poison lease+transport+owner、production callback已从`from_verified_execution_authority`
移除（只收exact owner且authority绑定校验）。接线约束留给后续slice：`probe_with_lease`
的cache hit返回原checked_at，executor `_fresh_auth`的echo校验须用始终live的`probe()`
或为lease路径另行放宽；scratch嵌套非空即poison的严格性须由下一slice的fake vendor矩阵
确认profile不产生嵌套残留。Python native port（AWP1 spawn）、executor接线、五秒操作
所有权与C3 main仍未开始。

实施状态（2026-09-15，`codex/r12-runtime-main` C3-a）：生产组合闭环已实现并经独立审查
PASS：owner 新增一次性 `bind_native_probe_path`（解开 owner↔factory↔process_port 构造
循环：owner 先建、port 用 owner 构造、factory 用 port 构造、owner 再 bind，校验与构造
kwargs 双入口等价互斥）；factory vendor digest 改用 manifest inventory 条目 per-entry
`max_bytes`（真实 vendor 二进制远超 64KiB 默认值）；`_compose_verified_v2` 与
`RuntimeExecutorServer` fixed 组合的 auth_probe 钉从 `WAWCachedPublicAuthProbe` 换成
`WAWProductionAuthOwner`（dev `_configure_waw_auth` 路径不变）。API 侧信封已核对：
`WAWControlClient` 新增 per-action `action_timeout_seconds`，生产组合对
`workspace.workspace.start` 用 9.0s（server 8.0s 信封 + 1.0s 传输余量），其余 action
保持 2.0s（决策 `R12-AUTH-PROBE-BUDGET-V1` 闭环）。profiles 生产可行性结论：
`profile_id`/`agent_type`/`probe_id`/`parser_id`/`executable` 可派生（仓内常量+manifest
entry.path）；`vendor_version` 与 `codex_unauthenticated_output_sha256` 必须外部输入
（D/G/H），缺失时组合 fail-closed，无 synthetic 回退。C3-b（生产 executor provider 与
`_main` 生产分支接线：activated sockets、static key、epoch store、provider、application
builder）仍未开始。

## 验收

Python验证exact owner/authority/cache、固定argv/env/预算、freshness/clock rollback、
unknown/unauthenticated不启动interactive、resume重新probe、lease归还和取消/关闭。
Linux native与sanitizer用fake vendor证明exec前placement、无Project/PTY/network、
exact FD/env/mount、stdin EOF，以及fork/setsid/ignoreTERM/4097bytes/hang/earlyexit/
malformed record/READY failure下的完整cleanup。原native interactive矩阵不得回归。
真实vendor版本、Codex未登录输出digest、目标kernel能力、profile/native签发属于D/G/H
输入，不由CI fake vendor或production_qualified布尔值替代。
