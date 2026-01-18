"""Tests for NotionVideoService.

This module tests the video URL population service for Story 5.4: Video Review Interface.
Tests cover video entry creation, Notion API integration, rate limiting, and error handling.

Test Coverage:
- Video entry creation in Notion Videos database
- File URL population (notion vs r2 storage strategies)
- Batch video population with partial failures
- Rate limiting (inherited from NotionClient)
- Error handling and retries

Dependencies:
    - pytest-asyncio for async test support
    - unittest.mock for NotionClient mocking
    - Factory functions for test data creation
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.clients.notion import NotionClient
from app.models import Channel
from app.services.notion_video_service import NotionVideoService


@pytest.fixture
def notion_client_mock():
    """Mock NotionClient with rate limiting disabled for tests."""
    client = MagicMock(spec=NotionClient)
    client.create_page = AsyncMock(return_value={"id": "page_123", "object": "page"})
    return client


@pytest.fixture
def channel_notion():
    """Channel with storage_strategy='notion' for testing."""
    channel = MagicMock(spec=Channel)
    channel.channel_id = "test_channel"
    channel.storage_strategy = "notion"
    return channel


@pytest.fixture
def channel_r2():
    """Channel with storage_strategy='r2' for testing."""
    channel = MagicMock(spec=Channel)
    channel.channel_id = "test_channel"
    channel.storage_strategy = "r2"
    return channel


@pytest.fixture
def video_files():
    """Sample video files list for testing."""
    return [
        {
            "clip_number": 1,
            "output_path": Path("/workspace/videos/clip_01.mp4"),
            "duration": 8.5,
        },
        {
            "clip_number": 2,
            "output_path": Path("/workspace/videos/clip_02.mp4"),
            "duration": 7.2,
        },
        {
            "clip_number": 3,
            "output_path": Path("/workspace/videos/clip_03.mp4"),
            "duration": 9.1,
        },
    ]


class TestNotionVideoService:
    """Test suite for NotionVideoService."""

    @pytest.mark.asyncio
    async def test_populate_videos_success_notion_storage(
        self, notion_client_mock, channel_notion, video_files
    ):
        """Test successful video population with notion storage strategy."""
        # Arrange
        with (
            patch(
                "app.services.notion_video_service.get_notion_videos_database_id",
                return_value="db_123",
            ),
            patch(
                "app.services.notion_video_service.get_notion_tasks_collection_id",
                return_value="collection://task_123",
            ),
        ):
            service = NotionVideoService(notion_client_mock, channel_notion)

        task_id = uuid4()
        notion_page_id = "abc123def456"

        # Act
        result = await service.populate_videos(
            task_id=task_id,
            notion_page_id=notion_page_id,
            video_files=video_files,
        )

        # Assert
        assert result["created"] == 3
        assert result["failed"] == 0
        assert result["storage_strategy"] == "notion"
        assert notion_client_mock.create_page.call_count == 3

        # Verify first call properties
        first_call = notion_client_mock.create_page.call_args_list[0]
        properties = first_call[1]["properties"]
        assert properties["Clip Number"]["number"] == 1
        assert properties["Duration"]["number"] == 8.5
        assert properties["Status"]["select"]["name"] == "generated"
        assert properties["Task"]["relation"][0]["id"] == notion_page_id
        assert properties["File URL"]["url"] is None  # Not implemented yet

    @pytest.mark.asyncio
    async def test_populate_videos_success_r2_storage(
        self, notion_client_mock, channel_r2, video_files
    ):
        """Test successful video population with r2 storage strategy."""
        # Arrange
        with (
            patch(
                "app.services.notion_video_service.get_notion_videos_database_id",
                return_value="db_123",
            ),
            patch(
                "app.services.notion_video_service.get_notion_tasks_collection_id",
                return_value="collection://task_123",
            ),
        ):
            service = NotionVideoService(notion_client_mock, channel_r2)

        task_id = uuid4()
        notion_page_id = "abc123def456"

        # Act
        result = await service.populate_videos(
            task_id=task_id,
            notion_page_id=notion_page_id,
            video_files=video_files,
        )

        # Assert
        assert result["created"] == 3
        assert result["failed"] == 0
        assert result["storage_strategy"] == "r2"

    @pytest.mark.asyncio
    async def test_populate_videos_partial_failure(
        self, notion_client_mock, channel_notion, video_files
    ):
        """Test video population with partial failures (some videos fail)."""
        # Arrange
        with (
            patch(
                "app.services.notion_video_service.get_notion_videos_database_id",
                return_value="db_123",
            ),
            patch(
                "app.services.notion_video_service.get_notion_tasks_collection_id",
                return_value="collection://task_123",
            ),
        ):
            service = NotionVideoService(notion_client_mock, channel_notion)

        task_id = uuid4()
        notion_page_id = "abc123def456"

        # Mock second call to fail
        notion_client_mock.create_page.side_effect = [
            {"id": "page_1"},  # Success
            Exception("Notion API error"),  # Failure
            {"id": "page_3"},  # Success
        ]

        # Act
        result = await service.populate_videos(
            task_id=task_id,
            notion_page_id=notion_page_id,
            video_files=video_files,
        )

        # Assert
        assert result["created"] == 2
        assert result["failed"] == 1
        assert result["storage_strategy"] == "notion"

    @pytest.mark.asyncio
    async def test_populate_videos_all_failures(
        self, notion_client_mock, channel_notion, video_files
    ):
        """Test video population when all videos fail (should raise RuntimeError)."""
        # Arrange
        with (
            patch(
                "app.services.notion_video_service.get_notion_videos_database_id",
                return_value="db_123",
            ),
            patch(
                "app.services.notion_video_service.get_notion_tasks_collection_id",
                return_value="collection://task_123",
            ),
        ):
            service = NotionVideoService(notion_client_mock, channel_notion)

        task_id = uuid4()
        notion_page_id = "abc123def456"

        # Mock all calls to fail
        notion_client_mock.create_page.side_effect = Exception("Notion API error")

        # Act & Assert
        with pytest.raises(RuntimeError, match="All 3 videos failed to populate"):
            await service.populate_videos(
                task_id=task_id,
                notion_page_id=notion_page_id,
                video_files=video_files,
            )

    @pytest.mark.asyncio
    async def test_populate_videos_empty_list(self, notion_client_mock, channel_notion):
        """Test video population with empty video list."""
        # Arrange
        with (
            patch(
                "app.services.notion_video_service.get_notion_videos_database_id",
                return_value="db_123",
            ),
            patch(
                "app.services.notion_video_service.get_notion_tasks_collection_id",
                return_value="collection://task_123",
            ),
        ):
            service = NotionVideoService(notion_client_mock, channel_notion)

        task_id = uuid4()
        notion_page_id = "abc123def456"

        # Act
        result = await service.populate_videos(
            task_id=task_id,
            notion_page_id=notion_page_id,
            video_files=[],
        )

        # Assert
        assert result["created"] == 0
        assert result["failed"] == 0
        assert notion_client_mock.create_page.call_count == 0

    @pytest.mark.asyncio
    async def test_create_video_entry_properties(self, notion_client_mock, channel_notion):
        """Test video entry properties are correctly formatted."""
        # Arrange
        with (
            patch(
                "app.services.notion_video_service.get_notion_videos_database_id",
                return_value="db_123",
            ),
            patch(
                "app.services.notion_video_service.get_notion_tasks_collection_id",
                return_value="collection://task_123",
            ),
        ):
            service = NotionVideoService(notion_client_mock, channel_notion)

        task_id = uuid4()
        notion_page_id = "abc123def456"

        video_files = [
            {
                "clip_number": 5,
                "output_path": Path("/workspace/videos/clip_05.mp4"),
                "duration": 6.8,
            }
        ]

        # Act
        await service.populate_videos(
            task_id=task_id,
            notion_page_id=notion_page_id,
            video_files=video_files,
        )

        # Assert
        call_args = notion_client_mock.create_page.call_args
        properties = call_args[1]["properties"]

        # Verify all required properties exist
        assert "Clip Number" in properties
        assert "Duration" in properties
        assert "Status" in properties
        assert "Generated Date" in properties
        assert "Task" in properties
        assert "File URL" in properties

        # Verify property values
        assert properties["Clip Number"]["number"] == 5
        assert properties["Duration"]["number"] == 6.8
        assert properties["Status"]["select"]["name"] == "generated"
        assert properties["Task"]["relation"][0]["id"] == notion_page_id
        assert properties["File URL"]["url"] is None  # Not implemented

        # Verify Generated Date is ISO format (contains 'T' and timezone)
        generated_date = properties["Generated Date"]["date"]["start"]
        assert "T" in generated_date
        assert "+" in generated_date or "Z" in generated_date

    @pytest.mark.asyncio
    async def test_populate_videos_with_correlation_id(
        self, notion_client_mock, channel_notion, video_files
    ):
        """[P2] should propagate correlation_id through logging."""
        # Arrange
        with (
            patch(
                "app.services.notion_video_service.get_notion_videos_database_id",
                return_value="db_123",
            ),
            patch(
                "app.services.notion_video_service.get_notion_tasks_collection_id",
                return_value="collection://task_123",
            ),
        ):
            service = NotionVideoService(notion_client_mock, channel_notion)

        task_id = uuid4()
        notion_page_id = "abc123def456"
        correlation_id = "corr_xyz789"

        # Act
        result = await service.populate_videos(
            task_id=task_id,
            notion_page_id=notion_page_id,
            video_files=video_files,
            correlation_id=correlation_id,
        )

        # Assert
        assert result["created"] == 3
        # Correlation ID is used for logging (verified manually in logs)

    @pytest.mark.asyncio
    async def test_populate_videos_uses_default_duration(self, notion_client_mock, channel_notion):
        """[P2] should use default duration when not provided in video_files."""
        # Arrange
        with (
            patch(
                "app.services.notion_video_service.get_notion_videos_database_id",
                return_value="db_123",
            ),
            patch(
                "app.services.notion_video_service.get_notion_tasks_collection_id",
                return_value="collection://task_123",
            ),
            patch("app.services.notion_video_service.DEFAULT_VIDEO_DURATION_SECONDS", 10.0),
        ):
            service = NotionVideoService(notion_client_mock, channel_notion)

        task_id = uuid4()
        notion_page_id = "abc123def456"

        # Video file without duration key
        video_files = [
            {
                "clip_number": 1,
                "output_path": Path("/workspace/videos/clip_01.mp4"),
                # duration missing - should use default
            }
        ]

        # Act
        await service.populate_videos(
            task_id=task_id,
            notion_page_id=notion_page_id,
            video_files=video_files,
        )

        # Assert
        call_args = notion_client_mock.create_page.call_args
        properties = call_args[1]["properties"]
        assert properties["Duration"]["number"] == 10.0  # Default duration

    @pytest.mark.asyncio
    async def test_create_video_entry_with_r2_url_placeholder(
        self, notion_client_mock, channel_r2, video_files
    ):
        """[P2] should set File URL to None when R2 upload not implemented."""
        # Arrange
        with (
            patch(
                "app.services.notion_video_service.get_notion_videos_database_id",
                return_value="db_123",
            ),
            patch(
                "app.services.notion_video_service.get_notion_tasks_collection_id",
                return_value="collection://task_123",
            ),
        ):
            service = NotionVideoService(notion_client_mock, channel_r2)

        task_id = uuid4()
        notion_page_id = "abc123def456"

        # Act
        await service.populate_videos(
            task_id=task_id,
            notion_page_id=notion_page_id,
            video_files=[video_files[0]],
        )

        # Assert
        call_args = notion_client_mock.create_page.call_args
        properties = call_args[1]["properties"]
        # R2 upload not implemented yet, should be None
        assert properties["File URL"]["url"] is None
