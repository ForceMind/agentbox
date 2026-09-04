# Fixed WAW interactive process

Status: R10 exact-head verified software candidate. It contains the fixed process/profile,
descriptor, native helper, Runtime transport, probe/conflict and inert packaging
implementation. It does not state that a host has installed a manifest or run a
real Claude/Codex build.

## Implemented software boundary

- Runtime host manifest v2 cross-pins the exact-six executable inventory,
  exact-two Claude/Codex profiles, Project/cgroup records, tmux, sandbox/socket
  policy, Claude policy and the canonical Codex two-file policy bundle. The
  production entry loads only the descriptor-verified filesystem v2 bundle;
  v1/raw/loaded constructors remain explicitly test/compatibility-only.
- One-shot executable launch handles originate from the descriptor-held pinned
  inventory. The production factory also binds Project, selected vendor
  HOME/TMP/policy and delegated cgroup handles to the same issued v2 authority.
- The fixed 64-byte WBR codec, launch descriptor and seven-role `SCM_RIGHTS`
  protocol reject missing, extra, replayed or truncated data and close received
  descriptors on failure.
- Three Linux C17 helpers implement pane bootstrap, PTY bridge and attach
  supervisor with held-FD execution, exact READY, tmux checks, namespace/UID/PID1
  isolation, descriptor mounts, private proc, Landlock/seccomp, bounded relay
  and child reaping.
- `WAWFixedTransport` connects that chain to the supervisor and encrypted stream:
  attach starts only at admission commit, output chunks are at most 32 KiB,
  resize requires PTY+WBR evidence, cleanup retains exact handles across failed
  retries, and Stop uses cgroup freeze/kill/wait-empty proof.
- Fresh version-bound auth evidence is required before spawn and same-generation
  login resume. LOGIN/TRUST remains local-TTY only. One host-wide conflict
  coordinator linearizes WAW and legacy Claude/Codex starts without adoption.

The interactive workspace argv remains empty for both vendors because the
documented interactive entry is the executable itself. The older proposal's
generic trailing `--` is not added without exact supported-build evidence; R12
must verify the selected vendor argv behavior.

## Inert packaged policies

R10 packages a closed set of inert templates under
`agentbox_runtime/assets/waw-inert/`:

- `tmux.conf` limits the tmux status surface and scrollback template;
- `exit-empty=on` makes the per-workspace tmux server terminate when its sole
  fixed session ends; after cgroup `populated=0`, Runtime removes tmux 3.2a's
  stale socket only when a dirfd-relative read-back still matches the recorded
  `(device,inode,type,uid)` identity;
- Start records that identity before pane acceptance; any later failed Start
  empties the cgroup and uses the same cleanup, while an unrecorded pathname or
  identity drift requires reconciliation instead of blind deletion;
- Runtime treats the tmux pane/bootstrap as an observed non-child: pidfd
  readiness proves exit, while `exit_code` remains unknown. Only Runtime's
  direct launcher and attach-supervisor children are reaped with `waitid`;
- `sandbox-policies.v1.json` carries the `waw-sandbox-policies-v1` template
  schema and `interactive-sandbox-v1` profile identifier;
- `claude/managed-settings.json` disables prompt-history retention through its
  documented environment setting;
- `codex/requirements.toml` carries the reviewed R10 managed requirements;
- `codex/managed_config.toml` carries managed defaults for retention, analytics,
  feedback and OpenTelemetry; and
- `codex/policy-bundle.v1.json` is canonical RFC 8785 JSON that pins the exact
  byte digests of those two TOML files in fixed order.

The package includes every template as Python package data. The release artifact
also includes `native/waw` source plus `scripts/build-waw-native.py` and
`scripts/check-waw-native.py`. Those inputs make later work reviewable. The
candidate does not contain or claim a production native helper binary, compiler
toolchain, vendor executable, vendor identity, account, extension identity,
credential, Secret, key, endpoint, or enrollment record.

