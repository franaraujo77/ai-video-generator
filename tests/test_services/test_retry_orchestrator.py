"""Tests for retry orchestrator service (Story 6.2).

Test Coverage:
    - Retry schedule calculations (1min, 5min, 15min, 1hr)
    - Should retry logic (transient vs permanent, retry limit)
    - Schedule retry workflow (increment count, set timestamp, append log)
    - Claim retry tasks polling (WHERE next_retry_at <= now)
    - Terminal failure handling (alert trigger, retry exhaustion)
"""

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select

from app.models import Task, TaskStatus
from app.services.error_classifier import ErrorAnalysis, ErrorCategory
from app.services.retry_orchestrator import (
    MAX_RETRY_ATTEMPTS,
    RETRY_SCHEDULE,
    calculate_next_retry,
    claim_retry_tasks,
    schedule_retry,
    should_retry_task,
)


class TestRetryScheduleCalculations:
    """Test retry schedule calculations match FR28 requirements."""

    def test_calculate_next_retry_first_attempt(self):
        """Verify first retry scheduled for 1 minute from now (AC1)."""
        before = datetime.now(timezone.utc)
        next_retry = calculate_next_retry(retry_count=0)
        after = datetime.now(timezone.utc)

        expected_delay = RETRY_SCHEDULE[0]  # 1 minute
        assert (next_retry - before) >= expected_delay
        assert (next_retry - after) <= expected_delay + timedelta(seconds=1)

    def test_calculate_next_retry_second_attempt(self):
        """Verify second retry scheduled for 5 minutes from now (AC2)."""
        before = datetime.now(timezone.utc)
        next_retry = calculate_next_retry(retry_count=1)
        after = datetime.now(timezone.utc)

        expected_delay = RETRY_SCHEDULE[1]  # 5 minutes
        assert (next_retry - before) >= expected_delay
        assert (next_retry - after) <= expected_delay + timedelta(seconds=1)

    def test_calculate_next_retry_third_attempt(self):
        """Verify third retry scheduled for 15 minutes from now (AC3)."""
        before = datetime.now(timezone.utc)
        next_retry = calculate_next_retry(retry_count=2)
        after = datetime.now(timezone.utc)

        expected_delay = RETRY_SCHEDULE[2]  # 15 minutes
        assert (next_retry - before) >= expected_delay
        assert (next_retry - after) <= expected_delay + timedelta(seconds=1)

    def test_calculate_next_retry_fourth_attempt(self):
        """Verify fourth retry scheduled for 1 hour from now (AC4)."""
        before = datetime.now(timezone.utc)
        next_retry = calculate_next_retry(retry_count=3)
        after = datetime.now(timezone.utc)

        expected_delay = RETRY_SCHEDULE[3]  # 1 hour
        assert (next_retry - before) >= expected_delay
        assert (next_retry - after) <= expected_delay + timedelta(seconds=1)

    def test_calculate_next_retry_boundary_fallback(self):
        """Verify retry_count >= 4 falls back to last schedule (1 hour)."""
        before = datetime.now(timezone.utc)
        next_retry = calculate_next_retry(retry_count=4)
        after = datetime.now(timezone.utc)

        expected_delay = RETRY_SCHEDULE[-1]  # Last entry: 1 hour
        assert (next_retry - before) >= expected_delay
        assert (next_retry - after) <= expected_delay + timedelta(seconds=1)


class TestShouldRetryLogic:
    """Test should_retry_task logic for transient vs permanent errors."""

    def test_should_retry_transient_first_attempt(self):
        """Verify transient error on first attempt returns True."""
        error_analysis = ErrorAnalysis(
            category=ErrorCategory.TRANSIENT,
            http_status_code=503,
            error_type="ServiceUnavailable",
            error_message="Service temporarily unavailable",
            retry_recommended=True,
            confidence=0.9,
            suggested_action="Retry with exponential backoff",
        )

        assert should_retry_task(error_analysis, retry_count=0) is True

    def test_should_retry_transient_fourth_attempt(self):
        """Verify transient error on 4th attempt still retries (last attempt)."""
        error_analysis = ErrorAnalysis(
            category=ErrorCategory.TRANSIENT,
            http_status_code=429,
            error_type="RateLimitError",
            error_message="Rate limit exceeded",
            retry_recommended=True,
            confidence=0.95,
            suggested_action="Wait and retry",
        )

        assert should_retry_task(error_analysis, retry_count=4) is True

    def test_should_retry_transient_exhausted_attempts(self):
        """Verify transient error after 5 attempts returns False (AC5)."""
        error_analysis = ErrorAnalysis(
            category=ErrorCategory.TRANSIENT,
            http_status_code=503,
            error_type="ServiceUnavailable",
            error_message="Service temporarily unavailable",
            retry_recommended=True,
            confidence=0.9,
            suggested_action="Retry with exponential backoff",
        )

        assert should_retry_task(error_analysis, retry_count=5) is False

    def test_should_retry_permanent_error(self):
        """Verify permanent error returns False immediately."""
        error_analysis = ErrorAnalysis(
            category=ErrorCategory.PERMANENT,
            http_status_code=400,
            error_type="BadRequestError",
            error_message="Invalid API parameters",
            retry_recommended=False,
            confidence=0.95,
            suggested_action="Fix request parameters",
        )

        assert should_retry_task(error_analysis, retry_count=0) is False

    def test_should_retry_unknown_error_conservative(self):
        """Verify unknown error returns True (conservative retry)."""
        error_analysis = ErrorAnalysis(
            category=ErrorCategory.UNKNOWN,
            http_status_code=None,
            error_type="UnknownError",
            error_message="Unexpected error occurred",
            retry_recommended=True,
            confidence=0.3,
            suggested_action="Retry cautiously",
        )

        assert should_retry_task(error_analysis, retry_count=0) is True


