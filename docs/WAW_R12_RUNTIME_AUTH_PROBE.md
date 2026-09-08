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

recvmsg必须拒绝truncated/oversize/undersize、ancillary和第二个record；不从argv/env取字段。
fixed FD角色为0 devnull只读stdin、1 stdout pipe、2 stderr pipe、3 config/placed-ready
SOCK_SEQPACKET、4 generation cgroup directory、5 held vendor executable、6 selected
vendor HOME、7 auth scratch/TMP、8 selected policy directory；无Project/bridge/PTY/tmux/WBR。
逐一核验type/ownership及角色身份，不允许混用或额外泄露Runtime/key descriptors。

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

## Borrow lease与cleanup

复用prepare_start已准备且尚未用于interactive的generation cgroup，不新增另一套cgroup
schema。exact transport一次只借出一个sealed auth lease，dup上述必要FD，借用前后
都要求cgroup empty。native probe返回完整cleanup proof后才归还interactive launch能力。
probe不能删除后续interactive还需使用的cgroup；只清理自身auth scratch/子进程和FD。
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

## 验收

Python验证exact owner/authority/cache、固定argv/env/预算、freshness/clock rollback、
unknown/unauthenticated不启动interactive、resume重新probe、lease归还和取消/关闭。
Linux native与sanitizer用fake vendor证明exec前placement、无Project/PTY/network、
exact FD/env/mount、stdin EOF，以及fork/setsid/ignoreTERM/4097bytes/hang/earlyexit/
malformed record/READY failure下的完整cleanup。原native interactive矩阵不得回归。
真实vendor版本、Codex未登录输出digest、目标kernel能力、profile/native签发属于D/G/H
输入，不由CI fake vendor或production_qualified布尔值替代。
