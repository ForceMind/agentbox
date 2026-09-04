# WAW inert package assets

These files are static R10 packaging inputs. They establish neither a host
installation nor a running interactive process. The artifact contains source
templates only: it does not contain a native helper binary, compiler toolchain,
vendor executable, vendor account, extension identity, credential, key, or
enrollment record.

The R12 host procedure must create the canonical public-manifest bundle and
pin the exact bytes used for `tmux.conf`, the sandbox-policy bundle, and each
managed policy. Runtime accepts only those separately installed, digest-pinned
bytes. It never reads this resource tree as a deployment authority.

`claude/managed-settings.json` and the two `codex/*.toml` files are deliberately
minimal policy templates. They do not configure a server path, account,
telemetry endpoint, update channel, Secret, or Provider integration. R11
integration and R12 host qualification decide whether a supported vendor build
can consume the templates and record its resulting digests.