@pytest.mark.asyncio
class TestScheduleRetryIntegration:
    """Integration tests for schedule_retry workflow."""

    async def test_schedule_retry_increments_count(self, async_session):
        """Verify schedule_retry increments retry_count and sets next_retry_at."""
        # Create task
        task = Task(
            id=uuid4(),
            channel_id=uuid4(),
            notion_page_id="test-page-id",
            title="Test Video",
            topic="Test",
            story_direction="Test story",
            retry_count=0,
        )
        async_session.add(task)
        await async_session.commit()

        # Simulate transient failure
        exception = httpx.HTTPStatusError(
            "Service unavailable",
            request=httpx.Request("GET", "https://api.example.com"),
            response=httpx.Response(503),
        )

        # Capture time before scheduling retry (for comparison)
        before_retry = datetime.now(timezone.utc)

        # Schedule retry
        await schedule_retry(task.id, exception, async_session)
        await async_session.commit()
        await async_session.refresh(task)

        # Verify task updated
        assert task.retry_count == 1
        assert task.next_retry_at is not None
        # Verify next_retry_at is in the future (relative to when retry was scheduled)
        # Note: SQLite doesn't preserve timezone info, so we need to ensure both datetimes are comparable
        task_next_retry = task.next_retry_at
        if task_next_retry.tzinfo is None:
            task_next_retry = task_next_retry.replace(tzinfo=timezone.utc)
        assert task_next_retry > before_retry

    async def test_schedule_retry_appends_error_log(self, async_session):
        """Verify schedule_retry appends to error_log in JSON lines format."""
        # Create task
        task = Task(
            id=uuid4(),
            channel_id=uuid4(),
            notion_page_id="test-page-id-2",
            title="Test Video",
            topic="Test",
            story_direction="Test story",
            retry_count=0,
        )
        async_session.add(task)
        await async_session.commit()

        # Simulate transient failure
        exception = httpx.HTTPStatusError(
            "Rate limited",
            request=httpx.Request("POST", "https://api.example.com"),
            response=httpx.Response(429),
        )

        # Schedule retry
        await schedule_retry(task.id, exception, async_session)
        await async_session.commit()
        await async_session.refresh(task)

        # Verify error log appended
        assert task.error_log is not None
        log_entry = json.loads(task.error_log)

        assert log_entry["task_id"] == str(task.id)
        assert log_entry["retry_attempt"] == 1
        assert (
            log_entry["error_type"] == "HTTPStatusError"
        )  # Story 6.1 classifier returns class name without module
        assert log_entry["is_transient"] is True

    async def test_schedule_retry_terminal_after_max_attempts(self, async_session):
        """Verify schedule_retry triggers terminal failure after 5 attempts (AC5)."""
        # Create task with 5 retry attempts already
        task = Task(
            id=uuid4(),
            channel_id=uuid4(),
            notion_page_id="test-page-id-3",
            title="Test Video",
            topic="Test",
            story_direction="Test story",
            retry_count=MAX_RETRY_ATTEMPTS,
            status=TaskStatus.ASSET_ERROR,
        )
        async_session.add(task)
        await async_session.commit()

        # Simulate transient failure (would normally retry)
        exception = httpx.HTTPStatusError(
            "Service unavailable",
            request=httpx.Request("GET", "https://api.example.com"),
            response=httpx.Response(503),
        )

        # Attempt to schedule retry (should trigger terminal failure)
        await schedule_retry(task.id, exception, async_session)
        await async_session.commit()
        await async_session.refresh(task)

        # Verify terminal failure
        assert task.retry_count == MAX_RETRY_ATTEMPTS
        assert task.next_retry_at is None  # No more retries
        assert task.status == TaskStatus.ASSET_ERROR  # Status unchanged

    async def test_schedule_retry_permanent_error_immediate_terminal(self, async_session):
        """Verify permanent error triggers immediate terminal failure."""
        # Create task
        task = Task(
            id=uuid4(),
            channel_id=uuid4(),
            notion_page_id="test-page-id-4",
            title="Test Video",
            topic="Test",
            story_direction="Test story",
            retry_count=0,
            status=TaskStatus.VIDEO_ERROR,
        )
        async_session.add(task)
        await async_session.commit()

        # Simulate permanent failure (400 Bad Request)
        exception = httpx.HTTPStatusError(
            "Bad request",
            request=httpx.Request("POST", "https://api.example.com"),
            response=httpx.Response(400),
        )

        # Attempt to schedule retry (should trigger terminal failure)
        await schedule_retry(task.id, exception, async_session)
        await async_session.commit()
        await async_session.refresh(task)

        # Verify terminal failure
        assert task.retry_count == MAX_RETRY_ATTEMPTS  # Marked as exhausted
        assert task.next_retry_at is None  # No retries scheduled
        assert task.status == TaskStatus.VIDEO_ERROR  # Status unchanged


