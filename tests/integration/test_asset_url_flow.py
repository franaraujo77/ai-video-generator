"""Integration tests for end-to-end asset URL flow (Story 8.3).

Tests the complete flow: worker → storage → Notion sync
"""

import uuid
from unittest.mock import AsyncMock, Mock

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, Task, TaskStatus
from app.services.asset_url_storage import get_task_assets, get_unsynced_assets, record_asset_url
from app.services.notion_asset_sync import sync_task_assets_to_notion


@pytest.fixture
async def channel(async_session: AsyncSession) -> Channel:
    """Create a test channel with R2 storage."""
    channel = Channel(
        channel_id="test_channel",
        channel_name="Test Channel",
        storage_strategy="r2",
        r2_bucket_name="test-bucket",
        max_concurrent=2,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


@pytest.fixture
async def task(async_session: AsyncSession, channel: Channel) -> Task:
    """Create a test task."""
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
async def test_complete_asset_url_flow_r2_storage(
    async_session: AsyncSession, task: Task, channel: Channel, mocker: MockerFixture
):
    """Test complete flow: record URL → verify in DB → sync to Notion → mark synced.

    This simulates a worker generating assets and the full lifecycle.
    """
    # Mock httpx for URL validation
    mock_head_response = mocker.Mock()
    mock_head_response.status_code = 200

    # Mock Notion API call
    mock_patch_response = mocker.Mock()
    mock_patch_response.status_code = 200
    mock_patch_response.json.return_value = {"object": "page"}

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

    # Step 1: Worker records asset URL (simulating asset generation)
    asset1 = await record_asset_url(
        db=async_session,
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="bulbasaur_01.png",
        storage_strategy="r2",
        asset_url="https://test-bucket.r2.dev/test_channel/proj1/assets/bulbasaur_01.png",
        local_file_path="/app/workspace/test/bulbasaur_01.png",
    )

    asset2 = await record_asset_url(
        db=async_session,
        task_id=task.id,
        channel_id=channel.id,
        asset_type="environment",
        asset_name="forest_01.png",
        storage_strategy="r2",
        asset_url="https://test-bucket.r2.dev/test_channel/proj1/assets/forest_01.png",
    )

    # Step 2: Verify assets stored in database
    all_assets = await get_task_assets(async_session, task.id)
    assert len(all_assets) == 2
    assert all_assets[0].asset_type == "character"
    assert all_assets[1].asset_type == "environment"

    # Step 3: Verify assets not yet synced
    unsynced = await get_unsynced_assets(async_session, task.id)
    assert len(unsynced) == 2

    # Step 4: Background job syncs to Notion
    await sync_task_assets_to_notion(async_session, task.id, "test_notion_token")

    # Step 5: Verify assets marked as synced
    await async_session.refresh(asset1)
    await async_session.refresh(asset2)
    assert asset1.notion_synced_at is not None
    assert asset2.notion_synced_at is not None

    # Step 6: Verify no unsynced assets remain
    unsynced_after = await get_unsynced_assets(async_session, task.id)
    assert len(unsynced_after) == 0


@pytest.mark.asyncio
async def test_asset_url_flow_with_filtering_by_type(
    async_session: AsyncSession, task: Task, channel: Channel, mocker: MockerFixture
):
    """Test asset retrieval with filtering by asset type."""
    # Mock URL validation
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_client = mocker.AsyncMock()
    mock_client.head.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mocker.patch("httpx.AsyncClient", return_value=mock_client)

    # Create assets of different types
    await record_asset_url(
        db=async_session,
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="char1.png",
        storage_strategy="r2",
        asset_url="https://test-bucket.r2.dev/test_channel/proj1/char1.png",
    )

    await record_asset_url(
        db=async_session,
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="char2.png",
        storage_strategy="r2",
        asset_url="https://test-bucket.r2.dev/test_channel/proj1/char2.png",
    )

    await record_asset_url(
        db=async_session,
        task_id=task.id,
        channel_id=channel.id,
        asset_type="video_clip",
        asset_name="clip1.mp4",
        storage_strategy="r2",
        asset_url="https://test-bucket.r2.dev/test_channel/proj1/clip1.mp4",
    )

    # Filter by character type
    characters = await get_task_assets(async_session, task.id, asset_type="character")
    assert len(characters) == 2
    assert all(a.asset_type == "character" for a in characters)

    # Filter by video_clip type
    videos = await get_task_assets(async_session, task.id, asset_type="video_clip")
    assert len(videos) == 1
    assert videos[0].asset_type == "video_clip"

    # Get all assets (no filter)
    all_assets = await get_task_assets(async_session, task.id)
    assert len(all_assets) == 3


@pytest.mark.asyncio
async def test_asset_url_flow_notion_sync_failure_recovers(
    async_session: AsyncSession, task: Task, channel: Channel, mocker: MockerFixture
):
    """Test that Notion sync failures don't block pipeline (fire-and-forget)."""
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

    # Record asset URL
    asset = await record_asset_url(
        db=async_session,
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="test.png",
        storage_strategy="r2",
        asset_url="https://test-bucket.r2.dev/test_channel/proj1/test.png",
    )

    # Attempt Notion sync (should fail but not raise)
    await sync_task_assets_to_notion(async_session, task.id, "test_notion_token")

    # Asset should remain unsynced (fire-and-forget doesn't block)
    await async_session.refresh(asset)
    assert asset.notion_synced_at is None

    # Unsynced assets list should still have this asset
    unsynced = await get_unsynced_assets(async_session, task.id)
    assert len(unsynced) == 1
    assert unsynced[0].id == asset.id
