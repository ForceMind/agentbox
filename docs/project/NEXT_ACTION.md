# Current Authorized Action

## 2026-10-04 独立 A3 content schema/codecs（当前批次）

已显式 fetch/read-back 核对 #139 正常合并为
`587fe8eabf7e5d5e4d3a561091ec00c3e9f40881`，tree
`5fecc5a36e0367ee6c92b6caea405ec9ec592ceb`，parents 为
`35d25bdccbb9311a57fc06a0683f4f60bf50dd9c` 与
`744ac4719e072f072c4bc07d5c00b31fdc3f53ad`。#139 exact-head 六套
workflow SUCCESS（24 jobs SUCCESS、2 历史 rc8 SKIPPED）；post-main 六套
首次 attempt 全 SUCCESS（23 SUCCESS、push dependency-review 与两项 rc8 共
3 SKIPPED），没有失败重跑或 pending。证据保存在
[PR #139](https://github.com/ForceMind/agentbox/pull/139)。旧 selector worktrees
与原历史提交全部保留；本批从 exact main 新建独立
`codex/s02-content-channel-codecs`。

本批仅落实 [A3 schema/codecs 合同](../WORKBENCH_A3_CONTENT_CODECS.md)：
独立 version/domain 与 typed formal Project/binding/session/Runtime epoch/
selector commitment/staged side/request nonce；四类 canonical flat JSON
plaintext records、严格 bounded parser、全量分页预检、单次 transcript 顺序/
complete/hash/expiry/close 模型及 Python/Web exact-byte/negative/interop vectors。
完整 PAGE plaintext（含 JSON metadata）保持 ≤16 KiB、最多 16 页；256 KiB 是
reader ceiling，不是可传输保证。固定测试 metadata 下实际上限 191,504 bytes，
191,505 先报 PATCH_TOO_LARGE，不输出 partial success。

未实现 Noise handshake/AEAD、生产 admission/currentness resolver、全局 nonce
ledger、Runtime RPC/socket/API relay 或 public patch UI；没有生产入口调用这些
纯函数。caller-fed context/time 只是模型输入，不能证明 READY/active session
或生产 authorization；下一层仍须 trusted resolver、独立 pin、新 CipherStates、
计时/revocation/visibility fencing 与 crypto vectors。真实 host/device 仍 NOT RUN，
不因 codec PASS 宣称 encrypted transport working。

当前动作：完成本候选的 canonical 全量质量检查、codec/crypto/selector 回归与
只读独立审查后再发布 Draft PR；require 新 exact-head 全部 CI 终态，再正常
merge/read-back。#139 CI 不能代替本批 evidence。下一批是独立 crypto-profile/
admission composition 合同，不能跳过 key-confirmation/transport schema、生产
currentness/replay/deadline 所有权或将 WAW state 复用为内容通道。


## 2026-10-04 Runtime-only staged selectors（当前批次）

已通过显式 main fetch/read-back 核对 PR [#138](https://github.com/ForceMind/agentbox/pull/138)
正常合并为 `35d25bdccbb9311a57fc06a0683f4f60bf50dd9c`，tree
`e74ef60de8c60650008ecd49f049526627f13557`；parents 为
`7fa54c3f5e3ce7e96c3d2cb33828c759665d81d2` 与
`f2148148fde8b2056630f6ddf67d3db411678e14`。#117 已因保留历史而间接
MERGED（GitHub 记录 f214814）；其原 head `8ef72862514c27b01f5f52a532e0ac4e16f20775`
与本地原提交 `ea6d638` 均保留，未改写旧 branch/worktree。

#138 exact-head 六套 workflow 全成功；post-main 六套 workflow 的最新结果也均
SUCCESS。post-main Frontend 初次在既有 late-Stop-receipt case 出现 5000ms timeout
与 PROTOCOL_INVALID，同一 SHA 仅重跑失败 job 后成功；首轮失败仍保留，根因未
宣称修复，未修改断言或 timeout。post-main 最新 job 汇总为 23 SUCCESS/3 SKIPPED
（push 的 dependency-review 与两项历史 rc8）；skipped 不算 pass。

Owner 已要求持续完成计划。本批从上述 exact main 的独立 feature branch
`codex/s02-runtime-staged-selectors` 实施下一项 Runtime-only staged selector：
完整 sorted staged snapshot（含全部 path/mode/HEAD/index OID）、当前正式 Project
binding、Runtime epoch、可信 API session scope、entry index 与 staged side 绑定；
TTL 最多 30 秒，token 校验与实际 patch read 共用同一个 held observation。
保留 #138 全部 Git isolation、双观察、资源与 cleanup 边界。

可信 current-context resolver 暂未接入生产：必须由未来的 Runtime composition
提供当前 READY formal mapping、有效 session scope 和 epoch；本批 fixture 回调
不构成生产 admission。没有 Runtime RPC、encrypted content channel、API/Worker
plaintext、WAW frame、UI、Files/unstaged、provider 或真实 host 激活。v1 metadata
schema 与 strict clients 不变；真实 host/device 验收仍为 NOT RUN。

当前动作：闭合本批必要 negative/race/expiry/cancel/cleanup 测试和质量检查，
完成源代码审查后再发布 Draft PR；待新 exact-head CI 全部终态，按授权流程进行
后续正常交付。旧 reader/v1 的 CI 不能替代本批证据。下一项是单独审查的 encrypted
content admission/transport 合同及接线，不能从内部 selector 的完成推导其已开放。

## 2026-10-04 软件续建优先级（覆盖下方历史冻结）

Owner 在首装软件合并后明确表示暂时不做真实测试、继续开发，并要求列出
后续计划。本次按该最新指令暂缓真实 host/device/login/reboot/upgrade/rollback
验收，继续不依赖现场输入的软件工作；这些现场项目仍为 **NOT RUN**，不视为
通过、取消或已交付可用版本。此段覆盖下方“不得推进 #117/S02”及先完成现场
验收才可开发后续软件的历史顺序限制，不改变 Runtime/Secret/发布门禁。

已核对 `origin/main = 7fa54c3f5e3ce7e96c3d2cb33828c759665d81d2`，
PR #136/#137 已合并；不重做 first-install composition。当前唯一实现批次是
S02 的 [Runtime-only staged reader](../WORKBENCH_A3_STAGED_READER.md)：
复用 Draft [#117](https://github.com/ForceMind/agentbox/pull/117) 的
`8ef72862514c27b01f5f52a532e0ac4e16f20775`，在独立 reconciliation branch
保留两边历史，不改写旧分支/WIP。原 head 六套 workflow 为 terminal SUCCESS，
但与当前 main 有四份治理文档冲突，且没有 GitHub review submission/thread；
旧 CI 不能当作新 reconciliation head 的证据。

范围仅为 tracked regular staged add/modify/delete 的 bounded reader、必要
安全修复/测试与合同。selector、Runtime RPC、独立加密 content channel、
patch UI、Files 编辑和 provider 功能均不在本批。先闭合配置/对象 provenance、
helper/network 隔离、超时/取消与双观察，再核验新 exact-head CI；自查须如实
标注，不称独立审查。全部 S00–S14 仍按 [全量计划](FULL_CAPABILITY_DELIVERY_PLAN.md)
的依赖逐批推进，真实支持与发布分别依赖实际证据。


## 2026-10-04 continuation verification

The Owner resumed AgentBox development in the current session. PR #136 head
`d6ee8c7c9635e2b5ecd58f18048fa8c1aaa59474` has six terminal successful workflows
(24 successful jobs and two prescribed historical rc8 skips). PR #136 was normally merged after the Owner confirmed continuation and repository
operations. Main read-back is `7d0521556727d64c80d02d69aea7b9d9b06432af`,
with parents `769197ed9dda2873b0b066a073efb7319d0665c1` and
`d6ee8c7c9635e2b5ecd58f18048fa8c1aaa59474`. Its tree exactly matches the
verified PR head. Post-merge CI is pending at this snapshot; no target-host
operation or product qualification is claimed.

This documentation-only continuation reconciles the stale #135 roadmap/index
and historical target inputs with the implemented `setup-fresh-waw` sequence.
See [target inputs](R12_TARGET_RECORD.md) for the actual remaining qualification
requirements. Do not redo composition, open #117, or substitute more fixture
checks for real fresh-host/client/login/reboot/upgrade/rollback evidence.
Repository link checking and `git diff --check` pass; the existing six workflow
results validate d6ee8c7 only, not a later documentation commit.


## 2026-10-04 hand off PR #136

Owner has paused this development session and will continue with another AI.
Do not redesign the first-version route or repeat #131/#134/#135.

Durable `main` is
`769197ed9dda2873b0b066a073efb7319d0665c1` (PR #135 merge).
Continue Draft PR #136 / branch
`codex/r12-fresh-install-composition`.

The last code-only exact head before handoff is
`815adfcb60a72c7de48cdfcdc2007c338b7b03cd`; all six workflows reached
SUCCESS on that exact head. Handoff/documentation commits after it intentionally
advance the branch, so the first action for the next developer is:

1. read live PR #136 head and changed files;
2. require Backend, Frontend, Security, Deployment, E2E and Release Candidate
   to be terminal SUCCESS on that **new exact head**;
3. fix any real documentation/format/test regression without weakening
   installer recovery or Runtime/native isolation;
4. if exact-head remains clean, mark #136 ready if necessary, merge normally
   with exact-head protection, and read back `main`.

Do not reopen #133. Do not replace release-qualified enrollment with installer
vendor execution. Do not substitute the diagnostic simple-empty-HOME Codex
digest for the accepted native-auth digest
`76522c70a3df95fdd59bc4851200017bf42947a49d47e216c95bb0dea1579d9c`.

After #136 merge, the next substantive gate is **real first-install
qualification**, not another composition redesign. Use the same immutable
candidate artifact and exercise:

`setup-fresh-waw -> HTTPS entry -> administrator bootstrap -> real Claude login
and turn -> real Codex login and turn -> resize/detach/reconnect/exact Stop ->
PC/Android/iOS -> service reboot -> host reboot -> upgrade -> rollback`.

Record concrete evidence and failures. A green fixture/CI composition must not
be described as a completed real-host or physical-client qualification.
Only after these gates close should the candidate be frozen and published as
the first immutable deployable release. #117 and unrelated workstation
features remain out of scope.

## 2026-10-03 finish qualified enrollment and merge #135

The production native qualification is now proven. Fixed Codex 0.159.3 runs
through `agentbox-waw-pane-bootstrap --auth-probe` after the narrow AF_UNIX
local-IPC seccomp compatibility repair, while AF_INET and all network
connect/bind/listen/send/recv operations remain denied. The accepted
unauthenticated framed digest is
`76522c70a3df95fdd59bc4851200017bf42947a49d47e216c95bb0dea1579d9c`.

Current action is to inspect the final documentation-inclusive exact head of
Draft #135. All Backend, Frontend, Security, Deployment, E2E and Release
Candidate workflows must reach terminal SUCCESS. Fix real failures without
weakening the native isolation or substituting the simple empty-HOME digest.
Then exit Draft if necessary, merge normally with exact-head protection and
read back `main`.

After #135 merge, start a fresh feature branch from the new main and compose
the already-built first-install pieces into one recoverable sequence:

`deferred apply -> dependencies -> fixed vendors -> manifests/policies ->
qualified vendor enrollment -> activation -> setup-waw-web`.

The composed path must keep explicit plan/recover semantics and may not execute
a vendor CLI from the Root installer. After complete fresh-install composition,
continue real Claude/Codex login/input/output/resize/detach/reconnect/exact Stop,
PC/Android/iOS, service/host reboot, upgrade/rollback and immutable release.
Do not advance #117 or unrelated workstation features.

## 2026-10-02 Runtime-only vendor observation/enrollment

Live GitHub state is now `main` =
`3da84df5fcc8b5543405f651d1a78c21ea9a8376`; PR #131 is merged and must not
be repeated. Continue the same first deployable release.

The immediate narrow batch is branch
`codex/r12-vendor-observation-digest`. It fixes the confirmed Codex
unauthenticated digest mismatch by making the actual pinned-vendor observation
use the same length-framed `waw_vendor_probe_output_digest(stdout, stderr)`
contract as the production Runtime parser, with a regression that rejects raw
stdout+stderr concatenation semantics.

Current action: push/read back this exact branch head, open the PR, require the
normal exact-head CI contract, fix any real failures, merge normally and read
back main. Do not weaken the parser or replace framed output with a synthetic
digest.

After that merge, implement the actual Runtime-only observation/enrollment
composition: derive the fixed Claude/Codex versions and Codex unauthenticated
framed digest from qualified Runtime-owned observation rather than operator-
supplied synthetic values, then compose deferred fresh install -> fixed
dependencies/vendors -> manifests/keys/public observations -> enrollment ->
`setup-waw-web` -> actual HTTPS entry.

Only after the composed install is closed proceed to real Claude/Codex
login/input/output/resize/detach/reconnect/exact Stop on PC/Android/iOS,
service/host reboot, upgrade/rollback and immutable release publication.
Do not advance #117 or unrelated workstation features.

## 历史行动记录

## 2026-10-01 qualify deferred fresh install and compose prerequisites

PR #129 merged at 7761310; exact source afafe55 has 24 SUCCESS/two prescribed
SKIPPED and actual official native/signature/version/unauthenticated evidence.
Continue on codex/r12-first-install with uncommitted deferred apply/resume and
its staged intent test. 160 affected checks/Ruff/372-file mypy pass. The mode
discrepancy was proven to be sandbox setgid removal by isolated probes; unchanged
tests outside that restriction passed 119 cases. Commit this batch and inspect
exact-head Linux CI; no assertion/permission relaxation is needed.

Then finish fixed Web/runtime dependencies and derive version/auth registration
from actual isolated observations, compose deferred apply/vendor/manifest/
enrollment/setup into the download entry, and qualify the complete installed
CLI/browser/reboot/upgrade/rollback path. Goal and first-version scope unchanged.

## 2026-10-01 verify actual native vendors then close initial install sequencing

PR #128 merged at 4f849be; source 131aadb reached 24 SUCCESS/two prescribed
SKIPPED. Current vendor bootstrap pins Claude 2.1.286/Codex 0.159.3 official
downloads and publishes verified ELF files create-only. Local real downloads
passed SHA/ELF checks; 153 affected regressions/Ruff/372-file mypy pass. Codex's
287086056-byte binary requires a fixed-path/kind-only 384 MiB pin; other/default
limits and legacy 256 MiB Codex pins remain. Inspect actual Linux signature,
version and unauthenticated-output evidence plus exact-head CI before merging.

Next compose fresh-install defer-activation, fixed Web/runtime dependencies,
native vendor installation and actual version/auth observation into manifest/
enrollment/setup. Do not make the operator supply synthetic vendor versions or
digests. Then qualify maintenance and the full installed CLI/browser/recovery
path and publish the immutable artifact/install command. No unrelated features.

## 2026-10-01 finish setup qualification and initial-install prerequisites

PR #127 merged at 753e8be; exact source ba13d10 has 24 SUCCESS/two prescribed
SKIPPED. The setup-waw-web WIP is on codex/r12-web-setup and composes the enrolled
installation under one lock, with consent/preflight before certificate effects
and no Runtime restart on recovery. 42 affected regressions/Ruff/369-file mypy
passed; the setup cases passed again after ingress preflight. Inspect exact-head CI.

Next add the initial-install prerequisite sequence: fixed dependencies and
actual vendor distribution/enrollment, maintenance sandbox evidence, then the
version-pinned download/apply/setup entry. Keep the explicit actual PC/mobile
CLI/input/reconnect/exact Stop and reboot/upgrade/rollback gates. Do not describe
the enrolled-host setup command as the final self-install command.

## 2026-10-01 verify ACME/maintenance then compose the install entry

The current certificate batch adds fixed, explicitly consented ACME issuance,
private policy/storage, sealed TLS pair recovery, and a daily Root-only Web
maintenance service/timer. Bootstrap refresh supports automatic and operator-
managed TLS; certificate renewal never touches Runtime services or credentials.
40 local affected regressions/Ruff/367-file mypy pass. Inspect exact-head CI and
the actual distro Certbot parser check; generated certificates are not public
CA evidence and the maintenance service sandbox still needs Linux execution.

Next finish fixed dependency installation without adopting/stopping unrelated
services, exercise the actual maintenance unit, and compose one operator setup
sequence for PKI, publication, Origin and WAW/HTTPS activation. Then close real
vendor CLI, PC/mobile input/reconnect/Stop and install/reboot/upgrade/rollback
acceptance before publishing the artifact and self-install command. Keep the
same first-version target and source version; no unrelated features.

## 2026-10-01 verify fixed Web activation then automate certificate/setup

PR #126 merged at ebf06758b93423b7110539854e9d30dd80b4266f; source f72ea3a
has 24 SUCCESS/two prescribed SKIPPED, with GitHub/fetched origin/main read-back.
Continue on codex/r12-web-certificates. The merged batch
adds configure-waw-web/activate-waw-web: verified current overlay, fixed TLS
provenance/hostname/validity/key checks, offline atomic Origin/proxy configuration,
and HTTPS-only restart with WAW-started admission and fixed failure cleanup.
32 focused regressions/Ruff/365-file mypy pass. Actual native PID-1
DynamicUser/LoadCredential/TLS/write-denial passed, run 36862158050/job
110368738448. Public CA/user-host/client/CLI qualification remains separate.

Next compose explicit operator-approved automatic certificate issuance and
renewal, public bootstrap refresh before expiry, and the single installer
setup sequence. Retain the final PC/mobile real CLI/input/reconnect/exact Stop,
reboot and upgrade/rollback gates. No user SSH target or new feature is needed;
the operator supplies domain/certificate/ACME choices in the installer itself.

## 2026-10-01 qualify ingress then compose self-install activation

PR #125 merged at f2af937; source 4f86c4d reached terminal 24 SUCCESS/two
prescribed SKIPPED. Both GitHub and fetched origin/main were read back.
Publication lifecycle/CLI, independent nginx configuration and DynamicUser/
LoadCredential service are composed as software. Actual nginx TLS/static/API
routing passed all four installer matrix combinations, run 36859319313.
Local 43 affected regressions/Ruff/362-file mypy pass; local systemd/nginx
checks skipped. Continue on codex/r12-web-activation from merged origin/main.

Next compose fixed nginx dependency checks, certificate provisioning/renewal,
exact allowed Origin and trusted proxy configuration, and explicit service
activation with systemd credential/read-only path evidence. Do not add CAP_CHOWN
or use the API static route as the HTTPS profile entry. Then prove API/Worker
write denial, publication/rollback and actual PC/mobile CLI/reboot/recovery;
finish the self-install artifact and command. The first full deployable version
remains the sole iteration; no user-host activation or release is implied.

## 2026-10-01 publish Root-owned HTTPS entry and independent serving

e1055e0 reached terminal 24 SUCCESS/two prescribed SKIPPED and actual native
PID-1 complete_remote_stopped_observed=true evidence. Current distinct HTTPS
consumer/lease, explicit secure-document selector and twelve-field canonical
public encoder have 70 Web/17 backend focused regressions and static checks.
Inspect this batch's exact-head CI before relying on it.

Next implement the Root-only public bootstrap/static overlay transaction and
independent serving at the accepted HTTPS Origin, with immutable assets,
API/Worker write denial, exact proxy routing/CSP and source/build replacement
recovery. Do not inject bootstrap into an API-controlled HTML route or call
Web trust independent/native-equivalent. Then close actual browser/core CLI
and composed installer/reboot/upgrade/rollback evidence plus the final
self-install command. This is one full deployment version, not a new scope.

## 2026-10-01 verify complete Remote evidence then HTTPS Web bootstrap

537b02d reached terminal 24 SUCCESS/two prescribed SKIPPED. Current complete
UID observer and observed confidence are connected through Runtime conflict,
protocol/API and Web. 173 backend regressions/Ruff/356-file mypy and eleven
Web DOM/hook tests/typecheck pass; two mocked Chromium desktop/mobile render
checks pass. Inspect the actual native PID-1 observer result and exact-head CI.
Permission, namespace, PID or alternate-executable uncertainty stays UNKNOWN;
never use the old boolean negative as STOPPED. The vendor Remote implementation
itself is not qualified by synthetic/current-process observations.

Then implement ADR 0010's canonical root-owned HTTPS public bootstrap and
distinct Web trust provider, with independent static serving and exact Origin/
CSRF/CSP boundaries. Complete the PC/mobile core input/output/resize/detach/
reconnect/exact Stop path, then isolated composed installation and real CLI/
reboot/upgrade/rollback evidence. No scope expansion, extra product version or
production/readiness claim substitutes for the full first self-installable
version.

## 2026-10-01 verify activation then close Codex Remote and HTTPS Web

41280ce reached terminal 24 SUCCESS/two prescribed SKIPPED. Current fixed
activation composes offline/idle guards, enrolled public-fingerprint comparison,
Root-private recoverable journal, paired profiles, scoped drop-in and ordered
named socket/service start. 49 focused regressions/Ruff/354-file mypy pass.
Inspect its exact-head CI. Service-manager active status alone is not usable
graph or target qualification; retain actual install/CLI/reboot/rollback gates.

Next implement positive, complete and fresh Codex Remote evidence without
converting ordinary process absence into ABSENT. Then the accepted HTTPS Web
trust/bootstrap profile must provide PC/mobile input/output/resize/detach/
reconnect/exact Stop. Validate the composed installer/application on isolated
Linux before claiming a deployable artifact. Scope remains this single full
self-installable version; no unrelated capability expansion or user-host
activation/publication is implied.

## 2026-10-01 compose fixed offline activation

001c4bd currently has terminal 24 SUCCESS/two prescribed SKIPPED, actual
absence/full/partial cleanup Linux probe evidence, and a retained first-run
sanitizer/tmux DCS failure that passed on same-head retry without a code fix.
Current policy preparation adds only three fixed cross-pinned global policies
while profiles stay disabled; 24 regressions/Ruff/352-file mypy pass. Inspect
its exact-head CI before relying on the new candidate.

Next complete the fixed systemd drop-in, named socket and paired profile
activation transaction with offline/idle evidence and recoverable failure
states. Existing services/processes may not be silently killed or adopted.
Then close positive Codex Remote and the accepted HTTPS PC/mobile core flow.
No new workstation feature, product version, user-host activation or release
is authorized by these internal software checkpoints; the full self-install,
CLI, reboot and upgrade/rollback delivery objective remains open.

## 2026-10-01 verify absence/cleanup Linux evidence then fixed activation

Both stores now have explicit new-epoch CAS operations, composed into the
existing Runtime-only cleanup acknowledgement with interrupted-write retry.
ccf8bf5 reached terminal 24 SUCCESS/two prescribed SKIPPED. Current follow-up
adds distinct absence records and exact empty-generation removal/partial retry.
152 local regressions, Ruff and 351-file mypy pass. Inspect the actual native
PID-1 producer/cleanup probe and exact-head CI before relying on Linux evidence.
It exercises real removal/ENOENT, not a host reboot or cross-invocation CLI
recovery. Preserve all generation floors, binding/host provenance and
fail-closed multi-generation ambiguity; never kill/adopt unknown groups.

Then complete fixed installer activation, positive Codex Remote evidence and
the accepted HTTPS Web PC/mobile flow. The sole delivery target remains the
full self-installable browser/CLI version; these internal batches do not close
reboot/upgrade/rollback acceptance or constitute separate product versions.

## 2026-10-01 verify FD persistence then close epoch recovery

The fixed Runtime stores and actual FD-backed observation factory are wired
in _main, with exact systemd invocation identity, fixed private directories,
finite Workspace/workload policy values and guarded persisted empty evidence.
85 focused tests/351-file mypy/Ruff pass. Synchronize this same Draft/version
and inspect the native PID-1 factory/store read-back. Then close explicit
Runtime epoch/generation provenance transitions and abandoned cgroup cleanup;
existing floors currently reject changed epochs, so reboot readiness remains
unproven. Follow with fixed activation, positive Codex Remote and HTTPS client
core/recovery flow. Do not equate stores being wired with full recovery.

## 2026-10-01 bind fixed stores and real FD observations in production

Port forwarding is synchronized as e474466733d75bb78a08e4b3644b97d8f466b437.
Three Backend checks are confirmed live; inspect their terminal results before
relying on full exact-head evidence. Continue the actual fixed instances/factory
below; optional forwarding is deliberately not the completion condition.

The application/server now forwards existing durable ports into registry;
43 construction/cleanup regressions and 349-file mypy/Ruff pass. Synchronize
this ownership gap fix on the same Draft/version, then build the fixed Runtime-
owned storage instances and real cgroup observation factory in _main. Preserve
explicit epoch/provenance transitions and positive empty cleanup; do not label
optional-port forwarding alone as recovery-ready. Actual creator evidence is
already recorded at d313624; no unchanged native probe rerun is needed.

## 2026-10-01 compose durable recovery and fixed activation

Actual creation helpers passed native PID-1 cgroupfs in Deployment
36766671223/job 110062461054 (three proof booleans true, mount 418).
d313624 has terminal 24 SUCCESS/two prescribed SKIPPED. Do not rerun unchanged
checks. Next connect existing Runtime-only Workspace/cgroup stores and a real
FD-backed attestation factory through application/server/bootstrap/_main;
provide cleanup/restart evidence, then fixed policy/socket/profile activation.
Use the existing contracts and current version, preserving exact Stop,
controller limits, private-key boundaries and no generic shell/filesystem path.
Continue positive Codex Remote plus HTTPS PC/mobile workflow afterward.

## 2026-10-01 complete delegated lifecycle and activation

The new isolated Deployment PID-1 fixture directly executes actual creation
helpers under a transient DynamicUser Runtime service (existing unit refusal,
unique cleanup marker, explicit metadata fixture). Inspect its real cgroupfs
result before claiming the creation path is host-verified. Continue durable
ports/activation afterward; a passing probe does not satisfy whole CLI recovery.

Creation wiring is synchronized as 714473bf786c7eaa33084eaa53608153fd3b5d40.
Its five pending CI jobs are confirmed live. Revalidate exact-head results,
then proceed with actual helper evidence and the remaining lifecycle ports.

Manifest preparation fa2ae6e passed terminal CI (24 SUCCESS/two prescribed
skips). Current code wires scoped root/workload creation to the actual Runtime
resource/provider path, with owner/mount/domain/controller/limit guards and
101 focused passes/349-file mypy. Synchronize this batch and obtain actual
Linux helper evidence; ordinary directory fixtures do not prove cgroupfs.
Then compose durable cgroup/workspace attestation and cleanup/restart behavior,
and fixed installed policy/socket/profile activation. Missing attestation ports
in the production builder must not be treated as recovery-ready defaults.
Continue positive Codex Remote and HTTPS Web/client acceptance within the same
first version; do not publish a deployable claim from internal green checks.

## 2026-10-01 validate complete issuer then activate bounded resources

Complete issuer is synchronized as fa2ae6e3c25f1e22923bb7aa0401e392c67654cf.
Its five pending CI jobs are confirmed live. Revalidate this exact head and
inspect failures rather than restarting unchanged runs, then proceed below.

The key batch a417add has terminal 24 SUCCESS/two prescribed SKIPPED. Complete
manifest preparation is now wired to its fixed Runtime public pin via the
installer command, with strict installed-resource observations, all 13 records,
explicit prefix/link recovery, plan-without-writes and disabled profiles.
33 focused tests/348-file mypy/Ruff pass. Synchronize the same Draft/version,
inspect Linux packaging/Backend evidence, then implement delegated root/workload
allocation and verified policy/socket/profile activation. Keep vendor login,
positive Codex Remote state, HTTPS trust/client flow and real recovery acceptance
as required first-version work; never treat prepared manifests as usable release.

## 2026-10-01 connect Runtime public pin to complete manifest issuance

Key initialization software and formatting correction are synchronized as
a417addf315ed9f1caf037d4ab18af351ef6961c. Its five pending CI jobs are live;
finish exact-head revalidation without restarting unchanged runs. Then wire
the existing HostOperations public-pin result into the complete issuer.

591d86f passed terminal exact-head CI (24 SUCCESS/two prescribed SKIPPED).
Runtime-only fixed initial-key command and installer public-output consumer
are implemented in the current batch, with 92 regressions/346-file mypy.
Synchronize this software, inspect its Linux checks, then connect the command
to the root-owned full v2 manifest issuer using restart-safe physical root
identity and one immutable helper release. Do not output/read private key bytes
in Installer/API/Worker, silently rotate lost enrolled keys, or activate profiles
without complete verified resources. Delegated root/workload creation, positive
Codex Remote evidence, HTTPS Web and actual PC/mobile CLI/recovery flow remain
first-version work. No new product version or later functionality is authorized.

## 2026-10-01 issue installable resources using the restart-safe profile

d41974d passed the actual Linux FD check and complete Backend/native/install/
client jobs. Its Release audit found four virtualenv advisories; the current
minimal fix pins 21.7.13 and required python-discovery 1.6.0 with verified
official wheel hashes and three-Python dependency closure. Synchronize and
inspect its exact-head audit/artifact checks, then continue actual manifest
issuance/key initialization and activation below. These remain one unfinished
first-version delivery, not completed product increments.

3b00cb4's real scoped PID-1 probe passed twice, with equal physical identity
and equal/reused namespace/mount numbers. Backend failed the real FD test on
an existing mnt_id parser tab-offset bug, corrected in the current follow-up.
One existing wire fixture also failed; bounded numeric diagnostics are added
without relaxing its 5ms budget/assertions. Synchronize this correction and
inspect exact-head Linux results. Continue the issuer/key/delegation/client
work below once these direct startup checks are established.

The synchronized 530fdf5 startup correction passed all 24 checks/two prescribed
skips. Current uncommitted code fixes install-time namespace IDs and helper
current-symlink paths, as recorded in ADR 0011. Commit this correction on the
same Draft/version and inspect its real Linux FD/two-instance PID-1 evidence.
Then implement the complete root-owned manifest issuer and Runtime-only key
initialization, followed by delegated workspace allocation and profile/socket
activation. Do not publish hand-filled numeric namespace IDs, mixed helper
releases, plaintext key output, or enabled profiles without validated resources.
Positive Codex Remote evidence and HTTPS Web/client/core/recovery acceptance
remain required. Keep the four user-path delivery checklist open; no later
features, product-version bump or subagents are part of this continuation.

## 2026-09-30 finish installation resources for the fixed production entry

The production self-conflict correction is synchronized as 530fdf51d517da7245eb1cd253c5bb4368ec18f3;
finish its pending exact-head CI before relying on complete Linux evidence:
formal binding reads must permit the WAW start whose legacy probe they serve,
while managed_conflict_states continues to deny overlapping legacy admission.
Both AgentType integration start/Stop tests pass with explicit vendor fixtures.
This correction stays within the existing startup scope and product version.

The b966480 Release Candidate audit found three new urllib3 2.7.0 advisories.
The follow-up pins official 2.8.0 plus independently verified PyPI wheel hash,
without bypassing audit. Finish the resulting exact-head checks, then continue
the installer resources below; dependency repair is part of this same version.

The filesystem-v2 _main candidate now composes the existing application using
fixed identities/resources, fresh fail-closed conflict probes and signal cleanup.
Focused application and Runtime regressions pass; the previous exact head's
Backend failure is a confirmed Black mismatch corrected in this batch.
Continue on Draft #125 and the same product version. Verify this batch's CI,
then implement complete installer resource issuance/enrollment and delegated
workspace creation before profile activation. Resolve positive Codex Remote
STOPPED evidence rather than relabeling UNKNOWN as absence. Follow with the
accepted HTTPS Web bootstrap and actual PC/mobile core workflow. Current code
has not been activated on a real host and is not a deployable-version claim.
Preserve the four-path checklist in RELEASE_ITERATION_PLAN; no later features,
additional candidate versions or subagents are authorized by this continuation.

## 2026-09-30 direct scoped startup wiring

The real systemd 255 probe passed (36708294115 / 109863711328). Current
uncommitted Runtime wiring adds the versioned delegated-subtree-v1 policy,
fixed path, exact template pin, UID/GID and RO/RW mount verification, and the
enrollment-only drop-in. 135 focused cases / 339-file mypy / Ruff pass.
88d1e99's native incomplete-DCS exit test failed with 1::; the follow-up keeps
the expected exit/time bound and adds bounded numeric-only failure diagnostics.
Commit this wiring on the same Draft, inspect Linux failure evidence, and
continue complete manifest/enrollment/_main within the four user-path checklist.
Do not call internal slices complete versions or expand unrelated recovery,
abstractions, labels, navigation or the 70-item backlog.

## 2026-09-30 resume accepted Web / cgroup architecture A

Owner approved the recommended HTTPS Web profile and 255-compatible scoped
delegation (“按你说的做”). ADRs 0010/0011 are accepted for software work;
do not ask the same architecture questions again. Continue the same Draft,
version and complete deployment goal, with no subagents or later features.

First run scripts/probe-waw-delegation.py through the Deployment Ubuntu 24.04
root CI fixture. It must prove actual scoped RW/global RO, limits, own-PID
movement and cleanup under native PID 1. If it fails, use the exact error to
correct the selected design; never substitute a simulated pass or unrestricted
cgroup mount. After proof, version and implement the exact Runtime path/policy
contract, non-secret manifest generation and _main. Then implement the accepted
Web trust bootstrap and actual PC/mobile core flow. No deployable claim yet.

## 2026-09-30 await the concrete architecture choices

Exact head a091701 on Draft #125 has 24 SUCCESS / two prescribed SKIPPED,
no pending/failing check. Backend run 36701077638 is terminal successful;
there is no live CI task left to poll or rerun.

The same unresolved architecture dependency has persisted for three goal
turns: Owner must answer the already submitted ADR 0010 Web-trust question
and ADR 0011 server/cgroup choice. Do not treat elapsed time or automatic
continuation as approval. Full deployment is unfinished; keep the goal's
complete scope. Stop automatic goal work at this dependency, preserve all
source/branch/artifact evidence, and resume the same version after answers.
These two post-CI docs remain local WIP for the next code batch; no version,
merge or public release is made for a status-only checkpoint.

## 2026-09-30 cgroup deployment prerequisite

9dda54d exact-head CI is now terminal. Keep Draft #125 and the same version;
the full deployable flow remains incomplete. Current compatibility correction
rejects private/strict on systemd <257 instead of pretending the directive's
boolean-era introduction covers those modes. 54 cases passed (one local
systemd-analyze skip), mypy/Ruff pass. ADR 0011 is Proposed, with an explicit
Owner choice requested for 255-compatible scoped delegation versus a newer
private-namespace target. ADR 0010's Web trust question is still pending.

Preserve all code and original checkout WIP. Do not issue/activate a cgroup
manifest until the selected versioned namespace/path contract and actual
Runtime observations exist; do not replace independent client trust before
the Web decision. Non-secret independent work may continue where possible.

## 2026-09-30 next after 9dda54d deployment matrix

Draft #125 head 9dda54d has successful Deployment run 36697969316, including
the actual root native-helper build/retry and Runtime-owned epoch check.
Inspect the still-running Backend/Frontend/Release/E2E checks on this same
head, repair concrete failures, then continue actual manifest generation and
the production Runtime graph. This snapshot is post-commit local doc WIP;
carry it into the next code batch instead of restarting CI for a status-only
commit. Full browser trust decision and core-flow qualification remain open.

## 2026-09-30 explicit staged recovery and fixed epoch candidate

Current PR #125 follow-up adds resume-install/bootstrap --resume for fresh
pre-activation staging only, with same artifact/transaction and preserved
account/configuration evidence. It also fixes Runtime-owned epoch bootstrap
without weakening the generic root-parent writer. Old/unknown/migrated/
activated/preflight/account-creation/upgrade stages are not auto-resumed.
Those remaining recovery states remain in the full delivery objective.

03ca4ed completed CI but failed the Release sudo prohibition. Move the root
fixture into Deployment; keep that assertion and release dependencies intact.
Local 47 focused cases, 124 broader cases (3 Linux skips and one known Mac
permission case deselected), 337-file mypy, Ruff and boundaries pass.
Commit/push this repaired batch to the same Draft; inspect actual Linux
epoch/root build evidence before continuing manifest generation and _main.

## 2026-09-30 deployment Draft CI repair

Continue PR #125, keeping the same version and Draft state. First checkpoint
c05cc3d passed actual Linux/root helper build/retry but failed the source
boundary and later root-polluted configuration read. Current repairs relocate
fixed execution into HostOperations and isolate root CI data/config/bytecode.
Local boundary, 37 focused cases (two Linux skips), 336-file mypy and Ruff pass.
Push the repaired head and inspect its Linux CI. Do not rerun an unchanged
failed head or call a partial installer a deployable version.

## 2026-09-30 Deliver the Owner's self-deployed PC/mobile version

Use DEPLOYABLE_RELEASE_PLAN. Owner will run the final server installer
themselves; do not ask again for an SSH deployment target. Finish the
current codex/r12-deployable-runtime branch from main 19f8c51.
Fixed enrollment publication/plan/recovery and interpreter selection are
uncommitted software WIP, with 59 focused tests, two selection tests,
333-file mypy and Ruff passes. No deployment or full core-flow claim follows.

The pinned downloader is now local WIP: fixed version/digest, HTTPS-only fixed
repository source, bounded safe extraction, verify/plan before optional apply.
Downloader/interpreter/publication tests passed 39 cases with local fixtures;
no Linux install or published URL follows from this result.
Native helper generation is now wired before activation and recorded with an
exact source/binary ledger; installed-state and recovery/retention readers
validate it explicitly. Linux/root actual-build and failed-build retry tests
are added to CI; local 145 passes plus one existing Mac permission failure
and two Linux skips are not target evidence. Full mypy passed 336 files.
Next close explicit whole-installer staged recovery, then generate actual
trusted manifests and wire the single production _main graph.
Close the positive Codex Remote conflict-state source without
turning UNKNOWN into ABSENT. Owner selected PC/mobile browsers first; ADR 0010
is a concrete Proposed Web trust profile awaiting architecture authorization.
Preserve the existing managed gate until that decision and implementation.
No subagent was started.

The eventual version is fixed only when its deployable software/installation
scope is complete; do not bump rc numbers for these debugging checkpoints.

## 2026-09-30 Close rc30 protocol-check failure

`64f3e69` passed dependency audits and all other jobs, but the complete
Python 3.13 job failed the same KEY_ATTEST trace twice. Current work retains
the 5 ms CPU limit, preallocates immutable scalar rules, adds real-clock
KEY_ATTEST regression coverage and bounded test-only failure diagnostics.
537 focused Python 3.13 cases passed locally. Run the new head's Linux CI;
if it fails, use the numeric diagnostic to locate the cause rather than
rerunning unchanged failures. Only terminal successful required checks allow
normal Ready/merge/read-back. No target-qualified or usable RC is claimed.

## 2026-09-30 Finish current rc30 candidate

The `4e9c394` frontend audit exposed high-severity brace-expansion findings.
After the additional moderate recursion-complexity advisory, the final
same-version patch pins only 1.1.21/5.0.12, preserves the audit level,
passes frozen installation, audit, 1201 Web/6 MV3 tests and lint/types/build.
Run this new head's required CI; repair failures without relaxing assertions.
Then normal Ready/merge/read-back follows the current AGENTS.md authority.
Main-agent risk checks are self-review, not independent PASS. After this
rc30 batch, the same first-usable-RC objective still needs production `_main`,
installer enrollment publication, positive legacy Codex Remote state and
client/target qualification. No S02–S14 work is started.

## 2026-09-30 R12 rc30 vendor enrollment candidate

当前只推进 [首个可用单机 RC](RELEASE_ITERATION_PLAN.md) 的 R12 依赖。
Draft #122 已对齐 `origin/main`，此前 head `8d11561` 的 26 项 CI 已终态
（24 success、2 prescribed skips）。当前 rc30 后继批次新增 installer
可复用的严格数据编码与真实文件/父目录替换、cleanup 失败测试；163 项
定向测试及 Ruff/Black 通过，待新 head 的 exact-head CI。
根据当前 AGENTS.md Review Protocol 完成主智能体自查并准确标注；
修复发现、相关回归与新 head 的必需 CI 通过后，可按已授权流程正常合并。
旧文档的额外独立审查机械门槛与当前 AGENTS.md 不符，不再作为恢复前提。
原 C3-b WIP 保全；#117 与 WS14 后续功能不进入本版。随后才处理
production `_main`、installer writer 与 D/E/F，真实 host/Secret/CLI/
recovery 验收仍需具体输入和授权。以下记录为历史行动项。

## 2026-09-29 首个可用 RC 收口

Owner 要求按版本迭代，不再以 70 项全量清单驱动并行旁支。当前唯一产品
目标与退出条件见 [逐版本计划](RELEASE_ITERATION_PLAN.md)。
`origin/main = 3a23f350582287de6b00499b8d4daa5d69c52011` 是 rc29
软件候选；六类 post-main workflow completed/success，但 R12 真实
host/client/CLI/recovery 未验收，不能称完整可用版本。

下一项是取得 Draft #122 的独立 Architecture/Security/Test 结论，处理
R12-C3-b 原工作区 WIP，再完成 `_main`、D/E/F 软件与制品。#117 保持
Draft，WS14 新功能暂停；现场输入缺失时报告本版阻断，不转去扩大功能
范围。Host、Secret、付费调用、重启、生产及发行仍按具体授权执行。
以下旧行动项保留为历史记录，不再驱动新的 WS14 批次。

## 2026-09-29 WS14 Workspace label command choices

`origin/main` remains rc27 merge
`458e7a5c9a87d50ebd9a4cd1040e7a51b148929a` with six successful
post-main workflows. Security-critical R12 rc28 Draft #122 has 26
terminal head checks (24 success, two prescribed skips) but awaits an
independent Architecture/Security/Test review; #117 remains Draft for the
same separate review gate. Continue independent WS14 software on
`codex/workbench-command-labels`: query-only label choices for an exact
formal Workspace route, current-session metadata validation, existing
CAS/Origin/CSRF API, exact ACK and GET readback, local panel invalidation,
pending/hidden/conflict fences, localization, desktop/mobile validation,
version and exact-head CI, then normal merge/read-back. The rc28 action
below is historical; real host/Secret/production gates remain untouched.

## 2026-09-29 WS14 visible-client label refresh

PR #120 delivered rc26 as merge
`88d2db79dd3cf58cfe0093ee90963f1ecfd45d35` with exact parents
`cab33679ec91bc2e46384f24e9a8cd3e4e985fa9` and
`816920a3c301569b8cd64ef99e7532537804d111`; six post-main workflows
completed successfully. On `codex/workbench-label-live-refresh`, finish
rc27's bounded visible-client Project/Workspace label refresh, prove
external-change convergence and hidden/pending/read fences, update the
version and acceptance record, then run exact-head CI, normal merge and
read-back. Cross-host synchronization remains S08. #117 stays Draft until
its independent security-critical review; R12 real-host/Secret/production
gates remain separate. The rc26 action below is historical.

## 2026-09-29 WS14 Workspace labels

Finish rc26 on `codex/workbench-workspace-labels`: shared-catalog formal
Workspace assignments, explicit Project+Workspace delete-impact count,
current-session Web readback and localized states. Run migration/foreign-key,
CAS/concurrency, API auth/Origin/CSRF, full Web/build, desktop/mobile browser
and release-version checks. Update exact local evidence, push feature branch,
obtain terminal exact-head CI, then normal merge and exact main/PR/workflow
read-back. Keep #117 Draft until its independent security-critical review;
continue R12 host and Secret gates separately. The prior rc25 action below
is historical and no longer directs this branch.

## 2026-09-29 WS14 Project label manager Web UI

PR #118's exact head `b7a529dfe92fabd0b83486ee6082296c64713fc9`
passed 26 terminal checks. GitHub generated main merge
`36aa7294c4d9c8eaa3283281022e61cf8bbc4f69` with that head as second
parent, but PR #118 remains OPEN in the API and no post-main workflows are
listed. Preserve both facts; do not force push, fabricate a merged PR state
or close the PR merely to remove the inconsistency. On
`codex/workbench-project-labels-ui`, finish rc25 Project-page label
create/assign/edit/delete with current-session GET readback, exact server
ACK, confirmed delete count, localization, desktop/mobile browser evidence,
version and regression checks under
[Project labels](../WORKBENCH_PROJECT_LABELS.md). Run exact-head CI, normal
merge and read-back. Subsequent Workspace assignment and cross-host label
sync remain separate. Draft A3 PR #117 awaits independent security-critical
review; R12 `_main` and real-host/Secret/production gates remain open.

## Historical 2026-09-29 WS14 label catalog and formal Project assignments

PR #116 delivered rc23 command-center navigation as merge
`3e0069381a4d8f867e333191f298b4847256d751`; six post-main workflows
succeeded. Draft PR #117 passed exact-head CI but remains unmerged pending
independent security-critical review and separate A3 content gates. Continue
on `codex/workbench-project-labels`: finish rc24 additive migration,
per-admin immutable label catalog, ordered Project assignment CAS, atomic
rename/delete, strict authenticated Origin/CSRF/no-store API, Audit,
capacity/concurrency/upgrade/restart tests and source/version records under
[Project labels](../WORKBENCH_PROJECT_LABELS.md). Then run exact-head CI,
normal merge and read-back. The Web picker and Workspace assignment follow
on the same shared label identity; they are not implied by backend delivery.
R12 `_main` still needs target fixed inputs and positive legacy Codex Remote
state; real-host/Secret/production gates remain separate.

## Historical 2026-09-29 WS14 authenticated command center

PR #115 delivered the internal staged Git selection policy as merge
`885c623cf1114d23c5fdc13503f4a2a598985c5b`; all six post-main
workflows succeeded. On `codex/workbench-command-center`, finish the rc23
fixed page/formal Project navigation UI under
[Command center](../WORKBENCH_COMMAND_CENTER.md): current-session API read,
desktop/mobile dialog, keyboard/focus behavior, stale-session fences,
localized errors, version and browser evidence. Then run exact-head CI,
normal merge and read-back. Wider command actions remain bound to their own
future permissions and service contracts. Resume A3 object-store provenance
and descriptor-held staged extraction as the independent content track.
R12 `_main` still requires actual fixed inputs and a positive legacy Codex
Remote state source; real-host/Secret/production gates remain separate.

## Historical 2026-09-29 A3 staged selection policy

PR #114 delivered rc22 Project favorites UI and its six post-main workflows
completed successfully. On `codex/workbench-staged-read-policy`, finish the
Runtime-only staged path/index eligibility check and negative fixtures under
[A3 patch content contract](../WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md).
Run exact-head CI, normal merge and merge read-back. Next, prove object-store
provenance and a descriptor-held bounded staged extraction before any
selector or encrypted content route. R12 `_main` still requires actual fixed
inputs and a positive legacy Codex Remote state source; the production
profile must keep failing closed until that graph is complete.

## Historical 2026-09-29 WS14 Project favorites UI and native read-back

PR #113 merged as `8fb017f3e294c4a303547da729b007e9605ed9a0`
with exact parents; its post-main Backend native job first failed on an
incomplete tmux pane-death status, then a same-SHA failed-job rerun succeeded.
Validate the scoped transitional-state test repair on rc22's exact head.
On `codex/workbench-project-favorites-ui`, complete the rc22 favorite control
under [WS14 favorites](../WORKBENCH_PROJECT_FAVORITES.md): server revision
ACK, conflict/uncertain GET read-back without PUT replay, session/visibility
fencing, desktop/mobile screenshots, local tests and exact-head CI. Then
normal merge and read-back. Named labels and command center remain later
WS14 slices; A3 content and R12 real-host gates remain separate.

## Historical 2026-09-29 WS14 Project favorites

PR #112 merged as `01a0ecd5eb21f74fe8605913bffd0c98bf322165`
with exact parent read-back and six successful post-main workflows. On
`codex/workbench-project-favorites`, finish the rc21 additive per-admin
preference schema, transactional revision/CAS service and typed authenticated
GET/PUT API under the [favorites contract](../WORKBENCH_PROJECT_FAVORITES.md).
The API must never call Runtime. Verify migration, concurrent writes, stale
conflicts, auth/CSRF/Origin and restart before exact-head CI and normal merge.
The Web toggle/pending/conflict flow, labels, ordering and command center
remain separate WS14 slices.

## Historical 2026-09-29 S02/WS14 Project search

PR #111 merged as `2d64ccde14877118f13f9c843d0c0aae0808dce0` with
exact parent read-back and six successful post-main workflows. Continue on
`codex/workbench-project-search`: verify the pure ranked matcher and the
authenticated Projects page against loaded formal Project data, nonmatching
and failed/loading states, desktop/mobile layout and visible rc20 version.
Retain the pinned source and attribution in
[Project search](../WORKBENCH_PROJECT_SEARCH.md), then run exact-head CI,
normal merge and read-back. Search remains read-only page state; favorites,
sync and the command center need separate contracts. A3 Git object provenance
and R12 `_main` are still unfinished, with real-host/Secret/production gates
separate.

## Historical 2026-09-29 S02/A3 descriptor-bound Git cwd

PR #110 merged as `6cd045dd8831283e2c0d0333a39461671b04bf76` with
exact parent read-back and six successful post-main workflows. Continue on
`codex/workbench-git-fd-cwd-v2`: verify the Linux-only fixed process runner
cwd descriptor inheritance and name-swap fail-closed behavior, then run
exact-head CI, normal merge and read-back. No Runtime action, API route or
patch bytes are added. The [cwd proof](../WORKBENCH_A3_GIT_CWD.md) and
[A3 patch contract](../WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md) retain object
store and index provenance, sensitivity and encrypted content as future
gates. The Owner's broad shell/file/plugin/Hub choice remains unanswered.

## Historical 2026-09-29 S02 Project work tabs

PR #109 merged as `1e3f463c5aafcc9ffdd266a94cfe35bfdca46c0a`
with exact parent read-back and six successful post-main workflows. Continue
on `codex/workbench-project-tabs`: finish bounded Project/Changed Paths/
Workspace navigation tabs with actual desktop/mobile rendering, route and
session fencing, and no implicit Runtime lifecycle operation. Record fixed
upstream source and legal attribution in
[Project work tabs](../WORKBENCH_PROJECT_TABS.md). Then run local regression,
exact-head Linux CI, normal merge and read-back. WS02 multiple conversations
and split panes remain separate. A3 patch content still needs complete Git
object provenance and child-cwd proof before extraction; broad permissions
await the Owner's semantic choice.

## Historical 2026-09-29 S02/A3 descriptor-held Git foundation

PR #108 merged as `692f58a5823c4a8fbb438e61f6575fc88150753f`
with exact parent read-back and six successful post-main workflows. On
`codex/workbench-git-content-root`, finish the internal rc17 Project/Git
descriptor custody and negative tests, then exact-head Linux CI, normal
merge and read-back. This source increment must expose no file bytes, Git
patch action, API route, browser selector or general filesystem gateway.
Afterward, prove complete object-store and child-cwd provenance before the
staged-only patch reader. The [A3 patch contract](../WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md)
keeps encrypted delivery, unstaged content and real-host qualification as
separate steps. Broad shell/file/plugin/Hub authority still awaits the
Owner's semantic choice.

## Historical 2026-09-29 S02/A3 patch content boundary

PR #107 merged as `87c0913f86324588608b191a8318115b36a59fbc` with
exact parent read-back and all six post-main workflows successful. Continue
on `codex/workbench-patch-contract` from that merge. Freeze the bounded,
sensitivity-aware Runtime Git patch reader and separate encrypted content
admission in [A3 patch content contract](../WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md),
then establish descriptor-held Project/repository and Git store/index
provenance before the staged-only Runtime extraction slice. No browser
content route precedes those proofs. Require fixed Git argv, current
Project/snapshot validation, bounded bytes/lines, helper-execution negatives
and explicit unsupported states. Unstaged content additionally needs
descriptor-bound working-file acquisition.
Document-only changes keep rc16; source behavior changes receive the next
aligned release candidate. Ordinary shell, arbitrary file browsing and
plugin/Hub authority still await the Owner's semantic choice. R12 `_main`
and real host/Secret/production gates remain separate.

## Historical 2026-09-29 S02 Changed Paths page

PR #106 merged as `c285872546f81c173c3e40e1711e8506c164cebc` with
exact parent read-back and six successful post-main workflows. Continue on
`codex/workbench-changes-tree`: connect its authenticated rc15 Project API
to a read-only AgentBox Changed Paths page. The candidate uses the migrated
folder ordering without fabricated line stats, presents staged/unstaged
metadata, and clears stale observations on Project/session change or browser
hide. Local Node 22 Web 1149/1149, MV3 6/6 and desktop/mobile browser E2E
100 pass/28 prescribed skips. Run exact-head Linux CI, normally merge and
read back. Then scope the next A3 sensitivity-aware patch/content contract;
ordinary shell, arbitrary file browsing and plugin authority still depend
on the pending Owner choice. See [A3 Git Changes](../WORKBENCH_A3_GIT_CHANGES.md).

## Historical 2026-09-28 S02 A3 bounded Git Changes metadata

PR #105 merged as `7ffc1734b0ce5a4f6fdc5575eaeac6804f2aca5c`
with exact parent read-back and six successful post-main workflows. R12's
Runtime profile gate is now software-delivered but enabled-mode composition,
positive legacy conflict observation, fixed manifest/native inputs and real
host/client/CLI evidence remain separate unfinished work.

Continue on `codex/workbench-git-changes` under
[A3 Git Changes metadata](../WORKBENCH_A3_GIT_CHANGES.md): complete fixed
Runtime `git.changes.list`, strict RPC, READY Project API, pagination and
negative tests. Local Git/Project API/release matrix (164 pass), Web/MV3
version/build checks and browser E2E (98 pass, 28 prescribed skips) now
pass. Run exact-head Linux CI, normally merge and read back. Then
connect the authenticated page to this real list and the migrated tree/order
logic; patch bodies and Files access need their own bounded sensitivity
contract. The pending broad-permission decision does not block this read-only
Project metadata slice.

## Historical 2026-09-28 R12 Runtime fixed deployment profile

PR #104 merged as `e6a5bf36636c5baf1225368c0acea1d89a73762e`
with exact parent read-back and six successful post-main workflows. Continue
on `codex/r12-runtime-deployment-profile`: the installer creates only the
canonical `disabled` Runtime profile at the fixed private path; an exact
loader checks parent and leaf provenance, and `_main` may run legacy mode
only when the profile remains disabled at startup. Explicit
`filesystem-v2` fails until the full application graph is wired. Local
installer/profile and focused entrypoint tests pass; Linux exact-head CI
and merge are pending. See [Runtime profile](../WAW_R12_RUNTIME_PROFILE.md).

After this software guard, replace the deliberate enabled-mode rejection
with one production composition from activated sockets, Runtime-only key,
epoch, verified manifest, deferred provider, current Project bindings and
one bounded bidirectional conflict authority. Installer CAS transactions
must coordinate API and Runtime profiles; no real host mode switch, Secret
or credential operation follows from a software merge.

## Historical 2026-09-28 R12-C3-b dynamic Runtime conflict state

PR #103 merged as `72b87c8333896eb6403e3a7e02516e4dcdf910c3`
with exact parent read-back and six successful post-main workflows. Continue
on `codex/r12-runtime-conflict-probe` with an internal, read-only snapshot
that maps current formal Project IDs back to their unique Runtime relative
keys and reports WAW supervisor/inflight/quarantine state to the existing
legacy conflict coordinator. Missing binding, ambiguity, concurrent change
and unknown state must block, never imply absence. Local executor tests pass;
Linux exact-head CI and merge are pending. See
[C3-b composition closure](../WAW_R12_C3B_PRODUCTION_COMPOSITION.md).

After this snapshot, bind a single closed production conflict probe to the
same executor and legacy managers. The legacy Claude/Codex observations need
bounded, fresh, read-only source evidence within the R12 start envelope;
do not use an always-ABSENT callback or a stale manager status cache to make
the software path appear complete. The [official Codex CLI command reference](https://learn.chatgpt.com/docs/developer-commands)
does not document `remote-control status`; local `codex-cli 0.153.4` help
also lacks it. Confirm a positive target-specific daemon state source rather
than interpreting an absent process match as stopped. Then close `_main` and remaining installer
manifest/native inputs, keeping real host/key/client/CLI gates separate.

PR #104's Linux native job reported 106 passed and one `tmux wait-for`
timeout in a pane-death test. The follow-up polls the exact retained pane
state and exact exit code within the same five-second budget, eliminating a
one-shot hook/waiter ordering race without relaxing the behavior assertion.
Require a new exact-head native/Backend pass before merge.

## Historical 2026-09-28 R12-D API disabled profile and singleton lock

PR #102 merged as `f70a3fdfda2439ad91a58aa9c38deb0e9c0f7417`
with exact parent read-back and six successful post-main workflows. Continue
R12-D on `codex/r12-api-profile-provision`: install the exact disabled
`/etc/agentbox/waw-api-profile.v1.json` and fixed
`/run/agentbox-waw-api/waw-api.v1.lock` with their loader-required owners
and modes. Existing valid `filesystem-v2` profile bytes must be preserved;
unknown or unsafe existing objects fail closed. No activation or mode update
is authorized by this software batch. Local fixture tests pass; Linux
installer/Backend CI and merge remain pending. See
[R12-D API resources](../WAW_R12_D_API_RESOURCES.md).

After exact-head CI and merge, continue the fixed public anchor/manifest and
Runtime `_main` composition. The separate mode CAS updater, static key
creation, external vendor enrollment and real host/client/CLI gates remain
later work. Keep the original checkout's WIP intact.

## Historical 2026-09-28 R12-D dormant installer socket substrate

PR #101 merged as `3d0ba375b5a616f1432789eb430ef1a7de4f3347`
after 24 exact-head successes, two prescribed skips, and six successful
post-main workflows. Continue R12-D on `codex/r12-installer-waw-sockets`:
install two fixed named socket units without enabling them; provision only
fixed non-secret directory structure; keep PID1 G3/HG-04 `NOT RUN`.

The current software candidate checks new directory collisions instead of
adopting them, stops any installed exact package WAW units before Runtime,
and removes newly introduced units when rolling back to an older backed-up
release. Simulated x86_64 fixture tests pass locally, but Linux
`systemd-analyze`, native installer CI and real host evidence are pending.
Next, run exact-head CI and normal merge/read-back, then continue fixed
manifest/policy/key provisioning and `_main` composition under separate
software and host gates. [R12-D socket substrate](../WAW_R12_D_INSTALLER_SOCKETS.md)
records the exact paths and incomplete inputs.

## Historical 2026-09-28 R12-D named socket admission refinement

PR #100 delivered the C3-b authority-deferred resource foundation as merge
`e3eb23930f6a34720ccf3ef604619acbc2d6cf4c` after exact-head CI and
six successful post-main workflows. Continue the production `_main` and
installer/client software work; do not claim host qualification.

Before writing two systemd socket units, close the loader's old FD ordering
assumption. [systemd.socket](https://github.com/systemd/systemd/blob/main/man/systemd.socket.xml)
does not guarantee relative order across socket units targeting one service.
Current `codex/r12-waw-socket-names` software candidate requires exact-two
unique control/stream `LISTEN_FDNAMES`, validates each FD's fixed path and
provenance, then normalizes the result. Linux CI and later PID 1 host evidence
must separately prove delivery; G3/HG-04 remain `NOT RUN`.

## 2026-09-28 C3-b deferred resource foundation — software candidate

Owner-approved [full capability plan](FULL_CAPABILITY_DELIVERY_PLAN.md) keeps
R12 production Runtime integration first. The latest main is rc14 merge
`986e8fa87c6d14030677c026342813c6921cc6f9`. An isolated branch
`codex/r12-c3b-resource-factory` carries the authority-deferred provider,
fixed executable/descriptor resource builder, distinct application owner,
native auth-probe path and cleanup repairs. Local related tests and Linux-target
type checking pass; exact-head CI and merge are pending. This is no production
entrypoint or host qualification.

The next software action is `_main` composition using installed activated
sockets, Runtime-only static key, epoch store and external vendor enrollment
without introducing a second authority. Keep the original checkout's C3-b
provider/tests, `.reasonix/`, `build/` and planning WIP intact. The exact
remaining issues and acceptance tests are in
[C3-b composition closure](../WAW_R12_C3B_PRODUCTION_COMPOSITION.md).

## R12-C2 C3-a composition closure delivered for review; C3-b next — 2026-09-15

M4 executor integration is delivered by PR #95: final head
`dfcefe87a2d53bac6eff73c7a63ea42d9ef52caf` completed all 26 terminal checks
(24 success, two prescribed rc8 skips), merged normally as
`4f374aef102c820a001517e14c49803da3e0ff73` with exact parent read-back, and
all six post-main workflows succeeded. Preserve this result.

The current branch `codex/r12-runtime-main` carries C3-a: the one-shot
`bind_native_probe_path` closing the owner↔factory↔process-port construction
loop, vendor digest per-entry `max_bytes`, the fixed-composition pin moved to
`WAWProductionAuthOwner`, and the API client per-action envelope
(`workspace.workspace.start` at 9.0s), closing decision
`R12-AUTH-PROBE-BUDGET-V1`. Independent review PASS with no P0/P1. Owner
review is held before merge per the 2026-09-15 milestone-review instruction.

C3-b after review/merge: production executor provider and the `_main`
production branch (activated sockets, static key, epoch store, provider,
application builder). Production profiles additionally require external
enrollment inputs (`vendor_version`, `codex_unauthenticated_output_sha256`,
D/G/H) and fail closed without them. No actual host/client/key/CLI activation
follows from the software merge.

## R12-B delivered; C1 candidate and C2 native work

R12-B/rc11 is delivered by PR #90: final head `64d45e7...` completed the exact
26-check contract, normal merge `e126e47172491f382efb2f5daaeac1e22a550ad6`
has verified parents and six successful post-main workflows. Preserve this result.
Continue the independently reviewed C1 static-key candidate on
`codex/r12-runtime-key`, followed by C2 fixed auth-isolation/executor and C3 main.
Native C2 work has separate file ownership; Python shared-file writes wait for C1
delivery. No actual host/client/key/CLI activation follows from the software merge.

## 2026-09-08 approved R12 execution

The Owner explicitly approved [PRP-2026-09-08-v1](PRODUCTION_READINESS_PLAN.md)
and instructed execution. Begin R12-A contract/input closure, then continue
dependency-ready R12-B/C/D/E/F software work on feature branches with CI,
normal merge and exact read-back. One persistent Goal is active; the main agent
owns the checklist and shared files. Mac Chrome/Edge terminal and mobile
management/exact Stop follow the plan's suggested scope, without claiming new
platform qualification.

Concrete host, Origin, client distribution and real key/login/paid-call/reboot
scope remain external inputs. Missing host evidence does not block independent
software work. Host/client activation and production/publication retain the
separate boundaries in the approved plan. The WEV-1 section below is historical
delivery context, not the current execution instruction.

## 2026-09-08 workstation evolution

The Owner requested a bounded incremental audit/research/implementation task.
Use [WORKSTATION_EVOLUTION](../WORKSTATION_EVOLUTION.md) as its task record and
[CAPABILITY_MATRIX](../CAPABILITY_MATRIX.md) as the evidence index. The current
software increment is WEV-1: invalidate browser Runtime observations after
interruption and re-read them on return before exposing lifecycle controls.
No automatic Start/Resume/Connect, new API/DB domain or production activation is
authorized by this increment. Branch: `codex/workstation-evolution`.

The seven-project research and WEV-1 implementation are merged through PR #87.
Head `80a6972466a514aa67577bb7812cf4c649a5983c` passed the complete 26-check
contract (24 success, two prescribed skips); merge
`b3e9cd5dbfbdca0c5e0cd652dc0cce7e1e53214e` has verified parents and six successful
post-main workflows. Preserve the completed tests, reviews and delivery record.

The next product-flow action is to establish the concrete R12 target and
authorized Runtime/Project/trust/key handling, then implement and verify the
five gates below. No other proposed feature is implicitly activated by WEV-1.
Later Files/Diff, Attention/Approval, Discovery/Resume and Task/Worktree proposals
need their own bounded contracts. R12 is still blocked on concrete target,
Runtime/trust/Secret scope and real-host evidence. The completed R11 record
below is historical context, not a command to repeat its work.

R12 must close all five [production bootstrap and host gates](../WORKSTATION_EVOLUTION.md#r12-production-bootstrap-and-host-gates):
production API mode/composition; Runtime filesystem-v2 builder and concrete
executor/key provider; activated sockets and peer/cgroup/isolation; managed CRX,
Native Messaging and trustd enrollment; real CLI login, input, return/reconnect,
exact Stop and reboot recovery. This is implementation plus host acceptance,
not a feature-flag change or a request to rerun synthetic tests.

Action ID: `DELEGATED-RUNTIME-RELAY-2026-09-03`

The Owner explicitly delegated software goal, plan and architecture decisions to
the Coding Agent and instructed continued development. The complete reviewed
[WAW stream supplement](WAW_ENCRYPTED_STREAM_DECISION.md) is accepted for software
implementation under [GOVERNANCE](GOVERNANCE.md). The previous R3 confirmation
blocker is resolved. Do not request the same software approval again.

## Active implementation

- rc8 is delivered by PR #83: documentation head
  710ceef696757a8a1f2a9165f2312672db57bb1e completed 26 exact-head checks,
  merged normally as 95bf65d6114008b962985f7311941499c961a7b8 with exact
  parents 87f5bce and 710ceef, and all six post-main workflows succeeded. This
  remains software-only evidence; no tag, release, host activation or R12
  qualification occurred.
- RC9 is delivered through PR #85: exact-head CI, normal merge, merge read-back
  and all post-main workflows succeeded. Preserve the immutable locale rule (only
  `navigator.languages[0]`, `zh` primary → `zh-CN`, otherwise English) and
  preserve technical values without translating or humanizing external protocol
  strings. R11 software rc6–rc9 is complete as software evidence; do not extend
  that result to R12.
- The fixed rc8 predecessor/artifact operations jobs are now version-aware and
  fail-closed: rc8 executes them successfully, while rc9 skips exactly those
  historical jobs and still requires current-candidate artifact checks and
  `release-gate` success. Preserve the fixed rc8 contract; skipped, failing or
  unknown results must never count as pass.

- rc9 version text is Python `0.3.0rc9`, npm `0.3.0-rc.9`, MV3 `0.3.0.9`.
  Production output must retain no test bypass; the distinct-origin Workspace
  harness is E2E-only and sensitive artifacts remain disabled. R12 stays
  independent, unstarted and host-gated. No tag, GitHub Release, production
  deployment, Provider credential operation or real host activation occurred.

- Historical rc6 work-unit and checkpoint evidence remains in the execution
  plan and current-state record. The rc8 and rc9 actions above are the current
  authoritative sequence.

- Historical rc9 foundation commit `184781c...` completed 20/20 exact-head
  checks. Its shared catalog, error-code mapper and route-state manifest are
  now incorporated in the delivered rc9 implementation; the page migration and
  bilingual visual matrix are no longer a pending implementation item. Current
  evidence is recorded in `CURRENT_STATE.md`; its CI/merge record is delivered.

- Preserve merged R0/R1/R2/R9.1/R10.1 and the verified delivery record, PRs #67–#72.
- R3/R4 are merged as PR #73 after 19/19 checks and exact read-back.
- R5 is merged as PR #74 after 19/19 checks and exact read-back. Cold-start/GC
  parser failures are fixed without relaxing the 5 ms budget.
- R6 is merged as PR #75 after 19/19 checks and exact read-back; staged ticket
  authority, atomic publication, reader handoff and cleanup/Audit fences delivered.
- R7 is merged as PR #76 after final independent PASS, 19/19 exact-head checks
  and exact read-back; Runtime encrypted stream/server and publication fences delivered.
- R8 is merged as PR #77 after independent PASS, 19/19 exact-head checks,
  normal merge, exact read-back and six successful post-main workflows.
- R9 is merged as PR #78 after independent PASS, 19/19 exact-head checks,
  normal merge `15a4632f915dd1e1bde19425e313b52ada27166f`, exact read-back and
  six successful standard post-main workflows.
- R10/rc5 is delivered by PR #79: final head `0d9e7c7...` completed 20/20
  exact-head checks and merged as `341a69bf...`; exact parent read-back, all six
  post-main workflows and dynamic Dependency Graph completed SUCCESS.
- PR #80 repair head `bbdd67c...` has terminal 20/20 CI after fixing the shared
  descriptor-release/inode-reuse issue. It verifies the current first-use/
  evidence checkpoint. Native/format follow-ups completed in `4222242...` 20/20
  CI. Do not merge before replay, controller composition and the remaining rc6
  acceptance set.
- Current evidence: the final local core matrix completed 216 plus 5 focused
  cases; independent Sol/xhigh review completed 244 cases with 1 Linux-only skip
  and 9 deselected, plus 8 encrypted-server non-UDS cases. Review is PASS with no
  remaining P0/P1/P2. Twenty-eight real-UDS cases are locally unverified because
  this environment returned `PermissionError` during socket setup. Ruff, Black,
  Linux-target mypy (256 sources), doc links (240) and `git diff --check` pass.
- The current uncommitted bounded-redraw slice has a neutral 24-row/60 KiB
  contract with row 25 and byte 61,441 as discarded sentinels. Held-FD tmux
  capture proves socket/pane/retained-pidfd identity before and after one shared
  one-second deadline; supervisor capture/cursor/baseline publication is atomic,
  and production capture callbacks are removed from registry/service/bootstrap.
  The unified focused matrix completed 341 tests with 9 Linux-only skips and 2
  local UDS cases deselected; independent Sol/xhigh review reports PASS with no
  P0/P1/P2. The new Linux native case requires exact-head CI; local UDS setup
  remains unverified after `PermissionError`.
- Head `adf44fc0...` ran the new real Linux capture successfully, then failed the
  native job at teardown because the test killed tmux before calling a helper
  that expects the tmux socket. The test-only follow-up removes that invalid
  cleanup assertion. Commit/push it and require a fresh exact-head native/full
  Backend pass before recording bounded redraw complete.
- Follow-up `f37f92d9...` completed the required 20/20 exact-head matrix. Linux
  native completed 73 cases; Backend Python 3.11 completed 3629 passed/44 skipped,
  with 3.12/3.13 also successful. Treat bounded redraw as verified and continue
  with `WAWRuntimeApplication` production composition and singleton ownership.
- The current `WAWRuntimeApplication` composition is uncommitted: typed Runtime
  key/executor providers and activated sockets have distinct one-shot ownership;
  stream, control and legacy share application start/close tasks and one dispatch
  gate. Partial production builders are private and weak-map provenance is gone.
  Incomplete construction retains a typed retryable owner. Provider closure waits
  for stream/control/lifecycle/legacy clean evidence. Independent Sol/xhigh review
  reports PASS with no P0/P1/P2; Linux-target mypy covers 260 sources. Production
  main, real key/provider and host activation remain disabled.
- `WAWRuntimeApplication` head `628e9c00...` completed 20/20 exact-head checks.
  Continue rc6 with the API singleton, one attachment/bind/control/relay owner and
  lifespan shutdown ordering; keep real key/provider and production activation in
  their existing host-gated scope.
- `AttachmentAuthority` shutdown fencing is implemented and independently reviewed:
  pending tickets burn, cleanup obligations survive invalidation, and only exact
  cleanup/Audit ACK reaches clean. Commit and exact-head verify this foundation,
  then implement the process lock and single bind/control/relay lifespan owner.
- Bind/control shutdown evidence is also complete locally: pending exchange,
  detached task, retained peer or uncertain FD close prevents clean. Commit and
  exact-head verify it, then continue process lock and stream-owner composition.
- Begin rc7 with named test-only checkpoints, manual promises, fake monotonic clocks
  and controlled partial-write sockets. Prove admission/stream/restart/shutdown/Stop/
  browser-lifecycle failure invariants before advancing to rc8 artifact rehearsal
  and rc9 full browser-selected bilingual UI.
- First integration head `e210d749...` completed 17/20 checks. Three Backend
  matrix jobs exposed one shared legacy regression: a clean non-fixed server could
  no longer restart without consuming a second epoch. The local reviewed fix
  restores only that compatible restart; fixed/control/poisoned/incomplete shutdown
  stays terminal. Follow-up `c534fe437...` completed the fresh exact-head 20/20
  matrix. Continue the remaining rc6 controller composition; do not merge rc6 until the full
  controller composition and rc6 acceptance set are complete.
- Locale remains fixed per document from only `navigator.languages[0]`: primary
  `zh` → `zh-CN`; all other, missing or malformed values → English. Technical
  identifiers remain English.
- Keep R7/R8 active lifecycle obligations explicit: 30s stale/60s grace,
  15min idle/8h absolute, Runtime health, current auth and positive cleanup.
- Resolve remaining software contracts with documented rationale and independent
  review under the delegated authority, rather than another mechanical Owner gate.

Each stage follows feature branch → exact-head terminal CI → normal merge →
exact read-back, updating CURRENT_STATE, the remaining plan and relevant scope
documents. Complex work uses sol; routine implementation/verification uses terra.

## Remaining evidence boundaries

Mac remains the development platform. Real host activation, production keys or
Provider Secret operations, publication and support promises require a concrete
scope/target and real evidence. Software decisions do not certify those gates.
The independent trust-provider deployment and actual CLI/PTY/isolation/restart
qualification remain required before full product completion. No synthetic
handler or passing codec test may be presented as a working terminal.
