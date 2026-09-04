# Managed browser trust client

This client is the independent authority for public WAW root/pin records. The
server Web/API/Runtime cannot install records, reset revision floors, choose the
trusted clock or impersonate provider invalidation.

The ordinary source build produces an externally inert MV3 extension. A
deployment bundle is generated only when an operator supplies the reviewed CRX
public key and matching extension ID, exact HTTPS Origin/update URL, enrolled
`trustd` installation fingerprint and bounded browser-client UIDs. Private
signing keys, browser profiles, provider credentials and terminal data never
enter this repository or bundle.

Production qualification remains limited to the exact managed Chrome/Linux
tuple recorded by R12. Unpacked extensions and the synthetic test provider do
not enable production Connect.
