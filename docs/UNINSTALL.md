# AgentBox Uninstall

Status: Phase 8 limited implementation, pending human review

`agentbox system uninstall` first verifies current/receipt identity, every
retained release, every present managed unit, and the tmpfiles policy. Only
after that complete preflight does it stop/disable exact AgentBox units and
remove verified program assets. It then reloads systemd and marks the receipt
as data-preserved.

The default and only Phase 8 behavior preserves:

- `/var/lib/agentbox`, the DB, administrator, backups, and lifecycle records;
- `/etc/agentbox` and the application secret;
- `/srv/agentbox/projects`;
- `/home/agentbox-runtime` and all third-party Runtime authentication;
- system identities.

It also never touches existing root Codex/Claude/tmux/gh state. `--purge` is
explicitly unavailable in Phase 8 because safe destructive ownership and
recovery semantics require separate human-approved design. Do not manually
`rm -rf` Project Root as an uninstall substitute.

If a unit or release no longer matches its verified AgentBox identity,
uninstall reports the collision before stopping services or deleting anything.
