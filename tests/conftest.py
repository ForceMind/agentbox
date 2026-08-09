import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Keep skeleton ASGI tests on the installed asyncio backend."""
    return "asyncio"
