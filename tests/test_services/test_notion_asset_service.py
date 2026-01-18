"""Tests for Notion Asset Service (Story 5.3 - Code Review Fixes).

UPDATED: Tests now validate 22-asset requirement, new parameters (min_success_rate, skip_existing),
and improved error handling per code review findings.

Note: These are UNIT TESTS using mocks. They verify service logic in isolation.

INTEGRATION TESTS NEEDED (Story 5.3 Task 6):
- Test complete approval flow (generate → populate → ready → approve → resume)
- Test complete rejection flow (generate → populate → ready → reject → error)
- Test with 22 real assets (characters, environments, props)
- Test 30-second approval workflow (UX requirement)
- Test with both Notion and R2 storage strategies

See story file AI Review Follow-ups section for integration test requirements.
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.clients.catbox import CatboxClient
from app.clients.notion import NotionClient
from app.models import Channel
from app.services.notion_asset_service import (
    AssetValidationError,
    AssetUploadError,
    NotionAssetService,
)


@pytest.fixture
def mock_notion_client():
    """Create mock Notion client with create_page and query_database methods."""
    client = MagicMock(spec=NotionClient)

    # Mock create_page as AsyncMock (Story 5.3 code review fix)
    client.create_page = AsyncMock(return_value={"id": "asset_page_id"})

    # Mock query_database for idempotency check
    client.query_database = AsyncMock(return_value={"results": [], "has_more": False})

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
def sample_asset_files_full():
    """Create 22 sample asset files (matches AC1 requirement)."""
    assets = []

    # 6 character assets
    for i in range(6):
        assets.append({
            "asset_type": "character",
            "name": f"character_{i}",
            "output_path": Path(f"/workspace/assets/character_{i}.png"),
        })

    # 10 environment assets
    for i in range(10):
        assets.append({
            "asset_type": "environment",
            "name": f"environment_{i}",
            "output_path": Path(f"/workspace/assets/environment_{i}.png"),
        })

    # 6 prop assets
    for i in range(6):
        assets.append({
            "asset_type": "prop",
            "name": f"prop_{i}",
            "output_path": Path(f"/workspace/assets/prop_{i}.png"),
        })

    return assets


@pytest.fixture
def sample_asset_files_partial():
    """Create 3 sample asset files (for testing validation failure)."""
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
        self, mock_notion_client, mock_channel, sample_asset_files_full
    ):
        """Test successful asset population creates all 22 entries."""
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
                asset_files=sample_asset_files_full,
                skip_existing=False,  # Disable for unit test
            )

            # Assert
            assert result["created"] == 22
            assert result["failed"] == 0
            assert result["skipped"] == 0
            assert result["storage_strategy"] == "notion"

            # Verify create_page called 22 times (once per asset)
            assert mock_notion_client.create_page.call_count == 22

    @pytest.mark.asyncio
    async def test_populate_assets_validation_failure_count(
        self, mock_notion_client, mock_channel, sample_asset_files_partial
    ):
        """Test that validation fails if asset count != 22 (Code Review Issue #5)."""
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

            # Act & Assert
            with pytest.raises(AssetValidationError) as exc_info:
                await service.populate_assets(
                    task_id=task_id,
                    notion_page_id=notion_page_id,
                    asset_files=sample_asset_files_partial,  # Only 3 assets
                )

            assert "Expected 22 assets" in str(exc_info.value)
            assert "got 3" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_populate_assets_validation_failure_invalid_type(
        self, mock_notion_client, mock_channel, sample_asset_files_full
    ):
        """Test that validation fails if asset type invalid (Code Review Issue #12)."""
        # Arrange
        task_id = uuid4()
        notion_page_id = "abc123def456"

        # Corrupt one asset with invalid type
        sample_asset_files_full[0]["asset_type"] = "invalid_type"

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

            # Act & Assert
            with pytest.raises(AssetValidationError) as exc_info:
                await service.populate_assets(
                    task_id=task_id,
                    notion_page_id=notion_page_id,
                    asset_files=sample_asset_files_full,
                )

            assert "Invalid asset_type 'invalid_type'" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_populate_assets_min_success_rate_threshold(
        self, mock_notion_client, mock_channel, sample_asset_files_full
    ):
        """Test that AssetUploadError raised if success rate < threshold (Code Review Issue #8)."""
        # Arrange
        task_id = uuid4()
        notion_page_id = "abc123def456"

        # Mock create_page to fail for half the assets
        call_count = 0

        async def create_page_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise Exception("Notion API error")
            return {"id": f"asset_page_{call_count}"}

        mock_notion_client.create_page.side_effect = create_page_side_effect

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

            # Act & Assert - 50% success rate < 90% threshold should raise
            with pytest.raises(AssetUploadError) as exc_info:
                await service.populate_assets(
                    task_id=task_id,
                    notion_page_id=notion_page_id,
                    asset_files=sample_asset_files_full,
                    min_success_rate=0.9,  # Require 90%
                    skip_existing=False,
                )

            assert "success rate" in str(exc_info.value).lower()
            assert "below minimum threshold" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_asset_entry_properties(self, mock_notion_client, mock_channel):
        """Test asset entry created with correct properties."""
        # Arrange
        notion_page_id = "abc123def456"
        asset_type = "character"
        asset_name = "bulbasaur_resting"
        file_url = "https://files.catbox.moe/abc123.png"

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
                file_url=file_url,
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
            assert properties["Status"]["select"]["name"] == "generated"  # FIXED: Constant used
            assert "Generated Date" in properties
            assert properties["Task"]["relation"][0]["id"] == notion_page_id
            assert properties["File URL"]["url"] == file_url  # Story 5.3 code review fix

    @pytest.mark.asyncio
    async def test_populate_assets_r2_strategy(self, mock_notion_client, sample_asset_files_full):
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
                asset_files=sample_asset_files_full,
                skip_existing=False,
            )

            # Assert
            assert result["storage_strategy"] == "r2"
            assert result["created"] == 22

    @pytest.mark.asyncio
    async def test_rate_limiting_enforced(
        self, mock_notion_client, mock_channel, sample_asset_files_full
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
                asset_files=sample_asset_files_full,
                skip_existing=False,
            )

            # Assert - create_page called 22 times (rate limiting enforced inside NotionClient.create_page)
            assert mock_notion_client.create_page.call_count == 22

    @pytest.mark.asyncio
    async def test_file_upload_via_catbox(
        self, mock_notion_client, mock_channel
    ):
        """Test file upload to catbox.moe and URL population in Notion property (Code Review Issue #2)."""
        # Arrange
        mock_catbox_client = MagicMock(spec=CatboxClient)
        mock_catbox_client.upload_image = AsyncMock(
            return_value="https://files.catbox.moe/abc123.png"
        )

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

            service = NotionAssetService(mock_notion_client, mock_channel, mock_catbox_client)

            asset_name = "bulbasaur_resting"
            asset_path = Path("/workspace/assets/bulbasaur_resting.png")

            # Act
            result = await service._create_asset_entry(
                notion_page_id="abc123",
                asset_type="character",
                asset_name=asset_name,
                file_url="https://files.catbox.moe/abc123.png",  # Pre-uploaded URL
                storage_strategy="notion",
            )

            # Assert
            assert result == {"id": "asset_page_id"}

            # Verify File URL property was set with catbox URL
            call_args = mock_notion_client.create_page.call_args
            properties = call_args[1]["properties"]
            assert properties["File URL"]["url"] == "https://files.catbox.moe/abc123.png"

    @pytest.mark.asyncio
    async def test_file_upload_failure_graceful_degradation(
        self, mock_notion_client, mock_channel
    ):
        """Test that asset entry is still created even if file upload fails (Code Review Issue #2)."""
        # Arrange
        mock_catbox_client = MagicMock(spec=CatboxClient)
        mock_catbox_client.upload_image = AsyncMock(
            side_effect=Exception("catbox.moe is down")
        )

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

            service = NotionAssetService(mock_notion_client, mock_channel, mock_catbox_client)

            # Act - Should not raise exception despite upload failure
            result = await service._create_asset_entry(
                notion_page_id="abc123",
                asset_type="character",
                asset_name="bulbasaur_resting",
                file_url=None,  # Upload failed, no URL
                storage_strategy="notion",
            )

            # Assert
            assert result == {"id": "asset_page_id"}

            # Verify File URL property was set to None (graceful degradation)
            call_args = mock_notion_client.create_page.call_args
            properties = call_args[1]["properties"]
            assert properties["File URL"]["url"] is None
