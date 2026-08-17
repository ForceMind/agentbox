"""Fixed local maintenance entry point for empty Secret Store initialization."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from agentbox_runtime.secret_store import RuntimeSecretStore
from agentbox_runtime.secret_store_models import SecretStoreInitializeResult


def main(
    argv: Sequence[str] | None = None,
    *,
    _store: RuntimeSecretStore | None = None,
) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if arguments != ("initialize",):
        # Never echo rejected arguments: an attempted Secret value must not reach stderr.
        sys.stderr.write("SECRET_STORE_INVALID_ARGUMENTS\n")
        raise SystemExit(2)
    result = (_store or RuntimeSecretStore()).initialize()
    sys.stdout.write(f"{result.value}\n")
    return (
        0
        if result
        in {
            SecretStoreInitializeResult.INITIALIZED,
            SecretStoreInitializeResult.ALREADY_INITIALIZED,
        }
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
