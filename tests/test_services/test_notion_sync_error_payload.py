"""Tests for Notion sync ErrorPayload integration (Story 6.4, Task 5).

This module tests that notion_sync correctly formats and pushes ErrorPayload
to Notion's Error Log field, providing users with rich error context including:
- Failure location (clip/asset index)
- Error category and API service
- Retry scheduling information
- Checkpoint progress
- Actionable recommendations

Test Coverage:
    - push_task_to_notion with ErrorPayload parameter
    - ErrorPayload markdown formatting for Notion
    - Error Log field population
    - push_error_payload_to_notion helper function
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models import PriorityLevel, Task, TaskStatus
from app.schemas.error_payload import ErrorPayload, FailureLocation
from app.services.notion_sync import (
    TaskSyncData,
    push_error_payload_to_notion,
    push_task_to_notion,
)


class TestPushTaskToNotionWithErrorPayload:
    """Test push_task_to_notion with ErrorPayload parameter."""

    @pytest.mark.asyncio
    async def test_push_task_with_error_payload_video_generation(self):
        """Verify push_task_to_notion formats ErrorPayload for Notion Error Log field."""
        # Arrange
        task_sync = TaskSyncData(
            id=uuid4(),
            notion_page_id="test-page-id-123",
            status=TaskStatus.VIDEO_ERROR,
            priority=PriorityLevel.NORMAL,
            title="Test Video",
            updated_at=datetime.now(timezone.utc),
            retry_count=2,
            next_retry_at=datetime.now(timezone.utc),
            completed_steps=["research", "story", "assets"],
            step_metadata={"completed_video_clips": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]},
        )

        error_payload = ErrorPayload(
            timestamp=datetime.now(timezone.utc),
            correlation_id=task_sync.id,
            step_name="video_generation",
            failure_location=FailureLocation(
                step_name="video_generation",
                item_index=11,
                total_items=18,
            ),
            error_category="TRANSIENT",
            error_message="HTTP 429: Rate limited by KIE.ai",
            api_service="KIE.ai",
            retry_attempt=2,
            next_retry_at=datetime.now(timezone.utc),
            partial_progress={
                "completed_video_clips": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                "total_clips": 18,
            },
            recommendation="Rate limit encountered - retry with exponential backoff",
        )

        # Mock NotionClient
        notion_client = MagicMock()
        notion_client.update_page_properties = AsyncMock()

        # Act
        await push_task_to_notion(task_sync, notion_client, error_payload)

        # Assert - Notion API called with ErrorPayload markdown
        notion_client.update_page_properties.assert_called_once()
        call_args = notion_client.update_page_properties.call_args
        page_id = call_args[0][0]
        properties = call_args[0][1]

        assert page_id == "test-page-id-123"
        assert "Error Log" in properties
        error_log_content = properties["Error Log"]["rich_text"][0]["text"]["content"]

        # Verify ErrorPayload markdown format
        assert "video_generation failed" in error_log_content
        assert "Item 11 of 18" in error_log_content
        assert "TRANSIENT" in error_log_content
        assert "KIE.ai" in error_log_content
        assert "10 of 18 clips completed" in error_log_content
        assert "Rate limit encountered" in error_log_content

    @pytest.mark.asyncio
    async def test_push_task_with_error_payload_asset_generation(self):
        """Verify push_task_to_notion formats asset generation ErrorPayload."""
        # Arrange
        task_sync = TaskSyncData(
            id=uuid4(),
            notion_page_id="test-page-id-456",
            status=TaskStatus.ASSET_ERROR,
            priority=PriorityLevel.NORMAL,
            title="Test Video",
            updated_at=datetime.now(timezone.utc),
            retry_count=1,
            next_retry_at=datetime.now(timezone.utc),
            completed_steps=["research", "story"],
            step_metadata={"completed_assets": [1, 2, 3, 4, 5], "total_assets": 22},
        )

        error_payload = ErrorPayload(
            timestamp=datetime.now(timezone.utc),
            correlation_id=task_sync.id,
            step_name="asset_generation",
            failure_location=FailureLocation(
                step_name="asset_generation",
                item_index=6,
                total_items=22,
                item_name="environment_background_3.png",
            ),
            error_category="CONFIGURATION",
            error_message="HTTP 401: Unauthorized - Gemini API key invalid",
            api_service="Gemini",
            retry_attempt=1,
            next_retry_at=None,  # Terminal failure
            partial_progress={"completed_assets": [1, 2, 3, 4, 5], "total_assets": 22},
            recommendation="Check Gemini API key configuration",
        )

        # Mock NotionClient
        notion_client = MagicMock()
        notion_client.update_page_properties = AsyncMock()

        # Act
        await push_task_to_notion(task_sync, notion_client, error_payload)

        # Assert - ErrorPayload includes asset name
        call_args = notion_client.update_page_properties.call_args
        properties = call_args[0][1]
        error_log_content = properties["Error Log"]["rich_text"][0]["text"]["content"]

        assert "asset_generation failed" in error_log_content
        assert "Item 6 of 22 (environment_background_3.png)" in error_log_content
        assert "CONFIGURATION" in error_log_content
        assert "Gemini" in error_log_content
        assert "5 of 22 assets completed" in error_log_content
        assert "Check Gemini API key" in error_log_content
        assert "Terminal failure" in error_log_content  # No retry scheduled

    @pytest.mark.asyncio
    async def test_push_task_without_error_payload_fallback(self):
        """Verify push_task_to_notion falls back to simple retry display without ErrorPayload."""
        # Arrange
        next_retry = datetime.now(timezone.utc)
        task_sync = TaskSyncData(
            id=uuid4(),
            notion_page_id="test-page-id-789",
            status=TaskStatus.VIDEO_ERROR,
            priority=PriorityLevel.NORMAL,
            title="Test Video",
            updated_at=datetime.now(timezone.utc),
            retry_count=3,
            next_retry_at=next_retry,
            completed_steps=["research", "story", "assets"],
            step_metadata={},
        )

        # Mock NotionClient
        notion_client = MagicMock()
        notion_client.update_page_properties = AsyncMock()

        # Act - No ErrorPayload provided
        await push_task_to_notion(task_sync, notion_client, error_payload=None)

        # Assert - Falls back to simple retry display
        call_args = notion_client.update_page_properties.call_args
        properties = call_args[0][1]
        error_log_content = properties["Error Log"]["rich_text"][0]["text"]["content"]

        # Should show simple retry format from Story 6.2
        assert "Retrying" in error_log_content or "Attempt" in error_log_content
        assert "3/5" in error_log_content  # Retry count


class TestPushErrorPayloadToNotion:
    """Test push_error_payload_to_notion helper function."""

    @pytest.mark.asyncio
    async def test_push_error_payload_to_notion_success(self, async_session):
        """Verify push_error_payload_to_notion loads task and syncs to Notion."""
        # Arrange
        task_id = uuid4()
        task = Task(
            id=task_id,
            channel_id=uuid4(),
            notion_page_id="test-page-id",
            title="Test Video",
            topic="Test",
            story_direction="Test story",
            status=TaskStatus.VIDEO_ERROR,
            retry_count=2,
            completed_steps=["research", "story", "assets"],
            step_metadata={"completed_video_clips": [1, 2, 3, 4, 5]},
        )
        async_session.add(task)
        await async_session.commit()

        error_payload = ErrorPayload(
            timestamp=datetime.now(timezone.utc),
            correlation_id=task_id,
            step_name="video_generation",
            failure_location=FailureLocation(
                step_name="video_generation",
                item_index=6,
                total_items=18,
            ),
            error_category="TRANSIENT",
            error_message="KIE.ai timeout",
            api_service="KIE.ai",
            retry_attempt=2,
            next_retry_at=datetime.now(timezone.utc),
            partial_progress={"completed_video_clips": [1, 2, 3, 4, 5], "total_clips": 18},
            recommendation="Video generation timeout - retry in progress",
        )

        # Mock NotionClient
        notion_client = MagicMock()
        notion_client.update_page_properties = AsyncMock()

        # Act
        with patch("app.services.notion_sync.async_session_factory", return_value=async_session):
            await push_error_payload_to_notion(task_id, error_payload, notion_client)

        # Assert - Notion API called with ErrorPayload
        notion_client.update_page_properties.assert_called_once()
        call_args = notion_client.update_page_properties.call_args
        properties = call_args[0][1]

        assert "Error Log" in properties
        error_log_content = properties["Error Log"]["rich_text"][0]["text"]["content"]
        assert "video_generation failed" in error_log_content
        assert "Item 6 of 18" in error_log_content

    @pytest.mark.asyncio
    async def test_push_error_payload_to_notion_task_not_found(self, async_session):
        """Verify push_error_payload_to_notion handles missing task gracefully."""
        # Arrange
        nonexistent_task_id = uuid4()
        error_payload = ErrorPayload(
            timestamp=datetime.now(timezone.utc),
            correlation_id=nonexistent_task_id,
            step_name="video_generation",
            failure_location=FailureLocation(step_name="video_generation"),
            error_category="TRANSIENT",
            error_message="Test error",
            api_service="KIE.ai",
            retry_attempt=1,
        )

        notion_client = MagicMock()
        notion_client.update_page_properties = AsyncMock()

        # Act
        with patch("app.services.notion_sync.async_session_factory", return_value=async_session):
            await push_error_payload_to_notion(nonexistent_task_id, error_payload, notion_client)

        # Assert - No Notion API call made (fire-and-forget pattern)
        notion_client.update_page_properties.assert_not_called()
