"""Async database engine and session management.

This module provides the async SQLAlchemy 2.0 engine configuration,
session factory, and FastAPI dependency injection for database sessions.
Story 2.6 adds PgQueuer integration for task queue management.

Usage:
    from app.database import get_session, task_queue

    async def my_route(db: AsyncSession = Depends(get_session)):
        result = await db.execute(select(Channel))
        ...

    # Enqueue task to PgQueuer
    from pgqueuer.models import Job
    await task_queue.enqueue(Job(queue_name="video_tasks", payload={"task_id": "..."}))
"""

import os
from collections.abc import AsyncGenerator

# PgQueuer will be fully integrated in Epic 4 (Worker Orchestration)
# from pgqueuer.db import AsyncpgDriver, Driver
# from pgqueuer.qm import QueueManager
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _get_database_url() -> str:
    """Get database URL from environment, ensuring asyncpg driver.

    Returns:
        Database URL with postgresql+asyncpg:// protocol.

    Raises:
        ValueError: If DATABASE_URL is not set.
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")

    # Railway provides postgresql:// but we need postgresql+asyncpg://
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    return database_url


# Check if DATABASE_URL is available (may not be during import in tests)
_database_url = os.getenv("DATABASE_URL")

if _database_url:
    # Production: Create engine with configured pool
    engine = create_async_engine(
        _get_database_url(),
        pool_size=10,
        max_overflow=5,
        pool_pre_ping=True,  # Railway connection recycling
        echo=os.getenv("DATABASE_ECHO", "").lower() == "true",
    )
else:
    # Development/Testing: Defer engine creation
    engine = None  # type: ignore[assignment]


async_session_factory: async_sessionmaker[AsyncSession] | None = (
    async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,  # CRITICAL: prevents attribute expiration after commit
    )
    if engine
    else None
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database session injection.

    Yields an async database session with automatic commit on success
    and rollback on exception.

    Yields:
        AsyncSession: Database session for the request.

    Raises:
        RuntimeError: If database is not configured.

    Example:
        @router.get("/channels")
        async def list_channels(db: AsyncSession = Depends(get_session)):
            result = await db.execute(select(Channel))
            return result.scalars().all()
    """
    if async_session_factory is None:
        raise RuntimeError("Database not configured. Set DATABASE_URL environment variable.")

    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def create_test_engine(
    database_url: str = "sqlite+aiosqlite:///:memory:",
) -> tuple["AsyncEngine", async_sessionmaker[AsyncSession]]:
    """Create an async engine for testing.

    Args:
        database_url: Test database URL (defaults to in-memory SQLite).

    Returns:
        Tuple of (engine, async_session_factory) for testing.
    """
    test_engine = create_async_engine(
        database_url,
        echo=False,
    )
    test_session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return test_engine, test_session_factory


# PgQueuer queue manager setup (Story 2.6)
# Full integration deferred to Epic 4 (Worker Orchestration)
# For now, tasks with status='queued' are ready for workers
task_queue = None  # Will be initialized in Epic 4
