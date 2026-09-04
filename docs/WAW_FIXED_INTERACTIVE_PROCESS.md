# Fixed WAW interactive process

Status: R10 software candidate. It contains the fixed process/profile,
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
| R10 software | v2 authority, fixed native/Runtime process chain, bounded probes/conflicts, closed templates, tests and release inventories | Linux exact-head CI remains software evidence, not installed-host evidence |
| R11 integration | Browser/API controller composition, full failure injection, artifact and operational checks | No real-host qualification by synthetic tests |
| R12 host | Authorized host installation, actual vendor/PTY/isolation/recovery evidence and canonical manifest pins | Production/support claim only after the applicable acceptance record |

R10 creates no systemd unit or socket and does not alter installer `UNIT_NAMES`,
`apply`, `start`, or activation paths. Existing Web Agent Workspace copy remains
document-fixed browser selection: only `navigator.languages[0]` is read, primary
`zh` maps to `zh-CN`, and every other/missing/malformed value maps to English.
Technical identifiers remain English; full cross-page bilingual migration remains
an R11 task.

Descriptor directory mounts use non-recursive `open_tree` clones: nested source
mounts are not imported into the isolated view. Linux `mount_setattr` only adds
`NOSUID|NODEV` and policy `RDONLY`; `move_mount` attaches the already-restricted
clone without a path reparse or less-restricted window. Missing Linux 5.12+
syscall/UAPI support fails closed and is an R12 host gate.
R12 must also prove these four source directories contain no nested mounts, or
audit both the nested mount and the underlying directory that a non-recursive
clone exposes. The setup owns each fixed target before the vendor starts.

## Validation

`tests/unit/test_release_candidate.py` verifies the core/Python/npm version
forms, Runtime package-data list, all seven static assets, sandbox schema, Claude
JSON, the Codex TOML values and canonical exact-two policy bundle, release
documentation inventory, plus the exact native source/script inventory. The
artifact scanner rejects a missing or unexpected native source, build script or
WAW wheel asset. The backend native job builds hardened PIE/RELRO/NOW helpers
and runs the Linux tmux/PTY/namespace/cgroup/relay matrix in normal and sanitizer
modes. Passing that job is not production binary provenance or host activation.
