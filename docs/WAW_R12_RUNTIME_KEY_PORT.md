# R12-C1 Runtime static-key custody contract

状态：按已批准PRP软件范围冻结，2026-09-08；实现进行中，未激活。
这是R12-C的第一独立软件切片，不代表C2 executor/auth-isolation或C3 production main完成。

## 现有缺口与拆分

现有`WAWRuntimeStaticKeyPort`仅有preflight/take/read/close，未把实际X25519 public
fingerprint与构造executor authority的同一CrossManifestPinV2绑定。另一个独立缺口是
production auth-isolation probe尚未实现，不能靠synthetic port或always-true callback
拼装可用executor。因此顺序为C1 key custody→C2 fixed auth isolation/executor→C3 main。

## 固定文件与authority

- production factory不接受path/env/Settings/外部factory参数。
- 固定路径：`/var/lib/agentbox-waw/keys-v1/static-x25519.key`。
- 进程必须是系统中exact `agentbox-runtime`的非root身份；固定passwd/group解析失败就拒绝。
- root到`/var/lib/agentbox-waw`使用逐级held/no-follow权限核验；顶层WAW目录沿用
  `root:agentbox-runtime 0750`，`keys-v1`为Runtime UID/GID `0700`。
- leaf为Runtime UID/GID `0600`，regular、single-link、恰好32 bytes的raw X25519 key；
  本批只读、不创建、不替换、不迁移、不轮换，缺失即失败。
- descriptor持有和每次读取都验证目录entry/parent、owner/mode/type/link/identity和size；
  bounded pread前后复核，替换或原地修改均拒绝。生产不使用fixture path/seam。

## 单次所有权与manifest绑定

现有协议增加`bind_authority(authority)`；具体port内部不向API/Worker或package顶层导出。
`take()`转移同一owned FD并使原对象consumed；重复take拒绝。preflight不等于绑定。
`WAWVerifiedExecutionAuthority`仅增加public只读fingerprint属性，来源仍是同一个已验证
CrossManifestPinV2，不能由独立字符串或第二次加载的manifest伪造。

精确顺序：key take/preflight→验证manifest-v2并issue该authority→key bind→验证derived
public fingerprint→executor creation/epoch transaction commit→stream composition。
可在受限内部executor-factory wrapper中先bind再创建executor，但不能新增生产注入端口。
fingerprint使用既有协议的派生规范与constant-time compare；key mismatch不提交新epoch，
也不创建stream。已提交epoch后失败保留其单调性并按现有construction cleanup处理。

private_key在bind前、source consumed后或close后拒绝；authority只能bind一次。
每次读取重算fingerprint并复核identity。close幂等；关闭不确定为sticky failure，不盲目
重试可能已复用的FD；application不能因此报告clean或释放仍被使用的provider。
Python内存模型不保证硬件擦除，不声明zeroization。repr/error/log仅状态或bounded code，
不输出key/public key、fingerprint片段、payload或私有路径。

## 边界、所有权与验证

C1不改Runtime `_main`、installer、systemd、Provider Secret Store、Browser Trust，
不创建初始化/轮换/purge命令，不执行真实key操作。后续初始化必须由Runtime authority
在具体获准目标上执行；Root Helper不获得key authority。

Sol/high worker负责新的`waw_static_key.py`、Runtime application/authority的最小接线、
必要bootstrap时点修正与对应tests；主智能体负责文档/版本/CI/Git，独立Sol复核。
与API worker文件范围分开；不引入空executor provider作为“已实现”成果。

必须验证：size31/32/33、missing/partial read；uid/gid/mode/parent/symlink/hardlink/
FIFO/device；open/read/preflight/bind后的replace/in-place drift；错误authority/fingerprint；
beforebind、doubletake/doublebind/afterclose；close/cancel/构造失败；key mismatch前后
epoch/stream/资源状态；canary不进入repr/error/log。Mac只使用合成fixture；真实Linux
权限与host key custody另需G/H证据。C2/C3依赖C1及固定production auth-isolation完成。
