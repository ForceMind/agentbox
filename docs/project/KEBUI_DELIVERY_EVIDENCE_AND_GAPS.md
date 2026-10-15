# Kebui 已交付能力、证据与剩余开发清单

核验日期：2026-10-15。性质：已合并源码和 GitHub 记录的核对、后续开发拆分；
不是新的 S03 认证方案、生产协议或上线准入。本轮由当前主智能体执行和自查，未启动子智能体。

## 1. 基线与本轮交付

Owner 要求先合并 PR175，再接续交接计划整理能力、证据和缺口。
[PR175](https://github.com/ForceMind/agentbox/pull/175) 已正常合并：

- final head：`c7b106ee2f79597f97843e327793d82d1dd308d6`；六套首次 CI success，25 success / 2 规定 skip。
- merge/main：`a346cac8cbd7cb6315f103895198d433015a877a`。
- parents：`fe8fae69204075aa5ade6f837c2283e552431eb2`、上述 final head。
- merge tree 与 final-head tree 均为 `8d9c4f4e4718f4c30ed1fc089c6deab46d0134a4`。
- PR175 仅改四份交接文档，未改变下列应用源码；合并后的准确 main 回归单独记录，不能由 PR 绿推定。

本清单的源码基线固定为该 merge。后续提交只更新本清单和交接入口；软件版本保持
Python `0.3.0rc31` / Web `0.3.0-rc.31`。公开 Release 仍为
[v0.3.0-rc.1](https://github.com/ForceMind/agentbox/releases/tag/v0.3.0-rc.1)。
原工作区 WIP 保留；独立分支 `codex/kebui-delivery-evidence-20261015` 承担本轮文档。
未提交的 authenticated S03 候选不属于输入，未读取、恢复、重写、上传或委派。

## 2. 已交付能力与可复用证据

下表的“已有”表示对应范围的软件/合成资格，不表示真实账号、设备、主机或上线可用。
精确 PR head 便于回读原检查；表内 source/test 链接对应本轮固定基线中的文件。

| ID | 已交付范围与来源 | 已有证据 | 剩余边界 |
| --- | --- | --- | --- |
| E00 | Kebui 标识、U2 既有页面与 U1 有界原型；[产品标识](../KEBUI_PRODUCT_IDENTITY.md)、[U2 收口](../WORKBENCH_UI_U2_CLOSURE.md)、[原型入口](../../design/kebui/README.md)；本轮基线同 §1 | 既有实际浏览器、限定像素、缩放/长文/焦点记录；[公开参考取证](../../design/kebui/PUBLIC_VISUAL_EVIDENCE.md) | 本轮未重拍或重新审图；不是 U0 全部退出、最终品牌或真实聊天功能资格 |
| E01 | [PR169](https://github.com/ForceMind/agentbox/pull/169)，head `e75b900852596dce84de478ec411386bad1c1f89`；[Cromma 合成参考卡](../../design/kebui/reference-board.html) | 参考卡合并和该 head 的成功 CI；既有两张代表图/五宽证据记录 | 纯合成设计；不恢复私人原图，不给会话或认证授权 |
| E02 | [PR170](https://github.com/ForceMind/agentbox/pull/170)，head `b1d46c9b7e80590fc036de4edbf69452ee29adb1`；[K2 架构](../KEBUI_K2_CONVERSATION_ARCHITECTURE.md) | 身份/内容/审批/UNKNOWN 语义与 K2-T01–T14 验收设计；准确 head 六套 CI 成功 | 设计用例不是已执行用例；没有生产会话路由或真实 adapter |
| E03 | [PR171](https://github.com/ForceMind/agentbox/pull/171)，head `1d6503df3510c54aa0dd8a897a0dcebfdea89b46`；[Python 校验](../../packages/agentbox-core/src/agentbox_core/kebui_observation.py)、[Web projection](../../apps/web/src/features/conversation/conversationObservation.ts) | [Python 回归](../../tests/unit/test_kebui_observation.py)、[Web 回归](../../apps/web/src/features/conversation/conversationObservation.test.ts)、[共享向量](../../tests/fixtures/kebui_observation/v1.json)；16 字段 scope、旧 view/attempt、revisionFloor/gap/terminal fences | producer 仅 synthetic；projection 未接正式 UI；tuple 相等不证明认证或写权限 |
| E04 | [PR172](https://github.com/ForceMind/agentbox/pull/172)，head `659ff785af5e01f4dafc1d0c481680892fddb44b`；[admission owner](../../packages/agentbox-runtime/src/agentbox_runtime/kebui_admission.py)、[journal](../../packages/agentbox-runtime/src/agentbox_runtime/kebui_admission_journal.py) | [owner 回归](../../tests/unit/test_kebui_admission.py)、[journal 回归](../../tests/unit/test_kebui_admission_journal.py)、[SIGKILL/reopen 集成](../../tests/integration/test_kebui_admission_inert.py)；durable acceptance/fence、CAS、取消保留 worker、UNKNOWN 不重发 | test owner/fake dispatch；没有生产 single-writer、安装路径、长期 retention 或断电/双 Runtime 资格 |
| E05 | [PR173](https://github.com/ForceMind/agentbox/pull/173)，head `cb90601037e4c4fad17b449f774e6850cd05cb42`；[immutable issuer/consumer](../../packages/agentbox-runtime/src/agentbox_runtime/kebui_content_admission.py) | [body 回归](../../tests/unit/test_kebui_content_admission.py)、E04 集成；原始 immutable UTF-8 bytes、同 issuer equality/witness、deadline/共同临界区与预算 | `SyntheticBodyConsumer`；无真实 source，失去原 witness 后不能凭相同 bytes 恢复，非跨重启正文幂等证明 |
| E06 | [PR174](https://github.com/ForceMind/agentbox/pull/174)，head `fed73bb3d38f7f1dc4cce3c129aa13d028de9eb4`；[S03 synthetic 合同](../KEBUI_S03_SUBMIT_SYNTHETIC_PROFILE.md)、[Web sender](../../apps/web/src/features/conversation/s03Submit.ts)、[Runtime root](../../packages/agentbox-runtime/src/agentbox_runtime/kebui_s03_submit.py) | [Python codec](../../tests/unit/test_s03_submit.py)、[root 回归](../../tests/unit/test_kebui_s03_submit.py)、[集成](../../tests/integration/test_kebui_s03_submit_inert.py)、[Web 回归](../../apps/web/src/features/conversation/s03Submit.test.ts)、[29 场景 runner](../../scripts/check-kebui-s03-submit-interop.mjs) | opaque binary pipe + fixed fake consumer；NX responder possession 不等于 user/browser/session/source 认证；无真实 relay/CLI/output |
| E07 | [S03 源码隔离检查](../../tests/unit/test_kebui_s03_boundaries.py)及 E04–E06 的固定错误处理 | production-import/outward-import mutation、受保护源码 hash、异常正文/traceback 回归；不是仅靠文档声明 default-off | lexical/AST 检查不是恶意同进程代码的 sandbox；未接生产不能证明未来接线不会泄漏 |
| E08 | 原有 [WAW wire](../WAW_WIRE_CONTRACT.md)、[API relay](../WAW_API_CIPHERTEXT_RELAY.md)、[A3 Changes reader](../WORKBENCH_A3_CHANGES_READER.md)、[统一 diff](../WORKBENCH_CHANGES_UNIFIED_DIFF.md)；本轮基线同 §1 | 既有 typed lifecycle/terminal、exact Stop 和受限 Git 内容的软件/CI 证据，各原合同记录实际范围 | WAW terminal 不是 structured turn；A3 patch 通道不是 S03；默认未配置的生产来源仍 unavailable；真实目标独立验收 |

PR169–174 已全部合并，完整 heads/merge commits 保留在 [CURRENT_STATE](CURRENT_STATE.md)。
本轮直接回读六个 PR 的各自 final head，均为 25 success / 2 规定 skip、无 pending；
其 E2E 记录分别为 [169](https://github.com/ForceMind/agentbox/actions/runs/38110120080)、
[170](https://github.com/ForceMind/agentbox/actions/runs/38064892702)、
[171](https://github.com/ForceMind/agentbox/actions/runs/38067418595)、
[172](https://github.com/ForceMind/agentbox/actions/runs/38072050326)、
[173](https://github.com/ForceMind/agentbox/actions/runs/38076166181)、
[174](https://github.com/ForceMind/agentbox/actions/runs/38081511565)。
PR175 的 [Backend](https://github.com/ForceMind/agentbox/actions/runs/38611951201)、
[Frontend](https://github.com/ForceMind/agentbox/actions/runs/38611951091)、
[E2E](https://github.com/ForceMind/agentbox/actions/runs/38611951326) 为上述未变更源码的后续回归证据。
其记录为：Python 3.11 6390 passed / 92 skipped，3.12/3.13 各 6394 / 88；
Web 2267 + extension 6；S03 interop 29；E2E 650 / 270 prescribed skipped，另 21 preflight。
这些是远端既有结果，本轮没有重新执行应用测试、CLI 调用或人工像素审查。

## 3. K2-T01–T14 覆盖与未覆盖部分

“部分”只指下面写明的 isolated 子集。十四项均不能据此标为真实 U3 端到端 PASS。
原用例定义保持 [K2 §9](../KEBUI_K2_CONVERSATION_ARCHITECTURE.md#9-required-adversarial-acceptance-cases)。

| 用例 | 已有子集与定位 | 未覆盖的关键部分 | 结论 |
| --- | --- | --- | --- |
| K2-T01 | E03 scope mutation；E04 `test_sixteen_scope_changes_after_acceptance_block_effect`；E06 context mutation | 真实认证/Project/current owner 与内容发布的生产链 | 部分 |
| K2-T02 | E03 closed decoded objects/u64；E06 codec 非规范/重复字段、非法 UTF-8、超限拒绝 | 真实会话 API/adapter 的完整 operation wire 与错误契约 | 部分 |
| K2-T03 | E04 duplicate/concurrent admission、execution 占用；E05 exact-byte equality；255 容量 | 真正跨 tab/conversation 与 structured/TUI writer 互斥；活动 turn 中审批仍可处理；跨重启正文 equality | 部分 |
| K2-T04 | E04 `test_real_child_crash_never_replays_on_reopen` 的九个窗口；E06 original-journal UNKNOWN recovery | 真实 vendor 发送/ACK/terminal 窗口、生产 store 生命周期与掉电恢复 | 部分 |
| K2-T05 | E03 duplicate/stale/gap/conflict、revisionFloor、terminal 不复活 | 真实 structured content sequence、同 sequence 异正文、完整输出/terminal 来源 | 部分 |
| K2-T06 | E03 old view/attempt/scope；E04 execution replacement；E06 last-await revocation | 正式 App 的 Project/Agent/logout/host 变化与真实会话响应竞态 | 部分 |
| K2-T07 | `awaiting_approval` 仅为 E03 metadata enum，不是审批实现 | request/revision/descriptor/TTL，跨 tab 决策 CAS、冲突与重复回读 | 未覆盖审批流程 |
| K2-T08 | 无 qualified approval adapter | deny/expiry 的真实 vendor ACK、丢 ACK/继续执行后的 UNKNOWN 与 fencing | 未覆盖 |
| K2-T09 | E04 waiter cancel 保留 worker、readiness/terminal 竞态、guard-exit UNKNOWN；E08 既有 WAW Stop | exact structured-turn interrupt、completion 竞态及其 owned process/cleanup；detach/Stop/interrupt 的真实联动 | 部分 |
| K2-T10 | E04 store/worker cap；E05 body pool；E06 raw/message/255 tombstones、deadline、真实 slow pipe reader | production aggregate 多实例/多 realm、output/event/display/control 预算、长期 retention；现有计数不是 RSS/secure erase | 部分 |
| K2-T11 | closed metadata/opaque bytes 不产生聊天 DOM 或审批请求 | 正式正文/工具/链接/路径渲染、伪造状态/审批注入、零意外资源请求 | 未覆盖正文/UI 场景 |
| K2-T12 | E03 interruption/stale 后显式 read；E06 uncertain write 不重发 | 正式聊天 App 的 hidden/offline/reload/Back/Forward、重新认证与显式 reconnect，消息/审批均不重放 | 部分 |
| K2-T13 | E04–E06 fixed errors、正文不入 journal、traceback 负例；E07 import isolation | 实际生产 API/Worker DB、Audit/log/cache/浏览器存储及 vendor logging/retention 的检查 | 部分 |
| K2-T14 | E06 只支持 `kebui-synthetic-adapter-v1` | 固定 Claude/Codex 每个真实操作 tuple、unsupported/stale 拒绝与双 Agent 实机资格 | 未覆盖真实 adapter |

## 4. 实施前必须冻结的接口边界

本节是开发卡的输入/输出要求，不新增可调用路由、Runtime action、枚举或 schema。
精确序列化、接口路径、存储迁移和 production import 只能在对应卡的合同确定后实施。

| 接口责任 | 必需输入/输出与失败语义 | 当前可复用 / 尚缺 |
| --- | --- | --- |
| 会话/operation 只读查询 | 既有 authenticated admin 与 authorized Project；返回 scope/revision、来源/currentness、operation/turn 各自状态与有限 cursor；未知/过期/无权限分开；不返回正文或 vendor handle | E03/E04 可复用；真实 resolver、跨 epoch 历史读授权、retention、真实 API 尚缺 |
| 受控 turn 提交 | exact scope/request/execution 与已合格的 Runtime-owned source/content admission；durable acceptance 先于 vendor effect；same-key conflict 与 UNKNOWN 可查询；不自动重试 | E04–E06 提供合成规则；真实 source/relay/current-owner/single-writer/adapter 尚缺；不能把客户端字符串当 source proof |
| adapter 能力与事件 | 固定 executable/version/profile + Agent/operation 矩阵；Runtime 保管 vendor handle；metadata 与正文分域；turn/revision/sequence/terminal 来源明确，unsupported/unknown/stale 不执行 | [既有固定版本研究](../KEBUI_K2_INERT_ADMISSION.md#9-fixed-vendor-evidence-informing-this-candidate)可复用；不可从 CLI 名字或 TUI 文本推导能力 |
| 审批与中断 | exact scope/turn/request/revision、不可变 descriptor、Runtime deadline 和单次消费；allow-once/deny；interrupt 与 exact Stop 分开；ACK 未知则 fence | [K2 审批/取消合同](../KEBUI_K2_CONVERSATION_ARCHITECTURE.md)已有要求；真实 adapter 行为与执行接口尚缺；禁止 terminal “yes”或 Ctrl-C fallback |
| 正文输出与恢复 | 受准入来源的 bounded encrypted records；sequence/gap/conflict/terminal；回读 metadata 与显式 reconnect 分开；跨刷新不自动提交/审批/Start/Resume | E03/E06 可复用部分机制；真实 output profile、UI owner、认证撤销与恢复尚缺；不借用 A3/WAW purpose |

## 5. 后续独立开发卡与顺序

每卡先交付可审的输入/输出、状态/失败/恢复和验收合同，再实现该卡允许的代码。
默认当前主智能体单独负责；本清单不启动子智能体，不扩大真实凭据、host、发布范围。
“可独立继续”指相应 source/contract 工作，不意味着可以绕过下列依赖直接接生产。

| 卡 | 交付物、写入归属和首次可查看节点 | 前置与验收 | 可独立继续 / 停止条件 |
| --- | --- | --- | --- |
| K2-D01 Fixed adapter contract | 在现有固定版本研究上补 Claude/Codex 的 operation/事件/approval/interrupt/recovery 矩阵、协议来源和拒绝行为；首先交付一份可审合同，代码只在合同闭合后进入 Runtime adapter 模块 | 固定 revision/digest；每操作的输入、ACK/terminal 来源和真实/fixture 证据分栏；不得把 SDK 类型或旧 history 当实际 CLI 资格；对应 T02/T08/T09/T14 | 可先完成只读 source/contract；实际安装/登录/付费调用需具体目标授权；不重做既有研究 |
| K2-D02 Metadata API and operation read | 明确会话/operation/query 接口、授权 resolver、fresh/stale/unknown、分页/cursor 和 restart 语义；先交接口文档与负例表，随后仅实现确定的 non-content 查询 | E03/E04 + D01 的状态来源；跨 auth/runtime epoch、missing ledger、retention 必须先决；对应 T01/T02/T05/T06/T13 | 只读 schema/契约可独立推进；真实状态源/读授权未确定时不加伪数据路由或把 test owner 接生产 |
| K2-D03 Source admission prerequisite | 记录真实 user/browser/session/source、pin/key custody、relay 撤销与 source lifetime 所需准入输入及明确的受限范围 | 真实 S03 source/relay 合同与操作授权先成立；E06 的公开 fixture keys/NX possession 不满足该条件；对应 T01/T03/T10/T13 | 当前只保留缺口和所需决定；不读取/恢复/改写未提交候选，不设计替代来绕开停止边界 |
| K2-D04 Owned execution and submit | 接既有 Runtime owner 的 exact execution/single-writer；已准入 content → journal → 固定 adapter；先有接口/状态图，再实现一条显式 Agent submit/read 流程 | D01/D02/D03；structured/TUI 排斥、跨会话 busy、accept/effect/ACK crash、body equality/retention、UNKNOWN 不重发；对应 T01/T03/T04/T09/T10 | production 接线被 D03 和真实 owner 契约阻挡；不得另建 supervisor、通用 shell 或借 WAW ID 授权 |
| K2-D05 Output, approval and interrupt | 按 D01 能力分别冻结 output、审批、turn interrupt 子合同；逐个实现并独立关闭能力矩阵中的操作，不要求一次开放所有操作 | D01/D03/D04；T05/T07/T08/T09/T10/T11/T13；approval 最长 60s 且不超过 vendor/source deadline，未知 vendor deadline 保持 unsupported；输出不生成伪工具事件 | source/能力不足的控件不可用；approval/interrupt 不从普通 terminal bytes 推断，也不以 Stop 代替 |
| K2-D06 U3 browser and recovery | 正式聊天页面接真实 non-content 查询与合格内容 owner；先展示准确的 unavailable/loading/unknown 状态，再接已资格化的提交/输出/审批 | D02 先支持只读；写/内容依赖 D03–D05；Project→Agent→turn→进展→结果/Changes；T06/T11/T12，桌面/手机、双语言与当前 head 浏览器/截图 | 可在已确定的只读 API 后先接只读状态；不能复用 synthetic prototype 事件假装真实任务；不重复 U1/U2 已交付改造 |
| K2-D07 Target qualification and release | 指定 host/Origin/client/CLI tuples；实际账号流程、断网、服务/主机重启、升级/回退与恢复；独立交付运行记录 | D01–D06 软件准入包、真实目标及凭据/host/发布授权；T14 与 U3 退出证据；精确 artifact/版本/部署身份回读 | 目前缺具体现场输入；绿色软件 CI 只保留 Software/Artifact Evidence，不能发布为已实机可用 |

主顺序为 D01/D02 的合同 → D03 的明确准入决定 → D04 → D05 → D06 → D07。
D01 与 D02 可以按依赖交替推进，不代表启动并行代理。第一张后继卡是 D01 的
固定操作矩阵/接口合同补齐；D02 的真实只读接口是第一处可新增的正式用户可见能力，
须先满足该卡的来源、授权和 retention 条件。遇到未闭合条件，只阻挡相应能力。

K3 durable Task、自动 routing、Agent handoff、长期记忆、协作、generic Files/任意命令、
最终品牌资产与 DNS 不由以上卡自动交付。K3 必须先有自己的 Task/retention/迁移合同，
不能把现有 Job、operation journal 或 CLI exit 改名为完成的 Task。

## 6. 具体未决项与不应重复的工作

1. 固定 adapter 研究已有起点，但没有逐操作的可执行/不可执行矩阵和真实 turn/approval/interrupt 证据；先由 D01 补齐，不将“尚缺实机”说成“尚未研究”。
2. 生产 dedup/tombstone 保存期、满额后的行为、跨重启 equality、metadata 历史读授权和 UNKNOWN 解除证据尚未冻结。现有 255 永久身份/UNKNOWN 占用不能悄悄改成 TTL 自动清除。
3. D03 保持受限；需要明确准入条件与操作范围后才可接真实 source。普通 UI 开发许可不包含读取 Runtime HOME、Secret 或恢复旧候选。
4. 实机阶段需要 Owner 给出/确认具体 host、Origin/client、Agent 版本和账号/恢复操作范围；域名购买记录不证明 DNS/技术控制或上线。
5. 复用 U1/U2、公开 19 图、zoom/focus、PR169–175 和既有模拟测试；只有新改动、具体失败或矛盾才补对应验证，不重复跑未变更基线或另造同功能 fixture。

## 7. 本轮验证、恢复和完成条件

本轮只改 Markdown，必要检查是 `git diff --check`、`python3 scripts/check-doc-links.py`、
`bash scripts/check-secrets.sh`、`bash scripts/check-skeleton-boundaries.sh`、
`python3 scripts/check-workflow-action-pins.py`，以及四键 CURRENT_STATE header、
旧正文保全、十四个用例各一行、来源链接和五文件范围的直接自查。
不新增镜像实现的测试，不本地重跑应用/E2E；自动 PR/main CI 分别等待自身准确 head 的终态。
本轮上述直接检查实际均 exit 0：980 relative links、54 action references / 7 audited
sources；五个 Markdown 文件、旧正文保全、四键 header、十四个用例和七张卡的
唯一行、命名回归源码定位均通过。准确 feature/main CI 终态及本批 merge SHA
只在本批 PR 的最终回读中记录，避免为未改变的软件基线反复增加文档提交。

执行记录和恢复入口：本清单、[CURRENT_STATE](CURRENT_STATE.md)、[NEXT_ACTION](NEXT_ACTION.md)
与本轮 PR。预算未另行指定，沿工具默认；未启用定时后台工作。
恢复先 fetch/read-back 当前 PR/head/CI 与 WIP，不 reset/stash/clean、不 force push。
遇到并发 main 更新按正常 merge-forward 保存双方历史，再按变化范围验证。

完成条件为：PR175 merge read-back、本清单与后继卡可审、本轮文档检查通过、
本轮功能分支准确 CI 通过并按授权正常 merge、最终 main 准确回读与 CI 终态。
本轮完成只表示交接核对批次完成；K2/U3 聊天工作台与真实双 Agent 产品验收仍未完成。
