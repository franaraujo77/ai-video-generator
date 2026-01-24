"""Tests for retry tracking fields in Task model (Story 6.9).

This module tests the new retry tracking fields added to the Task model:
- max_retry_attempts: Maximum retry attempts before terminal failure
- last_error_timestamp: Timestamp of most recent error

Integration with existing fields:
- retry_count (from Story 6.2): Current retry attempt number
- next_retry_at (from Story 6.2): Scheduled time for next retry
"""

import pytest
from datetime import datetime, timezone

from app.models import Task, TaskStatus, PriorityLevel, Channel


@pytest.fixture
async def test_channel(async_session):
    """Create a test channel for retry tracking tests."""
    channel = Channel(
        channel_id="test-channel-retry",
        channel_name="Test Retry Channel",
        is_active=True,
        max_concurrent=2,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


@pytest.mark.asyncio
async def test_task_has_max_retry_attempts_field(async_session, test_channel):
    """Verify Task model has max_retry_attempts field with default value 5."""
    task = Task(
        channel_id=test_channel.id,
        notion_page_id="test-page-001",
        title="Test Video",
        topic="Test Topic",
        story_direction="Test story",
        status=TaskStatus.DRAFT,
        priority=PriorityLevel.NORMAL,
    )
    async_session.add(task)
    await async_session.commit()
    await async_session.refresh(task)

    # Verify max_retry_attempts exists and defaults to 5
    assert hasattr(task, "max_retry_attempts")
    assert task.max_retry_attempts == 5


@pytest.mark.asyncio
async def test_task_has_last_error_timestamp_field(async_session, test_channel):
    """Verify Task model has last_error_timestamp field (nullable)."""
    task = Task(
        channel_id=test_channel.id,
        notion_page_id="test-page-002",
        title="Test Video",
        topic="Test Topic",
        story_direction="Test story",
        status=TaskStatus.DRAFT,
        priority=PriorityLevel.NORMAL,
    )
    async_session.add(task)
    await async_session.commit()
    await async_session.refresh(task)

    # Verify last_error_timestamp exists and is nullable
    assert hasattr(task, "last_error_timestamp")
    assert task.last_error_timestamp is None


@pytest.mark.asyncio
async def test_set_last_error_timestamp(async_session, test_channel):
    """Verify last_error_timestamp can be set to a datetime."""
    task = Task(
        channel_id=test_channel.id,
        notion_page_id="test-page-003",
        title="Test Video",
        topic="Test Topic",
        story_direction="Test story",
        status=TaskStatus.DRAFT,
        priority=PriorityLevel.NORMAL,
    )
    async_session.add(task)
    await async_session.commit()

    # Set last_error_timestamp
    error_time = datetime.now(timezone.utc)
    task.last_error_timestamp = error_time
    await async_session.commit()
    await async_session.refresh(task)

    # Verify timestamp was set correctly
    assert task.last_error_timestamp is not None
    # Handle timezone-aware comparison (SQLite may return naive datetime)
    if task.last_error_timestamp.tzinfo is None:
        # If naive, assume UTC
        task_time_utc = task.last_error_timestamp.replace(tzinfo=timezone.utc)
    else:
        task_time_utc = task.last_error_timestamp
    assert abs((task_time_utc - error_time).total_seconds()) < 1


@pytest.mark.asyncio
async def test_max_retry_attempts_can_be_customized(async_session, test_channel):
    """Verify max_retry_attempts can be set to custom value."""
    task = Task(
        channel_id=test_channel.id,
        notion_page_id="test-page-004",
        title="Test Video",
        topic="Test Topic",
        story_direction="Test story",
        status=TaskStatus.DRAFT,
        priority=PriorityLevel.NORMAL,
        max_retry_attempts=3,  # Custom value (not default 5)
    )
    async_session.add(task)
    await async_session.commit()
    await async_session.refresh(task)

    # Verify custom max_retry_attempts was set
    assert task.max_retry_attempts == 3


@pytest.mark.asyncio
async def test_retry_fields_work_together(async_session, test_channel):
    """Verify all retry fields (old + new) work together correctly."""
    task = Task(
        channel_id=test_channel.id,
        notion_page_id="test-page-005",
        title="Test Video",
        topic="Test Topic",
        story_direction="Test story",
        status=TaskStatus.DRAFT,
        priority=PriorityLevel.NORMAL,
    )
    async_session.add(task)
    await async_session.commit()

    # Simulate error and retry scheduling
    error_time = datetime.now(timezone.utc)
    next_retry = datetime.now(timezone.utc)

    task.retry_count = 3  # Third retry attempt (from Story 6.2)
    task.next_retry_at = next_retry  # Scheduled retry time (from Story 6.2)
    task.max_retry_attempts = 5  # Max attempts (Story 6.9)
    task.last_error_timestamp = error_time  # Most recent error (Story 6.9)

    await async_session.commit()
    await async_session.refresh(task)

    # Verify all retry fields are set correctly
    assert task.retry_count == 3
    assert task.next_retry_at is not None
    assert task.max_retry_attempts == 5
    assert task.last_error_timestamp is not None


@pytest.mark.asyncio
async def test_retry_fields_persist_across_sessions(async_session, test_channel):
    """Verify retry fields persist correctly across database sessions."""
    task = Task(
        channel_id=test_channel.id,
        notion_page_id="test-page-006",
        title="Test Video",
        topic="Test Topic",
        story_direction="Test story",
        status=TaskStatus.DRAFT,
        priority=PriorityLevel.NORMAL,
        max_retry_attempts=7,
    )
    error_time = datetime.now(timezone.utc)
    task.last_error_timestamp = error_time

    async_session.add(task)
    await async_session.commit()

    task_id = task.id
    await async_session.close()

    # Re-query in new session
    from sqlalchemy import select

    result = await async_session.execute(select(Task).where(Task.id == task_id))
    reloaded_task = result.scalar_one()

    # Verify fields persisted
    assert reloaded_task.max_retry_attempts == 7
    assert reloaded_task.last_error_timestamp is not None
    # Handle timezone-aware comparison (SQLite may return naive datetime)
    if reloaded_task.last_error_timestamp.tzinfo is None:
        # If naive, assume UTC
        reloaded_time_utc = reloaded_task.last_error_timestamp.replace(tzinfo=timezone.utc)
    else:
        reloaded_time_utc = reloaded_task.last_error_timestamp
    assert abs((reloaded_time_utc - error_time).total_seconds()) < 1
