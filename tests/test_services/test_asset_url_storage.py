"""Tests for Asset URL Storage Service (Story 8.3).

Tests cover:
- record_asset_url() function with URL validation
- get_unsynced_assets() function
- get_task_assets() function with optional filtering
- mark_synced() function
- Error handling for invalid URLs
"""

import uuid
from datetime import datetime, timezone

import httpx
import pytest
from pytest_mock import MockerFixture
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AssetMetadata, Channel, Task, TaskStatus
from app.services.asset_url_storage import (
    get_task_assets,
    get_unsynced_assets,
    mark_synced,
    record_asset_url,
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
    """Create a test task."""
    task = Task(
        channel_id=channel.id,
        notion_page_id=f"test-page-{uuid.uuid4()}",
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
async def test_record_asset_url_success(
    async_session: AsyncSession, task: Task, channel: Channel, mocker: MockerFixture
):
    """Test recording asset URL with successful validation."""
    # Mock httpx HEAD request
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_client = mocker.AsyncMock()
    mock_client.head.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mocker.patch("httpx.AsyncClient", return_value=mock_client)

    # Record asset URL
    asset = await record_asset_url(
        db=async_session,
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="bulbasaur_01.png",
        storage_strategy="r2",
        asset_url="https://bucket.r2.dev/test/bulbasaur_01.png",
        local_file_path="/app/workspace/test/bulbasaur_01.png",
    )

    # Verify asset created
    assert asset.id is not None
    assert asset.task_id == task.id
    assert asset.channel_id == channel.id
    assert asset.asset_type == "character"
    assert asset.asset_name == "bulbasaur_01.png"
    assert asset.storage_strategy == "r2"
    assert asset.asset_url == "https://bucket.r2.dev/test/bulbasaur_01.png"
    assert asset.local_file_path == "/app/workspace/test/bulbasaur_01.png"
    assert asset.notion_synced_at is None  # Not synced yet


@pytest.mark.asyncio
async def test_record_asset_url_validation_failure(
    async_session: AsyncSession, task: Task, channel: Channel, mocker: MockerFixture
):
    """Test recording asset URL fails when URL is not accessible."""
    # Mock httpx HEAD request with 404
    mock_response = mocker.Mock()
    mock_response.status_code = 404
    mock_client = mocker.AsyncMock()
    mock_client.head.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mocker.patch("httpx.AsyncClient", return_value=mock_client)

    # Attempt to record asset URL
    with pytest.raises(ValueError, match="Asset URL not accessible"):
        await record_asset_url(
            db=async_session,
            task_id=task.id,
            channel_id=channel.id,
            asset_type="character",
            asset_name="missing.png",
            storage_strategy="r2",
            asset_url="https://bucket.r2.dev/test/missing.png",
        )


@pytest.mark.asyncio
async def test_record_asset_url_redirects_allowed(
    async_session: AsyncSession, task: Task, channel: Channel, mocker: MockerFixture
):
    """Test recording asset URL allows 301/302 redirects."""
    # Mock httpx HEAD request with 301 redirect
    mock_response = mocker.Mock()
    mock_response.status_code = 301
    mock_client = mocker.AsyncMock()
    mock_client.head.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mocker.patch("httpx.AsyncClient", return_value=mock_client)

    # Record asset URL (should succeed with redirect)
    asset = await record_asset_url(
        db=async_session,
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="redirected.png",
        storage_strategy="notion",
        asset_url="https://notion.so/files/redirected.png",
    )

    assert asset.id is not None
    assert asset.asset_url == "https://notion.so/files/redirected.png"


@pytest.mark.asyncio
async def test_get_unsynced_assets(
    async_session: AsyncSession, task: Task, channel: Channel, mocker: MockerFixture
):
    """Test retrieving assets that haven't been synced to Notion."""
    # Mock URL validation
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_client = mocker.AsyncMock()
    mock_client.head.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mocker.patch("httpx.AsyncClient", return_value=mock_client)

    # Create synced asset
    synced_asset = await record_asset_url(
        db=async_session,
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="synced.png",
        storage_strategy="notion",
        asset_url="https://notion.so/files/synced.png",
    )
    synced_asset.notion_synced_at = datetime.now(timezone.utc)
    await async_session.commit()

    # Create unsynced asset
    await record_asset_url(
        db=async_session,
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="unsynced.png",
        storage_strategy="notion",
        asset_url="https://notion.so/files/unsynced.png",
    )

    # Get unsynced assets
    unsynced = await get_unsynced_assets(async_session, task.id)

    assert len(unsynced) == 1
    assert unsynced[0].asset_name == "unsynced.png"
    assert unsynced[0].notion_synced_at is None


@pytest.mark.asyncio
async def test_get_task_assets_all(
    async_session: AsyncSession, task: Task, channel: Channel, mocker: MockerFixture
):
    """Test retrieving all assets for a task."""
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
        asset_name="char.png",
        storage_strategy="r2",
        asset_url="https://bucket.r2.dev/test/char.png",
    )
    await record_asset_url(
        db=async_session,
        task_id=task.id,
        channel_id=channel.id,
        asset_type="video_clip",
        asset_name="clip.mp4",
        storage_strategy="r2",
        asset_url="https://bucket.r2.dev/test/clip.mp4",
    )

    # Get all assets
    assets = await get_task_assets(async_session, task.id)

    assert len(assets) == 2
    assert assets[0].asset_name == "char.png"
    assert assets[1].asset_name == "clip.mp4"


@pytest.mark.asyncio
async def test_get_task_assets_filtered_by_type(
    async_session: AsyncSession, task: Task, channel: Channel, mocker: MockerFixture
):
    """Test retrieving assets filtered by asset_type."""
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
        asset_name="char.png",
        storage_strategy="r2",
        asset_url="https://bucket.r2.dev/test/char.png",
    )
    await record_asset_url(
        db=async_session,
        task_id=task.id,
        channel_id=channel.id,
        asset_type="video_clip",
        asset_name="clip.mp4",
        storage_strategy="r2",
        asset_url="https://bucket.r2.dev/test/clip.mp4",
    )

    # Get character assets only
    characters = await get_task_assets(async_session, task.id, asset_type="character")

    assert len(characters) == 1
    assert characters[0].asset_name == "char.png"
    assert characters[0].asset_type == "character"


