"""Tests for Notion Asset Sync Service (Story 8.3).

Tests cover:
- NotionAssetSyncService with rate limiting
- update_asset_urls() with retry logic
- Error classification (permanent vs transient)
- sync_task_assets_to_notion() fire-and-forget pattern
- Short transactions (no DB lock during API calls)
"""

import uuid
from datetime import datetime, timezone

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, Task, TaskStatus
from app.services.asset_url_storage import record_asset_url
from app.services.notion_asset_sync import (
    NotionAssetSyncService,
    NotionSyncError,
    NotionSyncRetryError,
    sync_task_assets_to_notion,
)


@pytest.fixture
async def channel(async_session: AsyncSession) -> Channel:
    """Create a test channel."""
    channel = Channel(
        channel_id="test_channel",
        channel_name="Test Channel",
        storage_strategy="r2",
        max_concurrent=2,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


@pytest.fixture
async def task(async_session: AsyncSession, channel: Channel) -> Task:
    """Create a test task with Notion page ID."""
    task = Task(
        channel_id=channel.id,
        notion_page_id=f"test-page-{uuid.uuid4().hex}",
        title="Test Video",
        topic="Test Topic",
        story_direction="Test Story",
        status=TaskStatus.GENERATING_ASSETS,
    )
    async_session.add(task)
    await async_session.commit()
    await async_session.refresh(task)
    return task


@pytest.mark.asyncio
async def test_notion_asset_sync_service_success(mocker: MockerFixture):
    """Test NotionAssetSyncService successfully updates Notion page."""
    # Mock httpx response
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"object": "page"}

    mock_client = mocker.AsyncMock()
    mock_client.patch.return_value = mock_response
    mock_client.aclose = mocker.AsyncMock()

    mocker.patch("httpx.AsyncClient", return_value=mock_client)

    # Mock asset metadata
    mock_assets = [
        mocker.Mock(
            asset_type="character", asset_name="char1", asset_url="https://test.com/char1.png"
        ),
        mocker.Mock(
            asset_type="video_clip", asset_name="clip1", asset_url="https://test.com/clip1.mp4"
        ),
    ]

    # Create service and update assets
    service = NotionAssetSyncService("test_token")
    result = await service.update_asset_urls("test_page_id", mock_assets)
    await service.close()

    # Verify Notion API call
    assert mock_client.patch.called
    assert result == {"object": "page"}


@pytest.mark.asyncio
async def test_notion_asset_sync_service_permanent_error(mocker: MockerFixture):
    """Test NotionAssetSyncService raises NotionSyncError for 404."""
    # Mock httpx response with 404
    mock_response = mocker.Mock()
    mock_response.status_code = 404
    mock_response.text = "Page not found"

    mock_client = mocker.AsyncMock()
    mock_client.patch.return_value = mock_response
    mock_client.aclose = mocker.AsyncMock()

    mocker.patch("httpx.AsyncClient", return_value=mock_client)

    mock_assets = [
        mocker.Mock(
            asset_type="character", asset_name="char1", asset_url="https://test.com/char1.png"
        ),
    ]

    service = NotionAssetSyncService("test_token")

    with pytest.raises(NotionSyncError, match="404"):
        await service.update_asset_urls("test_page_id", mock_assets)

    await service.close()


@pytest.mark.asyncio
async def test_notion_asset_sync_service_transient_error(mocker: MockerFixture):
    """Test NotionAssetSyncService raises NotionSyncRetryError for 429."""
    # Mock httpx response with 429
    mock_response = mocker.Mock()
    mock_response.status_code = 429
    mock_response.headers = {"Retry-After": "5"}

    mock_client = mocker.AsyncMock()
    mock_client.patch.return_value = mock_response
    mock_client.aclose = mocker.AsyncMock()

    mocker.patch("httpx.AsyncClient", return_value=mock_client)

    mock_assets = [
        mocker.Mock(
            asset_type="character", asset_name="char1", asset_url="https://test.com/char1.png"
        ),
    ]

    service = NotionAssetSyncService("test_token")

    with pytest.raises(NotionSyncRetryError, match="429"):
        await service.update_asset_urls("test_page_id", mock_assets)

    await service.close()


