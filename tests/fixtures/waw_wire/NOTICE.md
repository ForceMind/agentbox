# WAW wire interop fixtures

`interop-cases.json` is hand-authored, public synthetic metadata for the R5
Python/TypeScript codec interoperability check.  It lists every allowed
direction/frame-type profile once; payloads are constructed by the bounded
checker from the fixed public values in that check.  It contains no keys,
credentials, tickets, capabilities, live host identifiers, or terminal data.
