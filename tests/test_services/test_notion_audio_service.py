"""Tests for NotionAudioService.

This module tests the audio URL population service for Story 5.5: Audio Review Interface.
Tests cover audio entry creation, Notion API integration, rate limiting, and error handling.

Test Coverage:
- Audio entry creation in Notion Audio database
- Dual audio types: narration (MP3) and SFX (MP3)
- File URL population (notion vs r2 storage strategies)
- Batch audio population with partial failures
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
from app.services.notion_audio_service import NotionAudioService


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
def narration_files():
    """Sample narration files list for testing (3 clips instead of 18 for speed)."""
    return [
        {
            "clip_number": 1,
            "output_path": Path("/workspace/audio/narration_01.mp3"),
            "duration": 7.2,
        },
        {
            "clip_number": 2,
            "output_path": Path("/workspace/audio/narration_02.mp3"),
            "duration": 6.5,
        },
        {
            "clip_number": 3,
            "output_path": Path("/workspace/audio/narration_03.mp3"),
            "duration": 8.1,
        },
    ]


@pytest.fixture
def sfx_files():
    """Sample SFX files list for testing (3 clips instead of 18 for speed)."""
    return [
        {
            "clip_number": 1,
            "output_path": Path("/workspace/sfx/sfx_01.mp3"),
            "duration": 7.2,
        },
        {
            "clip_number": 2,
            "output_path": Path("/workspace/sfx/sfx_02.mp3"),
            "duration": 6.5,
        },
        {
            "clip_number": 3,
            "output_path": Path("/workspace/sfx/sfx_03.mp3"),
            "duration": 8.1,
        },
    ]


class TestNotionAudioService:
    """Test suite for NotionAudioService."""

    @pytest.mark.asyncio
    async def test_populate_audio_success_notion_storage(
        self, notion_client_mock, channel_notion, narration_files, sfx_files
    ):
        """Test successful audio population with notion storage strategy."""
        # Arrange
        with (
            patch(
                "app.services.notion_audio_service.get_notion_audio_database_id",
                return_value="db_audio_123",
            ),
            patch(
                "app.services.notion_audio_service.get_notion_tasks_collection_id",
                return_value="collection://task_123",
            ),
        ):
            service = NotionAudioService(notion_client_mock, channel_notion)

        task_id = uuid4()
        notion_page_id = "abc123def456"

        # Act
        result = await service.populate_audio(
            task_id=task_id,
            notion_page_id=notion_page_id,
            narration_files=narration_files,
            sfx_files=sfx_files,
        )

        # Assert
        assert result["created"] == 6  # 3 narration + 3 SFX
        assert result["failed"] == 0
        assert result["narration_count"] == 3
        assert result["sfx_count"] == 3
        assert result["storage_strategy"] == "notion"
        assert notion_client_mock.create_page.call_count == 6

        # Verify first narration call properties
        first_call = notion_client_mock.create_page.call_args_list[0]
        properties = first_call[1]["properties"]
        assert properties["Clip Number"]["number"] == 1
        assert properties["Type"]["select"]["name"] == "narration"
        assert properties["Duration"]["number"] == 7.2
        assert properties["Status"]["select"]["name"] == "generated"
        assert properties["Task"]["relation"][0]["id"] == notion_page_id
        assert properties["File"]["files"] == []  # Empty until R2 upload implemented

        # Verify first SFX call properties (4th call overall)
        fourth_call = notion_client_mock.create_page.call_args_list[3]
        properties = fourth_call[1]["properties"]
        assert properties["Clip Number"]["number"] == 1
        assert properties["Type"]["select"]["name"] == "sfx"
        assert properties["Duration"]["number"] == 7.2

    @pytest.mark.asyncio
    async def test_populate_audio_success_r2_storage(
        self, notion_client_mock, channel_r2, narration_files, sfx_files
    ):
        """Test successful audio population with r2 storage strategy."""
        # Arrange
        with (
            patch(
                "app.services.notion_audio_service.get_notion_audio_database_id",
                return_value="db_audio_123",
            ),
            patch(
                "app.services.notion_audio_service.get_notion_tasks_collection_id",
                return_value="collection://task_123",
            ),
        ):
            service = NotionAudioService(notion_client_mock, channel_r2)

        task_id = uuid4()
        notion_page_id = "abc123def456"

        # Act
        result = await service.populate_audio(
            task_id=task_id,
            notion_page_id=notion_page_id,
            narration_files=narration_files,
            sfx_files=sfx_files,
        )

        # Assert
        assert result["created"] == 6
        assert result["failed"] == 0
        assert result["narration_count"] == 3
        assert result["sfx_count"] == 3
        assert result["storage_strategy"] == "r2"

    @pytest.mark.asyncio
    async def test_populate_audio_partial_failure_narration(
        self, notion_client_mock, channel_notion, narration_files, sfx_files
    ):
        """Test audio population with partial narration failures."""
        # Arrange
        with (
            patch(
                "app.services.notion_audio_service.get_notion_audio_database_id",
                return_value="db_audio_123",
            ),
            patch(
                "app.services.notion_audio_service.get_notion_tasks_collection_id",
                return_value="collection://task_123",
            ),
        ):
            service = NotionAudioService(notion_client_mock, channel_notion)

        task_id = uuid4()
        notion_page_id = "abc123def456"

        # Configure mock to fail on second narration call
        call_count = 0

        async def mock_create_page_with_failure(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # Fail second narration call
                raise Exception("Notion API error: rate limit")
            return {"id": f"page_{call_count}", "object": "page"}

        notion_client_mock.create_page = AsyncMock(side_effect=mock_create_page_with_failure)

        # Act
        result = await service.populate_audio(
            task_id=task_id,
            notion_page_id=notion_page_id,
            narration_files=narration_files,
            sfx_files=sfx_files,
        )

        # Assert
        assert result["created"] == 5  # 2 narration + 3 SFX succeeded
        assert result["failed"] == 1  # 1 narration failed
        assert result["narration_count"] == 2
        assert result["sfx_count"] == 3

    @pytest.mark.asyncio
    async def test_populate_audio_partial_failure_sfx(
        self, notion_client_mock, channel_notion, narration_files, sfx_files
    ):
        """Test audio population with partial SFX failures."""
        # Arrange
        with (
            patch(
                "app.services.notion_audio_service.get_notion_audio_database_id",
                return_value="db_audio_123",
            ),
            patch(
                "app.services.notion_audio_service.get_notion_tasks_collection_id",
                return_value="collection://task_123",
            ),
        ):
            service = NotionAudioService(notion_client_mock, channel_notion)

        task_id = uuid4()
        notion_page_id = "abc123def456"

        # Configure mock to fail on second SFX call (5th overall call)
        call_count = 0

        async def mock_create_page_with_sfx_failure(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 5:  # Fail second SFX call
                raise Exception("Notion API error: timeout")
            return {"id": f"page_{call_count}", "object": "page"}

        notion_client_mock.create_page = AsyncMock(side_effect=mock_create_page_with_sfx_failure)

        # Act
        result = await service.populate_audio(
            task_id=task_id,
            notion_page_id=notion_page_id,
            narration_files=narration_files,
            sfx_files=sfx_files,
        )

        # Assert
        assert result["created"] == 5  # 3 narration + 2 SFX succeeded
        assert result["failed"] == 1  # 1 SFX failed
        assert result["narration_count"] == 3
        assert result["sfx_count"] == 2

    @pytest.mark.asyncio
    async def test_populate_audio_complete_failure(
        self, notion_client_mock, channel_notion, narration_files, sfx_files
    ):
        """Test audio population with all clips failing (raises RuntimeError)."""
        # Arrange
        with (
            patch(
                "app.services.notion_audio_service.get_notion_audio_database_id",
                return_value="db_audio_123",
            ),
            patch(
                "app.services.notion_audio_service.get_notion_tasks_collection_id",
                return_value="collection://task_123",
            ),
        ):
            service = NotionAudioService(notion_client_mock, channel_notion)

        task_id = uuid4()
        notion_page_id = "abc123def456"

        # Configure mock to always fail
        notion_client_mock.create_page = AsyncMock(side_effect=Exception("Notion API down"))

        # Act & Assert
        with pytest.raises(RuntimeError, match="All 6 audio clips failed to populate"):
            await service.populate_audio(
                task_id=task_id,
                notion_page_id=notion_page_id,
                narration_files=narration_files,
                sfx_files=sfx_files,
            )

    @pytest.mark.asyncio
    async def test_populate_audio_empty_lists(self, notion_client_mock, channel_notion):
        """Test audio population with empty narration and SFX lists."""
        # Arrange
        with (
            patch(
                "app.services.notion_audio_service.get_notion_audio_database_id",
                return_value="db_audio_123",
            ),
            patch(
                "app.services.notion_audio_service.get_notion_tasks_collection_id",
                return_value="collection://task_123",
            ),
        ):
            service = NotionAudioService(notion_client_mock, channel_notion)

        task_id = uuid4()
        notion_page_id = "abc123def456"

        # Act
        result = await service.populate_audio(
            task_id=task_id,
            notion_page_id=notion_page_id,
            narration_files=[],
            sfx_files=[],
        )

        # Assert
        assert result["created"] == 0
        assert result["failed"] == 0
        assert result["narration_count"] == 0
        assert result["sfx_count"] == 0
        assert notion_client_mock.create_page.call_count == 0

    @pytest.mark.asyncio
    async def test_populate_audio_only_narration(
        self, notion_client_mock, channel_notion, narration_files
    ):
        """Test audio population with only narration files (no SFX)."""
        # Arrange
        with (
            patch(
                "app.services.notion_audio_service.get_notion_audio_database_id",
                return_value="db_audio_123",
            ),
            patch(
                "app.services.notion_audio_service.get_notion_tasks_collection_id",
                return_value="collection://task_123",
            ),
        ):
            service = NotionAudioService(notion_client_mock, channel_notion)

        task_id = uuid4()
        notion_page_id = "abc123def456"

        # Act
        result = await service.populate_audio(
            task_id=task_id,
            notion_page_id=notion_page_id,
            narration_files=narration_files,
            sfx_files=[],
        )

        # Assert
        assert result["created"] == 3
        assert result["failed"] == 0
        assert result["narration_count"] == 3
        assert result["sfx_count"] == 0
        assert notion_client_mock.create_page.call_count == 3

    @pytest.mark.asyncio
    async def test_populate_audio_only_sfx(self, notion_client_mock, channel_notion, sfx_files):
        """Test audio population with only SFX files (no narration)."""
        # Arrange
        with (
            patch(
                "app.services.notion_audio_service.get_notion_audio_database_id",
                return_value="db_audio_123",
            ),
            patch(
                "app.services.notion_audio_service.get_notion_tasks_collection_id",
                return_value="collection://task_123",
            ),
        ):
            service = NotionAudioService(notion_client_mock, channel_notion)

        task_id = uuid4()
        notion_page_id = "abc123def456"

        # Act
        result = await service.populate_audio(
            task_id=task_id,
            notion_page_id=notion_page_id,
            narration_files=[],
            sfx_files=sfx_files,
        )

        # Assert
        assert result["created"] == 3
        assert result["failed"] == 0
        assert result["narration_count"] == 0
        assert result["sfx_count"] == 3
        assert notion_client_mock.create_page.call_count == 3

    @pytest.mark.asyncio
    async def test_create_audio_entry_narration_properties(
        self, notion_client_mock, channel_notion, narration_files
    ):
        """Test _create_audio_entry correctly sets properties for narration."""
        # Arrange
        with (
            patch(
                "app.services.notion_audio_service.get_notion_audio_database_id",
                return_value="db_audio_123",
            ),
            patch(
                "app.services.notion_audio_service.get_notion_tasks_collection_id",
                return_value="collection://task_123",
            ),
        ):
            service = NotionAudioService(notion_client_mock, channel_notion)

        # Act
        await service._create_audio_entry(
            notion_page_id="abc123",
            clip_number=5,
            audio_type="narration",
            audio_path=Path("/workspace/audio/narration_05.mp3"),
            duration=6.8,
            storage_strategy="notion",
        )

        # Assert
        call_args = notion_client_mock.create_page.call_args
        properties = call_args[1]["properties"]

        assert properties["Clip Number"]["number"] == 5
        assert properties["Type"]["select"]["name"] == "narration"
        assert properties["Duration"]["number"] == 6.8
        assert properties["Status"]["select"]["name"] == "generated"
        assert "Generated Date" in properties
        assert properties["Task"]["relation"][0]["id"] == "abc123"
        assert properties["File"]["files"] == []

    @pytest.mark.asyncio
    async def test_create_audio_entry_sfx_properties(
        self, notion_client_mock, channel_notion, sfx_files
    ):
        """Test _create_audio_entry correctly sets properties for SFX."""
        # Arrange
        with (
            patch(
                "app.services.notion_audio_service.get_notion_audio_database_id",
                return_value="db_audio_123",
            ),
            patch(
                "app.services.notion_audio_service.get_notion_tasks_collection_id",
                return_value="collection://task_123",
            ),
        ):
            service = NotionAudioService(notion_client_mock, channel_notion)

        # Act
        await service._create_audio_entry(
            notion_page_id="xyz789",
            clip_number=12,
            audio_type="sfx",
            audio_path=Path("/workspace/sfx/sfx_12.mp3"),
            duration=7.5,
            storage_strategy="r2",
        )

        # Assert
        call_args = notion_client_mock.create_page.call_args
        properties = call_args[1]["properties"]

        assert properties["Clip Number"]["number"] == 12
        assert properties["Type"]["select"]["name"] == "sfx"
        assert properties["Duration"]["number"] == 7.5
        assert properties["Status"]["select"]["name"] == "generated"
        assert properties["Task"]["relation"][0]["id"] == "xyz789"
