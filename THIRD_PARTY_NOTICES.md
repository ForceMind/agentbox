# Third-Party Notices

AgentBox is licensed under Apache-2.0. The AgentBox release artifact also
contains unmodified or compiled forms of the following third-party packages.
This inventory records the dependency versions selected by
`requirements-release.txt`, `requirements-release-bootstrap.lock`, and
`pnpm-lock.yaml`; it is not legal advice and
does not replace the license text distributed by each upstream project.

## Adapted source code

The AgentBox Web Changes file-tree and diff-ordering code, and the Control
Plane navigation-label name/color/catalog behavior, include adaptations of
getpaseo/paseo source at commit
`30178c4f58b67f8472901356e1484022bd835de0`.
Copyright (c) 2025-present Mohamed Boudra. Licensed under Apache-2.0; the
license text is included in `LICENSE`. The adapted files retain source and
change notices. The repository records their original paths and digests in
`third_party/upstream-sources.json`. This attribution does not imply
affiliation or endorsement.

## T3 Code design references

Kebui's T3 Code integration plan and its independently implemented K2 operation
capability descriptor use design references from `pingdotgg/t3code` at commit
`d73e41a3fa379b591d9fb59d722d2569ec05994b`. Copyright (c) 2026 T3 Tools Inc.
The upstream source is MIT-licensed. This batch does not copy or port upstream
implementation code and does not add a T3 runtime dependency. The selected
research files, immutable source hashes and independent implementation mapping
are recorded in `third_party/t3code-sources.json`; the repository also retains
`third_party/t3code-LICENSE.txt`.

T3 names, icons, visual branding, domains and hosted services are not part of
this integration. AgentBox/Kebui is not affiliated with, endorsed by, or
maintained by T3 Tools Inc. Any later source-code port must record its files,
changes and applicable nested third-party licenses separately. The complete
upstream MIT notice is included here so this notice remains self-contained in
release artifacts:

```text
MIT License

Copyright (c) 2026 T3 Tools Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Python runtime dependencies

| Package | Version | Declared license |
|---|---:|---|
| Alembic | 1.19.1 | MIT |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| AnyIO | 4.14.2 | MIT |
| argon2-cffi | 25.1.0 | MIT |
| argon2-cffi-bindings | 25.1.0 | MIT |
| CFFI | 2.1.1 | MIT-0 |
| Click | 8.4.2 | BSD-3-Clause |
| cryptography | 50.0.0 | Apache-2.0 OR BSD-3-Clause |
| FastAPI | 0.141.1 | MIT |
| greenlet | 3.5.5 | MIT AND PSF-2.0 |
| h11 | 0.16.0 | MIT |
| idna | 3.18 | BSD-3-Clause |
| Mako | 1.4.1 | MIT |
| MarkupSafe | 3.0.3 | BSD-3-Clause |
| pycparser | 3.0 | BSD-3-Clause |
| Pydantic | 2.13.4 | MIT |
| pydantic-core | 2.46.4 | MIT |
| pydantic-settings | 2.15.0 | MIT |
| python-dotenv | 1.2.2 | BSD-3-Clause |
| rfc8785 | 0.1.4 | Apache-2.0 |
| SQLAlchemy | 2.0.52 | MIT |
| Starlette | 1.6.0 | BSD-3-Clause |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |
| Uvicorn | 0.52.2 | BSD-3-Clause |

## Offline bootstrap tooling

| Package | Version | Declared license |
|---|---:|---|
| pip | 26.2.1 | MIT |

## Frontend runtime dependencies

| Package | Version | Declared license |
|---|---:|---|
| cookie | 1.1.1 | MIT |
| lucide-react | 1.30.0 | ISC |
| react | 19.2.8 | MIT |
| react-dom | 19.2.8 | MIT |
| react-router | 7.18.2 | MIT |
| react-router-dom | 7.18.2 | MIT |
| scheduler | 0.27.0 | MIT |
| set-cookie-parser | 2.7.2 | MIT |

The machine-readable SPDX 2.3 SBOM shipped beside and inside each release
artifact is the authoritative generated package/version/license inventory for
that build. No GPL or AGPL runtime dependency was observed in this candidate
inventory. A maintainer must still review any lockfile or license change before
publication.