@pytest.mark.asyncio
class TestClaimRetryTasks:
    """Integration tests for claim_retry_tasks polling."""

    async def test_claim_retry_tasks_returns_ready_tasks(self, async_session):
        """Verify claim_retry_tasks returns tasks where next_retry_at <= now."""
        # Create tasks with different retry timestamps
        past_retry = datetime.now(timezone.utc) - timedelta(minutes=5)
        future_retry = datetime.now(timezone.utc) + timedelta(minutes=5)

        task_ready = Task(
            id=uuid4(),
            channel_id=uuid4(),
            notion_page_id="ready-task",
            title="Ready Task",
            topic="Test",
            story_direction="Test story",
            retry_count=1,
            next_retry_at=past_retry,
            status=TaskStatus.ASSET_ERROR,
        )

        task_waiting = Task(
            id=uuid4(),
            channel_id=uuid4(),
            notion_page_id="waiting-task",
            title="Waiting Task",
            topic="Test",
            story_direction="Test story",
            retry_count=1,
            next_retry_at=future_retry,
            status=TaskStatus.VIDEO_ERROR,
        )

        async_session.add_all([task_ready, task_waiting])
        await async_session.commit()

        # Claim retry tasks
        claimed_tasks = await claim_retry_tasks(async_session)
        await async_session.commit()

        # Verify only ready task claimed
        assert len(claimed_tasks) == 1
        assert claimed_tasks[0].id == task_ready.id

    async def test_claim_retry_tasks_clears_next_retry_at(self, async_session):
        """Verify claim_retry_tasks clears next_retry_at and updates status."""
        # Create task ready for retry
        past_retry = datetime.now(timezone.utc) - timedelta(minutes=1)
        task = Task(
            id=uuid4(),
            channel_id=uuid4(),
            notion_page_id="claim-test-task",
            title="Claim Test",
            topic="Test",
            story_direction="Test story",
            retry_count=2,
            next_retry_at=past_retry,
            status=TaskStatus.AUDIO_ERROR,
        )
        async_session.add(task)
        await async_session.commit()

        # Claim retry tasks
        claimed_tasks = await claim_retry_tasks(async_session)
        await async_session.commit()

        # Verify task claimed and updated
        assert len(claimed_tasks) == 1
        claimed_task = claimed_tasks[0]
        assert claimed_task.next_retry_at is None  # Cleared
        assert claimed_task.status == TaskStatus.QUEUED  # Reset to queue for retry

    async def test_claim_retry_tasks_fifo_ordering(self, async_session):
        """Verify claim_retry_tasks processes oldest retry first (FIFO)."""
        # Create tasks with different retry timestamps
        older_retry = datetime.now(timezone.utc) - timedelta(minutes=10)
        newer_retry = datetime.now(timezone.utc) - timedelta(minutes=5)

        task_older = Task(
            id=uuid4(),
            channel_id=uuid4(),
            notion_page_id="older-task",
            title="Older Task",
            topic="Test",
            story_direction="Test story",
            retry_count=1,
            next_retry_at=older_retry,
            status=TaskStatus.ASSET_ERROR,
        )

        task_newer = Task(
            id=uuid4(),
            channel_id=uuid4(),
            notion_page_id="newer-task",
            title="Newer Task",
            topic="Test",
            story_direction="Test story",
            retry_count=1,
            next_retry_at=newer_retry,
            status=TaskStatus.VIDEO_ERROR,
        )

        async_session.add_all([task_newer, task_older])  # Add in reverse order
        await async_session.commit()

        # Claim retry tasks
        claimed_tasks = await claim_retry_tasks(async_session)
        await async_session.commit()

        # Verify older task claimed first
        assert len(claimed_tasks) == 2
        assert claimed_tasks[0].id == task_older.id  # FIFO - oldest first
        assert claimed_tasks[1].id == task_newer.id
