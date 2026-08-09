# Integration tests

Phase 3 integration tests exercise the FastAPI authentication boundary and
temporary SQLite databases through real Alembic upgrade/downgrade cycles. They
do not call host services, third-party Runtimes, a Privileged Helper, or the
network.