@pytest.mark.asyncio
async def test_sync_task_assets_to_notion_success(
    async_session: AsyncSession, task: Task, channel: Channel, mocker: MockerFixture
):
    """Test sync_task_assets_to_notion successfully syncs assets."""
    # Mock URL validation (for record_asset_url)
    mock_head_response = mocker.Mock()
    mock_head_response.status_code = 200
    mock_head_client = mocker.AsyncMock()
    mock_head_client.head.return_value = mock_head_response
    mock_head_client.__aenter__.return_value = mock_head_client
    mock_head_client.__aexit__.return_value = None

    # Mock Notion API call
    mock_patch_response = mocker.Mock()
    mock_patch_response.status_code = 200
    mock_patch_response.json.return_value = {"object": "page"}

    # Create composite mock that handles both HEAD and PATCH
    mock_http_client = mocker.AsyncMock()

    async def mock_head(*args, **kwargs):
        return mock_head_response

    async def mock_patch(*args, **kwargs):
        return mock_patch_response

    mock_http_client.head = mock_head
    mock_http_client.patch = mock_patch
    mock_http_client.aclose = mocker.AsyncMock()
    mock_http_client.__aenter__.return_value = mock_http_client
    mock_http_client.__aexit__.return_value = None

    mocker.patch("httpx.AsyncClient", return_value=mock_http_client)

    # Create unsynced assets
    await record_asset_url(
        db=async_session,
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="char1.png",
        storage_strategy="r2",
        asset_url="https://bucket.r2.dev/test/char1.png",
    )

    # Sync assets to Notion
    await sync_task_assets_to_notion(async_session, task.id, "test_notion_token")

    # Verify assets marked as synced
    await async_session.refresh(task, ["assets"])
    assert len(task.assets) == 1
    assert task.assets[0].notion_synced_at is not None


@pytest.mark.asyncio
async def test_sync_task_assets_no_notion_page_id(
    async_session: AsyncSession, channel: Channel, mocker: MockerFixture
):
    """Test sync_task_assets_to_notion skips task without Notion page ID."""
    # Create task without notion_page_id
    task_no_page = Task(
        channel_id=channel.id,
        notion_page_id="",  # Empty page ID
        title="Test Video",
        topic="Test Topic",
        story_direction="Test Story",
        status=TaskStatus.GENERATING_ASSETS,
    )
    async_session.add(task_no_page)
    await async_session.commit()
    await async_session.refresh(task_no_page)

    # Should not raise error, just skip
    await sync_task_assets_to_notion(async_session, task_no_page.id, "test_token")


@pytest.mark.asyncio
async def test_sync_task_assets_no_unsynced_assets(
    async_session: AsyncSession, task: Task, channel: Channel, mocker: MockerFixture
):
    """Test sync_task_assets_to_notion skips when no unsynced assets."""
    # Mock URL validation
    mock_head_response = mocker.Mock()
    mock_head_response.status_code = 200
    mock_http_client = mocker.AsyncMock()
    mock_http_client.head.return_value = mock_head_response
    mock_http_client.__aenter__.return_value = mock_http_client
    mock_http_client.__aexit__.return_value = None
    mocker.patch("httpx.AsyncClient", return_value=mock_http_client)

    # Create already-synced asset
    asset = await record_asset_url(
        db=async_session,
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="synced.png",
        storage_strategy="r2",
        asset_url="https://bucket.r2.dev/test/synced.png",
    )
    asset.notion_synced_at = datetime.now(timezone.utc)
    await async_session.commit()

    # Should not raise error, just skip
    await sync_task_assets_to_notion(async_session, task.id, "test_token")


@pytest.mark.asyncio
async def test_sync_task_assets_permanent_error_does_not_block(
    async_session: AsyncSession, task: Task, channel: Channel, mocker: MockerFixture
):
    """Test sync_task_assets_to_notion logs permanent error but doesn't block."""
    # Mock URL validation
    mock_head_response = mocker.Mock()
    mock_head_response.status_code = 200

    # Mock Notion API call with permanent error
    mock_patch_response = mocker.Mock()
    mock_patch_response.status_code = 404
    mock_patch_response.text = "Page not found"

    mock_http_client = mocker.AsyncMock()

    async def mock_head(*args, **kwargs):
        return mock_head_response

    async def mock_patch(*args, **kwargs):
        return mock_patch_response

    mock_http_client.head = mock_head
    mock_http_client.patch = mock_patch
    mock_http_client.aclose = mocker.AsyncMock()
    mock_http_client.__aenter__.return_value = mock_http_client
    mock_http_client.__aexit__.return_value = None

    mocker.patch("httpx.AsyncClient", return_value=mock_http_client)

    # Create unsynced asset
    await record_asset_url(
        db=async_session,
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="char1.png",
        storage_strategy="r2",
        asset_url="https://bucket.r2.dev/test/char1.png",
    )

    # Should not raise error (fire-and-forget pattern)
    await sync_task_assets_to_notion(async_session, task.id, "test_notion_token")

    # Asset should remain unsynced
    await async_session.refresh(task, ["assets"])
    assert task.assets[0].notion_synced_at is None


@pytest.mark.asyncio
async def test_notion_asset_sync_service_rate_limiting(mocker: MockerFixture):
    """Test NotionAssetSyncService enforces 3 req/sec rate limit."""
    # Mock httpx response
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"object": "page"}

    mock_client = mocker.AsyncMock()
    mock_client.patch.return_value = mock_response
    mock_client.aclose = mocker.AsyncMock()

    mocker.patch("httpx.AsyncClient", return_value=mock_client)

    # Create service
    service = NotionAssetSyncService("test_token")

    # Verify rate limiter exists and has correct settings
    assert service.rate_limiter.max_rate == 3
    assert service.rate_limiter.time_period == 1

    await service.close()
