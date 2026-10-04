# AgentBox Roadmap

## 2026-10-04 A3 Changes-page staged reader 软件候选

已显式 fetch/read-back 核对 #142 merge `b7dd51d3288022f12604656515aafe7e11a00d3e`，
tree `2cdfa72e7ca99b57312dadf156af1b74d82db15e`；#142 exact-head 六套
workflow 均 SUCCESS。旧 staged/readback worktrees 全保留，新独立
`feature/s02-changes-a3-reader` 接续 [Changes-page 软件合同](../WORKBENCH_A3_CHANGES_READER.md)。

本批加入独立 staged-observation metadata route、purpose-specific A3 trust port、
显式点击/完整 END 后 inert text 展示和 page-owned lifecycle。API 新边界仅用 typed
metadata port，不导入/执行 Runtime；生产 source 默认缺失且拒绝注入，正式页面无
A3 adapter/pin 时明确不可用。实际 Git→API route→existing admission→opaque relay→
Web DOM 将由 isolated fixture 与新 exact-head CI Chromium 验证；此刻浏览器尚未运行，
不称生产可用或真实 host PASS。
无新 listener、WAW trust fallback、真实 key/pin enrollment、安装激活或发布。

本地检查与独立 source review 已完成；新 exact-head CI、merge/read-back 尚未运行，
不能使用 #142 的 CI 替代本候选证据。后续为候选审阅、Draft PR 与新 CI。
下方旧批次边界保留为历史，不覆盖本合同已批准的 source-only 页面接线。


## 2026-10-04 A3 admission/lifetime software continuation

#141 已正常合并为 `1c2befb9be47c8f7181accd67965e4187fcf06cf`，tree
`9c79cb24a121ff7641e191547a10823df3e1caef`；exact-head/post-main 六套首次
CI 全 SUCCESS。当前独立批次为 [default-off admission 与 crypto v2 lifetime](../WORKBENCH_A3_ADMISSION_LIFETIME.md)：
复用现有 API session/READY 与 Runtime binding/lifecycle owner，专用 synthetic
key/opaque TEST wiring，以及原始 selector lifetime 的 authenticated remaining-ms
桥接。plaintext/context/AAD v1 不变，无生产 route/key/pin/host/UI 激活。
候选需完成源代码独立审查、全量适用检查和新 exact-head CI；下方为历史批次。


## 2026-10-04 A3 独立加密单次读取

#140 exact-head/post-main 六套 CI 全 SUCCESS，main `57cb8cd`。本批将已有
reader/selector/codecs 组合为 [inert encrypted single-read](../WORKBENCH_A3_ENCRYPTED_SINGLE_READ.md)：
原始 expiry、owner nonce ledger、fresh NX、opaque-only 软件 relay 与 Web 完整
验证。actual synthetic fixture 不等同 production authentication/relay/UI；后续
生产接线和真实 host/client 资格仍需各自证据。下方阶段陈述保留历史。

## 2026-10-04 A3 独立协议软件候选

#139 已合并到 `587fe8eabf7e5d5e4d3a561091ec00c3e9f40881`，exact-head 与
post-main 六套 CI 均 SUCCESS。当前独立批次为 [content schema/codecs](../WORKBENCH_A3_CONTENT_CODECS.md)：
专用 context/AAD bytes、四类严格消息、单次 transcript 和跨语言向量；不实施
或开放 encrypted Runtime/API/UI path。完整 PAGE 16 KiB 限制不变，超容量先
TOO_LARGE；真实 host/client 验收继续 NOT RUN。后续 crypto/admission/relay/UI
按合同与证据分别交付，旧批次范围仅作历史。

## 2026-10-04 下一项软件边界

PR #138 已合并到 `35d25bdccbb9311a57fc06a0683f4f60bf50dd9c`，#117 因保留
历史而间接合并。当前仅推进 Runtime-only short-lived staged selectors：versioned
internal observation、完整 snapshot digest、可信 formal Project/session/epoch 绑定
及同一 held view 的校验/读取；生产 resolver、RPC、encrypted channel 与 UI 均未组合。
详见 [当前状态](CURRENT_STATE.md) 与 [reader/selector 合同](../WORKBENCH_A3_STAGED_READER.md)。
此段接续并覆盖下方 reader-only 的历史批次范围，不扩大真实 host/device/Secret 或发布权限。

## 2026-10-04 软件续建优先级（覆盖下方历史冻结）

Owner 已明确暂缓真实目标测试、继续开发并要求列出后续计划。真实
host/device/login/reboot/upgrade/rollback 仍为 **NOT RUN**；软件/CI 不能替代
现场验收或授权发布。当前基线为 PR #136/#137 合并后的
`7fa54c3f5e3ce7e96c3d2cb33828c759665d81d2`。
本批仅复用 Draft #117 接续 S02 Runtime-only staged reader、安全修复和必要
验证，不新增 selector/content channel/UI/Files 编辑。具体边界与事实见
[当前行动](NEXT_ACTION.md)；该最新 Owner 顺序覆盖下方禁止 #117/S02 的
历史冻结，其他 S00–S14 依赖和安全边界保持有效。


