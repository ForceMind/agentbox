---
schema_version: 1
verified_at_utc: "2026-10-01T12:27:09Z"
verified_by: "codex-deployable-installer-work"
repository: "ForceMind/agentbox"
---

# Current Verified State

## 2026-10-01 Web Origin/TLS configuration and fixed activation

Base HEAD/origin/main is f2af937dcf3c437409400ebcf1ba1d56c5a21f3a on
codex/r12-web-activation; previous PR #125 is merged, not a published version.
`configure-waw-web` now checks the complete current overlay against the active
cross-pinned release, fixed TLS leaf/key provenance, SAN/validity/key match,
and atomically changes only empty/equal allowed_origins and trusted_proxies.
Changing another Origin is rejected. Writes require existing offline/idle
evidence; matching interrupted config writes use explicit --recover.

`activate-waw-web` requires already committed browser configuration and a
started WAW activation record. It restarts only the independent HTTPS unit
after fixed nginx/API checks, rereads protected inputs and stops that unit if
startup fails. Runtime/API are not restarted. No real user-host execution or
provider login occurred. Certificate CA trust is not inferred from PEM checks.

32 configuration/publication/activation regressions, Ruff and 365-file mypy
pass. A native PID-1 CI probe now exercises the actual DynamicUser/LoadCredential
unit, HTTPS with a fixture trust anchor, and kernel write-denial; local macOS
skips this gated test. Its Linux result and exact-head CI still need read-back.
Automatic certificate issuance/renewal, bootstrap refresh, one-command setup,
actual PC/mobile CLI use and reboot/upgrade/rollback acceptance remain open.

## 2026-10-01 independent HTTPS Web ingress integration

PR #125 is MERGED. Exact source head
4f86c4d54d84d2a845dfaed23cfc0a56ffd20349 reached 24 SUCCESS/two prescribed
SKIPPED. Merge read-back and fetched origin/main both equal
f2af937dcf3c437409400ebcf1ba1d56c5a21f3a. Work continues on
codex/r12-web-activation in the existing managed worktree; original checkout
WIP remains untouched. This is software integration, not a published version.

7c6db085f5b71e00d639a16054df63565e5155a8 reached terminal exact-head CI:
24 SUCCESS/two prescribed SKIPPED, re-read from PR #125 during this task.
The current batch implements an
immutable overlay publisher and its focused regressions. It reads only
manifest-listed, SHA-verified Web source files, preserves the original release,
adds fixed public markers/bootstrap and a closed publication ledger, builds
Root-owned staging and switches only the fixed current pointer. Matching
recovery is explicit; source drift and foreign tree/pointer entries reject.
The `publish-waw-web` lifecycle/CLI now owns publication under the installation
lock and converts filesystem failures into installer errors. It also writes a
fixed Root-owned nginx configuration and separate `agentbox-web.service`.
Only `/api/v1/` proxies to fixed loopback `127.0.0.1:8787`; HTML/bootstrap/assets
come from the independent publication tree. Upstream X-Accel internal redirect
is ignored; API Content-Type/CSP/cache headers are replaced with data-only
JSON/no-store/sandbox rules. Static CSP, hidden-file denial, exact Host and
GET-only serving are explicit. Foreign configuration is never overwritten.

The ingress runs as a systemd DynamicUser with only CAP_NET_BIND_SERVICE;
Root-owned TLS files are delivered through LoadCredential. Automatic review
rejected CAP_CHOWN; the implementation removed Root worker switching instead.
32 publication/bootstrap/activation regressions, Ruff and 362-file mypy pass.
An actual nginx/TLS integration test passed in all four Ubuntu 22.04/24.04 and
Python 3.11/3.13 installer combinations (Deployment run 36859319313).
It checks SPA/static/bootstrap routes, unknown Host/hidden-file/missing-script
rejection, API JSON/sandbox headers and ignored malicious X-Accel-Redirect.
Fixture paths/ports/certificate replace production inputs; DynamicUser and
LoadCredential startup are not exercised by this probe. Local affected checks
passed 43 tests; systemd-analyze/nginx checks skipped locally on macOS.

No user-host service was started. Dependencies, TLS provisioning/renewal,
Origin/API configuration and explicit activation are not yet composed.
Platform write-denial, actual systemd credential startup, complete failure/
rollback and PC/mobile real CLI qualification remain outstanding. This batch
does not produce a usable version or authorize release publication.

## 2026-10-01 distinct HTTPS client profile candidate

Base e1055e0b2b7b03f4a1db82c55772bd99b05f1cb3 reached terminal CI:
24 SUCCESS/two prescribed SKIPPED. Deployment run 36809114137/job
110199972295 at 03:09:11Z emitted complete_remote_stopped_observed=true
alongside all seven prior actual cgroup creation/store/absence/cleanup flags.
The observer executes on actual Linux/non-root/native PID 1 with a selected
false executable and synthetic metadata; it does not qualify real vendor
Remote implementations or a complete application deployment.

Current code adds a separate HTTPS consumer/lease schema and canonical public
bootstrap encoder under ADR 0010. Explicit secure static-document meta markers
select it; otherwise the native path remains separate. Exact Origin, host,
revision, fingerprint, build, canonical fields/encoding and UTC validity are
checked with two bounded fresh no-redirect/credential-omitted reads. Rotation,
read loss, expiry, stale freshness, build/Origin drift, backward browser time
and close fence authorization. No native signature/persisted-floor/clock
guarantee is claimed. No plaintext terminal fallback is added.

70 HTTPS/native-consumer/hook/encrypted-controller Web regressions, Web
typecheck/ESLint, 17 public-codec/activation regressions, Ruff and 358-file mypy
passed. Evidence is client/file fixtures, not deployed HTTPS distribution or
actual vendor sessions. Main-agent self-review only. Root-owned publication,
independent static serving/proxy/CSP and complete composed install/client/CLI/
reboot/upgrade/rollback evidence remain open. No document markers or bootstrap
were published to a user server. Version stays rc30; no usable-release claim.

## 2026-10-01 complete UID Remote observation candidate

Base 537b02d85db7bad7a30e42e78da040ba8191acb1 reached terminal CI:
24 SUCCESS/two prescribed SKIPPED. Current code separates complete Linux
observation from the existing lossy boolean heuristic. Native systemd/public
namespace metadata, initial UID mapping, zero capabilities, unrestricted held
proc mount and two stable current-UID PID/start/executable/argv-hash snapshots
are required before observed STOPPED. Read denial, hidden/malformed/changing
processes and alternate Codex Remote executable evidence remain UNKNOWN.
No process text or argv is exported through API or logs. The actual supported
vendor Remote implementation still needs target qualification.

The WAW-only drop-in now uses ProtectProc=default, with the explicit privacy
tradeoff recorded in ADR 0011. Legacy/API/Worker and vendor isolation retain
their existing boundaries; no capability is added. Whole-template digest is
0f4723a099a7afb3d237ce38532d10d3d42c0b421969a5ccdea151d077ac9563.
Runtime status, protocol/API/Web metadata and localized confidence labels agree
on observed. The native PID-1 probe now exercises the actual observer; its
Linux result is pending this batch.

173 focused backend regressions, Ruff and 356-file mypy passed. Eleven Web
DOM/hook tests and Web typecheck passed. Actual Chromium rendered the observed
label at desktop 1280x800 and mobile 390x844 with no horizontal overflow (two
passes using mocked metadata); this is not real mobile-device or CLI evidence.
Main-agent self-review only. HTTPS trust/bootstrap, complete composed install,
actual double-CLI/core/reboot/upgrade/rollback qualification and final artifact/
install command remain open. Version stays rc30; no user-host operation/release.

## 2026-10-01 fixed activation transaction candidate

Base 41280ce50b97917282ac1a66e25c7e59461f538b reached terminal exact-head
CI: 24 SUCCESS/two prescribed SKIPPED. Current software adds activate-waw
--plan/--recover. Plan is read-only and explicitly does not observe the key.
Apply validates fixed enrollment/policies/units, offline services and no
remaining Runtime UID processes; it compares only the local Runtime-owned
public fingerprint with the enrolled anchor. No Root/API/Worker key read.

A Root-private journal pins version/host/digest and preparing/configured/started
phases. Atomic pending files have content-derived names, exact modes/owners and
explicit matching-prefix recovery. Paired profiles are published while offline;
the scoped drop-in directory rejects foreign entries. Named sockets start before
Runtime, then Worker/API. A failed start stops only fixed AgentBox services and
retains the recoverable configured state; no unknown process is killed/adopted.
Service-manager active checks are not graph/CLI/browser qualification.

49 activation/policy/manifest/host regressions, Ruff and 354-file mypy passed,
including profile/journal partial writes, mixed pair recovery, start failure,
key/enrollment/unit/drop-in drift and fixed command ordering. Evidence uses
local files and injected service/key observations; no actual user-host service
or credential operation occurred. Main-agent self-review only. Positive Codex
Remote evidence, HTTPS PC/mobile workflow and actual install/CLI/reboot/
upgrade/rollback qualification remain open. Version remains rc30, not a usable
release; no tag/publication/production support claim is made.

## 2026-10-01 fixed vendor-policy preparation candidate

Base 001c4bdd8acc3cfe42b328f36e2272e4ff9fcdab reached current terminal CI:
24 SUCCESS/two prescribed SKIPPED. Deployment run 36801295653/job
110175996950 at 01:29:36Z reported positive_absence_observed,
fixed_empty_cleanup_executed and partial_empty_cleanup_recovered all true,
alongside the prior four creation/FD/store checks. This is actual native
PID-1/cgroupfs producer and cleanup execution with synthetic authority and
empty workloads, not service/host reboot or actual vendor qualification.

The first sanitizer native job 110175996308 failed the incomplete-DCS exact
exit-74 check with tmux metadata 1::. Same-head retry job 110178385065 passed
without native source changes. The original failure remains recorded; its
root cause is unconfirmed, not claimed fixed by the retry.

Current software adds prepare-waw-policies --plan/--recover: exactly three
cross-pinned policies at fixed global Claude/Codex paths, Root-owned 444;
no key initialization, profile enable or service start. Plan does not write.
Apply requires inactive fixed services/sockets and complete Root-visible UID
metadata with no remaining Runtime processes. Different files/links/unsafe
directories reject before target creation; explicit recovery finishes only
matching safe prefixes. No Runtime HOME/credential read or generic command/path
action is added. 24 policy/manifest/guard regressions, Ruff and 352-file mypy
passed; evidence uses local files and injected host metadata, not user-host
policy preparation. Main-agent self-review only. Fixed activation, positive
Codex Remote, HTTPS browser/core CLI and full recovery qualification remain
open. No product version/tag/publication or user-host activation occurred.

## 2026-10-01 positive absence and fixed cleanup candidate

Candidate 001c4bdd8acc3cfe42b328f36e2272e4ff9fcdab is pushed on Draft #125
with exact remote read-back. CI is confirmed live, including Deployment run
36801295653/job 110175996950 for the native PID-1 probe. This post-push note
stays local for the next code batch; no docs-only CI rerun.

Synchronized base: ccf8bf537d4c1206ce786fedccec8006a9cc9f74 on Draft
#125; exact remote read-back and terminal CI confirmed: 24 SUCCESS/two
prescribed SKIPPED. The current follow-up connects the actual FD recovery
observer to the existing start path before executor side effects. It uses the
persisted generation, not the request's next generation, preserves bound host
and binding provenance, and imposes the existing observation timeout. Unknown,
live or failed observations retain quarantine. Status/reconcile stay
read-only. Recovery observation does not perform an ordinary cross-epoch write;
the registry's explicit CAS is the only commit path.

Earlier head 0d7d2b3ce6ea0cc2cfd64205107708135554daef reached terminal
CI: 24 SUCCESS/two prescribed SKIPPED. Deployment run 36792740947, job
110149149904 confirmed production_helpers_executed, limits_read_back,
existing_generation_rejected and fd_observation_persisted all true under
native PID 1. This is actual Linux helper/FD/store evidence with synthetic
metadata and an empty workload, not vendor/reboot acceptance.

Current changes add explicit compare-and-swap recovery in both Runtime stores
and integrate it into the existing internal cleanup acknowledgement. Fresh
new-epoch/new-invocation EMPTY_DURABLE evidence preserves logical identity,
controller policy and generation; host/binding provenance remains pinned.
Ordinary writes still reject epoch drift. Cgroup persistence precedes the
Workspace floor migration; interruption leaves quarantine set and exact
read-back can retry without lowering the floor. Older unresolved generations
remain fenced. No HTTP recovery action, generic path or command was added.

Current changes add the distinct v2 absence record described in ADR 0011;
current service/delegate FDs and repeated exact-component ENOENT are required,
with explicit absent Workspace/workload identities. Ordinary writes cannot
publish absence. Runtime removes only the durably empty exact old generation,
rechecking FD ownership/inodes/mount/limits, populated state and unknown leaves.
Partial workload deletion can retry from durable empty evidence; same-epoch
absence requires that prior emptiness and unchanged invocation/delegate facts.
There is no kill, recursive deletion or adoption of unknown generations.

152 recovery observer/store/lifecycle regressions passed; Ruff and 351-file
mypy passed. The native PID-1 probe now includes actual absent-directory,
full empty cleanup and interrupted-workload cleanup checks; its result is
pending this candidate. This is main-agent self-review, with local directory
and synthetic kernel/metadata fixtures. Whole service/host reboot, actual CLI,
upgrade/rollback qualification and fixed activation remain open, alongside
positive Codex Remote evidence and HTTPS PC/mobile workflow also remain open.
This batch is not a usable release. Product version remains rc30; no user-host
operation, tag or publication occurred.

## 2026-10-01 fixed durable storage and FD observations candidate

e474466733d75bb78a08e4b3644b97d8f466b437 reached terminal exact-head CI:
24 SUCCESS/two prescribed SKIPPED. Current _main creates fixed Runtime-only
Workspace/cgroup stores and forwards a bound FD observation factory through
the production graph. Installer provisions private 700 store directories;
the Runtime unit adds only their fixed writable paths. No API/Worker authority
or generic path/command action is added.

The factory records held service/delegate/workspace/workload identities, mount
and owner facts, actual limits and hierarchy populated/frozen state. It refuses
unknown child directories and reads state twice. STOPPED alone cannot claim
empty: positive populated=0 with no unknown leaves is required and the record
is written/read through the Runtime store. Workspace and workload limits now
both have finite closed policy values. The attestation codec accepts only the
exact generated 64-hex Workspace/generation component beyond the old 64-byte
component ceiling; arbitrary long path components remain rejected.

85 focused observation/production/setup/attestation/enrollment tests passed;
Ruff and 351-file mypy passed. These use explicit FD/kernel fixtures locally.
The native PID-1 probe now executes the actual factory with an empty workload
and Runtime-owned temporary store read-back; real Linux result is pending this
batch. Main-agent self-review only. Epoch/provenance migration, abandoned-group
cleanup and full restart/rollback acceptance remain required; this does not
claim reboot recovery complete. Fixed activation, positive Codex Remote state,
HTTPS Web and actual PC/mobile CLI workflow remain unfinished. No user-host
key/profile/service operation or product release occurred.

## 2026-10-01 durable port forwarding candidate

Latest synchronized head: e474466733d75bb78a08e4b3644b97d8f466b437 on Draft
#125, exact remote read-back confirmed. CI currently has 21 SUCCESS/two
prescribed SKIPPED and three live Backend jobs, no failure. This post-push
snapshot is local for the next code batch, not another docs-only CI restart.

Current application/server filesystem-v2 builders forward the same Workspace
attestation store, cgroup attestation store and factory into the existing
registry composition. The previous production signature dropped these inputs;
this closes that ownership/identity handoff gap. Regression verifies object
identity alongside key/provider/socket one-owner construction and cleanup.
43 application/bootstrap tests passed; Ruff and 349-file mypy passed.
Main-agent self-review only. Fixed _main store construction, real FD-backed
factory, epoch/generation transition and cleanup/restart recovery are still
required before durable recovery is claimed. No service/user-host activation.

## 2026-10-01 actual creation-helper Linux evidence

d313624e93aac9b6a9307457a138f2b2a68b6a18 on Draft #125 reached terminal
exact-head CI: 24 SUCCESS/two prescribed SKIPPED, no pending/failure.
Deployment run 36766671223/job 110062461054 at 19:35:41Z executed the actual
Runtime setup helpers under native systemd PID 1. It emitted production_helpers_executed,
limits_read_back and existing_generation_rejected all true, actual mount ID 418.
The fixture uses DynamicUser and synthetic metadata authority; cgroupfs,
namespace/ownership/controller/limit checks and helper code execution are real.
This closes the software creation-path Linux evidence gap, not cryptographic
admission, actual vendor session, host reboot or whole application qualification.

Durable Workspace/cgroup attestation composition, recovery/cleanup and fixed
service activation remain next. The production builder still has optional
attestation inputs without complete _main ownership; its in-memory defaults
must not be called recovery-ready. Positive Codex Remote and HTTPS Web/client
core flow also remain required. No user-host operation or product release.
This evidence snapshot is local for the next code batch, avoiding a docs-only
restart of the already terminal checks.

## 2026-10-01 fixed delegated cgroup creation candidate

Follow-up CI fixture adds a separate native PID-1 step that executes the
actual _open_scoped_workspace_root/_create_bound_workload_cgroup helpers.
It refuses an existing Runtime unit, uses only a uniquely marked transient
DynamicUser service, root-owned copied checkout packages and the CI Python
interpreter. Metadata authority is explicitly synthetic, while cgroupfs,
mount/owner/domain/controller checks and limit read-back are real. It tests
existing-generation refusal and cleans only its marked unit. No production
account, key, HOME, vendor session or credentials are involved. Static lint/
syntax pass; actual Linux result remains pending the new exact head.

Latest synchronized head: 714473bf786c7eaa33084eaa53608153fd3b5d40 on Draft
#125, exact remote read-back confirmed. Initial CI has 15 SUCCESS/no failures
with five pending checks. This post-push snapshot remains local for the next
code batch and does not restart unchanged CI.

fa2ae6e3c25f1e22923bb7aa0401e392c67654cf reached terminal exact-head CI:
24 SUCCESS/two prescribed SKIPPED, no pending/failure. Complete manifest
preparation remains disabled-mode software, not an activated deployment.

Current Runtime resources create/open only the scoped service workspace root
after exact non-root owner/group/mode and current RW-service/RO-global mount
verification. Empty domain/controllers are required and enabled controllers
are positively read back. The production provider requests create-only
Workspace/generation workload setup; identities are fixed from the authorized
tuple, limits are from the closed verified policy and are read back before
the existing cgroup handle is returned. Existing generations require
reconciliation; they are never adopted, killed or recursively removed.
Failure cleanup targets only newly created directories. Legacy private
resource-root opening and lifecycle freeze/kill write allowlists remain separate.

101 focused setup/resources/provider/transport tests passed; nine Linux cases
were skipped on macOS. Ruff passed; mypy passed 349 files. Setup fixtures
validate failure/control boundaries, not actual kernel controller creation.
The existing PID-1 probe proves the kernel hierarchy but does not directly
exercise this new production helper; real Linux integration remains required.
Main-agent self-review only. Activation, durable cgroup/workspace attestation
composition and cleanup/restart recovery, positive Codex Remote evidence,
HTTPS Web and actual PC/mobile CLI flows remain unfinished first-version work.
No product-version bump or actual user-host operation occurred.

## 2026-10-01 complete installation-manifest preparation candidate

Latest synchronized head: fa2ae6e3c25f1e22923bb7aa0401e392c67654cf on Draft
#125, exact remote read-back confirmed. Initial CI has 15 SUCCESS/no failure
and five pending checks. This post-push snapshot stays local for the next
code batch; it does not restart identical CI for documentation alone.

a417addf315ed9f1caf037d4ab18af351ef6961c reached terminal exact-head CI:
24 SUCCESS/two prescribed SKIPPED, no failure/pending. Current source adds
prepare-waw-manifests --plan/--recover/--json and connects the Runtime-only
key public pin to all 13 cross-verified manifest records. Release building
copies the exact five inert policy templates into the verified release;
preparation pins their bytes without claiming vendor/host policy qualification.

The issuer observes the physical ProjectRoot filesystem/inode, exact-six native
ELF identities and one immutable helper release. Held no-follow provenance,
source/parent revalidation, create-only publication, exact full-bundle checking,
explicit matching-prefix/link-pair recovery and rotation refusal preserve the
disabled-profile boundary. Fresh installation identity is derived in a distinct
domain from the unique Runtime public fingerprint, making unpublished recovery
deterministic; existing enrolled identity is preserved and drift is refused.
Plan does not initialize a key or write manifests. Private key bytes do not
enter this issuer or the Installer's public-output consumer.

33 manifest/preparation/enrollment/build tests passed with explicit binary/key
fixtures; Ruff and 348-file mypy passed. Main-agent self-review only. This is
actual software wiring, not a real user-host preparation or activated session.
Linux packaging/whole-source CI is pending this candidate. Delegated root and
workload creation, activation, positive Codex Remote evidence, HTTPS Web and
actual PC/mobile CLI/recovery acceptance remain open. No product version/tag,
public install command or user-host activation occurred.

## 2026-10-01 Runtime-only initial key software

