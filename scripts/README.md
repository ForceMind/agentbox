# Repository scripts

These scripts inspect only the checked-out repository. They do not install software, execute product Runtimes, access authentication files, or modify the host.

- `check-secrets.sh` checks tracked-source-style paths and high-confidence credential literals.
- `check-skeleton-boundaries.sh` rejects dangerous execution primitives in Phase 2 source and unexpected API routes.
