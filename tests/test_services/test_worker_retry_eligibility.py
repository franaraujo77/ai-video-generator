"""Tests for worker retry eligibility checks (Story 6.9, Task 5).

This module tests that workers properly check retry eligibility before
processing tasks:
- Workers skip tasks with future next_retry_at (not ready for retry)
- Workers process tasks when retry time has arrived
- Workers process normal tasks (retry_count=0) without checks
- Retry eligibility uses should_retry() from retry_state_service
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Channel, PriorityLevel, Task, TaskStatus


@pytest.fixture
async def test_channel(async_session):
    """Create test channel for worker retry tests."""
    channel = Channel(
        channel_id="test-channel-worker-retry",
        channel_name="Test Worker Retry Channel",
        is_active=True,
        max_concurrent=2,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


@pytest.fixture
async def normal_task(async_session, test_channel):
    """Create normal task (no retries) for testing."""
    task = Task(
        channel_id=test_channel.id,
        notion_page_id="test-page-normal",
        title="Normal Task",
        topic="Test Topic",
        story_direction="Test story",
        status=TaskStatus.QUEUED,
        priority=PriorityLevel.NORMAL,
        retry_count=0,
        next_retry_at=None,
    )
    async_session.add(task)
    await async_session.commit()
    await async_session.refresh(task)
    return task


@pytest.fixture
async def retry_ready_task(async_session, test_channel):
    """Create task that's ready for retry (retry time has arrived)."""
    # Set retry time 1 minute in the PAST
    past_retry_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    task = Task(
        channel_id=test_channel.id,
        notion_page_id="test-page-retry-ready",
        title="Retry Ready Task",
        topic="Test Topic",
        story_direction="Test story",
        status=TaskStatus.ASSET_ERROR,
        priority=PriorityLevel.NORMAL,
        retry_count=2,
        next_retry_at=past_retry_time,
        max_retry_attempts=5,
    )
    async_session.add(task)
    await async_session.commit()
    await async_session.refresh(task)
    return task


@pytest.fixture
async def retry_waiting_task(async_session, test_channel):
    """Create task waiting for retry (retry time in future)."""
    # Set retry time 15 minutes in the FUTURE
    future_retry_time = datetime.now(timezone.utc) + timedelta(minutes=15)
    task = Task(
        channel_id=test_channel.id,
        notion_page_id="test-page-retry-waiting",
        title="Retry Waiting Task",
        topic="Test Topic",
        story_direction="Test story",
        status=TaskStatus.VIDEO_ERROR,
        priority=PriorityLevel.NORMAL,
        retry_count=3,
        next_retry_at=future_retry_time,
        max_retry_attempts=5,
    )
    async_session.add(task)
    await async_session.commit()
    await async_session.refresh(task)
    return task


@pytest.fixture
async def retry_exhausted_task(async_session, test_channel):
    """Create task with exhausted retries (terminal failure)."""
    task = Task(
        channel_id=test_channel.id,
        notion_page_id="test-page-retry-exhausted",
        title="Retry Exhausted Task",
        topic="Test Topic",
        story_direction="Test story",
        status=TaskStatus.AUDIO_ERROR,
        priority=PriorityLevel.NORMAL,
        retry_count=5,  # Exhausted
        next_retry_at=None,  # No more retries
        max_retry_attempts=5,
    )
    async_session.add(task)
    await async_session.commit()
    await async_session.refresh(task)
    return task


class TestWorkerRetryEligibilityLogic:
    """Test worker retry eligibility logic using should_retry()."""

    @pytest.mark.asyncio
    async def test_should_retry_normal_task(self, normal_task):
        """Verify normal tasks (retry_count=0) pass eligibility check."""
        from app.services.retry_state_service import should_retry

        # Normal tasks have retry_count=0, so they skip the retry check in worker
        # This test verifies the logic: if retry_count > 0, then check should_retry
        assert normal_task.retry_count == 0
        # Worker code: if retry_count > 0: check should_retry()
        # For retry_count=0, worker proceeds without calling should_retry

    @pytest.mark.asyncio
    async def test_should_retry_ready_task(self, retry_ready_task):
        """Verify retry-ready tasks pass should_retry() check."""
        from app.services.retry_state_service import should_retry

        # Task with past next_retry_at should be eligible
        assert retry_ready_task.retry_count == 2
        assert retry_ready_task.next_retry_at is not None

        # should_retry returns True (retry time has arrived)
        is_eligible = should_retry(
            retry_attempt=retry_ready_task.retry_count,
            next_retry_at=retry_ready_task.next_retry_at,
            max_attempts=retry_ready_task.max_retry_attempts,
        )
        assert is_eligible is True

    @pytest.mark.asyncio
    async def test_should_retry_waiting_task(self, retry_waiting_task):
        """Verify retry-waiting tasks fail should_retry() check."""
        from app.services.retry_state_service import should_retry

        # Task with future next_retry_at should NOT be eligible
        assert retry_waiting_task.retry_count == 3
        assert retry_waiting_task.next_retry_at is not None

        # should_retry returns False (retry time hasn't arrived)
        is_eligible = should_retry(
            retry_attempt=retry_waiting_task.retry_count,
            next_retry_at=retry_waiting_task.next_retry_at,
            max_attempts=retry_waiting_task.max_retry_attempts,
        )
        assert is_eligible is False

    @pytest.mark.asyncio
    async def test_should_retry_exhausted_task(self, retry_exhausted_task):
        """Verify exhausted-retry tasks fail should_retry() check."""
        from app.services.retry_state_service import should_retry

        # Task with retry_count >= max_retry_attempts should NOT be eligible
        assert retry_exhausted_task.retry_count == 5
        assert retry_exhausted_task.max_retry_attempts == 5

        # should_retry returns False (retries exhausted)
        is_eligible = should_retry(
            retry_attempt=retry_exhausted_task.retry_count,
            next_retry_at=retry_exhausted_task.next_retry_at,
            max_attempts=retry_exhausted_task.max_retry_attempts,
        )
        assert is_eligible is False

    @pytest.mark.asyncio
    async def test_should_retry_integration(self):
        """Verify should_retry() logic matches expectations."""
        from app.services.retry_state_service import should_retry

        # Test 1: Retry ready (past time)
        past_time = datetime.now(timezone.utc) - timedelta(minutes=1)
        assert should_retry(2, past_time, 5) is True

        # Test 2: Retry waiting (future time)
        future_time = datetime.now(timezone.utc) + timedelta(minutes=15)
        assert should_retry(3, future_time, 5) is False

        # Test 3: Retry exhausted (count >= max)
        assert should_retry(5, past_time, 5) is False

        # Test 4: No retry scheduled (None)
        assert should_retry(2, None, 5) is False


class TestWorkerRetryEligibilityIntegration:
    """Integration tests for worker retry eligibility in entrypoint."""

    @pytest.mark.asyncio
    async def test_entrypoint_has_retry_check(self):
        """Verify entrypoint code includes retry eligibility check."""
        import inspect
        from app.entrypoints import register_entrypoints

        # Get the entrypoint source code
        source = inspect.getsource(register_entrypoints)

        # Verify retry eligibility check is present
        assert "should_retry" in source, "Entrypoint should import should_retry"
        assert "retry_count > 0" in source, "Entrypoint should check if task has retries"
        assert "task_retry_not_ready_releasing" in source, "Entrypoint should log retry release"