## Fixed policy and digest contract

The process-profile codec remains the authority for fixed profile names,
managed-policy destination names, supported AgentTypes and the closed fields it
accepts. Runtime host-manifest v2 cross-pinning calculates SHA-256 over every
canonical public-bundle member. The Claude profile's `managed_policy_digest`
pins `claude-managed-policy.v1.json`; the Codex profile's digest pins
`codex-managed-policy.v1.json`. Before it accepts that Codex bundle, Runtime
also verifies its exact-two `requirements.toml` and `managed_config.toml`
entries against the separately pinned TOML bytes. Every mismatch fails closed
before execution.

The packaged files are not that installed authority. R12 must select the
supported vendor configuration representation, write the canonical public
bundle, calculate the final digests, and bind them into the installation-owned
manifest. Runtime reads that bundle by descriptor and does not repair, replace,
or load a template from its installed Python package at runtime.

## Codex managed policy location and precedence

For supported Unix Codex clients, the documented system requirements location is
`/etc/codex/requirements.toml`. R10 ships a source template only and does not
write that location. The official precedence order, from lower to higher, is
the system requirements file, a cloud-delivered enterprise requirement bundle,
legacy `managed_config.toml` fields reinterpreted as requirements, and a macOS
MDM requirements payload. Normal scalar/list replacement, table merge and
field-specific requirement composition do not share one generic merge rule.

