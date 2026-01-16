"""Shared pytest fixtures for async database testing.

This module provides reusable fixtures for testing SQLAlchemy models
and database operations using an in-memory SQLite database.
Story 2.6 adds PgQueuer mock fixture.
"""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base
from app.utils.encryption import EncryptionService


@pytest.fixture
def valid_fernet_key() -> str:
    """Generate a valid Fernet key for testing.

    Returns a fresh, valid Fernet key string suitable for
    use with EncryptionService tests.
    """
    return Fernet.generate_key().decode()


@pytest.fixture(autouse=False)
def encryption_env(valid_fernet_key: str, monkeypatch: pytest.MonkeyPatch):
    """Set up encryption environment for tests.

    Sets FERNET_KEY environment variable and resets the
    EncryptionService singleton before and after the test.

    Use this fixture when tests need encryption capabilities.
    """
    EncryptionService.reset_instance()
    monkeypatch.setenv("FERNET_KEY", valid_fernet_key)
    yield valid_fernet_key
    EncryptionService.reset_instance()


@pytest_asyncio.fixture
async def async_engine():
    """Create an async SQLite engine for testing.

    Uses in-memory SQLite with aiosqlite for fast test execution.
    Creates all tables before yielding, disposes after.

    Yields:
        AsyncEngine: Configured test database engine.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine):
    """Create an async session for testing.

    Provides a session bound to the test engine with expire_on_commit=False
    to match production configuration.

    Args:
        async_engine: Test database engine fixture.

    Yields:
        AsyncSession: Database session for test operations.
    """
    async_session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_factory() as session:
        yield session


@pytest.fixture(autouse=True)
def mock_task_queue(monkeypatch):
    """Mock PgQueuer task queue for tests.

    Story 2.6: Automatically mocks task_queue.enqueue() for all tests
    to prevent RuntimeError when PgQueuer is not configured.

    This fixture is autouse=True so it applies to all tests by default.
    Tests can access the mock via this fixture to verify calls.

    Returns:
        AsyncMock: Mocked task_queue with enqueue method.
    """
    mock_queue = AsyncMock()
    mock_queue.enqueue = AsyncMock(return_value=None)

    # Patch task_queue in app.database where it's defined
    monkeypatch.setattr("app.database.task_queue", mock_queue)

    return mock_queue


# Import additional fixtures from fixtures/ package
# These provide enhanced database mocking capabilities from Epic 3 retrospective action items
from tests.fixtures.database import (  # noqa: F401, E402
    mock_async_session,
    async_test_engine,
    async_test_session,
    mock_session_factory,
    test_session_factory,
    sample_task_data,
    sample_channel_data,
)
