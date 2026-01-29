"""Tests for AssetMetadata model (Story 8.3).

Tests cover:
- Model field validation and constraints
- Foreign key relationships to Task and Channel
- Indexes for efficient querying
- Timestamps (created_at, updated_at, notion_synced_at)
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AssetMetadata, Channel, Task, TaskStatus


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
async def test_asset_metadata_creation(async_session: AsyncSession, task: Task, channel: Channel):
    """Test AssetMetadata model creation with all required fields."""
    asset = AssetMetadata(
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="bulbasaur_01.png",
        storage_strategy="r2",
        asset_url="https://bucket.r2.dev/test/bulbasaur_01.png",
        local_file_path="/app/workspace/test/bulbasaur_01.png",
    )

    async_session.add(asset)
    await async_session.commit()
    await async_session.refresh(asset)

    # Verify all fields
    assert asset.id is not None
    assert asset.task_id == task.id
    assert asset.channel_id == channel.id
    assert asset.asset_type == "character"
    assert asset.asset_name == "bulbasaur_01.png"
    assert asset.storage_strategy == "r2"
    assert asset.asset_url == "https://bucket.r2.dev/test/bulbasaur_01.png"
    assert asset.local_file_path == "/app/workspace/test/bulbasaur_01.png"
    assert asset.notion_synced_at is None  # Not synced yet
    assert asset.notion_asset_property_id is None
    assert asset.created_at is not None
    assert asset.updated_at is not None


@pytest.mark.asyncio
async def test_asset_metadata_relationships(
    async_session: AsyncSession, task: Task, channel: Channel
):
    """Test relationships to Task and Channel models."""
    asset = AssetMetadata(
        task_id=task.id,
        channel_id=channel.id,
        asset_type="video_clip",
        asset_name="clip_01.mp4",
        storage_strategy="r2",
        asset_url="https://bucket.r2.dev/test/clip_01.mp4",
    )

    async_session.add(asset)
    await async_session.commit()
    await async_session.refresh(asset)

    # Test task relationship (lazy loading)
    await async_session.refresh(asset, ["task"])
    assert asset.task.id == task.id
    assert asset.task.title == "Test Video"

    # Test channel relationship (lazy loading)
    await async_session.refresh(asset, ["channel"])
    assert asset.channel.id == channel.id
    assert asset.channel.channel_id == "test_channel"


@pytest.mark.asyncio
async def test_task_assets_relationship(async_session: AsyncSession, task: Task, channel: Channel):
    """Test Task.assets relationship (one-to-many)."""
    # Create multiple assets for task
    asset1 = AssetMetadata(
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="char_01.png",
        storage_strategy="r2",
        asset_url="https://bucket.r2.dev/test/char_01.png",
    )
    asset2 = AssetMetadata(
        task_id=task.id,
        channel_id=channel.id,
        asset_type="environment",
        asset_name="env_01.png",
        storage_strategy="r2",
        asset_url="https://bucket.r2.dev/test/env_01.png",
    )

    async_session.add_all([asset1, asset2])
    await async_session.commit()

    # Load task with assets
    await async_session.refresh(task, ["assets"])
    assert len(task.assets) == 2
    assert task.assets[0].asset_type == "character"
    assert task.assets[1].asset_type == "environment"


@pytest.mark.asyncio
async def test_channel_assets_relationship(
    async_session: AsyncSession, task: Task, channel: Channel
):
    """Test Channel.assets relationship (one-to-many)."""
    # Create assets for channel
    asset1 = AssetMetadata(
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="char_01.png",
        storage_strategy="r2",
        asset_url="https://bucket.r2.dev/test/char_01.png",
    )

    async_session.add(asset1)
    await async_session.commit()

    # Load channel with assets
    await async_session.refresh(channel, ["assets"])
    assert len(channel.assets) >= 1
    assert channel.assets[0].channel_id == channel.id


@pytest.mark.asyncio
async def test_cascade_delete_task(async_session: AsyncSession, task: Task, channel: Channel):
    """Test CASCADE delete: deleting task deletes assets."""
    asset = AssetMetadata(
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="test.png",
        storage_strategy="r2",
        asset_url="https://bucket.r2.dev/test/test.png",
    )

    async_session.add(asset)
    await async_session.commit()
    asset_id = asset.id

    # Delete task
    await async_session.delete(task)
    await async_session.commit()

    # Verify asset deleted
    stmt = select(AssetMetadata).where(AssetMetadata.id == asset_id)
    result = await async_session.execute(stmt)
    deleted_asset = result.scalar_one_or_none()
    assert deleted_asset is None


@pytest.mark.asyncio
async def test_notion_sync_timestamp(async_session: AsyncSession, task: Task, channel: Channel):
    """Test notion_synced_at timestamp update."""
    asset = AssetMetadata(
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="test.png",
        storage_strategy="notion",
        asset_url="https://notion.so/files/test.png",
    )

    async_session.add(asset)
    await async_session.commit()
    await async_session.refresh(asset)

    # Initially not synced
    assert asset.notion_synced_at is None

    # Mark as synced
    asset.notion_synced_at = datetime.now(timezone.utc)
    await async_session.commit()
    await async_session.refresh(asset)

    # Verify timestamp set
    assert asset.notion_synced_at is not None
    assert isinstance(asset.notion_synced_at, datetime)


@pytest.mark.asyncio
async def test_query_unsynced_assets(async_session: AsyncSession, task: Task, channel: Channel):
    """Test querying assets WHERE notion_synced_at IS NULL."""
    # Create synced and unsynced assets
    synced_asset = AssetMetadata(
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="synced.png",
        storage_strategy="notion",
        asset_url="https://notion.so/files/synced.png",
        notion_synced_at=datetime.now(timezone.utc),
    )
    unsynced_asset = AssetMetadata(
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="unsynced.png",
        storage_strategy="notion",
        asset_url="https://notion.so/files/unsynced.png",
        notion_synced_at=None,
    )

    async_session.add_all([synced_asset, unsynced_asset])
    await async_session.commit()

    # Query unsynced assets only
    stmt = select(AssetMetadata).where(
        AssetMetadata.task_id == task.id, AssetMetadata.notion_synced_at.is_(None)
    )
    result = await async_session.execute(stmt)
    unsynced = list(result.scalars().all())

    assert len(unsynced) == 1
    assert unsynced[0].asset_name == "unsynced.png"


@pytest.mark.asyncio
async def test_asset_type_filtering(async_session: AsyncSession, task: Task, channel: Channel):
    """Test filtering assets by asset_type."""
    # Create assets of different types
    char_asset = AssetMetadata(
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="char.png",
        storage_strategy="r2",
        asset_url="https://bucket.r2.dev/test/char.png",
    )
    video_asset = AssetMetadata(
        task_id=task.id,
        channel_id=channel.id,
        asset_type="video_clip",
        asset_name="clip.mp4",
        storage_strategy="r2",
        asset_url="https://bucket.r2.dev/test/clip.mp4",
    )

    async_session.add_all([char_asset, video_asset])
    await async_session.commit()

    # Query character assets only
    stmt = select(AssetMetadata).where(
        AssetMetadata.task_id == task.id, AssetMetadata.asset_type == "character"
    )
    result = await async_session.execute(stmt)
    characters = list(result.scalars().all())

    assert len(characters) == 1
    assert characters[0].asset_name == "char.png"


@pytest.mark.asyncio
async def test_storage_strategy_values(async_session: AsyncSession, task: Task, channel: Channel):
    """Test both Notion and R2 storage strategies."""
    # Notion storage
    notion_asset = AssetMetadata(
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="notion_asset.png",
        storage_strategy="notion",
        asset_url="https://prod-files-secure.s3.us-west-2.amazonaws.com/test.png",
    )

    # R2 storage
    r2_asset = AssetMetadata(
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="r2_asset.png",
        storage_strategy="r2",
        asset_url="https://bucket.r2.dev/test/r2_asset.png",
    )

    async_session.add_all([notion_asset, r2_asset])
    await async_session.commit()

    # Verify storage strategies
    await async_session.refresh(notion_asset)
    await async_session.refresh(r2_asset)
    assert notion_asset.storage_strategy == "notion"
    assert r2_asset.storage_strategy == "r2"


@pytest.mark.asyncio
async def test_repr_method(async_session: AsyncSession, task: Task, channel: Channel):
    """Test __repr__ method for debugging."""
    asset = AssetMetadata(
        task_id=task.id,
        channel_id=channel.id,
        asset_type="character",
        asset_name="test.png",
        storage_strategy="r2",
        asset_url="https://bucket.r2.dev/test/test.png",
    )

    async_session.add(asset)
    await async_session.commit()
    await async_session.refresh(asset)

    repr_str = repr(asset)
    assert "AssetMetadata" in repr_str
    assert "character" in repr_str
    assert "test.png" in repr_str
    assert str(asset.id)[:8] in repr_str
