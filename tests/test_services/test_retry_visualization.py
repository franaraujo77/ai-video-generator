"""Tests for retry visualization data formatting (Story 6.9, Task 6).

This module tests that retry information is properly formatted for
Notion view display requirements:
- Error Log contains retry status for filtering (View 4: Retrying Tasks)
- Retry information is human-readable and contains "Attempt" keyword
- Different retry states are distinguishable (scheduled, in progress, exhausted)
- Countdown format supports sorting by next retry time
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models import PriorityLevel, TaskStatus
from app.services.notion_sync import TaskSyncData, push_task_to_notion


class TestRetryVisualizationDataFormat:
    """Test retry visualization data formatting for Notion views."""

    @pytest.mark.asyncio
    async def test_error_log_contains_attempt_keyword(self):
        """Verify Error Log contains 'Attempt' keyword for view filtering."""
        # Arrange - Task in retry with countdown
        next_retry = datetime.now(timezone.utc) + timedelta(minutes=5)
        task_sync = TaskSyncData(
            id=uuid4(),
            notion_page_id="test-page-filter",
            status=TaskStatus.ASSET_ERROR,
            priority=PriorityLevel.NORMAL,
            title="Test Video",
            updated_at=datetime.now(timezone.utc),
            retry_count=2,
            next_retry_at=next_retry,
            completed_steps=[],
            step_metadata={},
        )

        # Mock NotionClient
        notion_client = MagicMock()
        notion_client.update_page_properties = AsyncMock()

        # Act
        await push_task_to_notion(task_sync, notion_client, error_payload=None)

        # Assert - Error Log contains "Attempt" for view filtering
        notion_client.update_page_properties.assert_called_once()
        call_args = notion_client.update_page_properties.call_args
        properties = call_args[0][1]

        assert "Error Log" in properties
        error_log_content = properties["Error Log"]["rich_text"][0]["text"]["content"]
        assert (
            "Attempt" in error_log_content
        ), "Error Log must contain 'Attempt' keyword for view filtering"

    @pytest.mark.asyncio
    async def test_retry_status_shows_attempt_count(self):
        """Verify retry status shows current attempt count (e.g., 'Attempt 3/5')."""
        # Arrange - Task on third retry
        next_retry = datetime.now(timezone.utc) + timedelta(minutes=15)
        task_sync = TaskSyncData(
            id=uuid4(),
            notion_page_id="test-page-attempt-count",
            status=TaskStatus.VIDEO_ERROR,
            priority=PriorityLevel.NORMAL,
            title="Test Video",
            updated_at=datetime.now(timezone.utc),
            retry_count=3,
            next_retry_at=next_retry,
            max_retry_attempts=5,
            completed_steps=[],
            step_metadata={},
        )

        # Mock NotionClient
        notion_client = MagicMock()
        notion_client.update_page_properties = AsyncMock()

        # Act
        await push_task_to_notion(task_sync, notion_client, error_payload=None)

        # Assert - Shows "Attempt 3/5"
        call_args = notion_client.update_page_properties.call_args
        properties = call_args[0][1]
        error_log_content = properties["Error Log"]["rich_text"][0]["text"]["content"]

        assert (
            "Attempt 3/5" in error_log_content
        ), "Must show attempt count for grouping in Notion views"

    @pytest.mark.asyncio
    async def test_retry_status_shows_countdown_time(self):
        """Verify retry status shows countdown time for sorting by next retry."""
        # Arrange - Task with retry in 5 minutes
        next_retry = datetime.now(timezone.utc) + timedelta(minutes=5)
        task_sync = TaskSyncData(
            id=uuid4(),
            notion_page_id="test-page-countdown",
            status=TaskStatus.AUDIO_ERROR,
            priority=PriorityLevel.NORMAL,
            title="Test Video",
            updated_at=datetime.now(timezone.utc),
            retry_count=1,
            next_retry_at=next_retry,
            completed_steps=[],
            step_metadata={},
        )

        # Mock NotionClient
        notion_client = MagicMock()
        notion_client.update_page_properties = AsyncMock()

        # Act
        await push_task_to_notion(task_sync, notion_client, error_payload=None)

        # Assert - Shows time unit (min, hr, etc.)
        call_args = notion_client.update_page_properties.call_args
        properties = call_args[0][1]
        error_log_content = properties["Error Log"]["rich_text"][0]["text"]["content"]

        # Must contain time information for sorting/filtering
        assert any(
            unit in error_log_content for unit in ["min", "hr", "sec"]
        ), "Must show countdown time for sorting in Notion views"

    @pytest.mark.asyncio
    async def test_terminal_failure_distinguishable(self):
        """Verify terminal failures (no retry scheduled) are distinguishable."""
        # Arrange - Task with exhausted retries
        task_sync = TaskSyncData(
            id=uuid4(),
            notion_page_id="test-page-terminal",
            status=TaskStatus.VIDEO_ERROR,
            priority=PriorityLevel.NORMAL,
            title="Test Video",
            updated_at=datetime.now(timezone.utc),
            retry_count=5,  # Exhausted
            next_retry_at=None,  # No retry scheduled
            max_retry_attempts=5,
            completed_steps=[],
            step_metadata={},
        )

        # Mock NotionClient
        notion_client = MagicMock()
        notion_client.update_page_properties = AsyncMock()

        # Act
        await push_task_to_notion(task_sync, notion_client, error_payload=None)

        # Assert - No Error Log (terminal failures handled differently)
        call_args = notion_client.update_page_properties.call_args
        properties = call_args[0][1]

        # Terminal failures without next_retry_at don't get Error Log retry display
        # They should be filtered OUT of "Retrying Tasks" view
        assert (
            "Error Log" not in properties or properties.get("Error Log") is None
        ), "Terminal failures should not show in 'Retrying Tasks' view filter"

    @pytest.mark.asyncio
    async def test_retry_states_for_color_coding(self):
        """Verify different retry states can be distinguished for color coding."""
        # Test setup: Create tasks at different retry stages
        test_cases = [
            {
                "name": "early_retry",
                "retry_count": 1,
                "next_retry": datetime.now(timezone.utc) + timedelta(minutes=1),
                "expected_attempt": "Attempt 1/5",
                "color_suggestion": "yellow",  # Yellow for early retries
            },
            {
                "name": "mid_retry",
                "retry_count": 3,
                "next_retry": datetime.now(timezone.utc) + timedelta(minutes=15),
                "expected_attempt": "Attempt 3/5",
                "color_suggestion": "orange",  # Orange for mid retries
            },
            {
                "name": "last_retry",
                "retry_count": 5,
                "next_retry": datetime.now(timezone.utc) + timedelta(hours=1),
                "expected_attempt": "Attempt 5/5",
                "color_suggestion": "red",  # Red for last attempt
            },
        ]

        for case in test_cases:
            # Arrange
            task_sync = TaskSyncData(
                id=uuid4(),
                notion_page_id=f"test-page-{case['name']}",
                status=TaskStatus.ASSET_ERROR,
                priority=PriorityLevel.NORMAL,
                title=f"Test Video {case['name']}",
                updated_at=datetime.now(timezone.utc),
                retry_count=case["retry_count"],
                next_retry_at=case["next_retry"],
                max_retry_attempts=5,
                completed_steps=[],
                step_metadata={},
            )

            # Mock NotionClient
            notion_client = MagicMock()
            notion_client.update_page_properties = AsyncMock()

            # Act
            await push_task_to_notion(task_sync, notion_client, error_payload=None)

            # Assert - Verify attempt count for grouping/color coding
            call_args = notion_client.update_page_properties.call_args
            properties = call_args[0][1]
            error_log_content = properties["Error Log"]["rich_text"][0]["text"]["content"]

            assert (
                case["expected_attempt"] in error_log_content
            ), f"{case['name']}: Must show {case['expected_attempt']} for color coding"

    @pytest.mark.asyncio
    async def test_view_filter_simulation(self):
        """Verify tasks match the 'Retrying Tasks' view filter criteria."""
        # Arrange - Task that should appear in "Retrying Tasks" view
        next_retry = datetime.now(timezone.utc) + timedelta(minutes=10)
        task_sync = TaskSyncData(
            id=uuid4(),
            notion_page_id="test-page-view-filter",
            status=TaskStatus.ASSET_ERROR,  # Error status
            priority=PriorityLevel.NORMAL,
            title="Test Video",
            updated_at=datetime.now(timezone.utc),
            retry_count=2,
            next_retry_at=next_retry,
            completed_steps=[],
            step_metadata={},
        )

        # Mock NotionClient
        notion_client = MagicMock()
        notion_client.update_page_properties = AsyncMock()

        # Act
        await push_task_to_notion(task_sync, notion_client, error_payload=None)

        # Assert - Verify view filter criteria are met
        call_args = notion_client.update_page_properties.call_args
        properties = call_args[0][1]

        # View filter criteria:
        # 1. Status is one of error states (Asset Error, Video Error, etc.)
        assert task_sync.status in [
            TaskStatus.ASSET_ERROR,
            TaskStatus.VIDEO_ERROR,
            TaskStatus.AUDIO_ERROR,
            TaskStatus.UPLOAD_ERROR,
        ], "Task must be in error status"

        # 2. Error Log contains "Attempt" keyword
        error_log_content = properties["Error Log"]["rich_text"][0]["text"]["content"]
        assert "Attempt" in error_log_content, "Error Log must contain 'Attempt' for view filter"

        # 3. Next retry is scheduled (distinguishes from terminal failures)
        assert task_sync.next_retry_at is not None, "Must have next_retry_at scheduled"
