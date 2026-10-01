# ADR 0010: first-deployment cross-platform Web trust bootstrap

Status: **Accepted for software implementation — Owner selected the recommended
HTTPS Web profile on 2026-09-30. Production claims still require the evidence below**.
Scope: first self-deployed AgentBox version for PC and phone browsers.

## Problem and approved product target

Owner selected PC/phone browsers as the first deployable clients, with native
desktop/iOS/Android Apps kept on the later full-capability roadmap. The current
R9 contract requires managed MV3/Native Messaging/trustd and explicitly has no
ordinary-page fallback. That desktop path cannot establish phone-browser
support. Responsive layout alone does not solve it.

The proposal below changes the client trust bootstrap model. It does not relax
Runtime/Secret/process authority or add a generic command/filesystem interface.
The desktop managed provider remains a separate stronger profile; its contract
must not be silently relabeled as equivalent to the proposed Web profile.

## Proposed first-deployment model

1. The installer provisions a canonical HTTPS Origin and a separately managed,
   root-owned static Web release and public bootstrap. The API/Worker account
   has no write authority over those assets, proxy configuration or bootstrap.
   The installer prints the Origin and server identity/fingerprint for the
   operator's out-of-band comparison.
2. Static HTML/JS/public bootstrap are served independently of the API process.
   Production is HTTPS-only. CSP and immutable asset/hash policy prohibit API
   responses, uploaded/project content and third-party code becoming executable
   client code. API responses remain data-only, with exact Origin/CSRF rules;
   no arbitrary proxy target is introduced.
3. The public bootstrap contains only versioned public identity/policy:
   canonical Origin, host ID/revision, Runtime attestation fingerprint,
   deployment/build identity and supported protocol. No Runtime HOME,
   private key, Provider Secret, login token or terminal content is present.
   Its exact format and publication/update transaction are frozen before
   implementation and fail closed on unknown/missing fields.
4. A dedicated Web trust-provider profile validates that bootstrap and exposes
   the same bounded public snapshot needed by Noise/AWCE. A missing,
   contradictory or stale observation closes Connect; there is no plaintext
   terminal fallback. Runtime continues checking the complete bound identity,
   generation/epoch, single-use admission, current permissions and exact Stop.
5. Official Claude/Codex login and credential storage stay Runtime-local.
   Web/API/Worker only relay admitted ciphertext and typed metadata.
   Root Helper gains no Secret authority and does not enter the terminal path.

## Explicit change in security assumptions

### First-release public wire format and client selection — 2026-10-01

The accepted software profile uses agentbox-waw-https-bootstrap.v1 at the fixed
/.well-known/agentbox/waw-bootstrap.v1.json path, canonical sorted ASCII JSON
with a trailing newline and exactly twelve string fields: schema_version,
trust_profile (https-web-v1), repository, origin, runtime_host_installation_id,
runtime_host_installation_revision (exact positive uint64 wire string),
runtime_attestation_x25519_fingerprint, host_manifest_digest, build_identity,
version, valid_from and valid_until. Validity is exact UTC, positive and at most
31 days. It contains no native signatures, native clocks or persisted floors.

Root-owned static HTML must explicitly supply the unique meta names
agentbox-waw-trust-profile and agentbox-waw-build-identity. The latter must
match the public bootstrap. Missing markers retain the separate native route;
HTTP/insecure context cannot select Web trust. Two initial fresh, bounded,
same-Origin/no-redirect/credential-omitted reads must match before a lease is
issued. Periodic read loss/change, expiry, build/Origin drift, browser-clock
backward movement or close fences the lease. Authorization identifies this
distinct schema/profile, never an independent native provider.

Client/codec implementation is not publication or distribution evidence. The
Root-only transaction, immutable overlay/static path, independent serving,
proxy/CSP boundary and actual client/CLI qualification still must be completed
before exposing this profile as a deployable entry point.

| Situation | Managed desktop provider | Proposed Web profile |
| --- | --- | --- |
| API/Worker cannot read Runtime/Provider Secrets | Retained | Retained |
| Untrusted API data cannot change root-owned static bootstrap | Separate client authority | Independent root-owned serving/publication must prove this |
| Web client code or its HTTPS distribution is compromised | Independent native root/floor/time authority remains | **No equivalent independent client guarantee**; trusted Web code and Origin integrity are prerequisites |
| Client public state is cleared or rolled back | Native service journal/floors govern acceptance | No native persistent-floor guarantee; fresh bootstrap and explicit reauthorization are required |
| Privileged consistent host/client rollback | Existing documented limits | No new hardware/monotonic rollback claim |

HTTPS alone is not claimed to reproduce the native provider threat model.
If independent protection from compromised Web code is required for phones,
this proposal cannot meet it: the correct alternative is a trusted native
phone client/provider, with separate signing/distribution and device evidence.

## Required software and operational evidence

- Immutable static/proxy paths, exact owner/mode and API/Worker write-denial;
  bootstrap replacement/update failure and rollback tests.
- CSP, script/hash boundaries, API/project-content XSS and Origin/CSRF tests;
  no API, DOM or storage value accepted as a desktop native-provider override.
- Public-bootstrap schema, wrong Origin/host/key/build, expiry/rotation,
  unsupported-client and reconnect/write-uncertain behavior.
- Full Noise/AWCE integrity/replay/generation tests and unchanged exact Stop,
  cleanup and Runtime Secret custody; no arbitrary argv/cwd/env/path input.
- Actual PC browser and Android/iOS browser rendering, keyboard/IME/touch,
  background suspension and reconnect. X25519/WebCrypto capability must be
  observed per declared browser version; unsupported clients are explicit.
- Self-install on the declared Linux platform, certificates, first-login,
  provider login guidance, backup/upgrade/rollback and a truthful readiness
  report. Synthetic data, builds and responsive screenshots are not host or
  real-agent qualification.

## Transition and current state

Until this decision is authorized and its evidence exists, the current
managed-provider production gate remains unchanged. No localStorage/API/DOM
fallback is enabled by this document. Server installer/publication work can
continue independently. Existing accepted domain boundaries and the full
70-capability roadmap remain in force.

Reference behavior: fixed Paseo commit
30178c4f58b67f8472901356e1484022bd835de0 connectivity and pairing documents.
Reuse the clear host-link/QR onboarding experience, not its daemon authority
or credential-optional relay compatibility.
