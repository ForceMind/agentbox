"""One bounded public-fixture exchange for the A3 codec interop command."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages/agentbox-protocol/src"))

from agentbox_protocol.a3_content import (  # noqa: E402
    ContentError,
    ContentRead,
    application_aad,
    context_bytes,
    decode_message,
    encode_message,
    prepare_pages,
)


def main() -> None:
    raw = sys.stdin.buffer.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("test input exceeds budget")
    value = json.loads(raw)
    context = value["context"]
    patch = bytes.fromhex(value["patch_hex"])
    pages = prepare_pages(context, patch, value["observed_at_ms"])
    read = ContentRead(context, now_ms=0, deadline_ms=30_000)
    observed = None
    for encoded in value["messages_hex"]:
        message = bytes.fromhex(encoded)
        assert encode_message(decode_message(message)) == message
        observed = read.accept(message, now_ms=1, current_context=context)
    assert observed == patch
    rejected = 0
    for invalid in value["invalid_messages"]:
        try:
            decode_message(invalid.encode())
        except ContentError:
            rejected += 1
        else:
            raise AssertionError("negative fixture accepted")
    print(
        json.dumps(
            {
                "context_hex": context_bytes(context).hex(),
                "pages_hex": [page.hex() for page in pages],
                "aad_hex": application_aad(context, "8" * 64, "PATCH_PAGE", 0).hex(),
                "rejected": rejected,
            }
        )
    )


if __name__ == "__main__":
    main()
