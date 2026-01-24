"""Tests for retry orchestrator Story 6.9 integration (retry tracking fields).

This module tests that schedule_retry() properly sets the new retry tracking fields:
- max_retry_attempts: Set to 5 (default) when scheduling retry
- last_error_timestamp: Updated with current UTC time on each error
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from app.models import Task, TaskStatus, PriorityLevel, Channel
from app.services.retry_orchestrator import schedule_retry, MAX_RETRY_ATTEMPTS
from app.services.error_classifier import ErrorContext


@pytest.fixture
async def test_channel(async_session):
    """Create test channel for retry orchestrator tests."""
    channel = Channel(
        channel_id="test-channel-retry-orch",
        channel_name="Test Retry Orchestrator Channel",
        is_active=True,
        max_concurrent=2,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


@pytest.fixture
async def test_task(async_session, test_channel):
    """Create test task for retry orchestrator tests."""
    task = Task(
        channel_id=test_channel.id,
        notion_page_id="test-page-retry-orch",
        title="Test Video",
        topic="Test Topic",
        story_direction="Test story",
        status=TaskStatus.ASSET_ERROR,  # Start in error status
        priority=PriorityLevel.NORMAL,
        retry_count=0,  # No retries yet
    )
    async_session.add(task)
    await async_session.commit()
    await async_session.refresh(task)
    return task


@pytest.mark.asyncio
async def test_schedule_retry_sets_max_retry_attempts(async_session, test_task):
    """Verify schedule_retry sets max_retry_attempts to default 5."""
    # Simulate transient error
    exception = Exception("Transient network error")
    context = ErrorContext(
        step_name="asset_generation",
        task_id=str(test_task.id),
        channel_id=test_task.channel_id,
    )

    # Schedule retry
    error_payload = await schedule_retry(test_task.id, exception, async_session, context)
    await async_session.commit()
    await async_session.refresh(test_task)

    # Verify max_retry_attempts set to default 5
    assert test_task.max_retry_attempts == 5
    assert error_payload is not None


@pytest.mark.asyncio
async def test_schedule_retry_sets_last_error_timestamp(async_session, test_task):
    """Verify schedule_retry sets last_error_timestamp to current time."""
    # Record time before scheduling retry
    time_before = datetime.now(timezone.utc)

    # Simulate transient error
    exception = Exception("Transient network error")
    context = ErrorContext(
        step_name="video_generation",
        task_id=str(test_task.id),
        channel_id=test_task.channel_id,
    )

    # Schedule retry
    await schedule_retry(test_task.id, exception, async_session, context)
    await async_session.commit()
    await async_session.refresh(test_task)

    # Record time after scheduling retry
    time_after = datetime.now(timezone.utc)

    # Verify last_error_timestamp is between time_before and time_after
    assert test_task.last_error_timestamp is not None

    # Handle timezone-aware vs naive datetime comparison
    if test_task.last_error_timestamp.tzinfo is None:
        error_timestamp_utc = test_task.last_error_timestamp.replace(tzinfo=timezone.utc)
    else:
        error_timestamp_utc = test_task.last_error_timestamp

    assert time_before <= error_timestamp_utc <= time_after


@pytest.mark.asyncio
async def test_schedule_retry_updates_last_error_timestamp_on_multiple_retries(
    async_session, test_task
):
    """Verify last_error_timestamp updates on each retry attempt."""
    context = ErrorContext(
        step_name="video_generation",
        task_id=str(test_task.id),
        channel_id=test_task.channel_id,
    )

    # First retry
    await schedule_retry(test_task.id, Exception("First error"), async_session, context)
    await async_session.commit()
    await async_session.refresh(test_task)
    first_timestamp = test_task.last_error_timestamp
    assert first_timestamp is not None

    # Wait a bit to ensure different timestamp
    import asyncio

    await asyncio.sleep(0.01)

    # Second retry
    await schedule_retry(test_task.id, Exception("Second error"), async_session, context)
    await async_session.commit()
    await async_session.refresh(test_task)
    second_timestamp = test_task.last_error_timestamp
    assert second_timestamp is not None

    # Handle timezone-aware vs naive datetime comparison
    if first_timestamp.tzinfo is None:
        first_timestamp = first_timestamp.replace(tzinfo=timezone.utc)
    if second_timestamp.tzinfo is None:
        second_timestamp = second_timestamp.replace(tzinfo=timezone.utc)

    # Verify timestamp updated (second should be after first)
    assert second_timestamp > first_timestamp


@pytest.mark.asyncio
async def test_terminal_failure_preserves_retry_fields(async_session, test_task):
    """Verify terminal failure preserves max_retry_attempts and last_error_timestamp."""
    context = ErrorContext(
        step_name="asset_generation",
        task_id=str(test_task.id),
        channel_id=test_task.channel_id,
    )

    # Exhaust all retries (MAX_RETRY_ATTEMPTS = 5)
    # should_retry_task checks CURRENT retry_count before increment
    # So set retry_count = 5 to trigger: should_retry_task(5) = False (5 >= 5)
    test_task.retry_count = MAX_RETRY_ATTEMPTS  # Set to 5
    await async_session.commit()

    # This call should trigger terminal failure immediately
    await schedule_retry(test_task.id, Exception("Final error"), async_session, context)
    await async_session.commit()
    await async_session.refresh(test_task)

    # Verify terminal failure state
    assert test_task.retry_count == MAX_RETRY_ATTEMPTS
    assert test_task.next_retry_at is None  # No more retries
    assert test_task.max_retry_attempts == 5  # Preserved
    assert test_task.last_error_timestamp is not None  # Preserved from last error


@pytest.mark.asyncio
async def test_permanent_error_sets_retry_fields_immediately(async_session, test_task):
    """Verify permanent error sets retry fields even though no retry scheduled."""
    # Simulate permanent error (400 bad request - classified as PERMANENT)
    import httpx

    request = httpx.Request("GET", "https://api.example.com")
    response = httpx.Response(400, request=request)
    exception = httpx.HTTPStatusError("Bad request", request=request, response=response)

    context = ErrorContext(
        step_name="asset_generation",
        task_id=str(test_task.id),
        channel_id=test_task.channel_id,
    )

    # Schedule retry (should go to terminal failure immediately due to PERMANENT error)
    await schedule_retry(test_task.id, exception, async_session, context)
    await async_session.commit()
    await async_session.refresh(test_task)

    # Verify retry fields set even for permanent error
    assert test_task.max_retry_attempts == 5
    assert test_task.last_error_timestamp is not None
    assert test_task.retry_count == MAX_RETRY_ATTEMPTS  # Exhausted immediately
    assert test_task.next_retry_at is None  # No retry


@pytest.mark.asyncio
async def test_retry_fields_persist_across_sessions(async_session, test_task):
    """Verify retry fields persist correctly across database sessions."""
    context = ErrorContext(
        step_name="video_generation",
        task_id=str(test_task.id),
        channel_id=test_task.channel_id,
    )

    # Schedule retry
    await schedule_retry(test_task.id, Exception("Transient error"), async_session, context)
    await async_session.commit()

    task_id = test_task.id

    # Close and reopen session
    await async_session.close()

    # Re-query in new session
    from sqlalchemy import select

    result = await async_session.execute(select(Task).where(Task.id == task_id))
    reloaded_task = result.scalar_one()

    # Verify fields persisted
    assert reloaded_task.max_retry_attempts == 5
    assert reloaded_task.last_error_timestamp is not None
    assert reloaded_task.retry_count == 1