@pytest.mark.asyncio
async def test_mark_synced(
    async_session: AsyncSession, task: Task, channel: Channel, mocker: MockerFixture
):
    """Test marking asset as synced to Notion."""
    # Mock URL validation
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_client = mocker.AsyncMock()
    mock_client.head.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mocker.patch("httpx.AsyncClient", return_value=mock_client)

    # Create asset
    asset = await record_asset_url(
        db=async_session,
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="test.png",
        storage_strategy="notion",
        asset_url="https://notion.so/files/test.png",
    )

    # Initially not synced
    assert asset.notion_synced_at is None

    # Mark as synced
    await mark_synced(async_session, asset.id)

    # Verify timestamp set
    await async_session.refresh(asset)
    assert asset.notion_synced_at is not None
    assert isinstance(asset.notion_synced_at, datetime)


@pytest.mark.asyncio
async def test_mark_synced_nonexistent_asset(async_session: AsyncSession):
    """Test mark_synced with non-existent asset ID does not raise error."""
    # Should not raise error
    await mark_synced(async_session, uuid.uuid4())


@pytest.mark.asyncio
async def test_record_asset_url_without_local_path(
    async_session: AsyncSession, task: Task, channel: Channel, mocker: MockerFixture
):
    """Test recording asset URL without local_file_path (optional field)."""
    # Mock URL validation
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_client = mocker.AsyncMock()
    mock_client.head.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mocker.patch("httpx.AsyncClient", return_value=mock_client)

    # Record asset without local path
    asset = await record_asset_url(
        db=async_session,
        task_id=task.id,
        channel_id=channel.id,
        asset_type="video_clip",
        asset_name="clip.mp4",
        storage_strategy="notion",
        asset_url="https://notion.so/files/clip.mp4",
    )

    assert asset.local_file_path is None
    assert asset.asset_url == "https://notion.so/files/clip.mp4"
