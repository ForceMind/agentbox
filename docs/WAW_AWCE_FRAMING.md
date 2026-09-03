# Opaque AWCE v1 framing

This software increment implements the existing binary envelope layout in Python
and TypeScript. It validates framing metadata and transports opaque bytes. It
does not encrypt, authenticate a sender, verify a tag or transcript, derive an
AAD/context identifier, admit a terminal, or activate any socket or CLI.

The application profile remains a separate
[proposed decision](project/WAW_ENCRYPTED_STREAM_DECISION.md). The historical
[architecture](../WEB_AGENT_WORKSPACE_ARCHITECTURE_AUTHORIZATION_REVIEW.md) remains
the source for the fixed header. The current delivery state is in
[CURRENT_STATE](project/CURRENT_STATE.md) and [REMAINING_PLAN](project/REMAINING_PLAN.md).

## Exact representation

| Offset | Bytes | Field and accepted value |
| --- | --- | --- |
| 0 | 4 | ASCII `AWCE` |
| 4 | 1 | `crypto_envelope_version = 1` |
| 5 | 1 | `direction_id`: input `1`, output `2` |
| 6 | 2 | `flags = 0` |
| 8 | 8 | Big-endian `crypto_sequence`: `1..2^64-2` |
| 16 | 8 | Big-endian `stream_cursor`: input `0`, output `1..2^64-2` |
| 24 | 4 | Big-endian `ciphertext_length`: `17..49168` |
| 28 | 16 | Opaque `context_id` |
| 44 | variable | Exact opaque ciphertext, including the 16-byte tag |

An envelope is exactly `44 + ciphertext_length` bytes (61..49212). Truncated or
trailing bytes, unsupported versions/directions/flags, reserved counters and
wrong cursor/length types are rejected. Sequence zero belongs to the separate
confirmation exchange; `2^64-1` is reserved. Python rejects booleans as integers;
TypeScript requires `bigint` for both 64-bit fields to avoid Number rounding.

The framing maximum is generic. Enforcing active input/output chunk limits,
expected direction/context, monotonic sequence and tag validity belongs to the
future application/session layer. A successful decode is not authentication.

## APIs and ownership

- Python: `agentbox_protocol.awce.AWCEEnvelope`, `encode_awce_header`,
  `encode_awce`, `decode_awce` and bounded framing exceptions.
- Web: `features/workspace/awce.ts`, `AWCEEnvelope`, `encodeAwceHeader`,
  `encodeAwce`, `decodeAwce` and equivalent framing exceptions.

The header builders accept metadata plus the known ciphertext length and return
exactly 44 bytes. Future encryption can obtain the header before ciphertext
exists, without dummy payload allocation. Full encoders use the same builder.
Caller input/output buffers cannot mutate a stored envelope; metadata is
immutable and representations omit opaque context/ciphertext bytes.

## Verification and remaining integration

- `tests/unit/test_awce.py`: 44 cases passed on the local Mac, including exact
  header/envelope vectors, high-bit counters, bounds and buffer ownership.
- `apps/web/src/features/workspace/awce.test.ts`: 38 cases passed, including
  values beyond `2^53`, offset views, malformed types and alias isolation.
- `AGENTBOX_AWCE_TEST_PYTHON="$PWD/.venv/bin/python" node scripts/check-awce-interop.mjs`:
  passed with an independent literal and Python/TypeScript encode/decode in both
  directions, minimum/maximum bodies and malformed framing. Only synthetic
  opaque bytes traverse bounded captured child pipes; reports omit payloads.
- Independent sol read-only review passed for the codec and pre-encryption
  header helpers. The Frontend CI workflow runs the interop check on Node 22 /
  Python 3.13; exact-head status is recorded separately in CURRENT_STATE.

No visible UI changes were made, so visual QA is not applicable to this slice.
Application cryptography, admission, ciphertext relay and real terminal testing
remain R4–R12 work; none is implied by these framing tests.
