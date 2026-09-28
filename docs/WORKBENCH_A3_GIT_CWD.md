# A3 Git child cwd foundation

Status: rc19 software candidate, 2026-09-29. This is an internal process
primitive under the [A3 patch contract](WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md),
not a Runtime action or content admission.

`ControlledProcessRunner.run_with_cwd_fd` accepts a fixed executable/argv
selected by Runtime code and one already-held Project directory descriptor.
Only Linux with `/proc/self/fd` is admitted. It duplicates the descriptor,
checks directory type, current Runtime ownership, unsafe write bits and exact
named path identity, then passes that duplicate alone to the child and uses
its `/proc/self/fd/<n>` path as cwd. The duplicate stays held through the
whole bounded subprocess operation and is closed on every result. The named
path is checked again before stdout can be returned; a replacement discards
the result with a fixed conflict code. The ordinary process-runner path is
unchanged and shares its limits, cancellation and exact child cleanup.

This closes only the cwd name-swap portion of the future reader. A caller
must still obtain the descriptor from a current, descriptor-verified formal
Project binding. The existing rc17 content-root class does not export its
descriptor or call this runner. Git object/pack and index provenance,
alternates, config, symlinked work files, snapshot consistency, fixed diff
argv, sensitive-path policy and encrypted delivery remain independent gates.
No caller may infer permission to read arbitrary files from an fd or a
successful subprocess return.

Local macOS tests verify the unchanged ordinary runner and the explicit
non-Linux refusal. Linux CI must execute the positive inherited-fd, wrong
named directory and name-swap tests before this primitive is merged. The
positive native tests do not by themselves qualify a real host or expose
patch content.
