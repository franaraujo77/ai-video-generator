"""Tests for retry logging integration (Story 6.9, Task 7).

This module tests that retry events are properly logged with correlation IDs
and retry history is formatted for Notion display:
- log_retry_started event when worker begins retry processing
- log_retry_succeeded event when retry succeeds
- log_retry_failed event when retry fails but can retry again
- format_retry_history builds human-readable history
- Retry history included in Notion Error Log property
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models import PriorityLevel, TaskStatus
from app.services.error_logger import (
    format_retry_history,
    log_retry_failed,
    log_retry_started,
    log_retry_succeeded,
)
from app.services.notion_sync import TaskSyncData, push_task_to_notion


class TestRetryEventLogging:
    """Test retry event logging functions."""

    @pytest.mark.asyncio
    async def test_log_retry_started_includes_all_context(self):
        """Verify log_retry_started includes task, correlation, and step context."""
        task_id = uuid4()
        correlation_id = uuid4()

        with patch("app.services.error_logger.log") as mock_log:
            await log_retry_started(
                task_id=task_id,
                correlation_id=correlation_id,
                channel_id="poke1",
                retry_attempt=3,
                step_name="video_generation",
            )

            # Verify log.info called with correct event
            mock_log.info.assert_called_once()
            call_args = mock_log.info.call_args
            assert call_args[0][0] == "task_retry_started"

            # Verify all required fields present
            kwargs = call_args[1]
            assert kwargs["task_id"] == str(task_id)
            assert kwargs["correlation_id"] == str(correlation_id)
            assert kwargs["channel_id"] == "poke1"
            assert kwargs["retry_attempt"] == 3
            assert kwargs["step_name"] == "video_generation"
            assert "timestamp" in kwargs
            assert "message" in kwargs

    @pytest.mark.asyncio
    async def test_log_retry_succeeded_includes_recovery_time(self):
        """Verify log_retry_succeeded includes recovery time metrics."""
        task_id = uuid4()
        correlation_id = uuid4()

        with patch("app.services.error_logger.log") as mock_log:
            await log_retry_succeeded(
                task_id=task_id,
                correlation_id=correlation_id,
                channel_id="poke1",
                retry_attempt=2,
                step_name="asset_generation",
                recovery_time_seconds=180.5,  # 3 minutes
            )

            # Verify log.info called with correct event
            mock_log.info.assert_called_once()
            call_args = mock_log.info.call_args
            assert call_args[0][0] == "task_retry_succeeded"

            # Verify recovery metrics present
            kwargs = call_args[1]
            assert kwargs["retry_attempt"] == 2
            assert kwargs["recovery_time_seconds"] == 180.5
            assert "recovered after" in kwargs["message"]

    @pytest.mark.asyncio
    async def test_log_retry_failed_distinguishes_retriable_vs_terminal(self):
        """Verify log_retry_failed shows if more retries remain."""
        task_id = uuid4()
        correlation_id = uuid4()

        # Test 1: Retriable failure (next_retry_at set)
        next_retry = datetime.now(timezone.utc) + timedelta(minutes=15)
        with patch("app.services.error_logger.log") as mock_log:
            await log_retry_failed(
                task_id=task_id,
                correlation_id=correlation_id,
                channel_id="poke1",
                retry_attempt=3,
                step_name="video_generation",
                error_type="KlingAPITimeout",
                error_message="Request timed out after 600s",
                next_retry_at=next_retry,
            )

            kwargs = mock_log.warning.call_args[1]
            assert "will retry" in kwargs["message"]
            assert kwargs["next_retry_at"] == next_retry.isoformat()

        # Test 2: Terminal failure (no next_retry_at)
        with patch("app.services.error_logger.log") as mock_log:
            await log_retry_failed(
                task_id=task_id,
                correlation_id=correlation_id,
                channel_id="poke1",
                retry_attempt=5,
                step_name="video_generation",
                error_type="KlingAPITimeout",
                error_message="Request timed out after 600s",
                next_retry_at=None,  # Terminal
            )

            kwargs = mock_log.warning.call_args[1]
            assert "no more retries" in kwargs["message"]
            assert kwargs["next_retry_at"] is None

    @pytest.mark.asyncio
    async def test_correlation_id_preserved_across_retry_events(self):
        """Verify same correlation_id used across all retry events."""
        task_id = uuid4()
        correlation_id = uuid4()  # Same correlation_id for all events

        with patch("app.services.error_logger.log") as mock_log:
            # Event 1: Retry started
            await log_retry_started(
                task_id=task_id,
                correlation_id=correlation_id,
                channel_id="poke1",
                retry_attempt=2,
                step_name="video_generation",
            )
            assert mock_log.info.call_args[1]["correlation_id"] == str(correlation_id)

            # Event 2: Retry failed
            await log_retry_failed(
                task_id=task_id,
                correlation_id=correlation_id,
                channel_id="poke1",
                retry_attempt=2,
                step_name="video_generation",
                error_type="KlingAPITimeout",
                error_message="Timeout",
                next_retry_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            )
            assert mock_log.warning.call_args[1]["correlation_id"] == str(correlation_id)

            # Event 3: Retry succeeded (after another attempt)
            await log_retry_succeeded(
                task_id=task_id,
                correlation_id=correlation_id,
                channel_id="poke1",
                retry_attempt=3,
                step_name="video_generation",
                recovery_time_seconds=900.0,
            )
            assert mock_log.info.call_args[1]["correlation_id"] == str(correlation_id)


class TestRetryHistoryFormatting:
    """Test retry history formatting for Notion display."""

    def test_format_retry_history_no_retries(self):
        """Verify format_retry_history shows 'No retry history' for fresh tasks."""
        history = format_retry_history(
            retry_attempt=0,
            last_error_timestamp=None,
            next_retry_at=None,
        )

        assert history == "No retry history"

    def test_format_retry_history_active_retry(self):
        """Verify format_retry_history shows attempt, last error, and next retry."""
        last_error = datetime(2026, 1, 23, 14, 30, 0, tzinfo=timezone.utc)
        next_retry = datetime(2026, 1, 23, 14, 45, 0, tzinfo=timezone.utc)

        history = format_retry_history(
            retry_attempt=3,
            last_error_timestamp=last_error,
            next_retry_at=next_retry,
            error_message="API timeout",
        )

        assert "Retry History:" in history
        assert "Attempt 3/5" in history
        assert "Last error: 2026-01-23 14:30:00 (API timeout)" in history
        assert "Next retry: 2026-01-23 14:45:00" in history
        assert "in" in history  # Countdown present

    def test_format_retry_history_terminal_failure(self):
        """Verify format_retry_history shows terminal status after exhaustion."""
        last_error = datetime(2026, 1, 23, 15, 0, 0, tzinfo=timezone.utc)

        history = format_retry_history(
            retry_attempt=5,  # Exhausted
            last_error_timestamp=last_error,
            next_retry_at=None,  # No more retries
            error_message="API timeout",
        )

        assert "Attempt 5/5" in history
        assert "Last error: 2026-01-23 15:00:00 (API timeout)" in history
        assert "Status: Terminal failure" in history
        assert "Next retry" not in history  # No retry scheduled

    def test_format_retry_history_without_error_message(self):
        """Verify format_retry_history works without optional error message."""
        last_error = datetime(2026, 1, 23, 14, 30, 0, tzinfo=timezone.utc)
        next_retry = datetime(2026, 1, 23, 14, 35, 0, tzinfo=timezone.utc)

        history = format_retry_history(
            retry_attempt=1,
            last_error_timestamp=last_error,
            next_retry_at=next_retry,
            error_message=None,  # No message
        )

        assert "Attempt 1/5" in history
        assert "Last error: 2026-01-23 14:30:00" in history
        assert "API timeout" not in history  # No error message included
        assert "Next retry:" in history


class TestNotionSyncRetryHistory:
    """Test retry history integration with Notion sync."""

    @pytest.mark.asyncio
    async def test_notion_sync_includes_retry_history(self):
        """Verify Notion sync includes detailed retry history in Error Log."""
        last_error = datetime.now(timezone.utc) - timedelta(minutes=10)
        next_retry = datetime.now(timezone.utc) + timedelta(minutes=5)

        task_sync = TaskSyncData(
            id=uuid4(),
            notion_page_id="test-page-retry-history",
            status=TaskStatus.VIDEO_ERROR,
            priority=PriorityLevel.NORMAL,
            title="Test Video",
            updated_at=datetime.now(timezone.utc),
            retry_count=3,
            next_retry_at=next_retry,
            max_retry_attempts=5,
            last_error_timestamp=last_error,
            completed_steps=[],
            step_metadata={},
        )

        # Mock NotionClient
        notion_client = MagicMock()
        notion_client.update_page_properties = AsyncMock()

        # Act
        await push_task_to_notion(task_sync, notion_client, error_payload=None)

        # Assert - Verify retry history in Error Log
        call_args = notion_client.update_page_properties.call_args
        properties = call_args[0][1]

        assert "Error Log" in properties
        error_log_content = properties["Error Log"]["rich_text"][0]["text"]["content"]

        # Should include both summary and detailed history
        assert "Retrying in" in error_log_content  # Summary
        assert "Retry History:" in error_log_content  # Detailed history
        assert "Attempt 3/5" in error_log_content
        assert "Last error:" in error_log_content
        assert "Next retry:" in error_log_content

    @pytest.mark.asyncio
    async def test_notion_sync_retry_history_terminal_failure(self):
        """Verify Notion sync excludes terminal failures from Error Log (no ErrorPayload).

        Terminal failures without ErrorPayload should NOT have Error Log property.
        This filters them OUT of "Retrying Tasks" view (Story 6.9, View 4 filter).

        Note: Terminal failures WITH ErrorPayload (rich error details) will still have
        Error Log through the ErrorPayload path, but that's tested separately.
        """
        last_error = datetime.now(timezone.utc) - timedelta(hours=1)

        task_sync = TaskSyncData(
            id=uuid4(),
            notion_page_id="test-page-terminal-history",
            status=TaskStatus.VIDEO_ERROR,
            priority=PriorityLevel.NORMAL,
            title="Test Video",
            updated_at=datetime.now(timezone.utc),
            retry_count=5,  # Exhausted
            next_retry_at=None,  # No more retries
            max_retry_attempts=5,
            last_error_timestamp=last_error,
            completed_steps=[],
            step_metadata={},
        )

        # Mock NotionClient
        notion_client = MagicMock()
        notion_client.update_page_properties = AsyncMock()

        # Act
        await push_task_to_notion(task_sync, notion_client, error_payload=None)

        # Assert - Terminal failures (no ErrorPayload) should NOT have Error Log
        # This filters them OUT of "Retrying Tasks" view
        call_args = notion_client.update_page_properties.call_args
        properties = call_args[0][1]

        assert "Error Log" not in properties or properties.get("Error Log") is None, (
            "Terminal failures without ErrorPayload should not have Error Log (filtered from 'Retrying Tasks' view)"
        )

    @pytest.mark.asyncio
    async def test_notion_sync_no_retry_history_for_fresh_tasks(self):
        """Verify Notion sync omits retry history for tasks without retries."""
        task_sync = TaskSyncData(
            id=uuid4(),
            notion_page_id="test-page-no-history",
            status=TaskStatus.GENERATING_VIDEO,  # Not an error
            priority=PriorityLevel.NORMAL,
            title="Test Video",
            updated_at=datetime.now(timezone.utc),
            retry_count=0,  # No retries
            next_retry_at=None,
            max_retry_attempts=5,
            last_error_timestamp=None,
            completed_steps=[],
            step_metadata={},
        )

        # Mock NotionClient
        notion_client = MagicMock()
        notion_client.update_page_properties = AsyncMock()

        # Act
        await push_task_to_notion(task_sync, notion_client, error_payload=None)

        # Assert - No Error Log for fresh tasks
        call_args = notion_client.update_page_properties.call_args
        properties = call_args[0][1]

        # Fresh task shouldn't have Error Log property
        assert "Error Log" not in properties or properties.get("Error Log") is None