Latest synchronized head is a417addf315ed9f1caf037d4ab18af351ef6961c on
Draft #125, exact remote read-back confirmed. Initial matrix snapshot has
15 SUCCESS/no failure and five pending checks. 1db8428's Backend failure was
Black after a final test-import change; a417add corrects that one test layout
and verifies idempotent Black formatting for all five changed Python files.
Do not label the new head fully green before terminal CI. This post-push
snapshot remains local for the next code batch, avoiding a docs-only CI restart.

591d86f4f4aca6d0c079962c1d930f4a77b19a85's dependency repair reached terminal
exact-head CI: 24 SUCCESS/two prescribed SKIPPED, no pending/failure.

Current code adds the fixed local `python -I -m agentbox_runtime.waw_key_initialize`
command under the exact non-root Runtime account. Disabled-profile first setup
may create one private 32-byte key; enabled mode is read-only. The existing
startup reader still never generates a missing key. Held no-follow parents,
directory lock, exclusive private pending publication, fsync, mode/owner/link
checks and parent revalidation fence creation. Explicit disabled-mode recovery
handles only an unpublished prefix/full pending key or exact two-link pair.
Missing enrolled keys, mismatched pending files, symlinks and unsafe provenance
are rejected; no automatic rotation is introduced.

Stdout is a closed schema plus public fingerprint, never private material.
Installer HostOperations invokes only fixed runuser/Runtime/module/recover
arguments from a fixed installed release, kills the child process group on
failure/timeout, and rejects oversized/duplicate/extra/untrusted public output
without printing its bytes. Fixture HostOperations cannot invent a production
fingerprint. The complete manifest issuer still needs to call this operation;
no apply/profile activation path is advertised as complete yet.

92 focused Runtime key/application/installer Host regressions passed on private
test data; Ruff passed and mypy passed 346 files. Main-agent self-review only.
Actual Linux non-root command/installed-key evidence and exact-head CI remain
pending this batch. No actual user-host key, Secret, profile or service was
created/activated. The deployable first-version goal remains open.

## 2026-10-01 restart-safe enrollment inputs candidate

