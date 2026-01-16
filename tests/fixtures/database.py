"""
Database testing fixtures for async SQLAlchemy sessions.

This module provides reusable pytest fixtures for testing worker components
that use async database sessions. It supports both mocked sessions (for unit
tests) and real SQLite in-memory databases (for integration tests).

Usage:
    @pytest.mark.asyncio
    async def test_worker_with_mock_session(mock_async_session):
        # Use mock_async_session for unit testing
        pass

    @pytest.mark.asyncio
    async def test_worker_with_real_db(async_test_session):
        # Use async_test_session for integration testing
        pass
"""

import pytest
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base


@pytest.fixture
def mock_async_session(mocker):
    """
    Create a mocked AsyncSession for unit testing.

    This fixture provides a mock session that tracks:
    - begin() calls (transaction starts)
    - commit() calls (transaction commits)
    - rollback() calls (transaction rollbacks)
    - get() calls (model retrievals)
    - add() calls (model additions)
    - Transaction lifecycle (open/closed state)

    Example:
        @pytest.mark.asyncio
        async def test_task_processing(mock_async_session):
            # Mock session tracks calls
            mock_async_session.get.return_value = Task(id="123", status="queued")

            # Verify transaction pattern
            async with mock_async_session.begin():
                task = await mock_async_session.get(Task, "123")
                task.status = "processing"
                await mock_async_session.commit()

            # Assert transaction lifecycle
            assert mock_async_session.begin.called
            assert mock_async_session.commit.called
    """
    mock_session = AsyncMock(spec=AsyncSession)

    # Track transaction state
    mock_session._transaction_active = False
    mock_session._transaction_count = 0

    # Mock begin() context manager
    mock_begin = AsyncMock()

    async def begin_context():
        """Track transaction begin"""
        mock_session._transaction_active = True
        mock_session._transaction_count += 1
        return mock_begin

    mock_session.begin = MagicMock(side_effect=begin_context)
    mock_begin.__aenter__ = AsyncMock(return_value=mock_begin)
    mock_begin.__aexit__ = AsyncMock(side_effect=lambda *args: setattr(
        mock_session, '_transaction_active', False
    ))

    # Mock commit() and rollback()
    async def commit():
        """Track commit calls"""
        if not mock_session._transaction_active:
            raise RuntimeError("No active transaction")
        mock_session._transaction_active = False

    async def rollback():
        """Track rollback calls"""
        if not mock_session._transaction_active:
            raise RuntimeError("No active transaction")
        mock_session._transaction_active = False

    mock_session.commit = AsyncMock(side_effect=commit)
    mock_session.rollback = AsyncMock(side_effect=rollback)

    # Mock common query methods
    mock_session.get = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()

    return mock_session


@pytest.fixture
async def async_test_engine():
    """
    Create an async SQLite in-memory engine for testing.

    Uses StaticPool to maintain single connection across async operations.
    Database schema is created from SQLAlchemy models.

    Returns:
        AsyncEngine configured for testing
    """
    # Create in-memory SQLite database with async driver
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,  # Set to True for SQL debugging
        poolclass=StaticPool,  # Single connection for in-memory DB
    )

    # Create all tables from models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup: drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def async_test_session(async_test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Create an async SQLAlchemy session for integration testing.

    This fixture provides a real database session backed by SQLite in-memory.
    Use this for integration tests that need to verify database transactions,
    relationships, and query behavior.

    Example:
        @pytest.mark.asyncio
        async def test_task_creation(async_test_session):
            # Real database operations
            task = Task(id="123", channel_id="poke1", status="queued")
            async_test_session.add(task)
            await async_test_session.commit()

            # Verify task was persisted
            result = await async_test_session.get(Task, "123")
            assert result.status == "queued"

    Yields:
        AsyncSession connected to in-memory SQLite database
    """
    # Create session factory
    async_session_factory = async_sessionmaker(
        async_test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Create session
    async with async_session_factory() as session:
        yield session


@pytest.fixture
def mock_session_factory(mock_async_session):
    """
    Create a mocked AsyncSessionLocal factory for testing workers.

    This fixture mocks the session factory used in worker code:
    `async with AsyncSessionLocal() as session:`

    Example:
        @pytest.mark.asyncio
        async def test_worker_transaction_pattern(mock_session_factory, mocker):
            # Patch AsyncSessionLocal
            mocker.patch("app.database.AsyncSessionLocal", mock_session_factory)

            # Worker code uses mocked session
            from app.workers.asset_worker import process_asset_generation_task
            await process_asset_generation_task("task_123")

            # Verify short transaction pattern
            assert mock_session_factory().begin.call_count == 2  # Claim + Update
            assert mock_session_factory().commit.call_count == 2
    """
    mock_factory = MagicMock()
    mock_factory.return_value = mock_async_session
    mock_factory().__aenter__ = AsyncMock(return_value=mock_async_session)
    mock_factory().__aexit__ = AsyncMock()
    return mock_factory


@pytest.fixture
async def test_session_factory(async_test_engine):
    """
    Create a real async session factory for integration testing.

    This fixture provides a session factory that creates real database
    sessions for integration tests. Use this when you need to test
    worker transaction patterns with actual database behavior.

    Example:
        @pytest.mark.asyncio
        async def test_worker_with_real_db(test_session_factory, mocker):
            # Patch AsyncSessionLocal with real factory
            mocker.patch("app.database.AsyncSessionLocal", test_session_factory)

            # Worker code uses real database
            from app.workers.asset_worker import process_asset_generation_task
            await process_asset_generation_task("task_123")

            # Verify task persisted in database
            async with test_session_factory() as session:
                task = await session.get(Task, "task_123")
                assert task.status == "completed"

    Yields:
        async_sessionmaker factory for creating real database sessions
    """
    factory = async_sessionmaker(
        async_test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return factory


# Helper fixtures for common test data

@pytest.fixture
def sample_task_data():
    """
    Sample task data for testing.

    Returns:
        Dict with task attributes for creating test tasks
    """
    return {
        "id": "test-task-123",
        "channel_id": "poke1",
        "project_id": "vid_abc123",
        "topic": "Bulbasaur forest documentary",
        "story_direction": "Show evolution through seasons",
        "status": "queued",
        "notion_page_id": "notion_page_abc",
    }


@pytest.fixture
def sample_channel_data():
    """
    Sample channel data for testing.

    Returns:
        Dict with channel attributes for creating test channels
    """
    return {
        "id": "poke1",
        "channel_name": "Pokemon Nature Docs",
        "voice_id": "EXAVITQu4vr4xnSDxMaL",
        "is_active": True,
    }