## 2026-10-04 接续核对与真实首装准备

已重新核对 PR #136 的 documentation-inclusive head
`d6ee8c7c9635e2b5ecd58f18048fa8c1aaa59474`：Backend、Frontend、Security、
Deployment、E2E、Release Candidate 六套 workflow 均为 terminal SUCCESS。
其中 24 jobs 成功、2 个历史 rc8 jobs 按版本跳过；不能把 skipped 写成通过。
[Backend 证据](https://github.com/ForceMind/agentbox/actions/runs/37166599345)。
Owner 已明确授权继续操作，PR #136 已正常合并，main read-back 为
`7d0521556727d64c80d02d69aea7b9d9b06432af`；父提交与已验证 PR head
一致，tree 与该 head 完全相同。此快照时 post-merge CI 尚待终态；
实时 GitHub 状态优先于本记录。

`setup-fresh-waw` 已完成软件组合与恢复逻辑，不再重做 #131/#134/#135，
也不再把 composition 当成待开发功能。下一实质阶段是同一固定 candidate 的
真实首装资格化，详见 [当前行动](NEXT_ACTION.md) 和
[目标输入记录](R12_TARGET_RECORD.md)。当前没有指定或激活真实目标服务器；
公网 HTTPS、管理员初始化、真实双 CLI 登录/turn、物理客户端、重启及升级回退
仍为 NOT RUN。下方旧阶段叙述仅为历史记录。


## 2026-10-03 接手顺序

[开发交接](DEVELOPMENT_HANDOFF.md) 为当前状态入口；
[逐版本计划](RELEASE_ITERATION_PLAN.md) 和 [首版部署计划](DEPLOYABLE_RELEASE_PLAN.md)
定义当前验收。只推进完整单机首版：一条安装命令、PC/手机、真实双 CLI 与恢复。

PR #134 已合并并统一真实 vendor/Runtime digest framing。当前 Draft #135 已完成
固定 Claude/Codex ELF 资格化、真实 Codex native auth probe 和不执行 vendor CLI 的
qualified enrollment；其最终 documentation-inclusive exact-head CI 与 merge/read-back
仍是当前动作。#135 合并后直接组合完整 fresh-install，再进入真实客户端/双 CLI/
reboot/upgrade/rollback。下方“not started”等均为历史阶段快照，不覆盖本节。
长期 70 项范围保留，在首版验收后逐版本展开。

## Current release focus — 2026-09-29

当前唯一产品目标是 [首个可用单机 RC](RELEASE_ITERATION_PLAN.md)：
先完成 R12 软件/制品，随后在指定目标完成真实 host/client/CLI/
recovery 验收。70 项完整吸收清单仍在 [全量计划](FULL_CAPABILITY_DELIVERY_PLAN.md)，
但 S02–S14 暂不扩大；下列历史阶段陈述不覆盖本次版本顺序。

## Current execution: approved R12 plan

Owner approved [PRP-2026-09-08-v1](PRODUCTION_READINESS_PLAN.md) on 2026-09-08.
R12-A contract/input closure is in progress; dependency-ready B/C/D/E/F software
follows. G/H/I real host/client/CLI qualification and J/K production/publication
remain separately authorized and evidence-bound. R11 and WEV-1 stay delivered;
later workstation features remain Proposed. The earlier snapshot below records
the starting state and does not override this execution update.

## Current increment: workstation evolution

The 2026-09-08 task adds an audit and evidence-backed product evolution to this
existing roadmap. [WORKSTATION_EVOLUTION](../WORKSTATION_EVOLUTION.md) defines
the sequence; [CAPABILITY_MATRIX](../CAPABILITY_MATRIX.md) separates design,
implementation, validation and availability.

1. WEV-1 — merged in PR #87 as `b3e9cd5`: revalidate Workspace observations when
   returning to the browser; no automatic Agent lifecycle operation or new data
   domain. Exact-head CI and independent reviews passed; delivery read-back is
   recorded in the evolution document.
2. R12 — not started: concrete authorized host/trust/provider/bootstrap and
   real CLI/recovery acceptance; remains the first real product-flow blocker.
   Use the five-part [bootstrap/host checklist](../WORKSTATION_EVOLUTION.md#r12-production-bootstrap-and-host-gates):
   production API composition, Runtime filesystem-v2/provider composition,
   activated sockets/isolation, managed CRX/Native Messaging/trustd, and real
   CLI login/input/return/reconnect/exact Stop/reboot acceptance.
3. Proposed follow-ups — bounded Active Work/Attention projection, read-only
   Changes/Files, then capability-bound Discovery/Resume and structured Approval.
   Task/Worktree and external notification remain later, contract-dependent work.

The completed R11 software evidence below remains valid; it does not claim
end-to-end production availability or authorize new host/Secret operations.

## Completed

- Phase 0 through Phase 10 (as per existing repository governance).
- Governance automation policy is merged; routine mechanical actions proceed after CI.
- WAW-1 typed HTTP lifecycle, transient ticket/reconnect, Runtime attachment prepare/detach contracts merged in PRs #47/#48/#49.
- WAW-1 bounded synthetic stream bridge and WAW-2 Codex command identity contract merged in PR #52.
- WAW-1 fail-closed WebSocket route boundary merged in PR #54; WAW-2 synthetic lifecycle support merged in PR #55.

- WAW-3 software recovery/cursor/lease and browser stale-event fences merged in PR #58, with 19/19 exact-head checks successful. Full WAW-3 real transport/reboot remains unverified.

- WAW-2 Codex API/ticket/Web contracts merged in PR #59 with 19/19 exact-head checks successful. Real CLI execution and legacy process interlocks remain gated.

- Workspace metadata workflow merged in PR #60 with 19/19 exact-head checks successful; desktop/mobile metadata interactions are tested, terminal admission remains unavailable.

- Software readiness and packaged WAW scope/gate documents merged in PR #61; 19/19 exact-head checks and independent artifact/doc-presence validation passed.

- Shared Claude/Codex supervisor and stream lifecycle fences merged in PR #63 with 19/19 exact-head checks successful.

- Concrete Runtime executor, formal Project mapping, read-only probes and failed-start recovery merged in PR #64 with 19/19 exact-head checks successful.

- Fixed Noise NX Python/WebCrypto cores, pinned independent vectors and two-role interoperability merged in PR #65 with 19/19 exact-head checks successful.

- Native Chromium Noise verification merged in PR #66; all 60 Linux E2E tests and 19/19 exact-head checks passed.

- Login/reauthentication capacity now follows actual worker completion after caller cancellation; PR #67 merged with 19/19 exact-head checks successful.

- Opaque AWCE Python/Web framing, header builders and interoperability merged in PR #68 with 19/19 exact-head checks successful.

- Descriptor-held executable provenance foundation merged in PR #69 with 19/19 exact-head checks successful; complete interactive process/host qualification remains unfinished.

- Isolated numeric authentication timing diagnostic and failure/privacy regressions merged in PR #70 with 19/19 exact-head checks successful; historical latency cause remains unknown.

- Incremental UTF-8/VT tokenizer foundation merged in PR #71 with 19/19 exact-head checks successful; complete browser terminal/controller remains unfinished.

- Accepted application cryptography merged in PR #73 with 19/19 exact-head checks; full-vector interop and 62 native/normal browser cases passed.

- Full WAW wire profiles and bounded transcript validation merged in PR #74 with 19/19 exact-head checks; real parser-budget integration failures were corrected and measured.

- Staged ticket authority and admission coordinator merged in PR #75 with 19/19 exact-head checks; four independent review findings were fixed before delivery.

- Runtime encrypted attachment stream and exact socket/Stop publication fences merged in PR #76 with 19/19 exact-head checks; final review deadlock and logical-line findings were repaired before delivery.

- Native WebSocket/API ciphertext relay, shared parser/INPUT budgets and cancellation-resistant cleanup merged in PR #77 with 19/19 exact-head checks; all six post-main workflows succeeded.

- Managed Chromium/Native Messaging/trustd browser trust, cumulative root checkpoints,
  bounded browser terminal model and `zh-CN`/English Workspace boundary merged in
  PR #78 with 19/19 exact-head checks and exact read-back.

- Fixed Claude/Codex interactive profiles, native PTY/bootstrap/attach chain,
  Runtime process composition and inert rc5 policies merged in PR #79 at
  `341a69bf...` after 20/20 exact-head checks; six post-main workflows and the
  dynamic Dependency Graph update succeeded.

## Current reassessment

See [REMAINING_PLAN.md](REMAINING_PLAN.md). R0–R10 are delivered through PR #79.
R10 final head `0d9e7c7...` passed 20/20 checks and merged as `341a69bf...` with
exact read-back and successful post-main workflows. Host evidence remains
separately tracked in R12.

## In Progress

- Mac remains the development platform. R11 rc6 and rc7 are delivered by
  PRs #80 and #81, and rc8 is delivered by PR #83. Documentation head
  710ceef completed 26 exact-head checks, merged normally as
  95bf65d6114008b962985f7311941499c961a7b8 with exact parents 87f5bce and
  710ceef, and all six post-main workflows succeeded. rc8 is software evidence
  only: no tag, GitHub Release, host activation or R12 qualification occurred.
  PR #85 final head `751d4d010f92e18780bd6d96fdb3c9ea23107464` completed all 26
  exact-head checks and merged normally as `b07f944ef2c7b590e5a3f1fa50354d6f492d6c31`.
  All six post-main workflows succeeded, so R11 software rc6–rc9 is delivered
  as software evidence. R12 remains independently unstarted and host-gated.

- Parallel multi-agent execution and per-stage GitHub/document updates are
  authorized by Owner on 2026-09-03. The active checklist is `EXECUTION_PLAN.md`.

## Next

- F1: preserve the delivered R11 software contracts and evidence; no tag, GitHub
  Release, production deployment or Provider credential operation follows from
  the merge.
- F2: real Linux host activation, isolation/CLI/PTY/reboot qualification and
  product acceptance remain independently gated.
