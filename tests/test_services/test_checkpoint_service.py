"""Tests for checkpoint service (Story 6.3).

Tests checkpoint save/load/query operations for step-level and sub-step resume.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from app.models import Task, TaskStatus, PriorityLevel, Channel
from app.services.checkpoint_service import (
    save_step_checkpoint,
    is_step_complete,
    get_step_checkpoint,
    update_step_metadata,
    clear_step_metadata,
)


@pytest.mark.asyncio
async def test_save_and_load_checkpoint(async_session):
    """Verify checkpoint save/load roundtrip (Task 1)."""
    # Create channel first
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()  # Flush to get channel.id

    # Create task
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_ASSETS,
        completed_steps=[],
        step_metadata={},
    )
    async_session.add(task)
    await async_session.commit()

    # Save checkpoint
    await save_step_checkpoint(
        str(task.id),
        "asset_generation",
        {"total_assets": 22, "assets_generated": 22},
        async_session,
    )

    # Verify checkpoint exists
    assert await is_step_complete(str(task.id), "asset_generation", async_session)

    # Load checkpoint
    checkpoint = await get_step_checkpoint(str(task.id), "asset_generation", async_session)
    assert checkpoint["step_name"] == "asset_generation"
    assert checkpoint["outputs"]["total_assets"] == 22
    assert "completed_at" in checkpoint


@pytest.mark.asyncio
async def test_checkpoint_not_found(async_session):
    """Verify is_step_complete returns False when checkpoint doesn't exist (Task 1)."""
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()  # Flush to get channel.id

    # Create task
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.QUEUED,
        completed_steps=[],
        step_metadata={},
    )
    async_session.add(channel)
    async_session.add(task)
    await async_session.commit()

    # Verify no checkpoint exists
    assert not await is_step_complete(str(task.id), "asset_generation", async_session)
    assert await get_step_checkpoint(str(task.id), "asset_generation", async_session) is None


@pytest.mark.asyncio
async def test_checkpoint_deduplication(async_session):
    """Verify same step checkpoint overwrites previous (Task 1)."""
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()  # Flush to get channel.id

    # Create task
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_ASSETS,
        completed_steps=[],
        step_metadata={},
    )
    async_session.add(channel)
    async_session.add(task)
    await async_session.commit()

    # Save checkpoint twice
    await save_step_checkpoint(
        str(task.id),
        "asset_generation",
        {"total_assets": 22, "assets_generated": 15},
        async_session,
    )
    await save_step_checkpoint(
        str(task.id),
        "asset_generation",
        {"total_assets": 22, "assets_generated": 22},
        async_session,
    )

    # Verify only one checkpoint exists
    await async_session.refresh(task)
    assert len(task.completed_steps) == 1
    assert task.completed_steps[0]["outputs"]["assets_generated"] == 22


@pytest.mark.asyncio
async def test_update_step_metadata(async_session):
    """Verify step metadata update (Task 2)."""
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()  # Flush to get channel.id

    # Create task
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_VIDEO,
        completed_steps=[],
        step_metadata={},
    )
    async_session.add(channel)
    async_session.add(task)
    await async_session.commit()

    # Update metadata
    await update_step_metadata(
        str(task.id), "completed_video_clips", [1, 2, 3, 4, 5], async_session
    )

    # Verify metadata updated
    await async_session.refresh(task)
    assert task.step_metadata["completed_video_clips"] == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_clear_step_metadata(async_session):
    """Verify step metadata clear (Task 6)."""
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()  # Flush to get channel.id

    # Create task
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_VIDEO,
        completed_steps=[],
        step_metadata={"completed_video_clips": [1, 2, 3]},
    )
    async_session.add(channel)
    async_session.add(task)
    await async_session.commit()

    # Clear metadata
    await clear_step_metadata(str(task.id), async_session)

    # Verify metadata cleared
    await async_session.refresh(task)
    assert task.step_metadata == {}


@pytest.mark.asyncio
async def test_multiple_checkpoints(async_session):
    """Verify multiple step checkpoints are preserved (Task 2)."""
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()  # Flush to get channel.id

    # Create task
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_VIDEO,
        completed_steps=[],
        step_metadata={},
    )
    async_session.add(channel)
    async_session.add(task)
    await async_session.commit()

    # Save multiple checkpoints
    await save_step_checkpoint(
        str(task.id),
        "asset_generation",
        {"total_assets": 22, "assets_generated": 22},
        async_session,
    )
    await save_step_checkpoint(
        str(task.id),
        "composite_creation",
        {"total_composites": 18, "composites_created": 18},
        async_session,
    )
    await save_step_checkpoint(
        str(task.id), "video_generation", {"total_clips": 18, "clips_generated": 10}, async_session
    )

    # Verify all checkpoints exist
    await async_session.refresh(task)
    assert len(task.completed_steps) == 3
    assert await is_step_complete(str(task.id), "asset_generation", async_session)
    assert await is_step_complete(str(task.id), "composite_creation", async_session)
    assert await is_step_complete(str(task.id), "video_generation", async_session)
