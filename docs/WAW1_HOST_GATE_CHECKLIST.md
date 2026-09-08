# WAW R12 Host-Gate Readiness Checklist

本清单是 R12 目标安装、真实流程与恢复验收的证据合同。它不证明目标主机、客户端、CLI、密钥或生产准入已经存在或通过。当前没有指定 host 或授权现场操作者，所有 **host observation** 均为 `NOT RUN`。

适用范围、阶段依赖和授权边界以 [Production readiness plan](project/PRODUCTION_READINESS_PLAN.md) 为准；五项 gate 的来源是 [Workstation evolution](WORKSTATION_EVOLUTION.md#r12-production-bootstrap-and-host-gates)，R11 的 API/Runtime/浏览器组合约束见 [WAW R11 controller composition](WAW_R11_CONTROLLER_COMPOSITION.md)。本清单不建立第二套准入规则。

## 状态、证据和权限

每条证据只能使用一个状态：`PASS`、`FAIL`、`BLOCKED`、`UNKNOWN`、`NOT RUN` 或 `N/A`。

- `PASS`：在已批准的 exact tuple 上取得可复核的预期观察。
- `FAIL`：实际执行失败；必须保留 case ID、命令、exit code、时间、期望与观察，不能改写成 `BLOCKED` 或未运行。
- `BLOCKED`：已知前置条件、授权或安全约束阻止执行；记录阻断与恢复条件。
- `UNKNOWN`：已有材料不足、矛盾或不可验证；不能当作通过。
- `NOT RUN`：尚未对目标执行观察。本文所有 host observation 初始使用此状态。
- `N/A`：仅当前版本契约明确排除时使用，并说明依据；必需项不得以 `N/A` 关闭。

每条记录至少包含：case ID、gate/requirement、evidence type、exact source SHA 与 artifact digest、OS/kernel/systemd、Runtime UID/GID、CLI/browser/client tuple、执行时间、命令和 exit code、期望/观察、恢复动作和审查结果。只保存允许公开的 identity、version、digest 与 bounded code；不得保存 Provider credential、登录输出、cookie、私钥、WAW key 或真实终端正文。敏感流程默认禁用 trace/video/screenshot；非敏感 evaluation Project 的视觉证据可在已批准范围内保留。

真实 host 安装、Runtime key 创建/轮换、Provider/CLI 登录、客户端安装、付费调用、reboot、production activation、tag/Release、商店或 MDM 分发和支持承诺，都需要各自明确的 target/scope/恢复授权。软件 CI、artifact-only 测试、文档合并或本清单更新不构成这些授权，也不构成 host evidence。

## 准入顺序与资格化启用

R12 顺序为 `A → (B ∥ C ∥ E) → D/F → G → H → I → J`。G 的安装与隔离完成后，可在已批准的隔离 host、非生产 evaluation Project、时间窗口与调用/费用上限内进行**资格化启用**。该启用使用真实 production 组合，并必须满足当次 identity、key、trust 和 isolation 校验；它只为收集 H/I 真实证据。

资格化启用不要求 H/I 已先通过，因而不会形成“验收前先验收”的环；它也不开放业务 Project，不改变 `NOT ADMITTED`，不作生产承诺。H/I 完成后可判定 `Target Qualified RC`。J 在 H/I 通过且有具体生产范围批准后，才决定 `Limited Production`。恢复到管理服务或 `WAW disabled` 是可验证恢复状态，不等同于生产准入。

## v2 资源和 cross-manifest 合同

目标安装必须使用当前 `RuntimeHostInstallation` / `api-host-anchor` v2 契约，不能以旧 v1 manifest 或旧部署记录替代。API 只读取固定 public `api-host-anchor.v2.json`；它不读取 Runtime-private bundle、Runtime HOME 或任何 Secret。installer/root 登记并固定 `runtime_host_installation_id`、revision 与 attestation X25519 fingerprint，Runtime 只核验它们；Runtime 独占 epoch 等运行状态。API/Runtime 读取结果中的 identity、enrollment epoch 和 enrollment state 必须一致。

`verify_api_host_anchor_v2_cross_manifest` 覆盖以下完整的 canonical whole-byte bundle；每个 digest、schema、path 和 cross-pin 都必须在目标上重读核验：

| 类别 | 必须核验的 v2 资源 |
| --- | --- |
| API public identity | `api-host-anchor.v2.json` |
| Runtime-private installer-owned manifest | `runtime-host-installation.v2.json`；API不读取 |
| Runtime验证的root-owned资源 | `project-root.v1.json`、`cgroup-delegation.v1.json`、`executable-inventory.v1.json`、`interactive-profiles.v1.json`、`tmux.conf`、`sandbox-policies.v1.json`、socket policy；具体public/private权限按固定loader与manifest验证，不因组合为bundle而改变 |
| Claude profile | Claude managed policy 与 interactive profile 中的 Claude pin |
| Codex profile | Codex managed policy、Codex requirements policy、Codex managed-config policy 与 interactive profile 中的 Codex pin |

manifest/anchor 必须严格 canonical decode；任一 legacy schema、重复/非 canonical 字段、sentinel digest、identity mismatch 或 pin mismatch 都 `FAIL` 当前 case 并保持不准入。这不是重新开启 crypto 选择：已接受的协议与 crypto 契约按现行文档执行；现场仍须验证其已要求的身份、transcript/payload binding、replay/epoch 与无 plaintext 行为。

## G1–G5 证据矩阵

| Gate | 必须关闭的缺口 | 初始现场状态 | 完成的最小真实证据 |
| --- | --- | --- | --- |
| G1 Production API | 实际 entrypoint/mode、public anchor、singleton、peer/readiness 与真实连接 | `NOT RUN` | 固定 installer-owned mode；API 只读 public anchor；缺项、第二 API、peer/epoch drift、partial startup/cleanup 都 fail-closed。Doctor/readiness 与 host qualification 分开记录。 |
| G2 Runtime provider | filesystem-v2 one-owner graph、fixed executor、Runtime-only channel-key provider、Claude/Codex profile | `NOT RUN` | `_main` 使用受限 production composition；固定 binary/profile/held descriptor 与 inventory digest 一致；key 不离开 Runtime；两种 AgentType 分别通过 readiness，legacy 与 WAW 互斥。 |
| G3 Installed socket/isolation | systemd activation、socket provenance、pidfd、cgroup/namespace/devpts/seccomp/LSM、Stop/cleanup | `NOT RUN` | PID 1 提供严格顺序的 FD 3/4；`LISTEN_PID`、`LISTEN_FDS=2`、`LISTEN_FDNAMES`、AF_UNIX stream、路径、owner/gid/mode、no-follow 与二次 `fstat` 均符合契约；记录 peer、controller/limits、cleanup 和重启结果。 |
| G4 Managed browser trust | 选定客户端的签名/分发、强制策略、extension、Native Host、trustd、撤销/恢复 | `NOT RUN` | 每个浏览器单独回读安装状态、extension ID、Origin/update policy、Native Host path 与 trustd fingerprint；错误 UID/ID/Origin、shadowing、trustd loss 或 revoke 必须拒绝；正常 restart/sleep/wake 后仅在新鲜信任与重新准入通过后恢复。 |
| G5 User workflow/operations | 双 CLI 与所选浏览器的真实操作、返回、Stop、重启/upgrade/rollback、runbook | `NOT RUN` | Claude 和 Codex 分别在批准 Project 中完成官方本地 login/Workspace Trust 的 redacted readiness、input/output、resize、detach/reconnect、exact/repeated Stop；API/Runtime/host restart、network loss、upgrade/rollback 与资源/备份恢复留证。 |

任何 G1–G5 的 `FAIL`、`BLOCKED`、`UNKNOWN` 或 `NOT RUN` 都不能声明相应 gate 通过。G 可完成 G2/G3 的安装和隔离子项；G4 的真实 client installation 同样在 G 留证；完整 gate 仍等待 H/I 的真实流程和恢复证据。

## 现场执行条目

以下是当前应逐项填充的最小清单。除非现场授权已经执行并提供可复核 redacted evidence，状态保持 `NOT RUN`。

| Case ID | Gate | 观察与验收 | 当前状态 |
| --- | --- | --- | --- |
| HG-01 | G1/G2 | 读取 public anchor 与 Runtime v2 bundle，严格 decode 并核验完整 cross-manifest pin、schema、identity、revision、epoch/state 和所有 digest。 | `NOT RUN` |
| HG-02 | G1 | 在固定 production mode 启动 API；验证缺 anchor/依赖、second process、peer/epoch drift 和 cleanup 均 fail-closed，管理 ready 不冒充 WAW qualified。 | `NOT RUN` |
| HG-03 | G2 | 核验 Runtime filesystem-v2 composition、fixed executor、held descriptor、inventory/profile 与 Claude/Codex policy pins；确认 key authority 仅在 Runtime。 | `NOT RUN` |
| HG-04 | G3 | 验证 systemd socket activation 和 control/stream descriptor 的顺序、路径、inode、owner/mode、peer credentials、no-follow/second-`fstat` 与重新 listen 后 identity。 | `NOT RUN` |
| HG-05 | G3 | 验证 cgroup delegation/controller/limits、same-UID write denial、PTY/devpts、setsid/TIOCSCTTY、process group/pidfd、namespace、seccomp、LSM 与 `PrivateDevices`。 | `NOT RUN` |
| HG-06 | G2/G3 | 验证 Runtime epoch 单调性、host revision/provenance、API/Runtime restart、stale ticket/generation fencing、Detach/Stop race 与 cgroup cleanup。 | `NOT RUN` |
| HG-07 | G2/G5 | 验证已接受的 WAW transport：authenticated WebSocket、Noise revision、transcript/payload binding、replay/epoch fence、bounded ABWS 和 API/proxy 无 plaintext。 | `NOT RUN` |
| HG-08 | G2/G5 | Claude：Runtime user 以官方本地流程完成 login/Workspace Trust；仅记录 redacted readiness、version/profile 和批准流程结果。 | `NOT RUN` |
| HG-09 | G2/G5 | Codex：Runtime user 以官方本地流程完成 login；仅记录 redacted readiness、version/profile 和批准流程结果。 | `NOT RUN` |
| HG-10 | G4 | 所选桌面浏览器逐个验证 trust installation、强制策略、extension/Native Host/trustd identity、revoke、restart 与恢复。 | `NOT RUN` |
| HG-11 | G5 | 以非敏感 evaluation Project 验证 Claude/Codex、浏览器 input/output/resize/detach/reconnect/exact Stop；不记录终端正文。 | `NOT RUN` |
| HG-12 | G5 | 执行已批准的 network/API/Runtime/host restart、reboot、upgrade/rollback、disk/resource 与 backup/restore 注入；记录 bounded state、cleanup 和恢复责任。 | `NOT RUN` |

## 客户端支持边界

当前建议的桌面目标是 macOS Chrome 和 Edge，但它们尚未获得受管安装、签名/公证、Native Host/trustd、强制策略或真实交互证据，状态为 unsupported and not qualified；不得以开发者模式、inert MV3、Linux `SO_PEERCRED`/`/run` 假设或普通网页安装替代。Chrome 和 Edge 必须分别通过 G4/G5，不能互相外推。

mobile 目前仅管理 capability：展示状态并发起 exact Stop；不承诺 mobile terminal input、trust/native provider、CLI 登录或完整互动。若扩大 mobile 范围，须先建立新的客户端契约、授权和真实证据。

## 交付与停止条件

现场 evidence package 应附 target tuple、授权范围、case 表、redacted artifacts、恢复 runbook 和未验证项。若 key/Secret 边界、Origin、host primitive、socket owner/mode、client identity、CLI readiness、费用窗口、Stop/cleanup 或 recovery 无法证明，停止该路径并保持 `NOT ADMITTED`；保留现有隔离与证据，按授权恢复到管理服务或 `WAW disabled`。

本清单可在 feature PR 中准备、审查和更新，但不授权真实 host、key、Secret、CLI、浏览器、付费调用、reboot、production 或发行操作。常规软件实现和 CI-gated Git 流程遵循 [project governance](project/GOVERNANCE.md)，且不能替代本清单所需的现场证据。