d41974dd83a9c954c5a879e204e71b43147d304a's Backend matrices, native,
installer and frontend/E2E checks passed, including the actual Linux FD test.
The earlier wire fixture failure did not recur; its root cause remains
unproven and the production budget/assertions remain unchanged. Terminal CI
has 19 SUCCESS, three dependency-skipped jobs and two Release failures.
The direct Release failure is unchanged pip-audit detecting four virtualenv
21.7.4 advisories (PYSEC-2026-4011/4012/4013/4014). Follow-up pins virtualenv
21.7.13 plus its required python-discovery 1.6.0, matching downloaded wheel
hashes to official PyPI JSON. Both dependency closures satisfy the existing
75-entry lock across Python 3.11–3.13; targeted audit reports no known findings.
See [upstream virtualenv fixes](https://virtualenv.pypa.io/en/latest/changelog.html).
No audit exception, runtime dependency, product version or host activation is
introduced. Complete exact-head CI for this lock repair remains required.

3b00cb4ba5bb93e8e2421a4e9da288326cf21143 reached terminal CI: 21 SUCCESS,
two prescribed SKIPPED and three Backend matrix failures. Deployment's actual
two-instance PID-1 probe passed (36743842988/job 109984874332): physical fsid/
inode stayed equal, scoped RW/global RO/outside denial passed. Both namespace
and mount numbers were equal/reused in this sample; no changed-number or reboot
proof is claimed. The real Linux FD test exposed a pre-existing off-by-one
fdinfo parser: line[7:] retained the tab in mnt_id, rejecting valid decimal IDs.
The correction removes the exact separator and keeps duplicate/invalid rejection.

The 3.11 matrix also failed one existing wire fixture with PROTOCOL_INVALID;
cause is not established. Failure-only fixture diagnostics now include bounded
numeric type/sequence/CPU duration; protocol assertions and the 5ms deadline
remain unchanged. Local wire/namespace/transport regression passed 356 cases,
ten Linux skips; Ruff and 343-file mypy passed. This does not turn 3b00cb4 into
a green head or prove the unrelated wire issue resolved. Inspect the next
exact-head real FD and full protocol/Backend results before readiness claims.

530fdf51d517da7245eb1cd253c5bb4368ec18f3 is synchronized on Draft #125 and
reached terminal exact-head CI: 24 SUCCESS/two prescribed SKIPPED, no pending
or failing checks. It is still not a deployable release.

Current installer-facing correction adds the distinct runtime-namespace-v1
binding: persist ProjectRoot filesystem ID/inode and observe actual FD mounts
per Runtime namespace; observe current cgroup device while retaining exact
scoped/global mount, ownership and limits checks. v2 cross-pins require one
consistent profile and reject v1 downgrade. New helper inventory locations are
closed to three fixed names under one immutable installed release, retaining
all no-follow/provenance guards. This resolves the current-symlink conflict;
it does not enable arbitrary executable paths. ADR 0011 records the rationale
and software-decision delegation.

241 affected profile/manifest/transport tests passed locally, with ten Linux
checks skipped on macOS. After adding the downgrade assertion, the new focused
selection passed 31 cases/one Linux skip; mypy passed 343 files and Ruff passed.
The real Linux FD test and two-instance PID-1 namespace probe remain pending
this candidate's CI. Main-agent self-review is not independent review.
Complete manifest issuance, Runtime-only key initialization, enrollment/profile
activation, delegated root/workload creation, positive Codex Remote evidence,
HTTPS Web bootstrap and actual PC/mobile CLI/recovery paths remain open.
No new source version/tag/release or actual user-host activation occurred.

## 2026-09-30 fixed production entry candidate

Latest synchronized head: 530fdf51d517da7245eb1cd253c5bb4368ec18f3,
Draft #125 exact remote read-back confirmed. Initial CI snapshot has six
successful checks, no failures, remaining checks pending. A transient local
ENOSPC prevented the first staging attempt; no files were lost or reset.
The subsequent no-cache Ruff, exact staging, commit and push succeeded.
Disk availability was then 2.1 GiB; no user data/caches were deleted.
This post-push snapshot is carried locally into the next code batch instead
of starting an otherwise identical CI run for documentation alone.

Integration follow-up: the production legacy-Claude lookup rejected WAW's own
in-flight start, causing a self-conflict. The formal-to-key read now fences
binding mutation/quarantine/ambiguity but permits an in-flight WAW operation;
legacy admission still rejects those operations through managed_conflict_states.
Start snapshot/commit pins remain. A test with the real executor/coordinator/
production bridge proves both AgentTypes start and exact Stop while legacy
Claude/Codex starts are rejected. Its vendor observations are explicit fixtures,
not real CLI evidence. 117 executor/production/conflict tests passed; mypy
passed 341 files. Entry-only RPC tests passed five cases. Full local RPC tests
also exposed macOS-only AF_UNIX length, epoch/peer-credential failures; assertions
were not weakened and Linux CI remains the required full RPC evidence.
e0856be read-back has no failing check, 21 SUCCESS/two SKIPPED with the three
Backend matrices still running; this is not a terminal all-green claim.

Follow-up: b966480's native, four installer, frontend and E2E checks passed.
Release Candidate failed its unchanged pip-audit gate: build-only urllib3
2.7.0 now reports CVE-2026-97687/97688/97689. The official 2.8.0 release fixes
the three advisories; only its build-lock entry is updated, with downloaded
wheel SHA256 matched to PyPI JSON. Python >=3.10 covers this project's
3.11–3.13 range. No advisory is ignored and no runtime dependency is added.
Complete exact-head CI remains required before any merge/readiness claim.
Its Backend matrix also identified the old runtime_rpc test that required the
unimplemented-entry exception (3.11: 4485 passed, 83 skipped, one failed).
The replacement checks actual enabled-profile routing and failure propagation,
while preserving the assertion that no standalone legacy server is constructed.
The updated entry/RPC tests pass locally; this does not convert the old failed
head into a full CI pass.

Current Draft #125 continues from 94b92d4; fetched origin/main remains
19f8c5125d5a831e3db2d9724a1cc7985b091294. 94b92d4's native and installer
checks passed, but all three Backend quality jobs failed Black on one
waw_runtime_resources.py expression. The exact job log (109885521498)
identified the formatting mismatch; this batch corrects it without changing
resource behavior. Do not describe 94b92d4 as fully green.

The filesystem-v2 branch of Runtime _main now calls the production application
builder. It pins Runtime/Control Plane account identities and exact allowlists,
fixed manifest/public/epoch/key paths, two named systemd sockets, one provider
and one executor. SIGTERM/SIGINT, cancellation and startup/serve failures join
the application cleanup owner. Only RuntimeAttachmentLease is allowed in the
encrypted production path; API ActiveAttachment is rejected. Fresh legacy
observations run on the event loop from start worker threads with a bounded
wait, binding recheck and UNKNOWN on missing evidence. There is no process-
absence-to-STOPPED conversion. Main-agent self-review is not independent review.

91 focused application/provider/profile/scoped tests and 139 Runtime executor/
conflict/server tests passed (overlapping selections, not 230 unique tests).
Ruff passed; mypy passed 341 files; changed Runtime files match Black.
These are software fixtures, not a real activated service or vendor session.
Complete generated manifests, delegated workspace directory, key/enrollment
and profile activation remain installer prerequisites. Positive Codex Remote
STOPPED evidence, HTTPS Web bootstrap, PC/mobile CLI flow and restart/rollback
acceptance remain first-version blockers. No product version/tag/release or
public install command has been issued. The current delivery checklist remains
open; the source startup entry does not close it.

## 2026-09-30 scoped delegation Runtime wiring candidate

88d1e99's Deployment native PID-1 probe passed on Ubuntu 24.04: emitted
scoped_write/outside_write_denied/global_mount_read_only/subtree_mount_read_write
all true. Run 36708294115, job 109863711328, step at 11:24:46Z. Its unrelated
Backend native job 109863711471 failed the incomplete-DCS pane exit assertion
after five seconds with observed 1::; do not call this head fully green.
The assertion/expected exit 74/time limit remain. A test-only bounded numeric
pane diagnostic is added to locate the failure; no terminal/argv/env capture
or unmodified rerun substitutes for evidence.

Current startup wiring distinguishes the accepted delegated-subtree-v1 policy
from legacy private. The shared resolver binds only the fixed service path and
agentbox-runtime-workspaces component. Codec pins the exact new Installer
drop-in SHA; resource opening and FD verification use the same resolver.
The scoped mount checker requires exact service-relative mount root/device,
RW service bind, RO global mount and no outside RW cgroup mount. Its root FD
must be owned by the exact non-root Runtime UID/GID and not group/other writable.
The drop-in is packaged as an explicit enrollment input, not activated by this
candidate. Legacy private fields/path behavior stay separate.

Focused codecs/resources/mount tests passed 135 cases; full mypy passed 339
files and Ruff/doc links passed. Native Linux diagnostic and complete startup
still need exact-head CI. Missing generated manifests, key/profile activation,
production _main and Web client/core flow remain current first-version blockers.
Delivery correction is recorded in RELEASE_ITERATION_PLAN's top checklist;
this is internal startup work, not another product release.

## 2026-09-30 Owner selected the recommended architectures

Owner instructed “按你说的做” after the two concrete recommended decisions.
ADR 0010 HTTPS Web profile and ADR 0011 alternative A (255-compatible scoped
delegation) are accepted for software implementation. This supersedes the
authorization blocker below; activation/support still requires real evidence.
The same complete deployable goal is active; no version bump or later feature
expansion follows. Original checkout WIP remains protected.

Current implementation starts with a CI-only native PID-1 probe of actual
delegation: a fixed, uniquely marked transient DynamicUser service, boolean
ProtectControlGroups, exact service-subtree ReadWritePaths and a supervisor
subgroup. It tests controller/limit writes, moving only its own PID, outside
write denial, ro global/rw scoped mount observations and leaf cleanup. Unit
ownership is checked before cleanup; bounded RuntimeMaxSec prevents an
unattended probe. No production account, key, credential, HOME or unit is used.
Local source syntax, Ruff and doc links pass; macOS cannot supply the host
evidence. Do not issue a manifest or enable the new model until this probe and
the complete qualification succeed. Web implementation follows the accepted
profile, with its explicitly weaker independent-client guarantee recorded.

## 2026-09-30 verified checkpoint and architecture dependency

Draft PR #125 exact head a091701178179d0d319729e88a1fa543c1db3533 now has
24 terminal SUCCESS and the two prescribed historical SKIPPED checks, with
no pending/failing check. Backend watch run 36701077638 exited successfully.
No merge/tag/release/deployment occurred; the version remains rc30.

The architecture authorization dependency has persisted through three
consecutive goal turns. ADR 0010 (PC/mobile Web trust assumptions) and ADR
0011 (actual cgroup/server compatibility) are still Proposed, with no Owner
reply observed. Manifest issuance depends on the selected namespace/path
contract; Runtime activation depends on those real resources; ordinary mobile
connection depends on the Web trust decision. Do not silently choose either
architecture or repeat CI/status commits as work. Preserve this exact-head
checkpoint and await the already requested decisions. The complete deployable
goal is not achieved, and unrelated later capabilities stay frozen.

This is local post-CI documentation WIP, intentionally not pushed just to
restart checks. Original checkout WIP is untouched. After Owner replies,
continue the same branch/PR and version, revalidate live Git, implement the
selected dependency and carry this snapshot into that code batch.

## 2026-09-30 actual cgroup compatibility conflict

9dda54d's exact-head CI is terminal with only the prescribed historical skips;
no remaining running or failing check was observed at readback. PR #125 stays
Draft because complete manifest/key/profile/Runtime and client flow are absent.

Manifest v1 requires ProtectControlGroups=private, but the current platform
baseline is systemd 255. Official versioned exec manuals show 255/256 accept
only booleans, while 257 adds private/strict. The legacy installed unit uses
true with no delegation, so it cannot be hashed into a valid active WAW policy.
The name-only compatibility checker incorrectly treated private as a 232
feature. Current WIP fixes value-aware/last-assignment/unknown-value checking;
existing boolean service support remains unchanged. 54 focused compatibility,
asset and platform cases passed with one local systemd-analyze skip; mypy
and Ruff passed. This is not a qualified WAW host or a new version.

ADR 0011 records two concrete alternatives: a separately versioned, scoped
delegated-subtree policy compatible with 255, or a private profile requiring
257 plus actual image/namespace qualification. Owner authorization is pending;
do not silently weaken the existing private contract, drop legacy support,
fabricate namespace observations, or install arbitrary replacement systemd.
The independent Web trust authorization (ADR 0010) is also still pending.

## 2026-09-30 staging recovery exact-head deployment evidence

Commit 9dda54d3d24adfe57dcf2f92544ba5a86ca5b0d5 is pushed to Draft PR #125.
Deployment run 36697969316 completed all four installer matrix jobs and
deployment-gate successfully. Job 109830394190's dedicated Linux/root step
"Verify actual native-helper build, retry and Runtime-owned epoch bootstrap"
ran successfully from 09:44:31Z to 09:44:37Z. This is real CI filesystem/build
evidence for the fixed epoch and helper paths, with isolated temporary data;
it is not a deployed host, real provider login or PC/mobile core-flow claim.
Other exact-head checks were still running at the last readback. Preserve
this post-commit evidence as local doc WIP until the next validated batch;
do not restart the current CI solely to commit this snapshot.

## 2026-09-30 same-artifact staging recovery candidate

PR #125 remains the single deployment Draft; version stays rc30. The
03ca4ed head completed native, deployment matrix, boundaries and several
other checks, but Backend/Release Candidate failed the unchanged packaging
contract forbidding sudo in the Release workflow. The failing Release unit
test was test_release_packaging_compatibility_lock_and_gate_are_fail_closed.
The new root fixture step is moved to Deployment; the sudo prohibition and
release gate assertions are preserved. Both focused workflow-contract tests
pass locally. No unchanged failed job is rerun as a substitute for repair.

Current software adds resume-install and bootstrap --resume. Only fresh,
unactivated schema-3 staging records may continue with the exact archive
digest, account/group identity, fixed-file/dir observations and original
transaction/resources. DB, receipt/current, unknown activation resources,
old logs, drift, migration/activation steps and unsupported states refuse
before continuation. Repeated staging failures retain the same proof;
accounts/configuration are not replayed. This does not close account-creation,
partial preflight, upgrade staging or all recovery requirements.

Self-review found the generic root-parent writer could not initialize the
fixed Runtime-owned epoch directory on a real host. Its general guard remains;
the fixed epoch initializer now validates root ancestors plus the exact
Runtime parent, holds no-follow FDs, creates exclusively, writes/fsyncs,
sets Runtime ownership and checks readback identity. A dedicated Linux/root
case asserts initialization, reuse and continued rejection by the generic
writer. This new case is pending CI.

Local evidence: 124 passes/3 Linux skips/1 known Mac setgid case deselected
for lifecycle/native/recovery; later 47 downloader/recovery/host cases pass.
Full Linux-target mypy passes 337 files; Ruff and source boundaries pass.
No new artifact publication, real CLI login, target activation or complete
PC/mobile core-flow evidence exists. Full manifests and production _main
remain unfinished; ADR 0010 architecture authorization remains pending.

## 2026-09-30 deployment Draft CI feedback

PR #125 is Draft/Open at first checkpoint
c05cc3d56410003dde06de42bd1793d2c3f62762. Version remains rc30; no release
or deployment is claimed. Release run 36691377561 / job 109809151521 passed
the actual Linux/root native-helper compilation and interrupted-retry step,
and the artifact-only offline install smoke. The complete run failed:
repository-boundaries rejected process execution in the new native module,
and root pytest's default development configuration polluted the checkout,
causing a later non-root configuration read to fail.

The follow-up moves both fixed build/check actions and process-group cleanup
into the already allowed Installer HostOperations, without expanding the
subprocess whitelist. Root CI configuration/data/pytest state now lives in a
dedicated runner temporary fixture, with bytecode writes disabled. The local
source-boundary check passes. Follow-up native/host/publication tests passed
37 cases with two Linux/root skips; full mypy passed 336 files and Ruff passed.
These repairs require a fresh exact-head CI result. PR stays Draft while the
complete deployment flow, staged recovery and Web trust implementation remain.

## 2026-09-30 deployable-version work in progress

Owner now requests a server-side one-command installer that they execute
themselves, with PC and phone support. No SSH target is required from the
Owner before independent software work. DEPLOYABLE_RELEASE_PLAN records
this scope and keeps the full core-flow acceptance; it is not replaced by
a software-only rc number or a desktop-only implementation.

The clean managed worktree now uses codex/r12-deployable-runtime from main
19f8c5125d5a831e3db2d9724a1cc7985b091294. The original R12 checkout and
the rc30 worktree's post-merge doc/build WIP remain separate and untouched.
Current uncommitted work adds a fixed installer publication/recovery module,
the actual enroll-waw-vendors CLI, manifest/profile currentness checks,
read-only --plan and explicit --recover. Publication is create-only,
idempotent, descriptor-held and never enables Runtime or reads credentials.
14 publication/CLI tests passed, including full cross-pinned fixture input;
the wider enrollment/build matrix passed 59 tests. Linux-target mypy passed
333 files and Ruff passed. These are local software/fixture observations,
not actual server/CLI qualification.

The offline release bootstrap now selects only supported fixed /usr/bin
Python candidates (3.11/3.12/3.13); installed venv creation uses that running
interpreter. Two selection tests and Bash syntax validation passed.
A broader script run had 73 passes and two existing Mac platform-order
failures before malformed-version/checksum checks; no assertion was relaxed.
New Linux CI is still needed. No new version, public release or installation
command URL has been issued for this incomplete iteration. The checkpoint
is for Draft CI verification, not a deployable release or merge decision.

Owner selected PC and phone browsers first; native Apps remain later scope.
ADR 0010 is Proposed and explicitly describes the weaker client assumption
relative to the managed native provider. Its architecture authorization is
pending; no page fallback or production trust gate has changed.

installer/bootstrap.sh now requires a fixed release version and independently
pinned archive digest, uses only the repository's HTTPS release URL, bounds
downloads/extraction, rejects archive links/traversal/collisions, then executes
bundle verification and plan before optional --apply. It does not use latest
or downloaded checksums as its trust anchor. No public release URL exists yet.
The downloader, interpreter and publication focused run passed 39 cases;
these include local transport/platform fixtures, not a real Linux install.
Bash syntax, Ruff and Black checks passed for the new files.

Server-side resource generation and production _main are still unfinished.
Installer apply now prepares the three fixed native helpers from verified
release sources on the target Linux host, with fixed gcc/binutils dependencies,
version/closed-command/hardening checks, an exact source/output digest ledger
and atomic directory publication before activation. Installed-state,
rollback/uninstall/retention verification explicitly validates this closed
generated subtree; the original artifact manifest is unchanged. No compiler
or command input is exposed to Web/API/Worker.
The local installer/native/platform/retention/host matrix passed 145 cases,
with one unchanged Mac setgid-directory assertion failing and two Linux/root
build cases skipped. The lifecycle fixture now explicitly models x86_64
OpenCloudOS instead of borrowing the test Mac's ARM architecture. The separate
platform rejection tests remain intact. Linux CI includes actual compilation,
hardening and failed-build retry, and has not yet run for this source batch.
Full Linux-target mypy passed 336 files; Ruff passed.
The later focused native/publication run passed 24 cases with two Linux/root
skips. It includes actual timeout/cancellation of a child process group and
proves that no child completion output is written after cancellation.
Helper-level build retry is covered separately from whole-installer recovery:
a fresh-install journal already classified as staged still lacks an explicit
resume operation. That existing recovery gap must be closed before delivery.
The current managed Chromium trust chain cannot be assumed to work in
ordinary mobile browsers.
Paseo's fixed connectivity/pairing source was re-read at
30178c4f58b67f8472901356e1484022bd835de0. The selected cross-platform
trust/connection contract must preserve AgentBox boundaries and get the
required architecture decision before any production activation.

Next: implement full trusted-resource generation and production Runtime
composition, including an authoritative positive Codex Remote conflict source.
Keep PC/mobile acceptance explicit, preserve data and
recoverability, and do not claim a deployable core flow before it is proved.

## 2026-09-30 rc30 protocol validation follow-up

On head `64f3e69c4c451cc818295fe0fbb1d6c6d80c8d96`, all jobs except
Python 3.13 reached successful terminal results or the two prescribed skips.
The full 3.13 job failed twice at the unchanged four-leg failure trace's
`KEY_ATTEST` decode. No third blind rerun was requested. The parser's 5 ms
CPU budget path is a suspect, but suppressed exceptions in those logs do not
prove its root cause. Local isolated Python 3.13.15 checks passed all 77 stream
cases after full-suite collection. A complete Mac diagnostic hit unrelated
Helper socket/platform failures and was stopped; it is not Linux evidence.

The current follow-up preallocates immutable enum/bounds tables in the wire
validator, retaining exact values, per-leg close rules and the unchanged
`VALIDATION_CPU_NS = 5_000_000`. Fresh-interpreter real-clock tests now include
KEY_ATTEST, including the 5000-decode mixed-profile test with normal GC.
The failing trace has bounded numeric CPU/GC/cause-location diagnostics only
when the original decoder raises; it still raises the original error.
Python 3.13 focused wire/stream/enrollment/provider/release tests passed
537 cases; Ruff/Black and Linux-target mypy (317 files) passed.

Paired synthetic KEY_ATTEST measurements on the same Mac interpreter/input,
5000 calls per implementation with alternating order and real thread CPU:
before median/p95/max 248063/366167/595959 ns, after 242958/358500/486541 ns.
Both remained within 5 ms; this small local improvement is not proof that the
Linux failure is fixed or caused by GC. New Linux CI remains required.
The scope stays rc30; host/client/CLI/recovery qualification remains open.

Sections below are historical snapshots.

## 2026-09-30 final rc30 brace-expansion correction

The `7365e4e` dependency review found the additional moderate advisory
GHSA-q2hr-2g5m-vwhr in brace-expansion 1.1.20. Final scoped overrides now
use 1.1.21 and 5.0.12, covering both high recursion issues and this quadratic
rewrite issue. No other dependency version was changed. Frozen installation
with scripts disabled passed; moderate-level audit identifies only the two
pre-existing Vitest/@vitest-mocker findings (GHSA-82fw-gwwq-j7x9), with
0 high/critical. The current high-level audit and dependency-review policies
are retained. No finding was suppressed.

Node 22.23.2 Web tests passed 1201/1201, MV3 tests 6/6, with lint/typecheck
and production builds passing. The corrected head still requires its full
CI before normal merge. Main-agent self-review follows the current AGENTS.md;
the original R12 WIP remains untouched and real host/client/CLI/recovery
qualification is unfinished. Earlier patch attempts below remain historical.

## 2026-09-30 rc30 dependency audit recovery

Head `4e9c394188e624aab5c75049441eb043f553a8af` reached terminal
CI with a frontend-audit failure: newly updated advisories
GHSA-qhr7-859c-m2p7 / GHSA-6j4f-fj2g-mc7p affect the previously locked
brace-expansion 1.1.18 and 5.0.9. This same-rc30 correction adds scoped
overrides for patched 1.1.20 and 5.0.11; pnpm regenerated only those two
package entries and their dependency references. Frozen installation with
scripts disabled passed. The original `pnpm audit --audit-level high`
threshold is retained; audit now exits 0 with 0 high/critical and 4 moderate
findings in metadata. No advisory suppression was added.

Node 22.23.2 full Web tests passed 1201/1201 and inert MV3 tests 6/6;
lint/typecheck and both production builds passed. An initial run under the
developer default Node 26 failed 20 existing localStorage-related tests;
switching to the installed CI-family Node 22 resolved them without changing
assertions. The existing 650.19 kB Web bundle warning remains. New-commit
exact-head CI is required before normal merge; Runtime/host qualification
is still incomplete. This patch stays in the current version.

Sections below are historical snapshots.

## 2026-09-30 rc30 encoding and enrollment failure paths

Current work stays on the rc30 Draft #122 candidate, based on main
`0347920d6725c32d6b8d559905a046653ce05728`. Its prior merge head
`8d11561e6887c4f1a2df77714e2a03afb7b1aa48` resolved the rc28/rc29
conflicts and completed 26 terminal checks (24 success, two prescribed skips).
It is still Draft with no independent reviews. The original dirty R12
checkout remains untouched; no subagent or target-host operation was started.

This follow-up adds a bounded data-only enrollment encoder for later
installer use and real fixture replacements of the leaf and parent during
reading, plus uncertain-close cleanup coverage. Local Runtime/provider/
release tests passed 163 cases; Ruff and an in-process Black formatting
check passed; Linux-target mypy checked 317 source files successfully. The
Black CLI could not start its multiprocessing listener in
the sandbox; the single-process library check was used instead. New-head CI
remains pending. Main-agent self-review checked canonical/bounded inputs,
descriptor and entry replacement, authority validation before lower resource
opening, cleanup failure propagation and the absence of new API/process paths.
No unresolved finding was identified in this scope; this is not an independent
review. The current AGENTS.md Review Protocol makes review quality evidence,
not an additional mechanical merge gate. GOVERNANCE and the release plan are
reconciled to that instruction; the earlier reviewer-authorization blocker was
based on the superseded document wording. No subagent was started.
This does not implement the installer publication transaction,
production `_main`, positive legacy Codex Remote state, client qualification
or the real host/CLI/recovery gates. No claim of a usable RC is made.

Sections below are historical snapshots.

## 2026-09-30 R12 vendor enrollment candidate refresh

Live `origin/main` is `0347920d6725c32d6b8d559905a046653ce05728`,
the merge of the single-release-focus plan PR #124. Its six Backend,
Frontend, E2E, Deployment, Security and Release Candidate post-main
workflows completed successfully. Draft #122's prior head
`26c8785f89560e979d7439d8e5f19b3cba7569ca` had 26 terminal
exact-head checks (24 success, two prescribed skips), but no independent
Architecture/Security/Test reviews and no merge. It became conflicting after
rc29 and the plan landed. This branch is resolving that conflict against
main, retaining the rc29 application work and targeting the next source
version rc30. New exact-head tests, CI and independent review remain pending.
Draft #117 stays separate for a later Files/Changes version.

The original `codex/r12-runtime-production` checkout remains at its old
HEAD with uncommitted C3-b provider/test/docs and build files; it was read
only and not used as an implementation source. The later main branch already
contains an authority-deferred resource/provider foundation. Production
`_main`, an installer enrollment writer, a positive legacy Codex Remote
state source, real host/client/CLI/recovery and production remain unfinished.

Sections below are historical snapshots.

## 2026-09-29 逐版本计划基线

本次 `git fetch origin --prune` 退出 0；`origin/main` 是
`3a23f350582287de6b00499b8d4daa5d69c52011`，当前计划分支从该 SHA
起步。该 SHA 是 PR #123 的 merge，Web 源码版本为 `0.3.0-rc.29`。
对该 exact SHA 的 Backend、
Frontend、E2E、Deployment、Security、Release Candidate 六类
post-main workflow 查询均 completed/success。Open PR #122 与 #117
仍为安全关键 Draft，历史 #42 亦未合并。原
`codex/r12-runtime-production` checkout 的未提交 R12 WIP 保持原样；
本次只在干净的独立计划分支修改项目文档，未运行产品测试。

Owner 要求按版本收口；[逐版本计划](RELEASE_ITERATION_PLAN.md)将当前
唯一产品目标定为首个可用单机 RC。上述代码/CI 证据不代表 R12 真实
host/client/CLI/recovery 已验收，也不代表软件候选、目标资格化或生产
发行已完成。以下原 rc29 候选段落保留为历史快照。

## 2026-09-29 WS14 Workspace label command candidate

Live `origin/main` is
`458e7a5c9a87d50ebd9a4cd1040e7a51b148929a`, rc27/PR #121's
normal merge; six Backend, Frontend, E2E, Deployment, Security and Release
Candidate post-main workflows are completed/success on it. Draft #122
head `26c8785f89560e979d7439d8e5f19b3cba7569ca` has 26 terminal
exact-head checks (24 success, two prescribed skips) but remains unmerged
pending independent security-critical review. Draft #117 is separately
unmerged for the same review gate. The original dirty R12 checkout is
untouched.

The clean managed `codex/workbench-command-labels` branch starts from
that main commit. It adds query-only shared-catalog Workspace label choices
to the existing command center only on an exact `aws_` route. The Web hook
validates current-session Workspace metadata and label observations, uses
the existing CAS API, waits for exact ACK/readback and locally refreshes
the visible label panel; no Runtime or arbitrary-command path is added.
Targeted command/label panel tests passed, including hidden pending-write
GET recovery without PUT replay; the Node 22 full Web suite passed
1201/1201. Release-version Python tests passed 93, inert MV3
tests/build passed, and Web format/lint/typecheck/build passed. The isolated
desktop/mobile Chromium matrix passed 114 tests with 28 prescribed skips;
the new flow used the real Project/Workspace label API and a synthetic
formal Workspace metadata row, then confirmed immediate panel readback
and deletion cleanup. Command-center screenshots were inspected at both
viewports without visible overlap or horizontal overflow. The Web JS bundle
was 650.19 kB/184.18 kB gzip; its >500 kB warning remains. PR and
exact-head CI remain pending.
This does not close broader command contributions, cross-host sync, R12
software or host/Secret/production qualification.

Sections below are historical snapshots.

## 2026-09-29 WS14 visible-client label refresh candidate

PR #120 final head `816920a3c301569b8cd64ef99e7532537804d111`
completed 26 exact-head checks: 24 success and two prescribed historical
skips. Its normal merge `88d2db79dd3cf58cfe0093ee90963f1ecfd45d35`
has parents `cab33679ec91bc2e46384f24e9a8cd3e4e985fa9` and that
head. GitHub PR API reports MERGED, `origin/main` and the remote main ref
match the merge SHA, and Backend, Frontend, E2E, Deployment, Security and
Release Candidate post-main workflows all completed successfully on it.
rc26 Workspace label assignment is software-delivered. The original dirty
R12 checkout remains untouched. Draft #117 is still unmerged pending its
independent security-critical review.

This clean managed worktree began `codex/workbench-label-live-refresh` from
that exact main commit. rc27 adds bounded visible/idle periodic GET for
Project and Workspace labels; no API, Runtime or Secret authority changes.
Local focused convergence tests passed 12 cases. The Node 22 full Web suite
passed 1196/1196, Web format/lint/typecheck and production build passed,
release-version Python tests passed 93, and inert MV3 tests/build passed.
The isolated desktop/mobile Chromium matrix passed 112 tests with 28
prescribed skips; current Workspace label screenshots were inspected at both
viewports without overlap or horizontal overflow. The Web JS bundle was
643.55 kB/182.53 kB gzip and retains its >500 kB warning. Exact-head CI,
PR and merge are pending. Cross-host synchronization and full WS14 parity
remain open.

Sections below are historical snapshots.

## 2026-09-29 WS14 Workspace label candidate

Live Git/GitHub preflight: `origin/main` is
`cab33679ec91bc2e46384f24e9a8cd3e4e985fa9`, the normal merge of #119;
its six Backend, Frontend, E2E, Deployment, Security and Release Candidate
post-main workflows all completed successfully. PR #118 is now MERGED
indirectly with recorded merge commit
`36aa7294c4d9c8eaa3283281022e61cf8bbc4f69`; its earlier OPEN
metadata mismatch is resolved. Draft PR #117 remains OPEN, unmerged, and
awaits the required independent security-critical review. The original
checkout's dirty R12 WIP remains untouched.

The `codex/workbench-workspace-labels` branch starts at that exact main SHA.
The rc26 candidate adds an additive Workspace assignment migration and
Control Plane CAS service/API, reuse of the shared catalog, a Workspace-page
picker, and confirmation of both affected Project and Workspace counts for
catalog deletion. Labels remain metadata, not Runtime authority. Local
Python label/API/version matrix passed 108 tests, Ruff passed, and
Linux-target mypy checked 315 files. Node 22 full Web suite passed
1194/1194; format, typecheck and build passed. The final isolated
desktop/mobile Chromium run passed 112 tests with 28 prescribed skips,
including actual Project→Workspace assign/edit/delete and repaired
synthetic Workspace API fixtures. Final Workspace label screenshots were
inspected at both viewports without visible overflow or overlap. Bundle
size was 643.14 kB/182.40 kB gzip; the >500 kB warning remains. The final
Hook dependency fix passed Web lint, typecheck, format, focused 3-case
Workspace label tests and a production rebuild. PR #120 was created at
first head `086a4b7cf3fa9a3708704e225a7d09ff0d33f966`. Its
`repository-boundaries` check failed because the reviewed API route count
was still 50 after adding two routes. The boundary script now explicitly
reviews the Workspace GET/PUT route pair and passes locally (exit 0);
the follow-up exact-head CI is pending. Merge and host qualification remain
separate. Cross-host sync and full WS14 parity are still open.

At second head `8359a1222a64d0124a15c55b6d8c3a2b8260bb7d`, the
route gate, Frontend, E2E, native, packaging, installer and release checks
passed. Python 3.11 quality failed four pre-existing migration tests whose
`head` expectations still named `0011_navigation_labels`; its other 4311
tests passed with 80 skips. The four assertions now target `0012`, and a
Workspace schema parity/data-preserving downgrade test was added. The
complete local migration file passes 44/44; the next exact-head CI is
pending. The 3.12/3.13 jobs were still running at this read-back.

Sections below are historical snapshots.

## 2026-09-29 WS14 Project label Web candidate

PR #118 final head `b7a529dfe92fabd0b83486ee6082296c64713fc9`
completed 26 terminal checks (24 success, two prescribed historical skips).
GitHub generated double-parent merge commit
`36aa7294c4d9c8eaa3283281022e61cf8bbc4f69` with parents
`3e0069381a4d8f867e333191f298b4847256d751` and that head; Git and
GitHub REST refs both report `main` at that commit. However the PR API still
reports #118 OPEN/`merged=false`, its base SHA remains the older parent,
and no post-main workflows are listed for `36aa729…`. The first `gh pr
merge` returned a GraphQL error after the ref changed; a subsequent read
initially saw OPEN, and a retry returned not mergeable. This is an external
metadata/event inconsistency, not proof of full PR delivery. The head's
CI and main Git ancestry are verified separately; do not close or force
the PR to hide the discrepancy.

Draft PR #117 remains unmerged despite 26 terminal exact-head checks
(24 success, two prescribed skips); required independent A3 security-critical
Architecture/Security/Test review and the separate content path remain open.
The explicit authorization question for one read-only reviewer is pending.

This managed worktree began `codex/workbench-project-labels-ui` cleanly from
actual main `36aa729…`. Its rc25 candidate consumes the rc24 label API on
the authenticated Project page: server-confirmed create/assign/edit,
delete-impact preview with transactional count recheck, conflict/uncertain
GET readback without mutation replay, and session/visibility fencing. The
related Python matrix passed 168 cases, full Node 22 Web suite passed 1191,
Linux-target mypy checked 315 source files, Web/MV3 format/lint/build and
version checks passed. The first desktop/mobile browser matrix completed
110 passes and 28 prescribed skips with inspected label-manager screenshots;
the final run after mobile long-name layout and stale-edit guard also
completed 110 passes and 28 prescribed skips. Its desktop/mobile screenshots
were inspected without visible overlap or horizontal overflow. The final
Web bundle is 636.01 kB/180.84 kB gzip after distinguishing definite
validation failures from uncertain ACKs in the active modal. The final
desktop/mobile browser run completed 112 passes and 28 prescribed skips,
including the new 422 error-state case. Desktop/mobile error screenshots
were inspected: the fixed message remains visible inside the modal without
server prose or horizontal overflow. Exact-head CI,
PR and merge remain pending. Workspace assignments and cross-host sync are
not delivered; R12 host/Secret/production gates remain separate. Original
checkout WIP remains untouched.

Sections below are historical snapshots.

## Historical 2026-09-29 WS14 navigation label backend/API candidate

PR #116 final head `57e819cf8d2be8ea5a3296f0211bc49b734f7914`
completed 26 terminal checks (24 success, two prescribed historical skips).
Frontend quality's first attempt timed out in an unchanged rc7 WAW browser
test; the same-SHA failed-job rerun succeeded, while the first failure and
unproven cause remain recorded. Normal merge
`3e0069381a4d8f867e333191f298b4847256d751` has parents
`885c623cf1114d23c5fdc13503f4a2a598985c5b` and that head. Backend,
Frontend, E2E, Deployment, Security and Release Candidate post-main
workflows all completed successfully on the exact merge SHA. rc23 fixed
command-center navigation is delivered as software/browser evidence.

Draft PR #117 starts at that merge and adds an A3 Runtime-internal staged
patch reader. Its exact head `8ef72862514c27b01f5f52a532e0ac4e16f20775`
completed 26 terminal checks (24 success, two prescribed skips) but remains
Draft and unmerged: independent security-critical Architecture/Security/Test
review and the separate content selector/encrypted route are still missing.
The Owner has been asked for explicit authorization for one read-only review
subagent; no agent has been started without that answer.

This separate clean worktree began `codex/workbench-project-labels` from
`3e0069381a4d8f867e333191f298b4847256d751`. Its rc24 candidate adds
an immutable-ID per-admin label catalog, ordered formal Project assignment
table, SQLite migration, revision/CAS service, authenticated no-store API,
Audit and fixed error taxonomy. The related Python matrix completed 164
passes across new labels/API, full migrations, old favorites, database
security and release-candidate checks; later additional API rejection
assertions passed 3/3. Linux-target mypy checked 315 source files. Web
format/lint/build and four focused AppShell tests passed; the final Web JS
bundle is 617.49 kB/176.47 kB gzip, in line with rc23. Inert MV3 version
tests and build passed, with packaged manifest `0.3.0.24`. The full local
desktop/mobile Chromium E2E completed 108 passes and 28 prescribed skips
after applying migration `0011`. Documentation links (546) and the updated
fixed-route source-boundary check passed. Exact-head CI, PR and merge remain
pending. It does not
grant Runtime/file/Agent authority. The Web picker/manager, Workspace label
assignments and cross-host sync are not delivered. Original checkout R12 WIP
remains untouched; R12 host/Secret/production gates remain separate.

## Historical 2026-09-29 WS14 command center candidate

PR #115 final head `bb077fd8a4da6738ed4bc492c6c57de98597e5a8`
completed 26 terminal checks (24 success, two prescribed historical skips).
Normal merge `885c623cf1114d23c5fdc13503f4a2a598985c5b` has parents
`a696d900c46dc348fc3b02cab2ae28d1c3edb33d` and that head. Backend,
Frontend, E2E, Deployment, Security and Release Candidate post-main workflows
all completed successfully on that exact merge SHA. This is A3 staged index
eligibility metadata only; it exposes no patch content or Runtime action.

The managed worktree was clean when `codex/workbench-command-center` started
from that merge. Its rc23 candidate adds an authenticated desktop/mobile
command center with fixed page and formal Project navigation, current-session
Project list read, keyboard search/selection, bounded results and failure
feedback. It invokes no Runtime, file, Agent, plugin or arbitrary command.
The Node 22 full Web suite passed 1181/1181 before one final abort test was
added; the final focused AppShell/command-center set passed 11/11. Local
desktop/mobile Chromium E2E completed 108 passes and 28 prescribed skips
after updating a menu locator whose accessible name changes on open. The
first browser run failed from a stale Python editable-install path; its
environment was corrected to use this worktree. Desktop/mobile command
center screenshots were inspected and no document overflow was observed.
Final Web format/lint/typecheck/build, 87 Python release-candidate tests,
two inert MV3 version tests and 540 documentation links passed. The final
Web JS bundle is 617.49 kB/176.47 kB gzip versus rc22
611.77/174.80 kB. The final read-cancellation change followed the full
browser run, so exact-head CI/browser confirmation remains pending. PR and
merge are pending. Original checkout WIP is untouched. Named
labels, wider command actions, A3 content, R12 composition and real-host/
Secret/production qualification remain open.

## Historical 2026-09-29 A3 staged selection policy candidate

PR #114 merged as `a696d900c46dc348fc3b02cab2ae28d1c3edb33d`;
Backend, Frontend, E2E, Deployment, Security and Release Candidate
post-main workflows completed successfully on that merge SHA. The original
checkout WIP remains untouched. This managed worktree starts its rc23 branch
from that merge.

The rc23 candidate adds a Runtime-only staged Git selection check with
case-folded sensitive-path denial, exact porcelain-v2 index OID/mode checks,
and fixed refusals for unsupported kinds or missing selections. It returns
metadata only. Local focused Git tests passed 36/36; Ruff and one-module
mypy passed. It does not execute Git, read patch bytes, expose a Runtime/API
action or enable Web content. Object-store provenance, stable extraction,
selector/channel/UI, R12 production composition and host/Secret/production
qualification remain open. Exact-head CI, PR and merge are pending.

## 2026-09-29 WS14 Project favorites UI candidate

PR #113 repaired head `5ab766236efa2395844f352b8791cab99b069b1a`
completed 26 terminal checks (24 success, two prescribed historical skips).
Normal merge `8fb017f3e294c4a303547da729b007e9605ed9a0` has parents
`01a0ecd5eb21f74fe8605913bffd0c98bf322165` and that head. Five
post-main workflows completed successfully initially; Backend native failed once in
`test_incomplete_vendor_dcs_fails_closed_before_pane_success` when tmux
briefly reported `pane_dead=1` without its exit status. The same-SHA failed
native job rerun completed successfully, so all six workflows now have
successful current results; the first failure remains recorded. The rc22 branch retains the same
five-second budget and wrong-status assertion while waiting for only that
incomplete transitional value; Linux positive/negative tests were added.

Current `codex/workbench-project-favorites-ui` starts at that exact merge.
Its rc22 candidate consumes the rc21 favorite API on the Projects page,
waits for exact server acknowledgment, refreshes after conflict/uncertain
outcome without PUT replay, and keeps prior-session state fenced. The
browser favorite scenario passed on desktop/mobile in an initial E2E run.
Four other E2E cases initially failed due a legacy fuzzy `Clone` locator
and two isolated rc9 auth fixtures missing the new read-only favorite GET.
After correcting these test inputs, the full isolated desktop/mobile suite
completed 106 passes and 28 prescribed skips. Favorite-state screenshots
were inspected without document overflow. Full Node 22 Web suite passed
1175/1175 serially, including twenty focused contract/hook/page tests.
Ninety-five backend precision/release Python cases, Linux-target mypy over
327 files, Web/MV3 format/lint/typecheck/build, documentation links and
source-boundary checks passed. Exact-head CI/PR/merge are pending.
The Web main JS bundle is 611.77 kB/174.80 kB gzip versus rc21
604.70/173.15 kB. Named labels and command center remain unfinished; the Owner's
broad-permission and R12 host/Secret/production gates remain separate.
Original checkout WIP is untouched. Sections below are historical snapshots.

## Historical 2026-09-29 WS14 Project favorites contract candidate

PR #112 final head `f3f31c0b58d0f3087ee85088eb7508577d98c0ee`
completed 26 terminal checks (24 success, two prescribed historical skips).
Normal merge `01a0ecd5eb21f74fe8605913bffd0c98bf322165` has parents
`2d64ccde14877118f13f9c843d0c0aae0808dce0` and that head. Backend,
Frontend, E2E, Deployment, Security and Release Candidate post-main workflows
all completed successfully. rc20 delivered in-memory search over loaded
Projects, not favorites, labels or a command center.

Current `codex/workbench-project-favorites` starts at that exact merge. Its
rc21 candidate implements the additive per-admin favorite table, revision/CAS
service, strict response/request schemas and authenticated no-store GET/PUT
routes under the [favorites contract](../WORKBENCH_PROJECT_FAVORITES.md).
It has no Runtime action or browser favorite control. Local
service/API/Project/migration/release regression passed 150 cases; Linux-target
mypy covered 327 source files. Web/MV3 format/lint/typecheck/build and six
targeted version tests passed; the Web bundle remains 604.70 kB/173.15 kB
gzip. Isolated desktop/mobile Chromium E2E completed 104 passes and 28
prescribed skips after applying migration 0010; no favorite UI case is
claimed. PR #113 initial head `4ff51a7e3969afffa11d276c0048c72b19129fd5`
failed Python 3.11/3.12/3.13 quality at mypy: a raw SQL `scalar_one()`
in the migration test lacked an inferred type. The repair uses a typed ORM
admin-ID query without weakening the migration assertions. Locally the
CI-scope Linux-target mypy passed 309 files and the focused migration/
favorites matrix passed 53 cases. New exact-head CI and merge are pending.
The Owner's
broad shell/file/plugin/Hub choice and R12 real-host/Secret/production gates
remain separate. Original checkout WIP is untouched. Sections below are
historical snapshots.

## Historical 2026-09-29 S02/WS14 Project search candidate

PR #111 final head `7e2123c59ec8b4e0c8fad55be75ca2b98114eb6f`
completed 26 terminal checks (24 success, two prescribed historical skips).
Normal merge `2d64ccde14877118f13f9c843d0c0aae0808dce0` has parents
`6cd045dd8831283e2c0d0333a39461671b04bf76` and that head. Backend,
Frontend, E2E, Deployment, Security and Release Candidate post-main workflows
all completed successfully. Linux Python 3.11 quality reported 4248 passed,
78 skipped; the Linux-only fd-cwd tests were admitted in that platform job.
rc19 remains an uncomposed internal process primitive, not a patch action.

Current `codex/workbench-project-search` starts at that exact merge. Its rc20
candidate adds local ranked search over already-loaded Project names, visible
slugs and printable Git branches, with an explicit no-match state and clear.
It sends no query to Runtime or a new API. Full Node 22 Web unit suite passed
1159/1159 serially; four pure matcher and four page tests are included.
Seventy-eight Python release-candidate tests, Web/MV3
format/lint/typecheck/build, docs links and source-boundary checks also
passed. The Web bundle is 604.70 kB/173.15 kB gzip versus rc19
601.72/172.29 kB. Isolated desktop/mobile Chromium E2E completed 104 passes
and 28 prescribed skips. Both page-top search screenshots were inspected;
neither showed overlap or document overflow. Exact-head CI, PR and merge are
pending. WS14 favorites,
synced labels and command center remain unfinished.
The Owner's broad permission choice and R12 real-host/Secret/production
gates remain separate. Original checkout WIP is untouched. Sections below
are historical snapshots.

## Historical 2026-09-29 S02/A3 Git child cwd candidate

PR #110 final head `3f77e592496575b9bd0104e0fc1a06fd2c6df46c`
completed 26 terminal checks (24 success, two prescribed historical skips).
Normal merge `6cd045dd8831283e2c0d0333a39461671b04bf76` has parents
`1e3f463c5aafcc9ffdd266a94cfe35bfdca46c0a` and that head. Backend,
Frontend, E2E, Deployment, Security and Release Candidate post-main workflows
all completed successfully. rc18 delivered in-memory Project work tabs;
multiple conversations, split panes and cross-device tabs remain unfinished.

Current `codex/workbench-git-fd-cwd-v2` starts at that exact merge. Its rc19
candidate adds a Linux-only descriptor-bound cwd seam to the internal
`ControlledProcessRunner`; no Git action or content route calls it yet.
Local ordinary runner and non-Linux refusal tests passed. One combined local
test run hit the existing 50ms child startup race. After extending only the
observation timeout to 0.5s while
retaining exact PID cleanup, the combined process/Git/content-root/release
matrix passed 166 cases with four Linux-only skips after the rc19 version
update and cancellation case. Scoped Ruff/Black, Linux-target mypy over
323 files and Web/MV3 format/lint/typecheck/build plus six targeted version/tab
tests passed. The Web bundle remains 601.72 kB/172.29 kB gzip. Isolated
desktop/mobile Chromium E2E completed 102 passes and 28 prescribed skips,
including the visible rc19 version. Linux positive tests, exact-head CI,
PR and merge are pending. The A3 content
action still needs complete object-store provenance, fixed Git argv, selection
and encryption.
R12 real-host/Secret/production evidence and the Owner's broad permission
choice remain separate. Original checkout WIP is untouched. Sections below
are historical snapshots.

## Historical 2026-09-29 S02 Project work tabs candidate

PR #109 final head `2e8ee2794b32815f84282d2e4fcfef74ee0e143a`
completed 26 terminal checks (24 success, two prescribed historical skips).
Normal merge `1e3f463c5aafcc9ffdd266a94cfe35bfdca46c0a` has parents
`692f58a5823c4a8fbb438e61f6575fc88150753f` and that head. Backend,
Frontend, E2E, Deployment, Security and Release Candidate post-main workflows
all completed successfully. rc17 delivered only internal Git content-root
descriptor custody; no patch action or content transport was added.

Current `codex/workbench-project-tabs` starts at that exact merge. Its rc18
candidate adds session-scoped, in-memory Project/Changed Paths/Workspace
navigation tabs, bounded to twelve, adapted from the pinned upstream pane
model. Close is navigation only; it calls no Runtime lifecycle action.
Full Node 22 Web suite passed 1154/1154 serially. Focused model/AppShell
tests passed (seven cases), MV3 version tests passed (two), Python release
matrix 72 passed, and Web/MV3 format/lint/typecheck/build passed. Isolated
desktop/mobile Chromium E2E completed 102 passes and 28
prescribed skips, including active-tab 44px targets and existing Workspace
routes; screenshots were inspected with no horizontal document overflow.
The Web main JS bundle is 601.72 kB/172.29 kB gzip versus rc17
598.88/171.21 kB. Linux exact-head CI, PR and merge are pending. WS02 remains partial because
multiple conversations, split panes and cross-device state are absent.
The broad shell/file/plugin/Hub permission choice and R12 real-host/Secret/
production gates remain separate. Original checkout WIP is untouched.
Sections below are historical snapshots.

## Historical 2026-09-29 S02/A3 Git content-root candidate

PR #108 final head `d824c8c4217c59196f87d5c1d0f49652eb9db200`
completed 26 terminal checks (24 success, two prescribed historical skips).
Normal merge `692f58a5823c4a8fbb438e61f6575fc88150753f` has parents
`87c0913f86324588608b191a8318115b36a59fbc` and that head. Backend,
Frontend, E2E, Deployment, Security and Release Candidate post-main workflows
all completed successfully. This merge delivered only the A3 patch contract;
it introduced no content action.

Current `codex/workbench-git-content-root` starts at that exact merge. Its
rc17 candidate adds an internal descriptor-held Project/Git provenance class
with no Git process, Runtime action, API route, patch bytes or browser control.
It currently holds/rechecks the Project and Git root plus objects/info/pack,
index/config/HEAD; replaced or unsafe nodes and alternate object stores fail.
Eleven focused content-root tests and the 165-case Git/release matrix passed;
Linux-target mypy covered 323 source files. Scoped Ruff/Black and Web/MV3
format/lint/typecheck/build plus four targeted version tests passed. The Web
bundle is 598.88 kB/171.21 kB gzip. Isolated desktop/mobile Chromium E2E
completed 100 passes and 28 prescribed skips. Linux exact-head CI, PR and
merge are pending.
The future reader still needs complete object-store provenance and a proven
child cwd, staged patch extraction, selectors and encrypted content transport.
R12 real-host/Secret/production evidence remains separate; the Owner's broad
shell/file/plugin/Hub permission choice remains unanswered. Original checkout
WIP is untouched. Sections below are historical snapshots.

## Historical 2026-09-29 S02/A3 patch content contract candidate

PR #107 final head `5c4cb801f18c231e95497f8b603df3d5c36674ea`
completed 26 terminal checks (24 success, two prescribed historical skips).
Normal merge `87c0913f86324588608b191a8318115b36a59fbc` has parents
`c285872546f81c173c3e40e1711e8506c164cebc` and that head. Backend,
Frontend, E2E, Deployment, Security and Release Candidate post-main workflows
all completed successfully on the merge SHA. rc16 delivered the authenticated
Changed Paths metadata page, not patch text or file preview. Local rc16 Web
1149/1149, browser 100 pass/28 prescribed skips, Linux-target mypy 321 files,
and desktop/mobile screenshots are recorded in the historical section below.

Current `codex/workbench-patch-contract` starts at that exact merge. It is
drafting [the A3 patch content contract](../WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md):
Runtime-only bounded extraction first, then a scoped selection ID and a
separately admitted encrypted content channel. This document is a candidate,
not an implemented Runtime action or API. The existing metadata API and page
remain read-only. R12 real host/Secret/production evidence and the Owner's
broad shell/file/plugin/Hub permission choice remain separate and unresolved.
The original checkout WIP remains untouched. The sections below are
historical point-in-time snapshots superseded by this live read-back.

## Historical 2026-09-29 S02 Changed Paths page candidate

PR #106 final head `e37383168883990a4fb031ecdd762267757ecb74`
completed 26 terminal checks (24 success, two prescribed historical skips).
Normal merge `c285872546f81c173c3e40e1711e8506c164cebc` has parents
`7ffc1734b0ce5a4f6fdc5575eaeac6804f2aca5c` and that head. Backend,
Frontend, E2E, Deployment, Security and Release Candidate post-main workflows
all completed successfully. This delivered the rc15 authenticated Git path
metadata API, not patch content or a page.

Current `codex/workbench-changes-tree` starts at that exact merge. It adds
a Project-linked read-only Changed Paths page that consumes the rc15 API,
uses the migrated directory order without fabricated line totals, escapes
control/invisible path characters, and separates loading, empty, non-Git,
stale, failed, pagination and refresh states. Source versions align at rc16.
Local evidence: full Web suite 1149 pass with file parallelism disabled on
supported Node 22.23.2; six MV3 tests passed; Python release/Project/Git
matrix 97 passed. Isolated desktop/mobile browser E2E completed 100 pass,
28 prescribed skips, including this page and no horizontal overflow.
Desktop and mobile screenshot inspection found the page readable with no
clipping after correcting banner spacing and sidebar footer separation.
The rc16 Web main JS bundle is 598.88 kB/171.22 kB gzip versus rc15
587.01/167.85 kB; the >500 kB warning predates rc16. Linux exact-head CI,
PR and merge are pending. Patch bodies, file preview, real host and R12
production evidence remain `NOT RUN` or unfinished as separately recorded.

The original checkout WIP remains untouched. The Owner's full 70-ID parity
goal and unresolved shell/file/plugin/Hub permission choice remain. Sections
below are historical point-in-time snapshots superseded by this live state.

## Historical 2026-09-28 S02 A3 Git Changes metadata candidate

PR #105 final head `d33dcf1548b39006d64d292277929d4d63672f33`
completed 26 terminal checks (24 success, two prescribed historical skips).
Normal merge `7ffc1734b0ce5a4f6fdc5575eaeac6804f2aca5c` has parents
`e6a5bf36636c5baf1225368c0acea1d89a73762e` and that final head.
Backend, Frontend, E2E, Deployment, Security and Release Candidate post-main
workflows all completed successfully. Runtime's installed mode remains
disabled; explicit filesystem-v2 still fails until `_main` composition.

Current `codex/workbench-git-changes` starts at that exact merge. It adds
only Project-scoped Git path/status metadata through a fixed Runtime action,
strict RPC and authenticated `GET /api/v1/projects/{id}/git/changes`.
No request path, argv, file body, patch, generic shell or direct API
filesystem read is introduced. Cursor pages reject a changed snapshot;
repository data and Runtime frames are bounded. Local parser, real Git,
RPC and API focused tests pass; 164 Git/Project API/release Python cases,
four Web/MV3 version tests, Web/MV3 builds and isolated browser E2E
(98 pass, 28 prescribed skips across desktop/mobile) completed. Python,
npm and inert MV3 source versions are aligned at rc15. Full Linux exact-head
CI, PR and merge are pending. The user-visible Changes page and content-specific A3 admission
remain unfinished. [A3 contract](../WORKBENCH_A3_GIT_CHANGES.md) gives the
scope and failure behavior.

The original checkout WIP remains untouched. The Owner's full 70-ID parity
goal and unresolved shell/file/plugin/Hub permission semantics remain.
Sections below are historical point-in-time snapshots superseded by this
live branch/CI revalidation.

## Historical 2026-09-28 R12 Runtime fixed deployment profile candidate

PR #104 final head `d147b35aae27dec510b85fa1e57fe4ae3c22dfeb`
completed 26 terminal checks (24 success, two prescribed historical skips),
including 107 Linux native normal and 58 sanitizer cases. Normal merge
`e6a5bf36636c5baf1225368c0acea1d89a73762e` has parents
`72b87c8333896eb6403e3a7e02516e4dcdf910c3` and that head. Backend,
Frontend, E2E, Deployment, Security and Release Candidate post-main
workflows all completed successfully. This delivers a current WAW state
snapshot and repairs a native test wait race, not production `_main`.

Current `codex/r12-runtime-deployment-profile` starts at that exact merge.
It adds a root-owned, Runtime-group-readable fixed profile under
`/var/lib/agentbox-waw`, installed with canonical `disabled` bytes; the
Runtime loader verifies its parent/leaf identity and rejects drift. An
explicit `filesystem-v2` value currently fails `_main` before legacy server
construction, rather than silently falling back. This is a safe intermediate
software candidate, not WAW activation. Local tests: 121 installer/profile
cases passed with one macOS `systemd-analyze` skip under an x86_64 fixture;
16 focused Runtime profile/entrypoint cases passed. Eight older Runtime RPC
socket cases failed on macOS because `server._peer_allowed` requires Linux
`SO_PEERCRED`; no peer assertion was changed. Full Linux-target mypy passed
315 source files. Linux exact-head CI and PR/merge remain pending. Real host,
key, vendor enrollment, client trust and production are `NOT RUN`.

The original checkout WIP and all full-parity capability IDs remain intact.
The broad shell/file/plugin/Hub permission choice remains unanswered.
Sections below are historical point-in-time snapshots superseded by this
live branch and CI revalidation.

## Historical 2026-09-28 R12-C3-b dynamic conflict snapshot candidate

PR #103 final head `fd3d97d2256895341e83cd8e04419fb74a101e43`
completed 26 terminal checks (24 success, two prescribed historical skips).
Normal merge `72b87c8333896eb6403e3a7e02516e4dcdf910c3` has parents
`f70a3fdfda2439ad91a58aa9c38deb0e9c0f7417` and that head; Backend,
Frontend, E2E, Deployment, Security and Release Candidate post-main workflows
all completed successfully. The API profile and lock are installed as
closed-state software resources, without host activation.

Current `codex/r12-runtime-conflict-probe` starts at that merge. It adds
internal `WAWSupervisorExecutor` read-only snapshots of dynamic formal
Project bindings and every relevant supervisor, inflight operation or
restart quarantine. Ambiguity or map drift yields `UNKNOWN`; no Runtime
request action, API route or shell/file access is added. Local executor suite
completed 41 passed; full Linux-target mypy (313 source files) and format
checks passed. Exact-head CI and PR are pending. The legacy Claude/Codex
live state source, provider binding and production `_main` are still absent;
this snapshot alone does not close R12-C3-b or qualify a host.

Official Codex CLI documentation does not specify a `remote-control status`
subcommand, and the development Mac's `codex-cli 0.153.4` help does not list
one. The target Linux CLI was not inspected. Positive absence of a legacy
Codex Remote daemon is therefore still an unresolved G2/C3-b input, not
evidence that no conflict exists.

PR #104's intermediate head `bc3669ec3ea528390535df2c9b7dc58292c125c2`
ran 106 native cases successfully and one failed while a test's
`tmux wait-for` client timed out after its pane-died hook could already have
signalled. Another test on PR #102 had the same five-second wait failure and
passed on a same-head rerun. The candidate test repair removes that one-shot
hook race and polls the exact retained pane's `pane_dead`, exit status and
signal within the unchanged five-second budget; wrong exit and lost pane fail.
Linux exact-head verification of this repair remains pending. It changes no
native or production execution code.

The original checkout's WIP remains untouched. The Owner's full parity
scope and unresolved broad-permission semantics remain as recorded in the
full capability plan. Sections below are historical point-in-time snapshots
superseded by this live branch/CI revalidation.

## Historical 2026-09-28 R12-D API disabled resource candidate

PR #102 final head `6217dd5c56343db731d718c27e5f6b719fea275e`
completed 26 terminal checks (24 success, two prescribed historical skips).
The Backend native job initially timed out waiting five seconds for an
unchanged tmux signal; its single-job rerun on that head passed. Normal merge
`f70a3fdfda2439ad91a58aa9c38deb0e9c0f7417` has parents
`3d0ba375b5a616f1432789eb430ef1a7de4f3347` and that final head.
Backend, Frontend, E2E, Deployment, Security and Release Candidate post-main
workflows all completed successfully on the merge SHA. Two named WAW socket
units and fixed directories are installed by software, but not enabled on a
real host; G3 remains `NOT RUN`.

Current `codex/r12-api-profile-provision` starts at that exact merge and
adds only the installer-owned disabled API profile and singleton lock
resources. A fixed valid existing `filesystem-v2` profile is preserved,
not created or enabled by this batch. The local x86_64 fixture matrix on
macOS completed 143 passed and one `systemd-analyze` skip across installer
and API profile loader cases; Ruff, Black and
full Linux-target mypy (313 source files) passed. This is a local software
candidate without exact-head CI, PR or merge. No real host, Secret, key,
client or production operation occurred.

The Owner's broad permissions choice for ordinary shell, arbitrary file
preview, plugins and multi-principal Hub remains pending. R12 software
progress does not answer that question or authorize those capabilities.

Sections below preserve earlier point-in-time candidates and are superseded
by this live revalidation for current branch/PR/CI status.

## Historical 2026-09-28 R12-D dormant installer socket candidate

PR #101 final head `476dccb5b4ddc44006c4e159f632f9a9e474116e`
completed 26 terminal checks (24 success, two prescribed historical skips).
Normal merge `3d0ba375b5a616f1432789eb430ef1a7de4f3347` was read back
with parents `e3eb23930f6a34720ccf3ef604619acbc2d6cf4c` and that head.
Backend, Frontend, E2E, Deployment, Security and Release Candidate workflows
on the merge SHA all completed successfully. The loader maps named FD3/4 in
either order and accepts a PID1 root-owned descriptor paired with a correctly
Runtime-owned pathname. No PID1 host socket has been qualified.

Current branch `codex/r12-installer-waw-sockets` starts at that exact merge.
It adds two fixed named socket unit assets and Runtime-only key/vendor/run
directories, but does not enable WAW sockets, create a static key, install
vendor policy/manifest, or change the production `_main` path. Simulated
installer tests on macOS with the platform fixture set to x86_64 completed
105 passed and one `systemd-analyze` skip; the native macOS aarch64 platform
is correctly rejected by the installer. Ruff, Black and Linux-target mypy
pass locally. Exact-head Linux CI, PR and merge are pending. G2/G3/HG-04
remain `NOT RUN` for a real host.

The original checkout's C3-b WIP remains untouched. The Owner's broad
permissions choice for ordinary shell, arbitrary file preview, plugins and
multi-principal Hub remains pending; S01 software work continues independently.

Sections below preserve earlier point-in-time candidates and are superseded
by this live revalidation for current branch/PR/CI status.

## Historical 2026-09-28 R12 named socket admission candidate

PR #100 final head `ad9f31c9dc967c727b8708d9a4d261ffc77e6ca1` completed
26 terminal checks (24 success, two prescribed historical skips). Normal
merge `e3eb23930f6a34720ccf3ef604619acbc2d6cf4c` was read back with
parents `986e8fa87c6d14030677c026342813c6921cc6f9` and that head.
Backend, Frontend, E2E, Deployment, Security and Release Candidate workflows
on the merge SHA all completed successfully. This is an authority-deferred
resource/owner software foundation; `_main` is still not production-wired.

The official systemd socket contract permits multiple socket units to
activate one service but does not guarantee their relative FD order. The
`codex/r12-waw-socket-names` branch is based on the PR #100 merge and changes
only the WAW activation loader, unit tests and associated R12 contracts:
FD3/4 must be the exact two unique fixed names; each name must match its
fixed AF_UNIX path and provenance; the result is normalized into control and
stream. Duplicate/unknown names and name/path drift fail closed. Local macOS
tests currently report seven pass and seven correctly marked Linux-only
skips because Darwin rejects AF_UNIX `SO_ACCEPTCONN`; Linux CI is required.
No systemd unit was installed or started, no real host socket qualified, and
the branch has not yet run exact-head CI. G3/HG-04 remain `NOT RUN`.

## Historical 2026-09-28 R12-C3-b authority-deferred resource candidate

PR #99 for rc14 final head `ad73f7c783e4cd817bc8a1eb9d6dccc732c92b01`
completed 26 terminal checks (24 success, two prescribed historical skips).
Normal merge `986e8fa87c6d14030677c026342813c6921cc6f9` was read back with
parents `8beeb1ea81a2b94e514e9452a2b5ce15ce8cbbd2` and that head.
All six Backend/Frontend/E2E/Deployment/Security/Release Candidate post-main
workflows completed successfully. rc14 remains a source/CI delivery and does
not qualify the Linux host or real CLI.

The original checkout's five C3-b WIP files were copied byte-for-byte to the
managed worktree and verified by SHA-256. On branch
`codex/r12-c3b-resource-factory` at base
`986e8fa87c6d14030677c026342813c6921cc6f9`, new
`waw_runtime_resources.py` opens exact-six executable handles and nine
installed roles only after the filesystem-v2 builder issues its unique
`WAWVerifiedExecutionAuthority`. A distinct owner returned by `take()`
transfers that bundle once to the internal provider. The original checkout
and its `.reasonix/`, `build/`, planning WIP, and provider/test source remain
untouched. The managed branch currently has uncommitted software and this
document, without an open PR or exact-head CI.

Local evidence: 162 relevant auth/provider/resources/application/executor/
bootstrap/key unit tests passed; Linux-target mypy passed 299 source files;
Ruff, Black, docs links and `git diff --check` passed. Tests use fixtures on
macOS and do not establish real descriptor, cgroup, native helper or host
qualification. The [C3-b composition record](../WAW_R12_C3B_PRODUCTION_COMPOSITION.md)
lists missing `_main` wiring, installer-owned socket/key/epoch/enrollment
inputs, late Project registration through the actual application, and Linux
native/sanitizer evidence. No real host, key, CLI login, Secret or production
operation occurred.

## Historical 2026-09-28 S02 recent Attention candidate

PR #98 for the full-capability scope merged normally as
`8beeb1ea81a2b94e514e9452a2b5ce15ce8cbbd2`; Git read-back verified
parents `135eb8cdb22a6b88a825eb214bde86f3f11e8442` and final head
`2ccf17b231274673f4ce103b646c0d512df0a241`. Backend, Frontend, E2E,
Deployment, Security, and Release Candidate post-main workflows all completed
successfully on that merge SHA. The authority decision noted below remains
pending; the merged plan does not activate any conflicting capability.

In the isolated managed worktree, `codex/workbench-attention` now contains
local commit `bce12a2874c6422b507f120b123fb9de5f62394d` for the
`0.3.0rc14` read-only Attention page, plus a normal local merge of the new
main (`6ab29997f12e72420e9669f1ce5fd16833723263`). The page uses the
existing authenticated bounded Jobs API, shows stored `needs_attention`
metadata among the 100 most recent Jobs, and invalidates its observation when
the document is hidden. It does not provide a full historical inbox or execute
recovery actions. Python/npm/MV3 visible values match rc14.

Local checks: 49 focused Web tests, two extension-version tests, 60
release-candidate unit tests, typecheck, format/lint, root Web/MV3 build,
and the isolated browser E2E (98 pass, 28 prescribed skips). The new E2E case
passed at desktop 1280×800 and mobile 390×844, including no horizontal
overflow and no raw Job summary rendering. A same-host Vite 7.3.6 rc13
baseline was 582.17 kB JS/166.49 kB gzip; rc14 was 587.01/167.85 kB.
The >500 kB Vite warning existed in rc13. Local browser work was macOS and
the unit environment used Python 3.14, so Linux/3.11–3.13, target host,
real CLI and production evidence remain separate. This rc14 branch has not
yet been pushed or run through exact-head CI.

## 2026-09-28 full capability scope expansion

Owner explicitly expanded the objective to absorb all existing upstream
capabilities into AgentBox. The [v2 delivery plan](FULL_CAPABILITY_DELIVERY_PLAN.md)
and [70-item inventory](FULL_CAPABILITY_INVENTORY.md) cover pinned main,
production relay, and Hub sources. The identity/content/source rules in the
earlier workbench plan remain; its selective-scope exclusions and 24–42 batch
estimate are superseded. A separate Owner decision is pending for ordinary
shell, arbitrary daemon-readable files, plugins/scripts, and multi-principal
Hub behavior that conflict with existing AgentBox authority boundaries.

PR #97 final head `ffe08c456d0870c1804644cdf662c7c862be2e4d` completed
26 terminal checks (24 success and the two prescribed historical skips).
Normal merge `135eb8cdb22a6b88a825eb214bde86f3f11e8442` was read back in
Git with parents `a696193fec127595b1beafb1ed1cabf2ae58efa9` and that
final head. Backend, Frontend, E2E, Deployment, Security, and Release Candidate
workflows on the merge SHA all completed successfully. This is A0/A1 source
and pure Changes logic delivery, not an available Files/Changes product.

The original checkout is on `codex/r12-runtime-production` with C3-b provider
and test WIP, plus older planning-document WIP, `.reasonix/`, and `build/`.
The isolated worktree is on `codex/full-workbench-parity` based on the merged
main SHA. C3-b's auth owner/native path and cleanup repairs have 41 focused
unit passes and four-file Linux-target mypy success, but the production
`_main` composition, installer inputs, host gates, and review remain open.
No Host/Secret/client/CLI/production operation was performed.

## 2026-09-28 workbench A0/A1 implementation snapshot

Owner approved [AB-WORKBENCH-2026-09-28-v1](WORKBENCH_INTEGRATION_PLAN.md)
for software implementation. The main Goal is active. An isolated managed
worktree at `/Users/wxx110/.codex/worktrees/workbench-integration/agentbox`
is on `codex/workbench-integration` from
`a696193fec127595b1beafb1ed1cabf2ae58efa9`; `main` and `origin/main`
matched that SHA after a successful `git fetch origin --prune`. The original
checkout's `.reasonix/`, `build/`, and two C3-b provider/test files remain
untouched and uncommitted.

Upstream getpaseo/paseo was shallow-cloned to a temporary research checkout at
exact SHA `30178c4f58b67f8472901356e1484022bd835de0`. A0 recorded source
file paths, digests, license and adapted destinations in
`third_party/upstream-sources.json`. Four Changes source/test files have been
adapted to AgentBox-local types, with source notices in their headers. The
project `NOTICE` and the packaged `THIRD_PARTY_NOTICES.md` carry attribution.
Only AgentBox Web modules were added; no Paseo service was installed or started.

The A1 thin slice currently passes 23 targeted Vitest cases across two files,
the Web TypeScript build check, targeted ESLint and Prettier, upstream source
digest/read-back, and the documentation link check; `git diff --check` passes.
The [workbench identity/content ADR](../adr/0009-workbench-identity-and-content-boundary.md)
is accepted for software scope. A3 exact content transport remains unimplemented.
First offline dependency installation failed because the locked `js-yaml`
tarball was absent locally; a subsequent lockfile-preserving Web install
succeeded without running installation scripts. No UI page, backend/Runtime,
target host, real CLI, credential or production validation is claimed by this
slice. PR #97 was opened from first head
`06f956095dd48995d5bfe3d350b5ad6ab9230835` against
`a696193fec127595b1beafb1ed1cabf2ae58efa9`. Its first Python quality
matrix failed in 3.11/3.12/3.13 on five existing unannotated scalar locals in
`database.py`, `test_phase11_approval.py`, and `test_services.py`. The follow-up
adds only five `str` annotations; the SQL and assertions are unchanged. Local
mypy with Linux/3.11 target passes all 295 files; targeted Ruff and Black pass.
New exact-head CI is required. Next: deliver this A1 slice through CI/normal
merge/read-back, then continue A2 and C3-b according to the approved plan.

## R12-C2 C3-a composition closure on review hold

PR #95 final head `dfcefe87a2d53bac6eff73c7a63ea42d9ef52caf` completed all 26
terminal checks: 24 success and the two prescribed rc8 historical skips. It
merged normally as `4f374aef102c820a001517e14c49803da3e0ff73`; exact Git
read-back verified parents `a6fbf775d471d388abac32b9db689f6e2bd8d495` and the
final PR head. All six post-main workflows succeeded (run set for `4f374ae`).

On `codex/r12-runtime-main`, the C3-a composition-closure slice is implemented
and under milestone review hold (2026-09-15 instruction): the owner gains a
one-shot `bind_native_probe_path` that closes the owner↔factory↔process-port
construction loop with constructor-equivalent validation; the factory's vendor
digest check now uses the manifest inventory per-entry `max_bytes` (real
vendor binaries far exceed the old 64KiB default); the fixed-composition
auth-probe pin moved from `WAWCachedPublicAuthProbe` to
`WAWProductionAuthOwner` in both `_compose_verified_v2` and
`RuntimeExecutorServer` (the dev `_configure_waw_auth` path is unchanged); and
the API-side envelope is reconciled through a per-action
`action_timeout_seconds` map with the production composition assigning
`workspace.workspace.start` 9.0s (8.0s server envelope plus 1.0s transport
margin), closing decision `R12-AUTH-PROBE-BUDGET-V1`. Local evidence: 202
related unit tests and 242 integration tests pass, ruff/black/`git diff
--check` clean, mypy identical to baseline. Independent
Security/Architecture/Test review: PASS with no P0/P1 (review follow-ups:
bind publication order swapped; contract and decision documents updated).

C2 is not complete: C3-b (production executor provider and `_main` production
branch: activated sockets, static key, epoch store, provider, application
builder) remains; production profiles additionally require external
enrollment inputs (`vendor_version`, `codex_unauthenticated_output_sha256`,
D/G/H) and fail closed without them. Host/client activation, real CLI login,
key operation and production remain closed.

## R12-B delivered; R12-C1 candidate

PR #90 final head `64d45e7434999f163ab35e0418ae1ea6da00d87c` completed all 26
terminal checks: 24 success and the two prescribed rc8 historical skips.
It merged normally at 2026-09-08T08:00:23Z as
`e126e47172491f382efb2f5daaeac1e22a550ad6`; exact Git read-back verified parents
`6db8d62896bf573ad4e1bc6c253db55003c87275` and the final PR head.
The earlier Web/E2E version expectations and proxy/Cookie fixture dependency
failures were fixed without weakening security assertions or production checks.

All six post-main workflows succeeded: Security `34202185144`, Frontend
`34202185164`, Deployment `34202185013`, Release Candidate `34202185006`,
Backend `34202185189`, E2E `34202185177`. R12-B software is delivered.
Local main and origin/main were fast-forwarded to the observed merge, preserving
all C1 source WIP on `codex/r12-runtime-key`.

C1/rc12 has 72 focused static-key/application/bootstrap passes and final
Architecture/Security/Test PASS. Constructor cleanup errors remain explicit;
production identity and post-bind/close access tests are included. The main agent
passed 54 release checks, 2 extension-version cases and 2 Web-shell version cases.
Full fixed-transport local results remain 95 passed / 9 skipped / 2 existing UDS
PermissionError failures; Linux CI is required. C1 exact-head CI/merge is pending.

C2 native auth-probe implementation has separate native-file ownership. It must
not change old interactive ABI/bridge or claim full C2 completion before the
Python lease/cache/provider path and Linux evidence are complete. Runtime main,
real keys, CLI login, client installation and production admission stay closed.

## R12-B candidate and R12-C1 work in progress

PR #89 delivered the approved plan and initial R12 software contracts. Exact
head `f58a41a9723bbe0c81bbc0e4ea38c3b996ccf636` completed 26 terminal checks
(24 success, two prescribed rc8 skips). Normal merge at 2026-09-08T06:45:45Z is
`6db8d62896bf573ad4e1bc6c253db55003c87275`; Git read-back verified parents
`1ab28e524d018df3d59e6c48f01646bb1021a978` and
`f58a41a9723bbe0c81bbc0e4ea38c3b996ccf636`. Local main and origin/main were
fast-forwarded to this merge; all API/Runtime WIP was preserved on
`codex/r12-api-bootstrap` without reset/stash.

Post-main Backend `34196104692`, Deployment `34196104777`, E2E `34196104741`,
Security `34196104744`, Release Candidate `34196104784` succeeded. Frontend
`34196104716` first failed one unchanged exact-Stop case with a 5000ms timeout
and PROTOCOL_INVALID; attempt 2 on the same SHA succeeded. The same unchanged
two-case file passed a one-worker local rerun. No timeout/assertion was relaxed;
the first failure remains recorded and does not establish a resolved root cause.

R12-B is the rc11 candidate: final local API/profile/application tests passed
82 cases. Architecture/Security/Test reviews passed after repairing parent-entry
replacement, missing-leaf recheck, cleanup-error visibility and a single factory
boundary covering all decorator/router/static registration. Ruff/Black and
Linux-target mypy passed; exact-head CI and software merge are pending.
PR #90 first head `fd7ad036d7aa7a38292e3483558c27c3884c89b9` failed Frontend
only on two stale rc10 shell-version expectations. The follow-up preserves the
exact assertions and updates Web/E2E expected versions to rc11; the two shell
tests and Prettier passed locally. New exact-head CI is required before merge.
Main-agent release validation passed 51 cases and the extension version check
passed 2 via direct Node/Vitest. An initial pnpm
wrapper dependency-repair attempt aborted; no forced cache/module purge followed.

R12-C1 has separate Runtime-only key/authority WIP with 72 targeted passes and
final Architecture/Security PASS after construction cleanup repair; Test
coverage for production identity and post-bind/close reads is being closed;
it is excluded from the API candidate's staged files and eventual PR. C2 needs
a real fixed auth-isolation provider before C3 can connect Runtime main.
No real host/client/key/credential/CLI/reboot or production operation occurred.

## R12 execution snapshot

On 2026-09-08 the Owner explicitly approved PRP-2026-09-08-v1 and instructed
execution. The current branch is `codex/production-readiness-plan`; the three
planning-document changes are retained task-owned WIP. Fetch and Git/GitHub
preflight exited 0: HEAD, main, origin/main and merge-base remain
`1ab28e524d018df3d59e6c48f01646bb1021a978`, with six successful exact-main
workflows and only historical Draft PR #42 open.

One persistent Goal is active. R12-A is in progress: Sol/ultra owns read-only
API contract planning, Sol/high owns read-only Runtime provider planning,
Terra/high owns the current host-checklist update, and the main agent owns
shared plan/state/integration/Git delivery. The approved suggested client scope
is Mac Chrome/Edge terminal and mobile management/exact Stop; neither is newly
qualified. Concrete host/Origin and Mac management/distribution inputs have
been requested while independent software work continues.

The approval-record commit `edbcab6d19470254a51b3265557bb09f26d86a29` is pushed
in PR #89; CI is in progress and no merge is claimed. The host checklist has
been updated to v2/current five-gate semantics, with all field observations
NOT RUN. [R12 API bootstrap](../WAW_R12_API_BOOTSTRAP.md) is the stable software
contract now being implemented by Terra/high. [R12 target record](R12_TARGET_RECORD.md)
records pending external inputs and the separate local Mac read-only observation.

R12-C1 is being implemented by Sol/high under
[the fixed key-port contract](../WAW_R12_RUNTIME_KEY_PORT.md). It binds the key
to the same verified manifest authority before epoch commit and retains exact
ownership/cleanup. Production auth-isolation is a separate C2 prerequisite;
Runtime main stays closed until C1/C2 and the C3 entrypoint are complete.

No real host/client activation, key/credential operation, paid CLI call, reboot,
production deployment or publication has occurred. Source version is still
`0.3.0rc10`; all five product gates remain unqualified. The planning snapshot
below is historical and no longer requires execution confirmation.

## Production readiness planning snapshot

The Owner requested a complete plan after the read-only project assessment.
Live preflight returned exit 0: clean `main`, `origin/main`, HEAD and merge-base
were `1ab28e524d018df3d59e6c48f01646bb1021a978`, the observed merge of PR #88.
All six exact-main workflows are terminal success. Only historical Draft PR #42
is open. This supersedes older branch/baseline snapshots below, not their evidence.

The document-only branch is `codex/production-readiness-plan`.
[PRODUCTION_READINESS_PLAN](PRODUCTION_READINESS_PLAN.md) records the complete
R12 software, artifact, host, client, CLI, recovery and limited-production plan,
plus separately proposed later product work. The requested client preference has
not yet been supplied; Mac Chrome/Edge terminal plus mobile management/Stop is a
recommendation only. Host, Origin, key and external-operation scopes remain to
be concretized. Plan delivery is complete: independent Sol/ultra planning and
Sol/high deployment reviews passed after repairs; all 378 relative documentation
links and whitespace checks passed. Execution confirmation is still pending;
implementation has not begun. These are document-review results, not host evidence.

The current Goal lookup returned null. No execution Goal, code/version change,
host/client installation, credential/key operation, commit/push/PR/merge, tag or
release is performed by this planning task. The source stays `0.3.0rc10` and
production remains NOT ADMITTED. R11 and WEV-1 remain delivered software.

## Workstation evolution task snapshot

Acquired baseline: `main`, `origin/main`, HEAD and merge-base were
`b72f6ea67647d63ce26ae5610094e8aec34f7a78`, with a clean working tree.
`git fetch origin --prune` and GitHub identity/open-PR/CI checks exited 0.
The baseline's six push workflows completed success; only historical Draft
PR #42 was open. This is the starting snapshot, not a prediction of this task's
future commit or merge SHA.

The 2026-09-08 Owner task authorizes research of seven named projects and the
first independent improvement within existing boundaries. Implementation branch:
`codex/workstation-evolution`; Goal and task checklist are recorded in
[WORKSTATION_EVOLUTION](../WORKSTATION_EVOLUTION.md). WEV-1 repairs Runtime
observation validity on browser return. Research/plan commit
`418bc678a3fdf78e9df66060d785c6cf9c01e7b5` is pushed. Source candidate rc10
implementation and independent Architecture/Test/Security review are complete.
PR #87 head `80a6972466a514aa67577bb7812cf4c649a5983c` completed 26 terminal
checks: 24 success and two prescribed rc8 historical skips. It merged normally
at `2026-09-08T03:44:14Z` as `b3e9cd5dbfbdca0c5e0cd652dc0cce7e1e53214e`,
with exact parents `b72f6ea...` and `80a6972...` verified by Git read-back.
All six post-main workflows succeeded; exact run IDs are in the evolution record.
Web CI passed 1109 tests and extension CI passed 6. Local final evidence is
status 18, controller 24 and page 18 unit passes, 48 release-candidate passes,
and Chromium 96 passed / 28 expected matrix skips. The initial parallel Mac
Web run failed with timeouts; all four failed files passed 92/92 with one
worker and unchanged assertions. See the task record for the full distinction.
The bounded software increment is delivered; this snapshot is synchronized
on `codex/wev1-merge-readback` without changing software behavior or version.
It records the verified PR #87 result and does not predict a later documentation
merge SHA or replace live Git/GitHub.

Production is still NOT ADMITTED: API's default WAW mode, Runtime concrete
providers/bootstrap and managed-browser trust installation require separate
closure. R11 software CI does not substitute for those R12 dependencies.

## Historical R11 implementation and delivery record

The following dated checkpoints are retained as history. Their former “current”
or “next” wording does not override the task snapshot above or live Git/GitHub.

- Live revalidation on 2026-09-05: `git fetch origin --prune` exited `0`;
  `main`, `origin/main` and the branch merge-base equal
  `341a69bf855f48f90cbecfb5c6872c3bf8c28360`. The upstream rc6 branch head was
  `9bf5e8d1defa4704b521d6c67a4725740c0f5fd4` before this checkpoint. The exact
  head `029378e...` completed 17/20 checks; all three Backend Python jobs exposed
  the same Linux inode-reuse flaw in the Runtime Project verifier. Repair head
  `bbdd67c...` completed the fresh exact-head 20/20 matrix, including native and
  Python 3.11/3.12/3.13. Later documentation head `801a494...` failed only native
  attach READY status 71; `af4d43e...` passed native, while `2381171...` quality
  failed only because its new Python test needed Black formatting. `9d078b4...`
  plus `4222242...` completed the fresh exact-head 20/20 matrix.
- The active, reviewed execution order is `docs/WAW_R11_EXECUTION_PLAN.md`.
  The rc6-B first-use contract and local evidence are recorded in
  `docs/WAW_R11_RC6_FIRST_USE.md`; this is not a claim that rc6, rc7, rc8, rc9
  or R12 is complete.
- Local commit `9c12ab3fd1f4f369e90f710a8ab6cec1f187edea` implements rc6-B
  deterministic binding replay: eager Runtime `bindings-v1` restoration,
  ordered API replay, closed inventory finalization, Project/binding drift
  fences, and the private installer boundary. Its affected-scope matrix is
  346 passed / 2 Linux-host skips; Black, Ruff, Linux-target mypy and
  `git diff --check` pass. Two independent Sol reviews found two P1/two P2 and
  then no remaining P0/P1/P2 after repair. The final exact head
  `854cf87774f3de22bd3a37bf74576dcfc29177ee` completed 20/20 CI. A fixture typing
  repair (`3341c13`) and faulthandler-only CI diagnostic (`854cf87`) preceded
  that terminal result; two abnormal non-terminal Python 3.12 runner attempts
  are not counted as evidence. The checkpoint is still not rc6-B completion or
  host evidence.
- Commit `ea0ac844c1f2e52fc8cdc51a0ec7d90645094338` hardens the rc6-C browser
  controller before production page composition: fresh redraw only, renderer
  gated cursor, context/trust publication checks, terminal-input uncertainty
  fence and exact control-operation lifecycle. Its controller scope has 28
  dedicated tests, an independent Sol PASS with no P0/P1/P2 and 20/20
  exact-head CI. That committed controller-only checkpoint did not itself create
  a production DOM renderer or wire a terminal into `WorkspacePage`.
- Commit `f4d868e` adds the bounded `DocumentFragment`/`textContent` terminal
  renderer with clear fallback, cancellation and reentrancy fences. Its final
  documentation head `48850bab3a7822d22114dd46b14ba4362f004f32` completed
  20/20 CI. That committed renderer checkpoint still had no production page
  owner, ticket flow or browser control UI.
- PR #80 delivered the rc6 page-composition checkpoint: its final candidate head
  `e1c10bfbf6dce251cafd24ef931b30e26d3001c0` completed 20/20 exact-head checks,
  merged normally as `8480bf81450a175b993d86d4255d462922dac87f`, and completed
  post-main read-back. The checkpoint owns the concrete
  `WorkspacePage` surface, managed-provider availability, lifecycle fencing,
  fresh page-control lease, viewport-only resize, bounded input outcome and
  Project binding drift cleanup. It has 28 Web files/983 tests, 117 API/relay
  tests and 64 E2E tests locally, plus a final independent Sol review with
  P0=0/P1=0. The first post-main native sanitizer run had an isolated tmux
  `wait-for` timeout; rerunning that exact failed job on the same main SHA passed,
  so all six post-main workflows are terminal success. It remains software
  evidence, not R11/R12 product qualification.
- PR #81 delivered rc7-A deterministic composed failure injection: candidate
  `04ef0ae2b94e127cacc496e7876bd41cf203f43d` completed all 20 exact-head checks,
  merged normally as `b0eaef2e4e54cf1aba86e7669733d0adc885c1fb` at
  `2026-09-06T02:26:40Z`, with `8480bf8...` and `04ef0ae...` as exact parents.
  All six post-main workflows completed success. It adds test-only
  closed checkpoints, void gates, integer-nanosecond clocks and controlled
  partial writes; composed admission/relay/restart/shutdown/browser/Stop tests;
  and dynamic canary scans across Audit/Jobs/logs/diagnostics/SQLite sidecars plus
  browser DOM/storage/task owners. Focused Python is 29 passed, related Python
  regression is 341 passed, full Web is 997 passed, Linux-target mypy covers 274
  sources, and independent Sol review reports P0=0/P1=0. rc7 is delivered; R11
  remains in progress for rc8/rc9 and R12 remains unstarted. One
  existing local real-UDS relay test cannot bind `/tmp` under this Mac sandbox;
  Linux CI remains required for that unrelated host capability.
- rc7 release-record PR #82 advances the unified source version to `0.3.0rc7`
  / `0.3.0-rc.7` / `0.3.0.7`; candidate
  `8546adadb08757156c5f2be045be93a30d2915af` completed 20/20 exact-head checks
  and merged normally as `87f5bce964eba231a6a7ade73eaedac7e54646ae` at
  `2026-09-06T03:02:07Z`, with `b0eaef2...` and `8546ada...` as exact parents.
  rc8 now uses that versioned merge as its only predecessor. Its P0 contract
  requires unpacked artifact provenance, isolated wheelhouse imports, synthetic
  WAW path and exact upgrade/rollback; no R12 capability is active.
- rc8 advances the unified source to 0.3.0rc8 / 0.3.0-rc.8 / 0.3.0.8
  and freezes the artifact/operations contract around the immutable rc7
  release-record predecessor.
- Implementation checkpoint c998fb9981553e6fbd6e411f7fe79f57ddc8ebb2 completed
  all 26 exact-head checks. It proved separate exact rc7/rc8 artifacts,
  candidate artifact imports on CPython 3.11/3.12/3.13, the non-skipping 3.11
  artifact API/Runtime/RFC6455/PTY flow, predecessor-to-candidate upgrade then
  receipt-bound rollback, and dynamic declared-surface canary scans. The safe
  receipt reported no secrets and no host qualification.
- Documentation head 710ceef696757a8a1f2a9165f2312672db57bb1e completed a fresh
  26 exact-head checks, then PR #83 merged normally as
  95bf65d6114008b962985f7311941499c961a7b8 at 2026-09-06T11:53:06Z. Its exact
  parents are 87f5bce964eba231a6a7ade73eaedac7e54646ae and
  710ceef696757a8a1f2a9165f2312672db57bb1e.
- All six post-main workflows for merge 95bf65d completed success: Security
  34031506669, Deployment 34031506642, Frontend 34031506663, E2E 34031506656,
  Release Candidate 34031506697, and Backend 34031506660. Local main was
  fast-forwarded to the observed merge with exit 0.
- rc8 is delivered as software evidence. No tag, GitHub Release, credential,
  host activation or R12 qualification occurred. The next software stage is rc9
  full browser-selected bilingual UI and its release-gate compatibility work.

- Earlier paragraphs labeled “current uncommitted” are retained historical
  checkpoints. The branch/CI status in this opening section and the rc6 current
  composition checkpoint supersede them.
- The first rc9 foundation increment is commit
  `184781cca3010e36fb979ad0490566363b0816cc`: typed bilingual catalog domains,
  English/Chinese key parity, known API-code localization and the route/state
  migration manifest. Its exact head completed 20/20 checks on PR #80. It does
  not migrate every page or claim rc9 is complete.

- RC9 delivered software evidence: all route/state bilingual UI migration, typed
  catalog parity, code-only API localization and version-aware release-gate work
  are implemented and verified on `codex/waw-rc9-bilingual-ui`. The
  document locale reads only `navigator.languages[0]` once: primary `zh` maps to
  `zh-CN`, and every other/missing/malformed first preference maps to English.
  Server/API prose is excluded from user-facing localization; technical protocol,
  identifier, enum, error-code and Audit values remain English. A distinct-origin
  Workspace E2E harness is test-only and excluded from the production bundle;
  trace/video/screenshot artifacts remain disabled for sensitive scenarios.
  Version mapping is Python `0.3.0rc9`, npm `0.3.0-rc.9`, MV3 `0.3.0.9`.
  Local commands exited 0: Web unit 44 files / 1088 tests; direct Chromium E2E
  92 passed / 28 designed skips; release-candidate unit 45 tests; browser trust
  extension 3 files / 6 tests plus packaged inert-manifest fence; documentation
  links 256; workflow action pins 48 references across 7 audited sources. The
  E2E runner rebuilds then fail-closes if production `dist` contains a Workspace
  harness marker. The repository browser-source boundary check passes and safe
  text components reject raw-HTML props at compile time. Project and
  Project-detail technical values have shrink/wrap boundaries for the desktop
  and mobile viewport matrix; the Workspace Project selector and terminal input
  can shrink inside their rows at 390px, and long runtime status badges wrap in
  a bounded heading. PR #85 final exact head
  `751d4d010f92e18780bd6d96fdb3c9ea23107464` completed all 26 checks, merged
  normally at `2026-09-06T17:57:57Z` as
  `b07f944ef2c7b590e5a3f1fa50354d6f492d6c31` with parents
  `b191f4bc259cf6c4e0357afa85a9be0c41acb8ef` and
  `751d4d010f92e18780bd6d96fdb3c9ea23107464`. Post-main Security `34050212985`,
  Deployment `34050213004`, Frontend `34050212993`, E2E `34050212986`, Release
  Candidate `34050213006`, and Backend `34050213380` all succeeded. Exact rc9
  release semantics were rc8-predecessor-artifact/rc8-artifact-operations
  `skipped`, while rc8 synthetic/import, current-candidate checks and
  `release-gate` succeeded. R11 software rc6–rc9 is delivered; no tag, GitHub
  Release, production deployment, Provider credential or real host activation
  occurred. R12 remains unstarted and independently host-gated.

- Live rc9 merge read-back at 2026-09-06T18:04:17Z: `git fetch origin --prune`
  exited 0; the current read-back branch, `main`, `origin/main` and the merge
  base equal `b07f944ef2c7b590e5a3f1fa50354d6f492d6c31`. Its exact parents are
  `b191f4bc259cf6c4e0357afa85a9be0c41acb8ef` and
  `751d4d010f92e18780bd6d96fdb3c9ea23107464`.
- Historical rc8 merge read-back at 2026-09-06T12:01:19Z observed
  `95bf65d6114008b962985f7311941499c961a7b8`; it remains RC8 evidence only and
  is not the current live Git baseline.

- R9 PR #78 completed 19/19 exact-head checks, normal merge, exact read-back and
  all six standard post-main workflows. The separate historical Dependency Graph
  limitation is addressed on this R10 branch by the `.txt` release input.
- Owner delegated the remaining software goal/plan/architecture and explicitly
  approved managed Chromium extension + Native Messaging + independent `trustd`,
  followed by R8 rc3 → R9/provider rc4 → R10 rc5 → R11 rc6–rc9. R9 is delivered;
  real host/key/provider activation remains R12.
- R10 `0.3.0rc5` is delivered by PR #79: final exact head `0d9e7c7...` completed
  20/20 checks and merged normally at `2026-09-04T20:37:51Z`. Fetch/read-back
  observed merge `341a69bf...` with exact parents `15a4632f...` and `0d9e7c7...`.
  All six standard post-main workflows and the dynamic Dependency Graph update
  completed SUCCESS. R11/rc6 software composition is now active.

## Historical live baselines

- At current-task start: clean tree; `HEAD/main/origin/main/merge-base` equal
  `dfb5eb796f8745ee10cd2a9cefe0cdd15de057a9`.
- All six exact-main workflows completed SUCCESS. Historical Draft PR #42 is
  the only open PR and is outside current writes. Network preflight exited 0.
- Latest code delivery baseline: clean tree before this documentation snapshot;
  `HEAD/main/origin/main/merge-base` equal
  `3f2e3a2de4b0482629f5f9a296d5db757f989876`. PR #71 completed 19/19 exact-head
  checks before normal merge. Fetch, merge read-back and main fast-forward exited 0.
- Active snapshot branch: `codex/remaining-plan-delivery-record`. This increment
  updates documentation only; it cannot predict its own future merge SHA.
- R0/R1/R10.1/R2 six-workflow post-main runs were separately read as SUCCESS.
  R9.1's six post-main workflows were also read as terminal SUCCESS at
  `2026-09-03T10:35:54Z`, independently of its PR-head checks.
- This snapshot records observed facts and cannot predict its own merge SHA.

## Delivered software stages

| Stage | PR | Exact reviewed head | Observed merge | Exact-head CI |
| --- | --- | --- | --- | --- |
| A/B — plan + recovery | #58 | `f3bb9035e061fc0babfcace6af891f257eb7fa74` | `d2470601a06da0a4024fa1772b4f32ec2daa7293` | 19/19 SUCCESS |
| C — Codex control | #59 | `3e0e7a921e008d9c6b5198d37b8254fbee174068` | `7c1c755854077d2e0989ff1d3ab3d54f77e9e707` | 19/19 SUCCESS |
| D — metadata UX | #60 | `9be95b10e57a3daa3690205d6c2ffad8da74424d` | `6972f0dba907afd9741c2dc3584f431ee32765ed` | 19/19 SUCCESS |
| E — software readiness | #61 | `0c894ff52f49793f599eb33c4b92b8223e6109b3` | `35191eeaf858041cf5c0767dc1579b67690444ec` | 19/19 SUCCESS |
| F1.1 — shared supervisor | #63 | `c78cb92a5afe8056ab44a1cc4e8a6bea3074e184` | `90df8b9adfe3c03fc089634c18214a4fb6fcfe9e` | 19/19 SUCCESS |
| F1.2 — Runtime composition | #64 | `ef8641bd409bbb6d17db707370de66f552bf4640` | `624b34b656dbf239dbc56fa79d216db7d17a349b` | 19/19 SUCCESS |
| F1.3 — fixed Noise core | #65 | `6d0c0f8ff8b452fd0288d6ac98b1f3fe79352ed7` | `f95d1a4b0f0bdbdda45bd8da6cc10f3f8ac10269` | 19/19 SUCCESS |
| Native browser Noise | #66 | `27ff0161ef65f4a6fe1389a4dbcf4fa318f63db1` | `dfb5eb796f8745ee10cd2a9cefe0cdd15de057a9` | 19/19 SUCCESS |
| R0 — auth worker capacity | #67 | `31a0bc9f38a5c2891a4b9d2bb403a09175579a98` | `d9c26b9eb26664368c384805d1138a5349b92b60` | 19/19 SUCCESS |
| R1 — opaque AWCE framing | #68 | `0dccb2a71ea38259f1e76e2b268961c213bc98e1` | `3ebb3e938a03d067ea7df66b6746b9675637e65b` | 19/19 SUCCESS |
| R10.1 — executable provenance | #69 | `9147cace5b554205dfecc20cf8bfb643d4c46761` | `9529da6d5c110b7a09d5972dfa0db5e012727451` | 19/19 SUCCESS |
| R2 — auth timing diagnostic | #70 | `eca03e47849b12449bb2ab4aec8dfdc001ef13dd` | `f7ef3c936529b19838cd087dc9e232397f1e304d` | 19/19 SUCCESS |
| R9.1 — browser tokenizer | #71 | `a57764ae0e1f3fc962bc4d52e3610373ef4226ff` | `3f2e3a2de4b0482629f5f9a296d5db757f989876` | 19/19 SUCCESS |
| R3/R4 — accepted application crypto | #73 | `df943ecbf37b6c748dc1af73f4270017a3d9f6dc` | `e4a6ecd0bc28de8b3895453cf9160f9a8d4e0064` | 19/19 SUCCESS |
| R5 — full wire profiles | #74 | `62d04adbfa775f3a14ab678c485093f15b1039ed` | `3b11ebf0b3442c111586fc08df9f6a5a4abb3db6` | 19/19 SUCCESS |
| R6 — staged admission | #75 | `679b2f71ec5917ead7695c3b20cb1118cb46cc76` | `a27621faca0e0d04b529b51993f98138496a75b5` | 19/19 SUCCESS |
| R7 — Runtime encrypted stream | #76 | `01c716bd4713ef4a6676b71754a4e065ebce3b82` | `4180f0991af97cba108b6e5a707b7abf58a444d2` | 19/19 SUCCESS |
| R8 — API ciphertext relay | #77 | `a2c0b6afd002455267745d3da4d21bd87943da8a` | `64d37f9a4d39195930959c53c926a4184877355a` | 19/19 SUCCESS |
| R9 — browser trust + bounded terminal | #78 | `fdf2bd77ac3178ee973d10c5429b1b2d8b7a5051` | `15a4632f915dd1e1bde19425e313b52ada27166f` | 19/19 SUCCESS |
| R10 — fixed interactive process | #79 | `0d9e7c7f2abdd7a19dabc611fd1d2c8d01d3d013` | `341a69bf855f48f90cbecfb5c6872c3bf8c28360` | 20/20 SUCCESS |

PR #61 merged at `2026-09-03T05:47:57Z`. Every listed merge was followed by a
GitHub merge read-back and `git fetch origin --prune`; commands exited `0`.
All B/C/D/E merge commits completed all six post-merge workflows. E main
`35191eeaf858041cf5c0767dc1579b67690444ec` was re-read after completion; all six
were terminal SUCCESS, separately from its reviewed PR-head evidence.

## Implemented scope

- Pure recovery/cursor/lease identity fences and browser stale-event rejection.
- Typed Project-scoped Claude/Codex Start/Stop/ticket contracts with exact
  response identity, CSRF/recent-auth, transient tickets and no-store behavior.
- READY Project/AgentType metadata lookup, explicit Start and native exact Stop
  confirmation; stale lookup/action/auth/Runtime observations fail closed.
- README, limitations, acceptance, platform and release documents now agree;
  candidates include four fixed WAW workflow/recovery/readiness/host-gate docs.
- Phase 11 includes metadata/capability/Runtime Secret Store foundations, not a
  product Provider/Secret Manager or production activation capability.

## Verification evidence

- Recovery tests: `pytest -q tests/unit/test_waw_recovery.py tests/unit/test_waw_lease.py tests/unit/test_waw_supervisor.py tests/unit/test_waw_stream_contract.py tests/unit/test_waw_lifecycle.py`: exit `0`, 101 passed.
- API/command tests: `pytest -q tests/integration/test_waw_workspace_api.py tests/unit/test_waw_admission.py tests/unit/test_workspace_api_contract.py tests/unit/test_waw_codex_command.py`: exit `0`, 56 passed.
- Web `typecheck`, `lint`, `format:check`, `build`: exit `0`; `NODE_OPTIONS=--no-experimental-webstorage pnpm test`: exit `0`, 115 passed.
- `ruff check`, `black --check`, Linux-target mypy: exit `0`; 188 application/test Python files and 14 installer files checked in the respective runs.
- `pytest -q tests/unit/test_release_candidate.py`: exit `0`, 22 passed, with an expected duplicate-ZIP fixture warning.
- Full local E2E first passed the 54 existing tests and found four ambiguous new test locators. After correction, all four new desktop/mobile metadata E2E passed; the final complete E2E CI gate passed for PRs #60 and #61.
- Main-agent visual QA viewed actual Chromium at 1280x900 and 390x844 for normal/native Stop/empty/error states: no horizontal overflow, tested controls at least 44px, Cancel/Escape restored Stop focus. Synthetic metadata only; screenshots were not committed. Temporary preview was stopped.
- Independent read-only Architecture/Security/Test reviews found no remaining blocker in the delivered software scope. Visual work was main-agent structured QA, not an independent visual certification.
- Local Python 3.14.7 / Node 26.7.0 / pnpm 11.19.0 differ from CI's supported matrix. The expanded macOS WAW matrix did not pass (Linux socket/provenance requirements); it was not promoted to host evidence. Python tests above used `.venv/bin/python -m pytest`; Linux CI is the authoritative supported matrix.

## Independently verified candidate with packaged WAW docs

- E head: `0c894ff52f49793f599eb33c4b92b8223e6109b3`; source ref kind `pull_request_head`.
- Release Candidate run `33719963292`, artifact ID `9879903829`; terminal SUCCESS.
- Tarball SHA-256: `9b1dcd19452a79ee933a4781da368d70415deb374b2a6bd46353501b0c23eb03`.
- Manifest SHA-256: `20d460d8e1a4aee9c05149289d474fcbf2ed9d20904acd685eccb154d60ed354`.
- SBOM SHA-256: `4405cf4f6c8510da3cfacf346a0231893ac8133c94bc5cda3200da3068c676d4`.
- `scripts/check-release-artifact.py` with exact source/ref: exit `0`, 81 archive members, 2757 nested wheel members, 27510853 bytes, no source maps/canaries; all four required WAW docs present. Download and read-only validation only, no install/execution.
- Earlier merged implementation artifact and complete scope are recorded in `../WAW_SOFTWARE_READINESS.md`. Artifact integrity is not publisher authenticity; the candidate is unsigned.

## Current action after Owner clarification

Owner explicitly clarified that development continues on this Mac. The missing
Linux host is a gate for actual activation/qualification, not a blanket block
on software implementation. The prior blocked status has been superseded for
Mac development; A–E remain historical delivered increments.

PR #63 delivered shared Claude/Codex supervisor/stream integration.
PR #64 delivered the concrete lifecycle executor, read-only process probe,
two-phase attachment boundary and failed-start cleanup/restart fencing. PR #65 delivered
fixed Noise NX Python/WebCrypto cores and their interoperability checks; application
encoding remains a separate pending decision.
Real Runtime/PTY/Noise/WebSocket deployment and production readiness are not
claimed. Next scope is in `NEXT_ACTION.md`.

Live preflight from `dfc788a29623de5b5a9c3230855af1ee7aed2953`: clean tree,
HEAD/main/origin/main/merge-base equal, six exact-main workflows SUCCESS, only
historical Draft PR #42 open. Git fetch/GitHub reads exited 0.

## F1.1 merged evidence

- Shared concrete Claude/Codex command union, full supervisor binding checks,
  command revalidation and terminal stream cleanup/replay fences implemented.
- `.venv/bin/python -m pytest -q tests/unit/test_waw_command.py tests/unit/test_waw_codex_command.py tests/unit/test_waw_supervisor.py tests/unit/test_waw_stream_contract.py tests/unit/test_waw_transport.py tests/unit/test_waw_lifecycle.py tests/integration/test_waw_workspace_api.py`: exit 0, 135 passed.
- `ruff check apps packages tests migrations`, `black --check ...` and
  `mypy --platform linux apps/api apps/worker apps/cli packages tests`: exit 0;
  mypy checked 189 source files.
- Independent read-only review: PASS for this increment, including positive
  cleanup proof, rejection of post-close replay and explicit unsupported real
  Codex tmux handling. Targeted reviewer tests passed (55).
- No frontend behavior, CLI argv, real host, credential or production activation
  changed. Mac development evidence is not Linux-host qualification.

## F1.2 merged Runtime composition

- Concrete `WAWSupervisorExecutor` shares exact supervisors between lifecycle
  dispatch and admitted stream bridges; factories are trusted Runtime inputs.
- Status/reconcile use a separate exact read-only probe. They do not reconnect
  a PTY, grant a writer or clear uncertain input.
- Failed readiness keeps the exact cleanup target. Durable generation
  reservation precedes process effects; unknown restart state stays quarantined
  until the existing host evidence path acknowledges cleanup.
- PR #63 merged at `2026-09-03T06:43:01Z`; GitHub merge read-back and fetch
  both exited 0. F1.2 validation/review and subsequent PR #64 CI/merge are complete.

F1.2 final local validation before PR CI:

- `.venv/bin/python -m pytest -q tests/unit/test_waw_command.py tests/unit/test_waw_codex_command.py tests/unit/test_waw_supervisor.py tests/unit/test_waw_stream_contract.py tests/unit/test_waw_transport.py tests/unit/test_waw_lifecycle.py tests/unit/test_waw_bootstrap.py tests/unit/test_waw_runtime_executor.py tests/integration/test_waw_workspace_api.py`: exit 0, 187 passed.
- `ruff check apps packages tests migrations`, `black --check apps/api apps/worker apps/cli packages tests migrations`, `mypy --platform linux apps/api apps/worker apps/cli packages tests`: exit 0; 199 formatted files and 191 typed files.
- `scripts/check-doc-links.py`: exit 0, 156 relative links; `git diff --check`: exit 0.
- Independent read-only review PASS; reviewer ran 127 tests before the final
  two binding cancellation/path-drift regressions. Final executor test file:
  14 passed, including those regressions. All transports/processes are synthetic.
- Six exact-main workflows for `90df8b9adfe3c03fc089634c18214a4fb6fcfe9e`
  completed successfully; this is separate from PR #63's reviewed-head CI.


## F1.3 merged fixed Noise core

- PR #64 merge read-back: `624b34b656dbf239dbc56fa79d216db7d17a349b`,
  merged at `2026-09-03T07:09:03Z`; GitHub merge/fetch exited 0. Final independent
  composition review passed with 129 tests. A final pre-existing composition
  regression was subsequently added locally (15 executor tests); it is tracked
  with the next software increment rather than attributed to the earlier SHA.
- The new Python and WebCrypto modules implement only fixed Noise revision-34 NX
  and split CipherStates. Existing cryptography 50.0.0 and native WebCrypto are
  used; no dependency, real-key file loader, socket or product activation added.
- Shared Noise-C public vector has pinned commit, source/fixture SHA-256 and MIT
  notice. It contains public test key material only.
- Handwritten state-machine independent security review: PASS after fixing
  concurrent destroy/late-result, malformed-input and key-reference handling.
  Reviewer ran 14 Python core tests and the real Python/Node interop check.
  Golden vectors and cross-language positives were reviewed separately from
  concurrency/failure regressions.
- `WAW_ENCRYPTED_STREAM_DECISION.md` provides the concrete proposed application
  bytes absent from the historical architecture; Owner confirmation requested.
  Fixed core implementation continues, while those application bytes remain
  unimplemented/unapproved. See `../WAW_NOISE_CORE.md` for exact scope.


F1.3 final local validation before PR CI:

- `AGENTBOX_NOISE_TEST_PYTHON="$PWD/.venv/bin/python" node scripts/check-noise-interop.mjs`: exit 0; both roles, exact independent handshake/hash/four transport vectors, nonempty AD, bidirectional transport and tamper/closed-state fence.
- `.venv/bin/python -m pytest -q tests/unit/test_noise_nx.py tests/unit/test_waw_runtime_executor.py tests/unit/test_waw_noise_contract.py`: exit 0, 54 passed (14 new core, 15 executor, 25 existing metadata contract).
- Web Vitest: exit 0, 129 passed; new core tests include paused AES/DH destroy, constructor digest destroy, malformed inputs, maximum boundaries, prologue mismatch and low-order peer rejection. Node WebCrypto evidence, not native-browser certification.
- Web Prettier, ESLint, typecheck and production build: exit 0. No visible UI or admission route changed, so a new visual check is not applicable.
- Ruff, Black, Linux-target mypy: exit 0; 202 formatted files, 194 typed files. Documentation link check: exit 0, 164 relative links. `git diff --check`: exit 0.
- Core review, local tests and all 19 PR #65 exact-head CI checks completed successfully. Application bytes, pins, encrypted relay, real CLI/PTY/host and production readiness remain unclaimed.


## Delivery read-back and next decision

PR #65 merged at `2026-09-03T07:40:44Z`; GitHub merge, merge read-back,
`git fetch origin --prune`, local main fast-forward and delivery-branch creation
all exited 0. F1.1/F1.2/F1.3 have completed applicable software tests, independent
reviews and exact-head CI/merge. This is not completion of the interactive
terminal product or F2 host qualification.

The next application-profile implementation is **未开始** pending the complete
supplemental decision in `WAW_ENCRYPTED_STREAM_DECISION.md`. The earlier three-rule
proposal has been expanded after identifying additional protocol conflicts;
Owner acceptance of the complete proposal has been requested and not received at
this snapshot. That is an architecture clarification under GOVERNANCE, not a Linux
host prerequisite for ordinary Mac development. After approval, continue the
application crypto, ciphertext-only relay, staged admission, browser controls
and remaining CLI/host acceptance in the existing plan.

## Native browser follow-up in the delivery PR

- Added `apps/web/e2e/noise-core.spec.ts`, reusing the actual core and pinned
  vector in native browser WebCrypto. No duplicated crypto implementation or
  product route/UI activation. Trace/video/screenshots disabled.
- Local engine: Chromium `151.0.7922.34`, desktop/mobile profiles. Both crypto
  tests passed, including the exact six messages/hash, nonextractable private
  keys, bidirectional AD and original-counter tamper/retry rejection.
- `node scripts/run-e2e.mjs`: exit 1, 56 passed and 4 existing 5-second
  authentication waits timed out (three Dashboard waits, one credentials alert).
  This is not recorded as a full local E2E pass. The new native crypto cases both
  passed in that run; root cause of local timing remains unproven. Linux CI must
  pass the complete updated suite before merge.
- Native test Prettier, ESLint and TypeScript checks passed. The worker's static
  preview on port 4173 was stopped; the isolated harness cleaned its own API,
  preview and temporary data after the run.
- The application byte proposal also passed independent read-only review as a
  coherent clarification. Its status remains PROPOSED pending Owner acceptance.


## Current reassessment

Owner requested a fresh remaining-plan evaluation, a persistent goal and
model-routed multi-agent work: complex sol, ordinary terra. See REMAINING_PLAN.
Sol confirmed AUTH-CAPACITY-CANCEL with an in-memory barrier reproduction:
configured limit 1, cancelled caller, peak actual workers 2. R0's fix and
deterministic unit/API verification are merged; this is not claimed as the cause
of old Mac E2E timeouts. Terra implemented independently specified opaque AWCE framing.
Sol also found additional full wire/admission/trust conflicts beyond the three
proposed bytes; those are consolidated in the new plan instead of silently
promoting the synthetic bridge or metadata state machine to production.


R0 local implementation evidence:

- `BoundedLoginExecutor` keeps shared login/reauthentication capacity until the
  underlying executor Future finishes, independent of caller cancellation. A
  non-throwing completion signal prevents Python 3.14 shield late-error logs;
  original exceptions still reach active callers and ContextVars propagate.
- `.venv/bin/python -m pytest -q tests/unit/test_auth_executor.py tests/integration/test_auth_api.py`: exit 0, 45 passed (14 new deterministic executor cases plus 31 existing auth API tests).
- Scoped Ruff, Black, Linux-target mypy and whitespace checks: exit 0.
- Independent sol review: PASS for this bounded fix; 14 executor cases rerun as
  part of its 48-case Python review with the separate opaque AWCE work.
- No password/Session/CSRF policy, limiter budget, database locking or E2E timeout
  was changed. The previous four Mac E2E authentication timeouts are not claimed
  resolved by this fix. PR #67 completed all 19 exact-head checks and merged at
  `2026-09-03T09:26:56Z`; GitHub read-back, fetch and main fast-forward exited 0.

## R1 framing and R3 proposal evidence

- R1 implements strict Python/Web opaque AWCE v1 framing and a shared header
  builder usable before encryption. Scope, field offsets and evidence are in
  [WAW_AWCE_FRAMING](../WAW_AWCE_FRAMING.md). No channel crypto or socket is activated.
- Python AWCE tests: exit 0, 44 passed. Web AWCE tests: exit 0, 38 passed.
  Bidirectional Python/TypeScript interop: exit 0. Scoped formatting/lint/type
  checks passed; independent sol read-only codec/header review: PASS.
- The complete R3 supplement freezes proposed key schemas/context derivation,
  Runtime/browser confirmation responsibility, ACK hop mapping, API ciphertext
  drop handling, effective limits and signed-pin compatibility. Independent sol
  review passed; three public Ed25519 fixtures and bootstrap digest were verified.
  It remains **PROPOSED**, not Owner acceptance or implemented application behavior.
- R1 merged at `2026-09-03T10:05:01Z` after 19/19 exact-head CI; read-back,
  fetch and main fast-forward exited 0. R2 diagnostics and R10 are separate increments.
- PR #66's Linux E2E run `33731800570`: exit 0, all 60 tests passed in 42.3s.
  Its six post-main workflows also completed SUCCESS. This does not erase the
  earlier four local timeouts or prove a local root cause.

## R10.1 executable provenance evidence

- New trusted Runtime inventory and descriptor-held executable verifier implement
  closed kind selection, root-owned no-follow ancestry, regular native ELF/file
  checks, bounded exact hash, path/descriptor revalidation and synchronized
  lifetime/cleanup. No execution or public filesystem action exists.
- `.venv/bin/python -m pytest -q tests/unit/test_waw_executable.py`: exit 0,
  80 passed / 1 native Linux skip. Scoped Ruff/Black/Linux-target mypy: exit 0.
- Independent sol read-only review: PASS, including additional syscall-failure
  and close/reuse injection. Mac positive stat/platform fixtures are synthetic;
  actual FD/read/rename/close work is exercised. No Linux-host readiness claimed.
- See [WAW_EXECUTABLE_PROVENANCE](../WAW_EXECUTABLE_PROVENANCE.md) for the API and
  [WAW_INTERACTIVE_PROFILE_ASSESSMENT](../WAW_INTERACTIVE_PROFILE_ASSESSMENT.md)
  for remaining launch/environment/state/retention gaps. R10.1 merged at
  `2026-09-03T10:15:12Z` with 19/19 exact-head CI and read-back; full R10 stays in progress. Browser parser foundation is independent R9 work.
- R2's review found raw exception logging, missing metrics accepted as PASS and
  an ambiguous 5-second flag. Fixes passed 21 dedicated regression cases and a
  fresh 4/4 isolated Chromium diagnostic; independent sol re-review passed with
  all 21 regression cases executed. R2 subsequently merged after 19/19
  exact-head CI and read-back.
  The historic four local auth timeouts remain unproven, not marked fixed.

## R2 diagnostic delivery evidence

- Added closed `--auth-timing` mode to the existing isolated harness, separate
  diagnostic Playwright configuration/spec and test-only numeric API wrapper.
  Normal default E2E selection and production auth/database policy are unchanged.
- Repaired three independent review findings: raw exception logs, missing metrics
  accepted as PASS and a misleading total-visibility flag. Required sample
  completeness, fixed numeric failure metadata and separate per-assertion/total
  elapsed flags are verified. See [AUTH_TIMING_DIAGNOSTIC](../AUTH_TIMING_DIAGNOSTIC.md).
- Worker and independent sol reviewer each ran 21 dedicated regressions, exit 0,
  zero skipped, including real Uvicorn/child-process and transpiled-spec negatives.
  E2E CI runs them after web dependency installation so these negatives cannot
  silently skip due to a Python-only job lacking TypeScript.
- Repaired isolated Chromium diagnostic: exit 0, 4/4 in 6.5s, observed visibility
  approximately 78–456 ms. Root default `node scripts/run-e2e.mjs`: exit 0,
  60 passed in 37.2s with API/preview cleanup. Historical timeout cause remains
  unknown; current passing samples do not establish a latency fix.
- Scoped lint/format/type/syntax checks and independent sol re-review passed.
  R2 merged at `2026-09-03T10:23:56Z` with 19/19 exact-head CI and read-back.
  CI E2E job `100611172739` executed all 21 regressions (3.67s) and the complete
  60-test browser suite (40.0s); no diagnostic case was skipped. R9.1 remains
  a separate increment; no browser terminal/controller has been enabled.
- PR #69 Python 3.13 CI job `100608598342`: 1864 passed / 1 skipped / 5 warnings
  in 171.77s. This is full software CI, not real CLI/host qualification.

## R9.1 tokenizer foundation evidence

- Added pure incremental UTF-8/VT tokenizer with typed output tokens, the closed
  character/control allowlist, frame/task/sequence/raw-line limits and explicit
  reset/destroy. No renderer, browser response, DOM, logging or persistence exists.
- Independent sol review found line overflow masking a simultaneous frame-control
  limit and incomplete ESC/CSI state exposing a denied C1 sequence body. Both
  were fixed; the same-root ESC re-entry case was fixed with the same budget rules.
  Output suppression no longer bypasses parsing/counters, and introducer changes
  preserve the earliest deadline and cumulative byte count.
- Worker and independent reviewer each ran 113 scoped Vitest tests, exit 0.
  The reviewer additionally ran 133 independent negatives against actual
  transpiled source, all passed. Independent sol re-review: PASS.
- Scoped ESLint, Prettier, TypeScript and whitespace checks passed. No visible
  UI change, so visual QA is not applicable. See
  [WAW_BROWSER_TOKENIZER](../WAW_BROWSER_TOKENIZER.md) for API and integration limits.
- R9.1 merged at `2026-09-03T10:32:17Z` after 19/19 exact-head CI and read-back.
  Frontend CI job `100613672473` ran 280 tests in 13 files, all passed, and both
  Noise NX / AWCE interoperability checks passed. Full R9 remains incomplete: renderer/controller,
  trust/crypto/admission, attachment scheduler and exact detach are not connected.
  Logical-line deadline duration and post-limit controller recovery still need
  explicit contract resolution; this core does not invent them.

## Historical checkpoint before software decision delegation

The current reassessment delivered five reviewed software increments: R0, R1,
R2, R10.1 and R9.1. Each has an observed merged PR and 19/19 successful exact-head
checks. Each stage updated GitHub and its scope/verification/plan documents.
The complete terminal product and the persistent overall goal are not complete.

The next implementation is R4/R5 after explicit acceptance of the reviewed
[complete protocol supplement](WAW_ENCRYPTED_STREAM_DECISION.md). Acceptance has
been requested but not received; its status remains PROPOSED. This is the
architecture Owner gate in GOVERNANCE, not an extra routine PR approval or a
requirement to move development off this Mac. No real key, Provider Secret,
Runtime HOME, CLI login, host activation or production release was performed.

Additional remaining decisions/evidence are tracked explicitly: interactive
AgentType launch/state/retention/official login/Project Trust profile; the
independent browser trust provider; logical-line deadline and post-limit
controller recovery; complete stream/relay/terminal integration; then authorized
real-host/CLI/isolation/restart qualification. Historical local authentication
timeouts were not reproduced, so their root cause remains unknown.

Independent terra documentation review found one stale R2 merge sentence and
missing R9/R10 decision dependencies in the plan's acceptance cells. Those are
corrected in this documentation checkpoint. Existing historical evidence and
PROPOSED architecture status are preserved.

## R3/R4 delegated implementation evidence

- Complete R3 supplement accepted by the Coding Agent under the Owner's explicit
  software decision delegation. GOVERNANCE/NEXT_ACTION/plan record that the old
  software approval blocker is resolved; real target/key/production scope and
  evidence remain separate.
- R4 implements exact context/prologue, four key frames, independent pin checks,
  confirmation n=0, AWCE n>=1/AAD/size/cursor binding and permanent failure/close
  fences. See [WAW_APPLICATION_CRYPTO](../WAW_APPLICATION_CRYPTO.md).
- Root Python context/profile + Noise/AWCE: exit 0, 560 passed. New Web suites:
  exit 0, 148 passed. Independent primitive reference and Python/WebCrypto
  bidirectional full-profile interop: exit 0, exact complete vector/bounds/fences.
- Independent sol review: PASS after fixing Python close publication and final
  readiness publication races. Both original P1 reproductions were rerun and
  rejected correctly; previously verified Web/metadata/vector evidence retained.
- Root isolated full E2E: exit 0, 62 passed in 45.3s, including new native
  Chromium desktop/mobile application crypto tests. Earlier attempt stopped at
  a temporary in-progress R5 test compile error, not a browser test failure.
- R3/R4 merged at `2026-09-03T11:54:23Z` after 19/19 exact-head checks;
  merge read-back/fetch/main fast-forward exited 0. R5 repaired hostile numeric exponent,
  failure-state/order, paired-source and Python sequence synchronization findings;
  independent R5 review passed with 276 Python / 274 Web cases. Its software
  delivery remains separate; no product admission is claimed.

## R5 full wire evidence

- All 27 types / 50 direction profiles, strict exact scalar/JSON/binary codecs,
  four-leg observed ordering, byte-preserving key/opaque relay and bounded FIFO
  source witnesses are implemented. Python state changes use RLock; no grant,
  decryption, ACK lifecycle or actual network ownership is implied.
- Independent sol review closed extreme-number exception escape, early/regressing
  STATE, premature browser failure, unsourced/altered relay and concurrent hop
  acceptance findings. See [WAW_WIRE_CONTRACT](../WAW_WIRE_CONTRACT.md).
- Python 279 / Web 274 cases passed; independent schema/negative/boundary review
  passed. Python/Web interop covers 50 controlled-clock structural profiles and
  four actual-clock probes, preserving raw key JSON and immutable AWCE bytes.
- Actual-clock combined R6/API/ticket/wire tests initially failed under parser GC
  or cold timestamp work. Moving the number-token type to module scope and using
  direct strict calendar validation resolved both causes without changing GC or
  the 5 ms budget. Final combined gate: exit 0, 496 passed.
- Independent fresh-process measurements: 6/6 first ADMITTED decodes passed,
  0.594–1.141 ms CPU; 5,000 mixed decodes had zero failures, P95 0.185 ms,
  maximum 1.430 ms. Injected >6 ms CPU work remains rejected. These are local
  measurements, not universal latency guarantees.
- R5 merged at `2026-09-03T13:03:37Z` after 19/19 exact-head CI; exact
  merge/fetch/main read-back completed. R6 passed independent review after four fixes;
  30s stale/60s grace and complete active lifecycle remain R7/R8 dependencies.

## R6 staged admission evidence

- Real staged ticket authority and coordinator implemented over closed ports,
  including exact burn/reserve/advance, required Audit, bounded quarantine,
  commit retry, reader retirement, atomic publication and positive cleanup.
  See [WAW_STAGED_ADMISSION](../WAW_STAGED_ADMISSION.md).
- Independent sol review PASS after four fixes: known mismatched bearer burn,
  single-reader handoff, known-cleanup issuance fence and detached failure Audit
  after Runtime cleanup errors. New suites: 135 passed; scoped type/lint/format
  and relevant existing API/ticket regressions passed. The actual-clock combined
  R6/wire suite passed 496 cases after R5 performance repair.
- The 30s stale/60s grace, idle/absolute lifetime, Runtime health, native controls,
  failed-attempt rate limits and real Audit/network adapters remain R7/R8 scope.
  Configured authority expiry is not a standalone live-input authorization proof.
- R6 merged at `2026-09-03T13:33:51Z` after 19/19 exact-head checks; normal
  merge, read-back, fetch and local main fast-forward exited 0. Root final staged/
  coordinator/ticket regression: exit 0, 164 passed; scoped lint/format/type passed.
- R7 Runtime server/lifecycle and R8 native WebSocket/API relay are being
  implemented in parallel; no complete terminal or real-host qualification is
  claimed yet. See [Runtime stream scope](../WAW_RUNTIME_ENCRYPTED_STREAM.md).

## R7/R8 current review checkpoint

- R7 worker completed bounded failure profiles, health/ping checks at each live
  permit, truthful non-exit STATE handling and preserved workspace fault fences.
  Actual UDS regressions also repaired late OUTPUT after detach/exact Stop, with
  socket publication tied to cleanup and the exact Runtime lease invalidator.
- Latest R7 stream/server/supervisor/executor command: exit 0, 160 passed; all
  ten owned files passed scoped lint/format/Linux-target type checks. Final
  independent R7 review found P1 map/supervisor lock inversion during a new Start
  and late old registry.open, plus P2 retaining 2001 logical lines by omitting a
  trailing non-LF line. Both were repaired before merge.
- Independent R7 review ran 11 targeted tests and four actual UDS writability
  delay/cleanup/revoke/health/Stop cases, all exit 0. Its deadlock and line-count
  reproductions also exited 0 and confirmed the defects. These results do not
  establish real-host qualification.
- Repaired R7 matrix: 170 passed; focused lock/state/cancellation set 16 passed;
  PTY set 17 passed. All ten R7 files passed lint/format/Linux-target mypy.
  Independent re-review PASS: 10 deadlock/state tests plus all 17 PTY tests,
  with exact repair hashes matched. R7 final head
  `01c716bd4713ef4a6676b71754a4e065ebce3b82` passed 19/19 exact-head checks
  and merged as `4180f0991af97cba108b6e5a707b7abf58a444d2` at
  `2026-09-03T17:46:25Z`. Fetch/main fast-forward/read-back exited 0; all six
  exact-main workflows subsequently completed SUCCESS.
- R8 repairs cover terminal queue authorization, actual send guards, pending PING
  deadlines and fresh browser-leg correlation IDs. Shared 128 partial slots /
  8 MiB parser accounting and synchronous first-ciphertext-drop fencing are now
  implemented. A shared INPUT ownership ledger now spans native-ready,
  browser-delivery, relay-pending and Runtime-send-inflight without releasing
  capacity at layer transitions. Its expanded matrix passed 604 cases; full
  lint/format and Linux-target mypy over 224 files passed. Independent direct
  replays closed the
  terminal, pending-PING, first-drop and former 65872-byte INPUT findings.
  Final R8 review found and closed a relay P2 and an admission-coordinator P1:
  `authority.fence` and CLOSE-frame encoding failures no longer skip Runtime
  cleanup, detached Audit or local transport/budget/wire closure. Cleanup is
  single-task and cancellation-resistant; first fence errors propagate only
  after cleanup, and authority release still requires exact positive proof.
  Independent re-review PASS: 12 directed cases, 126 admission unit cases and
  69 sandbox-compatible relay cases. Main-agent validation passed 539 R8 Python
  cases, 832 Web cases, 50-profile wire interop, Ruff, Black over 232 files,
  Linux-target mypy over 224 files, Web build and all 62 isolated Chromium E2E
  cases. R8 final head `a2c0b6afd002455267745d3da4d21bd87943da8a`
  passed 19/19 exact-head checks and merged normally as
  `64d37f9a4d39195930959c53c926a4184877355a` at `2026-09-04T04:11:58Z`.
  Fetch/read-back exited 0 and all six post-main workflows completed SUCCESS.
- An optional whole-repository macOS pytest run was stopped at 37% after 1,013
  passed, 184 failed and 2 skipped. The first failures were macOS AF_UNIX path
  length plus Linux/root-owned installer, diagnostics and Secret Store semantics;
  it is neither a pass nor R8 regression evidence. The exact-head Ubuntu matrix
  remains the authoritative full-suite gate.
- The R6 admission-negative integration seam is a separate uncommitted R8 change:
  17 new tests pass; independent review closed both correlation and per-frame
  revocation findings, with 26 focused coordinator/wire tests and direct replay.
- The existing two Sol/high execution/review roles resumed after a model-service
  interruption; unfinished checks were retained as unverified. A separate
  Sol/ultra role is doing only the new R9 read-only plan under the updated working
  agreement, with no execution delegation or file writes from that role.
- The visible version plan is approved. R7 delivered `0.3.0rc2`; the R8 worktree
  is now `0.3.0rc3`, with root/Web metadata and release documents aligned. Version
  consistency, TypeScript, lint and format passed. The R8 isolated browser suite
  passed 62 tests; actual desktop and 390x844 mobile Dashboard views showed
  `0.3.0rc3` / API v1 with no horizontal overflow or overlap. This is local
  preview evidence, not deployment.
- The approved Sol/ultra plans for Start lock order and shared INPUT ownership
  are implemented. R9 trust lifecycle and bounded terminal model implementation
  is active under the accepted browser decision; real provider qualification
  remains separate.

## R9 reviewed candidate and R10 plan

- Public trust lifecycle/provider/Chromium repairs pass 121 Web tests and the
  unchanged PyCA bootstrap/three-signature/nine-mutation vectors. Cumulative
  latest-ACTIVE checkpoints, strict history prefix/floors/tombstones, revocation,
  crash-fail-closed store transitions, exact registration/invalidation and the
  six-second provider request deadline are implemented.
- The bounded terminal passes 185 tokenizer/model/scheduler tests plus two
  offline Unicode generator checks. Fixed UCD 13 rules, cooperative five-
  millisecond work, exact 50 ms fixed-window throttling, 256 KiB/2,000-line
  cross-layer reservations, UTF-8 carry expansion and resumable maintenance are
  covered.
- The managed provider core includes an inert MV3 extension, fixed external/
  Native Messaging/trustd protocols, service-owned Ed25519 state/floor/time
  store, DNS policy, deployment cross-pin builder and Web adapter. Python
  provider/store/native/package tests pass 13 cases; MV3 passes 4. The production
  build emits the exact six-file inventory and passes a real `dist` to public-only
  bundle gate. No CRX, real extension ID/Origin, policy or service is installed.
- Browser locale/controller/Workspace shell passes 41 focused tests. Only
  `navigator.languages[0]` selects the document locale: primary `zh` maps to
  `zh-CN`; every other/missing/malformed value maps to English. Technical values
  remain printable English ASCII with `lang=en`, `dir=ltr`, `translate=no`.
- Root Web tests pass 915 plus 4 extension tests. Desktop/mobile Chromium E2E
  passes 64 cases, including Chinese, English, non-Chinese fallback, exact Stop,
  overflow and 44 px control checks. Build/type/lint/format, Ruff/Black on 264
  files, Linux-target mypy on 253 sources, 37 focused Python tests, 236 doc links
  and the real bundle gate pass locally.
- Main-agent visual inspection used the built rc4 assets with bounded synthetic
  metadata. The 1280x900 English Dashboard visibly shows `0.3.0rc4` / API v1;
  the 390x844 `zh-CN` Workspace shows Chinese lifecycle copy and technical values
  in English. Both measured no horizontal overflow, and no terminal payload was
  captured. This is local preview evidence, not a deployed/host-qualified UI.
- Independent read-only Architecture/Security/Test review reports PASS with no
  remaining P0/P1/P2. PR #78 exact head `fdf2bd77...` completed 19/19 checks,
  then merged normally at `2026-09-04T09:22:07Z`; fetch/read-back observed exact
  merge `15a4632f...` with parents `64d37f9a...` and `fdf2bd77...`.
- All six standard post-main workflows for `15a4632f...` are SUCCESS after the
  Security `frontend-audit` retry recovered from npm advisory API 503/timeouts.
  GitHub's separate dynamic Dependency Graph job remains a historical
  `pip-compile` `.lock` include limitation already present before R9; R10 tracks
  the `.txt` include repair and will require its post-main graph to succeed.
- Sol/ultra produced the complete R10 read-only plan: distinct fixed interactive
  Claude/Codex profile, host manifest v2, version/auth/env records, descriptor/WBR
  codecs, three native helper binaries, Runtime composition and inert installer
  assets. No CLI/HOME/key/host action occurred; implementation is approved after
  R9 delivery.

## R10 delivered fixed interactive process

- Runtime host manifest v2 closes the exact-six executable inventory and exact-two
  Claude/Codex profiles. Seven fixed descriptor roles, the 64-byte WBR protocol,
  three native helpers, pre-birth cgroup placement, tmux/PTY attachment, qualified
  auth probes, local-TTY login and host-wide WAW/legacy conflict coordination are
  implemented without activating a host or handling a real credential.
- Rootless isolation uses held-directory authority, in-namespace `openat2`
  reanchoring, exact metadata/mount-flag comparison, non-recursive binds and a
  two-level user-namespace lifecycle. Exact Stop proves cgroup empty, pane pidfd
  exit, process-group disappearance and identity-bound stale-socket cleanup.
- The bridge exits only after descendants are reaped, the inner PTY reaches EOF,
  output is empty and tmux returns the exact 192-bit random cursor challenge. R11
  must quiesce browser INPUT/WBR resize during this final barrier and retain an
  outer minimum size of eight columns by one row.
- PR #79 implementation head
  `6083e6e1aa118b19b548a9070b7e49558988f7e5` completed all `20/20` exact-head
  checks. Python 3.13 quality ran `3428 passed / 43 skipped`; Linux native ran
  `66 passed` normally and `24 passed` with sanitizers. Web ran `915`, the
  extension ran `6`, Chromium E2E ran `64`, release validation ran `143`, and
  the documentation checker verified `238` relative links.
- Independent Sol review reports PASS with no remaining P0/P1/P2 in the R10
  software scope. CI fake-vendor/native evidence is not a real vendor build,
  installed CRX, account, credential, production binary provenance or host
  qualification; those remain R12 gates.
- Documentation-only head `d5d1838...` exposed one sanitizer scheduling flake in
  the native tail fixture: intentional legacy DSR noise at frame 1900 could be
  echoed by the canonical inner PTY and alter tmux row 1 while the test treated
  the rendered grid as a raw log. The fixture now emits all 2,048 strictly
  ordered/hash-checked frames and its marker/padding before the same complete
  DSR5/eight-position DSR6 overlap noise. Production bridge code and every strict
  tail assertion remain unchanged; a new exact-head CI run is required.
- Final exact head `0d9e7c7f2abdd7a19dabc611fd1d2c8d01d3d013` completed
  all 20 checks, including native normal/sanitizer. PR #79 merged normally as
  `341a69bf855f48f90cbecfb5c6872c3bf8c28360`; exact parent read-back, all six
  post-main workflows and the dynamic Dependency Graph update are SUCCESS.
- Browser locale remains fixed: read only `navigator.languages[0]`; primary
  language `zh` selects `zh-CN`; every other, missing or malformed value selects
  English. Technical identifiers remain English. Full cross-page bilingual
  migration is part of R11/rc9.

## R11/rc6 foundation in progress

- The accepted rc6–rc9 composition contract is recorded in
  `WAW_R11_CONTROLLER_COMPOSITION.md`; PR #80 tracks the active rc6 branch.
- An API-only v2 anchor loader reads the fixed public leaf through a held,
  root-owned non-writable directory chain and revalidates all identities. It does
  not open Runtime-private manifest/HOME/Secret state; 21 boundary tests pass.
- Migration `0008_waw_runtime_epoch_fence` adds nullable canonical decimal TEXT
  `last_runtime_epoch`. One `BEGIN IMMEDIATE` transaction classifies first/same/
  greater epochs, preserves terminal rows and atomically fences every nonterminal
  workspace plus pending Stop operation to reconciliation on Runtime advance.
- Bind attestation is durably classified before coordinator publication. Focused
  binding/session/anchor tests pass 49 cases; the complete migration suite passes
  41. Scoped Ruff, Black and Linux-target mypy pass. Commit `4f27409...` completed
  all 20 exact-head checks in PR #80.
- Both systemd-inherited Runtime listeners now re-`listen` with fixed backlog 64
  before readiness/accept so client `SO_PEERCRED` can bind Runtime rather than the
  socket activator. Re-listen failure closes and poisons the inherited listener;
  four deterministic lifecycle tests pass. Real systemd credentials remain R12.
- Listener lifecycle now uses shared start/close operations, sticky close failure
  and explicit control-socket ownership `RAW → IN_FLIGHT → TRANSFERRED`. Close
  never raw-closes an ownership-unknown socket; accept/start failures, direct
  cancellation and delayed cleanup remain poisoned. Thirteen focused tests pass
  with one Linux-only real-loop skip; independent Sol review reports no P0/P1/P2.
- PR #80 head `6467a09...` passed the 66-case normal native run; sanitizer reached
  23 pass / 1 failure because tmux exposed PTY-dead before its child wait status,
  yielding transient `pane_dead_status` empty. The strict DCS gate now waits on a
  unique test-only `pane-died → wait-for -S` child-status event and then requires
  exact `1:74:` (normal exit 74, no signal). Independent Sol review PASS; a new
  exact-head Linux CI run remained required.
- Head `5b4237e...` proved that DCS gate, then the same PTY-dead/status-publication
  race appeared in the closed-descendant status check. All three `remain-on-exit`
  gates now share one test-only unique `pane-died → wait-for -S` barrier and
  strictly require `1:7:`, `1:74:`, and `1:7:` respectively. Tail order/hash and
  descendant termination-canary assertions remain unchanged; another exact-head
  native normal/sanitizer run was required.
- Head `6916406...` passed native normal/sanitizer. Python 3.11 alone then exposed
  a unit-test observation race: the intentionally failing close worker could
  finish and its done callback could clear `_close_operation` before the test
  captured it. The test now captures the synchronously created operation before
  its first await; sticky failure/direct-cancel assertions remain unchanged.
  Python 3.12/3.13 and the other 19 checks passed. Head `4059474...` then completed
  all 20 exact-head checks, including Python 3.11 and native normal/sanitizer.
- API control bind now publishes one retained `BoundRuntimePeer` only after full
  response/EOF, anchor attestation and durable epoch classification. Every later
  control request and stream connection borrows only a duplicate of that retained
  pidfd with exact peer credentials, owner identity and generation checks.
- Coordinator/client close synchronously fence new bind/request/borrow work;
  candidate publication rechecks the fence. Poison and close are irreversible;
  a retired client can issue only one replacement after a successful terminal
  close. `poll(0)` supports high pidfds, and uncertain writer cleanup poisons.
  Focused regression passes 115 with one Linux-only peer integration skip; full
  Linux-target mypy checks 254 sources. Independent Sol review reports PASS with
  no P0/P1/P2. Commit `3f7c301...` completed all 20 exact-head checks.
- Runtime `WAWPeerAuthority` now models candidate, connection lease, transfer plan
  and retained authority generation. It rejects foreign leases before locking,
  uses authority-to-FD lock order, and exposes an authority-scoped `RuntimePeer`
  view that survives connection-lease close but not transfer/poison/close.
- First/exact-repeat bind, live conflicts, terminal transfer, random new epochs,
  retired replay/capacity and CAS single-winner behavior are closed. Destructive
  transfer failure permanently poisons; all detached FD close errors are sticky,
  later close rethrows the first error without retrying an old FD number. Thirty-one
  focused tests and scoped Ruff/Black/Linux mypy pass; independent Sol review
  reports no P0/P1/P2. Exact-head CI remains required for this foundation.
- Runtime peer authority must now be wired through control dispatch, lifecycle
  bind/transfer and encrypted streams. Redraw and application ownership remain
  active rc6 work. No production WAW path is enabled by this foundation.

## R11/rc6 current composition checkpoint

- The upstream rc6 branch head before this documentation checkpoint is
  `9bf5e8d...`; it contains the API owner, browser-controller foundation and
  Runtime durable binding-store checkpoints. Its exact-head CI must be read from
  GitHub rather than inferred from older PR #80 evidence.
- Commit `708acd8...` adds the first Project Start path, closed typed executable
  evidence action, exact bound-host/epoch checks, response-loss fencing and
  concurrent first-use convergence. Its `029378e...` exact-head run failed 3
  Python matrix jobs on one shared Runtime verifier inode-reuse assertion; the
  other 17 checks passed.
- Repair `3ba85cb...` retains at most 256 verified Project descriptors for the
  Runtime epoch and rejects replacement before inode reuse can alias an existing
  binding. Local scope validation is 169 passed with one Linux-only skipped
  control-path test; Ruff, Black and Linux-target mypy pass. The resulting
  `bbdd67c...` exact head completed 20/20 checks; independent rc6 review remains
  pending.
- Documentation-only head `801a494...` then failed native attach READY status 71,
  with the other 19 checks passing. `af4d43e...` replaces fixed short client
  polling with one bounded monotonic READY deadline while preserving exact
  PID/session validation; Linux native passed. `2381171...` then exposed only a
  Black format failure in the new Python test, repaired by `9d078b4...`; its full
  CI completed 20/20 at `4222242...`.
- At this historical rc6 checkpoint, the planned order was rc7 deterministic
  composed failure injection, rc8 artifact/operations rehearsal and rc9 full
  locale migration. The opening current-state record supersedes this historical
  ordering; the R12 real-host boundary remains unchanged.
- Integration commit `e210d749...` completed 17/20 exact-head checks; all three
  Backend Python quality jobs failed on the same preserved non-fixed server
  restart contract. The reviewed follow-up restores restart only after a clean,
  successful non-fixed shutdown with no control server, poison or owned resource;
  fixed WAW composition remains terminal and the consumed Runtime epoch is not
  reset. `test_runtime_server.py` completed 23 cases, full static gates pass and
  independent Sol review reports PASS. Follow-up `c534fe437...` completed 20/20
  exact-head checks, including Linux native and Backend Python 3.11/3.12/3.13;
  each Backend matrix reported 3577 passed and 43 host-gated skips.
- The current bounded-redraw continuation is uncommitted. A neutral contract
  retains at most 24 physical rows and 60 KiB, using row 25 and byte 61,441 only
  as discarded sentinels. Held-FD tmux capture verifies socket, pane and retained
  pidfd identity both before and after one shared one-second deadline. The
  supervisor now owns one atomic capture/cursor/baseline publication, and the
  registry, attachment service and bootstrap no longer accept a production capture
  callback. The unified focused matrix completed 341 tests with 9 Linux-only
  skips and 2 local UDS cases deselected. Independent Sol/xhigh review reports
  PASS with no P0/P1/P2. The new real Linux native case awaits exact-head CI;
  28 broader local UDS cases remain unverified after `PermissionError` during
  socket setup.
- First bounded-redraw head `adf44fc0...` reached the real Linux native capture
  assertion and completed 72 native cases, but the 73rd failed only in test
  teardown: the test explicitly killed the tmux server and then called a helper
  that requires its socket to remain present. The local follow-up removes that
  contradictory post-kill assertion; implementation capture evidence passed in
  the failed run. A fresh exact-head result is still required.
- Bounded-redraw follow-up `f37f92d9...` completed 20/20 exact-head checks.
  Linux native completed 73 cases, including held-FD real tmux capture; Backend
  Python 3.11 completed 3629 passed/44 skipped, and the 3.12/3.13 matrix also
  completed successfully. The bounded-redraw slice is verified; the next rc6
  scope is `WAWRuntimeApplication` production composition.
- The current `WAWRuntimeApplication` slice is uncommitted. Typed Runtime
  key/executor providers and activated sockets transfer through distinct one-shot
  owners; shared start/close tasks compose stream, gated control, gated legacy and
  one final application-gate commit. Partial production builders are private and
  weak-map provenance is replaced by an unforgeable one-use binding. Incomplete
  construction exposes a typed, reachable cleanup owner for retry. Shutdown
  evidence keeps the provider until stream/control/lifecycle/legacy are all clean.
  No production main, real key/provider or host is enabled. Independent Sol/xhigh
  review reports PASS with no P0/P1/P2; Linux-target mypy covers 260 sources.
- `WAWRuntimeApplication` head `628e9c00...` completed 20/20 exact-head checks,
  including Linux native, E2E and Backend Python 3.11/3.12/3.13. This top-level
  Runtime ownership slice is verified. API singleton/lifespan ownership is the
  next rc6 scope; production main and real key/provider activation remain closed.
- The uncommitted API-singleton continuation adds `AttachmentAuthority.begin_shutdown()`.
  Pending tickets are burned; active and staged records retain exact cleanup/Audit
  obligations through `invalidate_all()`. New admission operations fail after
  shutdown, while exact positive cleanup remains admissible. Focused tests completed
  66 cases and independent Sol/xhigh review reports PASS with no P0/P1/P2.
- The same continuation now gives `WAWRuntimeBindCoordinator` and
  `WAWControlClient` strict shutdown evidence. Retained/candidate pidfd close
  failures are sticky, never retry an old FD number, invalidate bind state and
  permanently prevent false-clean. Independent Sol/xhigh review is PASS.
