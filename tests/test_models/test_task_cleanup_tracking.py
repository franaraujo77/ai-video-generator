"""Tests for Task model cleanup tracking field (Story 8.5 Task 4).

Tests verify that cleanup_performed_at field exists and can be set/queried correctly.
This is the database schema foundation for workspace cleanup functionality.
"""

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from app.models import Task, TaskStatus
from tests.support.factories import create_task, create_channel


@pytest.mark.asyncio
async def test_cleanup_performed_at_field_exists(async_test_session):
    """Test cleanup_performed_at column exists on Task model."""
    # Verify field exists via ORM metadata
    assert hasattr(Task, "cleanup_performed_at")

    # Create task and verify field is accessible
    channel = create_channel()
    task = create_task(channel=channel)
    async_test_session.add(task)
    await async_test_session.commit()
    await async_test_session.refresh(task)

    # Field should be nullable and initially None
    assert task.cleanup_performed_at is None


@pytest.mark.asyncio
async def test_set_cleanup_performed_at_timestamp(async_test_session):
    """Test setting cleanup_performed_at timestamp on task."""
    channel = create_channel()
    task = create_task(channel=channel, status=TaskStatus.PUBLISHED)
    async_test_session.add(task)
    await async_test_session.commit()

    # Set cleanup timestamp
    cleanup_time = datetime.now(timezone.utc)
    task.cleanup_performed_at = cleanup_time
    await async_test_session.commit()
    await async_test_session.refresh(task)

    # Verify timestamp was saved (compare without microseconds due to SQLite precision)
    assert task.cleanup_performed_at is not None
    # SQLite stores datetime without timezone, so compare using replace
    assert task.cleanup_performed_at.replace(tzinfo=timezone.utc) == cleanup_time


@pytest.mark.asyncio
async def test_query_tasks_by_cleanup_performed_at(async_test_session):
    """Test querying tasks by cleanup_performed_at status."""
    channel = create_channel()

    # Create mix of cleaned and uncleaned tasks
    cleaned_task = create_task(
        channel=channel,
        status=TaskStatus.PUBLISHED,
        updated_at=datetime.now(timezone.utc) - timedelta(days=10)
    )
    cleaned_task.cleanup_performed_at = datetime.now(timezone.utc)

    uncleaned_task = create_task(
        channel=channel,
        status=TaskStatus.PUBLISHED,
        updated_at=datetime.now(timezone.utc) - timedelta(days=10)
    )

    async_test_session.add_all([cleaned_task, uncleaned_task])
    await async_test_session.commit()

    # Query uncleaned tasks (cleanup_performed_at IS NULL)
    result = await async_test_session.execute(
        select(Task).where(Task.cleanup_performed_at.is_(None))
    )
    uncleaned_tasks = list(result.scalars())

    # Should only return uncleaned task
    assert len(uncleaned_tasks) == 1
    assert uncleaned_tasks[0].id == uncleaned_task.id


@pytest.mark.asyncio
async def test_cleanup_performed_at_is_timezone_aware(async_test_session):
    """Test cleanup_performed_at stores timezone-aware datetime."""
    channel = create_channel()
    task = create_task(channel=channel)
    async_test_session.add(task)
    await async_test_session.commit()

    # Set timezone-aware timestamp
    cleanup_time = datetime.now(timezone.utc)
    task.cleanup_performed_at = cleanup_time
    await async_test_session.commit()
    await async_test_session.refresh(task)

    # Verify datetime was saved correctly
    # Note: SQLite doesn't preserve timezone info, PostgreSQL does
    # In production (PostgreSQL), tzinfo will be preserved as UTC
    assert task.cleanup_performed_at is not None
    # Compare values after normalizing timezone
    if task.cleanup_performed_at.tzinfo is None:
        # SQLite case: add UTC timezone for comparison
        assert task.cleanup_performed_at.replace(tzinfo=timezone.utc) == cleanup_time
    else:
        # PostgreSQL case: timezone preserved
        assert task.cleanup_performed_at.tzinfo == timezone.utc


@pytest.mark.asyncio
async def test_cleanup_performed_at_index_exists(async_test_session):
    """Test that cleanup_performed_at has database index for query performance."""
    # This test verifies the index exists in the schema
    # Index name should be: ix_tasks_cleanup_performed_at
    from sqlalchemy import inspect

    def get_indexes_sync(conn):
        """Synchronous function to get indexes from connection."""
        inspector = inspect(conn)
        return inspector.get_indexes("tasks")

    # Get indexes using run_sync pattern
    async with async_test_session.begin():
        conn = await async_test_session.connection()
        indexes = await conn.run_sync(get_indexes_sync)

    # Check if cleanup_performed_at index exists
    index_names = [idx["name"] for idx in indexes]
    assert "ix_tasks_cleanup_performed_at" in index_names
