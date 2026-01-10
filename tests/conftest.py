"""Shared pytest fixtures for async database testing.

This module provides reusable fixtures for testing SQLAlchemy models
and database operations using an in-memory SQLite database.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base


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
