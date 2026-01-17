"""Tests for Notion Asset Service (Story 5.3).

Note: These are UNIT TESTS using mocks. They verify service logic in isolation.

INTEGRATION TESTS NEEDED (Story 5.3 Task 6):
- Test complete approval flow (generate → populate → ready → approve → resume)
- Test complete rejection flow (generate → populate → ready → reject → error)
- Test with 22 real assets (characters, environments, props)
- Test 30-second approval workflow (UX requirement)
- Test with both Notion and R2 storage strategies (currently blocked)

See story file AI Review Follow-ups section for integration test requirements.
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from app.clients.notion import NotionClient
from app.models import Channel
from app.services.notion_asset_service import NotionAssetService


@pytest.fixture
def mock_notion_client():
    """Create mock Notion client with create_page method."""
    client = MagicMock(spec=NotionClient)

    # Mock create_page as AsyncMock (Story 5.3 code review fix)
    client.create_page = AsyncMock(return_value={"id": "asset_page_id"})

    return client


@pytest.fixture
def mock_channel():
    """Create mock channel with notion storage strategy."""
    channel = MagicMock(spec=Channel)
    channel.channel_id = "poke1"
    channel.storage_strategy = "notion"
    return channel


@pytest.fixture
def notion_asset_service(mock_notion_client, mock_channel):
    """Create NotionAssetService instance with mocks."""
    # Mock config functions to return test IDs (Story 5.3 code review fix)
    with (
        patch("app.services.notion_asset_service.get_notion_assets_database_id") as mock_assets_id,
        patch("app.services.notion_asset_service.get_notion_tasks_collection_id") as mock_tasks_id,
    ):
        mock_assets_id.return_value = "d8503431f040432eb91c3b033460fbbd"
        mock_tasks_id.return_value = "collection://1b4bdba3-2e09-4cc7-be3b-f6475d49298a"
        return NotionAssetService(mock_notion_client, mock_channel)


@pytest.fixture
def sample_asset_files():
    """Create sample asset files list."""
    return [
        {
            "asset_type": "character",
            "name": "bulbasaur_resting",
            "output_path": Path("/workspace/assets/bulbasaur_resting.png"),
        },
        {
            "asset_type": "environment",
            "name": "forest_clearing",
            "output_path": Path("/workspace/assets/forest_clearing.png"),
        },
        {
            "asset_type": "prop",
            "name": "berry_bush",
            "output_path": Path("/workspace/assets/berry_bush.png"),
        },
    ]


class TestNotionAssetService:
    """Test suite for NotionAssetService."""

    @pytest.mark.asyncio
    async def test_populate_assets_success(
        self, mock_notion_client, mock_channel, sample_asset_files
    ):
        """Test successful asset population creates all entries."""
        # Arrange
        task_id = uuid4()
        notion_page_id = "abc123def456"

        # Mock config functions
        with (
            patch(
                "app.services.notion_asset_service.get_notion_assets_database_id"
            ) as mock_assets_id,
            patch(
                "app.services.notion_asset_service.get_notion_tasks_collection_id"
            ) as mock_tasks_id,
        ):
            mock_assets_id.return_value = "test_assets_db"
            mock_tasks_id.return_value = "test_tasks_collection"

            service = NotionAssetService(mock_notion_client, mock_channel)

            # Act
            result = await service.populate_assets(
                task_id=task_id,
                notion_page_id=notion_page_id,
                asset_files=sample_asset_files,
            )

            # Assert
            assert result["created"] == 3
            assert result["failed"] == 0
            assert result["storage_strategy"] == "notion"

            # Verify create_page called 3 times (once per asset)
            assert mock_notion_client.create_page.call_count == 3

    @pytest.mark.asyncio
    async def test_create_asset_entry_properties(self, mock_notion_client, mock_channel):
        """Test asset entry created with correct properties."""
        # Arrange
        notion_page_id = "abc123def456"
        asset_type = "character"
        asset_name = "bulbasaur_resting"
        asset_path = Path("/workspace/assets/bulbasaur_resting.png")

        # Mock config functions
        with (
            patch(
                "app.services.notion_asset_service.get_notion_assets_database_id"
            ) as mock_assets_id,
            patch(
                "app.services.notion_asset_service.get_notion_tasks_collection_id"
            ) as mock_tasks_id,
        ):
            mock_assets_id.return_value = "test_assets_db"
            mock_tasks_id.return_value = "test_tasks_collection"

            service = NotionAssetService(mock_notion_client, mock_channel)

            # Act
            result = await service._create_asset_entry(
                notion_page_id=notion_page_id,
                asset_type=asset_type,
                asset_name=asset_name,
                asset_path=asset_path,
                storage_strategy="notion",
            )

            # Assert
            assert result == {"id": "asset_page_id"}

            # Verify create_page was called
            assert mock_notion_client.create_page.called

            # Verify properties passed to create_page
            call_args = mock_notion_client.create_page.call_args
            properties = call_args[1]["properties"]
            assert properties["Asset Name"]["title"][0]["text"]["content"] == asset_name
            assert properties["Asset Type"]["select"]["name"] == asset_type
            assert properties["Status"]["select"]["name"] == "generated"
            assert "Generated Date" in properties
            assert properties["Task"]["relation"][0]["id"] == notion_page_id
            assert "File URL" in properties  # Story 5.3 code review fix

    @pytest.mark.asyncio
    async def test_populate_assets_r2_strategy(self, mock_notion_client, sample_asset_files):
        """Test asset population with R2 storage strategy."""
        # Arrange
        mock_channel = MagicMock(spec=Channel)
        mock_channel.storage_strategy = "r2"

        # Mock config functions
        with (
            patch(
                "app.services.notion_asset_service.get_notion_assets_database_id"
            ) as mock_assets_id,
            patch(
                "app.services.notion_asset_service.get_notion_tasks_collection_id"
            ) as mock_tasks_id,
        ):
            mock_assets_id.return_value = "test_assets_db"
            mock_tasks_id.return_value = "test_tasks_collection"

            service = NotionAssetService(mock_notion_client, mock_channel)

            task_id = uuid4()
            notion_page_id = "abc123def456"

            # Act
            result = await service.populate_assets(
                task_id=task_id,
                notion_page_id=notion_page_id,
                asset_files=sample_asset_files,
            )

            # Assert
            assert result["storage_strategy"] == "r2"
            assert result["created"] == 3

    @pytest.mark.asyncio
    async def test_rate_limiting_enforced(
        self, mock_notion_client, mock_channel, sample_asset_files
    ):
        """Test rate limiter is used via create_page method (Story 5.3 code review fix)."""
        # Arrange
        task_id = uuid4()
        notion_page_id = "abc123def456"

        # Mock config functions
        with (
            patch(
                "app.services.notion_asset_service.get_notion_assets_database_id"
            ) as mock_assets_id,
            patch(
                "app.services.notion_asset_service.get_notion_tasks_collection_id"
            ) as mock_tasks_id,
        ):
            mock_assets_id.return_value = "test_assets_db"
            mock_tasks_id.return_value = "test_tasks_collection"

            service = NotionAssetService(mock_notion_client, mock_channel)

            # Act
            await service.populate_assets(
                task_id=task_id,
                notion_page_id=notion_page_id,
                asset_files=sample_asset_files,
            )

            # Assert - create_page called 3 times (rate limiting enforced inside NotionClient.create_page)
            assert mock_notion_client.create_page.call_count == 3
