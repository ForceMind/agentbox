# R12-C3-b production Runtime composition closure

Status: implementation analysis and in-progress software work, 2026-09-28.
The accepted [R12 plan](project/PRODUCTION_READINESS_PLAN.md) governs scope.
This document records the remaining construction dependencies; it is not a
host receipt or permission to operate a real key, CLI credential, or Project.

## Observed first difference

Current `server.py::_main` still instantiates `RuntimeExecutorServer` directly.
The available filesystem-v2 application builder consumes activated control
and stream sockets, a Runtime-only static key, an epoch store, and one
`WAWRuntimeExecutorProvider`. A C3-b provider candidate now exists in an
isolated branch, but it does not yet make that production graph reachable
from `_main`.

The initial provider candidate had two concrete failures before launch:

1. It passed a subclass of `WAWVendorProbeRunner` to
   `WAWProductionAuthOwner`, whose constructor requires the exact runner type.
   The fallback runner was synthetic. The local repair creates a native-only
   unbound owner, seals the native probe factory exactly once, and rejects a
   plain probe on that path. It never constructs a synthetic runner in the
   production provider.
2. It treated `/run/agentbox-waw/auth-probe` as Runtime-owned scratch, though
   the native helper requires that path to be a root-owned 0755 mount anchor.
   The Runtime-owned source is `/run/agentbox-waw/tmp` (0755), with a 0700
   workspace/generation scratch child. The provider now uses that source,
   releases temporary descriptors, and retains lower owners if native process
   cleanup is uncertain. The installed `tmux.conf` is root-owned, not owned
   by the Runtime UID.

The focused auth owner/provider/resource tests pass locally, but they do not exercise
the full production application or target Linux host. A wider macOS suite had
187 passed, 9 platform skips, and six AF_UNIX path/permission failures; those
are not a Linux qualification result and no assertion was relaxed.

## Authority-deferred resource foundation

The current builder calls
`create_waw_lifecycle_registry_from_filesystem_bundle`, which loads and
cross-pins the v2 manifest, then issues the unique
`WAWVerifiedExecutionAuthority` inside the composition. The first provider
constructor required a `WAWVerifiedLaunchHandleFactory` already bound to
that same authority, six verified launch handles and the cgroup root.
Constructing it before the builder could not satisfy an object-identity
pin to an authority issued only inside the builder. Reloading the manifest
and issuing a second authority is not equivalent.

The current software candidate makes `take()` return a distinct application
owner. Its `create_executor` opens resources only after the builder passes
the unique authority. The fixed resource builder uses that exact manifest
for six executable handles, verifies nine installed directory/policy roles
and the cgroup delegation, then transfers the bundle to the internal
provider once. It accepts no request path/argv/env or second authority.
Tests cover ordering, partial descriptor failure, cross-authority rejection,
Project-root drift and sticky close uncertainty.

This closes the **software construction ordering** mismatch. It does not
yet prove full application start or Runtime main. Partial construction
cleanup failure remains an explicit error before epoch/stream publication.

## Dynamic Project binding

The lifecycle registry replays and registers Project bindings after the
executor is constructed. A frozen binding map passed into the provider at
startup therefore cannot authorize Projects added later. The Runtime
executor already validates a binding and resolves its registered Project
before invoking the command/transport factories. The local provider repair
uses that exact resolved command Project and revalidates its immediate child
under `ProjectRegistry` before the fixed launch handle factory consumes the
relative key. It refuses mismatched formal Project/Workspace IDs. The next
composed test must register a Project after startup, start it, rotate/revoke
its binding, and prove stale identities fail without a duplicate map.

The next software candidate also exposes `relative_key_for_formal_project`
and `managed_conflict_states` from that same executor. They read the live
binding/supervisor maps under the existing lock, observe supervisor state
outside the map lock to avoid lock inversion, and recheck map identity before
returning. Binding changes, inflight work or restart quarantine block legacy
starts. This closes only the WAW side of the bidirectional conflict probe;
the bounded, fresh legacy Claude/Codex state source and one-shot production
probe binding still need implementation and actual application tests. For a
formal Project lacking a current binding, the snapshot returns `UNKNOWN`;
host-wide empty state is not authoritative until the future application
composition has completed binding/restart inventory replay and opened its
startup gate.

## Production entrypoint sequence

1. The installer supplies fixed root-owned v2 manifest/public resources,
   exact Runtime UID/GID and directory modes, two systemd WAW sockets in FD
   3/4 with unique fixed names mapped to control/stream paths (cross-unit
   order is not authoritative), Runtime-only static X25519 material, one epoch store, and
   externally enrolled vendor version/digest inputs. Missing inputs stay
   `NOT RUN` for a target and fail closed in production code.
2. `_main` chooses the installed production profile only through its fixed
   trusted source. It validates the two inherited socket identities before
   `take()`, then constructs the key, epoch store and sealed executor provider
   without reading Provider Secret material in API/Worker or Root Helper.
3. The application builder issues one v2 authority, binds key/provider to
   that same object, consumes exactly one epoch, and publishes one legacy,
   control and encrypted stream graph. It does not fall back to the old
   `RuntimeExecutorServer` or a synthetic WAW implementation on failure.
4. Start/serve/close order follows `WAWRuntimeApplication` ownership.
   Startup failure, caller cancellation, active Stop, shutdown and restart
   must report whether stream, control, native process, key and provider
   resources are clean. Residue or uncertain cleanup blocks admission and
   re-creation under the same owner.

The current installer does not yet provision every production WAW path,
socket, native binary and enrollment input. That is R12-D/G work. This
software slice may be composed against controlled fixtures but must not be
described as usable on a real host before those stages are complete.

## Required evidence before C3-b closure

- Focused tests for the authority issue/order, one-shot takes, key pin before
  executor/epoch effect, late Project registration, auth cache/lease path,
  vendor/home/profile mismatch, close and cancellation at each partial stage.
- Failure injection for missing/reordered/wrong-owner sockets, manifest and
  installed policy/key drift, epoch store mismatch, second Runtime/API owner,
  live process on close, FD reuse and incomplete native cleanup.
- R11 legacy management behavior and WAW exclusion remain intact; no
  Browser → shell/filesystem/Runtime process path is added.
- Linux normal and sanitizer CI, independent security/architecture/test review
  where required, normal merge, exact merge read-back, then separate R12
  installer/client/host qualification. Current Mac unit passes do not close
  these checks.

## Current local state and continuation

The original checkout remains on `codex/r12-runtime-production`, forked from
`a696193fec127595b1beafb1ed1cabf2ae58efa9`, with uncommitted provider/test
and planning WIP plus `.reasonix/` and `build/`. Five relevant files were
copied byte-for-byte into the managed worktree on
`codex/r12-c3b-resource-factory` from latest main
`986e8fa87c6d14030677c026342813c6921cc6f9`; hashes matched at transfer.
The deferred resource implementation exists only on the managed branch.
Preserve the original checkout and do not claim this slice activates production.

Next: connect the deferred provider to the fixed `_main` branch, prove late
Project registration through the actual application, and supply installer-owned
socket/key/epoch/enrollment inputs. CI/merge of this resource foundation must
be read back separately from R12-D/G/H host evidence.