R12 must confirm the supported vendor build, actual placement, effective
precedence and every selected key before activation. In particular, the source
template cannot prove that a cloud or MDM layer did not override its settings.
The relevant official references are [managed
configuration](https://learn.chatgpt.com/docs/enterprise/managed-configuration)
and the [Codex configuration
reference](https://learn.chatgpt.com/docs/config-file/config-reference).

The templates contain no credential, endpoint, key, token, vendor identity or
caller-controlled/free-form executable path. The only executable path is the
fixed fail-closed `/bin/false` sentinel in `tmux.conf`.
The hardened tmux template removes prefix/root/copy key tables, command/new-
window/respawn paths, passthrough and clipboard, fixes `/bin/false` as the
default shell/command and bounds history to 25 lines. Codex requirements disable
login shell, remote control, unmanaged hooks, feedback and browser/plugin/memory/
update surfaces; managed defaults disable history persistence, analytics,
feedback and all three OpenTelemetry exporters. R12 must still verify the exact
vendor build and effective policy.

## Stage boundary

| Stage | Evidence supplied | Evidence still required |
| --- | --- | --- |
| R10 software | v2 authority, fixed native/Runtime process chain, bounded probes/conflicts, closed templates, tests and release inventories; PR #79 implementation head passed Linux exact-head CI | Final documentation-head CI, merge/read-back; CI remains software evidence, not installed-host evidence |
| R11 integration | Browser/API controller composition, full failure injection, artifact and operational checks | No real-host qualification by synthetic tests |
| R12 host | Authorized host installation, actual vendor/PTY/isolation/recovery evidence and canonical manifest pins | Production/support claim only after the applicable acceptance record |

R10 creates no systemd unit or socket and does not alter installer `UNIT_NAMES`,
`apply`, `start`, or activation paths. Existing Web Agent Workspace copy remains
document-fixed browser selection: only `navigator.languages[0]` is read, primary
`zh` maps to `zh-CN`, and every other/missing/malformed value maps to English.
Technical identifiers remain English; full cross-page bilingual migration remains
an R11 task.

Descriptor directory mounts use non-recursive rootless `MS_BIND` inside U1, so
nested source mounts are not imported into the isolated view. Linux
`mount_setattr` then only adds `NOSUID|NODEV` and policy `RDONLY`. U2 remains
blocked until every mount is installed and U1 has completed its NNP, capability
clear, and seccomp lockdown, so the vendor cannot observe the trusted setup
window. Missing Linux 5.12+ syscall/UAPI support fails closed and is an R12 host
gate.
The held directory FD remains the authority across namespace creation. Before
creating the mount namespace, U1 reads the kernel-generated absolute FD target
only as a lookup hint and rejects truncation, non-absolute results, and deleted
targets. Inside the new mount namespace, `openat2` reopens that hint beneath the
current root with `RESOLVE_IN_ROOT|RESOLVE_NO_MAGICLINKS`. The reopened directory
must exactly match the authority FD's device, inode, type/mode, visible owner,
and filesystem mount flags before it may be bound. A rename, replacement,
or alias only succeeds when lookup still reaches the same verified object with
the same visible owner and reported mount flags. A changed object or reported
flag, or unsupported `openat2`, fails closed; the reopened FD pins the verified
object through the bind.
R12 must also prove these four source directories contain no nested mounts, or
audit both the nested mount and the underlying directory that a non-recursive
clone exposes. The setup owns each fixed target before the vendor starts.
The R12 host contract additionally rejects idmapped source mounts and audits
source mount topology plus per-mount security metadata not exposed by
`fstatvfs`, including LSM and `nosymfollow` policy.

The rootless setup uses two user namespaces. A short-lived U1 maps namespace
UID/GID 0 to the non-root Runtime identity and owns mount/PID/IPC setup. PID1
then creates U2, where UID/GID 1000 maps to U1's 0. U2 clears all capabilities
with exact read-back before Landlock/seccomp and bridge exec. The saved host
`/proc` descriptor remains only in the fixed U1 map/wait/reap process.

The bridge configures its outer tmux pane terminal as raw before READY. After
the vendor and namespace descendants exit, the inner PTY reaches EOF, and the
bridge's final output buffer is empty, the bridge generates a 192-bit challenge
as 64 random columns in the fixed protocol-safe range `1..8` on row 1, resets
origin/margins, and sends each `CUP + DSR 6` pair as one ordered byte stream. It exits
only after tmux returns the exact random coordinate
sequence within one monotonic second. Because the challenge is generated after
vendor exit, delayed vendor queries cannot satisfy it; an incomplete terminal
sequence that prevents tmux from parsing the challenge, including incomplete
DCS handler/escape state, yields the fixed fail-closed system status instead of
a false success. R11 must quiesce the single browser INPUT writer and WBR resize
path during this final handshake so user input cannot imitate the random
responses or consume the one-second acknowledgment window; it must also keep
the outer pane at the protocol minimum of at least eight columns and one row.
The response scanner uses a prefix table, so delayed vendor DSR replies that
overlap the beginning of the random sequence cannot hide the real response.
Namespace descendants are reaped before entropy generation and the parser
challenge is the only successful relay-loop exit.

## Validation

`tests/unit/test_release_candidate.py` verifies the core/Python/npm version
forms, Runtime package-data list, all seven static assets, sandbox schema, Claude
JSON, the Codex TOML values and canonical exact-two policy bundle, release
documentation inventory, plus the exact native source/script inventory. The
artifact scanner rejects a missing or unexpected native source, build script or
WAW wheel asset. The backend native job builds hardened PIE/RELRO/NOW helpers
and runs the Linux tmux/PTY/namespace/cgroup/relay matrix in normal and sanitizer
modes. Passing that job is not production binary provenance or host activation.

PR #79 implementation head
`6083e6e1aa118b19b548a9070b7e49558988f7e5` completed all 20 exact-head checks.
The Python 3.13 matrix reported `3428 passed / 43 skipped`; the Linux native job
reported `66 passed` in normal mode and `24 passed` with sanitizers. Web reported
`915` tests, the browser-trust extension `6`, Chromium E2E `64`, release
validation `143`, and the documentation link check `238`. Independent Sol review
reported no remaining P0/P1/P2 in this software scope. A later documentation-only
head must complete its own CI before merge, and none of these counts qualifies a
real vendor CLI, account, CRX installation, native binary provenance or host.
