"""Tests for database connection and session management.

Tests the async database engine configuration, session factory,
and dependency injection patterns.
"""

import os
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.database import _get_database_url, create_test_engine


class TestGetDatabaseUrl:
    """Tests for _get_database_url function."""

    def test_raises_value_error_when_database_url_not_set(self):
        """Test that ValueError is raised when DATABASE_URL is missing."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove DATABASE_URL if it exists
            if "DATABASE_URL" in os.environ:
                del os.environ["DATABASE_URL"]

            with patch.dict(os.environ, {}, clear=True):
                with pytest.raises(
                    ValueError, match="DATABASE_URL environment variable is required"
                ):
                    _get_database_url()

    def test_returns_url_unchanged_when_already_asyncpg(self):
        """Test that postgresql+asyncpg:// URLs are returned unchanged."""
        test_url = "postgresql+asyncpg://user:pass@localhost:5432/testdb"
        with patch.dict(os.environ, {"DATABASE_URL": test_url}):
            result = _get_database_url()
            assert result == test_url

    def test_converts_postgresql_to_asyncpg(self):
        """Test that postgresql:// is converted to postgresql+asyncpg://."""
        original_url = "postgresql://user:pass@localhost:5432/testdb"
        expected_url = "postgresql+asyncpg://user:pass@localhost:5432/testdb"
        with patch.dict(os.environ, {"DATABASE_URL": original_url}):
            result = _get_database_url()
            assert result == expected_url

    def test_only_replaces_first_occurrence(self):
        """Test that only the protocol prefix is replaced, not other occurrences."""
        # Edge case: URL with postgresql in a different part
        original_url = "postgresql://user@postgresql-host:5432/db"
        expected_url = "postgresql+asyncpg://user@postgresql-host:5432/db"
        with patch.dict(os.environ, {"DATABASE_URL": original_url}):
            result = _get_database_url()
            assert result == expected_url


@pytest.mark.asyncio
async def test_create_test_engine_creates_working_connection():
    """Test that create_test_engine creates a working async engine."""
    engine, session_factory = create_test_engine()

    async with session_factory() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_session_factory_creates_async_session(async_session):
    """Test that session factory creates a valid AsyncSession."""
    # Session should be usable for queries
    result = await async_session.execute(text("SELECT 1"))
    assert result.scalar() == 1


@pytest.mark.asyncio
async def test_session_expire_on_commit_is_false(async_session):
    """Test that session has expire_on_commit=False.

    This is critical for accessing attributes after commit without
    triggering additional queries.
    """
    # In SQLAlchemy 2.0, expire_on_commit is on the sync_session
    assert async_session.sync_session.expire_on_commit is False


@pytest.mark.asyncio
async def test_engine_connect_and_execute(async_engine):
    """Test that engine can connect and execute queries."""
    async with async_engine.connect() as conn:
        result = await conn.execute(text("SELECT 42 as answer"))
        row = result.fetchone()
        assert row is not None
        assert row.answer == 42


@pytest.mark.asyncio
async def test_session_rollback_on_exception(async_engine):
    """Test that session rolls back changes on exception."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.models import Base, Channel

    # Create tables
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # First, add a channel and commit
    async with session_factory() as session:
        channel = Channel(channel_id="rollback-test", channel_name="Rollback Test")
        session.add(channel)
        await session.commit()

    # Now try to add a duplicate (should fail) - verify original still exists
    try:
        async with session_factory() as session:
            duplicate = Channel(channel_id="rollback-test", channel_name="Duplicate")
            session.add(duplicate)
            await session.commit()
    except Exception:
        pass  # Expected to fail

    # Verify original channel still exists
    async with session_factory() as session:
        from sqlalchemy import select

        result = await session.execute(select(Channel).where(Channel.channel_id == "rollback-test"))
        found = result.scalar_one()
        assert found.channel_name == "Rollback Test"


@pytest.mark.asyncio
async def test_multiple_sessions_isolation(async_engine):
    """Test that multiple sessions operate independently."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.models import Base, Channel

    # Create tables
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Session 1: Add a channel
    async with session_factory() as session1:
        channel1 = Channel(channel_id="session1-channel", channel_name="Session 1")
        session1.add(channel1)
        await session1.commit()

    # Session 2: Add a different channel
    async with session_factory() as session2:
        channel2 = Channel(channel_id="session2-channel", channel_name="Session 2")
        session2.add(channel2)
        await session2.commit()

    # Verify both channels exist
    async with session_factory() as session:
        from sqlalchemy import select

        result = await session.execute(select(Channel))
        channels = result.scalars().all()
        channel_ids = [c.channel_id for c in channels]
        assert "session1-channel" in channel_ids
        assert "session2-channel" in channel_ids


class TestGetSessionDependency:
    """Tests for get_session() FastAPI dependency function."""

    @pytest.mark.asyncio
    async def test_get_session_raises_when_not_configured(self):
        """Test that get_session() raises RuntimeError when database not configured."""
        from unittest.mock import patch

        from app.database import get_session

        # Mock async_session_factory to be None (simulating unconfigured database)
        with patch("app.database.async_session_factory", None):
            with pytest.raises(RuntimeError, match="Database not configured"):
                async for _ in get_session():
                    pass

    @pytest.mark.asyncio
    async def test_get_session_yields_session_and_commits(self, async_engine):
        """Test that get_session yields a session and commits on success."""
        from unittest.mock import AsyncMock, patch

        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from app.models import Base, Channel

        # Create tables
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Create a real session factory for this test
        test_session_factory = async_sessionmaker(
            bind=async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Import the actual function and mock the factory
        from app.database import get_session

        with patch("app.database.async_session_factory", test_session_factory):
            # Use the dependency
            async for session in get_session():
                # Add a channel within the session
                channel = Channel(channel_id="dep-test", channel_name="Dependency Test")
                session.add(channel)
                # Don't call commit - get_session should do it

        # Verify the channel was committed by querying in a new session
        async with test_session_factory() as verify_session:
            from sqlalchemy import select

            result = await verify_session.execute(
                select(Channel).where(Channel.channel_id == "dep-test")
            )
            found = result.scalar_one_or_none()
            assert found is not None
            assert found.channel_name == "Dependency Test"

    @pytest.mark.asyncio
    async def test_get_session_rolls_back_on_exception(self, async_engine):
        """Test that get_session rolls back on exception."""
        from unittest.mock import patch

        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from app.models import Base, Channel

        # Create tables
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        test_session_factory = async_sessionmaker(
            bind=async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        from app.database import get_session

        with patch("app.database.async_session_factory", test_session_factory):
            try:
                async for session in get_session():
                    # Add a channel
                    channel = Channel(channel_id="rollback-dep-test", channel_name="Rollback Test")
                    session.add(channel)
                    # Raise an exception before generator closes
                    raise ValueError("Simulated error")
            except ValueError:
                pass  # Expected

        # Verify the channel was NOT committed (rolled back)
        async with test_session_factory() as verify_session:
            from sqlalchemy import select

            result = await verify_session.execute(
                select(Channel).where(Channel.channel_id == "rollback-dep-test")
            )
            found = result.scalar_one_or_none()
            assert found is None, "Channel should not exist after rollback"
