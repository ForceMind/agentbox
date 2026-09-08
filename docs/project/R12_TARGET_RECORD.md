# R12 target and decision record

状态：进行中；2026-09-08。依据：[已批准PRP-v1](PRODUCTION_READINESS_PLAN.md)。
这是非Secret输入/软件决定/外部阻断记录，不是host qualification receipt。

## 当前决定与输入

| ID | 状态 | 当前值或决定 | 影响 |
| --- | --- | --- | --- |
| D01 host | UNKNOWN | 已向Owner请求测试host连接名称/SSH别名、发行版与架构；尚未提供 | 不访问/安装未指定服务器；B/C软件不依赖此输入 |
| D02 Origin | UNKNOWN | 已请求最终HTTPS域名；保持现有production DNS规则，不开放private fallback | 外部入口和client部署等待；不阻断固定API profile实现 |
| D03 client scope | ACCEPTED TARGET | Mac Chrome/Edge完整终端；手机管理/exact Stop；具体browser tuple尚未测量 | 目标不等于支持资格；Windows和mobile terminal不在首批 |
| D04 distribution | PARTIAL OBSERVATION | 开发Mac只读检查为macOS 26.2/arm64，`profiles status -type enrollment` exit0：DEP No、MDM No；MCX/Chrome Enterprise Core/商店路径未确定 | 此观察不能证明所有管理路径缺失；Mac真实分发尚未具备证据 |
| D05 Runtime/CLI/Project | UNKNOWN | 目标UID/GID、Project和CLI exact version/digest待目标确定 | 不读取其他HOME或登录状态，不发真实任务 |
| D06 key custody | SOFTWARE BOUNDARY ACCEPTED | Runtime WAW key、Provider Secret、CLI login、Browser installation key与root/CRX signer分离；具体key provider契约正在收敛 | 只用合成材料验证代码；实际key操作未发生 |
| D07 rollback threat | EXISTING LIMIT PRESERVED | 无抵抗管理员完整一致回滚或硬件不可导出声明 | 强要求需具体决定；不制造新支持承诺 |
| D08 recovery scope | UNKNOWN | 未选真实predecessor/备份/故障注入/reboot窗口 | 仅fixture测试；不覆盖既有主机服务/数据 |
| D09 budget | NOT PROVIDED | 未给真实Prompt/费用/目标机资源预算 | 不触发真实付费CLI；Mac定向检查，CI负责完整矩阵 |
| D10 authorization | SOFTWARE APPROVED | Owner批准PRP软件、记录和日常GitHub交付；host/client/key/reboot/production/release具体操作仍分别限定 | 不重复软件批准；不推定已批准外部操作 |
| D11 native/tuple | PENDING SUBCONTRACT | 复用固定native chain；目标ABI/工具链及完整client tuple需D阶段前唯一化 | 不在本轮安装编译器，不假定不同平台制品通用 |

表内decision状态不是G1–G5验收状态；所有真实host/client/CLI门禁仍为NOT RUN。
只读本机管理状态不是配置变更，也不是Mac client qualification。

## 已可执行的软件切片

1. R12-A更新[当前host checklist](../WAW1_HOST_GATE_CHECKLIST.md)，统一v2、双CLI、
   五gate、证据状态及qualification/production区别，现场项保持NOT RUN。
2. R12-B按[固定API bootstrap契约](../WAW_R12_API_BOOTSTRAP.md)实现，文件source不含
   host/Origin/key值，因此不等待D01/D02即可推进；实际安装仍在D/G。
3. R12-C按[C1固定key-port契约](../WAW_R12_RUNTIME_KEY_PORT.md)先实现；已确认
   production auth-isolation仍缺失，C2补齐它与executor后C3才接main，不用测试closure。

## 派工与共享边界

| Agent | 模型/强度 | 责任 | 写入 |
| --- | --- | --- | --- |
| main | 当前会话 | Goal、共享文档、接口决定、版本、Git/CI/merge、集成与恢复 | project docs/契约/后续共享版本，串行 |
| maturity_review | Sol/ultra | API契约规划，后续独立复核 | 只读 |
| deployment_evidence | Sol/high | Runtime provider与失败恢复契约，后续独立复核 | 只读 |
| host_gate_update | Terra/high | 已完成host checklist修订；当前承担API bootstrap | 先仅host checklist；移交后仅API main/new profile与指定tests |
| runtime_key_port | Sol/high | C1固定key port与manifest绑定 | Runtime key/application/authority的最小修改与指定tests |

不递归派工；总并发最多4（含main）。Owner输入到达后更新D项，不重做仍有效的软件结果。
表列可复用agent而非同时活跃人数；规划agent结束后复用槽位启动实现和独立审查。
每次交付记录exact commit/CI/merge，而不是提前写将来的SHA。
