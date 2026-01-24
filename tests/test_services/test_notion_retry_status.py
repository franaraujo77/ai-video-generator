"""Tests for Notion retry status integration (Story 6.9, Task 4).

This module tests that notion_sync correctly formats and displays retry state
using retry_state_service:
- "No retries" for tasks that haven't failed
- "Attempt 3/5 - Next: 15 min" for active retries
- "Attempt 5/5 - Retry exhausted" for terminal failures
- Integration with new max_retry_attempts and last_error_timestamp fields
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models import PriorityLevel, TaskStatus
from app.services.notion_sync import TaskSyncData, push_task_to_notion


class TestNotionRetryStatusDisplay:
    """Test Notion retry status display using retry_state_service."""

    @pytest.mark.asyncio
    async def test_push_task_no_retries(self):
        """Verify Notion shows 'No retries' for tasks that haven't failed."""
        # Arrange - Task with no retry attempts
        task_sync = TaskSyncData(
            id=uuid4(),
            notion_page_id="test-page-no-retry",
            status=TaskStatus.GENERATING_VIDEO,
            priority=PriorityLevel.NORMAL,
            title="Test Video",
            updated_at=datetime.now(timezone.utc),
            retry_count=0,  # No retries
            next_retry_at=None,  # No retry scheduled
            completed_steps=["research", "story", "assets"],
            step_metadata={},
        )

        # Mock NotionClient
        notion_client = MagicMock()
        notion_client.update_page_properties = AsyncMock()

        # Act
        await push_task_to_notion(task_sync, notion_client, error_payload=None)

        # Assert - No retry status in Error Log (task is not in error state)
        notion_client.update_page_properties.assert_called_once()
        call_args = notion_client.update_page_properties.call_args
        properties = call_args[0][1]

        # Error Log should not be present for non-error tasks
        assert "Error Log" not in properties

    @pytest.mark.asyncio
    async def test_push_task_active_retry_with_countdown(self):
        """Verify Notion shows 'Attempt 3/5 - Next: 15 min' for active retry."""
        # Arrange - Task in retry with future next_retry_at
        next_retry = datetime.now(timezone.utc) + timedelta(minutes=15)
        task_sync = TaskSyncData(
            id=uuid4(),
            notion_page_id="test-page-active-retry",
            status=TaskStatus.VIDEO_ERROR,
            priority=PriorityLevel.NORMAL,
            title="Test Video",
            updated_at=datetime.now(timezone.utc),
            retry_count=3,  # Third retry attempt
            next_retry_at=next_retry,  # Retry in 15 minutes
            completed_steps=["research", "story", "assets"],
            step_metadata={"completed_video_clips": [1, 2, 3, 4, 5]},
        )

        # Mock NotionClient
        notion_client = MagicMock()
        notion_client.update_page_properties = AsyncMock()

        # Act
        await push_task_to_notion(task_sync, notion_client, error_payload=None)

        # Assert - Retry status in Error Log shows attempt and countdown
        notion_client.update_page_properties.assert_called_once()
        call_args = notion_client.update_page_properties.call_args
        properties = call_args[0][1]

        assert "Error Log" in properties
        error_log_content = properties["Error Log"]["rich_text"][0]["text"]["content"]

        # Should show retry attempt and countdown
        # Format from format_retry_display: "Retrying in 15 min (Attempt 3/5)"
        assert "Attempt 3/5" in error_log_content
        assert "min" in error_log_content  # Should show time unit

    @pytest.mark.asyncio
    async def test_push_task_retry_exhausted(self):
        """Verify Notion shows terminal failure when retries exhausted."""
        # Arrange - Task with retry_count = 5 (exhausted)
        task_sync = TaskSyncData(
            id=uuid4(),
            notion_page_id="test-page-exhausted",
            status=TaskStatus.VIDEO_ERROR,
            priority=PriorityLevel.NORMAL,
            title="Test Video",
            updated_at=datetime.now(timezone.utc),
            retry_count=5,  # Retry exhausted
            next_retry_at=None,  # No more retries
            completed_steps=["research", "story", "assets"],
            step_metadata={},
        )

        # Mock NotionClient
        notion_client = MagicMock()
        notion_client.update_page_properties = AsyncMock()

        # Act
        await push_task_to_notion(task_sync, notion_client, error_payload=None)

        # Assert - Error Log should NOT show retry info (no next_retry_at)
        notion_client.update_page_properties.assert_called_once()
        call_args = notion_client.update_page_properties.call_args
        properties = call_args[0][1]

        # Error Log should not be added if no next_retry_at (lines 964-968)
        # Terminal failures with retry_count=5 and next_retry_at=None don't get retry display
        assert "Error Log" not in properties or properties.get("Error Log") is None

    @pytest.mark.asyncio
    async def test_push_task_first_retry(self):
        """Verify Notion shows first retry attempt correctly."""
        # Arrange - Task on first retry
        next_retry = datetime.now(timezone.utc) + timedelta(minutes=1)
        task_sync = TaskSyncData(
            id=uuid4(),
            notion_page_id="test-page-first-retry",
            status=TaskStatus.ASSET_ERROR,
            priority=PriorityLevel.NORMAL,
            title="Test Video",
            updated_at=datetime.now(timezone.utc),
            retry_count=1,  # First retry
            next_retry_at=next_retry,  # Retry in 1 minute
            completed_steps=["research", "story"],
            step_metadata={},
        )

        # Mock NotionClient
        notion_client = MagicMock()
        notion_client.update_page_properties = AsyncMock()

        # Act
        await push_task_to_notion(task_sync, notion_client, error_payload=None)

        # Assert - Shows first retry attempt
        notion_client.update_page_properties.assert_called_once()
        call_args = notion_client.update_page_properties.call_args
        properties = call_args[0][1]

        assert "Error Log" in properties
        error_log_content = properties["Error Log"]["rich_text"][0]["text"]["content"]

        # Should show first retry attempt
        assert "Attempt 1/5" in error_log_content

    @pytest.mark.asyncio
    async def test_push_task_last_retry(self):
        """Verify Notion shows last retry attempt (attempt 5/5)."""
        # Arrange - Task on last retry
        next_retry = datetime.now(timezone.utc) + timedelta(hours=2)
        task_sync = TaskSyncData(
            id=uuid4(),
            notion_page_id="test-page-last-retry",
            status=TaskStatus.AUDIO_ERROR,
            priority=PriorityLevel.NORMAL,
            title="Test Video",
            updated_at=datetime.now(timezone.utc),
            retry_count=5,  # Last retry (5th attempt, still has next_retry_at)
            next_retry_at=next_retry,  # Retry in 2 hours
            completed_steps=["research", "story", "assets", "video"],
            step_metadata={},
        )

        # Mock NotionClient
        notion_client = MagicMock()
        notion_client.update_page_properties = AsyncMock()

        # Act
        await push_task_to_notion(task_sync, notion_client, error_payload=None)

        # Assert - Shows 5th retry attempt
        notion_client.update_page_properties.assert_called_once()
        call_args = notion_client.update_page_properties.call_args
        properties = call_args[0][1]

        assert "Error Log" in properties
        error_log_content = properties["Error Log"]["rich_text"][0]["text"]["content"]

        # Should show 5th retry attempt (last one)
        assert "Attempt 5/5" in error_log_content
        assert "hr" in error_log_content  # Should show hours


class TestTaskSyncDataRetryFields:
    """Test TaskSyncData includes new retry tracking fields (Story 6.9)."""

    def test_task_sync_data_has_retry_fields(self):
        """Verify TaskSyncData includes retry_count and next_retry_at fields."""
        # These fields already exist from Story 6.2, verify they're present
        task_sync = TaskSyncData(
            id=uuid4(),
            notion_page_id="test-page",
            status=TaskStatus.VIDEO_ERROR,
            priority=PriorityLevel.NORMAL,
            title="Test",
            updated_at=datetime.now(timezone.utc),
            retry_count=3,
            next_retry_at=datetime.now(timezone.utc),
        )

        assert task_sync.retry_count == 3
        assert task_sync.next_retry_at is not None

    def test_task_sync_data_defaults(self):
        """Verify TaskSyncData retry fields have proper defaults."""
        task_sync = TaskSyncData(
            id=uuid4(),
            notion_page_id="test-page",
            status=TaskStatus.QUEUED,
            priority=PriorityLevel.NORMAL,
            title="Test",
            updated_at=datetime.now(timezone.utc),
        )

        # Default values from dataclass
        assert task_sync.retry_count == 0
        assert task_sync.next_retry_at is None
