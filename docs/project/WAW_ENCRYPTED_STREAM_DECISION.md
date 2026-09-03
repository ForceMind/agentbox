# WAW encrypted stream byte encoding decision

Status: **PROPOSED — application profile implementation awaits Owner decision**.
This supplements the existing WAW architecture; it does not change its historical
approval state. Fixed Noise NX core implementation and interoperability tests may
continue independently on macOS.

## Concrete gap

The existing [architecture](../../WEB_AGENT_WORKSPACE_ARCHITECTURE_AUTHORIZATION_REVIEW.md)
fixes Noise revision 34, the HandshakeContext fields, 44-byte AWCE header and
counter behavior. It does not specify the literal `protocol_id`, the exact
`transcript_context_hash` construction, or direction-label bytes/AAD concatenation.
Two correct independent implementations could therefore fail to interoperate.
The independent read-only review confirmed this gap.

## Proposed frozen bytes

| Item | Proposed value |
| --- | --- |
| HandshakeContext `protocol_id` | ASCII JSON string `agentbox-waw/v1` |
| Context encoding | Existing exact field set, RFC 8785 canonical UTF-8; all uint64 fields are canonical decimal strings; `crypto_envelope_version` is JSON number `1` |
| Noise prologue | Those complete canonical HandshakeContext bytes, established before message 1 |
| `transcript_context_hash` | The exact 32-byte final Noise handshake hash `h`, after message 2 and its challenge payload; no additional hash or concatenation |
| Browser-to-Runtime direction label | ASCII `browser-to-runtime`, without NUL or length prefix |
| Runtime-to-browser direction label | ASCII `runtime-to-browser`, without NUL or length prefix |
| AWCE associated data | `header_44_bytes || transcript_context_hash_32_bytes || direction_label_bytes`, in exactly that order |
| KEY_CONFIRM / KEY_CONFIRM_ACK associated data | Empty bytes, using the standard Noise transport operation; their existing exact plaintext formulas remain unchanged |

The final Noise `h` already binds the protocol name, complete prologue and both
exact handshake messages through Noise's `MixHash` rules. The fixed-size header
and hash make the AAD concatenation unambiguous; the direction label must match
the existing direction byte. Outer ABWS/WebSocket hop headers remain excluded.
See [Noise revision 34 processing rules](https://noiseprotocol.org/noise.html#processing-rules)
and [channel binding](https://noiseprotocol.org/noise.html#channel-binding).

This proposal keeps KEY_CONFIRM and KEY_CONFIRM_ACK at their separate direction
counters `n=0`; application INPUT/OUTPUT start at `n=1`. It does not approve a
manual nonce, key export, counter skip, alternate Noise pattern or plaintext
fallback. All existing pin trust, admission and cleanup gates remain required.

## Implementation after the decision

1. Add strict shared context/envelope codecs and fixed proposed-byte vectors;
   implement Python/WebCrypto confirmation and AWCE over the reviewed core.
2. Connect the Runtime encrypted stream to its exact supervisor after the
   existing staged admission/commit protocol; keep prepare distinct from a writer.
3. Implement API authentication/Origin/session fencing and ciphertext-only relay;
   keep terminal bytes and channel keys out of API/Worker logging and storage.
4. Connect browser crypto and terminal controls only after pin verification and
   successful admission; test failure, disconnect, reconnect and exact Stop.
5. Complete independent security review, Python/Node interoperability, relevant
   local tests and exact-head Linux CI; update GitHub and documents per stage.

Every context field, header byte, cursor, direction, tag and sequence mutation
must fail closed. Tests must prove fresh-key reconnect, no replay after key
failure, no writer before commit, no successful admission after state drift,
no API plaintext, and positive cleanup before slot reuse. Supported-browser
capabilities and real Linux host/PTY/CLI behavior still need their own evidence.

## Requested decision and limits

Approve the frozen bytes above for software implementation and testing, or
provide replacement exact bytes/formulas. This is an architecture contract
clarification under [GOVERNANCE.md](GOVERNANCE.md) Owner Gates. It does not authorize
real host activation, reading or rotating a production private key, Provider
Secret handling, publication or production support claims.
