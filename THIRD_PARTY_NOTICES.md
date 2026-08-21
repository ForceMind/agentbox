# Third-Party Notices

AgentBox is licensed under Apache-2.0. The AgentBox release artifact also
contains unmodified or compiled forms of the following third-party packages.
This inventory records the dependency versions selected by
`requirements-release.lock`, `requirements-release-bootstrap.lock`, and
`pnpm-lock.yaml`; it is not legal advice and
does not replace the license text distributed by each upstream project.

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
